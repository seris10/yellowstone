"""Tests for the microbial mat community and pigment model."""
from __future__ import annotations

import numpy as np
import pytest

import yellowstone_python.thermal_features.microbial_mats as mm
from yellowstone_python.thermal_features.microbial_mats import CLASS_BROWN_GREEN, CLASS_ID_BY_NAME, CLASS_ORANGE, CLASS_PINK, CLASS_WHITE, CLASS_YELLOW, CLASS_YELLOW_GREEN, PHOTOSYNTHESIS_LIMIT_ACIDIC_C, PHOTOSYNTHESIS_LIMIT_NEUTRAL_C, PIGMENT_RELAXATION_TAU_DAYS, build_mat_state, classify_cell, classify_temperature_field, integrate_pigment, photosynthesis_limit_c, relax_pigment, steady_state_pigment_index


def test_temperature_sweep_matches_nugent_table_1():
    assert classify_cell(86.0) == CLASS_WHITE
    assert classify_cell(82.0) == CLASS_PINK
    assert classify_cell(75.0) == CLASS_YELLOW
    assert classify_cell(72.0) == CLASS_YELLOW
    assert classify_cell(68.0) == CLASS_YELLOW_GREEN
    assert classify_cell(57.0) == CLASS_ORANGE
    assert classify_cell(43.0) == CLASS_BROWN_GREEN
    assert classify_cell(float("nan")) == "sinter_dry"


def test_acidic_ph_lowers_photosynthesis_edge():
    neutral = photosynthesis_limit_c(8.0)
    acidic = photosynthesis_limit_c(3.5)
    assert neutral == pytest.approx(PHOTOSYNTHESIS_LIMIT_NEUTRAL_C)
    assert acidic == pytest.approx(PHOTOSYNTHESIS_LIMIT_ACIDIC_C)
    assert acidic < neutral
    # A 60 C pool is a mat in neutral water; above the photo limit in acidic.
    assert classify_cell(60.0, ph=8.0) == CLASS_ORANGE
    assert classify_cell(60.0, ph=3.5) == "water_hot_clear"


def test_more_irradiance_raises_carotenoid_index():
    low = steady_state_pigment_index(50.0)
    high = steady_state_pigment_index(300.0)
    assert high > low
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0


def test_cloud_cover_reduces_daily_insolation():
    clear = mm.kasten_czeplak_cloud_attenuation(0.0)
    overcast = mm.kasten_czeplak_cloud_attenuation(1.0)
    assert clear == pytest.approx(1.0)
    assert overcast == pytest.approx(0.25)
    assert overcast < clear


def test_daily_mean_insolation_summer_vs_winter():
    summer = mm.daily_mean_insolation_w_m2(
        "2026-06-21", latitude=44.525, longitude=-110.837,
        daily_cloud_fraction=0.3, altitude_m=2216.0)
    winter = mm.daily_mean_insolation_w_m2(
        "2026-12-21", latitude=44.525, longitude=-110.837,
        daily_cloud_fraction=0.3, altitude_m=2216.0)
    assert summer["all_sky_mean_w_m2"] > winter["all_sky_mean_w_m2"]
    assert any("Kasten" in s for s in summer["sources"])


def test_relaxation_reaches_steady_state_under_constant_forcing():
    history = integrate_pigment(
        initial_index=0.0,
        steady_values=[0.6] * 200,
        dt_days=1.0,
        tau_days=PIGMENT_RELAXATION_TAU_DAYS,
    )
    assert history[0] == 0.0
    assert history[-1] == pytest.approx(0.6, abs=1e-3)
    # Monotone convergence.
    diffs = np.diff(history)
    assert np.all(diffs >= -1.0e-9)


def test_relax_pigment_single_step_approaches_target():
    out = relax_pigment(0.0, 1.0, dt_days=100.0,
                        tau_days=PIGMENT_RELAXATION_TAU_DAYS)
    assert out == pytest.approx(1.0, abs=0.1)


def test_classify_temperature_field_handles_nodata():
    arr = np.array([
        [np.nan, 86.0, 82.0],
        [75.0, 68.0, 57.0],
        [43.0, 20.0, 60.0],
    ])
    classes = classify_temperature_field(arr, ph=8.0)
    assert classes[0, 0] == -1
    assert classes[0, 1] == CLASS_ID_BY_NAME[CLASS_WHITE]
    assert classes[0, 2] == CLASS_ID_BY_NAME[CLASS_PINK]
    assert classes[1, 0] == CLASS_ID_BY_NAME[CLASS_YELLOW]
    assert classes[1, 1] == CLASS_ID_BY_NAME[CLASS_YELLOW_GREEN]
    assert classes[1, 2] == CLASS_ID_BY_NAME[CLASS_ORANGE]
    assert classes[2, 0] == CLASS_ID_BY_NAME[CLASS_BROWN_GREEN]
    assert classes[2, 1] == CLASS_ID_BY_NAME[CLASS_BROWN_GREEN]
    assert classes[2, 2] == CLASS_ID_BY_NAME[CLASS_ORANGE]


def test_build_mat_state_initial_pigment_equals_steady_state():
    arr = np.full((4, 4), 60.0)
    state = build_mat_state(arr, previous_pigment=None,
                            daily_mean_shortwave_w_m2=250.0, dt_days=1.0)
    expected = steady_state_pigment_index(250.0)
    assert state.pigment_index.shape == arr.shape
    assert np.allclose(state.pigment_index, expected, atol=1e-6)
    assert state.community_class.shape == arr.shape
    assert state.reflectance_rgb.shape == (4, 4, 3)


def test_build_mat_state_pigment_relaxes_from_previous():
    arr = np.full((2, 2), 60.0)
    prev = np.zeros((2, 2), dtype=np.float32)
    state = build_mat_state(arr, previous_pigment=prev,
                            daily_mean_shortwave_w_m2=250.0,
                            dt_days=1.0,
                            tau_days=PIGMENT_RELAXATION_TAU_DAYS)
    expected_target = steady_state_pigment_index(250.0)
    expected_step = (1.0 / (1.0 + PIGMENT_RELAXATION_TAU_DAYS)
                     * (expected_target - 0.0))
    assert np.allclose(state.pigment_index, expected_step, atol=1e-6)
    assert np.all(state.pigment_index < expected_target)


def test_mat_state_sidecar_carries_citations_schema_and_band_edges():
    arr = np.full((2, 2), 60.0)
    state = build_mat_state(arr, daily_mean_shortwave_w_m2=200.0,
                            dt_days=1.0)
    sidecar = state.to_sidecar(
        forcing_epoch_utc=1_700_000_000.0,
        daily_mean_shortwave_w_m2=200.0,
        daily_cloud_fraction=0.3,
        ph=8.0,
    )
    assert sidecar["schema"] == mm.SCHEMA_MAT_STATE
    assert sidecar["pigment_relaxation_tau_days"] == PIGMENT_RELAXATION_TAU_DAYS
    assert sidecar["band_edges_status"] == mm.CLASS_BAND_EDGES_STATUS
    for row in sidecar["class_band_edges_c"]:
        assert row["status"] == "authored_from_table"
    cites = " ".join(sidecar["citations"])
    assert "Nugent" in cites and "Brock" in cites and "Kasten" in cites


def test_mat_pigment_png_nodata_and_sinter_are_transparent(tmp_path):
    from PIL import Image
    n = mm.CORE_GRID_SIZE
    arr = np.full((n, n), np.nan)
    arr[0, 0] = 60.0
    state = build_mat_state(arr, daily_mean_shortwave_w_m2=200.0,
                            dt_days=1.0)
    state.community_class[0, 1] = CLASS_ID_BY_NAME["sinter_dry"]
    path = tmp_path / "mat_pigment.png"
    mm.write_mat_pigment_png(state, str(path))
    alpha = np.asarray(Image.open(path).convert("RGBA"))[..., 3]
    assert alpha[0, 0] == 255
    assert alpha[0, 2] == 0
    assert alpha[2, 2] == 0
    assert int((alpha > 0).sum()) == 4
