"""Outflow food web: temperature window, population dynamics, mite CV response, raster reader."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from yellowstone_python.thermal_features.outflow_foodweb import FLY_SPECIES, PREDATOR_DIETS, fly_temperature_occupancy, mite_parasitism_fraction_per_generation, mite_parasitism_rate_per_day, outflow_cell_population, outflow_foodweb_from_files, predator_offtake_holling_ii, predators_with_swallow, recruitment_per_m2_per_day


def test_fly_species_are_paracoenia_and_ephydra_bruesi():
    """Name the brine flies reported by Brock et al. (1969)."""
    assert "paracoenia_turbida" in FLY_SPECIES
    assert "ephydra_bruesi" in FLY_SPECIES
    for name, entry in FLY_SPECIES.items():
        assert entry["t_max_c"] <= 40.0, name
        assert entry["corner_status"] == "authored_from_literature_range"
        assert any("doi:" in src.lower() for src in entry["sources"])


def test_temperature_window_zero_at_bounds_and_peaks_in_optimum():
    """Occupancy is zero outside the authored window and flat 1 inside the optimum band."""
    assert fly_temperature_occupancy(5.0) == 0.0
    assert fly_temperature_occupancy(45.0) == 0.0
    assert fly_temperature_occupancy(30.0) == 1.0


def test_predator_entries_use_holling_type_ii_parameters_with_cited_sources():
    """Beetles, dolichopodids, apron spiders and the Yellowstone shorebirds are present with attack."""
    required = {"wetsalts_tiger_beetle", "dolichopodid_fly",
                "riparian_spider_apron", "spotted_sandpiper", "killdeer"}
    assert required.issubset(set(PREDATOR_DIETS))
    for cid, entry in PREDATOR_DIETS.items():
        assert entry["attack_rate_m2_per_day"] > 0.0, cid
        assert entry["handling_time_days"] > 0.0, cid
        assert entry["density_per_m2"] >= 0.0, cid
        assert entry["sources"], f"{cid} needs sources"


def test_predators_with_swallow_sources_swallow_parameters():
    """The apron fly consumer swallow entry is linked to AERIAL_INSECTIVORE_DIETS."""
    from yellowstone_python.insects_birds import AERIAL_INSECTIVORE_DIETS
    merged = predators_with_swallow()
    assert "swallow" in merged
    assert merged["swallow"]["status"] == (
        "linked_to_insects_birds_AERIAL_INSECTIVORE_DIETS")
    assert set(merged["swallow"]["sources"]) == set(
        AERIAL_INSECTIVORE_DIETS["swallow"]["sources"])


def test_holling_ii_bounds_per_predator_rate_above_zero_density():
    """Each predator's per-capita rate saturates at 1/handling as fly density grows."""
    low = predator_offtake_holling_ii(1.0)
    high = predator_offtake_holling_ii(1e6)
    for lcomp, hcomp in zip(low["components"], high["components"]):
        cap = hcomp["max_per_predator_per_day"]
        per_predator_low = lcomp["flies_per_m2_per_day"] / max(
            lcomp["density_per_m2"] * lcomp["diet_share_flies"], 1e-9)
        per_predator_high = hcomp["flies_per_m2_per_day"] / max(
            hcomp["density_per_m2"] * hcomp["diet_share_flies"], 1e-9)
        assert per_predator_high <= cap + 1e-9
        assert per_predator_high > per_predator_low


def test_mite_parasitism_rate_declines_with_outflow_variability():
    """More variable outflow lowers mite parasitism (Wiegert and Mitchell (1973))."""
    stable = mite_parasitism_rate_per_day(0.0)
    unstable = mite_parasitism_rate_per_day(1.0)
    very_unstable = mite_parasitism_rate_per_day(2.5)
    assert stable > unstable > very_unstable >= 0.0
    frac_stable = mite_parasitism_fraction_per_generation(0.0)
    frac_variable = mite_parasitism_fraction_per_generation(1.0)
    assert frac_stable > frac_variable > 0.0


def test_cell_population_balances_recruitment_losses_at_steady_state():
    """At the steady state, parasitism plus predation equals recruitment per day."""
    r = recruitment_per_m2_per_day(temperature_c=30.0,
                                     mat_biomass_g_per_m2=120.0)
    assert r > 0.0
    cell = outflow_cell_population(temperature_c=30.0, mat_area_m2=4.0,
                                     flow_cv=0.2,
                                     mat_biomass_g_per_m2=120.0)
    assert cell["fly_stock_count"] > 0.0
    # Flux residual: recruit - predation - parasitism, in flies/day on the whole cell.
    residual = cell["flux_balance_residual_per_day"]
    assert abs(residual) <= 1e-3 * max(1.0, cell["recruitment_total_per_day"])


def test_cell_population_falls_outside_temperature_window():
    """A cell above the fly maximum temperature carries zero flies."""
    cold = outflow_cell_population(temperature_c=55.0, mat_area_m2=4.0,
                                     flow_cv=0.2)
    assert cold["fly_stock_count"] == 0.0


def test_from_files_reads_wp_b_rasters(tmp_path):
    """outflow_foodweb_from_files reads the real sidecars and the companion float32 and int16 rasters."""
    nx = nz = 4
    cell_m = 1.0
    temps = np.array([
        [30.0, 55.0, float("nan"), 32.0],
        [30.0, 30.0, 20.0, 30.0],
        [np.nan, np.nan, np.nan, np.nan],
        [25.0, 25.0, 25.0, 25.0],
    ], dtype=np.float32)
    community = np.array([
        [2, 2, 2, 2],
        [2, 2, 2, 0],
        [0, 0, 0, 0],
        [2, 2, -1, 2],
    ], dtype="<i2")
    temp_bin = np.ascontiguousarray(temps.astype("<f4"))
    comm_bin = np.ascontiguousarray(community.astype("<i2"))
    temp_f32 = tmp_path / "outflow_temperature.f32"
    comm_i16 = tmp_path / "mat_community.i16"
    temp_f32.write_bytes(temp_bin.tobytes())
    comm_i16.write_bytes(comm_bin.tobytes())
    temp_json = tmp_path / "outflow_temperature.json"
    temp_json.write_text(json.dumps({
        "schema": "yellowstone.outflow_temperature.v1",
        "status": "authored",
        "grid": {"cell_size_m": cell_m, "nx": nx, "nz": nz,
                 "row_order": "north_to_south",
                 "origin_xz_m": [-nx / 2.0, -nz / 2.0]},
        "units": "degC",
        "nodata": "NaN",
        "raster_path": "outflow_temperature.f32",
        "sha256": hashlib.sha256(temp_bin.tobytes()).hexdigest(),
    }))
    mat_json = tmp_path / "mat_state.json"
    mat_json.write_text(json.dumps({
        "schema": "yellowstone.mat_state.v1",
        "status": "authored",
        "rasters": {
            "community": {
                "path": "mat_community.i16", "dtype": "int16",
                "nodata": -1,
                "sha256": hashlib.sha256(comm_bin.tobytes()).hexdigest(),
            },
        },
        "legend": [],
    }))
    report = outflow_foodweb_from_files(
        mat_state_json_path=str(mat_json),
        outflow_temp_json_path=str(temp_json),
        outflow_discharge_cv=0.2)
    # Mat cells inside the window and with mat_class > 0 count; others skip.
    assert report["occupied_cells"] > 0
    assert report["cell_area_m2"] == pytest.approx(1.0)
    assert report["fly_stock_count"] > 0.0
    assert report["inputs"]["nx"] == nx
