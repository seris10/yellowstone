"""Numerical verification of the river-temperature engine.

These tests verify mathematical/software behavior, not Yellowstone
calibration, species tolerances, or surveyed geometry.
"""
from __future__ import annotations

import math
import unittest

from yellowstone_python.replay.river_transport import (
    Cell,
    River,
    RHO_CP_J_M3_K,
    Series,
    Source,
    river_from_config,
)

class RiverTransportTests(unittest.TestCase):
    def test_uniform_temperature_is_preserved(self):
        cells = [
            Cell(
                id=f"c{i}",
                length_m=20.0 + i,
                width_m=3.0,
                volume_m3=40.0 + 10.0 * i,
                initial_c=20.0,
                dispersion_m2_s=0.8,
                exchange_w_m2_k=15.0,
            )
            for i in range(5)
        ]
        river = River(
            cells,
            boundary_m3_s=2.0,
            boundary_c=20.0,
            air_c=20.0,
            sources=[
                Source("lateral", "c2", 0.3, 20.0),
            ],
        )
        river.run(1000.0, dt_s=13.0, sample_s=1000.0)

        for temperature in river.temperature_c:
            self.assertAlmostEqual(temperature, 20.0, places=10)

        self.assertLess(
            river.budget()["heat_relative_residual"], 1e-10
        )

    def test_one_cell_steady_solution_matches_formula(self):
        cell = Cell(
            "c", 100.0, 10.0, 100.0, 12.0,
            exchange_w_m2_k=20.0,
        )
        river = River(
            [cell],
            boundary_m3_s=2.0,
            boundary_c=10.0,
            air_c=5.0,
            net_heat_flux_w_m2=100.0,
            sources=[Source("hot", "c", 1.0, 60.0)],
        )

        exchange = (
            cell.exchange_w_m2_k
            * cell.surface_area_m2
            / RHO_CP_J_M3_K
        )
        extra = (
            cell.surface_area_m2 * 100.0 / RHO_CP_J_M3_K
        )
        expected = (
            2.0 * 10.0 + 1.0 * 60.0 + exchange * 5.0 + extra
        ) / (3.0 + exchange)

        self.assertAlmostEqual(
            river.steady_temperatures()[0], expected, places=12
        )

    def test_cell_heat_closes_budget(self):
        cells = [
            Cell(f"c{i}", 50.0, 20.0, 50.0 * 20.0 * 1.1, 10.0,
                 dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
            for i in range(5)
        ]
        river = River(
            cells,
            boundary_m3_s=2.0,
            boundary_c=15.0,
            air_c=5.0,
            cell_heat_w={"c2": 1000.0},
        )
        river.run(600.0, dt_s=10.0, sample_s=600.0)
        budget = river.budget()
        self.assertAlmostEqual(budget["cell_heat_j"], 600000.0)
        self.assertLess(budget["heat_relative_residual"], 1e-9)
        with self.assertRaises(ValueError):
            River(
                cells,
                boundary_m3_s=2.0,
                boundary_c=15.0,
                cell_heat_w={"missing": 1.0},
            )

    def test_time_refinement_improves_one_cell_solution(self):
        def calculate(dt_s):
            river = River(
                [Cell("c", 10.0, 1.0, 10.0, 10.0)],
                boundary_m3_s=1.0,
                boundary_c=20.0,
            )
            river.run(10.0, dt_s=dt_s, sample_s=10.0)
            return river.temperature_c[0]

        exact = 20.0 - 10.0 * math.exp(-1.0)
        coarse_error = abs(calculate(1.0) - exact)
        fine_error = abs(calculate(0.5) - exact)

        self.assertLess(fine_error, 0.6 * coarse_error)

    def test_advection_grid_refinement_reduces_front_error(self):
        def calculate_error(n):
            dx = 1.0 / n
            river = River(
                [
                    Cell(f"c{i}", dx, 1.0, dx, 0.0)
                    for i in range(n)
                ],
                boundary_m3_s=1.0,
                boundary_c=1.0,
            )
            river.run(
                0.5, dt_s=0.2 * dx, sample_s=0.5
            )

            # Exact plug-flow solution: a unit-temperature front
            # travels at 1 m/s and is at s=0.5 m after 0.5 s.
            return math.fsum(
                dx * abs(
                    temperature
                    - (1.0 if (i + 0.5) * dx < 0.5 else 0.0)
                )
                for i, temperature in enumerate(river.temperature_c)
            )

        self.assertLess(
            calculate_error(80), calculate_error(40)
        )

    def test_large_step_does_not_create_temperature_overshoot(self):
        river = River(
            [
                Cell(
                    f"c{i}", 10.0, 2.0, 20.0,
                    5.0 if i % 2 == 0 else 30.0,
                    dispersion_m2_s=2.0,
                    exchange_w_m2_k=10.0,
                )
                for i in range(4)
            ],
            boundary_m3_s=1.0,
            boundary_c=12.0,
            air_c=8.0,
            sources=[Source("hot", "c1", 0.2, 40.0)],
        )
        river.step(100000.0)

        for temperature in river.temperature_c:
            self.assertGreaterEqual(temperature, 5.0 - 1e-10)
            self.assertLessEqual(temperature, 40.0 + 1e-10)

    def test_closed_dispersion_conserves_energy(self):
        cells = [
            Cell(
                "a", 10.0, 1.0, 10.0, 10.0,
                dispersion_m2_s=2.0,
            ),
            Cell(
                "b", 30.0, 1.0, 30.0, 30.0,
                dispersion_m2_s=2.0,
            ),
        ]
        river = River(cells, 0.0, 0.0)

        initial = math.fsum(
            cell.volume_m3 * temperature
            for cell, temperature in zip(
                cells, river.temperature_c
            )
        )
        river.step(1000000.0)
        final = math.fsum(
            cell.volume_m3 * temperature
            for cell, temperature in zip(
                cells, river.temperature_c
            )
        )

        self.assertTrue(
            math.isclose(initial, final, rel_tol=1e-10)
        )
        self.assertGreater(river.temperature_c[0], 10.0)
        self.assertLess(river.temperature_c[1], 30.0)

    def test_prescribed_surface_power_changes_storage(self):
        cell = Cell("c", 100.0, 2.0, 100.0, 5.0)
        river = River(
            [cell],
            boundary_m3_s=0.0,
            boundary_c=5.0,
            net_heat_flux_w_m2=50.0,
        )
        river.step(10.0)

        expected_j = 50.0 * cell.surface_area_m2 * 10.0
        budget = river.budget()

        self.assertAlmostEqual(
            budget["surface_exchange_j"], expected_j, places=6
        )
        self.assertAlmostEqual(
            budget["storage_change_j"], expected_j, delta=1e-3
        )

    def test_forcing_changes_are_not_integrated_early(self):
        river = River(
            [Cell("c", 10.0, 1.0, 10.0, 0.0)],
            boundary_m3_s=1.0,
            boundary_c=Series(
                (0.0, 2.0), (0.0, 10.0)
            ),
        )

        # A direct step cannot straddle the t=2 forcing change.
        with self.assertRaises(ValueError):
            river.step(3.0)
        self.assertEqual(river.time_s, 0.0)

        river.run(3.0, dt_s=5.0, sample_s=3.0)

        # First interval [0,2] stays at 0 C.
        # Second interval [2,3] applies the new inflow:
        # (10*T_new) = (10*0) + 1*(10 - T_new).
        self.assertAlmostEqual(
            river.temperature_c[0], 10.0 / 11.0, places=12
        )
        self.assertEqual(river.steps, 2)
        self.assertEqual(river.time_s, 3.0)

    def test_run_records_exact_final_time(self):
        river = River(
            [Cell("c", 10.0, 1.0, 10.0, 10.0)],
            1.0, 10.0,
        )
        frames = river.run(
            25.0, dt_s=7.0, sample_s=10.0
        )
        self.assertEqual(
            [frame["t_s"] for frame in frames],
            [0.0, 10.0, 20.0, 25.0],
        )

    def test_zero_duration_returns_starting_state(self):
        river = River(
            [Cell("c", 10.0, 1.0, 10.0, 10.0)],
            1.0, 10.0,
        )
        frames = river.run(0.0)
        self.assertEqual(len(frames), 1)
        self.assertEqual(river.steps, 0)

    def test_repeat_runs_are_deterministic(self):
        config = {
            "cells": [
                {
                    "id": "c",
                    "length_m": 10.0,
                    "width_m": 2.0,
                    "volume_m3": 20.0,
                    "initial_c": 12.0,
                }
            ],
            "boundary_m3_s": 1.0,
            "boundary_c": 17.0,
        }
        a = river_from_config(config)
        b = river_from_config(config)

        self.assertEqual(
            a.run(30.0, 2.0, 10.0),
            b.run(30.0, 2.0, 10.0),
        )

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            Cell("c", 0.0, 1.0, 10.0, 10.0)

        with self.assertRaises(ValueError):
            Series((0.0, 0.0), (10.0, 20.0))

        with self.assertRaises(ValueError):
            Source("s", "c", -1.0, 20.0)

        cell = Cell("c", 10.0, 1.0, 10.0, 10.0)

        with self.assertRaises(ValueError):
            River([cell, cell], 1.0, 10.0)

        with self.assertRaises(ValueError):
            River(
                [cell], 1.0, 10.0,
                sources=[Source("s", "missing", 1.0, 20.0)],
            )

        river = River([cell], 1.0, 10.0)
        with self.assertRaises(ValueError):
            river.run(10.0, dt_s=0.0)

    def test_closed_unforced_steady_problem_is_not_unique(self):
        river = River(
            [Cell("c", 10.0, 1.0, 10.0, 10.0)],
            0.0, 10.0,
        )
        with self.assertRaises(ArithmeticError):
            river.steady_temperatures()

if __name__ == "__main__":
    unittest.main()