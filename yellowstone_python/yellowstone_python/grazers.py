"""Bison/elk habitat-constrained movement."""
from __future__ import annotations

import copy
import heapq
import math

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
MAX_ROUTE_M = 200.0  # wildlife_actor.gd local-scope guard


def route_length(path_xz: list) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(path_xz, path_xz[1:]))


def segment_samples(a: tuple, b: tuple, every_m: float = 2.0):
    """Sample the full segment; waypoints alone miss crossings."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(math.ceil(length / every_m)))
    for k in range(n + 1):
        f = k / n
        yield (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def graze_timing(biomass: float, capacity: float,
                 base_graze_s: float, base_rest_s: float) -> tuple[float, float]:
    """Rich patch -> longer graze; poor patch -> sooner walk. Driven by fraction of capacity, not absolute index."""
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
            "hypotheses": [h["id"] for h in HYPOTHESES],
            "causal_claim": "none_single; forage basis only, "
                            "predation/hydrology unknowns listed"}
    return out


def check_routes(wildlife: list, shells: list) -> list:
    """Length + apron gates sampled along FULL segments (waypoints alone
    miss crossings between them; pool-polygon gate also lives in Godot)."""
    from .pool_crust import in_apron
    bad = []
    for rec in wildlife:
        if rec.get("medium") != "land" or "path_xz" not in rec:
            continue
        pts = [(float(x), float(z)) for x, z in rec["path_xz"]]
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
    """8-connected A* with Euclidean heuristic on an eligibility grid. Endpoints must be unblocked. Returned waypoints are cell centers. Each accepted step is re-sampled along its true segment and rejected if any sample is blocked."""
    (x0, z0, x1, z1) = (min(bounds[0], bounds[2]), min(bounds[1], bounds[3]),
                        max(bounds[0], bounds[2]), max(bounds[1], bounds[3]))

    def key(p):
        return (round((p[0] - x0) / cell_m), round((p[1] - z0) / cell_m))

    def pt(k):
        return (x0 + k[0] * cell_m, z0 + k[1] * cell_m)

    def step_clear(a, b) -> bool:
        """Every sample along the true segment a→b must be unblocked."""
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(length / segment_m)))
        for k in range(n + 1):
            f = k / n
            if blocked(a[0] + (b[0] - a[0]) * f,
                       a[1] + (b[1] - a[1]) * f):
                return False
        return True

    if blocked(*start):
        raise ValueError(f"plan_path: start {start} is blocked")
    if blocked(*goal):
        raise ValueError(f"plan_path: goal {goal} is blocked")
    sk, gk = key(start), key(goal)
    open_h = [(0.0, sk)]
    came, cost = {}, {sk: 0.0}
    while open_h:
        _, cur = heapq.heappop(open_h)
        if cur == gk:
            break
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nxt = (cur[0] + dx, cur[1] + dz)
            nx, nz = pt(nxt)
            if not (x0 <= nx <= x1 and z0 <= nz <= z1):
                continue
            if blocked(nx, nz):
                continue
            if dx and dz:
                # Corner-cut guard: both orthogonal neighbors must be free.
                if (blocked(*pt((cur[0] + dx, cur[1])))
                        or blocked(*pt((cur[0], cur[1] + dz)))):
                    continue
            # Sample the true segment; a diagonal can still clip a blocked
            # area that is smaller than the cell pitch.
            if not step_clear(pt(cur), (nx, nz)):
                continue
            step = cell_m * (1.4142 if dx and dz else 1.0)
            nc = cost[cur] + step
            if nxt not in cost or nc < cost[nxt]:
                cost[nxt] = nc
                came[nxt] = cur
                h = math.hypot(nx - goal[0], nz - goal[1])
                heapq.heappush(open_h, (nc + h, nxt))
    if gk not in came and gk != sk:
        raise ValueError("plan_path: goal unreachable in bounds")
    path, cur = [goal], gk
    while cur != sk:
        cur = came[cur]
        path.append(pt(cur))
    path[-1] = start
    return list(reversed(path))


def render_tracks(wildlife: list, path: str, w: int = 320,
                  h: int = 320) -> str:
    """Bison loops in the north_meadow frame (field-notes plate)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), (14, 20, 16))
    dr = ImageDraw.Draw(img)
    xs = [p[0] for r in wildlife if r.get("kind") in ("bison", "elk")
          for p in r.get("path_xz", [])]
    zs = [p[1] for r in wildlife if r.get("kind") in ("bison", "elk")
          for p in r.get("path_xz", [])]
    if not xs:
        img.save(path)
        return path
    lo_x, hi_x, lo_z, hi_z = min(xs), max(xs), min(zs), max(zs)
    span = max(hi_x - lo_x, hi_z - lo_z, 1.0) * 1.2

    def px(x, z):
        return (10 + (x - lo_x) / span * (w - 20),
                10 + (z - lo_z) / span * (h - 20))
    colors = [(214, 200, 143), (150, 200, 150), (200, 150, 150)]
    for i, r in enumerate([x for x in wildlife
                           if x.get("kind") in ("bison", "elk")]):
        pts = [px(x, z) for x, z in r["path_xz"]]
        dr.line(pts + [pts[0]], fill=colors[i % 3], width=2)
        dr.text((pts[0][0] + 4, pts[0][1] - 12), r["id"],
                fill=colors[i % 3])
    dr.text((8, h - 16), "sparse authored loops; not abundance",
            fill=(190, 190, 185))
    img.save(path)
    return path
