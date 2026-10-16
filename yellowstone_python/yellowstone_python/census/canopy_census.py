"""Canopy census: detect trees from NAIP imagery and emit stable records.
CLI --qa runs a mechanical self-check."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.checks import positive

import json
import math
from pathlib import Path

import numpy as np

from yellowstone_python.common.provenance import default_world_root

DETAIL_PATH = str(default_world_root() / "references/midway_orthophoto_detail.jpg")
DETAIL_HALF = 640.0  # local meters covered: [-640, 640]
PX_M = 1.25 / 2.0  # 0.625 m per pixel


def load_detail(path: str = DETAIL_PATH) -> np.ndarray:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    return np.asarray(im).astype(float) / 255.0


def crown_mask(sig, exg_min: float = 0.05, crown_dark_max: float = 0.55):
    return (
        (sig["exg"] > exg_min)
        & (sig["light"] < crown_dark_max)
        & (~sig["water"])
    )


def vegetation_signals(rgb: np.ndarray) -> dict:
    """ExG greenness, brightness, blue-water flag. All float32 arrays."""
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    exg = 2 * g - r - b
    light = (r + g + b) / 3.0
    return {"exg": exg.astype(np.float32),
            "light": light.astype(np.float32),
            "water": ((b - r > 0.12) & (light < 0.55))}


def detect(rgb: np.ndarray, *, exg_min: float = 0.05,
           crown_dark_max: float = 0.55, min_px: int = 3,
           peak_distance_m: float = 2.0) -> list:
    """Return tree records with pixel coords. Deterministic (no RNG)."""
    from scipy import ndimage
    sig = vegetation_signals(rgb)
    H, W = sig["exg"].shape
    # Candidate crown pixels: green and dark (conifer crowns; grass is lighter).
    crown = crown_mask(sig, exg_min=exg_min, crown_dark_max=crown_dark_max)
    labeled, ncomp = ndimage.label(crown)
    sizes = ndimage.sum(crown, labeled, range(1, ncomp + 1))
    # Peaks: local maxima of ExG inside crown mask, >= 2 m apart.
    dist_px = max(2, int(round(peak_distance_m / PX_M)))
    local_max = (ndimage.maximum_filter(sig["exg"], size=2 * dist_px + 1)
                 == sig["exg"]) & crown
    # Collapse flat-top plateaus: each connected max-component yields one peak at its centroid.
    plat, _ = ndimage.label(local_max)
    peak_iz, peak_ix = [], []
    for region in ndimage.find_objects(plat):
        if region is None:
            continue
        ys, xs = np.nonzero(plat[region])
        peak_iz.append(int(round(ys.mean())) + region[0].start)
        peak_ix.append(int(round(xs.mean())) + region[1].start)
    peak_iz = np.array(peak_iz, dtype=int)
    peak_ix = np.array(peak_ix, dtype=int)
    if len(peak_iz) == 0:
        return []
    peak_comp = labeled[peak_iz, peak_ix]
    order = np.argsort(-sig["exg"][peak_iz, peak_ix], kind="stable")
    taken = np.zeros(len(peak_ix), dtype=bool)
    records = []
    for idx in order:
        if taken[idx]:
            continue
        # Suppress weaker neighbors within the peak distance in a single strength-ordered pass.
        d2 = (peak_ix - peak_ix[idx]) ** 2 + (peak_iz - peak_iz[idx]) ** 2
        taken[(d2 < dist_px ** 2)] = True
        comp = int(peak_comp[idx])
        area_px = float(sizes[comp - 1]) if comp > 0 else float(min_px)
        npeaks = int((peak_comp == comp).sum()) if comp > 0 else 1
        share = max(area_px / max(1, npeaks), float(min_px))
        crown_r_m = math.sqrt(share / math.pi) * PX_M
        records.append({
            "ix": int(peak_ix[idx]), "iz": int(peak_iz[idx]),
            "exg": round(float(sig["exg"][peak_iz[idx], peak_ix[idx]]), 4),
            "crown_r_m": round(min(crown_r_m, 6.0), 2),
            "confidence": ("high" if area_px >= 12 else
                           "medium" if area_px >= 6 else "low"),
        })
    records.sort(key=lambda r: (r["iz"], r["ix"]))
    return records


def load_pool_rings(world_path: str | None = None) -> list:
    """Mapped water outlines (local x,z ring vertices)."""
    import json
    world_path = world_path or str(default_world_root() / "data/world.json")
    with open(world_path, encoding="utf-8") as f:
        world = json.load(f)
    return [[(float(a), float(b)) for a, b in pool.get("ring", [])]
            for pool in world.get("pools", []) if pool.get("ring")]


def _in_poly(x: float, z: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, zi = ring[i]
        xj, zj = ring[j]
        if ((zi > z) != (zj > z)) and (x < (xj - xi) * (z - zi) / (zj - zi) + xi):
            inside = not inside
        j = i
    return inside


def _point_to_segment_distance_sq(px: float, pz: float,
                                  ax: float, az: float,
                                  bx: float, bz: float) -> float:
    """Squared distance from (px,pz) to the segment ab."""
    dx, dz = bx - ax, bz - az
    denom = dx * dx + dz * dz
    if denom == 0.0:
        return (px - ax) ** 2 + (pz - az) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / denom))
    qx, qz = ax + t * dx, az + t * dz
    return (px - qx) ** 2 + (pz - qz) ** 2


def exclude_pool_rims(records: list, margin_m: float = 5.0) -> tuple[list, int]:
    """Drop detections inside mapped water plus a true point-to-segment margin."""
    rings = load_pool_rings()
    boxes = []
    for ring in rings:
        xs = [p[0] for p in ring]
        zs = [p[1] for p in ring]
        boxes.append((min(xs) - margin_m, min(zs) - margin_m,
                      max(xs) + margin_m, max(zs) + margin_m))
    margin_sq = margin_m ** 2
    kept, dropped = [], 0
    for r in records:
        bad = False
        for (x0, z0, x1, z1), ring in zip(boxes, rings):
            if x0 <= r["x"] <= x1 and z0 <= r["z"] <= z1:
                if _in_poly(r["x"], r["z"], ring):
                    bad = True
                    break
                # Edge distance: scan every ring segment so points near a straight run are also caught.
                nv = len(ring)
                for i in range(nv):
                    ax_, az_ = ring[i]
                    bx_, bz_ = ring[(i + 1) % nv]
                    if _point_to_segment_distance_sq(
                            r["x"], r["z"], ax_, az_, bx_, bz_) < margin_sq:
                        bad = True
                        break
                if bad:
                    break
        if bad:
            dropped += 1
        else:
            kept.append(r)
    return kept, dropped


def to_world(records: list, width: int = 2048, height: int = 2048,
             *, extent=None) -> list:
    """Pixel records to stable local-meter records; id derived from pixel coordinates."""
    out = []
    x0, z0, x1, z1 = extent or (-DETAIL_HALF, -DETAIL_HALF, DETAIL_HALF, DETAIL_HALF)
    for r in records:
        x = x0 + (r["ix"] + 0.5) / width * (x1 - x0)
        z = z0 + (r["iz"] + 0.5) / height * (z1 - z0)
        lidar = r.get("method") == "lidar_lmf"
        record = {
            "stable_id": f"census_{'lidar_' if lidar else ''}{r['ix']:04d}_{r['iz']:04d}",
            "x": round(x, 2), "z": round(z, 2),
            "crown_r_m": r["crown_r_m"], "peak_exg": r.get("exg"),
            "confidence": r["confidence"],
            "evidence_class": ("USGS first-return dominant crown detection; blind validation unavailable"
                               if lidar else "NAIP-2022-07-19 canopy detection (unreviewed)"),
        }
        if lidar:
            record.update({key: r[key] for key in ("method", "height_m", "crown_area_m2",
                                                   "splitting_basis", "ix", "iz")})
            record["footprint_scope"] = r.get("footprint_scope", "watershed footprint")
        out.append(record)
    return out


def render_overlay(rgb: np.ndarray, records: list, path: str,
                   width: int = 2048, height: int = 2048) -> str:
    """Red dots on imagery for human review (not a placement map)."""
    from PIL import Image, ImageDraw
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for r in records:
        x, y = r["ix"], r["iz"]
        rad = max(2, int(r["crown_r_m"] / PX_M))
        d.ellipse([x - rad, y - rad, x + rad, y + rad], outline=(255, 30, 30),
                  width=1)
        d.point((x, y), fill=(255, 255, 0))
    img.save(path)
    return path


def _coord(record: object, axis: int) -> float:
    """Record x/z: dict key or tuple index."""
    if isinstance(record, dict):
        return float(record["x"] if axis == 0 else record["z"])
    return float(record[axis])


def density_stats(records: list, zones: dict) -> dict:
    """Trees/ha per named zone."""
    out = {}
    for name, spec in zones.items():
        ((kind, val),) = spec.items()
        if kind == "circle":
            cx, cz, rr = val
            if rr <= 0:
                raise ValueError(f"circle zone {name}: radius {rr} must be > 0")
            inside = [r for r in records
                      if math.hypot(_coord(r, 0) - cx, _coord(r, 1) - cz) <= rr]
            area_ha = math.pi * rr ** 2 / 1e4
        elif kind == "ring":
            cx, cz, r0, r1 = val
            if r0 <= 0 or r1 <= 0 or r1 <= r0:
                raise ValueError(f"ring zone {name}: r0={r0}, r1={r1} must be positive with r1 > r0")
            inside = [r for r in records
                      if r0 < math.hypot(_coord(r, 0) - cx,
                                         _coord(r, 1) - cz) <= r1]
            area_ha = math.pi * (r1 ** 2 - r0 ** 2) / 1e4
        elif kind == "box":
            x0, z0, x1, z1 = val
            if x1 <= x0 or z1 <= z0:
                raise ValueError(f"box zone {name}: zero-area box")
            inside = [r for r in records
                      if x0 <= _coord(r, 0) <= x1 and z0 <= _coord(r, 1) <= z1]
            area_ha = abs(x1 - x0) * abs(z1 - z0) / 1e4
        else:
            raise ValueError(f"unknown zone type {kind!r} for zone {name}")
        out[name] = {"n": len(inside), "area_ha": round(area_ha, 2),
                     "trees_per_ha": round(len(inside) / area_ha, 1)}
    return out


QA_CONFIDENCE = ("high", "medium", "low")
QA_SPLITTING = ("peak", "area_topup", "lidar_watershed")
QA_CROWN_CAP_M = 6.0  # matches the cap in detect()
QA_TREE_FIELDS = ("stable_id", "x", "z", "crown_r_m", "peak_exg",
                   "confidence", "evidence_class")


def qa_census(doc: dict) -> list:
    """Mechanical self-check of a census document. Returns failure strings
(empty means pass). No image or human data needed."""
    failures = []
    if doc.get("schema") != "yellowstone.canopy_census.v1":
        failures.append(f"schema: expected yellowstone.canopy_census.v1, "
                        f"found {doc.get('schema')!r}")
        return failures
    trees = doc.get("trees", [])
    if not isinstance(trees, list):
        failures.append(f"trees: must be a list, got {type(trees).__name__}")
        return failures
    n_declared = doc.get("n")
    if not isinstance(n_declared, int) or isinstance(n_declared, bool):
        failures.append(f"n: must be an int, got {type(n_declared).__name__}")
    elif n_declared != len(trees):
        failures.append(f"count: n={n_declared} != len(trees)={len(trees)}")
    # Extent for coord-bounds check, falls back to DETAIL_HALF defaults.
    extent = doc.get("source", {}).get("extent_m",
                                        [-DETAIL_HALF, -DETAIL_HALF,
                                         DETAIL_HALF, DETAIL_HALF])
    try:
        x0, z0, x1, z1 = [float(v) for v in extent]
    except (TypeError, ValueError):
        x0, z0, x1, z1 = (-DETAIL_HALF, -DETAIL_HALF,
                          DETAIL_HALF, DETAIL_HALF)
    seen_ids: set = set()
    seen_xy: set = set()
    for t in trees:
        if not isinstance(t, dict):
            failures.append(f"trees: entry {t!r} is not a mapping")
            continue
        sid = t.get("stable_id", "?")
        if sid in seen_ids:
            failures.append(f"stable_id: duplicate {sid!r}")
        else:
            seen_ids.add(sid)
        xkey = (round(float(t.get("x", math.nan)), 2),
                round(float(t.get("z", math.nan)), 2)) \
            if isinstance(t.get("x"), (int, float)) \
            and isinstance(t.get("z"), (int, float)) else None
        if xkey is not None:
            if xkey in seen_xy:
                failures.append(f"coord: duplicate position {xkey} ({sid})")
            else:
                seen_xy.add(xkey)
            if not (x0 <= xkey[0] <= x1 and z0 <= xkey[1] <= z1):
                failures.append(
                    f"coord: {sid} ({xkey[0]}, {xkey[1]}) outside extent "
                    f"[{x0}, {z0}, {x1}, {z1}]")
        peak = t.get("peak_exg")
        if peak is not None:
            try:
                peak_f = float(peak)
                if not math.isfinite(peak_f) or peak_f < -1.0 or peak_f > 2.0:
                    failures.append(
                        f"peak_exg: {sid} value {peak_f} outside [-1, 2]")
            except (TypeError, ValueError):
                failures.append(f"peak_exg: {sid} value {peak!r} invalid")
    for t in trees:
        if not isinstance(t, dict):
            continue
        sid = t.get("stable_id", "?")
        missing = [f for f in QA_TREE_FIELDS if f not in t]
        if missing:
            failures.append(f"fields: {sid} missing {missing}")
            continue
        if t["confidence"] not in QA_CONFIDENCE:
            failures.append(f"confidence: {sid} has {t['confidence']!r}")
        try:
            crown_r = float(t.get("crown_r_m", 0))
            if not math.isfinite(crown_r):
                failures.append(f"cap: {sid} crown_r_m={t.get('crown_r_m')!r} nonfinite")
            elif crown_r > QA_CROWN_CAP_M and t.get("method") != "lidar_lmf":
                failures.append(f"cap: {sid} crown_r_m={crown_r} exceeds "
                                f"{QA_CROWN_CAP_M}")
            elif crown_r < 0:
                failures.append(f"cap: {sid} crown_r_m={crown_r} negative")
        except (TypeError, ValueError):
            failures.append(f"cap: {sid} crown_r_m={t.get('crown_r_m')!r} invalid")
        if "splitting_basis" in t and t["splitting_basis"] not in QA_SPLITTING:
            failures.append(f"splitting_basis: {sid} has "
                            f"{t['splitting_basis']!r}")
    density = doc.get("density", {})
    for zone, stats in density.items():
        if stats.get("n", 0) > len(trees):
            failures.append(f"density: zone {zone} n={stats.get('n')} "
                            f"exceeds total {len(trees)}")
    return failures






def calibrate_lone_trees(rgb: np.ndarray, isolation_m: float = 10.0) -> dict:
    """Measure single isolated crowns: components with no neighbor centroid within isolation_m."""
    from scipy import ndimage
    sig = vegetation_signals(rgb)
    crown = crown_mask(sig)
    labeled, ncomp = ndimage.label(crown)
    if ncomp == 0:
        raise ValueError("no crown components found")
    sizes = ndimage.sum(crown, labeled, range(1, ncomp + 1))
    cents = ndimage.center_of_mass(crown, labeled, range(1, ncomp + 1))
    cents = np.array(cents)  # (iz, ix)
    lone = []
    try:
        from scipy.spatial import cKDTree
        _dists, _ = cKDTree(cents).query(cents, k=2)
        _nearest_m = _dists[:, 1] * PX_M
    except ImportError:  # brute-force fallback
        _nearest_m = []
        for _i, (_z, _x) in enumerate(cents):
            _d2 = ((cents[:, 0] - _z) ** 2 + (cents[:, 1] - _x) ** 2)
            _d2[_i] = np.inf
            _nearest_m.append(_d2.min() ** 0.5 * PX_M)
        _nearest_m = np.array(_nearest_m)
    for _i, _d in enumerate(_nearest_m):
        if _d >= isolation_m:
            lone.append(float(sizes[_i]))
    if len(lone) < 10:
        raise ValueError(f"only {len(lone)} lone trees; cannot calibrate")
    lone = np.array(lone)
    return {"n_lone": len(lone),
            "median_area_px": round(float(np.median(lone)), 1),
            "p95_area_px": round(float(np.percentile(lone, 95)), 1),
            "median_crown_r_m": round(float(math.sqrt(np.median(lone) / math.pi) * PX_M), 2)}


def detect_v2(rgb: np.ndarray, calibration: dict | None = None, **kw) -> list:
    """Peaks plus area-based top-up: blobs larger than lone trees are split to their area-implied stem."""
    from scipy import ndimage
    if calibration is None:
        calibration = calibrate_lone_trees(rgb)
    base = detect(rgb, **kw)
    sig = vegetation_signals(rgb)
    dist_px = max(2, int(round(kw.get("peak_distance_m", 2.0) / PX_M)))
    taken = {(r["ix"], r["iz"]) for r in base}
    for r in base:
        r["splitting_basis"] = "peak"
    median_area = calibration["median_area_px"]
    # Secondary pass: tighter maxima grid for area-implied extra stems.
    fine = max(1, dist_px // 2)
    local_max = (ndimage.maximum_filter(sig["exg"], size=2 * fine + 1)
                 == sig["exg"])
    crown = crown_mask(sig, exg_min=kw.get("exg_min", 0.05),
                        crown_dark_max=kw.get("crown_dark_max", 0.55))
    labeled, _ = ndimage.label(crown)
    sizes = dict(zip(*np.unique(labeled, return_counts=True)))
    sizes.pop(0, None)
    # Per-component expected stems from lone-tree ruler.
    comp_of = {}
    for r in base:
        comp_of.setdefault(int(labeled[r["iz"], r["ix"]]), []).append(r)
    extra = []
    for comp, members in comp_of.items():
        area = float(sizes.get(comp, 0))
        expected = max(len(members), int(round(area / median_area)))
        need = expected - len(members)
        if need <= 0:
            continue
        ys, xs = np.nonzero((labeled == comp) & local_max)
        scored = sorted(zip(sig["exg"][ys, xs].tolist(), xs.tolist(), ys.tolist()),
                        reverse=True)
        added = 0
        for _, x, y in scored:
            if added >= need:
                break
            if any((x - tx) ** 2 + (y - ty) ** 2 < fine ** 2 for tx, ty in taken):
                continue
            taken.add((x, y))
            extra.append({"ix": int(x), "iz": int(y),
                          "exg": round(float(sig["exg"][y, x]), 4),
                          "crown_r_m": calibration["median_crown_r_m"],
                          "confidence": "medium",
                          "splitting_basis": "area_topup"})
            added += 1
    out = base + extra
    out.sort(key=lambda r: (r["iz"], r["ix"]))
    return out


LIDAR_WINDOW = {"slope": 0.06, "minimum_radius_m": 1.0, "maximum_radius_m": 3.0,
                "status": "authored", "source": "numerical search-window choice; height-only lodgepole allometry unavailable"}


def lidar_window_radius(height_m, *, slope=0.06, minimum_radius_m=1.0,
                        maximum_radius_m=3.0):
    """Return the authored height-dependent local-maximum search radius in meters."""
    slope = positive("window_slope", slope)
    minimum_radius_m = positive("minimum_radius_m", minimum_radius_m)
    maximum_radius_m = positive("maximum_radius_m", maximum_radius_m)
    if maximum_radius_m < minimum_radius_m:
        raise ValueError("maximum search radius must be at least the minimum radius")
    heights = np.asarray(height_m)
    if heights.dtype.kind not in "iuf" or not np.isfinite(heights).all():
        raise ValueError("height_m must contain finite numbers")
    return np.clip(heights * slope, minimum_radius_m, maximum_radius_m)


def detect_lidar(canopy_height: np.ndarray, *, pixel_size_m=0.5,
                 minimum_height_m=2.0, window=None, return_labels=False):
    """Segment dominant crown cores where watershed and nearest-peak ownership agree."""
    from scipy import ndimage
    pixel_size_m = positive("pixel_size_m", pixel_size_m)
    minimum_height_m = positive("minimum_height_m", minimum_height_m)
    chm = np.asarray(canopy_height)
    if chm.ndim != 2 or chm.dtype.kind not in "iuf" or np.isinf(chm).any():
        raise ValueError("canopy height must be a numeric 2-D array with finite or NoData cells")
    model = dict(LIDAR_WINDOW, **(window or {}))
    valid = np.isfinite(chm)
    weights = ndimage.gaussian_filter(valid.astype(np.float32), sigma=1, truncate=1)
    numerator = ndimage.gaussian_filter(np.where(valid, chm, 0).astype(np.float32),
                                       sigma=1, truncate=1)
    smooth = np.divide(numerator, weights, out=np.zeros_like(numerator), where=weights > 0)
    smooth[~valid] = -np.inf
    forest = valid & (chm >= minimum_height_m)
    radii = lidar_window_radius(np.where(valid, smooth, 0), slope=model["slope"],
        minimum_radius_m=model["minimum_radius_m"], maximum_radius_m=model["maximum_radius_m"])
    radius_px = np.ceil(radii / pixel_size_m).astype(np.int16)
    maxima = np.zeros(chm.shape, dtype=bool)
    for radius in np.unique(radius_px[forest]):
        maxima |= ((radius_px == radius) & forest & (smooth >= minimum_height_m)
                   & (ndimage.maximum_filter(smooth, size=2 * int(radius) + 1) == smooth))
    plateaus, _ = ndimage.label(maxima)
    candidates = []
    for region in ndimage.find_objects(plateaus):
        if region is None:
            continue
        ys, xs = np.nonzero(plateaus[region])
        ys, xs = ys + region[0].start, xs + region[1].start
        index = np.argmin((ys - ys.mean()) ** 2 + (xs - xs.mean()) ** 2)
        y, x = int(ys[index]), int(xs[index])
        candidates.append((float(smooth[y, x]), y, x, float(radii[y, x])))
    candidates.sort(key=lambda r: (-r[0], r[1], r[2]))
    maximum_radius = float(model["maximum_radius_m"])
    bins, selected = {}, []
    for height, y, x, radius in candidates:
        bx, by = math.floor(x * pixel_size_m / maximum_radius), math.floor(y * pixel_size_m / maximum_radius)
        neighbors = [p for dx in [-1, 0, 1] for dy in [-1, 0, 1]
                     for p in bins.get((bx + dx, by + dy), [])]
        if any(((x - px) * pixel_size_m) ** 2 + ((y - py) * pixel_size_m) ** 2
               < max(radius, pr) ** 2 for py, px, pr in neighbors):
            continue
        selected.append((y, x, radius))
        bins.setdefault((bx, by), []).append((y, x, radius))
    selected.sort()
    labels = np.zeros(chm.shape, dtype=np.int32)
    if not selected:
        return ([], labels) if return_labels else []
    components, _ = ndimage.label(forest)
    seeded = {int(components[y, x]) for y, x, _ in selected}
    supported_forest = forest & np.isin(components, list(seeded))
    markers = np.zeros(chm.shape, dtype=np.int32)
    for marker, (y, x, _) in enumerate(selected, 1):
        markers[y, x] = marker
    maximum_height = float(np.max(smooth[supported_forest]))
    height_span = max(maximum_height - minimum_height_m, 1e-6)
    topography = np.full(chm.shape, 65535, dtype=np.uint16)
    topography[supported_forest] = np.clip(
        (maximum_height - smooth[supported_forest]) / height_span * 65534,
        0, 65534).astype(np.uint16)
    labels = ndimage.watershed_ift(topography, markers)
    labels[~supported_forest] = 0
    nearest = ndimage.distance_transform_edt(markers == 0, return_distances=False,
                                            return_indices=True)
    nearest_owner = markers[nearest[0], nearest[1]]
    labels[labels != nearest_owner] = 0
    areas = np.bincount(labels.ravel(), minlength=len(selected) + 1) * pixel_size_m ** 2
    peaks = ndimage.maximum(np.where(valid, chm, -np.inf), labels,
                            index=np.arange(1, len(selected) + 1))
    records = [{"ix": x, "iz": y, "height_m": round(float(peaks[index]), 3),
                "crown_area_m2": round(float(areas[index + 1]), 3),
                "crown_r_m": round(math.sqrt(areas[index + 1] / math.pi), 3),
                "confidence": "medium", "method": "lidar_lmf",
                "splitting_basis": "lidar_watershed",
                "footprint_scope": "conservative watershed/nearest-peak consensus core; full crown unknown"}
               for index, (y, x, _) in enumerate(selected)]
    return (records, labels) if return_labels else records


def canopy_coverage_field(canopy_height, trees, *, extent, pixel_size_m=0.5,
                           cell_size_m=10.0, minimum_height_m=2.0, excluded_mask=None) -> dict:
    """Aggregate observed canopy cover, height and dominant-count lower bounds per cell."""
    pixel_size_m = positive("pixel_size_m", pixel_size_m)
    cell_size_m = positive("cell_size_m", cell_size_m)
    minimum_height_m = positive("minimum_height_m", minimum_height_m)
    ratio = cell_size_m / pixel_size_m
    if not math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-9):
        raise ValueError("coverage-cell size must be an integer multiple of raster spacing")
    block = round(ratio)
    chm = np.asarray(canopy_height)
    if chm.ndim != 2 or chm.dtype.kind not in "iuf" or np.isinf(chm).any():
        raise ValueError("canopy height must be a numeric 2-D array with finite or NoData cells")
    excluded = np.zeros(chm.shape, dtype=bool) if excluded_mask is None else np.asarray(excluded_mask)
    if excluded.dtype.kind != "b" or excluded.shape != chm.shape:
        raise ValueError("canopy exclusions must be a boolean mask matching the raster")
    x0, z0, x1, z1 = extent
    if not (math.isclose((x1 - x0) / pixel_size_m, chm.shape[1])
            and math.isclose((z1 - z0) / pixel_size_m, chm.shape[0])):
        raise ValueError("coverage extent does not match the raster shape and spacing")
    count = {}
    for tree in trees:
        ix = math.floor((tree["x"] - x0) / cell_size_m)
        iz = math.floor((tree["z"] - z0) / cell_size_m)
        count[(ix, iz)] = count.get((ix, iz), 0) + 1
    cells = []
    for row in range(0, chm.shape[0], block):
        for column in range(0, chm.shape[1], block):
            tile = chm[row:row + block, column:column + block]
            valid = np.isfinite(tile)
            raw_above = valid & (tile >= minimum_height_m)
            excluded_tile = excluded[row:row + block, column:column + block]
            canopy = raw_above & ~excluded_tile
            ix, iz = column // block, row // block
            area = tile.size * pixel_size_m ** 2
            dominant = count.get((ix, iz), 0)
            cells.append({"id": f"lidar_cell_{ix:03d}_{iz:03d}", "ix": ix, "iz": iz,
                "bounds_xz_m": [x0 + column * pixel_size_m, z0 + row * pixel_size_m,
                                  x0 + (column + tile.shape[1]) * pixel_size_m,
                                  z0 + (row + tile.shape[0]) * pixel_size_m],
                "area_m2": area, "valid_fraction": float(valid.mean()),
                "missing_fraction": float((~valid).mean()),
                "mapped_nonvegetation_fraction": float(excluded_tile.mean()),
                "raw_above_height_threshold_fraction": float(raw_above.sum() / valid.sum()) if valid.any() else None,
                "canopy_cover_fraction": float(canopy.sum() / valid.sum()) if valid.any() else None,
                "observed_canopy_area_m2": float(canopy.sum() * pixel_size_m ** 2),
                "mean_canopy_height_m": float(tile[canopy].mean()) if canopy.any() else None,
                "dominant_count_lower_bound": dominant,
                "dominant_density_lower_bound_per_ha": dominant * 10000.0 / area,
                "total_stem_density_per_ha": None, "subcanopy_stem_density_per_ha": None})
    return {"schema": "yellowstone.canopy_coverage.v1", "status": "derived_not_field_validated",
            "extent_m": list(extent), "cell_size_m": cell_size_m, "pixel_size_m": pixel_size_m,
            "canopy_height_threshold_m": minimum_height_m, "cells": cells,
            "count_scope": "canopy-dominant detections; total and subcanopy stem density unknown",
            "total_density_model": {"availability": "unavailable",
                "reason": "Turner permanent plots lack measured canopy cover and crown width"}}


def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.canopy_census import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
