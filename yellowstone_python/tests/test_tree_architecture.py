"""Seeded tree branch graph contracts."""
import copy
from dataclasses import replace
import json
import math

import pytest

from yellowstone_python.authoring.tree_architecture import (
    ArchitectureParameters, generate_architecture, validate_architecture,
)
from tools.tree_architecture import main

DIMENSIONS = dict(height_m=18.0, dbh_m=0.32, crown_radius_m=2.15, crown_ratio=0.7)


def test_seed_identity_preserves_repeatability_and_changes_branch_graph():
    """Require stable branch geometry and distinct seeded whorl arrangements."""
    first = generate_architecture(DIMENSIONS, "edge:0")
    assert first == generate_architecture(DIMENSIONS, "edge:0")
    second = generate_architecture(DIMENSIONS, "edge:1")
    assert first["whorls"] != second["whorls"]
    assert first["axes"] != second["axes"]
    assert first["shoots"] != second["shoots"]
    assert first["dimensions_m"] == second["dimensions_m"] == DIMENSIONS


@pytest.mark.parametrize("field,value", [("height_m", math.nan), ("dbh_m", -1),
                                           ("crown_radius_m", 0), ("crown_ratio", 1.1),
                                           ("height_m", True), ("height_m", 1.3)])
def test_invalid_tree_dimensions_fail(field, value):
    """Reject missing physical dimensions and invalid crown ratios."""
    with pytest.raises(ValueError):
        generate_architecture({**DIMENSIONS, field: value}, "bad")


@pytest.mark.parametrize("field,value", [("whorl_spacing_m", 0),
                                           ("branch_count_min", 1.5),
                                           ("lower_branch_survival", -0.1),
                                           ("trunk_sway_fraction", 0.1),
                                           ("needle_length_m", 0.2), ("fascicle_count", 3),
                                           ("apex_taper_length_m", 0)])
def test_invalid_architecture_parameters_fail(field, value):
    """Reject invalid distributions and unsupported needle morphology."""
    with pytest.raises(ValueError):
        generate_architecture(DIMENSIONS, "bad", replace(ArchitectureParameters(), **{field: value}))


def test_rooted_axis_attachments_and_straight_bole():
    """Require connected higher-order axes and a bounded nearly straight bole."""
    graph = generate_architecture(DIMENSIONS, "edge:2")
    axes = {axis["id"]: axis for axis in graph["axes"]}
    assert {axis["order"] for axis in axes.values()} == {0, 1, 2}
    for axis in axes.values():
        if axis["parent_id"]:
            assert axis["points_m"][0] == axis["attachment_m"]
            assert axes[axis["parent_id"]]["order"] == axis["order"] - 1
    maximum = DIMENSIONS["height_m"] * ArchitectureParameters().trunk_sway_fraction * math.sqrt(2)
    assert max(math.hypot(p[0], p[2]) for p in axes["stem"]["points_m"]) <= maximum
    assert all(0 <= w["height_m"] <= DIMENSIONS["height_m"] for w in graph["whorls"])
    assert all(axes[s["parent_id"]]["alive"] for s in graph["shoots"])


def test_dead_snag_has_branch_structure_and_no_foliage():
    """Retain authored dead branches without assigning live needle shoots."""
    graph = generate_architecture({**DIMENSIONS, "crown_ratio": 0}, "snag")
    assert len(graph["axes"]) > 1
    assert graph["shoots"] == []
    assert all(not axis["alive"] for axis in graph["axes"][1:])


@pytest.mark.parametrize("identity", [4381, 14388, 24395, 34402])
def test_live_crown_occupancy_and_terminal_taper(identity):
    """Require overlapping shoot heights and a narrower upper crown across seeded variants."""
    graph = generate_architecture(DIMENSIONS, identity)
    spans = sorted((min(s["base_m"][1], s["tip_m"][1]),
                    max(s["base_m"][1], s["tip_m"][1])) for s in graph["shoots"])
    covered_to = spans[0][1]
    for lower, upper in spans[1:]:
        assert lower - covered_to < .12
        covered_to = max(covered_to, upper)
    points = [s[key] for s in graph["shoots"] for key in ("base_m", "tip_m")]
    upper_radius = max(math.hypot(p[0], p[2]) for p in points if p[1] > 17.5)
    middle_radius = max(math.hypot(p[0], p[2]) for p in points if 9 < p[1] < 12)
    assert upper_radius < middle_radius * .36
    assert max(p[1] for p in points) <= DIMENSIONS["height_m"]
    assert any(s["parent_id"] == "stem" for s in graph["shoots"])


def test_disconnected_parent_and_shoot_geometry_fail():
    """Reject disconnected topology and nonfinite terminal shoot vectors."""
    graph = generate_architecture(DIMENSIONS, "negative")
    bad = copy.deepcopy(graph)
    bad["axes"][1]["parent_id"] = "missing"
    with pytest.raises(ValueError):
        validate_architecture(bad)
    bad = copy.deepcopy(graph)
    bad["shoots"][0]["tip_m"][0] = math.inf
    with pytest.raises(ValueError):
        validate_architecture(bad)


def test_export_records_source_classes_and_preserves_caller_dimensions(tmp_path):
    """Export connected variants with unknown local uncertainty and reproducible inputs."""
    out = tmp_path / "architecture.json"
    main(["--height-m", "18", "--dbh-m", "0.32", "--crown-radius-m", "2.15",
          "--crown-ratio", "0.7", "--out", str(out)])
    artifact = json.loads(out.read_text())
    assert len(artifact["variants"]) == 4
    assert all(v["graph"]["status"] == "illustrative_not_locally_validated" for v in artifact["variants"])
    assert all(v["graph"]["uncertainty"] == "unknown" for v in artifact["variants"])
    assert all(v["graph"]["dimensions_m"] == DIMENSIONS for v in artifact["variants"])


@pytest.mark.parametrize("dbh_in", [5.0, 10.0, 20.0, 62.2])
def test_transferred_crown_width_equation_and_unit_conversion(dbh_in):
    """Use the exact DBH-only coefficient row and convert mean diameter to radius."""
    from yellowstone_python.authoring.tree_architecture import bechtold_crown_radius_m
    expected = (-1.1994 + 1.5154 * dbh_in - .0232 * dbh_in**2) * .3048 / 2
    assert bechtold_crown_radius_m(dbh_in * .0254) == pytest.approx(expected)


@pytest.mark.parametrize("dbh_in", [4.999, 62.201])
def test_crown_width_model_refuses_predictor_extrapolation(dbh_in):
    """Return unavailable outside the lodgepole sample DBH bounds."""
    from yellowstone_python.authoring.tree_architecture import bechtold_crown_radius_m
    assert bechtold_crown_radius_m(dbh_in * .0254) is None


def test_display_envelope_retains_observation_core_and_donor_dimensions():
    """Keep raw source fields unchanged while labeling display-only width and crown base."""
    from yellowstone_python.authoring.tree_architecture import display_dimensions
    row = dict(id="local", kind="pine", height_m=18., dbh_m=.254,
               crown_radius_m=.8, crown_ratio=.3, source_class="derived_not_field_validated")
    original = copy.deepcopy(row)
    result = display_dimensions(row, DIMENSIONS)
    assert row == original
    assert result["height_m"] == row["height_m"]
    assert result["dbh_m"] == row["dbh_m"]
    assert result["source_core_radius_m"] == row["crown_radius_m"]
    assert result["source_crown_ratio"] == row["crown_ratio"]
    assert result["crown_radius_m"] > row["crown_radius_m"]
    assert result["crown_ratio"] == .3
    assert result["crown_ratio_policy"] == "preserve_source"
    assert display_dimensions({**row, "display_crown_policy": "photo_floor"}, DIMENSIONS)["crown_ratio"] == .7
    assert result["envelope_class"] == "transferred_bechtold_dbh"
    assert result["local_error"] == "unknown"


def test_missing_dbh_uses_explicit_unknown_photo_display_assumption():
    """Label the normalized photo envelope without inventing a metric observation."""
    from yellowstone_python.authoring.tree_architecture import display_dimensions
    row = dict(id="young", height_m=5., crown_radius_m=.3, crown_ratio=.6)
    result = display_dimensions(row, DIMENSIONS)
    assert result["dbh_domain_status"] == "bechtold_unavailable_or_outside_range"
    assert result["envelope_class"] == "authored"
    assert .24 <= result["image_width_height_ratio"] <= .32
    assert result == display_dimensions(row, DIMENSIONS)


def test_parent_interpolation_detects_consistent_self_anchor_disconnection():
    """Reject a self-consistent child that fails its actual parent interpolation."""
    graph = generate_architecture(DIMENSIONS, "parent_negative")
    bad = copy.deepcopy(graph)
    bad["axes"][1]["attachment_m"][0] += .01
    bad["axes"][1]["points_m"][0] = bad["axes"][1]["attachment_m"][:]
    with pytest.raises(ValueError, match="parent"):
        validate_architecture(bad)
    bad = copy.deepcopy(graph)
    bad["shoots"][0]["base_m"][0] += .01
    with pytest.raises(ValueError, match="parent"):
        validate_architecture(bad)


def test_authored_taper_preserves_breast_height_diameter():
    """Require the exported stem taper to preserve supplied DBH at 1.3 m."""
    from yellowstone_python.authoring.tree_architecture import stem_radius_m
    graph = generate_architecture(DIMENSIONS, "stem")
    stem = graph["axes"][0]
    section = next(row for row in stem["radius_profile_m"] if row[0] == 1.3)
    assert section[1] * 2 == DIMENSIONS["dbh_m"]
    assert stem_radius_m(18., .32, 1.3) * 2 == .32
    assert stem["radius_base_m"] > stem["radius_at_breast_height_m"]
    assert stem["radius_class"] == "authored_taper_preserving_dbh"


def test_record_export_integrates_display_envelope_without_overwriting_raw_record(tmp_path):
    """Carry source record bytes and the labeled envelope into authored architecture export."""
    record = tmp_path / "record.json"
    raw = dict(id="published_tree", height_m=18., dbh_m=.254, crown_radius_m=.8, crown_ratio=.3)
    record.write_text(json.dumps(raw))
    original = record.read_bytes()
    out = tmp_path / "architecture.json"
    main(["--input", str(record), "--out", str(out)])
    artifact = json.loads(out.read_text())
    assert artifact["input_record"] == raw and record.read_bytes() == original
    assert artifact["display_dimensions"]["source_core_radius_m"] == .8
    assert artifact["display_dimensions"]["envelope_class"] == "transferred_bechtold_dbh"
    assert artifact["variants"][0]["graph"]["dimensions_m"]["crown_radius_m"] > .8


@pytest.mark.parametrize("value", [math.nan, math.inf, -1, True])
def test_direct_stem_radius_rejects_invalid_dbh(value):
    """Reject invalid public taper inputs before evaluating the authored profile."""
    from yellowstone_python.authoring.tree_architecture import stem_radius_m
    with pytest.raises(ValueError):
        stem_radius_m(18., value, 1.3)


def test_census_input_selection_and_parameter_json(tmp_path):
    """Select an existing identity and apply explicit validated architecture parameters."""
    inputs = tmp_path / "census.json"
    row = dict(id="chosen", source_class="derived_not_field_validated", **DIMENSIONS)
    inputs.write_text(json.dumps({"payload": {"trees": [dict(id="other", **DIMENSIONS), row]}}))
    parameters = tmp_path / "parameters.json"
    parameters.write_text(json.dumps({"lower_branch_survival": 1.0}))
    out = tmp_path / "export.json"
    main(["--input", str(inputs), "--identity", "chosen", "--parameters", str(parameters), "--variants", "2", "--out", str(out)])
    result = json.loads(out.read_text())
    assert len(result["records"]) == 1 and len(result["variants"]) == 2
    assert result["records"][0]["input_record"] == row
    assert result["records"][0]["source_evidence_class"] == "derived_not_field_validated"
    assert result["parameters"]["lower_branch_survival"] == 1.0
    assert all(axis["alive"] for axis in result["variants"][0]["graph"]["axes"])


@pytest.mark.parametrize("case", ["mixed", "unknown_parameter", "too_many", "missing_identity", "nonfinite"])
def test_cli_rejects_invalid_source_and_export_budget(tmp_path, case):
    """Reject ambiguous inputs, unknown parameters, and unbounded source exports."""
    inputs = tmp_path / "inputs.json"
    parameters = tmp_path / "parameters.json"
    row = dict(id="tree", **DIMENSIONS)
    inputs.write_text(json.dumps([row] * 17 if case == "too_many" else row))
    parameters.write_text(json.dumps({"invented_trait": .7}))
    args = ["--input", str(inputs), "--out", str(tmp_path / "out.json")]
    if case == "mixed": args += ["--height-m", "18"]
    if case == "unknown_parameter": args += ["--parameters", str(parameters)]
    if case == "missing_identity": args += ["--identity", "missing"]
    if case == "nonfinite": inputs.write_text('{"id":"tree","height_m":NaN}')
    with pytest.raises(SystemExit):
        main(args)


def test_authored_taper_preserves_small_positive_dbh():
    """Retain supplied breast-height diameter below the usual asset tip-radius floor."""
    from yellowstone_python.authoring.tree_architecture import stem_radius_m
    assert stem_radius_m(2., .001, 1.3) * 2 == .001


def test_cli_component_budget_stops_during_generation(tmp_path, monkeypatch):
    """Stop a bounded batch before constructing every oversized architecture variant."""
    import tools.tree_architecture as cli
    calls = []
    def oversized(*args):
        calls.append(args)
        return {"axes": [None]*100000, "shoots": []}
    monkeypatch.setattr(cli, "generate_architecture", oversized)
    with pytest.raises(SystemExit):
        cli.main(["--height-m", "18", "--dbh-m", ".32", "--crown-radius-m", "2.15",
                  "--crown-ratio", ".7", "--variants", "8", "--out", str(tmp_path/"out.json")])
    assert len(calls) == 3 and not (tmp_path/"out.json").exists()
