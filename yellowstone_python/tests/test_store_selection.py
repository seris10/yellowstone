"""Analysis-store selection against published build and census bindings."""
import hashlib
import json
import os
import sqlite3

from yellowstone_python.service.llm_backend import Backend


def context(tmp_path):
    world = tmp_path / "world"
    derived = tmp_path / "derived"
    (world / "data").mkdir(parents=True)
    derived.mkdir()
    (world / "data/ecosystem.json").write_text(json.dumps({"build_id": "published"}))
    census = derived / "census.json"
    census.write_text(json.dumps({"trees": [{"x": 0, "z": 0, "crown_r_m": 1}]}))
    return Backend(world=world, derived=derived), census


def store(derived, name, build_id, census_sha=None):
    path = derived / f"analysis_{name}.sqlite"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE meta(build_id TEXT, source_shas TEXT)")
        sources = {"census": {"sha256": census_sha}} if census_sha else {}
        con.execute("INSERT INTO meta VALUES (?,?)", (build_id, json.dumps(sources)))
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_matching_published_store_precedes_unpublished_trial(tmp_path):
    backend, census = context(tmp_path)
    active = store(backend.derived, "active", "published", sha(census))
    trial = backend.derived / "trial"
    trial.mkdir()
    (trial / "CHECKS.json").write_text('{"passed":true}')
    store(backend.derived, "trial", "trial", sha(census))
    assert backend.store_path() == active


def test_old_build_store_cannot_replace_current_census_density(tmp_path):
    backend, census = context(tmp_path)
    store(backend.derived, "old", "old_build", sha(census))
    assert backend.store_path() is None
    result = backend.density(0, 0, 5)
    assert result["n"] == 1 and result["source"] == "census.json"


def test_missing_or_stale_census_binding_cannot_autoselect(tmp_path):
    backend, census = context(tmp_path)
    store(backend.derived, "unbound", "published")
    store(backend.derived, "stale", "published", "0" * 64)
    assert backend.store_path() is None


def test_census_change_invalidates_cached_store_binding(tmp_path):
    backend, census = context(tmp_path)
    matched = store(backend.derived, "active", "published", sha(census))
    assert backend.store_path() == matched
    census.write_text('{"trees":[]}')
    assert backend.store_path() is None


def test_explicit_historical_store_remains_selectable(tmp_path):
    backend, _ = context(tmp_path)
    old = store(backend.derived, "old", "historical")
    backend._store = old
    assert backend.store_path() == old


def test_missing_published_id_uses_latest_passed_build(tmp_path):
    backend, census = context(tmp_path)
    (backend.world / "data/ecosystem.json").write_text("{}")
    for name, passed, stamp in (("passed", True, 10), ("failed", False, 20)):
        folder = backend.derived / name
        folder.mkdir()
        path = folder / "CHECKS.json"
        path.write_text(json.dumps({"passed": passed}))
        os.utime(path, (stamp, stamp))
    expected = store(backend.derived, "passed", "passed", sha(census))
    store(backend.derived, "failed", "failed", sha(census))
    assert backend.store_path() == expected
