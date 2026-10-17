"""Reach profile_status stamping against measured junction topology."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import prepare_world


def tilted_source():
    """South-sloping DEM so tributary outlet selection is deterministic."""
    rows = np.arange(prepare_world.GRID) * 0.001
    return np.tile(rows[:, None], (1, prepare_world.GRID))


def statuses(rivers):
    """Run the profile join and return profile_status by reach id."""
    prepare_world.join_water_profiles(rivers, tilted_source())
    return {r["id"]: r["profile_status"] for r in rivers}


def test_shared_endpoint_stamps_joined_on_both_reaches():
    """An exact shared vertex stamps joined at the meeting ends."""
    rivers = [
        dict(id="firehole", name="FIREHOLE RIVER",
             points=[[-2048., 10., 0.], [0., 9., 0.], [100., 8., 0.]]),
        dict(id="trib", name="FAIRY CREEK",
             points=[[50., 12., 100.], [100., 8., 0.]]),
    ]
    result = statuses(rivers)
    assert "upstream domain_exit" in result["firehole"]
    assert "downstream joined" in result["firehole"]
    assert "upstream open" in result["trib"]
    assert "downstream joined" in result["trib"]


def test_boundary_exit_without_confluence_stamps_domain_exit():
    """Parallel channels exiting the south boundary never stamp joined."""
    rivers = [
        dict(id="firehole", name="FIREHOLE RIVER",
             points=[[-2048., 10., -1000.], [0., 9., -1500.], [532., 8., -2048.]]),
        dict(id="white", name="WHITE CREEK",
             points=[[611., 12., -1900.], [611., 8., -2048.]]),
    ]
    result = statuses(rivers)
    assert "downstream domain_exit" in result["firehole"]
    assert "upstream open" in result["white"]
    assert "downstream domain_exit" in result["white"]
    assert "joined" not in result["white"]


def test_stamp_tolerance_matches_bake_side_junction_tolerance():
    """A 1.0 m endpoint gap stamps joined; a 3.0 m gap stamps open."""
    rivers = [
        dict(id="firehole", name="FIREHOLE RIVER",
             points=[[-2048., 10., 0.], [0., 9., 0.], [100., 8., 0.]]),
        dict(id="near", name="RABBIT CREEK",
             points=[[50., 12., 100.], [101., 8., 0.]]),
        dict(id="far", name="MALLARD CREEK",
             points=[[60., 12., 100.], [103., 8., 0.]]),
    ]
    result = statuses(rivers)
    assert "downstream joined" in result["near"]
    assert "downstream open" in result["far"]
