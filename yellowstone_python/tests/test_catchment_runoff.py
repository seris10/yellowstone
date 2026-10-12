"""Tests for the snow-runoff discharge coupling and the overland null result."""
import math

import pytest
import yaml

from yellowstone_python.build import (load_inputs, predicted_quantities,
                                       simulate_all, validate_config)
from yellowstone_python.coupling import validate_contract
from yellowstone_python.snow_season import catchment_runoff_m3_s

from paths import BASE_CONFIG as BASE
from paths import MIDWAY as _MIDWAY
# Measured: USGS 06036805 Firehole at Old Faithful, 39.5 sqmi.
USGS_AREA_M2 = 39.5 * 2_589_988.110336


def _cfg():
    return yaml.safe_load(open(BASE).read())


def _sim(**overrides):
    cfg = _cfg()
    cfg["hydro"].setdefault("catchment", {})["area_m2"] = overrides.pop(
        "area_m2", None)
    for key, value in overrides.items():
        cfg[key] = value
    baseline, world, deps, tfns = load_inputs(cfg)
    return simulate_all(cfg, baseline, world, tfns)


def test_baseline_keeps_snow_hydrology_storage_only():
    res = _sim()
    assert res["catchment"]["enabled"] is False
    assert res["boundary_m3s"] == pytest.approx(res["baseflow_m3s"])
    assert "storage-only" in res["catchment"]["provenance"]


def test_configured_catchment_adds_runoff_to_the_boundary():
    res = _sim(area_m2=USGS_AREA_M2)
    catchment = res["catchment"]
    assert catchment["enabled"] is True
    assert catchment["runoff_m3_s"] > 0.0
    assert res["boundary_m3s"] == pytest.approx(
        res["baseflow_m3s"] + catchment["runoff_m3_s"])


def test_snow_melt_reaches_the_published_trout():
    off = _sim()
    on = _sim(area_m2=USGS_AREA_M2)
    off_trout = [w for w in off["variant"]["wildlife"] if "trout" in w["id"]][0]
    on_trout = [w for w in on["variant"]["wildlife"] if "trout" in w["id"]][0]
    assert on["boundary_m3s"] != off["boundary_m3s"]
    assert on_trout["refuge_cell_id"] != off_trout["refuge_cell_id"]


def test_snow_window_changes_the_discharge():
    summer = _sim(area_m2=USGS_AREA_M2)
    winter = _sim(area_m2=USGS_AREA_M2,
                  snow={"season": "winter", "days": 120,
                        "precip_mm_d": 2.0, "air_c_by_day": [-5.0] * 120})
    assert winter["catchment"]["runoff_m3_s"] > summer["catchment"]["runoff_m3_s"]
    assert winter["boundary_m3s"] > summer["boundary_m3s"]


def test_both_hydrology_models_see_the_same_discharge():
    res = _sim(area_m2=USGS_AREA_M2)
    forcing = res["replay_doc"]["forcing"]["boundary_m3_s"]
    assert forcing == pytest.approx(res["boundary_m3s"], rel=1e-9)
    assert res["river_state"][0]["flow_m3s"] == pytest.approx(
        res["boundary_m3s"], rel=1e-9)
    # The mixing chain's integrated inflow scales with the same discharge.
    off = _sim()
    ratio = res["hydro_ledger"]["boundary_in"] / off["hydro_ledger"]["boundary_in"]
    assert ratio == pytest.approx(res["boundary_m3s"] / off["boundary_m3s"],
                                  rel=1e-6)


def test_runoff_quantity_is_recorded_as_predicted_not_prescribed():
    cfg = _cfg()
    assert predicted_quantities(cfg) == []
    cfg["hydro"]["catchment"]["area_m2"] = USGS_AREA_M2
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
    from yellowstone_python.coupling import EXCHANGES
    ids = {r["exchange_id"] for r in EXCHANGES}
    assert "snow_runoff_discharge" in ids


def test_overland_field_carries_no_runoff_signal():
    from yellowstone_python.overland_flow import run_overland
    result = run_overland(_MIDWAY, rain_mm_h=2.0, grid=64, cell_m=8.0,
                          sim_s=120.0)
    assert result["surface_runoff"]["carries_runoff_signal"] is False
    assert result["surface_runoff"]["outflow_m3"] == 0.0
    assert "no water left the domain" in result["surface_runoff"]["note"]
    assert math.isclose(result["balance"]["rel_error"], 0.0, abs_tol=1e-9)
