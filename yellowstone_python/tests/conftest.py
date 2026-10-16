"""Shared test inputs and optional-world readiness fixtures."""
from pathlib import Path

import pytest

from tests.paths import REPO, MIDWAY


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the Python project root."""
    return REPO


@pytest.fixture(scope="session")
def world_root() -> Path:
    """Return the configured Godot world root."""
    return MIDWAY


@pytest.fixture
def world_ready(world_root) -> Path:
    """Require the world inputs and return the world directory."""
    for path in (world_root / "data/world.json", world_root / "data/terrain.f32"):
        if not path.is_file():
            pytest.skip(f"world input missing: {path}")
    return world_root


@pytest.fixture(scope="session")
def resolved_paths(repo_root, world_root):
    """Resolve common path aliases through the shared root fixtures."""
    data = world_root / "data"
    return {"REPO": repo_root, "MIDWAY": world_root, "DATA": data,
            "WORLD_JSON": data / "world.json", "ECO_LIVE": data / "ecosystem.json",
            "ECO_FROZEN": data / "ecosystem.json.pre-python", "TERRAIN_F32": data / "terrain.f32",
            "BASE_CONFIG": repo_root / "configs/baseline.yaml", "CENSUS_JSON": repo_root / "derived/census.json"}


@pytest.fixture(autouse=True)
def required_world_inputs(request, world_root):
    """Report missing world inputs for marked tests."""
    if request.node.get_closest_marker("needs_world"):
        for path in (world_root / "data/world.json", world_root / "data/terrain.f32"):
            if not path.is_file():
                pytest.skip(f"world input missing: {path}")
