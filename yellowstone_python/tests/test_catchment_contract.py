"""Isolated configuration, phase and scaling checks for runoff exchange."""
import pytest
import yaml

from yellowstone_python.build import predicted_quantities, validate_config
from yellowstone_python.registry.coupling import validate_contract
from yellowstone_python.land.snow_season import catchment_runoff_m3_s


@pytest.fixture(autouse=True)
def config_path(monkeypatch, repo_root):
    monkeypatch.setitem(globals(), "BASE", repo_root / "configs/baseline.yaml")


def _cfg():
    return yaml.safe_load(BASE.read_text())


def test_runoff_quantity_is_recorded_as_predicted_not_prescribed():
    cfg = _cfg()
    assert predicted_quantities(cfg) == []
    cfg["hydro"]["catchment"]["area_m2"] = 1e6
    assert predicted_quantities(cfg) == ["snow_runoff_increment"]


def test_config_rejects_a_nonpositive_catchment():
    bad = _cfg()
    bad["hydro"]["catchment"]["area_m2"] = 0.0
    with pytest.raises(ValueError):
        validate_config(bad)


def test_catchment_runoff_rejects_bad_inputs():
    patches = [{"id": "a", "snow_mm": 0.0, "moisture": 0.5}]
    ledger = {"runoff_mm": 10.0, "days": 30, "units": "mm"}
    with pytest.raises(ValueError):
        catchment_runoff_m3_s(patches, ledger, catchment_area_m2=0.0)
    with pytest.raises(ValueError):
        catchment_runoff_m3_s([], ledger, catchment_area_m2=1e8)
    with pytest.raises(ValueError):
        catchment_runoff_m3_s(patches, {"runoff_mm": 1.0, "days": 0},
                              catchment_area_m2=1e8)


def test_catchment_runoff_scales_the_ledger_depth():
    patches = [{"id": f"p{i}", "snow_mm": 0.0, "moisture": 0.5}
               for i in range(3)]
    ledger = {"runoff_mm": 60.0, "days": 30, "units": "mm"}
    out = catchment_runoff_m3_s(patches, ledger, catchment_area_m2=1e8)
    expected = (20.0 / 1000.0) * 1e8 / (30 * 86400.0)
    assert out["runoff_m3_s"] == pytest.approx(expected, rel=1e-6)
    assert out["modeled_patch_count"] == 3
    assert out["mean_runoff_depth_mm_d"] == pytest.approx(20.0 / 30, rel=1e-6)


def test_coupling_contract_records_the_snow_exchange():
    assert validate_contract() == []
    from yellowstone_python.registry.coupling import EXCHANGES
    ids = {r["exchange_id"] for r in EXCHANGES}
    assert "snow_runoff_discharge" in ids
