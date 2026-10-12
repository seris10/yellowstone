#!/usr/bin/env python3
"""
Visible-tree inventory from screenshots, RGB images, or RGB GeoTIFFs.

This is a detection-and-review workflow, not a guaranteed tree census.

Outputs:
    trees.csv               Active tree records
    inventory.csv           All inventory records, including user rejections
    candidates.csv          Model candidates and filtering decisions
    annotated.png           Active tree locations and detected boxes
    density_grid.csv        Counts and area for each grid cell
    density_grid.png        Spatial count/density visualization
    roi.json                Reusable analysis/exclusion boundaries
    summary.json            Counts, parameters, scale, limitations
    trees.geojson           Only if the source has a usable CRS
    crown_boxes.geojson     Only if the source has a usable CRS

Review controls:
    A: arm "add a missed tree"; click its crown centre
    D: arm "reject a detection"; click near it
    C: arm "confirm a detection"; click near it
    R: arm "restore a rejected detection"; click near it
    U: undo the last edit
    Escape: return to selection mode
    Click in selection mode: inspect a nearby record
    Close the window: save and finish

Use the Matplotlib toolbar to zoom and pan.
"""

import argparse
import copy
import csv
import json
import math
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import torch
from affine import Affine
from deepforest import main
from matplotlib.widgets import PolygonSelector
from PIL import Image, ImageDraw, ImageOps
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from shapely.geometry import Polygon, mapping
from torchvision.ops import nms

from scientific_addons import (
    archive_run,
    boundary_quality,
    scale_sensitivity,
    seed_run,
)


ACTIVE_STATUSES = {"unreviewed", "confirmed", "manual"}


def write_json(path, data):
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def write_csv(path, records, fields):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def load_image(path, bands, max_pixels):
    """Load one image. GeoTIFF RGB bands must already be uint8."""
    path = Path(path)
    geo = None

    if path.suffix.lower() in {".tif", ".tiff"}:
        with rasterio.open(path) as src:
            if src.width * src.height > max_pixels:
                raise ValueError(
                    "Image exceeds --max-pixels. Crop it first, or increase "
                    "the limit only if your computer has enough RAM."
                )

            if any(b < 1 or b > src.count for b in bands):
                raise ValueError("Requested RGB bands do not exist.")

            if any(src.dtypes[b - 1] != "uint8" for b in bands):
                raise ValueError(
                    "RGB bands must be uint8. Convert higher-bit-depth "
                    "imagery using appropriate, consistent RGB scaling."
                )

            rgb = np.moveaxis(src.read(bands), 0, -1)
            valid = np.all(src.read_masks(bands) > 0, axis=0)

            if src.crs is not None:
                geo = {
                    "crs": CRS.from_user_input(src.crs),
                    "transform": src.transform,
                }
    else:
        with Image.open(path) as opened:
            if opened.width * opened.height > max_pixels:
                raise ValueError(
                    "Image exceeds --max-pixels. Crop it first."
                )
            image = ImageOps.exif_transpose(opened)
            rgba = np.asarray(image.convert("RGBA"))
            rgb = rgba[:, :, :3].copy()
            valid = rgba[:, :, 3] > 0

    return np.ascontiguousarray(rgb), valid, geo


def select_polygon(rgb, title):
    """Draw one polygon; Enter accepts it, Escape cancels."""
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.imshow(rgb)
    ax.set_title(title + "\nClick vertices; finish polygon; press Enter.")
    chosen = []
    accepted = {"value": False}

    def on_select(vertices):
        chosen[:] = [[float(x), float(y)] for x, y in vertices]

    selector = PolygonSelector(ax, on_select, useblit=True)

    def on_key(event):
        if event.key == "enter" and len(chosen) >= 3:
            accepted["value"] = True
            plt.close(fig)
        elif event.key == "escape":
            plt.close(fig)

    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.show()
    selector.disconnect_events()

    if not accepted["value"]:
        raise ValueError("Polygon selection was cancelled.")

    polygon = Polygon(chosen)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError("Polygon must be valid and have positive area.")

    return chosen


def calibrate_scale(rgb, known_distance_m):
    """Calculate scalar ground metres/pixel from a known map distance."""
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.imshow(rgb)
    ax.set_title(
        f"Click the two endpoints of a known {known_distance_m:g} m distance.\n"
        "Use a scale bar or independently known horizontal map distance."
    )
    points = plt.ginput(2, timeout=0)
    plt.close(fig)

    if len(points) != 2:
        raise ValueError("Scale calibration needs two points.")

    pixel_distance = math.dist(points[0], points[1])
    if pixel_distance <= 0:
        raise ValueError("Calibration points must differ.")

    return known_distance_m / pixel_distance, {
        "points_px": [list(p) for p in points],
        "known_distance_m": known_distance_m,
        "distance_px": pixel_distance,
    }


def polygon_mask(vertices, shape):
    polygon = Polygon(vertices)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError("Invalid ROI/exclusion polygon.")

    return rasterize(
        [(mapping(polygon), 1)],
        out_shape=shape,
        transform=Affine.identity(),
        fill=0,
        dtype="uint8",
        all_touched=False,
    ).astype(bool)


def make_analysis_mask(valid, roi):
    mask = valid.copy()
    if roi["include"] is not None:
        mask &= polygon_mask(roi["include"], valid.shape)

    for vertices in roi["exclude"]:
        mask &= ~polygon_mask(vertices, valid.shape)

    if not mask.any():
        raise ValueError("Analysis boundary contains no valid image pixels.")

    return mask


def infer_area_scale(geo, supplied_mpp):
    """
    Return square metres/pixel when defensible.

    A scalar calibration assumes a flat map with approximately uniform scale.
    Web Mercator map units are not accepted as ground metres automatically.
    """
    if supplied_mpp is not None:
        return supplied_mpp ** 2, "user_supplied_ground_metres_per_pixel"

    if geo is None:
        return None, "unknown"

    crs = geo["crs"]
    axes = crs.axis_info[:2]

    if (
        crs.is_projected
        and len(axes) == 2
        and all(
            np.isclose(axis.unit_conversion_factor, 1.0)
            for axis in axes
        )
        and crs.to_epsg() not in {3857, 3395}
    ):
        t = geo["transform"]
        area = abs(t.a * t.e - t.b * t.d)
        if area > 0:
            return float(area), "input_projected_crs_area"

    return None, "unknown_or_requires_ground_scale"


def tile_origins(length, size, stride):
    if length <= size:
        return [0]

    origins = list(range(0, length - size + 1, stride))
    if origins[-1] != length - size:
        origins.append(length - size)
    return origins


def ownership_intervals(origins, size, length):
    """
    Partition an axis at midpoints between neighbouring tile centres.

    Each location belongs to one tile's central region. This reduces
    seam duplicates and favours predictions with surrounding context.
    """
    centres = [origin + min(size, length - origin) / 2 for origin in origins]
    boundaries = (
        [0.0]
        + [(a + b) / 2 for a, b in zip(centres[:-1], centres[1:])]
        + [float(length)]
    )
    return list(zip(boundaries[:-1], boundaries[1:]))


def load_detector(args):
    if args.device == "gpu" and not torch.cuda.is_available():
        raise ValueError("GPU requested, but CUDA is not available.")

    accelerator = (
        "gpu"
        if args.device == "gpu"
        or (args.device == "auto" and torch.cuda.is_available())
        else "cpu"
    )

    config = {
        "score_thresh": args.score,
        "nms_thresh": args.within_iou,
        "workers": 0,
        "batch_size": 1,
        "accelerator": accelerator,
        "devices": 1,
    }

    if args.checkpoint:
        # Load only checkpoints from a trusted source.
        detector = main.deepforest.load_from_checkpoint(
            args.checkpoint, map_location="cpu"
        )
        for key, value in config.items():
            detector.config[key] = value
        detector.create_trainer()
    else:
        detector = main.deepforest(config_args=config)
        # Explicitly load the requested pretrained model.
        detector.load_model(model_name="weecology/deepforest-tree")

    detector.config["score_thresh"] = args.score
    detector.config["nms_thresh"] = args.within_iou

    # Current DeepForest also propagates configuration during inference.
    if hasattr(detector.model, "score_thresh"):
        detector.model.score_thresh = args.score
    if hasattr(detector.model, "nms_thresh"):
        detector.model.nms_thresh = args.within_iou

    detector.model.eval()
    return detector, accelerator


def prediction_bounds(prediction):
    """Support both legacy box columns and geometry-based results."""
    names = ["xmin", "ymin", "xmax", "ymax"]

    if all(name in prediction.index for name in names):
        return [float(prediction[name]) for name in names]

    geometry = prediction.get("geometry")
    if geometry is not None and hasattr(geometry, "bounds"):
        bounds = list(geometry.bounds)
        if len(bounds) == 4:
            return [float(value) for value in bounds]

    raise ValueError(
        "Unsupported prediction output. Expected box columns or a "
        "Shapely geometry. Check your installed DeepForest version."
    )


def detect_candidates(rgb, valid, analysis_mask, detector, args):
    height, width = valid.shape
    stride = max(1, int(args.tile_size * (1 - args.overlap)))

    xs = tile_origins(width, args.tile_size, stride)
    ys = tile_origins(height, args.tile_size, stride)
    xcores = ownership_intervals(xs, args.tile_size, width)
    ycores = ownership_intervals(ys, args.tile_size, height)

    candidates = []
    candidate_number = 0
    total_tiles = len(xs) * len(ys)
    tile_number = 0

    for yi, row in enumerate(ys):
        for xi, col in enumerate(xs):
            tile_number += 1
            tw = min(args.tile_size, width - col)
            th = min(args.tile_size, height - row)

            local_analysis = analysis_mask[row:row + th, col:col + tw]
            if not local_analysis.any():
                continue

            # Keep imagery outside the ROI as context; only NoData is blacked.
            image = rgb[row:row + th, col:col + tw].astype(np.float32)
            image[~valid[row:row + th, col:col + tw]] = 0

            print(f"Predicting tile {tile_number}/{total_tiles}...", flush=True)
            with torch.inference_mode():
                predictions = detector.predict_image(image=image)

            if predictions is None or len(predictions) == 0:
                continue

            for _, prediction in predictions.iterrows():
                candidate_number += 1
                bounds = prediction_bounds(prediction)
                score = float(prediction["score"])
                label = str(prediction.get("label", "Tree"))

                record = {
                    "candidate_id": f"D{candidate_number:08d}",
                    "tile_id": tile_number,
                    "label": label,
                    "score": score if np.isfinite(score) else None,
                    "xmin": None,
                    "ymin": None,
                    "xmax": None,
                    "ymax": None,
                    "pixel_x": None,
                    "pixel_y": None,
                    "decision": "pending",
                }

                if not np.isfinite(bounds).all() or not np.isfinite(score):
                    record["decision"] = "invalid_prediction"
                    candidates.append(record)
                    continue

                x1, y1, x2, y2 = bounds
                x1, x2 = np.clip([x1, x2], 0, tw)
                y1, y2 = np.clip([y1, y2], 0, th)

                x1, x2 = float(x1 + col), float(x2 + col)
                y1, y2 = float(y1 + row), float(y2 + row)
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

                record.update({
                    "xmin": x1, "ymin": y1,
                    "xmax": x2, "ymax": y2,
                    "pixel_x": cx, "pixel_y": cy,
                })

                if x2 <= x1 or y2 <= y1:
                    decision = "invalid_box"
                elif score < args.score:
                    decision = "below_score"
                elif label.lower() != args.tree_label.lower():
                    decision = "other_class"
                elif not analysis_mask[
                    min(height - 1, max(0, int(cy))),
                    min(width - 1, max(0, int(cx))),
                ]:
                    decision = "outside_analysis_area"
                elif not (
                    xcores[xi][0] <= cx < xcores[xi][1]
                    and ycores[yi][0] <= cy < ycores[yi][1]
                ):
                    decision = "outside_tile_core"
                else:
                    decision = "pending"

                record["decision"] = decision
                candidates.append(record)

    pending = [r for r in candidates if r["decision"] == "pending"]

    if pending:
        boxes = torch.tensor(
            [[r["xmin"], r["ymin"], r["xmax"], r["ymax"]] for r in pending],
            dtype=torch.float32,
        )
        scores = torch.tensor(
            [r["score"] for r in pending], dtype=torch.float32
        )
        keep = set(nms(boxes, scores, args.merge_iou).tolist())

        for index, record in enumerate(pending):
            record["decision"] = (
                "retained" if index in keep else "suppressed_overlap"
            )

    return candidates


def create_inventory(candidates, width, height):
    records = []

    for candidate in candidates:
        if candidate["decision"] != "retained":
            continue

        record = {
            "tree_id": candidate["candidate_id"],
            "source": "model",
            "status": "unreviewed",
            "score": candidate["score"],
            "pixel_x": candidate["pixel_x"],
            "pixel_y": candidate["pixel_y"],
            "xmin": candidate["xmin"],
            "ymin": candidate["ymin"],
            "xmax": candidate["xmax"],
            "ymax": candidate["ymax"],
            "near_image_edge": (
                candidate["xmin"] <= 2
                or candidate["ymin"] <= 2
                or candidate["xmax"] >= width - 2
                or candidate["ymax"] >= height - 2
            ),
            "note": "",
            # Populated by boundary_quality() after review; explicit nulls
            # keep the pre-review inventory schema stable.
            "roi_edge_distance_px": None,
            "near_analysis_boundary": None,
        }
        records.append(record)

    return records


def review_inventory(rgb, mask, records):
    """Interactive point-based review. Edits remain auditable in inventory."""
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(rgb)
    ax.set_xlim(-0.5, rgb.shape[1] - 0.5)
    ax.set_ylim(rgb.shape[0] - 0.5, -0.5)

    artists = []
    undo = []
    mode = {"value": "select"}
    manual_number = {"value": 0}

    colours = {
        "unreviewed": "#ffd54a",
        "confirmed": "#00ff65",
        "manual": "#40bfff",
        "rejected": "#ff4545",
    }

    def redraw(selected=None):
        for artist in artists:
            artist.remove()
        artists.clear()

        for status, colour in colours.items():
            group = [r for r in records if r["status"] == status]
            if group:
                # c and facecolors must not be passed together (c wins
                # silently); rejected points are solid, the rest hollow.
                style = (
                    {"c": colour}
                    if status == "rejected"
                    else {"facecolors": "none", "edgecolors": colour}
                )
                artists.append(ax.scatter(
                    [r["pixel_x"] for r in group],
                    [r["pixel_y"] for r in group],
                    s=28,
                    marker="x" if status == "rejected" else "o",
                    linewidths=1,
                    label=status,
                    **style,
                ))

        active_count = sum(r["status"] in ACTIVE_STATUSES for r in records)
        ax.set_title(
            f"Active trees: {active_count} | mode: {mode['value']}\n"
            "A add | D reject | C confirm | R restore | U undo | "
            "Esc select | toolbar zoom/pan | close to save"
        )

        if selected is not None:
            r = records[selected]
            artists.append(ax.annotate(
                f"{r['tree_id']} | {r['status']} | score={r['score']}",
                (r["pixel_x"], r["pixel_y"]),
                xytext=(12, 12),
                textcoords="offset points",
                color="white",
                bbox={"facecolor": "black", "alpha": 0.8},
            ))

        fig.canvas.draw_idle()

    def nearest(event):
        if not records:
            return None
        points = np.array([[r["pixel_x"], r["pixel_y"]] for r in records])
        screen_points = ax.transData.transform(points)
        distances = np.hypot(
            screen_points[:, 0] - event.x,
            screen_points[:, 1] - event.y,
        )
        index = int(np.argmin(distances))
        return index if distances[index] <= 20 else None

    def on_click(event):
        if event.inaxes != ax or event.button != 1:
            return
        toolbar = getattr(fig.canvas.manager, "toolbar", None)
        if toolbar is not None and toolbar.mode:
            return

        x, y = float(event.xdata), float(event.ydata)
        height, width = mask.shape

        if mode["value"] == "add":
            if not (0 <= x < width and 0 <= y < height):
                return
            if not mask[int(y), int(x)]:
                print("Cannot add outside the analysis area.")
                return

            manual_number["value"] += 1
            records.append({
                "tree_id": f"M{manual_number['value']:08d}",
                "source": "manual",
                "status": "manual",
                "score": None,
                "pixel_x": x,
                "pixel_y": y,
                # A centre click does not establish a crown boundary.
                "xmin": None, "ymin": None,
                "xmax": None, "ymax": None,
                "near_image_edge": (
                    x <= 2 or y <= 2 or x >= width - 2 or y >= height - 2
                ),
                "note": "Added during visual review; crown centre only.",
                "roi_edge_distance_px": None,
                "near_analysis_boundary": None,
            })
            undo.append(("add", len(records) - 1, None))
            redraw(len(records) - 1)
            return

        index = nearest(event)
        if index is None:
            return

        record = records[index]
        action = mode["value"]

        if action == "select":
            redraw(index)
            return

        before = copy.deepcopy(record)

        if action == "reject":
            record["status"] = "rejected"
        elif action == "confirm":
            if record["status"] != "rejected":
                record["status"] = "confirmed"
        elif action == "restore" and record["status"] == "rejected":
            record["status"] = (
                "manual" if record["source"] == "manual" else "unreviewed"
            )

        if record != before:
            undo.append(("edit", index, before))
        redraw(index)

    def on_key(event):
        actions = {
            "a": "add", "d": "reject", "c": "confirm",
            "r": "restore", "escape": "select",
        }
        if event.key in actions:
            mode["value"] = actions[event.key]
            redraw()
        elif event.key == "u" and undo:
            action, index, before = undo.pop()
            if action == "add":
                records.pop(index)
            else:
                records[index] = before
            redraw()

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    redraw()
    plt.show()


def enrich_coordinates(records, geo, mpp):
    transformer = (
        Transformer.from_crs(geo["crs"], "EPSG:4326", always_xy=True)
        if geo is not None else None
    )

    for record in records:
        x, y = record["pixel_x"], record["pixel_y"]
        record.update({
            "map_x": None, "map_y": None,
            "longitude": None, "latitude": None,
            "coordinate_system": "image_pixels",
        })

        if geo is not None:
            mx, my = geo["transform"] * (x, y)
            lon, lat = transformer.transform(mx, my)
            if not np.isfinite([mx, my, lon, lat]).all():
                raise ValueError("Source geographic transformation failed.")
            record.update({
                "map_x": float(mx), "map_y": float(my),
                "longitude": float(lon), "latitude": float(lat),
                "coordinate_system": geo["crs"].to_string(),
            })
        elif mpp is not None:
            record.update({
                "map_x": x * mpp,
                "map_y": -y * mpp,
                "coordinate_system": "local_metres_origin_image_top_left",
            })


def annotated_image(rgb, active, output, labels):
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)

    colours = {
        "unreviewed": "#ffd54a",
        "confirmed": "#00ff65",
        "manual": "#40bfff",
    }

    for record in active:
        colour = colours[record["status"]]
        x, y = record["pixel_x"], record["pixel_y"]

        if record["xmin"] is not None:
            draw.rectangle(
                [
                    record["xmin"], record["ymin"],
                    record["xmax"], record["ymax"],
                ],
                outline=colour,
                width=1,
            )
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], outline=colour, width=2)

        if labels:
            draw.text((x + 4, y + 4), record["tree_id"], fill=colour)

    image.save(output)


def density_outputs(rgb, mask, active, pixel_area_m2, cell_size, out):
    height, width = mask.shape
    nrows = math.ceil(height / cell_size)
    ncols = math.ceil(width / cell_size)
    counts = np.zeros((nrows, ncols), dtype=np.int64)

    for record in active:
        col = min(ncols - 1, int(record["pixel_x"] // cell_size))
        row = min(nrows - 1, int(record["pixel_y"] // cell_size))
        counts[row, col] += 1

    values = np.full((nrows, ncols), np.nan)
    rows = []

    for row in range(nrows):
        for col in range(ncols):
            x1, y1 = col * cell_size, row * cell_size
            x2, y2 = min(width, x1 + cell_size), min(height, y1 + cell_size)
            valid_pixels = int(mask[y1:y2, x1:x2].sum())

            if valid_pixels == 0:
                continue

            area_ha = (
                valid_pixels * pixel_area_m2 / 10_000
                if pixel_area_m2 is not None else None
            )
            density = (
                int(counts[row, col]) / area_ha
                if area_ha is not None else None
            )

            values[row, col] = (
                density if density is not None else counts[row, col]
            )
            rows.append({
                "grid_row": row,
                "grid_col": col,
                "pixel_xmin": x1, "pixel_ymin": y1,
                "pixel_xmax": x2, "pixel_ymax": y2,
                "tree_count": int(counts[row, col]),
                "valid_area_pixels": valid_pixels,
                "area_ha": area_ha,
                "trees_per_ha": density,
            })

    write_csv(out / "density_grid.csv", rows, [
        "grid_row", "grid_col",
        "pixel_xmin", "pixel_ymin", "pixel_xmax", "pixel_ymax",
        "tree_count", "valid_area_pixels", "area_ha", "trees_per_ha",
    ])

    fig, ax = plt.subplots(figsize=(13, 8))
    ax.imshow(rgb, extent=(0, width, height, 0))
    # Padded extent keeps fixed-size grid cells aligned at the last row/column.
    heat = ax.imshow(
        np.ma.masked_invalid(values),
        extent=(0, ncols * cell_size, nrows * cell_size, 0),
        origin="upper",
        interpolation="nearest",
        cmap="magma",
        alpha=0.60,
    )
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)

    unit = (
        "Estimated trees / hectare"
        if pixel_area_m2 is not None else "Trees / grid cell"
    )
    fig.colorbar(heat, ax=ax, label=unit)
    ax.set_title(unit + " — active detections plus manual additions")
    fig.tight_layout()
    fig.savefig(out / "density_grid.png", dpi=160)
    plt.close(fig)


def geographic_outputs(active, geo, out):
    if geo is None:
        return

    transformer = Transformer.from_crs(
        geo["crs"], "EPSG:4326", always_xy=True
    )
    points, boxes = [], []

    for record in active:
        properties = {
            "tree_id": record["tree_id"],
            "status": record["status"],
            "source": record["source"],
            "model_score": record["score"],
        }
        points.append({
            "type": "Feature",
            "properties": properties,
            "geometry": {
                "type": "Point",
                "coordinates": [record["longitude"], record["latitude"]],
            },
        })

        if record["xmin"] is None:
            continue

        x1, y1 = record["xmin"], record["ymin"]
        x2, y2 = record["xmax"], record["ymax"]
        ring = []

        for x, y in [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]:
            mx, my = geo["transform"] * (x, y)
            lon, lat = transformer.transform(mx, my)
            if not np.isfinite([lon, lat]).all():
                raise ValueError("Crown geographic transformation failed.")
            ring.append([float(lon), float(lat)])

        boxes.append({
            "type": "Feature",
            "properties": {
                **properties,
                "geometry_type": "detected_crown_bounding_box",
            },
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })

    write_json(out / "trees.geojson", {
        "type": "FeatureCollection", "features": points,
    })
    write_json(out / "crown_boxes.geojson", {
        "type": "FeatureCollection", "features": boxes,
    })


def parse_args():
    parser = argparse.ArgumentParser(
        description="Detect and review visible trees in map screenshots."
    )
    parser.add_argument("image", help="PNG/JPG/RGB GeoTIFF")
    parser.add_argument("--output", default="tree_results")
    parser.add_argument("--bands", nargs=3, type=int, default=[1, 2, 3])
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--overlap", type=float, default=0.30)
    parser.add_argument("--score", type=float, default=0.25)
    parser.add_argument("--within-iou", type=float, default=0.40,
                        help="Detector's internal box suppression threshold")
    parser.add_argument("--merge-iou", type=float, default=0.40,
                        help="Final cross-tile box suppression threshold")
    parser.add_argument("--tree-label", default="Tree")
    parser.add_argument("--device", choices=["auto", "cpu", "gpu"], default="auto")
    parser.add_argument("--checkpoint", help="Trusted DeepForest checkpoint")
    parser.add_argument("--roi-json", help="Previously saved roi.json")
    parser.add_argument("--select-roi", action="store_true")
    parser.add_argument("--select-exclusions", type=int, default=0,
                        help="Number of exclusion polygons to draw")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--meters-per-pixel", type=float)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--scale-distance", type=float,
                        help="Known metres between two calibration clicks")
    parser.add_argument("--grid-pixels", type=int, default=128)
    parser.add_argument("--labels", action="store_true",
                        help="Draw tree IDs in annotated.png")
    parser.add_argument("--max-pixels", type=int, default=40_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--metadata-json",
        help="JSON file describing source, dates, target definition, and scale",
    )

    parser.add_argument(
        "--scale-range",
        nargs=2,
        type=float,
        metavar=("LOW_MPP", "HIGH_MPP"),
        help="Plausible ground metres/pixel range; sensitivity, not a confidence interval",
    )
    args = parser.parse_args()

    if args.tile_size < 64:
        parser.error("--tile-size must be >= 64")
    if not 0 < args.overlap < 1:
        parser.error("--overlap must be between 0 and 1")
    if any(not isinstance(b, int) or b < 1 for b in args.bands):
        parser.error("--bands must be three positive band indices")
    if len(set(args.bands)) != 3:
        parser.error("--bands must be three distinct bands")
    for name in ["score", "within_iou", "merge_iou"]:
        value = getattr(args, name)
        if not math.isfinite(value) or not 0 <= value <= 1:
            parser.error(f"--{name.replace('_', '-')} must be in [0,1]")
    if args.grid_pixels < 1 or args.max_pixels < 1:
        parser.error("Grid size and max pixels must be positive")
    if args.select_exclusions < 0:
        parser.error("--select-exclusions must be nonnegative")
    if args.meters_per_pixel is not None and (
        not math.isfinite(args.meters_per_pixel)
        or args.meters_per_pixel <= 0
    ):
        parser.error("--meters-per-pixel must be finite and positive")
    if args.calibrate and (
        args.scale_distance is None
        or not math.isfinite(args.scale_distance)
        or args.scale_distance <= 0
    ):
        parser.error("--calibrate requires positive --scale-distance")
    if args.calibrate and args.meters_per_pixel is not None:
        parser.error("Use calibration OR --meters-per-pixel, not both")

    return args


def run():
    args = parse_args()
    seed_run(args.seed)

    if (Path(args.output) / "science").exists():
        raise ValueError(
            "This output already contains a frozen scientific run. "
            "Use a new --output directory."
        )
    if args.metadata_json is not None:
        # Fail fast: a missing/unreadable metadata file must not waste a
        # full tiled detection run that only fails inside archive_run().
        try:
            with Path(args.metadata_json).open(encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot load --metadata-json: {exc}")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    # Avoid leaving geographic exports from an older run with another input.
    for filename in ["trees.geojson", "crown_boxes.geojson"]:
        (out / filename).unlink(missing_ok=True)

    rgb, valid, geo = load_image(
        args.image, args.bands, args.max_pixels
    )
    height, width = valid.shape

    roi = {
        "image_width": width,
        "image_height": height,
        "include": None,
        "exclude": [],
    }

    if args.roi_json:
        with Path(args.roi_json).open(encoding="utf-8") as f:
            roi = json.load(f)
        if (
            roi.get("image_width") != width
            or roi.get("image_height") != height
        ):
            raise ValueError("ROI dimensions do not match the input image.")

    if args.select_roi:
        roi["include"] = select_polygon(
            rgb, "Draw the analysis boundary. Exclude map controls where possible."
        )

    for index in range(args.select_exclusions):
        roi["exclude"].append(select_polygon(
            rgb,
            f"Draw exclusion {index + 1}/{args.select_exclusions}"
        ))

    mask = make_analysis_mask(valid, roi)
    write_json(out / "roi.json", roi)

    calibration = None
    if args.calibrate:
        args.meters_per_pixel, calibration = calibrate_scale(
            rgb, args.scale_distance
        )

    pixel_area_m2, scale_method = infer_area_scale(
        geo, args.meters_per_pixel
    )

    if pixel_area_m2 is None:
        print(
            "\nNo reliable ground scale: tree counts will be exported, "
            "but trees/hectare will be blank.\n"
        )

    print("Loading model...")
    detector, accelerator = load_detector(args)
    candidates = detect_candidates(
        rgb, valid, mask, detector, args
    )

    candidate_fields = [
        "candidate_id", "tile_id", "label", "score",
        "xmin", "ymin", "xmax", "ymax",
        "pixel_x", "pixel_y", "decision",
    ]
    write_csv(out / "candidates.csv", candidates, candidate_fields)

    records = create_inventory(candidates, width, height)
    science_directory = archive_run(
        args=args,
        rgb=rgb,
        mask=mask,
        detector=detector,
        automated_records=records,
        roi=roi,
        output_directory=out,
        pixel_area_m2=pixel_area_m2,
    )
    print(f"\nInitial retained detections: {len(records)}")

    # Save an initial inventory before opening the optional review window.
    inventory_fields = [
        "tree_id", "source", "status", "score",
        "pixel_x", "pixel_y", "xmin", "ymin", "xmax", "ymax",
        "near_image_edge", "note",
        "map_x", "map_y", "longitude", "latitude", "coordinate_system",
    ]
    inventory_fields.extend([
        "roi_edge_distance_px",
        "near_analysis_boundary",
    ])
    enrich_coordinates(records, geo, args.meters_per_pixel)
    write_csv(out / "inventory.csv", records, inventory_fields)

    if args.review:
        review_inventory(rgb, mask, records)

    boundary_quality(records, mask, margin_pixels=10)

    enrich_coordinates(records, geo, args.meters_per_pixel)
    active = [r for r in records if r["status"] in ACTIVE_STATUSES]

    write_csv(out / "inventory.csv", records, inventory_fields)
    write_csv(out / "trees.csv", active, inventory_fields)
    annotated_image(rgb, active, out / "annotated.png", args.labels)
    density_outputs(
        rgb, mask, active, pixel_area_m2, args.grid_pixels, out
    )
    geographic_outputs(active, geo, out)

    valid_pixels = int(mask.sum())
    area_ha = (
        valid_pixels * pixel_area_m2 / 10_000
        if pixel_area_m2 is not None else None
    )
    density = len(active) / area_ha if area_ha is not None else None

    summary = {
        "source_image": str(Path(args.image).resolve()),
        "image_width": width,
        "image_height": height,
        "deepforest_version": version("deepforest"),
        "model": args.checkpoint or "weecology/deepforest-tree",
        "accelerator": accelerator,
        "model_candidates_returned": len(candidates),
        "candidate_decisions": dict(Counter(
            r["decision"] for r in candidates
        )),
        "initial_retained_detections": sum(
            r["decision"] == "retained" for r in candidates
        ),
        "active_tree_count": len(active),
        "inventory_status_counts": dict(Counter(
            r["status"] for r in records
        )),
        "analysis_area_pixels": valid_pixels,
        "analysis_area_ha": area_ha,
        "estimated_trees_per_ha": density,
        "ground_metres_per_pixel": args.meters_per_pixel,
        "area_method": scale_method,
        "calibration": calibration,
        "input_crs": geo["crs"].to_string() if geo else None,
        "parameters": {
            "tile_size": args.tile_size,
            "overlap": args.overlap,
            "score_threshold": args.score,
            "within_tile_nms_iou": args.within_iou,
            "cross_tile_nms_iou": args.merge_iou,
            "grid_pixels": args.grid_pixels,
            "seed": args.seed,
            "bands": list(args.bands),
            "tree_label": args.tree_label,
            "device_requested": args.device,
            "checkpoint": args.checkpoint,
            "scale_range": (
                list(args.scale_range)
                if args.scale_range is not None else None
            ),
            "metadata_json": args.metadata_json,
        },
        "review_window_used": args.review,
        "complete_tree_census": False,
        "accuracy_measured": False,
        "notes": [
            "Inventory contains visible crown candidates and manual additions.",
            "Unreviewed detections are included in the active count.",
            "Coordinates indicate crown centres, not surveyed trunk positions.",
            "Model scores are not calibrated probabilities.",
            "Crown boxes are rectangles, not segmented crown outlines.",
            "Manual additions establish a centre only, not a crown boundary.",
            "Candidate audit begins after model-internal filtering.",
            "Tile ownership and suppression may miss or merge neighbouring trees.",
            "Area includes all valid pixels inside the ROI minus exclusions.",
            "Boundary trees are assigned by detected or manually placed centre.",
            "Scalar screenshot calibration assumes approximately uniform scale.",
            "Do not use scalar calibration on tilted/perspective map views.",
            "Projected CRS area is an estimate, subject to projection distortion.",
            "Tree IDs are run-local, not matched across images or dates.",
            "Hidden, small, overlapping, or obscured trees can be missed.",
        ],
    }
    summary["scientific_archive"] = str(science_directory.resolve())

    summary["scale_sensitivity"] = scale_sensitivity(
        count=len(active),
        valid_pixels=valid_pixels,
        scale_range=args.scale_range,
    )
    write_json(out / "summary.json", summary)

    print("\nFinished")
    print(f"Active tree records: {len(active):,}")
    if area_ha is not None:
        print(f"Analysis area: {area_ha:.4f} ha")
        print(f"Estimated density: {density:.2f} trees/ha")
    else:
        print("Trees/hectare: unavailable without a reliable scale.")
    print(f"Outputs: {out.resolve()}")


if __name__ == "__main__":
    run()