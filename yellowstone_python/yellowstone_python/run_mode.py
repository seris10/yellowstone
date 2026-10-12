"""Run modes: declared interpretation of one build."""
from __future__ import annotations

RUN_MODES = ("observed_replay", "hindcast", "scenario", "illustrative")
DEFAULT_RUN_MODE = "illustrative"

PRESCRIBED_DISCHARGE = "discharge"
PRESCRIBED_UPSTREAM_TEMPERATURE = "upstream_temperature"
PREDICTED_SNOW_RUNOFF = "snow_runoff_increment"


def normalize_run_mode(mode) -> str:
    """Checked mode string. Absent mode returns the default."""
    if mode is None:
        return DEFAULT_RUN_MODE
    if mode == "forecast":
        raise ValueError(
            "run_mode 'forecast' needs forecast-specific evaluation "
            "before any build may use it")
    if mode not in RUN_MODES:
        raise ValueError(
            f"run_mode {mode!r} unknown; choose from {list(RUN_MODES)}")
    return mode


def prescribed_quantities(cfg: dict) -> list:
    """Quantities prescribed as forcing by this config.

    Prescribed quantities count as forcing. Validation covers
    unprescribed outputs.
    """
    out = []
    hydro = cfg.get("hydro", {})
    if "boundary_m3s" in hydro:
        out.append(PRESCRIBED_DISCHARGE)
    if "boundary_c" in hydro:
        out.append(PRESCRIBED_UPSTREAM_TEMPERATURE)
    if "replay" in cfg:
        for q in (PRESCRIBED_DISCHARGE, PRESCRIBED_UPSTREAM_TEMPERATURE):
            if q not in out:
                out.append(q)
    return sorted(out)


def predicted_quantities(cfg: dict) -> list:
    """Quantities this config derives from a model rather than prescribing.

    Baseflow stays prescribed; a snow-derived runoff increment on top of it is
    model output, so it is tracked apart from the prescribed list.
    """
    catchment = (cfg.get("hydro", {}) or {}).get("catchment", {}) or {}
    if catchment.get("area_m2") is None:
        return []
    return [PREDICTED_SNOW_RUNOFF]


def claim_allowed(mode: str, quantity: str, prescribed) -> bool:
    """Whether a validation claim on quantity may be reported."""
    normalize_run_mode(mode)
    return quantity not in set(prescribed)


def check_split(prescribed, validated) -> None:
    """Raise when a validated quantity is also prescribed forcing."""
    overlap = sorted(set(prescribed) & set(validated))
    if overlap:
        raise ValueError(
            f"quantities {overlap} are prescribed forcing; validation "
            f"covers unprescribed outputs")
