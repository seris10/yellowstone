"""validate: NaN guards, topology, conservation, provenance."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as assert_finite
import warnings

_DEPRECATED_HEAT_KEYS = ("heat_budget_error", "residual")




def check_reach_chain(reaches: list) -> list[str]:
    """Serial chain upstream-first; ecosystem.gd supports a single chain."""
    errors = []
    seen = set()
    for i, r in enumerate(reaches):
        rid = r.get("id", "")
        if not rid or rid in seen:
            errors.append(f"invalid/duplicate reach id: {rid!r}")
        seen.add(rid)
        if float(r.get("volume_m3", 0)) <= 0:
            errors.append(f"reach {rid}: volume_m3 must be > 0")
        up = r.get("upstream_id", "")
        if i == 0:
            if up:
                errors.append(f"first reach {rid} must have empty upstream_id")
        elif up != reaches[i - 1].get("id"):
            errors.append(f"reach {rid}: branching/gap unsupported "
                          f"(upstream {up!r} != previous {reaches[i-1].get('id')!r})")
    return errors


def check_heat_ledger(ledger: dict, heat_tol_j: float = 1e-6,
                      water_tol_m3: float = 1e-6, *,
                      tol: float | None = None) -> list[str]:
    """Return failures for the ledger; canonical heat key is heat_budget_error_j."""
    if tol is not None:
        heat_tol_j = water_tol_m3 = tol
    failures: list[str] = []
    heat_val = ledger.get("heat_budget_error_j")
    legacy_present = [k for k in _DEPRECATED_HEAT_KEYS if k in ledger]
    if heat_val is None and not legacy_present:
        failures.append("ledger missing heat_budget_error_j")
        return failures
    if heat_val is None:
        heat_val = ledger[legacy_present[0]]
        warnings.warn(
            f"ledger uses deprecated heat key {legacy_present[0]!r}; "
            "rename to heat_budget_error_j",
            DeprecationWarning, stacklevel=2)
    for key in legacy_present:
        legacy_val = ledger[key]
        if heat_val is not None and legacy_val is not None:
            if abs(float(legacy_val) - float(heat_val)) > heat_tol_j:
                failures.append(
                    f"ledger carries {key}={legacy_val} and "
                    f"heat_budget_error_j={heat_val}; values disagree")
    if heat_val is None or abs(float(heat_val)) > heat_tol_j:
        failures.append(
            f"heat residual {heat_val} exceeds tol {heat_tol_j}")
    w = ledger.get("water_budget_error_m3", 0.0) or 0.0
    if abs(float(w)) > water_tol_m3:
        failures.append(f"water residual {w} exceeds tol {water_tol_m3}")
    return failures


def check_provenance(doc: dict) -> list[str]:
    errors = []
    for k in ("contract_version", "world_id", "code_rev", "status",
              "parameter_provenance", "sources"):
        if k not in doc:
            errors.append(f"missing provenance key: {k}")
    return errors
