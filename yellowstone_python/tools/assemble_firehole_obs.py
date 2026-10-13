"""Assemble a firehole_obs.v1 bundle from normalized usgs_nwis artifacts and a met forcing file.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.observation_io import (atomic_write_json,
                                      verify_artifact_hash)
    from tools.usgs_nwis import (SCHEMA_NORMALIZED,
                                 filter_series_by_quality)
except ImportError:
    from observation_io import (atomic_write_json,
                                verify_artifact_hash)
    from usgs_nwis import SCHEMA_NORMALIZED, filter_series_by_quality


FIREHOLE_SCHEMA = "yellowstone.firehole_obs.v1"
MET_SCHEMA_PREFIX = "yellowstone.met_forcing"
EXCLUDE_QUALITY = frozenset({"estimated", "flagged_conditions"})


def _load_json(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    return data


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
            "usgs_normalized": [str(p) for p in usgs_paths],
            "met": str(met_path),
        },
        "sites": sites,
        "met": met_entry,
    }
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usgs-normalized", type=Path, action="append",
                        default=[],
                        help="normalized usgs_nwis artifact "
                             "(repeat for multiple sites)")
    parser.add_argument("--met", type=Path, required=True,
                        help="fetch_met_forcing bundle to attach")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exclude-quality", action="append", default=None,
                        help="per-row quality_status label to drop; "
                             "defaults to estimated and flagged_conditions")
    args = parser.parse_args()
    if not args.usgs_normalized:
        parser.error("at least one --usgs-normalized is required")

    exclude = (frozenset(args.exclude_quality)
               if args.exclude_quality is not None else EXCLUDE_QUALITY)
    bundle = assemble(args.usgs_normalized, args.met, exclude=exclude)
    atomic_write_json(args.out, bundle)
    print(f"Wrote {args.out}")
    for site_id, record in bundle["sites"].items():
        kept_t = record["quality_filtering"]["temperature_c"]["retained"]
        kept_q = record["quality_filtering"]["discharge_m3_s"]["retained"]
        print(f"  {site_id}: temperature n={kept_t}, discharge n={kept_q}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
