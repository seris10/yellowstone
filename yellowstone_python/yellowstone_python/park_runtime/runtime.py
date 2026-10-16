"""Single-owner causal timeline, independent of scene residency or camera direction."""
from __future__ import annotations
from bisect import bisect_right
from collections import OrderedDict
import copy
import math
import uuid
from .contracts import SCHEMA, Domain, Interest, finite, identifier

class ParkRuntime:
    """Orchestration kernel advancing registered domains on one timeline.

    Interacting partitions need a shared flux coordinator inside one domain."""
    model_id = "yellowstone.park_orchestrator.v1"

    def __init__(self, domains: list[Domain], *, quantum_s=1., history_s=30.,
                 epoch_unix=1782064800., max_frames=256):
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
        self.max_frames = int(max_frames)
        self.epoch_unix = finite(epoch_unix, "epoch_unix")
        self.session_id = uuid.uuid4().hex
        self.time_s = times[0]
        self.revision = 0
        self.events = []
        self._event_results = OrderedDict()
        self._frames = []
        self._checkpoints = {}
        self._record()

    def _checkpoint(self):
        return {key: domain.checkpoint() for key, domain in self.domains.items()}

    def _restore_domains(self, checkpoint):
        for key, domain in self.domains.items():
            domain.restore(checkpoint[key])

    def _record(self):
        frame = {"t_s": self.time_s, "epoch_unix": self.epoch_unix + self.time_s,
                 "revision": self.revision,
                 "regions": {key: domain.snapshot() for key, domain in self.domains.items()}}
        if self._frames and self._frames[-1]["t_s"] == self.time_s:
            self._frames[-1] = frame
        else:
            self._frames.append(frame)
        self._checkpoints[self.time_s] = self._checkpoint()

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
        try:
            for domain in self.domains.values():
                domain.advance_to(target_s)
                if not math.isclose(domain.time_s, target_s, rel_tol=0, abs_tol=1e-7):
                    raise RuntimeError(f"domain {domain.domain_id} did not reach the common frontier")
        except BaseException:
            self._restore_domains(old)
            raise
        self.time_s = target_s
        self._record()

    def compute_until(self, target_s):
        target_s = finite(target_s, "target_s")
        while self.time_s < target_s - 1e-9:
            self.advance_one(min(target_s, self.time_s + self.quantum_s))
            if len(self._frames) > self.max_frames:
                raise RuntimeError("lookahead exceeds bounded frame storage; prune or lower horizon")

    def prune(self, presentation_s):
        cutoff = presentation_s - self.history_s
        while len(self._frames) > 2 and self._frames[1]["t_s"] < cutoff:
            old = self._frames.pop(0)
            self._checkpoints.pop(old["t_s"], None)

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
                    self._frames, self._checkpoints)
        checkpoint_time = max(t for t in self._checkpoints if t <= at_s)
        try:
            self._restore_domains(self._checkpoints[checkpoint_time])
            self.time_s = checkpoint_time
            self._frames, self._checkpoints = [], {}
            if at_s > checkpoint_time:
                self.advance_one(at_s)
            self.domains[domain_id].intervene(copy.deepcopy(changes))
            self.revision += 1
            self._frames, self._checkpoints = [], {}
            self._record()
        except BaseException:
            self.time_s, self.revision = original[:2]
            self._restore_domains(original[2])
            self._frames, self._checkpoints = original[3:]
            raise
        result = {"event_id": event_id, "domain_id": domain_id, "at_s": at_s,
                  "changes": copy.deepcopy(changes), "revision": self.revision,
                  "truncate_after_t_s": at_s}
        self.events.append(result)
        self._event_results[event_id] = result
        # Event IDs stay in the save for the whole session.
        return copy.deepcopy(result)

    def save_committed(self, store, world_id: str, presentation_s: float):
        """Persist no speculative future. Resume loses at most one output quantum."""
        if any(not getattr(d, "persistence_supported", True) for d in self.domains.values()):
            raise NotImplementedError("A domain lacks a versioned safe serializer; native persistence is not enabled")
        checkpoint_time = max(t for t in self._checkpoints if t <= presentation_s)
        data = {"epoch_unix": self.epoch_unix, "domains": self._checkpoints[checkpoint_time],
                "domain_models": {k: d.model_id for k, d in self.domains.items()},
                "events": [e for e in self.events if e["at_s"] <= checkpoint_time]}
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
        self._restore_domains(data["domains"])
        self.time_s, self.revision = saved["time_s"], saved["revision"]
        self.epoch_unix = data["epoch_unix"]
        self.events = copy.deepcopy(data["events"])
        self._event_results = OrderedDict((e["event_id"], e) for e in self.events)
        self._frames, self._checkpoints = [], {}
        self._record()
        return True
