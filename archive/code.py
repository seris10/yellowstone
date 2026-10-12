#!/usr/bin/env python3
"""
Estimate visible-tree density from a high-resolution RGB GeoTIFF.

Outputs:
    trees.csv
    trees.geojson
    crown_boxes.geojson
    summary.json

The output is a detection-based estimate, not a complete tree census.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import rasterio
import torch
from deepforest import main
from pyproj import CRS, Transformer
from rasterio.windows import Window
from torchvision.ops import nms


def tile_origins(length, tile_size, stride):
    """Cover an axis without producing tiny trailing tiles."""
    if length <= tile_size:
        return [0]

    origins = list(range(0, length - tile_size + 1, stride))
    last = length - tile_size

    if origins[-1] != last:
        origins.append(last)

    return origins


def valid_mask(src, bands, window):
    """Require all selected RGB bands to have valid data."""
    return np.all(src.read_masks(bands, window=window) > 0, axis=0)


def valid_pixel_count(src, bands, chunk_size=1024):
    """Count valid pixels without loading the entire image."""
    total = 0

    for row in range(0, src.height, chunk_size):
        for col in range(0, src.width, chunk_size):
            window = Window(
                col,
                row,
                min(chunk_size, src.width - col),
                min(chunk_size, src.height - row),
            )
            total += int(valid_mask(src, bands, window).sum())

    return total


def load_detector(checkpoint, score_threshold):
    if checkpoint:
        detector = main.deepforest.load_from_checkpoint(checkpoint)
    else:
        detector = main.deepforest()

        # Current DeepForest releases use load_model.
        # Older releases use use_release.
        if hasattr(detector, "load_model"):
            detector.load_model(model_name="weecology/deepforest-tree")
        else:
            detector.use_release()

    detector.config["score_thresh"] = score_threshold

    # Also update the underlying detector when supported.
    if hasattr(detector.model, "score_thresh"):
        detector.model.score_thresh = score_threshold

    detector.model.eval()
    return detector


def detect_trees(src, bands, detector, tile_size, overlap, score_threshold):
    stride = max(1, int(tile_size * (1 - overlap)))
    rows = tile_origins(src.height, tile_size, stride)
    cols = tile_origins(src.width, tile_size, stride)

    detections = []
    total_tiles = len(rows) * len(cols)
    completed = 0

    for row in rows:
        for col in cols:
            completed += 1

            width = min(tile_size, src.width - col)
            height = min(tile_size, src.height - row)
            window = Window(col, row, width, height)

            mask = valid_mask(src, bands, window)

            if not mask.any():
                print(f"Tile {completed}/{total_tiles}: no valid pixels")
                continue

            # Rasterio: channels x height x width.
            # DeepForest: height x width x channels, values 0–255.
            image = src.read(bands, window=window)
            image = np.moveaxis(image, 0, -1).astype(np.float32)
            image[~mask] = 0

            with torch.inference_mode():
                predictions = detector.predict_image(image=image)

            added = 0

            if predictions is not None and len(predictions):
                for prediction in predictions.itertuples(index=False):
                    score = float(prediction.score)
                    if score < score_threshold:
                        continue

                    x1 = float(np.clip(prediction.xmin, 0, width))
                    y1 = float(np.clip(prediction.ymin, 0, height))
                    x2 = float(np.clip(prediction.xmax, 0, width))
                    y2 = float(np.clip(prediction.ymax, 0, height))

                    if x2 <= x1 or y2 <= y1:
                        continue

                    # Exclude detections centred in NoData.
                    center_col = min(width - 1, int((x1 + x2) / 2))
                    center_row = min(height - 1, int((y1 + y2) / 2))

                    if not mask[center_row, center_col]:
                        continue

                    detections.append(
                        [x1 + col, y1 + row, x2 + col, y2 + row, score]
                    )
                    added += 1

            print(
                f"Tile {completed}/{total_tiles}: "
                f"{added} candidate detections"
            )

    return np.asarray(detections, dtype=np.float32).reshape(-1, 5)


def remove_duplicates(detections, iou_threshold):
    """Suppress overlapping duplicate boxes from overlapping tiles."""
    if len(detections) == 0:
        return detections

    boxes = torch.from_numpy(detections[:, :4].copy())
    scores = torch.from_numpy(detections[:, 4].copy())
    keep = nms(boxes, scores, iou_threshold).cpu().numpy()

    return detections[keep]


def write_outputs(src, detections, valid_pixels, args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    to_wgs84 = Transformer.from_crs(
        src.crs, "EPSG:4326", always_xy=True
    )

    # Handles both ordinary and rotated affine transforms.
    transform = src.transform
    pixel_area_m2 = abs(
        transform.a * transform.e - transform.b * transform.d
    )
    valid_area_m2 = valid_pixels * pixel_area_m2
    valid_area_ha = valid_area_m2 / 10_000

    rows = []
    point_features = []
    box_features = []

    # Stable spatial ordering gives readable IDs.
    if len(detections):
        order = np.lexsort((detections[:, 0], detections[:, 1]))
        detections = detections[order]

    for index, detection in enumerate(detections, start=1):
        x1, y1, x2, y2, score = map(float, detection)
        center_col = (x1 + x2) / 2
        center_row = (y1 + y2) / 2

        map_x, map_y = transform * (center_col, center_row)
        longitude, latitude = to_wgs84.transform(map_x, map_y)

        properties = {
            "tree_id": f"T{index:07d}",
            "confidence": score,
            "longitude": longitude,
            "latitude": latitude,
            "map_x": map_x,
            "map_y": map_y,
            "pixel_xmin": x1,
            "pixel_ymin": y1,
            "pixel_xmax": x2,
            "pixel_ymax": y2,
            "near_image_edge": (
                x1 <= 2
                or y1 <= 2
                or x2 >= src.width - 2
                or y2 >= src.height - 2
            ),
        }
        rows.append(properties)

        point_features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": {
                "type": "Point",
                "coordinates": [longitude, latitude],
            },
        })

        # Transform all corners; this also handles rotated rasters.
        corners = [
            (x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)
        ]
        ring = []
        for col, row in corners:
            x, y = transform * (col, row)
            lon, lat = to_wgs84.transform(x, y)
            ring.append([lon, lat])

        box_features.append({
            "type": "Feature",
            "properties": {
                "tree_id": properties["tree_id"],
                "confidence": score,
                "geometry_type": "detected_crown_bounding_box",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring],
            },
        })

    fields = [
        "tree_id", "confidence", "longitude", "latitude",
        "map_x", "map_y",
        "pixel_xmin", "pixel_ymin", "pixel_xmax", "pixel_ymax",
        "near_image_edge",
    ]

    with (out / "trees.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    for filename, features in [
        ("trees.geojson", point_features),
        ("crown_boxes.geojson", box_features),
    ]:
        with (out / filename).open("w", encoding="utf-8") as f:
            json.dump(
                {"type": "FeatureCollection", "features": features},
                f,
                allow_nan=False,
            )

    summary = {
        "source_image": str(Path(args.image).resolve()),
        "image_crs": src.crs.to_string(),
        "detected_tree_count": len(detections),
        "valid_imaged_area_m2": valid_area_m2,
        "valid_imaged_area_ha": valid_area_ha,
        "estimated_trees_per_ha": len(detections) / valid_area_ha,
        "pixel_size_x_m": float(np.hypot(transform.a, transform.d)),
        "pixel_size_y_m": float(np.hypot(transform.b, transform.e)),
        "score_threshold": args.score,
        "duplicate_suppression_iou": args.iou,
        "method": "DeepForest visible-tree-crown detection",
        "complete_tree_census": False,
        "notes": [
            "Tree positions are detected crown-box centres, not surveyed trunks.",
            "Bounding boxes are not precise crown outlines.",
            "Hidden, small, or overlapping trees may be missed.",
            "Duplicate suppression can also suppress overlapping real crowns.",
            "Confidence scores are model scores, not calibrated probabilities.",
            "Area is measured in the input projected coordinate system.",
        ],
    }

    with (out / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, allow_nan=False)

    print("\nResults")
    print(f"Detected trees: {summary['detected_tree_count']:,}")
    print(f"Valid area: {valid_area_ha:.3f} ha")
    print(f"Estimated density: {summary['estimated_trees_per_ha']:.2f} trees/ha")
    print(f"Output directory: {out.resolve()}")


def run():
    parser = argparse.ArgumentParser(
        description="Detect visible trees and estimate trees per hectare."
    )
    parser.add_argument("image", help="8-bit RGB GeoTIFF")
    parser.add_argument("--output", default="tree_results")
    parser.add_argument("--bands", nargs=3, type=int, default=[1, 2, 3],
                        metavar=("RED", "GREEN", "BLUE"))
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--overlap", type=float, default=0.25)
    parser.add_argument("--score", type=float, default=0.30)
    parser.add_argument("--iou", type=float, default=0.40)
    parser.add_argument("--checkpoint",
                        help="Optional locally fine-tuned DeepForest checkpoint")
    args = parser.parse_args()

    if args.tile_size < 64:
        parser.error("--tile-size must be at least 64")
    if not 0 <= args.overlap < 1:
        parser.error("--overlap must be in [0, 1)")
    if not 0 <= args.score <= 1 or not 0 <= args.iou <= 1:
        parser.error("--score and --iou must be in [0, 1]")

    with rasterio.open(args.image) as src:
        if src.crs is None:
            raise ValueError("The image must have a coordinate reference system.")

        crs = CRS.from_user_input(src.crs)
        if not crs.is_projected:
            raise ValueError(
                "Reproject the image to a suitable metre-based projected CRS."
            )

        axes = crs.axis_info[:2]
        if len(axes) != 2 or any(
            not np.isclose(axis.unit_conversion_factor, 1.0)
            for axis in axes
        ):
            raise ValueError("The projected CRS must use metres.")

        if any(b < 1 or b > src.count for b in args.bands):
            raise ValueError("Requested RGB bands do not exist.")

        if any(src.dtypes[b - 1] != "uint8" for b in args.bands):
            raise ValueError(
                "Selected RGB bands must be uint8. "
                "Convert higher-bit-depth imagery using appropriate scaling."
            )

        print("Measuring valid image area...")
        valid_pixels = valid_pixel_count(src, args.bands)

        if valid_pixels == 0:
            raise ValueError("The image has no valid RGB pixels.")

        print("Loading tree detector...")
        detector = load_detector(args.checkpoint, args.score)

        detections = detect_trees(
            src, args.bands, detector,
            args.tile_size, args.overlap, args.score,
        )
        print(f"\nCandidates before duplicate suppression: {len(detections):,}")

        detections = remove_duplicates(detections, args.iou)
        write_outputs(src, detections, valid_pixels, args)


if __name__ == "__main__":
    run()