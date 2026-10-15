"""Tests for the staged river-transport calibrator (offline, synthetic)."""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import pytest

from tools.calibrate_river_transport import (  # noqa: E402
    OBSERVATION_HIERARCHY,
    SCHEMA_STAGED,
    STAGE_PLAN,
    SURFACE_IDENTIFIABILITY,
    StagedConfig,
    fit_forcing_arrays,
    main,
    observation_hierarchy_report,
    run_staged,
    stage_a_hydraulics,
    stage_b_dispersion,
    stage_c_sources,
    stage_d_surface,
    write_stage_files,
)
from yellowstone_python.river.calibrate import run_fit_forward  # noqa: E402


def _synthetic_bundle(truth=(2.0, 25.0, 1.0), days=2, dt_s=1800.0,
                      include_downstream_q=True,
                      optional_channels=None):
    """Build a yellowstone.firehole_obs.v1 bundle from a forward run."""
    q_lat, t_lat, c_mult = truth
    t0 = time.time()
    n = int(days * 86400 // dt_s)
    grid = [t0 + i * dt_s for i in range(n + 1)]
    up_t = [[g, 10.0 + 2.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi)]
            for g in grid]
    up_q = [[g, 1.0] for g in grid]
    met = [[g, 8.0 + 5.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi),
            0.5, 2.0,
            max(0.0, 500.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi)),
            0.2]
           for g in grid]
    draft = {
        "schema": "yellowstone.firehole_obs.v1",
        "status": "measured_remote_not_calibrated",
        "fetched_at_utc": "2026-10-12T00:00:00Z",
        "sites": {
            "06036805": {"series": {"temperature_c": up_t,
                                    "discharge_m3_s": up_q}},
            "06036905": {"series": {"temperature_c": [],
                                    "discharge_m3_s": []}}},
        "met": {"hourly": met,
                "optional": optional_channels or {}}}
    fwd = run_fit_forward(draft, 20000.0, 20000.0 / 0.5,
                          q_lat, t_lat, c_mult, dt_s)
    down_q = ([[g, 1.0 + q_lat] for g in fwd["grid"]]
              if include_downstream_q else [])
    draft["sites"]["06036905"]["series"] = {
        "temperature_c": [[g, v] for g, v in zip(fwd["grid"],
                                                 fwd["modeled_c"])],
        "discharge_m3_s": down_q,
    }
    return draft


class TestObservationHierarchy:
    def test_reports_baseline_channels_present(self):
        bundle = _synthetic_bundle()
        report = observation_hierarchy_report(bundle)
        meteo = report["by_category"]["meteorology"]
        assert meteo["air_c"] is True
        assert meteo["rh"] is True
        assert meteo["wind_mps"] is True
        assert meteo["shortwave_w_m2"] is True
        assert meteo["cloud_fraction"] is True
        assert meteo["longwave_down_w_m2"] is False
        hydraulics = report["by_category"]["hydraulics"]
        assert hydraulics["upstream_discharge_m3_s"] is True
        assert hydraulics["downstream_discharge_m3_s"] is True
        temps = report["by_category"]["water_temperature"]
        assert temps["upstream_temperature_c"] is True
        assert temps["downstream_temperature_c"] is True

    def test_baseline_bundle_identifies_no_surface_params(self):
        bundle = _synthetic_bundle()
        report = observation_hierarchy_report(bundle)
        assert report["eligible_parameters_from_channels"] == []
        for field in SURFACE_IDENTIFIABILITY:
            assert field in report["ineligible_parameters_from_channels"]

    def test_longwave_channel_identifies_longwave_parameters(self):
        bundle = _synthetic_bundle(
            optional_channels={"longwave_down_w_m2": [[0.0, 310.0]]})
        report = observation_hierarchy_report(bundle)
        assert "shortwave_multiplier" in report["ineligible_parameters_from_channels"]
        for field in ("longwave_multiplier",
                      "longwave_bias_w_m2", "cloud_longwave_factor"):
            assert field in report["eligible_parameters_from_channels"]
        assert "a_RH" in report["ineligible_parameters_from_channels"]

    def test_measured_shortwave_or_net_radiation_identifies_shortwave(self):
        bundle = _synthetic_bundle()
        bundle["met"]["shortwave_source"] = "measured_station"
        report = observation_hierarchy_report(bundle)
        assert "shortwave_multiplier" in report["eligible_parameters_from_channels"]
        bundle["met"].pop("shortwave_source")
        bundle["flux_station"] = {"net": [[0.0, 200.0]]}
        report = observation_hierarchy_report(bundle)
        assert "shortwave_multiplier" in report["eligible_parameters_from_channels"]

    def test_hierarchy_covers_four_categories(self):
        assert set(OBSERVATION_HIERARCHY) == {
            "meteorology", "hydraulics", "water_temperature",
            "surface_flux"}


class TestStageA:
    def test_authored_geometry_prior_passes_through(self):
        bundle = _synthetic_bundle()
        res = stage_a_hydraulics(bundle, volume_m3=20000.0,
                                 area_m2=40000.0, dt_s=1800.0)
        assert res.volume_m3 == 20000.0
        assert res.area_m2 == 40000.0
        assert res.status.startswith(
            "authored_or_measured_prior_not_fitted_against_temperature")
        assert math.isfinite(res.travel_time_s_from_geometry)
        assert res.water_budget_closure_m3_s is not None

    def test_rejects_non_positive_geometry(self):
        bundle = _synthetic_bundle()
        with pytest.raises(ValueError):
            stage_a_hydraulics(bundle, volume_m3=0.0, area_m2=1.0)
        with pytest.raises(ValueError):
            stage_a_hydraulics(bundle, volume_m3=1.0, area_m2=0.0)

    def test_uncertainty_window_matches_sigma(self):
        bundle = _synthetic_bundle()
        res = stage_a_hydraulics(bundle, volume_m3=20000.0,
                                 area_m2=40000.0, dt_s=1800.0,
                                 volume_sigma_frac=0.25)
        lo, hi = res.uncertainty["volume_m3_window_1sigma"]
        assert lo == pytest.approx(20000.0 * 0.75)
        assert hi == pytest.approx(20000.0 * 1.25)


class TestStageB:
    def test_lumped_cell_marks_dispersion_not_identified(self):
        bundle = _synthetic_bundle()
        a = stage_a_hydraulics(bundle, 20000.0, 40000.0, dt_s=1800.0)
        b = stage_b_dispersion(bundle, a)
        assert b.dispersion_m2_s is None
        assert b.status == "not_identified_lumped_single_cell"
        assert "dispersion_sweep" in b.reason


class TestStageCRecovery:
    """Stage C recovers (q_lat, t_lat) on a synthetic bundle."""

    def test_grid_only_recovers_within_tolerance(self):
        truth = (2.0, 25.0, 1.0)
        bundle = _synthetic_bundle(truth=truth, dt_s=1800.0)
        a = stage_a_hydraulics(bundle, 20000.0, 40000.0, dt_s=1800.0)
        c = stage_c_sources(
            bundle, a, q_lat_grid=[1.5, 2.0, 2.5],
            t_lat_grid=[20.0, 25.0, 30.0], dt_s=1800.0,
            spinup_s=3600.0, train_frac=0.6, skip_de=True,
            skip_polish=True, min_members=3,
            n_bootstrap=100)
        # Grid is centered on truth, so the champion must land on it.
        assert c.q_lat == pytest.approx(truth[0], abs=1e-9)
        assert c.t_lat == pytest.approx(truth[1], abs=1e-9)
        assert c.method == "grid"
        assert c.train_rmse < 0.05

    def test_least_squares_polish_refines_off_grid(self):
        truth = (2.0, 25.0, 1.0)
        bundle = _synthetic_bundle(truth=truth, dt_s=1800.0)
        a = stage_a_hydraulics(bundle, 20000.0, 40000.0, dt_s=1800.0)
        c = stage_c_sources(
            bundle, a,
            q_lat_grid=[1.5, 3.0, 4.5],
            t_lat_grid=[15.0, 30.0, 45.0],
            dt_s=1800.0, spinup_s=3600.0, train_frac=0.6,
            skip_de=True, min_members=3,
            n_bootstrap=100)
        assert c.q_lat == pytest.approx(truth[0], abs=0.15)
        assert c.t_lat == pytest.approx(truth[1], abs=1.5)
        assert c.train_rmse < 0.05
        assert c.method in ("grid", "least_squares_polish")

    def test_uncertainty_reports_quantile_structure(self):
        bundle = _synthetic_bundle(dt_s=1800.0)
        a = stage_a_hydraulics(bundle, 20000.0, 40000.0, dt_s=1800.0)
        c = stage_c_sources(
            bundle, a, q_lat_grid=[1.5, 2.0, 2.5],
            t_lat_grid=[20.0, 25.0, 30.0], dt_s=1800.0,
            spinup_s=3600.0, train_frac=0.6, skip_de=True,
            skip_polish=True, min_members=3,
            n_bootstrap=100)
        for key in ("q_lat_quantiles", "t_lat_quantiles"):
            quant = c.uncertainty[key]
            assert set(quant) == {"lo", "median", "hi", "band_level"}
            assert quant["lo"] <= quant["median"] <= quant["hi"]
        assert c.uncertainty["method"] == (
            "ridge_ensemble_with_bootstrap_band")


class TestStageDIdentifiability:
    def test_baseline_only_c_mult_identified(self):
        bundle = _synthetic_bundle(dt_s=1800.0)
        a = stage_a_hydraulics(bundle, 20000.0, 40000.0, dt_s=1800.0)
        c = stage_c_sources(
            bundle, a, q_lat_grid=[1.5, 2.0, 2.5],
            t_lat_grid=[20.0, 25.0, 30.0], dt_s=1800.0,
            spinup_s=3600.0, train_frac=0.6, skip_de=True,
            skip_polish=True, min_members=3, n_bootstrap=100)
        d = stage_d_surface(bundle, a, c, dt_s=1800.0,
                            spinup_s=3600.0, train_frac=0.6,
                            lhs_samples=5, min_members=3,
                            n_bootstrap=100, skip_polish=True)
        assert d.identified_fields == []
        assert "shortwave_multiplier" in d.not_identified_fields
        assert d.budget_params["shortwave_multiplier"] == pytest.approx(1.0)
        assert d.budget_params["longwave_bias_w_m2"] == pytest.approx(0.0)

    def test_lhs_bands_cover_truth_in_c_mult_space(self):
        truth = (2.0, 25.0, 1.0)
        bundle = _synthetic_bundle(truth=truth, dt_s=1800.0)
        a = stage_a_hydraulics(bundle, 20000.0, 40000.0, dt_s=1800.0)
        c = stage_c_sources(
            bundle, a, q_lat_grid=[1.5, 2.0, 2.5],
            t_lat_grid=[20.0, 25.0, 30.0], dt_s=1800.0,
            spinup_s=3600.0, train_frac=0.6, skip_de=True,
            skip_polish=True, min_members=3, n_bootstrap=100)
        d = stage_d_surface(bundle, a, c, dt_s=1800.0,
                            spinup_s=3600.0, train_frac=0.6,
                            lhs_samples=12, min_members=3,
                            n_bootstrap=100, skip_polish=True)
        per_param = d.uncertainty["per_param_quantiles"]
        c_mult_q = per_param["c_mult"]
        assert c_mult_q["lo"] <= c_mult_q["hi"]

    def test_stage_d_polish_recovers_c_mult(self):
        truth = (2.0, 25.0, 1.0)
        bundle = _synthetic_bundle(truth=truth, dt_s=1800.0)
        a = stage_a_hydraulics(bundle, 20000.0, 40000.0, dt_s=1800.0)
        c = stage_c_sources(
            bundle, a, q_lat_grid=[1.5, 2.0, 2.5],
            t_lat_grid=[20.0, 25.0, 30.0], dt_s=1800.0,
            spinup_s=3600.0, train_frac=0.6, skip_de=True,
            skip_polish=True, min_members=3, n_bootstrap=100)
        d = stage_d_surface(bundle, a, c, dt_s=1800.0,
                            spinup_s=3600.0, train_frac=0.6,
                            lhs_samples=5, min_members=3,
                            n_bootstrap=100, skip_polish=False)
        assert d.c_mult == pytest.approx(truth[2], abs=0.1)
        assert d.train_rmse < 0.05


class TestRunStagedEndToEnd:
    def test_full_pipeline_produces_expected_schema(self):
        truth = (2.0, 25.0, 1.0)
        bundle = _synthetic_bundle(truth=truth, dt_s=1800.0)
        config = StagedConfig(
            volume_m3=20000.0, area_m2=40000.0, dt_s=1800.0,
            spinup_s=3600.0, train_frac=0.6,
            q_lat_grid=(1.5, 2.0, 2.5),
            t_lat_grid=(20.0, 25.0, 30.0),
            skip_de=True, skip_polish_c=True, skip_polish_d=True,
            lhs_samples=5, min_members=3, n_bootstrap=100)
        doc = run_staged(bundle, config)
        assert doc["schema"] == SCHEMA_STAGED
        assert doc["status"] == "fitted_not_validated_single_window"
        assert [s["id"] for s in doc["stage_plan"]] == ["A", "B", "C", "D"]
        for sid in ("stage_a", "stage_b", "stage_c", "stage_d"):
            assert sid in doc
        assert doc["stage_c"]["q_lat"] == pytest.approx(truth[0], abs=1e-9)
        assert doc["stage_c"]["t_lat"] == pytest.approx(truth[1], abs=1e-9)
        assert doc["observation_hierarchy"]["report"][
            "eligible_parameters_from_channels"] == []
        assert len(doc["sequence"]) == 10
        surface = doc["surface_model"]
        assert surface["parameter_status"]["c_h"] == "scaled_by_calibration"
        assert surface["parameter_status"][
            "shortwave_multiplier"] == "not_identified_by_current_observations"

    def test_cli_writes_both_output_and_stage_files(self, tmp_path):
        truth = (2.0, 25.0, 1.0)
        bundle = _synthetic_bundle(truth=truth, dt_s=1800.0)
        obs_path = tmp_path / "obs.json"
        obs_path.write_text(json.dumps(bundle))
        out_path = tmp_path / "staged.json"
        stage_dir = tmp_path / "stages"
        rc = main([
            "--obs", str(obs_path), "--out", str(out_path),
            "--stage-dir", str(stage_dir),
            "--volume-m3", "20000.0", "--area-m2", "40000.0",
            "--dt-s", "1800.0", "--spinup-s", "3600.0",
            "--train-frac", "0.6",
            "--q-lat", "1.5", "2.0", "2.5",
            "--t-lat", "20.0", "25.0", "30.0",
            "--skip-de", "--skip-polish-c", "--skip-polish-d",
            "--lhs-samples", "5", "--min-members", "3",
            "--n-bootstrap", "100",
        ])
        assert rc == 0
        assert out_path.exists()
        doc = json.loads(out_path.read_text())
        assert doc["schema"] == SCHEMA_STAGED
        for sid, _n, _i in STAGE_PLAN:
            path = stage_dir / f"stage_{sid.lower()}.json"
            assert path.exists()
            payload = json.loads(path.read_text())
            assert payload["stage_id"] == sid

    def test_rejects_wrong_schema(self, tmp_path):
        bundle = _synthetic_bundle(dt_s=1800.0)
        bundle["schema"] = "something.else.v1"
        obs_path = tmp_path / "obs.json"
        obs_path.write_text(json.dumps(bundle))
        out_path = tmp_path / "staged.json"
        with pytest.raises(SystemExit) as info:
            main([
                "--obs", str(obs_path), "--out", str(out_path),
                "--volume-m3", "20000.0", "--area-m2", "40000.0",
            ])
        assert info.value.code == 2


class TestForcingHelper:
    def test_forcing_arrays_match_grid_cardinality(self):
        bundle = _synthetic_bundle(dt_s=1800.0)
        arrays = fit_forcing_arrays(bundle, dt_s=1800.0)
        n = len(arrays["grid"])
        for key in ("up_t", "up_q", "air", "rh", "wind", "sw", "cloud"):
            assert len(arrays[key]) == n
        for name in ("air_c", "rh", "wind_mps", "sw", "cloud"):
            series = arrays["met_series"][name]
            assert series.times_s[0] == 0.0
            assert len(series.times_s) == n


class TestStageFilesWriter:
    def test_write_stage_files_round_trips(self, tmp_path):
        bundle = _synthetic_bundle(dt_s=1800.0)
        config = StagedConfig(
            volume_m3=20000.0, area_m2=40000.0, dt_s=1800.0,
            spinup_s=3600.0, train_frac=0.6,
            q_lat_grid=(1.5, 2.0, 2.5),
            t_lat_grid=(20.0, 25.0, 30.0),
            skip_de=True, skip_polish_c=True, skip_polish_d=True,
            lhs_samples=5, min_members=3, n_bootstrap=100)
        doc = run_staged(bundle, config)
        paths = write_stage_files(doc, tmp_path)
        assert set(paths) == {"A", "B", "C", "D"}
        for sid, path in paths.items():
            payload = json.loads(path.read_text())
            assert payload["schema"].endswith(f"stage_{sid.lower()}")
            assert payload["stage_id"] == sid
