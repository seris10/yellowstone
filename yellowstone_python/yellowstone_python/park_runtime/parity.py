"""Same-input comparison of the native LiveEngine against the ParkRuntime adapter.

Both sides start from one state, use one frame interval and forcing, and take one intervention."""
from __future__ import annotations
import argparse
import json
import math
import re
import time
from pathlib import Path
from .legacy_adapter import LegacyLiveDomain
from .runtime import ParkRuntime

DOMAIN_ID = "parity.firehole"
EXCLUDED = ("header.timings", "header.session_id", "header.compute_rate_sps", "header.max_dt_capacity_sps",
            "header.max_supported_time_scale", "header.clock_debt_s", "header.computing", "header.clock_held")
INDEX = re.compile(r"\[\d+\]")


def flatten(value, prefix=""):
    """Yield (path, leaf) pairs for nested dicts and sequences."""
    if isinstance(value, dict):
        for key in sorted(value):
            yield from flatten(value[key], f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from flatten(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def _excluded(path: str) -> bool:
    return any(path == name or path.startswith(name + ".") for name in EXCLUDED)


def _delta(left, right):
    """Return (absolute, relative) difference of two leaves, or None when they match exactly."""
    numeric = (int, float)
    if isinstance(left, numeric) and isinstance(right, numeric) and not isinstance(left, bool) \
            and not isinstance(right, bool):
        if left == right or (math.isnan(left) and math.isnan(right)):
            return 0.0, 0.0
        absolute = abs(left - right)
        return absolute, absolute / max(abs(left), abs(right), 1e-300)
    return (0.0, 0.0) if left == right else None


def compare_frames(native: dict, adapter: dict, *, abs_tol: float, rel_tol: float):
    """Compare two frames leaf by leaf and return counts, worst deltas and mismatches."""
    left = {path: leaf for path, leaf in flatten(native) if not _excluded(path)}
    right = {path: leaf for path, leaf in flatten(adapter) if not _excluded(path)}
    mismatches = [{"path": path, "reason": "missing on one side"} for path in sorted(left.keys() ^ right.keys())]
    worst_abs = worst_rel = 0.0
    fields = set()
    for path in sorted(left.keys() & right.keys()):
        fields.add(INDEX.sub("[]", path))
        delta = _delta(left[path], right[path])
        if delta is None:
            mismatches.append({"path": path, "native": left[path], "adapter": right[path]})
            continue
        worst_abs, worst_rel = max(worst_abs, delta[0]), max(worst_rel, delta[1])
        scale = max(abs(left[path]), abs(right[path])) if isinstance(left[path], (int, float)) else 0.0
        if delta[0] > abs_tol + rel_tol * scale:
            mismatches.append({"path": path, "native": left[path], "adapter": right[path], "abs_delta": delta[0]})
    return {"leaves": len(left), "fields": fields, "max_abs": worst_abs, "max_rel": worst_rel,
            "mismatches": mismatches}


def _adapter_frame(runtime, t_s):
    """Return the adapter frame held at a time, or None."""
    bracket = runtime.packet(t_s)["bracket"]
    match = next((row for row in bracket if row["t_s"] == t_s), None)
    return None if match is None else match["regions"][DOMAIN_ID]["frame"]


def budgets(engine) -> dict:
    """Return the river heat, solute mass and water budgets and the ecological ledgers."""
    state = engine.checkpoint_state()
    ecology = state["ecology"]
    return {"river": engine.river.budget(), "solute_mass": state["solutes"]._totals,
            "solute_water_m3": state["solutes"]._water_totals,
            "land": ecology.get("land_ledger"), "insects": ecology.get("insect_ledger"),
            "mammals": ecology.get("mammal_report", {}).get("ledger") if "mammal_report" in ecology else None}


def compare_native_and_adapter(make_engine, *, end_s: float, intervention: dict | None = None,
                               abs_tol: float = 0.0, rel_tol: float = 0.0, native_chunks: bool = True) -> dict:
    """Compare every frame field and budget of both paths over one interval.

    The intervention (at_s, changes) applies after end_s; both paths then run to 1.5 * end_s."""
    native, bridged = make_engine(), make_engine()
    quantum = native.frame_interval_s
    domain = LegacyLiveDomain(bridged, DOMAIN_ID)
    horizon = 3.0 * end_s
    runtime = ParkRuntime([domain], quantum_s=quantum, history_s=horizon, epoch_unix=bridged.epoch_origin,
                          max_frames=int(horizon / quantum) + 8)
    stops = [end_s] if intervention is None else [end_s, 1.5 * end_s]
    timing = {"native_s": 0.0, "adapter_s": 0.0}
    pairs = []
    for index, stop in enumerate(stops):
        if index == 1:
            at_s, changes = intervention["at_s"], intervention["changes"]
            started = time.perf_counter()
            native.command("control", {"at_s": at_s, "changes": changes})
            timing["native_s"] += time.perf_counter() - started
            started = time.perf_counter()
            runtime.intervene("parity.event", DOMAIN_ID, at_s, changes)
            timing["adapter_s"] += time.perf_counter() - started
        started = time.perf_counter()
        if native_chunks:
            while native.river.time_s < stop - 1e-9:
                native.compute_until(min(stop, native.river.time_s + quantum))
        else:
            native.compute_until(stop)
        timing["native_s"] += time.perf_counter() - started
        started = time.perf_counter()
        runtime.compute_until(stop)
        timing["adapter_s"] += time.perf_counter() - started
        pairs += [(index, t_s, frame, _adapter_frame(runtime, t_s)) for t_s, frame in
                  sorted({frame["t_s"]: frame for frame in native.frames()["frames"]}.items())
                  if index == 0 or t_s >= intervention["at_s"]]
    times, fields, mismatches = [], set(), []
    leaves, worst_abs, worst_rel = 0, 0.0, 0.0
    for stage, t_s, native_frame, adapter_frame in pairs:
        if adapter_frame is None:
            mismatches.append({"stage": stage, "t_s": t_s, "reason": "adapter holds no frame at this time"})
            continue
        result = compare_frames(native_frame, adapter_frame, abs_tol=abs_tol, rel_tol=rel_tol)
        times.append(t_s)
        fields |= result["fields"]
        leaves += result["leaves"]
        worst_abs, worst_rel = max(worst_abs, result["max_abs"]), max(worst_rel, result["max_rel"])
        mismatches += [{"stage": stage, "t_s": t_s, **row} for row in result["mismatches"]]
    native_budget, adapter_budget = budgets(native), budgets(bridged)
    budget_result = compare_frames(native_budget, adapter_budget, abs_tol=abs_tol, rel_tol=rel_tol)
    mismatches += [{"budget": True, **row} for row in budget_result["mismatches"]]
    return {"frames_compared": len(times), "first_t_s": times[0] if times else None,
            "last_t_s": times[-1] if times else None, "leaves_compared": leaves,
            "advertised_fields": sorted(fields), "budget_fields": sorted(budget_result["fields"]),
            "budget_leaves_compared": budget_result["leaves"], "excluded_header_fields": list(EXCLUDED),
            "tolerance": {"abs": abs_tol, "rel": rel_tol}, "native_stepping": "frame_interval" if native_chunks
            else "single_call", "max_abs_delta": max(worst_abs, budget_result["max_abs"]),
            "max_rel_delta": max(worst_rel, budget_result["max_rel"]), "mismatch_count": len(mismatches),
            "mismatches": mismatches[:50], "wall_s": timing, "passed": not mismatches}


def main():
    """Run the comparison on a published build and print or write the report."""
    from yellowstone_python.service.live import LiveEngine
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, help="derived/<build-id> directory")
    parser.add_argument("--end-s", type=float, default=600.0)
    parser.add_argument("--control", default='{"hydro.boundary_c": 17.0}', help="JSON control changes")
    parser.add_argument("--at-s", type=float, default=300.0)
    parser.add_argument("--bulk-native", action="store_true", help="step the native engine in one call")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = compare_native_and_adapter(
        lambda: LiveEngine.from_build(Path(args.build), start_worker=False), end_s=args.end_s,
        intervention={"at_s": args.at_s, "changes": json.loads(args.control)}, native_chunks=not args.bulk_native)
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
