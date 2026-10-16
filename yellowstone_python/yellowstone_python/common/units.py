"""Unit converters and dimensional validation."""
from __future__ import annotations

from typing import Any

from yellowstone_python.common.checks import finite, positive as require_positive, fraction as require_fraction


class UnitError(ValueError):
    pass


M3S_PER_US_GPM = 3.785411784e-3 / 60.0
US_GPM_PER_M3S = 1.0 / M3S_PER_US_GPM

M3S_PER_GPM = M3S_PER_US_GPM
GPM_PER_M3S = US_GPM_PER_M3S


def c_to_k(c: float) -> float:
    """Celsius to Kelvin; rejects values below absolute zero (-273.15 C)."""
    c = _unit_number("Celsius", c)
    if c < -273.15:
        raise UnitError(f"Celsius below absolute zero: {c}")
    return c + 273.15


def k_to_c(k: float) -> float:
    k = _unit_number("Kelvin", k)
    if k < 0:
        raise UnitError(f"Kelvin cannot be negative: {k}")
    return k - 273.15


def us_gpm_to_m3s(gpm: float) -> float:
    gpm = _unit_number("discharge", gpm)
    if gpm < 0:
        raise UnitError(f"discharge cannot be negative: {gpm}")
    return gpm * M3S_PER_US_GPM


def m3s_to_us_gpm(m3s: float) -> float:
    m3s = _unit_number("discharge", m3s)
    if m3s < 0:
        raise UnitError(f"discharge cannot be negative: {m3s}")
    return m3s * US_GPM_PER_M3S

def _unit_number(name: str, value: object) -> float:
    """Validate a numeric converter input using the unit API error type."""
    try:
        return finite(name, value)
    except ValueError as exc:
        raise UnitError(str(exc)) from exc


def label_index(name: str, value: float) -> dict:
    """Wrap a dimensionless 0..1 index with a units tag."""
    return {"name": name, "value": require_fraction(name, value),
            "units": "dimensionless_index_0_1",
            "warning": "relative index only; kg and organism counts are not implied"}


try:
    import pint
    _UREG = pint.UnitRegistry()
    HAS_PINT = True
except ImportError:
    _UREG = None
    HAS_PINT = False

UNIT_DOC = {
    "discharge": "meter**3/second",
    "temperature": "degree_Celsius",
    "epoch": "second",
    "length": "meter",
    "velocity": "meter/second",
    "irradiance": "watt/meter**2",
}

DISCHARGE_RANGE_M3S = (0.0, 200.0)
# Liquid water at ambient Firehole pressure; Goldstein (2001) peaks near 30 C.
TEMPERATURE_RANGE_C = (0.0, 35.0)
EPOCH_RANGE_S = (0.0, 5.0e9)
# West Yellowstone surface air extremes with margin.
AIR_RANGE_C = (-50.0, 40.0)
RH_RANGE = (0.0, 1.0)
# Aligned with yellowstone_midway/scripts/weather_snapshot_reader.gd clamp.
WIND_RANGE_MPS = (0.0, 65.0)
SHORTWAVE_RANGE_W_M2 = (0.0, 1400.0)
CLOUD_RANGE = (0.0, 1.0)


def _quantity(value: float, unit: str) -> Any:
    # Pint dimensionality check. Plain float where pint is absent.
    if not HAS_PINT:
        return float(value)
    return _UREG.Quantity(float(value), unit)


def _check_range(name: str, value: float, bounds: tuple,
                 unit: str) -> float:
    result = finite(name, value)
    _quantity(result, unit)
    if not (bounds[0] <= result <= bounds[1]):
        raise ValueError(f"{name}={result} outside {bounds} {unit}")
    return result


def check_discharge_m3s(value: float, name: str = "discharge") -> float:
    """Discharge in m3/s within the Firehole ingestion range."""
    return _check_range(name, value, DISCHARGE_RANGE_M3S,
                        UNIT_DOC["discharge"])


def check_temperature_c(value: float, name: str = "temperature") -> float:
    """Temperature in Celsius within the ingestion range."""
    return _check_range(name, value, TEMPERATURE_RANGE_C,
                        UNIT_DOC["temperature"])


def check_epoch_s(value: float, name: str = "epoch") -> float:
    """Epoch timestamp in seconds within the ingestion range."""
    return _check_range(name, value, EPOCH_RANGE_S, UNIT_DOC["epoch"])


def validate_usgs_bundle(bundle: dict[str, Any]) -> None:
    """Unit validation for a Firehole obs bundle on load."""
    sites = bundle.get("sites", {})
    for site_id, record in sites.items():
        series = record.get("series", {})
        for pair in series.get("discharge_m3_s", []):
            check_epoch_s(pair[0], f"{site_id} discharge epoch")
            check_discharge_m3s(pair[1], f"{site_id} discharge")
        for pair in series.get("temperature_c", []):
            check_epoch_s(pair[0], f"{site_id} temperature epoch")
            check_temperature_c(pair[1], f"{site_id} temperature")
    for row in bundle.get("met", {}).get("hourly", []):
        check_epoch_s(row[0], "met epoch")
        _check_range("met air_c", row[1], AIR_RANGE_C,
                     UNIT_DOC["temperature"])
        _check_range("met rh", row[2], RH_RANGE, "dimensionless")
        _check_range("met wind_mps", row[3], WIND_RANGE_MPS,
                     UNIT_DOC["velocity"])
        _check_range("met shortwave_w_m2", row[4],
                     SHORTWAVE_RANGE_W_M2, UNIT_DOC["irradiance"])
        _check_range("met cloud", row[5], CLOUD_RANGE, "dimensionless")


def validate_hydro_units(hydro: dict[str, Any]) -> None:
    """Config hydro boundary units: m3/s discharge, Celsius temperature."""
    if "boundary_m3s" in hydro:
        check_discharge_m3s(hydro["boundary_m3s"],
                            "hydro.boundary_m3s")
    if "boundary_c" in hydro:
        check_temperature_c(hydro["boundary_c"],
                            "hydro.boundary_c")
