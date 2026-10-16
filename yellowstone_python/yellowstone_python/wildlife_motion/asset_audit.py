"""Serialized wildlife geometry, skin, and motion diagnostics."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from .core import AssetError
from .gltf import accessor, read_glb
from .validation import imported_skin


def audit_asset(path: str | Path, samples: int = 9) -> dict:
    """Inspect geometry, joint weights, images, and declared clip contracts."""
    if samples < 3:
        raise ValueError("At least three animation samples required")
    path = Path(path)
    doc, blob = read_glb(path)
    report = {"schema": "yellowstone.wildlife_motion_audit.v1", "file": path.name,
              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "status": "derived_not_field_validated", "scientific_acceptance": "not_yet_accepted",
              "quantitative_uncertainty": "unknown", "vertices": 0, "triangles": 0,
              "skins": [], "images": [], "clips": [], "limitations": [
                  "Anatomical landmark accuracy is unmeasured.",
                  "Edge distortion diagnoses skinning and excludes biomechanical interpretation.",
                  "Physical dimensions require independent evidence or authored display values."]}
    for index in range(len(doc.get("accessors", []))):
        values = accessor(doc, blob, index)
        if not np.isfinite(values).all():
            raise AssetError("Nonfinite accessor values")
    for node in doc.get("nodes", []):
        if "mesh" not in node:
            continue
        for primitive in doc["meshes"][node["mesh"]]["primitives"]:
            attrs = primitive["attributes"]
            vertices = accessor(doc, blob, attrs["POSITION"])
            indices = (accessor(doc, blob, primitive["indices"], False).ravel()
                       if "indices" in primitive else np.arange(len(vertices)))
            if len(indices) % 3 or indices.max() >= len(vertices):
                raise AssetError("Invalid triangle indices")
            report["vertices"] += len(vertices)
            report["triangles"] += len(indices) // 3
            if "skin" in node:
                joints = accessor(doc, blob, attrs["JOINTS_0"], False)
                weights = accessor(doc, blob, attrs["WEIGHTS_0"])
                count = len(doc["skins"][node["skin"]]["joints"])
                if (joints.max() >= count or weights.min() < 0
                        or not np.allclose(weights.sum(1), 1, atol=3e-6)):
                    raise AssetError("Invalid skin influences")
                report["skins"].append({"joint_count": count,
                    "weight_sum_max_error": float(np.max(abs(weights.sum(1)-1)))})
    for image in doc.get("images", []):
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        data = blob[start:start+view["byteLength"]]
        with Image.open(BytesIO(data)) as pixels:
            report["images"].append({"name": image.get("name", ""),
                "dimensions": list(pixels.size), "sha256": hashlib.sha256(data).hexdigest()})
    for animation in doc.get("animations", []):
        metadata = animation.get("extras", {}).get("wildlife_motion", {})
        duration = float(max(accessor(doc, blob, s["input"])[-1, 0]
                             for s in animation["samplers"]))
        minima, maxima = [], []
        endpoints = []
        for time in np.linspace(0, duration, samples):
            positions = imported_skin(path, animation["name"], float(time))
            if not np.isfinite(positions).all():
                raise AssetError("Nonfinite animated surface")
            minima.append(positions.min(0)); maxima.append(positions.max(0))
            endpoints.append(positions)
        loop_error = float(np.max(np.abs(endpoints[0]-endpoints[-1])))
        declared_loop = bool(animation.get("extras", {}).get("loop", False))
        root_motion = bool(metadata.get("root_motion", False))
        if declared_loop and root_motion:
            raise AssetError("Root trajectory is marked as looping")
        if declared_loop and loop_error > 1e-5:
            raise AssetError("Declared animation loop has discontinuous positions")
        report["clips"].append({"name": animation["name"], "duration_s": duration,
            "root_motion": root_motion, "loop": declared_loop,
            "speed_asset_units_s": metadata.get("speed_asset_units_s"),
            "surface_loop_error_asset_units": loop_error,
            "sampled_bounds_asset_units": [np.min(minima, 0).tolist(), np.max(maxima, 0).tolist()],
            "sampled_finite": True, "parameter_status": metadata.get("parameter_status", "unknown")})
    return report
