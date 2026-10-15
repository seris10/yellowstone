"""Prepare explicit-receipt verification, ledger and release presentation records."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "yellowstone_python"))
from tools.run_evidence import evidence_status, source_hashes
from yellowstone_python.common.provenance import sha256_json
from forest_runtime_scope import audit_scope, scoped, scoped_receipt_status
from forest_benchmark_evidence import validate_benchmark


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(relative):
    return json.loads((ROOT / relative).read_text())


def local_path(relative):
    path = (ROOT / relative).resolve()
    assert path.is_relative_to(ROOT), relative
    return path


def receipt(specification, identity, expected_name=None):
    path = local_path(specification["path"])
    value = json.loads(path.read_text())
    assert value["name"] == specification["name"]
    if expected_name is not None:
        assert value["name"] == expected_name
    scope_status = scoped_receipt_status(value, ROOT)
    assert scope_status["scoped_runtime_identity"] == identity
    assert scope_status["status"] == "executed_passed", specification["path"]
    assert value["returncode"] == 0
    assert value.get("tests", {}).get("failed", 0) == 0
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path), "name": value["name"],
            "status": "executed_passed", "source_identity": value["source_identity"],
            "source_commit": value.get("source_commit"), "started_utc": value["started_utc"],
            "scope_verification": scope_status,
            "tests": value.get("tests"), "fixture_hashes": value.get("fixture_hashes", {})}


def replace_row(text, label, verdict, detail):
    row = f"| {label} | {verdict} | {detail} |"
    prefix = "| " + label + " |"
    lines = text.splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    assert len(matches) <= 1, label
    if matches:
        lines[matches[0]] = row
    else:
        at = next(i for i, line in enumerate(lines) if line.startswith("| Whole-world performance |"))
        lines.insert(at, row)
    return "\n".join(lines) + "\n"


def control_limit(submission):
    changed = []
    for view in submission["native"]:
        assert view["compaction_difference"]["changed_channels"] == 0
        for key in ("repeat_difference", "restoration_difference", "recompaction_difference"):
            item = view.get(key, {})
            if item.get("changed_channels", 0):
                changed.append(f"{view['id']} {key}: {item['changed_channels']} channels, maximum {item['maximum_byte_difference']}/255")
    prior = " ".join(item for item in submission.get("limitations", []) if "Earlier whole-scene controls" in item)
    for item in submission.get("prior_failed_diagnostics", []):
        assert digest(local_path(item["path"])) == item["sha256"]
    if changed:
        text = ("Original-to-compacted image comparisons retain exact equality. Independent control variability is "
                + "; ".join(changed) + ". No image tolerance was widened; these controls limit a general claim of deterministic raster output.")
    else:
        text = ("Original-to-compacted images and all recorded repeated/rebound controls have zero changed channels in this run. "
                "This result is limited to the tested views and renderer state.")
    return text + (" " + prior if prior else "")


def publication_record(config, archive, release_id):
    specification = config.get("publication")
    if specification is None:
        return {"status": "not_published_or_not_verified", "scope": "No durable GitHub publication evidence supplied."}
    assert archive is not None, "Archive verification precedes publication verification"
    tag = specification["tag"]
    expected_commit = specification["commit"]
    assert len(expected_commit) == 40
    metadata = json.loads(subprocess.check_output([
        "gh", "api", "repos/seris10/yellowstone/releases/tags/" + tag], cwd=ROOT))
    commit = subprocess.check_output([
        "gh", "api", "repos/seris10/yellowstone/commits/" + tag, "--jq", ".sha"], cwd=ROOT, text=True).strip()
    remote_main = subprocess.check_output([
        "git", "ls-remote", "origin", "refs/heads/main"], cwd=ROOT, text=True).split()[0]
    assert commit == expected_commit and remote_main == expected_commit
    assert metadata["tag_name"] == tag and metadata["draft"] is False
    asset = [a for a in metadata["assets"] if a["name"] == archive["archive"]]
    assert len(asset) == 1 and asset[0]["size"] == archive["archive_bytes"]
    downloaded = local_path(specification["downloaded_archive"])
    assert downloaded.stat().st_size == archive["archive_bytes"]
    assert digest(downloaded) == archive["archive_sha256"]
    if asset[0].get("digest"):
        assert asset[0]["digest"] == "sha256:" + archive["archive_sha256"]
    assert release_id == archive["release_id"]
    return {"status": "remote_tag_main_asset_and_download_verified", "tag": tag,
            "commit": commit, "remote_main_commit": remote_main, "release_url": metadata["html_url"],
            "release_id": release_id, "github_release_id": metadata["id"], "prerelease": metadata["prerelease"],
            "archive_asset_id": asset[0]["id"], "archive_bytes": asset[0]["size"],
            "downloaded_archive": str(downloaded.relative_to(ROOT)), "downloaded_archive_sha256": digest(downloaded),
            "ci_status": specification.get("ci_status", "not_checked"),
            "scope": "Read-only GitHub API and remote ref checks plus actual downloaded archive bytes. CI is reported separately."}


def prepare(config):
    equivalence = read(config["equivalence"])
    assert equivalence["ok"] is True
    assert scoped(source_hashes(ROOT)) == equivalence["scoped_runtime_source_hashes"]
    assert audit_scope(ROOT)["scope_helper_sha256"] == equivalence["runtime_scope_audit"]["scope_helper_sha256"]
    identity = equivalence["scoped_runtime_identity"]
    assert sha256_json(equivalence["scoped_runtime_source_hashes"]) == identity
    fresh = {role: receipt(specification, identity) for role, specification in config["receipts"].items()}
    required = {"provenance", "tree_submission", "package_headless", "package_native"}
    assert required <= fresh.keys(), required - fresh.keys()
    package = ROOT / "work/Yellowstone-Forest-Spring-Update"
    fixtures = {str((package / name).relative_to(ROOT)) for name in
                ("RUNTIME.json", "project.godot", "scenes/authored_world.tscn", "data/release.json")}
    for role, name in (("package_headless", "forest-package-headless"), ("package_native", "forest-package-native")):
        assert fresh[role]["name"] == name
        assert fixtures <= fresh[role]["fixture_hashes"].keys()
    assert read("work/forest-package-startup-receipts.json") == {
        fresh[role]["name"]: fresh[role]["path"] for role in ("package_headless", "package_native")}
    performance = read(config["performance"])
    assert performance["scoped_runtime_identity"] == identity
    assert [run["run"] for run in performance["runs"]] == ["a1", "b1", "b2", "a2"]
    measurements = {}
    for label, specification in config["performance_receipts"].items():
        measurements[label] = receipt(specification, identity)
        assert performance["measurement_receipts"][label] == measurements[label]["path"]
        assert performance["measurement_receipt_names"][label] == measurements[label]["name"]
    assert set(measurements) == {"a1", "b1", "b2", "a2"}
    benchmark_verification = validate_benchmark(performance,
        {label: read(item["path"]) for label, item in measurements.items()}, ROOT)
    assert performance["benchmark_verification"] == benchmark_verification
    targets = performance["acceptance_target"]
    runs = performance["runs"]
    prior = [r["report"]["moving_camera"] for r in runs if r["run"].startswith("a")]
    updated = [r["report"]["moving_camera"] for r in runs if r["run"].startswith("b")]
    median_delta = (sum(r["median_wall_frame_ms"] for r in updated) / sum(r["median_wall_frame_ms"] for r in prior) - 1) * 100
    draw_delta = (sum(r["draw_calls_mean"] for r in updated) / sum(r["draw_calls_mean"] for r in prior) - 1) * 100
    target_pass = all(r["median_wall_frame_ms"] <= targets["median_wall_frame_ms_max"] and r["p95_wall_frame_ms"] <= targets["p95_wall_frame_ms_max"] for r in updated)
    perf_text = (f"The mean of the two run medians changes by {median_delta:+.1f} percent versus the published surface package; mean draw calls change by {draw_delta:+.1f} percent. "
                 f"The update {'meets' if target_pass else 'does not meet'} the retained median <= 33.4 ms and p95 <= 50 ms target in both measured runs. "
                 "These four short ABBA runs share authored weather, epoch and a normalized physical sun vector, with the baseline sun convention corrected only in memory. They include presentation, common forcing-verification overhead and uncontrolled desktop load; GPU execution time is unavailable. They do not establish other-hardware performance.")
    submission = read(config["submission_report"])
    assert submission["ok"] and len(submission["native"]) >= 3
    for key, path in (("source_sha256", "yellowstone_midway/scripts/tree_submission.gd"),
                      ("world_sha256", "yellowstone_midway/scripts/world.gd"),
                      ("validator_sha256", "yellowstone_midway/tools/validate_tree_submission.gd"),
                      ("scene_sha256", "yellowstone_midway/scenes/authored_world.tscn")):
        assert submission[key] == digest(ROOT / path), path
    control_text = control_limit(submission)
    terrace = config["terrace"]
    assert terrace["summary"] and terrace["scope"] and terrace["source_hashes"]
    for path, expected in terrace["source_hashes"].items():
        assert digest(local_path(path)) == expected, path
    terrace_evidence = {path: digest(local_path(path)) for path in terrace["evidence"]}
    terrace_review = read(terrace["review"])
    assert terrace_review["ok"] is True
    assert terrace_review["shader_sha256"] == terrace["source_hashes"]["yellowstone_midway/shaders/thermal_apron.gdshader"]
    assert terrace_review["capture_report_sha256"] == digest(local_path(terrace["capture_report"]))
    for path, record in terrace_review["preserved_inputs"].items():
        assert digest(local_path(path)) == record["sha256"]
    terrace["verification_scope"] = "Stored native image diagnostics with authenticated shader/input/report hashes; not a new tools.run_evidence execution receipt. Other runtime changes after this diagnostic are covered only by separately recorded final native checks."

    canopy = config.get("canopy")
    canopy_verified = None
    if canopy is not None:
        assert canopy["receipt_role"] in fresh
        canopy_report = read(canopy["report"])
        assert canopy_report["ok"] is True and not canopy_report["failures"]
        assert canopy_report["checks"] > 0 and canopy_report["source_hashes"]
        for path, expected in canopy_report["source_hashes"].items():
            assert digest(local_path(path)) == expected, path
        assert canopy_report["native_views"], "Final native canopy views required"
        for view in canopy_report["native_views"]:
            assert digest(local_path(view["path"])) == view["sha256"]
        assert canopy["summary"]
        canopy_verified = {"report": canopy["report"], "sha256": digest(local_path(canopy["report"])),
            "receipt": fresh[canopy["receipt_role"]], "checks": canopy_report["checks"],
            "summary": canopy["summary"], "preservation": canopy_report["preservation"],
            "limitations": canopy_report["limitations"]}
    archive = None
    if config.get("archive_receipt"):
        archive = read(config["archive_receipt"])
        archive_path = Path(config["report"]["output_dir"]) / archive["archive"]
        assert digest(archive_path) == archive["archive_sha256"]
        assert archive["scoped_runtime_identity"] == identity
        assert archive["release_id"] == equivalence["release_id"]
    publication = publication_record(config, archive, equivalence["release_id"])
    verification = read("evidence/forest-verification.json")
    if "historical_numerical_verification" not in verification:
        historical_receipts = {}
        for name, relative in verification["receipts"].items():
            value = read(relative)
            assert value["status"] == "executed_passed" and value["source_commit"] == equivalence["model_source_commit"]
            assert digest(local_path(value["output"])) == value["output_sha256"]
            historical_receipts[name] = {"path": relative, "sha256": digest(local_path(relative)),
                "execution_status_at_recorded_source": value["status"], "current_whole_source_status": evidence_status(value, ROOT)}
        verification["historical_numerical_verification"] = {
            "source_commit": equivalence["model_source_commit"], "tests": copy.deepcopy(verification["tests"]),
            "builds": copy.deepcopy(verification["builds"]), "receipts": historical_receipts,
            "scope": "Executed at the recorded original source snapshot. Runtime-only changes make the global receipt freshness check stale; the equivalence proof separately verifies unchanged numerical code, inputs and checked outputs."}
    verification.update({"model_source_commit": equivalence["model_source_commit"],
        "runtime_source_commit": equivalence["runtime_source_commit"], "runtime_source_identity": equivalence["runtime_source_identity"],
        "scoped_runtime_identity": identity, "source_scope": equivalence["runtime_scope_audit"],
        "excluded_source_observation": equivalence["excluded_source_observation"],
        "status": "local_runtime_verified_publication_pending" if publication["status"] == "not_published_or_not_verified" else "local_runtime_and_github_download_verified",
        "test_scope": "Top-level 2,155-pass/14-skip totals describe the original numerical/source snapshot; fresh runtime receipt counts remain separate.",
        "runtime_equivalence": {"path": config["equivalence"], "sha256": digest(local_path(config["equivalence"]))},
        "runtime_receipts": fresh, "performance_receipts": measurements,
        "performance": {"path": config["performance"], "sha256": digest(local_path(config["performance"])),
                        "updated_runs_pass_target": target_pass, "median_percent_change": median_delta,
                        "draw_percent_change": draw_delta, "summary": perf_text, "benchmark_verification": benchmark_verification},
        "tree_submission": {"path": config["submission_report"], "sha256": digest(local_path(config["submission_report"])),
                            "checks": submission["checks"], "control_scope": control_text},
        "terrace_revision": {**terrace, "evidence_hashes": terrace_evidence}, "publication": publication,
        "package_startup_receipts": {fresh[role]["name"]: fresh[role]["path"] for role in ("package_headless", "package_native")}})
    if canopy_verified:
        verification["canopy_attachment"] = canopy_verified
        verification["remaining_limits"] = [item for item in verification["remaining_limits"]
            if not item.startswith("Thin residual-canopy supports")]
        verification["remaining_limits"].extend(item for item in canopy_verified["limitations"]
            if item not in verification["remaining_limits"])
    if archive:
        verification["archive_verification"] = {"receipt": config["archive_receipt"], "sha256": digest(local_path(config["archive_receipt"])),
            "archive_sha256": archive["archive_sha256"], "archive_bytes": archive["archive_bytes"],
            "verified_file_hashes": archive["verified_file_hashes"]}
    ledger = (ROOT / "yellowstone_python_spec/fixes/ledger/fixes-57.md").read_text()
    identity_text = (f"Numerical generation `{equivalence['release_id']}` retains build `{equivalence['build_id']}` and model source commit `{equivalence['model_source_commit']}`. "
        f"Runtime source commit `{equivalence['runtime_source_commit']}` has separate full-observation and scoped runtime hashes. Exactly `dashboard/build_data.py`, an unbundled dashboard generator outside the numerical hash roots, is excluded from runtime comparisons; its uncommitted hash and full global receipt status remain recorded. `evidence/forest-runtime-equivalence.json` verifies unchanged numerical code/configuration, physical inputs and checked outputs; reviewed runtime and license-metadata changes remain explicit. "
        "The 2,155 passing and 14 skipped Python cases belong to the original source snapshot. Fresh runtime execution receipts are individually listed in `evidence/forest-verification.json`.")
    ledger = replace_row(ledger, "Numerical and runtime identity", "verified separately", identity_text)
    ledger = replace_row(ledger, "Tree submission", "implemented; native checks pass", f"`{config['submission_report']}` records {submission['checks']} checks. Immutable source records, tree geometry, shader LOD ranges and existing shadows remain available. Runtime copies submit a conservative visible prefix, trading extra buffers and intermittent CPU work for fewer submitted primitives. {control_text} Whole-world timing remains a separate measurement.")
    if canopy_verified:
        ledger = replace_row(ledger, "Residual canopy attachment", "implemented; native checks pass",
            canopy_verified["summary"] + " " + " ".join(canopy_verified["limitations"]) +
            " Evidence: `" + canopy_verified["report"] + "` and its explicit final execution receipt.")
    ledger = replace_row(ledger, "Basin terrace detail", "implemented; runtime correction verified", terrace["summary"] + " " + terrace["scope"] + " Evidence: " + ", ".join("`" + p + "`" for p in terrace["evidence"]) + ".")
    ledger = replace_row(ledger, "Whole-world performance", "measured; target met" if target_pass else "measured; target unmet", perf_text + " `evidence/forest-render-pairs.json` retains the final reports and explicit receipts. The uncompacted regression remains separately available. Source counts and feature retention do not imply constant memory usage.")
    if publication["status"] == "not_published_or_not_verified":
        delivery_verdict = "local runtime verified; GitHub pending"
        delivery_text = "Fresh offline headless and native Godot 4.5.1 startup checks pass against the exact packaged RUNTIME inventory, selected generation and saved scene. Both check all four grounded starting anchors and zero reported heat-budget error. Explicit receipt paths are in `evidence/forest-verification.json`. " + ("The local archive is byte-verified. " if archive else "Archive assembly and byte verification remain separate. ") + "No GitHub publication completion is claimed."
    else:
        delivery_verdict = "GitHub release and downloaded archive verified"
        delivery_text = f"The remote main branch and release tag `{publication['tag']}` resolve to `{publication['commit']}`. GitHub release/asset metadata match the selected archive, and the downloaded {publication['archive_bytes']} bytes have SHA-256 `{publication['downloaded_archive_sha256']}`. Fresh packaged headless/native startup remains bound to the exact runtime inventory. CI state is `{publication['ci_status']}` and is separate from native/scientific verification."
    ledger = replace_row(ledger, "Delivery", delivery_verdict, delivery_text)
    ledger = ledger.replace("Whole-world performance and\ndelivery require their separate final receipts before either verdict changes.",
                            "Whole-world performance and delivery retain their separate recorded evidence states.")
    canopy_limit = (" ".join(canopy_verified["limitations"]) if canopy_verified else
                    "Thin residual-canopy supports and simplified logs remain visible close up.")
    compaction_limit = "Tree LOD endpoint fidelity still fails 62 of 96 retained cases; smooth transitions do not establish matching silhouettes or brightness. " + canopy_limit + " " + control_text
    limits = (compaction_limit + " Local crown envelopes, plant abundance, ring widths, terrace relief and rainbow occurrence frequency remain authored or uncalibrated. "
              "The historical numerical matrix skips 14 optional-library cases. Other platforms, native executable exports, field validation and human visual acceptance remain unavailable.")
    report = copy.deepcopy(config["report"])
    report.update({"summary": "Fuller lodgepole crowns, continuous pine-needle detail and terrain-checked wood and small plants improve the forest. The spring preserves the supplied palette, with brighter cyan, narrow yellow transitions and orange runoff. Clouds and weather-history-dependent rainbow optics are integrated.",
        "performance": perf_text, "performance_rows": [[r["run"].upper(), "Published surface package" if r["run"].startswith("a") else "Update", round(r["report"]["moving_camera"]["median_wall_frame_ms"],3), round(r["report"]["moving_camera"]["p95_wall_frame_ms"],3)] for r in runs],
        "verification": f"The numerical matrix executed at model source commit {equivalence['model_source_commit']} passed 2,155 cases with 14 optional-library skips. The runtime commit {equivalence['runtime_source_commit']} has fresh native, provenance and packaged-startup receipts. Exact source/input comparisons preserve the original checked numerical generation. Tree compaction passes {submission['checks']} checks, with exact original-to-compacted images in the tested views; control repeatability is reported below.",
        "limits": limits, "terrace": terrace["summary"] + " " + terrace["scope"],
        "generation": equivalence["release_id"], "zip_sha": archive["archive_sha256"] if archive else "Archive verification pending",
        "commit": report.get("commit") or equivalence["runtime_source_commit"]})
    if canopy_verified:
        report["summary"] += " " + canopy_verified["summary"]
    for key in ("overlook_caption", "floor_caption", "projection_caption", "rainbow_caption"):
        assert report.get(key), key
    notes = (report["summary"] + "\n\n" + terrace["summary"] + " " + terrace["scope"] + "\n\n"
             "Download **Yellowstone-Forest-Spring-Update.zip**, extract it, and open the included project with **Godot 4.5.1**. Python is unnecessary for offline exploration. This is a portable Godot project; native executable exports remain unavailable. `Yellowstone-Visual-Update.html` contains the visual comparison and measured performance.\n\n"
             + perf_text + "\n\n" + compaction_limit + "\n\n"
             + f"Checked numerical build: `{equivalence['build_id']}` at `{equivalence['model_source_commit']}`. Runtime source: `{equivalence['runtime_source_commit']}`. Fresh runtime checks and byte-identical numerical inputs are separately recorded. "
             "Scientific/ecological claims remain `not_yet_accepted`; authored display parameters and uncalibrated rainbow occurrence are identified in the report.\n\n"
             "Tree census, placements, measured terrain and existing features are preserved. Free human-made CC0 textures are attributed. KJR owns the included animal meshes. No 3DAIStudio credits were used. Other platforms and human visual acceptance remain untested.\n")
    return verification, ledger, report, notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--apply", action="store_true", help="Write maintained verification and ledger after validation")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    verification, ledger, report, notes = prepare(config)
    destination = ROOT / "work/forest-closeout-preview"
    destination.mkdir(exist_ok=True)
    (destination / "forest-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    (destination / "fixes-57.md").write_text(ledger)
    (ROOT / "work/forest-report-config.json").write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "work/forest-release-notes.md").write_text(notes)
    if args.apply:
        (ROOT / "evidence/forest-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
        (ROOT / "yellowstone_python_spec/fixes/ledger/fixes-57.md").write_text(ledger)
    print(json.dumps({"status": verification["status"], "maintained_files_written": args.apply,
                      "updated_runs_pass_target": verification["performance"]["updated_runs_pass_target"],
                      "preview_directory": str(destination.relative_to(ROOT)),
                      "report_config": "work/forest-report-config.json", "release_notes": "work/forest-release-notes.md"}, indent=2))


if __name__ == "__main__":
    main()
