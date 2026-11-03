"""Offline tests for overland_flow (synthetic terrain, no network)."""
import math

import numpy as np
import pytest

import yellowstone_python.land.overland_flow as OF
from yellowstone_python.land.overland_flow import GRID, run_overland, _downsample

hs, _hs_prov = OF._import_hydrosim()
needs_hydrosim = pytest.mark.skipif(hs is None, reason="hydrosim not present")


def _write_terrain(tmp_path, elev=2100.0):
    """1025 x 1025 little-endian float32 DEM with a tilted basin."""
    z = np.full((GRID, GRID), elev, dtype="<f4")
    z += np.linspace(0.0, 40.0, GRID, dtype=np.float32)[:, None]
    path = tmp_path / "data"
    path.mkdir(exist_ok=True)
    (path / "terrain.f32").write_bytes(z.tobytes())
    return tmp_path


def test_downsample_uses_all_source_cells():
    src = np.zeros((1025, 1025), dtype=np.float64)
    out = _downsample(src, 1025, 256)
    assert out.shape == (256, 256)
    # A spike in the trailing row and column must survive the block-mean.
    src2 = np.ones((1025, 1025), dtype=np.float64)
    src2[1024, 1024] = 1025.0
    out2 = _downsample(src2, 1025, 256)
    assert out2[255, 255] > 1.0


def test_downsample_uniform_field_is_exact():
    src = np.full((1025, 1025), 7.5, dtype=np.float64)
    out = _downsample(src, 1025, 256)
    assert np.allclose(out, 7.5)


def test_downsample_rejects_bad_sizes():
    src = np.zeros((16, 16))
    with pytest.raises(ValueError, match="positive"):
        _downsample(src, 0, 4)
    with pytest.raises(ValueError, match="must not exceed"):
        _downsample(src, 4, 16)
    with pytest.raises(ValueError, match="does not match"):
        _downsample(src, 1025, 4)


def test_missing_hydrosim_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "_import_hydrosim",
                        lambda: (None, "hydrosim not on the import path"))
    out = run_overland(_write_terrain(tmp_path))
    assert out["status"] == "not_available"
    assert out["field"] == [] and out["seconds"] == OF.DEFAULT_SIM_S


def test_input_validation(tmp_path):
    root = _write_terrain(tmp_path)
    for kwargs in ({"rain_mm_h": -1.0}, {"dt_s": 0.0}, {"sim_s": -5.0},
                   {"grid": 0}, {"cell_m": 0.0}, {"grid": 2048},
                   {"soil": "peat"}, {"rain_mm_h": float("nan")}):
        with pytest.raises(ValueError):
            run_overland(root, **kwargs)


@pytest.mark.needs_science
@needs_hydrosim
def test_soil_parameter_changes_effective_configuration(tmp_path):
    root = _write_terrain(tmp_path)
    base = run_overland(root, soil="sandy_loam", grid=16, sim_s=3600.0,
                        dt_s=600.0, rain_mm_h=50.0)
    clay = run_overland(root, soil="clay", grid=16, sim_s=3600.0,
                        dt_s=600.0, rain_mm_h=50.0)
    assert base["status"] == "illustrative_not_calibrated"
    assert base["configuration"]["soil"] == "sandy_loam"
    assert base["configuration"]["soil_map"] == "uniform_requested_soil"
    assert clay["configuration"]["soil"] == "clay"
    assert clay["soil"] == "clay"
    # Clay Ksat is far below sandy loam, so ponded depth must differ.
    assert max(clay["field"]) > max(base["field"])


@pytest.mark.needs_science
@needs_hydrosim
def test_partial_step_reports_actual_seconds(tmp_path):
    root = _write_terrain(tmp_path)
    out = run_overland(root, grid=8, sim_s=100.0, dt_s=60.0)
    assert out["seconds"] == pytest.approx(100.0)
    assert len(out["field"]) == 8 * 8


@pytest.mark.needs_science
@needs_hydrosim
def test_zero_duration_runs_no_steps(tmp_path):
    root = _write_terrain(tmp_path)
    out = run_overland(root, grid=8, sim_s=0.0, dt_s=60.0)
    assert out["seconds"] == 0.0
    assert all(v == 0.0 for v in out["field"])


@pytest.mark.needs_science
@needs_hydrosim
def test_balance_values_are_finite(tmp_path):
    root = _write_terrain(tmp_path)
    out = run_overland(root, grid=8, sim_s=120.0, dt_s=60.0)
    assert out["status"] in ("illustrative_not_calibrated", "balance_invalid")
    for v in out["balance"].values():
        assert math.isfinite(v)


@pytest.mark.needs_science
@needs_hydrosim
def test_configuration_records_effective_settings(tmp_path):
    root = _write_terrain(tmp_path)
    out = run_overland(root, grid=8, sim_s=60.0, dt_s=60.0)
    cfg = out["configuration"]
    for key in ("infiltration", "manning_overland", "enable_et",
                "perc_factor", "init_wetness", "max_substeps",
                "source_dem_cells", "sim_grid", "downsampling",
                "hydrosim"):
        assert key in cfg
    assert cfg["source_dem_cells"] == [GRID, GRID]
    assert cfg["downsampling"] == "block_mean_full_extent"
    assert cfg["runoff_boundary_mode"] == "closed_domain"
    assert cfg["boundary_role"] == "upstream_inflow"
    assert out["outflow_mapping_status"] == "not_available"
    assert out["runoff_series"] is None
    diag = out["solver_diagnostics"]
    assert diag["cfl_exceeded_count"] == 0
    assert "boundary_condition" in diag
    assert "outflow_slope" in diag


def test_open_edges_validation_rejects_unknown(tmp_path):
    root = _write_terrain(tmp_path)
    with pytest.raises(ValueError, match="unknown open edges"):
        run_overland(root, grid=8, sim_s=60.0, dt_s=60.0,
                     open_edges=("east",))
    with pytest.raises(ValueError, match="string"):
        run_overland(root, grid=8, sim_s=60.0, dt_s=60.0,
                     open_edges="left")


def test_boundary_role_round_trips_in_configuration(tmp_path):
    root = _write_terrain(tmp_path)
    out = run_overland(root, grid=8, sim_s=0.0, dt_s=60.0,
                       boundary_role="lateral_source")
    # sim_s=0 skips hydrosim; status is not_available or illustrative_not_calibrated; role echoes back.
    if "configuration" in out:
        assert out["configuration"]["boundary_role"] == "lateral_source"
    with pytest.raises(ValueError, match="boundary_role"):
        run_overland(root, grid=8, sim_s=0.0, dt_s=60.0,
                     boundary_role="floating")


@pytest.mark.needs_science
@needs_hydrosim
def test_rain_schedule_mapping_splits_at_breakpoints(tmp_path):
    root = _write_terrain(tmp_path)
    schedule = {"times_s": [0.0, 60.0], "values": [20.0, 0.0]}
    out = run_overland(root, grid=8, sim_s=120.0, dt_s=120.0,
                       rain_mm_h=schedule)
    assert out["rain_schedule"]["mode"] == "piecewise_constant"
    # The breakpoint at t=60 splits the single 120 s step into two.
    assert len(out["outflow_series"]["times_s"]) == 2
    assert out["rain_mm_h"] == pytest.approx(10.0, rel=1e-9)
