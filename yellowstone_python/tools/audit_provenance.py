"""Mechanical standing-rules check over derived/ provenance labels (reports only)."""

import argparse
import json
import os
import sys
from pathlib import Path
from yellowstone_python.common.io import write_json_atomic as _shared_json_write

SCHEMA_AUDIT = "yellowstone.provenance_audit.v1"

STATUS_VOCABULARY = (
    "measured",
    "derived_not_field_validated",
    "transferred",
    "unavailable",
    "measured_remote_not_calibrated",
    "fitted_not_validated_single_window",
    "illustrative_not_calibrated",
    "numerical_experiment_not_field_validation",
    "detection unreviewed; pool-rim artifacts excluded; not a placement authority",
    "authored_illustrative_effective_mixing_volume",
    "authored_illustrative_effective_mixing_volume; see sensitivity in "
    "parameter_notes",
    "Illustrative, dimensioned observational model. This is not calibrated "
    "hydrology, wildlife abundance or a biological forecast.",
    "authored",
    "authored_illustrative",
    "authored_illustrative_from_dem_and_census",
    "authored_illustrative_not_calibrated",
    "authored_standing_rules_check",
    "diagnostic",
    "diagnostic_not_calibrated",
    "fitted_not_validated",
    "illustrative",
    "illustrative_not_validated",
    "transferred_structure_authored_rates",
    "validation",
)

# Nested labels distinguish DEM-derived authored geometry from unmeasured boundary forcing.
NESTED_STATUS_VOCABULARY = STATUS_VOCABULARY + (
    "authored_estimate_from_usgs_3dep_dem",
    "illustrative_river_entry_forcing_not_measured",
)

LEGACY_ALLOWLIST = ("usgs_06036805.json", "llm_snapshot.json")

# Required when contract_version is present. Status is checked separately.
SIDECAR_KEYS = ("contract_version", "world_id", "code_rev",
                "parameter_provenance", "sources")


def _nested_statuses(doc, found: list) -> None:
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k == "status":
                found.append(v)
            else:
                _nested_statuses(v, found)
    elif isinstance(doc, list):
        for v in doc:
            _nested_statuses(v, found)


def audit_file(path: Path, strict: bool = False) -> list:
    """Return failure dicts for one artifact (empty means pass)."""
    failures = []
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return [{"file": path.name, "rule": "unreadable",
                 "found": str(exc)}]
    if path.name in LEGACY_ALLOWLIST:
        return []
    if not isinstance(doc, dict):
        # river_state.json is a bare list of reach dicts with no schema/status contract; this reports it without crashing.
        return [{"file": path.name, "rule": "non-dict-artifact",
                 "found": f"{type(doc).__name__} len={len(doc)}"}]
    if "schema" not in doc:
        failures.append({"file": path.name, "rule": "missing-schema",
                         "found": "absent"})
    status = doc.get("status")
    if status is None:
        failures.append({"file": path.name, "rule": "missing-status",
                         "found": "absent"})
    elif status not in STATUS_VOCABULARY:
        failures.append({"file": path.name, "rule": "unknown-status",
                         "found": status})
    if "contract_version" in doc:
        missing = [k for k in SIDECAR_KEYS if k not in doc]
        if missing:
            failures.append({"file": path.name, "rule": "incomplete-sidecar",
                             "found": f"missing {missing}"})
    if strict:
        nested: list = []
        _nested_statuses({k: v for k, v in doc.items() if k != "status"}, nested)
        for s in nested:
            if s not in NESTED_STATUS_VOCABULARY:
                failures.append({"file": path.name,
                                 "rule": "unknown-nested-status",
                                 "found": s})
    return failures


ALLOWED_STORE_TABLES = frozenset([
    "census_trees", "replay_cells", "replay_frames", "obs_usgs",
    "obs_snotel", "fits_reach", "fits_reach_nulls", "fits_snow", "meta",
    "sqlite_sequence",
])


def _dir_bytes(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):  # fd-ok: need per-entry st_size
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _per_build_disk(derived: Path) -> dict:
    """Return bytes per immediate build subdirectory under derived/."""
    out: dict = {}
    for child in sorted(derived.iterdir()):
        if child.is_dir():
            out[child.name] = _dir_bytes(child)
    return out


def _audit_store_sources(meta: dict) -> list:
    """Classify each entry in meta.source_shas against the live derived/."""
    out: list = []
    raw = meta.get("source_shas")
    if raw is None:
        return out
    import hashlib
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return [{"status": "UNKNOWN_PATH",
                 "detail": "source_shas is not valid JSON"}]
    if not isinstance(records, list):
        return [{"status": "UNKNOWN_PATH",
                 "detail": f"source_shas type {type(records).__name__}"}]
    for rec in records:
        if not isinstance(rec, dict):
            out.append({"status": "UNKNOWN_PATH", "record": repr(rec)[:120]})
            continue
        path_str = rec.get("path")
        basename = rec.get("basename")
        sha = rec.get("sha256")
        label = basename or path_str or "<unlabeled>"
        if path_str is None:
            out.append({"status": "UNKNOWN_PATH", "label": label})
            continue
        path = Path(path_str)
        if not path.exists():
            if path.parent.exists():
                out.append({"status": "MISSING_BUILD_DIR", "label": label,
                            "path": path_str})
            else:
                out.append({"status": "MISSING_BUILD_DIR", "label": label,
                            "path": path_str,
                            "detail": "parent build dir absent"})
            continue
        if sha:
            try:
                data = path.read_bytes()
            except OSError as exc:
                out.append({"status": "UNKNOWN_PATH", "label": label,
                            "detail": str(exc)})
                continue
            on_disk = hashlib.sha256(data).hexdigest()
            if on_disk != sha:
                out.append({"status": "STALE_SOURCE", "label": label,
                            "path": path_str,
                            "detail": f"expected {sha[:12]}, "
                                      f"found {on_disk[:12]}"})
                continue
        out.append({"status": "OK", "label": label, "path": path_str})
    return out


def _audit_store(store_path: Path) -> dict:
    """Audit one sqlite analysis store (tables allow-listed; sources checked)."""
    import sqlite3
    try:
        st = store_path.stat()
    except OSError as exc:
        return {"path": str(store_path), "error": str(exc)}
    out: dict = {"path": str(store_path), "bytes": st.st_size,
                 "mode": oct(st.st_mode & 0o777)}
    try:
        con = sqlite3.connect(f"file:{store_path}?mode=ro",
                              uri=True, timeout=1.0)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "ORDER BY name").fetchall()]
            out["tables"] = tables
            unknown = [t for t in tables if t not in ALLOWED_STORE_TABLES]
            if unknown:
                out["unknown_tables"] = unknown
            try:
                rows = con.execute(
                    "SELECT key, value FROM meta").fetchall()
                meta = {k: v for k, v in rows}
            except sqlite3.DatabaseError:
                meta = {}
            out["meta"] = meta
            out["source_audit"] = _audit_store_sources(meta)
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        out["error"] = f"sqlite: {exc}"
    return out


def audit_dir(directory: Path, strict: bool = False) -> dict:
    files = sorted(directory.glob("*.json"))
    failures = []
    for path in files:
        failures.extend(audit_file(path, strict))
    docs = {}
    for path in files:
        try:
            docs[path.name] = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
    obs_times = {d["fetched_at_utc"] for d in docs.values()
                 if isinstance(d, dict) and isinstance(d.get("schema"), str)
                 and d["schema"].endswith("_obs.v1")
                 and "fetched_at_utc" in d}
    for name, d in docs.items():
        if name in LEGACY_ALLOWLIST or not isinstance(d, dict):
            continue
        # met.json is the forcing bundle itself.
        if name == "met.json":
            continue
        for key in ("fetched_at_utc", "bundle_fetched_at_utc"):
            if key in d and "_obs_" not in name and d[key] not in obs_times:
                failures.append({"file": name, "rule": "stale-bundle-pointer",
                                 "found": f"{key}={d[key]}"})
    return {"schema": SCHEMA_AUDIT, "status": "authored_standing_rules_check",
            "dir": str(directory), "n_files": len(files),
            "passed": not failures, "failures": failures,
            "legacy_allowlist": list(LEGACY_ALLOWLIST)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("derived"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--derived-disk", action="store_true",
                        help="append disk usage summary to the report")
    parser.add_argument("--audit-stores", action="store_true",
                        help="audit every analysis_*.sqlite in --dir")
    args = parser.parse_args()
    if not args.dir.is_dir():
        parser.error(f"not a directory: {args.dir}")
    report = audit_dir(args.dir, args.strict)
    if args.derived_disk:
        report["disk"] = {"path": str(args.dir),
                          "bytes": _dir_bytes(args.dir),
                          "per_build": _per_build_disk(args.dir)}
    if args.audit_stores:
        stores = sorted(args.dir.glob("analysis_*.sqlite"))
        report["stores"] = [_audit_store(p) for p in stores]
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _shared_json_write(args.out, report)
        except OSError as exc:
            print(json.dumps(report, indent=2))
            print(f"report-unwritable: {args.out}: {exc}")
            return 1
    for f in report["failures"]:
        print(f"FAIL {f['rule']}: {f['file']}: {f['found']}")
    print(f"audit: {report['n_files']} files, "
          f"{len(report['failures'])} failure(s)")
    if args.derived_disk:
        mib = report["disk"]["bytes"] / (1024 * 1024)
        print(f"disk: {args.dir} {mib:.1f} MiB")
        for build, bytes_ in sorted(report["disk"]["per_build"].items(),
                                     key=lambda kv: -kv[1])[:10]:
            print(f"  {build}: {bytes_ / (1024 * 1024):.1f} MiB")
    if args.audit_stores:
        for s in report["stores"]:
            label = Path(s["path"]).name
            if "error" in s:
                print(f"store FAIL {label}: {s['error']}")
                continue
            unknown = s.get("unknown_tables") or []
            src = s.get("source_audit") or []
            tag = f"{s['bytes']} bytes, {len(s.get('tables', []))} tables"
            if unknown:
                tag += f", unknown_tables={unknown}"
            print(f"store {label}: {tag}")
            for row in src:
                print(f"  {row['status']}: {row.get('label', '?')} "
                      f"{row.get('detail', '')}".rstrip())
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
