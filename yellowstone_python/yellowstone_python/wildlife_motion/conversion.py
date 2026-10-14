"""Authored mammal proxy geometry and binary STL conversion."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import numpy as np

from .core import AssetError, vertex_normals
from .gltf import Appender, MeshAsset
from .synthetic import ellipsoid


def _surface(vertices, faces, source_hash, source, colors=None):
    normals = vertex_normals(vertices, faces)
    doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}], "scene": 0, "materials": [{
        "name": "AuthoredCoat", "pbrMetallicRoughness": {
        "baseColorFactor": [1, 1, 1, 1], "roughnessFactor": .9, "metallicFactor": 0}}]}
    app = Appender(doc)
    attrs = {"POSITION": app.add(vertices, bounds=True), "NORMAL": app.add(normals)}
    if colors is not None:
        attrs["COLOR_0"] = app.add(colors, "VEC4")
    doc["meshes"] = [{"primitives": [{"attributes": attrs,
        "indices": app.add(faces, "SCALAR", 5125), "material": 0}]}]
    doc["buffers"] = [{"byteLength": len(app.blob)}]
    return MeshAsset(doc, bytes(app.blob), vertices, normals, faces,
        [(0, len(vertices))], [(0, len(faces))], None, source_hash,
        {"mesh_index": 0, "source": source, "scale_status": "unverified_asset_units",
         "canonical_transform": np.eye(4).tolist()}, colors)


def read_binary_stl(path: str | Path) -> MeshAsset:
    """Preserve binary STL triangles in an untextured mesh asset."""
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 84:
        raise AssetError("Truncated binary STL")
    count = struct.unpack_from("<I", data, 80)[0]
    if count < 1 or len(data) != 84 + count * 50:
        raise AssetError("Binary STL triangle count differs from byte length")
    dtype = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)),
                      ("attribute", "<u2")])
    rows = np.frombuffer(data, dtype=dtype, count=count, offset=84)
    raw = rows["vertices"].reshape(-1, 3)
    if not np.isfinite(raw).all():
        raise AssetError("Nonfinite STL vertices")
    vertices, inverse = np.unique(raw, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    return _surface(vertices.astype(float), faces, hashlib.sha256(data).hexdigest(), path.name)


def mammal_shape(kind: str) -> MeshAsset:
    """Create a species-labeled authored wolf or deer geometry proxy."""
    if kind == "wolf":
        coat = [.34, .33, .30, 1.0]
        parts = [([0, .67, 0], [.23, .29, .57]),
                 ([0, .83, .44], [.20, .24, .27]),
                 ([0, .92, .69], [.15, .19, .21]),
                 ([0, .85, .87], [.11, .09, .22]),
                 ([0, .55, -.76], [.075, .11, .36])]
        for side in [-1, 1]:
            parts.append(([side*.12, 1.08, .67], [.06, .14, .055]))
            for z in [-.41, .40]:
                parts += [([side*.17, .32, z], [.07, .27, .075]),
                          ([side*.17, .045, z+.02], [.075, .045, .13])]
    elif kind == "deer":
        coat = [.48, .35, .23, 1.0]
        parts = [([0, .96, 0], [.24, .33, .62]),
                 ([0, 1.30, .46], [.13, .38, .17]),
                 ([0, 1.62, .67], [.13, .17, .20]),
                 ([0, 1.55, .82], [.09, .095, .18]),
                 ([0, .98, -.66], [.055, .08, .13])]
        for side in [-1, 1]:
            parts.append(([side*.16, 1.79, .64], [.065, .19, .09]))
            for z in [-.43, .43]:
                parts += [([side*.16, .42, z], [.055, .38, .065]),
                          ([side*.16, .035, z+.02], [.05, .035, .08])]
    else:
        raise ValueError("Authored geometry is available for wolf and deer")
    vertices, faces, count = [], [], 0
    for center, radii in parts:
        v, f = ellipsoid(center, radii, segments=12, rings=8)
        vertices.append(v); faces.append(f+count); count += len(v)
    v, f = np.vstack(vertices), np.vstack(faces)
    digest = hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest()
    colors = np.tile(coat, (len(v), 1))
    asset = _surface(v, f, digest, "authored_"+kind+"_shape", colors)
    asset.metadata["status"] = "authored"
    asset.metadata["scientific_acceptance"] = "not_yet_accepted"
    return asset
