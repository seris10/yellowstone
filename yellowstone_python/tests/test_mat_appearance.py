"""Tests for the mat appearance layer and instantaneous shortwave forcing."""
from __future__ import annotations

import datetime

import numpy as np
import pytest

import yellowstone_python.thermal_features.mat_appearance as ma
from yellowstone_python.thermal_features.microbial_mats import CLASS_ID_BY_NAME, MatState, instantaneous_shortwave_w_m2

ORANGE = np.array([0.79, 0.44, 0.27])
SINTER = np.array([0.92, 0.91, 0.88])


def test_srgb_to_lab_reference_points():
    lab = ma.srgb_to_lab(np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]))
    assert lab[0] == pytest.approx([100.0, 0.0, 0.0], abs=0.05)
    assert lab[1] == pytest.approx([0.0, 0.0, 0.0], abs=0.05)


def test_flow_intensity_is_monotone_and_bounded():
    ff = np.array([0.0, 1e-12, 1e-6, 1e-3, 1.0, np.nan])
    fi = ma.flow_intensity(ff)
    assert fi[0] == 0.0 and fi[1] == 0.0 and fi[-1] == 0.0
    assert fi[2] < fi[3] < fi[4]
    assert fi.max() <= 1.0


def test_imagery_mat_strength_separates_mat_sinter_and_vegetation():
    photo = np.tile(SINTER, (8, 8, 1))
    photo[2] = ORANGE
    photo[5] = [0.20, 0.35, 0.18]
    region = np.ones((8, 8), dtype=bool)
    region[:, 7] = False
    m, meta = ma.imagery_mat_strength(photo, region)
    assert m[2, 0] > 0.9
    assert m[0, 0] == 0.0
    assert m[5, 0] == 0.0
    assert m[2, 7] == 0.0
    assert meta["warm_top"] > meta["sinter_warm_median"]


def test_streamline_average_smooths_along_flow_only():
    field = np.zeros((1, 21, 21))
    field[0, 10, 10] = 1.0
    direction = np.zeros((2, 21, 21))
    direction[1] = 1.0
    rows = np.array([10, 12])
    cols = np.array([12, 10])
    avg = ma.streamline_average(field, direction, rows, cols, steps=4)
    assert avg[0, 0] > 0.0
    assert avg[0, 1] == 0.0


def _synthetic_inputs(n=16):
    classes = np.full((n, n), -1, dtype=np.int16)
    classes[4:12, :] = CLASS_ID_BY_NAME["brown_green_mixed_photosynthetic"]
    temperature = np.where(classes >= 0, 31.0, np.nan)
    state = MatState(community_class=classes,
                     pigment_index=np.ones((n, n), dtype=np.float32),
                     reflectance_rgb=np.zeros((n, n, 3), dtype=np.float32))
    flow = np.where(classes >= 0, 1e-3, 0.0)
    dem = np.tile(np.linspace(10.0, 0.0, n), (n, 1))
    size = n * ma.UPSAMPLE
    photo = np.tile(SINTER, (size, size, 1))
    photo[10:22, ::3] = ORANGE
    photo[:, :2] = [0.05, 0.08, 0.10]
    mineral = np.ones((size, size))
    return state, temperature, flow, dem, photo, mineral


def test_render_is_smooth_and_masks_water():
    state, temperature, flow, dem, photo, mineral = _synthetic_inputs()
    rgba, meta = ma.render_mat_appearance(state, temperature, flow, dem,
                                          photo, mineral)
    assert rgba.shape == (32, 32, 4)
    assert meta["schema"] == ma.SCHEMA_MAT_APPEARANCE
    assert rgba[:, 0, 3].max() == 0
    assert rgba[16, 16, 3] > 0
    blocks = np.repeat(np.repeat(rgba[::2, ::2], 2, axis=0), 2, axis=1)
    assert not np.array_equal(rgba, blocks)


def test_render_rejects_mismatched_photo_grid():
    state, temperature, flow, dem, photo, mineral = _synthetic_inputs()
    with pytest.raises(ValueError):
        ma.render_mat_appearance(state, temperature, flow, dem,
                                 photo[:-2], mineral)


def test_instantaneous_shortwave_follows_sun_and_cloud():
    noon = datetime.datetime(2026, 7, 15, 19, 0, tzinfo=datetime.timezone.utc)
    night = datetime.datetime(2026, 7, 15, 7, 0, tzinfo=datetime.timezone.utc)
    clear = instantaneous_shortwave_w_m2(noon.timestamp(), 44.525, -110.837,
                                         0.0, altitude_m=2240.0)
    cloudy = instantaneous_shortwave_w_m2(noon.timestamp(), 44.525, -110.837,
                                          1.0, altitude_m=2240.0)
    dark = instantaneous_shortwave_w_m2(night.timestamp(), 44.525, -110.837,
                                        0.0, altitude_m=2240.0)
    assert 800.0 < clear["all_sky_w_m2"] < 1100.0
    assert cloudy["all_sky_w_m2"] == pytest.approx(0.25 * clear["all_sky_w_m2"])
    assert dark["all_sky_w_m2"] == 0.0
    with pytest.raises(ValueError):
        instantaneous_shortwave_w_m2(noon.timestamp(), 44.5, -110.8, 1.5)
