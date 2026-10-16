import json
import math

import pytest

from yellowstone_python.thermal_features.pool_crust import build_all, buffered_ring, depth_at, exclusion_violations, in_apron, in_water, make_ramp_stops, r_water_from_area, radial_temp, render_apron_tiles, render_cross_section, render_ramp, shell_for_pool, validate_ramp_stops



def _pools():
    return {p["id"]: p for p in json.load(open(WORLD))["pools"]}


def test_mapped_outline_preserved():
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    # Effective radius from area 6723 m2 about 46 m; bounding per research ~94x102.
    assert abs(gp["r_water_m"] - 46.3) < 1.0
    # Shell radii strictly grow; outline itself untouched (no world.json write).
    assert gp["r_water_m"] < gp["r_shelf_m"] < gp["r_rim_m"] < gp["r_apron_m"]


def test_center_hotter_than_edge():
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    assert radial_temp(0, gp["r_water_m"], 72.0, 42.0) == 72.0
    # Edge temperature is exactly attained at the water edge (no residual).
    assert radial_temp(gp["r_water_m"], gp["r_water_m"], 72.0, 42.0) == 42.0
    assert radial_temp(gp["r_water_m"] * 3, gp["r_water_m"], 72.0, 42.0) == 42.0
    # Per-pool stops vary (no universal palette): deep Grand Prismatic differs from shallow Opal.
    op = shell_for_pool(pools["pool_1029_0"])
    assert gp["color_stops"][0] != op["color_stops"][0]


def test_exclusion_mask_catches_forest_in_apron():
    pools = _pools()
    shells = build_all([pools["pool_1034_0"]])
    cx, cz = shells[0]["center_xz"]
    bad = exclusion_violations([{"id": "t1", "x": cx, "z": cz},
                                {"id": "t2", "x": cx + 2000, "z": cz}], shells)
    assert [b["point_id"] for b in bad] == ["t1"]
    assert in_water(cx, cz, shells[0]) and in_apron(cx, cz, shells[0])


def test_mapped_ring_carried_not_circular():
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    assert len(gp["ring"]) == len(pools["pool_1034_0"]["ring"]) == 14
    assert 0.0 < gp["outline_circularity"] <= 1.0
    # Near-vertex interior point is water (polygon-exact); far exterior is not.
    vx, vz = gp["ring"][0]
    cx, cz = gp["center_xz"]
    ix, iz = cx * 0.1 + vx * 0.9, cz * 0.1 + vz * 0.9
    assert in_water(ix, iz, gp)
    assert not in_water(cx + 2 * gp["max_radius_m"], cz, gp)
    assert not in_apron(cx + 2 * gp["max_radius_m"] + 50, cz, gp)


def test_apron_reuses_geometry_and_tracks_mutations(monkeypatch):
    from yellowstone_python.thermal_features import pool_crust
    pool_crust._apron_ring.cache_clear()
    original = pool_crust.buffered_ring
    calls = []

    def counted(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(pool_crust, "buffered_ring", counted)
    shell = {"ring": [[-1, -1], [1, -1], [1, 1], [-1, 1]],
             "center_xz": [0, 0], "apron_margin_m": 0}
    assert in_apron(0, 0, shell)
    assert not in_apron(2, 0, shell)
    assert len(calls) == 1
    shell["apron_margin_m"] = 2
    assert in_apron(2, 0, shell)
    assert len(calls) == 2
    shell["ring"] = [[10, 10], [12, 10], [12, 12], [10, 12]]
    assert not in_apron(2, 0, shell)
    assert len(calls) == 3
    pool_crust._apron_ring.cache_clear()


def test_make_ramp_stops_is_pure():
    pools = _pools()
    shell = shell_for_pool(pools["pool_1034_0"])
    before = json.dumps(shell, sort_keys=True)
    result = make_ramp_stops(shell)
    assert json.dumps(shell, sort_keys=True) == before
    assert set(result) == {"stops", "ramp_params"}
    assert len(result["stops"]) == len(shell["color_stops"])
    validate_ramp_stops(result["stops"])


def test_ramp_stop_fractions_are_clamped_and_ordered():
    pools = _pools()
    for pid in _pools():
        stops = shell_for_pool(pools[pid])["color_stops"]
        validate_ramp_stops(stops)
        assert all(0.0 <= s["fraction"] <= 1.3 for s in stops)


def test_render_ramp_rejects_single_pixel_width(tmp_path):
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    with pytest.raises(ValueError, match="width"):
        render_ramp(gp, str(tmp_path / "ramp.png"), w=1)


def test_render_ramp_creates_parent_directory(tmp_path):
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    path = tmp_path / "nested" / "deeper" / "ramp.png"
    assert render_ramp(gp, str(path), w=32) == str(path)
    assert path.exists()


def test_depth_at_rejects_bad_geometry():
    with pytest.raises(ValueError, match="r_water"):
        depth_at(1.0, 0.0, 5.0, 1.0)
    with pytest.raises(ValueError, match="shelf_mult"):
        depth_at(1.0, 10.0, 5.0, 1.0, shelf_mult=1.0)
    with pytest.raises(ValueError, match="depth_center_m"):
        depth_at(1.0, 10.0, -1.0, 1.0)


def test_radial_temp_rejects_zero_radius():
    with pytest.raises(ValueError, match="r_water"):
        radial_temp(1.0, 0.0, 60.0, 40.0)


def test_buffered_ring_rejects_negative_margin():
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    with pytest.raises(ValueError, match="margin"):
        buffered_ring(gp["ring"], gp["center_xz"], -1.0)


def test_buffer_method_is_labeled():
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    assert gp["apron_buffer_method"]
    assert "not_guaranteed" in gp["apron_buffer_method"] or \
        gp["apron_buffer_method"] == "shapely_minkowski_buffer"


def test_shell_validation_refuses_bad_inputs():
    pools = _pools()
    gp = dict(pools["pool_1034_0"])
    bad_rings = {"short": [[0, 0], [1, 1]],
                 "nan": [[0, 0], [float("nan"), 1], [1, 0]],
                 "flat": [[0, 0], [0, 0], [0, 0]]}
    for label, ring in bad_rings.items():
        with pytest.raises(ValueError):
            shell_for_pool({**gp, "ring": ring})
    with pytest.raises(ValueError, match="area"):
        shell_for_pool({**gp, "area_m2": 0.0})
    with pytest.raises(ValueError, match="center"):
        shell_for_pool({**gp, "center": [0.0, float("nan")]})


def test_shell_records_area_disagreement_diagnostic():
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    assert gp["mapped_area_m2"] > 0
    assert gp["area_disagreement_pct"] >= 0.0
    # Force a disagreement to prove the diagnostic moves.
    inflated = shell_for_pool({**pools["pool_1034_0"], "area_m2": 1e6})
    assert inflated["area_disagreement_pct"] > gp["area_disagreement_pct"]


def test_outflow_channel_is_keyed_by_source_id():
    pools = _pools()
    shells = {s["id"]: s for s in build_all(list(pools.values()))}
    excelsior = [s for s in shells.values()
                 if s["name"] == "Excelsior Geyser Crater"][0]
    assert excelsior["outflow_channel"] == "authored_excelsior_outflow_01"
    others = [s for s in shells.values() if s is not excelsior]
    assert all(s["outflow_channel"] is None for s in others)


def test_render_apron_tiles_fills_the_apron(tmp_path):
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    paths = render_apron_tiles([gp], str(tmp_path / "tiles"), size=128)
    assert len(paths) == 1
    from PIL import Image
    img = Image.open(paths[0]).convert("L")
    size = img.size[0]
    cx, cz = gp["center_xz"]
    span = gp["r_apron_m"] * 1.2

    def px_of(x, z):
        return (round((x - (cx - span)) / (2 * span) * (size - 1)),
                round((z - (cz - span)) / (2 * span) * (size - 1)))
    center_val = img.getpixel(px_of(cx, cz))
    assert center_val == 200  # mapped water
    vx, vz = gp["ring"][0]
    r = math.hypot(vx - cx, vz - cz)
    margin = gp["apron_margin_m"]
    ax = cx + (vx - cx) * (r + 0.5 * margin) / r
    az = cz + (vz - cz) * (r + 0.5 * margin) / r
    apron_val = img.getpixel(px_of(ax, az))
    assert apron_val == 255  # apron band between outline and buffer is filled


def test_render_cross_section_writes_metadata_sidecar(tmp_path):
    pools = _pools()
    gp = shell_for_pool(pools["pool_1034_0"])
    path = str(tmp_path / "section.png")
    render_cross_section(gp, path, w=64, h=24)
    meta = json.loads(open(f"{path}.meta.json").read())
    assert meta["represents_mapped_outline"] is False
    assert meta["section_geometry"] == "radial"
    assert meta["pool_id"] == gp["id"]

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'WORLD', resolved_paths['WORLD_JSON'], raising=False)
