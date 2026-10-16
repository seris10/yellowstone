"""Offline unit tests for tools/fetch_yellowstone_tributaries.py. Covers _evidence.v1."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from yellowstone_python.observations import tributaries as FYT


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    """Provide an isolated tributary registry for each test."""
    monkeypatch.setattr(FYT, "VERIFIED_TRIBUTARY_REGISTRY", {})


def test_lookup_identity_unverified_when_missing_from_registry():
    """a site with no registry entry is unverified."""
    identity = FYT.lookup_verified_identity("0000", "Example Creek")
    assert identity["association_status"] == "unverified"
    assert "registry" in identity["association_reason"].lower()


def test_lookup_identity_rejected_when_name_mismatch():
    """a site_id reused on a different stream is rejected."""
    FYT.VERIFIED_TRIBUTARY_REGISTRY["06036805"] = {
        "stream_name": "Firehole River",
        "target_river_id": "river_main",
        "association_method": "manual_review",
    }
    identity = FYT.lookup_verified_identity("06036805", "Totally Other Creek")
    assert identity["association_status"] == "rejected"


def test_lookup_identity_verified_when_name_matches():
    """a matching registry entry becomes verified."""
    FYT.VERIFIED_TRIBUTARY_REGISTRY["12345678"] = {
        "stream_name": "Fictional Creek",
        "target_river_id": "river_firehole",
        "association_method": "world_endpoint_topology",
        "confluence_s_m": 1234.5,
    }
    identity = FYT.lookup_verified_identity("12345678", "Fictional Creek")
    assert identity["association_status"] == "verified"
    assert identity["target_river_id"] == "river_firehole"


def test_validate_series_pairs_flags_duplicates_and_non_monotonic():
    """duplicate and backwards timestamps are reported."""
    pairs = [[1.0, 10.0], [2.0, 11.0], [2.0, 11.1], [1.5, 10.5]]
    report = FYT.validate_series_pairs(pairs, "temperature_c")
    assert report["duplicate_timestamps"] == 1
    assert report["non_monotonic"] == 1
    assert report["strictly_increasing"] is False
    clean = FYT.validate_series_pairs(
        [[1.0, 10.0], [2.0, 11.0]], "temperature_c"
    )
    assert clean["strictly_increasing"] is True


def test_compute_coverage_reports_span_and_gaps():
    """coverage block captures span and max gap."""
    pairs = [[0.0, 1.0], [900.0, 2.0], [1800.0, 3.0]]
    cov = FYT.compute_coverage(pairs, window_s=3600.0)
    assert cov["n_points"] == 3
    assert cov["start_epoch_unix"] == 0.0
    assert cov["end_epoch_unix"] == 1800.0
    assert cov["nominal_interval_s"] == 900.0
    assert cov["max_gap_s"] == 900.0
    assert cov["coverage_fraction"] == pytest.approx(0.5)


def test_compute_coverage_empty_series():
    """empty series yields coverage_fraction=0 without crash."""
    cov = FYT.compute_coverage([], window_s=3600.0)
    assert cov["n_points"] == 0
    assert cov["coverage_fraction"] == 0.0
    assert cov["max_gap_s"] is None


def test_validate_confluence_chainages_outside_channel():
    """a chainage outside [0, length] is flagged."""
    records = [
        {"site_id": "a", "name": "A", "confluence_s_m": -5.0},
        {"site_id": "b", "name": "B", "confluence_s_m": 1200.0},
        {"site_id": "c", "name": "C", "confluence_s_m": 3500.0},
    ]
    report = FYT.validate_confluence_chainages(records, 2000.0)
    statuses = {r["site_id"]: r["confluence_status"] for r in report}
    assert statuses["a"] == "outside_modeled_channel"
    assert statuses["b"] == "within_modeled_channel"
    assert statuses["c"] == "outside_modeled_channel"


def test_validate_confluence_chainages_without_world():
    """missing world yields unchecked_no_world."""
    records = [{"site_id": "a", "name": "A", "confluence_s_m": 100.0}]
    report = FYT.validate_confluence_chainages(records, None)
    assert report[0]["confluence_status"] == "unchecked_no_world"


def test_fetch_usgs_site_data_timestamp_offset_preserved(monkeypatch):
    """an offset-aware ISO stamp preserves its tzinfo."""
    sample = {
        "value": {
            "timeSeries": [
                {
                    "variable": {
                        "variableCode": [{"value": "00010"}]
                    },
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "15.0",
                                    "dateTime": "2026-07-01T12:00:00-06:00",
                                    "qualifiers": ["A"],
                                },
                                {
                                    "value": "16.0",
                                    "dateTime": "2026-07-01T13:00:00-06:00",
                                    "qualifiers": ["P"],
                                },
                            ]
                        }
                    ],
                }
            ]
        }
    }

    class FakeResponse:
        headers = {"Content-Length": "100"}

        def __init__(self, payload):
            import json
            self._bytes = json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self._bytes

    def fake_urlopen(req, timeout=0):
        return FakeResponse(sample)

    monkeypatch.setattr(FYT, "logger", FYT.logger)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    rate = FYT.USHSDelayedRateLimiter(max_requests_per_minute=60)
    errs = FYT.USHSErrorHandler(max_retries=1, base_delay=0.0)

    result = FYT.fetch_usgs_site_data("06036805", 7, rate, errs)
    assert result is not None
    temp_series = result["series"]["temperature_c"]
    assert len(temp_series) == 2
    first_epoch = temp_series[0][0]
    expected = datetime(
        2026, 7, 1, 18, 0, 0, tzinfo=timezone.utc
    ).timestamp()
    assert abs(first_epoch - expected) < 1.0, first_epoch
    quality = result["quality"]["temperature_c"]
    assert quality["qualifier_counts"]["A"] == 1
    assert quality["qualifier_counts"]["P"] == 1
    assert quality["provisional_count"] == 1


def test_analyze_usgs_data_conditioned_on_hot_lowflow():
    """cold fraction counts tributary samples near hot/low-flow mainstem times."""
    temp = [[0.0, 11.0], [3600.0, 11.5], [7200.0, 12.0], [10800.0, 11.8]]
    tributary = {
        "series": {"temperature_c": temp, "discharge_m3_s": [[0.0, 1.0]]},
        "quality": {},
    }
    mainstem = {
        "temperature_c": [
            [0.0, 20.0],  # below hot threshold
            [3600.0, 25.0],  # qualifies
            [7200.0, 26.0],  # qualifies
            [10800.0, 22.0],  # below hot threshold
        ],
        "discharge_m3_s": [
            [0.0, 2.5],
            [3600.0, 2.5],
            [7200.0, 2.9],
            [10800.0, 2.4],
        ],
    }
    analysis = FYT.analyze_usgs_data(
        tributary,
        mainstem_pairs=mainstem,
        criterion=FYT.HOT_LOWFLOW_CRITERION,
        window_s=14400.0,
    )
    assert analysis["temperature_data_available"] is True
    cond = analysis["condition"]
    assert cond["status"] in {
        "measured_window_hot_lowflow_coincidence",
        "no_hot_lowflow_match_full_window_used",
    }
    assert analysis["n_qualified_observations"] == 2


def test_analyze_usgs_data_no_mainstem_marks_full_window():
    """Report missing mainstem data in the condition status."""
    tributary = {
        "series": {"temperature_c": [[0.0, 11.0], [3600.0, 12.0]]},
        "quality": {},
    }
    analysis = FYT.analyze_usgs_data(
        tributary,
        mainstem_pairs=None,
        criterion=FYT.HOT_LOWFLOW_CRITERION,
        window_s=86400.0,
    )
    assert analysis["condition"]["status"].startswith(
        "mainstem_series_not_provided"
    ) or analysis["condition"]["status"] == "no_hot_lowflow_match_full_window_used"


def test_generate_tributary_data_marks_unverified_and_schema(monkeypatch):
    """unverified sites stay out of candidates; schema is v1."""

    def no_fetch(site_id, days, rate_limiter, error_handler):
        return None

    monkeypatch.setattr(FYT, "fetch_usgs_site_data", no_fetch)
    data = FYT.generate_tributary_data(days=1, world_path=None)
    assert data["schema"] == "yellowstone.tributary_evidence.v1"
    assert data["cold_refuge_candidates"] == []
    assert data["solver_sources"] == []
    assert data["landscape_pockets"] == []
    assert data["summary"]["unverified"] == data["summary"]["total_tributaries_queried"]
    assert "records" in data
    for record in data["records"]:
        assert record["association_status"] in {"unverified", "rejected"}


def test_generate_tributary_data_promotes_verified_measured_sites(monkeypatch):
    """verified + measured sites appear as solver_sources and pockets."""
    FYT.VERIFIED_TRIBUTARY_REGISTRY["07057925"] = {
        "stream_name": "Little Firehole River at Grant Village",
        "target_river_id": "river_firehole",
        "association_method": "manual_review",
    }
    temp_pairs = [[1000.0, 11.0], [2000.0, 11.5], [3000.0, 12.0]]
    discharge_pairs = [[1000.0, 1.2], [2000.0, 1.3], [3000.0, 1.1]]

    def fake_fetch(site_id, days, rate_limiter, error_handler):
        if site_id == "07057925":
            return {
                "site_id": site_id,
                "url": "test://",
                "series": {
                    "temperature_c": temp_pairs,
                    "discharge_m3_s": discharge_pairs,
                },
                "quality": {
                    "temperature_c": {
                        "qualifier_counts": {"A": 3},
                        "provisional_count": 0,
                        "provisional_fraction": 0.0,
                    },
                    "discharge_m3_s": {
                        "qualifier_counts": {"A": 3},
                        "provisional_count": 0,
                        "provisional_fraction": 0.0,
                    },
                },
                "integrity_hash": "test-hash",
            }
        return None

    monkeypatch.setattr(FYT, "fetch_usgs_site_data", fake_fetch)
    data = FYT.generate_tributary_data(days=1, world_path=None)
    verified_ids = {s["id"] for s in data["solver_sources"]}
    assert "07057925" in verified_ids
    pocket_ids = {p["id"] for p in data["landscape_pockets"]}
    assert "pocket_07057925" in pocket_ids
    candidate_ids = {c["id"] for c in data["cold_refuge_candidates"]}
    assert "07057925" in candidate_ids


def test_candidate_catalog_is_renamed_and_provenance_recorded(monkeypatch):
    """S4: load_unverified_tributary_candidates names what it returns, and the document records provenance."""
    assert hasattr(FYT, "load_unverified_tributary_candidates")
    assert "Lower Mississippi" in FYT.UNVERIFIED_CANDIDATE_PROVENANCE


    def no_fetch(site_id, days, rate_limiter, error_handler):
        return None

    monkeypatch.setattr(FYT, "fetch_usgs_site_data", no_fetch)
    data = FYT.generate_tributary_data(days=1, world_path=None)
    assert data["provenance"]["candidate_catalog"] == (
        FYT.UNVERIFIED_CANDIDATE_PROVENANCE
    )


def test_consumer_shape_backward_compatibility(monkeypatch):
    """verified records keep the top-level keys the consumer reads."""
    FYT.VERIFIED_TRIBUTARY_REGISTRY["07057925"] = {
        "stream_name": "Little Firehole River at Grant Village",
        "target_river_id": "river_firehole",
        "association_method": "manual_review",
    }

    def fake_fetch(site_id, days, rate_limiter, error_handler):
        if site_id == "07057925":
            return {
                "site_id": site_id,
                "url": "test://",
                "series": {
                    "temperature_c": [[1.0, 11.5], [2.0, 11.8]],
                    "discharge_m3_s": [[1.0, 1.2], [2.0, 1.3]],
                },
                "quality": {
                    "temperature_c": {"qualifier_counts": {}, "provisional_fraction": 0.0, "provisional_count": 0},
                    "discharge_m3_s": {"qualifier_counts": {}, "provisional_fraction": 0.0, "provisional_count": 0},
                },
                "integrity_hash": "h",
            }
        return None

    monkeypatch.setattr(FYT, "fetch_usgs_site_data", fake_fetch)
    data = FYT.generate_tributary_data(days=1, world_path=None)
    candidates = data["cold_refuge_candidates"]
    assert candidates, "verified + measured site should be a candidate"
    first = candidates[0]
    assert "confluence_s_m" in first
    assert "temperature_c" in first
    assert "discharge_m3s" in first


def test_world_source_path_is_project_relative(monkeypatch, tmp_path, repo_root):
    monkeypatch.setattr(FYT, "fetch_usgs_site_data", lambda *args: None)
    world = tmp_path / "missing_world.json"
    data = FYT.generate_tributary_data(days=1, world_path=world)
    recorded = data["world_path"]
    assert not __import__("pathlib").Path(recorded).is_absolute()
    assert (repo_root / recorded).resolve() == world.resolve()
