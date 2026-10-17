"""HTTP backend for census analysis and proposal review. Stdlib only."""
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from yellowstone_python.common.io import write_json_atomic

from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG

from yellowstone_python.common.io import sha256_file as _sha256

import hashlib
import json
import math
import re
import socket
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from yellowstone_python.service.server import JsonRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yellowstone_python.common.provenance import default_world_root

PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORLD = default_world_root()
DEFAULT_DERIVED = PKG_ROOT / "derived"
CENSUS_FILE = DEFAULT_DERIVED / "census.json"
# Per-request socket read/write timeout. Caps slow-client exposure.
REQUEST_SOCKET_TIMEOUT_S = 30.0
# Firehole site centroid used by the solar snapshot producer.

# Same zone definitions as canopy_census --stats, plus full-detail box.
ZONES = {
    "spring_0_50m": {"circle": (-94.7, -10.6, 50.0)},
    "apron_50_100m": {"ring": (-94.7, -10.6, 50.0, 100.0)},
    "transition_100_200m": {"ring": (-94.7, -10.6, 100.0, 200.0)},
    "outwash_200_400m": {"ring": (-94.7, -10.6, 200.0, 400.0)},
    "overlook_knoll_r120": {"circle": (-252.0, 159.0, 120.0)},
    "detail_full": {"box": (-640.0, -640.0, 640.0, 640.0)},
}

ACCURACY_NOTES = ["Canopy detections require independent crown validation."]


# Reject density radii outside [MIN_RADIUS_M, MAX_RADIUS_M], with bounds from analysis_store.
from yellowstone_python.service.analysis_store import RADIUS_MAX_M as MAX_RADIUS_M
from yellowstone_python.service.analysis_store import RADIUS_MIN_M as MIN_RADIUS_M
# Legitimate /api/propose bodies are <1 KB; anything larger is junk/DoS.
MAX_BODY_BYTES = 64 * 1024
# Review logs are returned inline; longer ones are truncated with a marker.
PROPOSAL_LOG_LIMIT = 1000


class DataError(RuntimeError):
    """A data file on disk is missing or corrupt (server-side -> HTTP 500)."""


def _load_json(path: Path) -> dict | list:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"{Path(path).name}: missing file ({exc})") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise DataError(f"{Path(path).name}: invalid JSON or encoding ({exc})") from exc
    except OSError as exc:
        raise DataError(f"{Path(path).name}: unreadable ({exc})") from exc


def _as_float(name: str, value) -> float:
    """Strict numeric coercion: rejects bools and non-finite values."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not boolean")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number ({exc})") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def _as_int(name: str, value) -> int:
    """Strict integer coercion: rejects bools, truncating floats, int(inf)."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, not boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{name} must be an integer")
        return int(value)
    if isinstance(value, str):
        if not re.fullmatch(r"[+-]?\d+", value.strip()):
            raise ValueError(f"{name} must be an integer")
        return int(value.strip())
    raise ValueError(f"{name} must be an integer")




def _wind_direction_from_vector(vx: float, vz: float) -> float:
    """Meteorological from-direction in [0, 360) given a +x east, +z south wind-to vector."""
    deg = math.degrees(math.atan2(-float(vx), -float(vz)))
    return deg % 360.0


def _validate_placement_doc(doc, name: str) -> None:
    """Shared schema check for placements.json and placement_overrides.json.
Raises DataError on any violation."""
    if not isinstance(doc, dict):
        raise DataError(f"{name}: top-level must be an object")
    for key in ("trees", "add"):
        if key not in doc:
            continue
        values = doc[key]
        if not isinstance(values, list):
            raise DataError(
                f"{name}: {key!r} must be a list, got "
                f"{type(values).__name__}")
        for i, rec in enumerate(values):
            if not isinstance(rec, dict):
                raise DataError(
                    f"{name} {key} #{i}: record must be an object, got "
                    f"{type(rec).__name__}")
    if "remove" in doc:
        values = doc["remove"]
        if not isinstance(values, list):
            raise DataError(
                f"{name}: 'remove' must be a list, got "
                f"{type(values).__name__}")
        for i, rec in enumerate(values):
            if not isinstance(rec, str):
                raise DataError(
                    f"{name} remove #{i}: stable id must be a string, "
                    f"got {type(rec).__name__}")
    if "replace" in doc:
        replace = doc["replace"]
        if not isinstance(replace, (dict, list)):
            raise DataError(
                f"{name}: 'replace' must be an object or list, got "
                f"{type(replace).__name__}")


def _coerce_pos_xz(name: str, rec: dict) -> tuple[float, float]:
    """Extract [x, y, z] from a placement record and return (x, z)."""
    if "position" not in rec:
        raise DataError(f"{name}: missing 'position'")
    pos = rec["position"]
    if not isinstance(pos, (list, tuple)) or len(pos) < 3:
        raise DataError(f"{name}: 'position' must be [x, y, z]")
    try:
        return (_as_float(f"{name} x", pos[0]),
                _as_float(f"{name} z", pos[2]))
    except ValueError as exc:
        raise DataError(str(exc)) from exc


class Backend:
    """Cached file-backed state. All methods read-only (no writes)."""

    def __init__(self, world: Path = DEFAULT_WORLD,
                 derived: Path = DEFAULT_DERIVED,
                 store: Path | None = None,
                 hydrology=None):
        self.world = Path(world)
        self.derived = Path(derived)
        self._census = None
        self._census_signature = None
        self._census_lock = threading.Lock()
        self._store = Path(store) if store is not None else None
        self.hydrology = hydrology
        self._propose_lock = threading.Lock()
        self._terrain_cache = None
        self._shell_cache = None

    def store_path(self) -> Path | None:
        """Select a store bound to the published build and active census."""
        if self._store is not None:
            return self._store if self._store.exists() else None
        build_id = None
        published = self.world / "data/ecosystem.json"
        if published.is_file() or (self.world / "data/release.json").is_file():
            document = self.ecosystem()
            if isinstance(document, dict):
                value = document.get("build_id")
                if isinstance(value, str) and value:
                    build_id = value
        newest_mtime = -1.
        if build_id is None:
            for checks in self.derived.glob("*/CHECKS.json"):
                try:
                    document = json.loads(checks.read_text())
                    mtime = checks.stat().st_mtime
                except (OSError, ValueError):
                    continue
                if (isinstance(document, dict) and document.get("passed") is True
                        and mtime > newest_mtime):
                    newest_mtime = mtime
                    build_id = checks.parent.name
        if build_id is None:
            return None
        census = self.derived / "census.json"
        with self._census_lock:
            try:
                stat = census.stat()
                signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
                if signature != getattr(self, "_store_census_signature", None):
                    digest = _sha256(census)
                    self._store_census_signature = signature
                    self._store_census_sha = digest
                census_sha = self._store_census_sha
            except OSError:
                return None
        best, best_mtime = None, -1.
        for cand in self.derived.glob("analysis_*.sqlite"):
            try:
                mtime = cand.stat().st_mtime
                con = sqlite3.connect(f"file:{cand}?mode=ro", uri=True)
            except (OSError, sqlite3.Error):
                continue
            try:
                row = con.execute("SELECT build_id, source_shas FROM meta LIMIT 1").fetchone()
                sources = json.loads(row[1]) if row is not None else {}
                record = sources.get("census") if isinstance(sources, dict) else None
                if (row is not None and row[0] == build_id and isinstance(record, dict)
                        and record.get("sha256") == census_sha and mtime > best_mtime):
                    best, best_mtime = cand, mtime
            except (sqlite3.Error, TypeError, ValueError):
                continue
            finally:
                con.close()
        return best

    def query_store(self, table: str, columns: list[str] | None = None,
                    limit: int = 100, offset: int = 0,
                    **filters) -> dict:
        """Read-only bounded query over the analysis store.
NoStoreError (HTTP 503) when no store exists; ValueError (HTTP 400) on validation."""
        from yellowstone_python.service.analysis_store import NoStoreError, query as _store_query
        path = self.store_path()
        if path is None:
            raise NoStoreError(
                "no analysis store matches the active build and census; build one with "
                "tools/build_store.py --build derived/<id>")
        out = _store_query(path, table, columns=columns,
                           limit=limit, offset=offset, **filters)
        out["store"] = path.name
        return out

    def density(self, x: float, z: float, r: float) -> dict:
        """Circle crown count by canopy center.
Store-backed when a store exists; crown-overlap counts live under census_crown_overlap_count."""
        path = self.store_path()
        if path is not None:
            from yellowstone_python.service.analysis_store import census_center_count
            out = census_center_count(path, x, z, r)
            out["source"] = path.name
            return out
        out = self.circle_stats(self.census_points(), x, z, r)
        out["source"] = "census.json"
        return out

    # ---- cached loaders ----
    def census(self) -> dict:
        path = self.derived / "census.json"
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        except OSError as exc:
            raise DataError(f"census.json: {exc}") from exc
        with self._census_lock:
            if self._census is None or getattr(self, "_census_signature", None) != signature:
                doc = _load_json(path)
                if not isinstance(doc, dict):
                    raise DataError(
                        f"census.json: must be a JSON object, got "
                        f"{type(doc).__name__}")
                self._census = doc
                self._census_signature = signature
        return self._census

    def placements(self) -> dict:
        return _load_json(self.world / "data" / "placements.json")

    def overrides(self) -> dict:
        return _load_json(self.world / "data" / "placement_overrides.json")

    def ecosystem(self) -> dict:
        pointer_path = self.world / "data/release.json"
        if pointer_path.is_file():
            from yellowstone_python.publish import verify_release
            pointer = _load_json(pointer_path)
            relative = "data/releases/" + str(pointer.get("release_id", "")) + "/RELEASE.json"
            if pointer.get("manifest") != relative or len(str(pointer.get("release_id", ""))) != 64:
                raise DataError("Invalid active release pointer")
            manifest_path = self.world / relative
            if _sha256(manifest_path) != pointer.get("sha256"):
                raise DataError("Active release manifest hash mismatch")
            manifest = _load_json(manifest_path)
            verify_release(manifest_path.parent, manifest)
            return _load_json(manifest_path.parent / "data/ecosystem.json")
        return _load_json(self.world / "data" / "ecosystem.json")

    def weather(self, hour: float | None = None, *, epoch_unix: float | None = None,
                elapsed_hours: float | None = None) -> dict:
        """Return shared weather at the requested simulation hour."""
        from yellowstone_python.atmosphere.microclimate import load_weather_bundle, weather_snapshot
        from yellowstone_python.atmosphere.time_utils import resolve_query_epoch
        bundle = load_weather_bundle(str(self.derived / "met.json"))
        requested = _as_float("hour", hour) if hour is not None else None
        eco = self.ecosystem() if any((self.world / "data" / name).is_file() for name in ("ecosystem.json", "release.json")) else {}
        weather = eco.get("weather", {})
        offset = float(weather.get("utc_offset_hours", -6.))
        epoch = resolve_query_epoch(eco.get("simulation_epoch_unix"), offset,
            local_hour=requested, elapsed_hours=elapsed_hours, epoch_unix=epoch_unix)
        clock = ((epoch + offset * 3600.) / 3600.) % 24.
        bundle_window = {"status": "available" if bundle is not None else "unavailable_missing"}
        if weather.get("use_met_bundle") is False:
            bundle = None
            bundle_window = {"status": "disabled_in_scenario"}
        if bundle is not None and not float(bundle["hourly"][0][0]) <= epoch <= float(bundle["hourly"][-1][0]):
            bundle_window = {"status": "unavailable_out_of_window", "requested_epoch_unix": epoch,
                "first_epoch_unix": float(bundle["hourly"][0][0]), "last_epoch_unix": float(bundle["hourly"][-1][0])}
            bundle = None
        snapshot = weather_snapshot(float(epoch), weather, bundle)
        current = snapshot["weather"]
        precip_status = snapshot["source"]["precipitation_status"]
        precip = current["precipitation_rate_mm_h"] if precip_status != "unavailable" else None
        hydrology_state = {"status": "not_configured"}
        wetness = None
        if self.hydrology is not None:
            report = self.hydrology.snapshot(weather={
                "air_c": current["air_temperature_c"],
                "humidity": current["relative_humidity"],
                "wind_speed_m_s": current["wind_speed_mps"],
                "precipitation_rate_mm_h": precip}, hour=clock)
            hydrology_state = report.state
            wetness = report.ground_wetness_fraction
        current["ground_wetness_fraction"] = wetness
        snapshot["source"].update({"hour_requested": requested, "elapsed_hours_requested": elapsed_hours,
            "epoch_requested": epoch_unix, "clock_policy": "scenario_absolute_epoch_with_recorded_local_offset",
            "weather_bundle_window": bundle_window,
            "hydrology_status": hydrology_state.get("status", "available")})
        snapshot.update({"air_c": current["air_temperature_c"],
                         "humidity": current["relative_humidity"],
                         "cloud": current["cloud_fraction"],
                         "wind_xz_mps": current["wind_xz_mps"],
                         "gust_mps": float(weather.get("gust_mps", 0.45)),
                         "snow_fraction": current["snow_fraction"],
                         "snow_partition_source": snapshot["source"]["snow_partition_source"],
                         "precipitation_rate_mm_h": precip,
                         "precipitation_status": precip_status,
                         "ground_wetness_fraction": wetness,
                         "hour_requested": requested,
                         "bundle": bundle.get("schema") if bundle else None,
                         "hydrology_sim_state": hydrology_state})
        return snapshot

    # ---- tree math ----
    @staticmethod
    def circle_stats(points: list, x: float, z: float, r: float) -> dict:
        x, z, r = _as_float("x", x), _as_float("z", z), _as_float("r", r)
        if not MIN_RADIUS_M <= r <= MAX_RADIUS_M:
            raise ValueError(
                f"radius r must be in [{MIN_RADIUS_M}, {MAX_RADIUS_M}] m")
        inside = sum(1 for px, pz in points
                     if math.hypot(px - x, pz - z) <= r)
        try:
            area_ha = math.pi * r ** 2 / 1e4
        except OverflowError as exc:
            raise ValueError(
                f"radius r={r} overflows area computation") from exc
        if not math.isfinite(area_ha) or area_ha <= 0:
            raise ValueError(f"radius r={r} gives non-finite area")
        return {"n": inside, "area_ha": round(area_ha, 4),
                "trees_per_ha": round(inside / area_ha, 1)}

    def census_points(self) -> list:
        doc = self.census()
        trees = doc.get("trees")
        if not isinstance(trees, list):
            raise DataError(
                "census.json: 'trees' must be a list, got "
                f"{type(trees).__name__}")
        out = []
        for i, t in enumerate(trees):
            if not isinstance(t, dict):
                raise DataError(
                    f"census.json tree #{i}: record must be an object, "
                    f"got {type(t).__name__}")
            try:
                x = _as_float(f"census.json tree #{i} x", t["x"])
                z = _as_float(f"census.json tree #{i} z", t["z"])
            except KeyError as exc:
                raise DataError(
                    f"census.json tree #{i}: missing key {exc}") from exc
            except ValueError as exc:
                # Server-side data rot: HTTP 500.
                raise DataError(str(exc)) from exc
            out.append((x, z))
        return out

    def placed_points(self) -> list:
        place = self.placements()
        _validate_placement_doc(place, "placements.json")
        ov = self.overrides()
        _validate_placement_doc(ov, "placement_overrides.json")
        removed = set(ov.get("remove", []))
        replacements = ov.get("replace", {})
        if not isinstance(replacements, dict):
            raise DataError("placement_overrides.json: replace must be an object")
        records = [(f"placements.json tree #{i}", t)
                   for i, t in enumerate(place.get("trees", []))]
        for i, r in enumerate(ov.get("add", [])):
            if r.get("kind") not in {"pine", "snag"}:
                continue
            records.append((f"placement_overrides add #{i}", r))
        pts = []
        for name, record in records:
            identity = str(record.get("id", record.get("stable_id", "")))
            if identity in removed:
                continue
            record = replacements.get(identity, record)
            if not isinstance(record, dict):
                raise DataError(f"{name}: replacement must be an object")
            if record.get("kind", "pine") not in {"pine", "snag"}:
                continue
            pts.append(_coerce_pos_xz(name, record))
        return pts

    def census_accuracy_notes(self) -> list[str]:
        census = self.census()
        methods = {tree.get("method") for tree in census.get("trees", [])
                   if isinstance(tree, dict)}
        if "lidar_lmf" in methods:
            return [
                "LiDAR detections estimate dominant crowns; blind precision and recall are unavailable.",
                "Total and subcanopy stem counts remain unknown.",
            ]
        return list(ACCURACY_NOTES)

    def zones(self) -> dict:
        from yellowstone_python.census.canopy_census import density_stats
        trees = self.census_points()
        return density_stats(trees, ZONES)

    def compare(self, x: float, z: float, r: float) -> dict:
        x, z, r = _as_float("x", x), _as_float("z", z), _as_float("r", r)
        obs = self.circle_stats(self.census_points(), x, z, r)
        placed = self.circle_stats(self.placed_points(), x, z, r)
        return {
            "center_xz": [x, z], "radius_m": r,
            "area_ha": obs["area_ha"],
            "observed_census": obs,
            "placed_game": placed,
            "deficit_observed_minus_placed": obs["n"] - placed["n"],
            "interpretation": (
                "Positive deficit means fewer rendered tree centers than detected crown centers; "
                "negative means more. Counts do not establish total stem density or canopy coverage."),
            "census_source": self.census().get("source"),
        }

    def placements_summary(self) -> dict:
        from collections import Counter
        place = self.placements()
        _validate_placement_doc(place, "placements.json")
        ov = self.overrides()
        _validate_placement_doc(ov, "placement_overrides.json")
        staged_add = ov.get("add", [])
        try:
            return {
                "baked_trees": len(place.get("trees", [])),
                "baked_other": {k: len(v) for k, v in place.items()
                                if isinstance(v, list) and k != "trees"},
                "staged_add": len(staged_add),
                "staged_add_by_kind": dict(Counter(
                    r.get("kind") for r in staged_add)),
                "staged_remove": len(ov.get("remove", [])),
                "staged_replace": len(ov.get("replace", [])),
                "rule": "proposals enter via placement_overrides.json::{add}; placements.json is read-only",
            }
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise DataError(f"placements data: {exc}") from exc

    def ecosystem_summary(self) -> dict:
        from collections import Counter
        try:
            eco = self.ecosystem()
        except DataError:
            raise
        except (KeyError, TypeError, AttributeError) as exc:
            raise DataError(f"ecosystem.json: {exc}") from exc
        try:
            reaches = [
                {"id": r["id"], "temperature_c": round(float(r["temperature_c"]), 2)}
                for r in eco.get("river_reaches", [])]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DataError(
                f"ecosystem.json river_reaches: {exc}") from exc
        try:
            patches = [
                {"id": p["id"], "biomass": round(float(p.get("biomass", 0)), 3),
                 "moisture": p.get("moisture")}
                for p in eco.get("patches", [])]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DataError(f"ecosystem.json patches: {exc}") from exc
        wildlife = eco.get("wildlife", [])
        if not isinstance(wildlife, list):
            raise DataError(
                "ecosystem.json wildlife: must be a list, got "
                f"{type(wildlife).__name__}")
        for i, w in enumerate(wildlife):
            if not isinstance(w, dict):
                raise DataError(
                    f"ecosystem.json wildlife #{i}: record must be an "
                    f"object, got {type(w).__name__}")
        try:
            by_kind = dict(Counter(w.get("kind") for w in wildlife))
        except (TypeError, AttributeError) as exc:
            raise DataError(f"ecosystem.json wildlife: {exc}") from exc
        return {
            "clock_hour": eco.get("clock_hour"),
            "weather": eco.get("weather"),
            "river_reaches": reaches,
            "patches": patches,
            "wildlife_total": len(wildlife),
            "wildlife_by_kind": by_kind,
            "status": eco.get("status"),
        }

    def latest_build(self) -> dict:
        best, best_sig = None, None
        for checks in self.derived.glob("*/CHECKS.json"):
            try:
                stat = checks.stat()
                sig = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            except FileNotFoundError:
                continue
            if best_sig is None or sig > best_sig:
                best_sig = sig
                best = checks
        if best is None:
            return {"build": None, "note": 'no derived/*/CHECKS.json '}
        doc = _load_json(best)
        build_doc = {}
        build_file = best.parent / "BUILD.json"
        if build_file.exists():
            build_doc = _load_json(build_file)
        return {"build_id": best.parent.name, "checks": doc,
                "build": build_doc}

    def snapshot(self) -> dict:
        files = {
            "census.json": self.derived / "census.json",
            "ecosystem.json": self.world / "data" / "ecosystem.json",
            "placements.json": self.world / "data" / "placements.json",
            "placement_overrides.json": self.world / "data" / "placement_overrides.json",
            "world.json": self.world / "data" / "world.json",
        }
        sources = {}
        for k, p in files.items():
            if p.exists():
                try:
                    sources[k] = {"sha256": _sha256(p)}
                except OSError:
                    continue  # raced deletion; section errors below say more
        out: dict = {
            "contract": "yellowstone.llm_snapshot.v1",
            "world_id": "yellowstone_midway",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
        }
        # Fault-isolated sections: one corrupt file degrades its own section.
        try:
            census = self.census()
            out["census"] = {
                "n": census.get("n"), "status": census.get("status"),
                "source": census.get("source"), "zones": self.zones()}
        except DataError as exc:
            out["census"] = {"error": f"data: {exc}"}
        for key, fn in (("placements", self.placements_summary),
                        ("ecosystem", self.ecosystem_summary),
                        ("latest_build", self.latest_build)):
            try:
                out[key] = fn()
            except DataError as exc:
                out[key] = {"error": f"data: {exc}"}
        try:
            out["accuracy_notes"] = self.census_accuracy_notes()
        except DataError:
            out["accuracy_notes"] = list(ACCURACY_NOTES)
        out["limitations"] = [
            "Dominant-crown detections are not a total stem survey.",
            "Placement dimensions retain their recorded measurement, transfer or authored status.",
            "No calibrated hydrology/bathymetry/organism counts.",
        ]
        return out

    def propose(self, guild: str, x: float, z: float, radius_m: float,
                count: int, seed: int = 7, habitat_id: str = "forest_edge",
                suitability_threshold: float = 0.12,
                canopy: float = 0.6) -> dict:
        """Dry-run only: suitability proposals + machine review, no writes."""
        x = _as_float("x", x)
        z = _as_float("z", z)
        radius_m = _as_float("radius_m", radius_m)
        count = _as_int("count", count)
        seed = _as_int("seed", seed)
        suitability_threshold = _as_float(
            "suitability_threshold", suitability_threshold)
        canopy = _as_float("canopy", canopy)
        with self._propose_lock:
            from yellowstone_python.thermal_features.pool_crust import build_all as build_shells
            from yellowstone_python.thermal_features.pool_crust import in_apron
            from yellowstone_python.authoring.review_proposals import review
            from yellowstone_python.land.vegetation import GUILDS, load_terrain, moisture_at, terrain_fns
            from yellowstone_python.land.vegetation import propose_plantings_reviewed

        if guild not in GUILDS:
            raise ValueError(f"unknown guild {guild!r}; have {list(GUILDS)}")
        if not isinstance(habitat_id, str) or not habitat_id.strip():
            raise ValueError("habitat_id must be a non-empty string")
        known_habitats = {"unsuitable_matrix"}
        for spec in GUILDS.values():
            known_habitats |= set(spec.get("needs", ()))
            known_habitats |= set(spec.get("excluded", ()))
        if habitat_id not in known_habitats:
            raise ValueError(
                f"unknown habitat_id {habitat_id!r}; "
                f"have {sorted(known_habitats)}")
        from yellowstone_python.land.vegetation import HALF
        if not (-HALF <= x <= HALF and -HALF <= z <= HALF):
            raise ValueError(
                f"proposal center ({x}, {z}) lies outside the baked world square (+/-{HALF} m); records would never bake")
        if not (0 < radius_m <= 500):
            raise ValueError("radius_m must be in (0, 500]")
        if not (0 < count <= 500):
            raise ValueError("count must be in (0, 500]")
        if not (0.0 <= suitability_threshold <= 1.0):
            raise ValueError("suitability_threshold must be in [0, 1]")
        if not (0.0 <= canopy <= 1.0):
            raise ValueError("canopy must be in [0, 1]")
        with self._propose_lock:
            if self._shell_cache is None:
                try:
                    world = _load_json(self.world / "data" / "world.json")
                    pools = world["pools"]
                except KeyError as exc:
                    raise DataError(
                        f"world.json: missing 'pools' ({exc})") from exc
                self._shell_cache = build_shells(pools)
            shells = self._shell_cache
            if self._terrain_cache is None:
                try:
                    self._terrain_cache = terrain_fns(load_terrain(
                        str(self.world / "data" / "terrain.f32")))
                except (ValueError, OSError) as exc:
                    raise DataError(
                        f"terrain.f32: unreadable ({exc})") from exc
            sample, slope = self._terrain_cache
        frozen = self.world / "data" / "ecosystem.json.pre-python"
        try:
            eco_doc = _load_json(frozen if frozen.exists()
                                 else self.world / "data" / "ecosystem.json")
            patches = eco_doc["patches"]
        except KeyError as exc:
            raise DataError(
                f"ecosystem data: missing 'patches' ({exc})") from exc
        accepted, log = propose_plantings_reviewed(
            guild, (x, z), radius_m, count, seed, habitat_id=habitat_id,
            exclusion_test=lambda ax, az: any(in_apron(ax, az, s) for s in shells),
            terrain_fn=(sample, slope), patches=patches, canopy=canopy,
            suitability_threshold=suitability_threshold)
        try:
            trees = [(t["position"][0], t["position"][2])
                     for t in self.placements().get("trees", [])]
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise DataError(f"placements.json: {exc}") from exc
        ok, ledger = review(accepted, shells, sample, slope, trees,
                            lambda ax, az: moisture_at(ax, az, patches),
                            canopy=canopy,
                            suitability_threshold=suitability_threshold)
        return {"proposals": accepted, "proposal_log": log,
                "review_accepted": ok, "review_ledger": ledger,
                "note": "dry run only; stage via review_proposals --apply after human NAIP review"}


# ---- HTTP layer (stdlib only) ----
class _Handler(JsonRequestHandler):
    backend: Backend = None  # set by serve()

    def setup(self) -> None:
        # Per-connection socket timeout bounds slow-client exposure.
        super().setup()
        try:
            self.request.settimeout(REQUEST_SOCKET_TIMEOUT_S)
        except (OSError, socket.error):
            pass

    def _send(self, obj: dict, status: int = 200) -> None:
        try:
            self.write_json(obj, status)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _params(self) -> dict:
        return {k: v[0] for k, v in
                parse_qs(urlparse(self.path).query).items()}

    def do_GET(self) -> None:  # noqa: N802
        from yellowstone_python.service.analysis_store import NoStoreError
        if not self.guard(mutating=False):
            return
        try:
            route = urlparse(self.path).path
            b = self.backend
            if route in ("/api", "/"):
                return self._send({"endpoints": [
                    "GET /api/snapshot", "GET /api/census/zones",
                    "GET /api/density?x=&z=&r=",
                    "GET /api/compare?x=&z=&r=",
                    "GET /api/placements/summary",
                    "GET /api/ecosystem/summary",
                    "GET /api/build/latest",
                    "GET /api/weather?hour=",
                    "GET /api/query?table=census_trees&x0=&x1=&z0=&z1=&limit=",
                    "POST /api/propose"]})
            if route == "/api/snapshot":
                return self._send(b.snapshot())
            if route == "/api/census/zones":
                return self._send(b.zones())
            if route == "/api/density":
                p = self._params()
                return self._send(b.density(
                    float(p["x"]), float(p["z"]),
                    float(p.get("r", 120))))
            if route == "/api/query":
                p = self._params()
                if "table" not in p:
                    return self._send(
                        {"error": "missing required table parameter"}, 400)
                table = p.pop("table")
                cols = p.pop("columns", None)
                columns = ([c.strip() for c in cols.split(",") if c.strip()]
                           if cols is not None else None)
                limit = p.pop("limit", 100)
                offset = p.pop("offset", 0)
                return self._send(b.query_store(
                    table, columns=columns,
                    limit=limit, offset=offset, **p))
            if route == "/api/compare":
                p = self._params()
                return self._send(b.compare(
                    float(p["x"]), float(p["z"]), float(p.get("r", 120))))
            if route == "/api/placements/summary":
                return self._send(b.placements_summary())
            if route == "/api/ecosystem/summary":
                return self._send(b.ecosystem_summary())
            if route == "/api/build/latest":
                return self._send(b.latest_build())
            if route == "/api/weather":
                p = self._params()
                if "hour" in p:
                    hour = float(p["hour"])
                    if not (0.0 <= hour < 24.0):
                        return self._send(
                            {"error": f"hour must be in [0, 24), got {hour}"}, 400)
                else:
                    hour = None
                return self._send(b.weather(hour, **{key: p[key] for key in ("epoch_unix", "elapsed_hours") if key in p}))
            return self._send({"error": f"unknown route {route}"}, 404)
        except NoStoreError as exc:
            # /api/query only: 503 for a missing store.
            return self._send({"error": f"no store: {exc}"}, 503)
        except DataError as exc:
            return self._send({"error": f"data: {exc}"}, 500)
        except (KeyError, ValueError, TypeError,
                OverflowError, ZeroDivisionError) as exc:
            return self._send({"error": str(exc)}, 400)
        except Exception as exc:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("backend failure")
            return self._send({"error": "internal server error"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        if not self.guard(mutating=True):
            return
        try:
            content_type = self.headers.get("Content-Type", "")
            # Media type must be application/json; charset parameter allowed.
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                return self._send(
                    {"error": "Content-Type must be application/json"}, 400)
            if urlparse(self.path).path != "/api/propose":
                return self._send({"error": "unknown route"}, 404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except (TypeError, ValueError):
                return self._send({"error": "bad Content-Length"}, 400)
            if length < 0:
                return self._send({"error": "bad Content-Length"}, 400)
            if length > MAX_BODY_BYTES:
                self.close_connection = True
                return self._send(
                    {"error": f"body {length} bytes exceeds "
                              f"{MAX_BODY_BYTES} byte limit"}, 413)
            try:
                raw = self.rfile.read(length) if length else b""
            except OSError as exc:
                return self._send({"error": f"unreadable body ({exc})"}, 400)
            try:
                body = json.loads(raw or b"{}")
            except ValueError as exc:
                return self._send({"error": f"malformed JSON ({exc})"}, 400)
            if not isinstance(body, dict):
                return self._send(
                    {"error": "body must be a JSON object"}, 400)
            x, z = body.get("x"), body.get("z")
            if x is None and "center_xz" in body:
                try:
                    x, z = body["center_xz"]
                except (TypeError, ValueError) as exc:
                    return self._send(
                        {"error": f"center_xz must be [x, z] ({exc})"}, 400)
            if x is None or z is None:
                return self._send(
                    {"error": "missing required x/z (or center_xz)"}, 400)
            out = self.backend.propose(
                guild=body.get("guild", "lodgepole_pine"),
                x=x, z=z,
                radius_m=body.get("radius_m", 30),
                count=body.get("count", 40),
                seed=body.get("seed", 7),
                habitat_id=body.get("habitat_id", "forest_edge"),
                suitability_threshold=body.get(
                    "suitability_threshold", 0.12),
                canopy=body.get("canopy", 0.6))
            log = out.get("proposal_log", [])
            if len(log) > PROPOSAL_LOG_LIMIT:
                out["proposal_log"] = log[:PROPOSAL_LOG_LIMIT]
                out["proposal_log_truncated"] = len(log) - PROPOSAL_LOG_LIMIT
            return self._send(out)
        except DataError as exc:
            return self._send({"error": f"data: {exc}"}, 500)
        except (KeyError, ValueError, TypeError,
                OverflowError, ZeroDivisionError) as exc:
            return self._send({"error": str(exc)}, 400)
        except Exception as exc:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("backend failure")
            return self._send({"error": "internal server error"}, 500)




def _provider_terrain(world: Path):
    try:
        from yellowstone_python.land.vegetation import load_terrain
        return load_terrain(str(Path(world) / "data" / "terrain.f32"))
    except (OSError, ValueError):
        return None


def serve(port: int = 8765, world: Path = DEFAULT_WORLD,
          derived: Path = DEFAULT_DERIVED,
          hydrology: bool = True) -> int:
    provider = None
    if hydrology:
        from yellowstone_python.land.hydrology_provider import HydrologyProvider
        provider = HydrologyProvider(
            terrain=_provider_terrain(world), enabled=True)
    _Handler.backend = Backend(world, derived, hydrology=provider)
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.timeout = 30.0
    logger.info(f"llm_backend serving 127.0.0.1:{port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0






def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.llm_backend import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
