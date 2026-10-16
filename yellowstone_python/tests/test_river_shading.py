"""Tests for the per-cell river shortwave shading model."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from yellowstone_python.aquatic.river_shading import DEFAULT_CANOPY_TRANSMISSIVITY, DIFFUSE_FRACTION_DEFAULT, DIRECT_BEAM_FRACTION_DEFAULT, TerrainGrid, canopy_direct_beam_fraction, describe_model, horizon_angle_rad, load_terrain_source, shortwave_multiplier, sky_view_factor, solar_position


def _flat_terrain(elevation_m: float = 100.0, half: float = 100.0,
                  spacing_m: float = 2.0) -> TerrainGrid:
    """Flat DEM over [-half, half] in local x,z."""
    n = int(2.0 * half / spacing_m) + 1
    return TerrainGrid(
        heights_m=np.full((n, n), elevation_m, dtype=np.float32),
        origin_xz_m=(-half, -half),
        cell_size_m=spacing_m,
    )


def _bank_terrain(base_m: float = 100.0, half: float = 100.0,
                  spacing_m: float = 2.0,
                  bank_height_m: float = 15.0,
                  bank_x_m: float = 20.0) -> TerrainGrid:
    """DEM with a vertical bank east of x = bank_x_m."""
    n = int(2.0 * half / spacing_m) + 1
    xs = -half + np.arange(n) * spacing_m
    heights = np.full((n, n), base_m, dtype=np.float32)
    for i, x in enumerate(xs):
        if x >= bank_x_m:
            heights[:, i] = base_m + bank_height_m
    return TerrainGrid(
        heights_m=heights,
        origin_xz_m=(-half, -half),
        cell_size_m=spacing_m,
    )


def test_horizon_zero_on_flat_terrain():
    grid = _flat_terrain()
    assert horizon_angle_rad(grid, 0.0, 0.0, 0.0) == pytest.approx(0.0)
    assert horizon_angle_rad(grid, 0.0, 0.0, math.pi / 2.0) == (
        pytest.approx(0.0))


def test_bank_raises_horizon_toward_east():
    grid = _bank_terrain(bank_height_m=20.0, bank_x_m=10.0)
    east = horizon_angle_rad(grid, 0.0, 0.0, math.pi / 2.0)
    west = horizon_angle_rad(grid, 0.0, 0.0, -math.pi / 2.0)
    assert east > west
    assert east > math.radians(45.0)


def test_sky_view_falls_in_bank_shadow():
    flat = _flat_terrain()
    banked = _bank_terrain()
    svf_flat = sky_view_factor(flat, 0.0, 0.0, azimuth_count=16)
    svf_banked = sky_view_factor(banked, 0.0, 0.0, azimuth_count=16)
    assert svf_flat > svf_banked
    assert svf_flat == pytest.approx(1.0, abs=1e-6)
    assert 0.0 < svf_banked < 1.0


def test_canopy_blocks_direct_beam_when_tree_in_sun_path():
    tree_east = [{"x": 5.0, "z": 0.0, "crown_r_m": 3.0}]
    tree_behind = [{"x": -5.0, "z": 0.0, "crown_r_m": 3.0}]
    sun_az = math.pi / 2.0
    sun_el = math.radians(30.0)
    blocked = canopy_direct_beam_fraction(
        tree_east, 0.0, 0.0, sun_az, sun_el, tree_height_m=15.0,
        tau=0.1)
    open_sky = canopy_direct_beam_fraction(
        tree_behind, 0.0, 0.0, sun_az, sun_el, tree_height_m=15.0,
        tau=0.1)
    assert blocked < open_sky
    assert blocked == pytest.approx(0.1)
    assert open_sky == pytest.approx(1.0)


def test_shortwave_multiplier_combines_terrain_and_canopy():
    midday = datetime(2024, 7, 1, 19, 0, tzinfo=timezone.utc)
    flat = _flat_terrain(half=200.0, spacing_m=4.0)
    banked = _bank_terrain(half=200.0, spacing_m=4.0,
                           bank_height_m=50.0, bank_x_m=5.0)
    open_tree_list: list[dict] = []
    out_flat = shortwave_multiplier(flat, open_tree_list, 0.0, 0.0, midday,
                                    svf=1.0)
    out_banked = shortwave_multiplier(banked, open_tree_list, 0.0, 0.0,
                                      midday,
                                      svf=sky_view_factor(banked, 0.0, 0.0))
    assert out_flat["shortwave_multiplier"] >= out_banked["shortwave_multiplier"]


def test_daily_shortwave_is_lower_in_narrow_section():
    bank = _bank_terrain(bank_height_m=40.0, bank_x_m=5.0)
    open_sky = _flat_terrain()
    open_tree_list: list[dict] = []
    svf_bank = sky_view_factor(bank, 0.0, 0.0)
    svf_open = sky_view_factor(open_sky, 0.0, 0.0)
    daily_bank = 0.0
    daily_open = 0.0
    base_day = datetime(2024, 7, 1, 0, 0, tzinfo=timezone.utc)
    for hour in range(0, 24, 3):
        when = base_day.replace(hour=hour)
        bank_row = shortwave_multiplier(bank, open_tree_list, 0.0, 0.0, when,
                                        svf=svf_bank)
        open_row = shortwave_multiplier(open_sky, open_tree_list, 0.0, 0.0,
                                        when, svf=svf_open)
        daily_bank += bank_row["shortwave_multiplier"]
        daily_open += open_row["shortwave_multiplier"]
    assert daily_bank < daily_open


def test_solar_position_runs_and_returns_radians():
    noon = datetime(2024, 7, 1, 19, 0, tzinfo=timezone.utc)
    sp = solar_position(noon)
    assert sp["elevation_rad"] > math.radians(50.0)
    assert math.isfinite(sp["azimuth_rad"])


def test_describe_model_contains_sources():
    doc = describe_model()
    assert doc["schema"] == "yellowstone.river_shading.v1"
    assert "Hardy" in doc["sources"]["canopy_transmissivity"]
    assert doc["parameters"]["default_canopy_transmissivity"] == pytest.approx(
        DEFAULT_CANOPY_TRANSMISSIVITY)
    assert (DIRECT_BEAM_FRACTION_DEFAULT + DIFFUSE_FRACTION_DEFAULT
            == pytest.approx(1.0))


@pytest.mark.needs_world
@pytest.mark.needs_network_inputs
def test_load_terrain_source_reads_real_dem():
    grid = load_terrain_source()
    assert grid.heights_m.shape == (1025, 1025)
    assert grid.cell_size_m == 4.0
    sample = grid.elevation_at(0.0, 0.0)
    assert 2100.0 < sample < 2500.0
