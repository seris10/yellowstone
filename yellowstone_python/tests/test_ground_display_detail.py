"""Physical surface spectra and mapped display contrast."""
import numpy as np
import pytest

from tools.prepare_ground_detail import mapped_contrast, mineral_field


def test_metric_height_has_declared_rms_and_band_limited_spectrum():
    height, derivatives, parameters = mineral_field(512)
    assert np.sqrt(np.mean(height ** 2)) == pytest.approx(.0045)
    assert parameters["evidence_class"] == "authored_display_parameter"
    assert parameters["uncertainty"] == "unknown"
    frequency = np.fft.fftfreq(512, d=4 / 512)
    radial = np.hypot(frequency[:, None], frequency[None, :])
    power = np.abs(np.fft.fft2(height)) ** 2
    outside = (radial < 1 / 1.5) | (radial > 1 / .02)
    assert power[outside].sum() < power.sum() * 1e-24
    assert abs(height.mean()) < 1e-15
    assert np.isfinite(derivatives).all()


def test_spectral_derivatives_match_independent_periodic_difference():
    height, derivatives, _ = mineral_field()
    finite = np.stack([(np.roll(height, -1, axis=axis) - np.roll(height, 1, axis=axis)) / (2 * 4 / 1024)
                       for axis in (1, 0)], axis=-1)
    assert np.sqrt(np.mean((finite - derivatives) ** 2)) / np.sqrt(np.mean(derivatives ** 2)) < .12
    assert np.corrcoef(finite.ravel(), derivatives.ravel())[0, 1] > .995


def test_surface_is_deterministic_without_resetting_global_random_state():
    state = np.random.get_state()
    first = mineral_field(128)
    second = mineral_field(128)
    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])
    assert np.array_equal(state[1], np.random.get_state()[1])


def test_constant_mapped_color_retains_unity_without_inventing_detail():
    rgb = np.full((64, 64, 3), .7)
    before = rgb.copy()
    ratio = mapped_contrast(rgb, .625)
    assert np.allclose(ratio, 1, atol=1e-12)
    assert np.array_equal(rgb, before)


def test_mapped_contrast_retains_positions_and_bounds_extremes():
    rgb = np.full((64, 64, 3), .5)
    rgb[20:25, 32:37] = .9
    rgb[40:45, 10:15] = .05
    ratio = mapped_contrast(rgb, .625)
    assert .45 <= ratio.min() <= .4500001
    assert ratio.max() == 1.7
    assert ratio[22, 34].mean() > ratio[0, 0].mean()
    assert ratio[42, 12].mean() < ratio[0, 0].mean()


@pytest.mark.parametrize("size,width", [(32, 4), (128, 0), (128, -2)])
def test_surface_rejects_invalid_metric_grid(size, width):
    with pytest.raises(ValueError):
        mineral_field(size, width)
