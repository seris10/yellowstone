"""Multi-day insect + trout + dipper dynamics on a thermal landscape."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from yellowstone_python.common.checks import finite, positive, fraction, nonnegative
from yellowstone_python.registry.coupling import POCKET_CONSERVATION
from yellowstone_python.aquatic.fish import REFUGE_WEIGHT, predation_survival_factor, suitability_with_stressors, thermal_performance
from yellowstone_python.insects_birds import DEFAULT_DIETS, INSECT_GROUPS, develop_benthic, emergence_total_from_taxa, holling_type_ii, trout_diet_at_temp

SCHEMA = "yellowstone.aquatic_foodweb.v1"
COVER_DEFAULT = 0.6  # authored trout cover (same default as update_trout)


# River taxa carry cited thermal, DO, and feeding traits; emerges=False marks nonemerging grazers.
INVERT_TAXA = {
    "mayflies": {
        "feeding_group": "grazer_scraper",
        "tbase_c": 2.0,
        "rate_per_dd": 0.012,
        "t_cutoff_c": 22.0,
        "thermal_status": "authored_from_literature_review",
        "do_sensitive_min_mg_l": 5.0,
        "do_lethal_min_mg_l": 3.0,
        "do_status": "authored_from_literature_review",
        "periphyton_consumption_rate_per_day": 0.08,
        "periphyton_consumption_status": "authored_illustrative",
        "emerges": True,
        "sources": [
            'Hynes (1970) The Ecology of Running Waters, University of Toronto Press (Ephemeroptera as scrapers and collectors on periphyton biofilms; book-level secondary reference, no DOI)',
            'Davis (1975) Minimal dissolved oxygen requirements of aquatic life, Journal of the Fisheries Research Board of Canada 32:2295-2312; authored_within_cited_range DO ramp anchors; Gaufin, Clubb and Newell (1974)',
        ],
    },
    "caddisflies": {
        "feeding_group": "grazer_scraper_mixed",
        "tbase_c": 2.0,
        "rate_per_dd": 0.011,
        "t_cutoff_c": 24.0,
        "thermal_status": "authored_from_literature_review",
        "do_sensitive_min_mg_l": 4.5,
        "do_lethal_min_mg_l": 2.5,
        "do_status": "authored_from_literature_review",
        "periphyton_consumption_rate_per_day": 0.06,
        "periphyton_consumption_status": "authored_illustrative",
        "emerges": True,
        "sources": [
            'Hynes (1970) The Ecology of Running Waters, University of Toronto Press (Trichoptera functional feeding groups; book-level secondary reference, no DOI)',
            'Davis (1975) Minimal dissolved oxygen requirements of aquatic life, Journal of the Fisheries Research Board of Canada 32:2295-2312; authored_within_cited_range DO ramp anchors',
        ],
    },
    "stoneflies": {
        "feeding_group": "shredder_predator",
        "tbase_c": 2.0,
        "rate_per_dd": 0.010,
        "t_cutoff_c": 20.0,
        "thermal_status": "authored_from_literature_review",
        "do_sensitive_min_mg_l": 6.0,
        "do_lethal_min_mg_l": 4.0,
        "do_status": "authored_from_literature_review",
        "periphyton_consumption_rate_per_day": 0.015,
        "periphyton_consumption_status": "authored_illustrative",
        "emerges": True,
        "sources": [
            'Hynes (1970) The Ecology of Running Waters, University of Toronto Press (Plecoptera shredder and predator feeding groups; book-level secondary reference, no DOI)',
            'Davis (1975) Minimal dissolved oxygen requirements of aquatic life, Journal of the Fisheries Research Board of Canada 32:2295-2312; authored DO ramp anchors ordered by sensitivity: stoneflies > mayflies > caddisflies > chironomids',
        ],
    },
    "midges": {
        "feeding_group": "collector_gatherer",
        "tbase_c": 8.0,
        "rate_per_dd": 0.030,
        "t_cutoff_c": 30.0,
        "thermal_status": "transferred_from_literature_with_ranges",
        "do_sensitive_min_mg_l": 3.0,
        "do_lethal_min_mg_l": 1.0,
        "do_status": "authored_from_literature_review",
        "periphyton_consumption_rate_per_day": 0.04,
        "periphyton_consumption_status": "authored_illustrative",
        "emerges": True,
        "sources": [
            'Mackey (1977) Growth and development of larval Chironomidae ; secondary literature summary of development at 10, 15 and 20 C; rates authored within cited range',
            'Davis (1975) Minimal dissolved oxygen requirements of aquatic life, Journal of the Fisheries Research Board of Canada 32:2295-2312 (existence verified; Chironomidae low-DO tolerance ramp anchors authored)',
        ],
    },
    "nz_mudsnail": {
        "feeding_group": "invasive_grazer",
        "tbase_c": 0.0,
        "rate_per_dd": 0.0,
        "t_cutoff_c": 28.0,
        "thermal_status": "authored_from_literature_review",
        "do_sensitive_min_mg_l": 2.0,
        "do_lethal_min_mg_l": 0.5,
        "do_status": "authored_from_literature_review",
        "periphyton_consumption_rate_per_day": 0.10,
        "periphyton_consumption_status": "authored_illustrative",
        "emerges": False,
        "sources": [
            'Dybdahl and Kane (2005), Potamopyrgus antipodarum, Ecology 86:1592-1601; authored_within_cited_range upper thermal threshold 28 C; literature phenotypic plasticity across temperatures',
            'Hall Tank and Dybdahl (2003) Exotic snails dominate nitrogen and carbon cycling in a highly productive stream, Frontiers in Ecology and the Environment 1(8):407-411 (consumption of about three-quarters of gross primary productivity and two-thirds of ammonium demand attributed to high mudsnail biomass; literature)',
            'species_catalogue.json id new_zealand_mudsnail (Firehole invaded-corridor evidence; literature)',
        ],
    },
}

# Mudsnail competition weight on native grazers; authored illustrative.
NZ_MUDSNAIL_COMPETITION_WEIGHT = 1.0
NZ_MUDSNAIL_COMPETITION_SOURCE = (
    'authored_illustrative_competition_strength; Hall Tank Dybdahl (2003) report that P. antipodarum can dominate periphyton grazing without quantifying a per-capita competition coefficient for mayflies and caddisflies specifically'
)


def _taxon_do_survival(taxon: dict, do_mg_l: float | None) -> float:
    """Taxon DO survival factor in [0, 1] from a linear ramp between do_lethal and do_sensitive"""
    if do_mg_l is None:
        return 1.0
    try:
        do = float(do_mg_l)
    except (TypeError, ValueError) as exc:
        raise ValueError("do_mg_l must be numeric") from exc
    if not math.isfinite(do) or do < 0.0:
        raise ValueError("do_mg_l must be finite and >= 0")
    lethal = float(taxon["do_lethal_min_mg_l"])
    sensitive = float(taxon["do_sensitive_min_mg_l"])
    if sensitive <= lethal:
        raise ValueError("do_sensitive_min_mg_l must exceed do_lethal_min_mg_l")
    if do <= lethal:
        return 0.0
    if do >= sensitive:
        return 1.0
    return (do - lethal) / (sensitive - lethal)


def taxon_step(state_by_taxon: dict[str, float],
               water_c: float,
               periphyton_biomass_mg_c_m2: float,
               dt_s: float,
               taxa: dict[str, dict] | None = None,
               do_mg_l: float | None = None,
               mudsnail_competition_weight: float = NZ_MUDSNAIL_COMPETITION_WEIGHT
               ) -> dict[str, Any]:
    """Advance per-taxon larval biomass by dt_s with periphyton as food base."""
    taxa = taxa or INVERT_TAXA
    water = float(water_c)
    if not math.isfinite(water):
        raise ValueError("water_c must be finite")
    dt = float(dt_s)
    if not math.isfinite(dt) or dt < 0.0:
        raise ValueError("dt_s must be finite and >= 0")
    periphyton = float(periphyton_biomass_mg_c_m2)
    if not math.isfinite(periphyton) or periphyton < 0.0:
        raise ValueError("periphyton_biomass_mg_c_m2 must be finite and >= 0")
    weight = float(mudsnail_competition_weight)
    if not math.isfinite(weight) or weight < 0.0:
        raise ValueError("mudsnail_competition_weight must be finite and >= 0")
    out: dict[str, Any] = {}
    emergence_by_taxon: dict[str, float] = {}
    hours = dt / 3600.0
    mudsnail_density = float(state_by_taxon.get("nz_mudsnail", 0.0))
    for taxon_id, taxon in taxa.items():
        before = float(state_by_taxon.get(taxon_id, 0.0))
        if before < 0.0:
            if before > -1e-12:
                before = 0.0
            else:
                raise ValueError(f"{taxon_id}: biomass must be >= 0")
        emerges = bool(taxon.get("emerges", True))
        if emerges:
            nb_new, emergence, _ = develop_benthic(
                before, water, dt,
                tbase=taxon["tbase_c"],
                rate=taxon["rate_per_dd"],
                t_cutoff=taxon["t_cutoff_c"])
        else:
            # Nonemerging mudsnails grow logistically on periphyton, independently of developmental emergence.
            if water < taxon["t_cutoff_c"]:
                growth_per_day = (
                    taxon["periphyton_consumption_rate_per_day"]
                    * (periphyton / (periphyton + 100.0)
                       if periphyton > 0.0 else 0.0))
                nb_new = min(1.0, before + growth_per_day * hours / 24.0)
            else:
                # Above cutoff: mortality drives biomass toward zero.
                nb_new = max(0.0, before - 0.05 * hours / 24.0)
            emergence = 0.0
        do_surv = _taxon_do_survival(taxon, do_mg_l)
        nb_new = max(0.0, nb_new * do_surv)
        emergence = max(0.0, emergence * do_surv)
        # Taxon grazing consumes periphyton; mudsnails increase native scrapers' effective competition.
        base_rate = float(taxon["periphyton_consumption_rate_per_day"])
        if taxon.get("feeding_group") in (
                "grazer_scraper", "grazer_scraper_mixed"):
            effective = base_rate * (1.0 + weight * mudsnail_density)
        else:
            effective = base_rate
        grazing_mg_c_m2_s = (
            effective / 86400.0 * before * periphyton)
        if emerges:
            emergence_by_taxon[taxon_id] = emergence
        out[taxon_id] = {
            "nb": nb_new,
            "emergence": emergence,
            "do_survival": do_surv,
            "grazing_mg_c_m2_s": grazing_mg_c_m2_s,
            "feeding_group": taxon["feeding_group"],
            "emerges": emerges,
        }
    emergent_input = emergence_total_from_taxa(emergence_by_taxon)
    return {
        "taxa": out,
        "emergence_by_taxon": emergence_by_taxon,
        "emergent_compartment_input": emergent_input,
    }


def run_taxon_foodweb(
        landscape: list[dict[str, Any]],
        periphyton_biomass_mg_c_m2_by_cell: dict[str, float] | None = None,
        do_mg_l_by_cell: dict[str, float] | None = None,
        days: float = 14.0,
        dt_days: float = 1.0,
        taxa: dict[str, dict] | None = None,
        initial_biomass_by_taxon: dict[str, float] | None = None,
        periphyton_shortfall_decay_per_day: float = 0.2,
        mudsnail_competition_weight: float = NZ_MUDSNAIL_COMPETITION_WEIGHT
        ) -> dict[str, Any]:
    """Taxon-level benthic foodweb per cell with periphyton as food base."""
    if not isinstance(landscape, list) or not landscape:
        raise ValueError("landscape must be a nonempty list")
    taxa = taxa or INVERT_TAXA
    initial = dict(initial_biomass_by_taxon or {t: 0.5 for t in taxa})
    peri_map = dict(periphyton_biomass_mg_c_m2_by_cell or {})
    do_map = dict(do_mg_l_by_cell or {})
    decay = float(periphyton_shortfall_decay_per_day)
    if not math.isfinite(decay) or decay < 0.0:
        raise ValueError("periphyton_shortfall_decay_per_day must be finite "
                         "and >= 0")
    span = float(days)
    step = float(dt_days)
    if not math.isfinite(span) or span <= 0.0:
        raise ValueError("days must be finite and > 0")
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("dt_days must be finite and > 0")
    states: dict[str, dict[str, float]] = {
        cell["id"]: {taxon_id: float(initial.get(taxon_id, 0.5))
                     for taxon_id in taxa}
        for cell in landscape
    }
    cumulative_emergence: dict[str, float] = {
        taxon_id: 0.0 for taxon_id in taxa
        if taxa[taxon_id].get("emerges", True)
    }
    cumulative_emergent_input = 0.0
    remaining = span
    steps = 0
    while remaining > 1e-12:
        this_step = min(step, remaining)
        dt_s_step = this_step * 86400.0
        for cell in landscape:
            cell_id = cell["id"]
            water_c = float(cell["temperature_c"])
            peri_biomass = float(peri_map.get(cell_id, 0.0))
            do_mg_l = do_map.get(cell_id)
            # Missing or zero periphyton causes grazer starvation; loss is separate from degree-day emergence.
            if peri_biomass <= 0.0:
                for taxon_id, taxon in taxa.items():
                    group = taxon.get("feeding_group", "")
                    if "grazer" in group or "collector" in group:
                        states[cell_id][taxon_id] *= math.exp(
                            -decay * this_step)
            report = taxon_step(
                states[cell_id], water_c, max(peri_biomass, 0.0),
                dt_s_step, taxa=taxa, do_mg_l=do_mg_l,
                mudsnail_competition_weight=mudsnail_competition_weight)
            for taxon_id, taxon_report in report["taxa"].items():
                states[cell_id][taxon_id] = float(taxon_report["nb"])
            for taxon_id, amount in report["emergence_by_taxon"].items():
                cumulative_emergence[taxon_id] = (
                    cumulative_emergence.get(taxon_id, 0.0) + float(amount))
            cumulative_emergent_input += float(
                report["emergent_compartment_input"])
        remaining -= this_step
        steps += 1
    emergent_input_from_sum = emergence_total_from_taxa(cumulative_emergence)
    return {
        "schema": "yellowstone.taxon_foodweb.v1",
        "status": "illustrative_not_calibrated",
        "days": span,
        "steps": steps,
        "cell_states": {
            cell_id: {taxon_id: round(value, 6)
                      for taxon_id, value in state.items()}
            for cell_id, state in states.items()
        },
        "cumulative_emergence_by_taxon": {
            taxon_id: round(amount, 6)
            for taxon_id, amount in cumulative_emergence.items()
        },
        "cumulative_emergent_compartment_input":
            round(cumulative_emergent_input, 6),
        "emergent_input_sum_check": round(emergent_input_from_sum, 6),
        "taxa": sorted(taxa.keys()),
        "provenance": {
            "periphyton_source":
                'yellowstone_python.aquatic.periphyton.step_biomass output or periphyton sidecar',
            "do_source": 'yellowstone_python.aquatic.river_oxygen.advect_cells output or river_oxygen sidecar',
            "do_response_source":
                'linear ramp from do_lethal_min_mg_l (survival 0) to do_sensitive_min_mg_l (survival 1); per-taxon anchors from Davis (1975) and Dybdahl and Kane (2005)',
            "mudsnail_competition_source": NZ_MUDSNAIL_COMPETITION_SOURCE,
        },
    }


TRIBUTARY_CANDIDATES = (
    {
        "key": "rabbit_creek",
        "cell_id": "trib_rabbit_creek",
        "name": "Rabbit Creek mouth pocket",
        "confluence_s_m": 1260.0,
        "confluence_provenance": ("map_measured_world.json_river_5877_0_"
                                  "downstream_end_within_10m_of_replay_"
                                  "cell_00064_solver_chainage"),
        "temperature_c": 11.0,
        "temperature_provenance": ("authored_scenario_from_DEFAULT_"
                                   "TRIBUTARIES_rabbit_creek_11C_zero_"
                                   "flow_baseline_no_observation"),
    },
    {
        "key": "mallard_creek",
        "cell_id": "trib_mallard_creek",
        "name": "Mallard Creek mouth pocket",
        "confluence_s_m": 35.0,
        "confluence_provenance": ("map_measured_world.json_river_5938_0_"
                                  "downstream_end_within_7m_of_replay_"
                                  "cell_00002_solver_chainage"),
        "temperature_c": 11.0,
        "temperature_provenance": ("authored_scenario_from_DEFAULT_"
                                   "TRIBUTARIES_mallard_creek_11C_zero_"
                                   "flow_baseline_no_observation"),
    },
)
# Habitat-area food scaling: pocket food is a fraction of a mainstem cell. Authored ratio 22/440 m2.
TRIBUTARY_FOOD_SCALE_DEFAULT = 0.05
TRIBUTARY_FOOD_SCALE_PROVENANCE = (
    "authored_area_ratio_22m2_pocket_over_440m2_mainstem_cell")
# Slow pocket hydraulics; authored estimates.
TRIBUTARY_VELOCITY_M_S = 0.25
TRIBUTARY_DEPTH_M = 0.5
TRIBUTARY_WIDTH_M = 6.0


def unwrap_replay(document: dict[str, Any]) -> dict[str, Any]:
    """Accept a bare replay, a river_replay.json sidecar, or {data:{...}}."""
    if "cells" in document and "frames" in document:
        return document
    for key in ("replay", "data"):
        inner = document.get(key)
        if isinstance(inner, dict):
            try:
                return unwrap_replay(inner)
            except ValueError:
                continue
    raise ValueError("not a recognized replay document (no cells+frames)")


def thermal_landscape(replay_doc: dict[str, Any],
                      t_min_s: float | None = None,
                      t_max_s: float | None = None) -> list[dict[str, Any]]:
    """Per-cell quasi-steady thermal and hydraulic habitat from replay frames."""
    rep = unwrap_replay(replay_doc)
    cells, frames = rep["cells"], rep["frames"]
    if not cells or not frames:
        raise ValueError("replay needs cells and frames")
    if t_min_s is not None and t_max_s is not None and t_min_s > t_max_s:
        raise ValueError("t_min_s must be <= t_max_s")
    for fi, frame in enumerate(frames):
        if "t_s" not in frame or "temperature_c" not in frame:
            raise ValueError(f"frame {fi} missing 't_s'/'temperature_c'")
        temps = frame["temperature_c"]
        if not isinstance(temps, list) or len(temps) != len(cells):
            raise ValueError(
                f"frame {fi}: expected {len(cells)} temperatures, got {len(temps) if isinstance(temps, list) else type(temps)}")
        if not all(math.isfinite(float(v)) for v in temps):
            raise ValueError(f"frame {fi}: non-finite temperature")
    window = [f for f in frames
              if (t_min_s is None or f["t_s"] >= t_min_s)
              and (t_max_s is None or f["t_s"] <= t_max_s)]
    if not window:
        raise ValueError("time window selects no frames")
    landscape = []
    for i, cell in enumerate(cells):
        temps = [float(frame["temperature_c"][i]) for frame in window]
        mean_t = sum(temps) / len(temps)
        hydro = cell.get("hydraulics") or {}
        velocity = hydro.get("velocity_continuity_m_s",
                             cell.get("representative_velocity_m_s", 0.0))
        landscape.append({
            "id": cell["id"],
            "river_id": cell.get("river_id", "?"),
            "s_m": float(cell.get("center_s_m",
                                 (cell.get("start_s_m", 0.0)
                                  + cell.get("end_s_m", 0.0)) / 2.0)),
            "temperature_c": mean_t,
            "temp_min_c": min(temps),
            "temp_max_c": max(temps),
            "velocity_m_s": float(velocity or 0.0),
            "depth_m": float(cell.get("depth_m", 0.5)),
            "width_m": float(cell.get("width_m", 20.0)),
            # Mapped bed shear in Pa; None where Manning is undefined. run_foodweb maps None to zero disturbance.
            "shear_pa": hydro.get("bed_shear_pa"),
        })
    return landscape


def build_tributary_cell(spec: dict[str, Any],
                         temperature_c: float | None = None,
                         food_scale: float = TRIBUTARY_FOOD_SCALE_DEFAULT,
                         ) -> dict[str, Any]:
    """Build one tributary mouth-pocket landscape cell from a spec."""
    if food_scale is None or not math.isfinite(float(food_scale)):
        raise ValueError("food_scale must be a finite number")
    food_scale = float(food_scale)
    if food_scale < 0.0:
        raise ValueError("food_scale must be >= 0")
    temp = float(temperature_c) if temperature_c is not None \
        else float(spec["temperature_c"])
    if not math.isfinite(temp):
        raise ValueError("tributary temperature must be finite")
    s = float(spec["confluence_s_m"])
    if not math.isfinite(s):
        raise ValueError("tributary confluence_s_m must be finite")
    return {
        "id": spec["cell_id"],
        "river_id": "tributary",
        "s_m": s,
        "temperature_c": temp,
        "temp_min_c": temp,
        "temp_max_c": temp,
        "velocity_m_s": TRIBUTARY_VELOCITY_M_S,
        "depth_m": TRIBUTARY_DEPTH_M,
        "width_m": TRIBUTARY_WIDTH_M,
        # Pocket holding water per coupling.pocket_holding; excluded from solver heat and water budgets.
        "conservation": POCKET_CONSERVATION,
        # Manning-undefined pocket: shear None maps to zero disturbance in run_foodweb.
        "shear_pa": None,
        # Habitat-area food scaling: pocket production is a small fraction of a mainstem cell.
        "food_scale": food_scale,
        "tributary_provenance": {
            "confluence_s_m": s,
            "confluence_provenance":
                spec["confluence_provenance"],
            "temperature_c": temp,
            "temperature_provenance":
                spec["temperature_provenance"] if temperature_c is None
                else "authored_sensitivity_sweep_override",
            "food_scale": food_scale,
            "food_scale_provenance":
                TRIBUTARY_FOOD_SCALE_PROVENANCE if food_scale
                == TRIBUTARY_FOOD_SCALE_DEFAULT
                else "authored_sensitivity_sweep_override",
            "velocity_m_s": TRIBUTARY_VELOCITY_M_S,
            "depth_m": TRIBUTARY_DEPTH_M,
            "hydraulics_provenance":
                "authored_slow_pocket_estimate_not_measured",
        },
    }


def append_tributary_cells(
        landscape: list[dict[str, Any]],
        specs: list[dict[str, Any]] | tuple | None = None,
        temperature_c: float | None = None,
        food_scale: float = TRIBUTARY_FOOD_SCALE_DEFAULT) -> list[dict[str, Any]]:
    """Append cold tributary mouth-pocket cells to a thermal landscape."""
    if specs is None:
        specs = list(TRIBUTARY_CANDIDATES)
    out = list(landscape)
    for spec in specs:
        out.append(build_tributary_cell(spec, temperature_c=temperature_c,
                                        food_scale=food_scale))
    return out


def shear_to_disturbance(shear_pa: float | None,
                         threshold_pa: float | None) -> float:
    """Map bed shear in Pa to a benthic disturbance fraction in [0, 1]."""
    if shear_pa is None or threshold_pa is None:
        return 0.0
    shear, thr = float(shear_pa), float(threshold_pa)
    if not (math.isfinite(shear) and math.isfinite(thr)):
        raise ValueError("shear and threshold must be finite")
    if shear < 0.0 or thr <= 0.0:
        raise ValueError("shear must be >= 0 and threshold must be > 0")
    if shear <= thr:
        return 0.0
    return min(1.0, (shear - thr) / thr)


def _per_cell_stressor_factors(
        cell: dict[str, Any],
        solute_concentrations: dict[str, dict[str, float]] | None,
        do_mg_l_by_cell: dict[str, float] | None,
        predation_rate_by_cell: dict[str, float] | None,
        predation_window_days: float
        ) -> dict[str, float | None]:
    """Resolve the solute, DO and predation stressor factors for one landscape cell."""
    cell_id = cell.get("id")
    solute_factor = None
    if solute_concentrations is not None:
        entry = solute_concentrations.get(cell_id)
        if entry is not None:
            from yellowstone_python.river.solute_transport import solute_habitat_multiplier
            solute_factor = float(solute_habitat_multiplier(
                float(entry["chloride_mg_l"]),
                float(entry["arsenic_ug_l"]),
                float(entry["boron_mg_l"]))["combined"])
    do_factor = None
    if do_mg_l_by_cell is not None:
        do_value = do_mg_l_by_cell.get(cell_id)
        if do_value is not None:
            from yellowstone_python.aquatic.river_oxygen import fish_suitability
            do_factor = float(fish_suitability(float(do_value)))
    predation_factor = None
    if predation_rate_by_cell is not None:
        rate = predation_rate_by_cell.get(cell_id)
        if rate is not None:
            predation_factor = float(predation_survival_factor(
                float(rate), days=float(predation_window_days)))
    return {"solute_factor": solute_factor,
            "do_factor": do_factor,
            "predation_factor": predation_factor}


def foodweb_state(landscape: list[dict]) -> dict:
    """Initialize foodweb stocks and cumulative fluxes for an online run."""
    if not landscape:
        raise ValueError("landscape must be nonempty")
    return {"stocks": [{"ept": 0.5, "dipt": 0.5, "ne": 0.2} for _ in landscape],
            "cell_ids": [cell["id"] for cell in landscape],
            "totals": {"emergence": 0.0, "regrowth": 0.0, "trout_eaten": 0.0,
                       "dipper_eaten": 0.0, "ne_turnover": 0.0},
            "refuge_history": [], "simulated_days": 0.0, "steps": 0,
            "chosen_cell_id": None, "stressor_factors_last_step": []}


def step_foodweb(state_value: dict, landscape: list[dict], step_days: float,
                 settings: dict | None = None) -> dict:
    """Advance foodweb stocks, intake and refuge choice by a physical day interval."""
    settings = settings or {}
    step_days = positive("step_days", step_days)
    trout_species = settings.get("trout_species", "brown_trout")
    cover = fraction("cover", settings.get("cover", COVER_DEFAULT))
    ne_turnover_days = positive("ne_turnover_days", settings.get("ne_turnover_days", 2.0))
    shear_disturb_pa = settings.get("shear_disturb_pa", 20.0)
    food_mode = settings.get("food_mode", "relative")
    if food_mode not in ("relative", "absolute"):
        raise ValueError("food_mode must be relative or absolute")
    food_absolute_scale = positive("food_absolute_scale", settings.get("food_absolute_scale", 1.0))
    solute_concentrations = settings.get("solute_concentrations")
    do_mg_l_by_cell = settings.get("do_mg_l_by_cell")
    predation_rate_by_cell = settings.get("predation_rate_by_cell")
    predation_window_days = settings.get("predation_window_days", 1.0)
    delta_u_switch = nonnegative("delta_u_switch", settings.get("delta_u_switch", 0.0))
    movement_cost_per_m = nonnegative("movement_cost_per_m", settings.get("movement_cost_per_m", 0.0))
    thermal_curve_form = settings.get("thermal_curve_form", "piecewise_linear")
    if state_value["cell_ids"] != [cell["id"] for cell in landscape]:
        raise ValueError("foodweb state cell order does not match landscape")
    state = state_value["stocks"]
    totals = state_value["totals"]
    refuge_history = state_value["refuge_history"]
    dipper = DEFAULT_DIETS["dipper"]
    disturbances = [shear_to_disturbance(cell.get("shear_pa"), shear_disturb_pa)
                    for cell in landscape]
    food_scales = [nonnegative("food_scale", cell.get("food_scale", 1.0)) for cell in landscape]
    dt_s_step = step_days * 86400.0
    eat_substeps = max(1, int(math.ceil(step_days * 24.0)))
    eat_dt_h = step_days * 24.0 / eat_substeps

    foods: list[float] = []
    for cell, stock, disturb, scale in zip(landscape, state,
                                           disturbances, food_scales):
        t = cell["temperature_c"]
        edible = 0.0
        for group, key in (("ept", "ept"), ("dipteran", "dipt")):
            params = INSECT_GROUPS[group]
            before = stock[key]
            after, emergence, disturb_loss = develop_benthic(
                before, t, dt_s_step, tbase=params["tbase_c"],
                rate=params["rate_per_dd"],
                disturbance=disturb,
                t_cutoff=params["t_cutoff_c"])
            regrow = after - (before - emergence - disturb_loss)
            totals["emergence"] += emergence
            totals["regrowth"] += regrow
            stock[key] = after
            stock["ne"] += emergence
            edible += emergence + 0.5 * after
        foods.append(edible * scale)
    if food_mode == "relative":
        ceiling = max(foods) or 1.0
        food_terms = [f / ceiling for f in foods]
    else:
        food_terms = [min(1.0, max(0.0, f / float(food_absolute_scale)))
                      for f in foods]

    scored: list[tuple[float, int, dict[str, Any], Any, dict]] = []
    per_cell_stressors: list[dict[str, Any]] = []
    for idx, cell in enumerate(landscape):
        food = food_terms[idx]
        perf = thermal_performance(cell["temperature_c"], trout_species, thermal_curve_form)
        factors = _per_cell_stressor_factors(
            cell, solute_concentrations, do_mg_l_by_cell,
            predation_rate_by_cell, predation_window_days)
        report = suitability_with_stressors(
            food=food, cover=cover, t_c=cell["temperature_c"],
            velocity=cell["velocity_m_s"], depth=cell["depth_m"],
            species=trout_species, refuge_weight=REFUGE_WEIGHT,
            solute_multiplier=factors["solute_factor"],
            do_multiplier=factors["do_factor"],
            predation_multiplier=factors["predation_factor"],
                thermal_curve_form=thermal_curve_form)
        u = report["U"]
        scored.append((u, idx, cell, perf, report))
        per_cell_stressors.append({
            "cell_id": cell["id"],
            "thermal_only_U": report["thermal_only"],
            "solute_factor": report["solute_factor"],
            "do_factor": report["do_factor"],
            "predation_factor": report["predation_factor"],
            "combined_stressor_factor":
                report["combined_stressor_factor"],
            "U": u,
        })
    scored.sort(key=lambda row: row[0], reverse=True)
    best_u, idx, best_cell, best_perf, best_report = scored[0]
    previous_id = state_value.get("chosen_cell_id")
    if previous_id is not None and (delta_u_switch > 0.0 or movement_cost_per_m > 0.0):
        previous = next((row for row in scored if row[2]["id"] == previous_id), None)
        if previous is not None:
            distance = abs(best_cell["s_m"] - previous[2]["s_m"])
            if best_u - previous[0] <= delta_u_switch + movement_cost_per_m * distance:
                best_u, idx, best_cell, best_perf, best_report = previous
    state_value["chosen_cell_id"] = best_cell["id"]

    diet = trout_diet_at_temp(best_cell["temperature_c"])

    def demand(avail: float, a: float, h: float,
               share: float) -> float:
        return min(avail,
                   holling_type_ii(avail, a, h) * share * eat_dt_h)

    for _ in range(eat_substeps):
        # Stocks cannot go negative; clamp float noise at zero.
        avail_b = max(0.0, state[idx]["ept"] + state[idx]["dipt"])
        avail_e = max(0.0, state[idx]["ne"])
        trout_dem_b = demand(avail_b, 1.0, 0.5, diet["benthic"])
        trout_dem_e = demand(avail_e, 1.0, 0.5, diet["emergent"])
        dipper_dem_b = demand(avail_b, dipper["a"], dipper["h"],
                              dipper["diet"]["benthic"])
        dipper_dem_e = demand(avail_e, dipper["a"], dipper["h"],
                              dipper["diet"]["emergent"])
        scale_b = min(1.0, avail_b / (trout_dem_b + dipper_dem_b)
                      if trout_dem_b + dipper_dem_b > 0 else 1.0)
        scale_e = min(1.0, avail_e / (trout_dem_e + dipper_dem_e)
                      if trout_dem_e + dipper_dem_e > 0 else 1.0)
        totals["trout_eaten"] += (trout_dem_b * scale_b
                                  + trout_dem_e * scale_e)
        totals["dipper_eaten"] += (dipper_dem_b * scale_b
                                   + dipper_dem_e * scale_e)
        total_b = avail_b or 1.0
        benthic_taken = (trout_dem_b + dipper_dem_b) * scale_b
        state[idx]["ept"] -= benthic_taken * state[idx]["ept"] / total_b
        state[idx]["dipt"] -= benthic_taken * state[idx]["dipt"] / total_b
        state[idx]["ne"] -= (trout_dem_e + dipper_dem_e) * scale_e
    for stock in state:
        before = stock["ne"]
        stock["ne"] *= math.exp(-step_days / ne_turnover_days)
        totals["ne_turnover"] += before - stock["ne"]
    refuge_history.append({
        "cell_id": best_cell["id"], "s_m": best_cell["s_m"],
        "temperature_c": round(best_cell["temperature_c"], 2),
        "U": round(best_u, 3),
        "feeding": round(best_perf["feeding"], 3),
        "refuge_drive": round(best_perf["refuge_drive"], 3),
        "thermal_only_U": round(best_report["thermal_only"], 3),
        "solute_factor": best_report["solute_factor"],
        "do_factor": best_report["do_factor"],
        "predation_factor": best_report["predation_factor"],
        "combined_stressor_factor":
            best_report["combined_stressor_factor"],
        "trout_eaten_cumulative": round(
            totals["trout_eaten"], 6),
    })
    # Store final per-cell stressor labels beside the refuge history.
    state_value["stressor_factors_last_step"] = per_cell_stressors

    state_value["simulated_days"] += step_days
    state_value["steps"] += 1
    return {"trout": refuge_history[-1], "prey_totals": dict(totals),
            "dipper": {"intake_total": totals["dipper_eaten"],
                       "intake_per_day": totals["dipper_eaten"] / state_value["simulated_days"]},
            "per_cell": per_cell_stressors}


def run_foodweb(landscape: list[dict[str, Any]],
              days: float = 14.0,
              trout_species: str = "brown_trout",
              dt_days: float = 1.0,
              cover: float = COVER_DEFAULT,
              ne_turnover_days: float = 2.0,
              shear_disturb_pa: float | None = 20.0,
              food_mode: str = "relative",
              food_absolute_scale: float = 1.0,
              solute_concentrations: dict[str, dict[str, float]] | None = None,
              do_mg_l_by_cell: dict[str, float] | None = None,
              predation_rate_by_cell: dict[str, float] | None = None,
              predation_window_days: float = 1.0,
              delta_u_switch: float = 0.0,
              movement_cost_per_m: float = 0.0,
              thermal_curve_form: str = "piecewise_linear") -> dict[str, Any]:
    """Multi-day insect, trout and dipper dynamics on a thermal landscape."""
    if food_mode not in ("relative", "absolute"):
        raise ValueError(
            f"food_mode must be 'relative' or 'absolute', got {food_mode!r}")
    if food_mode == "absolute":
        scale = float(food_absolute_scale)
        if not math.isfinite(scale) or scale <= 0.0:
            raise ValueError("food_absolute_scale must be finite and > 0")
    if not landscape:
        raise ValueError("landscape must be nonempty")
    days = positive("days", days)
    dt_days = positive("dt_days", dt_days)
    ne_turnover_days = positive("ne_turnover_days", ne_turnover_days)
    cover = float(cover)
    if not math.isfinite(cover) or not 0 <= cover <= 1:
        raise ValueError("cover must be finite and in [0, 1]")
    # Partial final step: simulate exactly `days`.
    remaining_days = float(days)
    simulated_days = 0.0
    step_index = 0
    state = [{"ept": 0.5, "dipt": 0.5, "ne": 0.2} for _ in landscape]
    totals = {"emergence": 0.0, "regrowth": 0.0, "trout_eaten": 0.0,
              "dipper_eaten": 0.0, "ne_turnover": 0.0}
    dipper = DEFAULT_DIETS["dipper"]
    refuge_history: list[dict[str, Any]] = []
    last_per_cell_stressors: list[dict[str, Any]] = []
    disturbances = [shear_to_disturbance(cell.get("shear_pa"),
                                         shear_disturb_pa)
                    for cell in landscape]
    food_scales = []
    for cell in landscape:
        scale = float(cell.get("food_scale", 1.0))
        if not math.isfinite(scale) or scale < 0.0:
            raise ValueError(
                f"cell {cell.get('id', '?')}: food_scale must be "
                f"finite and >= 0, got {cell.get('food_scale')!r}")
        food_scales.append(scale)

    state_value = foodweb_state(landscape)
    state = state_value["stocks"]
    totals = state_value["totals"]
    refuge_history = state_value["refuge_history"]
    settings = {"trout_species": trout_species, "cover": cover,
                "ne_turnover_days": ne_turnover_days, "shear_disturb_pa": shear_disturb_pa,
                "food_mode": food_mode, "food_absolute_scale": food_absolute_scale,
                "solute_concentrations": solute_concentrations, "do_mg_l_by_cell": do_mg_l_by_cell,
                "predation_rate_by_cell": predation_rate_by_cell,
                "predation_window_days": predation_window_days,
                "delta_u_switch": delta_u_switch, "movement_cost_per_m": movement_cost_per_m,
                "thermal_curve_form": thermal_curve_form}
    while remaining_days > 1e-12:
        step_days = min(float(dt_days), remaining_days)
        step_foodweb(state_value, landscape, step_days, settings)
        remaining_days -= step_days
        simulated_days += step_days
        step_index += 1
    last_per_cell_stressors = state_value["stressor_factors_last_step"]

    closing = {
        "final_benthic": sum(s["ept"] + s["dipt"] for s in state),
        "final_emergent": sum(s["ne"] for s in state),
    }
    final = refuge_history[-1]
    return {
        "schema": SCHEMA,
        "status": "illustrative_not_calibrated",
        "trout_species": trout_species,
        "days": days,
        "simulated_days": round(simulated_days, 6),
        "steps": step_index,
        "trout": {
            **final,
            "thermal_performance": thermal_performance(
                final["temperature_c"], trout_species),
            "refuge_reason": (
                f"cell {final['cell_id']} at s={final['s_m']:.0f} m "
                f"(U {final['U']}, {final['temperature_c']} C) selected "
                f"by {trout_species} literature suitability over "
                f"{len(landscape)} replay cells"),
        },
        "dipper": {
            "intake_total": round(totals["dipper_eaten"], 6),
            "intake_per_day": round(totals["dipper_eaten"] / max(1e-9, simulated_days or days), 6),
            "basis": ("Holling intake on refuge-cell benthic+emergent; "
                      "shared-foraging-ground assumption; simultaneous "
                      "pro-rata competition with trout"),
        },
        "prey_totals": {k: round(v, 6) for k, v in totals.items()},
        "closing_stocks": {k: round(v, 6) for k, v in closing.items()},
        "per_cell": [
            {"id": cell["id"], "s_m": cell["s_m"],
             "temperature_c": round(cell["temperature_c"], 2),
             "ept": round(stock["ept"], 4), "dipt": round(stock["dipt"], 4),
             "ne": round(stock["ne"], 4)}
            for cell, stock in zip(landscape, state)
        ],
        "stressor_factors_last_step": last_per_cell_stressors,
        "stressor_sources": {
            "solute": (None if solute_concentrations is None
                       else "yellowstone_python.river.solute_transport"
                            ".solute_habitat_multiplier"),
            "do": (None if do_mg_l_by_cell is None
                   else "yellowstone_python.aquatic.river_oxygen.fish_suitability"),
            "predation": (None if predation_rate_by_cell is None
                          else "yellowstone_python.aquatic.piscivores."
                               "refuge_predation_risk via "
                               "fish.predation_survival_factor"),
        },
        "provenance": {
            "thermal": "replay time-mean field (quasi-steady landscape)",
            "velocity": ("mapped hydraulics continuity velocity; "
                         "representative fallback where absent"),
            "shear_coupling": (
                f"bed_shear_pa -> disturbance ramp "
                f"{('0@%sPa to 1@2x' % shear_disturb_pa) if shear_disturb_pa is not None else 'OFF (threshold None)'}; "
                f"None shear -> 0; mean applied "
                f"{sum(disturbances) / len(disturbances):.4f} over "
                f"{len(disturbances)} cells "
                f"({sum(1 for c in landscape if c.get('shear_pa') is None)} "
                f"shear-null)"),
            "trout": "THERMAL_SPECIES literature anchors + authored shapes",
            "insects": "INSECT_GROUPS transferred structure, authored rates",
            "diet": 'trout_diet_at_temp (Kaeding & Kaya (1978) endpoints)',
            "cover": f"authored constant {cover}",
            "food": (("relative: per-cell production normalized by the daily "
                      "maximum (absolute starvation unrepresentable)"
                      if food_mode == "relative"
                      else f"absolute: per-cell production divided by scale "
                           f"{food_absolute_scale} and clamped to [0, 1] "
                           f"(food-poor landscapes rank low)")
                     + "; cells carrying food_scale (tributary pockets, "
                       "authored area ratio) rank on scaled production (mean "
                     f"scale {sum(food_scales) / len(food_scales):.4f} over "
                     f"{len(food_scales)} cells, "
                     f"{sum(1 for s in food_scales if s != 1.0)} scaled)"),
            "limitations": ("no emergent drift; no molluscs (warm food "
                            "underestimated); single trout, single dipper; "
                            "no mortality simulation"),
            "foraging_scope": "selected_cell_only",
            "movement_cost": {"per_m": movement_cost_per_m, "delta_u_switch": delta_u_switch,
                              "status": "authored"},
            "thermal_curve_form": thermal_curve_form,
            "unvisited_prey": "continues local dynamics",
        },
    }


def compare_runs(control_doc: dict[str, Any], pulse_doc: dict[str, Any],
                 window_s: tuple[float, float] | None = None,
                 extra_cells: list[dict[str, Any]] | None = None,
                 **foodweb_kwargs: Any) -> dict[str, Any]:
    """Refuge, diet and emergence response to a thermal intervention."""
    if window_s is None:
        control_land = thermal_landscape(control_doc)
        pulse_land = thermal_landscape(pulse_doc)
        window_note = ("full-run means; short pulses are diluted. "
                       "pass window_s to isolate the intervention")
    else:
        control_land = thermal_landscape(
            control_doc, t_min_s=window_s[0], t_max_s=window_s[1])
        pulse_land = thermal_landscape(
            pulse_doc, t_min_s=window_s[0], t_max_s=window_s[1])
        window_note = (f"both landscapes windowed to "
                       f"[{window_s[0]}, {window_s[1]}] s")
    if extra_cells:
        control_land = list(control_land) + list(extra_cells)
        pulse_land = list(pulse_land) + list(extra_cells)
        window_note += (f"; +{len(extra_cells)} tributary refuge cells "
                         f"appended to both landscapes "
                         f"({', '.join(c.get('id', '?') for c in extra_cells)})")
    control_ids = [c["id"] for c in control_land]
    pulse_ids = [c["id"] for c in pulse_land]
    if control_ids != pulse_ids:
        raise ValueError("control and pulse landscapes have different cell ordering")
    control = run_foodweb(control_land, **foodweb_kwargs)
    pulse = run_foodweb(pulse_land, **foodweb_kwargs)
    shift = pulse["trout"]["s_m"] - control["trout"]["s_m"]
    return {
        "schema": "yellowstone.aquatic_intervention.v1",
        "status": "illustrative_not_calibrated",
        "landscape_window": window_note,
        "days": control["days"],
        "trout_species": control["trout_species"],
        "control": {k: control["trout"][k] for k in
                    ("cell_id", "s_m", "temperature_c", "U", "feeding",
                     "refuge_drive")},
        "pulse": {k: pulse["trout"][k] for k in
                   ("cell_id", "s_m", "temperature_c", "U", "feeding",
                    "refuge_drive")},
        "refuge_shift_m": round(shift, 1),
        "emergence_change": round(
            pulse["prey_totals"]["emergence"]
            - control["prey_totals"]["emergence"], 4),
        "dipper_intake_change": round(
            pulse["dipper"]["intake_total"]
            - control["dipper"]["intake_total"], 4),
    }
