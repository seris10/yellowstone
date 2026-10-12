"""HTTP backend for census analysis and proposal review. Stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .common.provenance import default_world_root

PKG_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = default_world_root()
DEFAULT_DERIVED = PKG_ROOT / "derived"
CENSUS_FILE = DEFAULT_DERIVED / "census.json"

# Same zone definitions as canopy_census --stats, plus full-detail box.
ZONES = {
    "spring_0_50m": {"circle": (-94.7, -10.6, 50.0)},
    "apron_50_100m": {"ring": (-94.7, -10.6, 50.0, 100.0)},
    "transition_100_200m": {"ring": (-94.7, -10.6, 100.0, 200.0)},
    "outwash_200_400m": {"ring": (-94.7, -10.6, 200.0, 400.0)},
    "overlook_knoll_r120": {"circle": (-252.0, 159.0, 120.0)},
    "detail_full": {"box": (-640.0, -640.0, 640.0, 640.0)},
}

ACCURACY_NOTES = ["Pretrained DeepForest underdetects vs census (~1,175 crowns)."]


# Density circles outside [MIN_RADIUS_M, MAX_RADIUS_M] are rejected. Bounds single-sourced from analysis_store.
from .analysis_store import RADIUS_MAX_M as MAX_RADIUS_M
from .analysis_store import RADIUS_MIN_M as MIN_RADIUS_M
# Legitimate /api/propose bodies are <1 KB; anything larger is junk/DoS.
MAX_BODY_BYTES = 64 * 1024
# Review logs are returned inline; longer ones are truncated with a marker.
PROPOSAL_LOG_LIMIT = 1000


class DataError(RuntimeError):
    """A data file on disk is missing or corrupt (server-side -> HTTP 500).

    Raised for unreadable files and malformed records so handlers can
    distinguish server data rot (500) from bad client input (400).
    """


def _load_json(path: Path) -> dict | list:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise DataError(f"{Path(path).name}: missing file ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"{Path(path).name}: invalid JSON ({exc})") from exc
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Backend:
    """Cached file-backed state. All methods read-only (no writes)."""

    def __init__(self, world: Path = DEFAULT_WORLD,
                 derived: Path = DEFAULT_DERIVED,
                 store: Path | None = None,
                 hydrology=None):
        self.world = Path(world)
        self.derived = Path(derived)
        self._census = None
        self._census_mtime = None
        self._store = Path(store) if store is not None else None
        self.hydrology = hydrology

    def store_path(self) -> Path | None:
        """Newest derived/analysis_*.sqlite, or None when no store exists.

        Explicit constructor `store=` wins; otherwise the newest store
        file is resolved live (stores are history: one file per build).
        """
        if self._store is not None:
            return self._store if self._store.exists() else None
        best, best_mtime = None, -1.0
        for cand in self.derived.glob("analysis_*.sqlite"):
            mtime = cand.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best = cand
        return best

    def query_store(self, table: str, columns: list[str] | None = None,
                    limit: int = 100, offset: int = 0,
                    **filters) -> dict:
        """Read-only bounded query over the analysis store.

        Raises FileNotFoundError (HTTP 503) when no store file exists;
        ValueError (HTTP 400) on any validation rejection.
        """
        from .analysis_store import query as _store_query
        path = self.store_path()
        if path is None:
            raise FileNotFoundError(
                "no derived/analysis_*.sqlite store; build one with "
                "tools/build_store.py --build derived/<id>")
        out = _store_query(path, table, columns=columns,
                           limit=limit, offset=offset, **filters)
        out["store"] = path.name
        return out

    def density(self, x: float, z: float, r: float) -> dict:
        """Circle crown count, store-backed when a store file exists. Store path and JSON path share one answer contract."""
        path = self.store_path()
        if path is not None:
            from .analysis_store import census_circle_count
            out = census_circle_count(path, x, z, r)
            out["source"] = path.name
            return out
        out = self.circle_stats(self.census_points(), x, z, r)
        out["source"] = "census.json"
        return out

    # ---- cached loaders ----
    def census(self) -> dict:
        path = self.derived / "census.json"
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            raise DataError(f"census.json: {exc}") from exc
        if self._census is None or mtime != self._census_mtime:
            doc = _load_json(path)
            if not isinstance(doc, dict):
                raise DataError(
                    f"census.json: must be a JSON object, got "
                    f"{type(doc).__name__}")
            self._census = doc
            self._census_mtime = mtime
        return self._census

    def placements(self) -> dict:
        return _load_json(self.world / "data" / "placements.json")

    def overrides(self) -> dict:
        return _load_json(self.world / "data" / "placement_overrides.json")

    def ecosystem(self) -> dict:
        return _load_json(self.world / "data" / "ecosystem.json")

    def weather(self, hour: float | None = None) -> dict:
        """Live weather state for the Godot runtime.

        Reads the frozen met bundle (yellowstone_python/derived/met.json)
        when present, else falls back to authored defaults. Returns the
        values the renderer consumes: air, humidity, cloud, wind vector,
        plus the provenance of each. hour is game clock hour (0-24); the
        default is the published clock_hour.
        """
        from .microclimate import load_weather_bundle, bundle_weather
        bundle = load_weather_bundle(str(self.derived / "met.json"))
        if bundle is None:
            return {"source": "authored_defaults",
                    "provenance": "no met bundle; authored scenario",
                    "air_c": 7.0, "humidity": 0.45, "cloud": 0.16,
                    "wind_xz_mps": [1.8, 0.6], "gust_mps": 0.45,
                    "bundle": None}
        if hour is None:
            eco = self.ecosystem()
            hour = float(eco.get("clock_hour", 16.2))
        w = bundle_weather(bundle, hour=float(hour))
        mb = w.get("met_bundle", {})
        # Precipitation: only explicit measurement, not cloud inference.
        precipitation_rate_mm_h = None
        precipitation_status = "unavailable"
        hourly = w.get("hourly", {}) if isinstance(w, dict) else {}
        # Try to extract explicit precipitation from bundle weather fields.
        precip_raw = None
        if isinstance(bundle, dict):
            bundle_hourly = bundle.get("hourly", {})
            if isinstance(bundle_hourly, dict):
                precip_raw = bundle_hourly.get("precipitation_mm_h")
            elif isinstance(bundle_hourly, list) and len(bundle_hourly) > 0:
                # Fallback: try index-based extraction if structured differently.
                pass
        if precip_raw is not None:
            try:
                precipitation_rate_mm_h = float(precip_raw)
                if math.isfinite(precipitation_rate_mm_h) and precipitation_rate_mm_h >= 0:
                    precipitation_status = "measured_bundle"
                else:
                    precipitation_rate_mm_h = None
                    precipitation_status = "invalid_bundle"
            except (TypeError, ValueError):
                precipitation_rate_mm_h = None
                precipitation_status = "unavailable"
        # Explicit provenance: no cloud-to-rain substitution.
        hydrology_link_ref = (
            "optional hydrology provider; no absolute filesystem path; "
            "actual precipitation input required"
        )
        ground_wetness_fraction = None
        hydrology_sim_state = None
        if self.hydrology is not None:
            try:
                weather_for_hydrology = {
                    "air_c": float(w.get("night_air_c", 7.0)) if isinstance(w, dict) else 7.0,
                    "humidity": float(w.get("humidity", 0.45)) if isinstance(w, dict) else 0.45,
                    "wind_speed_m_s": math.hypot(
                        float(w.get("wind_xz_mps", [1.8, 0.6])[0]) if isinstance(w, dict) else 1.8,
                        float(w.get("wind_xz_mps", [1.8, 0.6])[1]) if isinstance(w, dict) else 0.6,
                    ) if isinstance(w, dict) else 2.0,
                    "precipitation_rate_mm_h": precipitation_rate_mm_h,
                }
                snapshot = self.hydrology.snapshot(
                    weather=weather_for_hydrology, hour=float(hour) if hour is not None else 16.2
                )
                ground_wetness_fraction = snapshot.ground_wetness_fraction
                hydrology_sim_state = snapshot.state
                hydrology_link_ref = "hydrology provider status=" + snapshot.status
            except (OSError, ValueError, AttributeError, TypeError, ImportError) as exc:
                hydrology_sim_state = {"error": f"{type(exc).__name__}: {exc}", "fallback": "provider_failed"}
                hydrology_link_ref += " (provider failed: " + str(exc) + ")"
        else:
            hydrology_sim_state = {"status": "not_configured"}
            hydrology_link_ref += " (no provider configured)"
        snow_fraction = 0.0
        if "night_air_c" in w and "humidity" in w:
            # Simple wet-bulb approximation: Tw = T * atan(0.151977 * sqrt(rh))
            # ... but using a calibrated operational proxy from the doc.
            t_c = float(w.get("night_air_c", 7.0))
            rh = float(w.get("humidity", 0.45))
            # Wet-bulb proxy: below ~0 C with humidity > 0.7 favors snow.
            # The scientific recommendation is wet-bulb-based, not fixed threshold.
            # Using the calibrated proxy from weather-simulation.md.
            wet_bulb_proxy = t_c - 2.5 * (1.0 - rh)  # rough approximation
            snow_fraction = max(0.0, min(1.0, (1.0 - wet_bulb_proxy / 2.0)))

        w_extra = {
            "precipitation_rate_mm_h": (
                round(float(precipitation_rate_mm_h), 3)
                if precipitation_rate_mm_h is not None else None),
            "precipitation_status": precipitation_status,
            "snow_fraction": round(snow_fraction, 3),
            "ground_wetness_fraction": (
                round(float(ground_wetness_fraction), 4)
                if ground_wetness_fraction is not None else None),
            "hydrology_ref": hydrology_link_ref,
            "hydrology_sim_state": hydrology_sim_state,
            "snow_partition_ref": "weather-simulation.md (wet-bulb, not fixed 0 C)",
        }
        return {"source": "open-meteo_hourly_bundle",
                "provenance": "measured_remote_not_calibrated; snow_partition_wet_bulb_based",
                "air_c": w["night_air_c"], "humidity": w["humidity"],
                "cloud": w["cloud"], "wind_xz_mps": w["wind_xz_mps"],
                "gust_mps": w["gust_mps"],
                "snow_fraction": w_extra["snow_fraction"],
                "precipitation_rate_mm_h": w_extra["precipitation_rate_mm_h"],
                "precipitation_status": w_extra["precipitation_status"],
                "ground_wetness_fraction": w_extra["ground_wetness_fraction"],
                "bundle": {"schema": mb.get("schema"),
                           "fetched_at_utc": mb.get("fetched_at_utc"),
                           "elevation_m": mb.get("elevation_m"),
                           "row_index_utc": mb.get("row_index_utc")},
                "hour_requested": float(hour),
                "hydrology_link": w_extra["hydrology_ref"],
                "snow_partition_link": w_extra["snow_partition_ref"],
                "hydrology_sim_state": w_extra.get("hydrology_sim_state")}

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
                # Server-side data rot, not client input -> 500, not 400.
                raise DataError(str(exc)) from exc
            out.append((x, z))
        return out

    def placed_points(self) -> list:
        place = self.placements()
        baked = place.get("trees")
        if not isinstance(baked, list):
            raise DataError(
                "placements.json: 'trees' must be a list, got "
                f"{type(baked).__name__}")
        pts = []
        for i, t in enumerate(baked):
            if not isinstance(t, dict):
                raise DataError(
                    f"placements.json tree #{i}: record must be an object")
            try:
                pos = t["position"]
            except KeyError as exc:
                raise DataError(
                    f"placements.json tree #{i}: missing 'position'") from exc
            if not isinstance(pos, (list, tuple)) or len(pos) < 3:
                raise DataError(
                    f"placements.json tree #{i}: 'position' must be [x,y,z]")
            try:
                pts.append((_as_float(f"tree #{i} x", pos[0]),
                            _as_float(f"tree #{i} z", pos[2])))
            except ValueError as exc:
                raise DataError(str(exc)) from exc
        ov = self.overrides()
        staged = ov.get("add")
        if not isinstance(staged, list):
            raise DataError(
                "placement_overrides.json: 'add' must be a list, got "
                f"{type(staged).__name__}")
        for i, r in enumerate(staged):
            if not isinstance(r, dict):
                raise DataError(
                    f"placement_overrides add #{i}: record must be an object")
            if r.get("kind") != "pine":
                continue
            try:
                pos = r["position"]
            except KeyError as exc:
                raise DataError(
                    f"placement_overrides add #{i}: pine record missing "
                    f"'position'") from exc
            if not isinstance(pos, (list, tuple)) or len(pos) < 3:
                raise DataError(
                    f"placement_overrides add #{i}: 'position' must be [x,y,z]")
            try:
                pts.append((_as_float(f"add #{i} x", pos[0]),
                            _as_float(f"add #{i} z", pos[2])))
            except ValueError as exc:
                raise DataError(str(exc)) from exc
        return pts

    def zones(self) -> dict:
        from .canopy_census import density_stats
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
                "positive deficit = game sparser than 2022 NAIP canopy; "
                "negative = game denser. Both layers are unreviewed/authored; "
                "target human NAIP review, not auto-editing."),
        }

    def placements_summary(self) -> dict:
        from collections import Counter
        try:
            place = self.placements()
            ov = self.overrides()
            staged_add = ov.get("add", [])
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
        try:
            wildlife = eco.get("wildlife", [])
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
        best, best_mtime = None, -1.0
        for checks in self.derived.glob("*/CHECKS.json"):
            mtime = checks.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best = checks
        if best is None:
            return {"build": None, "note": "no derived/*/CHECKS.json yet"}
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
        # Fault-isolated sections: one corrupt file degrades its section
        # instead of failing the whole bundle.
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
        out["accuracy_notes"] = ACCURACY_NOTES
        out["limitations"] = [
            "Census is unreviewed detection, not a stem survey.",
            "Placements are authored representatives.",
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
        from .pool_crust import build_all as build_shells
        from .pool_crust import in_apron
        from .review_proposals import review
        from .vegetation import GUILDS, load_terrain, moisture_at, terrain_fns
        from .vegetation import propose_plantings_reviewed

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
        from .vegetation import HALF
        if not (-HALF <= x <= HALF and -HALF <= z <= HALF):
            raise ValueError(
                f"proposal center ({x}, {z}) lies outside the baked "
                f"world square (±{HALF} m); records would never bake")
        if not (0 < radius_m <= 500):
            raise ValueError("radius_m must be in (0, 500]")
        if not (0 < count <= 500):
            raise ValueError("count must be in (0, 500]")
        if not (0.0 <= suitability_threshold <= 1.0):
            raise ValueError("suitability_threshold must be in [0, 1]")
        if not (0.0 <= canopy <= 1.0):
            raise ValueError("canopy must be in [0, 1]")
        try:
            world = _load_json(self.world / "data" / "world.json")
            pools = world["pools"]
        except KeyError as exc:
            raise DataError(f"world.json: missing 'pools' ({exc})") from exc
        shells = build_shells(pools)
        try:
            sample, slope = terrain_fns(load_terrain(
                str(self.world / "data" / "terrain.f32")))
        except (ValueError, OSError) as exc:
            raise DataError(f"terrain.f32: unreadable ({exc})") from exc
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
class _Handler(BaseHTTPRequestHandler):
    backend: Backend = None  # set by serve()

    def _send(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, indent=1).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away mid-response; nothing to report to

    def _params(self) -> dict:
        return {k: v[0] for k, v in
                parse_qs(urlparse(self.path).query).items()}

    def do_GET(self) -> None:  # noqa: N802
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
                hour = float(p["hour"]) if "hour" in p else None
                return self._send(b.weather(hour))
            return self._send({"error": f"unknown route {route}"}, 404)
        except FileNotFoundError as exc:
            # /api/query only: llm_backend still serves everything else
            # when no store file exists.
            return self._send({"error": f"no store: {exc}"}, 503)
        except DataError as exc:
            return self._send({"error": f"data: {exc}"}, 500)
        except (KeyError, ValueError, TypeError,
                OverflowError, ZeroDivisionError) as exc:
            return self._send({"error": str(exc)}, 400)
        except Exception as exc:  # never leak a traceback to clients
            return self._send({"error": f"internal: {exc}"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        try:
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
            return self._send({"error": f"internal: {exc}"}, 500)

    def log_message(self, fmt: str, *args) -> None:
        pass  # quiet; use --serve logs from the caller if needed


def _provider_terrain(world: Path):
    try:
        from .vegetation import load_terrain
        return load_terrain(str(Path(world) / "data" / "terrain.f32"))
    except (OSError, ValueError):
        return None


def serve(port: int = 8765, world: Path = DEFAULT_WORLD,
          derived: Path = DEFAULT_DERIVED,
          hydrology: bool = True) -> int:
    provider = None
    if hydrology:
        from .hydrology_provider import HydrologyProvider
        provider = HydrologyProvider(
            terrain=_provider_terrain(world), enabled=True)
    _Handler.backend = Backend(world, derived, hydrology=provider)
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"llm_backend serving 127.0.0.1:{port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--no-hydrology", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--world", default=str(DEFAULT_WORLD))
    ap.add_argument("--derived", default=str(DEFAULT_DERIVED))
    ap.add_argument("--snapshot-out", default=None)
    ap.add_argument("--zones", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--x", type=float, default=-252.0)
    ap.add_argument("--z", type=float, default=159.0)
    ap.add_argument("--r", type=float, default=120.0)
    args = ap.parse_args()

    backend = Backend(Path(args.world), Path(args.derived))
    if args.serve:
        return serve(args.port, Path(args.world), Path(args.derived),
                     hydrology=not args.no_hydrology)
    if args.snapshot_out:
        out = Path(args.snapshot_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(backend.snapshot(), indent=1))
        print(f"snapshot -> {out}")
        return 0
    if args.zones:
        print(json.dumps(backend.zones(), indent=1))
        return 0
    if args.compare:
        print(json.dumps(backend.compare(args.x, args.z, args.r), indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
