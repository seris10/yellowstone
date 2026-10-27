"""Focus contract, chainage mapping, service residency and accelerated-time walks."""
import json
import math
import os
import re
import signal
import subprocess
import sys
import time

import pytest

from tests.park_runtime.test_park_runtime import domain
from tests.park_runtime.test_residency import CLOSURE_REL, SWAP_REL, assert_walk_accepted
from tests.paths import DATA, REPO
from yellowstone_python.common.io import load_json
from yellowstone_python.park_runtime.contracts import Focus
from yellowstone_python.park_runtime.residency import (ResidencyManager, RiverChainage, evaluate_walk,
                                                       firehole_residency, run_walk)
from yellowstone_python.park_runtime.runtime import ParkRuntime
from yellowstone_python.park_runtime.service import RuntimeService
from yellowstone_python.park_runtime.state_store import StateStore
from yellowstone_python.river.river_transport import demo_config, river_from_config

# Position and chainage tolerance in m, set before the runs.
LOCATE_M = 1e-6
HELD_RATE_REL = 1e-12


def straight_cells(river):
    """Return replay-style cells laid along +x from the solver cell lengths."""
    cells, start = [], 0.0
    for cell in river.cells:
        end = start + cell.length_m
        cells.append({"id": cell.id, "position_xyz": [0.5 * (start + end), 0.0, 0.0],
                      "downstream_unit_xz": [1.0, 0.0], "start_s_m": start,
                      "center_s_m": 0.5 * (start + end), "end_s_m": end})
        start = end
    return cells


def focus(sequence, x, z=0.0, vx=0.0, **extra):
    return {"sequence": sequence, "position_m": [x, 0.0, z], "velocity_mps": [vx, 0.0, 0.0], **extra}


def test_membership_change_keeps_presentation_frames(tmp_path):
    r = ParkRuntime([domain("upper")], history_s=30, max_frames=64)
    r.compute_until(5)
    late = domain("lower")
    late.advance_to(5)
    r.add_domain(late)
    r.compute_until(7)
    early = r.packet(3.5)["bracket"]
    assert [f["t_s"] for f in early] == [3.0, 4.0] and all(list(f["regions"]) == ["upper"] for f in early)
    assert list(r.packet(5.5)["bracket"][1]["regions"]) == ["lower", "upper"]
    with pytest.raises(ValueError, match="rollback history"):
        r.intervene("early", "upper", 4.0, {"inputs": {}})
    r.intervene("late", "upper", 6.0, {"inputs": {}})
    store = StateStore(tmp_path / "state.db")
    with pytest.raises(ValueError, match="no committed checkpoint"):
        r.save_committed(store, "world", 5.5)
    store.close()


def test_focus_parse_validates_the_section_8_fields():
    parsed = Focus.parse(focus(3, 12.0, view_dir=[0, 0, -1], fov_deg=70, reach=["L1_0_0"],
                               resident={"L1_0_0": "A", "L2_0_0": "D"}, time_scale=60, t_s=5.0))
    assert parsed.sequence == 3 and parsed.position_m == (12.0, 0.0, 0.0) and parsed.time_scale == 60.0
    assert parsed.resident == (("L1_0_0", "A"), ("L2_0_0", "D"))
    for bad in ({"sequence": 1, "position_m": [0, 0, 0]}, focus(True, 0.0), focus(-1, 0.0),
                focus(1, 0.0, view_dir=[0, 0, 0]), focus(1, 0.0, fov_deg=180), focus(1, 0.0, resident={"t": "E"}),
                focus(1, 0.0, time_scale=0), {"sequence": 1, "position_m": [0, 0], "velocity_mps": [0, 0, 0]}):
        with pytest.raises(ValueError):
            Focus.parse(bad)


def test_chainage_projects_onto_straight_cells():
    river = river_from_config(demo_config())
    cells = straight_cells(river)
    chainage = RiverChainage(cells)
    center = cells[7]["center_s_m"]
    s, lateral, index = chainage.locate(center, 5.0)
    assert s == pytest.approx(center, abs=LOCATE_M) and lateral == pytest.approx(5.0, abs=LOCATE_M) and index == 7
    assert chainage.along_channel(index, -1.4, 3.0) == pytest.approx(-1.4)
    end = math.fsum(c.length_m for c in river.cells)
    assert chainage.locate(end + 40.0, 0.0)[:2] == pytest.approx((end, 40.0))


@pytest.mark.needs_world
def test_chainage_locates_every_replay_cell_center():
    replay = load_json(DATA / "river_replay.json")
    replay = replay.get("replay", replay)
    chainage = RiverChainage(replay["cells"])
    for k, cell in enumerate(replay["cells"]):
        x, _, z = cell["position_xyz"]
        s, lateral, index = chainage.locate(x, z)
        assert index == k and lateral < LOCATE_M and abs(s - cell["center_s_m"]) < LOCATE_M
        ux, uz = cell["downstream_unit_xz"]
        assert chainage.along_channel(index, 1.4 * ux, 1.4 * uz) == pytest.approx(1.4, rel=1e-6)


@pytest.fixture
def residency_service():
    manager = ResidencyManager(demo_config(), [20, 40], prefix="demo", workers=1)
    service = RuntimeService(manager.runtime, horizon_s=manager.quantum_s, residency=manager,
                             chainage=RiverChainage(straight_cells(river_from_config(demo_config()))))
    yield manager, service
    service.close()
    manager.close()


def test_focus_command_reports_residency_and_ignores_older_sequences(residency_service):
    manager, service = residency_service
    x = manager.specs[1].start_m + 25.0
    first = service._command("focus", focus(2, x, z=3.0, vx=1.4))
    assert first["accepted"] and first["focus_sequence"] == 2
    assert first["walker"]["segment"] == "demo.s1" and first["walker"]["lateral_m"] == pytest.approx(3.0)
    assert first["walker"]["chainage_m"] == pytest.approx(x) and "demo.s1" in first["reach"]
    assert first["walker"]["along_velocity_mps"] == pytest.approx(1.4)
    assert service._command("focus", focus(1, 0.0)) == {"accepted": False, "focus_sequence": 2}
    with pytest.raises(ValueError, match="time_scale"):
        service._command("focus", focus(3, x, time_scale=601))
    assert service.focus.sequence == 2


def test_service_applies_an_intervention_under_residency(residency_service):
    manager, service = residency_service
    manager.advance(manager.quantum_s, presentation_s=0.0)
    command = {"session_id": manager.runtime.session_id, "revision": 0, "event_id": "warm",
               "domain_id": "demo.s1", "at_s": 5.0, "changes": {"air_c": 15.0}}
    service.presentation_s = 5.0
    result = service._command("intervene", command)
    assert result["revision"] == 1 and manager.runtime.revision == 1
    assert service.presentation_s == 5.0 and manager.runtime.time_s == 5.0
    assert manager.runtime.domains["demo.s1"].river.air_c.at(5.0) == 15.0
    assert service._command("intervene", command) == result
    with pytest.raises(ValueError, match="stale revision"):
        service._command("intervene", dict(command, event_id="again"))


def test_service_installs_the_focused_segment_and_publishes_it(residency_service):
    manager, service = residency_service
    service.start()
    service.submit("focus", focus(1, manager.specs[2].start_m + 10.0))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        data = json.loads(service.publication())
        block = data["residency"]
        if block["focus_sequence"] == 1 and "demo.s2" in block["active"]:
            break
        time.sleep(0.05)
    assert data["worker_error"] is None and block["schema"] == "yellowstone.park_residency.v1"
    assert block["walker"]["segment"] == "demo.s2" and block["walker"]["representation"] == "fine"
    assert "demo.s2" in block["active"] and data["bracket"][0]["regions"]["demo.s2"]
    swaps = [s for s in manager.swaps if s["domain_id"] == "demo.s2"]
    assert swaps and max(s["heat_relative"] for s in swaps) <= SWAP_REL


def test_presentation_rate_is_the_held_rate_below_the_request(residency_service):
    manager, service = residency_service
    manager.capacity = 100.0
    report = service._command("focus", focus(1, 10.0, time_scale=10))
    assert report["held"] and report["requested_rate"] == 10.0
    assert report["effective_rate"] == pytest.approx(0.8 * 100.0 / manager.cells["demo.s0"])
    assert service.presentation_rate() == report["effective_rate"]
    manager.capacity = None
    service._command("focus", focus(2, 10.0))
    assert service.presentation_rate() == 10.0


@pytest.fixture
def demo_manager():
    manager = ResidencyManager(demo_config(), [20, 40], prefix="demo", workers=1, virtual_wall=True,
                               velocity_mps=1.4, time_scale=60.0)
    yield manager
    manager.close()


def test_walk_at_sixty_times_activates_ahead_and_retires_behind(demo_manager):
    reports = run_walk(demo_manager, 0.0, 1100.0, 1.4, time_scale=60.0)
    result = assert_walk_accepted(demo_manager, reports, 0.0, 1.4)
    assert [a["domain_id"] for a in result["arrivals"]] == ["demo.s1"]
    assert reports[-1]["t_s"] > 60 * 700


def test_held_walk_reports_the_rate_and_closes_the_ledger():
    manager = ResidencyManager(demo_config(), [20, 40], prefix="demo", workers=1, virtual_wall=True,
                               position_m=900.0, velocity_mps=1.4, time_scale=3600.0, utilization=0.01)
    try:
        reports = run_walk(manager, 900.0, 1100.0, 1.4, time_scale=3600.0)
        result = evaluate_walk(manager, reports, 900.0, 1.4)
        assert result["activated_before_arrival"] and result["reports_on_coarse"] == 0
        assert result["held_updates"] > 0 and result["unreported_holds"] == 0
        assert result["max_held_rate_relative"] <= HELD_RATE_REL and result["admission_inside_budget"]
        assert result["max_swap_heat_relative"] <= SWAP_REL
        assert result["ledger"]["heat_closure_relative"] <= CLOSURE_REL
        assert result["ledger"]["water_closure_relative"] <= CLOSURE_REL
    finally:
        manager.close()


def run_firehole(cwd, state, run_s):
    """Run the Firehole residency service for run_s, send a termination signal, return its output."""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    process = subprocess.Popen([sys.executable, "-m", "yellowstone_python.park_runtime", "--port", "0", "--firehole",
                                "--state", str(state)],
                               cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        first = process.stdout.readline()
        if "PermissionError" in first or process.poll() is not None:
            rest = process.stdout.read()
            if "PermissionError" in first + rest:
                pytest.skip("sandbox disallows loopback socket binding")
            raise AssertionError(first + rest)
        assert "Firehole residency" in first and "saves committed state" in first
        time.sleep(run_s)
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=60)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    assert process.returncode == 0, output
    return output


@pytest.mark.needs_world
def test_firehole_service_saves_on_sigterm_and_resumes(tmp_path):
    state = tmp_path / "firehole.sqlite3"
    output = run_firehole(tmp_path, state, 12.5)
    saved = float(re.search(r"Saved committed checkpoint at ([0-9.]+) physical seconds", output).group(1))
    assert saved >= 10.0 and state.exists()
    output = run_firehole(tmp_path, state, 2.0)
    assert float(re.search(r"Resumed committed state at ([0-9.]+) physical seconds", output).group(1)) == saved
    assert float(re.search(r"Saved committed checkpoint at ([0-9.]+) physical seconds", output).group(1)) >= saved


@pytest.mark.needs_world
def test_firehole_builder_matches_solver_and_mapped_chainage():
    manager, chainage = firehole_residency(load_json(DATA / "river_replay.json"), workers=1)
    try:
        assert manager.runtime.epoch_unix == pytest.approx(1792015920.0)
        for spec in manager.specs:
            assert chainage.locate(*chainage.pieces[spec.lo][:2])[2] == spec.lo
    finally:
        manager.close()
