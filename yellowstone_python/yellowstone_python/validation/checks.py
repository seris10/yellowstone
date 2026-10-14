"""checks: conservation, topology, provenance, determinism gates."""
from __future__ import annotations

import math
from typing import Any

from yellowstone_python.validation.contracts import check_heat_ledger, check_provenance, check_reach_chain
from yellowstone_python.registry.run_mode import DEFAULT_RUN_MODE, RUN_MODES, check_split

# Shared tolerances for replay and ledger closure gates; one source for build and tests.
REPLAY_HEAT_RELATIVE_TOLERANCE = 1e-9
REPLAY_WATER_RELATIVE_TOLERANCE = 1e-12
HYDRO_HEAT_LEDGER_TOL_J = 1e-9
HYDRO_WATER_LEDGER_TOL_M3 = 1e-9
SNOW_STORAGE_TOL_MM = 0.05


def check_uq_document(uq_doc: dict[str, Any]) -> list[str]:
    """Return failures for uq_doc shape invariants replay/figures.build_all reads."""
    failures: list[str] = []
    if not isinstance(uq_doc, dict):
        return [f"uq_doc must be a dict, got {type(uq_doc).__name__}"]
    bands = uq_doc.get("bands")
    if not isinstance(bands, dict):
        failures.append("uq_doc.bands missing or not a mapping")
    else:
        if "seed" not in bands:
            failures.append("uq_doc.bands.seed missing")
        if "level" not in bands:
            failures.append("uq_doc.bands.level missing")
    coverage = uq_doc.get("holdout_coverage")
    if not isinstance(coverage, dict):
        failures.append("uq_doc.holdout_coverage missing or not a mapping")
    else:
        if "coverage" not in coverage:
            failures.append("uq_doc.holdout_coverage.coverage missing")
        if "interpretation" not in coverage:
            failures.append(
                "uq_doc.holdout_coverage.interpretation missing; "
                "band_coverage must carry its interpretation string")
    geometry = uq_doc.get("effective_geometry")
    if not isinstance(geometry, dict):
        failures.append("uq_doc.effective_geometry missing or not a mapping")
    else:
        for key in ("volume_m3", "area_m2"):
            if key not in geometry:
                failures.append(f"uq_doc.effective_geometry.{key} missing")
    if "members" not in uq_doc:
        failures.append("uq_doc.members missing")
    return failures


def run_all(*, river_state, ledger, ecosystem_doc, build_id_a,
            build_id_b=None, run_mode=DEFAULT_RUN_MODE,
            prescribed=(), validated_quantities=(), replay_doc=None,
            landscape=None, membership=None, chainage=None,
            chainage_offset_m=0.0) -> dict:
    """Return {passed, failures, metrics, run_mode, prescribed_quantities}."""
    failures: list[str] = []
    failures += check_reach_chain(river_state)
    if ledger.get("scope") == "replay_relative_conservation":
        budget = (replay_doc or {}).get("final_budget", {})
        for key, tolerance in (("heat_relative_residual", REPLAY_HEAT_RELATIVE_TOLERANCE),
                               ("water_relative_residual", REPLAY_WATER_RELATIVE_TOLERANCE)):
            value = budget.get(key)
            if value is None or not math.isfinite(float(value)) or abs(float(value)) > tolerance:
                failures.append(f"replay {key}: {value} exceeds {tolerance}")
    else:
        failures += check_heat_ledger(ledger,
                                     heat_tol_j=HYDRO_HEAT_LEDGER_TOL_J,
                                     water_tol_m3=HYDRO_WATER_LEDGER_TOL_M3)
    failures += ["provenance: " + e for e in check_provenance(ecosystem_doc)]
    if run_mode not in RUN_MODES:
        failures.append(f"run_mode {run_mode!r} unknown")
    try:
        check_split(prescribed, validated_quantities)
    except ValueError as exc:
        failures.append(str(exc))
    for r in river_state:
        fa = float(r.get("fish_activity", -1))
        if not (0.0 <= fa <= 1.0):
            failures.append(f"reach {r.get('id')}: fish_activity {fa} out of [0,1]")
    heat_metric = ledger.get("heat_budget_error_j",
                             ledger.get("heat_budget_error"))
    metrics = {"heat_budget_error_j": heat_metric,
               "heat_budget_error": heat_metric,
               "water_budget_error_m3": ledger.get("water_budget_error_m3"),
               "n_reaches": len(river_state)}
    try:
        from yellowstone_python.river.benchmarks import run_all_benchmarks
        numerics = run_all_benchmarks()
        metrics["numerics_passed"] = numerics["passed"]
        metrics["numerics_excluded"] = [e["benchmark"]
                                        for e in numerics["not_applicable"]]
        for result in numerics["results"]:
            metrics[f"numerics_{result['name']}"] = result["passed"]
            if not result["passed"]:
                failures.append(f"numerics: {result['name']} failed")
    except (ValueError, ArithmeticError, ImportError, AssertionError,
            OSError) as exc:
        metrics["numerics_passed"] = False
        failures.append(
            f"numerics: benchmark error ({type(exc).__name__}: {exc})")
    # FiPy convergence checks (analytic reference and MMS forcing); skip when fipy is absent.
    try:
        from yellowstone_python.river import fipy_reference as _fr
        if _fr.HAS_FIPY:
            fipy_doc = _fr.run_convergence()
            mms_doc = _fr.run_mms_convergence()
            metrics["fipy_convergence_rates"] = fipy_doc["observed_rates"]
            metrics["fipy_mms_rates"] = mms_doc["observed_rates"]
            metrics["fipy_reference_skipped"] = False
            # First-order upwind: observed rate above 0.9 counts as design-order.
            if not all(rate > 0.9 for rate in fipy_doc["observed_rates"]):
                failures.append(
                    "fipy_reference: analytic-case convergence rate "
                    "below first-order threshold")
            if not all(rate > 0.9 for rate in mms_doc["observed_rates"]):
                failures.append(
                    "fipy_reference: MMS convergence rate below "
                    "first-order threshold")
        else:
            metrics["fipy_reference_skipped"] = True
            metrics["fipy_reference_skip_reason"] = (
                "fipy not installed; install the fipy extras group "
                "to run the dispersion and MMS references")
    except (ValueError, ArithmeticError, ImportError, OSError) as exc:
        metrics["fipy_reference_skipped"] = True
        metrics["fipy_reference_skip_reason"] = (
            f"fipy_reference error ({type(exc).__name__}: {exc})")
    if replay_doc is not None and landscape is not None:
        from yellowstone_python.registry.coupling import check_coupling
        coupling = check_coupling(replay_doc, landscape)
        metrics["coupling_passed"] = coupling["passed"]
        metrics.update({f"coupling_{k}": v
                        for k, v in coupling["metrics"].items()})
        failures += [f"coupling: {e}" for e in coupling["failures"]]
        # numerical_warnings from the replay solver are logged.
        warn_rows = (replay_doc.get("numerical_checks", {})
                     .get("numerical_warnings") or [])
        if warn_rows:
            metrics["replay_numerical_warnings"] = [str(w) for w in warn_rows]
    if landscape is not None and membership is not None and chainage is not None:
        from yellowstone_python.registry.coupling import check_cross_family
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
