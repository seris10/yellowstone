"""Bison/elk habitat-constrained movement."""
from __future__ import annotations

import copy
import heapq
import math
from pathlib import Path

HYPOTHESES = [
    {"id": "forage_quality",
     "claim": "graze-bout length tracks patch biomass and moisture",
     "status": "implemented_basis",
     "unknowns": ["species composition", "forage quality vs bulk biomass",
                  "seasonal phenology"]},
    {"id": "predation_risk",
     "claim": "wolves/bears shift vigilance and meadow use",
     "status": "not_modeled",
     "unknowns": ["predator presence data", "vigilance budgets",
                  "calf-season sensitivity"]},
    {"id": "hydrology",
     "claim": "soil moisture and snowmelt set meadow green-up timing",
     "status": "partial_via_M08",
     "unknowns": ["soil depth/Ksat layers (null per contract)",
                  "hydroperiod observations"]},
]
def model_context(hypotheses: list) -> dict:
    """Split hypothesis provenance by modeled status."""
    return {
        "implemented": [h["id"] for h in hypotheses
                        if h["status"] == "implemented_basis"],
        "partial": [h["id"] for h in hypotheses
                    if h["status"].startswith("partial")],
        "not_modeled": [h["id"] for h in hypotheses
                        if h["status"] == "not_modeled"],
    }


MAX_ROUTE_M = 200.0  # wildlife_actor.gd local-scope guard

SPECIES_PARAMS: dict[str, dict] = {
    "bison": {
        "crater_depth_m": 0.90,
        "cost_half_m": 0.60,
        "intake_dry_kg_per_s": 500.0 * 0.022 / 86400.0,
        "source": ('Authored within cited ranges. Meagher (1973) NPS Scientific Monograph 1 (winter cratering in deep snow); Fortin, Fryxell and Regis (2002) Ecology 83(4) 970-982 doi:10.1890/0012-9658(2002)083[0970:TTSOFD]2.0.CO;2 (bison foraging decisions and snow); Van Soest (1994) Nutritional Ecology of the Ruminant (intake rates).'),
    },
    "elk": {
        "crater_depth_m": 0.50,
        "cost_half_m": 0.40,
        "intake_dry_kg_per_s": 250.0 * 0.020 / 86400.0,
        "source": ('Authored within cited ranges. Telfer and Kelsall (1984) Ecology 65(6) 1828-1834 doi:10.2307/1937779 (ungulate adaptations to snow); Van Soest (1994) Nutritional Ecology of the Ruminant (intake rates).'),
    },
}

# One biomass index unit maps to one kg dry forage, authored for coupling.
BIOMASS_INDEX_PER_KG_DRY = 1.0
BIOMASS_INDEX_PROVENANCE = (
    "authored_dimensionless_biomass_index_per_kg_dry_mapping_for_coupling")


def route_length(path_xz: list) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(path_xz, path_xz[1:]))


def segment_samples(a: tuple, b: tuple, every_m: float = 2.0):
    """Sample the full segment; waypoints alone miss crossings."""
    if not math.isfinite(every_m) or every_m <= 0.0:
        raise ValueError("every_m must be finite and > 0")
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(2, int(math.ceil(length / every_m)))
    for k in range(n + 1):
        f = k / n
        yield (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def graze_timing(biomass: float, capacity: float,
                 base_graze_s: float, base_rest_s: float) -> tuple[float, float]:
    """Rich patch yields a longer graze, poor patch an earlier walk; driven by fraction of capacity."""
    frac = min(1.0, max(0.0, float(biomass) / max(1e-4, float(capacity))))
    return (max(6.0, float(base_graze_s) * (0.5 + frac)),
            max(6.0, float(base_rest_s)))


def snow_movement_cost(species: str, snow_depth_m: float) -> float:
    """Movement-cost multiplier (dimensionless, >= 1) for a species in snow.
Sigmoid cost 1 + depth / cost_half_m; infinite above the species cratering limit."""
    if species not in SPECIES_PARAMS:
        raise ValueError(f"unknown species {species!r}; "
                         f"have {sorted(SPECIES_PARAMS)}")
    d = float(snow_depth_m)
    if not math.isfinite(d) or d < 0.0:
        raise ValueError("snow_depth_m must be finite and >= 0")
    params = SPECIES_PARAMS[species]
    crater = float(params["crater_depth_m"])
    if d >= crater:
        return math.inf
    return 1.0 + d / float(params["cost_half_m"])


def route_cost(path_xz: list, snow_depth_m: float, species: str) -> float:
    """Species-weighted route cost: length times the snow movement cost."""
    length = route_length(path_xz)
    return length * snow_movement_cost(species, snow_depth_m)


def select_patch(current_patch_id: str, patches: list,
                 snow_depth_by_patch: dict | None,
                 warm_ground_by_patch: dict | None,
                 species: str = "bison",
                 deep_snow_threshold_m: float | None = None) -> str:
    """Choose where the grazer feeds."""
    if species not in SPECIES_PARAMS:
        raise ValueError(f"unknown species {species!r}")
    threshold = (float(deep_snow_threshold_m)
                 if deep_snow_threshold_m is not None
                 else SPECIES_PARAMS[species]["crater_depth_m"])
    depth = (float((snow_depth_by_patch or {}).get(current_patch_id, 0.0))
             if snow_depth_by_patch is not None else 0.0)
    if depth < threshold:
        return current_patch_id
    warm = warm_ground_by_patch or {}
    if warm.get(current_patch_id):
        return current_patch_id
    for p in patches:
        pid = p.get("id")
        if pid == current_patch_id:
            continue
        if warm.get(pid):
            return pid
    return current_patch_id


def grazing_eligible(record: dict) -> bool:
    """Exclude inactive, unqualified and independently allocated grazer records."""
    return (record.get("active") is not False
            and record.get("route_support", {}).get("qualified") is not False
            and record.get("grazing_owner") != "mammals")


def consumed_by_patch_from_grazers(wildlife: list, dt_s: float) -> dict:
    """Aggregate per-patch forage consumption (biomass index units) over dt_s.
Reads rate_per_second set by update_grazers; returns {patch_id: consumed}."""
    dt = float(dt_s)
    if not math.isfinite(dt) or dt < 0.0:
        raise ValueError("dt_s must be finite and >= 0")
    out: dict[str, float] = {}
    for rec in wildlife or []:
        if rec.get("kind") not in SPECIES_PARAMS:
            continue
        if not grazing_eligible(rec):
            continue
        pid = rec.get("patch_id")
        rate = rec.get("rate_per_second")
        if pid is None or rate is None:
            continue
        try:
            r = float(rate)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(r) or r <= 0.0:
            continue
        out[pid] = out.get(pid, 0.0) + r * dt
    return out


def update_grazers(wildlife: list, patches: list,
                   snow_depth_by_patch: dict | None = None,
                   warm_ground_by_patch: dict | None = None) -> list:
    out = copy.deepcopy(wildlife)
    by_patch = {p["id"]: p for p in patches}
    for rec in out:
        kind = rec.get("kind")
        if kind not in SPECIES_PARAMS:
            continue
        if not grazing_eligible(rec):
            rec["rate_per_second"] = 0.0
            rec["timing_basis"] = {"causal_claim": "inactive, excluded route or independent mammal allocation"}
            continue
        current_id = rec.get("patch_id", "")
        chosen = select_patch(current_id, patches,
                              snow_depth_by_patch, warm_ground_by_patch,
                              species=kind)
        if chosen != current_id:
            rec["patch_id"] = chosen
            rec["patch_shift_reason"] = "warm_ground_refuge_under_deep_snow"
        patch = by_patch.get(chosen, {})
        graze, rest = graze_timing(patch.get("biomass", 0.5),
                                   patch.get("capacity", 1.0),
                                   rec.get("graze_seconds", 24.0),
                                   rec.get("rest_seconds", 18.0))
        # Snow depth on the active patch lengthens rest and shortens graze.
        if snow_depth_by_patch is not None:
            depth = float(snow_depth_by_patch.get(chosen, 0.0))
            try:
                mult = snow_movement_cost(kind, depth)
            except ValueError:
                mult = 1.0
            if math.isinf(mult):
                graze_eff = 6.0
                rest = max(rest, graze * 2.0)
            else:
                graze_eff = max(6.0, graze / mult)
                rest = rest * mult
            graze = graze_eff
            rec["snow_depth_m"] = round(depth, 3)
            rec["movement_cost_factor"] = (
                "inf" if math.isinf(mult) else round(mult, 3))
        rec["graze_seconds"] = round(graze, 1)
        rec["rest_seconds"] = round(rest, 1)
        intake = SPECIES_PARAMS[kind]["intake_dry_kg_per_s"]
        duty = graze / max(1e-6, graze + rest)
        rec["rate_per_second"] = round(
            intake * BIOMASS_INDEX_PER_KG_DRY * duty, 10)
        rec["intake_source"] = SPECIES_PARAMS[kind]["source"]
        rec["timing_basis"] = {
            "patch_biomass": round(float(patch.get("biomass", 0.0)), 4),
            "model_context": model_context(HYPOTHESES),
            "causal_claim": "forage + snow access; predation unknown",
        }
    return out


def _route_xz(rec: dict) -> list | None:
    """Route as finite float pairs, or None when the record is malformed."""
    pts = []
    for p in rec.get("path_xz") or []:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        try:
            x, z = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(x) and math.isfinite(z)):
            return None
        pts.append((x, z))
    return pts


def check_routes(wildlife: list, shells: list) -> list:
    """Length and apron gates sampled along the full segment; a one-point path is a stationary anchor.
Pool-polygon gate also lives in Godot (wildlife_actor.gd route build)."""
    from yellowstone_python.thermal_features.pool_crust import in_apron
    bad = []
    for rec in wildlife:
        if rec.get("medium") != "land" or "path_xz" not in rec:
            continue
        pts = _route_xz(rec)
        if pts is None:
            bad.append({"actor": rec.get("id"), "why": "route path_xz is malformed"})
            continue
        if not pts:
            bad.append({"actor": rec.get("id"), "why": "route path_xz is empty"})
            continue
        if len(pts) == 1:
            x, z = pts[0]
            for s in shells:
                if in_apron(x, z, s):
                    bad.append({"actor": rec.get("id"),
                                "why": "anchor inside apron",
                                "pool": s["id"]})
                    break
            continue
        if route_length(pts) > MAX_ROUTE_M:
            bad.append({"actor": rec["id"], "why": "route exceeds 200 m"})
        for a, b in zip(pts, pts[1:]):
            for x, z in segment_samples(a, b):
                for s in shells:
                    if in_apron(x, z, s):
                        bad.append({"actor": rec["id"],
                                    "why": "segment inside apron",
                                    "pool": s["id"]})
                        break
                else:
                    continue
                break
    return bad


def plan_path(start: tuple, goal: tuple, blocked, cell_m: float = 4.0,
              bounds: tuple = (-300, -600, 100, -200),
              segment_m: float = 1.0) -> list:
    """8-connected A* with admissible Euclidean heuristic on an eligibility grid."""
    (x0, z0, x1, z1) = (min(bounds[0], bounds[2]), min(bounds[1], bounds[3]),
                        max(bounds[0], bounds[2]), max(bounds[1], bounds[3]))
    cell_m = float(cell_m)
    if not math.isfinite(cell_m) or cell_m <= 0.0:
        raise ValueError(f"cell_m must be finite and > 0, got {cell_m}")
    segment_m = float(segment_m)
    if not math.isfinite(segment_m) or segment_m <= 0.0:
        raise ValueError(f"segment_m must be finite and > 0, got {segment_m}")

    def _finite_xz(name: str, xz) -> tuple[float, float]:
        if not isinstance(xz, (list, tuple)) or len(xz) != 2:
            raise ValueError(f"{name} must be a two-number [x, z] pair")
        out = []
        for v in xz:
            try:
                v = float(v)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
            if not math.isfinite(v):
                raise ValueError(f"{name} must be finite")
            out.append(v)
        return (out[0], out[1])

    start = _finite_xz("start", start)
    goal = _finite_xz("goal", goal)
    for name, xz in (("start", start), ("goal", goal)):
        if not (x0 <= xz[0] <= x1 and z0 <= xz[1] <= z1):
            raise ValueError(f"plan_path: {name} {xz} outside bounds "
                             f"[{x0}, {z0}, {x1}, {z1}]")

    cache: dict = {}

    def is_blocked(x: float, z: float) -> bool:
        k = (float(x), float(z))
        if k not in cache:
            cache[k] = bool(blocked(x, z))
        return cache[k]

    def key(p):
        return (round((p[0] - x0) / cell_m), round((p[1] - z0) / cell_m))

    def pt(k):
        return (x0 + k[0] * cell_m, z0 + k[1] * cell_m)

    def step_clear(a, b) -> bool:
        """Each sample along the true segment a to b must be unblocked."""
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(2, int(math.ceil(length / segment_m)))
        for k in range(n + 1):
            f = k / n
            if is_blocked(a[0] + (b[0] - a[0]) * f,
                          a[1] + (b[1] - a[1]) * f):
                return False
        return True

    if is_blocked(*start):
        raise ValueError(f"plan_path: start {start} is blocked")
    if is_blocked(*goal):
        raise ValueError(f"plan_path: goal {goal} is blocked")
    sk, gk = key(start), key(goal)
    if sk == gk:
        if step_clear(start, goal):
            return [start, goal]
        raise ValueError("plan_path: start and goal share a cell with a "
                         "blocked segment")
    if not step_clear(start, pt(sk)):
        raise ValueError("plan_path: start cannot connect to its start cell")
    if not step_clear(pt(gk), goal):
        raise ValueError("plan_path: goal cannot connect to its goal cell")
    # Insertion counter breaks f-cost ties so repeat runs return the same path.
    counter = 0
    open_h: list = [(0.0, counter, sk)]
    counter += 1
    came, cost = {}, {sk: 0.0}
    while open_h:
        priority, _, cur = heapq.heappop(open_h)
        if cur == gk:
            break
        if priority > (cost[cur] + math.hypot(pt(cur)[0] - goal[0],
                                            pt(cur)[1] - goal[1]) + 1e-9):
            continue  # superseded by a cheaper route to the same cell
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nxt = (cur[0] + dx, cur[1] + dz)
            nx, nz = pt(nxt)
            if not (x0 <= nx <= x1 and z0 <= nz <= z1):
                continue
            if is_blocked(nx, nz):
                continue
            if dx and dz:
                # Corner-cut guard: both orthogonal neighbors must be free.
                if (is_blocked(*pt((cur[0] + dx, cur[1])))
                        or is_blocked(*pt((cur[0], cur[1] + dz)))):
                    continue
            # Sample the true segment; a diagonal can clip a blocked area smaller than the cell pitch.
            if not step_clear(pt(cur), (nx, nz)):
                continue
            step = math.hypot(dx * cell_m, dz * cell_m)
            nc = cost[cur] + step
            if nxt not in cost or nc < cost[nxt]:
                cost[nxt] = nc
                came[nxt] = cur
                h = math.hypot(nx - goal[0], nz - goal[1])
                heapq.heappush(open_h, (nc + h, counter, nxt))
                counter += 1
    if gk not in came and gk != sk:
        raise ValueError("plan_path: goal unreachable in bounds")
    path, cur = [goal], gk
    while cur != sk:
        cur = came[cur]
        path.append(pt(cur))
    path[-1] = start
    path = list(reversed(path))
    # Final guarantee: the real endpoint segments (not just cell centers) are clear.
    if not step_clear(path[0], path[1]):
        raise ValueError("plan_path: start segment crosses blocked terrain")
    if len(path) >= 2 and not step_clear(path[-2], path[-1]):
        raise ValueError("plan_path: goal segment crosses blocked terrain")
    return path


def render_tracks(wildlife: list, path: str, w: int = 320,
                  h: int = 320) -> str:
    """Bison loops in the north_meadow frame (field-notes plate)."""
    from PIL import Image, ImageDraw
    actors = [r for r in wildlife
              if r.get("kind") in ("bison", "elk")
              and len(r.get("path_xz") or []) >= 2]
    img = Image.new("RGB", (w, h), (14, 20, 16))
    dr = ImageDraw.Draw(img)
    if not actors:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        return path
    xs = [p[0] for r in actors for p in r.get("path_xz", [])]
    zs = [p[1] for r in actors for p in r.get("path_xz", [])]
    if not xs:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        return path
    lo_x, hi_x, lo_z, hi_z = min(xs), max(xs), min(zs), max(zs)
    span = max(hi_x - lo_x, hi_z - lo_z, 1.0) * 1.2

    def px(x, z):
        return (10 + (x - lo_x) / span * (w - 20),
                10 + (z - lo_z) / span * (h - 20))
    colors = [(214, 200, 143), (150, 200, 150), (200, 150, 150)]
    for i, r in enumerate(actors):
        pts = [px(x, z) for x, z in r.get("path_xz", [])]
        dr.line(pts + [pts[0]], fill=colors[i % 3], width=2)
        dr.text((pts[0][0] + 4, pts[0][1] - 12), r.get("id", ""),
                fill=colors[i % 3])
    dr.text((8, h - 16), "sparse authored loops; not abundance",
            fill=(190, 190, 185))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
