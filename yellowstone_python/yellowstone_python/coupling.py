"""Component coupling contract for water, heat, and landscape mapping."""
from __future__ import annotations

from typing import Any

EXCHANGE_FIELDS = ("exchange_id", "quantity", "units", "sign_convention",
                   "spatial_support", "temporal_support", "kind", "source",
                   "destination", "method", "conservation")

POCKET_CONSERVATION = "non_conservative"

CROSS_FAMILY_TOLERANCE_C = 2.0

SURFACE_METHODS = ("newton_lumped", "explicit_budget")

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
        "method": "explicit budget linearized implicitly, Newton off",
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
        "quantity": "mean snow-ledger runoff as a discharge increment",
        "units": "m3/s",
        "sign_convention": "positive added to prescribed baseflow",
        "spatial_support": "configured catchment area",
        "temporal_support": "mean rate over the snow season window",
        "kind": "transfer",
        "source": "snow_season ledger runoff_mm over the modeled patches",
        "destination": "upstream boundary discharge of both hydrology models",
        "method": ("mean patch runoff depth scaled to the catchment area and "
                   "divided by the window length"),
        "conservation": "conserved",
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
    """Field presence and id uniqueness over the exchange records."""
    errors = []
    for record in EXCHANGES:
        for field in EXCHANGE_FIELDS:
            if field not in record:
                errors.append(f"{record.get('exchange_id', '?')}: "
                              f"missing {field}")
    ids = [record["exchange_id"] for record in EXCHANGES]
    if len(ids) != len(set(ids)):
        errors.append("duplicate exchange_id in contract")
    return errors


def _unwrap(document: dict[str, Any]) -> dict[str, Any]:
    if "cells" in document and "frames" in document:
        return document
    for key in ("replay", "data"):
        inner = document.get(key)
        if isinstance(inner, dict):
            try:
                return _unwrap(inner)
            except ValueError:
                continue
    raise ValueError("not a recognized replay document (no cells+frames)")


def check_coupling(replay_doc: dict[str, Any],
                   landscape: list[dict[str, Any]]) -> dict[str, Any]:
    """One authoritative record per exchange; pockets labeled held."""
    failures: list[str] = []
    try:
        rep = _unwrap(replay_doc)
    except ValueError as exc:
        return {"passed": False, "failures": [str(exc)], "metrics": {}}
    solver_ids = [cell["id"] for cell in rep.get("cells", [])]
    if len(solver_ids) != len(set(solver_ids)):
        failures.append("duplicate solver cell ids")
    sources = rep.get("forcing", {}).get("sources", [])
    source_ids = [s.get("id", "?") for s in sources]
    if len(source_ids) != len(set(source_ids)):
        failures.append("duplicate solver source ids")
    inventory = rep.get("hydraulics_summary", {}).get(
        "thermal_inventory", {})
    if inventory:
        tallied = {row["id"] for row in inventory.get("sources", [])}
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
    budget = rep.get("final_budget", {})
    frames = rep.get("frames", [])
    if budget and frames and sources:
        duration = float(frames[-1].get("t_s", 0.0))
        if duration > 0.0:
            expected = sum(float(s.get("flow_m3_s", 0.0))
                           for s in sources) * duration
            actual = float(budget.get("lateral_input_m3", float("nan")))
            scale = max(1.0, abs(expected))
            if abs(actual - expected) / scale > 1e-9:
                failures.append("solver lateral volume differs from "
                                "recorded source flows")
    land_ids = [cell.get("id", "?") for cell in landscape]
    if len(land_ids) != len(set(land_ids)):
        failures.append("duplicate landscape cell ids")
    solver_set = set(solver_ids)
    n_pockets = 0
    for cell in landscape:
        if cell.get("id") in solver_set:
            continue
        if cell.get("river_id") == "tributary":
            n_pockets += 1
            if cell.get("conservation") != POCKET_CONSERVATION:
                failures.append(f"pocket {cell.get('id', '?')} lacks "
                                f"non-conservative label")
            if "tributary_provenance" not in cell:
                failures.append(f"pocket {cell.get('id', '?')} lacks "
                                f"provenance record")
            if cell.get("id") in solver_set:
                failures.append(f"pocket {cell.get('id', '?')} collides "
                                f"with a solver cell id")
        else:
            failures.append(f"landscape cell {cell.get('id', '?')} maps "
                            f"to no solver cell or declared pocket")
    metrics = {"n_solver_cells": len(solver_ids),
               "n_landscape_cells": len(land_ids),
               "n_pockets": n_pockets,
               "n_sources": len(source_ids),
               "surface_method": method}
    return {"passed": not failures, "failures": failures,
            "metrics": metrics}


def _landscape_profile(landscape: list[dict[str, Any]]
                       ) -> list[tuple[float, float]]:
    cells = sorted((float(cell["s_m"]), float(cell["temperature_c"]))
                   for cell in landscape
                   if "s_m" in cell and "temperature_c" in cell)
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
                       tolerance_c: float = CROSS_FAMILY_TOLERANCE_C
                       ) -> dict[str, Any]:
    """Lumped reach temperatures against the replay field at the same chainage.

    membership and chainage are the per-point tables fish.update_trout uses, so
    each reach is compared where it actually sits on the river polyline.
    chainage_offset_m converts local polyline chainage to the replay's global
    chainage. Reaches whose chainage leaves the landscape are reported and
    skipped.
    """
    failures: list[str] = []
    if not landscape or not reaches or len(membership) != len(chainage):
        return {"passed": False,
                "failures": ["cross-family inputs incomplete"],
                "metrics": {"cross_family_compared": 0}}
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
               "cross_family_skipped": skipped}
    return {"passed": not failures, "failures": failures, "metrics": metrics}
