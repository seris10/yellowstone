from yellowstone_python.land.grazers import check_routes, graze_timing, plan_path, route_length, update_grazers


def test_existing_bison_loops_valid():
    wl = [{"id": "bison_01", "kind": "bison", "medium": "land",
           "path_xz": [[-120, -450], [-125, -440], [-112, -434], [-105, -445]]}]
    assert route_length(wl[0]["path_xz"]) < 200.0
    assert check_routes(wl, []) == []


def test_rich_patch_grazes_longer():
    g_rich, _ = graze_timing(0.9, 1.0, 24.0, 18.0)
    g_poor, _ = graze_timing(0.1, 1.0, 24.0, 18.0)
    assert g_rich > g_poor >= 6.0


def test_apron_gate_flags_pool_cutting():
    wl = [{"id": "elk_x", "kind": "elk", "medium": "land",
           "path_xz": [[-94.7, -10.6], [-80, -10.0]]}]
    shells = [{"id": "pool_1034_0", "center_xz": [-94.7, -10.6],
               "r_apron_m": 76.0}]
    bad = check_routes(wl, shells)
    assert any(b["actor"] == "elk_x" and b["why"] == "segment inside apron" for b in bad)


def test_planner_routes_around_block():
    blocked = lambda x, z: abs(x) < 8 and abs(z) < 8  # mock pool
    path = plan_path((-20, 0), (20, 0), blocked, cell_m=4.0,
                     bounds=(-30, -20, 30, 20))
    assert all(not blocked(x, z) for x, z in path)
    assert path[0] == (-20, 0) and path[-1] == (20, 0)


def test_grazer_update_keeps_ids_and_hypotheses():
    wl = [{"id": "bison_01", "kind": "bison", "patch_id": "north_meadow",
           "graze_seconds": 24, "rest_seconds": 18}]
    out = update_grazers(wl, [{"id": "north_meadow", "biomass": 0.8}])
    assert out[0]["id"] == "bison_01"
    assert out[0]["graze_seconds"] > 24  # rich patch extends bout
    context = out[0]["timing_basis"]["model_context"]
    assert "forage_quality" in context.get("implemented", [])
    assert "predation_risk" in context.get("not_modeled", [])


def test_segment_sampling_catches_midpoint_crossing():
    from yellowstone_python.land.grazers import segment_samples
    pts = list(segment_samples((-10, 0), (10, 0)))
    assert any(abs(x) < 1e-9 for x, z in pts)


def test_planner_rejects_blocked_endpoints_and_corner_cuts():
    import pytest
    from yellowstone_python.land.grazers import plan_path, segment_samples
    with pytest.raises(ValueError):
        plan_path((0, 0), (5, 5), lambda x, z: True)
    # Wall with a gap: path must go through the gap, never cut corners.
    wall = lambda x, z: abs(x) < 2 and abs(z) > 4
    path = plan_path((-20, 0), (20, 0), wall, cell_m=4.0,
                     bounds=(-30, -20, 30, 20))
    assert all(not wall(x, z) for x, z in path)
    # A diagonal step clips a blocked region smaller than the cell pitch; the planner rejects it.
    block = lambda x, z: -2 < x < 2 and -2 < z < 2
    path = plan_path((-6, -6), (6, 6), block, cell_m=4.0,
                     bounds=(-10, -10, 10, 10))
    assert all(not block(x, z) for x, z in path)
    for a, b in zip(path, path[1:]):
        assert not any(block(x, z) for x, z in segment_samples(a, b, 0.5))


def test_grazer_timing_uses_capacity_fraction():
    from yellowstone_python.land.grazers import update_grazers
    wl = [{"id": "b1", "kind": "bison", "patch_id": "m",
           "graze_seconds": 24, "rest_seconds": 18}]
    rich = update_grazers(wl, [{"id": "m", "biomass": 1.6, "capacity": 2.0}])[0]
    poor = update_grazers(wl, [{"id": "m", "biomass": 0.2, "capacity": 2.0}])[0]
    assert rich["graze_seconds"] > poor["graze_seconds"]


def test_single_point_anchor_is_gated_as_a_point():
    shells = [{"id": "pool_1034_0", "center_xz": [-94.7, -10.6],
               "r_apron_m": 76.0}]
    clear = [{"id": "swarm_a", "kind": "insects", "medium": "land",
              "path_xz": [[78, -317]]}]
    assert check_routes(clear, shells) == []
    inside = [{"id": "swarm_b", "kind": "insects", "medium": "land",
               "path_xz": [[-94.7, -10.6]]}]
    bad = check_routes(inside, shells)
    assert [b["why"] for b in bad] == ["anchor inside apron"]
    empty = [{"id": "swarm_c", "kind": "insects", "medium": "land",
              "path_xz": []}]
    assert [b["why"] for b in check_routes(empty, shells)] == [
        "route path_xz is empty"]
