from pathlib import Path

import pytest

from yellowstone_python.registry.param_registry import PARAM_CLASSES, PARAMS, registry_errors, source_ref_errors, validate_entry

REPO_ROOT = Path(__file__).resolve().parents[1]


def _entry(**over):
    base = {"param_id": "replay.hydraulics.manning_n", "meaning": "m",
            "units": "s/m^(1/3)", "param_class": "assumed", "source": "s",
            "applicability": "a", "uncertainty": "unknown",
            "missingness": "m", "review": "not_yet_accepted"}
    base.update(over)
    return base


def test_registry_passes_validation():
    assert registry_errors() == []


def test_registry_covers_all_classes_used():
    classes = {e["param_class"] for e in PARAMS}
    assert {"assumed", "illustrative", "literature", "calibrated",
            "physical_constant"} <= classes
    assert classes <= set(PARAM_CLASSES)


def test_registry_has_seed_depth():
    assert len(PARAMS) >= 10


def test_unknown_uncertainty_recorded_as_unknown():
    unknowns = [e for e in PARAMS if e["uncertainty"] == "unknown"]
    assert unknowns
    for e in PARAMS:
        assert e["uncertainty"], e["param_id"]


def test_seed_entries_name_source_and_applicability():
    for e in PARAMS:
        assert e["source"], e["param_id"]
        assert e["applicability"], e["param_id"]
        assert e["units"], e["param_id"]


def test_units_name_one_quantity():
    for e in PARAMS:
        assert "," not in e["units"], e["param_id"]


def test_param_ids_are_dotted_words():
    for e in PARAMS:
        for seg in e["param_id"].split("."):
            assert seg and all(ch.isalnum() or ch == "_" for ch in seg), seg


def test_review_states_come_from_claim_vocabulary():
    from yellowstone_python.registry.claims import REVIEW_STATUSES
    assert {e["review"] for e in PARAMS} <= set(REVIEW_STATUSES)


def test_validate_entry_catches_missing_fields():
    assert validate_entry({"param_id": "x"}) != []
    bad = _entry(param_class="measured", review="r")
    assert validate_entry(bad) != []


def test_validate_entry_rejects_nonstring_and_empty_fields():
    for field in ("param_id", "meaning", "units", "param_class", "source",
                  "applicability", "uncertainty", "missingness", "review"):
        for bad in (None, "", "   ", [], 3):
            errors = validate_entry(_entry(**{field: bad}))
            assert any(field in msg for msg in errors), (field, bad)


def test_validate_entry_rejects_compound_units():
    assert any("two quantities" in msg
               for msg in validate_entry(_entry(units="m3/s, C")))


def test_validate_entry_rejects_bad_param_id_segments():
    for bad in ("", ".", "a..b", "a.b!", "a b"):
        assert any("param_id" in msg
                   for msg in validate_entry(_entry(param_id=bad))), bad


def test_validate_entry_rejects_bad_source_refs():
    bad_shapes = ([], "x", [{"path": "p.yaml"}],
                  [{"key": "k", "expected": 1}])
    for bad in bad_shapes:
        assert validate_entry(_entry(source_refs=bad)) != [], bad


def test_registry_errors_survives_entries_without_ids():
    import yellowstone_python.registry.param_registry as P
    original = P.PARAMS
    try:
        P.PARAMS = [{"meaning": "no id"}, _entry(), _entry()]
        errors = P.registry_errors()
        assert any("param_id" in msg for msg in errors)
        assert any("duplicate" in msg for msg in errors)
    finally:
        P.PARAMS = original


def _configs():
    import yaml
    path = REPO_ROOT / "configs" / "baseline.yaml"
    return {"configs/baseline.yaml": yaml.safe_load(path.read_text())}


def test_source_refs_match_the_baseline_config():
    assert source_ref_errors(_configs()) == []


def test_source_ref_errors_flag_stale_values():
    cfgs = _configs()
    cfgs["configs/baseline.yaml"]["replay"]["hydraulics"]["manning_n"] = 0.9
    errors = source_ref_errors(cfgs)
    assert any("manning_n" in msg for msg in errors)


def test_source_ref_errors_flag_missing_config():
    assert source_ref_errors({}) != []
