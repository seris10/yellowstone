import pytest
import yaml

from yellowstone_python.build import validate_config
from yellowstone_python.common.hydro_units import (
    AIR_RANGE_C,
    TEMPERATURE_RANGE_C,
    UNIT_DOC,
    WIND_RANGE_MPS,
    validate_hydro_units,
    validate_usgs_bundle,
)

from paths import BASE_CONFIG as BASE


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
    from yellowstone_python.common.hydro_units import check_temperature_c
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


def test_validate_config_enforces_hydro_units():
    cfg = yaml.safe_load(open(BASE).read())
    validate_config(cfg)
    bad = yaml.safe_load(open(BASE).read())
    bad["hydro"]["boundary_c"] = 500.0
    with pytest.raises(ValueError):
        validate_config(bad)
