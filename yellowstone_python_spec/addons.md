The most important scientific upgrades are **independent validation, representative sampling, uncertainty estimates, and reproducibility**—not simply adding another detection model.

I researched four relevant areas:

| Finding | Addition below |
|---|---|
| Image-drawn reference labels can themselves be wrong, especially in closed canopy. A 2025 TLS-based study found substantially worse performance than validation against manual image labels. | A **blind reference-annotation workflow**, separate from reviewing model detections. |
| Tree detections need one-to-one matching; matching errors and counting errors are different. | **Precision, recall, F1, localization error, count bias, MAE, and RMSE**. |
| Spatial dependence can make randomly splitting individual trees into training/test sets overly optimistic. | Validation uses **whole image plots**, not random individual trees. Keep these plots out of training and threshold tuning. |
| Forest inventories can combine wall-to-wall predictions with probability-sampled reference plots. | A **difference estimator** correcting the automated count, with an approximate sampling confidence interval. |

Sources: [TLS validation study—preprint](https://arxiv.org/html/2503.14273v1), [NEON crown benchmark](https://pmc.ncbi.nlm.nih.gov/articles/PMC8282040/), [DeepForest evaluation API](https://deepforest.readthedocs.io/en/latest/source/deepforest.html), [spatial cross-validation research](https://nsojournals.onlinelibrary.wiley.com/doi/10.1111/ecog.02881), [model-assisted forest inventory tutorial](https://doi.org/10.3390/f11020244).

Below are **additions**, not a rewrite of your program. The code is my implementation of these methods; I have not executed or tested it in your environment.

---

# What these additions will and will not establish

With Google Maps screenshots, the defensible target is:

> **Visible tree-crown count within a defined image boundary.**

These additions do **not** establish:

- A complete census of hidden trees.
- Surveyed trunk coordinates.
- Tree species, height, biomass, or carbon.
- Accurate hectares without a reliable ground scale.
- That manual annotations are flawless.

The corrected count is an **aggregate estimate**. It does not invent records or locations for trees the detector missed.

# 1. Install one additional dependency

```bash
pip install scipy
```

# 2. Create `scientific_addons.py`

Put this file beside `tree_inventory.py`.

It provides:

1. A frozen copy of the automated results **before human review**.
2. Input, code, and model fingerprints.
3. Random validation-plot selection.
4. Blind reference annotation.
5. Object-level and count-level evaluation.
6. Plot-level bootstrap intervals for evaluation metrics.
7. A probability-sampling-based corrected total and density estimate.
8. Boundary warnings and scale sensitivity.

```python
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
    }

    for filename, key in checks.items():
        if file_sha256(directory / filename) != manifest[key]:
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
```

# 3. Insert these small changes into `tree_inventory.py`

## A. Add imports

Near the other imports:

```python
from scientific_addons import (
    archive_run,
    boundary_quality,
    scale_sensitivity,
    seed_run,
)
```

## B. Add command-line arguments

Inside `parse_args()`, **before**:

```python
args = parser.parse_args()
```

insert:

```python
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
```

## C. Seed the run and prevent scientific archives being overwritten

At the beginning of `run()`, immediately after:

```python
args = parse_args()
```

insert:

```python
seed_run(args.seed)

if (Path(args.output) / "science").exists():
    raise ValueError(
        "This output already contains a frozen scientific run. "
        "Use a new --output directory."
    )
```

## D. Archive the automated inventory before review

Find:

```python
records = create_inventory(candidates, width, height)
```

Immediately after it, insert:

```python
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
```

**This placement matters.** It evaluates the detector’s original performance, not an inventory already corrected by looking at its predictions.

## E. Add analysis-boundary warnings

Find:

```python
if args.review:
    review_inventory(rgb, mask, records)
```

Immediately after that block, insert:

```python
boundary_quality(records, mask, margin_pixels=10)
```

The 10-pixel margin is a **quality-control flag**, not a scientifically established cutoff. It marks records for inspection; it does not remove them.

Find the definition of `inventory_fields`. Immediately after its closing bracket, insert:

```python
inventory_fields.extend([
    "roi_edge_distance_px",
    "near_analysis_boundary",
])
```

This covers boundaries the original `near_image_edge` flag misses: ROI boundaries, exclusion polygons, and NoData.

## F. Add scale sensitivity to the summary

Immediately before:

```python
write_json(out / "summary.json", summary)
```

insert:

```python
summary["scientific_archive"] = str(science_directory.resolve())

summary["scale_sensitivity"] = scale_sensitivity(
    count=len(active),
    valid_pixels=valid_pixels,
    scale_range=args.scale_range,
)
```

Keep the existing:

```python
"accuracy_measured": False
```

unchanged in this initial summary. Accuracy is measured later and recorded in the separate `validation_report.json`; it should not be claimed before validation is completed.

# 4. Add a metadata file

Save this as `study_metadata.json` and replace unknowns only when you actually know them:

```json
{
  "study_name": "Grand Prismatic visible crown inventory",
  "source": "Google Maps screenshot",
  "capture_datetime_utc": null,
  "imagery_acquisition_date": null,
  "source_attribution": "Record the attribution displayed on the image",
  "target_definition": "One individually distinguishable visible tree crown centre inside the analysis mask",
  "include_dead_visible_crowns": true,
  "minimum_crown_size_rule": "No explicit size cutoff; document any annotation limitations",
  "flat_map_view_verified": null,
  "ground_scale_basis": null,
  "reference_annotator": null,
  "reference_protocol": "Exhaustive crown-centre annotation without model overlay",
  "notes": "Copyright year is not assumed to be imagery acquisition year"
}
```

The imagery’s **copyright year is not an acquisition date**. Google Maps screenshots can also include imagery from different dates or sources, labels, compression, and uncertain native resolution.

# 5. Scientific workflow

## Step 1: Create the automated inventory

Use a new output directory:

```bash
python tree_inventory.py google_maps.png --select-roi --metadata-json study_metadata.json --seed 42 --output study_run_01
```

You can still include `--review`. The scientific archive remains the **pre-review automated output**.

If you have a measured ground scale:

```bash
python tree_inventory.py google_maps.png --select-roi --meters-per-pixel 0.25 --metadata-json study_metadata.json --output study_run_01
```

Again, **0.25 is illustrative—not your screenshot’s measured scale**.

## Step 2: Randomly select reference plots

```bash
python scientific_addons.py sample study_run_01/science --plots 12 --cell-pixels 256 --seed 42
```

Important:

- Twelve plots is a demonstration setting, **not a justified sample size**.
- All nonempty analysis-grid cells are eligible, including partial boundary cells.
- Do not replace plots because they are dense, difficult, or contain no trees.
- Choose plot dimensions large enough to provide useful crown context.
- For a final study, determine sample size using a separate pilot study or precision target.

The sample is selected without looking for places where the detector performed well.

## Step 3: Make independent reference annotations

```bash
python scientific_addons.py annotate study_run_01/science
```

For each sampled plot:

1. Click every distinguishable crown centre in the unshaded area.
2. Press **Enter**.
3. Explicitly accept the plot as completely annotated.

Zero-tree plots must also be accepted. Closing a window is not automatically treated as a valid zero.

**Prefer a second person who has not inspected the model results.** The interface hides predictions, but it cannot erase an annotator’s prior knowledge.

If a plot contains crowns that cannot be distinguished reliably, do not pretend its reference count is certain. Resolve it using better imagery or additional reference information, or redesign and document the target before producing final estimates.

## Step 4: Evaluate

```bash
python scientific_addons.py evaluate study_run_01/science --tolerances 3 5 8 --bootstrap 2000
```

The tolerances are in **image pixels**. These values are examples.

Choose and document the main tolerance using crown size, image resolution, and reference-position uncertainty **before inspecting validation performance**. The sweep shows sensitivity; do not select whichever tolerance makes the model look best.

Outputs:

- `validation_report.json`
- `validation_per_plot.csv`

# 6. How to interpret the new results

## Object detection

- **Precision:** fraction of detections matched to reference crowns.
- **Recall:** fraction of reference crowns detected.
- **F1:** balance between precision and recall.
- **Matched centre RMSE:** positional discrepancy for matched crowns only.

The last metric is **not geographic positioning accuracy** and does not include missed trees.

## Counting performance

- **Bias:** average automated count minus reference count per plot.
- **MAE:** typical absolute count error per plot.
- **RMSE:** gives more weight to plots with large count errors.

A correct total can hide poor detection: ten missed crowns and ten false detections cancel in the count. That is why both count and object metrics are necessary.

## Corrected total and density

For each reference plot:

\[
e_i=\text{reference count}_i-\text{automated count}_i
\]

The estimator is:

\[
\widehat{T}
=
T_{\text{automated}}
+
N\overline{e}
\]

where \(N\) is the number of cells in the complete sampling frame.

This is a fixed-prediction difference estimator under **simple random sampling without replacement**. Different boundary-cell areas are allowed because correction is applied to **cell counts**, and each eligible cell has equal inclusion probability. Density is then obtained using the entire analysis area.

The confidence interval is an **approximate sampling interval**, not a guarantee. Its justification depends on:

- The sampling design being followed.
- Reference counts being sufficiently reliable.
- Predictions remaining frozen independently of those reference plots.
- Enough sampled plots and sufficiently well-behaved residuals.

Very small samples or rare, large errors can make intervals misleading. A zero estimated sampling variance is not proof that errors are impossible.

## Two uncertainty products—not one

The code deliberately separates:

1. **Approximate sampling intervals** for the corrected total.
2. **Scale sensitivity** for the area denominator.

For example:

```bash
python tree_inventory.py google_maps.png --select-roi --meters-per-pixel 0.25 --scale-range 0.23 0.27 --output study_run_02
```

The scale range must come from an actual calibration uncertainty assessment. It is not automatically a 95% confidence interval, and it excludes uncertainty in the count.

# 7. Add a few sanity tests

Save as `test_scientific_addons.py`:

```python
import unittest
import numpy as np

from scientific_addons import match_points, difference_estimate


class ScientificTests(unittest.TestCase):
    def test_empty_reference(self):
        tp, fp, fn, distances = match_points(
            [[1, 1]], [], tolerance=2
        )
        self.assertEqual((tp, fp, fn), (0, 1, 0))
        self.assertEqual(distances, [])

    def test_one_to_one_matching(self):
        # First prediction can match either reference.
        # Second can match only [2, 0].
        # A correct assignment therefore matches both.
        tp, fp, fn, _ = match_points(
            [[0, 0], [4, 0]],
            [[2, 0], [-2, 0]],
            tolerance=2,
        )
        self.assertEqual((tp, fp, fn), (2, 0, 0))

    def test_difference_estimator(self):
        result = difference_estimate(
            model_total=40,
            population_cells=4,
            residuals=np.array([2.0, -2.0]),
            area_ha=1.0,
        )
        self.assertAlmostEqual(
            result["estimated_reference_total"], 40.0
        )
        self.assertAlmostEqual(
            result["estimated_sampling_standard_error"],
            np.sqrt(32.0),
        )

    def test_census_has_no_sampling_variance(self):
        result = difference_estimate(
            model_total=40,
            population_cells=2,
            residuals=[2.0, 4.0],
            area_ha=None,
        )
        self.assertAlmostEqual(
            result["estimated_reference_total"], 46.0
        )
        self.assertEqual(
            result["estimated_sampling_standard_error"], 0.0
        )


if __name__ == "__main__":
    unittest.main()
```

Run:

```bash
python -m unittest test_scientific_addons.py
```

These are sanity tests, not a substitute for testing the image workflow, annotation GUI, and installed DeepForest version.

---

## What I would add next—but not calculate from this screenshot alone

After these additions, the next research-grade improvements would be:

- **Independent annotator agreement:** duplicate annotation on a subset, then adjudicate disagreements.
- **Spatially separated training/tuning/test regions:** particularly if you fine-tune DeepForest. Adjacent tiles and overlapping crops must not leak across splits.
- **Crown polygons with polygon-level validation:** if you need crown area or canopy cover; bounding-box area is not crown area.
- **Co-registered field or LiDAR reference data:** if the target is actual stems rather than visible crowns.
- **Image registration and acquisition-date control:** before claiming tree growth, loss, or mortality across dates.

**For your current tool, the highest-value scientific addition is the frozen, independently validated inventory plus a probability-sampled error correction.** It makes the tool’s accuracy measurable rather than assumed.