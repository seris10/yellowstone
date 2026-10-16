"""Measured canopy acquisition and raster contracts."""
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from yellowstone_python.observations.lidar import intersecting_tiles, las_header, pit_fill, rasterize_highest_first
from yellowstone_python.census.canopy_census import canopy_coverage_field, detect_lidar, lidar_window_radius, to_world


def test_detail_window_intersects_twelve_delivered_tiles():
    names = [f"USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ{x:03d}{y:03d}.laz"
             for x in [120, 125, 130, 135] for y in [295, 300, 305, 310]]
    selected = intersecting_tiles(names, (512312.595, 4929559.044, 513592.595, 4930839.044))
    assert len(selected) == 12
    assert all(not name.endswith("310.laz") for name in selected)


def test_las_header_reads_extended_point_count_and_bounds():
    data = bytearray(375)
    data[:4] = b"LASF"
    data[24:26] = bytes([1, 4])
    data[104] = 134
    struct.pack_into("<Q", data, 247, 8268421)
    struct.pack_into("<6d", data, 179, 512999.99, 512500, 4930499.99, 4930000, 3558.11, 1882.69)
    header = las_header(data)
    assert header["point_count"] == 8268421
    assert header["point_format"] == 6
    assert header["bounds_utm_m"] == [512500, 4930000, 512999.99, 4930499.99]


def test_first_return_raster_filters_noise_withheld_and_other_classes():
    surface = np.full((2, 2), -np.inf, dtype=np.float32)
    support = np.zeros((2, 2), dtype=np.uint32)
    x = np.full(8, 0.25)
    y = np.full(8, 0.75)
    z = np.array([5, 7, 50, 60, 70, 80, 90, 100.0])
    result = rasterize_highest_first(surface, support, x, y, z,
        np.array([1, 2, 7, 18, 9, 1, 1, 21]), np.array([1, 1, 1, 1, 1, 2, 1, 1]),
        np.array([False, False, False, False, False, False, True, False]),
        SimpleNamespace(a=0.5, c=0, e=-0.5, f=1))
    assert surface[0, 0] == 7
    assert support[0, 0] == 2
    assert result == {"eligible_first_returns": 2, "first_returns_inside": 2}
    assert np.isneginf(surface[1, 1])


def test_pit_filling_preserves_missing_cells_and_ground_residuals():
    surface = np.array([[5, 5, 5], [5, 1, 5], [5, np.nan, 5]], dtype=np.float32)
    filled = pit_fill(surface)
    assert filled[1, 1] == 5
    assert np.isnan(filled[2, 1])
    negative = np.full((3, 3), -0.2, dtype=np.float32)
    assert np.array_equal(pit_fill(negative), negative)


def test_dominant_detector_segments_supported_touching_crowns():
    y, x = np.mgrid[:48, :48]
    chm = np.maximum(12 * np.exp(-((x - 16) ** 2 + (y - 24) ** 2) / 18),
                     18 * np.exp(-((x - 28) ** 2 + (y - 24) ** 2) / 18))
    chm[0, :] = np.nan
    trees, labels = detect_lidar(chm, return_labels=True)
    assert len(trees) == 2
    assert sorted(t["height_m"] for t in trees) == [12, 18]
    assert all(t["crown_area_m2"] > 0 for t in trees)
    assert not labels[0].any()
    assert np.all((labels > 0) <= (np.isfinite(chm) & (chm >= 2)))
    from scipy.ndimage import distance_transform_edt
    markers = np.zeros(chm.shape, dtype=int)
    for index, tree in enumerate(trees, 1):
        markers[tree["iz"], tree["ix"]] = index
    nearest = distance_transform_edt(markers == 0, return_distances=False, return_indices=True)
    owner = markers[nearest[0], nearest[1]]
    assert np.all(labels[labels > 0] == owner[labels > 0])
    world = to_world(trees, 48, 48, extent=(-12, -12, 12, 12))
    assert len({t["stable_id"] for t in world}) == 2
    assert world == to_world(trees, 48, 48, extent=(-12, -12, 12, 12))


@pytest.mark.parametrize("invalid", [True, "2", np.inf, np.nan])
def test_window_rejects_invalid_public_numbers(invalid):
    with pytest.raises(ValueError):
        lidar_window_radius(10, slope=invalid)


def test_coverage_separates_raw_returns_exclusions_and_missing_support():
    chm = np.array([[10, 10], [np.nan, 0]], dtype=float)
    excluded = np.array([[True, False], [False, False]])
    field = canopy_coverage_field(chm, [{"x": .75, "z": .25}], extent=(0, 0, 1, 1),
                                  cell_size_m=1, excluded_mask=excluded)
    cell = field["cells"][0]
    assert cell["valid_fraction"] == .75
    assert cell["raw_above_height_threshold_fraction"] == pytest.approx(2 / 3)
    assert cell["canopy_cover_fraction"] == pytest.approx(1 / 3)
    assert cell["observed_canopy_area_m2"] == .25
    assert cell["dominant_count_lower_bound"] == 1
    assert cell["total_stem_density_per_ha"] is None
    assert cell["subcanopy_stem_density_per_ha"] is None


def test_empty_detector_does_not_infill_unsupported_or_bare_ground():
    assert detect_lidar(np.full((10, 10), np.nan)) == []
    assert detect_lidar(np.zeros((10, 10))) == []


def test_catalog_cache_is_verified_and_missing_tiles_are_rejected(tmp_path, monkeypatch):
    pytest.importorskip("pyproj")
    import json
    from yellowstone_python.observations import lidar
    from yellowstone_python.common.io import sha256_file, write_json_atomic
    bounds = (512312.595, 4929559.044, 513592.595, 4930839.044)
    names = [f"USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ{x:03d}{y:03d}.laz"
             for x in [120, 125, 130, 135] for y in [295, 300, 305]]
    body = tmp_path / "lpc_catalog_response.json"
    body.write_text(json.dumps({"items": [{"downloadURL": lidar.TILE_BASE_URL + name,
                                           "sizeInBytes": 1000} for name in names]}))
    receipt = tmp_path / "lpc_catalog.provenance.json"
    def seal():
        write_json_atomic(receipt, {"bounds_utm_m": list(bounds), "response_sha256": sha256_file(body)})
    seal()
    def blocked(*args, **kwargs):
        raise AssertionError("cached resume must not perform source discovery")
    monkeypatch.setattr(lidar.urllib.request, "urlopen", blocked)
    assert lidar.catalog_tiles(bounds, tmp_path)[0] == sorted(names)
    items = json.loads(body.read_text())
    items["items"].pop()
    body.write_text(json.dumps(items))
    with pytest.raises(ValueError, match="checksum"):
        lidar.catalog_tiles(bounds, tmp_path)
    seal()
    with pytest.raises(ValueError, match="missing required"):
        lidar.catalog_tiles(bounds, tmp_path)


def test_cached_tile_must_match_catalog_bytes_as_well_as_its_receipt(tmp_path):
    from yellowstone_python.observations.lidar import fetch_tile
    from yellowstone_python.common.io import sha256_file, write_json_atomic
    name = "USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ125300.laz"
    tile = tmp_path / name
    tile.write_bytes(b"cached source bytes")
    write_json_atomic(tmp_path / f"{name}.provenance.json",
                      {"sha256": sha256_file(tile), "bytes": tile.stat().st_size})
    assert fetch_tile(name, tmp_path, expected_bytes=tile.stat().st_size)["bytes"] == tile.stat().st_size
    with pytest.raises(ValueError, match="source catalog"):
        fetch_tile(name, tmp_path, expected_bytes=tile.stat().st_size + 1)
