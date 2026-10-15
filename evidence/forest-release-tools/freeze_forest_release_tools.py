"""Snapshot final release tooling for review and reproducibility; no game execution."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'evidence/forest-release-tools'
SOURCES = [
    'work/forest_runtime_scope.py',
    'work/verify_forest_runtime_equivalence.py',
    'work/forest_benchmark_evidence.py',
    'work/check_forest_benchmark_evidence.py',
    'work/finalize_forest_evidence.py',
    'work/finalize_forest_verification.py',
    'work/finalize_forest_package.py',
    'work/prepare_forest_report.py',
    'work/stage_forest_release.py',
    'work/prepare_runtime_inventory.py',
    'work/check_package_startup.py',
    'work/check_package_native.py',
    'work/run_forest_attachment_pairs.py',
    'work/run_canopy_attachment_evidence.py',
    'yellowstone_midway/work/capture_floor_authoritative.gd',
    'work/validate_forest_benchmark.gd',
    'work/forest-benchmark-forcing.json',
    'work/forest-closeout-config.template.json',
    'work/forest-release-checklist.md',
    'work/freeze_forest_release_tools.py',
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


DESTINATION.mkdir(parents=True, exist_ok=True)
records = []
for relative in SOURCES:
    source = ROOT / relative
    assert source.is_file(), relative
    target = DESTINATION / source.name
    if target.exists() and target.read_bytes() != source.read_bytes():
        previous = DESTINATION / 'previous' / (digest(target)[:16] + '-' + target.name)
        previous.parent.mkdir(exist_ok=True)
        if previous.exists():
            assert previous.read_bytes() == target.read_bytes()
        else:
            shutil.copy2(target, previous)
    shutil.copy2(source, target)
    records.append({'source_path': relative, 'snapshot_path': str(target.relative_to(ROOT)),
                    'sha256': digest(source), 'bytes': source.stat().st_size})
(DESTINATION / 'manifest.json').write_text(json.dumps({
    'schema': 'yellowstone.release_tool_snapshots.v1',
    'scope': 'Release tooling snapshots only. Hashes authenticate helper bytes, not scientific or game execution. Prior unpublished helper revisions, when present, are retained in previous/.',
    'files': records,
}, indent=2) + '\n')
(DESTINATION / 'README.md').write_text('''# Release-tool reproduction

These are frozen copies of the work-only tools used to prepare this release. `manifest.json` maps each original repository-relative path to its snapshot and SHA-256. This directory contains scripts and fixture provenance, not a claim that every script ran. Original command receipts, raw reports and their execution scopes remain separate.

Use a source checkout of the Yellowstone repository with its required assets, checked generation, Python virtual environment and Godot 4.5.1. The portable Godot ZIP is sufficient for offline gameplay, but it is not the complete Python reproduction environment. Restore each snapshot to its exact repository-relative `source_path` before running it. Most tools belong in `work/`; the saved-world capture wrapper belongs in `yellowstone_midway/work/`. Do not execute these copies directly from `evidence/forest-release-tools/`: Python `__file__`-relative repository resolution and imports expect the recorded layout, while Godot resolves the capture wrapper as `res://work/capture_floor_authoritative.gd`.

The shared native benchmark runs the exact same `validate_forest_benchmark.gd` and `forest-benchmark-forcing.json` against the separately extracted published baseline and the current project. It normalizes the older sun convention only in memory, locks authored forcing, disables game inputs/readers, and checks both requested values and drift. Run the benchmark only after other native jobs and builds stop. Native captures require a visible graphics backend. No benchmark or package creation is triggered by reading this directory.

Start with `forest-release-checklist.md` and a fresh copy of `forest-closeout-config.template.json`. Supply exact new receipt paths and names; never select an ambiguous latest receipt or reuse the template's historical pointers after runtime changes. Local filesystem paths, output directories, Godot binary paths and the extracted baseline location reflect the recorded machine and must be reviewed for another host. Such adaptations and new receipts are new reproduction evidence, not the original execution.

`forest_runtime_scope.py` excludes exactly the unbundled `dashboard/build_data.py` from runtime source comparisons. It keeps original full inventory observations and global freshness status. It never excuses changes to any included source, fixture, output, or originally stale/failed execution. The numerical generation retains its original build/source identity; the runtime equivalence helper proves unchanged numerical bytes separately from current graphics checks.

`finalize_forest_verification.py` defaults to work-only preview output. Its `--apply` option updates maintained verification/ledger documents. Publication is not claimed until an explicit publication configuration passes live GitHub tag/main/asset checks and an actual downloaded archive hash check. Staging, archive assembly, push and release creation are separate mutating steps in the checklist. Review them before executing a reproduction.

`check_forest_benchmark_evidence.py` uses synthetic records to test rejection of corrupt benchmark evidence. Passing it does not establish renderer correctness or performance. Prior native control failures and sun-mismatched intermediate benchmarks remain separate historical evidence and are not converted into passes by these tools.
''')
extra = ROOT / 'work/forest-release-stage-extra.json'
paths = json.loads(extra.read_text()) if extra.exists() else []
paths = sorted(set(paths) | {str(path.relative_to(ROOT)) for path in DESTINATION.rglob('*') if path.is_file()})
extra.write_text(json.dumps(paths, indent=2) + '\n')
print(json.dumps({'snapshotted_tools': len(records), 'directory': str(DESTINATION.relative_to(ROOT)),
                  'stage_extra_paths': len(paths)}, indent=2))
