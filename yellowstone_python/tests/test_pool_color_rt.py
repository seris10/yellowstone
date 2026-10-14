"""Tests for the Nugent (2015) 1-D radiative-transfer pool color ramp."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

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
