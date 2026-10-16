"""Tests for llm_backend: snapshot shape, zone math, compare, propose dry-run."""

import pytest
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from yellowstone_python.service.llm_backend import Backend, _Handler



def _backend():
    return Backend()


def test_snapshot_shape():
    backend = _backend()
    roster = json.loads((backend.world / "data/ecosystem.json").read_text())["wildlife"]
    snap = backend.snapshot()
    assert snap["contract"] == "yellowstone.llm_snapshot.v1"
    assert snap["world_id"] == "yellowstone_midway"
    assert snap["census"]["n"] > 30000
    assert "overlook_knoll_r120" in snap["census"]["zones"]
    assert snap["placements"]["baked_trees"] > 30000
    assert snap["ecosystem"]["wildlife_total"] == len(roster)
    assert any("LiDAR" in n for n in snap["accuracy_notes"])
    assert any("unknown" in n for n in snap["accuracy_notes"])


def test_zones_match_census_module():
    from yellowstone_python.census.canopy_census import density_stats
    b = _backend()
    assert b.zones() == density_stats(b.census()["trees"],
                                      __import__(
                                          "yellowstone_python.service.llm_backend",
                                          fromlist=["ZONES"]).ZONES)


def test_compare_math():
    out = _backend().compare(-252.0, 159.0, 120.0)
    assert out["observed_census"]["n"] >= 1000  # knoll is forested
    assert out["area_ha"] > 4.0
    assert (out["deficit_observed_minus_placed"]
            == out["observed_census"]["n"] - out["placed_game"]["n"])


def test_radius_validation():
    import pytest
    b = _backend()
    for bad in (0, -5, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            b.circle_stats([], 0, 0, bad)
        with pytest.raises(ValueError):
            b.compare(0, 0, bad)


def test_propose_rejects_out_of_world():
    import pytest
    b = _backend()
    with pytest.raises(ValueError):
        b.propose("lodgepole_pine", 99999, 99999, 30, 3)
    with pytest.raises(ValueError):
        b.propose("lodgepole_pine", 0, -5000, 30, 3)
    # Edge of the baked square is still legal.
    out = b.propose("lodgepole_pine", -360, 260, 30, 1, seed=7)
    assert len(out["review_accepted"]) <= 1


def test_propose_dry_run_no_writes():
    before = json.load(open(DATA / "placement_overrides.json"))
    out = _backend().propose("lodgepole_pine", -360, 260, 30, 5, seed=7)
    assert len(out["review_accepted"]) <= 5
    assert all(r["stable_id"].startswith("prop_lodgepole_pine_7_")
               for r in out["proposals"])
    after = json.load(open(DATA / "placement_overrides.json"))
    assert before == after  # propose must not write


def test_http_endpoints():
    _Handler.backend = _backend()
    roster = json.loads((_Handler.backend.world / "data/ecosystem.json").read_text())["wildlife"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def get(path):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
                return json.load(r)
        assert "endpoints" in get("/api")
        assert get("/api/census/zones")["overlook_knoll_r120"]["n"] >= 1000
        assert get("/api/compare?x=-252&z=159&r=120")["area_ha"] > 4.0
        assert get("/api/placements/summary")["baked_trees"] > 30000
        assert get("/api/ecosystem/summary")["wildlife_total"] == len(roster)
        # /api/weather returns schema_version 2 nested shape and flat aliases for older callers.
        w = get("/api/weather")
        assert w["schema_version"] == 2
        assert isinstance(w["generated_at_unix"], int)
        assert isinstance(w["valid_time_unix"], int)
        assert isinstance(w["simulation_time_unix"], int)
        assert isinstance(w["source"], dict)
        assert w["source"]["endpoint"] in (
            "open-meteo_hourly_bundle", "authored_defaults")
        for k in ("air_temperature_c", "relative_humidity",
                  "wind_speed_mps", "wind_direction_deg",
                  "cloud_fraction", "precipitation_rate_mm_h",
                  "snow_fraction", "visibility_m"):
            assert k in w["weather"], f"nested weather missing {k}"
        assert "air_c" in w and "humidity" in w and "cloud" in w
        assert isinstance(w["wind_xz_mps"], list) and len(w["wind_xz_mps"]) == 2
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/density?x=0&z=0&r=0")
            raise AssertionError("r=0 should not return 200")
        except urllib.error.HTTPError as e:
            assert e.code == 400
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/propose",
            data=json.dumps({"guild": "lodgepole_pine", "x": -360,
                             "z": 260, "radius_m": 30, "count": 3}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            assert len(json.load(r)["review_accepted"]) <= 3
    finally:
        server.shutdown()
        thread.join()


def test_threshold_and_canopy_validated():
    import math
    import pytest
    b = _backend()
    # Non-finite or out-of-range thresholds raise ValueError on the suitability gate.
    for bad_thresh in (float("nan"), float("inf"), -1.0, 2.0):
        with pytest.raises(ValueError):
            b.propose("lodgepole_pine", -360, 260, 30, 1,
                      suitability_threshold=bad_thresh)
    for bad_canopy in (float("nan"), float("inf"), -0.5, 1.5):
        with pytest.raises(ValueError):
            b.propose("lodgepole_pine", -360, 260, 30, 1, canopy=bad_canopy)
    with pytest.raises(ValueError):
        b.propose("lodgepole_pine", -360, 260, 30, 1,
                  habitat_id="NOT_A_HABITAT")
    # Bools are not numbers/locations.
    with pytest.raises(ValueError):
        b.propose("lodgepole_pine", True, 260, 30, 1)
    with pytest.raises(ValueError):
        b.propose("lodgepole_pine", -360, 260, 30, True)
    with pytest.raises(ValueError):
        b.circle_stats([(0, 0)], True, 0, 5)
    # int(inf) overflow paths raise ValueError.
    with pytest.raises(ValueError):
        b.propose("lodgepole_pine", -360, 260, 30, 1, seed=float("inf"))
    with pytest.raises(ValueError):
        b.propose("lodgepole_pine", -360, 260, 30, float("inf"))
    assert math.isfinite(
        b.propose("lodgepole_pine", -360, 260, 30, 1)["proposals"][0]["x"])


def test_circle_stats_radius_bounds():
    import pytest
    for bad in (1e-9, 1e-200, 1e200, 1e9, 0.05, 6000):
        with pytest.raises(ValueError):
            Backend.circle_stats([(0, 0)], 0, 0, bad)
        with pytest.raises(ValueError):
            _backend().compare(0, 0, bad)


def test_compare_returns_numeric_center():
    out = _backend().compare("-252", "159", "120")
    assert out["center_xz"] == [-252.0, 159.0]
    assert isinstance(out["radius_m"], float)
    assert out["area_ha"] == 4.5239


def test_zone_numbers_pinned():
    # Frozen USGS crown centers; total stem counts remain unknown.
    zones = _backend().zones()
    assert set(zones) == {"spring_0_50m", "apron_50_100m",
                          "transition_100_200m", "outwash_200_400m",
                          "overlook_knoll_r120", "detail_full"}
    assert zones["overlook_knoll_r120"]["n"] == 1274
    assert zones["overlook_knoll_r120"]["area_ha"] == 4.52
    assert zones["apron_50_100m"]["n"] == 0
    assert zones["detail_full"]["n"] == 34303
    knoll = _backend().compare(-252.0, 159.0, 120.0)
    assert knoll["observed_census"]["n"] == 1274
    assert knoll["placed_game"]["n"] == 1274
    assert knoll["deficit_observed_minus_placed"] == 0
    assert knoll["census_source"]["agency"] == "USGS 3DEP"


def test_compare_matches_bake_override_semantics(tmp_path):
    world = tmp_path / "world"
    derived = tmp_path / "derived"
    (world / "data").mkdir(parents=True)
    derived.mkdir()
    (derived / "census.json").write_text(json.dumps({
        "trees": [{"x": 0, "z": 0}, {"x": 1, "z": 1}]}))
    (world / "data/placements.json").write_text(json.dumps({"trees": [
        {"id": "remove", "position": [0, 0, 0]},
        {"id": "replace", "position": [50, 0, 50]},
    ]}))
    (world / "data/placement_overrides.json").write_text(json.dumps({
        "remove": ["remove"],
        "replace": {"replace": {"kind": "pine", "position": [1, 0, 1]}},
        "add": [{"id": "grass", "kind": "grass", "position": [0, 0, 0]}],
    }))
    comparison = Backend(world=world, derived=derived).compare(0, 0, 10)
    assert comparison["placed_game"]["n"] == 1
    assert comparison["deficit_observed_minus_placed"] == 1
    assert "2022 NAIP" not in comparison["interpretation"]


def test_preserved_rgb_zone_counts():
    from yellowstone_python.census.canopy_census import density_stats
    from yellowstone_python.service.llm_backend import PKG_ROOT, ZONES
    fixture = (PKG_ROOT / "data/authoring_baselines/census_rgb.json")
    if not fixture.is_file():
        pytest.skip("historical RGB fixture missing")
    census = json.loads(fixture.read_text())
    zones = density_stats(census["trees"], ZONES)
    assert zones["overlook_knoll_r120"]["n"] == 1175
    assert zones["apron_50_100m"]["n"] == 63


def test_large_propose_is_bounded():
    import time
    b = _backend()
    t0 = time.monotonic()
    out = b.propose("meadow_grass", -360, 260, 500, 1, seed=7)
    assert time.monotonic() - t0 < 10
    assert len(out["proposal_log"]) < 30000
    assert any("coarsened" in entry.get("reason", "")
               for entry in out["proposal_log"])


def test_http_hardening_statuses():
    import http.client
    _Handler.backend = _backend()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def code(path):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}{path}", timeout=30)
                return 200
            except urllib.error.HTTPError as e:
                return e.code

        def post_code(obj):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/propose",
                data=json.dumps(obj).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code

        assert code("/api/density?x=0&z=0&r=1e-200") == 400
        assert code("/api/density?x=0&z=0&r=1e200") == 400
        assert code("/api/density?x=0&z=0&r=1e-9") == 400
        assert post_code({"guild": "lodgepole_pine", "x": -360, "z": 260,
                          "radius_m": 30, "count": 2, "seed": 1e999}) == 400
        assert post_code({"guild": "lodgepole_pine", "x": -360, "z": 260,
                          "radius_m": 30, "count": 2,
                          "suitability_threshold": float("nan")}) == 400
        assert post_code({"guild": "lodgepole_pine", "x": -360, "z": 260,
                          "radius_m": 30, "count": 2,
                          "habitat_id": "BOGUS"}) == 400
        assert post_code({"guild": "lodgepole_pine", "x": -360, "z": 260,
                          "radius_m": 30, "count": True}) == 400
        assert post_code([1, 2, 3]) == 400
        # Oversize bodies are rejected without being processed.
        big = json.dumps({"guild": "lodgepole_pine", "x": -360, "z": 260,
                          "radius_m": 30, "count": 2,
                          "pad": "x" * (128 * 1024)}).encode()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("POST", "/api/propose", body=big,
                     headers={"Content-Type": "application/json"})
        assert conn.getresponse().status == 413
        conn.close()
    finally:
        server.shutdown()
        thread.join()


def test_snapshot_degrades_section_not_bundle(tmp_path):
    import shutil
    world = tmp_path / "world"
    derived = tmp_path / "derived"
    shutil.copytree(DATA, world / "data", ignore=shutil.ignore_patterns("release.json", "releases"))
    derived.mkdir()
    shutil.copy(CENSUS_JSON, derived / "census.json")
    eco_path = world / "data" / "ecosystem.json"
    eco = json.loads(eco_path.read_text())
    eco["river_reaches"][0].pop("temperature_c")
    eco_path.write_text(json.dumps(eco))
    from yellowstone_python.service.llm_backend import Backend as RealBackend
    snap = RealBackend(world=world, derived=derived).snapshot()
    assert "error" in snap["ecosystem"]
    assert snap["census"]["n"] > 30000  # healthy sections still served


def test_malformed_census_raises_data_error(tmp_path):
    """Adversarial finding #1: a corrupt census.json raises DataError (an empty list reads as '0 trees."""
    import pytest
    from yellowstone_python.service.llm_backend import Backend, DataError
    for label, doc in [
        ("non-numeric x", {"trees": [{"x": "not-a-number", "z": 0}]}),
        ("missing trees key", {"n": 5}),
        ("census is a list", [1, 2, 3]),
        ("trees not a list", {"trees": 5}),
        ("tree missing x", {"trees": [{"z": 0}]}),
        ("tree not an object", {"trees": [5]}),
    ]:
        d = tmp_path / label.replace(" ", "_")
        d.mkdir()
        (d / "census.json").write_text(json.dumps(doc))
        b = Backend(derived=d)
        with pytest.raises(DataError):
            if label == "census is a list":
                b.census()
            else:
                b.census_points()


def test_weather_never_derives_rain_from_cloud(tmp_path):
    """Overcast with no bundle precipitation leaves precipitation_rate at None."""
    import json
    import shutil
    world = tmp_path / "world"
    derived = tmp_path / "derived"
    shutil.copytree(DATA, world / "data", ignore=shutil.ignore_patterns("release.json", "releases"))
    derived.mkdir()
    # Six-column bundle (no precip column); cloud is 1.0 at every row.
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[float(epoch), 10.0, 0.5, 2.0, 150.0, 1.0]
                   for epoch in range(0, 24 * 3600, 3600)],
    }
    (derived / "met.json").write_text(json.dumps(bundle))
    ecosystem_path = world / "data/ecosystem.json"
    ecosystem = json.loads(ecosystem_path.read_text())
    ecosystem["simulation_epoch_unix"] = 21600.
    ecosystem.setdefault("weather", {})["use_met_bundle"] = True
    ecosystem_path.write_text(json.dumps(ecosystem))
    from yellowstone_python.service.llm_backend import Backend
    out = Backend(world=world, derived=derived).weather(hour=0.0)
    assert out["weather"]["cloud_fraction"] == 1.0
    # No seventh column means no measured precip and no cloud-to-rain substitution.
    assert out["precipitation_rate_mm_h"] is None
    assert out["precipitation_status"] == "unavailable"
    assert out["weather"]["precipitation_rate_mm_h"] == 0.0


def test_concurrent_census_reads_share_cache():
    """Multiple threaded Backend.census() calls return the same cached object."""
    from yellowstone_python.service.llm_backend import Backend
    b = Backend()
    seen: list = []
    errors: list = []

    def worker():
        try:
            seen.append(id(b.census()))
        except Exception as exc:  # pragma: no cover (would fail the test)
            errors.append(exc)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(seen) == 8
    assert len(set(seen)) == 1


def test_placed_points_strict_on_schema_violations(tmp_path):
    """placements.json / placement_overrides.json records are validated the same way as census records:."""
    import pytest
    from yellowstone_python.service.llm_backend import Backend, DataError
    for label, place_doc, ov_doc in [
        ("trees not a list", {"trees": 5}, {"add": []}),
        ("tree missing position", {"trees": [{"id": "x"}]}, {"add": []}),
        ("add not a list", {"trees": []}, {"add": 5}),
        ("pine add missing position", {"trees": []}, {"add": [{"kind": "pine"}]}),
    ]:
        d = tmp_path / label.replace(" ", "_")
        (d / "data").mkdir(parents=True)
        (d / "data" / "placements.json").write_text(json.dumps(place_doc))
        (d / "data" / "placement_overrides.json").write_text(json.dumps(ov_doc))
        b = Backend(world=d)
        with pytest.raises(DataError):
            b.placed_points()

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'CENSUS_JSON', resolved_paths['CENSUS_JSON'], raising=False)
    monkeypatch.setattr(module, 'DATA', resolved_paths['DATA'], raising=False)
