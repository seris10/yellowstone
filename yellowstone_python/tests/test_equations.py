from yellowstone_python.equations import COMPONENTS, validate_inventory


def test_inventory_passes_validation():
    assert validate_inventory() == []


def test_inventory_covers_core_components():
    names = [c["component"] for c in COMPONENTS]
    for want in ("M01 six-reach mixing chain",
                 "M01b 1-D advection-dispersion replay",
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
