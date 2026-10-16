"""Frozen blind-crop sampling and submitted visible-crown matching."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from tools.audit_provenance import audit_file

from yellowstone_python.census import census_validate
from yellowstone_python.census.census_validate import (
    LIDAR_DENSITY_CLASSES, _hungarian, evaluate_lidar_blind_crops,
    lidar_density_class, sample_lidar_blind_crops,
)
from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic


def _census(points, extent):
    """Return a geometric census with measured-source metadata."""
    return {"trees": [{"x": x, "z": z, "method": "lidar_lmf"} for x, z in points],
            "source": {"extent_m": extent, "acquisition_year": 2020, "status": "measured"}}


def _freeze(tmp_path, points, *, size=(30, 10), extent=None, name="blind", **kwargs):
    """Freeze a deterministic plain image and geometric census."""
    extent = extent or [0, 0, size[0], size[1]]
    pixels = np.arange(size[0] * size[1] * 3, dtype=np.uint8).reshape(size[1], size[0], 3)
    image = tmp_path / "review.png"
    Image.fromarray(pixels).save(image)
    out = tmp_path / name
    plan = sample_lidar_blind_crops(
        _census(points, extent), image, out, cell_px=10, plots_per_class=3,
        tolerances_m=(1.0,), main_tolerance_m=1.0,
        imagery_metadata={"acquisition_year": 2022, "source": "NAIP"}, **kwargs)
    return out, plan, pixels


def _labels(directory, point_map):
    """Build explicit submissions and stable point identifiers for selected crops."""
    sample = load_json(directory / "sample.json", expect=list)
    refs, marks = [], []
    for plot in sample:
        pid = plot["plot_id"]
        points = point_map.get(pid, [])
        marks.append({"plot_id": pid, "submitted": True, "n": len(points)})
        refs.extend({"plot_id": pid, "reference_id": f"{pid}_{i}", "pixel_x": x, "pixel_y": y}
                    for i, (x, y) in enumerate(points))
    return refs, marks


@pytest.mark.parametrize("density, expected", [(0, "under_600"), (599.9, "under_600"),
                                              (600, "600_to_2200"), (2200, "600_to_2200"),
                                              (2200.1, "over_2200")])
def test_density_class_boundaries(density, expected):
    """Include both boundary densities in the middle visible-crown class."""
    assert lidar_density_class(density) == expected


def test_sampling_density_strata_partial_area_and_plain_crops(tmp_path):
    """Freeze exact partial-cell areas and preserve source pixels without overlays."""
    points = ([(1 + i, 1) for i in range(6)]
              + [(21 + i % 8, 1 + i // 8) for i in range(12)]
              + [(41 + i % 8, 1 + i // 8) for i in range(23)])
    chm = tmp_path / "chm.f32"
    chm.write_bytes(b"measured canopy bytes")
    out, plan, pixels = _freeze(tmp_path, points, size=(25, 10), extent=[0, 0, 50, 10],
                               source_paths={"raw_chm": chm})
    frame = load_json(out / "frame.json", expect=list)
    assert [plot["area_m2"] for plot in frame] == [200, 200, 100]
    assert [plot["selection_density_proxy_per_ha"] for plot in frame] == [300, 600, 2300]
    assert [plot["selection_density_proxy_class"] for plot in frame] == list(LIDAR_DENSITY_CLASSES)
    assert plan["source_hashes"]["raw_chm"] == sha256_file(chm)
    assert plan["source_hashes"]["review_image"] == sha256_file(tmp_path / "review.png")
    assert plan["source_metadata"]["acquisition_year"] == 2020
    assert plan["imagery_metadata"]["acquisition_year"] == 2022
    assert "epochs" in plan["epoch_limitation"]
    assert plan["density_class_quantity"] == "visible dominant crowns per ha"
    assert plan["total_stem_density_status"] == plan["subcanopy_stem_density_status"] == "unknown"
    assert plan["model_overlays"] is False
    for plot in load_json(out / "sample.json", expect=list):
        assert "model_count" not in plot
        assert "selection_density_proxy_class" not in plot
        with Image.open(out / "blind_crops" / f"{plot['plot_id']}.png") as crop:
            assert np.array_equal(np.asarray(crop), pixels[plot["y0"]:plot["y1"], plot["x0"]:plot["x1"]])


def test_sampling_selection_is_reproducible_and_existing_directory_is_preserved(tmp_path):
    """Select the same proxy-stratified cells from identical seeded inputs."""
    points = [(10 * cell + 1 + i % 8, 1 + i // 8)
              for cell in range(9) for i in range((1, 6, 23)[cell // 3])]
    image = tmp_path / "image.png"
    Image.new("RGB", (90, 10), (15, 70, 30)).save(image)
    census = _census(points, [0, 0, 90, 10])
    kwargs = {"cell_px": 10, "plots_per_class": 2, "seed": 42}
    first = sample_lidar_blind_crops(census, image, tmp_path / "first", **kwargs)
    second = sample_lidar_blind_crops(census, image, tmp_path / "second", **kwargs)
    assert first["selected"] == second["selected"]
    assert len(first["selected"]) == 6
    assert all(value["selected_plots"] == 2 for value in first["selection_proxy_strata"].values())
    before = {path.relative_to(tmp_path / "first"): sha256_file(path)
              for path in (tmp_path / "first").rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="already exists"):
        sample_lidar_blind_crops(census, image, tmp_path / "first", **kwargs)
    assert before == {path.relative_to(tmp_path / "first"): sha256_file(path)
                      for path in (tmp_path / "first").rglob("*") if path.is_file()}


def test_empty_labels_are_unavailable_without_mutating_references(tmp_path):
    """Keep metrics unavailable until explicit hand-label submissions exist."""
    out, _, _ = _freeze(tmp_path, [(1, 1)])
    before = {path: sha256_file(path) for path in out.rglob("*") if path.is_file()}
    report = evaluate_lidar_blind_crops(out)
    assert report["status"] == "derived_not_field_validated"
    assert report["validation_availability"] == "unavailable"
    assert report["evaluations"] == report["plots"] == []
    assert before == {path: sha256_file(path) for path in out.rglob("*") if path.is_file()}


def test_explicit_zero_crown_submissions_have_defined_false_positives(tmp_path):
    """Distinguish submitted empty plots from missing hand labels."""
    out, _, _ = _freeze(tmp_path, [(1, 1)], size=(10, 10))
    refs, markers = _labels(out, {})
    report = evaluate_lidar_blind_crops(out, reference_points=refs, reference_submissions=markers)
    assert report["validation_availability"] == "submitted_hand_labels"
    metrics = report["evaluations"][0]["overall"]
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (0, 1, 0)
    assert metrics["precision"] == 0
    assert metrics["recall"] is None


def test_geometric_matching_is_one_to_one_in_metric_space(tmp_path):
    """Match floating metric coordinates without pixel truncation or duplicate credit."""
    out, _, _ = _freeze(tmp_path, [(2.0, 1.0), (2.8, 1.0)], size=(10, 10), extent=[0, 0, 20, 10])
    refs, markers = _labels(out, {"L00000000": [(1.1, 1.0)]})
    report = evaluate_lidar_blind_crops(out, reference_points=refs, reference_submissions=markers)
    metrics = report["evaluations"][0]["overall"]
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (1, 1, 0)
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 1
    assert metrics["matched_rmse_m"] == pytest.approx(0.2)


def test_matching_maximizes_cardinality_before_distance():
    """Retain both feasible assignments when a nearest-first match loses a crown."""
    tp, fp, fn, distances = _hungarian([(0, 0), (0.7, 0)], [(0.1, 0), (-0.7, 0)], 0.8)
    assert (tp, fp, fn) == (2, 0, 0)
    assert sorted(distances) == pytest.approx([0.6, 0.7])


def test_evaluation_density_classes_come_from_reference_labels(tmp_path):
    """Rebin plots using hand-count density after detector-proxy sampling."""
    points = [(10 * cell + 1 + i % 8, 1 + i // 8)
              for cell, count in enumerate((1, 6, 23)) for i in range(count)]
    out, _, _ = _freeze(tmp_path, points)
    labels = {f"L0000{cell:04d}": [(10 * cell + 1 + i % 8, 1 + i // 8) for i in range(count)]
              for cell, count in enumerate((6, 23, 1))}
    refs, markers = _labels(out, labels)
    report = evaluate_lidar_blind_crops(out, reference_points=refs, reference_submissions=markers)
    assert [plot["reference_density_class"] for plot in report["plots"]] == [
        "600_to_2200", "over_2200", "under_600"]
    by_class = report["evaluations"][0]["by_reference_density_class"]
    assert by_class["under_600"]["reference_count"] == 1
    assert by_class["600_to_2200"]["reference_count"] == 6
    assert by_class["over_2200"]["reference_count"] == 23
    assert all(metrics["n_plots"] == 1 and metrics["area_m2"] == 100 for metrics in by_class.values())


@pytest.mark.parametrize("failure", ["unresolved", "duplicate_submission", "duplicate_id",
                                    "duplicate_coordinates", "wrong_count", "unknown_plot",
                                    "outside_crop", "unsubmitted"])
def test_reference_submission_failures_are_rejected(tmp_path, failure):
    """Reject ambiguous, duplicate, incomplete, and out-of-crop hand labels."""
    out, _, _ = _freeze(tmp_path, [(1, 1)], size=(10, 10))
    refs, markers = _labels(out, {"L00000000": [(1, 1)]})
    if failure == "unresolved":
        markers = []
    elif failure == "duplicate_submission":
        markers.append(dict(markers[0]))
    elif failure in ("duplicate_id", "duplicate_coordinates"):
        refs.append(dict(refs[0]))
        if failure == "duplicate_coordinates":
            refs[-1]["reference_id"] = "second"
        markers[0]["n"] = 2
    elif failure == "wrong_count":
        markers[0]["n"] = 0
    elif failure == "unknown_plot":
        refs[0]["plot_id"] = "unknown"
    elif failure == "outside_crop":
        refs[0]["pixel_x"] = 10
    elif failure == "unsubmitted":
        markers[0]["submitted"] = False
    with pytest.raises(ValueError):
        evaluate_lidar_blind_crops(out, reference_points=refs, reference_submissions=markers)
    assert load_json(out / "reference_points.json", expect=list) == []


def test_frozen_artifact_changes_are_rejected(tmp_path):
    """Reject changed detections before evaluating labels."""
    out, _, _ = _freeze(tmp_path, [(1, 1)], size=(10, 10))
    doc = load_json(out / "census_frozen.json")
    doc["trees"][0]["x"] = 2
    write_json_atomic(out / "census_frozen.json", doc)
    with pytest.raises(ValueError, match="hash mismatch"):
        evaluate_lidar_blind_crops(out)


def test_json_paths_and_output_preservation(tmp_path):
    """Read explicit JSON label paths and refuse replacement of an existing report."""
    out, _, _ = _freeze(tmp_path, [(1, 1)], size=(10, 10))
    refs, markers = _labels(out, {"L00000000": [(1, 1)]})
    ref_path, mark_path = tmp_path / "labels.json", tmp_path / "submitted.json"
    write_json_atomic(ref_path, refs)
    write_json_atomic(mark_path, markers)
    output = tmp_path / "report.json"
    report = evaluate_lidar_blind_crops(out, reference_points=ref_path,
                                      reference_submissions=mark_path, out_path=output)
    assert load_json(output) == report
    original = sha256_file(output)
    with pytest.raises(ValueError, match="already exists"):
        evaluate_lidar_blind_crops(out, reference_points=ref_path,
                                  reference_submissions=mark_path, out_path=output)
    assert sha256_file(output) == original
    assert not audit_file(output, strict=True)
    assert not audit_file(out / "sampling_plan.json", strict=True)
    assert not audit_file(out / "manifest.json", strict=True)


@pytest.mark.parametrize("bad", [True, -1, float("nan"), float("inf"), "600"])
def test_density_class_rejects_invalid_numeric_values(bad):
    """Reject invalid density quantities through the shared numeric validator."""
    with pytest.raises(ValueError):
        lidar_density_class(bad)


def test_census_file_input_and_invalid_geometry_leave_output_absent(tmp_path):
    """Hash the source census file and reject geometry before creating review files."""
    image = tmp_path / "image.png"
    Image.new("RGB", (10, 10)).save(image)
    census = tmp_path / "census.json"
    write_json_atomic(census, _census([(1, 1)], [0, 0, 10, 10]))
    plan = sample_lidar_blind_crops(census, image, tmp_path / "good", cell_px=10)
    assert plan["source_hashes"]["census_file"] == sha256_file(census)
    with pytest.raises(ValueError, match="outside the source extent"):
        sample_lidar_blind_crops(_census([(10, 1)], [0, 0, 10, 10]), image, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def _naip_inputs(tmp_path, monkeypatch):
    """Create frozen two-plot NAIP inputs for submission behavior checks."""
    directory = tmp_path / "naip"
    directory.mkdir()
    monkeypatch.setattr(census_validate, "VDIR", directory)
    sample = [{"plot_id": f"P{index}", "x0": index * 10, "y0": 0,
               "x1": (index + 1) * 10, "y1": 10, "reference_count": ""}
              for index in range(2)]
    write_json_atomic(directory / "census_frozen.json", _census([(1, 1), (11, 1)], [0, 0, 20, 10]))
    write_json_atomic(directory / "sample.json", sample)
    write_json_atomic(directory / "frame.json", [dict(plot, model_count=1) for plot in sample])
    write_json_atomic(directory / "reference_points.json", [])
    write_json_atomic(directory / "sampling_plan.json", {
        "image_dims_px": [20, 10], "main_tolerance_px": 1, "tolerances_frozen_px": [1]})
    return directory, sample, SimpleNamespace(tolerances=[1])


def test_naip_empty_references_leave_metrics_unavailable(tmp_path, monkeypatch):
    """Withhold NAIP scores and total corrections before point submissions exist."""
    directory, _, args = _naip_inputs(tmp_path, monkeypatch)
    original = {name: sha256_file(directory / name)
                for name in ("sample.json", "reference_points.json", "census_frozen.json", "frame.json")}
    assert census_validate.cmd_evaluate(args) == 0
    report = load_json(directory / "validation_report.json")
    assert report["validation_availability"] == "unavailable"
    assert report["unresolved_plots"] == ["P0", "P1"]
    assert report["evaluations"] == []
    assert report["corrected_total"] is None
    assert original == {name: sha256_file(directory / name) for name in original}


def test_naip_partial_references_are_rejected_before_scoring(tmp_path, monkeypatch):
    """Reject partial NAIP labels even when a missing point set has a stored count."""
    directory, sample, args = _naip_inputs(tmp_path, monkeypatch)
    refs, _ = _labels(directory, {"P0": [(1, 1)]})
    sample[1]["reference_count"] = 1
    write_json_atomic(directory / "sample.json", sample)
    write_json_atomic(directory / "reference_points.json", refs)
    with pytest.raises(SystemExit, match="unresolved.*P1"):
        census_validate.cmd_evaluate(args)
    assert not (directory / "validation_report.json").exists()


def test_naip_submitted_point_scores_are_preserved(tmp_path, monkeypatch):
    """Preserve point-matching and difference-estimator values for submitted NAIP plots."""
    directory, _, args = _naip_inputs(tmp_path, monkeypatch)
    refs, _ = _labels(directory, {"P0": [(1, 1)], "P1": [(11, 1)]})
    write_json_atomic(directory / "reference_points.json", refs)
    assert census_validate.cmd_evaluate(args) == 0
    report = load_json(directory / "validation_report.json")
    assert report["validation_availability"] == "submitted_hand_labels"
    assert report["evaluations"] == [{"tolerance_px": 1, "tp": 2, "fp": 0, "fn": 0,
                                      "precision": 1.0, "recall": 1.0, "f1": 1.0,
                                      "matched_rmse_px": 0.0}]
    assert report["corrected_total"]["estimated_total"] == 2.0
    assert report["corrected_total"]["approx_95_interval"] == [2.0, 2.0]


@pytest.mark.parametrize("record", ["marker", "plan", "sample"])
def test_naip_explicit_empty_plot_submissions_are_preserved(tmp_path, monkeypatch, record):
    """Preserve explicit zero-crown submissions from each NAIP annotation record."""
    directory, sample, args = _naip_inputs(tmp_path, monkeypatch)
    refs, _ = _labels(directory, {"P0": [(1, 1)]})
    write_json_atomic(directory / "reference_points.json", refs)
    if record == "marker":
        write_json_atomic(directory / "reference_submissions.json", [{"plot_id": "P1", "submitted": True, "n": 0}])
    elif record == "plan":
        plan = load_json(directory / "sampling_plan.json")
        plan["zero_point_plots"] = ["P1"]
        write_json_atomic(directory / "sampling_plan.json", plan)
    else:
        sample[1]["reference_count"] = 0
        write_json_atomic(directory / "sample.json", sample)
    assert census_validate.cmd_evaluate(args) == 0
    report = load_json(directory / "validation_report.json")
    assert report["validation_availability"] == "submitted_hand_labels"
    assert report["evaluations"][0]["tp"] == 1
    assert report["evaluations"][0]["fp"] == 1
    assert report["corrected_total"]["estimated_total"] == 1.0
