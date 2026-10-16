"""In-process bridge to the existing LiveEngine with one shared clock.

Checkpoints stay native in memory and encode to a versioned document when persisted."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .contracts import finite, identifier

@dataclass(frozen=True)
class NativeCheckpoint:
    """Native engine checkpoint that encodes itself when a store persists it."""
    engine: Any
    native: dict
    revision: int
    frames: list

    def to_portable(self) -> dict:
        """Return the versioned JSON document for this checkpoint."""
        return self.engine.export_state(self.native, revision=self.revision)

class LegacyLiveDomain:
    model_id = "yellowstone.legacy_live_bridge.v1"
    persistence_supported = True

    def __init__(self, engine, domain_id="midway.firehole"):
        if engine.worker_running:
            raise ValueError("construct LiveEngine with start_worker=False; only ParkRuntime owns advancement")
        self.engine = engine
        self.domain_id = identifier(domain_id)

    @property
    def time_s(self):
        return float(self.engine.river.time_s)

    def advance_to(self, target_s):
        self.engine.compute_until(finite(target_s, "target_s"))
        # The parent orchestrator retains history. Avoid an unbounded second history.
        self.engine.trim_history(self.time_s - max(self.engine.horizon_s, 60.))

    def snapshot(self):
        return {"domain_id": self.domain_id, "model_id": self.model_id,
                "quality": "existing_solver_claims_unchanged", "t_s": self.time_s,
                "frame": self.engine.snapshot_at_frontier()}

    def checkpoint(self):
        return {"model_id": self.model_id,
                "state": NativeCheckpoint(self.engine, self.engine.checkpoint_state(),
                                          self.engine.revision, [self.engine.snapshot_at_frontier()])}

    def restore(self, checkpoint):
        if checkpoint["model_id"] != self.model_id:
            raise ValueError("legacy checkpoint identity mismatch")
        state = checkpoint["state"]
        if isinstance(state, NativeCheckpoint):
            self.engine.restore_state(state.native, revision=state.revision, frames=state.frames)
        else:
            self.engine.import_state(state)

    def intervene(self, changes):
        self.engine.command("control", {"at_s": self.time_s, "changes": changes})
