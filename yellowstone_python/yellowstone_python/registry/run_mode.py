"""Run modes: declared interpretation of one build."""
from __future__ import annotations

from typing import Iterable

RUN_MODES = ("observed_replay", "hindcast", "scenario", "illustrative")
DEFAULT_RUN_MODE = "illustrative"

PRESCRIBED_DISCHARGE = "discharge"
PRESCRIBED_UPSTREAM_TEMPERATURE = "upstream_temperature"
PREDICTED_SNOW_RUNOFF = "snow_runoff_increment"

ALLOWED_PRESCRIBED_QUANTITIES = frozenset({PRESCRIBED_DISCHARGE,
                                           PRESCRIBED_UPSTREAM_TEMPERATURE})


def normalize_run_mode(mode) -> str:
    """Checked mode string. Absent mode returns the default."""
    if mode is None:
        return DEFAULT_RUN_MODE
    if not isinstance(mode, str):
        raise TypeError("run_mode must be a string or None")
    if mode == "forecast":
        raise ValueError(
            "run_mode 'forecast' needs forecast-specific evaluation "
            "before any build may use it")
    if mode not in RUN_MODES:
        raise ValueError(
            f"run_mode {mode!r} unknown; choose from {list(RUN_MODES)}")
    return mode


def _normalize_quantities(values, *,
                          restrict_to_prescribed: bool = False) -> set[str]:
    """Build a string set from a sequence or scalar.
restrict_to_prescribed enforces the allowed-forcing vocabulary."""
    if values is None:
        return set()
    if isinstance(values, str):
        iterable: Iterable = [values]
    elif isinstance(values, (list, tuple, set, frozenset)):
        iterable = values
    else:
        raise TypeError(
            "prescribed/validated must be a sequence of strings")
    result: set[str] = set()
    for item in iterable:
        if not isinstance(item, str):
            raise TypeError(f"quantity {item!r} is not a string")
        result.add(item)
    if restrict_to_prescribed:
        unknown = result - ALLOWED_PRESCRIBED_QUANTITIES
        if unknown:
            raise ValueError(
                f"unknown prescribed quantities: {sorted(unknown)}; "
                f"allowed: {sorted(ALLOWED_PRESCRIBED_QUANTITIES)}")
    return result


def prescribed_quantities(cfg: dict) -> list:
    """Quantities prescribed as forcing by this config.
A replay block prescribes a quantity when the solver carries an explicit series."""
    out: list[str] = []
    hydro = cfg.get("hydro", {})
    if "boundary_m3s" in hydro:
        out.append(PRESCRIBED_DISCHARGE)
    if "boundary_c" in hydro:
        out.append(PRESCRIBED_UPSTREAM_TEMPERATURE)
    replay = cfg.get("replay")
    if isinstance(replay, dict):
        if "discharge" in replay and PRESCRIBED_DISCHARGE not in out:
            out.append(PRESCRIBED_DISCHARGE)
        if ("upstream_temperature" in replay
                and PRESCRIBED_UPSTREAM_TEMPERATURE not in out):
            out.append(PRESCRIBED_UPSTREAM_TEMPERATURE)
    return sorted(out)


def predicted_quantities(cfg: dict) -> list:
    """Model-derived quantities (tracked apart from the prescribed list).
Baseflow stays prescribed; a snow-derived runoff increment is reported here."""
    catchment = (cfg.get("hydro", {}) or {}).get("catchment", {}) or {}
    if catchment.get("area_m2") is None:
        return []
    return [PREDICTED_SNOW_RUNOFF]


def claim_allowed(mode: str, quantity: str, prescribed) -> bool:
    """Whether a validation claim on quantity may be reported."""
    normalize_run_mode(mode)
    if not isinstance(quantity, str):
        raise TypeError("quantity must be a string")
    return quantity not in _normalize_quantities(
        prescribed, restrict_to_prescribed=True)


def check_split(prescribed, validated) -> None:
    """Raise when a validated quantity is also prescribed forcing."""
    prescribed_set = _normalize_quantities(
        prescribed, restrict_to_prescribed=True)
    validated_set = _normalize_quantities(validated)
    overlap = sorted(prescribed_set & validated_set)
    if overlap:
        raise ValueError(
            f"quantities {overlap} are prescribed forcing; validation "
            f"covers unprescribed outputs")
