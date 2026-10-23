"""Export source-gradient normals for display; leave terrain heights unchanged."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normals(heights, spacing):
    heights = np.asarray(heights, dtype=np.float64)
    if heights.ndim != 2 or min(heights.shape) < 2:
        raise ValueError("Expected a two-dimensional terrain grid")
    if not np.isfinite(heights).all() or not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("Finite terrain and positive spacing are required")
    dz, dx = np.gradient(heights, spacing, edge_order=1)
    result = np.stack((-dx, np.ones_like(dx), -dz), axis=-1)
    return result / np.linalg.norm(result, axis=-1, keepdims=True)


def encode(values):
    return np.rint((np.clip(values, -1, 1) + 1) * 127.5).astype(np.uint8)


def self_check():
    flat = normals(np.full((5, 6), 2200.0), 2)
    np.testing.assert_array_equal(flat, np.broadcast_to([0, 1, 0], flat.shape))
    row, col = np.indices((7, 8))
    slope = normals(2200 + col * 2 * 0.4 + row * 2 * -0.7, 2)
    expected = np.array([-0.4, 1, 0.7]) / np.linalg.norm([-0.4, 1, 0.7])
    np.testing.assert_allclose(slope, np.broadcast_to(expected, slope.shape), atol=1e-12)
    decoded = encode(slope).astype(float) / 127.5 - 1
    assert np.max(np.abs(decoded - slope)) <= 1 / 255 + 1e-12
    for bad, spacing in ((np.array([[1, 2], [3, np.nan]]), 1), (np.zeros((3, 3)), 0)):
        try:
            normals(bad, spacing)
        except ValueError:
            continue
        raise AssertionError("Invalid source accepted")


def export(root, out):
    self_check()
    data = out / "data"
    manifest_path = data / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    refs = root / "yellowstone_midway/references"
    specs = {
        "full": (refs / "terrain_source.f32", 4, (1025, 1025)),
        "core": (refs / "dem_1m_core.tif", 1, (1280, 1280)),
    }
    report = {}
    for extent, (path, spacing, shape) in specs.items():
        relative = str(path.relative_to(root))
        source_hash = digest(path)
        if source_hash != manifest["sources"][relative]:
            raise ValueError(f"Source hash differs from explorer export: {relative}")
        if path.suffix == ".f32":
            heights = np.fromfile(path, dtype="<f4").reshape(shape)
        else:
            with Image.open(path) as raster:
                heights = np.asarray(raster).copy()
        if heights.shape != shape:
            raise ValueError(f"Unexpected source dimensions: {extent}")
        computed = normals(heights, spacing)
        terrain = manifest["terrain"][extent]
        span = (terrain["n"] - 1) * terrain["spacing_m"]
        width = int(span / spacing) + 1
        if span % spacing or width > shape[0] or shape[0] != shape[1]:
            raise ValueError("Source and displayed terrain domains differ")
        computed = computed[:width, :width]
        pixels = encode(computed)
        filename = f"normal-{extent}.png"
        output_path = data / filename
        Image.fromarray(pixels).save(output_path, compress_level=9)
        with Image.open(output_path) as raster:
            restored = np.asarray(raster)
        np.testing.assert_array_equal(restored, pixels)
        # Independent central differences verify source orientation and units.
        sample_count = 0
        max_error = 0.0
        for r, c in ((1, 1), (width // 4, width // 3), (width // 2, width // 2), (width - 2, width - 2)):
            dx = (float(heights[r, c + 1]) - float(heights[r, c - 1])) / (2 * spacing)
            dz = (float(heights[r + 1, c]) - float(heights[r - 1, c])) / (2 * spacing)
            expected = np.array([-dx, 1, -dz])
            expected /= np.linalg.norm(expected)
            np.testing.assert_allclose(computed[r, c], expected, atol=1e-12)
            error = float(np.max(np.abs(restored[r, c].astype(float) / 127.5 - 1 - expected)))
            assert error <= 1 / 255 + 1e-12
            max_error = max(max_error, error)
            sample_count += 1
        metadata = {
            "file": filename,
            "n": width,
            "spacing_m": spacing,
            "start": terrain["start"],
            "coordinate_space": "object; x east, y up, z south",
            "encoding": "RGB uint8; normal = RGB / 127.5 - 1; linear color space",
            "row_order": "north_to_south; texture flipY=false",
            "uv_offset": [0.5 / width, 0.5 / width],
            "uv_scale": [(width - 1) / width, (width - 1) / width],
            "derivation": "Unit vector (-dH/dx,1,-dH/dz); centered finite differences internally and first-order one-sided differences at original source edges; computed before display-domain crop",
            "source": relative,
            "source_sha256": source_hash,
            "scope": "Display shading from source terrain gradients; no change to mesh heights, sampling, or scientific data; no added noise",
        }
        terrain["normal"] = metadata
        manifest["assets"][filename] = {"sha256": digest(output_path), "bytes": output_path.stat().st_size}
        report[extent] = {"dimensions": [width, width], "samples_verified": sample_count, "max_component_quantization_error": max_error, **manifest["assets"][filename]}
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":"), allow_nan=False))
    return {"self_checks": "flat, signed two-axis ramp, RGB quantization, invalid inputs passed", "textures": report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    print(json.dumps(export(args.root, args.out), indent=2))
