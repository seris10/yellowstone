"""Core and master height composition, ownership and feature page checks."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from yellowstone_python.park_runtime.feature_pages import river_features, verify_feature_pages
from yellowstone_python.park_runtime.terrain_pack import (
    build_composed_pack, build_pack, carve_river_beds, compose_window, core_window, coverage_report,
    load_core, river_bed_segments, triangle_sample)

DATA = Path(__file__).resolve().parents[3]/"yellowstone_midway"/"data"
needs_data = pytest.mark.skipif(not (DATA/"terrain.f32").exists() or not (DATA/"core_terrain").exists(),
                                reason="real Midway source data is absent")


def write_core(directory: Path, x_min=40., z_min=24., nx=49, nz=49):
    directory.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:nz, 0:nx]
    base = (30+0.5*xx+0.25*yy+np.sin(xx/3.0)).astype("<f4")
    micro = (0.04*np.cos(yy/2.0)+0.04).astype("<f4")
    files = {"core_heightfield.f32": base, "core_microrelief.f32": micro}
    layers = {}
    for name, key in (("core_heightfield.f32", "core_heightfield_m"), ("core_microrelief.f32", "core_microrelief_m")):
        raw = files[name].tobytes()
        (directory/name).write_bytes(raw)
        layers[key] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "dtype": "<f4", "shape": [nz, nx]}
    (directory/"stitch.json").write_text("{}")
    meta = {"schema": "yellowstone.core_terrain.v1", "vertical_origin_m": 2200.0,
            "frame": {"crs": "EPSG:32612", "origin_utm_m": [512952.5950985841, 4930199.044097667]},
            "grid": {"cell_m": 1.0, "x_min_m": x_min, "x_max_m": x_min+nx-1, "z_min_m": z_min,
                     "z_max_m": z_min+nz-1, "nx": nx, "nz": nz},
            "layers": layers}
    (directory/"core_terrain.json").write_text(json.dumps(meta))
    return base.astype(np.float64)+micro.astype(np.float64)


def master_raster():
    yy, xx = np.mgrid[0:129, 0:129]
    return (10+0.2*xx+0.3*yy+2*np.sin(xx/7)*np.cos(yy/5)).astype("<f4")


def test_compose_uses_core_inside_and_master_triangles_outside(tmp_path):
    expected = write_core(tmp_path/"core")
    core = load_core(tmp_path/"core")
    master = master_raster()
    window = core_window(core, root_m=128., origin_x_m=0., origin_z_m=0., extent_m=512.)
    assert window == (0., 0., 128.)
    composed = compose_window(master, core, window=window, master_origin_x_m=0., master_origin_z_m=0.)
    assert composed.shape == (129, 129)
    assert np.array_equal(composed[24:73, 40:89], expected.astype("<f4"))
    xs = np.arange(129)/4.
    pure = triangle_sample(master.astype(np.float64), xs[None, :], xs[:, None])
    mask = np.ones(composed.shape, bool)
    mask[24:73, 40:89] = False
    assert np.max(np.abs(composed[mask]-pure[mask])) < 1e-5
    assert np.array_equal(composed[::4, ::4][mask[::4, ::4]], master[:33, :33][mask[::4, ::4]])


def test_core_off_master_lattice_is_rejected(tmp_path):
    write_core(tmp_path/"core", x_min=41.)
    core = load_core(tmp_path/"core")
    with pytest.raises(ValueError, match="master lattice"):
        compose_window(master_raster(), core, window=(0., 0., 128.), master_origin_x_m=0., master_origin_z_m=0.)


def test_core_checksum_mismatch_is_rejected(tmp_path):
    write_core(tmp_path/"core")
    with (tmp_path/"core"/"core_heightfield.f32").open("r+b") as stream:
        stream.write(b"\x00\x00\x80\x3f")
    with pytest.raises(ValueError, match="checksum"):
        load_core(tmp_path/"core")


def build_small(tmp_path, **extra):
    write_core(tmp_path/"core")
    return build_composed_pack(master_raster(), tmp_path/"core", tmp_path/"pack", mesh_cells=16, master_root_cells=32,
                               origin_x_m=0., origin_z_m=0., **extra)


def test_composed_pack_owns_every_square_exactly_once(tmp_path):
    catalog = build_small(tmp_path)
    report = coverage_report(catalog, (0., 0., 512., 512.))
    assert report == {"root_area_m2": 512.**2, "overlapping_pairs": 0, "uncovered_area_m2": 0.}
    packs = {r["key"].split(":")[0] for r in catalog["roots"]}
    assert packs == {"midway", "core"}
    core_roots = [r for r in catalog["roots"] if r["key"].startswith("core")]
    assert [(r["origin_x_m"], r["origin_z_m"], r["size_m"]) for r in core_roots] == [(0., 0., 128.)]
    assert len([r for r in catalog["roots"] if r["key"].startswith("midway")]) == 15


def test_core_leaf_pages_hold_composed_one_meter_heights(tmp_path):
    catalog = build_small(tmp_path)
    root = next(r for r in catalog["roots"] if r["key"] == "core:3:0:0")
    node = json.loads((tmp_path/"pack"/root["page"]).read_text())
    while node["tile"]["lod"] > 0:
        node = json.loads((tmp_path/"pack"/node["children"][0]["page"]).read_text())
    assert node["tile"]["size_m"] == 16.0
    leaf = np.frombuffer((tmp_path/"pack"/node["heights"]["path"]).read_bytes(), dtype="<f4").reshape(17, 17)
    composed = compose_window(master_raster(), load_core(tmp_path/"core"), window=(0., 0., 128.),
                              master_origin_x_m=0., master_origin_z_m=0.)
    assert np.array_equal(leaf, composed[:17, :17])


def test_appending_an_overlapping_root_is_still_rejected(tmp_path):
    build_small(tmp_path)
    with pytest.raises(ValueError, match="overlaps"):
        build_pack(np.zeros((129, 129), dtype="<f4"), tmp_path/"pack", pack_id="intruder", cell_m=1.,
                   mesh_cells=16, root_cells=128, origin_x_m=64., origin_z_m=64., append=True)


def test_failed_composition_leaves_no_output(tmp_path):
    write_core(tmp_path/"core")
    master = master_raster()
    master[100, 100] = np.nan
    with pytest.raises(ValueError):
        build_composed_pack(master, tmp_path/"core", tmp_path/"pack", mesh_cells=16, master_root_cells=32,
                            origin_x_m=0., origin_z_m=0.)
    assert not (tmp_path/"pack").exists()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".compose")] == []


def test_existing_output_is_not_overwritten(tmp_path):
    build_small(tmp_path)
    with pytest.raises(FileExistsError):
        build_small(tmp_path)


def test_carve_lowers_channel_to_bed_and_blends_banks():
    heights = np.full((9, 9), 10., dtype="<f4")
    rivers = [{"id": "r", "width": 4.0, "points": [[2., 8., 0.], [2., 8., 8.]]}]
    report = carve_river_beds(heights, cell_m=1., x_min_m=0., z_min_m=0., rivers=rivers)
    assert float(heights[4, 2]) == pytest.approx(7.55, abs=1e-6)
    assert float(heights[4, 4]) == pytest.approx(7.55, abs=1e-6)
    assert float(heights[4, 5]) == pytest.approx(10.-2.45*0.25925926, abs=1e-4)
    assert float(heights[4, 6]) == 10.
    assert report["changed_vertices"] > 0
    assert report["maximum_lowering_m"] == pytest.approx(2.45, abs=1e-5)
    assert report["value_class"] == "authored_render_bed"


def test_carve_depth_selects_wide_or_narrow():
    rivers = [{"id": "wide", "width": 22.0, "points": [[0., 5., 0.], [4., 5., 0.]]},
              {"id": "narrow", "width": 3.5, "points": [[0., 5., 4.], [4., 5., 4.]]}]
    segments = river_bed_segments(rivers)
    assert [s[3] for s in segments] == [0.53, 0.45]
    assert [s[2] for s in segments] == [11.0, 1.75]


def test_carve_keeps_the_stitched_boundary_ring():
    heights = np.full((9, 9), 10., dtype="<f4")
    rivers = [{"id": "r", "width": 4.0, "points": [[4., 8., -4.], [4., 8., 12.]]}]
    carve_river_beds(heights, cell_m=1., x_min_m=0., z_min_m=0., rivers=rivers)
    assert float(heights[4, 4]) == pytest.approx(7.55, abs=1e-6)
    assert np.all(heights[0, :] == 10.) and np.all(heights[8, :] == 10.)
    assert np.all(heights[:, 0] == 10.) and np.all(heights[:, 8] == 10.)


def test_carve_never_raises_vertices():
    heights = np.full((5, 5), 3., dtype="<f4")
    rivers = [{"id": "r", "width": 4.0, "points": [[2., 8., 0.], [2., 8., 4.]]}]
    report = carve_river_beds(heights, cell_m=1., x_min_m=0., z_min_m=0., rivers=rivers)
    assert report["changed_vertices"] == 0
    assert np.all(heights == 3.)


def test_carve_rejects_river_without_geometry():
    with pytest.raises(ValueError, match="points and positive width"):
        river_bed_segments([{"id": "r", "width": 0.0, "points": [[0., 0., 0.], [1., 0., 1.]]}])
    with pytest.raises(ValueError, match="points and positive width"):
        river_bed_segments([{"id": "r", "width": 4.0, "points": [[0., 0., 0.]]}])


def test_composed_pack_carves_core_river_beds(tmp_path):
    world = small_world()
    world["rivers"] = [{"id": "r", "width": 4.0, "points": [[44., 6., 24.], [44., 6., 72.]]}]
    (tmp_path/"world.json").write_text(json.dumps(world))
    catalog = build_small(tmp_path, world_path=tmp_path/"world.json")
    source = next(s for s in catalog["sources"] if s["pack_id"] == "core")
    assert source["river_bed_carve"]["changed_vertices"] > 0
    assert "river bed carve" in source["composition"]
    core = load_core(tmp_path/"core")
    carve_river_beds(core["heights"], cell_m=1., x_min_m=40., z_min_m=24., rivers=world["rivers"])
    composed = compose_window(master_raster(), core, window=(0., 0., 128.),
                              master_origin_x_m=0., master_origin_z_m=0.)
    root = next(r for r in catalog["roots"] if r["key"] == "core:3:0:0")
    node = json.loads((tmp_path/"pack"/root["page"]).read_text())
    while node["tile"]["lod"] > 0:
        child = next(c for c in node["children"]
                     if c["origin_x_m"] <= 44. <= c["origin_x_m"]+c["size_m"]
                     and c["origin_z_m"] <= 44. <= c["origin_z_m"]+c["size_m"])
        node = json.loads((tmp_path/"pack"/child["page"]).read_text())
    assert (node["tile"]["origin_x_m"], node["tile"]["origin_z_m"]) == (32., 32.)
    leaf = np.frombuffer((tmp_path/"pack"/node["heights"]["path"]).read_bytes(), dtype="<f4").reshape(17, 17)
    assert np.array_equal(leaf, composed[32:49, 32:49])
    assert float(leaf[12, 12]) == pytest.approx(5.55, abs=1e-6)


def test_composed_pack_without_world_skips_the_carve(tmp_path):
    catalog = build_small(tmp_path)
    source = next(s for s in catalog["sources"] if s["pack_id"] == "core")
    assert "river_bed_carve" not in source


def small_world():
    ring = [[100., 40.], [112., 40.], [112., 52.], [100., 52.]]
    near_edge = [[250., 20.], [262., 20.], [262., 30.], [250., 30.]]
    route = [[x, 5.+0.01*x, 60.+0.1*x] for x in range(0, 500, 20)]
    river = [[20.+2.*k, 10.+0.05*k, 300.+2.0*k] for k in range(80)]
    tributary = [[450.-11.0*k, 8., 480.-4.6*k] for k in range(40)]
    tributary[-1] = list(river[0])
    return {"pools": [{"id": "p1", "name": "Hot", "thermal": True, "temperature_c": 71.5,
                       "ring": ring, "center": [106., 3.5, 46.]},
                      {"id": "p2", "name": "Edge", "thermal": True, "temperature_c": 45.0,
                       "ring": near_edge, "center": [256., 4.0, 25.]},
                      {"id": "lake", "thermal": False, "temperature_c": 12.0,
                       "ring": ring, "center": [0., 0., 0.]}],
            "routes": [{"id": "r1", "kind": "trail", "name": "Boardwalk", "surface": "Boardwalk", "width": 2.4,
                        "source_id": 7, "points": route, "bridge_spans": [[10, 14]], "bridge_approach_spans": [[8, 10]]}],
            "rivers": [{"id": "rv1", "name": "TEST RIVER", "width": 12.0, "flow_mps": 0.8, "points": river},
                       {"id": "rv2", "name": "TEST TRIBUTARY", "width": 3.0, "flow_mps": 0.4,
                        "points": tributary}]}


def pack_with_world(tmp_path):
    (tmp_path/"world.json").write_text(json.dumps(small_world()))
    catalog = build_small(tmp_path, world_path=tmp_path/"world.json")
    return catalog


def read_pages(tmp_path, layer):
    index = json.loads((tmp_path/"pack"/"features"/"index.json").read_text())
    return {name: json.loads((tmp_path/"pack"/"features"/entry["path"]).read_text())
            for name, entry in index["layers"][layer].items()}


def test_feature_pages_bind_to_the_catalog_hash_chain(tmp_path):
    catalog = pack_with_world(tmp_path)
    assert verify_feature_pages(tmp_path/"pack", catalog)["pools"] >= 2
    page = next(iter(read_pages(tmp_path, "pools").values()))
    path = tmp_path/"pack"/"features"/"pools"/f"{page['cell']['cx']}_{page['cell']['cz']}.json"
    path.write_text(path.read_text().replace("Hot", "Hxt"))
    with pytest.raises(ValueError, match="differs"):
        verify_feature_pages(tmp_path/"pack", catalog)


def test_pool_pages_keep_all_pools_with_thermal_flags_and_cross_cell_halo(tmp_path):
    pack_with_world(tmp_path)
    pages = read_pages(tmp_path, "pools")
    ids = {f["id"] for page in pages.values() for f in page["features"]}
    assert ids == {"p1", "p2", "lake"}
    flags = {f["id"]: f["thermal"] for page in pages.values() for f in page["features"]}
    assert flags == {"p1": True, "p2": True, "lake": False}
    temperatures = {f["id"]: f["temperature_c"] for page in pages.values() for f in page["features"]}
    assert temperatures["p1"] == 71.5 and temperatures["lake"] == 12.0
    # The second pool lies within the halo of its neighbor cell, so two pages hold it.
    holders = [name for name, page in pages.items() if any(f["id"] == "p2" for f in page["features"])]
    assert len(holders) == 2
    thermal = [f for page in pages.values() for f in page["features"] if f["thermal"]]
    assert all(f["water_y_m"] in (3.5, 4.0) for f in thermal)


def test_route_chunks_cover_every_segment_and_overlap_across_cells(tmp_path):
    pack_with_world(tmp_path)
    pages = read_pages(tmp_path, "routes")
    chunks = [c for page in pages.values() for c in page["features"]]
    total = chunks[0]["route_point_count"]
    covered = set()
    for chunk in chunks:
        assert chunk["points"] == small_world()["routes"][0]["points"][chunk["first_point"]:chunk["last_point"]+1]
        assert chunk["arcs"][0] == pytest.approx(0.0 if chunk["first_point"] == 0 else chunk["arcs"][0])
        assert [b-a for a, b in zip(chunk["arcs"], chunk["arcs"][1:])] == pytest.approx(
            [math.dist(a, b) for a, b in zip(chunk["points"], chunk["points"][1:])])
        assert chunk["continues_before"] == (chunk["first_point"] > 0)
        assert chunk["continues_after"] == (chunk["last_point"] < total-1)
        covered.update(range(chunk["first_point"], chunk["last_point"]))
    assert covered == set(range(total-1))
    assert len({c["route_sha256"] for c in chunks}) == 1
    assert len(pages) > 1
    spans = [tuple(s) for c in chunks for s in c["bridge_spans"]]
    assert spans and all(10 <= a <= b <= 14 for a, b in spans)


@needs_data
def test_real_composition_keeps_core_authority_and_a_watertight_seam():
    core = load_core(DATA/"core_terrain")
    master = np.memmap(DATA/"terrain.f32", mode="r", dtype="<f4", shape=(1025, 1025))
    window = core_window(core, root_m=512., origin_x_m=-2048., origin_z_m=-2048., extent_m=4096.)
    assert window == (-512., -512., 1024.)
    composed = compose_window(master, core, window=window)
    i0, j0 = int(core["x_min_m"]-window[0]), int(core["z_min_m"]-window[1])
    rows, cols = core["heights"].shape
    assert np.array_equal(composed[j0:j0+rows, i0:i0+cols], core["heights"])
    xs = window[0]+np.arange(1025)
    zs = window[1]+np.arange(1025)
    pure = triangle_sample(np.asarray(master, dtype=np.float64), ((xs+2048)/4.)[None, :],
                           ((zs+2048)/4.)[:, None])
    seam = np.zeros(composed.shape, bool)
    seam[j0, i0:i0+cols] = seam[j0+rows-1, i0:i0+cols] = True
    seam[j0:j0+rows, i0] = seam[j0:j0+rows, i0+cols-1] = True
    assert np.max(np.abs(composed[seam]-pure[seam])) < 1e-5
    outside = np.ones(composed.shape, bool)
    outside[j0:j0+rows, i0:i0+cols] = False
    assert np.max(np.abs(composed[outside]-pure[outside])) < 1e-5


@needs_data
def test_real_pack_has_exact_ownership_and_feature_pages(tmp_path):
    master = np.memmap(DATA/"terrain.f32", mode="r", dtype="<f4", shape=(1025, 1025))
    catalog = build_composed_pack(master, DATA/"core_terrain", tmp_path/"park", world_path=DATA/"world.json")
    assert coverage_report(catalog, (-2048., -2048., 2048., 2048.)) == {
        "root_area_m2": 4096.**2, "overlapping_pairs": 0, "uncovered_area_m2": 0.}
    assert len(catalog["roots"]) == 61
    counts = verify_feature_pages(tmp_path/"park", catalog)
    assert counts["pools"] >= 1 and counts["routes"] > 10
    world = json.loads((DATA/"world.json").read_text())
    routes = {c["id"] for page in read_pages_at(tmp_path/"park", "routes") for c in page["features"]}
    assert routes == {r["id"] for r in world["routes"]}
    pools = {f["id"] for page in read_pages_at(tmp_path/"park", "pools") for f in page["features"]}
    assert pools == {p["id"] for p in world["pools"]}
    rivers = {c["id"] for page in read_pages_at(tmp_path/"park", "rivers") for c in page["features"]}
    assert rivers == {r["id"] for r in world["rivers"]}


def test_river_chunks_cover_every_station_segment_and_share_endpoints(tmp_path):
    pack_with_world(tmp_path)
    pages = read_pages(tmp_path, "rivers")
    chunks = [c for page in pages.values() for c in page["features"]]
    assert {c["id"] for c in chunks} == {"rv1", "rv2"}
    for river_id, source in (("rv1", small_world()["rivers"][0]), ("rv2", small_world()["rivers"][1])):
        parts = [c for c in chunks if c["id"] == river_id]
        total = parts[0]["river_station_count"]
        covered = set()
        for chunk in parts:
            assert chunk["stations"][-1]["arc"] > chunk["stations"][0]["arc"] or len(parts) == 1
            assert chunk["continues_before"] == (chunk["first_station"] > 0)
            assert chunk["continues_after"] == (chunk["last_station"] < total-1)
            covered.update(range(chunk["first_station"], chunk["last_station"]))
        assert covered == set(range(total-1))
        assert len({c["river_sha256"] for c in parts}) == 1
        assert all(c["sample_z"] == pytest.approx(source["points"][len(source["points"])//2][2])
                   for c in parts)


def test_river_stations_follow_the_bake_ribbon_contract(tmp_path):
    pack_with_world(tmp_path)
    pages = read_pages(tmp_path, "rivers")
    rv1 = [c for page in pages.values() for c in page["features"] if c["id"] == "rv1"]
    stations = sorted((s for c in rv1 for s in c["stations"]), key=lambda s: s["arc"])
    # Resampled stations hold the 2 m spacing inside a chunk run.
    steps = [stations[k+1]["arc"]-stations[k]["arc"] for k in range(len(stations)-1)]
    interior = [s for s in steps if s > 0]
    assert min(interior) > 0.5 and max(interior) <= 2.0+1e-9
    # Visual half width follows width*0.5 plus the clamped bank margin.
    assert all(c["visual_half_m"] == pytest.approx(6.0+min(max(12.0*0.23, 0.8), 5.0)) for c in rv1)
    # Reaches never fold inside the minimum fraction of the visual half width.
    for c in rv1:
        for s in c["stations"]:
            assert s["reach_p"] >= c["visual_half_m"]*0.30-1e-9
            assert s["reach_m"] >= c["visual_half_m"]*0.30-1e-9
            assert 0.0 <= s["fade"] <= 1.0
    # The tributary joins the main river start, so both junction ends stay capped.
    assert all(not c["free_start"] for c in rv1)
    assert all(c["free_end"] for c in rv1)
    rv2 = [c for page in pages.values() for c in page["features"] if c["id"] == "rv2"]
    assert all(c["free_start"] for c in rv2)
    assert all(not c["free_end"] for c in rv2)


def test_river_junction_snapping_matches_bake_centroid():
    world = small_world()
    rivers = river_features(world)
    rv1 = next(r for r in rivers if r["id"] == "rv1")
    rv2 = next(r for r in rivers if r["id"] == "rv2")
    joined = rv2["stations"][-1]["p"]
    start = rv1["stations"][0]["p"]
    assert math.hypot(joined[0]-start[0], joined[2]-start[2]) <= 2.0


def read_pages_at(pack, layer):
    index = json.loads((pack/"features"/"index.json").read_text())
    return [json.loads((pack/"features"/entry["path"]).read_text()) for entry in index["layers"][layer].values()]
