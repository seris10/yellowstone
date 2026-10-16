import pytest

from yellowstone_python.thermal_features.geochemistry import MIDWAY_POOLS, SubstrateError, check_midway_shells, forbid_whitening, rules_doc, system_for_feature


def test_midway_is_siliceous():
    assert system_for_feature("hot_spring") == "siliceous_sinter"
    assert system_for_feature("travertine_terrace") == "travertine"
    with pytest.raises(SubstrateError):
        system_for_feature("lava_fountain")


def test_whitening_refused():
    with pytest.raises(SubstrateError):
        forbid_whitening("pool_1034_0", "white_calcite")
    forbid_whitening("pool_1034_0", "green_mat")  # own system is fine


def test_all_midway_shells_validate():
    shells = [{"id": pid, "substrate": "siliceous_sinter_illustrative"}
              for pid in MIDWAY_POOLS]
    assert check_midway_shells(shells) == []
    bad = [{"id": "pool_1034_0", "substrate": "travertine_illustrative"}]
    assert len(check_midway_shells(bad)) == 1


def test_rules_cite_source():
    assert any("nps.gov" in s.get("url", "") for s in rules_doc()["sources"])
