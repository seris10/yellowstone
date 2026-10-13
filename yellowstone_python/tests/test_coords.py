import math

from yellowstone_python.common import coords
from yellowstone_python.common.coords import (ANCHORS, GEOID_MODEL, GRID,
                                              HALF, HORIZONTAL_DATUM,
                                              VERTICAL_DATUM, local_to_utm,
                                              sample_height, sample_index,
                                              utm_to_local)


def test_round_trip_anchors():
    for x, z in ANCHORS.values():
        e, n, h = local_to_utm(x, 12.0, z)
        x2, y2, z2 = utm_to_local(e, n, h)
        assert abs(x2 - x) < 1e-6 and abs(z2 - z) < 1e-6 and abs(y2 - 12.0) < 1e-9


def test_sample_index_uses_floor_not_truncation():
    assert sample_index(-1.0, -1.0) == (511, 511)
    assert math.floor(-0.25) == -1 and int(-0.25) == 0


def test_diagonal_matches_height_field():
    n = 1025
    h = [float(ix + 2 * iz) for iz in range(n) for ix in range(n)]
    assert sample_height(h, -2048.0, -2048.0) == h[0]
    assert abs(sample_height(h, -2047.0, -2047.0) - (0 + 0.25 * 1 + 0.25 * 2)) < 1e-9
    v = sample_height(h, -2045.0, -2045.0)
    assert abs(v - 2.25) < 1e-9


def test_datum_metadata_present():
    assert HORIZONTAL_DATUM == "WGS 84"
    assert VERTICAL_DATUM == "NAVD88"
    assert GEOID_MODEL == "GEOID12B"
    doc = local_to_utm.__doc__ or ""
    for token in ("WGS 84", "NAVD88", "GEOID12B"):
        assert token in doc, f"{token!r} missing from local_to_utm docstring"


def test_sample_height_corner_no_epsilon():
    n = GRID
    h = [float(ix + iz) for iz in range(n) for ix in range(n)]
    v = sample_height(h, HALF - 1e-9, HALF - 1e-9)
    expected = h[(GRID - 1) * GRID + (GRID - 1)]
    assert abs(v - expected) < 1e-9
    assert sample_height(h, -HALF, -HALF) == h[0]


def test_sample_height_clamp_module_present():
    assert coords.GRID == GRID
