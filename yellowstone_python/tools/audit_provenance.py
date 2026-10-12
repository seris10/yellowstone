"""Mechanical standing-rules check over derived/ provenance labels.

Matches status strings against the measured in-use vocabulary (see
tooling-spec-audit-provenance.md); reports, never rewrites, artifacts.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCHEMA_AUDIT = "yellowstone.provenance_audit.v1"

# Exact vocabulary measured across derived/*.json (28 occurrences, 2026-10-10).
STATUS_VOCABULARY = (
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
)

# Files with no schema/status contract (legacy, allowlisted not failed).
LEGACY_ALLOWLIST = ("usgs_06036805.json", "llm_snapshot.json")

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
        # river_state.json is a bare list of reach dicts; it carries no
        # schema/status contract of its own. Report, do not crash.
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
            if s not in STATUS_VOCABULARY:
                failures.append({"file": path.name,
                                 "rule": "unknown-nested-status",
                                 "found": s})
    return failures


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
        # met.json is the forcing bundle itself; its fetched_at_utc is its own
        # timestamp, not a pointer at an obs bundle.
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
    args = parser.parse_args()
    if not args.dir.is_dir():
        parser.error(f"not a directory: {args.dir}")
    report = audit_dir(args.dir, args.strict)
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            tmp = args.out.with_name(args.out.name + ".tmp")
            tmp.write_text(json.dumps(report, indent=2))
            tmp.replace(args.out)
        except OSError as exc:
            print(json.dumps(report, indent=2))
            print(f"report-unwritable: {args.out}: {exc}")
            return 1
    for f in report["failures"]:
        print(f"FAIL {f['rule']}: {f['file']}: {f['found']}")
    print(f"audit: {report['n_files']} files, "
          f"{len(report['failures'])} failure(s)")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
