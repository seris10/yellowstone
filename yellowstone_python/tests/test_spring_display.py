"""Authored spring palette and metric terrace checks."""
import numpy as np
import pytest

from tools.prepare_spring_display import palette_profile, shoreline_distance, terrace_field
from tools.sample_image_gradient import srgb_to_linear


def test_palette_interpolates_in_linear_light():
    values = palette_profile(np.array([0, .5, 1]), [[0, "#000000"], [1, "#ffffff"]])
    np.testing.assert_allclose(values, np.array([[0, 0, 0], [.5, .5, .5], [1, 1, 1]]))


def test_palette_reproduces_reference_colors():
    colors = ["#2371a9", "#15a3a1", "#e9cc58", "#f18233"]
    values = palette_profile(np.arange(4), list(enumerate(colors)))
    expected = np.array([[int(c[i:i+2], 16)/255 for i in (1, 3, 5)] for c in colors])
    np.testing.assert_allclose(values, srgb_to_linear(expected), atol=1e-14)


def test_palette_rejects_unordered_coordinates():
    with pytest.raises(ValueError):
        palette_profile(np.arange(2), [[1, "#000000"], [0, "#ffffff"]])


def test_signed_shoreline_distance_for_concave_polygon():
    polygon = np.array([[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]])
    x = np.array([.5, 2, 5, 1])
    z = np.array([.5, 2, .5, 1])
    distances, inside = shoreline_distance(x, z, polygon)
    np.testing.assert_allclose(distances, [-.5, 1, 1, 0])
    assert inside[:3].tolist() == [True, False, False]


def test_metric_relief_is_deterministic_bounded_and_resolved():
    x, z = np.meshgrid(np.linspace(-50, 50, 401), np.linspace(20, 120, 401))
    height, slope = terrace_field(x, z, [0, 0, 0], 6.5, .065, .8)
    assert np.max(np.abs(height)) < .04
    assert .02 < np.linalg.norm(slope, axis=-1).max() < .08
    other, derivative = terrace_field(x, z, [0, 0, 0], 6.5, .065, .8)
    np.testing.assert_array_equal(other, height)
    np.testing.assert_array_equal(derivative, slope)
    coarse, coarse_slope = terrace_field(x[::2, ::2], z[::2, ::2], [0, 0, 0], 6.5, .065, .8)
    np.testing.assert_allclose(coarse, height[::2, ::2], atol=1e-14)
    assert np.sqrt(np.mean((coarse_slope[1:-1, 1:-1]-slope[2:-2:2, 2:-2:2])**2)) < .0015


def test_terrace_edges_follow_repeated_outflow_facing_drops():
    x, z = np.meshgrid(np.linspace(-1, 1, 5), np.linspace(20, 120, 801))
    _, slope = terrace_field(x, z, [0, 0, 0], 6.5, .065, .8)
    faces = -slope[:, 2, 1] > .016
    starts = np.flatnonzero(np.diff(faces.astype(int)) == 1)
    assert 14 <= len(starts) <= 17
    assert np.all((np.diff(z[starts, 2]) > 5.5) & (np.diff(z[starts, 2]) < 7.5))
