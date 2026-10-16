"""Preferred raster footprints, exclusions, and measured-support limits."""
from pathlib import Path

import numpy as np
import pytest

from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.pipeline.stages.vegetation import _canopy_from_census, _canopy_from_height


def _products(tmp_path, values, *, interpreted=None):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    out = tmp_path / "lidar_canopy"
    out.mkdir()
    artifacts = {}
    for name, data in [("canopy_height", values), ("interpreted_canopy_height", interpreted)]:
        if data is None:
            continue
        path = out / f"{name}.tif"
        with rasterio.open(path, "w", driver="GTiff", height=8, width=8, count=1,
                           dtype="float32", nodata=np.nan, transform=from_origin(-2, 2, .5, .5)) as dst:
            dst.write(np.asarray(data, dtype="float32"), 1)
        artifacts[name] = {"path": path.name, "sha256": sha256_file(path)}
    metadata = out / "canopy_height.provenance.json"
    write_json_atomic(metadata, {"schema": "yellowstone.canopy_height.v1", "status": "measured",
                                "extent_m": [-2, -2, 2, 2], "resolution_m": .5, "artifacts": artifacts})
    census = tmp_path / "census.json"
    write_json_atomic(census, {"trees": [{"x": 0, "z": 0, "crown_r_m": 10}] * 10})
    return metadata, census


def test_canopy_authority_uses_pixel_footprint_without_overlapping_circle_double_count(tmp_path):
    values = np.zeros((8, 8))
    values[:, :4] = 12
    _, census = _products(tmp_path, values)
    fraction, source = _canopy_from_census((0, 0), 1.5, census)
    assert fraction == .5
    assert source.startswith("measured_canopy_height_footprint")


def test_mapped_exclusions_override_unclassified_high_surface_returns(tmp_path):
    raw = np.full((8, 8), 49)
    interpreted = np.zeros((8, 8))
    metadata, census = _products(tmp_path, raw, interpreted=interpreted)
    fraction, quality = _canopy_from_height((0, 0), 1.5, metadata)
    assert fraction == 0
    assert quality["mapped_nonvegetation_excluded"] is True
    assert _canopy_from_census((0, 0), 1.5, census)[0] == 0


def test_missing_support_is_labeled_and_not_counted_as_bare_ground(tmp_path):
    values = np.full((8, 8), 12.)
    values[:, :4] = np.nan
    metadata, census = _products(tmp_path, values)
    fraction, quality = _canopy_from_height((0, 0), 1.5, metadata)
    assert fraction is None
    assert quality["valid_fraction"] == .5
    assert _canopy_from_census((0, 0), 1.5, census)[1] == "illustrative_fallback_missing_canopy_height_support"


def test_canopy_source_rejects_corrupt_bytes_and_respects_coverage_window(tmp_path):
    metadata, _ = _products(tmp_path, np.zeros((8, 8)))
    assert _canopy_from_height((2, 0), 1, metadata)[1]["reason"] == "outside_measured_canopy_window"
    (Path(metadata).parent / "canopy_height.tif").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        _canopy_from_height((0, 0), 1, metadata)
