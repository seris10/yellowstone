"""Tests for the component coupling contract and pocket resolution."""
import copy

from yellowstone_python.aquatic.aquatic_foodweb import TRIBUTARY_CANDIDATES, append_tributary_cells, build_tributary_cell, thermal_landscape
from yellowstone_python.registry.coupling import EXCHANGES, POCKET_CONSERVATION, PRESCRIBED_INCREMENT, check_coupling, validate_contract
from yellowstone_python.river.hydraulics import thermal_inventory
from yellowstone_python.river.river_transport import make_replay


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
    doc = make_replay(config)
    doc["hydraulics_summary"] = {
        "thermal_inventory": thermal_inventory(doc["forcing"]["sources"]),
    }
    return doc


def test_contract_records_are_valid():
    assert validate_contract() == []
    ids = [r["exchange_id"] for r in EXCHANGES]
    assert len(ids) == len(set(ids))
    for record in EXCHANGES:
        assert record["conservation"] in ("conserved", "mapped",
                                          POCKET_CONSERVATION,
                                          PRESCRIBED_INCREMENT)


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


def test_check_names_missing_thermal_inventory():
    doc = _doc()
    del doc["hydraulics_summary"]
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("missing hydraulics_summary" in f for f in result["failures"])


def test_check_names_absent_thermal_inventory_key():
    doc = _doc()
    doc["hydraulics_summary"] = {}
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("missing thermal_inventory" in f for f in result["failures"])


def test_check_names_empty_thermal_inventory_sources():
    doc = _doc()
    doc["hydraulics_summary"] = {"thermal_inventory": {"sources": []}}
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("empty thermal_inventory sources" in f
               for f in result["failures"])


def test_check_names_missing_final_budget():
    doc = _doc()
    del doc["final_budget"]
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("missing final_budget" in f for f in result["failures"])


def test_check_names_empty_final_budget():
    doc = _doc()
    doc["final_budget"] = {}
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("empty final_budget" in f for f in result["failures"])


def test_check_names_missing_frames():
    doc = _doc()
    landscape = thermal_landscape(doc)
    del doc["frames"]
    result = check_coupling(doc, landscape)
    assert not result["passed"]
    assert any("missing frames" in f for f in result["failures"])


def test_check_names_empty_frames():
    doc = _doc()
    landscape = thermal_landscape(doc)
    doc["frames"] = []
    result = check_coupling(doc, landscape)
    assert not result["passed"]
    assert any("empty frames" in f for f in result["failures"])


def test_check_names_missing_forcing_sources():
    doc = _doc()
    del doc["forcing"]["sources"]
    result = check_coupling(doc, thermal_landscape(doc))
    assert not result["passed"]
    assert any("missing forcing.sources" in f for f in result["failures"])
