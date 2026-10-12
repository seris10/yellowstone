"""Shared repository path resolution for tests (no absolute paths)."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIDWAY = Path(os.environ.get("YELLOWSTONE_WORLD")
              or REPO.parent / "yellowstone_midway")
DATA = MIDWAY / "data"
WORLD_JSON = DATA / "world.json"
ECO_LIVE = DATA / "ecosystem.json"
ECO_FROZEN = DATA / "ecosystem.json.pre-python"
TERRAIN_F32 = DATA / "terrain.f32"
BASE_CONFIG = REPO / "configs" / "baseline.yaml"
CENSUS_JSON = REPO / "derived" / "census.json"
