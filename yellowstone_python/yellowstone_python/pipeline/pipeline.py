"""Ordered simulation orchestration with checked stage dependencies."""
from __future__ import annotations

from yellowstone_python.pipeline.stages import weather, thermal, vegetation, land, river, foodweb, insects, fish, grazers, mammals, finalize

STAGES = (weather, thermal, vegetation, land, river, foodweb, insects, fish, grazers, mammals, finalize,)

def stage_contracts() -> list[dict]:
    """Return the ordered modules and state keys used by the build stages."""
    return [{"name": stage.__name__.rsplit(".", 1)[-1],
             "module": stage.__name__, "reads": list(stage.READS),
             "writes": list(stage.WRITES)} for stage in STAGES]

def validate_stage_dependencies() -> None:
    """Require each stage input to be an initial input or an earlier output."""
    available = {"baseline", "world", "tfns"}
    for stage in STAGES:
        missing = set(stage.READS) - available
        if missing:
            raise ValueError(f"{stage.__name__} missing inputs {sorted(missing)}")
        available.update(stage.WRITES)


def simulate_all(cfg: dict, baseline: dict, world: dict, tfns) -> dict:
    """Run the ordered model stages and return their result."""
    validate_stage_dependencies()
    state = {"baseline": baseline, "world": world, "tfns": tfns}
    for stage in STAGES:
        stage.run(state, cfg)
    return state["result"]
