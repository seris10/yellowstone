import copy
import math

import pytest
import yaml

from yellowstone_python.build import (_find, load_inputs, simulate_all,
                                      validate_config)

from paths import BASE_CONFIG as BASE


def _cfg():
    return yaml.safe_load(open(BASE).read())


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


def test_simulate_all_is_pure_and_complete(tmp_path):
    cfg = _cfg()
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
    # Pure: no files written into tmp cwd and derived untouched by simulate.
    assert list(tmp_path.iterdir()) == []


def test_food_web_refuge_reaches_the_published_wildlife():
    cfg = _cfg()
    baseline, world, deps, tfns = load_inputs(cfg)
    res = simulate_all(cfg, baseline, world, tfns)
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


def test_dipper_intake_comes_from_the_food_web():
    cfg = _cfg()
    baseline, world, deps, tfns = load_inputs(cfg)
    res = simulate_all(cfg, baseline, world, tfns)
    per_day = res["aquatic_foodweb"]["dipper"]["intake_per_day"]
    dipper = next(w for w in res["variant"]["wildlife"] if w["id"] == "dipper_01")
    assert dipper["intake_basis"] == "replay_foodweb"
    assert dipper["intake_basis_prey_per_h"] == pytest.approx(per_day / 24.0,
                                                             abs=1e-3)
    raven = next(w for w in res["variant"]["wildlife"] if w["id"] == "raven_01")
    assert raven["intake_basis"] == "insect_compartments"


def test_replay_and_chain_share_the_configured_air_forcing():
    cfg = _cfg()
    baseline, world, deps, tfns = load_inputs(cfg)
    res = simulate_all(cfg, baseline, world, tfns)
    forced = res["replay_doc"]["forcing"]["air_c"]["values"][0]
    effective = res["weather_frag"]
    night = effective["night_air_c"]
    warming = effective["day_warming_c"]
    lag = effective.get("lag_hours", 3.0)
    hour = res["hour0"]
    shape = max(0.0, math.sin((hour - 6.0 - lag) * math.pi / 12.0))
    assert forced == pytest.approx(night + warming * shape, abs=1e-6)
    assert forced == pytest.approx(res["air0"], abs=1e-6)
    # Every sample on the solver's own clock, from the resolved hour.
    forcing = res["replay_doc"]["forcing"]["air_c"]
    expected = [night + warming * max(0.0, math.sin(
        ((hour + t / 3600.0) % 24.0 - 6.0 - lag) * math.pi / 12.0))
        for t in forcing["times_s"]]
    assert forcing["values"] == pytest.approx(expected, abs=1e-6)


def test_replay_solver_conserves_heat_and_water():
    cfg = _cfg()
    baseline, world, deps, tfns = load_inputs(cfg)
    res = simulate_all(cfg, baseline, world, tfns)
    rd = res["replay_doc"]
    assert rd["numerical_checks"]["passed"] is True
    fb = rd["final_budget"]
    assert fb["heat_relative_residual"] < 1e-9, fb["heat_relative_residual"]
    assert fb["water_relative_residual"] < 1e-12, fb["water_relative_residual"]
    assert len(rd["frames"]) > 1
    assert len(rd["cells"]) > 0
    assert rd["model"]["space"] == "1-D upstream-to-downstream chainage"


def test_replay_uses_dem_cross_sections():
    cfg = _cfg()
    baseline, world, deps, tfns = load_inputs(cfg)
    res = simulate_all(cfg, baseline, world, tfns)
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
