import pytest
import yaml

from yellowstone_python.build import validate_config
from yellowstone_python.registry.run_mode import check_split, claim_allowed, normalize_run_mode, prescribed_quantities
from yellowstone_python.validation.checks import run_all



def _cfg():
    return yaml.safe_load(open(BASE).read())


def test_normalize_defaults_and_accepts_modes():
    assert normalize_run_mode(None) == "illustrative"
    for m in ("observed_replay", "hindcast", "scenario", "illustrative"):
        assert normalize_run_mode(m) == m


def test_normalize_rejects_forecast_and_unknown():
    with pytest.raises(ValueError):
        normalize_run_mode("forecast")
    with pytest.raises(ValueError):
        normalize_run_mode("nowcast")


def test_prescribed_quantities_decoupled():
    assert prescribed_quantities({"hydro": {"boundary_c": 15.0}}) == \
        ["upstream_temperature"]
    assert prescribed_quantities({"hydro": {"boundary_m3s": 4.0}}) == \
        ["discharge"]
    assert prescribed_quantities({"hydro": {}}) == []
    assert prescribed_quantities({}) == []
    # An empty replay block carries no explicit series, so it adds nothing.
    assert prescribed_quantities({"replay": {}}) == []
    # Each replay series is tracked independently.
    assert prescribed_quantities({"replay": {"discharge": "x"}}) == \
        ["discharge"]
    assert prescribed_quantities(
        {"replay": {"discharge": "x", "upstream_temperature": "y"}}) == \
        ["discharge", "upstream_temperature"]


def test_prescribed_quantities_are_not_validatable():
    prescribed = prescribed_quantities(_cfg())
    assert claim_allowed("observed_replay", "discharge", prescribed) is False
    assert claim_allowed("hindcast", "upstream_temperature", prescribed) is False
    assert claim_allowed("scenario", "trout_refuge", prescribed) is True
    assert claim_allowed("illustrative", "snow_swe", prescribed) is True


def test_claim_allowed_rejects_forecast():
    with pytest.raises(ValueError):
        claim_allowed("forecast", "discharge", [])


def test_check_split():
    check_split(["discharge"], ["downstream_temperature"])
    check_split([], [])
    try:
        check_split(["discharge"], ["discharge"])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_validate_config_rejects_forecast(tmp_path):
    bad = _cfg()
    bad["world_root"] = str(tmp_path)
    bad["run_mode"] = "forecast"
    with pytest.raises(ValueError):
        validate_config(bad)
    ok = _cfg()
    ok["world_root"] = str(tmp_path)
    ok["run_mode"] = "scenario"
    validate_config(ok)


@pytest.mark.needs_world
def test_run_all_records_mode_and_prescribed():
    from yellowstone_python.build import load_inputs, simulate_all
    cfg = _cfg()
    baseline, world, deps, tfns = load_inputs(cfg)
    res = simulate_all(cfg, baseline, world, tfns)
    eco_doc = {"contract_version": "0.1.0", "world_id": "t",
               "code_rev": "t", "status": "t", "parameter_provenance": {},
               "sources": []}
    checks = run_all(river_state=res["river_state"],
                     ledger=res["hydro_ledger"], ecosystem_doc=eco_doc,
                     build_id_a="abc",
                     run_mode="illustrative",
                     prescribed=prescribed_quantities(cfg))
    assert checks["run_mode"] == "illustrative"
    assert "discharge" in checks["prescribed_quantities"]
    assert "heat_budget_error" in checks["metrics"]


def test_run_all_rejects_validated_prescribed():
    eco_doc = {"contract_version": "0.1.0", "world_id": "t",
               "code_rev": "t", "status": "t", "parameter_provenance": {},
               "sources": []}
    state = [{"id": "r1", "volume_m3": 1.0, "upstream_id": "",
              "fish_activity": 0.5}]
    ledger = {"residual": 0.0, "water_budget_error_m3": 0.0}
    bad = run_all(river_state=state, ledger=ledger,
                  ecosystem_doc=eco_doc, build_id_a="a",
                  run_mode="observed_replay", prescribed=["discharge"],
                  validated_quantities=["discharge"])
    assert bad["passed"] is False
    assert any("discharge" in f for f in bad["failures"])
    ok = run_all(river_state=state, ledger=ledger,
                 ecosystem_doc=eco_doc, build_id_a="a",
                 run_mode="observed_replay", prescribed=["discharge"],
                 validated_quantities=["downstream_temperature"])
    assert ok["passed"] is True


def test_run_all_forecast_single_failure():
    eco_doc = {"contract_version": "0.1.0", "world_id": "t",
               "code_rev": "t", "status": "t", "parameter_provenance": {},
               "sources": []}
    checks = run_all(river_state=[{"id": "r1", "volume_m3": 1.0,
                                   "upstream_id": "", "fish_activity": 0.5}],
                     ledger={"residual": 0.0, "water_budget_error_m3": 0.0},
                     ecosystem_doc=eco_doc, build_id_a="a",
                     run_mode="forecast", prescribed=[])
    assert checks["passed"] is False
    assert len(checks["failures"]) == 1


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'BASE', resolved_paths['BASE_CONFIG'], raising=False)
