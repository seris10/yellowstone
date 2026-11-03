"""Tests for the snow-runoff discharge coupling and the overland null result."""
import json
import math

import pytest
import yaml

from yellowstone_python.build import load_inputs, simulate_all

# Measured: USGS 06036805 Firehole at Old Faithful, 39.5 sqmi.
USGS_AREA_M2 = 39.5 * 2_589_988.110336


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
    # A 9% flow increase shifts temperature ~0.1 C; a coupled response must change. See the readme.
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



def test_cold_season_retains_snow_and_exports_solid_water(simulate_case):
    summer = simulate_case(area_m2=USGS_AREA_M2)
    winter = simulate_case(area_m2=USGS_AREA_M2,
                  snow={"season": "winter", "days": 120,
                        "precip_mm_d": 2.0, "air_c_by_day": [-5.0] * 120})
    # Initial soil drainage and geothermal melt supply liquid; wind exports solid snow.
    assert winter["snow_ledger"]["snow_export_mm"] > 0.
    assert winter["snow_ledger"]["runoff_mm"] == winter["snow_ledger"]["surface_runoff_mm"]
    assert winter["catchment"]["phase"] == "liquid"
    assert winter["catchment"]["runoff_m3_s"] < summer["catchment"]["runoff_m3_s"]
    assert winter["boundary_m3s"] < summer["boundary_m3s"]


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
