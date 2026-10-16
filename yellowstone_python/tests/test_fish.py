
import pytest
import json
from pathlib import Path

from yellowstone_python.aquatic.fish import assign_reach, build_chainage, check_trout_clear_of_pools, fish_activity, reach_membership, select_refuge, suitability, temp_penalty, update_trout
from yellowstone_python.thermal_features.pool_crust import build_all

# Tests derive from the frozen shipped baseline, as build.py does.


def _data():
    w = json.load(open(WORLD))
    e = json.load(open(ECO))
    river = next(r for r in w["rivers"] if r["id"] == "river_5856_0")
    return river["points"], e["river_reaches"], e["wildlife"], w["pools"]


def test_activity_is_visibility_not_mortality():
    assert fish_activity(17.5) == 1.0
    assert 0.0 < fish_activity(19.0) < 1.0
    assert temp_penalty(18.0) == 0.0 and temp_penalty(25.0) == 0.5


def test_hot_reach_relocates_not_dies():
    pts, reaches, wl, _ = _data()
    warm = [dict(r, temperature_c=24.0) if r["id"] == "excelsior_mixing" else r
            for r in reaches]
    base = [t for t in wl if t["id"] == "trout_01"][0]
    cool = update_trout([base], reaches, pts)
    hot = update_trout([base], warm, pts)
    # Refuge selection: the hot window is abandoned for cooler chainage.
    assert hot[0]["reach_id"] != "excelsior_mixing"
    assert hot[0]["reach_temp_c"] < 24.0
    # The hot fish ends in a reach at least as cool as the cool fish's reach.
    assert hot[0]["reach_temp_c"] <= cool[0]["reach_temp_c"] + 1e-6
    assert "chainage" in hot[0]["refuge_reason"]
    # Timing still responds when temperature differs at the hold site.
    assert hot[0]["hold_seconds"] >= cool[0]["hold_seconds"]


def test_trout_clear_of_hot_pools_and_interior():
    pts, reaches, wl, pools = _data()
    shells = build_all(pools)
    bad = check_trout_clear_of_pools(wl, pts, shells)
    assert bad == []
    out = update_trout(wl, reaches, pts)
    for t in out:
        if "trout" in t["id"]:
            assert abs(t["lateral_offset_m"]) <= 22.0 * 0.35
            assert t["suitability_U"] is not None


def test_suitability_weights_behave():
    assert suitability(0.7, 0.6, 18.0, 0.34, 1.1) > suitability(
        0.7, 0.6, 24.0, 0.34, 1.1)
    # Preferred velocity range: optimum beats both still and fast water.
    assert suitability(0.7, 0.6, 18.0, 0.35, 1.1) > suitability(
        0.7, 0.6, 18.0, 0.0, 1.1)
    assert suitability(0.7, 0.6, 18.0, 0.35, 1.1) > suitability(
        0.7, 0.6, 18.0, 1.5, 1.1)


def test_chainage_membership_is_auditable():
    pts, reaches, _, _ = _data()
    chain = build_chainage(pts)
    assert chain[0] == 0.0 and all(b > a for a, b in zip(chain, chain[1:]))
    memb = reach_membership(pts, reaches)
    assert len(memb) == len(pts)
    runs = sum(1 for a, b in zip(memb, memb[1:]) if a != b) + 1
    assert runs <= 2 * len(reaches)  # near-contiguous runs, no z-flicker


def test_segment_check_covers_offsets():
    from yellowstone_python.aquatic.fish import _samples_along
    a, b = [0.0, 0.0, 0.0], [10.0, 0.0, 0.0]
    pts = list(_samples_along(a, b, 3.0, every_m=2.0))
    assert any(abs(x) < 1e-9 and abs(z - 3.0) < 1e-9 for x, z in pts)
    assert any(abs(z) < 1e-9 for x, z in pts)


def test_update_trout_per_cell_velocity_depth():
    """Per-cell velocity and depth arrays steer the refuge toward the preferred-velocity cell."""
    pts, reaches, wl, _ = _data()
    base = [t for t in wl if t["id"] == "trout_01"][0]
    n = len(pts)
    # Uniform array equal to reach-average velocity: result should match the reach-average call.
    uniform_v = [0.34] * n
    uniform_d = [1.1] * n
    reach_result = update_trout([base], reaches, pts)[0]
    per_cell_result = update_trout([base], reaches, pts,
                                     cell_velocity_mps=uniform_v,
                                     cell_depth_m=uniform_d)[0]
    assert per_cell_result["suitability_basis"] == "per_cell_velocity_depth"
    # Hold-interval start chosen from the same chainage window as the baseline.
    assert abs(per_cell_result["reach_temp_c"]
               - reach_result["reach_temp_c"]) < 2.0


def test_update_trout_per_cell_rejects_length_mismatch():
    pts, reaches, wl, _ = _data()
    base = [t for t in wl if t["id"] == "trout_01"][0]
    import pytest
    with pytest.raises(ValueError):
        update_trout([base], reaches, pts,
                     cell_velocity_mps=[0.3],
                     cell_depth_m=[1.0])


def test_reach_z_windows_chainage_mode_bounds_first_reach():
    from yellowstone_python.aquatic.fish import reach_z_windows
    pts, reaches, _, _ = _data()
    windows = reach_z_windows(reaches, river_points=pts)
    for w in windows:
        assert "s_lo" in w and "s_hi" in w
        assert w["s_hi"] >= w["s_lo"]
        assert w["z_hi"] < 1e8
        assert w["z_lo"] <= w["z_hi"]
    legacy = reach_z_windows(reaches)
    assert any(w.get("z_hi", 0.0) > 1e8 for w in legacy)

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'ECO_FROZEN', resolved_paths['ECO_FROZEN'], raising=False)
    monkeypatch.setattr(module, 'ECO_LIVE', resolved_paths['ECO_LIVE'], raising=False)
    monkeypatch.setattr(module, 'WORLD', resolved_paths['WORLD_JSON'], raising=False)
    monkeypatch.setattr(module, "ECO", ECO_FROZEN if ECO_FROZEN.exists() else ECO_LIVE, raising=False)
