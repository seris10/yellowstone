"""Tests for yellowstone_python.validation.checks shape and gate behavior."""
from __future__ import annotations

from yellowstone_python.validation.checks import check_uq_document


def _valid_uq_doc():
    return {
        "bands": {"level": 0.68, "seed": 12345},
        "holdout_coverage": {"coverage": 0.73,
                             "interpretation": "fraction of holdout"},
        "effective_geometry": {"volume_m3": 1000.0, "area_m2": 500.0},
        "members": [],
    }


def test_valid_uq_doc_passes():
    assert check_uq_document(_valid_uq_doc()) == []


def test_missing_bands_seed_fails():
    doc = _valid_uq_doc()
    del doc["bands"]["seed"]
    out = check_uq_document(doc)
    assert any("bands.seed" in failure for failure in out)


def test_missing_holdout_coverage_fails():
    doc = _valid_uq_doc()
    del doc["holdout_coverage"]["coverage"]
    out = check_uq_document(doc)
    assert any("holdout_coverage.coverage" in failure for failure in out)


def test_missing_interpretation_fails():
    doc = _valid_uq_doc()
    del doc["holdout_coverage"]["interpretation"]
    out = check_uq_document(doc)
    assert any("interpretation" in failure for failure in out)


def test_missing_effective_geometry_fails():
    doc = _valid_uq_doc()
    del doc["effective_geometry"]
    out = check_uq_document(doc)
    assert any("effective_geometry" in failure for failure in out)


def test_non_dict_rejected():
    out = check_uq_document([])
    assert out and "dict" in out[0]
