import copy

import pytest
import yaml

from yellowstone_python.common.provenance import sha256_json
from yellowstone_python.study_mode import PRESETS, _validate, apply_preset, diff_configs

from paths import BASE_CONFIG as BASE


def _base():
    return yaml.safe_load(open(BASE).read())


def test_reset_reproduces_baseline_hash():
    base = _base()
    clone = copy.deepcopy(base)
    assert sha256_json(apply_preset(base, "hot_surge")) != sha256_json(base)
    assert sha256_json(clone) == sha256_json(base)  # baseline never mutated


def test_presets_only_touch_sliders():
    base = _base()
    for name in PRESETS:
        cfg = apply_preset(base, name)
        d = diff_configs(base, cfg)
        paths = [r["path"] for r in d]
        assert paths, name
        assert all(p == "study" or p == "run_mode" or p.startswith(("weather.", "hydro.",
                                                           "insects.", "fish.",
                                                           "snow.", "clock_hour",
                                                           "study.")) for p in paths), paths
        assert not any(p.startswith(("routes", "pools", "placements"))
                       for p in paths)


def test_counterexample_present():
    assert "warm_air_cold_water" in PRESETS
    assert "COUNTEREXAMPLE" in PRESETS["warm_air_cold_water"]["about"]


def test_winter_preset_accumulates():
    from yellowstone_python.snow_season import run_season
    base = _base()
    cfg = apply_preset(base, "winter_week")
    patches = [{"id": "m", "habitat": "dry_meadow", "center_xz": [500, 500],
                "moisture": 0.5}]
    out, _ = run_season(patches, days=cfg["snow"]["days"],
                        air_c_by_day=cfg["snow"]["air_c_by_day"],
                        precip_mm_d=cfg["snow"]["precip_mm_d"],
                        thermal_test=lambda x, z: False)
    assert out[0]["snow_mm"] > 0


def test_strict_schema_rejects_unknown_and_out_of_range():
    with pytest.raises(ValueError):
        _validate("routes", [])
    with pytest.raises(ValueError):
        _validate("clock_hourly", 5.0)  # prefix lookalike, not an exact key
    with pytest.raises(ValueError):
        _validate("hydro.boundary_m3s", -2.0)
    with pytest.raises(ValueError):
        _validate("snow.season", "monsoon")
    _validate("snow.season", "winter")  # exact keys pass


def test_preset_stamps_run_mode():
    base = _base()
    assert apply_preset(base, "hot_surge")["run_mode"] == "scenario"
    assert apply_preset(base, "hot_surge",
                        run_mode="hindcast")["run_mode"] == "hindcast"
    with pytest.raises(ValueError):
        apply_preset(base, "hot_surge", run_mode="forecast")


def test_surge_merges_existing_attachments():
    base = _base()
    base["hydro"]["attach"] = {"upstream_midway": ["fairy_creek"]}
    base["hydro"]["tributaries"] = {"fairy_creek": {"flow_m3s": 0.5,
                                                   "temperature_c": 12.0}}
    cfg = apply_preset(base, "hot_surge")
    assert "fairy_creek" in cfg["hydro"]["attach"]["upstream_midway"]
    assert "excelsior_surge" in cfg["hydro"]["attach"]["excelsior_mixing"]


def test_compare_quantifies_ab(tmp_path):
    from yellowstone_python.compare import compare_builds
    from pathlib import Path
    # Newest build directory that carries the sidecars compare_builds
    # reads; a build still in progress leaves a partial directory behind.
    complete = [p for p in Path("derived").iterdir()
                if p.is_dir() and (p / "fish.json").exists()
                and (p / "river_state.json").exists()]
    assert complete, "no complete build under derived/"
    a = max(complete, key=lambda p: p.stat().st_mtime)
    out = compare_builds(a, a)
    assert all(r["d_temp_c"] == 0.0 for r in out["reach_deltas"])
    assert out["scope"].startswith("endpoint comparison")


def test_allowed_prefixes_are_enforced():
    from yellowstone_python.study_mode import SCHEMA, _prefix_allowed
    # Every schema key must sit under an allowed prefix.
    for key in SCHEMA:
        assert _prefix_allowed(key), key
    # A path that is not a slider stays unreachable even if spelled validly.
    for bad in ("river.manning_n", "pools.pool_1034_0.depth_m"):
        assert not _prefix_allowed(bad)


def test_presets_self_validate():
    from yellowstone_python.study_mode import preset_errors
    assert preset_errors() == []


def test_lateral_flow_and_temperature_are_validated():
    from yellowstone_python.study_mode import _validate_lateral
    ok = _validate_lateral("excelsior_mixing",
                           {"id": "x", "flow_m3s": 0.26, "temperature_c": 62.0})
    assert ok == {"flow_m3s": 0.26, "temperature_c": 62.0}
    for bad in ({"id": "x", "flow_m3s": -1.0, "temperature_c": 60.0},
                {"id": "x", "flow_m3s": float("nan"), "temperature_c": 60.0},
                {"id": "", "flow_m3s": 0.1, "temperature_c": 60.0},
                {"id": "x", "flow_m3s": 0.1},
                {"id": "x", "flow_m3s": True, "temperature_c": 60.0}):
        with pytest.raises(ValueError):
            _validate_lateral("excelsior_mixing", bad)


def test_surge_refuses_to_overwrite_a_conflicting_tributary():
    baseline = {"hydro": {"attach": {"excelsior_mixing": ["excelsior_surge"]},
                          "tributaries": {"excelsior_surge":
                                          {"flow_m3s": 0.9,
                                           "temperature_c": 40.0}}}}
    with pytest.raises(ValueError, match="already"):
        apply_preset(baseline, "hot_surge")


def test_surge_attachment_is_idempotent():
    baseline = {"hydro": {"attach": {}, "tributaries": {}}}
    once = apply_preset(baseline, "hot_surge")
    twice = apply_preset(once, "hot_surge")
    assert (once["hydro"]["attach"]["excelsior_mixing"]
            == twice["hydro"]["attach"]["excelsior_mixing"])
    assert twice["hydro"]["attach"]["excelsior_mixing"].count(
        "excelsior_surge") == 1


def test_clock_hour_upper_bound_is_exclusive():
    _validate("clock_hour", 0.0)
    _validate("clock_hour", 23.999)
    with pytest.raises(ValueError):
        _validate("clock_hour", 24.0)


def test_nonfinite_values_refused_everywhere():
    for dotted in ("weather.night_air_c", "hydro.boundary_m3s",
                   "snow.precip_mm_d", "weather.wind_xz_mps",
                   "snow.air_c_by_day", "clock_hour"):
        for bad in (float("nan"), float("inf")):
            with pytest.raises(ValueError):
                _validate(dotted, bad if dotted != "clock_hour"
                          else bad)
