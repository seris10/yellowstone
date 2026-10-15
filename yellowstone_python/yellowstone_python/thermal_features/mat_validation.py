"""Validate the modeled mat class map against the NAIP orthophoto detail.
Returns a confusion matrix and areas without changing model parameters."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic

from yellowstone_python.common.checks import finite as _finite

import json
import math
import os
from typing import Any

import numpy as np

SCHEMA_VALIDATION = "yellowstone.mat_validation.v1"

OBSERVED_BLUE_WATER = "blue_water"
OBSERVED_YELLOW = "yellow"
OBSERVED_ORANGE = "orange"
OBSERVED_BROWN = "brown"
OBSERVED_GREEN = "green"
OBSERVED_WHITE_SINTER = "white_sinter"
OBSERVED_UNCLASSIFIED = "unclassified"

OBSERVED_CLASSES = (
    OBSERVED_BLUE_WATER, OBSERVED_YELLOW, OBSERVED_ORANGE,
    OBSERVED_BROWN, OBSERVED_GREEN, OBSERVED_WHITE_SINTER,
    OBSERVED_UNCLASSIFIED,
)

MODELED_TO_OBSERVED = {
    "water_hot_clear": OBSERVED_BLUE_WATER,
    "white_chemolithotroph": OBSERVED_WHITE_SINTER,
    "pink_chemolithotroph": OBSERVED_WHITE_SINTER,
    "yellow_cyanobacteria": OBSERVED_YELLOW,
    "yellow_green_cyanobacteria_chloroflexus": OBSERVED_YELLOW,
    "orange_cyanobacteria_chromatiaceae": OBSERVED_ORANGE,
    "brown_green_mixed_photosynthetic": OBSERVED_GREEN,
    "sinter_dry": OBSERVED_WHITE_SINTER,
}




def classify_pixel_rgb(r: float, g: float, b: float) -> str:
    """Classify one RGB pixel in [0, 255] into an observed color class.
Separates blue, white, yellow, orange, green and brown by thresholded hue."""
    rf = _finite("r", r)
    gf = _finite("g", g)
    bf = _finite("b", b)
    for value in (rf, gf, bf):
        if value < 0.0 or value > 255.0:
            raise ValueError("RGB components must lie in [0, 255]")
    v_max = max(rf, gf, bf)
    v_min = min(rf, gf, bf)
    sat = 0.0 if v_max == 0.0 else (v_max - v_min) / v_max

    if bf > rf and bf > gf and bf >= 90.0:
        return OBSERVED_BLUE_WATER
    if v_max >= 215.0 and sat < 0.18:
        return OBSERVED_WHITE_SINTER
    if rf < 90.0 and gf < 90.0 and bf < 90.0:
        return OBSERVED_BROWN
    if rf >= 150.0 and gf >= 150.0 and bf < 140.0 and rf - bf > 40.0:
        return OBSERVED_YELLOW
    if rf >= 150.0 and gf >= 70.0 and gf < 150.0 and bf < 110.0:
        return OBSERVED_ORANGE
    if gf > rf and gf > bf and gf >= 90.0:
        return OBSERVED_GREEN
    if rf > gf and rf > bf and rf >= 120.0 and gf < 120.0:
        return OBSERVED_BROWN
    return OBSERVED_UNCLASSIFIED


def classify_image_array(rgb_array: np.ndarray,
                         mask: np.ndarray | None = None) -> np.ndarray:
    """Classify an RGB image (H, W, 3) into observed classes.
Returns int8 class indices with -1 outside the optional mask."""
    arr = np.asarray(rgb_array)
    if arr.ndim != 3 or arr.shape[-1] < 3:
        raise ValueError("rgb_array must be (H, W, 3)")
    rgb = arr[..., :3].astype(np.float64)
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    v_max = np.maximum(np.maximum(r, g), b)
    v_min = np.minimum(np.minimum(r, g), b)
    sat = np.zeros_like(v_max)
    nz = v_max > 0.0
    sat[nz] = (v_max[nz] - v_min[nz]) / v_max[nz]

    classes = np.full(r.shape, OBSERVED_CLASSES.index(OBSERVED_UNCLASSIFIED),
                      dtype=np.int8)

    is_brown = (r < 90.0) & (g < 90.0) & (b < 90.0)
    is_green = (g > r) & (g > b) & (g >= 90.0)
    is_orange = ((r >= 150.0) & (g >= 70.0) & (g < 150.0) & (b < 110.0))
    is_yellow = ((r >= 150.0) & (g >= 150.0) & (b < 140.0) & (r - b > 40.0))
    is_warm_brown = (r > g) & (r > b) & (r >= 120.0) & (g < 120.0)
    is_white = (v_max >= 215.0) & (sat < 0.18)
    is_blue = (b > r) & (b > g) & (b >= 90.0)

    classes[is_brown] = OBSERVED_CLASSES.index(OBSERVED_BROWN)
    classes[is_green] = OBSERVED_CLASSES.index(OBSERVED_GREEN)
    classes[is_orange] = OBSERVED_CLASSES.index(OBSERVED_ORANGE)
    classes[is_yellow] = OBSERVED_CLASSES.index(OBSERVED_YELLOW)
    classes[is_warm_brown & ~is_orange & ~is_yellow] = (
        OBSERVED_CLASSES.index(OBSERVED_BROWN))
    classes[is_white] = OBSERVED_CLASSES.index(OBSERVED_WHITE_SINTER)
    classes[is_blue] = OBSERVED_CLASSES.index(OBSERVED_BLUE_WATER)

    if mask is not None:
        mask_arr = np.asarray(mask).astype(bool)
        if mask_arr.shape != classes.shape:
            raise ValueError("mask shape must match the image")
        classes[~mask_arr] = -1
    return classes


def _modeled_to_observed_array(modeled_classes: np.ndarray,
                               legend_by_id: dict[int, str]
                               ) -> np.ndarray:
    """Map a modeled int16 class map to the observed-class index space."""
    out = np.full(modeled_classes.shape,
                  OBSERVED_CLASSES.index(OBSERVED_UNCLASSIFIED),
                  dtype=np.int8)
    for cls_id, name in legend_by_id.items():
        observed = MODELED_TO_OBSERVED.get(name, OBSERVED_UNCLASSIFIED)
        out[modeled_classes == cls_id] = OBSERVED_CLASSES.index(observed)
    out[modeled_classes < 0] = -1
    return out


def confusion_matrix(observed: np.ndarray,
                     modeled_observed: np.ndarray) -> np.ndarray:
    """Confusion matrix of observed vs modeled (both int indexed arrays).
Rows index observed, columns the modeled-to-observed classes."""
    if observed.shape != modeled_observed.shape:
        raise ValueError("observed and modeled shapes must match")
    n = len(OBSERVED_CLASSES)
    matrix = np.zeros((n, n), dtype=np.int64)
    obs_flat = observed.ravel()
    mod_flat = modeled_observed.ravel()
    for oi in range(n):
        obs_mask = obs_flat == oi
        if not obs_mask.any():
            continue
        for mi in range(n):
            mod_mask = mod_flat == mi
            matrix[oi, mi] = int(np.sum(obs_mask & mod_mask))
    return matrix


def per_class_area_m2(classes: np.ndarray,
                      pixel_area_m2: float) -> dict:
    """Area in square meters per observed class."""
    pix = _finite("pixel_area_m2", pixel_area_m2)
    if pix <= 0.0:
        raise ValueError("pixel_area_m2 must be > 0")
    out = {}
    for i, name in enumerate(OBSERVED_CLASSES):
        count = int(np.sum(classes == i))
        out[name] = count * pix
    return out


def validate_mats(
    observed_rgb: np.ndarray,
    thermal_mask: np.ndarray,
    modeled_class_map: np.ndarray,
    modeled_legend: list,
    *,
    observed_pixel_area_m2: float,
    modeled_pixel_area_m2: float,
    status: str = "validation",
    sources: list | None = None,
) -> dict:
    """Return a validation block for BUILD.json.
Confusion matrix and per-class areas; model parameters are not touched."""
    legend_by_id: dict[int, str] = {
        int(entry["class_id"]): str(entry["name"]) for entry in modeled_legend}
    observed_classes = classify_image_array(observed_rgb, thermal_mask)
    modeled_observed = _modeled_to_observed_array(modeled_class_map,
                                                  legend_by_id)
    cm = confusion_matrix(observed_classes, modeled_observed)
    cm_dict = {
        OBSERVED_CLASSES[r]: {OBSERVED_CLASSES[c]: int(cm[r, c])
                              for c in range(len(OBSERVED_CLASSES))}
        for r in range(len(OBSERVED_CLASSES))
    }
    total = int(cm.sum())
    diag = int(np.trace(cm))
    overall_agreement = (diag / total) if total > 0 else 0.0
    return {
        "schema": SCHEMA_VALIDATION,
        "status": status,
        "confusion_matrix": cm_dict,
        "overall_agreement": round(overall_agreement, 4),
        "per_class_area_m2": {
            "observed": per_class_area_m2(observed_classes,
                                          observed_pixel_area_m2),
            "modeled": per_class_area_m2(modeled_observed,
                                         modeled_pixel_area_m2),
        },
        "classes": list(OBSERVED_CLASSES),
        "model_class_to_observed": dict(MODELED_TO_OBSERVED),
        "sources": sources or [
            "USGS imagery product page: hyperspectral image of Grand Prismatic Spring",
            "USDA FSA APFO NAIP export (orthophoto detail reference)",
        ],
        "note": "validation only; never feeds back into model parameters",
    }


def write_validation(block: dict, out_path: str) -> str:
    """Serialize a validation block as pretty JSON."""
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    write_json_atomic(out_path, block, indent=2)
    return out_path


__all__ = [
    "SCHEMA_VALIDATION",
    "OBSERVED_CLASSES",
    "MODELED_TO_OBSERVED",
    "classify_pixel_rgb",
    "classify_image_array",
    "confusion_matrix",
    "per_class_area_m2",
    "validate_mats",
    "write_validation",
]
