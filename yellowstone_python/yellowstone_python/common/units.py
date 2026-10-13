"""M00 units: explicit converters. Fail loudly on bare or mixed units."""
from __future__ import annotations

import warnings


class UnitError(ValueError):
    pass


M3S_PER_US_GPM = 3.785411784e-3 / 60.0
US_GPM_PER_M3S = 1.0 / M3S_PER_US_GPM

M3S_PER_GPM = M3S_PER_US_GPM
GPM_PER_M3S = US_GPM_PER_M3S


def c_to_k(c: float) -> float:
    """Celsius to Kelvin; rejects values below absolute zero (-273.15 C)."""
    if c < -273.15:
        raise UnitError(f"Celsius below absolute zero: {c}")
    return c + 273.15


def k_to_c(k: float) -> float:
    if k < 0:
        raise UnitError(f"Kelvin cannot be negative: {k}")
    return k - 273.15


def us_gpm_to_m3s(gpm: float) -> float:
    if gpm < 0:
        raise UnitError(f"discharge cannot be negative: {gpm}")
    return gpm * M3S_PER_US_GPM


def m3s_to_us_gpm(m3s: float) -> float:
    if m3s < 0:
        raise UnitError(f"discharge cannot be negative: {m3s}")
    return m3s * US_GPM_PER_M3S


def gpm_to_m3s(gpm: float) -> float:
    """Alias for us_gpm_to_m3s; emits a DeprecationWarning on each call."""
    warnings.warn(
        "gpm_to_m3s is deprecated; call us_gpm_to_m3s to disambiguate US and "
        "imperial gallons",
        DeprecationWarning, stacklevel=2)
    return us_gpm_to_m3s(gpm)


def m3s_to_gpm(m3s: float) -> float:
    """Alias for m3s_to_us_gpm; emits a DeprecationWarning on each call."""
    warnings.warn(
        "m3s_to_gpm is deprecated; call m3s_to_us_gpm to disambiguate US and "
        "imperial gallons",
        DeprecationWarning, stacklevel=2)
    return m3s_to_us_gpm(m3s)


def require_positive(name: str, value: float) -> float:
    if not (value > 0):
        raise UnitError(f"{name} must be > 0, got {value}")
    return value


def require_fraction(name: str, value: float) -> float:
    if not (0.0 <= value <= 1.0):
        raise UnitError(f"{name} must be in [0,1], got {value}")
    return value


def label_index(name: str, value: float) -> dict:
    """Wrap a dimensionless 0..1 index with a units tag."""
    return {"name": name, "value": require_fraction(name, value),
            "units": "dimensionless_index_0_1",
            "warning": "relative index only; kg and organism counts are not implied"}
