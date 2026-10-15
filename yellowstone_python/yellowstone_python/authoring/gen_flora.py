"""Flora density pass: generate, machine-review, and stage grass and pine infill."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic

import json
import math
import random

from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.thermal_features.pool_crust import build_all as build_shells
from yellowstone_python.thermal_features.pool_crust import in_apron as _in_apron
from yellowstone_python.authoring.review_proposals import review, to_override_record
from yellowstone_python.land.vegetation import HALF, load_terrain, moisture_at, terrain_fns
from yellowstone_python.land.vegetation import propose_plantings_reviewed

WORLD = default_world_root()

# Habitat-mask mineral channel (R) at or above this value is sinter; corridor_flora convention.
MINERAL_PINE_MAX = 0.35

REGIONS = [
    {"guild": "meadow_grass", "center": (-127, -450), "radius": 70,
     "count": 2500, "seed": 101, "habitat": "dry_meadow",
     "threshold": 0.10, "canopy": 0.3, "min_existing_m": 0.0},
    {"guild": "meadow_grass", "center": (69, -315), "radius": 65,
     "count": 1500, "seed": 102, "habitat": "river_bank",
     "threshold": 0.10, "canopy": 0.2, "min_existing_m": 0.0},
    {"guild": "meadow_grass", "center": (-252, 159), "radius": 110,
     "count": 1500, "seed": 103, "habitat": "dry_meadow",
     "threshold": 0.06, "canopy": 0.5, "min_existing_m": 0.0,
     "note": "sparse edge colonization; threshold recorded, not tuned"},
    {"guild": "lodgepole_pine", "center": (-360, 260), "radius": 80,
     "count": 200, "seed": 201, "habitat": "forest_edge",
     "threshold": 0.12, "canopy": 0.6, "min_existing_m": 2.0},
]


def canopy_driven_forest(project=None, world_root=None, *, apply=False):
    """Produce dominant-tree placements from measured canopy cover and crown centers."""
    from pathlib import Path
    from yellowstone_python.census.lidar_workflow import build_forest_products
    project = Path(project) if project is not None else Path(__file__).resolve().parents[2]
    return build_forest_products(project, world_root or WORLD, apply=apply)




def _ortho():
    from PIL import Image as _Image
    import numpy as _np
    im = _np.asarray(_Image.open(
        WORLD / "references" / "orthophoto.jpg").convert("RGB")).astype(float) / 255.0
    H, W = im.shape[:2]
    return im, H, W


def green_light_at(im, H, W, x, z):
    ix = min(max(int((x + HALF) / (2.0 * HALF) * (W - 1)), 0), W - 1)
    iz = min(max(int((z + HALF) / (2.0 * HALF) * (H - 1)), 0), H - 1)
    r, g, b = (float(v) for v in im[iz, ix])
    light = (r + g + b) / 3.0
    green = min(1.0, max(0.0, (g - r + 0.045) * 8.0))
    return green, light


def _segment_dist_sq(px, pz, ax, az, bx, bz):
    dx, dz = bx - ax, bz - az
    denom = dx * dx + dz * dz
    if denom == 0:
        return (px - ax) ** 2 + (pz - az) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / denom))
    qx, qz = ax + t * dx, az + t * dz
    return (px - qx) ** 2 + (pz - qz) ** 2


class PlacementConstraints:
    """Shared exclusion gates for flora generation."""
    def __init__(self, shells, patches, trees, river_pts=None, river_hw=None, route_pts=None, ortho_data=None):
        self.shells = shells
        self.patches = patches
        self.trees = trees
        self.river_pts = river_pts
        self.river_hw = river_hw
        self.route_pts = route_pts
        self.ortho_data = ortho_data

    def excluded(self, x, z) -> bool:
        # Pool apron exclusion.
        from yellowstone_python.thermal_features.pool_crust import in_apron, in_water
        for s in self.shells:
            if in_apron(x, z, s):
                return True
        # Water exclusion.
        for s in self.shells:
            if in_water(x, z, s):
                return True
        # River exclusion using segment distance.
        if self.river_pts is not None and len(self.river_pts) > 0 and self.river_hw is not None and len(self.river_hw) > 0:
            max_rhw = max(float(hw) for hw in self.river_hw)
            for a_idx in range(len(self.river_pts) - 1):
                a = self.river_pts[a_idx]
                b = self.river_pts[a_idx + 1]
                if _segment_dist_sq(x, z, float(a[0]), float(a[1]), float(b[0]), float(b[1])) < (max_rhw + 2.0) ** 2:
                    return True
        # Route exclusion using segment distance.
        if self.route_pts is not None and len(self.route_pts) > 0:
            for a_idx in range(len(self.route_pts) - 1):
                a = self.route_pts[a_idx]
                b = self.route_pts[a_idx + 1]
                if _segment_dist_sq(x, z, float(a[0]), float(a[1]), float(b[0]), float(b[1])) < (float(a[2]) + 2.0) ** 2:
                    return True
        # Existing trees exclusion.
        for tx, tz in self.trees:
            if (x - tx) ** 2 + (z - tz) ** 2 < 4.0 ** 2:
                return True
        # Barren ground exclusion if ortho configured.
        if self.ortho_data is not None:
            barren_state = self.ortho_data
            if barren_state[0] is not None and is_barren(barren_state[1], barren_state[2], barren_state[3], x, z):
                return True
        return False


def shuffled_cells(n_i: int, n_j: int, seed: int) -> list[tuple[int, int]]:
    """Grid cell indices (i, j) in a seeded random order, so a count cap samples the whole grid."""
    cells = [(i, j) for j in range(n_j) for i in range(n_i)]
    random.Random(f"{seed}:cell_order").shuffle(cells)
    return cells


def _habitat_mask():
    """World habitat mask as float RGB in [0, 1] on the terrain grid (row zero north)."""
    import numpy as _np
    from PIL import Image as _Image
    return _np.asarray(_Image.open(
        WORLD / "assets/textures/habitat_mask.png").convert("RGB")).astype(float) / 255.0


def is_mineral(mask, x: float, z: float) -> bool:
    """Mineral channel at (x, z) at or above MINERAL_PINE_MAX; points off the mask read mineral."""
    from yellowstone_python.land.vegetation import GRID, STEP
    mx, mz = int((x + HALF) / STEP), int((z + HALF) / STEP)
    if not (0 <= mx < GRID and 0 <= mz < GRID):
        return True
    return float(mask[mz, mx, 0]) >= MINERAL_PINE_MAX


def is_barren(im, H, W, x, z) -> bool:
    """Truly bare pale ground (bright AND greenless)."""
    green, light = green_light_at(im, H, W, x, z)
    return light > 0.55 and green < 0.15


def _broadphase_excluded(x, z, circles, shells) -> bool:
    """Shared broad-phase gate: circle test then exact shell apron."""
    for cx, cz, r in circles:
        if (x - cx) ** 2 + (z - cz) ** 2 < (r + 2.0) ** 2:
            for s in shells:
                if _in_apron(x, z, s):
                    return True
    return False


def forest_infill(count: int = 6000, seed: int = 301) -> tuple[list, list]:
    """Map-wide lodgepole infill from the habitat mask (forest = low meadow,
low mineral). 12 m grid, per-cell RNG, full gates. IDs are cell-stable."""
    import math as _math
    import random as _random
    import numpy as _np
    from PIL import Image as _Image
    from yellowstone_python.thermal_features.pool_crust import in_apron, in_water
    from yellowstone_python.land.vegetation import GUILDS, guild_suitability, load_terrain, moisture_at
    from yellowstone_python.land.vegetation import terrain_fns as _tfns

    from yellowstone_python.land.vegetation import GRID, HALF, STEP
    h = load_terrain(str(WORLD / "data" / "terrain.f32"))
    sample, slope = _tfns(h)
    mask = _np.asarray(_Image.open(WORLD / "assets/textures/habitat_mask.png").convert("RGB")).astype(float) / 255.0
    barren_state = (True,) + _ortho()
    gy, gx = _np.gradient(h, STEP)
    slope_grid = _np.degrees(_np.arctan(_np.hypot(gx, gy)))
    world = json.loads((WORLD / "data" / "world.json").read_text())
    shells = build_shells(world["pools"])
    patches = json.loads((WORLD / "data" / "ecosystem.json.pre-python").read_text())["patches"]
    place = json.loads((WORLD / "data" / "placements.json").read_text())
    taken = [(t["position"][0], t["position"][2]) for t in place["trees"]]
    ov0 = json.loads((WORLD / "data" / "placement_overrides.json").read_text())
    taken += [(r["position"][0], r["position"][2]) for r in ov0.get("add", []) if r.get("kind") == "pine"]
    try:
        from scipy.spatial import cKDTree as _KD
        tree = _KD(taken) if taken else None
    except ImportError:
        tree = None
    river_pts = []
    river_hw = []
    for r in world.get("rivers", []):
        hw = float(r.get("width", 22.0)) / 2.0 + 4.0
        for pt in r.get("points", []):
            river_pts.append((pt[0], pt[2]))
            river_hw.append(hw)
    river_pts = _np.asarray(river_pts, dtype=float).reshape(-1, 2) if river_pts else _np.zeros((0, 2))
    river_hw = _np.asarray(river_hw, dtype=float).reshape(-1) if river_hw else _np.zeros((0,))
    route_pts = []
    for r in world["routes"]:
        w = 8.0 if r["kind"] == "road" else 5.0
        for p in r["points"][::4]:
            route_pts.append((p[0], p[2], w))
    route_pts = _np.asarray(route_pts, dtype=float).reshape(-1, 3) if route_pts else _np.zeros((0, 3))

    circles = [(s["center_xz"][0], s["center_xz"][1], s["r_apron_m"])
               for s in shells]
    waters = [(s["center_xz"][0], s["center_xz"][1], s["max_radius_m"])
              for s in shells]
    accepted, log = [], []
    g = GUILDS["lodgepole_pine"]
    cell = 12.0
    n = math.ceil((2.0 * HALF) / cell)
    for i, j in shuffled_cells(n, n, seed):
        if len(accepted) >= count:
            break
        rng = _random.Random(f"{seed}:infill:{i}:{j}")
        x = -HALF + (i + 0.5) * cell + (rng.random() - 0.5) * 6.0
        z = -HALF + (j + 0.5) * cell + (rng.random() - 0.5) * 6.0
        mx, mz = int((x + HALF) / STEP), int((z + HALF) / STEP)
        if not (0 <= mx < GRID and 0 <= mz < GRID):
            continue
        if is_mineral(mask, x, z):
            continue
        if barren_state[0] is not None and is_barren(barren_state[1], barren_state[2], barren_state[3], x, z):
            continue
        if slope_grid[mz, mx] > g["slope_max_deg"]:
            continue
        if any((x - cx) ** 2 + (z - cz) ** 2 < (r + 2.0) ** 2
               for cx, cz, r in circles):
            if any(_in_apron(x, z, s) for s in shells):
                continue
        if any((x - cx) ** 2 + (z - cz) ** 2 < (r + 2.0) ** 2
               for cx, cz, r in waters):
            if any(in_water(x, z, s) for s in shells):
                continue
        river_excluded = False
        if len(river_pts) > 0 and len(river_hw) > 0:
            max_rhw = max(float(hw) for hw in river_hw)
            for a_idx in range(len(river_pts) - 1):
                a = river_pts[a_idx]
                b = river_pts[a_idx + 1]
                if _segment_dist_sq(x, z, float(a[0]), float(a[1]), float(b[0]), float(b[1])) < (max_rhw + 2.0) ** 2:
                    river_excluded = True
                    break
        if river_excluded:
            continue
        route_excluded = False
        if len(route_pts) > 0:
            for a_idx in range(len(route_pts) - 1):
                a = route_pts[a_idx]
                b = route_pts[a_idx + 1]
                if _segment_dist_sq(x, z, float(a[0]), float(a[1]), float(b[0]), float(b[1])) < (float(a[2]) + 2.0) ** 2:
                    route_excluded = True
                    break
        if route_excluded:
            continue
        if tree is not None and tree.query_ball_point([x, z], 4.0):
            continue
        mo = moisture_at(x, z, patches)
        hab = "dry_meadow" if mask[mz, mx, 1] > 0.5 else "forest_lodgepole"
        suit = guild_suitability("lodgepole_pine", hab,
                                 float(slope_grid[mz, mx]), mo, 0.7)
        if suit < 0.15:
            continue
        # Candidate spacing: no overlap with already-accepted same-guild candidates.
        too_close = False
        for prev in accepted:
            if prev.get("guild") == "lodgepole_pine":
                if (x - prev["x"]) ** 2 + (z - prev["z"]) ** 2 < 4.0 ** 2:
                    too_close = True
                    break
        if too_close:
            continue
        accepted.append({
            "stable_id": f"prop_infill_pine_{seed}_{i:03d}_{j:03d}",
            "guild": "lodgepole_pine", "habitat": hab,
            "x": round(x, 3), "y": round(float(sample(x, z)), 3),
            "z": round(z, 3), "slope_deg": round(float(slope_grid[mz, mx]), 1),
            "suitability": round(suit, 3),
            "yaw": round(rng.random() * 2 * _math.pi, 3),
            "scale": round(0.85 + rng.random() * 0.5, 3),
            "variation_key": rng.randint(0, 3),
            "evidence_class": "habitat-based authored candidate",
            "author_note": f"forest infill; mask+slope+mineral gated; seed {seed}",
        })
    return accepted, log


def override_id(record: dict) -> str | None:
    return record.get("id") or record.get("stable_id")


def _stage(records: list) -> int:
    ov_path = WORLD / "data" / "placement_overrides.json"
    ov = json.loads(ov_path.read_text())
    have = {override_id(r) for r in ov.get("add", []) if override_id(r) is not None}
    added = 0
    for rec in records:
        if override_id(rec) in have:
            continue
        ov.setdefault("add", []).append(to_override_record(rec, rec["y"]))
        added += 1
    write_json_atomic(ov_path, ov, indent=1)
    return added


def corridor_flora() -> tuple[list, list]:
    barren_state = (True,) + _ortho()
    """Grass verges and pine sentinels along each foot trail polyline.
    Grass 1.5 to 5.5 m off centerline; pines 10 to 28 m off, forest-gated. Stable route and pulse ids."""
    import math as _math
    import random as _random
    import numpy as _np
    from PIL import Image as _Image
    from yellowstone_python.thermal_features.pool_crust import in_apron, in_water
    from yellowstone_python.land.vegetation import GUILDS, guild_suitability, load_terrain, moisture_at
    from yellowstone_python.land.vegetation import GRID, HALF, STEP, terrain_fns as _tfns

    h = load_terrain(str(WORLD / "data" / "terrain.f32"))
    sample, slope = _tfns(h)
    mask = _np.asarray(_Image.open(WORLD / "assets/textures/habitat_mask.png").convert("RGB")).astype(float) / 255.0
    barren_state = (True,) + _ortho()
    gy, gx = _np.gradient(h, STEP)
    slope_grid = _np.degrees(_np.arctan(_np.hypot(gx, gy)))
    world = json.loads((WORLD / "data" / "world.json").read_text())
    shells = build_shells(world["pools"])
    circles = [(s["center_xz"][0], s["center_xz"][1], s["r_apron_m"]) for s in shells]
    patches = json.loads((WORLD / "data" / "ecosystem.json.pre-python").read_text())["patches"]
    place = json.loads((WORLD / "data" / "placements.json").read_text())
    taken = [(t["position"][0], t["position"][2]) for t in place["trees"]]
    ov0 = json.loads((WORLD / "data" / "placement_overrides.json").read_text())
    taken += [(r["position"][0], r["position"][2]) for r in ov0.get("add", []) if r.get("kind") == "pine"]
    try:
        from scipy.spatial import cKDTree as _KD
        tree = _KD(taken) if taken else None
    except ImportError:
        tree = None

    def clear_of_water(x, z):
        for cx, cz, r in circles:
            if (x - cx) ** 2 + (z - cz) ** 2 < (r + 2.0) ** 2:
                for s in shells:
                    if _in_apron(x, z, s) or in_water(x, z, s):
                        return False
        return True

    accepted = []
    for ri, r in enumerate(world["routes"]):
        if r["kind"] != "trail":
            continue
        pts = [(p[0], p[2]) for p in r["points"]]
        w = float(r["width"])
        for k in range(0, len(pts), 2):
            a = pts[max(0, k - 1)]; b = pts[min(len(pts) - 1, k + 1)]
            dx, dz = b[0] - a[0], b[1] - a[1]
            L = _math.hypot(dx, dz) or 1.0
            sx, sz = -dz / L, dx / L
            rng = _random.Random(f"corr:{ri}:{k}")
            for side in (-1.0, 1.0):
                gx_ = pts[k][0] + sx * side * (w / 2 + 1.5 + rng.random() * 4.0)
                gz_ = pts[k][1] + sz * side * (w / 2 + 1.5 + rng.random() * 4.0)
                if not clear_of_water(gx_, gz_):
                    continue
                mx, mz = int((gx_ + HALF) / STEP), int((gz_ + HALF) / STEP)
                if not (0 <= mx < GRID and 0 <= mz < GRID):
                    continue
                sl = float(slope(gx_, gz_))
                if sl > 20.0:
                    continue
                mo = moisture_at(gx_, gz_, patches)
                suit = guild_suitability("meadow_grass", "dry_meadow", sl, mo, 0.3)
                if suit < 0.05:
                    continue
                too_close = False
                for prev in accepted:
                    if prev.get("guild") == "meadow_grass":
                        if (gx_ - prev["x"]) ** 2 + (gz_ - prev["z"]) ** 2 < 2.0 ** 2:
                            too_close = True
                            break
                if too_close:
                    continue
                accepted.append({
                    "stable_id": f"prop_corr_grass_{ri:02d}_{k:04d}_{int(side)}",
                    "guild": "meadow_grass", "habitat": "dry_meadow",
                    "x": round(gx_, 3), "y": round(float(sample(gx_, gz_)), 3),
                    "z": round(gz_, 3), "slope_deg": round(sl, 1),
                    "suitability": round(suit, 3),
                    "yaw": round(rng.random() * 2 * _math.pi, 3),
                    "scale": round(1.6 + rng.random() * 0.8, 3),
                    "variation_key": rng.randint(0, 3),
                    "evidence_class": "trail-verge colonization",
                    "author_note": f"corridor verge; route {r['id']}",
                })
        for k in range(0, len(pts), 8):
            a = pts[max(0, k - 2)]; b = pts[min(len(pts) - 1, k + 2)]
            dx, dz = b[0] - a[0], b[1] - a[1]
            L = _math.hypot(dx, dz) or 1.0
            sx, sz = -dz / L, dx / L
            rng = _random.Random(f"corrp:{ri}:{k}")
            for side in (-1.0, 1.0):
                d = 10.0 + rng.random() * 18.0
                x = pts[k][0] + sx * side * d
                z = pts[k][1] + sz * side * d
                mx, mz = int((x + HALF) / STEP), int((z + HALF) / STEP)
                if not (0 <= mx < GRID and 0 <= mz < GRID):
                    continue
                if not (mask[mz, mx, 1] < 0.45 and mask[mz, mx, 0] < 0.35):
                    if is_barren(barren_state[1], barren_state[2], barren_state[3], x, z):
                        continue
                if float(slope_grid[mz, mx]) > 25.0:
                    continue
                if not clear_of_water(x, z):
                    continue
                if tree is not None and tree.query_ball_point([x, z], 4.0):
                    continue
                mo = moisture_at(x, z, patches)
                suit = guild_suitability("lodgepole_pine", "forest_lodgepole",
                                         float(slope_grid[mz, mx]), mo, 0.7)
                if suit < 0.15:
                    continue
                accepted.append({
                    "stable_id": f"prop_corr_pine_{ri:02d}_{k:04d}_{int(side)}",
                    "guild": "lodgepole_pine", "habitat": "forest_lodgepole",
                    "x": round(x, 3), "y": round(float(sample(x, z)), 3),
                    "z": round(z, 3),
                    "slope_deg": round(float(slope_grid[mz, mx]), 1),
                    "suitability": round(suit, 3),
                    "yaw": round(rng.random() * 2 * _math.pi, 3),
                    "scale": round(0.85 + rng.random() * 0.5, 3),
                    "variation_key": rng.randint(0, 3),
                    "evidence_class": "trail-corridor sentinel",
                    "author_note": f"corridor pine; route {r['id']}",
                })
    return accepted, []


def grove_planting(canopy_light_max: float = 0.40, spacing_m: float = 4.0,
                   count: int = 4000, seed: int = 401) -> tuple[list, list]:
    barren_state = (True,) + _ortho()
    """Closed-canopy groves where the NAIP aerial shows canopy.
    True stand spacing; slope, water, route, and existing gates apply; cell-stable ids."""
    import math as _math
    import random as _random
    import numpy as _np
    from PIL import Image as _Image
    from yellowstone_python.land.vegetation import guild_suitability, load_terrain, moisture_at
    from yellowstone_python.land.vegetation import GRID, HALF, STEP, terrain_fns as _tfns

    h = load_terrain(str(WORLD / "data" / "terrain.f32"))
    sample, slope = _tfns(h)
    barren_state = (True,) + _ortho()
    gy, gx = _np.gradient(h, STEP)
    slope_grid = _np.degrees(_np.arctan(_np.hypot(gx, gy)))
    ortho = _np.asarray(_Image.open(
        WORLD / "references" / "orthophoto.jpg").convert("RGB")).astype(float) / 255.0
    light = ortho.mean(2)
    mask = _habitat_mask()
    world = json.loads((WORLD / "data" / "world.json").read_text())
    shells = build_shells(world["pools"])
    circles = [(s["center_xz"][0], s["center_xz"][1], s["r_apron_m"]) for s in shells]
    patches = json.loads((WORLD / "data" / "ecosystem.json.pre-python").read_text())["patches"]
    place = json.loads((WORLD / "data" / "placements.json").read_text())
    taken = [(t["position"][0], t["position"][2]) for t in place["trees"]]
    ov0 = json.loads((WORLD / "data" / "placement_overrides.json").read_text())
    taken += [(r["position"][0], r["position"][2]) for r in ov0.get("add", []) if r.get("kind") == "pine"]
    try:
        from scipy.spatial import cKDTree as _KD
        tree = _KD(taken) if taken else None
    except ImportError:
        tree = None
    river_pts, river_hw = [], []
    for r in world["rivers"]:
        hw = float(r["width"]) / 2.0 + 4.0
        for pt in r["points"]:
            river_pts.append((pt[0], pt[2])); river_hw.append(hw)
    river_pts = (_np.asarray(river_pts, dtype=float).reshape(-1, 2)
                 if river_pts else _np.zeros((0, 2)))
    river_hw = (_np.asarray(river_hw, dtype=float).reshape(-1)
                if river_hw else _np.zeros((0,)))
    route_pts = []
    for r in world["routes"]:
        wdt = 8.0 if r["kind"] == "road" else 5.0
        for pt in r["points"][::4]:
            route_pts.append((pt[0], pt[2], wdt))
    route_pts = (_np.asarray(route_pts, dtype=float).reshape(-1, 3)
                 if route_pts else _np.zeros((0, 3)))

    accepted = []
    cell = 12.0
    n = math.ceil((2.0 * HALF) / cell)
    OH, OW = light.shape[:2]
    for i, j in shuffled_cells(n, n, seed):
        if len(accepted) >= count:
            break
        x0, z0 = -HALF + i * cell, -HALF + j * cell
        mx, mz = int((x0 + HALF) / STEP), int((z0 + HALF) / STEP)
        if not (0 <= mx < GRID and 0 <= mz < GRID):
            continue
        if float(slope_grid[mz, mx]) > 28.0:
            continue
        rng = _random.Random(f"{seed}:grove:{i}:{j}")
        for a in range(3):
            for b in range(3):
                if len(accepted) >= count:
                    break
                x = x0 + (a + 0.5) * spacing_m + (rng.random() - 0.5) * 2.0
                z = z0 + (b + 0.5) * spacing_m + (rng.random() - 0.5) * 2.0
                if is_mineral(mask, x, z):
                    continue
                # Canopy brightness read at the candidate point.
                ox = int((x + HALF) / (2.0 * HALF) * (OW - 1))
                oz = int((z + HALF) / (2.0 * HALF) * (OH - 1))
                if 0 <= ox < OW and 0 <= oz < OH:
                    if light[oz, ox] > canopy_light_max:
                        continue
                if any((x - cx) ** 2 + (z - cz) ** 2 < (rr + 2.0) ** 2
                       for cx, cz, rr in circles):
                    continue
                # River exclusion.
                river_excluded = False
                if len(river_pts) > 0 and len(river_hw) > 0:
                    max_rhw = max(float(hw) for hw in river_hw)
                    for a_idx in range(len(river_pts) - 1):
                        a_pt = river_pts[a_idx]
                        b_pt = river_pts[a_idx + 1]
                        if _segment_dist_sq(x, z, float(a_pt[0]), float(a_pt[1]), float(b_pt[0]), float(b_pt[1])) < (max_rhw + 2.0) ** 2:
                            river_excluded = True
                            break
                if river_excluded:
                    continue
                # Route exclusion.
                route_excluded = False
                if len(route_pts) > 0:
                    for a_idx in range(len(route_pts) - 1):
                        a_pt = route_pts[a_idx]
                        b_pt = route_pts[a_idx + 1]
                        if _segment_dist_sq(x, z, float(a_pt[0]), float(a_pt[1]), float(b_pt[0]), float(b_pt[1])) < (float(a_pt[2]) + 2.0) ** 2:
                            route_excluded = True
                            break
                if route_excluded:
                    continue
                if tree is not None and tree.query_ball_point([x, z], 3.0):
                    continue
                young = rng.random() < 0.25
                sc = round((0.45 + rng.random() * 0.3) if young else (0.85 + rng.random() * 0.5), 3)
                # Candidate spacing: avoid overlap with already-accepted same-guild.
                too_close = False
                for prev in accepted:
                    if prev.get("guild") == "lodgepole_pine":
                        if (x - prev["x"]) ** 2 + (z - prev["z"]) ** 2 < 4.0 ** 2:
                            too_close = True
                            break
                if too_close:
                    continue
                mo = moisture_at(x, z, patches)
                suit = guild_suitability("lodgepole_pine", "forest_lodgepole",
                                         float(slope_grid[mz, mx]), mo, 0.7)
                if suit < 0.15:
                    continue
                accepted.append({
                    "stable_id": f"prop_grove_{seed}_{i:03d}_{j:03d}_{a}{b}",
                    "guild": "lodgepole_pine", "habitat": "forest_lodgepole",
                    "x": round(x, 3), "y": round(float(sample(x, z)), 3),
                    "z": round(z, 3),
                    "slope_deg": round(float(slope_grid[mz, mx]), 1),
                    "suitability": round(suit, 3),
                    "yaw": round(rng.random() * 2 * _math.pi, 3),
                    "scale": sc,
                    "variation_key": rng.randint(0, 3),
                    "evidence_class": "canopy-observed placement (NAIP 2022)",
                    "author_note": "grove fill where aerial shows canopy; recruitment understory included",
                })
    return accepted, []


def deck_viewshed_groves(cx: float = -252.0, cz: float = 159.0,
                         r0: float = 100.0, r1: float = 400.0,
                         spacing_m: float = 4.0, count: int = 2500,
                         seed: int = 501) -> tuple[list, list]:
    """Art-directed density ring around the overlook deck."""
    import math as _math
    import random as _random
    import numpy as _np
    from yellowstone_python.land.vegetation import guild_suitability
    from yellowstone_python.land.vegetation import GRID, STEP, terrain_fns as _tfns
    barren_state = (True,) + _ortho()
    mask = _habitat_mask()

    h = load_terrain(str(WORLD / "data" / "terrain.f32"))
    sample, slope = _tfns(h)
    gy, gx = _np.gradient(h, STEP)
    slope_grid = _np.degrees(_np.arctan(_np.hypot(gx, gy)))
    world = json.loads((WORLD / "data" / "world.json").read_text())
    shells = build_shells(world["pools"])
    circles = [(s["center_xz"][0], s["center_xz"][1], s["r_apron_m"]) for s in shells]
    patches = json.loads((WORLD / "data" / "ecosystem.json.pre-python").read_text())["patches"]
    place = json.loads((WORLD / "data" / "placements.json").read_text())
    taken = [(t["position"][0], t["position"][2]) for t in place["trees"]]
    ov0 = json.loads((WORLD / "data" / "placement_overrides.json").read_text())
    taken += [(r["position"][0], r["position"][2]) for r in ov0.get("add", []) if r.get("kind") == "pine"]
    try:
        from scipy.spatial import cKDTree as _KD
        tree = _KD(taken) if taken else None
    except ImportError:
        tree = None
    river_pts, river_hw = [], []
    for r in world["rivers"]:
        hw = float(r["width"]) / 2.0 + 4.0
        for pt in r["points"]:
            river_pts.append((pt[0], pt[2])); river_hw.append(hw)
    river_pts = (_np.asarray(river_pts, dtype=float).reshape(-1, 2)
                 if river_pts else _np.zeros((0, 2)))
    river_hw = (_np.asarray(river_hw, dtype=float).reshape(-1)
                if river_hw else _np.zeros((0,)))
    route_pts = []
    for r in world["routes"]:
        wdt = 10.0 if r["kind"] == "road" else 6.0
        for pt in r["points"][::4]:
            route_pts.append((pt[0], pt[2], wdt))
    route_pts = (_np.asarray(route_pts, dtype=float).reshape(-1, 3)
                 if route_pts else _np.zeros((0, 3)))

    accepted = []
    step = 8.0
    n = int(2 * r1 / step)
    for i, j in shuffled_cells(n + 1, n + 1, seed):
        if len(accepted) >= count:
            break
        rng = _random.Random(f"{seed}:deck:{i}:{j}")
        x = cx - r1 + i * step + (rng.random() - 0.5) * 4.0
        z = cz - r1 + j * step + (rng.random() - 0.5) * 4.0
        d = _math.hypot(x - cx, z - cz)
        if not (r0 <= d <= r1):
            continue
        mx, mz = int((x + HALF) / STEP), int((z + HALF) / STEP)
        if not (0 <= mx < GRID and 0 <= mz < GRID):
            continue
        if is_mineral(mask, x, z):
            continue
        if float(slope_grid[mz, mx]) > 28.0:
            continue
        if any((x - ax) ** 2 + (z - az) ** 2 < (rr + 2.0) ** 2
               for ax, az, rr in circles):
            continue
        river_excluded = False
        if len(river_pts) > 0 and len(river_hw) > 0:
            max_rhw = max(float(hw) for hw in river_hw)
            for a_idx in range(len(river_pts) - 1):
                a_pt = river_pts[a_idx]
                b_pt = river_pts[a_idx + 1]
                if _segment_dist_sq(x, z, float(a_pt[0]), float(a_pt[1]), float(b_pt[0]), float(b_pt[1])) < (max_rhw + 2.0) ** 2:
                    river_excluded = True
                    break
        if river_excluded:
            continue
        route_excluded = False
        if len(route_pts) > 0:
            for a_idx in range(len(route_pts) - 1):
                a_pt = route_pts[a_idx]
                b_pt = route_pts[a_idx + 1]
                if _segment_dist_sq(x, z, float(a_pt[0]), float(a_pt[1]), float(b_pt[0]), float(b_pt[1])) < (float(a_pt[2]) + 2.0) ** 2:
                    route_excluded = True
                    break
        if route_excluded:
            continue
        if tree is not None and tree.query_ball_point([x, z], 3.0):
            continue
        if barren_state[0] is not None and is_barren(barren_state[1], barren_state[2], barren_state[3], x, z):
            continue
        mo = moisture_at(x, z, patches)
        suit = guild_suitability("lodgepole_pine", "forest_edge",
                                 float(slope_grid[mz, mx]), mo, 0.6)
        if suit < 0.08:
            continue
        young = rng.random() < 0.25
        # Candidate spacing.
        too_close = False
        for prev in accepted:
            if prev.get("guild") == "lodgepole_pine":
                if (x - prev["x"]) ** 2 + (z - prev["z"]) ** 2 < 4.0 ** 2:
                    too_close = True
                    break
        if too_close:
            continue
        accepted.append({
            "stable_id": f"prop_deck_{seed}_{i:03d}_{j:03d}",
            "guild": "lodgepole_pine", "habitat": "forest_edge",
            "x": round(x, 3), "y": round(float(sample(x, z)), 3),
            "z": round(z, 3),
            "slope_deg": round(float(slope_grid[mz, mx]), 1),
            "suitability": round(suit, 3),
            "yaw": round(rng.random() * 2 * _math.pi, 3),
            "scale": round((0.45 + rng.random() * 0.3) if young else (0.85 + rng.random() * 0.5), 3),
            "variation_key": rng.randint(0, 3),
            "evidence_class": "art-directed density enhancement (NOT observed cover)",
            "author_note": "deck viewshed ring; explicit aesthetic fill",
        })
    return accepted, []




def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.gen_flora import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
