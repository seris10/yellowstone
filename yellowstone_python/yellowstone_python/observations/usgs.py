"""USGS field measurements, time series, and Firehole observation normalization."""
from __future__ import annotations

from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE, STATIONS

import hashlib
import json
import math
import logging
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from yellowstone_python.common.io import write_json_atomic as _shared_json_write
from typing import Any

logger = logging.getLogger(__name__)

BASE_URL = "https://nwis.waterdata.usgs.gov/usa/nwis"
IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USER_AGENT = "yellowstone-python/0.1"

SCHEMA_RAW = "yellowstone.usgs_site_raw.v1"
SCHEMA_NORMALIZED = "yellowstone.usgs_site_observations.v1"

MIN_PERIOD_DAYS = 1
MAX_PERIOD_DAYS = 366
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
REQUEST_TIMEOUT_S = 30
FUTURE_TOLERANCE_S = 86400.0

CFS_TO_M3S = 0.028316846592

SITES = {
    UPSTREAM_GAUGE: {
        "name": "Firehole River at Old Faithful, YNP",
        "drainage_area_sqmi": 39.5,
        "latitude": STATIONS[UPSTREAM_GAUGE]["latitude"],
        "longitude": STATIONS[UPSTREAM_GAUGE]["longitude"],
        "altitude_ft": 7339.88,
        "notes": "Upstream of Midway Geyser Basin; Upper Geyser Basin inflows only",
    },
    DOWNSTREAM_GAUGE: {
        "name": "Firehole River near West Yellowstone MT",
        "drainage_area_sqmi": 261.0,
        "latitude": STATIONS[DOWNSTREAM_GAUGE]["latitude"],
        "longitude": STATIONS[DOWNSTREAM_GAUGE]["longitude"],
        "altitude_ft": 7056.08,
        "notes": "Downstream of all Firehole thermal inflows; below Firehole Falls",
    },
}

PARAM_DISCHARGE = "00060"
PARAM_TEMP = "00010"
PARAM_GAGE_HEIGHT = "00065"
PARAM_WIDTH = "00066"
PARAM_AREA = "00067"
PARAM_VELOCITY = "00068"
PARAM_SPECIFIC_CONDUCTANCE = "00095"
PARAM_DISSOLVED_OXYGEN = "00300"
PARAM_PH = "00400"

PARAM_CODES = {
    PARAM_DISCHARGE: "discharge_cfs",
    PARAM_TEMP: "temperature_c",
    PARAM_GAGE_HEIGHT: "gage_height_ft",
    PARAM_WIDTH: "width_ft",
    PARAM_AREA: "area_sqft",
    PARAM_VELOCITY: "velocity_fps",
}

IV_PARAMETERS = {
    PARAM_DISCHARGE: {
        "name": "discharge", "source_units": "ft3/s",
        "normalized_units": "m3/s", "conversion": CFS_TO_M3S,
    },
    PARAM_TEMP: {
        "name": "temperature", "source_units": "degC",
        "normalized_units": "degC", "conversion": 1.0,
    },
}

# Chemistry IV parameters live in a parallel map so the discharge-and-temperature bundle output stays unchanged.
IV_CHEM_PARAMETERS: dict[str, dict[str, Any]] = {
    PARAM_SPECIFIC_CONDUCTANCE: {
        "name": "specific_conductance",
        "source_units": "uS/cm_at_25C",
        "normalized_units": "uS/cm_at_25C",
        "conversion": 1.0,
        "value_range": (0.0, 50000.0),
    },
    PARAM_DISSOLVED_OXYGEN: {
        "name": "dissolved_oxygen",
        "source_units": "mg/L",
        "normalized_units": "mg/L",
        "conversion": 1.0,
        "value_range": (0.0, 25.0),
    },
    PARAM_PH: {
        "name": "ph",
        "source_units": "std_units",
        "normalized_units": "std_units",
        "conversion": 1.0,
        "value_range": (0.0, 14.0),
    },
}

SCHEMA_CHEM_RAW = "yellowstone.usgs_site_chem_raw.v1"
SCHEMA_CHEM_NORMALIZED = "yellowstone.usgs_site_chem_observations.v1"

RDB_COLUMN_MAP = {
    "chan_width": "width_ft",
    "chan_area": "area_sqft",
    "chan_velocity": "velocity_fps",
    "discharge_va": "discharge_cfs",
    "gage_height_va": "gage_height_ft",
}

MEASUREMENT_UNITS = {
    "width_ft": "ft",
    "area_sqft": "ft2",
    "velocity_fps": "ft/s",
    "discharge_cfs": "ft3/s",
    "gage_height_ft": "ft",
}

TEMPERATURE_RANGE_C = (-50.0, 60.0)

_CONDITION_QUALIFIERS = frozenset(
    {"ice", "eqp", "mnt", "dis", "dry", "bkw", "fld"})

MIN_COVERAGE_FOR_SCREENING = 0.8

_SITE_NO_RE = re.compile(r"^\d{8,15}$")
_RDB_TYPE_RE = re.compile(r"^\d*[sdn]$")


class NWISRequestError(RuntimeError):
    """Request failure with status code and retryable flag."""

    def __init__(self, message: str, *, status: int | None = None,
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def validate_period_days(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("period-days must be an integer")
    if not MIN_PERIOD_DAYS <= value <= MAX_PERIOD_DAYS:
        raise ValueError(
            f"period-days must be between {MIN_PERIOD_DAYS} and "
            f"{MAX_PERIOD_DAYS}")
    return value


def validate_site_no(site_no: str) -> str:
    if not isinstance(site_no, str) or not _SITE_NO_RE.match(site_no):
        raise ValueError(
            f"USGS site number must be 8 to 15 digits, got {site_no!r}")
    return site_no


def parse_usgs_timestamp(value: Any) -> float:
    """Parse a USGS ISO timestamp to UTC epoch seconds."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("USGS timestamp must be a nonempty string")

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("USGS timestamp must include a timezone")

    return parsed.astimezone(timezone.utc).timestamp()


def _iso_utc(epoch: float) -> str:
    return (datetime.fromtimestamp(epoch, tz=timezone.utc)
            .isoformat().replace("+00:00", "Z"))


def _now_utc_iso() -> str:
    return (datetime.now(timezone.utc).isoformat()
            .replace("+00:00", "Z"))


def _parse_float(value: Any) -> float | None:
    """Finite float or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def classify_qualifiers(qualifiers: Any) -> str:
    """Quality status label from USGS qualifier codes."""
    if not qualifiers:
        return "unqualified"

    lowered = {str(q).strip().lower() for q in qualifiers}

    if lowered & _CONDITION_QUALIFIERS:
        return "flagged_conditions"
    if "e" in lowered:
        return "estimated"
    if "p" in lowered:
        return "provisional"
    if "a" in lowered:
        return "approved"
    return "qualified_with_flags"


def _http_get(url: str, *, timeout: float = REQUEST_TIMEOUT_S) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        retryable = e.code == 429 or 500 <= e.code < 600
        raise NWISRequestError(
            f"NWIS request failed: HTTP {e.code} {e.reason}",
            status=e.code, retryable=retryable) from e
    except OSError as e:
        raise NWISRequestError(
            f"NWIS request failed: {e}", retryable=True) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise NWISRequestError(
            f"NWIS response exceeds {MAX_RESPONSE_BYTES} bytes")
    return body


def _request_iv_json(site_no: str, parameter_cds: list[str],
                     period_days: int) -> tuple[dict, str]:
    """Request IV data (WaterML JSON). Returns (parsed JSON, request URL)."""
    query = urllib.parse.urlencode({
        "sites": site_no,
        "parameterCd": ",".join(parameter_cds),
        "period": f"P{period_days}D",
        "format": "json",
    }, safe=",")
    url = f"{IV_URL}?{query}"
    body = _http_get(url)
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise NWISRequestError(
            "NWIS IV response was not valid JSON") from e
    if not isinstance(data, dict):
        raise NWISRequestError("NWIS IV response was not a JSON object")
    return data, url


def _series_codes(series: Any) -> set[str]:
    if not isinstance(series, dict):
        return set()
    variable = series.get("variable")
    if not isinstance(variable, dict):
        return set()
    return {str(item.get("value"))
            for item in variable.get("variableCode", [])
            if isinstance(item, dict) and item.get("value") is not None}


def _empty_ingest_stats() -> dict:
    return {"rows_received": 0, "rows_retained": 0,
            "rows_rejected": 0, "rejected_malformed": 0,
            "rejected_timestamp": 0, "rejected_value": 0,
            "rejected_nodata": 0, "rejected_range": 0,
            "rejected_future": 0, "duplicates_removed": 0}


def _rows_from_series(series: dict, parameter_cd: str,
                      now_epoch: float) -> tuple[list[dict], dict]:
    """Parse one WaterML time series into validated rows plus counters."""
    stats = _empty_ingest_stats()
    blocks = series.get("values") or []
    block = blocks[0] if blocks and isinstance(blocks[0], dict) else {}
    raw_values = block.get("value") or []
    variable = series.get("variable") or {}
    nodata = _parse_float(variable.get("noDataValue"))
    spec = IV_PARAMETERS.get(parameter_cd)
    conversion: float = (
        float(spec["conversion"]) if spec is not None else 1.0  # type: ignore[arg-type]
    )

    rows: list[dict] = []
    for item in raw_values:
        stats["rows_received"] += 1
        if not isinstance(item, dict):
            stats["rejected_malformed"] += 1
            continue
        try:
            epoch = parse_usgs_timestamp(item.get("dateTime"))
        except ValueError:
            stats["rejected_timestamp"] += 1
            continue
        if epoch > now_epoch + FUTURE_TOLERANCE_S:
            stats["rejected_future"] += 1
            continue
        value = _parse_float(item.get("value"))
        if value is None:
            stats["rejected_value"] += 1
            continue
        if (nodata is not None and value == nodata) or value <= -999000.0:
            stats["rejected_nodata"] += 1
            continue
        if parameter_cd == PARAM_TEMP and not (
                TEMPERATURE_RANGE_C[0] <= value <= TEMPERATURE_RANGE_C[1]):
            stats["rejected_range"] += 1
            continue
        if parameter_cd == PARAM_DISCHARGE and value < 0.0:
            stats["rejected_range"] += 1
            continue
        qualifiers = [str(q) for q in (item.get("qualifiers") or [])]
        row: dict[str, Any] = {
            "epoch_unix": epoch,
            "datetime_utc": _iso_utc(epoch),
            "datetime_source": item.get("dateTime"),
            "value": value,
            "qualifiers": qualifiers,
            "quality_status": classify_qualifiers(qualifiers),
        }
        if parameter_cd == PARAM_DISCHARGE:
            row["value_m3_s"] = value * conversion
        rows.append(row)

    rows.sort(key=lambda r: r["epoch_unix"])
    deduped: list[dict] = []
    for row in rows:
        if deduped and row["epoch_unix"] <= deduped[-1]["epoch_unix"]:
            stats["duplicates_removed"] += 1
            continue
        deduped.append(row)

    stats["rows_retained"] = len(deduped)
    stats["rows_rejected"] = (stats["rows_received"] - stats["rows_retained"]
                              - stats["duplicates_removed"])
    return deduped, stats


def extract_iv_rows(data: dict, parameter_cd: str, *,
                    now_epoch: float | None = None
                    ) -> tuple[list[dict], dict, dict]:
    """Select the time series for ``parameter_cd`` and parse it."""
    now = datetime.now(timezone.utc).timestamp() if now_epoch is None \
        else now_epoch
    value = data.get("value")
    all_series = value.get("timeSeries", []) if isinstance(value, dict) else []
    if not isinstance(all_series, list):
        all_series = []

    candidates = [s for s in all_series
                  if parameter_cd in _series_codes(s)]
    parsed = [(_rows_from_series(s, parameter_cd, now), s)
              for s in candidates]

    selection: dict[str, Any] = {
        "parameter_cd": parameter_cd,
        "candidate_count": len(candidates),
        "selected_index": None,
        "selected_name": None,
        "value_blocks": None,
        "rule": "most_retained_rows_first_on_tie",
        "candidates": [
            {"index": i, "name": s.get("name"),
             "rows_retained": res[1]["rows_retained"]}
            for i, (res, s) in enumerate(
                ((p[0], p[1]) for p in parsed))
        ],
    }
    if not parsed:
        return [], _empty_ingest_stats(), selection

    best = max(range(len(parsed)),
               key=lambda i: (parsed[i][0][1]["rows_retained"], -i))
    (rows, stats), chosen = parsed[best]
    selection["selected_index"] = best
    selection["selected_name"] = chosen.get("name")
    selection["value_blocks"] = len(chosen.get("values") or [])
    if len(candidates) > 1:
        selection["warning"] = (
            "multiple time series carry this parameter; verify the "
            "selected sensor and method")
    if selection["value_blocks"] > 1:
        selection["warning_value_blocks"] = (
            "series has several value blocks (methods); only the first "
            "is used")
    return rows, stats, selection


def series_quality(rows: list[dict],
                   requested_window_s: float | None = None) -> dict:
    """Continuity, coverage and qualifier diagnostics for rows."""
    times = [row["epoch_unix"] for row in rows]
    qualifier_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for row in rows:
        for q in row.get("qualifiers", []):
            qualifier_counts[q] = qualifier_counts.get(q, 0) + 1
        status = row.get("quality_status", "unqualified")
        status_counts[status] = status_counts.get(status, 0) + 1

    result: dict[str, Any] = {
        "n": len(times),
        "start_epoch_unix": times[0] if times else None,
        "end_epoch_unix": times[-1] if times else None,
        "nominal_interval_s": None,
        "max_gap_s": None,
        "coverage_fraction": None,
        "qualifier_counts": qualifier_counts,
        "quality_status_counts": status_counts,
    }
    if len(times) < 2:
        return result

    intervals = [later - earlier
                 for earlier, later in zip(times, times[1:])]
    nominal = sorted(intervals)[len(intervals) // 2]
    result["nominal_interval_s"] = nominal
    result["max_gap_s"] = max(intervals)
    if requested_window_s and requested_window_s > 0 and nominal > 0:
        covered = sum(i for i in intervals if i <= 2.0 * nominal) + nominal
        result["coverage_fraction"] = min(1.0, covered / requested_window_s)
    return result


def _series_status(n: int, coverage: float | None) -> str:
    if n == 0:
        return "no_data"
    if coverage is None:
        return "insufficient_for_coverage"
    if coverage >= MIN_COVERAGE_FOR_SCREENING:
        return "usable_for_screening"
    return "gappy"


def _overall_status(statuses: list[str]) -> str:
    if statuses and all(s == "usable_for_screening" for s in statuses):
        return "usable_for_screening"
    if any(s != "no_data" for s in statuses):
        return "partial_or_gappy"
    return "no_data"


_DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def _valid_measurement_date(text: str) -> bool:
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def _fetch_rdb(site_no: str, begin_date: str = "", end_date: str = "",
               parameter_cd: str = "") -> tuple[list[dict], dict]:
    """Fetch RDB-format field measurements. Returns (rows, parse stats)."""
    validate_site_no(site_no)
    parts = [f"{BASE_URL}/measurements?site_no={site_no}"
             "&format=rdb&agency_cd=USGS"]
    if begin_date:
        parts.append(f"begin_date={urllib.parse.quote(begin_date)}")
    if end_date:
        parts.append(f"end_date={urllib.parse.quote(end_date)}")
    if parameter_cd:
        parts.append(f"parameter_cd={urllib.parse.quote(parameter_cd)}")
    url = "&".join(parts)

    raw = _http_get(url).decode("utf-8", errors="replace")
    head = raw[:1000].lower()
    if "<html" in head or "<!doctype" in head:
        raise NWISRequestError(
            'NWIS returned HTML with RDB data', retryable=False)

    lines = [line for line in raw.splitlines()
             if line.strip() and not line.startswith("#")]
    stats = {"rows_received": 0, "rows_retained": 0,
             "rows_rejected_date": 0, "rows_rejected_short": 0}
    if not lines:
        return [], stats

    header = [c.strip() for c in lines[0].split("\t")]
    if "measurement_dt" not in header:
        raise NWISRequestError(
            "unexpected RDB header: no measurement_dt column",
            retryable=False)
    body = lines[1:]
    if body:
        types = [c.strip() for c in body[0].split("\t")]
        if all(_RDB_TYPE_RE.match(t) for t in types if t):
            body = body[1:]

    rows = []
    for line in body:
        stats["rows_received"] += 1
        fields = [f.strip() for f in line.split("\t")]
        if len(fields) < len(header):
            fields.extend([""] * (len(header) - len(fields)))
        record = dict(zip(header, fields))
        date_text = record.get("measurement_dt", "")
        if not _valid_measurement_date(date_text):
            stats["rows_rejected_date"] += 1
            continue
        row: dict[str, Any] = {}
        for key, val in record.items():
            if key in ("agency_cd", "site_no"):
                continue
            if key == "measurement_dt":
                row["date"] = val
            elif key in PARAM_CODES:
                row[PARAM_CODES[key]] = _parse_float(val)
            elif key in RDB_COLUMN_MAP:
                row[RDB_COLUMN_MAP[key]] = _parse_float(val)
                row[key] = val
            else:
                row[key] = val
        rows.append(row)
    stats["rows_retained"] = len(rows)
    return rows, stats


def _fetch_iv(site_no: str, parameter_cd: str, period_days: int = 30) -> list[dict]:
    """Fetch instantaneous values for one parameter."""
    validate_site_no(site_no)
    validate_period_days(period_days)
    data, _url = _request_iv_json(site_no, [parameter_cd], period_days)
    rows, _stats, _selection = extract_iv_rows(data, parameter_cd)
    return rows


def _site_info(site_no: str, site_info: dict | None) -> tuple[dict, dict]:
    if site_info is not None:
        info = dict(site_info)
        provenance = {"source": "caller_supplied", "retrieved_at_utc": None,
                      "status": "requires_verification"}
    elif site_no in SITES:
        info = dict(SITES[site_no])
        provenance = {"source": "authored_station_registry",
                      "retrieved_at_utc": None,
                      "status": "requires_verification"}
    else:
        info = {}
        provenance = {"source": "not_in_registry",
                      "retrieved_at_utc": None,
                      "status": "no_site_metadata"}
    info = {"site_no": site_no, **info}
    return info, provenance


def fetch_raw(site_no: str, period_days: int = 30, *,
              include_measurements: bool = True,
              site_info: dict | None = None) -> dict:
    """Fetch measurements and IV series for a site as a raw artifact."""
    validate_site_no(site_no)
    period_days = validate_period_days(period_days)
    info, site_provenance = _site_info(site_no, site_info)
    window_s = period_days * 86400.0

    result: dict[str, Any] = {
        "schema": SCHEMA_RAW,
        "site_id": site_no,
        "site": info,
        "site_metadata_provenance": site_provenance,
        "retrieved_at_utc": _now_utc_iso(),
        "period_days": period_days,
        "measurements": [],
        "measurements_status": "not_requested",
        "measurements_meta": {
            "units": dict(MEASUREMENT_UNITS),
            "parse_stats": None,
        },
        "discharge_iv": [],
        "temperature_iv": [],
        "units": {
            "discharge_iv.value": "ft3/s",
            "discharge_iv.value_m3_s": "m3/s",
            "temperature_iv.value": "degC",
            **{f"measurements.{k}": v for k, v in MEASUREMENT_UNITS.items()},
        },
        "parameters": {
            code: {"code": code, **spec}
            for code, spec in IV_PARAMETERS.items()
        },
        "quality": {},
        "warnings": [],
        "provenance": {
            "agency": "USGS",
            "iv_endpoint_family": "legacy_waterservices_iv",
            "iv_url": IV_URL,
            "parameter_codes": [PARAM_TEMP, PARAM_DISCHARGE],
            "request_url": None,
            "time_basis": "epoch_unix_utc_from_offset_aware_timestamps",
        },
    }

    if include_measurements:
        try:
            rows, parse_stats = _fetch_rdb(site_no)
            result["measurements"] = rows
            result["measurements_meta"]["parse_stats"] = parse_stats
            result["measurements_status"] = (
                "retrieved" if rows else "empty_or_unavailable")
        except RuntimeError as e:
            result["measurements_status"] = "unavailable"
            result["warnings"].append(f"field measurements: {e}")

    iv_quality: dict[str, Any] = {}
    try:
        data, url = _request_iv_json(
            site_no, [PARAM_TEMP, PARAM_DISCHARGE], period_days)
        result["provenance"]["request_url"] = url
        for code, key in ((PARAM_DISCHARGE, "discharge_iv"),
                          (PARAM_TEMP, "temperature_iv")):
            iv_rows, iv_stats, selection = extract_iv_rows(data, code)
            result[key] = iv_rows
            diagnostics = series_quality(iv_rows, window_s)
            iv_quality[key] = {
                **diagnostics,
                "ingest": iv_stats,
                "selection": selection,
                "status": _series_status(
                    diagnostics["n"], diagnostics["coverage_fraction"]),
            }
            if selection.get("warning"):
                result["warnings"].append(
                    f"{key}: {selection['warning']}")
    except RuntimeError as e:
        result["warnings"].append(f"instantaneous values: {e}")
        for key in ("discharge_iv", "temperature_iv"):
            iv_quality[key] = {"n": 0, "status": "request_failed"}

    result["quality"] = {
        **iv_quality,
        "status": _overall_status(
            [q["status"] for q in iv_quality.values()]),
    }
    return result


def normalize_site_result(raw: dict) -> dict:
    """Convert a raw artifact to the normalized observation schema."""
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA_RAW:
        raise ValueError(f"expected a {SCHEMA_RAW} document")

    temperature_rows = raw.get("temperature_iv", [])
    discharge_rows = raw.get("discharge_iv", [])

    temperature = [[r["epoch_unix"], r["value"]] for r in temperature_rows]
    discharge = [[r["epoch_unix"], r["value_m3_s"]] for r in discharge_rows]

    return {
        "schema": SCHEMA_NORMALIZED,
        "site_id": raw["site_id"],
        "site": raw["site"],
        "site_metadata_provenance": raw["site_metadata_provenance"],
        "retrieved_at_utc": raw["retrieved_at_utc"],
        "series": {"temperature_c": temperature,
                   "discharge_m3_s": discharge},
        "series_units": {"temperature_c": "degC", "discharge_m3_s": "m3/s"},
        "series_quality_status": {
            "temperature_c": [r["quality_status"] for r in temperature_rows],
            "discharge_m3_s": [r["quality_status"] for r in discharge_rows],
        },
        "series_source": {
            "discharge_m3_s": {"source_units": "ft3/s",
                               "conversion": CFS_TO_M3S},
            "temperature_c": {"source_units": "degC", "conversion": 1.0},
        },
        "measurements": {
            "records": raw.get("measurements", []),
            "units": raw.get("measurements_meta", {}).get("units", {}),
            "status": raw.get("measurements_status"),
            "quality": raw.get("measurements_meta", {}).get("parse_stats"),
        },
        "quality": raw.get("quality", {}),
        "warnings": list(raw.get("warnings", [])),
        "provenance": {
            **raw.get("provenance", {}),
            "normalized_from": SCHEMA_RAW,
        },
    }


def filter_series_by_quality(normalized: dict, name: str,
                             exclude: frozenset | set = frozenset(
                                 {"estimated", "flagged_conditions"})
                             ) -> list[list[float]]:
    """Pairs from ``series[name]`` whose quality status is not excluded."""
    pairs = normalized["series"][name]
    statuses = normalized["series_quality_status"][name]
    return [pair for pair, status in zip(pairs, statuses)
            if status not in exclude]


_HASH_FIELDS = ("artifact_sha256", "artifact_sha256_scope")


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def write_json_atomic(path: Path, document: dict) -> str:
    """Write ``document`` atomically with an embedded content hash."""
    path = Path(path)
    payload = {k: v for k, v in document.items() if k not in _HASH_FIELDS}
    digest = hashlib.sha256(
        _canonical_json(payload).encode("utf-8")).hexdigest()
    out = {**payload, "artifact_sha256": digest,
           "artifact_sha256_scope": "canonical_json_without_hash_fields"}
    _shared_json_write(path, out, indent=2)
    return digest


def verify_artifact_hash(document: dict) -> bool:
    """True when the embedded hash matches the document content."""
    payload = {k: v for k, v in document.items() if k not in _HASH_FIELDS}
    digest = hashlib.sha256(
        _canonical_json(payload).encode("utf-8")).hexdigest()
    return document.get("artifact_sha256") == digest


def _chem_rows_from_series(series: dict, parameter_cd: str,
                           now_epoch: float) -> tuple[list[dict], dict]:
    """Parse a chemistry WaterML series into validated rows plus counters."""
    stats = _empty_ingest_stats()
    blocks = series.get("values") or []
    block = blocks[0] if blocks and isinstance(blocks[0], dict) else {}
    raw_values = block.get("value") or []
    variable = series.get("variable") or {}
    nodata = _parse_float(variable.get("noDataValue"))
    spec = IV_CHEM_PARAMETERS.get(parameter_cd)
    if spec is not None:
        low_f, high_f = spec["value_range"]
        low = float(low_f)
        high = float(high_f)
    else:
        low = -1e18
        high = 1e18

    rows: list[dict] = []
    for item in raw_values:
        stats["rows_received"] += 1
        if not isinstance(item, dict):
            stats["rejected_malformed"] += 1
            continue
        try:
            epoch = parse_usgs_timestamp(item.get("dateTime"))
        except ValueError:
            stats["rejected_timestamp"] += 1
            continue
        if epoch > now_epoch + FUTURE_TOLERANCE_S:
            stats["rejected_future"] += 1
            continue
        value = _parse_float(item.get("value"))
        if value is None:
            stats["rejected_value"] += 1
            continue
        if (nodata is not None and value == nodata) or value <= -999000.0:
            stats["rejected_nodata"] += 1
            continue
        if not low <= value <= high:
            stats["rejected_range"] += 1
            continue
        qualifiers = [str(q) for q in (item.get("qualifiers") or [])]
        rows.append({
            "epoch_unix": epoch,
            "datetime_utc": _iso_utc(epoch),
            "datetime_source": item.get("dateTime"),
            "value": value,
            "qualifiers": qualifiers,
            "quality_status": classify_qualifiers(qualifiers),
        })

    rows.sort(key=lambda r: r["epoch_unix"])
    deduped: list[dict] = []
    for row in rows:
        if deduped and row["epoch_unix"] <= deduped[-1]["epoch_unix"]:
            stats["duplicates_removed"] += 1
            continue
        deduped.append(row)
    stats["rows_retained"] = len(deduped)
    stats["rows_rejected"] = (stats["rows_received"] - stats["rows_retained"]
                              - stats["duplicates_removed"])
    return deduped, stats


def extract_chem_iv_rows(data: dict, parameter_cd: str, *,
                         now_epoch: float | None = None
                         ) -> tuple[list[dict], dict, dict]:
    """Chemistry equivalent of extract_iv_rows for a chem parameter code."""
    now = (datetime.now(timezone.utc).timestamp()
           if now_epoch is None else now_epoch)
    value = data.get("value")
    all_series = (value.get("timeSeries", [])
                  if isinstance(value, dict) else [])
    if not isinstance(all_series, list):
        all_series = []
    candidates = [s for s in all_series
                  if parameter_cd in _series_codes(s)]
    parsed = [(_chem_rows_from_series(s, parameter_cd, now), s)
              for s in candidates]
    selection: dict[str, Any] = {
        "parameter_cd": parameter_cd,
        "candidate_count": len(candidates),
        "selected_index": None,
        "selected_name": None,
        "rule": "most_retained_rows_first_on_tie",
    }
    if not parsed:
        return [], _empty_ingest_stats(), selection
    best = max(range(len(parsed)),
               key=lambda i: (parsed[i][0][1]["rows_retained"], -i))
    (rows, stats), chosen = parsed[best]
    selection["selected_index"] = best
    selection["selected_name"] = chosen.get("name")
    if len(candidates) > 1:
        selection["warning"] = (
            "multiple time series carry this parameter; verify the "
            "selected sensor and method")
    return rows, stats, selection


def fetch_chem_raw(site_no: str, period_days: int = 7, *,
                   site_info: dict | None = None,
                   parameters: tuple[str, ...] = (
                       PARAM_SPECIFIC_CONDUCTANCE,
                       PARAM_DISSOLVED_OXYGEN,
                       PARAM_PH,
                   )) -> dict:
    """Fetch chemistry IV series (SC, DO, pH) for a site as a raw artifact."""
    validate_site_no(site_no)
    period_days = validate_period_days(period_days)
    for code in parameters:
        if code not in IV_CHEM_PARAMETERS:
            raise ValueError(
                f"unknown chem parameter code {code!r}")
    info, site_provenance = _site_info(site_no, site_info)
    window_s = period_days * 86400.0

    result: dict[str, Any] = {
        "schema": SCHEMA_CHEM_RAW,
        "site_id": site_no,
        "site": info,
        "site_metadata_provenance": site_provenance,
        "retrieved_at_utc": _now_utc_iso(),
        "period_days": period_days,
        "series": {},
        "units": {
            code: IV_CHEM_PARAMETERS[code]["source_units"]
            for code in parameters
        },
        "parameters": {
            code: {"code": code, **IV_CHEM_PARAMETERS[code]}
            for code in parameters
        },
        "quality": {},
        "warnings": [],
        "provenance": {
            "agency": "USGS",
            "iv_endpoint_family": "legacy_waterservices_iv",
            "iv_url": IV_URL,
            "parameter_codes": list(parameters),
            "request_url": None,
            "time_basis": (
                "epoch_unix_utc_from_offset_aware_timestamps"),
            "terms": (
                "USGS Water Services IV, provisional and subject to "
                "revision; see "
                "https://waterdata.usgs.gov/nwis/help/?provisional"),
        },
    }

    quality: dict[str, Any] = {}
    try:
        data, url = _request_iv_json(site_no, list(parameters), period_days)
        result["provenance"]["request_url"] = url
        for code in parameters:
            name = IV_CHEM_PARAMETERS[code]["name"]
            rows, ingest, selection = extract_chem_iv_rows(data, code)
            result["series"][name] = rows
            diagnostics = series_quality(rows, window_s)
            quality[name] = {
                **diagnostics,
                "ingest": ingest,
                "selection": selection,
                "status": _series_status(
                    diagnostics["n"], diagnostics["coverage_fraction"]),
                "parameter_cd": code,
            }
    except RuntimeError as e:
        result["warnings"].append(f"instantaneous values: {e}")
        for code in parameters:
            name = IV_CHEM_PARAMETERS[code]["name"]
            quality[name] = {"n": 0, "status": "request_failed",
                             "parameter_cd": code}

    overall = _overall_status([q["status"] for q in quality.values()])
    result["quality"] = {**quality, "status": overall}
    return result


def normalize_chem_result(raw: dict) -> dict:
    """Convert a chem raw artifact to a normalized chem observation schema."""
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA_CHEM_RAW:
        raise ValueError(f"expected a {SCHEMA_CHEM_RAW} document")
    normalized_series: dict[str, list[list[float]]] = {}
    quality_status: dict[str, list[str]] = {}
    for name, rows in raw.get("series", {}).items():
        normalized_series[name] = [
            [r["epoch_unix"], r["value"]] for r in rows
        ]
        quality_status[name] = [r["quality_status"] for r in rows]
    return {
        "schema": SCHEMA_CHEM_NORMALIZED,
        "site_id": raw["site_id"],
        "site": raw["site"],
        "site_metadata_provenance": raw["site_metadata_provenance"],
        "retrieved_at_utc": raw["retrieved_at_utc"],
        "series": normalized_series,
        "series_units": {
            k: v for k, v in raw.get("units", {}).items()
        },
        "series_quality_status": quality_status,
        "parameters": raw.get("parameters", {}),
        "quality": raw.get("quality", {}),
        "warnings": list(raw.get("warnings", [])),
        "provenance": {
            **raw.get("provenance", {}),
            "normalized_from": SCHEMA_CHEM_RAW,
        },
    }


def fetch_all(site_no: str, out_path: Path, period_days: int = 30, *,
              include_measurements: bool = True,
              normalized_out: Path | None = None) -> dict:
    """Fetch a registered site and write the raw artifact."""
    if site_no not in SITES:
        raise ValueError(f"Unknown site {site_no}; have {list(SITES)}")
    period_days = validate_period_days(period_days)

    name = SITES[site_no]["name"]
    logger.info(f"Fetching {name} ({period_days} days)...")
    result = fetch_raw(site_no, period_days,
                       include_measurements=include_measurements)
    logger.info(f"  measurements: {result['measurements_status']} "
          f"({len(result['measurements'])})")
    logger.info(f"  discharge IV: {len(result['discharge_iv'])} values")
    logger.info(f"  temperature IV: {len(result['temperature_iv'])} values")
    for warning in result["warnings"]:
        logger.info(f"  WARNING: {warning}")

    result["artifact_sha256"] = write_json_atomic(out_path, result)
    logger.info(f"Wrote {out_path}")
    if normalized_out is not None:
        normalized = normalize_site_result(result)
        write_json_atomic(normalized_out, normalized)
        logger.info(f"Wrote {normalized_out}")
    return result
