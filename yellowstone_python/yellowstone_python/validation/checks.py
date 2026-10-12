"""M11 checks: conservation, topology, provenance, determinism gates."""
from __future__ import annotations

from ..common.validate import (check_heat_ledger, check_provenance,
                               check_reach_chain)
from ..run_mode import DEFAULT_RUN_MODE, RUN_MODES, check_split


def run_all(*, river_state, ledger, ecosystem_doc, build_id_a,
            build_id_b=None, run_mode=DEFAULT_RUN_MODE,
            prescribed=(), validated_quantities=(), replay_doc=None,
            landscape=None, membership=None, chainage=None,
            chainage_offset_m=0.0) -> dict:
    """Return {passed, failures, metrics, run_mode, prescribed_quantities}."""
    failures: list[str] = []
    failures += check_reach_chain(river_state)
    failures += check_heat_ledger(ledger, tol=1e-9)
    failures += ["provenance: " + e for e in check_provenance(ecosystem_doc)]
    if run_mode not in RUN_MODES:
        if run_mode == "forecast":
            failures.append("run_mode forecast needs forecast-specific "
                            "evaluation")
        else:
            failures.append(f"run_mode {run_mode!r} unknown")
    try:
        check_split(prescribed, validated_quantities)
    except ValueError as exc:
        failures.append(str(exc))
    # Downstream monotone temperature is NOT required (hot lateral warms mid-chain);
    # instead assert no NaN and fish_activity in [0,1]. Monotone STAGE (water surface
    # never climbs downstream) is a baked-geometry invariant and lives where the
    # geometry lives: yellowstone_midway/tools/validate_world.py (Firehole
    # northward-order + climb check). Do not re-add a temperature version here.
    for r in river_state:
        fa = float(r.get("fish_activity", -1))
        if not (0.0 <= fa <= 1.0):
            failures.append(f"reach {r.get('id')}: fish_activity {fa} out of [0,1]")
    metrics = {"heat_budget_error": ledger.get("heat_budget_error"),
               "water_budget_error_m3": ledger.get("water_budget_error_m3"),
               "n_reaches": len(river_state)}
    try:
        from ..replay.benchmarks import run_all_benchmarks
        numerics = run_all_benchmarks()
        metrics["numerics_passed"] = numerics["passed"]
        metrics["numerics_excluded"] = [e["benchmark"]
                                        for e in numerics["not_applicable"]]
        for result in numerics["results"]:
            metrics[f"numerics_{result['name']}"] = result["passed"]
            if not result["passed"]:
                failures.append(f"numerics: {result['name']} failed")
    except (ValueError, ArithmeticError) as exc:
        metrics["numerics_passed"] = False
        failures.append(f"numerics: benchmark error ({exc})")
    if replay_doc is not None and landscape is not None:
        from ..coupling import check_coupling
        coupling = check_coupling(replay_doc, landscape)
        metrics["coupling_passed"] = coupling["passed"]
        metrics.update({f"coupling_{k}": v
                        for k, v in coupling["metrics"].items()})
        failures += [f"coupling: {e}" for e in coupling["failures"]]
    if landscape is not None and membership is not None and chainage is not None:
        from ..coupling import check_cross_family
        cross = check_cross_family(landscape, river_state, membership,
                                   chainage,
                                   chainage_offset_m=chainage_offset_m)
        metrics["cross_family_passed"] = cross["passed"]
        metrics.update(cross["metrics"])
        failures += [f"cross-family: {e}" for e in cross["failures"]]
    if build_id_b is not None and build_id_a != build_id_b:
        failures.append(f"non-deterministic build_id: {build_id_a} != {build_id_b}")
    return {"passed": not failures, "failures": failures, "metrics": metrics,
            "run_mode": run_mode,
            "prescribed_quantities": sorted(set(prescribed))}
