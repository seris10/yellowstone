"""Tests for the optional hyporheic storage-zone term on the replay cells."""
from __future__ import annotations

import math

import pytest

from yellowstone_python.river.river_transport import Cell, HyporheicZone, River, RHO_CP_J_M3_K, Series


def _diurnal_air() -> Series:
    """A single-period air temperature oscillating around 10 degC."""
    times = tuple(i * 1800.0 for i in range(49))
    values = tuple(
        10.0 + 6.0 * math.sin((t / 86400.0) * 2.0 * math.pi)
        for t in times
    )
    return Series(times, values)


def _make_cells() -> list[Cell]:
    return [
        Cell(id=f"c{i}", length_m=50.0, width_m=20.0,
             volume_m3=50.0 * 20.0 * 1.0, initial_c=12.0,
             dispersion_m2_s=0.5, exchange_w_m2_k=25.0)
        for i in range(4)
    ]


def test_default_hyporheic_off_matches_baseline():
    cells = _make_cells()
    baseline = River(cells, boundary_m3_s=2.0, boundary_c=12.0,
                     air_c=_diurnal_air())
    baseline.run(86400.0, dt_s=30.0, sample_s=3600.0)
    off_run = River(cells, boundary_m3_s=2.0, boundary_c=12.0,
                    air_c=_diurnal_air(),
                    hyporheic_zones=None)
    off_run.run(86400.0, dt_s=30.0, sample_s=3600.0)
    for a, b in zip(baseline.temperature_c, off_run.temperature_c):
        assert a == pytest.approx(b, abs=1e-12)


def _diurnal_range(temps: list[float]) -> float:
    return max(temps) - min(temps)


def test_hyporheic_damps_diurnal_range():
    cells = _make_cells()
    air = _diurnal_air()
    unperturbed = River(cells, boundary_m3_s=2.0, boundary_c=12.0,
                        air_c=air)
    base_frames = unperturbed.run(86400.0, dt_s=30.0, sample_s=1800.0)
    base_cell = [row["temperature_c"][2] for row in base_frames]

    perturbed_cells = _make_cells()
    zone = HyporheicZone(storage_volume_m3=4000.0, alpha_per_s=5e-4)
    perturbed = River(perturbed_cells, boundary_m3_s=2.0, boundary_c=12.0,
                      air_c=air,
                      hyporheic_zones={"c2": zone})
    perturbed_frames = perturbed.run(86400.0, dt_s=30.0,
                                     sample_s=1800.0)
    perturbed_cell = [row["temperature_c"][2] for row in perturbed_frames]
    assert _diurnal_range(perturbed_cell) < _diurnal_range(base_cell)


def test_channel_plus_storage_heat_is_conserved():
    cells = [
        Cell(id="c", length_m=50.0, width_m=20.0,
             volume_m3=50.0 * 20.0 * 1.0, initial_c=30.0,
             dispersion_m2_s=0.0, exchange_w_m2_k=0.0),
    ]
    zone = HyporheicZone(storage_volume_m3=500.0, alpha_per_s=2e-3,
                         initial_c=10.0)
    river = River(cells, boundary_m3_s=0.0, boundary_c=30.0,
                  air_c=30.0,
                  hyporheic_zones={"c": zone})
    initial_channel_j = (
        RHO_CP_J_M3_K * cells[0].volume_m3 * cells[0].initial_c)
    initial_storage_j = (
        RHO_CP_J_M3_K * zone.storage_volume_m3 * zone.initial_c)
    initial_total_j = initial_channel_j + initial_storage_j
    river.run(1800.0, dt_s=30.0, sample_s=1800.0)
    budget = river.budget()
    hypo = budget["hyporheic"]
    final_channel_j = (
        RHO_CP_J_M3_K * cells[0].volume_m3 * river.temperature_c[0])
    final_storage_j = (
        RHO_CP_J_M3_K * zone.storage_volume_m3
        * hypo["storage_temperature_c"][0])
    final_total_j = final_channel_j + final_storage_j
    assert abs(final_total_j - initial_total_j) < 1.0
    assert abs(hypo["combined_relative_residual"]) < 1e-10
    assert hypo["cells_with_zone"] == 1
    assert "Bencala" in hypo["source"]
    assert river.temperature_c[0] < cells[0].initial_c
    assert hypo["storage_temperature_c"][0] > zone.initial_c


def test_cell_schedule_still_closes_with_hyporheic():
    cells = _make_cells()
    zone = HyporheicZone(storage_volume_m3=2000.0, alpha_per_s=1e-3)
    river = River(cells, boundary_m3_s=2.0, boundary_c=12.0,
                  air_c=_diurnal_air(),
                  hyporheic_zones={"c2": zone})
    river.run(7200.0, dt_s=30.0, sample_s=1800.0)
    budget = river.budget()
    assert budget["heat_relative_residual"] < 1e-7
    assert budget["water_relative_residual"] < 1e-12
    assert budget["hyporheic"] is not None
    assert budget["hyporheic"]["combined_relative_residual"] < 1e-7


def test_transient_exchange_closes_to_roundoff():
    cells = _make_cells()
    zones = {cell.id: HyporheicZone(storage_volume_m3=2000.0,
                                    alpha_per_s=1e-3, initial_c=20.0)
             for cell in cells}
    river = River(cells, boundary_m3_s=2.0, boundary_c=12.0,
                  air_c=_diurnal_air(), hyporheic_zones=zones)
    river.run(7200.0, dt_s=30.0, sample_s=1800.0)
    budget = river.budget()
    assert abs(budget["hyporheic_exchange_j"]) > 1e9
    assert budget["heat_relative_residual"] < 1e-12
    assert budget["hyporheic"]["combined_relative_residual"] < 1e-12
    assert budget["max_step_heat_residual_j"] < 1e-2
    assert budget["max_cell_heat_residual_j"] < 1e-2


def test_hyporheic_rejects_unknown_cell_id():
    cells = _make_cells()
    with pytest.raises(ValueError):
        River(cells, boundary_m3_s=2.0, boundary_c=12.0,
              hyporheic_zones={
                  "nope": HyporheicZone(100.0, 1e-3),
              })


def test_shortwave_multiplier_scales_surface_shortwave():
    cells = _make_cells()
    budget_spec = {
        "rh": {"times_s": [0.0], "values": [0.6]},
        "wind_mps": {"times_s": [0.0], "values": [2.0]},
        "shortwave_w_m2": {"times_s": [0.0], "values": [600.0]},
        "cloud": {"times_s": [0.0], "values": [0.3]},
    }
    full = River(cells, boundary_m3_s=2.0, boundary_c=12.0,
                 air_c=10.0, surface_budget=budget_spec)
    full.run(600.0, dt_s=30.0, sample_s=600.0)
    full_budget = full.budget()
    shaded = River(_make_cells(), boundary_m3_s=2.0, boundary_c=12.0,
                   air_c=10.0, surface_budget=budget_spec,
                   shortwave_multiplier={cell.id: 0.1 for cell in cells})
    shaded.run(600.0, dt_s=30.0, sample_s=600.0)
    shaded_budget = shaded.budget()
    assert shaded_budget["surface_shortwave_j"] < (
        0.5 * full_budget["surface_shortwave_j"])
    assert shaded.temperature_c[0] < full.temperature_c[0]


def test_shortwave_multiplier_defaults_identical():
    cells = _make_cells()
    budget_spec = {
        "rh": {"times_s": [0.0], "values": [0.6]},
        "wind_mps": {"times_s": [0.0], "values": [2.0]},
        "shortwave_w_m2": {"times_s": [0.0], "values": [500.0]},
        "cloud": {"times_s": [0.0], "values": [0.2]},
    }
    reference = River(cells, boundary_m3_s=2.0, boundary_c=12.0,
                      air_c=10.0, surface_budget=budget_spec)
    reference.run(1200.0, dt_s=30.0, sample_s=1200.0)
    with_default = River(_make_cells(), boundary_m3_s=2.0, boundary_c=12.0,
                         air_c=10.0, surface_budget=budget_spec,
                         shortwave_multiplier={})
    with_default.run(1200.0, dt_s=30.0, sample_s=1200.0)
    for a, b in zip(reference.temperature_c, with_default.temperature_c):
        assert a == pytest.approx(b, abs=1e-12)
