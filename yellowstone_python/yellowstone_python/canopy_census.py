"""Canopy census: detect trees from NAIP imagery and produce stable records. CLI flags: --qa for mechanical self-check."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from .common.provenance import default_world_root

DETAIL_PATH = str(default_world_root() / "references/midway_orthophoto_detail.jpg")
DETAIL_HALF = 640.0  # local metres covered: [-640, 640]
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
    # Candidate crown pixels: green AND dark (conifer crowns, not grass).
    crown = (sig["exg"] > exg_min) & (sig["light"] < crown_dark_max) & (~sig["water"])
    labeled, ncomp = ndimage.label(crown)
    sizes = ndimage.sum(crown, labeled, range(1, ncomp + 1))
    # Peaks: local maxima of ExG inside crown mask, >= 2 m apart.
    dist_px = max(2, int(round(peak_distance_m / PX_M)))
    local_max = (ndimage.maximum_filter(sig["exg"], size=2 * dist_px + 1)
                 == sig["exg"]) & crown
    # Collapse flat-top plateaus: each connected max-component yields one
    # peak at its centroid (uniform discs would otherwise count per pixel).
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
        # Suppress weaker neighbors within the peak distance (same pass,
        # strength-ordered, so suppression cannot shift later acceptances).
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


def exclude_pool_rims(records: list, margin_m: float = 5.0) -> tuple[list, int]:
    """Drop detections inside mapped water + margin (rim artifacts, not
    stems). Returns (kept, n_dropped)."""
    rings = load_pool_rings()
    boxes = []
    for ring in rings:
        xs = [p[0] for p in ring]
        zs = [p[1] for p in ring]
        boxes.append((min(xs) - margin_m, min(zs) - margin_m,
                      max(xs) + margin_m, max(zs) + margin_m))
    kept, dropped = [], 0
    for r in records:
        bad = False
        for (x0, z0, x1, z1), ring in zip(boxes, rings):
            if x0 <= r["x"] <= x1 and z0 <= r["z"] <= z1:
                # margin test: inside ring, or within margin of any vertex
                if _in_poly(r["x"], r["z"], ring):
                    bad = True
                    break
                if min((r["x"] - vx) ** 2 + (r["z"] - vz) ** 2
                       for vx, vz in ring) < margin_m ** 2:
                    bad = True
                    break
        if bad:
            dropped += 1
        else:
            kept.append(r)
    return kept, dropped


def to_world(records: list, width: int = 2048, height: int = 2048) -> list:
    """Pixel records -> stable local-metre records (id from pixel, stable)."""
    out = []
    for r in records:
        x = (r["ix"] + 0.5) / width * (2 * DETAIL_HALF) - DETAIL_HALF
        z = (r["iz"] + 0.5) / height * (2 * DETAIL_HALF) - DETAIL_HALF
        out.append({
            "stable_id": f"census_{r['ix']:04d}_{r['iz']:04d}",
            "x": round(x, 2), "z": round(z, 2),
            "crown_r_m": r["crown_r_m"], "peak_exg": r["exg"],
            "confidence": r["confidence"],
            "evidence_class": "NAIP-2022-07-19 canopy detection (unreviewed)",
        })
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
    """Trees/ha per named zone. Zone spec: {"circle": (cx, cz, r)} or
    {"ring": (cx, cz, r0, r1)} or {"box": (x0, z0, x1, z1)}.
    Records may be dicts ({x,z,...}) or (x, z) tuples."""
    out = {}
    for name, spec in zones.items():
        ((kind, val),) = spec.items()
        if kind == "circle":
            cx, cz, rr = val
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
        out[name] = {"n": len(inside), "area_ha": round(area_ha, 2),
                     "trees_per_ha": round(len(inside) / area_ha, 1)}
    return out


QA_CONFIDENCE = ("high", "medium", "low")
QA_SPLITTING = ("peak", "area_topup")
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
    if doc.get("n") != len(trees):
        failures.append(f"count: n={doc.get('n')} != len(trees)={len(trees)}")
    for t in trees:
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
            elif crown_r > QA_CROWN_CAP_M:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", default=DETAIL_PATH)
    ap.add_argument("--out", default="derived/census.json")
    ap.add_argument("--overlay", default=None)
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--qa", default=None,
                    help="self-check a census JSON file and exit (no imaging)")
    args = ap.parse_args()

    if args.qa is not None:
        try:
            doc = json.loads(Path(args.qa).read_text())
        except (OSError, ValueError) as exc:
            print(f"qa-unreadable: {args.qa}: {exc}")
            return 1
        failures = qa_census(doc)
        for f in failures:
            print(f"qa-rule: {f}")
        print(f"qa: {len(doc.get('trees', []))} trees, "
              f"{len(failures)} violation(s)")
        return 1 if failures else 0

    rgb = load_detail(args.detail)
    records = to_world(detect(rgb))
    records, dropped_rim = exclude_pool_rims(records)
    doc = {"schema": "yellowstone.canopy_census.v1",
           "source": {"image": args.detail, "acquired": "2022-07-19",
                      "agency": "USDA NAIP via USGS",
                      "extent_m": [-DETAIL_HALF, -DETAIL_HALF,
                                   DETAIL_HALF, DETAIL_HALF],
                      "px_m": PX_M},
           "status": "detection unreviewed; not a placement authority",
           "n": len(records),
           "dropped_rim": dropped_rim,
           "trees": records}
    if args.stats:
        doc["density"] = density_stats(records, {
            "spring_0_50m": {"circle": (-94.7, -10.6, 50.0)},
            "apron_50_100m": {"ring": (-94.7, -10.6, 50.0, 100.0)},
            "transition_100_200m": {"ring": (-94.7, -10.6, 100.0, 200.0)},
            "outwash_200_400m": {"ring": (-94.7, -10.6, 200.0, 400.0)},
            "overlook_knoll_r120": {"circle": (-252.0, 159.0, 120.0)},
            "detail_full": {"box": (-640.0, -640.0, 640.0, 640.0)},
        })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc))
    print(f"census: {len(records)} trees -> {out}")
    if args.overlay:
        render_overlay(rgb, [dict(r, ix=int(r["stable_id"].split("_")[1]),
                             iz=int(r["stable_id"].split("_")[2]))
                            for r in records], args.overlay)
        print(f"overlay -> {args.overlay}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def calibrate_lone_trees(rgb: np.ndarray, isolation_m: float = 10.0) -> dict:
    """Measure single isolated crowns: components with no neighbor centroid within isolation_m."""
    from scipy import ndimage
    sig = vegetation_signals(rgb)
    crown = (sig["exg"] > 0.05) & (sig["light"] < 0.55) & (~sig["water"])
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
    """Peaks plus area-based top-up: blobs larger than lone trees are split to their area-implied stem count. Each record carries splitting_basis: peak | area_topup."""
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
