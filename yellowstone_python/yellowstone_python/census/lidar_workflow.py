"""Build measured-height crown products and a reviewable dominant-tree placement layer."""
from __future__ import annotations

import logging
from pathlib import Path
import shutil

import numpy as np

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic
from yellowstone_python.census.canopy_census import (LIDAR_WINDOW, canopy_coverage_field,
    density_stats, detect_lidar, qa_census, to_world)
from yellowstone_python.authoring.canopy_placement import (apply_override_plan,
    exclusion_masks, filter_crowns, make_override_plan, placement_records)

logger = logging.getLogger(__name__)
ZONES = {"spring_0_50m": {"circle": (-94.7, -10.6, 50)},
         "apron_50_100m": {"ring": (-94.7, -10.6, 50, 100)},
         "transition_100_200m": {"ring": (-94.7, -10.6, 100, 200)},
         "outwash_200_400m": {"ring": (-94.7, -10.6, 200, 400)},
         "overlook_knoll_r120": {"circle": (-252, 159, 120)},
         "detail_full": {"box": (-640, -640, 640, 640)}}


def build_forest_products(project, world_root, *, apply=False, sensitivity=True):
    """Produce actual crown and coverage artifacts, retaining raw returns and prior sources."""
    import rasterio
    from PIL import Image
    from yellowstone_python.land.vegetation import load_terrain, terrain_fns
    project, world_root = Path(project), Path(world_root)
    out = project / "derived/lidar_canopy"
    metadata_path = out / "canopy_height.provenance.json"
    metadata = load_json(metadata_path)
    raw_path = out / metadata["artifacts"]["canopy_height"]["path"]
    if sha256_file(raw_path) != metadata["artifacts"]["canopy_height"]["sha256"]:
        raise ValueError("raw canopy-height checksum mismatch")
    with rasterio.open(raw_path) as raster:
        raw = raster.read(1, masked=True).filled(np.nan)
        profile = raster.profile.copy()
    world_path = world_root / "data/world.json"
    habitat_path = world_root / "assets/textures/habitat_mask.png"
    world = load_json(world_path)
    habitat = np.asarray(Image.open(habitat_path).convert("RGB"), dtype=float) / 255
    extent, spacing = metadata["extent_m"], metadata["resolution_m"]
    masks = exclusion_masks(world, habitat, raw.shape, extent, spacing)
    nonvegetation = masks["mineral"] | masks["pool_apron"] | masks["river"]
    interpreted = np.where(np.isfinite(raw) & nonvegetation, 0, raw)
    logger.info("Detecting dominant crowns from interpreted surface heights")
    pixels, labels = detect_lidar(interpreted, pixel_size_m=spacing, return_labels=True)
    world_trees = to_world(pixels, width=raw.shape[1], height=raw.shape[0], extent=extent)
    trees, rejected = filter_crowns(world_trees, masks)
    sensitivity_counts = {}
    if sensitivity:
        for slope in [.04, .08]:
            detected = detect_lidar(interpreted, pixel_size_m=spacing, window={"slope": slope})
            kept, _ = filter_crowns(to_world(detected, width=raw.shape[1],
                                            height=raw.shape[0], extent=extent), masks)
            sensitivity_counts[str(slope)] = {"n": len(kept), "density": density_stats(kept, ZONES)}
    inputs = {"raw_canopy_height": sha256_file(raw_path), "world": sha256_file(world_path),
              "habitat_mask": sha256_file(habitat_path),
              "detector": sha256_file(Path(__file__).with_name("canopy_census.py"))}
    census = {"schema": "yellowstone.canopy_census.v1", "status": "derived_not_field_validated",
        "source": {"agency": "USGS 3DEP", "acquisition_start": "2020-09-29",
            "acquisition_end": "2020-10-09", "acquisition_year": 2020,
            "extent_m": extent, "px_m": spacing, "input_sha256": inputs},
        "n": len(trees), "trees": trees, "density": density_stats(trees, ZONES),
        "detector_window": LIDAR_WINDOW, "validation_availability": "unavailable",
        "count_scope": "dominant crown detections; total and subcanopy stems unknown",
        "rejected": rejected, "sensitivity": sensitivity_counts}
    failures = qa_census(census)
    if failures:
        raise ValueError(f"new crown census failed mechanical checks: {failures}")
    census_path = project / "derived/census.json"
    backup = project / "data/authoring_baselines/census_rgb.json"
    if census_path.exists() and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(census_path, backup)
    old = load_json(backup) if backup.exists() else {"trees": []}
    write_json_atomic(census_path, census, indent=1)
    write_json_atomic(out / "dominant_crowns.json", census, indent=1)
    coverage = canopy_coverage_field(raw, trees, extent=extent, pixel_size_m=spacing,
                                     excluded_mask=nonvegetation)
    coverage["source_sha256"] = inputs
    write_json_atomic(out / "canopy_coverage.json", coverage, indent=1)
    for name, values, dtype in [("interpreted_canopy_height", interpreted, "float32"),
                                ("crown_labels", labels, "int32")]:
        path = out / f"{name}.tif"
        temp = path.with_suffix(".tmp.tif")
        options = dict(profile, dtype=dtype, nodata=np.nan if dtype == "float32" else 0)
        with rasterio.open(temp, "w", **options) as destination:
            destination.write(values.astype(dtype), 1)
        temp.replace(path)
        metadata["artifacts"][name] = {"path": path.name, "sha256": sha256_file(path)}
    metadata["interpretation"] = {"status": "derived_not_field_validated",
        "mapped_nonvegetation_exclusions": ["mineral channel >=0.35", "pool apron", "river channel"],
        "excluded_raw_returns_preserved": True, "input_sha256": inputs}
    write_json_atomic(metadata_path, metadata, indent=1)
    from rasterio.enums import Resampling
    from yellowstone_python.census.canopy_residual import write_residual_canopy
    with rasterio.open(world_root / "references/dem_1m_core.tif") as dem:
        ground = dem.read(1, out_shape=raw.shape, resampling=Resampling.bilinear)
    residual_metadata = write_residual_canopy(interpreted, ground, trees, out,
        extent=extent, source_sha256={**inputs, "matched_dem": metadata["dem_sha256"]}, spacing=spacing)
    terrain_path = world_root / "data/terrain.f32"
    sample, _ = terrain_fns(load_terrain(str(terrain_path)))
    treemap_path = project / "derived/treemap_midway.json"
    treemap = load_json(treemap_path) if treemap_path.exists() else None
    records, missing = placement_records(trees, sample, treemap)
    base_path = world_root / "data/placements.json"
    overrides_path = world_root / "data/placement_overrides.json"
    original_hash = sha256_file(overrides_path)
    override_backup = project / "data/authoring_baselines/placement_overrides_before_lidar.json"
    baseline_overrides = override_backup if override_backup.exists() else overrides_path
    plan = make_override_plan(load_json(base_path), load_json(baseline_overrides), records, extent)
    plan_path = out / "placement_overrides.plan.json"
    write_json_atomic(plan_path, plan, indent=1)
    control = {}
    for name in ["mineral", "pool_apron", "river"]:
        region = masks[name]
        valid = region & np.isfinite(raw)
        control[name] = {"area_m2": float(region.sum() * spacing ** 2),
            "valid_fraction": float(valid.sum() / region.sum()) if region.any() else None,
            "missing_fraction": float((region & ~np.isfinite(raw)).sum() / region.sum()) if region.any() else None,
            "raw_below_0_5m_fraction": float((valid & (raw < .5)).sum() / valid.sum()) if valid.any() else None,
            "raw_99_percent_ground_check_passed": bool((valid & (raw < .5)).sum() / valid.sum() >= .99) if valid.any() else False}
    report = {"schema": "yellowstone.forest_receipt.v1", "status": "derived_not_field_validated", "n_dominant": len(trees),
        "raw_detection_count": len(world_trees), "rejected": rejected, "sensitivity": sensitivity_counts,
        "coverage": {"valid_fraction": float(np.isfinite(raw).mean()),
                     "missing_fraction": float((~np.isfinite(raw)).mean()),
                     "interpreted_canopy_fraction_valid": float(((interpreted >= 2) & np.isfinite(raw)).sum() / np.isfinite(raw).sum())},
        "raw_nonvegetation_controls": control, "old_density": density_stats(old["trees"], ZONES),
        "new_density": census["density"], "placement_count": len(records),
        "placement_missing_donor_fields": missing, "placement_plan": str(plan_path),
        "canopy_coverage": str(out / "canopy_coverage.json"), "source_sha256": inputs,
        "unresolved_canopy": residual_metadata,
        "original_overrides_sha256": original_hash, "placement_plan_sha256": sha256_file(plan_path),
        "applied": False, "total_stem_density": None,
        "validation_availability": "unavailable; no submitted human labels",
        "scientific_acceptance": "not_yet_accepted; raw nonvegetation99percent gatefailed or blindlabels unavailable",
        "dryad_fit_availability": "unavailable; no canopy cover/crown-width covariates and no local plots",
        "raw_height_tail": {"maximum_m": float(np.nanmax(raw)),
            "maximum_nonvegetation": bool(nonvegetation.flat[np.nanargmax(raw)]),
            "cause": "unknown; raw surface return retained, excluded from crown interpretation"}}
    if apply:
        apply_override_plan(plan, overrides_path, expected_sha256=original_hash,
                            backup=override_backup)
        report["applied"] = True
        report["applied_overrides_sha256"] = sha256_file(overrides_path)
    elif all(load_json(overrides_path).get(key) == plan.get(key) for key in ("add", "remove", "replace")):
        report["applied"] = True
        report["applied_overrides_sha256"] = sha256_file(overrides_path)
        report["applied_geometry_matches_plan"] = True
    write_json_atomic(out / "forest_receipt.json", report, indent=1)
    logger.info("Produced %s dominant crowns, %s placement records", len(trees), len(records))
    return report
