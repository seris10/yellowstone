"""Tests for the snow-runoff discharge coupling and the overland null result."""
import json
import math

import pytest
import yaml

from yellowstone_python.build import (load_inputs, predicted_quantities,
                                       simulate_all, validate_config)
from yellowstone_python.registry.coupling import validate_contract
from yellowstone_python.land.snow_season import catchment_runoff_m3_s

# Measured: USGS 06036805 Firehole at Old Faithful, 39.5 sqmi.
USGS_AREA_M2 = 39.5 * 2_589_988.110336


def _cfg():
    return yaml.safe_load(open(BASE).read())


@pytest.fixture(scope="module")
def simulate_case(repo_root, world_root):
    """Reuse real simulations only for identical configs read by these assertions."""
    cache = {}

    def run(**overrides):
        cfg = yaml.safe_load((repo_root / "configs/baseline.yaml").read_text())
        cfg["world_root"] = str(world_root)
        cfg["hydro"].setdefault("catchment", {})["area_m2"] = overrides.pop("area_m2", None)
        cfg.update(overrides)
        key = json.dumps(cfg, sort_keys=True)
        if key not in cache:
            baseline, world, deps, tfns = load_inputs(cfg)
            cache[key] = simulate_all(cfg, baseline, world, tfns)
        return cache[key]

    return run


def test_baseline_keeps_snow_hydrology_storage_only(simulate_case):
    res = simulate_case()
    assert res["catchment"]["enabled"] is False
    assert res["boundary_m3s"] == pytest.approx(res["baseflow_m3s"])
    assert "storage-only" in res["catchment"]["provenance"]


def test_configured_catchment_adds_runoff_to_the_boundary(simulate_case):
    res = simulate_case(area_m2=USGS_AREA_M2)
    catchment = res["catchment"]
    assert catchment["enabled"] is True
    assert catchment["runoff_m3_s"] > 0.0
    assert res["boundary_m3s"] == pytest.approx(
        res["baseflow_m3s"] + catchment["runoff_m3_s"])


def test_snow_melt_reaches_the_published_trout(simulate_case):
    """Snowmelt discharge changes the trout's refuge inputs."""
    off = simulate_case()
    on = simulate_case(area_m2=USGS_AREA_M2)
    off_trout = [w for w in off["variant"]["wildlife"] if "trout" in w["id"]][0]
    on_trout = [w for w in on["variant"]["wildlife"] if "trout" in w["id"]][0]
    assert on["boundary_m3s"] != off["boundary_m3s"]
    # Tolerance from a 9 percent discharge increase: temperature shifts about 0.1 C, walk_mps and hold_seconds track velocity and activity. Any one of these must move for the coupling to be live.
    temp_delta = abs(float(on_trout.get("reach_temp_c", 0.0))
                     - float(off_trout.get("reach_temp_c", 0.0)))
    walk_delta = abs(float(on_trout.get("walk_mps", 0.0))
                     - float(off_trout.get("walk_mps", 0.0)))
    hold_delta = abs(float(on_trout.get("hold_seconds", 0.0))
                     - float(off_trout.get("hold_seconds", 0.0)))
    assert (temp_delta >= 0.01 or walk_delta >= 1e-3 or hold_delta >= 0.01
            or on_trout.get("refuge_cell_id")
            != off_trout.get("refuge_cell_id")), (
        f"snowmelt signal did not reach trout inputs: "
        f"temp_delta={temp_delta} walk_delta={walk_delta} "
        f"hold_delta={hold_delta}, "
        f"off_cell={off_trout.get('refuge_cell_id')} "
        f"on_cell={on_trout.get('refuge_cell_id')}")


@pytest.mark.needs_science
def test_large_runoff_reaches_the_published_trout(simulate_case):
    """Higher runoff propagates through the refuge selection to the published trout."""
    off = simulate_case()
    on = simulate_case(area_m2=USGS_AREA_M2 * 2.0)
    off_trout = [w for w in off["variant"]["wildlife"] if "trout" in w["id"]][0]
    on_trout = [w for w in on["variant"]["wildlife"] if "trout" in w["id"]][0]
    assert on["boundary_m3s"] > off["boundary_m3s"]
    for result, trout in ((off, off_trout), (on, on_trout)):
        selection = result["aquatic_foodweb"]["trout"]
        assert trout["refuge_cell_id"] == selection["cell_id"]
        assert trout["reach_temp_c"] == round(selection["temperature_c"], 2)
        assert trout["suitability_U"] == selection["U"]
    assert on_trout["reach_temp_c"] != off_trout["reach_temp_c"]



def test_snow_window_changes_the_discharge(simulate_case):
    summer = simulate_case(area_m2=USGS_AREA_M2)
    winter = simulate_case(area_m2=USGS_AREA_M2,
                  snow={"season": "winter", "days": 120,
                        "precip_mm_d": 2.0, "air_c_by_day": [-5.0] * 120})
    assert winter["catchment"]["runoff_m3_s"] > summer["catchment"]["runoff_m3_s"]
    assert winter["boundary_m3s"] > summer["boundary_m3s"]


def test_runoff_boundary_and_budget_share_discharge(simulate_case):
    res = simulate_case(area_m2=USGS_AREA_M2)
    forcing = res["replay_doc"]["forcing"]["boundary_m3_s"]
    assert forcing == pytest.approx(res["boundary_m3s"], rel=1e-9)
    assert res["river_state"][0]["flow_m3s"] == pytest.approx(
        res["boundary_m3s"], rel=1e-9)
    budget = res["replay_doc"]["final_budget"]
    assert res["hydro_ledger"]["replay_budget"] == budget
    duration_s = res["replay_doc"]["frames"][-1]["t_s"]
    assert budget["boundary_input_m3"] == pytest.approx(
        res["boundary_m3s"] * duration_s, rel=1e-6)
    assert budget["water_relative_residual"] < 1e-12



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
    from yellowstone_python.registry.coupling import EXCHANGES
    ids = {r["exchange_id"] for r in EXCHANGES}
    assert "snow_runoff_discharge" in ids


def test_overland_field_carries_no_runoff_signal():
    from yellowstone_python.land.overland_flow import run_overland
    result = run_overland(_MIDWAY, rain_mm_h=2.0, grid=64, cell_m=8.0,
                          sim_s=120.0)
    assert result["surface_runoff"]["carries_runoff_signal"] is False
    assert result["surface_runoff"]["outflow_m3"] == 0.0
    assert "no water left the domain" in result["surface_runoff"]["note"]
    assert math.isclose(result["balance"]["rel_error"], 0.0, abs_tol=1e-9)

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'BASE', resolved_paths['BASE_CONFIG'], raising=False)
    monkeypatch.setattr(module, '_MIDWAY', resolved_paths['MIDWAY'], raising=False)
