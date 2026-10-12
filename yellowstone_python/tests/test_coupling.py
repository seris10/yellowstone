"""Tests for the component coupling contract and pocket resolution."""
import copy

from yellowstone_python.aquatic_foodweb import (
    TRIBUTARY_CANDIDATES,
    append_tributary_cells,
    build_tributary_cell,
    thermal_landscape,
)
from yellowstone_python.coupling import (
    EXCHANGES,
    POCKET_CONSERVATION,
    check_coupling,
    validate_contract,
)
from yellowstone_python.replay.river_transport import make_replay


def _doc():
    config = {
        "boundary_m3_s": 2.0,
        "boundary_c": 15.0,
        "air_c": 9.0,
        "duration_s": 600.0,
        "dt_s": 10.0,
        "sample_s": 60.0,
        "cells": [
            {"id": f"c{i}", "length_m": 50.0, "width_m": 10.0,
             "volume_m3": 550.0, "initial_c": 15.0,
             "exchange_w_m2_k": 12.0}
            for i in range(4)
        ],
        "sources": [
            {"id": "creek", "cell_id": "c1", "flow_m3_s": 0.2,
             "temperature_c": 11.0,
             "status": "illustrative_not_calibrated"},
        ],
    }
    return make_replay(config)


def test_contract_records_are_valid():
    assert validate_contract() == []
    ids = [r["exchange_id"] for r in EXCHANGES]
    assert len(ids) == len(set(ids))
    for record in EXCHANGES:
        assert record["conservation"] in ("conserved", "mapped",
                                          POCKET_CONSERVATION)


def test_pocket_cells_carry_non_conservative_label():
    cell = build_tributary_cell(TRIBUTARY_CANDIDATES[0])
    assert cell["conservation"] == POCKET_CONSERVATION
    assert "tributary_provenance" in cell


def test_check_passes_on_solver_landscape_with_pockets():
    doc = _doc()
    landscape = append_tributary_cells(thermal_landscape(doc))
    result = check_coupling(doc, landscape)
    assert result["passed"], result["failures"]
    assert result["metrics"]["n_pockets"] == 2
    assert result["metrics"]["n_sources"] == 1
    assert result["metrics"]["surface_method"] == "newton_lumped"


def test_check_rejects_unlabeled_pocket():
    doc = _doc()
    landscape = thermal_landscape(doc)
    bad = build_tributary_cell(TRIBUTARY_CANDIDATES[0])
    del bad["conservation"]
    result = check_coupling(doc, landscape + [bad])
    assert not result["passed"]
    assert any("non-conservative" in f for f in result["failures"])


def test_check_rejects_unmapped_cell():
    doc = _doc()
    landscape = thermal_landscape(doc)
    stray = copy.deepcopy(landscape[0])
    stray["id"] = "nowhere_cell"
    result = check_coupling(doc, landscape + [stray])
    assert not result["passed"]
    assert any("nowhere_cell" in f for f in result["failures"])


def test_check_rejects_duplicate_sources():
    doc = _doc()
    doc["forcing"]["sources"].append(
        copy.deepcopy(doc["forcing"]["sources"][0]))
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("duplicate" in f for f in result["failures"])


def test_check_rejects_surface_method_mismatch():
    doc = _doc()
    doc["forcing"]["surface_budget"] = {"rh": {}, "wind_mps": {}}
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("Newton" in f for f in result["failures"])
