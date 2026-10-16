"""Observation-bound residual canopy area and compact renderer coordinates."""
from pathlib import Path

import numpy as np
import pytest

from yellowstone_python.census.canopy_residual import crown_circle_mask, residual_canopy, write_residual_canopy
from yellowstone_python.common.io import sha256_file


def test_residual_partition_conserves_observed_area_and_preserves_missing_support():
    height = np.array([[5, 10], [np.nan, 0]])
    cores = np.array([[True, False], [True, False]])
    residual, covered, valid = residual_canopy(height, cores)
    assert residual.tolist() == [[False, True], [False, False]]
    assert covered.tolist() == [[True, False], [False, False]]
    assert valid.tolist() == [[True, True], [False, True]]
    assert not (residual & covered).any()
    assert np.array_equal(residual | covered, np.isfinite(height) & (height >= 2))


def test_compact_export_uses_real_residual_top_height_ground_datum_and_exact_coverage(tmp_path):
    pytest.importorskip("PIL")
    heights = np.array([[10, 20, 0, np.nan], [30, 40, 0, 0],
                        [0, 0, 12, 14], [0, 0, 16, 18]], dtype=float)
    ground = np.full((4, 4), 2220.)
    metadata = write_residual_canopy(heights, ground, [], tmp_path, extent=(-1, -1, 1, 1),
                                    source_sha256={"source": "frozen"}, cell_size=1)
    assert metadata["width"] == metadata["height"] == 2
    assert metadata["first_cell_x_m"] == metadata["first_cell_z_m"] == -.5
    assert metadata["row_step_z_m"] == 1
    assert metadata["conservation_residual_m2"] == 0
    assert metadata["observed_canopy_area_m2"] == 2
    arrays = {}
    for name, artifact in metadata["artifacts"].items():
        path = Path(tmp_path) / artifact["path"]
        assert artifact["sha256"] == sha256_file(path)
        assert artifact["bytes"] == path.stat().st_size
        if path.suffix == ".f32":
            arrays[name] = np.fromfile(path, dtype="<f4").reshape(2, 2)
    assert arrays["ground_scene_y"].tolist() == [[20, 20], [20, 20]]
    assert arrays["canopy_top_scene_y"][0, 0] == 45
    assert arrays["canopy_top_scene_y"][1, 1] == 35
    assert np.isnan(arrays["canopy_top_scene_y"][0, 1])
    assert arrays["cover_fraction"].tolist() == [[1, 0], [0, 1]]
    assert arrays["valid_fraction"][0, 1] == .75


def test_core_circle_union_is_area_based_and_does_not_double_count():
    tree = {"x": 0, "z": 0, "crown_r_m": 1}
    one = crown_circle_mask([tree], (8, 8), (-2, -2, 2, 2), .5)
    repeated = crown_circle_mask([tree, tree], (8, 8), (-2, -2, 2, 2), .5)
    assert np.array_equal(one, repeated)
    assert one.any() and not one.all()


def test_residual_rejects_mismatched_mask_and_unmatched_ground(tmp_path):
    with pytest.raises(ValueError, match="boolean"):
        residual_canopy(np.ones((4, 4)), np.ones((4, 4)))
    with pytest.raises(ValueError, match="matched ground"):
        write_residual_canopy(np.ones((4, 4)), np.ones((2, 2)), [], tmp_path,
                              extent=(0, 0, 2, 2), source_sha256={})


@pytest.mark.parametrize("invalid", [True, "2200", np.nan, np.inf])
def test_render_datum_offset_rejects_invalid_numeric_input(tmp_path, invalid):
    with pytest.raises(ValueError):
        write_residual_canopy(np.ones((4, 4)), np.ones((4, 4)), [], tmp_path,
                              extent=(0, 0, 2, 2), source_sha256={}, ground_offset=invalid)
