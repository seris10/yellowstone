"""Tests for the Nugent (2015) 1-D radiative-transfer pool color ramp."""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import pytest
from PIL import Image

import yellowstone_python.thermal_features.microbial_mats as mm
from yellowstone_python.thermal_features.microbial_mats import pool_ramp, radiative_transfer_color, write_pool_ramp_png
from yellowstone_python.thermal_features.pool_crust import shell_for_pool


def _test_shell(name: str = "Grand Prismatic Spring") -> dict:
    return shell_for_pool({
        "id": "p01", "name": name, "source_id": "1001",
        "center": [0.0, 0.0, 0.0],
        "ring": [[-5.0, -5.0], [5.0, -5.0], [5.0, 5.0], [-5.0, 5.0]],
        "area_m2": 1000.0,
        "temperature_c": 72.0,
    })


def test_radiative_transfer_at_zero_depth_returns_mat_color():
    mat_rgb = (0.85, 0.30, 0.10)
    rgb = radiative_transfer_color(0.0, mat_rgb,
                                   surface_reflection=0.0)
    assert rgb[0] == pytest.approx(mat_rgb[0], abs=1e-6)
    assert rgb[1] == pytest.approx(mat_rgb[1], abs=1e-6)
    assert rgb[2] == pytest.approx(mat_rgb[2], abs=1e-6)


def test_deep_water_is_bluer_than_shallow_water():
    mat_rgb = (0.85, 0.30, 0.10)
    shallow = radiative_transfer_color(0.1, mat_rgb)
    deep = radiative_transfer_color(10.0, mat_rgb)
    shallow_blue_ratio = shallow[2] / max(shallow[0], 1e-9)
    deep_blue_ratio = deep[2] / max(deep[0], 1e-9)
    assert deep_blue_ratio > shallow_blue_ratio
    assert deep[0] < shallow[0]


def test_pool_ramp_bluer_toward_center_matches_mat_at_rim():
    shell = _test_shell()
    ramp = pool_ramp(shell)
    samples = ramp["samples"]
    assert ramp["schema"] == mm.SCHEMA_POOL_RAMP
    assert samples[0]["r_m"] == 0.0
    assert samples[-1]["r_m"] == pytest.approx(shell["r_water_m"])
    # Center sample is deeper so bluer; rim sample is shallow mat.
    center_rgb = samples[0]["rgb01"]
    rim_rgb = samples[-1]["rgb01"]
    assert center_rgb[2] / max(center_rgb[0], 1e-9) > rim_rgb[2] / max(rim_rgb[0], 1e-9)


def test_pool_ramp_carries_sources():
    shell = _test_shell()
    ramp = pool_ramp(shell)
    joined = " ".join(ramp["sources"])
    assert "Pope and Fry" in joined
    assert "Nugent" in joined


def test_grand_prismatic_optics_separates_bottom_from_surface_temperature():
    shell = _test_shell()
    ramp = pool_ramp(shell)
    assert {sample["class"] for sample in ramp["samples"]} == {mm.CLASS_YELLOW}
    assert ramp["samples"][0]["depth_m"] == shell["depth_center_m"]
    assert ramp["samples"][-1]["depth_m"] == 0.0
    assert "uniform yellow mat" in ramp["bottom_basis"]
    assert pool_ramp(_test_shell("Other pool"))["samples"][-1]["depth_m"] > 0.0


def test_write_pool_ramp_png_writes_image():
    shell = _test_shell()
    ramp = pool_ramp(shell, n_samples=16)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "ramp.png")
        write_pool_ramp_png(ramp, out, width=32, height=2)
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0


def test_pool_ramp_sidecar_round_trips_json():
    shell = _test_shell()
    ramp = pool_ramp(shell, n_samples=8)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "ramp.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(ramp, fh)
        with open(out, "r", encoding="utf-8") as fh:
            back = json.load(fh)
    assert back["schema"] == mm.SCHEMA_POOL_RAMP
    assert len(back["samples"]) == 8


@pytest.mark.parametrize("depth", [0.1, 1.0, 37.0, 100.0])
def test_column_matches_independent_gaussian_quadrature(depth):
    """Integrate the upward source over depth independently of its closed form."""
    nodes, weights = np.polynomial.legendre.leggauss(96)
    positions = (nodes + 1.0) * depth / 2.0
    mat = (0.4, 0.3, 0.2)
    reflection = 0.02
    expected = []
    for a, b, bottom in zip((0.340, 0.0565, 0.00922), (0.0008, 0.0015, 0.0035), mat):
        column = float(np.dot(weights, 0.5 * b * np.exp(-(2.0 * a + b) * positions))) * depth / 2.0
        expected.append(0.002 + (1.0 - reflection) ** 2 * (bottom * np.exp(-(2.0 * a + b) * depth) + column))
    assert radiative_transfer_color(depth, mat) == pytest.approx(expected, abs=1e-12)


def test_absorption_without_scattering_emits_no_column_light(monkeypatch):
    monkeypatch.setattr(mm, "_scattering_rgb", lambda: (0.0, 0.0, 0.0))
    assert radiative_transfer_color(100.0, (0.0, 0.0, 0.0), surface_reflection=0.0) == (0.0, 0.0, 0.0)
    monkeypatch.setattr(mm, "_absorption_rgb", lambda: (0.0, 0.0, 0.0))
    assert radiative_transfer_color(100.0, (0.1, 0.2, 0.3), surface_reflection=0.0) == (0.1, 0.2, 0.3)


def test_ramp_texture_encodes_linear_light_once(tmp_path):
    ramp = {"samples": [{"fraction": 0.0, "rgb01": [0.0, 0.18, 1.0]},
                        {"fraction": 1.0, "rgb01": [1.0, 0.18, 0.0]}]}
    path = tmp_path / "ramp.png"
    write_pool_ramp_png(ramp, str(path), width=3)
    with Image.open(path) as image:
        assert image.getpixel((0, 0)) == (0, 118, 255)
        assert image.getpixel((1, 0)) == (188, 118, 188)
    generated = pool_ramp(_test_shell())
    assert generated["color_space"] == "linear_rgb"
    assert generated["texture_color_space"] == "srgb"


@pytest.mark.parametrize("depth", [0.0, 0.01, 1.0, 50.0, 1e6])
def test_normalized_passive_water_cannot_exceed_incident_light(depth):
    for bottom in [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]:
        assert all(0.0 <= value <= 1.0 for value in radiative_transfer_color(depth, bottom))
