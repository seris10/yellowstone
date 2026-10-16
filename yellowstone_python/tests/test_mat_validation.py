"""Tests for the mat appearance validation module."""
from __future__ import annotations

import numpy as np
import pytest

import yellowstone_python.thermal_features.mat_validation as mv
from yellowstone_python.thermal_features.mat_validation import MODELED_TO_OBSERVED, OBSERVED_BLUE_WATER, OBSERVED_BROWN, OBSERVED_CLASSES, OBSERVED_GREEN, OBSERVED_ORANGE, OBSERVED_WHITE_SINTER, OBSERVED_YELLOW, classify_image_array, classify_pixel_rgb, confusion_matrix, validate_mats
from yellowstone_python.thermal_features.microbial_mats import COMMUNITY_LEGEND


def _six_class_legend() -> list:
    return [dict(entry) for entry in COMMUNITY_LEGEND]


def _synthetic_image_and_mask() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build an RGB tile and modeled map that match under the model mapping."""
    rgb = np.zeros((4, 5, 3), dtype=np.uint8)
    rgb[:, 0] = (10, 30, 150)
    rgb[:, 1] = (210, 200, 60)
    rgb[:, 2] = (200, 110, 50)
    rgb[:, 3] = (60, 150, 80)
    rgb[:, 4] = (240, 240, 240)
    mask = np.ones((4, 5), dtype=bool)
    modeled = np.full((4, 5), -1, dtype=np.int16)
    legend_id = {entry["name"]: entry["class_id"] for entry in COMMUNITY_LEGEND}
    modeled[:, 0] = legend_id["water_hot_clear"]
    modeled[:, 1] = legend_id["yellow_cyanobacteria"]
    modeled[:, 2] = legend_id["orange_cyanobacteria_chromatiaceae"]
    modeled[:, 3] = legend_id["brown_green_mixed_photosynthetic"]
    modeled[:, 4] = legend_id["white_chemolithotroph"]
    return rgb, mask, modeled


def test_classify_pixel_matches_each_color_class():
    assert classify_pixel_rgb(10, 30, 150) == OBSERVED_BLUE_WATER
    assert classify_pixel_rgb(210, 200, 60) == OBSERVED_YELLOW
    assert classify_pixel_rgb(200, 110, 50) == OBSERVED_ORANGE
    assert classify_pixel_rgb(70, 55, 40) == OBSERVED_BROWN
    assert classify_pixel_rgb(60, 150, 80) == OBSERVED_GREEN
    assert classify_pixel_rgb(240, 240, 240) == OBSERVED_WHITE_SINTER


def test_classify_image_matches_single_pixel():
    rgb, mask, _ = _synthetic_image_and_mask()
    classes = classify_image_array(rgb, mask)
    assert classes[0, 0] == OBSERVED_CLASSES.index(OBSERVED_BLUE_WATER)
    assert classes[0, -1] == OBSERVED_CLASSES.index(OBSERVED_WHITE_SINTER)
    for j in range(classes.shape[1]):
        for i in range(classes.shape[0]):
            single = classify_pixel_rgb(*(int(v) for v in rgb[i, j]))
            assert classes[i, j] == OBSERVED_CLASSES.index(single)


def test_synthetic_perfect_agreement():
    rgb, mask, modeled = _synthetic_image_and_mask()
    block = validate_mats(
        rgb, mask, modeled, _six_class_legend(),
        observed_pixel_area_m2=1.0, modeled_pixel_area_m2=1.0,
    )
    assert block["overall_agreement"] == pytest.approx(1.0)
    assert block["status"] == "validation"
    assert block["schema"] == mv.SCHEMA_VALIDATION


def test_mask_restricts_classification():
    rgb, _, _ = _synthetic_image_and_mask()
    mask = np.zeros(rgb.shape[:2], dtype=bool)
    mask[:, 0] = True
    classes = classify_image_array(rgb, mask)
    assert classes[0, 0] == OBSERVED_CLASSES.index(OBSERVED_BLUE_WATER)
    assert classes[0, -1] == -1


def test_confusion_matrix_offdiagonal():
    observed = np.array([[0, 1], [2, 3]], dtype=np.int8)
    modeled = np.array([[0, 2], [2, 3]], dtype=np.int8)
    cm = confusion_matrix(observed, modeled)
    assert cm[0, 0] == 1
    assert cm[1, 2] == 1
    assert cm[2, 2] == 1
    assert cm[3, 3] == 1


def test_validation_block_names_sources_and_classes():
    rgb, mask, modeled = _synthetic_image_and_mask()
    block = validate_mats(
        rgb, mask, modeled, _six_class_legend(),
        observed_pixel_area_m2=0.4, modeled_pixel_area_m2=1.0,
    )
    assert set(block["classes"]) >= {
        OBSERVED_BLUE_WATER, OBSERVED_YELLOW, OBSERVED_ORANGE,
        OBSERVED_BROWN, OBSERVED_GREEN, OBSERVED_WHITE_SINTER,
    }
    assert block["model_class_to_observed"] == MODELED_TO_OBSERVED
    assert "validation only" in block["note"]
    assert isinstance(block["sources"], list) and block["sources"]
