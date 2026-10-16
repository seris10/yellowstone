"""Tests for the outflow_network module."""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pytest

import yellowstone_python.thermal_features.outflow_network as onet


def _synthetic_dem(nx: int = 64, nz: int = 64) -> np.ndarray:
    """Conical hill rising at the center on a 1 m synthetic grid."""
    cx = (nx - 1) * 0.5
    cz = (nz - 1) * 0.5
    xs = np.arange(nx) - cx
    zs = np.arange(nz) - cz
    xx, zz = np.meshgrid(xs, zs)
    dem = 100.0 + 10.0 * np.exp(-(xx ** 2 + zz ** 2) / (2 * (nx * 0.25) ** 2))
    return dem.astype(np.float32)


def _grid_for(dem: np.ndarray) -> onet.Grid:
    """Grid whose extent spans the given DEM."""
    size = dem.shape[0]
    assert dem.shape == (size, size)
    return onet.Grid(cell_m=1.0, size=size, half_m=size / 2)


def test_polygon_mask_and_rim_mask_consistency():
    grid = onet.Grid(cell_m=1.0, size=32, half_m=16.0)
    ring = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
    mask = onet.polygon_mask(ring, grid)
    assert mask.any()
    rim = onet.rim_mask(mask)
    # Each rim cell has at least one 4-neighbor outside the pool mask.
    for jj, ii in zip(*np.where(rim)):
        touches_outside = False
        for dj, di in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nj, ni = jj + dj, ii + di
            if 0 <= nj < grid.size and 0 <= ni < grid.size and not mask[nj, ni]:
                touches_outside = True
                break
        assert touches_outside, "rim cell should touch outside the pool mask"


def test_fill_depressions_fills_a_closed_pit():
    dem = np.full((16, 16), 100.0, dtype=np.float32)
    dem[8, 8] = 50.0
    filled = onet.fill_depressions(dem, epsilon=1e-3)
    assert filled[8, 8] > dem[8, 8]
    assert filled[8, 8] <= 100.0 + 1.0


def test_mfd_weights_sum_to_one_where_slope_exists():
    dem = _synthetic_dem(32, 32)
    filled = onet.fill_depressions(dem, epsilon=1e-4)
    weights = onet.mfd_weights(filled, cell_m=1.0)
    sums = weights.sum(axis=2)
    nontrivial = sums > 0
    assert np.all(np.isclose(sums[nontrivial], 1.0, atol=1e-5))


def _ring_injections(nz: int, nx: int, radius: int, amount_total: float
                     ) -> list[tuple[int, int, int, float]]:
    """Divide amount equally over 16 points on a ring around the center."""
    cz = nz // 2
    cx = nx // 2
    pts = []
    for angle in np.linspace(0, 2 * math.pi, 16, endpoint=False):
        j = int(round(cz + radius * math.sin(angle)))
        i = int(round(cx + radius * math.cos(angle)))
        pts.append((0, j, i, amount_total / 16))
    return pts


def test_propagate_discharge_conservation():
    dem = _synthetic_dem(32, 32)
    filled = onet.fill_depressions(dem, epsilon=1e-4)
    weights = onet.mfd_weights(filled, cell_m=1.0)
    injections = _ring_injections(32, 32, radius=4, amount_total=1.0)
    discharge, dominant, exported = onet.propagate_discharge(
        weights, filled, injections)
    assert discharge.shape == (1, filled.shape[0], filled.shape[1])
    # All injected mass must leave the grid in a radially draining cone.
    assert math.isclose(float(exported[0]), 1.0, rel_tol=1e-3, abs_tol=1e-3)
    # The dominant array labels the injection cells themselves.
    for _, j, i, _ in injections:
        assert dominant[j, i] == 0


def test_propagate_descends_downhill():
    dem = _synthetic_dem(32, 32)
    filled = onet.fill_depressions(dem, epsilon=1e-4)
    weights = onet.mfd_weights(filled, cell_m=1.0)
    injections = _ring_injections(32, 32, radius=4, amount_total=1.0)
    discharge, _, _ = onet.propagate_discharge(weights, filled, injections)
    acc = discharge[0]
    max_inj_elev = max(filled[j, i] for _, j, i, _ in injections)
    live = acc > 1e-6
    assert np.all(filled[live] <= max_inj_elev + 1e-3)


def test_classify_wet_mask_respects_thermal_mask():
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    rgb[:, :, 0] = 0.9
    rgb[:, :, 1] = 0.1
    rgb[:, :, 2] = 0.1
    tmask = np.zeros((8, 8), dtype=bool)
    tmask[2:6, 2:6] = True
    wet, _ = onet.classify_wet_mask(rgb, tmask)
    assert not bool(wet[0, 0])
    assert bool(wet[3, 3])


def test_derive_outflow_network_cli_raises_without_dem(tmp_path):
    import subprocess
    import sys
    env = os.environ.copy()
    env["PYTHONPATH"] = str(
        Path(__file__).resolve().parents[1]) + ":" + env.get("PYTHONPATH", "")
    out_dir = tmp_path / "out"
    cmd = [sys.executable,
           str(Path(__file__).resolve().parents[1] / "tools" /
               "derive_outflow_network.py"),
           "--dem", str(tmp_path / "missing.tif"),
           "--pools", str(tmp_path / "missing_world.json"),
           "--out-dir", str(out_dir)]
    completed = subprocess.run(cmd, capture_output=True, env=env, text=True, check=False)
    assert completed.returncode != 0
    stderr = completed.stderr.lower() + completed.stdout.lower()
    assert "dem" in stderr or "not found" in stderr


def test_extract_channels_segments_split_at_confluences():
    dem = _synthetic_dem(32, 32)
    filled = onet.fill_depressions(dem, epsilon=1e-4)
    weights = onet.mfd_weights(filled, cell_m=1.0)
    grid = _grid_for(filled)
    cx_i = filled.shape[1] // 2
    cz_j = filled.shape[0] // 2
    rim_cells = []
    for angle in np.linspace(0, 2 * math.pi, 16, endpoint=False):
        j = int(round(cz_j + 3 * math.sin(angle)))
        i = int(round(cx_i + 3 * math.cos(angle)))
        rim_cells.append((j, i, 1.0 / 16))
    injections = [(0, j, i, w) for j, i, w in rim_cells]
    discharge, _, _ = onet.propagate_discharge(weights, filled, injections)
    slope = onet.slope_magnitude(filled, cell_m=1.0)
    pool_mask = np.zeros_like(filled, dtype=bool)
    rim_mask_arr = np.zeros_like(filled, dtype=bool)
    for j, i, _ in rim_cells:
        pool_mask[j, i] = True
        rim_mask_arr[j, i] = True
    springs = [{
        "pool_id": "synthetic",
        "name": "synthetic",
        "index": 0,
        "center_xz": grid.cell_center_xz(cz_j, cx_i),
        "rim_cells": rim_cells,
        "pool_mask": pool_mask,
        "rim_mask": rim_mask_arr,
    }]
    segments = onet.extract_channels(
        springs, weights, discharge, slope,
        wet=np.zeros_like(filled, dtype=bool),
        grid=grid,
        river_mask=np.zeros_like(filled, dtype=bool),
        flow_threshold=0.001)
    assert segments, "radial outflow should yield at least one segment"
    heads = [s for s in segments if s["upstream_endpoint_kind"] == "head"]
    assert heads, "at least one head-rooted segment is required"
    for s in segments:
        if s["upstream_endpoint_kind"] == "head":
            assert s["upstream_id"] is None
        else:
            # Non-head segments must link to a parent segment at a confluence.
            assert s["upstream_id"] is not None or s.get("terminator") == "confluence"


def test_cleanup_segments_prunes_short_low_flow_spur_and_merges_chains():
    grid = onet.Grid(cell_m=1.0, size=16, half_m=8.0)
    slope = np.zeros((16, 16), dtype=np.float32)
    raw = [
        {
            "id": "seg_0000", "spring_index": 0, "upstream_id": None,
            "points_xz": [[-1.5, -1.5], [-0.5, -0.5]],
            "length_m": 1.414, "mean_slope": 0.01, "width_m": 1.0,
            "width_source": "fallback_default_authored",
            "flow_fraction": 0.6, "imagery_wet_fraction": 0.0,
            "leaves_core_grid": False, "reaches_river": False,
            "terminator": "confluence",
            "upstream_endpoint_xz": [-1.5, -1.5],
            "downstream_endpoint_xz": [-0.5, -0.5],
            "upstream_endpoint_kind": "head",
        },
        {
            "id": "seg_0001", "spring_index": 0, "upstream_id": "seg_0000",
            "points_xz": [[-0.5, -0.5], [0.3, 0.3]],
            "length_m": 1.0, "mean_slope": 0.02, "width_m": 1.0,
            "width_source": "fallback_default_authored",
            "flow_fraction": 0.05, "imagery_wet_fraction": 0.0,
            "leaves_core_grid": False, "reaches_river": False,
            "terminator": "dry",
            "upstream_endpoint_xz": [-0.5, -0.5],
            "downstream_endpoint_xz": [0.3, 0.3],
            "upstream_endpoint_kind": "confluence",
        },
        {
            "id": "seg_0002", "spring_index": 0, "upstream_id": "seg_0000",
            "points_xz": [[-0.5, -0.5], [0.5, 0.5], [1.5, 1.5], [2.5, 2.5]],
            "length_m": 4.242, "mean_slope": 0.03, "width_m": 1.0,
            "width_source": "fallback_default_authored",
            "flow_fraction": 0.6, "imagery_wet_fraction": 0.0,
            "leaves_core_grid": False, "reaches_river": True,
            "terminator": "river",
            "upstream_endpoint_xz": [-0.5, -0.5],
            "downstream_endpoint_xz": [2.5, 2.5],
            "upstream_endpoint_kind": "confluence",
        },
    ]
    cleaned, report = onet.cleanup_segments(raw, slope, grid)
    assert report["pre_count"] == 3
    assert report["pruned_count"] >= 1
    assert all(seg["id"] != "seg_0001" for seg in cleaned)
    assert abs(report["terminal_flow_delta"]["0"]) < 1e-6


def test_rasterize_rivers_mask_marks_near_polyline_cells():
    grid = onet.Grid(cell_m=1.0, size=32, half_m=16.0)
    rivers = [{
        "points": [[-10.0, 0.0, 0.0], [10.0, 0.0, 0.0]],
        "width": 3.0,
    }]
    mask = onet.rasterize_rivers_mask(rivers, grid)
    assert mask.any()
    j, i = grid.world_to_index(0.0, 0.0)
    assert bool(mask[j, i])
    j, i = grid.world_to_index(0.0, 10.0)
    assert not bool(mask[j, i])


@pytest.mark.needs_world
def test_real_dem_integration_matches_pixel_comparison():
    tif = (Path(__file__).resolve().parents[2]
           / "yellowstone_midway" / "references" / "dem_1m_core.tif")
    if not tif.exists():
        pytest.skip("real 1 m DEM tile is not present")
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    arr = np.asarray(Image.open(tif))
    assert arr.shape == (1280, 1280)
    center = arr[arr.shape[0] // 2, arr.shape[1] // 2]
    assert abs(float(center) - 2216.95) < 0.1


ORIENTATION_AGREEMENT_MIN = 0.15
ORIENTATION_AGREEMENT_OVERALL_MIN = 0.30
MIN_SEGMENT_LENGTH_M = 2.0
MIN_SPUR_FLOW_FRACTION = 0.1
TERMINAL_FLOW_PRESERVATION_TOLERANCE = 0.05


@pytest.mark.needs_network_inputs
def test_orientation_agreement_meets_stated_pass_level():
    network = (Path(__file__).resolve().parents[2]
               / "yellowstone_midway" / "data" / "outflow_network"
               / "outflow_network.json")
    if not network.exists():
        pytest.skip("outflow network output is not present")
    import json

    data = json.loads(network.read_text())
    agreement = data["validation"]["orientation_agreement"]
    overall = float(agreement["fraction_on_wet_pixels"])
    assert overall >= ORIENTATION_AGREEMENT_OVERALL_MIN, (
        f"overall orientation agreement {overall} below "
        f"{ORIENTATION_AGREEMENT_OVERALL_MIN}")
    for spring_idx, metrics in agreement["per_spring"].items():
        frac = float(metrics["fraction_on_wet_pixels"])
        assert frac >= ORIENTATION_AGREEMENT_MIN, (
            f"spring {spring_idx} orientation agreement {frac} below "
            f"{ORIENTATION_AGREEMENT_MIN}")


def _load_network():
    network = (Path(__file__).resolve().parents[2]
               / "yellowstone_midway" / "data" / "outflow_network"
               / "outflow_network.json")
    if not network.exists():
        pytest.skip("outflow network output is not present")
    import json
    return json.loads(network.read_text())


def test_cleanup_leaves_no_singleton_segments():
    data = _load_network()
    for seg in data["segments"]:
        assert len(seg["points_xz"]) >= 2, (
            f"segment {seg['id']} has fewer than 2 points")


def test_short_non_terminal_segments_carry_minimum_flow():
    data = _load_network()
    for seg in data["segments"]:
        if seg.get("reaches_river") or seg.get("leaves_core_grid"):
            continue
        if seg.get("upstream_endpoint_kind") == "head":
            continue
        if float(seg["length_m"]) < MIN_SEGMENT_LENGTH_M:
            assert float(seg["flow_fraction"]) >= MIN_SPUR_FLOW_FRACTION, (
                f"short non-terminal non-head segment {seg['id']} carries "
                f"flow {seg['flow_fraction']} below spur-prune threshold "
                f"{MIN_SPUR_FLOW_FRACTION}")


def test_terminal_flow_fractions_preserved_through_cleanup():
    data = _load_network()
    cleanup = data["validation"]["segment_cleanup"]
    for spring_idx, delta in cleanup["terminal_flow_delta"].items():
        assert abs(float(delta)) <= TERMINAL_FLOW_PRESERVATION_TOLERANCE, (
            f"spring {spring_idx} terminal flow delta {delta} exceeds "
            f"tolerance {TERMINAL_FLOW_PRESERVATION_TOLERANCE}")


def test_cleanup_report_fields_present():
    data = _load_network()
    cleanup = data["validation"]["segment_cleanup"]
    for field in ("pre_count", "post_count", "pruned_count", "merged_count",
                  "absorbed_count", "terminal_flow_delta", "ratio_status"):
        assert field in cleanup, f"cleanup report missing {field}"
    assert cleanup["ratio_status"] == "authored"


def test_river_vs_grid_fractions_sum_to_injection():
    data = _load_network()
    fractions = data["validation"]["river_vs_grid_fractions"]
    tolerance = float(data["validation"]["river_vs_grid_tolerance"])
    assert fractions, "river_vs_grid_fractions missing"
    for entry in fractions:
        river = float(entry["river_inflow_fraction"])
        grid_exit = float(entry["grid_exit_fraction"])
        assert 0.0 <= river <= 1.0, (
            f"spring {entry['spring_index']} river_inflow_fraction "
            f"{river} outside [0, 1]")
        assert 0.0 <= grid_exit <= 1.0, (
            f"spring {entry['spring_index']} grid_exit_fraction "
            f"{grid_exit} outside [0, 1]")
        assert abs(river + grid_exit - 1.0) <= tolerance, (
            f"spring {entry['spring_index']} river+grid "
            f"{river + grid_exit} not within {tolerance} of 1.0")


def test_spring_record_carries_conservative_fractions():
    data = _load_network()
    for spring in data["springs"]:
        assert "river_inflow_fraction" in spring
        assert "grid_exit_fraction" in spring
        assert "river_plus_grid_fraction" in spring
        assert 0.0 <= spring["river_inflow_fraction"] <= 1.0
        assert 0.0 <= spring["grid_exit_fraction"] <= 1.0


def test_per_segment_non_additive_note_present():
    data = _load_network()
    assert "per_segment_flow_note" in data["validation"]
    for spring in data["springs"]:
        assert "river_terminal_points_note" in spring


def test_weir_rim_injection_flows_sum_to_discharge():
    z = [100.0, 100.5, 101.0, 100.2, 100.1]
    q = 0.5
    res = onet.weir_rim_injection(z, q)
    total = sum(res["flows_m3_s"])
    assert abs(total - q) < 1e-5, f"flows sum {total} not equal to {q}"
    assert abs(sum(res["weights"]) - 1.0) < 1e-9


def test_weir_rim_injection_zero_flow_above_stage():
    z = [100.0, 100.5, 101.0, 100.2, 100.1]
    q = 0.5
    res = onet.weir_rim_injection(z, q)
    stage = res["pool_stage_m"]
    for zi, fi in zip(z, res["flows_m3_s"]):
        if zi >= stage:
            assert fi == 0.0, (
                f"rim cell at elevation {zi} above stage {stage} should "
                f"carry zero flow, got {fi}")


def test_weir_rim_injection_concentrates_through_a_notch():
    z = [100.0] * 10 + [99.5]  # one low notch
    q = 0.01
    res = onet.weir_rim_injection(z, q)
    weights = res["weights"]
    # Notch cell is index 10; it must carry the majority of flow.
    assert weights[10] > 0.9, (
        f"notch cell should carry >90 percent of flow; got {weights[10]}")


def test_weir_rim_injection_uniform_elevation_distributes_uniformly():
    z = [100.0] * 20
    q = 0.1
    res = onet.weir_rim_injection(z, q)
    weights = np.asarray(res["weights"])
    expected = 1.0 / len(z)
    assert np.allclose(weights, expected, atol=1e-8), (
        f"uniform rim should distribute uniformly; got {weights}")


def test_weir_rim_injection_matches_broad_crested_formula():
    z = [100.0, 100.1]
    q = 0.05
    res = onet.weir_rim_injection(z, q, cd=0.544, g_m_s2=9.81, cell_width_m=1.0)
    stage = res["pool_stage_m"]
    recomputed = sum(0.544 * math.sqrt(9.81) * max(0.0, stage - zi) ** 1.5
                     for zi in z)
    assert abs(recomputed - q) < 1e-5


def test_rim_injection_sensitivity_reports_monte_carlo_bounds():
    z = [100.0, 100.05, 100.1, 100.2]
    q = 0.05
    sens = onet.rim_injection_sensitivity(z, q, rmse_z_m=0.1, n_samples=10,
                                          seed=42)
    mc = sens["monte_carlo"]
    assert mc["rim_length_carrying_50pct_m_min"] <= mc["rim_length_carrying_50pct_m_max"]
    assert mc["rim_length_carrying_90pct_m_min"] <= mc["rim_length_carrying_90pct_m_max"]
    assert mc["pool_stage_above_lowest_rim_m_min"] <= mc["pool_stage_above_lowest_rim_m_max"]
    assert sens["noise_samples"] == 10


def test_derive_tool_emits_weir_fields():
    data = _load_network()
    assert "rim_injection" in data["method"]
    assert data["method"]["rim_injection"]["convention"] == "weir"
    assert "rim_injection_discharges" in data["validation"]
    for entry in data["validation"]["rim_injection_discharges"]:
        assert "pool_stage_above_lowest_rim_m" in entry
        assert "n_active_rim_cells" in entry
        assert "weir_sensitivity_monte_carlo" in entry
    assert "near_rim_imagery_overlap_30m" in data["validation"]


def test_upstream_references_all_resolve():
    data = _load_network()
    ids = {seg["id"] for seg in data["segments"]}
    for seg in data["segments"]:
        upstream = seg.get("upstream_id")
        if upstream is not None:
            assert upstream in ids, (
                f"segment {seg['id']} upstream_id {upstream} not in ids")
        for trib in seg.get("tributary_upstream_ids", []):
            assert trib in ids, (
                f"segment {seg['id']} tributary_upstream_id {trib} not in ids")
    report = data["validation"]["segment_cleanup"].get("dangling_references")
    assert report is not None
    assert "upstream_id_resolution_counts" in report
    assert "tributary_resolution_counts" in report
    assert "orphan_segments_dropped" in report


def test_null_upstream_only_at_rim_heads():
    data = _load_network()
    grid = data["grid"]
    cell_m = float(grid["cell_m"])
    springs_by_index = {s["index"]: s for s in data["springs"]}
    rim_sets: dict = {}
    for s_idx, spring in springs_by_index.items():
        rim_sets[s_idx] = [(float(x), float(z))
                           for x, z in spring.get("rim_xz", [])]
    tol = cell_m * math.sqrt(2.0) + 1e-6
    for seg in data["segments"]:
        if seg.get("upstream_id") is not None:
            continue
        s_idx = int(seg["spring_index"])
        rim = rim_sets.get(s_idx, [])
        x, z = seg["upstream_endpoint_xz"]
        close = any(math.hypot(x - rx, z - rz) <= tol for rx, rz in rim)
        assert close, (
            f"segment {seg['id']} upstream_id is null but starts at "
            f"({x}, {z}) more than one cell from spring {s_idx}'s rim")
