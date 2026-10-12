"""Trout thermal suitability and refuge selection."""
from __future__ import annotations

import copy
import math
import os
from pathlib import Path

THERMAL_DATA_PATH = os.getenv("THERMAL_DATA_PATH")

DEFAULT_WEIGHTS = {"wf": 0.4, "wc": 0.3, "wt": 0.5, "wv": 0.4, "wd": 0.2}
ASSUMED_DEPTH_M = 1.1  # prepare_world carve_water_support default depth
RIVER_WIDTH_M = 22.0   # Firehole authored width
MAX_LATERAL_FRACTION = 0.35  # wildlife_actor.gd river-interior guard
REFUGE_WINDOW_M = 150.0  # accessible swim range along chainage
VELOCITY_OPT_MPS = 0.35  # trout holding preference (illustrative)
VELOCITY_TOL_MPS = 0.45
DEPTH_REF_M = 1.2
# Cold-water trout thermal optimum band (illustrative). Two-sided: below the band is too cold, above is stressful. A one-sided penalty cannot discriminate reaches all below 20 C. Kept for ecosystem.gd parity. THERMAL_SPECIES + thermal_performance() provides the literature-based path.
T_OPT_LO_C = 12.0
T_OPT_HI_C = 18.0


# Literature-transferred thermal performance. Anchor points from measurement; piecewise-linear shapes between them are authored.
THERMAL_SPECIES_PROVENANCE = {
    "brown_trout": {
        "anchors_real": True,
        "curve_shape_authored": True,
        "data_sources": [
            "Elliott 1975 (growth optimum, lab measurement)",
            "Elliott & Hurley 1999 (zero growth, lab measurement)",
            "EPA 1977 chronic 17 C (regulatory standard, derived from studies)",
            "NDEP BrownTTA (UILT 24.4-26.5 C, reviewed literature)",
        ],
        "real_data_gap": "No laboratory feeding/stress curves at 1 C resolution; "
                           "current piecewise-linear interpolation between anchors is authored. "
                           "Kaya 1977 refuge claim verified by abstract (mean >24C / max >25C); "
                           "full text unretrieved; secondary Sullivan 2023 reports ~23C (likely rounding/metric difference).",
    },
    "rainbow_trout": {
        "anchors_real": True,
        "curve_shape_authored": True,
        "data_sources": [
            "Hokanson et al. 1977 (growth optimum/growth-to-22C, lab)",
            "EPA 1977 chronic 19 C (regulatory standard)",
            "NDEP RainbowTTA (UILT 24.3-26.7 C, reviewed literature)",
        ],
        "real_data_gap": "No fine-resolution feeding-rate vs temperature measurements; "
                           "curve shape between 13-17 C (optimum) and 22 C (feed zero) is authored. "
                           "Kaya 1977 refuge claim verified by abstract (same paper, same >24C threshold for both species).",
    },
}

THERMAL_SPECIES = {
    "brown_trout": {
        "t_opt_lo_c": 12.0, "t_opt_hi_c": 16.0,
        "t_feed_zero_c": 20.0, "t_refuge_c": 24.0, "t_uilt_c": 26.0,
        "status": "transferred_from_literature_with_ranges",
        "sources": [
            "Elliott 1975 (optimum growth 12.8-13.6 C, upper optimum 15.0 C)",
            "Elliott & Hurley 1999 (zero growth 18.7 C, optimum 13.9 C)",
            "EPA 1977 chronic 17 C; UILT 24.4-26.5 C warm-acclimated",
            "Kaya Kaeding Burkhalter 1977 (Firehole refuge at mean>24 C)",
            "Kaeding 1976 (growth restricted at means ~21 C)",
        ],
    },
    "rainbow_trout": {
        "t_opt_lo_c": 13.0, "t_opt_hi_c": 17.0,
        "t_feed_zero_c": 22.0, "t_refuge_c": 24.0, "t_uilt_c": 26.0,
        "status": "transferred_from_literature_with_ranges",
        "sources": [
            "Hokanson et al. 1977 (optimum 15-17 C, growth to ~22 C)",
            "EPA 1977 chronic 19 C; UILT 24.3-26.7 C warm-acclimated",
            "Kaya Kaeding Burkhalter 1977 (Firehole refuge at mean>24 C)",
            "Kaeding & Kaya 1978 (warm-station growth, fall spawning shift)",
        ],
    },
}
# Behavioral refuge ramp width above t_refuge: authored shape choice.
REFUGE_RAMP_C = 2.0
# Weight of the refuge-drive term in suitability: authored model choice
# (the anchors it multiplies are literature; the weight is not).
REFUGE_WEIGHT = 0.6

# Lab thermal measurements integration point. THERMAL_DATA_PATH = None  # Set to file path when measurements are available.


def load_lab_thermal(species: str = "brown_trout") -> dict | None:
    """Return configured laboratory data, or None when unavailable."""
    if THERMAL_DATA_PATH is None:
        return None
    p = Path(THERMAL_DATA_PATH)
    if not p.is_file():
        return None
    import json
    data = json.loads(p.read_text())
    return data.get(species)


def thermal_data_status() -> dict:
    """Report provenance status for thermal performance data."""
    return {
        "species_configured": sorted(THERMAL_SPECIES.keys()),
        "anchors_source": "literature_transferred",
        "curve_shape": "authored_piecewise_linear",
        "lab_thermal_available": THERMAL_DATA_PATH is not None,
        "data_gaps": THERMAL_SPECIES_PROVENANCE,
        "note": "Laboratory feeding/stress curves at fine T resolution "
                "would replace authored interpolation between anchors.",
    }


def fish_activity(t_c: float) -> float:
    return min(1.0, max(0.0, (26.0 - float(t_c)) / 8.0))


def temp_penalty(t_c: float) -> float:
    """One-sided stress term kept for ecosystem.gd parity (≥0 above 20 °C)."""
    return max(0.0, float(t_c) - 20.0) / 10.0


def normalize_weights(weights: dict) -> dict:
    total = sum(max(0.0, float(v)) for v in weights.values())
    if total <= 0:
        raise ValueError("at least one weight must be positive")
    return {k: max(0.0, float(v)) / total for k, v in weights.items()}


def thermal_preference(t_c: float) -> float:
    """Two-sided preference in [0, 1]: 1.0 inside the optimum band, falling linearly to 0 outside. Kept for ecosystem.gd parity; thermal_performance() provides the literature path."""
    t = float(t_c)
    if T_OPT_LO_C <= t <= T_OPT_HI_C:
        return 1.0
    if t < T_OPT_LO_C:
        return max(0.0, 1.0 - (T_OPT_LO_C - t) / T_OPT_LO_C)
    return max(0.0, 1.0 - (t - T_OPT_HI_C) / (30.0 - T_OPT_HI_C))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def suitability(food: float, cover: float, t_c: float, velocity: float,
                depth: float, weights: dict | None = None,
                species: str | None = None,
                refuge_weight: float = 0.0) -> float:
    """Ranking score with ceiling 1. Thermal term uncapped: hot ordering survives as negative avoidance."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    food_term = _clamp01(food)
    cover_term = _clamp01(cover)
    vel_term = min(1.0, abs(float(velocity) - VELOCITY_OPT_MPS) / VELOCITY_TOL_MPS)
    # Two-sided depth preference.
    DEPTH_TOL_M = 0.8
    depth_term = min(1.0, abs(float(depth) - DEPTH_REF_M) / DEPTH_TOL_M)
    if species is None:
        temp_term = 1.0 - thermal_preference(t_c)
        refuge_term = 0.0
    else:
        perf = thermal_performance(t_c, species)
        temp_term = (1.0 - perf["feeding"]) + perf["stress"]
        refuge_term = perf["refuge_drive"]
    u = (
        w["wf"] * food_term
        + w["wc"] * cover_term
        - w["wt"] * temp_term
        - w["wv"] * vel_term
        - w["wd"] * depth_term
        - float(refuge_weight) * refuge_term
    )
    return min(1.0, u)


def thermal_performance(t_c: float, species: str = "brown_trout") -> dict:
    """Literature-anchored performance at one water temperature. Returns {feeding, stress, refuge_drive, lethal_flag} in [0, 1]. Anchor points from measurement; piecewise-linear shapes authored. refuge_drive from Kaya et al. 1977. lethal_flag marks water above UILT; shelter, never mortality."""
    if species not in THERMAL_SPECIES:
        raise ValueError(f"unknown trout species {species!r}; "
                         f"have {sorted(THERMAL_SPECIES)}")
    spec = THERMAL_SPECIES[species]
    t = float(t_c)
    lo, hi = spec["t_opt_lo_c"], spec["t_opt_hi_c"]
    zero, refuge, uilt = (spec["t_feed_zero_c"], spec["t_refuge_c"],
                          spec["t_uilt_c"])
    if lo <= t <= hi:
        feeding = 1.0
    elif t < lo:
        feeding = max(0.0, 1.0 - (lo - t) / max(lo - 2.0, 1.0))
    else:
        feeding = max(0.0, 1.0 - (t - hi) / max(zero - hi, 1e-6))
    if t <= zero:
        stress = 0.0
    else:
        # Uncapped ramp: mortality risk keeps rising past refuge and UILT.
        stress = (t - zero) / max(refuge - zero, 1e-6)
    if t <= refuge - REFUGE_RAMP_C:
        drive = 0.0
    else:
        drive = min(1.0, (t - (refuge - REFUGE_RAMP_C)) / REFUGE_RAMP_C)
    return {"feeding": feeding, "stress": stress,
            "refuge_drive": drive,
            "lethal_flag": 1 if t > uilt else 0,
            "species": species,
            "status": spec["status"]}


def velocity_for(flow_m3s: float, width_m: float = RIVER_WIDTH_M,
                 depth_m: float = ASSUMED_DEPTH_M) -> float:
    return float(flow_m3s) / max(1e-6, float(width_m) * float(depth_m))


def assign_reach(z: float, reaches: list) -> dict:
    """Nearest reach by z. Mirrors ecosystem.gd::reach_at."""
    return min(reaches, key=lambda r: abs(float(z) - float(r["z"])))


def build_chainage(river_points: list) -> list:
    """Cumulative metres along the saved downhill point order."""
    s = [0.0]
    for a, b in zip(river_points, river_points[1:]):
        s.append(s[-1] + math.hypot(float(b[0]) - float(a[0]),
                                    float(b[2]) - float(a[2])))
    return s


def reach_membership(river_points: list, reaches: list) -> list:
    """Per-point reach id table using the declared upstream chain order. z-nearestness fails for looping or U-shaped channels. Walk the declared chain and assign every point to the reach whose z-window contains it; points outside every window fall back to the nearest reach by z, flagged."""
    ordered = _chain_order(reaches)
    out = []
    for p in river_points:
        z = float(p[2])
        hit = None
        for r in ordered:
            lo = float(r.get("z_lo", -1e9))
            hi = float(r.get("z_hi", 1e9))
            if lo <= z <= hi:
                hit = r["id"]
                break
        if hit is None:
            hit = assign_reach(z, ordered)["id"]
        out.append(hit)
    return out


def _chain_order(reaches: list) -> list:
    by_id = {r["id"]: r for r in reaches}
    ids = [r["id"] for r in reaches]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate reach IDs")
    missing = {
        r["upstream_id"] for r in reaches
        if r.get("upstream_id") and r["upstream_id"] not in by_id
    }
    if missing:
        raise ValueError(f"unknown upstream reach IDs: {sorted(missing)}")
    starts = [r for r in reaches if not r.get("upstream_id")]
    if len(starts) != 1:
        return sorted(reaches, key=lambda r: -float(r["z"]))
    ordered, seen = [], set()
    cur = starts[0]
    while cur is not None:
        ordered.append(cur)
        seen.add(cur["id"])
        nxt = cur.get("upstream_id")
        cur = by_id.get(nxt) if nxt else None
        if cur is not None and cur["id"] in seen:
            break
    for r in reaches:
        if r["id"] not in seen:
            ordered.append(r)
    return ordered


def reach_z_windows(reaches: list) -> list:
    ordered = _chain_order(reaches)
    out = []
    for i, r in enumerate(ordered):
        lo = float(r["z"])
        hi = float(ordered[i - 1]["z"]) if i > 0 else 1e9
        if hi < lo:
            lo, hi = hi, lo
        if lo > hi:
            raise ValueError(f"invalid reach window for {r['id']}: {lo}, {hi}")
        rec = dict(r)
        rec["z_lo"] = lo
        rec["z_hi"] = hi
        out.append(rec)
    return out


def _reach_by_id(reaches: list, rid: str) -> dict:
    return next(r for r in reaches if r["id"] == rid)


def suitability_at(index: int, river_points: list, membership: list,
                   reaches: list, weights: dict | None, food: float,
                   cover: float, species: str | None = None,
                   refuge_weight: float = 0.0) -> tuple[float, str, float]:
    """(U, reach_id, reach_temp) for holding at a river index."""
    reach = _reach_by_id(reaches, membership[index])
    t = float(reach["temperature_c"])
    v = velocity_for(float(reach.get("flow_m3s", 8.0)))
    return (suitability(food, cover, t, v, ASSUMED_DEPTH_M, weights,
                        species=species, refuge_weight=refuge_weight),
            reach["id"], t)


def select_refuge(record: dict, river_points: list, membership: list,
                  chainage: list, reaches: list, weights: dict | None = None,
                  food: float = 0.7, cover: float = 0.6,
                  species: str | None = None,
                  refuge_weight: float = 0.0) -> dict:
    i0 = int(record.get("start_point_index", 0))
    i1 = int(record.get("end_point_index", 0))
    if not river_points:
        raise ValueError("empty river_points")
    if len(chainage) != len(river_points):
        raise ValueError("chainage and river_points length mismatch")
    if not (0 <= i0 <= i1 < len(river_points)):
        raise ValueError(f"invalid trout interval: {i0}, {i1}")
    width = i1 - i0
    mid_s = (chainage[i0] + chainage[i1]) / 2.0
    from bisect import bisect_left, bisect_right
    lo = max(0, bisect_left(chainage, mid_s - REFUGE_WINDOW_M))
    hi = min(len(chainage) - 1, bisect_right(chainage, mid_s + REFUGE_WINDOW_M))
    best, best_u, best_r, best_t = i0, None, None, None
    for i in range(lo, hi + 1):
        u, rid, t = suitability_at(i, river_points, membership, reaches,
                                   weights, food, cover, species,
                                   refuge_weight)
        if best_u is None or u > best_u:
            best, best_u, best_r, best_t = i, u, rid, t
    half = width // 2
    start = min(max(0, best - half), len(chainage) - 1 - width)
    u0, r0, t0 = suitability_at(i0, river_points, membership, reaches,
                                weights, food, cover, species,
                                refuge_weight)
    basis = f"species {species} (literature performance)" if species \
        else "legacy authored band"
    return {"start": start, "end": start + width, "reach_id": best_r,
            "U": round(best_u, 3), "reach_temp_c": round(best_t, 2),
            "reason": (f"holding index {best} (U {best_u:.2f} at {best_t:.1f}°C) "
                       f"beats index {i0} (U {u0:.2f} at {t0:.1f}°C) "
                       f"within ±{REFUGE_WINDOW_M:.0f} m chainage [{basis}]")}  


def trout_midpoint_z(record: dict, river_points: list) -> float:
    i0, i1 = int(record["start_point_index"]), int(record["end_point_index"])
    mid = river_points[(i0 + i1) // 2]
    return float(mid[2])


def update_trout(wildlife: list, reaches: list, river_points: list,
                  weights: dict | None = None,
                  food: float = 0.7, cover: float = 0.6) -> list:
    """Refuge-selecting trout: holding window relocates toward max suitability
    within swim range; hold/swim cadence follows reach temperature (shelter,
    never mortality). Lateral offsets preserved and clamped to the 0.35
    interior guard."""
    ordered = reach_z_windows(reaches)
    membership = reach_membership(river_points, ordered)
    chainage = build_chainage(river_points)
    out = copy.deepcopy(wildlife)
    for rec in out:
        if "trout" not in str(rec.get("id", "")):
            continue
        species = rec.get("species", "brown_trout")
        if species not in THERMAL_SPECIES:
            rec["refuge_reason"] = f"unknown species {species!r}; skipped"
            continue
        sel = select_refuge(rec, river_points, membership, chainage,
                            ordered, weights, food, cover, species,
                            REFUGE_WEIGHT)
        rec["start_point_index"] = sel["start"]
        rec["end_point_index"] = sel["end"]
        t = sel["reach_temp_c"]
        act = fish_activity(t)
        heat = 1.0 + temp_penalty(t)  # 1.0 at ≤20 °C
        rec["hold_seconds"] = round(float(rec.get("hold_seconds", 10.0))
                                    * (0.75 + 0.5 * heat), 2)
        rec["walk_mps"] = round(float(rec.get("walk_mps", 0.19))
                                * (0.6 + 0.4 * act), 3)
        lat = float(rec.get("lateral_offset_m", 0.0))
        lim = RIVER_WIDTH_M * MAX_LATERAL_FRACTION
        rec["lateral_offset_m"] = round(min(lim, max(-lim, lat)), 2)
        rec["reach_id"] = sel["reach_id"]
        rec["reach_temp_c"] = t
        rec["suitability_U"] = sel["U"]
        rec["refuge_reason"] = sel["reason"]
        rec["species"] = species
        rec["thermal_performance"] = thermal_performance(t, species)
    return out


def chainage_to_index(chainage: list, s: float) -> int:
    """Point index nearest chainage s, clamped to the polyline."""
    from bisect import bisect_left
    if not chainage:
        raise ValueError("empty chainage")
    target = float(s)
    i = max(0, min(len(chainage) - 1, bisect_left(chainage, target)))
    if i > 0 and abs(chainage[i - 1] - target) <= abs(chainage[i] - target):
        i -= 1
    return i


def place_trout_at_chainage(wildlife: list, reaches: list, river_points: list,
                            selection: dict, chainage_offset_m: float = 0.0
                            ) -> list:
    """Hold each trout where the replay food web chose its refuge cell.

    selection is the food web trout block: s_m, cell_id, temperature_c, U.
    chainage_offset_m converts the replay's global chainage to the polyline's
    local chainage. A selection outside the polyline clamps to the nearest end
    and records the gap in refuge_off_polyline_m.
    """
    if not river_points:
        raise ValueError("empty river_points")
    s_m = selection.get("s_m")
    if s_m is None or not math.isfinite(float(s_m)):
        raise ValueError("food web trout selection needs a finite s_m")
    ordered = reach_z_windows(reaches)
    membership = reach_membership(river_points, ordered)
    chainage = build_chainage(river_points)
    width_total = len(chainage)
    local_s = float(s_m) - float(chainage_offset_m)
    cell_t = float(selection.get("temperature_c",
                                 ordered[0]["temperature_c"]))
    center = chainage_to_index(chainage, local_s)
    clamped_s = chainage[center]
    out = copy.deepcopy(wildlife)
    for rec in out:
        if "trout" not in str(rec.get("id", "")):
            continue
        width = int(rec.get("end_point_index", 0)) - int(
            rec.get("start_point_index", 0))
        width = max(0, min(width, width_total - 1))
        start = min(max(0, center - width // 2), width_total - 1 - width)
        rec["start_point_index"] = start
        rec["end_point_index"] = start + width
        rec["reach_id"] = membership[center]
        rec["reach_temp_c"] = round(cell_t, 2)
        if selection.get("U") is not None:
            rec["suitability_U"] = selection["U"]
        rec["refuge_cell_id"] = selection.get("cell_id")
        rec["refuge_chainage_m"] = round(float(s_m), 1)
        rec["refuge_rendered_s_m"] = round(clamped_s, 1)
        rec["refuge_off_polyline_m"] = round(local_s - clamped_s, 1)
        rec["refuge_basis"] = "replay_foodweb"
        rec["thermal_performance"] = thermal_performance(
            cell_t, rec.get("species", "brown_trout"))
        act = fish_activity(cell_t)
        heat = 1.0 + temp_penalty(cell_t)  # 1.0 at <=20 C
        rec["hold_seconds"] = round(float(rec.get("hold_seconds", 10.0))
                                    * (0.75 + 0.5 * heat), 2)
        rec["walk_mps"] = round(float(rec.get("walk_mps", 0.19))
                                * (0.6 + 0.4 * act), 3)
        rec["refuge_reason"] = selection.get(
            "refuge_reason",
            f"replay cell {selection.get('cell_id')} at s={float(s_m):.0f} m")
    return out


def _samples_along(a: list, b: list, lateral: float, every_m: float = 2.0):
    """Centerline AND laterally-offset segment samples (offsets matter)."""
    dx, dz = float(b[0]) - float(a[0]), float(b[2]) - float(a[2])
    length = math.hypot(dx, dz) or 1e-9
    tx, tz = -dz / length, dx / length  # unit side vector
    n = max(1, int(math.ceil(length / every_m)))
    for off in (0.0, lateral):
        for k in range(n + 1):
            f = k / n
            yield (float(a[0]) + dx * f + tx * off,
                   float(a[2]) + dz * f + tz * off)


def check_trout_clear_of_pools(wildlife: list, river_points: list,
                               shells: list) -> list:
    """Every trout SEGMENT (centerline and laterally offset, sampled every
    2 m) must lie outside every apron. Waypoint-only checks miss crossings."""
    from .pool_crust import in_apron
    bad = []
    for rec in wildlife:
        if "trout" not in str(rec.get("id", "")):
            continue
        lat = float(rec.get("lateral_offset_m", 0.0))
        i0 = int(rec.get("start_point_index", 0))
        i1 = int(rec.get("end_point_index", 0))
        if not river_points or not (0 <= i0 <= i1 < len(river_points)):
            continue
        for i in range(i0, i1):
            a, b = river_points[i], river_points[i + 1]
            for x, z in _samples_along(a, b, lat):
                for s in shells:
                    if in_apron(x, z, s):
                        bad.append({"trout": rec["id"], "pool": s["id"],
                                    "segment": [i, i + 1]})
                        break
                else:
                    continue
                break
    return bad


def render_refuge_map(reaches: list, trout: list, path: str,
                      river_points: list | None = None,
                      shells: list | None = None,
                      w: int = 420, h: int = 420) -> str:
    """Deterministic refuge map: Firehole centerline in world position, pool polygons, trout holding midpoints + selected-refuge markers. Every dot is a world coordinate; reproducible across processes and seeds."""
    from PIL import Image, ImageDraw
    from .pool_crust import HALF
    img = Image.new("RGB", (w, h), (14, 20, 18))
    dr = ImageDraw.Draw(img)

    # Frame: tight box around the Firehole points actually used, so the
    # whole channel and every pool ring fit. Falls back to the world square.
    if river_points:
        xs = [float(p[0]) for p in river_points]
        zs = [float(p[2]) for p in river_points]
        x0, x1 = min(xs) - 40, max(xs) + 40
        z0, z1 = min(zs) - 40, max(zs) + 40
        span = max(x1 - x0, z1 - z0, 1.0)

        def px(x, z):
            return ((x - x0) / span * (w - 1), (z - z0) / span * (h - 1))
    else:
        def px(x, z):
            return ((x + HALF) / (2 * HALF) * (w - 1),
                    (z + HALF) / (2 * HALF) * (h - 1))
    if river_points:
        pts = [px(float(p[0]), float(p[2])) for p in river_points[::3]]
        dr.line(pts, fill=(70, 130, 180), width=3)
    for s in shells or []:
        if s.get("ring"):
            dr.polygon([px(x, z) for x, z in s["ring"]],
                       outline=(200, 120, 90))
    for t in trout:
        if "trout" not in str(t.get("id", "")):
            continue
        i = (int(t["start_point_index"]) + int(t["end_point_index"])) // 2
        if river_points and 0 <= i < len(river_points):
            p = river_points[i]
            x, y = px(float(p[0]), float(p[2]))
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(255, 230, 120))
            dr.text((x + 7, y - 8), f"{t['id']}@{t.get('reach_id', '?')}",
                    fill=(255, 230, 120))
    dr.text((8, h - 16), "trout dots = holding midpoints (world coords)",
            fill=(200, 200, 190))
    img.save(path)
    return path
