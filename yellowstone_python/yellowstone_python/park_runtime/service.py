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
from .contracts import Interest, finite
from .state_store import canonical

MAX_REQUEST = 64 * 1024
MAX_RESPONSE = 16 * 1024 * 1024

class RuntimeService:
    def __init__(self, runtime, *, horizon_s=5., time_scale=1.):
        self.runtime = runtime
        self.horizon_s = finite(horizon_s, "horizon_s")
        self.time_scale = finite(time_scale, "time_scale")
        if self.horizon_s < runtime.quantum_s or not 0 < self.time_scale <= 600:
            raise ValueError("invalid horizon or time scale")
        if (self.horizon_s + runtime.history_s) / runtime.quantum_s + 4 > runtime.max_frames:
            raise ValueError("timeline storage cannot hold configured horizon and history")
        self.presentation_s = runtime.time_s
        self.interest = Interest()
        self.paused = False
        self.error = None
        self.commands = queue.Queue(maxsize=64)
        self._results = OrderedDict()
        self._publication = b"{}"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._worker = None
        self._publish()

    def _publish(self):
        packet = self.runtime.packet(self.presentation_s, self.interest)
        packet.update({"paused": self.paused, "time_scale": self.time_scale,
                       "clock_held": self.presentation_s >= self.runtime.time_s - 1e-8,
                       "worker_error": self.error, "horizon_s": self.horizon_s})
        payload = canonical(packet)
        if len(payload) > MAX_RESPONSE:
            raise RuntimeError("publication exceeds 16 MiB: add region/channel filtering or binary fields")
        with self._lock:
            self._publication = payload

    def publication(self):
        with self._lock:
            return self._publication  # immutable bytes; no live solver access

    def submit(self, kind: str, payload: dict):
        if kind not in {"interest", "clock", "intervene"}:
            raise ValueError("unsupported command")
        if kind == "interest":
            Interest.parse(payload)
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
                scale = finite(payload["time_scale"], "time_scale")
                if not 0 < scale <= 600:
                    raise ValueError("time_scale must be in (0,600]")
            self.paused, self.time_scale = paused, scale
            return {"paused": self.paused, "time_scale": self.time_scale}
        if payload.get("session_id") != self.runtime.session_id:
            raise ValueError("stale session; obtain a current publication")
        if payload.get("event_id") in self.runtime._event_results:
            return self.runtime.intervene(payload["event_id"], payload["domain_id"],
                                          payload["at_s"], payload["changes"])
        if payload.get("revision") != self.runtime.revision:
            raise ValueError("stale revision; obtain a current publication")
        at_s = finite(payload["at_s"], "at_s")
        if abs(at_s - self.presentation_s) > 2 * self.runtime.quantum_s:
            raise ValueError("intervention time differs from the presentation clock")
        result = self.runtime.intervene(payload["event_id"], payload["domain_id"], at_s, payload["changes"])
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
                                              self.presentation_s + elapsed * self.time_scale)
                goal = math.ceil((self.presentation_s + self.horizon_s) / self.runtime.quantum_s) * self.runtime.quantum_s
                if self.error is None and self.runtime.time_s < goal:
                    next_boundary = (math.floor(self.runtime.time_s / self.runtime.quantum_s + 1e-8) + 1) * self.runtime.quantum_s
                    self.runtime.advance_one(min(goal, next_boundary))
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
