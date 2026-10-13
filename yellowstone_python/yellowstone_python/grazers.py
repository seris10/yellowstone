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


def update_grazers(wildlife: list, patches: list) -> list:
    out = copy.deepcopy(wildlife)
    by_patch = {p["id"]: p for p in patches}
    for rec in out:
        if rec.get("kind") not in ("bison", "elk"):
            continue
        patch = by_patch.get(rec.get("patch_id", ""), {})
        graze, rest = graze_timing(patch.get("biomass", 0.5),
                                   patch.get("capacity", 1.0),
                                   rec.get("graze_seconds", 24.0),
                                   rec.get("rest_seconds", 18.0))
        rec["graze_seconds"] = round(graze, 1)
        rec["rest_seconds"] = round(rest, 1)
        rec["timing_basis"] = {
            "patch_biomass": round(float(patch.get("biomass", 0.0)), 4),
            "model_context": model_context(HYPOTHESES),
            "causal_claim": "none_single; forage basis only, "
                            "predation/hydrology unknowns listed"}
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
    from .pool_crust import in_apron
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
    """8-connected A* with admissible Euclidean heuristic on an eligibility grid. Endpoints, their cell centers, and every returned segment are validated against blocked terrain. Returned waypoints are cell centers."""
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

