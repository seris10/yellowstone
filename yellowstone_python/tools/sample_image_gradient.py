"""Image-space and planar-rectified color transects."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def srgb_to_linear(values: np.ndarray) -> np.ndarray:
    """Decode normalized sRGB values to linear light."""
    return np.where(values <= .04045, values / 12.92, ((values + .055) / 1.055) ** 2.4)


def linear_to_srgb(values: np.ndarray) -> np.ndarray:
    """Encode nonnegative linear-light values as sRGB."""
    values = np.maximum(values, 0)
    return np.where(values <= .0031308, values * 12.92, 1.055 * values ** (1 / 2.4) - .055)


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Project finite planar points through a nonsingular homography."""
    homogeneous = np.column_stack([points, np.ones(len(points))]) @ matrix.T
    if not np.all(np.isfinite(homogeneous)) or np.any(np.abs(homogeneous[:, 2]) < 1e-12):
        raise ValueError("homography maps a point to infinity")
    return homogeneous[:, :2] / homogeneous[:, 2:]


def fit_homography(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Fit a normalized DLT homography from four or more noncollinear correspondences."""
    source, target = np.asarray(source, float), np.asarray(target, float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2 or len(source) < 4:
        raise ValueError("homography requires matching Nx2 point arrays with N >= 4")
    if not np.all(np.isfinite(source)) or not np.all(np.isfinite(target)):
        raise ValueError("homography points must be finite")
    normalized, transforms = [], []
    for points in (source, target):
        center = points.mean(axis=0)
        radius = np.sqrt(np.mean(np.sum((points - center) ** 2, axis=1)))
        if radius < 1e-12:
            raise ValueError("homography control points are degenerate")
        scale = 2 ** .5 / radius
        matrix = np.array([[scale, 0, -scale * center[0]], [0, scale, -scale * center[1]], [0, 0, 1]])
        transforms.append(matrix)
        normalized.append(transform_points(points, matrix))
    rows = []
    for (x, y), (u, v) in zip(*normalized):
        rows.extend([[-x, -y, -1, 0, 0, 0, u*x, u*y, u],
                     [0, 0, 0, -x, -y, -1, v*x, v*y, v]])
    design = np.asarray(rows)
    if np.linalg.matrix_rank(design) < 8:
        raise ValueError("homography control points are degenerate")
    _, _, vectors = np.linalg.svd(design, full_matrices=True)
    matrix = np.linalg.inv(transforms[1]) @ vectors[-1].reshape(3, 3) @ transforms[0]
    if abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("homography is singular")
    return matrix / np.linalg.norm(matrix)


def bilinear(image: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sample linear RGB pixels without extrapolating outside the image."""
    height, width = image.shape[:2]
    valid = np.all(np.isfinite(points), axis=1) & (points[:, 0] >= 0) & (points[:, 0] <= width - 1)
    valid &= (points[:, 1] >= 0) & (points[:, 1] <= height - 1)
    safe = np.clip(points, [0, 0], [width - 1, height - 1])
    safe = np.nan_to_num(safe)
    lower = np.floor(safe).astype(int)
    upper = np.minimum(lower + 1, [width - 1, height - 1])
    dx, dy = (safe - lower).T
    values = ((image[lower[:, 1], lower[:, 0]] * (1-dx)[:, None]
               + image[lower[:, 1], upper[:, 0]] * dx[:, None]) * (1-dy)[:, None]
              + (image[upper[:, 1], lower[:, 0]] * (1-dx)[:, None]
                 + image[upper[:, 1], upper[:, 0]] * dx[:, None]) * dy[:, None])
    values[~valid] = np.nan
    return values, valid


def sample_transect(image: np.ndarray, start: list, end: list, count: int = 256,
                    half_width: float = 0, strip_samples: int = 1,
                    plane_to_pixel: np.ndarray | None = None) -> dict:
    """Sample an evenly spaced strip in pixel or rectified-plane coordinates."""
    image = np.asarray(image, float)
    if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 1:
        raise ValueError("transect image requires a nonempty RGB array")
    if not np.all(np.isfinite(image)) or np.any(image < 0) or np.any(image > 1):
        raise ValueError("transect RGB values must be finite and normalized")
    if not np.isfinite(half_width):
        raise ValueError("transect width must be finite")
    start, end = np.asarray(start, float), np.asarray(end, float)
    if start.shape != (2,) or end.shape != (2,) or not np.all(np.isfinite([start, end])):
        raise ValueError("transect endpoints require two finite coordinates")
    length = float(np.linalg.norm(end - start))
    if count < 2 or strip_samples < 1 or half_width < 0 or length <= 0:
        raise ValueError("transect requires positive length, count >= 2 and nonnegative width")
    points = np.linspace(start, end, count)
    tangent = (end - start) / length
    normal = np.array([-tangent[1], tangent[0]])
    offsets = np.linspace(-half_width, half_width, strip_samples) if strip_samples > 1 else np.zeros(1)
    strip = points[:, None, :] + offsets[None, :, None] * normal
    projected = strip.reshape(-1, 2)
    if plane_to_pixel is not None:
        projected = transform_points(projected, plane_to_pixel)
    sampled, valid = bilinear(srgb_to_linear(np.asarray(image, float)), projected)
    sampled = sampled.reshape(count, strip_samples, 3)
    valid = valid.reshape(count, strip_samples)
    denominator = np.maximum(valid.sum(axis=1), 1)
    linear = np.nansum(sampled, axis=1) / denominator[:, None]
    linear[valid.sum(axis=1) == 0] = np.nan
    srgb = linear_to_srgb(linear)
    center = transform_points(points, plane_to_pixel) if plane_to_pixel is not None else points
    gradient = np.gradient(linear, length / (count - 1), axis=0)
    records = []
    for index in range(count):
        available = bool(valid[index].any())
        records.append({"distance": float(index * length / (count - 1)),
            "position": points[index].tolist(), "pixel": center[index].tolist(),
            "valid_fraction": float(valid[index].mean()),
            "srgb": srgb[index].tolist() if available else None,
            "linear_rgb": linear[index].tolist() if available else None,
            "linear_gradient": gradient[index].tolist() if np.all(np.isfinite(gradient[index])) else None,
            "hex": "#" + "".join(f"{int(np.clip(c, 0, 1)*255+.5):02x}" for c in srgb[index]) if available else None})
    return {"length": length, "half_width": half_width, "strip_samples": strip_samples, "samples": records}


def analyze(image_path: Path, specification: dict) -> dict:
    """Analyze reference transects while retaining source identity and interpretation limits."""
    image = np.asarray(Image.open(image_path).convert("RGB"), float) / 255
    controls = specification.get("planar_controls")
    matrix, residual = None, None
    if controls:
        matrix = fit_homography(controls["plane"], controls["pixel"])
        residual = float(np.sqrt(np.mean(np.sum((transform_points(np.asarray(controls["plane"]), matrix)
                                                  - controls["pixel"]) ** 2, axis=1))))
    transects = {}
    for name, spec in specification["transects"].items():
        transects[name] = sample_transect(image, **spec, plane_to_pixel=matrix)
    return {"schema": "yellowstone.image_gradient.v1", "source_name": image_path.name,
        "source_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "size_px": [image.shape[1], image.shape[0]], "color_space_assumption": "sRGB",
        "distance_units": controls.get("units", "arbitrary_plane_units") if controls else "pixels",
        "illumination": specification.get("illumination", "unknown"),
        "camera_processing": "unknown", "radiometric_calibration": "unavailable",
        "uncertainty": "unknown", "planar_controls": controls,
        "control_reprojection_rms_px": residual, "plane_to_pixel": matrix.tolist() if controls else None,
        "limits": "Planar rectification requires valid correspondences on one plane; steam, canopy and relief violate that assumption. Pixel colors are image observations, not surface reflectance.",
        "transects": transects}


def main() -> int:
    """Write color transects as JSON and CSV."""
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("specification", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.image, json.loads(args.specification.read_text()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    with args.out.with_suffix(".csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["transect", "distance", "units", "pixel_x", "pixel_y", "valid_fraction", "red", "green", "blue", "hex"])
        for name, transect in report["transects"].items():
            for row in transect["samples"]:
                writer.writerow([name, row["distance"], report["distance_units"], *row["pixel"], row["valid_fraction"], *(row["srgb"] or [None]*3), row["hex"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
