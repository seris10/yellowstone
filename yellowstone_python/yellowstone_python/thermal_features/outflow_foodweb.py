"""Hot-spring outflow food web: ephydrid flies on mats, mite parasitism and predation."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite, nonnegative as _nonnegative

import json
import math
import os

import numpy as np

SCHEMA = "yellowstone.outflow_foodweb.v1"
STATUS = "transferred_structure_authored_rates"


# Brine fly thermal corners are authored from cited ranges (Brock et al. (1969); Collins (1975)).
FLY_SPECIES = {
    "paracoenia_turbida": {
        "t_min_c": 15.0, "t_opt_lo_c": 25.0,
        "t_opt_hi_c": 35.0, "t_max_c": 40.0,
        "corner_status": "authored_from_literature_range",
        "max_density_per_m2": 2000.0,
        "max_density_status": "authored",
        "generation_time_days": 20.0,
        "generation_time_status": "authored_from_general_literature",
        "status": "authored_from_literature_range",
        "sources": [
            'Brock (1967) Life at high temperatures. Science 158:1012 (Paracoenia on Yellowstone thermal mats; grazing to about 40 C) doi:10.1126/science.158.3804.1012',
            'Brock Wiegert and Brock (1969) Feeding by Paracoenia and Ephydra on the microorganisms of hot springs. Ecology 50:192 doi:10.2307/1934846',
            'Collins Mitchell and Wiegert (1976) Functional analysis of a thermal spring ecosystem. Ecology 57:1221 doi:10.2307/1935046',
            'Collins (1977) Mechanisms determining the relative abundance of brine flies (Diptera: Ephydridae) in Yellowstone thermal spring effluents. Canadian Entomologist 109:415 doi:10.4039/ent109415-3',
        ],
    },
    "ephydra_bruesi": {
        "t_min_c": 20.0, "t_opt_lo_c": 28.0,
        "t_opt_hi_c": 35.0, "t_max_c": 40.0,
        "corner_status": "authored_from_literature_range",
        "max_density_per_m2": 1200.0,
        "max_density_status": "authored",
        "generation_time_days": 25.0,
        "generation_time_status": "authored_from_general_literature",
        "status": "authored_from_literature_range",
        "sources": [
            'Brock Wiegert and Brock (1969) Feeding by Paracoenia and Ephydra on the microorganisms of hot springs. Ecology 50:192 doi:10.2307/1934846',
            'Collins (1977) Mechanisms determining the relative abundance of brine flies (Diptera: Ephydridae) in Yellowstone thermal spring effluents. Canadian Entomologist 109:415 doi:10.4039/ent109415-3',
            'Collins Mitchell and Wiegert (1976) Functional analysis of a thermal spring ecosystem. Ecology 57:1221 doi:10.2307/1935046',
        ],
    },
}


# Mite baseline and flow-CV sensitivity are authored; cited studies supply the response direction.
MITE_BASELINE_PARASITISM = 0.18
MITE_BASELINE_STATUS = "authored"
MITE_FLOW_CV_SENSITIVITY = 1.6
MITE_FLOW_CV_SENSITIVITY_STATUS = "authored"
MITE_GENERATION_DAYS = 20.0
MITE_GENERATION_STATUS = "authored"
MITE_SOURCES = [
    "Wiegert and Mitchell 1973 Ecology of Yellowstone thermal "
    "effluent systems: intersects of blue-green algae, grazing flies "
    "(Paracoenia, Ephydridae) and water mites (Partnuniella, "
    "Hydrachnellae). Hydrobiologia 41:3 doi:10.1007/BF00016450",
    "Collins 1977 Mechanisms determining the relative abundance of "
    "brine flies (Diptera: Ephydridae) in Yellowstone thermal spring "
    "effluents. Canadian Entomologist 109:415 "
    "doi:10.4039/ent109415-3",
]


# Predator densities and Holling parameters are authored; trophic-link sources are listed below.
PREDATOR_DIETS = {
    "wetsalts_tiger_beetle": {
        "attack_rate_m2_per_day": 50.0,
        "handling_time_days": 1.0 / 50.0,
        "density_per_m2": 0.08,
        "diet_share_flies": 1.0,
        "status": "authored_illustrative",
        "sources": [
            'Wiegert and Mitchell (1973) Thermophilic ecosystems. In: Simulation Councils Proceedings (Cicindela predation on Paracoenia on hot-spring aprons)',
            'Pearson and Vogler (2001) Tiger Beetles: evolution ecology and diversity (foraging on wet apron substrates)',
        ],
    },
    "dolichopodid_fly": {
        "attack_rate_m2_per_day": 8.0,
        "handling_time_days": 1.0 / 20.0,
        "density_per_m2": 0.5,
        "diet_share_flies": 0.8,
        "status": "authored_illustrative",
        "sources": [
            'Foote (1995) Biology of shore flies. Annual Review of Entomology 40:417 (dolichopodid flies as predators of ephydrids on thermal apron substrates) doi:10.1146/annurev.ento.40.1.417',
        ],
    },
    "riparian_spider_apron": {
        "attack_rate_m2_per_day": 6.0,
        "handling_time_days": 1.0 / 15.0,
        "density_per_m2": 0.3,
        "diet_share_flies": 0.7,
        "status": "authored_illustrative",
        "sources": [
            'Baxter Fausch and Saunders (2005) Freshwater Biology 50:201 (riparian predators of emergent aquatic insects) doi:10.1111/j.1365-2427.2004.01328.x',
        ],
    },
    "spotted_sandpiper": {
        "attack_rate_m2_per_day": 1200.0,
        "handling_time_days": 1.0 / 2000.0,
        "density_per_m2": 0.0015,
        "diet_share_flies": 0.6,
        "status": "authored_illustrative",
        "sources": [
            'Kuenzel and Wiegert (1973) Wilson Bulletin 85:473 (spotted sandpipers feeding on Paracoenia larvae on Yellowstone thermal outflows)',
        ],
    },
    "killdeer": {
        "attack_rate_m2_per_day": 900.0,
        "handling_time_days": 1.0 / 1500.0,
        "density_per_m2": 0.001,
        "diet_share_flies": 0.4,
        "status": "authored_illustrative",
        "sources": [
            'Kuenzel and Wiegert (1973) Wilson Bulletin 85:473 (shorebirds take ephydrid larvae on Yellowstone thermal outflows; killdeer co-occur on the apron)',
        ],
    },
}






def _unit(name: str, value) -> float:
    result = _finite(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return result


def _swallow_entry_from_aerial_insectivores() -> dict:
    """Lift the item-9 swallow Holling pair into the apron Holling frame (per-m2 attack rate).
Keeps one swallow definition shared across modules."""
    from yellowstone_python.insects_birds import AERIAL_INSECTIVORE_DIETS
    swallow = AERIAL_INSECTIVORE_DIETS["swallow"]
    attack = float(swallow["a"]) * 1200.0
    handling = float(swallow["h"]) / 1200.0
    return {
        "attack_rate_m2_per_day": attack,
        "handling_time_days": handling,
        "density_per_m2": 0.004,
        "density_status": "authored_illustrative",
        "diet_share_flies": float(swallow["diet"].get("emergent", 0.5)),
        "status": "linked_to_insects_birds_AERIAL_INSECTIVORE_DIETS",
        "sources": list(swallow["sources"]),
    }


def predators_with_swallow(base: dict | None = None) -> dict:
    """Attach the item-9 swallow as the apron fly predator (source)."""
    merged = dict(base if base is not None else PREDATOR_DIETS)
    merged["swallow"] = _swallow_entry_from_aerial_insectivores()
    return merged


def fly_temperature_occupancy(temperature_c: float,
                              species: str = "paracoenia_turbida") -> float:
    """Trapezoidal temperature-window occupancy in [0, 1].
Zero outside [t_min, t_max]; linear ramps on either side of the optimum band."""
    temperature_c = _finite("temperature_c", temperature_c)
    sp = FLY_SPECIES.get(species)
    if sp is None:
        raise ValueError(f"unknown species {species!r}; "
                         f"have {sorted(FLY_SPECIES)}")
    t_min = float(sp["t_min_c"])
    t_opt_lo = float(sp["t_opt_lo_c"])
    t_opt_hi = float(sp["t_opt_hi_c"])
    t_max = float(sp["t_max_c"])
    if temperature_c <= t_min or temperature_c >= t_max:
        return 0.0
    if t_opt_lo <= temperature_c <= t_opt_hi:
        return 1.0
    if temperature_c < t_opt_lo:
        return (temperature_c - t_min) / (t_opt_lo - t_min)
    return (t_max - temperature_c) / (t_max - t_opt_hi)


def carrying_density_per_m2(temperature_c: float,
                            mat_biomass_g_per_m2: float = 100.0,
                            species: str = "paracoenia_turbida") -> float:
    """Mat-cell carrying density for the species: max_density scaled by occupancy and biomass fraction."""
    sp = FLY_SPECIES[species]
    biomass = _nonnegative("mat_biomass_g_per_m2", mat_biomass_g_per_m2)
    occ = fly_temperature_occupancy(temperature_c, species)
    biomass_fraction = min(1.0, biomass / 200.0)
    return float(sp["max_density_per_m2"]) * occ * biomass_fraction


def recruitment_per_m2_per_day(temperature_c: float,
                               mat_biomass_g_per_m2: float = 100.0,
                               species: str = "paracoenia_turbida",
                               current_density_per_m2: float = 0.0) -> float:
    """Logistic recruitment onto 1 m2 of mat per day."""
    sp = FLY_SPECIES[species]
    carrying = carrying_density_per_m2(temperature_c, mat_biomass_g_per_m2,
                                        species)
    generation = float(sp["generation_time_days"])
    if generation <= 0.0:
        raise ValueError("generation_time_days must be > 0")
    r_max = carrying / generation
    if carrying == 0.0:
        return 0.0
    n = _nonnegative("current_density_per_m2", current_density_per_m2)
    return max(0.0, r_max * (1.0 - n / carrying))


def mite_parasitism_rate_per_day(flow_cv: float,
                                 baseline: float = MITE_BASELINE_PARASITISM,
                                 sensitivity: float = MITE_FLOW_CV_SENSITIVITY,
                                 generation_days: float = MITE_GENERATION_DAYS
                                 ) -> float:
    """Per-day parasitism rate: baseline fraction per generation divided by generation days.
flow_cv damps the baseline; see MITE_SOURCES for the direction (declines with variability)."""
    flow_cv = _nonnegative("flow_cv", flow_cv)
    baseline = _unit("baseline", baseline)
    sensitivity = _nonnegative("sensitivity", sensitivity)
    generation = _nonnegative("generation_days", generation_days)
    if generation == 0.0:
        raise ValueError("generation_days must be > 0")
    frac_per_gen = baseline * math.exp(-sensitivity * flow_cv)
    return frac_per_gen / generation


def mite_parasitism_fraction_per_generation(flow_cv: float,
                                            baseline: float = MITE_BASELINE_PARASITISM,
                                            sensitivity: float = MITE_FLOW_CV_SENSITIVITY
                                            ) -> float:
    """Dimensionless parasitized fraction per fly generation; declines with discharge variability."""
    flow_cv = _nonnegative("flow_cv", flow_cv)
    baseline = _unit("baseline", baseline)
    sensitivity = _nonnegative("sensitivity", sensitivity)
    return baseline * math.exp(-sensitivity * flow_cv)


def predator_offtake_holling_ii(fly_density_per_m2: float,
                                predators: dict | None = None) -> dict:
    """Per-m2 fly offtake per day under a Holling type II response per predator.
Rate_i = density_i * share_i * (a_i * N) / (1 + a_i * h_i * N); N is the fly density."""
    fly_density_per_m2 = _nonnegative("fly_density_per_m2",
                                       fly_density_per_m2)
    preds = predators if predators is not None else PREDATOR_DIETS
    components: list[dict] = []
    total = 0.0
    for cid, entry in preds.items():
        density = _nonnegative(f"{cid}.density_per_m2",
                                entry["density_per_m2"])
        attack = _nonnegative(f"{cid}.attack_rate_m2_per_day",
                               entry["attack_rate_m2_per_day"])
        handling = _nonnegative(f"{cid}.handling_time_days",
                                 entry["handling_time_days"])
        share = _unit(f"{cid}.diet_share_flies",
                       entry["diet_share_flies"])
        if fly_density_per_m2 == 0.0:
            rate_per_m2 = 0.0
        else:
            per_predator = (attack * fly_density_per_m2) / (
                1.0 + attack * handling * fly_density_per_m2)
            rate_per_m2 = density * share * per_predator
        components.append({
            "id": cid,
            "flies_per_m2_per_day": rate_per_m2,
            "density_per_m2": density,
            "attack_rate_m2_per_day": attack,
            "handling_time_days": handling,
            "diet_share_flies": share,
            "max_per_predator_per_day": (1.0 / handling) if handling > 0 else 0.0,
        })
        total += rate_per_m2
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "fly_density_per_m2": fly_density_per_m2,
        "predation_flies_per_m2_per_day": total,
        "components": components,
    }


def outflow_cell_population(temperature_c: float,
                            mat_area_m2: float,
                            flow_cv: float,
                            mat_biomass_g_per_m2: float = 100.0,
                            species: str = "paracoenia_turbida",
                            predators: dict | None = None) -> dict:
    """Steady-state fly population on a mat cell under logistic recruitment, mite parasitism and."""
    temperature_c = _finite("temperature_c", temperature_c)
    mat_area_m2 = _nonnegative("mat_area_m2", mat_area_m2)
    flow_cv = _nonnegative("flow_cv", flow_cv)
    mite_rate = mite_parasitism_rate_per_day(flow_cv)
    preds = predators if predators is not None else PREDATOR_DIETS
    carrying = carrying_density_per_m2(temperature_c, mat_biomass_g_per_m2,
                                        species)
    sp = FLY_SPECIES[species]
    generation = float(sp["generation_time_days"])
    r_max = carrying / generation if carrying > 0.0 else 0.0

    def _balance(n: float) -> float:
        rec = (r_max * (1.0 - n / carrying)) if carrying > 0.0 else 0.0
        pred = predator_offtake_holling_ii(
            n, preds)["predation_flies_per_m2_per_day"]
        return rec - mite_rate * n - pred

    if carrying <= 0.0:
        density = 0.0
    else:
        lo, hi = 0.0, carrying
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if _balance(mid) <= 0.0:
                hi = mid
            else:
                lo = mid
            if hi - lo < 1e-9:
                break
        density = 0.5 * (lo + hi)
    stock = density * mat_area_m2
    recruitment_rate = (r_max * (1.0 - density / carrying)
                        if carrying > 0.0 else 0.0)
    pred_ledger = predator_offtake_holling_ii(density, preds)
    predation_total = pred_ledger["predation_flies_per_m2_per_day"] * mat_area_m2
    parasitism_total = mite_rate * stock
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "species": species,
        "temperature_c": temperature_c,
        "temperature_occupancy": fly_temperature_occupancy(
            temperature_c, species),
        "mat_area_m2": mat_area_m2,
        "mat_biomass_g_per_m2": _nonnegative(
            "mat_biomass_g_per_m2", mat_biomass_g_per_m2),
        "flow_cv": flow_cv,
        "carrying_density_per_m2": carrying,
        "recruitment_r_max_per_m2_per_day": r_max,
        "recruitment_per_m2_per_day": recruitment_rate,
        "recruitment_total_per_day": recruitment_rate * mat_area_m2,
        "fly_density_per_m2": density,
        "fly_stock_count": stock,
        "mite_parasitism_rate_per_day": mite_rate,
        "mite_parasitism_total_per_day": parasitism_total,
        "predator_ledger": pred_ledger,
        "predation_total_per_day": predation_total,
        "flux_balance_residual_per_day":
            recruitment_rate * mat_area_m2
            - parasitism_total
            - predation_total,
        "fly_sources": FLY_SPECIES[species]["sources"],
        "mite_sources": list(MITE_SOURCES),
    }


def _resolve_adjacent_path(json_path: str, raster_name: str) -> str:
    """Resolve a raster path recorded next to its JSON sidecar."""
    base = os.path.dirname(os.path.abspath(json_path))
    return os.path.join(base, os.path.basename(raster_name))


def _load_f32_raster(path: str, nx: int, nz: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<f4")
    if arr.size != nx * nz:
        raise ValueError(
            f"raster {path} size {arr.size} does not match grid {nx}x{nz}")
    return arr.reshape((nz, nx))


def _load_i16_raster(path: str, nx: int, nz: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<i2")
    if arr.size != nx * nz:
        raise ValueError(
            f"raster {path} size {arr.size} does not match grid {nx}x{nz}")
    return arr.reshape((nz, nx))


def outflow_foodweb_from_files(mat_state_json_path: str,
                               outflow_temp_json_path: str,
                               outflow_discharge_cv: float,
                               mat_biomass_g_per_m2: float = 100.0,
                               species: str = "paracoenia_turbida",
                               predators: dict | None = None) -> dict:
    """Reduce real model artifacts to per-cell fly populations."""
    with open(outflow_temp_json_path, "r", encoding="utf-8") as fh:
        temp_sidecar = json.load(fh)
    if not isinstance(temp_sidecar, dict):
        raise ValueError("outflow_temperature sidecar must be a mapping")
    if not str(temp_sidecar.get("schema", "")).startswith(
            "yellowstone.outflow_temperature"):
        raise ValueError("outflow_temperature sidecar has wrong schema")
    grid = temp_sidecar.get("grid", {})
    nx = int(grid.get("nx"))
    nz = int(grid.get("nz"))
    cell_m = float(grid.get("cell_size_m", grid.get("cell_m", 1.0)))
    temp_path = _resolve_adjacent_path(
        outflow_temp_json_path,
        temp_sidecar.get("raster_path", "outflow_temperature.f32"))
    temp_raster = _load_f32_raster(temp_path, nx, nz)

    with open(mat_state_json_path, "r", encoding="utf-8") as fh:
        mat_sidecar = json.load(fh)
    if not isinstance(mat_sidecar, dict):
        raise ValueError("mat_state sidecar must be a mapping")
    if not str(mat_sidecar.get("schema", "")).startswith(
            "yellowstone.mat_state"):
        raise ValueError("mat_state sidecar has wrong schema")
    rasters = mat_sidecar.get("rasters", {})
    community = rasters.get("community")
    if not isinstance(community, dict):
        raise ValueError("mat_state rasters.community missing")
    community_path = _resolve_adjacent_path(
        mat_state_json_path, community.get("path", "mat_community.i16"))
    community_raster = _load_i16_raster(community_path, nx, nz)

    cell_area_m2 = cell_m * cell_m
    total_stock = 0.0
    total_mat_m2 = 0.0
    total_recruit = 0.0
    total_predation = 0.0
    total_parasitism = 0.0
    occupied = 0
    for j in range(nz):
        for i in range(nx):
            cls = int(community_raster[j, i])
            if cls <= 0:
                continue
            t = float(temp_raster[j, i])
            if not math.isfinite(t):
                continue
            cell = outflow_cell_population(
                temperature_c=t, mat_area_m2=cell_area_m2,
                flow_cv=outflow_discharge_cv,
                mat_biomass_g_per_m2=mat_biomass_g_per_m2,
                species=species, predators=predators)
            total_stock += cell["fly_stock_count"]
            total_mat_m2 += cell["mat_area_m2"]
            total_recruit += cell["recruitment_total_per_day"]
            total_predation += cell["predation_total_per_day"]
            total_parasitism += cell["mite_parasitism_total_per_day"]
            occupied += 1
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "species": species,
        "cell_area_m2": cell_area_m2,
        "occupied_cells": occupied,
        "total_mat_m2": total_mat_m2,
        "fly_stock_count": total_stock,
        "recruitment_total_per_day": total_recruit,
        "predation_total_per_day": total_predation,
        "mite_parasitism_total_per_day": total_parasitism,
        "flow_cv": _nonnegative("outflow_discharge_cv",
                                 outflow_discharge_cv),
        "inputs": {
            "mat_state_json": os.path.abspath(mat_state_json_path),
            "outflow_temperature_json": os.path.abspath(
                outflow_temp_json_path),
            "nx": nx, "nz": nz, "cell_size_m": cell_m,
        },
    }


__all__ = [
    "FLY_SPECIES",
    "MITE_BASELINE_PARASITISM",
    "MITE_BASELINE_STATUS",
    "MITE_FLOW_CV_SENSITIVITY",
    "MITE_FLOW_CV_SENSITIVITY_STATUS",
    "MITE_GENERATION_DAYS",
    "MITE_GENERATION_STATUS",
    "MITE_SOURCES",
    "PREDATOR_DIETS",
    "SCHEMA",
    "STATUS",
    "fly_temperature_occupancy",
    "mite_parasitism_fraction_per_generation",
    "mite_parasitism_rate_per_day",
    "outflow_cell_population",
    "outflow_foodweb_from_files",
    "predator_offtake_holling_ii",
    "predators_with_swallow",
    "recruitment_per_m2_per_day",
]
