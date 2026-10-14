"""Tests for the ssurgo MT628 loader against a synthetic tabular fixture."""
from __future__ import annotations

import pytest

from yellowstone_python.land.ssurgo_loader import CHORIZON_IDX, COMPONENT_IDX, MT628_SURVEY_AREA, MAPUNIT_IDX, SOIL_TUPLE_FIELDS, SSURGOError, load_ssurgo_soils, to_hydrosim_soils_table


def _row(indices: dict, values: dict, width: int = 200) -> str:
    cells = [""] * width
    for key, idx in indices.items():
        if key in values:
            if idx >= width:
                raise ValueError("index exceeds synthetic row width")
            cells[idx] = str(values[key])
    return "|".join(cells)


def _write_fixture(tmp_path):
    comp_path = tmp_path / "comp.txt"
    chorizon_path = tmp_path / "chorizon.txt"
    mapunit_path = tmp_path / "mapunit.txt"
    mapunit_rows = [
        _row(MAPUNIT_IDX, {
            "musym": "APR",
            "muname": "Sinter apron complex",
            "mukey": "901001",
        }),
    ]
    comp_rows = [
        _row(COMPONENT_IDX, {
            "comppct_r": "80",
            "compname": "Sinter_apron",
            "majcompflag": "Yes",
            "cokey": "co-sinter",
            "mukey": "901001",
        }),
        _row(COMPONENT_IDX, {
            "comppct_r": "20",
            "compname": "Minor_filler",
            "majcompflag": "No",
            "cokey": "co-minor",
            "mukey": "901001",
        }),
    ]
    chorizon_rows = [
        _row(CHORIZON_IDX, {
            "hzdept_r": "0",
            "hzdepb_r": "15",
            "hzthk_r": "15",
            "wsatiated_r": "0.10",
            "wthirdbar_r": "0.05",
            "wfifteenbar_r": "0.02",
            # Saturated Ks in um/s (0.0556 um/s = 0.2 mm/h; halved by Bouwer = 0.1 mm/h).
            "ksat_r": "0.0555556",
            "cokey": "co-sinter",
        }),
        _row(CHORIZON_IDX, {
            "hzdept_r": "15",
            "hzdepb_r": "40",
            "hzthk_r": "25",
            "wsatiated_r": "0.10",
            "wthirdbar_r": "0.05",
            "wfifteenbar_r": "0.02",
            "ksat_r": "0.0555556",
            "cokey": "co-sinter",
        }),
        _row(CHORIZON_IDX, {
            "hzdept_r": "0",
            "hzdepb_r": "40",
            "hzthk_r": "40",
            "wsatiated_r": "0.20",
            "wthirdbar_r": "0.10",
            "wfifteenbar_r": "0.05",
            "ksat_r": "0.027778",
            "cokey": "co-minor",
        }),
    ]
    comp_path.write_text("\n".join(comp_rows) + "\n", encoding="utf-8")
    chorizon_path.write_text("\n".join(chorizon_rows) + "\n", encoding="utf-8")
    mapunit_path.write_text("\n".join(mapunit_rows) + "\n", encoding="utf-8")
    return tmp_path


def test_load_requires_both_tables(tmp_path):
    (tmp_path / "comp.txt").write_text("", encoding="utf-8")
    with pytest.raises(SSURGOError):
        load_ssurgo_soils(tmp_path)


def test_load_skips_non_major_components(tmp_path):
    root = _write_fixture(tmp_path)
    soils = load_ssurgo_soils(root)
    assert "sinter_apron" in soils
    assert "minor_filler" not in soils


def test_tuple_matches_hydrosim_shape(tmp_path):
    root = _write_fixture(tmp_path)
    soils = load_ssurgo_soils(root)
    tup = soils["sinter_apron"]["tuple"]
    assert len(tup) == len(SOIL_TUPLE_FIELDS)
    porosity, suction_mm, ks_mm_h, theta_fc, theta_wp = tup
    assert porosity == pytest.approx(0.10)
    assert theta_fc == pytest.approx(0.05)
    assert theta_wp == pytest.approx(0.02)
    # Fixture Ks=0.0555556 um/s per horizon gives 0.1 mm/h under Bouwer's half-K convention.
    assert ks_mm_h == pytest.approx(0.1, abs=1e-3)
    # Suction psi is not derivable from chorizon; it stays zero until a texture class supplies it.
    assert suction_mm == 0.0


def test_to_hydrosim_soils_table_shape(tmp_path):
    root = _write_fixture(tmp_path)
    soils = load_ssurgo_soils(root)
    table = to_hydrosim_soils_table(soils)
    assert set(table.keys()) == {"sinter_apron"}
    assert len(table["sinter_apron"]) == 5


def test_survey_area_metadata_documented():
    assert MT628_SURVEY_AREA["survey_area_id"] == "MT628"
    assert MT628_SURVEY_AREA["state"] == "MT"
    assert MT628_SURVEY_AREA["status"].startswith(
        "dataset_not_present_on_this_machine")
