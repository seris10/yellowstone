"""Skill gates for the seed thermal and snow claims: each evidence fit must beat its recorded null."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from yellowstone_python.registry.claims import get_claim, resolve_artifact_id


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _resolve_evidence(claim_id: str) -> list[Path]:
    """Project-rooted paths for a claim's evidence artifacts."""
    try:
        claim = get_claim(claim_id)
    except KeyError:
        return []
    out: list[Path] = []
    for aid in claim.get("evidence_artifact_ids", []):
        try:
            out.append(resolve_artifact_id(aid))
        except (ValueError, FileNotFoundError):
            continue
    return out


# Nulls named in the reach claim's acceptance criteria; the gate lists the ones the evidence fit lacks.
REACH_REQUIRED_NULLS = ("upstream_persistence", "mixing_only_c0_refit",
                        "downstream_climatology")
SNOTEL_NULL_KEYS = ("null_persistence_rmse_mm", "null_nomelt_rmse_mm")


DISCHARGE_RELATIVE_RESIDUAL_TOL = 0.10


def check_reach_rmse() -> dict[str, Any]:
    """Reach gate for reach_water_temperature_ice_free: champion holdout rmse below every recorded null."""
    for path in _resolve_evidence("reach_water_temperature_ice_free"):
        doc = _load(path)
        if not isinstance(doc, dict):
            continue
        champion = doc.get("champion")
        if not isinstance(champion, dict):
            continue
        rmse = _finite_float(champion.get("holdout_rmse"))
        if rmse is None:
            continue
        nulls: dict[str, float] = {}
        for record in doc.get("null_models") or []:
            if not isinstance(record, dict):
                continue
            value = _finite_float(record.get("holdout_rmse"))
            if value is not None:
                nulls[str(record.get("name"))] = value
        failures: list[str] = []
        if not nulls:
            failures.append("evidence fit records no null models")
        for name, value in nulls.items():
            if not rmse < value:
                failures.append(
                    f"champion holdout_rmse {rmse:.3f} C does not beat "
                    f"null {name} {value:.3f} C")
        if champion.get("budget_ok") is not True:
            failures.append("champion budget_ok is not true")
        boundary_discharge = champion.get("boundary_discharge")
        discharge_resid = _finite_float(
            champion.get("discharge_relative_residual"))
        if boundary_discharge == "measured_series":
            if discharge_resid is None:
                failures.append(
                    "boundary_discharge=measured_series but "
                    "champion.discharge_relative_residual is missing")
            elif discharge_resid > DISCHARGE_RELATIVE_RESIDUAL_TOL:
                failures.append(
                    f"champion discharge_relative_residual "
                    f"{discharge_resid:.4f} exceeds tol "
                    f"{DISCHARGE_RELATIVE_RESIDUAL_TOL}")
        return {"name": "reach_holdout_beats_nulls",
                "skipped": False,
                "source": str(path),
                "holdout_rmse_c": rmse,
                "null_holdout_rmse_c": nulls,
                "missing_nulls": [n for n in REACH_REQUIRED_NULLS
                                  if n not in nulls],
                "boundary_discharge": boundary_discharge,
                "discharge_relative_residual": discharge_resid,
                "failures": failures}
    return {"name": "reach_holdout_beats_nulls",
            "skipped": False,
            "failures": ["no champion holdout_rmse in reach claim evidence"]}


def check_snotel_rmse() -> dict[str, Any]:
    """Snow gate for snow_swe_clearings: each site's holdout SWE rmse below its persistence and."""
    for path in _resolve_evidence("snow_swe_clearings"):
        doc = _load(path)
        sites = doc.get("sites") if isinstance(doc, dict) else None
        if not isinstance(sites, dict) or not sites:
            continue
        failures: list[str] = []
        rows: dict[str, dict[str, float | None]] = {}
        for site_id, record in sites.items():
            swe = record.get("holdout_swe_mm") if isinstance(record, dict) else None
            rmse = _finite_float(swe.get("rmse")) if isinstance(swe, dict) else None
            if rmse is None:
                failures.append(f"site {site_id}: no holdout_swe_mm.rmse")
                continue
            row: dict[str, float | None] = {"holdout_rmse_mm": rmse}
            for key in SNOTEL_NULL_KEYS:
                value = _finite_float(record.get(key))
                row[key] = value
                if value is None:
                    failures.append(f"site {site_id}: {key} missing")
                elif not rmse < value:
                    failures.append(
                        f"site {site_id}: holdout rmse {rmse:.2f} mm does "
                        f"not beat {key} {value:.2f} mm")
            rows[str(site_id)] = row
        return {"name": "snotel_holdout_beats_nulls",
                "skipped": False,
                "source": str(path),
                "sites": rows,
                "failures": failures}
    return {"name": "snotel_holdout_beats_nulls",
            "skipped": False,
            "failures": ["no per-site holdout SWE in snow claim evidence"]}


def run_claim_gates() -> dict[str, Any]:
    """Aggregated non-regression gate output for build check reporting."""
    gates = [check_reach_rmse(), check_snotel_rmse()]
    failures: list[str] = []
    for g in gates:
        for f in g.get("failures", []):
            failures.append(f"{g['name']}: {f}")
    return {"passed": not failures,
            "failures": failures,
            "gates": gates}
