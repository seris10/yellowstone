import copy
import math

import pytest
import yaml

from yellowstone_python.build import (_find, _grazers_input_from_consumed,
                                      _overland_runoff_to_boundary,
                                      check_cross_sections, load_inputs,
                                      simulate_all, validate_config)



def _cfg():
    return yaml.safe_load(open(BASE).read())



@pytest.fixture(scope="module")
def simulation_result(repo_root, world_root):
    """Compute the pinned baseline once for read-only output assertions."""
    for path in (world_root / "data/world.json", world_root / "data/terrain.f32"):
        if not path.is_file():
            pytest.skip(f"world input missing: {path}")
    cfg = yaml.safe_load((repo_root / "configs/baseline.yaml").read_text())
    baseline, world, _, tfns = load_inputs(cfg)
    return simulate_all(cfg, baseline, world, tfns)

def test_validate_config_accepts_baseline():
    validate_config(_cfg())


def test_validate_config_rejects_nonphysical():
    bad = _cfg()
    bad["hydro"]["boundary_m3s"] = 0.0
    with pytest.raises(ValueError):
        validate_config(bad)
    bad = _cfg()
    bad["clock_hour"] = 25.0
    with pytest.raises(ValueError):
        validate_config(bad)
    bad = _cfg()
    bad["weather"]["humidity"] = 1.5
    with pytest.raises(ValueError):
        validate_config(bad)
    bad = _cfg()
    bad["snow"]["precip_mm_d"] = -1.0
    with pytest.raises(ValueError):
        validate_config(bad)


def test_find_names_available_ids():
    with pytest.raises(ValueError) as e:
        _find([{"id": "a"}], "id", "zzz", "reach")
    assert "have ['a']" in str(e.value)


def test_simulate_all_is_pure_and_complete(tmp_path, monkeypatch, world_root):
    cfg = _cfg()
    cfg["world_root"] = str(world_root)
    monkeypatch.chdir(tmp_path)
    baseline, world, deps, tfns = load_inputs(cfg)
    for key in ("world.json", "placements.json", "species_catalogue.json",
                "terrain.f32", "config"):
        assert key in deps, key
    res = simulate_all(cfg, baseline, world, tfns)
    for key in ("river_state", "shells", "proposals", "variant",
                "wildlife3", "patches2", "snow_ledger", "timeline",
                "hydro_ledger", "prey_ledger", "corridor", "replay_doc",
                "aquatic_foodweb", "fh_chainage", "fh_chainage_offset_m"):
        assert key in res, key
    assert res["timeline"]["fast_window_s"] == 600.0
    # Simulation leaves the working directory empty.
    assert list(tmp_path.iterdir()) == []


def test_food_web_refuge_reaches_the_published_wildlife(simulation_result):
    res = simulation_result
    chosen = res["aquatic_foodweb"]["trout"]
    published = res["variant"]["wildlife"]
    trout = [w for w in published if "trout" in w["id"]]
    assert trout, "no trout record published"
    for rec in trout:
        assert rec["refuge_cell_id"] == chosen["cell_id"]
        assert rec["refuge_basis"] == "replay_foodweb"
        assert rec["reach_temp_c"] == pytest.approx(chosen["temperature_c"],
                                                    abs=0.01)
        assert rec["suitability_U"] == pytest.approx(chosen["U"], abs=1e-6)
    assert abs(res["fh_chainage_offset_m"]) > 0.0


def test_dipper_intake_comes_from_the_food_web(simulation_result):
    res = simulation_result
    per_day = res["aquatic_foodweb"]["dipper"]["intake_per_day"]
    dipper = next(w for w in res["variant"]["wildlife"] if w["id"] == "dipper_01")
    assert dipper["intake_basis"] == "replay_foodweb"
    assert dipper["intake_basis_prey_per_h"] == pytest.approx(per_day / 24.0,
                                                             abs=1e-3)
    raven = next(w for w in res["variant"]["wildlife"] if w["id"] == "raven_01")
    assert raven["intake_basis"] == "insect_compartments"


def test_replay_and_chain_share_the_configured_air_forcing(simulation_result):
    res = simulation_result
    forced = res["replay_doc"]["forcing"]["air_c"]["values"][0]
    effective = res["weather_frag"]
    night = effective["night_air_c"]
    warming = effective["day_warming_c"]
    lag = effective.get("lag_hours", 3.0)
    hour = res["hour0"]
    shape = max(0.0, math.sin((hour - 6.0 - lag) * math.pi / 12.0))
    assert forced == pytest.approx(night + warming * shape, abs=1e-6)
    assert forced == pytest.approx(res["air0"], abs=1e-6)
    # Samples run on the solver's own clock, from the resolved hour.
    forcing = res["replay_doc"]["forcing"]["air_c"]
    expected = [night + warming * max(0.0, math.sin(
        ((hour + t / 3600.0) % 24.0 - 6.0 - lag) * math.pi / 12.0))
        for t in forcing["times_s"]]
    assert forcing["values"] == pytest.approx(expected, abs=1e-6)


def test_replay_solver_conserves_heat_and_water(simulation_result):
    res = simulation_result
    rd = res["replay_doc"]
    assert rd["numerical_checks"]["passed"] is True
    fb = rd["final_budget"]
    assert fb["heat_relative_residual"] < 1e-9, fb["heat_relative_residual"]
    assert fb["water_relative_residual"] < 1e-12, fb["water_relative_residual"]
    assert len(rd["frames"]) > 1
    assert len(rd["cells"]) > 0
    assert rd["model"]["space"] == "1-D upstream-to-downstream chainage"


def test_replay_uses_dem_cross_sections(simulation_result):
    res = simulation_result
    rd = res["replay_doc"]
    firehole_cells = [c for c in rd["cells"] if c.get("river_id") == "river_5856_0"]
    assert len(firehole_cells) > 0
    for cell in firehole_cells:
        assert cell.get("depth_status") == "authored_estimate_from_usgs_3dep_dem", \
            f"cell {cell['id']} has depth_status={cell.get('depth_status')}"
        assert cell.get("depth_m", 0) > 0.3
        assert cell.get("depth_m", 0) < 1.0


def test_replay_config_validation():
    bad = _cfg()
    bad["replay"]["duration_s"] = 0.0
    with pytest.raises(ValueError):
        validate_config(bad)
    bad = _cfg()
    bad["replay"]["dispersion_m2_s"] = -1.0
    with pytest.raises(ValueError):
        validate_config(bad)


def test_validate_config_is_non_mutating_and_returns_normalized():
    cfg = _cfg()
    before = copy.deepcopy(cfg)
    normalized = validate_config(cfg)
    assert cfg == before, "validate_config must not mutate its input"
    assert normalized["run_mode"] == "illustrative"
    assert normalized["world_root"]


def test_validate_config_rejects_nan_and_inf_numerics():
    bad = _cfg()
    bad["hydro"]["boundary_m3s"] = float("nan")
    with pytest.raises(ValueError):
        validate_config(bad)
    bad = _cfg()
    bad["replay"]["duration_s"] = float("inf")
    with pytest.raises(ValueError):
        validate_config(bad)
    bad = _cfg()
    bad["hydro"]["boundary_c"] = True
    with pytest.raises(ValueError):
        validate_config(bad)


def test_validate_config_requires_explicit_start_in_measured_modes():
    cfg = _cfg()
    cfg.pop("simulation", None)
    cfg["run_mode"] = "hindcast"
    with pytest.raises(ValueError, match="simulation"):
        validate_config(cfg)
    cfg["simulation"] = {"start_utc": "2026-07-15T22:20:00Z"}
    validate_config(cfg)


def test_check_cross_sections_detects_missing_and_unknown():
    world = {"rivers": [{"id": "river_a"}, {"id": "river_b"}], "pools": []}
    report = check_cross_sections(
        {"river_a": {"depth_m": 0.5, "status": "x"},
         "river_c": {"depth_m": 0.6, "status": "x"}},
        world)
    assert report["status"] == "partial"
    assert "river_c" in report["unknown_feature_entries"]
    assert "river_b" in report["missing_features"]


def test_grazers_input_from_consumed_wiring():
    out = _grazers_input_from_consumed({"north_meadow": 0.03}, dt_s=600.0)
    assert out is not None
    (entry,) = out.values()
    assert entry["patch_id"] == "north_meadow"
    assert entry["active"] is True
    assert entry["rate_per_second"] == pytest.approx(0.03 / 600.0)
    assert _grazers_input_from_consumed({}, dt_s=600.0) is None


def test_overland_runoff_zero_when_disabled():
    rate, report = _overland_runoff_to_boundary(
        {"surface_runoff": {"outflow_m3": 0.0,
                            "carries_runoff_signal": False}},
        {"catchment": {"area_m2": None}}, 600.0)
    assert rate == 0.0
    assert report["status"] == "no_outflow"


def test_overland_runoff_divides_outflow_by_window():
    rate, report = _overland_runoff_to_boundary(
        {"surface_runoff": {"outflow_m3": 60.0,
                            "carries_runoff_signal": True}},
        {"catchment": {"area_m2": 1.0e6}}, 600.0)
    assert rate == pytest.approx(0.1)
    assert report["status"] == "wired_mean_rate"
    assert report["mean_rate_m3_s"] == pytest.approx(0.1)
    assert report["coupling"].startswith("partial")


def test_build_result_reports_cross_sections_overland_and_shared_tolerances(simulation_result):
    res = simulation_result
    assert "cross_sections_report" in res
    assert res["cross_sections_report"]["status"] in (
        "covers", "partial", "empty", "no_cross_sections")
    assert "overland_runoff_m3_s" in res
    assert res["overland_runoff_m3_s"] >= 0.0
    assert "bundle_window_check" in res
    cs_report = res["replay_doc"].get(
        "provenance", {}).get("cross_sections_report")
    assert cs_report is not None


def test_build_result_wires_per_cell_benthic_and_trout_hydraulics(simulation_result):
    res = simulation_result
    assert "benthic_grid" in res
    assert "trout_hydraulics_source" in res
    bg = res["benthic_grid"]
    if bg is not None and "cell_ids" in bg:
        assert len(bg["cell_ids"]) == len(bg["water_c_cells"])
        assert len(bg["nb"]) == len(bg["cell_ids"])
    assert res["trout_hydraulics_source"] in (
        "per_cell_from_replay_firehole_landscape_nearest_chainage",
        "reach_level_fallback_no_firehole_cells")


def test_snow_cover_fraction_in_season_patches(simulation_result):
    res = simulation_result
    for patch in res["patches2"]:
        assert "snow_cover_fraction" in patch
        assert 0.0 <= float(patch["snow_cover_fraction"]) <= 1.0

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'BASE', resolved_paths['BASE_CONFIG'], raising=False)
