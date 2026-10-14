"""Normalized Firehole observation bundle assembly."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yellowstone_python.observations.bundles import atomic_write_json, verify_artifact_hash, source_path
from yellowstone_python.observations.usgs import SCHEMA_CHEM_NORMALIZED, SCHEMA_NORMALIZED, filter_series_by_quality


FIREHOLE_SCHEMA = "yellowstone.firehole_obs.v1"
FIREHOLE_CHEM_SCHEMA = "yellowstone.firehole_chem_obs.v1"
MET_SCHEMA_PREFIX = "yellowstone.met_forcing"
EXCLUDE_QUALITY = frozenset({"estimated", "flagged_conditions"})
CHEM_SERIES_NAMES = ("specific_conductance", "dissolved_oxygen", "ph")


from yellowstone_python.common.io import load_json as _load_json


def _require_hash(document: dict, source: Path) -> None:
    if not document.get("artifact_sha256"):
        raise ValueError(
            f"{source}: artifact_sha256 missing; refuse to assemble")
    if not verify_artifact_hash(document):
        raise ValueError(f"{source}: artifact_sha256 does not match content")


def _site_record(normalized: dict,
                 exclude: frozenset) -> tuple[dict[str, Any], str]:
    """Shape one normalized artifact into the sites[site_id] layout."""
    if normalized.get("schema") != SCHEMA_NORMALIZED:
        raise ValueError(
            f"expected {SCHEMA_NORMALIZED}, got {normalized.get('schema')!r}")
    site_id = normalized["site_id"]
    site_info = dict(normalized.get("site") or {})
    kept = {
        name: filter_series_by_quality(normalized, name, exclude=exclude)
        for name in ("temperature_c", "discharge_m3_s")
    }
    original = {name: len(normalized["series"][name])
                for name in kept}
    retained = {name: len(kept[name]) for name in kept}
    quality_stats = {
        name: {
            "retained": retained[name],
            "excluded": original[name] - retained[name],
            "exclude_statuses": sorted(exclude),
            "total_in_source": original[name],
        }
        for name in kept
    }
    return {
        "site_id": site_id,
        **site_info,
        "series": kept,
        "series_units": dict(normalized.get("series_units") or {}),
        "series_source": dict(normalized.get("series_source") or {}),
        "quality": dict(normalized.get("quality") or {}),
        "quality_filtering": quality_stats,
        "retrieved_at_utc": normalized.get("retrieved_at_utc"),
        "site_metadata_provenance": dict(
            normalized.get("site_metadata_provenance") or {}),
        "upstream_artifact_sha256": normalized.get("artifact_sha256"),
    }, site_id


def _chem_site_record(normalized: dict) -> tuple[dict[str, Any], str]:
    """Shape one normalized chem artifact into the chem sites[site_id] layout."""
    if normalized.get("schema") != SCHEMA_CHEM_NORMALIZED:
        raise ValueError(
            f"expected {SCHEMA_CHEM_NORMALIZED}, got "
            f"{normalized.get('schema')!r}"
        )
    site_id = normalized["site_id"]
    site_info = dict(normalized.get("site") or {})
    series = dict(normalized.get("series") or {})
    quality = dict(normalized.get("series_quality_status") or {})
    coverage: dict[str, dict[str, int]] = {}
    status: dict[str, str] = {}
    for name in CHEM_SERIES_NAMES:
        coverage[name] = {
            "total_in_source": len(series.get(name, [])),
            "retained": len(series.get(name, [])),
            "excluded": 0,
        }
        status[name] = (
            "retrieved" if series.get(name) else "not_collected_in_window"
        )
    return {
        "site_id": site_id,
        **site_info,
        "series": series,
        "series_units": dict(normalized.get("series_units") or {}),
        "series_quality_status": quality,
        "series_status": status,
        "quality": dict(normalized.get("quality") or {}),
        "quality_filtering": coverage,
        "retrieved_at_utc": normalized.get("retrieved_at_utc"),
        "site_metadata_provenance": dict(
            normalized.get("site_metadata_provenance") or {}),
        "upstream_artifact_sha256": normalized.get("artifact_sha256"),
    }, site_id


def assemble_chem(usgs_chem_paths: list[Path]) -> dict:
    """Read normalized chem artifacts and return a firehole_chem_obs.v1 bundle."""
    if not usgs_chem_paths:
        raise ValueError("at least one --usgs-chem-normalized is required")
    sites: dict[str, dict] = {}
    for path in usgs_chem_paths:
        document = _load_json(path)
        _require_hash(document, path)
        record, site_id = _chem_site_record(document)
        if site_id in sites:
            raise ValueError(
                f"duplicate site_id {site_id!r} across chem inputs"
            )
        sites[site_id] = record
    bundle = {
        "schema": FIREHOLE_CHEM_SCHEMA,
        "status": "measured_remote_not_calibrated",
        "components": {
            "sites": {"kind": "observation",
                      "status": "measured_remote_not_calibrated"},
        },
        "assembled_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "usgs": (
                "Composed from yellowstone.usgs_site_chem_observations.v1 "
                "artifacts; each site's content hash is embedded under "
                "upstream_artifact_sha256"
            ),
            "finding_policy": (
                "A parameter absent from the window is a finding, not an "
                "error; the series_status label distinguishes "
                "not_collected_in_window from retrieved."
            ),
        },
        "sources": {
            "usgs_chem_normalized": [source_path(p) for p in usgs_chem_paths],
        },
        "sites": sites,
    }
    return bundle


def assemble(usgs_paths: list[Path], met_path: Path,
             *, exclude: frozenset = EXCLUDE_QUALITY) -> dict:
    """Read inputs, verify hashes and return a firehole_obs.v1 bundle."""
    if not usgs_paths:
        raise ValueError("at least one --usgs-normalized is required")
    sites: dict[str, dict] = {}
    for path in usgs_paths:
        document = _load_json(path)
        _require_hash(document, path)
        record, site_id = _site_record(document, exclude)
        if site_id in sites:
            raise ValueError(
                f"duplicate site_id {site_id!r} across normalized inputs")
        sites[site_id] = record

    met_doc = _load_json(met_path)
    _require_hash(met_doc, met_path)
    schema = met_doc.get("schema", "")
    if not isinstance(schema, str) or not schema.startswith(MET_SCHEMA_PREFIX):
        raise ValueError(
            f"{met_path}: expected a {MET_SCHEMA_PREFIX}* bundle")
    met_entry: dict[str, Any] = {
        k: v for k, v in met_doc.items()
        if k not in ("artifact_sha256", "artifact_sha256_scope")}
    met_entry.update({
        "kind": "model_forcing",
        "role": "surface_budget_forcing",
        "location_role": "upstream_boundary_proxy",
        "measurement_status": "not_a_direct_observation",
        "observation_status": "model_output",
        "upstream_artifact_sha256": met_doc.get("artifact_sha256"),
    })

    bundle = {
        "schema": FIREHOLE_SCHEMA,
        "status": "measured_remote_not_calibrated",
        "components": {
            "sites": {"kind": "observation",
                      "status": "measured_remote_not_calibrated"},
            "met": {"kind": "model_forcing",
                    "status": "model_output_not_observation"},
        },
        "assembled_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "usgs": ("Composed from yellowstone.usgs_site_observations.v1 "
                     "artifacts; each site's content hash is embedded "
                     "under upstream_artifact_sha256"),
            "met": ("Composed from a fetch_met_forcing bundle; the met "
                    "block is forcing, not observation"),
            "quality_filter": ("Series filtered by quality status; "
                               f"excluded = {sorted(exclude)}"),
            "use": ("Upstream series are boundary forcing; downstream "
                    "series are the calibration target"),
        },
        "sources": {
            "usgs_normalized": [source_path(p) for p in usgs_paths],
            "met": source_path(met_path),
        },
        "sites": sites,
        "met": met_entry,
    }
    return bundle
