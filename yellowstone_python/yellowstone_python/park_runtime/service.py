"""Loopback service with a worker-owned simulation and immutable publications.

Runs as a separate process from Godot; no solver runs in an HTTP handler."""
from __future__ import annotations
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import json
import logging
import math
import queue
import threading
import time
import uuid
from .contracts import Focus, Interest, finite
from .state_store import canonical

MAX_REQUEST = 64 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
RESIDENCY_SCHEMA = "yellowstone.park_residency.v1"

def _rate(value) -> float:
    scale = finite(value, "time_scale")
    if not 0 < scale <= 600:
        raise ValueError("time_scale must be in (0,600]")
    return scale

class RuntimeService:
    """Own the model clock in one worker thread; a residency manager adds focus-driven tiers.

    With residency the walker sits at chainage 0 at rest until the first focus."""
    def __init__(self, runtime, *, horizon_s=5., time_scale=1., residency=None, chainage=None):
        if residency is not None and (runtime is not residency.runtime or chainage is None):
            raise ValueError("a residency service runs its manager's runtime and needs a chainage map")
        self.runtime = runtime
        self.residency, self.chainage = residency, chainage
        self.horizon_s = finite(horizon_s, "horizon_s")
        self.time_scale = finite(time_scale, "time_scale")
        if self.horizon_s < runtime.quantum_s or not 0 < self.time_scale <= 600:
            raise ValueError("invalid horizon or time scale")
        if (self.horizon_s + runtime.history_s) / runtime.quantum_s + 4 > runtime.max_frames:
            raise ValueError("timeline storage cannot hold configured horizon and history")
        self.presentation_s = runtime.time_s
        self.interest = Interest()
        self.focus = None
        self.walker = None
        self.residency_report = None
        self.paused = False
        self.error = None
        self.commands = queue.Queue(maxsize=64)
        self._results = OrderedDict()
        self._publication = b"{}"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._worker = None
        self._wall_origin = time.monotonic()
        if self.residency is not None:
            self._update_residency()
        self._publish()

    def _update_residency(self):
        """Apply the residency policy at the frontier with the latest focus."""
        position_m, velocity_mps = (0.0, 0.0) if self.walker is None else (self.walker[0], self.walker[2])
        self.residency_report = self.residency.update(time.monotonic() - self._wall_origin, position_m,
                                                      velocity_mps, self.time_scale)

    def presentation_rate(self) -> float:
        """Return the presentation clock rate: the requested scale, or the held rate below it."""
        if self.residency_report is None:
            return self.time_scale
        return min(self.time_scale, self.residency_report["effective_rate"])

    def residency_block(self) -> dict:
        """Return the published residency report for the latest focus."""
        r = self.residency_report
        walker = None
        if self.walker is not None:
            walker = {"chainage_m": self.walker[0], "lateral_m": self.walker[1],
                      "along_velocity_mps": self.walker[2], "segment": r["segment"],
                      "representation": r["walker_on"], "temperature_c": r["walker_temperature_c"]}
        return {"schema": RESIDENCY_SCHEMA, "focus_sequence": None if self.focus is None else self.focus.sequence,
                "t_s": r["t_s"], "active": r["fine"], "activating": r["activating"], "retiring": r["retiring"],
                "coarse": r["coarse"], "reach": r["reach"], "ranked": [list(item) for item in r["ranked"]],
                "effective_rate": r["effective_rate"], "requested_rate": self.time_scale, "held": r["held"],
                "lead_wall_s": r["lead_wall_s"], "capacity_cell_s_per_s": r["capacity_cell_s_per_s"],
                "worker_rate_cell_s_per_s": r["worker_rate"], "walker": walker}

    def _publish(self):
        packet = self.runtime.packet(self.presentation_s, self.interest)
        packet.update({"paused": self.paused, "time_scale": self.time_scale,
                       "clock_held": self.presentation_s >= self.runtime.time_s - 1e-8,
                       "worker_error": self.error, "horizon_s": self.horizon_s})
        if self.residency is not None:
            packet["residency"] = self.residency_block()
        payload = canonical(packet)
        if len(payload) > MAX_RESPONSE:
            raise RuntimeError("publication exceeds 16 MiB: add region/channel filtering or binary fields")
        with self._lock:
            self._publication = payload

    def publication(self):
        with self._lock:
            return self._publication  # immutable bytes; no live solver access

    def submit(self, kind: str, payload: dict):
        if kind not in {"interest", "clock", "intervene", "focus"}:
            raise ValueError("unsupported command")
        if kind == "interest":
            Interest.parse(payload)
        if kind == "focus":
            if self.residency is None:
                raise ValueError("this service has no residency policy for focus")
            Focus.parse(payload)
        command_id = uuid.uuid4().hex
        self.commands.put_nowait((command_id, kind, payload))
        return command_id

    def result(self, command_id):
        with self._lock:
            return self._results.get(command_id, {"status": "pending_or_expired"})

    def _command(self, kind, payload):
        if kind == "interest":
            candidate = Interest.parse(payload)
            if set(candidate.region_ids) - self.runtime.domains.keys():
                raise ValueError("unknown interest region")
            if candidate.sequence >= self.interest.sequence:
                self.interest = candidate
            return {"interest_sequence": self.interest.sequence}
        if kind == "clock":
            paused = self.paused
            scale = self.time_scale
            if "paused" in payload:
                if not isinstance(payload["paused"], bool):
                    raise ValueError("paused must be boolean")
                paused = payload["paused"]
            if "time_scale" in payload:
                scale = _rate(payload["time_scale"])
            self.paused, self.time_scale = paused, scale
            return {"paused": self.paused, "time_scale": self.time_scale}
        if kind == "focus":
            focus = Focus.parse(payload)
            if self.focus is not None and focus.sequence < self.focus.sequence:
                return {"accepted": False, "focus_sequence": self.focus.sequence}
            scale = self.time_scale if focus.time_scale is None else _rate(focus.time_scale)
            chainage_m, lateral_m, index = self.chainage.locate(focus.position_m[0], focus.position_m[2])
            along = self.chainage.along_channel(index, focus.velocity_mps[0], focus.velocity_mps[2])
            self.focus, self.walker, self.time_scale = focus, (chainage_m, lateral_m, along), scale
            self._update_residency()
            return {"accepted": True, **self.residency_block()}
        if payload.get("session_id") != self.runtime.session_id:
            raise ValueError("stale session; obtain a current publication")
        # Segment residency owns rollback across representation swaps.
        owner = self.runtime if self.residency is None else self.residency
        if payload.get("event_id") in self.runtime._event_results:
            return owner.intervene(payload["event_id"], payload["domain_id"], payload["at_s"], payload["changes"])
        if payload.get("revision") != self.runtime.revision:
            raise ValueError("stale revision; obtain a current publication")
        at_s = finite(payload["at_s"], "at_s")
        if abs(at_s - self.presentation_s) > 2 * self.runtime.quantum_s:
            raise ValueError("intervention time differs from the presentation clock")
        result = owner.intervene(payload["event_id"], payload["domain_id"], at_s, payload["changes"])
        self.presentation_s = at_s
        return result

    def start(self):
        if self._worker is not None:
            raise RuntimeError("already started")
        self._worker = threading.Thread(target=self._work, name="park-model-owner", daemon=True)
        self._worker.start()

    def _work(self):
        last_wall = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            elapsed = now - last_wall
            last_wall = now
            try:
                for _ in range(8):
                    try:
                        command_id, kind, payload = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        result = {"status": "done", "result": self._command(kind, payload)}
                    except Exception as exc:
                        result = {"status": "rejected", "error": str(exc)}
                    with self._lock:
                        self._results[command_id] = result
                        while len(self._results) > 256:
                            self._results.popitem(last=False)
                if not self.paused and self.error is None:
                    # Presentation time is capped at the computed frontier.
                    self.presentation_s = min(self.runtime.time_s,
                                              self.presentation_s + elapsed * self.presentation_rate())
                goal = math.ceil((self.presentation_s + self.horizon_s) / self.runtime.quantum_s) * self.runtime.quantum_s
                if self.residency is not None and self.error is None:
                    self._update_residency()
                if self.error is None and self.runtime.time_s < goal:
                    next_boundary = (math.floor(self.runtime.time_s / self.runtime.quantum_s + 1e-8) + 1) * self.runtime.quantum_s
                    if self.residency is None:
                        self.runtime.advance_one(min(goal, next_boundary))
                    else:
                        self.residency.advance(min(goal, next_boundary), presentation_s=self.presentation_s)
                self.runtime.prune(self.presentation_s)
                self._publish()
            except Exception as exc:
                logging.exception("park worker paused")
                self.error, self.paused = f"{type(exc).__name__}: {exc}", True
                try:
                    self._publish()
                except Exception:
                    pass  # preserve last immutable valid packet; log failure above
            self._stop.wait(.01)

    def close(self):
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=30)
            if self._worker.is_alive():
                raise TimeoutError("model job did not stop; use smaller solver quanta")


def make_server(service: RuntimeService, host="127.0.0.1", port=8766):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("this unauthenticated service is loopback-only")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_json(self, value, code=200):
            payload = value if isinstance(value, bytes) else canonical(value)
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/park/state":
                self.send_json(service.publication())
            elif path.startswith("/api/park/commands/"):
                self.send_json(service.result(path.rsplit("/", 1)[-1]))
            else:
                self.send_json({"error": "not found"}, 404)

        def do_POST(self):
            # Browser origins are rejected so web pages cannot drive the local model.
            if self.headers.get("Origin"):
                self.send_json({"error": "browser origins are not accepted"}, 403)
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("application/json required")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_REQUEST:
                    raise ValueError("invalid request size")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("object required")
                path = urlparse(self.path).path
                if not path.startswith("/api/park/"):
                    raise ValueError("invalid route")
                kind = path[len("/api/park/"):]
                command_id = service.submit(kind, data)
                self.send_json({"command_id": command_id, "status": "queued"}, 202)
            except queue.Full:
                self.send_json({"error": "command queue full"}, 429)
            except (ValueError, TypeError, KeyError) as exc:
                self.send_json({"error": str(exc)}, 400)
    return ThreadingHTTPServer((host, port), Handler)
