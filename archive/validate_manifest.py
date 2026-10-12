#!/usr/bin/env python3
"""Validate proposed shared-world manifests. Reads data; never runs world code.

Requires jsonschema>=4.25,<5. JSON output distinguishes structural, semantic,
byte-integrity and baseline-preservation checks from unperformed engine/science QA.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "0.1.0"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "world_manifest.schema.json"
INTERFACES = {
    "anchors": "anchor", "terrain": "terrain", "water": "water", "geology": "geology",
    "habitats": "habitat", "species": "species", "roads": "road", "placements": "placement",
    "overrides": "override", "chunks": "chunk", "runtime_states": "runtime_state", "materials": "material",
}


class StrictJSONError(ValueError):
    pass


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise StrictJSONError(f"Duplicate object key: {key!r}")
        result[key] = value
    return result


def _float(token):
    value = float(token)
    if not math.isfinite(value):
        raise StrictJSONError(f"Nonfinite/overflow number: {token}")
    return value


def _constant(token):
    raise StrictJSONError(f"Nonstandard JSON constant: {token}")


def strict_loads(text):
    return json.loads(text, object_pairs_hook=_pairs, parse_float=_float, parse_constant=_constant)


def load_json(path):
    return strict_loads(Path(path).read_text(encoding="utf-8"))


def pointer(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def key(reference):
    return (reference["world_id"], reference["namespace"], reference["id"])


def label(reference):
    return "/".join(key(reference))


def record_hash(record):
    """shared_record_v1: this validator's sorted compact UTF-8 JSON, not IR/JCS."""
    data = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def issue(stage, code, path, message, witness=None):
    out = {"stage": stage, "code": code, "path": path, "message": message}
    if witness is not None:
        out["witness"] = witness
    return out


def short(value):
    if isinstance(value, (str, int, float, bool, type(None))):
        return value if not isinstance(value, str) or len(value) < 500 else value[:500] + "…"
    if isinstance(value, list):
        return {"type": "array", "length": len(value)}
    if isinstance(value, dict):
        return {"type": "object", "keys": list(value)[:30]}
    return {"type": type(value).__name__}


def non_json(value, path=""):
    """Also check programmatic input; Python's bool is not a finite numeric ID."""
    found = []
    if isinstance(value, float) and not math.isfinite(value):
        found.append(issue("parse", "NONFINITE_NUMBER", path, "Nonfinite numbers are prohibited."))
    elif isinstance(value, dict):
        for name, item in value.items():
            if not isinstance(name, str):
                found.append(issue("parse", "NONSTRING_KEY", path, "JSON object keys must be strings."))
            found.extend(non_json(item, path + pointer([name])))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.extend(non_json(item, path + f"/{i}"))
    elif not isinstance(value, (str, int, float, bool, type(None))):
        found.append(issue("parse", "NONJSON_VALUE", path, "Value is not a JSON type.", short(value)))
    return found


def structural(document, schema, definition=None):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise RuntimeError("Install requirements-validation.txt; jsonschema is required, not silently skipped.") from exc
    Draft202012Validator.check_schema(schema)
    selected = schema if definition is None else {
        "$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"
    }
    validator = Draft202012Validator(selected, format_checker=FormatChecker())
    result = []
    for error in sorted(validator.iter_errors(document), key=lambda e: pointer(e.absolute_path)):
        result.append(issue("structure", "SCHEMA_VIOLATION", pointer(error.absolute_path), error.message,
            {"schema_path": pointer(error.absolute_schema_path), "keyword": error.validator, "value": short(error.instance)}))
    return result


def base_records(document):
    groups = [("coordinate_frames", "coordinate_frame"), ("artifacts", "artifact"),
              ("native_bindings", "native_binding"), ("models", "model")]
    for group, kind in groups:
        for i, record in enumerate(document[group]):
            yield f"/{group}/{i}", kind, record
    for group, kind in (("sources", "source"), ("activities", "activity"), ("licenses", "license")):
        for i, record in enumerate(document["provenance"][group]):
            yield f"/provenance/{group}/{i}", kind, record
    for group, kind in {**INTERFACES, "bindings": "interface_binding"}.items():
        for i, record in enumerate(document["interfaces"].get(group, [])):
            yield f"/interfaces/{group}/{i}", kind, record


def file_path(artifact, root):
    raw = artifact.get("local_path")
    if raw is None and artifact.get("uri_kind") == "package_relative":
        raw = artifact.get("uri")
    if raw is None:
        raise ValueError("No local package path. Supply local_path or a package_relative uri; remote/native URIs are not fetched.")
    candidate = (root / raw).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes the explicitly selected artifact root.")
    if not candidate.is_file():
        raise ValueError("Artifact is not an accessible regular file.")
    return candidate


def json_at_pointer(value, path):
    if path == "":
        return value
    if not path.startswith("/"):
        raise ValueError("A JSON Pointer must be empty or start with '/'.")
    for token in path[1:].split("/"):
        if re.search(r"~(?:[^01]|$)", token):
            raise ValueError("A JSON Pointer token contains an invalid '~' escape.")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("A JSON Pointer array index must be 0 or a positive decimal integer without leading zeros.")
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise ValueError("A JSON Pointer cannot traverse a scalar value.")
    return value


def references(value, path=""):
    """Only contract reference fields; do not reinterpret native extension data."""
    if not isinstance(value, dict):
        return
    for name, item in value.items():
        here = path + pointer([name])
        if name in ("ref", "extensions", "parameters", "changes", "initial_state", "color_space", "channel_packing"):
            continue
        if name.endswith("_ref") and isinstance(item, dict):
            yield here, name, item
        elif name.endswith("_refs") or name == "dependencies":
            if isinstance(item, list):
                for index, reference in enumerate(item):
                    yield f"{here}/{index}", name, reference
        elif isinstance(item, dict):
            yield from references(item, here)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                if isinstance(child, dict):
                    yield from references(child, f"{here}/{index}")


def expected_kind(field):
    if field.endswith("artifact_ref") or field.endswith("artifact_refs") or field in ("identity_catalog_ref",):
        return {"artifact"}
    mapping = {
        "frame_ref": {"coordinate_frame"}, "parent_frame_ref": {"coordinate_frame"},
        "source_frame_ref": {"coordinate_frame"}, "frame_refs": {"coordinate_frame"},
        "native_binding_ref": {"native_binding"}, "provenance_refs": {"source", "activity"},
        "license_refs": {"license"}, "activity_ref": {"activity"}, "resampling_activity_ref": {"activity"}, "model_ref": {"model"},
        "species_ref": {"species"}, "species_refs": {"species"}, "habitat_refs": {"habitat"},
        "material_refs": {"material"}, "surface_material_ref": {"material"}, "state_ref": {"runtime_state"},
        "terrain_refs": {"terrain"}, "placement_refs": {"placement"}, "road_refs": {"road"},
        "water_refs": {"water"}, "water_ref": {"water"}, "dependencies": {"chunk"}, "crossing_refs": {"road", "water"},
    }
    return mapping.get(field)


def validate_manifest(document, *, schema=None, artifact_root=None, check_files=False, baseline=None,
                      baseline_artifact_root=None, _records_out=None):
    schema = schema or load_json(SCHEMA_PATH)
    root = Path(artifact_root or ".").resolve()
    errors = non_json(document)
    warnings = []
    if not errors:
        errors.extend(structural(document, schema))
    summary = {"record_count": 0, "verified_artifact_claims": 0, "artifacts_rechecked": 0,
               "sidecar_records_checked": 0, "sidecar_bindings_unopened": 0,
               "baseline_requested": baseline is not None, "baseline_checked": False,
               "runtime_executed": False, "scientific_models_executed": False}
    if errors:
        return {"valid": False, "contract_version": CONTRACT_VERSION, "errors": errors, "warnings": warnings, "summary": summary}

    records = list(base_records(document))
    initial_index = {key(r["ref"]): (path, kind, r) for path, kind, r in records}
    # Sidecars are parsed as data only. Native opaque bindings remain archival references.
    for path, kind, binding in list(records):
        if kind != "interface_binding":
            continue
        if INTERFACES[binding["interface"]] != binding["record_definition"]:
            errors.append(issue("semantics", "BINDING_DEFINITION_MISMATCH", path,
                                "Interface and record definition disagree."))
            continue
        binding_artifact = initial_index.get(key(binding["artifact_ref"]))
        if document["profile"] == "streamable" and binding_artifact and binding_artifact[1] == "artifact" and binding_artifact[2]["availability"] != "verified_bytes":
            errors.append(issue("semantics", "STREAMABLE_BINDING_UNVERIFIED", path, "Streamable external record sets must bind immutable, verified bytes."))
        if binding["encoding"] == "native_unparsed":
            summary["sidecar_bindings_unopened"] += 1
            warnings.append(issue("semantics", "NATIVE_BINDING_UNPARSED", path,
                                  "Native payload preserved; its records are not asserted to meet the shared record schema."))
            if document["profile"] == "streamable":
                errors.append(issue("semantics", "STREAMABLE_OPAQUE_BINDING", path,
                                    "Streamable profile requires inspectable shared record sidecars."))
            continue
        if not check_files:
            summary["sidecar_bindings_unopened"] += 1
            warnings.append(issue("bytes", "SIDECAR_NOT_OPENED", path, "Use --check-files to validate external record content."))
            continue
        target = initial_index.get(key(binding["artifact_ref"]))
        if not target or target[1] != "artifact":
            continue  # normal referential pass emits a precise dangling/type witness
        try:
            payload = json_at_pointer(load_json(file_path(target[2], root)), binding["records_json_pointer"])
            if binding["encoding"] == "json_array" and not isinstance(payload, list):
                raise ValueError("Selected sidecar value must be an array.")
            if binding["encoding"] == "json_object_values" and not isinstance(payload, dict):
                raise ValueError("Selected sidecar value must be an object of records.")
            entries = list(enumerate(payload)) if isinstance(payload, list) else list(payload.items())
            for name, record in entries:
                here = path + "/payload" + pointer([name])
                found = non_json(record) or structural(record, schema, binding["record_definition"])
                for problem in found:
                    problem["path"] = here + problem["path"]
                errors.extend(found)
                if not found:
                    records.append((here, binding["record_definition"], record))
                    summary["sidecar_records_checked"] += 1
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            errors.append(issue("bytes", "SIDECAR_READ_FAILED", path, str(exc)))

    registry = {}
    for path, kind, record in records:
        ident = key(record["ref"])
        if ident in registry:
            errors.append(issue("semantics", "DUPLICATE_ID", path + "/ref", "Composite identity is already registered.",
                                {"reference": record["ref"], "first_path": registry[ident][0]}))
        else:
            registry[ident] = (path, kind, record)
    summary["record_count"] = len(records)
    if _records_out is not None:
        _records_out.extend(records)

    def resolve(reference, want=None):
        target = registry.get(key(reference)) if reference else None
        return target[2] if target and (want is None or target[1] == want) else None

    for path, _, record in records:
        for location, field, reference in references(record, path):
            target = registry.get(key(reference))
            if not target:
                errors.append(issue("semantics", "DANGLING_REFERENCE", location, "Reference has no record in this manifest or inspected sidecars.", reference))
            elif expected_kind(field) and target[1] not in expected_kind(field):
                errors.append(issue("semantics", "REFERENCE_TYPE", location, "Reference points to the wrong record interface.",
                                    {"reference": reference, "actual": target[1], "expected": sorted(expected_kind(field))}))
    for location, field, reference in references(document["runtime"], "/runtime"):
        if not resolve(reference, "coordinate_frame"):
            errors.append(issue("semantics", "DANGLING_RUNTIME_FRAME", location, "Runtime frame must resolve to a coordinate frame.", reference))

    def require_role(record, field, expected, path, code="ARTIFACT_ROLE"):
        reference = record.get(field)
        if not reference:
            return
        artifact = resolve(reference, "artifact")
        if artifact and artifact["role"] not in expected:
            errors.append(issue("semantics", code, path + "/" + field, "Artifact has an incompatible scientific/rendering role.",
                                {"reference": reference, "actual_role": artifact["role"], "expected_roles": sorted(expected)}))

    def bounds_valid(bounds, path):
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            errors.append(issue("semantics", "INVALID_BOUNDS", path, "Bounds must have strictly positive X and Z extents.", bounds))

    def affine_valid(affine, path):
        if affine is None:
            return
        try:
            determinant = affine[1] * affine[5] - affine[2] * affine[4]
            if not math.isfinite(determinant):
                raise OverflowError
        except OverflowError:
            errors.append(issue("semantics", "AFFINE_NUMERIC_RANGE", path, "Affine determinant exceeds finite validator arithmetic; choose a numerically usable coordinate frame."))
            return
        if abs(determinant) < 1e-20:
            errors.append(issue("semantics", "SINGULAR_AFFINE", path, "Raster affine transform is singular or below this validator's 1e-20 determinant threshold."))

    for path, kind, record in records:
        if kind == "artifact":
            if record["availability"] == "verified_bytes":
                summary["verified_artifact_claims"] += 1
                if check_files:
                    try:
                        p = file_path(record, root)
                        digest = hashlib.sha256()
                        length = 0
                        with p.open("rb") as source:
                            for block in iter(lambda: source.read(1024 * 1024), b""):
                                digest.update(block)
                                length += len(block)
                        if length != record["byte_length"] or digest.hexdigest() != record["sha256"]:
                            errors.append(issue("bytes", "ARTIFACT_INTEGRITY", path, "Artifact bytes do not match the immutable record.",
                                {"expected_sha256": record["sha256"], "actual_sha256": digest.hexdigest(),
                                 "expected_bytes": record["byte_length"], "actual_bytes": length}))
                        else:
                            summary["artifacts_rechecked"] += 1
                    except (ValueError, OSError) as exc:
                        errors.append(issue("bytes", "ARTIFACT_UNAVAILABLE", path, str(exc), {"reference": record["ref"]}))
        elif kind == "source" and record["availability"] == "verified_bytes":
            artifact = resolve(record.get("artifact_ref"), "artifact")
            if not artifact or artifact["availability"] != "verified_bytes":
                errors.append(issue("semantics", "SOURCE_BYTES_UNBOUND", path, "Verified source bytes require a verified artifact binding."))
        elif kind == "native_binding":
            fmt, version = record["format"], record["format_version"]
            if version is None and document["profile"] == "streamable":
                errors.append(issue("semantics", "NATIVE_VERSION_UNKNOWN", path + "/format_version", "Streamable bindings need a known native format version."))
            if version is not None and record.get("format_version_status") == "unknown":
                errors.append(issue("semantics", "NATIVE_VERSION_STATUS", path + "/format_version_status", "A supplied format version cannot simultaneously have unknown status."))
            if version is not None and fmt in ("groundwork_recipe", "groundwork_material") and (type(version) is not int or version != 1):
                errors.append(issue("semantics", "NATIVE_VERSION", path + "/format_version", "Recovered Groundwork recipe/material schema is integer 1, independently of compiler 0.1.0."))
            if fmt == "open_world_artifact_ir":
                if version is not None and version != "0.2.0":
                    errors.append(issue("semantics", "NATIVE_VERSION", path + "/format_version", "This adapter only describes recovered IR 0.2.0."))
                if version == "0.2.0" and (record["position_space"] != "authored_game" or record["scale_application"] != "already_applied"):
                    errors.append(issue("semantics", "IR_DOUBLE_COMPRESSION", path, "Recovered IR entity transforms are already game-space; preserve their positions without recompression."))
            snapshot = record.get("source_snapshot_sha256")
            artifact = resolve(record["artifact_ref"], "artifact")
            if record["identity_mode"] == "enrolled_sidecar":
                require_role(record, "identity_catalog_ref", {"placement_catalog"}, path)
            if document["profile"] == "streamable" and artifact and artifact["availability"] != "verified_bytes":
                errors.append(issue("semantics", "STREAMABLE_NATIVE_UNVERIFIED", path, "Streamable native adapters must bind immutable, verified source bytes."))
            if snapshot and artifact and artifact.get("sha256") and snapshot != artifact["sha256"]:
                errors.append(issue("semantics", "SNAPSHOT_HASH_MISMATCH", path, "Binding source snapshot must match its source artifact hash."))
        elif kind == "coordinate_frame":
            if record["geography_mode"] == "georeferenced" and record["georeference"]["operation"]["method"] == "affine_approximation":
                errors.append(issue("semantics", "GEOGRAPHIC_MODE_OVERCLAIM", path, "An approximate geographic transform must declare approximate_geographic mode."))
            if record["position_space"] == "runtime_local" and record["geography_mode"] == "unknown":
                warnings.append(issue("semantics", "RUNTIME_FRAME_UNKNOWN", path, "Runtime coordinate mapping remains unresolved."))
        elif kind == "model" and record["space"] == "physical":
            for i, reference in enumerate(record["frame_refs"]):
                frame = resolve(reference, "coordinate_frame")
                if frame and (frame["geography_mode"] in ("representative", "unknown") or frame["position_space"] != "source_scientific"):
                    errors.append(issue("semantics", "MODEL_SPACE_MISMATCH", path + f"/frame_refs/{i}",
                                        "Physical geographic modeling requires an explicit scientific frame; compressed/unknown authored geometry is not physical distance.", reference))
        elif kind == "terrain":
            require_role(record, "elevation_artifact_ref", {"terrain_elevation"}, path, "MATERIAL_HEIGHT_IS_NOT_TERRAIN")
            require_role(record, "geometry_artifact_ref", {"terrain_mesh"}, path)
            require_role(record, "collision_artifact_ref", {"collision_mesh"}, path)
            require_role(record, "validity_mask_artifact_ref", {"height_validity_mask"}, path)
            if record.get("nodata_policy") == "mask" and not record.get("validity_mask_artifact_ref"):
                errors.append(issue("semantics", "NODATA_MASK_REQUIRED", path, "Mask policy requires a validity mask artifact."))
            if record.get("nodata_policy") == "sentinel" and record.get("nodata_value") is None:
                errors.append(issue("semantics", "NODATA_SENTINEL_REQUIRED", path, "Sentinel policy requires a finite sentinel value."))
            if record.get("grid"):
                grid = record["grid"]
                bounds_valid(grid["bounds_xz"], path + "/grid/bounds_xz")
                expected = [n + 1 for n in grid["cell_count"]]
                if grid["sample_count"] != expected:
                    errors.append(issue("semantics", "GRID_SAMPLE_COUNT", path + "/grid/sample_count", "A heightfield with N cells needs N+1 samples on each axis.",
                                        {"actual": grid["sample_count"], "expected": expected}))
                frame = resolve(record["frame_ref"], "coordinate_frame")
                if frame and frame["meters_per_unit"] is not None:
                    b = grid["bounds_xz"]
                    try:
                        actual = [(b[2] - b[0]) * frame["meters_per_unit"][0], (b[3] - b[1]) * frame["meters_per_unit"][2]]
                        expected_span = [grid["cell_count"][i] * grid["spacing_m"][i] for i in range(2)]
                        if any(not math.isfinite(v) for v in actual + expected_span):
                            raise OverflowError
                        if any(not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-7) for a, b in zip(actual, expected_span)):
                            errors.append(issue("semantics", "GRID_BOUNDS_SPACING", path + "/grid", "Cell spacing and frame-scaled bounds disagree.", {"actual_span_m": actual, "expected_span_m": expected_span}))
                    except OverflowError:
                        errors.append(issue("semantics", "GRID_NUMERIC_RANGE", path + "/grid", "Derived grid spans exceed finite validator arithmetic; choose usable units and bounds."))
                else:
                    errors.append(issue("semantics", "GRID_UNITS_UNKNOWN", path + "/grid", "A numerical grid needs known frame meters_per_unit."))
                affine_valid(grid.get("affine_gdal"), path + "/grid/affine_gdal")
            raster = record.get("source_raster")
            if raster:
                require_role(raster, "artifact_ref", {"terrain_elevation", "model_input"}, path + "/source_raster")
                require_role(raster, "mask_artifact_ref", {"height_validity_mask"}, path + "/source_raster")
                affine_valid(raster.get("affine_gdal"), path + "/source_raster/affine_gdal")
        elif kind == "water":
            require_role(record, "geometry_artifact_ref", {"water_geometry"}, path)
        elif kind == "road":
            require_role(record, "geometry_artifact_ref", {"road_geometry"}, path)
            if document["profile"] != "inventory" and record["polyline"] is None and record["geometry_artifact_ref"] is None and not record.get("native_binding_ref"):
                errors.append(issue("semantics", "ROAD_GEOMETRY_UNBOUND", path, "Authored road requires geometry or an explicit native binding."))
        elif kind == "habitat":
            elevations = record.get("ecological_reference_elevation_range_m")
            if elevations and elevations[0] > elevations[1]:
                errors.append(issue("semantics", "HABITAT_ELEVATION_RANGE", path, "Ecological reference range is inverted; it remains separate from a geometric vertical datum."))
        elif kind == "species" and record["occurrence_evidence"] == "observed":
            if not record["evidence_artifact_refs"]:
                errors.append(issue("semantics", "OBSERVATION_WITHOUT_EVIDENCE", path, "An observed occurrence claim must cite an evidence artifact."))
        elif kind == "placement":
            frame = resolve(record["frame_ref"], "coordinate_frame")
            binding = resolve(record.get("native_binding_ref"), "native_binding")
            if record["status"] in ("accepted", "frozen_incumbent") and document["profile"] != "inventory" and record["position"] is None:
                errors.append(issue("semantics", "ACCEPTED_POSITION_UNKNOWN", path, "A retained authored placement needs its actual position; do not invent [0,0,0]."))
            if frame and frame["position_space"] != "unknown" and record["position_space"] != frame["position_space"]:
                errors.append(issue("semantics", "POSITION_FRAME_SPACE", path, "Placement position_space disagrees with the referenced frame."))
            if record["position_space"] == "authored_game" and record["scale_application"] == "source_to_view_pending":
                errors.append(issue("semantics", "DOUBLE_COMPRESSION", path, "Authored-game positions must not be treated as untransformed scientific source coordinates."))
            if binding and binding["scale_application"] == "already_applied" and record["scale_application"] == "source_to_view_pending":
                errors.append(issue("semantics", "DOUBLE_COMPRESSION", path, "Native binding says scaling has already been applied."))
        elif kind == "material":
            require_role(record, "descriptor_artifact_ref", {"material_descriptor"}, path)
            require_role(record, "height_master_artifact_ref", {"material_height_master"}, path)
            require_role(record, "height_preview_artifact_ref", {"material_height_preview"}, path)
            require_role(record, "blend_height_artifact_ref", {"material_blend_height"}, path)
        elif kind == "chunk":
            bounds_valid(record["bounds_xz"], path + "/bounds_xz")
            for field, role in (("payload_artifact_ref", "chunk_payload"), ("collision_artifact_ref", "collision_mesh"), ("validation_artifact_ref", "validation_report")):
                require_role(record, field, {role}, path)
            if document["profile"] == "streamable":
                if record["readiness"] not in ("validated", "runtime_verified"):
                    errors.append(issue("semantics", "CHUNK_NOT_READY", path, "Streamable chunks require at least validated readiness."))
                if not record["source_artifact_refs"]:
                    errors.append(issue("semantics", "CHUNK_SOURCE_REQUIRED", path, "Streamable chunks require immutable source artifact references."))
                for field in ("payload_artifact_ref", "collision_artifact_ref", "validation_artifact_ref"):
                    artifact = resolve(record[field], "artifact")
                    if not artifact or artifact["availability"] != "verified_bytes":
                        errors.append(issue("semantics", "CHUNK_ARTIFACT_NOT_VERIFIED", path + "/" + field, "Streamable payload/collision/validation evidence must bind verified bytes."))
                for reference in record["source_artifact_refs"]:
                    artifact = resolve(reference, "artifact")
                    if artifact and artifact["availability"] != "verified_bytes":
                        errors.append(issue("semantics", "CHUNK_SOURCE_NOT_VERIFIED", path, "Streamable source bytes must be verified.", reference))
                frame = resolve(record["frame_ref"], "coordinate_frame")
                if frame and (frame["geography_mode"] == "unknown" or frame["meters_per_unit"] is None):
                    errors.append(issue("semantics", "CHUNK_FRAME_UNKNOWN", path, "Streamable chunk geometry requires a resolved frame and units."))
                for field in ("terrain_refs", "placement_refs", "road_refs", "water_refs"):
                    for reference in record[field]:
                        feature = resolve(reference)
                        if feature and feature.get("frame_ref") != record["frame_ref"]:
                            errors.append(issue("semantics", "CHUNK_FEATURE_FRAME", path + "/" + field, "A streamable chunk must reference feature views in its own frame; keep source-frame features separate and declare the conversion activity.", reference))
                if record["readiness"] == "runtime_verified" and not document["runtime"].get("verified_engine"):
                    errors.append(issue("semantics", "RUNTIME_EVIDENCE_ENGINE", path, "A runtime-verified chunk claim requires the engine version actually used for that verification."))
        elif kind == "override":
            target = resolve(record["target_ref"])
            if record["operation"] in ("suppress", "restore") and record["changes"].get("suppressed") is not (record["operation"] == "suppress"):
                errors.append(issue("semantics", "OVERRIDE_OPERATION_DIFF", path, "Suppress/restore must explicitly set the retained placement's suppressed flag; it never deletes the accepted ID."))
            if record["status"] == "proposed" and target and target.get("locked"):
                errors.append(issue("semantics", "LOCKED_OVERRIDE", path, "An override cannot modify a locked accepted target.", record["target_ref"]))
            if record["status"] == "proposed" and record["base_world_revision"] != document["world"]["revision"]:
                errors.append(issue("semantics", "STALE_OVERRIDE_REVISION", path, "Proposed override targets a different world revision.",
                                    {"expected": record["base_world_revision"], "actual": document["world"]["revision"]}))
            if record["status"] == "proposed" and target and record["hash_domain"] == "shared_record_v1" and record["expected_target_hash"] != record_hash(target):
                errors.append(issue("semantics", "STALE_OVERRIDE_HASH", path, "Proposed override target hash is stale."))
            if record["status"] != "rejected" and record["hash_domain"] == "native_opaque":
                warnings.append(issue("semantics", "NATIVE_HASH_NOT_RECOMPUTED", path, "Native hash is retained; its native codec must validate it. It is not the shared record hash."))
            if record["status"] == "accepted" and baseline is None:
                warnings.append(issue("baseline", "ACCEPTED_OVERRIDE_WITHOUT_BASELINE", path, "Historical acceptance is recorded. Supply --baseline to verify the actual candidate diff, prior lock, revision, and target hash."))

    # DAG checks include frames as well as chunks; no recursive graph traversal is needed.
    for kind, field, code in (("chunk", "dependencies", "CHUNK_CYCLE"), ("coordinate_frame", "parent_frame_ref", "FRAME_CYCLE")):
        group = {key(r["ref"]): (p, r) for p, k, r in records if k == kind}
        edges = {ident: [key(v) for v in (r.get(field, []) if field == "dependencies" else [r[field]] if r.get(field) else []) if key(v) in group] for ident, (_, r) in group.items()}
        remaining = set(edges)
        while remaining:
            leaves = {ident for ident in remaining if not any(child in remaining for child in edges[ident])}
            if not leaves:
                start = next(iter(sorted(remaining)))
                trail, seen = [], {}
                current = start
                while current not in seen:
                    seen[current] = len(trail)
                    trail.append(current)
                    current = next(c for c in edges[current] if c in remaining)
                cycle = trail[seen[current]:] + [current]
                errors.append(issue("semantics", code, group[current][0], "Dependency cycle detected.", {"cycle": [list(x) for x in cycle]}))
                break
            remaining -= leaves

    streaming = document["runtime"].get("streaming")
    if streaming and streaming["unload_radius_chunks"] <= streaming["load_radius_chunks"]:
        errors.append(issue("semantics", "STREAM_HYSTERESIS", "/runtime/streaming", "Unload radius must exceed load radius."))
    if document["profile"] == "streamable" and not check_files:
        errors.append(issue("bytes", "STREAMABLE_FILES_REQUIRED", "/profile", "Streamable validation requires --check-files; recorded hashes alone are insufficient."))
    if summary["verified_artifact_claims"] and not check_files:
        warnings.append(issue("bytes", "ARTIFACT_BYTES_NOT_RECHECKED", "/artifacts", "Recorded hash claims were structurally checked; file bytes were not reread in this invocation."))

    if baseline is not None:
        baseline_records = []
        baseline_result = validate_manifest(baseline, schema=schema,
            artifact_root=baseline_artifact_root or root, check_files=check_files, _records_out=baseline_records)
        if not baseline_result["valid"]:
            errors.append(issue("baseline", "BASELINE_INVALID", "", "Baseline must pass validation before it can establish preservation.", baseline_result["errors"][:10]))
        elif baseline_result["summary"]["sidecar_bindings_unopened"] or summary["sidecar_bindings_unopened"]:
            errors.append(issue("baseline", "BASELINE_RECORDS_UNINSPECTED", "/interfaces/bindings", "A baseline comparison cannot claim preservation while either manifest contains uninspected external record bindings. Supply inspectable JSON sidecars and --check-files."))
        else:
            summary["baseline_checked"] = True
            summary["baseline_sidecar_records_checked"] = baseline_result["summary"]["sidecar_records_checked"]
            errors.extend(validate_baseline(document, baseline, registry, baseline_records))
    return {"valid": not errors, "contract_version": CONTRACT_VERSION, "profile": document["profile"],
            "errors": errors, "warnings": warnings, "summary": summary}


def validate_baseline(candidate, baseline, candidate_registry, originals):
    errors = []
    if any(candidate["world"][f] != baseline["world"][f] for f in ("id", "namespace")):
        errors.append(issue("baseline", "WORLD_IDENTITY_DRIFT", "/world", "Candidate and baseline must describe the same world identity."))
    if candidate["world"]["revision"] < baseline["world"]["revision"]:
        errors.append(issue("baseline", "REVISION_ROLLBACK", "/world/revision", "Candidate revision must not move backwards."))
    overrides = {}
    for p, k, r in candidate_registry.values():
        if k != "override" or r["status"] != "accepted" or r["base_world_revision"] != baseline["world"]["revision"]:
            continue
        target = key(r["target_ref"])
        if target in overrides:
            errors.append(issue("baseline", "AMBIGUOUS_OVERRIDE", p, "Multiple accepted overrides target the same object and baseline revision; supply one consolidated candidate patch.", r["target_ref"]))
        overrides[target] = (p, r)
    protected = ("frame_ref", "fidelity", "object_kind", "status", "locked", "suppressed", "position", "position_space", "scale_application", "rotation_euler_radians", "scale", "basis_row_major", "species_ref", "asset_artifact_ref", "extensions")
    for path, kind, old in originals:
        found = candidate_registry.get(key(old["ref"]))
        new = found[2] if found and found[1] == kind else None
        if kind == "coordinate_frame" and (new is None or any(old.get(f) != new.get(f) for f in ("geography_mode", "position_space", "axes", "handedness", "meters_per_unit", "origin", "parent_frame_ref", "georeference", "representation"))):
            errors.append(issue("baseline", "FRAME_DRIFT", path, "Existing coordinate frame semantics are immutable; add a versioned adapter/frame instead of silently changing them.", old["ref"]))
        if kind == "artifact" and old["authority"] in ("source_of_truth", "accepted_authored") and old.get("sha256"):
            if new is None or any(new.get(f) != old.get(f) for f in ("sha256", "byte_length", "authority", "role")):
                errors.append(issue("baseline", "SOURCE_ARTIFACT_DRIFT", path, "Accepted/source artifact identity or bytes changed; retain the old artifact and add a versioned derivative.", old["ref"]))
        if new is not None and any(r not in new.get("provenance_refs", []) for r in old.get("provenance_refs", [])):
            errors.append(issue("baseline", "PROVENANCE_LINK_REMOVED", path, "Existing provenance references must survive migration; append additional evidence instead of erasing its history.", old["ref"]))
        if kind in ("source", "activity", "license"):
            if new is None:
                errors.append(issue("baseline", "PROVENANCE_RECORD_REMOVED", path, "A provenance record from the baseline cannot be removed by migration.", old["ref"]))
            elif record_hash(old) != record_hash(new):
                errors.append(issue("baseline", "PROVENANCE_RECORD_DRIFT", path, "Historical provenance record content is immutable under its existing identity; append a versioned correction or new evidence record.", old["ref"]))
        if kind == "native_binding" and (new is None or record_hash(old) != record_hash(new)):
            errors.append(issue("baseline", "NATIVE_BINDING_DRIFT", path, "An existing native binding cannot be retargeted or reinterpreted under the same identity; append a separately identified binding.", old["ref"]))
        if kind != "placement" or (old["status"] not in ("accepted", "frozen_incumbent") and not old["locked"]):
            continue
        if new is None:
            errors.append(issue("baseline", "ACCEPTED_ID_REMOVED", path, "Accepted or frozen incumbent placement identity cannot be removed or renamed by a migration.", old["ref"]))
            continue
        if any(old.get(f) != new.get(f) for f in ("source_locator", "native_binding_ref")):
            errors.append(issue("baseline", "PLACEMENT_PROVENANCE_DRIFT", found[0], "An accepted placement's native binding and immutable recovery locator must be retained.", old["ref"]))
        changed = [f for f in protected if old.get(f) != new.get(f)]
        if not changed:
            continue
        if candidate["world"]["revision"] <= baseline["world"]["revision"]:
            errors.append(issue("baseline", "REVISION_NOT_ADVANCED", "/world/revision", "A candidate that changes an accepted placement must advance the world revision."))
        if old["locked"]:
            errors.append(issue("baseline", "LOCKED_PLACEMENT_CHANGED", found[0], "Candidate changes a locked accepted placement.", {"reference": old["ref"], "changed_fields": changed}))
            continue
        authorization = overrides.get(key(old["ref"]))
        if not authorization:
            errors.append(issue("baseline", "ACCEPTED_CHANGE_WITHOUT_OVERRIDE", found[0], "An accepted placement change requires an explicit accepted override against this baseline.", {"changed_fields": changed}))
            continue
        override_path, override = authorization
        if override["base_world_revision"] != baseline["world"]["revision"]:
            errors.append(issue("baseline", "STALE_OVERRIDE_REVISION", override_path, "Accepted override does not target the supplied baseline revision."))
        if override["hash_domain"] != "shared_record_v1" or override["expected_target_hash"] != record_hash(old):
            errors.append(issue("baseline", "STALE_OVERRIDE_HASH", override_path, "Accepted override must match the baseline shared-record hash; native hashes need their own adapter."))
        if any(f not in override["changes"] or override["changes"][f] != new.get(f) for f in changed):
            errors.append(issue("baseline", "OVERRIDE_DIFF_MISMATCH", override_path, "Declared changes do not cover the candidate's actual protected-field differences.", {"changed_fields": changed}))
        if any(f == "ref" or f not in new or new[f] != value for f, value in override["changes"].items()):
            errors.append(issue("baseline", "OVERRIDE_DIFF_MISMATCH", override_path, "Every declared change must match an actual candidate field; identity replacement and unapplied changes are forbidden."))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path, help="Explicit root for package/local artifact files; defaults to manifest folder.")
    parser.add_argument("--check-files", action="store_true", help="Read artifact bytes, verify hashes, and validate supported JSON sidecars; never fetch URLs.")
    parser.add_argument("--baseline", type=Path, help="Check a candidate against immutable coordinates/accepted placements in a prior manifest.")
    parser.add_argument("--baseline-artifact-root", type=Path, help="Root for baseline files; defaults to the baseline manifest folder (or the explicit shared --artifact-root).")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args(argv)
    try:
        result = validate_manifest(load_json(args.manifest), schema=load_json(args.schema),
            artifact_root=args.artifact_root or args.manifest.parent, check_files=args.check_files,
            baseline=load_json(args.baseline) if args.baseline else None,
            baseline_artifact_root=args.baseline_artifact_root or args.artifact_root or (args.baseline.parent if args.baseline else None))
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"valid": False, "contract_version": CONTRACT_VERSION,
                  "errors": [issue("parse_or_setup", "INPUT_OR_DEPENDENCY_ERROR", "", str(exc))], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
