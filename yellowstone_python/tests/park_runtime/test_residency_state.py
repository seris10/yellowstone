"""Interventions under segment residency and committed residency saves."""
import copy
import math

import pytest

from tests.park_runtime.test_residency import CLOSURE_REL, SWAP_REL
from tests.paths import DATA
from yellowstone_python.common.io import load_json
from yellowstone_python.park_runtime import residency as residency_module
from yellowstone_python.park_runtime.residency import (BUDGET_TERMS_J, ResidencyManager, evaluate_walk,
                                                       firehole_residency, replay_segment, run_walk, spinup_job)
from yellowstone_python.park_runtime.state_store import StateStore
from yellowstone_python.river.river_transport import demo_config

# Tolerances set before the runs.
TEMPERATURE_C = 1e-9
BUDGET_REL = 1e-9


def manager(**kwargs):
    kwargs.setdefault("velocity_mps", 1.4)
    return ResidencyManager(demo_config(), [20, 40], prefix="demo", workers=1, virtual_wall=True, **kwargs)


@pytest.fixture
def managers():
    made = []

    def make(**kwargs):
        made.append(manager(**kwargs))
        return made[-1]
    yield make
    for item in made:
        item.close()


def advance(m, quanta):
    for _ in range(quanta):
        m.advance(m.runtime.time_s + m.quantum_s)


def temperatures(m):
    return [t for d in m.cells for t in m.runtime.domains[d].river.temperature_c]


def worst_c(a, b):
    return max(abs(x - y) for x, y in zip(temperatures(a), temperatures(b)))


def relative(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def walk_until_installed(m, domain_id, position_m, speed_mps=1.4):
    """Walk with one update per quantum until a segment installs; return the wall time and position."""
    wall = 0.0
    while True:
        m.update(wall, position_m, speed_mps, 1.0)
        if m.runtime.domains[domain_id].representation == "fine":
            return wall, position_m
        m.advance(m.runtime.time_s + m.quantum_s)
        wall += m.quantum_s
        position_m += speed_mps * m.quantum_s


def test_rollback_intervention_matches_a_frontier_intervention(managers):
    rolled, reference, untouched = managers(), managers(), managers()
    advance(rolled, 12)
    advance(reference, 11)
    advance(untouched, 11)
    at_s = reference.runtime.time_s
    change = {"air_c": 15.0}
    expected = reference.intervene("warm", "demo.s1", at_s, change)
    assert rolled.intervene("warm", "demo.s1", at_s, change) == expected
    assert rolled.runtime.time_s == at_s and expected["revision"] == 1
    for _ in range(60):
        for m in (rolled, reference, untouched):
            advance(m, 1)
        assert worst_c(rolled, reference) <= TEMPERATURE_C
    assert worst_c(reference, untouched) > 1e-6
    for key in rolled.cells:
        a, b = rolled.runtime.domains[key].river.budget(), reference.runtime.domains[key].river.budget()
        assert all(relative(a[k], b[k]) <= BUDGET_REL for k in BUDGET_TERMS_J)
    assert rolled.runtime.events == reference.runtime.events


def test_intervention_before_a_frontier_install_rolls_the_swap_back(managers):
    m = managers(position_m=900.0)
    wall, position = walk_until_installed(m, "demo.s1", 900.0)
    install_s = m.runtime.time_s
    assert any(e["t_s"] == install_s for e in m.runtime.membership)
    m.intervene("warm", "demo.s1", install_s - m.quantum_s, {"air_c": 15.0})
    assert m.runtime.time_s == install_s - m.quantum_s
    assert m.runtime.domains["demo.s1"].representation == "coarse"
    assert all(e["t_s"] < install_s for e in m.runtime.membership)
    reports = []
    while position < 1500.0:
        reports.append(m.update(wall, position, 1.4, 1.0))
        m.advance(m.runtime.time_s + m.quantum_s)
        wall += m.quantum_s
        position += 1.4 * m.quantum_s
    fine = m.runtime.domains["demo.s1"]
    assert fine.representation == "fine" and fine.river.air_c.at(fine.time_s) == 15.0
    assert all(r["walker_on"] == "fine" for r in reports)
    assert max(s["heat_relative"] for s in m.swaps) <= SWAP_REL
    assert max(s["water_relative"] for s in m.swaps) <= SWAP_REL
    ledger = m.tier_ledger()
    assert ledger["heat_closure_relative"] <= CLOSURE_REL and ledger["water_closure_relative"] <= CLOSURE_REL
    assert all(f["heat_relative"] <= CLOSURE_REL and f["water_relative"] <= CLOSURE_REL for f in ledger["faces"])


def test_spinup_replays_through_an_intervention(managers):
    m = managers()
    advance(m, 5)
    m.intervene("cool", "demo.s0", m.runtime.time_s, {"air_c": 2.0})
    advance(m, 7)
    pristine = m.fine_pristine["demo.s0"]
    inlet, outlet = m._faces("demo.s0", 0.0, m.runtime.time_s)
    changes = [(50.0, {"air_c": 2.0})]
    local = replay_segment(copy.deepcopy(pristine), 0.0, list(pristine.temperature_c), inlet, outlet,
                           m.runtime.time_s, 1.0, changes)
    live = m.runtime.domains["demo.s0"].river.temperature_c
    assert max(abs(a - b) for a, b in zip(local, live)) <= TEMPERATURE_C
    spec = m.by_id["demo.s0"]
    remote = m.pool.submit(spinup_job, spec.lo, spec.hi, 0.0, list(pristine.temperature_c), inlet, outlet,
                           m.runtime.time_s, 1.0, changes).result()
    assert remote["temperature_c"] == local
    plain = replay_segment(copy.deepcopy(pristine), 0.0, list(pristine.temperature_c), inlet, outlet,
                           m.runtime.time_s, 1.0)
    assert max(abs(a - b) for a, b in zip(plain, live)) > 1e-6
    with pytest.raises(ValueError, match="not split"):
        replay_segment(copy.deepcopy(pristine), 0.0, list(pristine.temperature_c), inlet, outlet,
                       m.runtime.time_s, 1.0, [(55.0, {"air_c": 2.0})])


def test_rebuilt_segments_keep_the_change(managers):
    m = managers()
    assert m.runtime.domains["demo.s2"].representation == "coarse"
    assert m.fine_pristine["demo.s2"].air_c.at(0.0) != 15.0
    m.intervene("warm", "demo.s2", 0.0, {"air_c": 15.0})
    reports = run_walk(m, 0.0, 2500.0, 1.4)
    installed = m.runtime.domains["demo.s2"]
    assert installed.representation == "fine" and installed.river.air_c.at(installed.time_s) == 15.0
    wall = reports[-1]["wall_s"]
    while m.runtime.domains["demo.s2"].representation == "fine":
        m.advance(m.runtime.time_s + m.quantum_s)
        wall += m.quantum_s
        m.update(wall, 100.0, -1.4, 1.0)
    retired = m.runtime.domains["demo.s2"]
    assert retired.representation == "coarse" and retired.river.air_c.at(retired.time_s) == 15.0
    assert m.tier_ledger()["heat_closure_relative"] <= CLOSURE_REL


def test_refused_interventions_leave_the_state_unchanged(managers):
    m = managers()
    advance(m, 5)
    before = (temperatures(m), m.runtime.revision, sorted(m._snapshots), m.runtime.time_s)
    refused = [("demo.s1", 40.0, {"cell_heat_w.channel_021": 100.0}, "representation-specific"),
               ("demo.s1", 40.0, {"boundary_c": 10.0}, "upstream interface"),
               ("demo.s1", 40.0, {"bogus": 1.0}, "unknown forcing"),
               ("demo.s0", 40.0, {"boundary_m3_s": 0.0}, "positive"),
               ("demo.s1", 40.0, {}, "at least one"),
               ("demo.s1", 10.0, {"air_c": 1.0}, "outside"),
               ("demo.s1", 60.0, {"air_c": 1.0}, "outside"),
               ("demo.s9", 40.0, {"air_c": 1.0}, "unknown intervention domain")]
    for k, (domain_id, at_s, changes, message) in enumerate(refused):
        with pytest.raises(ValueError, match=message):
            m.intervene(f"bad{k}", domain_id, at_s, changes)
        assert (temperatures(m), m.runtime.revision, sorted(m._snapshots), m.runtime.time_s) == before
    first = m.intervene("ok", "demo.s1", 40.0, {"air_c": 1.0})
    assert m.intervene("ok", "demo.s1", 40.0, {"air_c": 1.0}) == first and m.runtime.revision == 1
    with pytest.raises(ValueError, match="reused"):
        m.intervene("ok", "demo.s1", 40.0, {"air_c": 2.0})
    advance(m, 1)
    with pytest.raises(ValueError, match="outside|late"):
        m.intervene("early", "demo.s1", 35.0, {"air_c": 2.0})
    assert m.runtime.revision == 1


def test_save_before_a_swap_and_load_restore_the_composite_state(managers, tmp_path):
    m = managers(position_m=900.0)
    m.intervene("warm", "demo.s2", 0.0, {"air_c": 15.0})
    walk_until_installed(m, "demo.s1", 900.0)
    install_s = m.runtime.time_s
    store = StateStore(tmp_path / "residency.sqlite3")
    assert m.save_committed(store, "before-swap", install_s - 0.5 * m.quantum_s) == install_s - m.quantum_s
    snap = m._snapshots[install_s - m.quantum_s]
    loaded = managers(position_m=900.0)
    assert loaded.load_committed(store, "before-swap")
    assert loaded.runtime.time_s == snap["t_s"] and loaded.runtime.revision == snap["revision"]
    for key, saved in snap["domains"].items():
        domain = loaded.runtime.domains[key]
        assert domain.model_id == saved["model_id"] and domain.river.checkpoint() == saved["state"]
    assert loaded.runtime.domains["demo.s1"].representation == "coarse"
    assert [c.checkpoint() for c in loaded.runtime.couplers] == snap["couplers"]
    assert loaded.interventions == m.interventions
    for key, history in loaded.face_history.items():
        assert list(history) == [e for e in m.face_history[key] if e[1] <= snap["t_s"]]
    for key, history in loaded.coarse_history.items():
        assert list(history) == [e for e in m.coarse_history[key] if e[0] <= snap["t_s"]]
    assert loaded.lifetimes == m.lifetimes[:snap["lifetimes"]] and loaded.swaps == m.swaps[:snap["swaps"]]
    assert loaded.open_lifetimes == snap["open_lifetimes"] and loaded.initial_stores == m.initial_stores
    store.close()


def test_frontier_save_resumes_and_activates_from_persisted_history(managers, tmp_path):
    m = managers(position_m=900.0)
    m.intervene("warm", "demo.s2", 0.0, {"air_c": 15.0})
    wall, position = walk_until_installed(m, "demo.s1", 900.0)
    store = StateStore(tmp_path / "residency.sqlite3")
    assert m.save_committed(store, "frontier", m.runtime.time_s) == m.runtime.time_s
    loaded = managers(position_m=position)
    assert loaded.load_committed(store, "frontier")
    advance(m, 30)
    advance(loaded, 30)
    assert worst_c(loaded, m) <= TEMPERATURE_C
    a, b = loaded.tier_ledger(), m.tier_ledger()
    assert a["heat_closure_relative"] <= CLOSURE_REL and a["water_closure_relative"] <= CLOSURE_REL
    assert relative(a["external_flux_j"], b["external_flux_j"]) <= BUDGET_REL
    start = position + 1.4 * 30 * loaded.quantum_s
    reports = run_walk(loaded, start, 2500.0, 1.4)
    result = evaluate_walk(loaded, reports, start, 1.4)
    assert [x["domain_id"] for x in result["arrivals"]] == ["demo.s2"] and result["activated_before_arrival"]
    assert result["reports_on_coarse"] == 0
    installed = loaded.runtime.domains["demo.s2"]
    assert installed.representation == "fine" and installed.river.air_c.at(installed.time_s) == 15.0
    assert loaded.tier_ledger()["heat_closure_relative"] <= CLOSURE_REL
    store.close()


def test_load_refuses_another_segmentation_policy_or_source(managers, tmp_path, monkeypatch):
    store = StateStore(tmp_path / "residency.sqlite3")
    assert not managers().load_committed(store, "w")
    m = managers()
    advance(m, 3)
    m.save_committed(store, "w", m.runtime.time_s)
    others = [ResidencyManager(demo_config(), [30, 45], prefix="demo", workers=1),
              managers(dt_s=0.5), managers(cells_per_coarse=7)]
    try:
        for other in others:
            with pytest.raises(ValueError, match="different replay"):
                other.load_committed(store, "w")
    finally:
        others[0].close()
    versions = residency_module.residency_model_versions()
    changed = dict(versions, **{"yellowstone_python.park_runtime.residency": "0" * 64})
    monkeypatch.setattr(residency_module, "residency_model_versions", lambda: changed)
    with pytest.raises(ValueError, match="model source changed.*residency"):
        managers().load_committed(store, "w")
    store.close()


def test_save_needs_a_snapshot_at_or_before_presentation(managers, tmp_path):
    m = managers()
    advance(m, 6)
    store = StateStore(tmp_path / "residency.sqlite3")
    with pytest.raises(ValueError, match="no committed residency state"):
        m.save_committed(store, "w", 5.0)
    store.close()


@pytest.mark.needs_world
def test_firehole_intervention_and_resume_continue_the_walk(tmp_path):
    document = load_json(DATA / "river_replay.json")
    store = StateStore(tmp_path / "firehole.sqlite3")
    first, _ = firehole_residency(document, workers=2, virtual_wall=True, velocity_mps=1.4)
    try:
        s1, s3 = first.by_id["firehole.s1"], first.by_id["firehole.s3"]
        middle = 0.5 * (s1.start_m + s1.end_m)
        run_walk(first, 0.0, middle, 1.4)
        assert first.runtime.domains["firehole.s3"].representation == "coarse"
        at_s = first.runtime.time_s
        first.intervene("warm-s3", "firehole.s3", at_s, {"air_c": 20.0})
        assert first.save_committed(store, "firehole", at_s) == at_s
    finally:
        first.close()
    second, _ = firehole_residency(document, workers=2, virtual_wall=True, velocity_mps=1.4, position_m=middle)
    try:
        assert second.load_committed(store, "firehole") and second.runtime.time_s == at_s
        reports = run_walk(second, middle, s3.end_m, 1.4)
        result = evaluate_walk(second, reports, middle, 1.4)
        # The walk ends on the upstream face of firehole.s4.
        assert [a["domain_id"] for a in result["arrivals"]] == ["firehole.s2", "firehole.s3", "firehole.s4"]
        assert result["activated_before_arrival"] and result["reports_on_coarse"] == 0
        installed = second.runtime.domains["firehole.s3"]
        assert installed.representation == "fine" and installed.river.air_c.at(installed.time_s) == 20.0
        ledger = second.tier_ledger()
        assert ledger["heat_closure_relative"] <= CLOSURE_REL and ledger["water_closure_relative"] <= CLOSURE_REL
        assert result["max_swap_heat_relative"] <= SWAP_REL
    finally:
        second.close()
        store.close()
