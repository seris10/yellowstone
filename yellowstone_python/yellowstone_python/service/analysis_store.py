"""SQLite-backed analysis store for derived artifacts."""

from __future__ import annotations

from yellowstone_python.common.io import sha256_file as _sha256

import datetime
import hashlib
import json
import math
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "yellowstone.analysis_store.v2"
STATUS = "illustrative"
CONFIDENCES = ("low", "medium", "high")

# Unit factors for SNOTEL raw codes (depth codes in inches, temperature codes in degF).
IN_TO_MM = 25.4


class NoStoreError(FileNotFoundError):
    """Raised when no analysis store file exists at the resolved path."""


def f_to_c(f: float) -> float:
    return (float(f) - 32.0) * 5.0 / 9.0


def in_to_mm(inches: float) -> float:
    return float(inches) * IN_TO_MM


def _finite_float(name: str, value, *, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric (boolean rejected)")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(float(v))




def require_rtree(con: sqlite3.Connection) -> None:
    """Raise RuntimeError when the connected SQLite lacks the R-tree module."""
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS "
                    "_rtree_probe USING rtree(id, x0, x1, z0, z1)")
        con.execute("DROP TABLE _rtree_probe")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"SQLite R-tree module unavailable ({exc}); spatial queries "
            f"require it"
        ) from exc


_SCHEMA = """
CREATE TABLE census_trees(
  stable_id TEXT PRIMARY KEY,
  x REAL NOT NULL, z REAL NOT NULL,
  crown_r_m REAL NOT NULL, confidence TEXT NOT NULL,
  peak_exg REAL, evidence_class TEXT NOT NULL);
CREATE VIRTUAL TABLE census_rtree USING rtree(
  tree_row INTEGER PRIMARY KEY, x0, x1, z0, z1);
CREATE TABLE replay_cells(
  cell_id TEXT PRIMARY KEY, river_id TEXT NOT NULL,
  s_m REAL NOT NULL, start_s_m REAL NOT NULL, end_s_m REAL NOT NULL,
  length_m REAL NOT NULL, width_m REAL NOT NULL, depth_m REAL NOT NULL,
  velocity_m_s REAL NOT NULL, volume_m3 REAL NOT NULL);
CREATE TABLE replay_frames(
  t_s REAL NOT NULL, cell_id TEXT NOT NULL, temperature_c REAL NOT NULL,
  PRIMARY KEY (t_s, cell_id));
CREATE INDEX replay_frames_cell_t ON replay_frames(cell_id, t_s);
CREATE TABLE obs_usgs(
  site TEXT NOT NULL, epoch REAL NOT NULL,
  discharge_m3_s REAL, temperature_c REAL);
CREATE INDEX obs_usgs_site_epoch ON obs_usgs(site, epoch);
CREATE TABLE obs_snotel(
  site TEXT NOT NULL, day TEXT NOT NULL,
  wteq_mm REAL, prcp_mm REAL, snwd_mm REAL,
  tavg_c REAL, tmax_c REAL, tmin_c REAL);
CREATE INDEX obs_snotel_site_day ON obs_snotel(site, day);
CREATE TABLE fits_reach(
  source_file TEXT NOT NULL, volume_m3 REAL,
  q_lat REAL, t_lat REAL, c_mult REAL,
  train_rmse REAL, holdout_rmse REAL, train_bias REAL, holdout_bias REAL,
  champion INTEGER NOT NULL, status TEXT NOT NULL,
  window_start_epoch REAL, window_end_epoch REAL,
  n_train INTEGER, n_holdout INTEGER);
CREATE TABLE fits_reach_nulls(
  source_file TEXT NOT NULL, name TEXT NOT NULL,
  q_lat REAL, t_lat REAL, c_mult REAL,
  train_rmse REAL, holdout_rmse REAL,
  k INTEGER);
CREATE INDEX fits_reach_nulls_src_name ON fits_reach_nulls(source_file, name);
CREATE TABLE fits_snow(
  source_file TEXT NOT NULL, site TEXT NOT NULL,
  k_melt REAL, wind_loss REAL,
  train_rmse_mm REAL, holdout_rmse_mm REAL, holdout_bias_mm REAL,
  null_persistence_rmse_mm REAL, null_nomelt_rmse_mm REAL,
  peak_timing_err_d REAL, status TEXT NOT NULL,
  holdout_start_day TEXT, holdout_end_day TEXT);
CREATE TABLE meta(
  schema_version TEXT NOT NULL, build_id TEXT NOT NULL,
  source_shas TEXT NOT NULL, created_utc TEXT NOT NULL,
  status TEXT NOT NULL, notes TEXT NOT NULL);
"""


def _unwrap_replay(doc: dict) -> dict:
    if "cells" in doc and "frames" in doc:
        return doc
    inner = doc.get("replay")
    if isinstance(inner, dict) and "cells" in inner and "frames" in inner:
        return inner
    raise ValueError("replay doc has no cells+frames (nor a 'replay' sidecar)")


def _velocity_of(cell: dict) -> float:
    """Velocity (m/s) from continuity first, representative fallback. None raises."""
    hydro = cell.get("hydraulics")
    if isinstance(hydro, dict) and hydro.get("velocity_continuity_m_s") is not None:
        return _finite_float("velocity_continuity_m_s",
                             hydro["velocity_continuity_m_s"])
    if cell.get("representative_velocity_m_s") is not None:
        return _finite_float("representative_velocity_m_s",
                             cell["representative_velocity_m_s"])
    raise ValueError(
        f"replay cell {cell.get('id')!r}: no velocity "
        f"(expected hydraulics.velocity_continuity_m_s or "
        f"representative_velocity_m_s)")


def create_empty() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    require_rtree(con)
    con.executescript(_SCHEMA)
    return con


def ingest_census(con: sqlite3.Connection, doc: dict) -> int:
    """Store census coordinates and nullable RGB excess-green measurements."""
    trees = doc.get("trees")
    if not isinstance(trees, list):
        raise ValueError("census doc: 'trees' must be a list")
    if any(isinstance(t, dict) and "peak_exg" in t and t["peak_exg"] is None
           for t in trees):
        column = next((row for row in con.execute("PRAGMA table_info(census_trees)")
                       if row[1] == "peak_exg"), None)
        if column is None or column[3]:
            raise ValueError(
                "analysis store schema cannot store unmeasured peak_exg; "
                "rebuild the store with a new output filename")
    n = 0
    for i, t in enumerate(trees):
        for k in ("stable_id", "x", "z", "crown_r_m",
                  "confidence", "peak_exg"):
            if k not in t:
                raise ValueError(f"census tree #{i}: missing key {k!r}")
        if t["confidence"] not in CONFIDENCES:
            raise ValueError(
                f"census tree #{i}: bad confidence {t['confidence']!r}")
        x = _finite_float(f"census tree #{i} x", t["x"])
        z = _finite_float(f"census tree #{i} z", t["z"])
        crown_r = _finite_float(f"census tree #{i} crown_r_m", t["crown_r_m"])
        peak_exg = _finite_float(f"census tree #{i} peak_exg", t["peak_exg"],
                                 allow_none=True)
        sid = str(t["stable_id"])
        # Last write wins on duplicate stable_id; drop the paired rtree row for the retired rowid first.
        old = con.execute("SELECT rowid FROM census_trees WHERE stable_id=?",
                          (sid,)).fetchone()
        if old is not None:
            con.execute("DELETE FROM census_rtree WHERE tree_row=?",
                        (old[0],))
        row = con.execute(
            "INSERT OR REPLACE INTO census_trees VALUES (?,?,?,?,?,?,?)",
            (sid, x, z, crown_r,
             t["confidence"], peak_exg,
             str(t.get("evidence_class", "")))).lastrowid
        con.execute("INSERT OR REPLACE INTO census_rtree VALUES (?,?,?,?,?)",
                    (row, x, x, z, z))
        n += 1
    return n


REQUIRED_REPLAY_CELL = (
    "id", "river_id", "start_s_m", "end_s_m",
    "length_m", "width_m", "depth_m", "volume_m3",
)


def ingest_replay(con: sqlite3.Connection, doc: dict) -> tuple[int, int]:
    rep = _unwrap_replay(doc)
    cells, frames = rep["cells"], rep["frames"]
    # Replay tables are rebuilt on each ingest.
    con.execute("DELETE FROM replay_frames")
    con.execute("DELETE FROM replay_cells")
    for ci, c in enumerate(cells):
        for k in REQUIRED_REPLAY_CELL:
            if k not in c:
                raise ValueError(f"replay cell #{ci}: missing {k!r}")
        start_s = _finite_float(f"replay cell #{ci} start_s_m", c["start_s_m"])
        end_s = _finite_float(f"replay cell #{ci} end_s_m", c["end_s_m"])
        if not start_s < end_s:
            raise ValueError(
                f"replay cell #{ci}: start_s_m {start_s} must be less than "
                f"end_s_m {end_s}")
        length = _finite_float(f"replay cell #{ci} length_m", c["length_m"])
        width = _finite_float(f"replay cell #{ci} width_m", c["width_m"])
        depth = _finite_float(f"replay cell #{ci} depth_m", c["depth_m"])
        volume = _finite_float(f"replay cell #{ci} volume_m3", c["volume_m3"])
        for label, value in (("length_m", length), ("width_m", width),
                             ("depth_m", depth), ("volume_m3", volume)):
            if value <= 0:
                raise ValueError(
                    f"replay cell #{ci}: {label} must be positive, got {value}")
        center_s = _finite_float(
            f"replay cell #{ci} center_s_m",
            c.get("center_s_m", (start_s + end_s) / 2.0))
        vel = _velocity_of(c)
        con.execute(
            "INSERT OR REPLACE INTO replay_cells VALUES (?,?,?,?,?,?,?,?,?,?)",
            (str(c["id"]), str(c["river_id"]), center_s,
             start_s, end_s, length, width, depth, vel, volume))
    nf = 0
    for f in frames:
        if "t_s" not in f or "temperature_c" not in f:
            raise ValueError("replay frame missing 't_s'/'temperature_c'")
        t_s = float(f["t_s"])
        temps = f["temperature_c"]
        if len(temps) != len(cells):
            raise ValueError(
                f"frame t={t_s}: {len(temps)} temps for {len(cells)} cells")
        try:
            temps_f = [_finite_float(f"frame t={t_s} temp index {i}", tp)
                        for i, tp in enumerate(temps)]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"frame t={t_s}: non-numeric temperature ({exc})") from exc
        con.executemany(
            "INSERT OR REPLACE INTO replay_frames VALUES (?,?,?)",
            [(t_s, str(c["id"]), tp) for c, tp in zip(cells, temps_f)])
        nf += len(cells)
    return len(cells), nf


def _ingest_firehole_series(label: str, pairs) -> dict:
    if not isinstance(pairs, list):
        raise ValueError(f"firehole {label}: series must be a list, got "
                         f"{type(pairs).__name__}")
    out: dict = {}
    for i, pair in enumerate(pairs):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(
                f"firehole {label} #{i}: expected [epoch, value]")
        epoch = _finite_float(f"firehole {label} #{i} epoch", pair[0])
        value = _finite_float(f"firehole {label} #{i} value", pair[1],
                              allow_none=True)
        if epoch in out and out[epoch] != value:
            raise ValueError(
                f"firehole {label}: duplicate epoch {epoch} with "
                f"divergent values ({out[epoch]} vs {value})")
        out[epoch] = value
    return out


def ingest_firehole(con: sqlite3.Connection, doc: dict) -> int:
    sites = doc.get("sites")
    if not isinstance(sites, dict):
        raise ValueError("firehole doc: 'sites' must be an object, got "
                         f"{type(sites).__name__}")
    n = 0
    for site, rec in sites.items():
        series = (rec or {}).get("series") or {}
        q = _ingest_firehole_series(f"{site} discharge_m3_s",
                                     series.get("discharge_m3_s", []))
        t = _ingest_firehole_series(f"{site} temperature_c",
                                     series.get("temperature_c", []))
        for epoch in sorted(set(q) | set(t)):
            ep = _finite_float(f"firehole {site} epoch", epoch)
            discharge = _finite_float(
                f"firehole {site} discharge_m3_s@{epoch}",
                q.get(epoch), allow_none=True)
            temperature = _finite_float(
                f"firehole {site} temperature_c@{epoch}",
                t.get(epoch), allow_none=True)
            con.execute("INSERT INTO obs_usgs VALUES (?,?,?,?)",
                        (site, ep, discharge, temperature))
            n += 1
    return n


def ingest_snotel(con: sqlite3.Connection, doc: dict) -> int:
    import datetime
    n = 0
    for site, rec in doc.get("sites", {}).items():
        for day in sorted(rec.get("days", {})):
            try:
                datetime.date.fromisoformat(str(day))
            except ValueError:
                raise ValueError(f"snotel: invalid date {day!r}; must be YYYY-MM-DD")
            d = rec["days"][day]

            def _finite_optional_mm(code: str, value, converter):
                if value is None:
                    return None
                _finite_float(f"snotel {site} {day} {code}", value)
                return converter(value)

            con.execute(
                "INSERT INTO obs_snotel VALUES (?,?,?,?,?,?,?,?)",
                (site, day,
                 _finite_optional_mm("WTEQ", d.get("WTEQ"), in_to_mm),
                 _finite_optional_mm("PRCP", d.get("PRCP"), in_to_mm),
                 _finite_optional_mm("SNWD", d.get("SNWD"), in_to_mm),
                 _finite_optional_mm("TAVG", d.get("TAVG"), f_to_c),
                 _finite_optional_mm("TMAX", d.get("TMAX"), f_to_c),
                 _finite_optional_mm("TMIN", d.get("TMIN"), f_to_c)))
            n += 1
    return n


def ingest_reach_fit(con: sqlite3.Connection, doc: dict,
                     source_file: str) -> int:
    champ = doc.get("champion") or {}
    vol = (doc.get("effective_geometry") or {}).get("volume_m3")
    window = doc.get("window") or {}
    window_start = window.get("start_epoch")
    window_end = window.get("end_epoch")
    n_train = doc.get("n_train")
    n_holdout = doc.get("n_holdout")
    con.execute(
        "INSERT INTO fits_reach VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (source_file, vol,
         champ.get("q_lat"), champ.get("t_lat"), champ.get("c_mult"),
         champ.get("train_rmse"), champ.get("holdout_rmse"),
         champ.get("train_bias"), champ.get("holdout_bias"), 1,
         str(doc.get("status", "")),
         window_start, window_end, n_train, n_holdout))
    for row in doc.get("top10_train", [])[:10]:
        if (row.get("q_lat") == champ.get("q_lat")
                and row.get("t_lat") == champ.get("t_lat")
                and row.get("c_mult") == champ.get("c_mult")):
            continue
        con.execute(
            "INSERT INTO fits_reach VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (source_file, vol, row.get("q_lat"), row.get("t_lat"),
             row.get("c_mult"), row.get("train_rmse"),
             row.get("holdout_rmse"), row.get("train_bias"),
             row.get("holdout_bias"), 0, str(doc.get("status", "")),
             window_start, window_end, n_train, n_holdout))
    for nm in doc.get("null_models", []) or []:
        con.execute("INSERT INTO fits_reach_nulls VALUES (?,?,?,?,?,?,?,?)",
                    (source_file, str(nm.get("name", "?")),
                     nm.get("q_lat"), nm.get("t_lat"), nm.get("c_mult"),
                     nm.get("train_rmse"), nm.get("holdout_rmse"),
                     nm.get("k")))
    return 1


def ingest_snow_fit(con: sqlite3.Connection, doc: dict,
                    source_file: str) -> int:
    n = 0
    for site, rec in doc.get("sites", {}).items():
        fit = rec.get("fitted", {})
        hold = rec.get("holdout_swe_mm", {})
        # wind_loss is a dimensionless fraction in [0, 1]; reject anything else.
        wl = fit.get("wind_loss_effective")
        if wl is not None:
            wl_f = _finite_float(f"snow fit {site} wind_loss_effective", wl)
            if not 0.0 <= wl_f <= 1.0:
                raise ValueError(
                    f"snow fit {site}: wind_loss_effective={wl_f} outside "
                    f"[0, 1] (dimensionless fraction)")
        hold_start = hold.get("start_day")
        hold_end = hold.get("end_day")
        for label, value in (("holdout start_day", hold_start),
                             ("holdout end_day", hold_end)):
            if value is not None:
                if not isinstance(value, str) or not value:
                    raise ValueError(
                        f"snow fit {site}: {label} must be a nonempty string")
                try:
                    datetime.date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(
                        f"snow fit {site}: {label} {value!r} must be "
                        f"YYYY-MM-DD") from exc
        con.execute(
            "INSERT INTO fits_snow VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (source_file, site,
             (fit.get("k_melt_mm_per_deg_day")),
             (fit.get("wind_loss_effective")),
             (fit.get("train_rmse_mm")),
             hold.get("rmse"), hold.get("bias"),
             rec.get("null_persistence_rmse_mm"),
             rec.get("null_nomelt_rmse_mm"),
             rec.get("peak_timing_error_days"),
             str(rec.get("status", doc.get("status", ""))),
             hold_start, hold_end))
        n += 1
    return n


def build_con(*, build_id: str, census: dict, replay: dict,
              firehole: dict, snotel: dict,
              reach_fits: list[tuple[str, dict]] | None = None,
              snow_fits: list[tuple[str, dict]] | None = None,
              source_shas: dict | None = None,
              notes: str = "") -> sqlite3.Connection:
    """Build an in-memory store from parsed docs. Fits optional."""
    con = create_empty()
    parts = [f"census_trees={ingest_census(con, census)}",
             f"replay_cells+frames={ingest_replay(con, replay)}",
             f"obs_usgs={ingest_firehole(con, firehole)}",
             f"obs_snotel={ingest_snotel(con, snotel)}"]
    fit_notes = []
    for src, doc in (reach_fits or []):
        ingest_reach_fit(con, doc, src)
        parts.append(f"fits_reach+={src}")
    for src, doc in (snow_fits or []):
        ingest_snow_fit(con, doc, src)
        parts.append(f"fits_snow+={src}")
    if not reach_fits:
        fit_notes.append("no reach-fit artifacts: fits_reach(+nulls) empty")
    if not snow_fits:
        fit_notes.append("no snow-fit artifacts: fits_snow empty")
    con.execute(
        "INSERT INTO meta VALUES (?,?,?,?,?,?)",
        (SCHEMA_VERSION, build_id, json.dumps(source_shas or {}),
         datetime.datetime.now(datetime.timezone.utc).isoformat(),
         STATUS, "; ".join([notes] + fit_notes + parts)))
    con.commit()
    return con


def _source_record(path: Path) -> dict:
    """Return a path/basename/sha256/bytes record for one source file."""
    p = Path(path)
    return {
        "path": str(p.resolve()),
        "basename": p.name,
        "sha256": _sha256(p),
        "bytes": p.stat().st_size,
    }


def build_file(*, build_dir: Path, out: Path,
               census_path: Path, firehole_path: Path, snotel_path: Path,
               reach_fit_paths: list[Path] | None = None,
               snow_fit_paths: list[Path] | None = None) -> dict:
    """Build a store file from one build dir and obs inputs. Atomic write; refuses to overwrite."""
    build_dir, out = Path(build_dir), Path(out)
    if out.exists():
        raise FileExistsError(
            f"{out} already exists (derived artifacts are history; "
            f"choose a new --out name or remove it explicitly)")
    replay_path = build_dir / "river_replay.json"
    docs = {
        "river_replay.json": json.loads(replay_path.read_text()),
        "census": json.loads(Path(census_path).read_text()),
        "firehole_obs": json.loads(Path(firehole_path).read_text()),
        "snotel_obs": json.loads(Path(snotel_path).read_text()),
    }
    shas: dict[str, dict] = {
        f"derived/{build_dir.name}/river_replay.json": _source_record(replay_path),
        "census": _source_record(census_path),
        "firehole_obs": _source_record(firehole_path),
        "snotel_obs": _source_record(snotel_path),
    }
    reach_fits, snow_fits = [], []
    for p in reach_fit_paths or []:
        d = json.loads(Path(p).read_text())
        reach_fits.append((Path(p).name, d))
        shas[f"reach_fit:{Path(p).name}"] = _source_record(p)
    for p in snow_fit_paths or []:
        d = json.loads(Path(p).read_text())
        snow_fits.append((Path(p).name, d))
        shas[f"snow_fit:{Path(p).name}"] = _source_record(p)
    con = build_con(build_id=build_dir.name, census=docs["census"],
                    replay=docs["river_replay.json"],
                    firehole=docs["firehole_obs"], snotel=docs["snotel_obs"],
                    reach_fits=reach_fits, snow_fits=snow_fits,
                    source_shas=shas)
    import os
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    disk = sqlite3.connect(str(tmp))
    try:
        con.backup(disk)
        disk.commit()
    finally:
        disk.close()
    # Fsync tmp before the rename, then fsync the parent directory to survive a crash.
    try:
        file_handle = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(file_handle)
        finally:
            os.close(file_handle)
        if out.exists():
            raise FileExistsError(
                f"{out} appeared after existence check (concurrent writer); "
                f"refusing to overwrite")
        tmp.replace(out)
        dir_handle = os.open(str(out.parent), os.O_RDONLY)
        try:
            os.fsync(dir_handle)
        except OSError:
            pass
        finally:
            os.close(dir_handle)
    except OSError:
        if tmp.exists():
            tmp.unlink()
        raise
    # Mark the finished store read-only so a later open-for-write would fail.
    import stat
    try:
        mode = out.stat().st_mode
        out.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    except OSError:
        pass
    row = con.execute("SELECT notes FROM meta").fetchone()
    con.close()
    return {"out": str(out), "build_id": build_dir.name,
            "schema": SCHEMA_VERSION, "status": STATUS,
            "sources": len(shas), "notes": row[0] if row else ""}


# ---- read-only query layer (allow-listed tables/columns, no raw SQL) ----
QUERY_TABLES: dict[str, list[str]] = {
    "census_trees": ["stable_id", "x", "z", "crown_r_m",
                     "confidence", "peak_exg", "evidence_class"],
    "replay_cells": ["cell_id", "river_id", "s_m", "start_s_m", "end_s_m",
                     "length_m", "width_m", "depth_m",
                     "velocity_m_s", "volume_m3"],
    "replay_frames": ["t_s", "cell_id", "temperature_c"],
    "obs_usgs": ["site", "epoch", "discharge_m3_s", "temperature_c"],
    "obs_snotel": ["site", "day", "wteq_mm", "prcp_mm", "snwd_mm",
                   "tavg_c", "tmax_c", "tmin_c"],
    "fits_reach": ["source_file", "volume_m3", "q_lat", "t_lat", "c_mult",
                   "train_rmse", "holdout_rmse", "train_bias",
                   "holdout_bias", "champion", "status",
                   "window_start_epoch", "window_end_epoch",
                   "n_train", "n_holdout"],
    "fits_reach_nulls": ["source_file", "name", "q_lat", "t_lat", "c_mult",
                         "train_rmse", "holdout_rmse", "k"],
    "fits_snow": ["source_file", "site", "k_melt", "wind_loss",
                  "train_rmse_mm", "holdout_rmse_mm", "holdout_bias_mm",
                  "null_persistence_rmse_mm", "null_nomelt_rmse_mm",
                  "peak_timing_err_d", "status",
                  "holdout_start_day", "holdout_end_day"],
    "meta": ["schema_version", "build_id", "source_shas", "created_utc",
             "status", "notes"],
}
DEFAULT_LIMIT = 100
MAX_LIMIT = 5000
# Circle-radius bounds for density queries, in meters.
RADIUS_MIN_M = 0.1
RADIUS_MAX_M = 5000.0


# Per-table ordering constants document each query's supporting index.
ORDER_BY: dict[str, tuple[str, ...]] = {
    "census_trees": ("stable_id",),
    "replay_cells": ("cell_id",),
    "replay_frames": ("cell_id", "t_s"),
    "obs_usgs": ("site", "epoch"),
    "obs_snotel": ("site", "day"),
    "fits_reach": ("source_file", "champion DESC"),
    "fits_reach_nulls": ("source_file", "name"),
    "fits_snow": ("source_file", "site"),
    "meta": ("rowid",),
}


def _as_float_strict(name: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number (boolean rejected)")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number ({exc})") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def _as_int_strict(name: str, value) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer (boolean rejected)")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{name} must be an integer")
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s.lstrip("+-").isdigit():
            raise ValueError(f"{name} must be an integer")
        return int(s)
    raise ValueError(f"{name} must be an integer")


def _require_nonempty_string(name: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _require_enum(name: str, value, allowed) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {tuple(allowed)}")
    return value


def _open(con_or_path) -> sqlite3.Connection:
    """Return a read-only connection; caller-owned connections are not mutated."""
    if isinstance(con_or_path, sqlite3.Connection):
        return con_or_path
    p = Path(con_or_path)
    if not p.exists():
        raise NoStoreError(f"analysis store not found: {p}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = ON")
    return con


def query(con_or_path, table: str, *, columns: list[str] | None = None,
          limit: int = DEFAULT_LIMIT, offset: int = 0,
          **filters) -> dict:
    """Read-only bounded query over allow-listed tables/columns/filters."""
    if table not in QUERY_TABLES:
        raise ValueError(
            f"unknown table {table!r}; have {sorted(QUERY_TABLES)}")
    allowed = QUERY_TABLES[table]
    cols = list(allowed) if columns is None else list(columns)
    if not cols:
        raise ValueError("columns must be nonempty")
    for c in cols:
        if c not in allowed:
            raise ValueError(f"unknown column {c!r} for table {table!r}")
    limit = _as_int_strict("limit", limit)
    offset = _as_int_strict("offset", offset)
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be in [1, {MAX_LIMIT}]")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    where, args = [], []
    spatial = None
    if table == "census_trees":
        for k in ("x0", "x1", "z0", "z1"):
            if k in filters:
                filters[k] = _as_float_strict(k, filters.pop(k))
        x0 = filters.pop("x0", None)
        x1 = filters.pop("x1", None)
        z0 = filters.pop("z0", None)
        z1 = filters.pop("z1", None)
        conf = filters.pop("confidence", None)
        if conf is not None:
            _require_enum("confidence", conf, CONFIDENCES)
            where.append("census_trees.confidence = ?")
            args.append(conf)
        ec = filters.pop("evidence_class", None)
        if ec is not None:
            _require_nonempty_string("evidence_class", ec)
            where.append("census_trees.evidence_class = ?")
            args.append(ec)
        if (x0 is None) != (x1 is None) or (z0 is None) != (z1 is None):
            raise ValueError("bbox needs both x0+x1 and/or both z0+z1")
        if x0 is not None and z0 is not None:
            spatial = (x0, x1, z0, z1)
        elif x0 is not None:
            where.append("census_trees.x BETWEEN ? AND ?")
            args += [min(x0, x1), max(x0, x1)]
        elif z0 is not None:
            where.append("census_trees.z BETWEEN ? AND ?")
            args += [min(z0, z1), max(z0, z1)]
    elif table == "replay_cells":
        for k in ("river_id", "cell_id"):
            if k in filters:
                v = _require_nonempty_string(k, filters.pop(k))
                where.append(f"replay_cells.{k} = ?")
                args.append(v)
    elif table == "replay_frames":
        if "cell_id" in filters:
            v = _require_nonempty_string("cell_id", filters.pop("cell_id"))
            where.append("replay_frames.cell_id = ?")
            args.append(v)
        for k, col in (("t0", "t_s"), ("t1", "t_s")):
            if k in filters:
                filters[k] = _as_float_strict(k, filters.pop(k))
        t0 = filters.pop("t0", None)
        t1 = filters.pop("t1", None)
        if t0 is not None:
            where.append("replay_frames.t_s >= ?")
            args.append(t0)
        if t1 is not None:
            where.append("replay_frames.t_s <= ?")
            args.append(t1)
    elif table == "obs_usgs":
        if "site" in filters:
            v = _require_nonempty_string("site", filters.pop("site"))
            where.append("obs_usgs.site = ?")
            args.append(v)
        for k in ("epoch0", "epoch1"):
            if k in filters:
                filters[k] = _as_float_strict(k, filters.pop(k))
        if "epoch0" in filters:
            where.append("obs_usgs.epoch >= ?")
            args.append(filters.pop("epoch0"))
        if "epoch1" in filters:
            where.append("obs_usgs.epoch <= ?")
            args.append(filters.pop("epoch1"))
    elif table == "obs_snotel":
        if "site" in filters:
            v = _require_nonempty_string("site", filters.pop("site"))
            where.append("obs_snotel.site = ?")
            args.append(v)
        for k in ("day0", "day1"):
            if k in filters:
                filters[k] = _require_nonempty_string(k, filters.pop(k))
        if "day0" in filters:
            where.append("obs_snotel.day >= ?")
            args.append(filters.pop("day0"))
        if "day1" in filters:
            where.append("obs_snotel.day <= ?")
            args.append(filters.pop("day1"))
    if filters:
        raise ValueError(
            f"unknown filter(s) for {table}: {sorted(filters)}")

    con = _open(con_or_path)
    try:
        if spatial is not None:
            x0, x1, z0, z1 = spatial
            sql = ("SELECT " + ", ".join(f't."{c}"' for c in cols) +
                   " FROM census_trees t JOIN census_rtree r "
                   "ON r.tree_row = t.rowid "
                   "WHERE r.x0 BETWEEN ? AND ? AND r.z0 BETWEEN ? AND ?")
            rargs = [min(x0, x1), max(x0, x1), min(z0, z1), max(z0, z1)]
            if where:
                sql += " AND " + " AND ".join(
                    w.replace("census_trees.", "t.") for w in where)
            sql += " ORDER BY t.stable_id LIMIT ? OFFSET ?"
            cur = con.execute(sql, rargs + args + [limit + 1, offset])
            cols_out = cols
        else:
            sel = ", ".join(f'"{c}"' for c in cols)
            sql = f'SELECT {sel} FROM "{table}"'
            if where:
                sql += " WHERE " + " AND ".join(where)
            order_cols = ", ".join(ORDER_BY[table])
            sql += f" ORDER BY {order_cols} LIMIT ? OFFSET ?"
            cur = con.execute(sql, args + [limit + 1, offset])
            cols_out = cols
        rows = cur.fetchall()
    finally:
        if not isinstance(con_or_path, sqlite3.Connection):
            con.close()
    truncated = len(rows) > limit
    return {"table": table, "columns": cols_out,
            "rows": [list(r) for r in rows[:limit]],
            "n": min(len(rows), limit), "truncated": truncated,
            "limit": limit, "offset": offset}


def _validate_circle(x, z, r):
    x = _as_float_strict("x", x)
    z = _as_float_strict("z", z)
    r = _as_float_strict("r", r)
    if not RADIUS_MIN_M <= r <= RADIUS_MAX_M:
        raise ValueError(
            f"radius r must be in [{RADIUS_MIN_M}, {RADIUS_MAX_M}] m")
    return x, z, r


def census_center_count(con_or_path, x: float, z: float,
                        r: float) -> dict:
    """Count tree centers inside the circle of radius r m."""
    x, z, r = _validate_circle(x, z, r)
    con = _open(con_or_path)
    try:
        cur = con.execute(
            "SELECT t.x, t.z FROM census_trees t JOIN census_rtree r "
            "ON r.tree_row = t.rowid "
            "WHERE r.x0 BETWEEN ? AND ? AND r.z0 BETWEEN ? AND ?",
            (x - r, x + r, z - r, z + r))
        inside = sum(1 for px, pz in cur
                     if math.hypot(px - x, pz - z) <= r)
    finally:
        if not isinstance(con_or_path, sqlite3.Connection):
            con.close()
    area_ha = math.pi * r ** 2 / 1e4
    return {"n": inside, "area_ha": round(area_ha, 4),
            "trees_per_ha": round(inside / area_ha, 1)}


def census_crown_overlap_count(con_or_path, x: float, z: float,
                               r: float) -> dict:
    """Count tree crowns overlapping the circle of radius r m."""
    x, z, r = _validate_circle(x, z, r)
    con = _open(con_or_path)
    try:
        row = con.execute(
            "SELECT COALESCE(MAX(crown_r_m), 0.0) FROM census_trees"
        ).fetchone()
        max_crown = float(row[0] or 0.0)
        probe = r + max_crown
        cur = con.execute(
            "SELECT t.x, t.z, t.crown_r_m FROM census_trees t "
            "JOIN census_rtree r ON r.tree_row = t.rowid "
            "WHERE r.x0 BETWEEN ? AND ? AND r.z0 BETWEEN ? AND ?",
            (x - probe, x + probe, z - probe, z + probe))
        inside = sum(1 for px, pz, pc in cur
                     if math.hypot(px - x, pz - z) <= r + float(pc or 0.0))
    finally:
        if not isinstance(con_or_path, sqlite3.Connection):
            con.close()
    area_ha = math.pi * r ** 2 / 1e4
    return {"n": inside, "area_ha": round(area_ha, 4),
            "trees_per_ha": round(inside / area_ha, 1)}


# Backward-compatible alias; llm_backend reads this name.
census_circle_count = census_center_count
