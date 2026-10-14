import pytest
import yaml

from yellowstone_python.build import validate_config
from yellowstone_python.common.units import (
    AIR_RANGE_C,
    TEMPERATURE_RANGE_C,
    UNIT_DOC,
    WIND_RANGE_MPS,
    check_discharge_m3s, check_temperature_c, check_epoch_s,
    validate_hydro_units,
    validate_usgs_bundle,
)



def _bundle():
    t0 = 1_700_000_000.0
    series = {
        "discharge_m3_s": [[t0 + i * 900.0, 8.0] for i in range(10)],
        "temperature_c": [[t0 + i * 900.0, 15.0] for i in range(10)],
    }
    met = {"hourly": [[t0 + i * 3600.0, 10.0, 0.5, 2.0, 200.0, 0.2]
                       for i in range(10)]}
    return {"sites": {"06036805": {"series": dict(series)},
                      "06036905": {"series": dict(series)}},
            "met": met}


def test_registry_documents_hydro_units():
    assert UNIT_DOC["discharge"] == "meter**3/second"
    assert UNIT_DOC["temperature"] == "degree_Celsius"
    assert UNIT_DOC["epoch"] == "second"


def test_unit_doc_names_irradiance():
    assert "irradiance" in UNIT_DOC
    assert UNIT_DOC["irradiance"] == "watt/meter**2"
    assert "pressure_flux" not in UNIT_DOC


def test_bounds_align_with_godot_consumer():
    # weather_snapshot_reader.gd:45 clamps wind_speed_mps to [0, 65].
    assert WIND_RANGE_MPS == (0.0, 65.0)
    assert AIR_RANGE_C == (-50.0, 40.0)
    assert TEMPERATURE_RANGE_C == (0.0, 35.0)


def test_subzero_water_rejected():
    from yellowstone_python.common.units import check_temperature_c
    with pytest.raises(ValueError):
        check_temperature_c(-1.0)


def test_valid_bundle_passes():
    validate_usgs_bundle(_bundle())


def test_discharge_out_of_range_raises():
    bundle = _bundle()
    bundle["sites"]["06036805"]["series"]["discharge_m3_s"][0][1] = -1.0
    with pytest.raises(ValueError):
        validate_usgs_bundle(bundle)


def test_temperature_out_of_range_raises():
    bundle = _bundle()
    bundle["sites"]["06036905"]["series"]["temperature_c"][0][1] = 400.0
    with pytest.raises(ValueError):
        validate_usgs_bundle(bundle)


def test_epoch_out_of_range_raises():
    bundle = _bundle()
    bundle["sites"]["06036805"]["series"]["temperature_c"][0][0] = float("nan")
    with pytest.raises(ValueError):
        validate_usgs_bundle(bundle)


def test_met_out_of_range_raises():
    bundle = _bundle()
    bundle["met"]["hourly"][0][2] = 1.5
    with pytest.raises(ValueError):
        validate_usgs_bundle(bundle)


def test_hydro_units_accept_baseline():
    cfg = yaml.safe_load(open(BASE).read())
    validate_hydro_units(cfg["hydro"])


def test_hydro_units_reject_bad_boundary():
    with pytest.raises(ValueError):
        validate_hydro_units({"boundary_m3s": -2.0, "boundary_c": 17.5})
    with pytest.raises(ValueError):
        validate_hydro_units({"boundary_m3s": 8.0, "boundary_c": 500.0})


def test_validate_config_enforces_hydro_units(tmp_path):
    cfg = yaml.safe_load(open(BASE).read())
    cfg["world_root"] = str(tmp_path)
    validate_config(cfg)
    bad = yaml.safe_load(open(BASE).read())
    bad["world_root"] = str(tmp_path)
    bad["hydro"]["boundary_c"] = 500.0
    with pytest.raises(ValueError):
        validate_config(bad)


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'BASE', resolved_paths['BASE_CONFIG'], raising=False)


@pytest.mark.parametrize("validator", [check_discharge_m3s, check_temperature_c, check_epoch_s])
@pytest.mark.parametrize("value", [True, False, "1.0", float("nan"), float("inf"), None])
def test_range_validators_reject_coercible_and_nonfinite_inputs(validator, value):
    with pytest.raises(ValueError):
        validator(value)


@pytest.mark.parametrize("key", ["boundary_m3s", "boundary_c"])
@pytest.mark.parametrize("value", [True, False, "1.0", float("nan"), float("inf"), None])
def test_hydro_validation_preserves_input_type_checks(key, value):
    with pytest.raises(ValueError):
        validate_hydro_units({key: value})


@pytest.mark.parametrize("field", ["discharge_m3_s", "temperature_c"])
@pytest.mark.parametrize("column", [0, 1])
@pytest.mark.parametrize("value", [True, "1.0", float("nan"), float("inf")])
def test_bundle_gauge_series_preserve_input_type_checks(field, column, value):
    bundle = _bundle()
    bundle["sites"]["06036805"]["series"][field][0][column] = value
    with pytest.raises(ValueError):
        validate_usgs_bundle(bundle)


@pytest.mark.parametrize("column", range(6))
@pytest.mark.parametrize("value", [True, "1.0", float("nan"), float("inf")])
def test_bundle_met_rows_preserve_input_type_checks(column, value):
    bundle = _bundle()
    bundle["met"]["hourly"][0][column] = value
    with pytest.raises(ValueError):
        validate_usgs_bundle(bundle)


def test_upstream_temperature_control_endpoints_match_config_validation(tmp_path):
    from yellowstone_python.study_mode import SCHEMA, _validate
    entry = SCHEMA["hydro.boundary_c"]
    assert (entry["min"], entry["max"]) == TEMPERATURE_RANGE_C
    for value in TEMPERATURE_RANGE_C:
        _validate("hydro.boundary_c", value)
        validate_config({"world_root": str(tmp_path),
                         "hydro": {"boundary_m3s": 2.5, "boundary_c": value}})


@pytest.mark.parametrize("value", [-0.01, 35.01])
def test_upstream_temperature_outside_reviewed_range_is_rejected(tmp_path, value):
    from yellowstone_python.study_mode import _validate
    with pytest.raises(ValueError):
        _validate("hydro.boundary_c", value)
    with pytest.raises(ValueError):
        validate_config({"world_root": str(tmp_path),
                         "hydro": {"boundary_m3s": 2.5, "boundary_c": value}})
