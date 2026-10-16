"""Tests for the LLM analysis store: builder, query validation, cross-checks."""
import json
import math
import os
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import yellowstone_python.service.analysis_store as A
from yellowstone_python.service.llm_backend import Backend, _Handler


def _census_doc():
    # Edge coordinates: e1 sits on the (0,0,10,10) bbox edges and is in; e2 sits outside.
    trees = [
        {"stable_id": "t_edge", "x": 0.0, "z": 0.0,
         "crown_r_m": 1.0, "confidence": "high", "peak_exg": 0.2,
         "evidence_class": "synthetic"},
        {"stable_id": "t_corner", "x": 10.0, "z": 10.0,
         "crown_r_m": 2.0, "confidence": "medium", "peak_exg": 0.1,
         "evidence_class": "synthetic"},
        {"stable_id": "t_out", "x": 10.01, "z": 5.0,
         "crown_r_m": 1.5, "confidence": "low", "peak_exg": 0.05,
         "evidence_class": "synthetic"},
        {"stable_id": "t_mid", "x": 5.0, "z": 5.0,
         "crown_r_m": 1.2, "confidence": "high", "peak_exg": 0.3,
         "evidence_class": "synthetic"},
        {"stable_id": "t_far", "x": -500.0, "z": 300.0,
         "crown_r_m": 0.8, "confidence": "low", "peak_exg": 0.06,
         "evidence_class": "synthetic"},
    ]
    return {"schema": "yellowstone.canopy_census.v1", "n": len(trees),
            "trees": trees}


def _replay_doc():
    cells = [
        {"id": "cell_A", "river_id": "river_x",
         "center_s_m": 5.0, "start_s_m": 0.0, "end_s_m": 10.0,
         "length_m": 10.0, "width_m": 20.0, "depth_m": 0.5,
         "volume_m3": 100.0,
         "hydraulics": {"velocity_continuity_m_s": 0.5},
         "representative_velocity_m_s": 0.9},
        {"id": "cell_B", "river_id": "river_x",
         "center_s_m": 15.0, "start_s_m": 10.0, "end_s_m": 20.0,
         "length_m": 10.0, "width_m": 22.0, "depth_m": 0.6,
         "volume_m3": 120.0, "hydraulics": {},
         "representative_velocity_m_s": 0.7},
    ]
    frames = [{"t_s": float(t), "temperature_c": [17.0 + t, 18.0 + t]}
              for t in (0.0, 10.0, 20.0)]
    return {"cells": cells, "frames": frames}


def _firehole_doc():
    return {"schema": "yellowstone.firehole_obs.v1",
            "sites": {"06036805": {"series": {
                "discharge_m3_s": [[1000.0, 1.5], [2000.0, 1.6]],
                "temperature_c": [[1000.0, 12.0], [2000.0, 12.5]]}}}}


def _snotel_doc():
    return {"schema": "yellowstone.snotel_obs.v1",
            "sites": {"609:MT:SNTL": {"days": {
                "2026-01-01": {"WTEQ": 1.0, "PRCP": 0.5, "SNWD": 2.0,
                               "TAVG": 32.0, "TMAX": 212.0, "TMIN": -40.0},
                "2026-01-02": {"WTEQ": None, "PRCP": None, "SNWD": None,
                               "TAVG": None, "TMAX": None, "TMIN": None}}}}}


def _reach_fit_doc():
    return {"status": "fitted_not_validated_single_window",
            "effective_geometry": {"volume_m3": 300000.0},
            "window": {"start_epoch": 1000.0, "end_epoch": 2000.0},
            "n_train": 123, "n_holdout": 45,
            "champion": {"q_lat": 3.5, "t_lat": 30.0, "c_mult": 1.0,
                         "train_rmse": 0.5, "holdout_rmse": 0.6,
                         "train_bias": 0.03, "holdout_bias": 0.3},
            "top10_train": [
                {"q_lat": 3.5, "t_lat": 30.0, "c_mult": 1.0,
                 "train_rmse": 0.5, "holdout_rmse": 0.6},
                {"q_lat": 4.0, "t_lat": 25.0, "c_mult": 0.5,
                 "train_rmse": 0.9, "holdout_rmse": 1.0}],
            "null_models": [
                {"name": "upstream_persistence",
                 "train_rmse": 7.0, "holdout_rmse": 6.9, "k": 0},
                {"name": "mixing_only_c0_refit", "q_lat": 3.5,
                 "t_lat": 25.0, "c_mult": 0.0,
                 "train_rmse": 1.0, "holdout_rmse": 1.6, "k": 2}]}


def _snow_fit_doc():
    return {"status": "fitted_not_validated_single_window",
            "sites": {"609:MT:SNTL": {
                "fitted": {"k_melt_mm_per_deg_day": 1.0,
                           "wind_loss_effective": 0.0,
                           "train_rmse_mm": 10.5},
                "holdout_swe_mm": {"rmse": 112.0, "bias": 67.0},
                "null_persistence_rmse_mm": 293.0,
                "null_nomelt_rmse_mm": 471.0,
                "peak_timing_error_days": 48,
                "status": "fitted_not_validated_single_window"}}}


def _mem_con(with_fits=True):
    kw = {"build_id": "testbuild", "census": _census_doc(),
          "replay": _replay_doc(), "firehole": _firehole_doc(),
          "snotel": _snotel_doc(),
          "source_shas": {"a.json": "deadbeef"}}
    if with_fits:
        kw["reach_fits"] = [("reach.json", _reach_fit_doc())]
        kw["snow_fits"] = [("snow.json", _snow_fit_doc())]
    return A.build_con(**kw)


def _file_store(tmp_path, with_fits=True):
    con = _mem_con(with_fits=with_fits)
    out = tmp_path / "analysis_test.sqlite"
    disk = sqlite3.connect(str(out))
    try:
        con.backup(disk)
    finally:
        disk.close()
    con.close()
    (tmp_path / "census.json").write_text(json.dumps(_census_doc()))
    return out


def test_schema_and_meta():
    con = _mem_con()
    row = con.execute(
        "SELECT schema_version, build_id, status FROM meta").fetchone()
    assert row == (A.SCHEMA_VERSION, "testbuild", "illustrative")
    shas = json.loads(con.execute(
        "SELECT source_shas FROM meta").fetchone()[0])
    assert shas == {"a.json": "deadbeef"}
    for t, want in [("census_trees", 5), ("replay_cells", 2),
                    ("replay_frames", 6), ("obs_usgs", 2),
                    ("obs_snotel", 2), ("fits_reach", 2),
                    ("fits_reach_nulls", 2), ("fits_snow", 1)]:
        assert con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == want
    con.close()


def test_si_conversions_at_ingestion():
    con = _mem_con()
    r = con.execute(
        "SELECT wteq_mm, prcp_mm, snwd_mm, tavg_c, tmax_c, tmin_c "
        "FROM obs_snotel WHERE day='2026-01-01'").fetchone()
    assert r[0] == pytest.approx(25.4)   # 1 in -> mm
    assert r[1] == pytest.approx(12.7)   # 0.5 in -> mm
    assert r[2] == pytest.approx(50.8)   # 2 in -> mm
    assert r[3] == pytest.approx(0.0)    # 32 F -> C
    assert r[4] == pytest.approx(100.0)  # 212 F -> C
    assert r[5] == pytest.approx(-40.0)  # -40 F == -40 C
    nulls = con.execute(
        "SELECT wteq_mm, tavg_c FROM obs_snotel "
        "WHERE day='2026-01-02'").fetchone()
    assert nulls == (None, None)
    con.close()


def test_velocity_continuity_then_representative_fallback():
    con = _mem_con()
    v = dict(con.execute(
        "SELECT cell_id, velocity_m_s FROM replay_cells").fetchall())
    assert v == {"cell_A": 0.5, "cell_B": 0.7}
    con.close()


def test_missing_fits_empty_tables_with_note_never_error():
    con = _mem_con(with_fits=False)
    assert con.execute("SELECT COUNT(*) FROM fits_reach").fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) FROM fits_reach_nulls").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM fits_snow").fetchone()[0] == 0
    notes = con.execute("SELECT notes FROM meta").fetchone()[0]
    assert "no reach-fit" in notes and "no snow-fit" in notes
    con.close()


def test_rtree_bbox_includes_edge_coordinates():
    con = _mem_con()
    out = A.query(con, "census_trees", x0=0.0, x1=10.0, z0=0.0, z1=10.0,
                  limit=100)
    got = sorted(r[0] for r in out["rows"])
    assert got == ["t_corner", "t_edge", "t_mid"]
    con.close()


def test_rtree_absent_raises_error():
    class _NoRtree:
        def execute(self, *a, **k):
            raise sqlite3.OperationalError("no such module: rtree")
    with pytest.raises(RuntimeError, match="R-tree"):
        A.require_rtree(_NoRtree())


def test_query_validation_rejections():
    con = _mem_con()
    bad = [
        lambda: A.query(con, "nope"),
        lambda: A.query(con, "census_trees", columns=["x", "nope"]),
        lambda: A.query(con, "census_trees", columns=[]),
        lambda: A.query(con, "census_trees", limit=0),
        lambda: A.query(con, "census_trees", limit=5001),
        lambda: A.query(con, "census_trees", limit=True),
        lambda: A.query(con, "census_trees", limit="lots"),
        lambda: A.query(con, "census_trees", offset=-1),
        lambda: A.query(con, "census_trees", bogus=1),
        lambda: A.query(con, "census_trees", x0=0.0),  # half bbox
        lambda: A.query(con, "census_trees", confidence="extreme"),
        lambda: A.query(con, "census_trees", x0=float("nan"),
                        x1=1.0, z0=0.0, z1=1.0),
        lambda: A.query(con, "census_trees", x0=float("inf"),
                        x1=1.0, z0=0.0, z1=1.0),
        lambda: A.query(con, "replay_frames", t0=True),
        lambda: A.query(con, "obs_usgs", site=""),
        lambda: A.query(con, "obs_snotel", day0=123),
    ]
    for fn in bad:
        with pytest.raises((ValueError, TypeError)):
            fn()
    con.close()


def test_query_limit_offset_truncation():
    con = _mem_con()
    p1 = A.query(con, "replay_frames", limit=2, offset=0)
    assert p1["n"] == 2 and p1["truncated"] is True
    p2 = A.query(con, "replay_frames", limit=2, offset=2)
    assert p2["n"] == 2 and p2["truncated"] is True
    p3 = A.query(con, "replay_frames", limit=5000, offset=0)
    assert p3["n"] == 6 and p3["truncated"] is False
    assert p1["rows"] != p2["rows"]
    con.close()


def test_cross_check_json_vs_store(tmp_path):
    store = _file_store(tmp_path)
    b = Backend(derived=tmp_path, store=store)
    for (x, z, r) in [(5.0, 5.0, 8.0), (0.0, 0.0, 0.5),
                      (-500.0, 300.0, 120.0), (5.0, 5.0, 1000.0)]:
        from_json = Backend.circle_stats(b.census_points(), x, z, r)
        from_store = b.density(x, z, r)
        assert from_store["n"] == from_json["n"]
        assert from_store["area_ha"] == from_json["area_ha"]
        assert from_store["trees_per_ha"] == from_json["trees_per_ha"]
        assert from_store["source"] == store.name
    # Without any store file the same endpoint still serves from JSON.
    b2 = Backend(derived=tmp_path, store=tmp_path / "absent.sqlite")
    assert b2.store_path() is None
    assert b2.density(5.0, 5.0, 8.0)["source"] == "census.json"


def test_query_http_and_503_without_store(tmp_path):
    store = _file_store(tmp_path)
    _Handler.backend = Backend(derived=tmp_path, store=store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.error
        import urllib.request

        def get(path):
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}{path}") as r:
                return r.status, json.load(r)

        status, body = get("/api/query?table=census_trees&limit=2")
        assert status == 200 and body["n"] == 2
        assert body["store"] == "analysis_test.sqlite"

        status, body = get(
            "/api/query?table=replay_frames&cell_id=cell_A&t0=0&t1=10")
        assert status == 200 and body["n"] == 2

        for bad in ("/api/query?table=nope",
                    "/api/query?table=census_trees&limit=99999",
                    "/api/query"):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{bad}")
                raise AssertionError(f"{bad} should not return 200")
            except urllib.error.HTTPError as e:
                assert e.code == 400

        # Derived dir with no store: query -> 503, density still serves.
        empty = tmp_path / "empty"
        empty.mkdir()
        (empty / "census.json").write_text(json.dumps(_census_doc()))
        _Handler.backend = Backend(derived=empty)
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/query?table=meta")
            raise AssertionError("storeless query should not return 200")
        except urllib.error.HTTPError as e:
            assert e.code == 503
        status, body = get("/api/density?x=5&z=5&r=8")
        assert status == 200 and body["source"] == "census.json"
    finally:
        server.shutdown()
        thread.join()


def test_census_example_executes_on_synthetic_store(tmp_path, monkeypatch, repo_root):
    store = _file_store(tmp_path)
    monkeypatch.setenv("ANALYSIS_STORE", str(store))
    figdir = tmp_path / "figs"
    monkeypatch.setenv("FIG_DIR", str(figdir))
    import runpy
    example = repo_root / "examples/census_explorer.py"
    assert example.exists()
    # The example must read the store only, never the JSON interchange.
    assert "census.json" not in example.read_text()
    runpy.run_path(str(example), run_name="__main__")
    for fig in ("confidence_hist.png", "census_map.png"):
        p = figdir / fig
        assert p.exists() and p.stat().st_size > 1000


def test_circle_count_radius_bounds():
    con = _mem_con()
    for bad in (0.05, 6000.0, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            A.census_circle_count(con, 0, 0, bad)
    con.close()


def test_long_format_frame_rowcount_and_index():
    con = _mem_con()
    assert con.execute("SELECT COUNT(*) FROM replay_frames").fetchone()[0] \
        == 2 * 3
    idx = con.execute("PRAGMA index_list(replay_frames)").fetchall()
    assert any("cell" in str(i).lower() for i in idx)
    temps = con.execute(
        "SELECT temperature_c FROM replay_frames WHERE cell_id='cell_B' "
        "ORDER BY t_s").fetchall()
    assert [t[0] for t in temps] == [18.0, 28.0, 38.0]
    con.close()


def test_snotel_day_filters_are_applied():
    # Regression: day0/day1 filter the result and do apply.
    con = _mem_con()
    jan1 = A.query(con, "obs_snotel", day0="2026-01-01", day1="2026-01-01",
                   limit=10)
    assert jan1["n"] == 1 and jan1["rows"][0][1] == "2026-01-01"
    jan2 = A.query(con, "obs_snotel", day0="2026-01-02", limit=10)
    assert jan2["n"] == 1 and jan2["rows"][0][1] == "2026-01-02"
    empty = A.query(con, "obs_snotel", day0="2030-01-01", limit=10)
    assert empty["n"] == 0 and empty["truncated"] is False
    both = A.query(con, "obs_snotel", site="609:MT:SNTL",
                   day0="2026-01-01", day1="2026-01-02", limit=10)
    assert both["n"] == 2
    con.close()


def test_duplicate_stable_id_leaves_no_stale_rtree():
    con = A.create_empty()
    doc = {"trees": [
        {"stable_id": "dup", "x": 0.0, "z": 0.0,
         "crown_r_m": 1.0, "confidence": "high", "peak_exg": 0.2},
        {"stable_id": "dup", "x": 100.0, "z": 100.0,
         "crown_r_m": 1.0, "confidence": "high", "peak_exg": 0.2},
    ]}
    A.ingest_census(con, doc)
    assert con.execute("SELECT COUNT(*) FROM census_trees").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM census_rtree").fetchone()[0] == 1
    old_box = A.query(con, "census_trees", x0=-5, x1=5, z0=-5, z1=5,
                      limit=10)
    assert old_box["n"] == 0
    new_box = A.query(con, "census_trees", x0=95, x1=105, z0=95, z1=105,
                      limit=10)
    assert new_box["n"] == 1
    con.close()


@pytest.mark.parametrize("exg", [None, 0.0, -0.25, 0.3])
def test_census_exg_preserves_unmeasured_and_finite_values(exg):
    con = A.create_empty()
    tree = {**_census_doc()["trees"][0], "peak_exg": exg}
    try:
        assert A.ingest_census(con, {"trees": [tree]}) == 1
        out = A.query(con, "census_trees", columns=["stable_id", "peak_exg"])
        assert out["rows"] == [[tree["stable_id"], exg]]
        assert json.loads(json.dumps(out))["rows"][0][1] == exg
    finally:
        con.close()


def test_nullable_exg_persists_in_versioned_store(tmp_path):
    doc = _census_doc()
    doc["trees"][0]["peak_exg"] = None
    con = A.build_con(build_id="nullable", census=doc, replay=_replay_doc(),
                      firehole=_firehole_doc(), snotel=_snotel_doc())
    out = tmp_path / "nullable.sqlite"
    disk = sqlite3.connect(out)
    try:
        con.backup(disk)
    finally:
        disk.close()
        con.close()
    values = A.query(out, "census_trees", columns=["stable_id", "peak_exg"])
    assert dict(values["rows"]) == {t["stable_id"]: t["peak_exg"] for t in doc["trees"]}
    meta = A.query(out, "meta", columns=["schema_version"])
    assert meta["rows"] == [["yellowstone.analysis_store.v2"]]


@pytest.mark.parametrize("exg", [True, False, float("nan"), float("inf"),
                                float("-inf"), "not numeric"])
def test_census_exg_rejects_invalid_values_before_replacement(exg):
    con = A.create_empty()
    original = _census_doc()["trees"][0]
    try:
        A.ingest_census(con, {"trees": [original]})
        bad = {**original, "x": 100.0, "peak_exg": exg}
        with pytest.raises(ValueError, match="peak_exg"):
            A.ingest_census(con, {"trees": [bad]})
        row = A.query(con, "census_trees", columns=["x", "peak_exg"])
        assert row["rows"] == [[original["x"], original["peak_exg"]]]
        assert con.execute("SELECT COUNT(*) FROM census_rtree").fetchone()[0] == 1
    finally:
        con.close()


@pytest.mark.parametrize("before,after", [(0.2, None), (None, 0.4)])
def test_census_nullable_exg_replacement_preserves_rtree(before, after):
    con = A.create_empty()
    original = {**_census_doc()["trees"][0], "peak_exg": before}
    replacement = {**original, "x": 100.0, "z": 100.0, "peak_exg": after}
    try:
        A.ingest_census(con, {"trees": [original, replacement]})
        assert con.execute("SELECT COUNT(*) FROM census_trees").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM census_rtree").fetchone()[0] == 1
        assert A.query(con, "census_trees", x0=-5, x1=5, z0=-5, z1=5)["n"] == 0
        out = A.query(con, "census_trees", x0=95, x1=105, z0=95, z1=105,
                      columns=["stable_id", "peak_exg"])
        assert out["rows"] == [[original["stable_id"], after]]
    finally:
        con.close()


def test_legacy_store_rebuild_preserves_rgb_and_unrelated_data(tmp_path):
    out = tmp_path / "legacy.sqlite"
    con = sqlite3.connect(out)
    con.executescript("""
        CREATE TABLE census_trees(
            stable_id TEXT PRIMARY KEY, x REAL NOT NULL, z REAL NOT NULL,
            crown_r_m REAL NOT NULL, confidence TEXT NOT NULL,
            peak_exg REAL NOT NULL, evidence_class TEXT NOT NULL);
        CREATE VIRTUAL TABLE census_rtree USING rtree(tree_row, x0, x1, z0, z1);
        CREATE TABLE unrelated(value TEXT NOT NULL);
        INSERT INTO unrelated VALUES ('preserved observation');
    """)
    try:
        A.ingest_census(con, _census_doc())
        con.commit()
        before = out.read_bytes()
        assert A.query(out, "census_trees", columns=["peak_exg"])["n"] == 5
        assert out.read_bytes() == before
        tree = {**_census_doc()["trees"][0], "peak_exg": None, "x": 100.0}
        with pytest.raises(ValueError, match="rebuild.*new output"):
            A.ingest_census(con, {"trees": [tree]})
        assert A.query(con, "census_trees", columns=["peak_exg"])["n"] == 5
        assert con.execute("SELECT COUNT(*) FROM census_rtree").fetchone()[0] == 5
        assert con.execute("SELECT value FROM unrelated").fetchone()[0] == \
            "preserved observation"
        assert out.read_bytes() == before
    finally:
        con.close()


@pytest.mark.needs_world
def test_active_lidar_census_ingests_with_unmeasured_exg(repo_root):
    path = repo_root / "derived/census.json"
    doc = json.loads(path.read_text())
    assert len(doc["trees"]) == 34303
    assert all(tree["peak_exg"] is None for tree in doc["trees"])
    con = A.create_empty()
    try:
        assert A.ingest_census(con, doc) == len(doc["trees"])
        assert con.execute("SELECT COUNT(*) FROM census_trees").fetchone()[0] == 34303
        assert con.execute("SELECT COUNT(*) FROM census_rtree").fetchone()[0] == 34303
        assert con.execute("SELECT COUNT(peak_exg) FROM census_trees").fetchone()[0] == 0
        stored_ids = {row[0] for row in con.execute("SELECT stable_id FROM census_trees")}
        assert stored_ids == {tree["stable_id"] for tree in doc["trees"]}
    finally:
        con.close()


def test_radius_bounds_single_sourced():
    import yellowstone_python.service.llm_backend as L
    assert (A.RADIUS_MIN_M, A.RADIUS_MAX_M) == \
        (L.MIN_RADIUS_M, L.MAX_RADIUS_M) == (0.1, 5000.0)


def test_replay_garbage_raises_valueerror():
    con = A.create_empty()

    def _cell(**over):
        base = {"id": "c", "river_id": "r",
                "start_s_m": 0.0, "end_s_m": 10.0, "length_m": 10.0,
                "width_m": 10.0, "depth_m": 0.5, "volume_m3": 50.0,
                "representative_velocity_m_s": 0.5}
        base.update(over)
        return base

    no_id = {"cells": [{"river_id": "r"}],
             "frames": [{"t_s": 0.0, "temperature_c": [1.0]}]}
    with pytest.raises(ValueError, match="missing 'id'"):
        A.ingest_replay(con, no_id)
    missing_geo = {"cells": [{"id": "c",
                              "representative_velocity_m_s": 0.5}],
                   "frames": [{"t_s": 0.0, "temperature_c": [1.0]}]}
    with pytest.raises(ValueError, match="missing 'river_id'"):
        A.ingest_replay(con, missing_geo)
    bad_volume = {"cells": [_cell(volume_m3=0.0)],
                  "frames": [{"t_s": 0.0, "temperature_c": [1.0]}]}
    with pytest.raises(ValueError, match="volume_m3 must be positive"):
        A.ingest_replay(con, bad_volume)
    inverted = {"cells": [_cell(start_s_m=10.0, end_s_m=0.0)],
                "frames": [{"t_s": 0.0, "temperature_c": [1.0]}]}
    with pytest.raises(ValueError, match="start_s_m .* must be less than"):
        A.ingest_replay(con, inverted)
    # A cell with no velocity source raises; missing is not zero.
    no_vel_cell = _cell()
    no_vel_cell.pop("representative_velocity_m_s")
    no_velocity = {"cells": [no_vel_cell],
                   "frames": [{"t_s": 0.0, "temperature_c": [1.0]}]}
    with pytest.raises(ValueError, match="no velocity"):
        A.ingest_replay(con, no_velocity)
    none_temp = {"cells": [_cell()],
                 "frames": [{"t_s": 0.0, "temperature_c": [None]}]}
    with pytest.raises(ValueError, match="non-numeric"):
        A.ingest_replay(con, none_temp)
    no_ts = {"cells": [_cell()],
             "frames": [{"temperature_c": [1.0]}]}
    with pytest.raises(ValueError, match="t_s"):
        A.ingest_replay(con, no_ts)
    con.close()


def test_build_file_refuses_overwrite(tmp_path):
    from yellowstone_python.service.analysis_store import build_file
    out = tmp_path / "analysis_x.sqlite"
    kw = {"build_id": "x", "census": _census_doc(),
          "replay": _replay_doc(), "firehole": _firehole_doc(),
          "snotel": _snotel_doc()}
    con = A.build_con(**kw)
    disk = sqlite3.connect(str(out))
    try:
        con.backup(disk)
    finally:
        disk.close()
    con.close()
    with pytest.raises(FileExistsError):
        build_file(build_dir=tmp_path, out=out,
                   census_path=tmp_path / "c.json",
                   firehole_path=tmp_path / "f.json",
                   snotel_path=tmp_path / "s.json")


def _write_build_tree(tmp_path):
    (tmp_path / "river_replay.json").write_text(json.dumps(_replay_doc()))
    census = tmp_path / "census.json"
    firehole = tmp_path / "firehole_obs.json"
    snotel = tmp_path / "snotel_obs.json"
    census.write_text(json.dumps(_census_doc()))
    firehole.write_text(json.dumps(_firehole_doc()))
    snotel.write_text(json.dumps(_snotel_doc()))
    return census, firehole, snotel


def test_build_file_sources_record_shape_and_readonly(tmp_path):
    from yellowstone_python.service.analysis_store import build_file
    census, firehole, snotel = _write_build_tree(tmp_path)
    out = tmp_path / "analysis_build_rec.sqlite"
    build_file(build_dir=tmp_path, out=out,
               census_path=census, firehole_path=firehole,
               snotel_path=snotel)
    import stat as _stat
    mode = out.stat().st_mode
    assert not mode & _stat.S_IWUSR
    con = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
    try:
        shas_text = con.execute(
            "SELECT source_shas FROM meta").fetchone()[0]
        shas = json.loads(shas_text)
    finally:
        con.close()
    assert "census" in shas and "firehole_obs" in shas and "snotel_obs" in shas
    rec = shas["census"]
    assert set(rec) == {"path", "basename", "sha256", "bytes"}
    assert rec["basename"] == "census.json"
    assert rec["bytes"] > 0
    assert len(rec["sha256"]) == 64
    replay_key = next(k for k in shas if k.endswith("/river_replay.json"))
    assert tmp_path.name in replay_key


def test_ingest_replay_rejects_missing_geometry_field():
    con = A.create_empty()
    bad = {"cells": [{"id": "c", "river_id": "r",
                      "start_s_m": 0.0, "end_s_m": 10.0}],
           "frames": [{"t_s": 0.0, "temperature_c": [1.0]}]}
    with pytest.raises(ValueError, match="missing 'length_m'"):
        A.ingest_replay(con, bad)
    con.close()


def test_fits_reach_window_and_null_k_recorded():
    con = _mem_con()
    champ = con.execute(
        "SELECT window_start_epoch, window_end_epoch, "
        "n_train, n_holdout FROM fits_reach "
        "WHERE champion=1").fetchone()
    assert champ == (1000.0, 2000.0, 123, 45)
    nulls = dict(con.execute(
        "SELECT name, k FROM fits_reach_nulls").fetchall())
    assert nulls == {"upstream_persistence": 0, "mixing_only_c0_refit": 2}
    con.close()


def test_fits_reach_order_champion_first():
    con = _mem_con()
    rows = A.query(con, "fits_reach",
                   columns=["source_file", "champion", "q_lat"],
                   limit=10)
    assert rows["rows"][0][1] == 1
    assert rows["rows"][-1][1] == 0
    con.close()


def test_fits_reach_nulls_source_name_index_exists():
    con = _mem_con()
    rows = con.execute(
        "PRAGMA index_list(fits_reach_nulls)").fetchall()
    assert any("src_name" in str(row).lower() or
               "source_file" in str(row).lower() for row in rows)
    con.close()


def test_query_filter_evidence_class():
    con = A.create_empty()
    doc = {"trees": [
        {"stable_id": "s", "x": 1.0, "z": 1.0, "crown_r_m": 0.5,
         "confidence": "high", "peak_exg": 0.2,
         "evidence_class": "synthetic"},
        {"stable_id": "n", "x": 2.0, "z": 2.0, "crown_r_m": 0.5,
         "confidence": "high", "peak_exg": 0.2,
         "evidence_class": "naip_detect"},
    ]}
    A.ingest_census(con, doc)
    syn = A.query(con, "census_trees", evidence_class="synthetic", limit=10)
    naip = A.query(con, "census_trees", evidence_class="naip_detect", limit=10)
    assert syn["n"] == 1 and syn["rows"][0][0] == "s"
    assert naip["n"] == 1 and naip["rows"][0][0] == "n"
    with pytest.raises(ValueError, match="evidence_class"):
        A.query(con, "census_trees", evidence_class="")
    con.close()


def test_ingest_snow_fit_rejects_wind_loss_outside_01():
    con = A.create_empty()
    bad = {"status": "fitted_not_validated_single_window",
           "sites": {"X": {"fitted": {"k_melt_mm_per_deg_day": 1.0,
                                      "wind_loss_effective": 1.5},
                           "holdout_swe_mm": {"rmse": 1.0, "bias": 0.0}}}}
    with pytest.raises(ValueError, match="wind_loss_effective"):
        A.ingest_snow_fit(con, bad, "snow.json")
    con.close()


def test_ingest_snow_fit_records_holdout_window():
    con = A.create_empty()
    doc = {"status": "fitted_not_validated_single_window",
           "sites": {"X": {"fitted": {"k_melt_mm_per_deg_day": 1.0,
                                      "wind_loss_effective": 0.1,
                                      "train_rmse_mm": 5.0},
                           "holdout_swe_mm": {"rmse": 10.0, "bias": 2.0,
                                              "start_day": "2026-02-01",
                                              "end_day": "2026-04-30"},
                           "null_persistence_rmse_mm": 50.0,
                           "null_nomelt_rmse_mm": 60.0,
                           "peak_timing_error_days": 3}}}
    A.ingest_snow_fit(con, doc, "snow.json")
    row = con.execute(
        "SELECT holdout_start_day, holdout_end_day FROM fits_snow").fetchone()
    assert row == ("2026-02-01", "2026-04-30")
    con.close()


def test_no_store_error_subclass_of_file_not_found():
    assert issubclass(A.NoStoreError, FileNotFoundError)
    with pytest.raises(A.NoStoreError):
        A.query("/this/path/does/not/exist.sqlite", "meta")


def test_query_does_not_leak_query_only_pragma():
    con = A.create_empty()
    doc = _census_doc()
    A.ingest_census(con, doc)
    A.query(con, "census_trees", limit=10)
    doc2 = {"trees": [
        {"stable_id": "later", "x": 7.0, "z": 7.0, "crown_r_m": 1.0,
         "confidence": "high", "peak_exg": 0.1,
         "evidence_class": "synthetic"}]}
    A.ingest_census(con, doc2)
    con.close()


def test_crown_overlap_count_includes_overlapping_crown():
    con = A.create_empty()
    doc = {"trees": [
        {"stable_id": "near", "x": 2.1, "z": 0.0, "crown_r_m": 2.0,
         "confidence": "high", "peak_exg": 0.1,
         "evidence_class": "synthetic"},
    ]}
    A.ingest_census(con, doc)
    center = A.census_center_count(con, 0.0, 0.0, 1.0)
    crown = A.census_crown_overlap_count(con, 0.0, 0.0, 1.0)
    assert center["n"] == 0
    assert crown["n"] == 1
    con.close()
