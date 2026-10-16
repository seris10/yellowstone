"""Immutable runtime generations and atomic release activation."""
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from yellowstone_python.common.io import write_json_atomic

from yellowstone_python.common.io import sha256_file as _sha

import datetime
import hashlib
import json
import shutil
from pathlib import Path

from yellowstone_python.common.provenance import CONTRACT_VERSION, WORLD_ID, default_world_root
from yellowstone_python.common.io import load_json
from yellowstone_python.exporters.godot_sidecars import produce_all as produce_sidecars
from yellowstone_python.exporters.to_ecosystem import validate_for_godot
from yellowstone_python.common.canopy_artifacts import CANOPY_RENDER_FILES, FOREST_FLOOR_FILE

FILES = [
    ("ecosystem.godot.json", "data/ecosystem.json", True),
    # Unread artifacts stay in build sidecars; data/ carries runtime files.
    ("pool_shells.json", "data/pool_shells.json", False),
    ("snow_map.png", "assets/textures/snow_map.png", False),
    ("snow_patch_mask.png", "data/snow_patch_mask.png", False),
    ("outflow_network/outflow_network.json", "data/outflow_network/outflow_network.json", False),
    ("outflow_network/wet_mask.i16", "data/outflow_network/wet_mask.i16", False),
    ("outflow_network/flow_fraction.f32", "data/outflow_network/flow_fraction.f32", False),
    ("outflow_network/in_pool.i16", "data/outflow_network/in_pool.i16", False),
    ("season.json", "data/season.json", False),
    # Missing optional build artifacts are recorded as publish gaps.
    ("plume_field.json", "data/plume_field.json", False),
    ("geochemistry.json", "data/geochemistry.json", False),
    ("calibration_summary.json", "data/calibration_summary.json", False),
    ("pools_state.json", "data/pools_state.json", False),
    ("snow_cover.json", "data/snow_cover.json", False),
    ("overland_field.json", "data/overland_field.json", False),
    ("groundwater_field.json", "data/groundwater_field.json", False),
    ("census.json", "data/census.json", False),
    # Weather snapshot (schema v2) consumed by yellowstone_midway/scripts/weather_snapshot_reader.gd.
    ("weather_snapshot.json", "data/weather_snapshot.json", False),
    # Replay files refresh the study-scene comparison pair when a build produces them.
    ("firehole_control.json", "data/firehole_control.json", False),
    ("firehole_pulse.json", "data/firehole_pulse.json", False),
    # and integration sidecars.
    ("ground_heat.json", "data/ground_heat.json", False),
    ("soil_temperature.json", "data/soil_temperature.json", False),
    ("evapotranspiration.json", "data/evapotranspiration.json", False),
    ("winter_grazing.json", "data/winter_grazing.json", False),
    ("mammals.json", "data/mammals.json", False),
    ("mammal_catalogue.json", "data/mammal_catalogue.json", False),
    ("piscivores.json", "data/piscivores.json", False),
    ("steam_microclimate.json", "data/steam_microclimate.json", False),
    # per-cell replay stressor sidecars.
    ("river_shading.json", "data/river_shading.json", False),
    ("river_oxygen.json", "data/river_oxygen.json", False),
    ("periphyton.json", "data/periphyton.json", False),
    ("solute_transport.json", "data/solute_transport.json", False),
    # outflow chain and mat state outputs.
    ("outflow_temperature.json", "data/outflow_temperature.json", False),
    ("outflow_temperature.f32", "data/outflow_temperature.f32", False),
    ("mat_state.json", "data/mat_state.json", False),
    ("mat_community.i16", "data/mat_community.i16", False),
    ("mat_pigment.png", "data/mat_pigment.png", False),
    ("outflow_to_replay_lateral.json", "data/outflow_to_replay_lateral.json",
     False),
    ("outflow_foodweb.json", "data/outflow_foodweb.json", False),
    ("pool_ramps.json", "data/pool_ramps.json", False),
    ("river_replay.json", "data/river_replay.json", True),
    ("world.runtime.json", "data/world.json", True),
    ("portfolio_comparison.json", "data/portfolio_comparison.json", False),
    ("insect_bird.json", "data/insect_bird.json", False),
    ("grazer.json", "data/grazer.json", False),
    ("fish.json", "data/fish.json", False),
    ("equations.json", "data/equations.json", False),
    ("param_registry.json", "data/param_registry.json", False),
    ("claims.json", "data/claims.json", False),
    ("species_catalogue.json", "data/species_catalogue.json", False),
    ("substrate_rules.json", "data/substrate_rules.json", False),
]
FILES.extend((f"lidar_canopy/{name}", f"data/lidar_canopy/{name}", False)
             for name in CANOPY_RENDER_FILES)
FILES.append((FOREST_FLOOR_FILE, f"data/{FOREST_FLOOR_FILE}", False))
# Study replays carry a build_id that must resolve to a build dir under derived/.
STUDY_REPLAY_FILES = ("firehole_control.json", "firehole_pulse.json")
DIRS = [
    ("pool_ramps", "assets/textures/pool_ramps"),
]


def consumer_manifest_errors(world_root: Path, files=None) -> list[str]:
    """Require published files to name an existing script consumer."""
    try:
        manifest = load_json(world_root / "data" / "consumers.json")
    except ValueError as exc:
        return [str(exc)]
    consumers = manifest.get("consumers", {})
    errors = []
    for _, target, _ in FILES if files is None else files:
        readers = consumers.get(target)
        if not isinstance(readers, list) or not readers:
            errors.append(f"{target}: no registered consumer")
            continue
        for reader in readers:
            path = world_root / reader
            if not path.is_file():
                errors.append(f"{target}: missing consumer {reader}")
    return errors




def _study_replay_build_id_ok(path: Path,
                              derived_root: Path) -> tuple[str, str]:
    """Verdict for a study-replay file: (status, detail).
'ok' when source_build_id names a sibling build dir; 'refused' otherwise."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "refused", f"could not read {path.name}: {exc}"
    if not isinstance(doc, dict):
        return "refused", f"{path.name} is not a JSON object"
    source_bid = doc.get("source_build_id")
    if not isinstance(source_bid, str) or not source_bid.strip():
        return "refused", (
            f"{path.name} lacks source_build_id; the study runner must "
            f"carry forward the build_id of the derived/ build it "
            f"consumed")
    target = derived_root / source_bid
    if not target.is_dir():
        return "refused", (
            f"study replay source_build_id {source_bid!r} has no "
            f"matching build dir at {target}")
    return "ok", (f"{path.name} source_build_id {source_bid!r} "
                  f"resolves to {target}")


def _load_json_or_refuse(path: Path, label: str) -> tuple[dict | None, int]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        logger.error(f"refusing: missing {label} at {path}")
        return None, 3
    except json.JSONDecodeError as exc:
        logger.error(f"refusing: invalid JSON in {label} ({path}): {exc}")
        return None, 3
    if not isinstance(value, dict):
        logger.error(f"refusing: {label} is not a JSON object")
        return None, 3
    return value, 0


def verify_build(build: Path, *, unverified: bool = False) -> tuple[dict, dict]:
    """Authenticate build artifacts and the check report before staging."""
    build = Path(build)
    manifest = load_json(build / "BUILD.json")
    checks = load_json(build / "CHECKS.json")
    if manifest.get("build_id") != build.name:
        raise ValueError("build directory identity differs from BUILD.json")
    if manifest.get("contract_version") != CONTRACT_VERSION or manifest.get("world_id") != WORLD_ID:
        raise ValueError("unsupported build contract or world")
    hashes = manifest.get("output_artifact_hashes")
    if not isinstance(hashes, dict) or "CHECKS.json" not in hashes:
        raise ValueError("build lacks authenticated output and check-report hashes")
    for name, expected in hashes.items():
        relative = Path(name)
        source = build / relative
        if relative.is_absolute() or not source.resolve().is_relative_to(build.resolve()):
            raise ValueError("artifact path escapes build directory")
        if source.is_symlink() or not source.is_file() or _sha(source) != expected:
            raise ValueError(f"checked artifact changed: {name}")
    if not isinstance(checks.get("passed"), bool) or (not checks["passed"] and not unverified):
        raise ValueError("build checks did not pass")
    assessment = checks.get("assessment", {})
    if not unverified:
        if assessment.get("build_id") != manifest["build_id"]:
            raise ValueError("check report lacks the evaluated build identity")
        if assessment.get("model_variant_id") != manifest.get("model_variant_id"):
            raise ValueError("check report model variant differs from build")
        from yellowstone_python.common.provenance import sha256_json
        if assessment.get("input_identity") != manifest.get("input_identity") or manifest.get("input_identity") != sha256_json(manifest.get("portable_identity")):
            raise ValueError("check report effective inputs differ from build")
        if assessment.get("artifact_hashes") != {key: value for key, value in hashes.items() if key != "CHECKS.json"}:
            raise ValueError("check report artifact binding differs from build")
    return manifest, checks


def release_plan(build: Path, manifest: dict, checks: dict, *, unverified: bool = False) -> tuple[dict, dict]:
    """Resolve complete runtime contents and explicit optional absence."""
    files, artifacts = {}, {}
    hashes = manifest["output_artifact_hashes"]
    for source_name, target, required in FILES:
        source = build / source_name
        if not source.is_file():
            if required:
                raise ValueError(f"required runtime artifact absent: {source_name}")
            artifacts[target] = {"state": "unavailable", "required": False,
                                 "reason": "absent from this build"}
            continue
        if source_name not in hashes:
            raise ValueError(f"runtime artifact lacks checked hash: {source_name}")
        if source_name in STUDY_REPLAY_FILES:
            status, detail = _study_replay_build_id_ok(source, build.parent)
            if status != "ok":
                raise ValueError(detail)
        files[target] = source
        artifacts[target] = {"state": "present", "path": target, "required": required,
                             "sha256": hashes[source_name]}
    for source_name, target in DIRS:
        source_dir = build / source_name
        members = sorted(source_dir.rglob("*")) if source_dir.is_dir() else []
        selected = [path for path in members if path.is_file() and path.suffix in (".png", ".json")]
        artifacts[target + "/"] = {"state": "present" if selected else "unavailable",
                                    "reason": "complete directory membership for this generation"}
        for source in selected:
            name = str(source.relative_to(build))
            if name not in hashes:
                raise ValueError(f"runtime texture lacks checked hash: {name}")
            relative = target + "/" + str(source.relative_to(source_dir))
            files[relative] = source
            artifacts[relative] = {"state": "present", "path": relative,
                                   "required": False, "sha256": hashes[name]}
    for name in ("BUILD.json", "CHECKS.json"):
        files[name] = build / name
        artifacts[name] = {"state": "present", "path": name, "required": True,
                           "sha256": _sha(build / name)}
    release = {"schema": "yellowstone.release.v1", "build_id": manifest["build_id"],
               "model_variant_id": manifest.get("model_variant_id", "unidentified"),
               "scenario_id": manifest.get("scenario_id", manifest["build_id"]),
               "source_commit": manifest.get("code_commit"),
               "source_sha256": manifest.get("code_sha256"),
               "run_mode": manifest.get("run_mode"), "artifacts": artifacts,
               "checks": {"path": "CHECKS.json", "sha256": hashes["CHECKS.json"]},
               "verification": {"status": "unverified_development" if unverified else "numerical_and_contract_checks_passed",
                                "checks_passed": checks["passed"], "empirical_acceptance": "not_yet_accepted"}}
    from yellowstone_python.common.provenance import sha256_json
    release["release_id"] = sha256_json(release)
    return release, files


def verify_release(directory: Path, release: dict) -> None:
    """Require a complete generation with matching artifact bytes."""
    for record in release["artifacts"].values():
        if record["state"] != "present" or "path" not in record:
            continue
        source = directory / record["path"]
        if not source.resolve().is_relative_to(directory.resolve()) or source.is_symlink():
            raise ValueError("release artifact escapes generation")
        if not source.is_file() or _sha(source) != record["sha256"]:
            raise ValueError(f"release artifact changed: {record['path']}")


def publish_generation(build: Path, destination: Path, *, unverified: bool = False,
                       copy_file=None) -> dict:
    """Stage verified immutable bytes and activate one generation atomically."""
    import os
    import tempfile
    build, destination = Path(build), Path(destination)
    manifest, checks = verify_build(build, unverified=unverified)
    errors = validate_for_godot(load_json(build / "ecosystem.godot.json"))
    if errors:
        raise ValueError("ecosystem contract: " + "; ".join(errors))
    if not (destination / "project.godot").is_file():
        raise ValueError("destination is not a Godot project")
    errors = consumer_manifest_errors(destination)
    if errors:
        raise ValueError("consumer declarations: " + "; ".join(errors))
    release, files = release_plan(build, manifest, checks, unverified=unverified)
    parent = destination / "data/releases"
    parent.mkdir(parents=True, exist_ok=True)
    final = parent / release["release_id"]
    copier = shutil.copy2 if copy_file is None else copy_file
    if not final.exists():
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=parent))
        for target_name, source in files.items():
            target = stage / target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            copier(source, target)
            with target.open("rb") as stream:
                os.fsync(stream.fileno())
        verify_release(stage, release)
        write_json_atomic(stage / "RELEASE.json", release, indent=2)
        os.replace(stage, final)
    elif load_json(final / "RELEASE.json") != release:
        raise ValueError("existing generation identity differs from release manifest")
    verify_release(final, release)
    pointer = {"schema": "yellowstone.release_pointer.v1", "release_id": release["release_id"],
               "manifest": str((final / "RELEASE.json").relative_to(destination)),
               "sha256": _sha(final / "RELEASE.json")}
    write_json_atomic(destination / "data/release.json", pointer, indent=2)
    return release






def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.publish import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
