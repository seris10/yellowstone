"""Tests for exporters.to_ecosystem, to_map and godot_sidecars (E1-5 scope)."""
from __future__ import annotations

import copy
import json

import pytest

from yellowstone_python.exporters import godot_sidecars
from yellowstone_python.exporters.godot_sidecars import (
    MissingSourceError,
    produce_all,
    write_calibration_summary_json,
    write_census_sidecar,
    write_geochemistry_json,
    write_groundwater_field_json,
    write_overland_field_json,
    write_plume_field_json,
    write_pools_state_json,
    write_snow_cover_sidecar,
)
from yellowstone_python.exporters.to_ecosystem import (
    merge_fragments,
    validate_for_godot,
)
from yellowstone_python.exporters.to_map import reproject_to_macro


def _baseline() -> dict:
    return {
        "schema_version": 1,
        "boundary_m3s": 8.0,
        "boundary_c": 17.5,
        "humidity": 0.45,
        "cloud": 0.2,
        "clock_hour": 16.2,
        "weather": {
            "night_air_c": 5.0,
            "day_warming_c": 10.0,
            "wind_xz_mps": [1.0, 0.5],
            "gust_mps": 2.5,
        },
        "river_reaches": [
            {"id": "excelsior_mixing", "upstream_id": "",
             "volume_m3": 100.0, "cooling_seconds": 1800.0,
             "temperature_c": 19.1, "lateral_sources": []},
            {"id": "bridge_downstream", "upstream_id": "excelsior_mixing",
             "volume_m3": 150.0, "cooling_seconds": 1800.0,
             "temperature_c": 17.8, "lateral_sources": []},
        ],
        "patches": [
            {"id": "north_meadow", "biomass": 0.7, "capacity": 1.0,
             "moisture": 0.5, "growth_per_hour": 0.01,
             "insect_resource": 0.3, "insect_recovery_per_hour": 0.01},
        ],
    }


def test_merge_fragments_leaves_baseline_alone():
    baseline = _baseline()
    original = copy.deepcopy(baseline)
    merge_fragments(baseline)
    assert baseline == original


def test_merge_fragments_propagates_effective_boundary():
    baseline = _baseline()
    out = merge_fragments(baseline, boundary_m3s=8.75, boundary_c=18.1)
    assert out["boundary_m3s"] == pytest.approx(8.75)
    assert out["boundary_c"] == pytest.approx(18.1)
    out2 = merge_fragments(baseline)
    assert out2["boundary_m3s"] == 8.0
    assert out2["boundary_c"] == 17.5


def test_merge_fragments_applies_river_state_and_weather():
    baseline = _baseline()
    river_state = [{"id": "excelsior_mixing", "temperature_c": 25.0}]
    weather = {"wind_xz_mps": [3.0, 0.0], "humidity": 0.6, "cloud": 0.9}
    out = merge_fragments(baseline, river_state=river_state, weather=weather,
                          clock_hour=5.5)
    assert out["clock_hour"] == pytest.approx(5.5)
    assert out["river_reaches"][0]["temperature_c"] == pytest.approx(25.0)
    assert out["weather"]["wind_xz_mps"] == [3.0, 0.0]
    assert out["humidity"] == pytest.approx(0.6)
    assert out["cloud"] == pytest.approx(0.9)


def test_validate_for_godot_passes_for_well_formed_doc():
    assert validate_for_godot(_baseline()) == []


def test_validate_for_godot_flags_missing_patch_field():
    doc = _baseline()
    doc["patches"][0].pop("growth_per_hour")
    errors = validate_for_godot(doc)
    assert any("growth_per_hour" in e for e in errors)


def test_validate_for_godot_flags_missing_weather_key():
    doc = _baseline()
    doc["weather"].pop("gust_mps")
    assert any("gust_mps" in e for e in validate_for_godot(doc))


def test_validate_for_godot_flags_wrong_wind_arity():
    doc = _baseline()
    doc["weather"]["wind_xz_mps"] = [1.0]
    assert any("wind_xz_mps must be a 2-array" in e
               for e in validate_for_godot(doc))


def test_validate_for_godot_flags_zero_cooling_seconds():
    doc = _baseline()
    doc["river_reaches"][1]["cooling_seconds"] = 0.0
    assert any("cooling_seconds" in e for e in validate_for_godot(doc))


def test_validate_for_godot_flags_lateral_source_missing_fields():
    doc = _baseline()
    doc["river_reaches"][0]["lateral_sources"] = [{"id": "trib"}]
    errors = validate_for_godot(doc)
    assert any("flow_m3s" in e for e in errors)
    assert any("temperature_c" in e for e in errors)


def test_validate_for_godot_flags_missing_boundary_c():
    doc = _baseline()
    doc.pop("boundary_c")
    assert any("boundary_c" in e for e in validate_for_godot(doc))


def test_reproject_to_macro_copies_when_size_matches(tmp_path):
    from PIL import Image

    src = tmp_path / "src.png"
    dst = tmp_path / "dst.png"
    Image.new("RGB", (4, 3), color="black").save(src)
    out = reproject_to_macro(str(src), str(dst), expected_size_px=(4, 3))
    assert out == str(dst)
    assert dst.is_file()


def test_reproject_to_macro_rejects_wrong_size(tmp_path):
    from PIL import Image

    src = tmp_path / "src.png"
    dst = tmp_path / "dst.png"
    Image.new("RGB", (4, 3), color="black").save(src)
    with pytest.raises(ValueError):
        reproject_to_macro(str(src), str(dst), expected_size_px=(5, 3))
    assert not dst.exists()


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_dir_with_sources(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    _write_json(build / "river_state.json", {
        "river_state": [
            {"id": "excelsior_mixing", "temperature_c": 25.0},
            {"id": "bridge_downstream", "temperature_c": 18.0},
        ]
    })
    _write_json(build / "river_replay.json", {
        "replay": {
            "simulation_start_epoch_unix": 1785600000.0,
            "cells": [{"id": "cell_a", "center_s_m": 100.0}, {"id": "cell_b", "center_s_m": 200.0}],
            "source_connections": [{"source_id": "excelsior", "s_m": 100.0}],
            "legacy_queries": [{"reach_id": "bridge_downstream", "s_m": 200.0}],
            "frames": [
                {"t_s": 0.0, "temperature_c": [17.5, 17.6]},
                {"t_s": 60.0, "temperature_c": [25.0, 18.0]},
            ],
        }
    })
    _write_json(build / "pool_shells.json", {"pool_shells": []})
    _write_json(build / "season.json", {"patches": [
        {"id": "a", "snow_depth_m": 0.2, "snow_mm": 50.0},
    ]})
    derived_root = build.parent
    _write_json(derived_root / "reach_heat_fit_test.json", {
        "champion": {
            "q_lat": 1.5, "t_lat": 20.0, "c_mult": 1.0,
            "train_rmse": 0.5, "holdout_rmse": 0.6,
            "train_bias": 0.1, "holdout_bias": 0.2,
            "budget_ok": True,
            "status": "fitted_not_validated_single_window",
        }
    })
    _write_json(derived_root / "firehole_obs.json", {
        "sites": {
            "0001": {
                "series": {
                    "discharge_m3_s": [[100.0, 8.0], [160.0, 8.1]],
                    "temperature_c": [[100.0, 17.5], [160.0, 17.6]],
                }
            }
        }
    })
    return build


@pytest.mark.needs_science
def test_plume_producer_writes_grid(tmp_path):
    pytest.importorskip("scipy")
    build = _build_dir_with_sources(tmp_path)
    out = write_plume_field_json(build)
    assert out == build / "plume_field.json"
    doc = json.loads(out.read_text())
    assert doc["schema"] == godot_sidecars.PLUME_FIELD_SCHEMA
    assert doc["status"] == "illustrative"
    assert doc["nx"] == 128 and doc["nz"] == 128
    assert len(doc["axes_x_m"]) == 128
    assert len(doc["axes_z_m"]) == 128
    assert len(doc["temperature_grid_c"]) == 128
    assert len(doc["temperature_grid_c"][0]) == 128
    assert doc["hot_source_c"] == pytest.approx(25.0)
    assert doc["river_c"] == pytest.approx(18.0)


def test_plume_producer_raises_when_source_absent(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    with pytest.raises(MissingSourceError):
        write_plume_field_json(build)


@pytest.mark.needs_science
def test_plume_producer_uses_mapped_replay_with_list_river_state(tmp_path):
    pytest.importorskip("scipy")
    build = _build_dir_with_sources(tmp_path)
    _write_json(build / "river_state.json", [
        {"id": "excelsior_mixing", "temperature_c": 24.0},
        {"id": "bridge_downstream", "temperature_c": 17.9},
    ])
    out = write_plume_field_json(build)
    doc = json.loads(out.read_text())
    assert doc["hot_source_c"] == pytest.approx(25.0)
    assert doc["river_c"] == pytest.approx(18.0)


def test_geochemistry_producer_writes_per_cell(tmp_path):
    build = _build_dir_with_sources(tmp_path)
    out = write_geochemistry_json(build)
    doc = json.loads(out.read_text())
    assert doc["schema"] == godot_sidecars.GEOCHEMISTRY_SCHEMA
    assert doc["phase"] == "quartz"
    assert doc["status"] == "illustrative"
    assert len(doc["cells"]) == 2
    row = doc["cells"][0]
    assert row["cell"] == "cell_a"
    assert row["silica_saturation_index"] is None
    assert row["flag"] == "no_observation"
    assert row["equilibrium_mg_L"] > 0.0


def test_calibration_producer_reads_fit_and_obs(tmp_path):
    build = _build_dir_with_sources(tmp_path)
    out = write_calibration_summary_json(build)
    doc = json.loads(out.read_text())
    assert doc["schema"] == godot_sidecars.CALIBRATION_SUMMARY_SCHEMA
    assert doc["reach_fit"]["train_rmse_c"] == pytest.approx(0.5)
    assert doc["reach_fit"]["holdout_rmse_c"] == pytest.approx(0.6)
    assert doc["reach_fit"]["budget_ok"] is True
    gauge = doc["gauge_trace"]
    assert gauge["site_id"] == "0001"
    assert len(gauge["samples"]) == 2
    assert gauge["samples"][0]["temperature_c"] == pytest.approx(17.5)
    assert doc["status"] == "illustrative"


def test_calibration_producer_without_fit_raises(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    with pytest.raises(MissingSourceError):
        write_calibration_summary_json(build)


def test_pools_state_producer_records_gap_on_empty_shells(tmp_path):
    build = _build_dir_with_sources(tmp_path)
    # The baseline fixture carries an empty pool_shells list; the producer refuses.
    with pytest.raises(MissingSourceError):
        write_pools_state_json(build)


def test_pools_state_producer_writes_from_shells(tmp_path):
    build = _build_dir_with_sources(tmp_path)
    shells_path = build / "pool_shells.json"
    _write_json(shells_path, {"pool_shells": [
        {"id": "pool_a", "name": "Pool A", "source_id": "1030",
         "t_center_c": 72.0, "t_edge_c": 48.0,
         "r_water_m": 10.0, "r_apron_m": 22.0},
    ]})
    out = write_pools_state_json(build)
    doc = json.loads(out.read_text())
    assert doc["schema"] == godot_sidecars.POOLS_STATE_SCHEMA
    assert doc["pools"][0]["t_center_c"] == pytest.approx(72.0)
    assert doc["pools"][0]["t_edge_c"] == pytest.approx(48.0)


def test_snow_cover_producer_derives_from_snow_depth(tmp_path):
    build = _build_dir_with_sources(tmp_path)
    # Fixture carries snow_depth_m=0.2 which is twice the full-cover threshold.
    out = write_snow_cover_sidecar(build)
    doc = json.loads(out.read_text())
    assert doc["schema"] == godot_sidecars.SNOW_COVER_SCHEMA
    assert doc["patches"][0]["snow_cover_fraction"] == pytest.approx(1.0)
    assert "derived_from_snow_depth_m" in doc["source"]


def test_snow_cover_producer_writes_when_fraction_present(tmp_path):
    build = _build_dir_with_sources(tmp_path)
    season = build / "season.json"
    doc = json.loads(season.read_text())
    doc["patches"][0]["snow_cover_fraction"] = 0.42
    season.write_text(json.dumps(doc), encoding="utf-8")
    out = write_snow_cover_sidecar(build)
    sidecar = json.loads(out.read_text())
    assert sidecar["schema"] == godot_sidecars.SNOW_COVER_SCHEMA
    assert sidecar["patches"][0]["snow_cover_fraction"] == pytest.approx(0.42)
    assert sidecar["source"].startswith("season.json::")


@pytest.mark.needs_science
def test_produce_all_reports_written_and_gaps(tmp_path):
    pytest.importorskip("scipy")
    build = _build_dir_with_sources(tmp_path)
    produced, gaps = produce_all(build)
    assert "plume_field.json" in produced
    assert "geochemistry.json" in produced
    assert "calibration_summary.json" in produced
    # snow_cover.json lands because the fixture carries snow_depth_m.
    assert "snow_cover.json" in produced
    assert any(g.startswith("pools_state.json:") for g in gaps)
    assert any(g.startswith("overland_field.json:") for g in gaps)
    assert any(g.startswith("groundwater_field.json:") for g in gaps)
    assert any(g.startswith("weather_snapshot.json:") for g in gaps)


def test_overland_producer_republishes_with_status(tmp_path):
    build = _build_dir_with_sources(tmp_path)
    _write_json(build / "overland_flow.json", {
        "status": "illustrative_not_calibrated",
        "enabled": False,
        "surface_runoff": {"max_depth_m": 0.0, "outflow_m3": 0.0,
                           "carries_runoff_signal": False,
                           "note": "module disabled; no field computed"},
        "overland_flow_role": "diagnostic_not_wired_to_river",
    })
    out = write_overland_field_json(build)
    doc = json.loads(out.read_text())
    assert doc["status"] == "synthetic_catchment_predicted_not_validated"
    assert doc["overland_module_status"] == "illustrative_not_calibrated"
    assert doc["enabled"] is False


def test_overland_producer_raises_when_absent(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    with pytest.raises(MissingSourceError):
        write_overland_field_json(build)


def test_groundwater_producer_records_gap_without_sidecar(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    with pytest.raises(MissingSourceError):
        write_groundwater_field_json(build)


def test_groundwater_producer_wraps_sidecar_when_present(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    _write_json(build / "groundwater.json", {
        "status": "authored_lateral_not_modeled",
        "laterals": [],
    })
    out = write_groundwater_field_json(build)
    doc = json.loads(out.read_text())
    assert doc["status"] == "authored_lateral_not_modeled"
    assert doc["payload"]["laterals"] == []


def test_census_producer_wraps_sibling_census(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    _write_json(build.parent / "census.json", {
        "status": "illustrative",
        "trees": [],
    })
    out = write_census_sidecar(build)
    doc = json.loads(out.read_text())
    assert doc["status"] == "illustrative"
    assert doc["payload"]["trees"] == []


def test_census_producer_prefers_local_copy(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    local = build / "census.json"
    _write_json(local, {"already": True})
    out = write_census_sidecar(build)
    assert out == local
    assert json.loads(local.read_text()) == {"already": True}


def _weather_json_payload(met_bundle: bool = False) -> dict:
    return {
        "weather": {
            "valid_time_unix": 1785600000.0,
            "night_air_c": 8.5,
            "day_warming_c": 0.0,
            "wind_xz_mps": [4.0, 0.6],
            "gust_mps": 0.45,
            "humidity": 0.85,
            "cloud": 0.3,
            "met_bundle": bool(met_bundle),
        }
    }


def test_weather_snapshot_producer_requires_source(tmp_path):
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    from yellowstone_python.exporters.godot_sidecars import (
        write_weather_snapshot_json)
    with pytest.raises(MissingSourceError):
        write_weather_snapshot_json(build)


def test_weather_snapshot_producer_writes_schema_v2(tmp_path):
    from yellowstone_python.exporters.godot_sidecars import (
        validate_weather_snapshot_doc,
        write_weather_snapshot_json,
    )
    build = tmp_path / "derived" / "build_000"
    build.mkdir(parents=True)
    _write_json(build / "weather.json", _weather_json_payload(met_bundle=True))
    _write_json(build / "season.json", {"simulation_epoch_unix": 1785600000.0})
    out = write_weather_snapshot_json(build)
    assert out == build / "weather_snapshot.json"
    doc = json.loads(out.read_text())
    assert doc["schema_version"] == 2
    for key in ("generated_at_unix", "valid_time_unix",
                "simulation_time_unix", "source", "weather"):
        assert key in doc
    for field in ("air_temperature_c", "relative_humidity",
                  "wind_speed_mps", "wind_direction_deg",
                  "cloud_fraction", "precipitation_rate_mm_h",
                  "snow_fraction", "visibility_m"):
        assert field in doc["weather"]
    # The Godot reader's validation rules must all pass against the produced doc.
    assert validate_weather_snapshot_doc(doc) == []


def test_weather_snapshot_validator_catches_schema_mismatch():
    from yellowstone_python.exporters.godot_sidecars import (
        validate_weather_snapshot_doc)
    bad = {"schema_version": 99, "generated_at_unix": 0,
           "weather": {}}
    errors = validate_weather_snapshot_doc(bad)
    assert any("schema_version" in e for e in errors)


def test_weather_snapshot_validator_catches_out_of_range_wind():
    from yellowstone_python.exporters.godot_sidecars import (
        validate_weather_snapshot_doc)
    bad = {
        "schema_version": 2, "generated_at_unix": 0,
        "valid_time_unix": 0, "simulation_time_unix": 0,
        "weather": {
            "air_temperature_c": 20.0, "relative_humidity": 0.5,
            "wind_speed_mps": 999.0, "wind_direction_deg": 90.0,
            "cloud_fraction": 0.5, "precipitation_rate_mm_h": 0.0,
            "snow_fraction": 0.0, "visibility_m": 10000.0,
        },
    }
    errors = validate_weather_snapshot_doc(bad)
    assert any("wind_speed_mps" in e for e in errors)


def test_weather_snapshot_validator_catches_bad_wind_direction():
    from yellowstone_python.exporters.godot_sidecars import (
        validate_weather_snapshot_doc)
    bad = {
        "schema_version": 2, "generated_at_unix": 0,
        "valid_time_unix": 0, "simulation_time_unix": 0,
        "weather": {
            "air_temperature_c": 20.0, "relative_humidity": 0.5,
            "wind_speed_mps": 2.0, "wind_direction_deg": 360.0,
            "cloud_fraction": 0.5, "precipitation_rate_mm_h": 0.0,
            "snow_fraction": 0.0, "visibility_m": 10000.0,
        },
    }
    errors = validate_weather_snapshot_doc(bad)
    assert any("wind_direction_deg" in e for e in errors)


def test_weather_snapshot_validator_passes_optional_terrain():
    from yellowstone_python.exporters.godot_sidecars import (
        validate_weather_snapshot_doc)
    doc = {
        "schema_version": 2, "generated_at_unix": 0,
        "valid_time_unix": 0, "simulation_time_unix": 0,
        "weather": {
            "air_temperature_c": 20.0, "relative_humidity": 0.5,
            "wind_speed_mps": 2.0, "wind_direction_deg": 90.0,
            "cloud_fraction": 0.5, "precipitation_rate_mm_h": 0.0,
            "snow_fraction": 0.0, "visibility_m": 10000.0,
        },
        "terrain": {"snow_cover_fraction": 0.7},
    }
    assert validate_weather_snapshot_doc(doc) == []
    doc["terrain"]["snow_cover_fraction"] = 1.5
    errors = validate_weather_snapshot_doc(doc)
    assert any("snow_cover_fraction" in e for e in errors)
