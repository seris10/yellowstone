"""pool_crust: authored pool shells and aprons for Midway thermal pools.
Builds crater, shelf, rim, apron, and outflow around the mapped water outline."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic

import json
import math
import os
from functools import lru_cache

try:
    import shapely  # noqa: F401
    _HAS_SHAPELY = True
except ImportError:
    _HAS_SHAPELY = False

HALF = 2048.0  # world half-extent, meters (matches coords.py)

# Outflow channel links keyed by the stable pool source_id from world.json.
OUTFLOW_CHANNELS = {
    "1030": "authored_excelsior_outflow_01",
}

# Authored shell recipe per named pool: multipliers/offsets on r_water.
RECIPES = {
    "Grand Prismatic Spring": {"shelf": 1.18, "rim_m": 7.0, "apron_m": 30.0,
                               "depth_center_m": 37.0, "shelf_depth_m": 1.2,
                               "t_edge_c": 42.0, "outflow_bearing_deg": 100.0},
    "Excelsior Geyser Crater": {"shelf": 1.25, "rim_m": 6.0, "apron_m": 45.0,
                                "depth_center_m": 8.0, "shelf_depth_m": 0.8,
                                "t_edge_c": 45.0, "outflow_bearing_deg": 95.0},
    "Turquoise Pool": {"shelf": 1.2, "rim_m": 3.0, "apron_m": 12.0,
                       "depth_center_m": 6.0, "shelf_depth_m": 0.6,
                       "t_edge_c": 40.0, "outflow_bearing_deg": 120.0},
    "Opal Pool": {"shelf": 1.2, "rim_m": 3.0, "apron_m": 12.0,
                  "depth_center_m": 4.0, "shelf_depth_m": 0.5,
                  "t_edge_c": 40.0, "outflow_bearing_deg": 120.0},
}
DEFAULT_RECIPE = {"shelf": 1.2, "rim_m": 4.0, "apron_m": 15.0,
                  "depth_center_m": 3.0, "shelf_depth_m": 0.6,
                  "t_edge_c": 38.0, "outflow_bearing_deg": 90.0}

# Base bands store (r_water fraction, color, meaning); make_ramp_stops() adjusts per-pool copies.
COLOR_STOPS = [
    (0.00, "#0b3d91", "deep hot center (illustrative)"),
    (0.35, "#1b7f79", "teal transition (illustrative)"),
    (0.60, "#4d9b47", "green microbial margin (illustrative)"),
    (0.80, "#c9a227", "yellow/orange mat edge (illustrative)"),
    (1.00, "#b8a88a", "wet sinter rim (illustrative)"),
    (1.30, "#8d8577", "dry sinter apron (illustrative)"),
]


def _hex(rgb_hex: str) -> tuple:
    h = rgb_hex.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c1: tuple, c2: tuple, f: float) -> tuple:
    return tuple(int(a + (b - a) * f) for a, b in zip(c1, c2))


def make_ramp_stops(shell: dict) -> dict:
    """Per-pool pigment stops; returns {"stops": [...], "ramp_params": {...}}.
Fractions clamped to [0, 1.3]; monotonicity checked by validate_ramp_stops()."""
    depth_f = min(1.0, float(shell.get("depth_center_m", 5.0)) / 40.0)
    grad = (float(shell["t_center_c"]) - float(shell["t_edge_c"])) / max(
        1.0, float(shell["t_center_c"]))
    grad_f = min(1.0, max(0.0, grad * 2.0))
    stops = []
    for frac, color, meaning in COLOR_STOPS:
        rgb = _hex(color)
        if frac == 0.00:
            rgb = _mix(rgb, (4, 26, 63), depth_f)
        adjusted = frac + (0.06 * grad_f if frac in (0.35, 0.60) else 0.0)
        adjusted = min(1.3, max(0.0, adjusted))
        stops.append({"fraction": adjusted,
                      "color": "#%02x%02x%02x" % rgb, "meaning": meaning})
    return {"stops": stops,
            "ramp_params": {"depth_f": round(depth_f, 3),
                            "gradient_f": round(grad_f, 3)}}


def validate_ramp_stops(stops: list) -> None:
    """Fractions must sit in [0, 1.3] and strictly increase."""
    previous = -1.0
    for s in stops:
        f = float(s["fraction"])
        if not math.isfinite(f) or f < 0.0 or f > 1.3:
            raise ValueError(f"ramp stop fraction {f} outside [0, 1.3]")
        if f <= previous:
            raise ValueError("ramp stop fractions must strictly increase")
        previous = f


def render_ramp(shell: dict, path: str, w: int = 256) -> str:
    """Horizontal gradient x=0 center to x=1 rim. Matches water.gdshader
band_ramp sampling (shader passes 1-side, i.e. 0 at center)."""
    from PIL import Image
    w = int(w)
    if w < 2:
        raise ValueError(f"ramp width must be >= 2, got {w}")
    stops = make_ramp_stops(shell)["stops"]
    validate_ramp_stops(stops)
    pts = sorted(((s["fraction"] / 1.3, _hex(s["color"]))) for s in stops)
    img = Image.new("RGB", (w, 1))
    px = img.load()
    for ix in range(w):
        f = ix / (w - 1)
        for (f0, c0), (f1, c1) in zip(pts, pts[1:]):
            if f <= f1 or (f1 == pts[-1][0]):
                t = 0.0 if f1 <= f0 else (f - f0) / (f1 - f0)
                px[ix, 0] = _mix(c0, c1, min(1.0, max(0.0, t)))
                break
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(path)
    return path


def r_water_from_area(area_m2: float) -> float:
    area_m2 = float(area_m2)
    if not math.isfinite(area_m2) or area_m2 <= 0:
        raise ValueError(f"pool area must be finite and > 0, got {area_m2}")
    return math.sqrt(area_m2 / math.pi)


def _validate_ring(ring) -> list:
    """Return the ring as finite [x, z] pairs.
Three distinct points required; consecutive duplicates dropped."""
    if ring is None or len(list(ring)) < 3:
        raise ValueError("pool ring requires at least three points")
    cleaned = []
    for p in ring:
        if len(p) < 2:
            raise ValueError("ring point must contain x and z")
        x, z = float(p[0]), float(p[1])
        if not (math.isfinite(x) and math.isfinite(z)):
            raise ValueError("ring coordinates must be finite")
        if not cleaned or math.hypot(x - cleaned[-1][0], z - cleaned[-1][1]) > 0:
            cleaned.append([x, z])
    if len(cleaned) < 3:
        raise ValueError("pool ring has fewer than three distinct points")
    if _perimeter(cleaned) <= 0:
        raise ValueError("pool ring has zero perimeter")
    return cleaned


def _ring_area(ring: list) -> float:
    """Shoelace polygon area in square meters."""
    total = 0.0
    for (x0, z0), (x1, z1) in zip(ring, ring[1:] + ring[:1]):
        total += x0 * z1 - x1 * z0
    return abs(total) / 2.0


def _perimeter(ring: list) -> float:
    pts = [(float(p[0]), float(p[1])) for p in ring]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(pts, pts[1:] + pts[:1]))


def point_in_ring(x: float, z: float, ring: list) -> bool:
    """Ray-cast point-in-polygon on the mapped outline."""
    inside = False
    pts = [(float(p[0]), float(p[1])) for p in ring]
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, zi = pts[i]
        xj, zj = pts[j]
        if ((zi > z) != (zj > z)) and (x < (xj - xi) * (z - zi) / (zj - zi) + xi):
            inside = not inside
        j = i
    return inside


def buffer_method() -> str:
    """Label for the buffering implementation in use."""
    return ("shapely_minkowski_buffer" if _HAS_SHAPELY
            else "radial_expansion_from_centroid_approximation_not_guaranteed")


def buffered_ring(ring: list, center: tuple, margin_m: float) -> list:
    """Outline expanded by an absolute margin in meters.
Minkowski buffer with shapely; vertex-radial fallback otherwise (see buffer_method())."""
    margin_m = float(margin_m)
    if not math.isfinite(margin_m) or margin_m < 0:
        raise ValueError("margin must be finite and >= 0")
    if margin_m == 0:
        return [[float(p[0]), float(p[1])] for p in ring]
    if _HAS_SHAPELY:
        from shapely.geometry import Polygon
        poly = Polygon([(float(p[0]), float(p[1])) for p in ring])
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_valid:
            raise ValueError("ring cannot be buffered even after repair")
        return [list(pt) for pt in poly.buffer(margin_m).exterior.coords]
    cx, cz = center
    out = []
    for p in ring:
        vx, vz = float(p[0]) - cx, float(p[1]) - cz
        d = math.hypot(vx, vz) or 1.0
        out.append([cx + vx * (1.0 + margin_m / d),
                    cz + vz * (1.0 + margin_m / d)])
    return out


def radial_temp(r: float, r_water: float, t_center: float,
                t_edge: float) -> float:
    """Quadratic falloff reaching t_edge at the water edge.
Beyond the edge the value stays t_edge."""
    r_water = float(r_water)
    if not math.isfinite(r_water) or r_water <= 0:
        raise ValueError(f"r_water must be finite and > 0, got {r_water}")
    f = max(0.0, 1.0 - (float(r) / r_water) ** 2)
    return float(t_edge + (t_center - t_edge) * f)


def depth_at(r: float, r_water: float, depth_center_m: float,
             shelf_depth_m: float, shelf_mult: float = 1.18) -> float:
    """Illustrative crater profile: deep bowl to shallow shelf to 0 at rim."""
    r_water = float(r_water)
    depth_center_m = float(depth_center_m)
    shelf_depth_m = float(shelf_depth_m)
    shelf_mult = float(shelf_mult)
    if not math.isfinite(r_water) or r_water <= 0:
        raise ValueError(f"r_water must be finite and > 0, got {r_water}")
    if not math.isfinite(shelf_mult) or shelf_mult <= 1:
        raise ValueError(f"shelf_mult must be > 1, got {shelf_mult}")
    for name, value in (("depth_center_m", depth_center_m),
                        ("shelf_depth_m", shelf_depth_m)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and >= 0, got {value}")
    r = float(r)
    if r <= r_water:
        return float(depth_center_m * (1.0 - (r / r_water) ** 2)
                     + shelf_depth_m * (r / r_water) ** 2)
    if r <= r_water * shelf_mult:
        f = (r - r_water) / (r_water * (shelf_mult - 1.0))
        return float(shelf_depth_m * (1.0 - f))
    return 0.0


def shell_for_pool(pool: dict) -> dict:
    """Author one pool shell. Never alters the mapped outline."""
    name = pool.get("name", pool.get("id", "unnamed"))
    recipe = RECIPES.get(name, DEFAULT_RECIPE)
    for key in ("shelf", "rim_m", "apron_m", "depth_center_m",
                "shelf_depth_m", "t_edge_c"):
        if float(recipe[key]) <= 0:
            raise ValueError(f"recipe {name}: {key} must be > 0")
    if float(recipe["shelf"]) <= 1.0:
        raise ValueError(f"recipe {name}: shelf multiplier must be > 1")
    center = pool["center"]
    if len(center) < 3 or not all(math.isfinite(float(v)) for v in center[:3]):
        raise ValueError("pool center must hold three finite coordinates")
    cx, _, cz = center
    ring = _validate_ring(pool.get("ring", []))
    rw = r_water_from_area(float(pool.get("area_m2", 100.0)))
    max_r = max((math.hypot(vx - cx, vz - cz) for vx, vz in ring), default=rw)
    perim = _perimeter(ring) if ring else 2 * math.pi * rw
    circularity = (4 * math.pi * float(pool.get("area_m2", 0.0)) / perim ** 2
                   if perim > 0 else 1.0)
    # Declared area versus shoelace area; shell radii come from the declared area.
    mapped_area = _ring_area(ring) if ring else math.pi * rw * rw
    area_disagreement_pct = (abs(mapped_area
                                 - float(pool.get("area_m2", mapped_area)))
                             / max(1e-9, float(pool.get("area_m2", 1.0)))
                             * 100.0)
    t_center = float(pool.get("temperature_c", 60.0))
    r_shelf = max(rw * recipe["shelf"], max_r + 2.0)
    # Keep radii strictly growing even when an additive rim would land inside the shelf.
    r_rim = max(rw + recipe["rim_m"], r_shelf + 2.0)
    r_apron = max(rw + recipe["apron_m"], r_rim + 5.0, max_r + 8.0)
    apron_margin = max(0.0, r_apron - max_r)
    shell = {
        "id": pool["id"], "source_id": pool.get("source_id"), "name": name,
        "center_xz": [float(cx), float(cz)],
        "ring": ring,  # mapped outline carried verbatim; never resampled
        "outline_circularity": round(circularity, 3),
        "max_radius_m": round(max_r, 2),
        "mapped_area_m2": round(mapped_area, 1),
        "area_disagreement_pct": round(area_disagreement_pct, 2),
        "apron_buffer_method": buffer_method(),
        "apron_margin_m": round(apron_margin, 2),
        "r_water_m": rw, "r_shelf_m": r_shelf,
        "r_rim_m": r_rim, "r_apron_m": r_apron,
        "t_center_c": t_center, "t_edge_c": recipe["t_edge_c"],
        "depth_center_m": recipe["depth_center_m"],
        "shelf_depth_m": recipe["shelf_depth_m"],
        "outflow_bearing_deg": recipe["outflow_bearing_deg"],
        "outflow_channel": OUTFLOW_CHANNELS.get(str(pool.get("source_id"))),
        "substrate": "siliceous_sinter_illustrative",
        "status": ("authored shell; mapped outline preserved; depths and "
                   "colors illustrative, not bathymetry or calibrated pigment"),
    }
    ramp = make_ramp_stops(shell)
    shell["color_stops"] = ramp["stops"]
    shell["ramp_params"] = ramp["ramp_params"]
    validate_ramp_stops(shell["color_stops"])
    return shell


def build_all(pools: list) -> list:
    return [shell_for_pool(p) for p in pools]


def _dist(x: float, z: float, shell: dict) -> float:
    cx, cz = shell["center_xz"]
    return math.hypot(x - cx, z - cz)


def in_water(x: float, z: float, shell: dict) -> bool:
    """Exact mapped-polygon test (circle only if the ring is missing)."""
    if shell.get("ring"):
        return point_in_ring(x, z, shell["ring"])
    return _dist(x, z, shell) <= shell["r_water_m"]


@lru_cache(maxsize=256)
def _apron_ring(ring: tuple, center: tuple, margin_m: float,
                shapely_enabled: bool) -> tuple:
    """Cache immutable buffered outlines by complete geometry and method."""
    return tuple(tuple(p) for p in buffered_ring(ring, center, margin_m))


def in_apron(x: float, z: float, shell: dict) -> bool:
    """Buffered-outline test; circle fallback preserves conservatism."""
    if shell.get("ring"):
        cx, cz = shell["center_xz"]
        ring = tuple((float(p[0]), float(p[1])) for p in shell["ring"])
        buf = _apron_ring(ring, (float(cx), float(cz)),
                          float(shell.get("apron_margin_m", 0.0)),
                          _HAS_SHAPELY)
        return point_in_ring(x, z, buf)
    return _dist(x, z, shell) <= shell["r_apron_m"]


def exclusion_violations(points: list, shells: list) -> list:
    """Forest-type points that fall inside any apron (masking failure)."""
    bad = []
    for p in points:
        x, z = p["x"], p["z"]
        for s in shells:
            if in_apron(x, z, s):
                bad.append({"point_id": p.get("id"), "pool": s["id"]})
                break
    return bad


def render_apron_mask(shells: list, size: int, path: str) -> str:
    """World-extent eligibility mask: 0=ok, 255=hydrothermal apron.
Draws buffered mapped outlines (exact); circles only as fallback."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (size, size), 0)
    dr = ImageDraw.Draw(img)

    def px(x):
        return (x + HALF) / (2 * HALF) * (size - 1)
    for s in shells:
        cx, cz = s["center_xz"]
        if s.get("ring"):
            buf = buffered_ring(s["ring"], (cx, cz),
                                s.get("apron_margin_m", 0.0))
            dr.polygon([(px(x), px(z)) for x, z in buf], fill=255)
        else:
            r = s["r_apron_m"] / (2 * HALF) * (size - 1)
            dr.ellipse([px(cx) - r, px(cz) - r, px(cx) + r, px(cz) + r],
                       fill=255)
    img.save(path)
    return path


def render_apron_tiles(shells: list, outdir: str, size: int = 128) -> list:
    """Per-pool apron tiles (about 1 to 2 m per pixel) for pool inspection.
World mask pixels are about 16 m; small pools use these local tiles."""
    from PIL import Image, ImageDraw
    import os
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for s in shells:
        cx, cz = s["center_xz"]
        span = s["r_apron_m"] * 1.2
        img = Image.new("L", (size, size), 0)
        dr = ImageDraw.Draw(img)

        def px(x, z):
            return ((x - (cx - span)) / (2 * span) * (size - 1),
                    (z - (cz - span)) / (2 * span) * (size - 1))
        if s.get("ring"):
            buf = buffered_ring(s["ring"], (cx, cz),
                                s.get("apron_margin_m", 0.0))
            dr.polygon([px(x, z) for x, z in buf], fill=255)
            dr.polygon([px(x, z) for x, z in s["ring"]], fill=200)
        p = os.path.join(outdir, f"apron_{s['id']}.png")
        img.save(p)
        paths.append(p)
    return paths


def render_cross_section(shell: dict, path: str, w: int = 640,
                         h: int = 240) -> str:
    """Side-view diagram plate for field notes (field-notes key)."""
    from PIL import Image, ImageDraw
    w, h = int(w), int(h)
    if w < 2 or h < 2:
        raise ValueError("cross-section plate must be at least 2x2 pixels")
    img = Image.new("RGB", (w, h), (16, 22, 19))
    dr = ImageDraw.Draw(img)
    rw, rs, rr, ra = (shell["r_water_m"], shell["r_shelf_m"],
                      shell["r_rim_m"], shell["r_apron_m"])
    sm = rs / max(1e-6, rw)  # shell's own shelf ratio, never a default
    dc = shell["depth_center_m"]
    span = max(ra * 1.15, 1.0)
    depth_span = max(dc * 1.25, 1.0)

    def X(r):
        return w / 2 + (r / span) * (w / 2 - 20)

    def Y(d):
        return 40 + (d / depth_span) * (h - 90)
    # water surface + bowl + shelf + rim + apron
    dr.line([(X(-rw), Y(0)), (X(rw), Y(0))], fill=(70, 130, 180), width=3)
    pts = []
    n = 48
    for i in range(n + 1):
        r = -rs + 2 * rs * i / n
        pts.append((X(r), Y(depth_at(abs(r), rw, dc, shell["shelf_depth_m"],
                                     shelf_mult=sm))))
    dr.line(pts, fill=(150, 120, 80), width=2)
    for rx, label in ((rw, "water"), (rs, "shelf"), (rr, "rim"), (ra, "apron")):
        dr.line([(X(rx), 30), (X(rx), h - 30)], fill=(90, 90, 90), width=1)
        dr.text((X(rx) + 3, h - 28), label, fill=(200, 200, 190))
    dr.text((12, 8), f"{shell['name']} - authored section (illustrative, not survey)",
             fill=(214, 200, 143))
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(path)
    # Plate radii are circular equivalents; the image's sidecar labels this radial-diagram geometry.
    meta = {
        "schema": "yellowstone.pool_cross_section_meta.v1",
        "pool_id": shell["id"],
        "section_geometry": "radial",
        "radii_basis": "circular_equivalent_from_area_m2",
        "represents_mapped_outline": False,
        "depths_basis": "authored_illustrative_fill_not_bathymetry",
        "radii_m": {"water": rw, "shelf": rs, "rim": rr, "apron": ra},
        "status": shell.get("status", ""),
    }
    write_json_atomic(f"{path}.meta.json", meta, indent=2)
    return path
