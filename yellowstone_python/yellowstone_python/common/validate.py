"""M00 validate: NoData/NaN guards, topology, conservation, provenance checks."""
from __future__ import annotations

import math


def assert_finite(name: str, value: float) -> float:
    if value is None or (isinstance(value, float) and
                         (math.isnan(value) or math.isinf(value))):
        raise ValueError(f"{name} is missing/non-finite (null, NaN, inf forbidden)")
    return value


def check_reach_chain(reaches: list) -> list[str]:
    """Must be an upstream-first serial chain (ecosystem.gd supports one chain)."""
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


def check_heat_ledger(ledger: dict, tol: float = 1e-6) -> list[str]:
    resid = ledger.get("residual", ledger.get("heat_budget_error"))
    if resid is None or abs(resid) > tol:
        return [f"heat residual {resid} exceeds tol {tol}"]
    w = ledger.get("water_budget_error_m3", 0.0) or 0.0
    if abs(w) > tol:
        return [f"water residual {w} exceeds tol {tol}"]
    return []


def check_provenance(doc: dict) -> list[str]:
    errors = []
    for k in ("contract_version", "world_id", "code_rev", "status",
              "parameter_provenance", "sources"):
        if k not in doc:
            errors.append(f"missing provenance key: {k}")
    return errors
