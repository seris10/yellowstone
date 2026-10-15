"""Image-gradient sampling and projective geometry checks."""
import numpy as np
import pytest

from tools.sample_image_gradient import (bilinear, fit_homography, linear_to_srgb,
                                        sample_transect, srgb_to_linear, transform_points)


def test_color_roundtrip():
    values = np.linspace(0, 1, 1001)
    np.testing.assert_allclose(linear_to_srgb(srgb_to_linear(values)), values, atol=1e-14)


def test_linear_light_strip_average():
    image = np.zeros((3, 5, 3))
    image[2] = 1
    result = sample_transect(image, [0, 1], [4, 1], 5, 1, 3)
    np.testing.assert_allclose([row["linear_rgb"] for row in result["samples"]], 1/3)
    assert result["samples"][0]["hex"] == "#9c9c9c"


def test_analytic_linear_gradient():
    linear = np.tile(np.linspace(0, 1, 65)[None, :, None], (4, 1, 3))
    result = sample_transect(linear_to_srgb(linear), [0, 1], [64, 1], 33)
    np.testing.assert_allclose([row["linear_gradient"] for row in result["samples"]], 1/64, atol=1e-14)


def test_bilinear_outside_is_missing():
    values, valid = bilinear(np.ones((3, 3, 3)), np.array([[-1, 1], [2, 2], [3, 2]]))
    assert valid.tolist() == [False, True, False]
    assert np.all(np.isnan(values[[0, 2]]))
    np.testing.assert_allclose(values[1], 1)


def test_projective_recovery_and_metric_sampling():
    plane = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [4, 7]])
    expected = np.array([[3, .2, 20], [.1, 2, 15], [.01, .02, 1]])
    pixels = transform_points(plane, expected)
    fitted = fit_homography(plane, pixels)
    probes = np.array([[2, 3], [7, 1], [5, 9]])
    np.testing.assert_allclose(transform_points(probes, fitted), transform_points(probes, expected), atol=1e-11)
    result = sample_transect(np.ones((80, 80, 3)), [0, 0], [10, 0], 11, plane_to_pixel=fitted)
    assert result["length"] == 10
    assert [row["distance"] for row in result["samples"]] == list(range(11))
    assert not np.allclose(np.diff([row["pixel"][0] for row in result["samples"]]), 1)


@pytest.mark.parametrize("points", [np.zeros((4, 2)), np.array([[0, 0], [1, 1], [2, 2], [3, 3]])])
def test_degenerate_control_points_rejected(points):
    with pytest.raises(ValueError, match="degenerate"):
        fit_homography(points, points)


def test_missing_strip_not_black():
    result = sample_transect(np.ones((4, 4, 3)), [-2, 1], [-1, 1], 3)
    assert all(row["srgb"] is None and row["hex"] is None for row in result["samples"])


def test_partially_visible_strip_reports_support():
    result = sample_transect(np.ones((3, 3, 3)), [0, 0], [2, 0], 3, 1, 3)
    assert result["samples"][1]["valid_fraction"] == pytest.approx(2/3)
    assert result["samples"][1]["hex"] == "#ffffff"
