"""Single-owner causal timeline, independent of scene residency or camera direction."""
from __future__ import annotations
from bisect import bisect_right
from collections import OrderedDict
import copy
import dataclasses
import math
import sys
import uuid
from .contracts import SCHEMA, Domain, Interest, finite, identifier

def estimate_bytes(value, _seen=None) -> int:
    """Approximate retained bytes of plain data: containers, dataclasses, arrays and scalars."""
    seen = set() if _seen is None else _seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    nbytes = getattr(value, "nbytes", None)
    if isinstance(nbytes, int):
        return sys.getsizeof(value) + nbytes
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(estimate_bytes(k, seen) + estimate_bytes(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(estimate_bytes(item, seen) for item in value)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        size += sum(estimate_bytes(getattr(value, f.name), seen) for f in dataclasses.fields(value))
    return size

class ParkRuntime:
    """Orchestration kernel advancing registered domains on one timeline.

    Couplers exchange interface fluxes between an upstream and a downstream domain each quantum."""
    model_id = "yellowstone.park_orchestrator.v1"

    def __init__(self, domains: list[Domain], *, quantum_s=1., history_s=30.,
                 epoch_unix=1782064800., max_frames=256, checkpoint_interval_s=None,
                 history_byte_cap=None, couplers=()):
        self.domains = {identifier(d.domain_id): d for d in domains}
        if not domains or len(self.domains) != len(domains):
            raise ValueError("nonempty unique domains required")
        times = [float(d.time_s) for d in domains]
        if any(not math.isclose(t, times[0], abs_tol=1e-9) for t in times):
            raise ValueError("all domains must start at a common physical time")
        self.quantum_s = finite(quantum_s, "quantum_s")
        self.history_s = finite(history_s, "history_s")
        if self.quantum_s <= 0 or self.history_s < self.quantum_s or max_frames < 3:
            raise ValueError("invalid timeline limits")
        # The rollback granule: one full checkpoint per interval, frames per quantum.
        self.checkpoint_interval_s = self.quantum_s if checkpoint_interval_s is None else finite(
            checkpoint_interval_s, "checkpoint_interval_s")
        if self.checkpoint_interval_s < self.quantum_s:
            raise ValueError("checkpoint interval shorter than one quantum")
        if history_byte_cap is not None and (isinstance(history_byte_cap, bool)
                                             or not isinstance(history_byte_cap, int) or history_byte_cap <= 0):
            raise ValueError("history_byte_cap must be a positive integer of bytes per domain")
        self.history_byte_cap = history_byte_cap
        self.max_frames = int(max_frames)
        self.epoch_unix = finite(epoch_unix, "epoch_unix")
        self.session_id = uuid.uuid4().hex
        self.time_s = times[0]
        self.revision = 0
        self.events = []
        self.membership = []
        self.couplers = list(couplers)
        for coupler in self.couplers:
            identifier(coupler.upstream_id)
            identifier(coupler.downstream_id)
        self._order_domains()
        self._event_results = OrderedDict()
        self._frames = []
        self._checkpoints = {}
        self._frame_bytes = {}
        self._checkpoint_bytes = {}
        self._record()

    def _order_domains(self):
        """Place each coupler's upstream domain before its downstream domain."""
        keys = list(self.domains)
        for _ in range(len(keys) + 1):
            moved = False
            for coupler in self.couplers:
                if coupler.upstream_id in keys and coupler.downstream_id in keys:
                    up, down = keys.index(coupler.upstream_id), keys.index(coupler.downstream_id)
                    if up > down:
                        keys.insert(down, keys.pop(up))
                        moved = True
            if not moved:
                break
        else:
            raise ValueError("couplers form a cycle")
        self.domains = {key: self.domains[key] for key in keys}

    def _active_couplers(self):
        return [c for c in self.couplers if c.upstream_id in self.domains and c.downstream_id in self.domains]

    def _checkpoint(self):
        return {"domains": {key: domain.checkpoint() for key, domain in self.domains.items()},
                "couplers": [coupler.checkpoint() for coupler in self.couplers]}

    def _restore_domains(self, checkpoint):
        for key, domain in self.domains.items():
            domain.restore(checkpoint["domains"][key])
        for coupler, state in zip(self.couplers, checkpoint.get("couplers", [])):
            coupler.restore(state)

    def _domain_bytes(self, key, item):
        domain = self.domains[key]
        return domain.history_bytes(item) if hasattr(domain, "history_bytes") else estimate_bytes(item)

    def _retained_bytes(self):
        """Estimated retained frame and checkpoint bytes per domain."""
        totals = dict.fromkeys(self.domains, 0)
        for sizes in list(self._frame_bytes.values()) + list(self._checkpoint_bytes.values()):
            for key, size in sizes.items():
                if key in totals:
                    totals[key] += size
        return totals

    def _record(self):
        frame = {"t_s": self.time_s, "epoch_unix": self.epoch_unix + self.time_s,
                 "revision": self.revision,
                 "regions": {key: domain.snapshot() for key, domain in self.domains.items()}}
        if self._frames and self._frames[-1]["t_s"] == self.time_s:
            self._frames[-1] = frame
        else:
            self._frames.append(frame)
        self._frame_bytes[self.time_s] = {k: self._domain_bytes(k, v) for k, v in frame["regions"].items()}
        latest = max(self._checkpoints) if self._checkpoints else None
        if latest is None or latest == self.time_s or self.time_s - latest >= self.checkpoint_interval_s - 1e-9:
            checkpoint = self._checkpoint()
            self._checkpoints[self.time_s] = checkpoint
            self._checkpoint_bytes[self.time_s] = {k: self._domain_bytes(k, v)
                                                   for k, v in checkpoint["domains"].items()}

    def _over_cap(self):
        if self.history_byte_cap is None:
            return []
        return [key for key, size in self._retained_bytes().items() if size > self.history_byte_cap]

    def advance_one(self, target_s):
        """Commit all registered domains atomically at one synchronization boundary."""
        target_s = finite(target_s, "target_s")
        if target_s < self.time_s:
            raise ValueError("time cannot go backwards without restore")
        if target_s == self.time_s:
            return
        if len(self._frames) >= self.max_frames:
            raise RuntimeError("bounded timeline full; prune before advancing")
        old = self._checkpoint()
        start_s = self.time_s
        couplers = self._active_couplers()
        try:
            for coupler in couplers:
                coupler.begin(self.domains[coupler.upstream_id], self.domains[coupler.downstream_id],
                              start_s, target_s)
            for key, domain in self.domains.items():
                for coupler in couplers:
                    if coupler.downstream_id == key:
                        coupler.transfer(self.domains[coupler.upstream_id], domain, start_s, target_s,
                                         self.revision)
                domain.advance_to(target_s)
                if not math.isclose(domain.time_s, target_s, rel_tol=0, abs_tol=1e-7):
                    raise RuntimeError(f"domain {domain.domain_id} did not reach the common frontier")
            self.time_s = target_s
            self._record()
            over = self._over_cap()
            if over:
                raise RuntimeError(f"history byte cap exceeded for {over}; prune or lower the horizon")
        except BaseException:
            self._restore_domains(old)
            self._drop_after(start_s)
            self.time_s = start_s
            raise

    def _drop_after(self, time_s):
        """Discard frames and checkpoints later than a time."""
        self._frames = [frame for frame in self._frames if frame["t_s"] <= time_s]
        for store in (self._checkpoints, self._frame_bytes, self._checkpoint_bytes):
            for t in [t for t in store if t > time_s]:
                del store[t]

    def compute_until(self, target_s):
        """Advance in quanta through a target time inside the frame and byte bounds."""
        target_s = finite(target_s, "target_s")
        self._refuse_horizon(target_s)
        while self.time_s < target_s - 1e-9:
            self.advance_one(min(target_s, self.time_s + self.quantum_s))
            if len(self._frames) > self.max_frames:
                raise RuntimeError("lookahead exceeds bounded frame storage; prune or lower horizon")

    def _refuse_horizon(self, target_s):
        """Refuse a target whose projected retained history exceeds the byte cap."""
        if self.history_byte_cap is None or target_s <= self.time_s or not self._frame_bytes:
            return
        quanta = math.ceil((target_s - self.time_s) / self.quantum_s - 1e-9)
        checkpoints = math.ceil((target_s - max(self._checkpoints)) / self.checkpoint_interval_s - 1e-9)
        frame_sizes = self._frame_bytes[max(self._frame_bytes)]
        checkpoint_sizes = self._checkpoint_bytes[max(self._checkpoint_bytes)]
        for key, retained in self._retained_bytes().items():
            projected = retained + quanta * frame_sizes.get(key, 0) + checkpoints * checkpoint_sizes.get(key, 0)
            if projected > self.history_byte_cap:
                raise ValueError(f"horizon to {target_s} s needs about {projected} bytes for {key}, "
                                 f"above the history byte cap {self.history_byte_cap}")

    def prune(self, presentation_s):
        """Drop frames before the retained window, keeping a checkpoint at or before the first frame."""
        cutoff = presentation_s - self.history_s
        while len(self._frames) > 2 and self._frames[1]["t_s"] < cutoff:
            old = self._frames.pop(0)
            self._frame_bytes.pop(old["t_s"], None)
        first = self._frames[0]["t_s"]
        anchors = [t for t in self._checkpoints if t <= first]
        keep_from = max(anchors) if anchors else first
        for t in [t for t in self._checkpoints if t < keep_from]:
            del self._checkpoints[t]
            self._checkpoint_bytes.pop(t, None)

    def packet(self, presentation_s: float, interest: Interest = Interest()):
        """Return only a bracketing pair; never serialize the complete future buffer."""
        times = [frame["t_s"] for frame in self._frames]
        if presentation_s < times[0] - 1e-9 or presentation_s > times[-1] + 1e-9:
            raise ValueError("presentation time is outside completed history")
        i = max(0, bisect_right(times, presentation_s) - 1)
        j = min(i + 1, len(times) - 1)
        ids = set(interest.region_ids) if interest.region_ids else set(self.domains)
        if ids - self.domains.keys():
            raise ValueError("unknown subscription region")
        selected = []
        for index in sorted({i, j}):
            frame = self._frames[index]
            selected.append({**frame, "regions": {k: frame["regions"][k] for k in sorted(ids)}})
        return copy.deepcopy({"schema": SCHEMA, "session_id": self.session_id,
            "revision": self.revision, "presentation_s": presentation_s,
            "epoch_unix": self.epoch_unix, "completed_s": self.time_s,
            "bracket": selected, "interest_sequence": interest.sequence,
            "unloaded_regions_continue": True})

    def intervene(self, event_id: str, domain_id: str, at_s: float, changes: dict):
        """Apply an intervention at its effective time and recompute later frames.

        Events older than the latest accepted intervention are rejected."""
        identifier(event_id)
        if event_id in self._event_results:
            previous = self._event_results[event_id]
            if previous["domain_id"] != domain_id or previous["at_s"] != at_s or previous["changes"] != changes:
                raise ValueError("event id reused with different contents")
            return copy.deepcopy(previous)
        if domain_id not in self.domains:
            raise ValueError("unknown intervention domain")
        at_s = finite(at_s, "at_s")
        if not self._frames[0]["t_s"] <= at_s <= self.time_s:
            raise ValueError("event is outside retained history")
        if self.events and at_s < self.events[-1]["at_s"]:
            raise ValueError("late event precedes committed event history")
        original = (self.time_s, self.revision, self._checkpoint(),
                    self._frames, self._checkpoints, self._frame_bytes, self._checkpoint_bytes)
        checkpoint_time = max(t for t in self._checkpoints if t <= at_s)
        try:
            self._restore_domains(self._checkpoints[checkpoint_time])
            self.time_s = checkpoint_time
            self._reset_history()
            # Replay on the quantum grid so coupler intervals match the original timeline.
            while self.time_s < at_s - 1e-9:
                self.advance_one(min(at_s, self.time_s + self.quantum_s))
            self.domains[domain_id].intervene(copy.deepcopy(changes))
            self.revision += 1
            self._reset_history()
        except BaseException:
            self.time_s, self.revision = original[:2]
            self._restore_domains(original[2])
            (self._frames, self._checkpoints, self._frame_bytes, self._checkpoint_bytes) = original[3:]
            raise
        result = {"event_id": event_id, "domain_id": domain_id, "at_s": at_s,
                  "changes": copy.deepcopy(changes), "revision": self.revision,
                  "truncate_after_t_s": at_s}
        self.events.append(result)
        self._event_results[event_id] = result
        # Event IDs stay in the save for the whole session.
        return copy.deepcopy(result)

    def _reset_history(self):
        """Start retained history at the current state."""
        self._frames, self._checkpoints, self._frame_bytes, self._checkpoint_bytes = [], {}, {}, {}
        self._record()

    def add_domain(self, domain: Domain) -> dict:
        """Admit a domain at the current quantum boundary; rollback history restarts here."""
        key = identifier(domain.domain_id)
        if key in self.domains:
            raise ValueError("domain id already registered")
        if not math.isclose(float(domain.time_s), self.time_s, rel_tol=0, abs_tol=1e-9):
            raise ValueError("a domain joins at the runtime frontier")
        self.domains[key] = domain
        try:
            self._order_domains()
        except ValueError:
            del self.domains[key]
            raise
        return self._membership_entry("add", domain)

    def remove_domain(self, domain_id: str) -> dict:
        """Retire a domain at the current quantum boundary; returns its final checkpoint and stores."""
        if domain_id not in self.domains:
            raise ValueError("unknown domain")
        if len(self.domains) == 1:
            raise ValueError("the runtime keeps at least one domain")
        domain = self.domains[domain_id]
        checkpoint = domain.checkpoint()
        del self.domains[domain_id]
        for coupler in self.couplers:
            if domain_id in (coupler.upstream_id, coupler.downstream_id) and hasattr(coupler, "detach"):
                coupler.detach(domain_id, self.time_s)
        entry = self._membership_entry("remove", domain)
        return {"entry": entry, "checkpoint": checkpoint}

    def _membership_entry(self, action, domain):
        stores = domain.stores() if hasattr(domain, "stores") else None
        entry = {"t_s": self.time_s, "action": action, "domain_id": domain.domain_id,
                 "model_id": domain.model_id, "revision": self.revision,
                 "stores": None if stores is None else {"water_m3": stores.water_m3, "heat_j": stores.heat_j,
                                                        "solute_kg": stores.solute_kg}}
        self.membership.append(entry)
        # Interventions never replay across a membership change.
        self._reset_history()
        return copy.deepcopy(entry)

    def save_committed(self, store, world_id: str, presentation_s: float):
        """Persist no speculative future. Resume loses at most one checkpoint interval."""
        if any(not getattr(d, "persistence_supported", True) for d in self.domains.values()):
            raise NotImplementedError("A domain lacks a versioned safe serializer; native persistence is not enabled")
        checkpoint_time = max(t for t in self._checkpoints if t <= presentation_s)
        checkpoint = self._checkpoints[checkpoint_time]
        data = {"epoch_unix": self.epoch_unix, "domains": checkpoint["domains"],
                "domain_models": {k: d.model_id for k, d in self.domains.items()},
                "events": [e for e in self.events if e["at_s"] <= checkpoint_time],
                "membership": [m for m in self.membership if m["t_s"] <= checkpoint_time]}
        if self.couplers:
            data["couplers"] = checkpoint["couplers"]
        store.save(world_id, self.model_id, checkpoint_time, self.revision, data, data["events"])
        return checkpoint_time

    def load_committed(self, store, world_id: str):
        saved = store.load(world_id, self.model_id)
        if saved is None:
            return False
        data = saved["checkpoint"]
        expected = {k: d.model_id for k, d in self.domains.items()}
        if data["domain_models"] != expected:
            raise ValueError("domain versions changed; explicit model migration required")
        self._restore_domains({"domains": data["domains"], "couplers": data.get("couplers", [])})
        self.time_s, self.revision = saved["time_s"], saved["revision"]
        self.epoch_unix = data["epoch_unix"]
        self.events = copy.deepcopy(data["events"])
        self.membership = copy.deepcopy(data.get("membership", []))
        self._event_results = OrderedDict((e["event_id"], e) for e in self.events)
        self._reset_history()
        return True
