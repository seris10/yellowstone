"""M00 units: explicit converters. Fail loudly on bare/mixed units."""
from __future__ import annotations


class UnitError(ValueError):
    pass


M3S_PER_GPM = 0.0000630902  # 1 US gal/min in m3/s
GPM_PER_M3S = 1.0 / M3S_PER_GPM


def c_to_k(c: float) -> float:
    return c + 273.15


def k_to_c(k: float) -> float:
    if k < 0:
        raise UnitError(f"Kelvin cannot be negative: {k}")
    return k - 273.15


def gpm_to_m3s(gpm: float) -> float:
    if gpm < 0:
        raise UnitError(f"discharge cannot be negative: {gpm}")
    return gpm * M3S_PER_GPM


def m3s_to_gpm(m3s: float) -> float:
    if m3s < 0:
        raise UnitError(f"discharge cannot be negative: {m3s}")
    return m3s * GPM_PER_M3S


def require_positive(name: str, value: float) -> float:
    if not (value > 0):
        raise UnitError(f"{name} must be > 0, got {value}")
    return value


def require_fraction(name: str, value: float) -> float:
    if not (0.0 <= value <= 1.0):
        raise UnitError(f"{name} must be in [0,1], got {value}")
    return value


def label_index(name: str, value: float) -> dict:
    """Wrap a dimensionless 0..1 index so it can never be mistaken for kg/counts."""
    return {"name": name, "value": require_fraction(name, value),
            "units": "dimensionless_index_0_1",
            "warning": "relative index only; not kg, not organism counts"}
