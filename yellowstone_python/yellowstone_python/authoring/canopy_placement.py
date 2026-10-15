"""Observed dominant-crown placement and mapped nonvegetation exclusions."""
from __future__ import annotations

from collections import Counter
import copy
import math
from pathlib import Path
import random
import shutil

import numpy as np

from yellowstone_python.common.checks import fraction, positive
from yellowstone_python.common.io import sha256_file, write_json_atomic


def exclusion_masks(world, habitat, shape, extent, spacing):
    """Rasterize individual mapped features without connecting separate polylines."""
    from affine import Affine
    from rasterio.features import rasterize
    from shapely.geometry import LineString, Polygon
    from yellowstone_python.land.vegetation import HALF, STEP
    from yellowstone_python.thermal_features.pool_crust import build_all
    x0, z0, _, _ = extent
    transform = Affine(spacing, 0, x0, 0, spacing, z0)
    def burned(geometries):
        if not geometries:
            return np.zeros(shape, dtype=bool)
        return rasterize([(g, 1) for g in geometries], out_shape=shape,
                         transform=transform, dtype="uint8").astype(bool)
    xs = ((x0 + (np.arange(shape[1]) + .5) * spacing + HALF) / STEP).astype(int)
    zs = ((z0 + (np.arange(shape[0]) + .5) * spacing + HALF) / STEP).astype(int)
    if (xs.min() < 0 or zs.min() < 0 or xs.max() >= habitat.shape[1]
            or zs.max() >= habitat.shape[0]):
        raise ValueError("canopy raster extends beyond the mapped habitat mask")
    mineral = habitat[zs[:, None], xs[None, :], 0] >= .35
    shells = build_all(world["pools"])
    pool_shapes = [Polygon(shell["ring"]).buffer(shell["apron_margin_m"])
                   for shell in shells]
    rivers, buffered_rivers, routes = [], [], []
    for feature in world.get("rivers", []):
        points = [(p[0], p[2]) for p in feature.get("points", [])]
        if len(points) > 1:
            line = LineString(points)
            width = float(feature.get("width", 22)) / 2
            rivers.append(line.buffer(width))
            buffered_rivers.append(line.buffer(width + 6))
    for feature in world.get("routes", []):
        points = [(p[0], p[2]) for p in feature.get("points", [])]
        if len(points) > 1:
            clearance = 10 if feature.get("kind") == "road" else 7
            routes.append(LineString(points).buffer(clearance))
    return {"mineral": mineral, "pool_apron": burned(pool_shapes),
            "river": burned(rivers), "river_clearance": burned(buffered_rivers),
            "route_clearance": burned(routes)}


def filter_crowns(trees, masks):
    """Reject detected centers on mapped exclusion pixels and retain reason counts."""
    accepted, reasons = [], Counter()
    for tree in trees:
        reason = next((name for name, mask in masks.items()
                       if mask[tree["iz"], tree["ix"]]), None)
        if reason:
            reasons[reason] += 1
        else:
            accepted.append(tree)
    return accepted, dict(reasons)


def placement_records(trees, sample_ground, treemap=None):
    """Place detected crown centers; transferred donor dimensions never replace heights."""
    from yellowstone_python.observations.treemap import profile_at_local, sample_tree_reference
    records, missing = [], Counter()
    for tree in trees:
        rng = random.Random(tree["stable_id"])
        row = None
        if treemap:
            profile = profile_at_local(treemap, tree["x"], tree["z"])
            if profile:
                row = sample_tree_reference(profile, rng, species_symbol="PICO",
                                            measured_height_m=tree["height_m"])
        record = {"id": tree["stable_id"], "stable_id": tree["stable_id"], "kind": "pine",
                  "position": [tree["x"], float(sample_ground(tree["x"], tree["z"])), tree["z"]],
                  "yaw": rng.random() * math.tau, "variant": rng.randrange(5), "scale": 1.0,
                  "height_m": tree["height_m"], "crown_radius_m": tree["crown_r_m"],
                  "crown_area_m2": tree["crown_area_m2"],
                  "source_class": "derived_not_field_validated",
                  "height_source": "USGS first-return surface height above matched DEM",
                  "crown_source": tree.get("footprint_scope", "watershed footprint") + "; equivalent-area radius",
                  "species_source": "authored lodgepole render identity; LiDAR does not identify species",
                  "review": {"decision": "accept", "basis": "observed dominant peak outside mapped exclusions"}}
        if row:
            record["fia_reference"] = row
            if row.get("dbh_cm") is not None:
                record["dbh_m"] = positive("donor_dbh_cm", row["dbh_cm"]) / 100
                record["dbh_source"] = "transferred TreeMap donor; local error unknown"
            else:
                missing["donor_dbh_unavailable"] += 1
            ratio = fraction("donor_crown_ratio", row["crown_ratio"]) if row.get("crown_ratio") is not None else None
            if ratio is not None and ratio > 0:
                record["crown_ratio"] = ratio
                record["crown_ratio_source"] = "transferred TreeMap donor; local error unknown"
        else:
            missing["compatible_fia_donor_unavailable"] += 1
        if "crown_ratio" not in record:
            missing["live_crown_ratio_unavailable"] += 1
        records.append(record)
    return records, dict(missing)


def make_override_plan(base, overrides, records, extent):
    """Replace generated pines inside the observed window, retaining explicit replacements."""
    x0, z0, x1, z1 = extent
    def inside(record):
        p = record.get("position", [math.inf, 0, math.inf])
        return record.get("kind") == "pine" and x0 <= p[0] < x1 and z0 <= p[2] < z1
    replacements = overrides.get("replace", {})
    removed = {r["id"] for r in base.get("trees", []) if inside(r)
               and str(r.get("id", "")).startswith("pine_") and r["id"] not in replacements}
    plan = copy.deepcopy(overrides)
    plan["status"] = "derived_not_field_validated"
    plan["remove"] = sorted(set(plan.get("remove", [])) | removed)
    kept, discarded = [], []
    for record in plan.get("add", []):
        generated = str(record.get("id", record.get("stable_id", ""))).startswith(("prop_", "census_lidar_"))
        (discarded if inside(record) and generated else kept).append(record)
    plan["add"] = kept + records
    plan["canopy_source"] = {"status": "derived_not_field_validated",
        "count_scope": "observed dominant crowns only; total stems unknown",
        "generated_base_removed": len(removed), "generated_add_removed": len(discarded),
        "protected_add_retained": len(kept), "placement_count": len(records),
        "spacing_method": "detector height-window suppression; no arbitrary stem infill"}
    return plan


def apply_override_plan(plan, destination, *, expected_sha256, backup):
    """Apply a reviewed plan only to its unchanged source, after preserving original bytes."""
    destination, backup = Path(destination), Path(backup)
    if sha256_file(destination) != expected_sha256:
        raise ValueError("placement overrides changed after the plan was generated")
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copyfile(destination, backup)
    write_json_atomic(destination, plan, indent=1)
