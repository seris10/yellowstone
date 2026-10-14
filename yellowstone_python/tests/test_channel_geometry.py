"""Pinning tests for tools/channel_geometry.py (synthetic/offline, no I/O)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.channel_geometry import (_cross_section_from_dem,
                                    _dem_mean_depth, _unit_perpendicular,
                                    _usgs_mean_depth)

WATER_Y = 100.0


def _flat(x, z):
    return WATER_Y - 1.0


def _dry(x, z):
    return WATER_Y + 5.0


FEATURE = {"id": "stub_01",
           "points": [[0.0, WATER_Y, 0.0], [200.0, WATER_Y, 0.0]]}


def test_unit_perpendicular_basis():
    px, pz = _unit_perpendicular(10.0, 0.0)
    assert px == pytest.approx(0.0)
    assert pz == pytest.approx(1.0)
    assert _unit_perpendicular(0.0, 0.0) == (0.0, 0.0)


def test_cross_section_flat_depth():
    area, width, mean = _cross_section_from_dem(0.0, 0.0, WATER_Y, 0.0, 1.0,
                                                _flat)
    assert width == pytest.approx(70.0)
    assert mean == pytest.approx(1.0, abs=0.02)
    assert area == pytest.approx(width * mean, rel=0.05)


def test_cross_section_dry_returns_zeros():
    assert _cross_section_from_dem(0.0, 0.0, WATER_Y, 0.0, 1.0,
                                   _dry) == (0.0, 0.0, 0.0)


def test_bank_threshold_sensitivity_010_vs_015():
    def slope(x, z):
        return WATER_Y - 0.2 + abs(x) * 0.005
    narrow = _cross_section_from_dem(0.0, 0.0, WATER_Y, 1.0, 0.0, slope,
                                     min_depth=0.10)
    wide = _cross_section_from_dem(0.0, 0.0, WATER_Y, 1.0, 0.0, slope,
                                   min_depth=0.15)
    assert narrow[1] > wide[1] > 0


def test_dem_mean_depth_success_shape():
    out = _dem_mean_depth(FEATURE, _flat)
    assert out["status"] == "authored_estimate_from_usgs_3dep_dem"
    assert out["depth_m"] == pytest.approx(1.0, abs=0.05)
    assert out["depth_m"] == round(out["depth_m"], 3)
    assert "mean_area=" in out["source"] and "depth_std=" in out["source"]


def test_dem_mean_depth_fallback_shape():
    out = _dem_mean_depth(FEATURE, _dry)
    assert out["depth_m"] == 1.1
    assert out["status"] == "default_assumed_no_valid_transects"
    assert out["source"] == "feature stub_01: no valid DEM transects"
    assert out["n_transects_valid"] == 0
    assert out["valid_fraction"] == 0.0


def test_usgs_mean_depth_conversion():
    out = _usgs_mean_depth({"measurements": [{"area_sqft": 100.0,
                                               "width_ft": 10.0}]})
    assert out["depth_m"] == pytest.approx(3.048)
    assert out["status"] == "usgs_field_measurement_current_meter"


def test_usgs_mean_depth_empty_none():
    assert _usgs_mean_depth({"measurements": []}) is None


def test_golden_cross_sections_json():
    path = Path(__file__).resolve(
        ).parents[1] / "configs" / "cross_sections.json"
    doc = json.loads(path.read_text())
    doc = {k: v for k, v in doc.items() if not k.startswith("_")}
    depths = [doc[k]["depth_m"] for k in sorted(doc)]
    assert depths == [0.53, 0.529, 0.512, 0.521, 0.513]
    assert all(v["status"] == "authored_estimate_from_usgs_3dep_dem"
               for v in doc.values())


def test_tool_import_safe():
    r = subprocess.run([sys.executable, "-c",
                        "from tools.channel_geometry import analyze; "
                        "print('import-only ok')"],
                       capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parents[1]))
    assert r.returncode == 0
    assert "import-only ok" in r.stdout
