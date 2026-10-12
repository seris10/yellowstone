import math

from yellowstone_python.common.coords import (ANCHORS, local_to_utm,
                                              sample_height, sample_index,
                                              utm_to_local)


def test_round_trip_anchors():
    for x, z in ANCHORS.values():
        e, n, h = local_to_utm(x, 12.0, z)
        x2, y2, z2 = utm_to_local(e, n, h)
        assert abs(x2 - x) < 1e-6 and abs(z2 - z) < 1e-6 and abs(y2 - 12.0) < 1e-9


def test_sample_index_uses_floor_not_truncation():
    # Negative coords: floor(-0.25) = -1, int() truncation would give 0.
    assert sample_index(-1.0, -1.0) == (511, 511)
    assert math.floor(-0.25) == -1 and int(-0.25) == 0  # documents the trap


def test_diagonal_matches_height_field():
    # Flat plane h = ix + 2*iz over 1025²: spot-check both triangle branches.
    n = 1025
    h = [float(ix + 2 * iz) for iz in range(n) for ix in range(n)]
    # Cell corner exact
    assert sample_height(h, -2048.0, -2048.0) == h[0]
    # fx+fz<=1 branch: quarter into cell (0,0)
    assert abs(sample_height(h, -2047.0, -2047.0) - (0 + 0.25 * 1 + 0.25 * 2)) < 1e-9
    # fx+fz>1 branch: three-quarters into cell (linear plane → 0.75 + 2*0.75)
    v = sample_height(h, -2045.0, -2045.0)
    assert abs(v - 2.25) < 1e-9
