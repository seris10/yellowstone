"""Claim skill gates against recorded null models."""
import json

from yellowstone_python.validation import claims as gates


def _point_evidence(monkeypatch, tmp_path, doc):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(gates, "_resolve_evidence", lambda claim_id: [path])


def test_reach_gate_passes_when_champion_beats_every_null(monkeypatch, tmp_path):
    _point_evidence(monkeypatch, tmp_path, {
        "champion": {"holdout_rmse": 0.6, "budget_ok": True},
        "null_models": [{"name": "upstream_persistence", "holdout_rmse": 6.9},
                        {"name": "mixing_only_c0_refit", "holdout_rmse": 1.7}]})
    gate = gates.check_reach_rmse()
    assert gate["failures"] == []
    assert gate["missing_nulls"] == ["downstream_climatology"]


def test_reach_gate_fails_when_a_null_wins(monkeypatch, tmp_path):
    _point_evidence(monkeypatch, tmp_path, {
        "champion": {"holdout_rmse": 2.0, "budget_ok": True},
        "null_models": [{"name": "mixing_only_c0_refit", "holdout_rmse": 1.7}]})
    gate = gates.check_reach_rmse()
    assert len(gate["failures"]) == 1
    assert "mixing_only_c0_refit" in gate["failures"][0]


def test_reach_gate_fails_on_open_budget_or_absent_champion(monkeypatch, tmp_path):
    _point_evidence(monkeypatch, tmp_path, {
        "champion": {"holdout_rmse": 0.6, "budget_ok": False},
        "null_models": [{"name": "upstream_persistence", "holdout_rmse": 6.9}]})
    assert gates.check_reach_rmse()["failures"] == ["champion budget_ok is not true"]
    _point_evidence(monkeypatch, tmp_path, {"status": "no fit"})
    assert gates.check_reach_rmse()["failures"] == [
        "no champion holdout_rmse in reach claim evidence"]


def test_snotel_gate_scores_each_site_against_both_nulls(monkeypatch, tmp_path):
    _point_evidence(monkeypatch, tmp_path, {"sites": {
        "609": {"holdout_swe_mm": {"rmse": 112.0},
                "null_persistence_rmse_mm": 293.3, "null_nomelt_rmse_mm": 471.6},
        "924": {"holdout_swe_mm": {"rmse": 200.0},
                "null_persistence_rmse_mm": 179.0}}})
    failures = gates.check_snotel_rmse()["failures"]
    assert failures == [
        "site 924: holdout rmse 200.00 mm does not beat null_persistence_rmse_mm 179.00 mm",
        "site 924: null_nomelt_rmse_mm missing"]


def test_gates_pass_on_the_committed_evidence():
    result = gates.run_claim_gates()
    assert result["passed"], result["failures"]
