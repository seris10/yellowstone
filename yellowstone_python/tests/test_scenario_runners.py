"""Static shape checks for the hot low-flow scenario runners."""
from __future__ import annotations

import ast
import math

from tests.paths import REPO

TOOLS_DIR = REPO / "tools"


def test_orphan_runner_removed():
    """fixes-30 finding 1: run_hot_lowflow_with_tributaries.py deleted."""
    orphan = TOOLS_DIR / "run_hot_lowflow_with_tributaries.py"
    assert not orphan.exists(), f"{orphan} should be deleted per fixes-30"


def test_scenario_constants_single_source():
    """fixes-30 finding 8: constants and sources live in one module."""
    mod = TOOLS_DIR / "scenario_constants.py"
    assert mod.exists()
    source = mod.read_text(encoding="utf-8")
    for name in (
        "HOT_LOWFLOW_BOUNDARY_M3S",
        "HOT_LOWFLOW_BOUNDARY_M3S_SOURCE",
        "HOT_LOWFLOW_BOUNDARY_C",
        "HOT_LOWFLOW_BOUNDARY_C_SOURCE",
        "HOT_LOWFLOW_BOUNDARY_C_SUB_UILT",
        "REFUGE_THRESHOLD_C",
        "REFUGE_THRESHOLD_SOURCE",
    ):
        assert name in source


def test_run_hot_lowflow_sets_scenario_run_mode():
    """fixes-30 finding 14: run_mode scenario forced on the hot build."""
    text = (TOOLS_DIR / "run_hot_lowflow.py").read_text(encoding="utf-8")
    assert 'hot["run_mode"] = "scenario"' in text


def test_run_hot_lowflow_declares_sub_uilt_and_plus_c_and_settle_s():
    """fixes-30 findings 6, 7, 13: new CLI flags present."""
    text = (TOOLS_DIR / "run_hot_lowflow.py").read_text(encoding="utf-8")
    for flag in ("--sub-uilt", "--plus-c", "--settle-s"):
        assert flag in text, f"missing flag {flag} in run_hot_lowflow.py"


def test_run_hot_lowflow_scenario_block_carries_source_citations():
    """fixes-30 finding 6: scenario block emits citation dicts."""
    text = (TOOLS_DIR / "run_hot_lowflow.py").read_text(encoding="utf-8")
    for key in (
        "boundary_m3s_source",
        "boundary_c_source",
        "observed_max_c_source",
        "uilt_c_source",
        "refuge_threshold_source",
    ):
        assert key in text


def test_tributary_refuge_declares_sweeps_and_fields():
    """fixes-30 findings 5, 9, 12, 15: scope, N=1 flag, sweeps."""
    text = (TOOLS_DIR / "run_hot_lowflow_tributary_refuge.py").read_text(
        encoding="utf-8"
    )
    assert "--out-single-pocket" in text
    assert "--settle-s" in text
    assert "VELOCITY_DEPTH_SWEEP" in text
    assert "velocity_depth_sweep" in text
    assert "starvation_absent" in text
    assert "model_scope" in text


def test_tributary_refuge_temp_sweep_steps_1c_near_flip():
    """fixes-30 finding 15: TEMP_SWEEP_C covers 23..26 at 1 C step."""
    source = (TOOLS_DIR / "run_hot_lowflow_tributary_refuge.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    sweep = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TEMP_SWEEP_C":
                    sweep = ast.literal_eval(node.value)
    assert sweep is not None
    values = tuple(float(v) for v in sweep)
    assert 23.0 in values and 24.0 in values and 25.0 in values and 26.0 in values
    hits = sorted(v for v in values if 23.0 <= v <= 26.0)
    for a, b in zip(hits, hits[1:]):
        assert math.isclose(b - a, 1.0, abs_tol=1e-9), hits


def test_tributary_refuge_carries_source_build_id():
    """Tributary refuge runner carries pulse source_build_id into outputs."""
    text = (TOOLS_DIR / "run_hot_lowflow_tributary_refuge.py").read_text(
        encoding="utf-8"
    )
    assert 'pulse_doc.get("source_build_id")' in text
    assert text.count('"source_build_id"') >= 2


def test_no_fabricated_tributaries_in_live_runners():
    """fixes-30 finding 2: no runner appends to pulse_doc['cells']."""
    forbidden = ('modified_doc["cells"] = pulse_doc["cells"] +',
                 "modified_doc['cells'] = pulse_doc['cells'] +")
    for path in sorted(TOOLS_DIR.glob("run_hot_lowflow*.py")):
        text = path.read_text(encoding="utf-8")
        for bad in forbidden:
            assert bad not in text, f"{path} appends fabricated cells"
