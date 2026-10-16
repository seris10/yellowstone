"""Dominant-crown placement, transferred dimensions, and protected override application."""
from __future__ import annotations

import copy

import numpy as np
import pytest

from yellowstone_python.authoring.canopy_placement import (
    apply_override_plan, exclusion_masks, filter_crowns, make_override_plan, placement_records,
)
from yellowstone_python.common.io import load_json, sha256_file
from yellowstone_python.observations import treemap


def _tree(stable_id="census_lidar_a", *, x=1.25, z=2.5, height=24.25, radius=1.234):
    """Return an observed dominant crown with exact source dimensions."""
    return {"stable_id": stable_id, "x": x, "z": z, "height_m": height,
            "crown_r_m": radius, "crown_area_m2": 4.785, "ix": 1, "iz": 2}


def _record(identifier, x=1, z=1, kind="pine", **fields):
    """Return a placement record for bounded override checks."""
    return {"id": identifier, "kind": kind, "position": [x, 100, z], **fields}


@pytest.fixture
def donor_bundle(monkeypatch):
    """Provide joint FIA donor rows with an identity coordinate transform."""
    class Identity:
        def transform(self, x, y):
            return x, y

    monkeypatch.setattr(treemap, "_transformer", lambda *args: Identity())
    rows = [
        {"species_symbol": "PICO", "tree_status": "live", "sampling_weight": 100,
         "fia_reference_height_m": 2, "dbh_cm": 4, "crown_ratio": 0.8},
        {"species_symbol": "PICO", "tree_status": "live", "sampling_weight": 0.1,
         "fia_reference_height_m": 25, "dbh_cm": 33, "crown_ratio": 0.23},
        {"species_symbol": "PICO", "tree_status": "dead", "sampling_weight": 100,
         "fia_reference_height_m": 24.25, "dbh_cm": 50, "crown_ratio": 0},
        {"species_symbol": "PIEN", "tree_status": "live", "sampling_weight": 100,
         "fia_reference_height_m": 24.25, "dbh_cm": 60, "crown_ratio": 0.9},
    ]
    return {
        "world_center_utm_m": [500, 1000], "world_crs": "EPSG:32612",
        "requested_bounds_utm_m": [450, 950, 550, 1050],
        "grid": {"crs": "EPSG:32612", "transform": [100, 0, 450, 0, -100, 1050],
                 "tm_ids": [[7]], "nodata": 65535},
        "profiles": {"7": {"tm_id": 7, "plot_cn": "1234567890123456789", "trees": rows}},
    }


def test_deterministic_placement_retains_measured_dimensions_and_joint_fia_metadata(donor_bundle):
    """Keep observed dimensions while conditioning transferred FIA references on height."""
    trees = [_tree(), _tree("census_lidar_b", x=-4.5, z=3.25, height=2.25, radius=0.625)]
    original = copy.deepcopy(trees)
    bundle_original = copy.deepcopy(donor_bundle)
    ground = lambda x, z: 100 + x + z / 2
    records, missing = placement_records(trees, ground, donor_bundle)
    repeated, repeated_missing = placement_records(trees, ground, donor_bundle)
    reversed_records, _ = placement_records(list(reversed(trees)), ground, donor_bundle)
    assert records == repeated
    assert missing == repeated_missing == {}
    assert {r["id"]: r for r in records} == {r["id"]: r for r in reversed_records}
    assert trees == original
    assert donor_bundle == bundle_original
    for tree, record in zip(trees, records):
        assert record["id"] == record["stable_id"] == tree["stable_id"]
        assert record["position"] == [tree["x"], ground(tree["x"], tree["z"]), tree["z"]]
        assert record["height_m"] == tree["height_m"]
        assert record["crown_radius_m"] == tree["crown_r_m"]
        assert record["crown_area_m2"] == tree["crown_area_m2"]
        assert record["source_class"] == "derived_not_field_validated"
        donor = record["fia_reference"]
        assert donor["evidence_class"] == "transferred"
        assert donor["source_class"] == "imputed"
        assert donor["measured_height_m"] == tree["height_m"]
        assert donor["height_mismatch_m"] == (0.75 if tree["height_m"] > 20 else 0.25)
        assert donor["matching_method"] == "nearest_fia_reference_height_cohort"
        assert donor["matching_rule_evidence_class"] == "authored"
        assert donor["local_transfer_error"] == "unknown"
        assert donor["species_symbol"] == "PICO" and donor["tree_status"] == "live"
        assert record["dbh_m"] == donor["dbh_cm"] / 100
        assert record["crown_ratio"] == donor["crown_ratio"]
    assert records[0]["dbh_m"] == 0.33
    assert records[0]["height_m"] != records[0]["fia_reference"]["fia_reference_height_m"]


def test_missing_fia_reference_keeps_observed_crown_and_unknown_dimensions():
    """Retain observed crown records when transferred donor dimensions are unavailable."""
    records, missing = placement_records([_tree()], lambda x, z: 111)
    assert len(records) == 1
    assert records[0]["height_m"] == 24.25
    assert records[0]["crown_radius_m"] == 1.234
    assert "dbh_m" not in records[0] and "crown_ratio" not in records[0]
    assert missing == {"compatible_fia_donor_unavailable": 1, "live_crown_ratio_unavailable": 1}


@pytest.mark.parametrize("field", ["crown_ratio", "dbh_cm"])
def test_missing_fia_dimension_does_not_replace_observed_dimensions(donor_bundle, field):
    """Keep missing donor dimensions unavailable while retaining the observed crown."""
    donor_bundle["profiles"]["7"]["trees"][1][field] = None
    records, missing = placement_records([_tree()], lambda x, z: 111, donor_bundle)
    assert records[0]["height_m"] == 24.25
    assert records[0]["crown_radius_m"] == 1.234
    if field == "crown_ratio":
        assert "crown_ratio" not in records[0]
        assert missing["live_crown_ratio_unavailable"] == 1
    else:
        assert "dbh_m" not in records[0]


def test_override_plan_preserves_manual_outside_replacements_and_source_objects():
    """Remove generated in-window pines while preserving protected placement layers."""
    base = {"trees": [_record("pine_0001"), _record("pine_0002", 2, 2),
                      _record("pine_upper_edge", 10, 2), _record("pine_outside", -1, 2),
                      _record("manual_base", 3, 3), _record("pine_other_kind", 4, 4, "oak")]}
    additions = [_record("prop_inside"), _record("census_lidar_inside", 2, 2),
                 {"stable_id": "census_lidar_without_id", "kind": "pine", "position": [3, 100, 3]},
                 _record("prop_outside", -1, 2), _record("manual_added", 4, 4),
                 _record("prop_other_kind", 4, 4, "grass"), _record("census_lidar_edge", 5, 10)]
    replacements = {"pine_0002": {"kind": "pine", "position": [2, 102, 2], "manual": True}}
    overrides = {"schema": 1, "remove": ["protected_prior_removal"], "replace": replacements,
                 "add": additions, "owner_metadata": {"authority": "manual"}}
    records = [_record("census_lidar_observed", 6, 6, height_m=20)]
    original_base, original_overrides, original_records = map(copy.deepcopy, (base, overrides, records))
    plan = make_override_plan(base, overrides, records, [0, 0, 10, 10])
    assert plan["remove"] == ["pine_0001", "protected_prior_removal"]
    assert plan["replace"] == replacements
    assert plan["owner_metadata"] == {"authority": "manual"}
    assert plan["add"] == additions[3:] + records
    assert plan["canopy_source"]["generated_base_removed"] == 1
    assert plan["canopy_source"]["generated_add_removed"] == 3
    assert plan["canopy_source"]["protected_add_retained"] == 4
    assert plan["canopy_source"]["placement_count"] == 1
    assert plan["canopy_source"]["status"] == "derived_not_field_validated"
    assert base == original_base and overrides == original_overrides and records == original_records
    plan["replace"]["pine_0002"]["position"][1] = 0
    assert overrides == original_overrides


def test_override_plan_lower_edges_are_inside_and_upper_edges_are_outside():
    """Use half-open bounds when replacing generated base pines."""
    base = {"trees": [_record("pine_lower", 0, 0), _record("pine_x_upper", 10, 0),
                      _record("pine_z_upper", 0, 10), _record("pine_below", -0.001, 0)]}
    plan = make_override_plan(base, {"remove": [], "replace": {}, "add": []}, [], [0, 0, 10, 10])
    assert plan["remove"] == ["pine_lower"]


def test_apply_plan_preserves_exact_source_bytes_before_atomic_write(tmp_path):
    """Preserve source formatting byte for byte before applying the reviewed plan."""
    destination = tmp_path / "overrides.json"
    original = b'{ "schema": 1, "add": [] }\r\n'
    destination.write_bytes(original)
    expected = sha256_file(destination)
    backup = tmp_path / "backups" / "overrides.json"
    plan = {"schema": 1, "add": [_record("census_lidar_a")]}
    apply_override_plan(plan, destination, expected_sha256=expected, backup=backup)
    assert backup.read_bytes() == original
    assert sha256_file(backup) == expected
    assert load_json(destination) == plan


def test_apply_plan_rejects_changed_source_without_writing_backup(tmp_path):
    """Reject a changed override source before creating backups or replacing data."""
    destination = tmp_path / "overrides.json"
    destination.write_bytes(b'{"schema": 1, "add": []}\n')
    expected = sha256_file(destination)
    changed = b'{"schema": 1, "add": [], "manual": true}\n'
    destination.write_bytes(changed)
    backup = tmp_path / "backups" / "overrides.json"
    with pytest.raises(ValueError, match="changed"):
        apply_override_plan({"schema": 1, "add": []}, destination,
                            expected_sha256=expected, backup=backup)
    assert destination.read_bytes() == changed
    assert not backup.exists()
    assert not backup.parent.exists()


def test_filter_crowns_reports_first_mapped_exclusion_reason():
    """Retain only crown centers outside mapped exclusion pixels."""
    mineral = np.zeros((3, 3), dtype=bool)
    river = np.zeros((3, 3), dtype=bool)
    mineral[0, 0] = river[0, 0] = True
    river[1, 1] = True
    trees = [{"stable_id": str(index), "ix": index, "iz": index} for index in range(3)]
    accepted, reasons = filter_crowns(trees, {"mineral": mineral, "river": river})
    assert accepted == [trees[2]]
    assert reasons == {"mineral": 1, "river": 1}


@pytest.mark.needs_science
def test_exclusion_masks_keep_disconnected_river_and_route_features_separate(monkeypatch):
    """Rasterize separated mapped polylines without creating a cross-gap segment."""
    pytest.importorskip("affine")
    pytest.importorskip("rasterio")
    pytest.importorskip("shapely")
    from yellowstone_python.land import vegetation
    monkeypatch.setattr(vegetation, "HALF", 0)
    monkeypatch.setattr(vegetation, "STEP", 1)
    habitat = np.zeros((40, 40, 1), dtype=float)
    world = {"pools": [], "rivers": [
        {"width": 2, "points": [[2, 0, 2], [5, 0, 2]]},
        {"width": 2, "points": [[30, 0, 30], [34, 0, 30]]}], "routes": [
        {"kind": "trail", "points": [[2, 0, 2], [5, 0, 2]]},
        {"kind": "trail", "points": [[30, 0, 30], [34, 0, 30]]}]}
    masks = exclusion_masks(world, habitat, (40, 40), [0, 0, 40, 40], 1)
    assert masks["river"][2, 3]
    assert masks["river"][30, 32]
    assert not masks["river"][16, 17]
    assert not masks["river_clearance"][16, 17]
    assert not masks["route_clearance"][16, 17]
