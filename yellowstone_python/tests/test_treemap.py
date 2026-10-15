"""Imputed tree-size distributions and spatial sampling."""
import csv
import io
import random
import zipfile

import numpy as np
import pytest

from yellowstone_python.observations.treemap import (
    TREE_MEMBER, crop_tm_ids, fetch_tree_table, profile_at_local,
    read_tree_profiles, sample_tree_reference,
)


def write_table(path, rows):
    """Write donor rows in the published tree-table columns."""
    fields = ["TM_ID", "PLT_CN", "STATUSCD", "TPA_UNADJ", "SPCD", "COMMON_NAME",
              "SCIENTIFIC_NAME", "SPECIES_SYMBOL", "DIA", "HT", "ACTUALHT", "CR",
              "SUBP", "TREE", "AGENTCD"]
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)


@pytest.fixture
def table(tmp_path):
    path = tmp_path / "trees.csv"
    write_table(path, [
        [7, "1234567890123456789", 1, 6, 108, "lodgepole pine", "Pinus contorta",
         "PICO", 10, 50, 50, 40, 1, 1, "NA"],
        [7, "1234567890123456789", 1, 12, 108, "lodgepole pine", "Pinus contorta",
         "PICO", 20, 90, 65, 20, 1, 2, "NA"],
        [7, "1234567890123456789", 2, 6, 108, "lodgepole pine", "Pinus contorta",
         "PICO", 15, 80, 60, 0, 2, 1, 30],
        [7, "1234567890123456789", 1, 6, 66, "Rocky Mountain juniper",
         "Juniperus scopulorum", "JUSC2", 5, 20, 20, 70, 2, 2, "NA"],
    ])
    return path


def test_joint_size_units_exact_cn_and_pool_weights(table):
    profiles = read_tree_profiles(table, {7})
    profile = profiles["7"]
    assert profile["plot_cn"] == "1234567890123456789"
    first = profile["trees"][0]
    assert first["dbh_cm"] == 25.4
    assert first["fia_reference_height_m"] == 15.24
    assert first["crown_ratio"] == 0.4
    assert first["sampling_weight"] == 0.25
    assert profile["trees"][1]["sampling_weight"] == 0.5
    assert profile["trees"][2]["sampling_weight"] == 1.0
    assert profile["trees"][3]["dbh_cm"] is None
    assert "stem_count" not in profile
    assert "stem_density" not in profile


def test_species_sampling_retains_joint_donor_rows(table):
    profile = read_tree_profiles(table, {7})["7"]
    rng = random.Random(1985)
    draws = [sample_tree_reference(profile, rng, species_symbol="PICO")
             for _ in range(3000)]
    assert all(t["species_symbol"] == "PICO" and t["tree_status"] == "live"
               for t in draws)
    assert {(t["dbh_cm"], t["fia_reference_height_m"], t["crown_ratio"])
            for t in draws} == {(25.4, 15.24, 0.4), (50.8, 27.432000000000002, 0.2)}
    fraction = sum(t["dbh_cm"] == 50.8 for t in draws) / len(draws)
    assert fraction == pytest.approx(2 / 3, abs=0.03)
    assert sample_tree_reference(profile, rng, species_symbol="PIEN") is None
    assert sample_tree_reference(None, rng) is None
    dead = sample_tree_reference(profile, rng, status="dead", species_symbol="PICO")
    assert dead["tree_status"] == "dead"
    assert dead["fia_actual_height_m"] == 60 * 0.3048


def test_missing_or_conflicting_donor_join_fails(table):
    with pytest.raises(ValueError, match="missing"):
        read_tree_profiles(table, {8})
    with table.open("a") as stream:
        stream.write('7,999,1,6,108,lodgepole pine,Pinus contorta,PICO,5,30,30,40,3,1,NA\n')
    with pytest.raises(ValueError, match="multiple plot"):
        read_tree_profiles(table, {7})


@pytest.mark.needs_science
def test_world_axes_nodata_and_window_edges():
    pytest.importorskip("pyproj")
    bundle = {
        "world_center_utm_m": [10, 20], "world_crs": "EPSG:32612",
        "requested_bounds_utm_m": [0, 10, 20, 30],
        "grid": {"crs": "EPSG:32612", "transform": [10, 0, 0, 0, -10, 30],
                 "tm_ids": [[7, 65535], [8, 9]], "nodata": 65535},
        "profiles": {str(i): {"tm_id": i} for i in (7, 8, 9)},
    }
    assert profile_at_local(bundle, -5, -5)["tm_id"] == 7
    assert profile_at_local(bundle, -5, 5)["tm_id"] == 8
    assert profile_at_local(bundle, 5, -5) is None
    assert profile_at_local(bundle, 5, 5)["tm_id"] == 9
    assert profile_at_local(bundle, 10, 0) is None
    with pytest.raises(ValueError, match="finite"):
        profile_at_local(bundle, float("nan"), 0)


@pytest.mark.needs_science
def test_crop_contains_fractional_boundary_pixels(tmp_path, monkeypatch):
    pytest.importorskip("pyproj")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    source = tmp_path / "national.tif"
    values = np.array([[7, 7, 7], [8, 8, 8], [9, 9, 65535]], dtype="uint16")
    with rasterio.open(source, "w", driver="GTiff", height=3, width=3, count=1,
                       dtype=values.dtype, crs="EPSG:32612", nodata=65535,
                       transform=from_origin(0, 3, 1, 1)) as raster:
        raster.write(values, 1)
    original = rasterio.open

    def open_source(path, *args, **kwargs):
        return original(source if str(path).startswith("/vsizip/") else path,
                        *args, **kwargs)

    monkeypatch.setattr(rasterio, "open", open_source)
    grid, ids = crop_tm_ids([0.2, 0.2, 2.8, 2.8], tmp_path / "subset.tif")
    assert grid["tm_ids"] == values.tolist()
    assert ids == {7, 8, 9}


def test_cache_install_is_atomic_and_rejects_changed_source(tmp_path, monkeypatch):
    from yellowstone_python.observations import treemap
    content = b"verified donor table\n"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as writer:
        writer.writestr(TREE_MEMBER, content)
    monkeypatch.setattr(treemap, "_RemoteArchive",
                        lambda *args: io.BytesIO(archive.getvalue()))
    target = tmp_path / "cache" / "trees.csv"
    replace = treemap.os.replace

    def fail_replace(*args):
        raise OSError("interrupted cache installation")

    monkeypatch.setattr(treemap.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        fetch_tree_table(target)
    assert not target.exists()
    assert list(target.parent.iterdir()) == []
    monkeypatch.setattr(treemap.os, "replace", replace)
    receipt = fetch_tree_table(target)
    assert target.read_bytes() == content
    assert receipt["bytes"] == len(content)
    target.write_bytes(b"different content")
    with pytest.raises(ValueError, match="differs"):
        fetch_tree_table(target)
    assert target.read_bytes() == b"different content"


def test_measured_dominant_height_selects_nearest_tall_donor(table):
    profile = read_tree_profiles(table, {7})["7"]
    profile["trees"][0]["fia_reference_height_m"] = 2.0
    profile["trees"][1]["fia_reference_height_m"] = 25.0
    before = [dict(t) for t in profile["trees"]]
    for seed in range(20):
        sample = sample_tree_reference(profile, random.Random(seed),
                                      species_symbol="PICO", measured_height_m=24.0)
        assert sample["dbh_cm"] == 50.8
        assert sample["fia_reference_height_m"] == 25.0
        assert sample["measured_height_m"] == 24.0
        assert sample["height_mismatch_m"] == 1.0
        assert sample["matching_method"] == "nearest_fia_reference_height_cohort"
        assert sample["matching_rule_evidence_class"] == "authored"
        assert sample["evidence_class"] == "transferred"
        assert sample["local_transfer_error"] == "unknown"
    assert profile["trees"] == before


def test_equal_distance_height_cohort_preserves_expansion_weights(table):
    profile = read_tree_profiles(table, {7})["7"]
    profile["trees"][0]["fia_reference_height_m"] = 10.0
    profile["trees"][1]["fia_reference_height_m"] = 20.0
    rng = random.Random(2020)
    samples = [sample_tree_reference(profile, rng, species_symbol="PICO",
                                    measured_height_m=15.0) for _ in range(3000)]
    assert {t["fia_reference_height_m"] for t in samples} == {10.0, 20.0}
    assert all(t["height_mismatch_m"] == 5.0 for t in samples)
    fraction = sum(t["fia_reference_height_m"] == 20.0 for t in samples) / len(samples)
    assert fraction == pytest.approx(2 / 3, abs=0.03)


def test_missing_donor_height_has_no_conditioned_reference(table):
    profile = read_tree_profiles(table, {7})["7"]
    for tree in profile["trees"]:
        tree["fia_reference_height_m"] = None
    assert sample_tree_reference(profile, random.Random(7), species_symbol="PICO",
                                 measured_height_m=24.0) is None
    assert sample_tree_reference(profile, random.Random(7), species_symbol="PICO") is not None


@pytest.mark.parametrize("height", [0, -1, float("nan"), float("inf")])
def test_invalid_measured_height_is_rejected(table, height):
    profile = read_tree_profiles(table, {7})["7"]
    with pytest.raises(ValueError, match="finite and positive"):
        sample_tree_reference(profile, random.Random(7), measured_height_m=height)
