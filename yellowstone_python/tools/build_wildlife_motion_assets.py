"""Wildlife asset import and source-bound animation diagnostics."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import os
import tempfile
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from yellowstone_python.wildlife_motion.asset_audit import audit_asset
from yellowstone_python.wildlife_motion.conversion import mammal_shape, read_binary_stl
from yellowstone_python.wildlife_motion.gltf import export_asset, load_asset, read_glb, write_glb
from yellowstone_python.wildlife_motion.mammals import MammalEngine, register_sole_offsets
from yellowstone_python.wildlife_motion.rigging import make_weights, prepare
from yellowstone_python.wildlife_motion.species import get_profile
from yellowstone_python.wildlife_motion.core import Skeleton
from yellowstone_python.wildlife_motion.validation import validate_motion
from yellowstone_python.wildlife_motion.quality import serialized_surface_report, evaluate_surface_budget
from yellowstone_python.common.provenance import sha256_json


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_roots(source: Path, target: Path) -> dict:
    """Promote the skinned surface to a scene root while preserving binary views."""
    if source.resolve() == target.resolve():
        raise ValueError("Source and target must differ")
    doc, blob = read_glb(source)
    skinned = [i for i, node in enumerate(doc["nodes"]) if "skin" in node]
    for index in skinned:
        for node in doc["nodes"]:
            if index in node.get("children", []):
                if any(k in node for k in ("matrix", "translation", "rotation", "scale")):
                    raise ValueError("Skinned surface has a transformed parent")
                node["children"].remove(index)
        for scene in doc["scenes"]:
            if index not in scene["nodes"]:
                scene["nodes"].append(index)
    write_glb(target, doc, blob)
    return {"source_sha256": _digest(source), "sha256": _digest(target),
            "binary_views_preserved": read_glb(target)[1] == blob,
            "change": "skinned_surface_scene_root" if skinned else "container_normalization"}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False))


def load_review_manifest(path: Path | None) -> dict:
    """Resolve source-bound rig, control and quality inputs for production."""
    if path is None:
        return {}
    document = json.loads(path.read_text())
    if document.get("schema") != "yellowstone.wildlife_motion_build_review.v1" or not isinstance(document.get("assets"), dict):
        raise ValueError("Reviewed assets require the production review manifest schema")
    result = copy.deepcopy(document["assets"])
    for identity, record in result.items():
        if len(identity) != 64 or record.get("source_sha256", identity) != identity:
            raise ValueError("Review records require exact source SHA256 keys")
        for field in ("rig", "controls", "target_engine_review"):
            if isinstance(record.get(field), str):
                source = path.parent / record[field]
                record[field+"_sha256"] = _digest(source)
                record[field] = json.loads(source.read_text())
        evidence = record.get("target_engine_review", {}).get("captures", [])
        for capture in evidence:
            source = path.parent / capture["path"]
            if _digest(source) != capture.get("sha256"):
                raise ValueError("Target-engine review capture differs from its recorded bytes")
    return result


def _quality_gate(path, review, allow_development):
    """Require exact serialized surfaces and a predeclared production budget."""
    report = serialized_surface_report(path)
    budget = review.get("deformation_budget")
    decision = evaluate_surface_budget(report, budget) if budget else {
        "passed": False, "failures": ["predeclared_deformation_budget_unavailable"]}
    decision["geometric_budget_passed"] = decision["passed"]
    rig_status = review.get("rig", {}).get("metadata", {}).get("review_status")
    engine = review.get("target_engine_review", {})
    if rig_status != "reviewed":
        decision["failures"].append("source_bound_rig_review_unavailable")
    required = {"Idle", "Walk", "turn", "ground_height", "pause", "speed_change", "clip_transition"}
    if (engine.get("asset_sha256") != report.get("asset_sha256") or engine.get("status") != "accepted"
            or not engine.get("reviewer") or not engine.get("reviewer_kind") or not engine.get("captures")
            or not required <= set(engine.get("reviewed_cases", []))):
        decision["failures"].append("hash_bound_target_engine_visual_review_unavailable")
    decision["passed"] = not decision["failures"]
    if not decision["passed"] and not allow_development:
        raise ValueError("Production surface quality refused: " + ", ".join(decision["failures"]))
    return {"surface": report, "decision": decision,
            "production_eligibility": "passed" if decision["passed"] else "unaccepted_development"}


def check_preanimated_review(document: dict, review: dict) -> None:
    """Require selected landmarks and resolved controls in each serialized clip."""
    source_rig = document.get("extras", {}).get("wildlife_motion", {}).get("rig", {})
    expected = copy.deepcopy(review.get("rig", {}))
    actual = copy.deepcopy(source_rig)
    for rig in (expected, actual):
        rig.get("metadata", {}).pop("sole_offsets", None)
    if not actual or actual.get("metadata", {}).get("review_status") != "reviewed" or actual != expected:
        raise ValueError("Preanimated production assets must be rebuilt with the selected reviewed rig")
    profile = get_profile(actual["metadata"]["species"])
    if profile["engine"] != "mammal":
        raise ValueError("Preanimated production import requires a mammal profile")
    engine = MammalEngine(Skeleton.from_dict(source_rig), profile)
    controls = review.get("controls", {})
    if "overrides" in controls:
        controls = {"Walk": controls["overrides"]}
    if set(controls)-{"Idle", "Walk"}:
        raise ValueError("Production controls must select supported Idle or Walk modes")
    clips = {clip.get("name"): clip for clip in document.get("animations", [])}
    for mode in ("Idle", "Walk"):
        serialized = clips.get(mode, {}).get("extras", {}).get("wildlife_motion", {}).get("controls")
        if serialized != engine.parameters(mode, controls.get(mode, {})):
            raise ValueError("Preanimated clip controls differ from the selected " + mode + " controls")


def _animate(asset, profile_name, target, texture_limit=None, *, review_assets=None,
             allow_unreviewed_development=False, **axes):
    profile = get_profile(profile_name)
    review = (review_assets or {}).get(asset.source_sha256, {})
    rig = review.get("rig")
    if not allow_unreviewed_development and (not rig or rig.get("metadata", {}).get("review_status") != "reviewed"):
        raise ValueError("Production animation requires a source-bound reviewed rig; use explicit development mode for estimates")
    asset, skeleton = prepare(asset, profile, rig, **axes)
    joints, weights, weight_report = make_weights(asset.vertices, asset.faces, skeleton)
    register_sole_offsets(asset.vertices, joints, weights, skeleton)
    engine = MammalEngine(skeleton, profile)
    controls = review.get("controls", {})
    if "overrides" in controls:
        controls = {"Walk": controls["overrides"]}
    if set(controls)-{"Idle", "Walk"}:
        raise ValueError("Production controls must select supported Idle or Walk modes")
    clips, diagnostics, resolved = [], {}, {}
    for mode in ("Idle", "Walk"):
        override = controls.get(mode, {})
        resolved[mode] = engine.parameters(mode, override)
        clips.extend(engine.clips([mode], cycles=2, overrides=override))
        checked = copy.deepcopy(profile)
        checked["gaits"][mode] = resolved[mode]
        diagnostics[mode] = validate_motion(asset, skeleton, joints, weights,
                                            MammalEngine(skeleton, checked), [mode])
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".animation-stage-", dir=target.parent) as directory:
        staged = Path(directory)/target.name
        manifest = export_asset(asset, staged, skeleton, joints, weights, clips, texture_limit=texture_limit)
        quality = _quality_gate(staged, review, allow_unreviewed_development)
        quality.update(source_rig_sha256=sha256_json(rig) if rig else None,
                       resolved_controls=resolved, analytic_deformation=diagnostics)
        _write(staged.with_suffix(".quality.json"), quality)
        manifest["production_quality"] = {"path": target.with_suffix(".quality.json").name,
            "sha256": _digest(staged.with_suffix(".quality.json")), "status": quality["production_eligibility"]}
        manifest["rig_review_status"] = skeleton.metadata["review_status"]
        _write(staged.with_suffix(".manifest.json"), manifest)
        for source in (staged, staged.with_suffix(".manifest.json"), staged.with_suffix(".quality.json")):
            os.replace(source, target.parent/source.name)
    return manifest, weight_report


def bison_derivative(runtime_source: Path, original_source: Path, world_root: Path, *,
                     review_assets=None, allow_unreviewed_development=False) -> tuple:
    """Bind the reduced bison mesh and original texture bytes to runtime clips."""
    target = world_root / "assets/imported/wildlife_motion/bison_animated.glb"
    original, reduced = load_asset(original_source), load_asset(runtime_source)
    if len(reduced.faces) > 30000:
        raise ValueError("Runtime bison exceeds the authored 30000-triangle budget")
    textures = []
    for source in (original_source, runtime_source):
        doc, blob = read_glb(source)
        hashes = []
        for image in doc.get("images", []):
            view = doc["bufferViews"][image["bufferView"]]
            start = view.get("byteOffset", 0)
            hashes.append(hashlib.sha256(blob[start:start+view["byteLength"]]).hexdigest())
        textures.append(hashes)
    if textures[0] != textures[1]:
        raise ValueError("Reduced bison changes source texture bytes")
    manifest, weights = _animate(reduced, "bison", target, forward="+x", up="+y", align_heading=True,
        review_assets=review_assets, allow_unreviewed_development=allow_unreviewed_development)
    distances = cKDTree(reduced.vertices).query(original.vertices, workers=4)[0]
    reverse = cKDTree(original.vertices).query(reduced.vertices, workers=4)[0]
    proof = {"original_sha256": _digest(original_source),
        "reduced_source_sha256": _digest(runtime_source),
        "original_vertices": len(original.vertices), "original_triangles": len(original.faces),
        "runtime_vertices": len(reduced.vertices), "runtime_triangles": len(reduced.faces),
        "texture_bytes_preserved": True, "texture_sha256": textures[0],
        "original_bounds": [original.vertices.min(0).tolist(), original.vertices.max(0).tolist()],
        "runtime_bounds": [reduced.vertices.min(0).tolist(), reduced.vertices.max(0).tolist()],
        "vertex_distance_source_to_runtime": {"p95_asset_units": float(np.quantile(distances, .95)),
                                              "maximum_asset_units": float(distances.max())},
        "vertex_distance_runtime_to_source": {"p95_asset_units": float(np.quantile(reverse, .95)),
                                              "maximum_asset_units": float(reverse.max())},
        "distance_metric": "nearest_vertex_distances; triangle_surface_Hausdorff_unavailable",
        "status": "derived_not_field_validated", "scientific_acceptance": "not_yet_accepted"}
    entry = {"id": "bison_animated", "path": target.relative_to(world_root).as_posix(),
        "sha256": _digest(target), "source_sha256": proof["original_sha256"],
        "status": "operator_supplied", "geometry_rights": "unknown",
        "rig_status": manifest["rig_review_status"], "scientific_acceptance": "not_yet_accepted",
        "audit": audit_asset(target), "weights": weights, "geometry_reduction": proof}
    mapping = {"path": "res://assets/imported/wildlife_motion/bison_animated.glb",
        "mode": "ground", "yaw": np.pi, "length_axis": "z",
        "clip_manifest": "res://assets/imported/wildlife_motion/bison_animated.manifest.json",
        "art_status": "operator_supplied_reduced_estimated_rig", "geometry_rights": "unknown"}
    return entry, mapping


def _pbr_image_hashes(path: Path) -> dict:
    """Hash each embedded material image by its channel role."""
    document, blob = read_glb(path)
    hashes = {}
    for index, material in enumerate(document.get("materials", [])):
        channels = dict(material.get("pbrMetallicRoughness", {}))
        channels.update({key: value for key, value in material.items() if key.endswith("Texture")})
        for channel, texture in channels.items():
            if not channel.endswith("Texture"):
                continue
            image = document["images"][document["textures"][texture["index"]]["source"]]
            view = document["bufferViews"][image["bufferView"]]
            start = view.get("byteOffset", 0)
            hashes[f"material_{index}.{channel}"] = hashlib.sha256(blob[start:start+view["byteLength"]]).hexdigest()
    return hashes


def textured_mammal_derivative(kind: str, profile_name: str, runtime_source: Path,
                              original_source: Path, forward: str, up: str,
                              world_root: Path, texture_limit: int = 2048, *,
                              review_assets=None, allow_unreviewed_development=False) -> tuple:
    """Bind supplied PBR geometry to an explicitly oriented species rig."""
    if not kind or any(character not in "abcdefghijklmnopqrstuvwxyz_0123456789" for character in kind):
        raise ValueError("Mammal kind must be a lowercase identifier")
    if forward in ("x+", "x-", "y+", "y-", "z+", "z-"):
        forward = forward[1]+forward[0]
    if up in ("x+", "x-", "y+", "y-", "z+", "z-"):
        up = up[1]+up[0]
    original, reduced = load_asset(original_source), load_asset(runtime_source)
    if len(reduced.faces) > 30000:
        raise ValueError("Runtime mammal exceeds the authored 30000-triangle budget")
    original_images = _pbr_image_hashes(original_source)
    if len(original_images) < 3 or original_images != _pbr_image_hashes(runtime_source):
        raise ValueError("Reduced mammal must preserve all original PBR channel bytes")
    target = world_root / "assets/imported/wildlife_motion" / (kind+"_animated.glb")
    manifest, weights = _animate(reduced, profile_name, target, texture_limit=texture_limit,
        forward=forward, up=up, align_heading=True,
        review_assets=review_assets, allow_unreviewed_development=allow_unreviewed_development)
    distances = cKDTree(reduced.vertices).query(original.vertices, workers=2)[0]
    reverse = cKDTree(original.vertices).query(reduced.vertices, workers=2)[0]
    geometry = {"original_vertices": len(original.vertices), "original_triangles": len(original.faces),
        "runtime_vertices": len(reduced.vertices), "runtime_triangles": len(reduced.faces),
        "original_bounds": [original.vertices.min(0).tolist(), original.vertices.max(0).tolist()],
        "runtime_bounds": [reduced.vertices.min(0).tolist(), reduced.vertices.max(0).tolist()],
        "vertex_distance_source_to_runtime": {"p95_asset_units": float(np.quantile(distances, .95)), "maximum_asset_units": float(distances.max())},
        "vertex_distance_runtime_to_source": {"p95_asset_units": float(np.quantile(reverse, .95)), "maximum_asset_units": float(reverse.max())},
        "distance_metric": "nearest_vertex_distances; triangle_surface_Hausdorff_unavailable",
        "status": "derived_not_field_validated", "scientific_acceptance": "not_yet_accepted"}
    entry = {"id": kind, "path": target.relative_to(world_root).as_posix(), "sha256": _digest(target),
        "source_sha256": _digest(original_source), "runtime_source_sha256": _digest(runtime_source),
        "source_file": original_source.name, "status": "operator_supplied", "geometry_rights": "unknown",
        "source_texture_sha256": original_images, "texture_resizing": manifest["texture_resizing"],
        "textures": "source_PBR_documented_resolution_reduction", "texture_resolution_evidence_class": "authored",
        "texture_content": "source_color_normal_ORM", "rig_status": manifest["rig_review_status"],
        "tangent_frame_repair": manifest["metadata"].get("tangent_frame_repair"),
        "scientific_acceptance": "not_yet_accepted", "source_axes": {"forward": forward, "up": up},
        "audit": audit_asset(target), "weights": weights, "geometry_reduction": geometry}
    mapping = {"path": "res://"+entry["path"], "mode": "ground", "yaw": np.pi, "length_axis": "z",
        "clip_manifest": "res://"+target.with_suffix(".manifest.json").relative_to(world_root).as_posix(),
        "art_status": "operator_supplied_textured_estimated_rig", "geometry_rights": "unknown"}
    return entry, mapping


def build(assets_root: Path, badger_source: Path, world_root: Path,
          bison_runtime_source: Path | None = None, bison_original: Path | None = None,
          badger_original: Path | None = None, badger_texture_limit: int = 2048,
          textured_mammals: list | None = None, *, review_manifest: Path | None = None,
          allow_unreviewed_development: bool = False, geometry_owner: str = "KJR") -> dict:
    """Import supplied assets and add explicit wolf and deer shape proxies."""
    reviews = load_review_manifest(review_manifest)
    if not reviews and not allow_unreviewed_development:
        raise ValueError("Production build requires --review-manifest; estimated rigs require --allow-unreviewed-development")
    policy = {"review_assets": reviews, "allow_unreviewed_development": allow_unreviewed_development}
    target_root = world_root / "assets/imported/wildlife_motion"
    target_root.mkdir(parents=True, exist_ok=True)
    entries, source_files, mappings = [], [], {}
    for source in sorted(assets_root.rglob("*")):
        if not source.is_file() or source.suffix not in (".glb", ".json"):
            continue
        relative = source.relative_to(assets_root)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source_files.append({"path": relative.as_posix(), "sha256": _digest(source),
                             "bytes": source.stat().st_size})
        if source.suffix == ".glb":
            synthetic = relative.parts[0] == "birds"
            document, _ = read_glb(source)
            source_rig = document.get("extras", {}).get("wildlife_motion", {}).get("rig", {})
            review = reviews.get(source_rig.get("metadata", {}).get("source_sha256"), {})
            if not synthetic and not allow_unreviewed_development:
                check_preanimated_review(document, review)
            with tempfile.TemporaryDirectory(prefix=".import-stage-", dir=target.parent) as directory:
                staged = Path(directory)/target.name
                changes = normalize_roots(source, staged)
                audit = audit_asset(staged)
                quality = _quality_gate(staged, review, allow_unreviewed_development) if not synthetic else {"production_eligibility": "excluded_synthetic_fixture"}
                _write(staged.with_suffix(".quality.json"), quality)
                os.replace(staged, target)
                os.replace(staged.with_suffix(".quality.json"), target.with_suffix(".quality.json"))
            entries.append({"id": source.stem, "path": target.relative_to(world_root).as_posix(),
                "status": "authored" if synthetic else "operator_supplied",
                "geometry_rights": "MIT" if synthetic else "unknown",
                "rig_status": "synthetic_fixture" if synthetic else source_rig.get("metadata", {}).get("review_status", "unavailable"),
                "physical_dimensions": "synthetic_fixture_meters" if synthetic else "unverified_asset_units",
                "scientific_acceptance": "not_yet_accepted", "audit": audit, "production_quality": quality["production_eligibility"], **changes})
        else:
            shutil.copy2(source, target)
    for kind in ("bobcat", "grizzly"):
        filename = kind+"_animated_2k.glb"
        mappings[kind] = {"path": "res://assets/imported/wildlife_motion/"+filename,
            "mode": "ground", "yaw": 3.141592653589793, "length_axis": "z",
            "clip_manifest": "res://assets/imported/wildlife_motion/"+kind+"_animated_2k.manifest.json",
            "art_status": "operator_supplied_estimated_rig", "geometry_rights": "unknown"}
    for kind, profile_name in [("wolf", "gray_wolf"), ("deer", "mule_deer")]:
        target = target_root / (kind+"_authored.glb")
        manifest, weights = _animate(mammal_shape(kind), profile_name, target, **policy)
        entries.append({"id": kind+"_authored", "path": target.relative_to(world_root).as_posix(),
            "sha256": _digest(target), "status": "authored", "geometry_rights": "Apache-2.0",
            "rig_status": manifest["rig_review_status"], "scientific_acceptance": "not_yet_accepted",
            "audit": audit_asset(target), "weights": weights})
        mappings[kind] = {"path": "res://assets/imported/wildlife_motion/"+target.name,
            "mode": "ground", "yaw": 3.141592653589793, "length_axis": "z",
            "clip_manifest": "res://assets/imported/wildlife_motion/"+target.with_suffix(".manifest.json").name,
            "art_status": "authored_species_shape_proxy", "geometry_rights": "Apache-2.0"}
    badger = target_root / "badger_animated.glb"
    textured_badger = badger_source.suffix.lower() == ".glb"
    badger_asset = load_asset(badger_source) if textured_badger else read_binary_stl(badger_source)
    if len(badger_asset.faces) > 30000:
        raise ValueError("Reduce the badger source to the authored 30000-triangle budget")
    original_sha = _digest(badger_original) if badger_original is not None else _digest(badger_source)
    original_images = {}
    if badger_original is not None:
        for source in [badger_original, badger_source]:
            doc, blob = read_glb(source)
            images = {}
            for image in doc.get("images", []):
                view = doc["bufferViews"][image["bufferView"]]
                start = view.get("byteOffset", 0)
                images[image.get("name", "")] = hashlib.sha256(blob[start:start+view["byteLength"]]).hexdigest()
            if not original_images:
                original_images = images
            elif original_images != images:
                raise ValueError("Badger geometry reduction changes original texture bytes")
    manifest, weights = _animate(badger_asset, "american_badger", badger,
        texture_limit=badger_texture_limit if textured_badger else None,
        forward="+x", up="+y" if textured_badger else "+z", align_heading=True, **policy)
    entries.append({"id": "badger", "path": badger.relative_to(world_root).as_posix(),
        "source_sha256": original_sha, "runtime_source_sha256": _digest(badger_source), "sha256": _digest(badger),
        "status": "operator_supplied", "geometry_rights": "unknown",
        "textures": "source_PBR_documented_resolution_reduction" if textured_badger else "explicit_untextured_STL",
        "source_texture_sha256": original_images, "texture_resizing": manifest.get("texture_resizing", []),
        "texture_resolution_evidence_class": "authored", "texture_content": "source_color_normal_ORM",
        "rig_status": manifest["rig_review_status"], "scientific_acceptance": "not_yet_accepted",
        "audit": audit_asset(badger), "weights": weights})
    mappings["badger"] = {"path": "res://assets/imported/wildlife_motion/badger_animated.glb",
        "mode": "ground", "yaw": 3.141592653589793, "length_axis": "z",
        "clip_manifest": "res://assets/imported/wildlife_motion/badger_animated.manifest.json",
        "art_status": "operator_supplied_textured_estimated_rig" if textured_badger else "operator_supplied_untextured_estimated_rig", "geometry_rights": "unknown"}
    mappings["gray_wolf"] = mappings["wolf"]
    mappings["mule_deer"] = mappings["deer"]
    mappings["american_badger"] = mappings["badger"]
    if (bison_runtime_source is None) != (bison_original is None):
        raise ValueError("Both bison source paths are required")
    if bison_runtime_source is not None:
        entry, mapping = bison_derivative(bison_runtime_source, bison_original, world_root, **policy)
        entries.append(entry)
        mappings["bison"] = mapping
    for kind, profile, reduced, original, forward, up in textured_mammals or []:
        if kind in mappings:
            raise ValueError("Duplicate mammal kind: "+kind)
        entry, mapping = textured_mammal_derivative(kind, profile, Path(reduced), Path(original),
            forward, up, world_root, **policy)
        entries.append(entry)
        mappings[kind] = mapping
    if "canada_lynx" in mappings:
        mappings["canadian_lynx"] = mappings["canada_lynx"]
    result = {"schema": "yellowstone.wildlife_motion_assets.v1", "status": "authored",
        "scientific_acceptance": "not_yet_accepted", "quantitative_uncertainty": "unknown",
        "software_license": "MIT", "integration_license": "Apache-2.0",
        "source_files": source_files, "assets": entries, "wildlife_species_asset_map": mappings,
        "limitations": ["Automatic joint centers lack anatomical certification.",
            "Geometry ownership does not establish biological or visual acceptance.",
            "Bird fixtures demonstrate motion and are excluded from wildlife species mapping.",
            "Scene body dimensions are authored display values."]}
    for record in result["assets"] + list(result["wildlife_species_asset_map"].values()):
        record["geometry_owner"] = geometry_owner
        record["geometry_permission"] = "owner_confirmed"
        record["redistribution_permission"] = "owner_authorized_project_release"
        if record.get("geometry_rights") == "unknown":
            record["geometry_rights"] = "owner_confirmed"
    _write(world_root / "data/wildlife_motion_assets.json", result)
    return result


def main(argv=None):
    """Build portable assets from explicitly supplied source directories."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--badger-source", type=Path, required=True,
                        help="Unskinned textured GLB or explicitly selected binary STL")
    parser.add_argument("--badger-original", type=Path,
                        help="Preserved original GLB for reduced-geometry texture verification")
    parser.add_argument("--badger-texture-limit", type=int, default=2048)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--review-manifest", type=Path, help="Source-bound rigs, resolved controls and predeclared deformation budgets")
    parser.add_argument("--allow-unreviewed-development", action="store_true", help="Label estimated rigs and failed quality budgets as unaccepted development")
    parser.add_argument("--geometry-owner", default="KJR", help="Confirmed owner of this project's supplied animal meshes")
    parser.add_argument("--bison-runtime-source", type=Path)
    parser.add_argument("--bison-original", type=Path)
    parser.add_argument("--textured-mammal", action="append", nargs=6,
        metavar=("KIND", "PROFILE", "REDUCED", "ORIGINAL", "FORWARD", "UP"),
        help="Explicit species source pair; axes accept x-/y+ or signed forms")
    args = parser.parse_args(argv)
    result = build(args.assets_root, args.badger_source, args.world,
                   args.bison_runtime_source, args.bison_original,
                   args.badger_original, args.badger_texture_limit, args.textured_mammal,
                   review_manifest=args.review_manifest, allow_unreviewed_development=args.allow_unreviewed_development,
                   geometry_owner=args.geometry_owner)
    print(json.dumps({"assets": len(result["assets"]),
                      "mapped_kinds": list(result["wildlife_species_asset_map"])}))


if __name__ == "__main__":
    main()
