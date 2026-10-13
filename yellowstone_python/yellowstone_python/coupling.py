"""Component coupling contract for water, heat, and landscape mapping."""
from __future__ import annotations

import math
from typing import Any

EXCHANGE_FIELDS = ("exchange_id", "quantity", "units", "sign_convention",
                   "spatial_support", "temporal_support", "kind", "source",
                   "destination", "method", "conservation")

POCKET_CONSERVATION = "non_conservative"
PRESCRIBED_INCREMENT = "prescribed_increment"

CROSS_FAMILY_TOLERANCE_C = 2.0

SURFACE_METHODS = ("newton_lumped", "explicit_budget")

VALID_KINDS = ("transfer", "mapping", "prescription")
VALID_CONSERVATIONS = ("conserved", "mapped", POCKET_CONSERVATION,
                       PRESCRIBED_INCREMENT)

EXCHANGES = [
    {
        "exchange_id": "boundary_water",
        "quantity": "upstream water inflow",
        "units": "m3/s",
        "sign_convention": "positive into domain",
        "spatial_support": "upstream face",
        "temporal_support": "instantaneous rate",
        "kind": "transfer",
        "source": "prescribed boundary forcing",
        "destination": "solver cell 0",
        "method": "advective face flux with zero dispersive boundary flux",
        "conservation": "conserved",
    },
    {
        "exchange_id": "boundary_heat",
        "quantity": "thermal energy carried by upstream inflow",
        "units": "J/s",
        "sign_convention": "positive into domain",
        "spatial_support": "upstream face",
        "temporal_support": "instantaneous rate",
        "kind": "transfer",
        "source": "prescribed boundary forcing",
        "destination": "solver cell 0",
        "method": "face discharge times boundary temperature",
        "conservation": "conserved",
    },
    {
        "exchange_id": "lateral_water",
        "quantity": "tributary water inflow per source",
        "units": "m3/s",
        "sign_convention": "positive into receiving cell",
        "spatial_support": "receiving cell",
        "temporal_support": "instantaneous rate",
        "kind": "transfer",
        "source": "ecosystem lateral_sources or scenario pulse",
        "destination": "solver cell at connection chainage",
        "method": "one solver Source per ecosystem lateral",
        "conservation": "conserved",
    },
    {
        "exchange_id": "lateral_heat",
        "quantity": "thermal energy carried by lateral inflow",
        "units": "J/s",
        "sign_convention": "positive into receiving cell",
        "spatial_support": "receiving cell",
        "temporal_support": "instantaneous rate",
        "kind": "transfer",
        "source": "ecosystem lateral_sources or scenario pulse",
        "destination": "solver cell at connection chainage",
        "method": "lateral discharge times lateral temperature",
        "conservation": "conserved",
    },
    {
        "exchange_id": "outlet_export",
        "quantity": "downstream water and heat export",
        "units": "m3/s and J/s",
        "sign_convention": "positive out of domain",
        "spatial_support": "downstream face",
        "temporal_support": "instantaneous rate",
        "kind": "transfer",
        "source": "solver last cell",
        "destination": "outside domain",
        "method": "advective face flux with zero dispersive boundary flux",
        "conservation": "conserved",
    },
    {
        "exchange_id": "surface_newton",
        "quantity": "lumped surface heat exchange",
        "units": "W/m2",
        "sign_convention": "positive into water",
        "spatial_support": "cell surface area",
        "temporal_support": "instantaneous flux",
        "kind": "transfer",
        "source": "prescribed air temperature series",
        "destination": "solver cell",
        "method": "Newton coefficient times air-minus-water temperature",
        "conservation": "conserved",
    },
    {
        "exchange_id": "surface_budget",
        "quantity": "shortwave, longwave, sensible, latent heat fluxes",
        "units": "W/m2",
        "sign_convention": "positive into water",
        "spatial_support": "cell surface area",
        "temporal_support": "instantaneous flux",
        "kind": "transfer",
        "source": "prescribed meteorology series",
        "destination": "solver cell",
        "method": ("explicit surface budget solved by damped Newton "
                   "iteration; final nonlinear flux used for accounting"),
        "conservation": "conserved",
    },
    {
        "exchange_id": "landscape_temperature",
        "quantity": "cell time-mean temperature and hydraulics",
        "units": "C, m/s, m, Pa",
        "sign_convention": "values as simulated",
        "spatial_support": "solver cell",
        "temporal_support": "interval mean over replay frames",
        "kind": "mapping",
        "source": "solver cells and frames",
        "destination": "landscape cell",
        "method": "thermal_landscape time mean, one record per cell",
        "conservation": "mapped",
    },
    {
        "exchange_id": "pocket_holding",
        "quantity": "prescribed tributary mouth-pocket holding water",
        "units": "C, m/s, m",
        "sign_convention": "values as prescribed",
        "spatial_support": "off-channel pocket cell",
        "temporal_support": "fixed scenario value",
        "kind": "prescription",
        "source": "authored scenario specification",
        "destination": "landscape cell",
        "method": "build_tributary_cell with recorded provenance",
        "conservation": POCKET_CONSERVATION,
    },
    {
        "exchange_id": "snow_runoff_discharge",
        "quantity": "mean snow-ledger runoff increment",
        "units": "m3/s",
        "sign_convention": "positive added to prescribed baseflow",
        "spatial_support": "configured catchment area",
        "temporal_support": "constant scalar over the configured replay",
        "kind": "prescription",
        "source": "snow_season ledger runoff_mm over the modeled patches",
        "destination": ("upstream boundary discharge increment applied to "
                        "the legacy chain and the replay (constant scalar; "
                        "not a routed hydrograph)"),
        "method": ("illustrative mean patch runoff depth scaled to the "
                   "configured catchment area and divided by the season "
                   "window"),
        "conservation": PRESCRIBED_INCREMENT,
    },
    {
        "exchange_id": "shear_disturbance",
        "quantity": "benthic disturbance fraction from bed shear",
        "units": "dimensionless in [0, 1]",
        "sign_convention": "0 calm, 1 fully disturbed",
        "spatial_support": "landscape cell",
        "temporal_support": "fixed per run",
        "kind": "mapping",
        "source": "mapped bed shear",
        "destination": "insect development",
        "method": "ramp from threshold to twice threshold, null maps to 0",
        "conservation": "mapped",
    },
]


def validate_contract() -> list[str]:
    """Field presence, vocabulary, and id uniqueness over the exchanges."""
    errors: list[str] = []
    for record in EXCHANGES:
        exchange_id = record.get("exchange_id", "?")
        for field in EXCHANGE_FIELDS:
            value = record.get(field)
            if field not in record:
                errors.append(f"{exchange_id}: missing {field}")
                continue
            if isinstance(value, str) and not value.strip():
                errors.append(f"{exchange_id}: empty {field}")
        kind = record.get("kind")
        if kind not in VALID_KINDS:
            errors.append(f"{exchange_id}: invalid kind {kind!r}")
        conservation = record.get("conservation")
        if conservation not in VALID_CONSERVATIONS:
            errors.append(
                f"{exchange_id}: invalid conservation {conservation!r}")
    ids: list[str] = []
    for record in EXCHANGES:
        raw_id = record.get("exchange_id")
        if raw_id is not None:
            ids.append(raw_id)
    if len(ids) != len(set(ids)):
        errors.append("duplicate exchange_id in contract")
    return errors


def _records_with_ids(records: Any, label: str,
                      failures: list[str]) -> list[dict[str, Any]]:
    """Dict records with a nonempty string id; others become failures."""
    if not isinstance(records, list):
        failures.append(f"{label} must be a list")
        return []
    result: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"{label}[{index}] must be an object")
            continue
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            failures.append(f"{label}[{index}] lacks a nonempty string id")
            continue
        result.append(record)
    return result


def _finite_float(value: Any) -> float | None:
    """Finite float, or None for non-numeric or non-finite input."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _unwrap(document: dict[str, Any]) -> dict[str, Any]:
    if "cells" in document:
        return document
    for key in ("replay", "data"):
        inner = document.get(key)
        if isinstance(inner, dict):
            try:
                return _unwrap(inner)
            except ValueError:
                continue
    raise ValueError("not a recognized replay document (no cells)")


def check_coupling(replay_doc: dict[str, Any],
                   landscape: list[dict[str, Any]]) -> dict[str, Any]:
    """One authoritative record per exchange; pockets labeled held."""
    failures: list[str] = []
    try:
        rep = _unwrap(replay_doc)
    except ValueError as exc:
        return {"passed": False, "failures": [str(exc)], "metrics": {}}
    cells = _records_with_ids(rep.get("cells", []), "cells", failures)
    solver_ids = [cell["id"] for cell in cells]
    if len(solver_ids) != len(set(solver_ids)):
        failures.append("duplicate solver cell ids")
    forcing = rep.get("forcing")
    if forcing is None:
        failures.append("missing forcing")
        sources: list[dict[str, Any]] = []
    elif not isinstance(forcing, dict):
        failures.append("forcing must be an object")
        sources = []
    elif "sources" not in forcing:
        failures.append("missing forcing.sources")
        sources = []
    else:
        sources = _records_with_ids(forcing["sources"], "sources", failures)
    source_ids = [s["id"] for s in sources]
    if len(source_ids) != len(set(source_ids)):
        failures.append("duplicate solver source ids")
    hydraulics_summary = rep.get("hydraulics_summary")
    if hydraulics_summary is None:
        failures.append("missing hydraulics_summary")
    elif not isinstance(hydraulics_summary, dict):
        failures.append("hydraulics_summary must be an object")
    elif "thermal_inventory" not in hydraulics_summary:
        failures.append("missing thermal_inventory in hydraulics_summary")
    else:
        inventory = hydraulics_summary["thermal_inventory"]
        if not isinstance(inventory, dict):
            failures.append("thermal_inventory must be an object")
        elif "sources" not in inventory:
            failures.append("thermal_inventory lacks a sources list")
        elif inventory["sources"] == []:
            failures.append("empty thermal_inventory sources")
        else:
            inv_sources = _records_with_ids(
                inventory["sources"], "inventory.sources", failures)
            tallied = {row["id"] for row in inv_sources}
            if tallied != set(source_ids):
                failures.append("thermal inventory does not match solver "
                                "sources one to one")
    method = rep.get("model", {}).get("surface_flux")
    if method not in SURFACE_METHODS:
        failures.append(f"surface method {method!r} outside contract")
    else:
        has_budget = rep.get("forcing", {}).get(
            "surface_budget") is not None
        if method == "explicit_budget" and not has_budget:
            failures.append("explicit budget method lacks budget forcing")
        if method == "newton_lumped" and has_budget:
            failures.append("budget forcing present under Newton method")
        if method == "explicit_budget":
            solver = rep.get("model", {}).get("surface_solver", {})
            if not isinstance(solver, dict):
                failures.append("explicit budget lacks surface_solver record")
            elif solver.get("method") != "damped_newton":
                failures.append(
                    "explicit budget lacks damped-Newton metadata")
    if "final_budget" not in rep:
        failures.append("missing final_budget")
        budget: dict[str, Any] = {}
    elif not isinstance(rep["final_budget"], dict):
        failures.append("final_budget must be an object")
        budget = {}
    elif rep["final_budget"] == {}:
        failures.append("empty final_budget")
        budget = {}
    else:
        budget = rep["final_budget"]
    if "frames" not in rep:
        failures.append("missing frames")
        raw_frames: Any = []
    else:
        raw_frames = rep["frames"]
        if raw_frames == []:
            failures.append("empty frames")
    frame_times: list[float] = []
    frames_ok = True
    if raw_frames and not isinstance(raw_frames, list):
        failures.append("frames must be a list")
        frames_ok = False
    elif isinstance(raw_frames, list):
        for index, frame in enumerate(raw_frames):
            if not isinstance(frame, dict):
                failures.append(f"frames[{index}] must be an object")
                frames_ok = False
                break
            t_value = _finite_float(frame.get("t_s"))
            if t_value is None:
                failures.append(f"frames[{index}] lacks a finite t_s")
                frames_ok = False
                break
            frame_times.append(t_value)
    if frames_ok and len(frame_times) >= 2:
        monotonic = all(later > earlier for earlier, later
                        in zip(frame_times, frame_times[1:]))
        if not monotonic:
            failures.append("replay frame times are not strictly increasing")
            frames_ok = False
    if budget and frames_ok and frame_times and sources:
        duration = frame_times[-1] - frame_times[0]
        if duration > 0.0:
            # Volume check uses the solver's recorded lateral volume.
            raw_flows = [s.get("flow_m3_s") for s in sources]
            if all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in raw_flows):
                flows = [_finite_float(v) for v in raw_flows]
                if any(f is None for f in flows):
                    failures.append(
                        "source flow_m3_s must be finite for the "
                        "lateral volume check")
                    expected: float | None = None
                else:
                    expected = sum(f for f in flows if f is not None) * duration
            else:
                # Scheduled series rely on the recorded lateral_input_m3.
                expected = None
            actual = _finite_float(budget.get("lateral_input_m3"))
            if actual is None:
                failures.append(
                    "recorded lateral_input_m3 is missing or non-finite")
            elif expected is not None:
                scale = max(1.0, abs(expected))
                if abs(actual - expected) / scale > 1e-9:
                    failures.append(
                        "solver lateral volume differs from recorded "
                        "source flows")
    land_records = _records_with_ids(landscape, "landscape", failures)
    land_ids = [cell["id"] for cell in land_records]
    if len(land_ids) != len(set(land_ids)):
        failures.append("duplicate landscape cell ids")
    solver_set = set(solver_ids)
    n_pockets = 0
    for cell in land_records:
        cell_id = cell["id"]
        if cell_id in solver_set:
            if cell.get("river_id") == "tributary":
                failures.append(
                    f"pocket {cell_id!r} collides with a solver cell id")
            continue
        if cell.get("river_id") == "tributary":
            n_pockets += 1
            if cell.get("conservation") != POCKET_CONSERVATION:
                failures.append(
                    f"pocket {cell_id!r} lacks non-conservative label")
            if not isinstance(cell.get("tributary_provenance"), dict):
                failures.append(
                    f"pocket {cell_id!r} lacks provenance record")
        else:
            failures.append(
                f"landscape cell {cell_id!r} maps to no solver cell or "
                f"declared pocket")

    # Snow runoff coupling: boundary flow equals baseflow plus runoff.
    snow_runoff_status = "not_available"
    catchment = rep.get("forcing", {}).get("catchment_runoff")
    if isinstance(catchment, dict):
        baseflow = _finite_float(catchment.get("baseflow_m3_s"))
        runoff = _finite_float(catchment.get("runoff_m3_s"))
        boundary = _finite_float(
            rep.get("forcing", {}).get("boundary_m3_s"))
        if baseflow is None or runoff is None or boundary is None:
            failures.append(
                "snow_runoff_discharge: non-finite catchment fields")
            snow_runoff_status = "non_finite"
        elif not math.isclose(boundary, baseflow + runoff,
                              rel_tol=1e-12, abs_tol=1e-9):
            failures.append(
                "replay boundary flow does not equal baseflow plus "
                "catchment runoff")
            snow_runoff_status = "mismatch"
        else:
            snow_runoff_status = "ok"

    metrics = {"n_solver_cells": len(solver_ids),
               "n_landscape_cells": len(land_ids),
               "n_pockets": n_pockets,
               "n_sources": len(source_ids),
               "surface_method": method,
               "snow_runoff_check": snow_runoff_status}
    return {"passed": not failures, "failures": failures,
            "metrics": metrics}


def _landscape_profile(landscape: list[dict[str, Any]]
                       ) -> list[tuple[float, float]]:
    """Sorted (s_m, temperature_c) pairs for mainstem solver cells.
    Off-channel pockets and malformed cells are excluded; duplicate chainages are rejected."""
    cells: list[tuple[float, float]] = []
    for cell in landscape:
        if not isinstance(cell, dict):
            continue
        if cell.get("river_id") == "tributary":
            continue
        if cell.get("kind") == "pocket":
            continue
        if "s_m" not in cell or "temperature_c" not in cell:
            continue
        s = _finite_float(cell["s_m"])
        temperature = _finite_float(cell["temperature_c"])
        if s is None or temperature is None:
            continue
        cells.append((s, temperature))
    cells.sort()
    # Duplicate mainstem chainages make _interpolate ambiguous; one solver cell per chainage.
    seen_chainages = [chainage for chainage, _ in cells]
    duplicates = sorted({
        chainage for chainage in seen_chainages
        if seen_chainages.count(chainage) > 1
    })
    if duplicates:
        raise ValueError(
            "landscape profile has duplicate mainstem chainages at "
            f"{duplicates}; mainstem cells must be unique in s_m"
        )
    return cells


def _interpolate(profile: list[tuple[float, float]], s: float) -> float | None:
    """Linear temperature at chainage s, or None outside the profile."""
    if len(profile) < 2:
        return None
    if s < profile[0][0] or s > profile[-1][0]:
        return None
    lo, hi = 0, len(profile) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if profile[mid][0] <= s:
            lo = mid
        else:
            hi = mid
    s0, t0 = profile[lo]
    s1, t1 = profile[hi]
    if s1 == s0:
        return t0
    return t0 + (t1 - t0) * (s - s0) / (s1 - s0)


def check_cross_family(landscape: list[dict[str, Any]],
                       reaches: list[dict[str, Any]],
                       membership: list[str],
                       chainage: list[float],
                       chainage_offset_m: float = 0.0,
                       tolerance_c: float = CROSS_FAMILY_TOLERANCE_C,
                       profile_kind: str = "time_mean"
                       ) -> dict[str, Any]:
    """Lumped reach temperatures against the replay field at the same chainage.
    profile_kind is the replay statistic: time_mean, final_state, initial_state."""
    failures: list[str] = []
    if not landscape or not reaches or len(membership) != len(chainage):
        return {"passed": False,
                "failures": ["cross-family inputs incomplete"],
                "metrics": {"cross_family_compared": 0,
                            "cross_family_profile_kind": profile_kind}}
    profile = _landscape_profile(landscape)
    reach_temp = {r["id"]: float(r["temperature_c"]) for r in reaches
                  if "temperature_c" in r}
    stations: dict[str, list[float]] = {}
    for rid, s in zip(membership, chainage):
        if rid in reach_temp:
            stations.setdefault(rid, []).append(float(s))
    compared: list[dict[str, Any]] = []
    skipped: list[str] = []
    for rid, temps in reach_temp.items():
        points = stations.get(rid)
        if not points:
            skipped.append(f"{rid}: no polyline points")
            continue
        mid = (min(points) + max(points)) / 2.0 + float(chainage_offset_m)
        field_t = _interpolate(profile, mid)
        if field_t is None:
            skipped.append(f"{rid}: s={mid:.0f} m outside replay field "
                           f"{profile[0][0]:.0f}-{profile[-1][0]:.0f} m")
            continue
        delta = abs(field_t - temps)
        compared.append({"reach_id": rid, "s_m": round(mid, 1),
                         "reach_c": round(temps, 3),
                         "field_c": round(field_t, 3),
                         "abs_delta_c": round(delta, 3)})
        if delta > tolerance_c:
            failures.append(
                f"{rid}: lumped {temps:.2f} C against replay field "
                f"{field_t:.2f} C at s={mid:.0f} m (delta {delta:.2f} C "
                f"over {tolerance_c:.2f} C)")
    if not compared:
        failures.append("cross-family: no reach overlapped the replay field")
    deltas = [row["abs_delta_c"] for row in compared]
    metrics = {"cross_family_compared": len(compared),
               "cross_family_max_delta_c": max(deltas) if deltas else None,
               "cross_family_mean_delta_c": (sum(deltas) / len(deltas)
                                             if deltas else None),
               "cross_family_tolerance_c": tolerance_c,
               "cross_family_profile_kind": profile_kind,
               "cross_family_comparison_statistic":
                   f"replay_{profile_kind}_vs_lumped_final",
               "cross_family_skipped": skipped}
    return {"passed": not failures, "failures": failures, "metrics": metrics}
