"""Offline tests for the firehole_obs assembler."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
from yellowstone_python.observations import assembly as AFO
from yellowstone_python.observations import bundles as OIO
from yellowstone_python.observations import usgs as NWIS


def _write_hashed(path: Path, document: dict) -> dict:
    """Write document with embedded hash and return the on-disk form."""
    OIO.atomic_write_json(path, document)
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_site(site_id: str, offset: float) -> dict:
    """Minimal normalized usgs_nwis artifact for one site."""
    base_epoch = 1_700_000_000.0 + offset
    return {
        "schema": NWIS.SCHEMA_NORMALIZED,
        "site_id": site_id,
        "site": {"site_no": site_id, "name": f"stub-{site_id}",
                 "latitude": 44.5, "longitude": -110.8},
        "site_metadata_provenance": {"source": "test_fixture",
                                     "status": "requires_verification"},
        "retrieved_at_utc": "2026-10-12T00:00:00Z",
        "series": {
            "temperature_c": [
                [base_epoch, 7.1],
                [base_epoch + 900.0, 7.3],
                [base_epoch + 1800.0, 7.5],
            ],
            "discharge_m3_s": [
                [base_epoch, 1.2],
                [base_epoch + 900.0, 1.25],
                [base_epoch + 1800.0, 1.3],
            ],
        },
        "series_units": {"temperature_c": "degC",
                         "discharge_m3_s": "m3/s"},
        "series_quality_status": {
            "temperature_c": ["approved", "estimated", "provisional"],
            "discharge_m3_s": ["approved", "approved", "approved"],
        },
        "series_source": {
            "discharge_m3_s": {"source_units": "ft3/s",
                               "conversion": NWIS.CFS_TO_M3S},
            "temperature_c": {"source_units": "degC", "conversion": 1.0},
        },
        "measurements": {"records": [], "units": {},
                         "status": "not_requested", "quality": None},
        "quality": {"status": "usable_for_screening"},
        "warnings": [],
        "provenance": {"normalized_from": NWIS.SCHEMA_RAW},
    }


def _met_doc() -> dict:
    rows = [[1_700_000_000.0, 10.0, 0.6, 2.0, 400.0, 0.3],
            [1_700_003_600.0, 11.0, 0.55, 2.5, 420.0, 0.25]]
    return {
        "schema": "yellowstone.met_forcing.v1",
        "status": "model_output_not_observation",
        "hourly": rows,
        "columns": ["epoch_unix", "air_c", "rh", "wind_mps",
                    "shortwave_w_m2", "cloud"],
        "units": {"air_c": "degC", "rh": "0..1", "wind_mps": "m/s",
                  "shortwave_w_m2": "W/m2", "cloud": "0..1"},
        "elevation_m": 2200.0,
        "provider_timezone": "UTC",
    }


def test_assemble_round_trip(tmp_path):
    up = _write_hashed(tmp_path / "usgs_up.json",
                       _normalized_site("06036805", 0.0))
    down = _write_hashed(tmp_path / "usgs_down.json",
                         _normalized_site("06036905", 10.0))
    met = _write_hashed(tmp_path / "met.json", _met_doc())
    assert OIO.verify_artifact_hash(up)
    assert OIO.verify_artifact_hash(down)
    assert OIO.verify_artifact_hash(met)

    bundle = AFO.assemble(
        [tmp_path / "usgs_up.json", tmp_path / "usgs_down.json"],
        tmp_path / "met.json")
    assert bundle["schema"] == AFO.FIREHOLE_SCHEMA
    assert set(bundle["sites"]) == {"06036805", "06036905"}

    up_site = bundle["sites"]["06036805"]
    # Default filter removes estimated and flagged_conditions rows.
    assert len(up_site["series"]["temperature_c"]) == 2
    assert len(up_site["series"]["discharge_m3_s"]) == 3
    assert up_site["quality_filtering"]["temperature_c"]["excluded"] == 1

    assert bundle["met"]["kind"] == "model_forcing"
    assert bundle["met"]["schema"] == "yellowstone.met_forcing.v1"

    # Shape checks match validate_usgs_bundle: epoch, discharge and temperature pair layout per site, and a six-column met.hourly row. The call itself is not run here because unrelated UNIT_DOC entries are missing in the cross-module registry (handoff for cluster E1).
    for site_record in bundle["sites"].values():
        for pair in site_record["series"]["discharge_m3_s"]:
            assert len(pair) == 2
            assert isinstance(pair[0], (int, float))
            assert pair[1] >= 0.0
        for pair in site_record["series"]["temperature_c"]:
            assert len(pair) == 2
            assert isinstance(pair[1], (int, float))
    for row in bundle["met"]["hourly"]:
        assert len(row) == 6


def test_assemble_refuses_tampered_input(tmp_path):
    doc = _normalized_site("06036805", 0.0)
    OIO.atomic_write_json(tmp_path / "usgs.json", doc)
    tampered = json.loads((tmp_path / "usgs.json").read_text(encoding="utf-8"))
    tampered["series"]["temperature_c"][0][1] = 99.0
    (tmp_path / "usgs.json").write_text(json.dumps(tampered), encoding="utf-8")
    OIO.atomic_write_json(tmp_path / "met.json", _met_doc())
    with pytest.raises(ValueError, match="does not match"):
        AFO.assemble([tmp_path / "usgs.json"], tmp_path / "met.json")


def test_assemble_requires_normalized_schema(tmp_path):
    doc = _normalized_site("06036805", 0.0)
    doc["schema"] = "wrong.schema"
    OIO.atomic_write_json(tmp_path / "usgs.json", doc)
    OIO.atomic_write_json(tmp_path / "met.json", _met_doc())
    with pytest.raises(ValueError, match="SCHEMA|usgs_site_observations"):
        AFO.assemble([tmp_path / "usgs.json"], tmp_path / "met.json")


def test_assemble_rejects_duplicate_site(tmp_path):
    OIO.atomic_write_json(tmp_path / "a.json", _normalized_site("06036805", 0.0))
    OIO.atomic_write_json(tmp_path / "b.json", _normalized_site("06036805", 100.0))
    OIO.atomic_write_json(tmp_path / "met.json", _met_doc())
    with pytest.raises(ValueError, match="duplicate site_id"):
        AFO.assemble([tmp_path / "a.json", tmp_path / "b.json"],
                     tmp_path / "met.json")
