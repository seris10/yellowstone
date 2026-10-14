"""Stages vegetation build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import CANOPY_FALLBACK, Path, json, math


def _canopy_from_height(center_xz, radius_m, provenance_path):
    """Sample supported canopy-height pixels within a fully covered circular region."""
    import numpy as np
    import rasterio
    from rasterio.windows import Window
    from yellowstone_python.common.checks import finite, positive
    from yellowstone_python.common.io import load_json, sha256_file
    cx, cz = finite("canopy_center_x", center_xz[0]), finite("canopy_center_z", center_xz[1])
    radius = positive("canopy_radius_m", radius_m)
    provenance = load_json(provenance_path)
    if provenance.get("schema") != "yellowstone.canopy_height.v1" or provenance.get("status") != "measured":
        raise ValueError("preferred canopy raster requires measured canopy-height provenance")
    x0, z0, x1, z1 = provenance["extent_m"]
    if cx - radius < x0 or cx + radius > x1 or cz - radius < z0 or cz + radius > z1:
        return None, {"reason": "outside_measured_canopy_window"}
    artifact = provenance["artifacts"].get("interpreted_canopy_height", provenance["artifacts"]["canopy_height"])
    if artifact["path"] not in {"canopy_height.tif", "interpreted_canopy_height.tif"}:
        raise ValueError("preferred canopy artifact path is outside the declared canopy products")
    raster_path = Path(provenance_path).parent / artifact["path"]
    if sha256_file(raster_path) != artifact["sha256"]:
        raise ValueError("preferred canopy raster checksum does not match provenance")
    spacing = positive("canopy_resolution_m", provenance["resolution_m"])
    left = max(0, math.floor((cx - radius - x0) / spacing))
    top = max(0, math.floor((cz - radius - z0) / spacing))
    right = math.ceil((cx + radius - x0) / spacing)
    bottom = math.ceil((cz + radius - z0) / spacing)
    with rasterio.open(raster_path) as raster:
        values = raster.read(1, window=Window(left, top, right - left, bottom - top),
                             masked=True).filled(np.nan)
    xs = x0 + (np.arange(left, right) + 0.5) * spacing
    zs = z0 + (np.arange(top, bottom) + 0.5) * spacing
    circle = (xs[None, :] - cx) ** 2 + (zs[:, None] - cz) ** 2 <= radius ** 2
    valid = circle & np.isfinite(values)
    support = float(valid.sum() / circle.sum()) if circle.any() else 0.0
    details = {"valid_fraction": support, "missing_fraction": 1 - support,
               "supported_area_m2": float(valid.sum() * spacing ** 2),
               "height_threshold_m": 2.0, "raster_sha256": artifact["sha256"],
               "mapped_nonvegetation_excluded": artifact["path"] == "interpreted_canopy_height.tif"}
    if support < 0.95:
        details["reason"] = "insufficient_measured_canopy_support"
        return None, details
    return float(((values >= 2.0) & valid).sum() / valid.sum()), details


def _canopy_from_census(center_xz: tuple, radius_m: float,
                        census_path: Path, *, canopy_provenance_path=None) -> tuple[float, str]:
    """Canopy fraction in a circle from census.json crowns, or the fallback."""
    canopy_provenance_path = (Path(canopy_provenance_path) if canopy_provenance_path is not None
                              else Path(census_path).parent / "lidar_canopy/canopy_height.provenance.json")
    if canopy_provenance_path.is_file():
        observed, quality = _canopy_from_height(center_xz, radius_m, canopy_provenance_path)
        if observed is not None:
            return observed, f"measured_canopy_height_footprint; valid_fraction={quality['valid_fraction']:.6f}"
        if quality["reason"] == "insufficient_measured_canopy_support":
            return CANOPY_FALLBACK, "illustrative_fallback_missing_canopy_height_support"
        if quality["reason"] == "outside_measured_canopy_window":
            return CANOPY_FALLBACK, "illustrative_fallback_outside_canopy_height_window"
    try:
        doc = json.loads(census_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CANOPY_FALLBACK, "illustrative_fallback_no_census"
    trees = doc.get("trees") if isinstance(doc, dict) else None
    if not isinstance(trees, list) or not trees:
        return CANOPY_FALLBACK, "illustrative_fallback_empty_census"
    cx, cz = float(center_xz[0]), float(center_xz[1])
    r = float(radius_m)
    if not math.isfinite(r) or r <= 0.0:
        return CANOPY_FALLBACK, "illustrative_fallback_bad_radius"
    r2 = r * r
    area_circle = math.pi * r2
    area_crowns = 0.0
    for t in trees:
        if not isinstance(t, dict):
            continue
        try:
            x = float(t["x"])
            z = float(t["z"])
            cr = float(t.get("crown_r_m", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(x) and math.isfinite(z) and math.isfinite(cr)):
            continue
        if cr <= 0.0:
            continue
        if (x - cx) * (x - cx) + (z - cz) * (z - cz) <= (r + cr) * (r + cr):
            area_crowns += math.pi * cr * cr
    fraction = min(1.0, area_crowns / area_circle)
    return fraction, "census_json_crown_area_sum"


def _grazers_input_from_consumed(prev_consumed_by_patch: dict,
                                 dt_s: float) -> dict | None:
    """Convert a previous step's consumed_by_patch into a grazers input for patch_step.
Empty input returns None so patch_step applies no demand."""
    if not prev_consumed_by_patch or dt_s <= 0.0:
        return None
    out: dict = {}
    for pid, eaten in prev_consumed_by_patch.items():
        try:
            rate = float(eaten) / float(dt_s)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if rate <= 0.0 or not math.isfinite(rate):
            continue
        out[f"grazing_feedback_{pid}"] = {
            "patch_id": pid, "active": True,
            "rate_per_second": rate,
            "source": "previous_step_consumed_by_patch"}
    return out or None


from yellowstone_python.pipeline.shared import PKG_ROOT, copy
from yellowstone_python.pipeline.stages.vegetation import _canopy_from_census, _grazers_input_from_consumed

READS = ('_excluded', 'baseline', 'hour0', 'shells', 'sim_s', 'tfns')
WRITES = ('canopy_input', 'canopy_source', 'patches0', 'patches1', 'prop_cfg', 'prop_violations', 'proposals', 'review_log', 'veg_ledger')

def run(state: dict, cfg: dict) -> dict:
    """Advance the vegetation stage and return its state."""
    _excluded = state['_excluded']
    baseline = state['baseline']
    hour0 = state['hour0']
    shells = state['shells']
    sim_s = state['sim_s']
    tfns = state['tfns']
    from yellowstone_python.aquatic.fish import check_trout_clear_of_pools, update_trout
    from yellowstone_python.thermal_features.geochemistry import check_midway_shells
    from yellowstone_python.land.grazers import check_routes as check_grazer_routes, consumed_by_patch_from_grazers, plan_path, route_length as _rlen, update_grazers
    from yellowstone_python.insects_birds import (diets_with_aerial_insectivores, foraging_state,
                                insect_activity, step_compartments,
                                step_resource, update_wildlife,
                                update_wildlife_from_intake)
    from yellowstone_python.thermal_features.pool_crust import build_all as build_shells
    from yellowstone_python.thermal_features.pool_crust import exclusion_violations as apron_violations
    from yellowstone_python.thermal_features.pool_crust import in_apron as _in_apron
    from yellowstone_python.land.snow_season import resolve_game_clock, run_season
    from yellowstone_python.land.vegetation import patch_step, propose_plantings_reviewed
    from yellowstone_python.thermal_features.ground_heat import heat_flux_mask_field, soil_temperature_by_patch, thermal_flux_mm_d_by_patch, tree_thermal_suitability, LODGEPOLE_SOIL_DIEOFF_C
    from yellowstone_python.land.evapotranspiration import reference_et0_mm_d, step_patches_et, CROP_COEFFICIENTS
    from yellowstone_python.aquatic.piscivores import predation_over_refuge, TROUT_DENSITY_DEFAULT_PER_M2_WETTED, RIVER_WETTED_WIDTH_DEFAULT_M
    from yellowstone_python.atmosphere.steam_microclimate import plume_microclimate_adjustment, fog_present, rime_present
    from yellowstone_python.aquatic.river_oxygen import saturation_mg_l as do_saturation_mg_l, fish_suitability as do_fish_suitability

    from yellowstone_python.atmosphere.microclimate import load_weather_bundle, bundle_weather

    from yellowstone_python.atmosphere.microclimate import condensation_potential

    from yellowstone_python.land.snow_season import catchment_runoff_m3_s

    from yellowstone_python.exporters.runtime_series import reach_summaries

    from yellowstone_python.aquatic.aquatic_foodweb import run_foodweb as run_aquatic_foodweb

    from yellowstone_python.aquatic.aquatic_foodweb import thermal_landscape

    from yellowstone_python.aquatic.aquatic_foodweb import shear_to_disturbance

    from yellowstone_python.insects_birds import develop_benthic_grid

    from yellowstone_python.aquatic.fish import build_chainage, place_trout_at_chainage, reach_membership, reach_z_windows

    from yellowstone_python.land.grazers import route_length as _rlen

    from yellowstone_python.exporters.runtime_series import python_series

    # --- vegetation + proposals ---
    vcfg = cfg.get("vegetation", {})
    patches0 = copy.deepcopy(baseline.get("patches", []))
    # Grazing feedback: pass the previous step's consumed_by_patch from the grazer module.
    prev_consumed_by_patch = (vcfg.get("prev_consumed_by_patch") or {})
    graz_from_prev = _grazers_input_from_consumed(prev_consumed_by_patch,
                                                  sim_s)
    patches1, veg_ledger = patch_step(patches0, hour0, sim_s,
                                      grazers=graz_from_prev)
    veg_ledger["grazing_feedback_lag_steps"] = 1
    veg_ledger["grazing_feedback_available"] = bool(prev_consumed_by_patch)
    veg_ledger["grazing_feedback_source"] = (
        "grazer_module_previous_step_consumed_by_patch"
        if prev_consumed_by_patch
        else "grazer_module_previous_step_consumed_by_patch (empty for single-step build)")
    veg_ledger["prev_consumed_by_patch"] = dict(prev_consumed_by_patch)
    veg_ledger["coupling_status"] = (
        "partial" if not prev_consumed_by_patch else "wired")
    veg_ledger["config_grazers_ignored"] = (
        "vcfg.grazers no longer feeds patch_step; grazing offtake comes "
        "from the grazer module output with a one-step lag")
    prop_cfg = vcfg.get("proposal", {})
    proposal_center = tuple(prop_cfg.get("center_xz", [-360, 260]))
    proposal_radius_m = float(prop_cfg.get("radius_m", 30))
    canopy_input, canopy_source = _canopy_from_census(
        proposal_center, proposal_radius_m, PKG_ROOT / "derived" / "census.json")
    proposals, review_log = propose_plantings_reviewed(
        prop_cfg.get("guild", "lodgepole_pine"),
        proposal_center,
        proposal_radius_m,
        int(prop_cfg.get("count", 40)), int(prop_cfg.get("seed", 7)),
        habitat_id=prop_cfg.get("habitat_id", "forest_edge"),
        exclusion_test=_excluded, terrain_fn=tfns, patches=patches0,
        canopy=canopy_input,
        suitability_threshold=float(prop_cfg.get("suitability_threshold", 0.12)))
    prop_violations = apron_violations(
        [{"id": r["stable_id"], "x": r["x"], "z": r["z"]} for r in proposals],
        shells)


    state.update({'canopy_input': canopy_input, 'canopy_source': canopy_source, 'patches0': patches0, 'patches1': patches1, 'prop_cfg': prop_cfg, 'prop_violations': prop_violations, 'proposals': proposals, 'review_log': review_log, 'veg_ledger': veg_ledger})
    return state
