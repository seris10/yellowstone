"""Multi-day insect + trout + dipper dynamics on a thermal landscape."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from .coupling import POCKET_CONSERVATION
from .fish import REFUGE_WEIGHT, suitability, thermal_performance
from .insects_birds import (DEFAULT_DIETS, INSECT_GROUPS, develop_benthic,
                             holling_type_ii, trout_diet_at_temp)

SCHEMA = "yellowstone.aquatic_foodweb.v1"
COVER_DEFAULT = 0.6  # authored trout cover (same default as update_trout)


# --- Tributary cold-refuge candidates (landscape-level scenario cells) ---
#
# Survey of the BASELINE ecosystem (2026-10-11, map-measured from
# yellowstone_midway/data/world.json + ecosystem.json):
#   - ecosystem.json river_reaches carry NO active cold lateral inflow:
#     every reach has lateral_sources == [] except excelsior_mixing, whose
#     only source is the 62 C excelsior_aggregate_outflow (hot).
#   - hydro_thermal.DEFAULT_TRIBUTARIES names four cold creeks
#     (fairy/white/rabbit/mallard at authored 11-12 C) but all sit at
#     0.0 flow, i.e. omitted — the baseline is preserved, none of them
#     run anywhere under any boundary condition.
#   - world.json maps real creek polylines (Fairy/White/Rabbit/Mallard).
#     Only two mapped fragments actually touch the replay chain (solver
#     chainage s=7..5470 m on the Midway reach):
#       Rabbit Creek feature river_5877_0 downstream end lands 10 m from
#         replay cell_00064 -> confluence s ~= 1260 m (river_5872_0 reach);
#       Mallard Creek feature river_5938_0 downstream end lands 7 m from
#         replay cell_00002 -> confluence s ~= 35 m (river_5998_0 reach).
#     Fairy Creek fragments stay >1300 m off-chain and White Creek's best
#     fragment ends 85 m off-chain at the downstream end (s ~= 5470 m):
#     mapped but not junctions in this world snapshot, so not candidates.
# Temperatures below are AUTHORED scenario values taken from the named
# DEFAULT_TRIBUTARIES entries (11 C), not measurements: no tributary
# temperature observation exists in this repo. Under the hot-lowflow
# boundary (26 C) both candidates run below the Kaya 24 C refuge-drive
# threshold; in the baseline they run at zero flow (absent).
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
# Habitat-area food scaling: a confluence pocket (~18-36 m2 wetted, small
# cold plume mouth) produces a fraction of a mainstem replay cell's food
# (typical cell ~20 m x ~22 m ~= 440 m2 surface). Default 0.05 is the
# authored area ratio (22 m2 / 440 m2); the sensitivity sweep varies it.
# Provenance authored throughout; the sweep reports the flip threshold.
TRIBUTARY_FOOD_SCALE_DEFAULT = 0.05
TRIBUTARY_FOOD_SCALE_PROVENANCE = (
    "authored_area_ratio_22m2_pocket_over_440m2_mainstem_cell")
# Slow pocket hydraulics (authored estimates, stated, never measured):
# mouth-pool water barely moves and is shallower than the mainstem.
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
    """Per-cell quasi-steady thermal + hydraulic habitat from replay frames. t_min_s/t_max_s restrict to a window for intervention comparison."""
    rep = unwrap_replay(replay_doc)
    cells, frames = rep["cells"], rep["frames"]
    if not cells or not frames:
        raise ValueError("replay needs cells and frames")
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
            # Mapped bed shear (Pa) or None where Manning is undefined
            # (sub-noise-floor grade cells); run_foodweb maps None to
            # zero disturbance, never to an invented value.
            "shear_pa": hydro.get("bed_shear_pa"),
        })
    return landscape


def build_tributary_cell(spec: dict[str, Any],
                         temperature_c: float | None = None,
                         food_scale: float = TRIBUTARY_FOOD_SCALE_DEFAULT,
                         ) -> dict[str, Any]:
    """Build one tributary mouth-pocket landscape cell from a spec.

    temperature_c overrides the spec temperature (sensitivity sweep
    hook); food_scale sets the habitat-area food multiplier (finite,
    >= 0). Raises ValueError on nonfinite inputs. The cell carries a
    non-conservative conservation flag: holding water for selection,
    excluded from solver heat and water budgets.
    """
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
        # Contract coupling.pocket_holding: prescribed holding water,
        # excluded from solver heat and water budgets.
        "conservation": POCKET_CONSERVATION,
        # Manning-undefined pocket: shear None maps to zero
        # disturbance in run_foodweb, never to an invented value.
        "shear_pa": None,
        # Habitat-area food scaling: pocket production is a small
        # fraction of a mainstem cell's (authored area ratio).
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
    """Append cold tributary mouth-pocket cells to a thermal landscape.

    Operates on LANDSCAPE dicts (thermal_landscape output), never on
    replay cells/frames: the 1-D solver's heat/water budget closure is
    left untouched, and the pockets are off-channel holding water the
    trout can select, not mainstem transport volumes. Returns a new
    list; the input is not mutated.

    specs defaults to TRIBUTARY_CANDIDATES (N=2: Rabbit + Mallard).
    temperature_c overrides every pocket's temperature (sensitivity
    sweep hook); food_scale sets each pocket's habitat-area food
    multiplier (must be finite and >= 0). Every assumption is recorded
    on the cell under "tributary_provenance" with authored provenance.
    """
    if specs is None:
        specs = list(TRIBUTARY_CANDIDATES)
    out = list(landscape)
    for spec in specs:
        out.append(build_tributary_cell(spec, temperature_c=temperature_c,
                                        food_scale=food_scale))
    return out


def shear_to_disturbance(shear_pa: float | None,
                         threshold_pa: float | None) -> float:
    """Mapped bed shear (Pa) -> benthic disturbance fraction in [0, 1].

    None shear (Manning-undefined cell) and None threshold (coupling off)
    both yield zero. Positive shear at/below the threshold yields zero;
    above it the fraction ramps linearly to 1 at twice the threshold
    (authored shape, stated in run_foodweb). Nonfinite or negative shear
    raises instead of silently zeroing.
    """
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


def run_foodweb(landscape: list[dict[str, Any]],
              days: float = 14.0,
              trout_species: str = "brown_trout",
              dt_days: float = 1.0,
              cover: float = COVER_DEFAULT,
              ne_turnover_days: float = 2.0,
              shear_disturb_pa: float | None = 20.0) -> dict[str, Any]:
    """Multi-day insect + trout + dipper dynamics. shear_disturbance ramps 0 at threshold to 1 at twice it. None shear maps to zero; None threshold switches coupling off. Default 20 Pa."""
    if not landscape:
        raise ValueError("landscape must be nonempty")
    def _positive_finite(name, value):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be numeric, not boolean")
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and > 0")
        return value

    days = _positive_finite("days", days)
    dt_days = _positive_finite("dt_days", dt_days)
    ne_turnover_days = _positive_finite("ne_turnover_days", ne_turnover_days)
    cover = float(cover)
    if not math.isfinite(cover) or not 0 <= cover <= 1:
        raise ValueError("cover must be finite and in [0, 1]")
    # Partial final step: simulate exactly `days`, not rounded steps.
    remaining_days = float(days)
    simulated_days = 0.0
    step_index = 0
    state = [{"ept": 0.5, "dipt": 0.5, "ne": 0.2} for _ in landscape]
    totals = {"emergence": 0.0, "regrowth": 0.0, "trout_eaten": 0.0,
              "dipper_eaten": 0.0, "ne_turnover": 0.0}
    dipper = DEFAULT_DIETS["dipper"]
    refuge_history: list[dict[str, Any]] = []
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

    while remaining_days > 1e-12:
        step_days = min(float(dt_days), remaining_days)
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
                after, emergence = develop_benthic(
                    before, t, dt_s_step, tbase=params["tbase_c"],
                    rate=params["rate_per_dd"],
                    disturbance=disturb,
                    t_cutoff=params["t_cutoff_c"])
                regrow = after - (before - emergence)
                totals["emergence"] += emergence
                totals["regrowth"] += regrow
                stock[key] = after
                stock["ne"] += emergence
                edible += emergence + 0.5 * after
            foods.append(edible * scale)
        ceiling = max(foods) or 1.0

        scored: list[tuple[float, int, dict[str, Any], Any]] = []
        for idx, cell in enumerate(landscape):
            food = foods[idx]
            perf = thermal_performance(cell["temperature_c"], trout_species)
            u = suitability(food / ceiling, cover, cell["temperature_c"],
                            cell["velocity_m_s"], cell["depth_m"],
                            species=trout_species,
                            refuge_weight=REFUGE_WEIGHT)
            scored.append((u, idx, cell, perf))
        scored.sort(key=lambda row: row[0], reverse=True)
        best_u, idx, best_cell, best_perf = scored[0]

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
            "trout_eaten_cumulative": round(
                totals["trout_eaten"], 6),
        })
        remaining_days -= step_days
        simulated_days += step_days
        step_index += 1

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
            "diet": "trout_diet_at_temp (Kaeding & Kaya 1978 endpoints)",
            "cover": f"authored constant {cover}",
            "food": ("per-cell production normalized by the daily maximum: "
                     "purely relative ranking, absolute starvation is "
                     "impossible in this model; cells carrying food_scale "
                     "(tributary pockets, authored area ratio) rank on "
                     f"scaled production (mean scale "
                     f"{sum(food_scales) / len(food_scales):.4f} over "
                     f"{len(food_scales)} cells, "
                     f"{sum(1 for s in food_scales if s != 1.0)} scaled)"),
            "limitations": ("no emergent drift; no molluscs (warm food "
                            "underestimated); single trout, single dipper; "
                            "no mortality simulation"),
            "foraging_scope": "selected_cell_only",
            "movement_cost": "not modeled",
            "unvisited_prey": "continues local dynamics",
        },
    }


def compare_runs(control_doc: dict[str, Any], pulse_doc: dict[str, Any],
                 window_s: tuple[float, float] | None = None,
                 extra_cells: list[dict[str, Any]] | None = None,
                 **foodweb_kwargs: Any) -> dict[str, Any]:
    """Refuge + diet + emergence response to a thermal intervention.

    window_s isolates the intervention clock interval in BOTH runs
    (control window-mean vs pulse window-mean); without it a short
    pulse vanishes into the whole-run mean. Reported explicitly.
    extra_cells (e.g. tributary pockets from append_tributary_cells)
    are appended to BOTH landscapes so control and pulse rank the same
    choice set; the count is reported explicitly.
    """
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--pulse", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--species", default="brown_trout")
    parser.add_argument("--window", type=float, nargs=2, default=None,
                        metavar=("T_MIN_S", "T_MAX_S"),
                        help="isolate the intervention clock interval in "
                             "both runs (required for short pulses)")
    args = parser.parse_args()
    try:
        control_doc = json.loads(args.control.read_text(encoding="utf-8"))
        kwargs: dict[str, Any] = {"days": args.days,
                                  "trout_species": args.species}
        if args.pulse:
            pulse_doc = json.loads(args.pulse.read_text(encoding="utf-8"))
            window = tuple(args.window) if args.window else None
            document = compare_runs(control_doc, pulse_doc, window,
                                    **kwargs)
        else:
            landscape = thermal_landscape(control_doc)
            document = run_foodweb(landscape, **kwargs)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_name(args.out.name + ".tmp")
        tmp.write_text(json.dumps(document, indent=1, allow_nan=False)
                       + "\n", encoding="utf-8")
        tmp.replace(args.out)
    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"aquatic foodweb failed: {error}\n")
    if "refuge_shift_m" in document:
        print(f"refuge shift: {document['refuge_shift_m']} m "
              f"(control s={document['control']['s_m']:.0f} m @ "
              f"{document['control']['temperature_c']} C -> pulse "
              f"s={document['pulse']['s_m']:.0f} m @ "
              f"{document['pulse']['temperature_c']} C)")
    else:
        print(f"refuge: {document['trout']['cell_id']} "
              f"s={document['trout']['s_m']:.0f} m @ "
              f"{document['trout']['temperature_c']} C")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
