from pathlib import Path

from yellowstone_python.registry.equations import COMPONENTS, validate_inventory


def test_inventory_passes_validation():
    assert validate_inventory(Path(__file__).resolve().parents[1] / "yellowstone_python") == []


def test_inventory_covers_core_components():
    names = [c["component"] for c in COMPONENTS]
    for want in ("six-reach mixing chain",
                 "1-D advection-dispersion replay",
                 "surface heat exchange",
                 "trout suitability and refuge",
                 "snow and soil water"):
        assert want in names


def test_each_component_states_level_and_limits():
    for c in COMPONENTS:
        assert c["model_level"], c["component"]
        assert c["equations"], c["component"]
        assert c["assumptions"], c["component"]
        assert c["limits"], c["component"]
