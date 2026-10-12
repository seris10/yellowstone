#!/usr/bin/env python3
"""
Scientific add-ons for tree_inventory.py.

CLI:
    python scientific_addons.py sample RUN_DIRECTORY --plots 12
    python scientific_addons.py annotate RUN_DIRECTORY
    python scientific_addons.py evaluate RUN_DIRECTORY --tolerances 3 5 8

RUN_DIRECTORY is the "science" directory created by archive_run().

Reference target:
    Exhaustively annotated visible crown centres within each sampled plot.

Important:
    Validation plots must not be used to tune or train the evaluated model.
    Annotation is independent of the model overlay.
    Object matching evaluates crown-centre agreement, not crown delineation.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from scipy.stats import t


FRAME_FIELDS = [
    "plot_id", "x0", "y0", "x1", "y1",
    "valid_pixels", "model_count",
]

SAMPLE_FIELDS = FRAME_FIELDS + ["reference_count"]

POINT_FIELDS = ["reference_id", "plot_id", "pixel_x", "pixel_y"]


def save_json(path, obj):
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, allow_nan=False)


def load_json(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def save_csv(path, rows, fields):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fields, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def load_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def state_sha256(model):
    """Fingerprint actual loaded model parameters and buffers."""
    h = hashlib.sha256()

    for name, tensor in sorted(model.state_dict().items()):
        h.update(name.encode())
        h.update(str(tensor.dtype).encode())
        h.update(str(tuple(tensor.shape)).encode())

        raw = (
            tensor.detach().cpu().contiguous()
            .reshape(-1).view(torch.uint8)
        )
        h.update(raw.numpy().tobytes())

    return h.hexdigest()


def seed_run(seed):
    """
    Request reproducible computation.

    Warning-only deterministic mode does not guarantee bitwise-identical
    results across different GPUs, software versions, or unsupported ops.
    """
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)


def archive_run(
    args, rgb, mask, detector, automated_records,
    roi, output_directory, pixel_area_m2
):
    """
    Freeze the automated output before visual review.

    Never overwrite this directory. Use a new --output for another run.
    """
    directory = Path(output_directory) / "science"
    directory.mkdir(parents=True, exist_ok=False)

    Image.fromarray(rgb).save(directory / "analysis_rgb.png")
    np.save(directory / "analysis_mask.npy", mask.astype(bool))
    save_json(directory / "roi.json", roi)

    save_csv(
        directory / "automated_trees.csv",
        automated_records,
        ["tree_id", "score", "pixel_x", "pixel_y"],
    )

    metadata = (
        load_json(args.metadata_json)
        if getattr(args, "metadata_json", None)
        else {}
    )

    try:
        packages = subprocess.check_output(
            [sys.executable, "-m", "pip", "freeze"],
            text=True,
        )
    except Exception as exc:
        packages = f"Could not obtain package list: {exc}"

    (directory / "environment.txt").write_text(
        packages, encoding="utf-8"
    )

    code_hashes = {}
    for path in [Path(sys.argv[0]), Path(__file__)]:
        if path.is_file():
            code_hashes[str(path.resolve())] = file_sha256(path)

    manifest = {
        "archive_datetime_utc": datetime.now(timezone.utc).isoformat(),
        "source_image": str(Path(args.image).resolve()),
        "source_sha256": file_sha256(args.image),
        "archived_rgb_sha256": file_sha256(
            directory / "analysis_rgb.png"
        ),
        "mask_sha256": file_sha256(
            directory / "analysis_mask.npy"
        ),
        "roi_sha256": file_sha256(
            directory / "roi.json"
        ),
        "automated_trees_sha256": file_sha256(
            directory / "automated_trees.csv"
        ),
        "model_state_sha256": state_sha256(detector.model),
        "code_sha256": code_hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "cuda_version": torch.version.cuda,
        "seed": args.seed,
        "deterministic_mode": "requested_warning_only",
        "parameters": vars(args),
        "metadata": metadata,
        "image_width": int(rgb.shape[1]),
        "image_height": int(rgb.shape[0]),
        "analysis_area_pixels": int(mask.sum()),
        "pixel_area_m2": pixel_area_m2,
        "automated_count": len(automated_records),
        "inventory_stage": "automated_before_human_review",
        "target": "visible_crown_centres",
    }

    save_json(directory / "manifest.json", manifest)
    print(f"Frozen scientific inputs: {directory.resolve()}")
    return directory


def boundary_quality(records, mask, margin_pixels=10):
    """
    Flag centres close to an ROI, exclusion, NoData, or image boundary.

    Distance is a raster approximation. This is a warning, not a reason
    to automatically delete a tree.
    """
    distances = distance_transform_edt(
        np.pad(mask.astype(bool), 1, constant_values=False)
    )[1:-1, 1:-1]

    height, width = mask.shape

    for record in records:
        x = min(width - 1, max(0, int(record["pixel_x"])))
        y = min(height - 1, max(0, int(record["pixel_y"])))
        distance = float(distances[y, x])

        record["roi_edge_distance_px"] = distance
        record["near_analysis_boundary"] = distance <= margin_pixels


def scale_sensitivity(count, valid_pixels, scale_range):
    """
    A plausible-scale sensitivity interval, NOT a confidence interval.

    count is held fixed; only the area denominator changes.
    """
    if scale_range is None:
        return None

    low, high = map(float, scale_range)

    if (
        not np.isfinite([low, high]).all()
        or low <= 0
        or high < low
    ):
        raise ValueError(
            "Scale range must be two positive values, LOW <= HIGH."
        )

    small_area_ha = valid_pixels * low ** 2 / 10_000
    large_area_ha = valid_pixels * high ** 2 / 10_000

    return {
        "type": "scale_sensitivity_not_statistical_confidence_interval",
        "ground_mpp_range": [low, high],
        "area_ha_range": [small_area_ha, large_area_ha],
        "trees_per_ha_range": [
            count / large_area_ha,
            count / small_area_ha,
        ],
        "count_held_fixed": count,
        "assumption": "uniform_ground_scale_flat_map",
    }


def check_frozen_inputs(directory):
    directory = Path(directory)
    manifest = load_json(directory / "manifest.json")

    checks = {
        "analysis_rgb.png": "archived_rgb_sha256",
        "analysis_mask.npy": "mask_sha256",
        "automated_trees.csv": "automated_trees_sha256",
        "roi.json": "roi_sha256",
    }

    for filename, key in checks.items():
        expected = manifest.get(key)
        if expected is None:
            raise ValueError(
                f"Frozen manifest lacks {key}; archive predates integrity check"
            )
        if file_sha256(directory / filename) != expected:
            raise ValueError(f"Frozen input changed: {filename}")

    return manifest


def create_sample(directory, number, cell_pixels, seed):
    """
    Simple random sample without replacement from all nonempty grid cells.

    Partial boundary cells remain eligible. Their area may differ, but
    every frame cell has the same sampling probability.
    """
    directory = Path(directory)
    check_frozen_inputs(directory)

    if (directory / "sampling_plan.json").exists():
        raise ValueError(
            "A sample already exists. Do not replace it after seeing errors."
        )

    mask = np.load(directory / "analysis_mask.npy")
    predictions = load_csv(directory / "automated_trees.csv")
    height, width = mask.shape

    counts = {}
    for prediction in predictions:
        col = int(float(prediction["pixel_x"]) // cell_pixels)
        row = int(float(prediction["pixel_y"]) // cell_pixels)
        counts[(row, col)] = counts.get((row, col), 0) + 1

    frame = []

    for row, y0 in enumerate(range(0, height, cell_pixels)):
        for col, x0 in enumerate(range(0, width, cell_pixels)):
            x1 = min(width, x0 + cell_pixels)
            y1 = min(height, y0 + cell_pixels)
            valid_pixels = int(mask[y0:y1, x0:x1].sum())

            if valid_pixels == 0:
                continue

            frame.append({
                "plot_id": f"P{len(frame) + 1:06d}",
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "valid_pixels": valid_pixels,
                "model_count": counts.get((row, col), 0),
            })

    population_size = len(frame)

    if not 2 <= number <= population_size:
        raise ValueError(
            f"--plots must be between 2 and {population_size}."
        )

    rng = np.random.default_rng(seed)
    indices = rng.choice(
        population_size, size=number, replace=False
    )

    sample = [
        {**frame[int(index)], "reference_count": ""}
        for index in sorted(indices)
    ]

    save_csv(directory / "frame.csv", frame, FRAME_FIELDS)
    save_csv(directory / "sample.csv", sample, SAMPLE_FIELDS)
    save_csv(directory / "reference_points.csv", [], POINT_FIELDS)

    save_json(directory / "sampling_plan.json", {
        "design": "simple_random_sampling_without_replacement",
        "population_cells": population_size,
        "sample_cells": number,
        "inclusion_probability": number / population_size,
        "cell_pixels": cell_pixels,
        "seed": seed,
        "frame_sha256": file_sha256(directory / "frame.csv"),
        "selected_plot_ids": [row["plot_id"] for row in sample],
        "boundary_rule": "centre_in_half_open_cell_and_analysis_mask",
        "reference_target": "exhaustive_visible_crown_centres",
    })

    print(
        f"Selected {number} of {population_size} plots. "
        "Next run the annotate command."
    )


def inside_plot(x, y, plot, mask):
    x0, y0, x1, y1 = [
        int(plot[key]) for key in ["x0", "y0", "x1", "y1"]
    ]
    return (
        x0 <= x < x1
        and y0 <= y < y1
        and bool(mask[int(y), int(x)])
    )


def annotate_sample(directory):
    """
    Blind annotation: no model points or predicted counts are displayed.

    A zero-tree plot must be explicitly accepted; closing a window does
    not automatically declare a plot complete.
    """
    directory = Path(directory)
    check_frozen_inputs(directory)

    rgb = np.asarray(
        Image.open(directory / "analysis_rgb.png").convert("RGB")
    )
    mask = np.load(directory / "analysis_mask.npy")
    sample = load_csv(directory / "sample.csv")
    references = load_csv(directory / "reference_points.csv")

    for plot in sample:
        if plot["reference_count"] != "":
            continue

        x0, y0, x1, y1 = [
            int(plot[key]) for key in ["x0", "y0", "x1", "y1"]
        ]

        while True:
            fig, ax = plt.subplots(figsize=(10, 8))
            ax.imshow(
                rgb[y0:y1, x0:x1],
                extent=(x0, x1, y1, y0),
            )

            # Shade excluded pixels, while retaining image context.
            excluded = ~mask[y0:y1, x0:x1]
            shade = np.zeros((*excluded.shape, 4))
            shade[:, :, 3] = excluded * 0.60
            ax.imshow(shade, extent=(x0, x1, y1, y0))

            ax.set_title(
                f"Blind reference annotation: {plot['plot_id']}\n"
                "Click every visible crown centre in unshaded area.\n"
                "Left add; right remove; Enter finish."
            )

            points = plt.ginput(n=-1, timeout=0)
            plt.close(fig)

            valid_points = [
                (float(x), float(y))
                for x, y in points
                if inside_plot(x, y, plot, mask)
            ]

            print(
                f"{plot['plot_id']}: {len(valid_points)} accepted points; "
                f"{len(points) - len(valid_points)} outside-area clicks ignored."
            )

            answer = input(
                "Exhaustive annotation complete? "
                "[y=accept / n=redo / q=save progress and stop]: "
            ).strip().lower()

            if answer == "q":
                return
            if answer != "y":
                continue

            references = [
                row for row in references
                if row["plot_id"] != plot["plot_id"]
            ]

            references.extend({
                "reference_id": f"{plot['plot_id']}_R{index:05d}",
                "plot_id": plot["plot_id"],
                "pixel_x": x,
                "pixel_y": y,
            } for index, (x, y) in enumerate(valid_points, start=1))

            plot["reference_count"] = len(valid_points)
            save_csv(directory / "sample.csv", sample, SAMPLE_FIELDS)
            save_csv(
                directory / "reference_points.csv",
                references,
                POINT_FIELDS,
            )
            break

    print("All sampled plots have accepted reference annotations.")


def match_points(predicted, reference, tolerance):
    """
    Threshold-aware, one-to-one assignment.

    Maximize the number of valid matches first, then minimize total
    matched distance. Unmatched predictions/references become FP/FN.
    """
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Matching tolerance must be finite and positive.")
    predicted = np.asarray(predicted, dtype=float).reshape(-1, 2)
    reference = np.asarray(reference, dtype=float).reshape(-1, 2)
    p, r = len(predicted), len(reference)

    if p == 0 or r == 0:
        return 0, p, r, []

    distances = cdist(predicted, reference)
    penalty = min(p, r) + 1.0

    # One private-or-shared dummy column per prediction guarantees that
    # invalid real matches are never necessary.
    cost = np.full((p, r + p), penalty)
    cost[:, :r] = np.where(
        distances <= tolerance,
        distances / tolerance,
        2 * penalty,
    )

    rows, cols = linear_sum_assignment(cost)
    valid = (cols < r)

    matched_distances = [
        float(distances[i, j])
        for i, j in zip(rows[valid], cols[valid])
        if distances[i, j] <= tolerance
    ]

    tp = len(matched_distances)
    return tp, p - tp, r - tp, matched_distances


def pooled_metrics(rows):
    tp = sum(row["tp"] for row in rows)
    fp = sum(row["fp"] for row in rows)
    fn = sum(row["fn"] for row in rows)

    errors = np.asarray([
        row["predicted_count"] - row["reference_count"]
        for row in rows
    ], dtype=float)

    ref_total = sum(row["reference_count"] for row in rows)

    return {
        "tp": int(tp), "fp": int(fp), "fn": int(fn),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn)
        if 2 * tp + fp + fn else None,
        "count_bias_per_plot": float(errors.mean()),
        "count_mae_per_plot": float(np.abs(errors).mean()),
        "count_rmse_per_plot": float(np.sqrt((errors ** 2).mean())),
        "relative_count_bias": float(errors.sum() / ref_total)
        if ref_total else None,
    }


def plot_bootstrap(rows, repetitions, seed):
    """
    Exploratory percentile intervals resampling whole plots.

    These are not the finite-population design-based total intervals.
    They assume plots are reasonable resampling units and do not include
    reference-label, scale, or registration uncertainty.
    """
    rng = np.random.default_rng(seed)
    keys = [
        "precision", "recall", "f1",
        "count_bias_per_plot", "count_mae_per_plot",
        "count_rmse_per_plot",
    ]
    draws = {key: [] for key in keys}

    for _ in range(repetitions):
        indices = rng.integers(0, len(rows), size=len(rows))
        metrics = pooled_metrics([rows[int(i)] for i in indices])
        for key in keys:
            if metrics[key] is not None:
                draws[key].append(metrics[key])

    return {
        key: {
            "interval_95": [
                float(value)
                for value in np.percentile(values, [2.5, 97.5])
            ] if values else None,
            "defined_bootstrap_replicates": len(values),
        }
        for key, values in draws.items()
    }


def difference_estimate(model_total, population_cells, residuals, area_ha):
    """
    Fixed-prediction difference estimator under SRS without replacement.

    residual = reference count - automated count for each sampled cell.

    Estimated total:
        model_total + N * mean(residual)

    Estimated sampling variance:
        N^2 * (1 - n/N) * sample_variance(residual) / n

    Predictions must be frozen independently of these reference plots.
    """
    residuals = np.asarray(residuals, dtype=float)
    n = len(residuals)
    N = int(population_cells)

    if not 2 <= n <= N:
        raise ValueError("Difference estimator requires 2 <= n <= N.")

    correction = N * float(residuals.mean())
    estimate = float(model_total + correction)

    variance = (
        N ** 2
        * (1 - n / N)
        * float(residuals.var(ddof=1))
        / n
    )
    standard_error = math.sqrt(max(0.0, variance))
    half_width = float(t.ppf(0.975, n - 1)) * standard_error
    interval = [estimate - half_width, estimate + half_width]

    # Do not silently truncate negative estimates or interval limits.
    result = {
        "method": "fixed_prediction_difference_estimator_SRSWOR",
        "automated_total": int(model_total),
        "estimated_total_correction": correction,
        "estimated_reference_total": estimate,
        "estimated_sampling_standard_error": standard_error,
        "approximate_95_sampling_interval": interval,
        "sample_cells": n,
        "population_cells": N,
        "sampling_fraction": n / N,
        "negative_estimate_warning": estimate < 0,
        "uncertainty_excludes": [
            "reference_annotation_error",
            "systematic_image_or_registration_error",
            "scale_and_area_error",
        ],
    }

    if area_ha is not None:
        if not np.isfinite(area_ha) or area_ha <= 0:
            raise ValueError("area_ha must be finite and positive.")
        result["area_ha"] = area_ha
        result["estimated_reference_trees_per_ha"] = estimate / area_ha
        result["approximate_95_density_interval"] = [
            limit / area_ha for limit in interval
        ]

    return result


def evaluate_sample(directory, tolerances, repetitions, seed):
    directory = Path(directory)
    manifest = check_frozen_inputs(directory)
    plan = load_json(directory / "sampling_plan.json")

    if file_sha256(directory / "frame.csv") != plan["frame_sha256"]:
        raise ValueError("Sampling frame changed.")

    frame = load_csv(directory / "frame.csv")
    sample = load_csv(directory / "sample.csv")
    references = load_csv(directory / "reference_points.csv")
    predictions = load_csv(directory / "automated_trees.csv")
    mask = np.load(directory / "analysis_mask.npy")

    if (
        len(frame) != plan["population_cells"]
        or len(sample) != plan["sample_cells"]
        or sorted(row["plot_id"] for row in sample)
        != sorted(plan["selected_plot_ids"])
    ):
        raise ValueError("Sample no longer matches the original design.")

    if any(row["reference_count"] == "" for row in sample):
        raise ValueError(
            "Every selected plot must be completed. "
            "Do not skip difficult or zero-tree plots."
        )

    frame_by_id = {row["plot_id"]: row for row in frame}

    for plot in sample:
        original = frame_by_id[plot["plot_id"]]
        for key in FRAME_FIELDS:
            if str(plot[key]) != str(original[key]):
                raise ValueError(f"Sample frame value changed: {key}")

    selected_ids = set(plan["selected_plot_ids"])
    if any(row["plot_id"] not in selected_ids for row in references):
        raise ValueError("Reference point outside the selected sample.")

    reference_ids = [row["reference_id"] for row in references]
    if len(reference_ids) != len(set(reference_ids)):
        raise ValueError("Duplicate reference IDs.")

    datasets = []
    for plot in sample:
        predicted = [
            [float(row["pixel_x"]), float(row["pixel_y"])]
            for row in predictions
            if inside_plot(
                float(row["pixel_x"]), float(row["pixel_y"]), plot, mask
            )
        ]
        reference = [
            [float(row["pixel_x"]), float(row["pixel_y"])]
            for row in references
            if row["plot_id"] == plot["plot_id"]
        ]

        if any(not inside_plot(x, y, plot, mask) for x, y in reference):
            raise ValueError("Reference point outside its plot/ROI.")

        if len(predicted) != int(plot["model_count"]):
            raise ValueError("Stored model count is inconsistent.")

        if len(reference) != int(plot["reference_count"]):
            raise ValueError("Reference count and point file disagree.")

        datasets.append((plot, predicted, reference))

    evaluations = []
    per_plot_output = []

    for tolerance in tolerances:
        rows = []
        distances = []

        for plot, predicted, reference in datasets:
            tp, fp, fn, matched = match_points(
                predicted, reference, tolerance
            )
            distances.extend(matched)

            row = {
                "plot_id": plot["plot_id"],
                "tolerance_px": tolerance,
                "tp": tp, "fp": fp, "fn": fn,
                "predicted_count": len(predicted),
                "reference_count": len(reference),
            }
            rows.append(row)
            per_plot_output.append(row)

        metrics = pooled_metrics(rows)
        metrics["matched_centre_rmse_px"] = (
            float(np.sqrt(np.mean(np.square(distances))))
            if distances else None
        )

        evaluations.append({
            "matching_tolerance_px": tolerance,
            "metrics": metrics,
            "exploratory_plot_bootstrap_95": plot_bootstrap(
                rows, repetitions, seed
            ),
        })

    residuals = [
        len(reference) - len(predicted)
        for _, predicted, reference in datasets
    ]

    model_total = sum(int(row["model_count"]) for row in frame)
    if model_total != len(predictions):
        raise ValueError("Frame does not account for every automated tree.")

    pixel_area = manifest["pixel_area_m2"]
    area_ha = (
        manifest["analysis_area_pixels"] * pixel_area / 10_000
        if pixel_area is not None else None
    )

    report = {
        "evaluated_inventory": "automated_before_human_review",
        "reference_target": "visible_crown_centres",
        "reference_plot_count": len(sample),
        "evaluations": evaluations,
        "corrected_total": difference_estimate(
            model_total, len(frame), residuals, area_ha
        ),
        "validation_file_sha256": {
            name: file_sha256(directory / name)
            for name in [
                "sample.csv", "reference_points.csv", "frame.csv"
            ]
        },
        "limitations": [
            "Point matching does not measure crown-boundary accuracy.",
            "Matching tolerance must be justified before inspecting test results.",
            "Bootstrap intervals are exploratory plot-level intervals.",
            "Difference-estimator interval is an approximate sampling interval.",
            "Reference labels must exhaustively cover every selected plot.",
            "Sampling uncertainty does not include annotation or scale error.",
            "These plots must not be used for model or threshold tuning.",
            "Corrected totals do not supply locations of undetected trees.",
        ],
    }

    save_json(directory / "validation_report.json", report)
    save_csv(
        directory / "validation_per_plot.csv",
        per_plot_output,
        [
            "plot_id", "tolerance_px", "tp", "fp", "fn",
            "predicted_count", "reference_count",
        ],
    )

    print(json.dumps(report["corrected_total"], indent=2))
    print(f"Full report: {directory / 'validation_report.json'}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample")
    sample.add_argument("directory")
    sample.add_argument("--plots", type=int, default=12)
    sample.add_argument("--cell-pixels", type=int, default=256)
    sample.add_argument("--seed", type=int, default=42)

    annotate = sub.add_parser("annotate")
    annotate.add_argument("directory")

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("directory")
    evaluate.add_argument(
        "--tolerances", nargs="+", type=float, required=True
    )
    evaluate.add_argument("--bootstrap", type=int, default=2000)
    evaluate.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    if args.command == "sample":
        if args.cell_pixels < 1:
            parser.error("--cell-pixels must be positive")
        create_sample(
            args.directory, args.plots, args.cell_pixels, args.seed
        )
    elif args.command == "annotate":
        annotate_sample(args.directory)
    else:
        if (
            args.bootstrap < 1
            or any(
                not math.isfinite(value) or value <= 0
                for value in args.tolerances
            )
        ):
            parser.error("Bootstrap count and tolerances must be positive.")
        evaluate_sample(
            args.directory, args.tolerances, args.bootstrap, args.seed
        )


if __name__ == "__main__":
    main()