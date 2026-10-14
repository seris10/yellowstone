"""Independent authored floor records, observed support and preserved tree inputs."""
from __future__ import annotations

import copy

import numpy as np
import pytest

from yellowstone_python.authoring.forest_floor import (FloorContext, GUILDS, author_records,
    authoring_settings, thermal_band_weight, understory_weight, validate_document)


def _context(cover=.45, valid=1, *, thermal_distance=10., slope=5., protected=False):
    shape = (100, 100)
    cells = [{"id": f"cell_{i}_{j}", "ix": i, "iz": j, "canopy_cover_fraction": cover,
              "valid_fraction": valid} for j in range(5) for i in range(5)]
    coverage = {"schema": "yellowstone.canopy_coverage.v1", "status": "derived_not_field_validated",
                "extent_m": [0, 0, 50, 50], "cell_size_m": 10, "cells": cells}
    return FloorContext(coverage, {"route_clearance": np.full(shape, protected)},
        np.ones(shape, dtype=bool), np.full(shape, thermal_distance), np.full(shape, 100.),
        lambda x, z: 10 + .01 * x + .02 * z, lambda x, z: slope, lambda x, z: .3, 120.)


def _document(records, options=None):
    return {"schema": "yellowstone.forest_floor.v1", "status": "authored",
            "scientific_acceptance": "not_yet_accepted", "quantitative_uncertainty": "unknown",
            "records": records, "authoring_choices": {key: {"value": value, "status": "authored", "uncertainty": "unknown"}
                for key, value in authoring_settings(options).items()}}


def test_moderate_canopy_response_is_explicit_authored_and_not_field_density():
    assert understory_weight(0) == understory_weight(.15) == 0
    assert understory_weight(.45) == 1
    assert understory_weight(.75) == understory_weight(1) == 0
    assert understory_weight(.3) == pytest.approx(.5)
    assert thermal_band_weight(0) == thermal_band_weight(31) == 0
    assert thermal_band_weight(3) == 1


def test_reproducible_records_use_real_terrain_and_named_authored_guilds():
    context = _context()
    before = copy.deepcopy(context.coverage)
    records, diagnostics = author_records(context)
    repeated, repeated_diagnostics = author_records(context)
    assert records == repeated and diagnostics == repeated_diagnostics
    assert context.coverage == before
    assert validate_document(_document(records), context)
    assert {r["guild"] for r in records if r["kind"] == "understory_card"} == set(GUILDS)
    for record in records:
        x, y, z = record["position"]
        assert y == context.terrain(x, z)
        assert record["evidence_class"] == "authored"
        assert record["species_presence_class"] == "authored_representative"
        if record["kind"] == "snag":
            assert record["support"]["thermal_band"] is True
            assert record["height_m"] == record["size"][1]
            assert record["dbh_m"] == record["size"][0] == record["size"][2]
            assert record["crown_ratio"] == 0


def test_canopy_support_and_slope_exclusions_cannot_be_filled_by_authoring():
    for context in [_context(valid=.9), _context(slope=42), _context(protected=True)]:
        assert author_records(context)[0] == []
    context = _context()
    context.supported[:] = False
    assert author_records(context)[0] == []


def test_snags_only_appear_in_authored_forest_side_thermal_band():
    near, _ = author_records(_context())
    far, _ = author_records(_context(thermal_distance=80), {"log_display_probability": 1.})
    assert any(r["kind"] == "snag" for r in near)
    assert not any(r["kind"] == "snag" for r in far)
    assert any(r["kind"] == "log" for r in far)
    cold = _context()
    cold.apron_heat = .3
    assert not any(r["kind"] == "snag" for r in author_records(cold)[0])


def test_understory_occurrence_changes_with_supported_cover_without_inventing_stems():
    moderate, _ = author_records(_context(cover=.45, thermal_distance=80))
    closed, _ = author_records(_context(cover=.95, thermal_distance=80))
    assert any(r["kind"] == "understory_card" for r in moderate)
    assert not any(r["kind"] == "understory_card" for r in closed)
    assert not any(r["kind"] == "pine" for r in moderate + closed)


def test_display_budgets_bound_each_primitive_family():
    options = {"max_understory_cards": 3, "max_snags": 2, "max_logs": 1}
    records, diagnostics = author_records(_context(), options)
    assert diagnostics["counts"] == {"understory_card": 3, "snag": 2, "log": 1}
    assert validate_document(_document(records, options))


@pytest.mark.parametrize("setting,invalid", [("seed", True), ("seed", "12"), ("max_logs", 1.5),
    ("candidate_spacing_m", np.nan), ("thermal_band_outer_m", np.inf), ("moderate_cover_low", -.1)])
def test_public_authoring_numbers_reject_non_numeric_or_invalid_values(setting, invalid):
    with pytest.raises(ValueError):
        authoring_settings({setting: invalid})


def test_field_class_guards_reject_claimed_species_or_calibration_and_fake_snag_bands():
    records, _ = author_records(_context())
    doc = _document(records)
    for key, value in [("status", "measured"), ("scientific_acceptance", "accepted"),
                        ("quantitative_uncertainty", "known")]:
        invalid = copy.deepcopy(doc)
        invalid[key] = value
        with pytest.raises(ValueError):
            validate_document(invalid)
    invalid = copy.deepcopy(doc)
    invalid["records"][0]["evidence_class"] = "measured"
    with pytest.raises(ValueError, match="species"):
        validate_document(invalid)
    invalid = copy.deepcopy(doc)
    invalid["authoring_choices"]["seed"]["status"] = "fitted"
    with pytest.raises(ValueError, match="calibrated"):
        validate_document(invalid)
    invalid = copy.deepcopy(doc)
    snag = next(r for r in invalid["records"] if r["kind"] == "snag")
    snag["support"]["apron_distance_m"] = 80
    with pytest.raises(ValueError, match="outside"):
        validate_document(invalid)


def test_log_endpoints_follow_real_terrain_and_preserve_center_coordinates():
    records, _ = author_records(_context())
    logs = [r for r in records if r["kind"] == "log"]
    assert logs
    for record in logs:
        a, b = record["end_positions"]
        assert (a[0] + b[0]) / 2 == pytest.approx(record["position"][0])
        assert (a[2] + b[2]) / 2 == pytest.approx(record["position"][2])
        for x, y, z in [a, b]:
            assert y == _context().terrain(x, z)


def test_observed_support_field_requires_its_actual_unvalidated_source_class():
    context = _context()
    bad = copy.deepcopy(context.coverage)
    bad["status"] = "authored"
    with pytest.raises(ValueError, match="unvalidated"):
        FloorContext(bad, context.masks, context.supported, context.apron_distance,
                     context.clearance, context.terrain, context.slope, context.heat_sampler, 120.)
