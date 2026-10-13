These are relevant, but both are currently **descriptive contracts rather than fully reliable validation layers**. `coupling.py` is closer to executable validation; `equations.py` is mainly documentation. They should be updated together with the newer `river_transport.py`, `river_world.py`, `surface_flux.py`, and build pipeline.

# `coupling.py`

## 1. The contract is not validated by the build

The build writes:

```python
write_sidecar(out / "coupling.json", {
    "schema": "yellowstone.coupling.v1",
    "exchanges": EXCHANGES,
})
```

but this is only contract metadata. It does not appear to run:

```python
validate_contract()
check_coupling(...)
```

Add both to the build gate and write the actual result separately:

```python
contract_errors = validate_contract()

coupling_result = check_coupling(
    res["replay_doc"],
    thermal_landscape(res["replay_doc"]),
)

if contract_errors:
    coupling_result["passed"] = False
    coupling_result["failures"].extend(contract_errors)
```

Write:

```python
write_sidecar(
    out / "coupling_check.json",
    coupling_result,
    sources=[{"id": "code", "sha256": deps["code"]}],
    params={"build_id": bid, "run_mode": mode},
)
```

Do not confuse:

```text
coupling.json       contract declaration
coupling_check.json actual validation result
```

---

## 2. `validate_contract()` can crash on malformed records

Current code:

```python
ids = [record["exchange_id"] for record in EXCHANGES]
```

If an exchange is missing `exchange_id`, validation raises `KeyError`.

Use:

```python
ids = []

for record in EXCHANGES:
    exchange_id = record.get("exchange_id")

    if exchange_id is not None:
        ids.append(exchange_id)

if len(ids) != len(set(ids)):
    errors.append("duplicate exchange_id in contract")
```

Also validate field values:

```python
VALID_KINDS = {"transfer", "mapping", "prescription"}
VALID_CONSERVATION = {"conserved", "mapped", POCKET_CONSERVATION}

for record in EXCHANGES:
    exchange_id = record.get("exchange_id", "?")

    if record.get("kind") not in VALID_KINDS:
        errors.append(
            f"{exchange_id}: invalid kind "
            f"{record.get('kind')!r}"
        )

    if record.get("conservation") not in VALID_CONSERVATION:
        errors.append(
            f"{exchange_id}: invalid conservation "
            f"{record.get('conservation')!r}"
        )
```

Check nonempty strings too.

---

## 3. `check_coupling()` is not safe against malformed replay documents

These expressions can raise:

```python
solver_ids = [cell["id"] for cell in rep.get("cells", [])]
```

```python
tallied = {row["id"] for row in inventory.get("sources", [])}
```

```python
duration = float(frames[-1].get("t_s", 0.0))
```

A checker should report malformed input, not crash.

Add a helper:

```python
def _records_with_ids(
    records: Any,
    label: str,
    failures: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        failures.append(f"{label} must be a list")
        return []

    result = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"{label}[{index}] must be an object")
            continue

        record_id = record.get("id")

        if not isinstance(record_id, str) or not record_id:
            failures.append(
                f"{label}[{index}] lacks a nonempty string id"
            )
            continue

        result.append(record)

    return result
```

Then use it for cells, sources, inventory records, and landscape cells.

---

## 4. The pocket collision check is unreachable

Current code:

```python
for cell in landscape:
    if cell.get("id") in solver_set:
        continue

    if cell.get("river_id") == "tributary":
        ...
        if cell.get("id") in solver_set:
            failures.append(...)
```

The inner check can never run because colliding IDs already hit `continue`.

Fix:

```python
for cell in landscape:
    cell_id = cell.get("id")

    if cell_id in solver_set:
        if cell.get("river_id") == "tributary":
            failures.append(
                f"pocket {cell_id!r} collides with solver cell id"
            )
        continue

    if cell.get("river_id") == "tributary":
        n_pockets += 1

        if cell.get("conservation") != POCKET_CONSERVATION:
            failures.append(
                f"pocket {cell_id!r} lacks non-conservative label"
            )

        if not isinstance(
            cell.get("tributary_provenance"),
            dict,
        ):
            failures.append(
                f"pocket {cell_id!r} lacks provenance record"
            )
    else:
        failures.append(
            f"landscape cell {cell_id!r} maps to no solver cell "
            "or declared pocket"
        )
```

---

## 5. The pocket contract does not match the current tributary script

The contract defines:

```python
"exchange_id": "pocket_holding",
"kind": "prescription",
"conservation": "non_conservative",
```

That is sensible for an off-channel refuge pocket.

But `run_hot_lowflow_with_tributaries_v2.py` currently appends tributary records directly to:

```python
modified_doc["cells"]
```

and gives them:

```python
"river_id": "river_5856_0"
```

That makes them look like solver cells, not pockets.

The current contract expects something like:

```python
{
    "id": "pocket_tributary_001",
    "river_id": "tributary",
    "conservation": "non_conservative",
    "tributary_provenance": {...},
    "temperature_c": 11.5,
    "chainage_m": 3500.0,
}
```

The refuge script should produce a separate landscape-pocket collection rather than modifying `replay_doc["cells"]`.

---

## 6. The lateral water-volume check assumes constant source flows

Current code:

```python
expected = sum(
    float(s.get("flow_m3_s", 0.0))
    for s in sources
) * duration
```

This is only correct if:

- every source flow is scalar;
- all sources are active for the entire replay;
- replay time begins at zero;
- source flow does not vary.

The newer design is moving toward scheduled forcing. Support both scalar and `Series`-like schedules:

```python
def _integrated_series_value(
    value: Any,
    times: list[float],
) -> float:
    series = Series.parse(value)
    total = 0.0

    for start, end in zip(times, times[1:]):
        total += series.at(start) * (end - start)

    return total
```

Better: expose the solver’s authoritative accumulated source volume in the replay budget and compare against that, rather than reconstructing it from source metadata.

At minimum, use:

```python
actual = budget.get("lateral_input_m3")
```

and only perform an independent calculation when the source representation is unambiguously constant.

---

## 7. The duration calculation is fragile

Current code:

```python
duration = float(frames[-1].get("t_s", 0.0))
```

This assumes the first frame is at zero. Use:

```python
times = [
    float(frame["t_s"])
    for frame in frames
]

if not times:
    failures.append("replay has no frames")
elif any(
    later <= earlier
    for earlier, later in zip(times, times[1:])
):
    failures.append("replay frame times are not strictly increasing")
else:
    duration = times[-1] - times[0]
```

Also verify that the first frame is actually at zero if that is part of the replay contract.

---

## 8. NaN values can bypass the budget check

Current code:

```python
actual = float(
    budget.get("lateral_input_m3", float("nan"))
)

if abs(actual - expected) / scale > 1e-9:
```

If `actual` is NaN, the comparison is false and the check passes.

Fix:

```python
if not math.isfinite(actual):
    failures.append(
        "recorded lateral_input_m3 is missing or non-finite"
    )
elif abs(actual - expected) / scale > 1e-9:
    failures.append(
        "solver lateral volume differs from recorded source flows"
    )
```

Apply the same rule to frame times, flows, temperatures, and inventory values.

---

## 9. Surface-budget contract is stale after damped Newton

Current contract says:

```python
"method": "explicit budget linearized implicitly, Newton off"
```

That conflicts with the newer implementation, where explicit surface budget is solved using damped Newton iteration.

Update to:

```python
"method": (
    "explicit surface budget solved by damped Newton iteration; "
    "final nonlinear flux used for accounting"
),
```

Also add the numerical settings to the replay metadata:

```json
{
  "surface_solver": {
    "method": "damped_newton",
    "max_iterations": 12,
    "temperature_tolerance_c": 1e-7,
    "relaxation": 0.8
  }
}
```

The contract should require:

```python
if method == "explicit_budget":
    solver = rep.get("model", {}).get("surface_solver", {})
    if solver.get("method") != "damped_newton":
        failures.append(
            "explicit budget lacks damped-Newton metadata"
        )
```

---

## 10. `snow_runoff_discharge` overstates what the build does

The contract says:

```python
"destination": "upstream boundary discharge of both hydrology models"
```

But the build currently:

- computes a scalar snow-derived runoff increment;
- adds it to the boundary of the legacy hydrology model;
- passes the resulting scalar to the replay;
- does not use overland-flow output for river forcing;
- does not produce a time-varying hydrograph.

A more accurate contract is:

```python
"quantity": "mean snow-ledger runoff increment",
"temporal_support": "constant scalar over the configured replay",
"method": (
    "illustrative mean patch runoff depth scaled by configured "
    "catchment area and divided by season window"
),
"conservation": "prescribed_increment",
```

If it is not a routed hydrograph, do not call it a general runoff transfer.

Consider adding:

```python
PRESCRIBED_INCREMENT = "prescribed_increment"
```

to conservation/kind vocabulary.

---

## 11. `check_coupling()` does not check snow runoff at all

The contract includes:

```python
"snow_runoff_discharge"
```

but `check_coupling()` never verifies:

- whether the catchment is enabled;
- whether runoff was applied;
- whether effective boundary flow equals baseflow plus runoff;
- whether the replay and legacy model received the same boundary;
- whether units are m³/s.

Add optional metadata checks:

```python
catchment = rep.get("forcing", {}).get("catchment_runoff")

if catchment is not None:
    baseflow = float(catchment["baseflow_m3_s"])
    runoff = float(catchment["runoff_m3_s"])
    boundary = float(rep["forcing"]["boundary_m3_s"])

    if not math.isclose(
        boundary,
        baseflow + runoff,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        failures.append(
            "replay boundary flow does not equal "
            "baseflow plus catchment runoff"
        )
```

If the check cannot be performed, report:

```python
"snow_runoff_check": "not_available"
```

rather than silently passing.

---

## 12. Landscape profile handling is unsafe with pockets and duplicate chainages

Current code:

```python
cells = sorted(
    (float(cell["s_m"]), float(cell["temperature_c"]))
    for cell in landscape
    if "s_m" in cell and "temperature_c" in cell
)
```

Problems:

- pockets may have `chainage_m`, not `s_m`;
- solver cells and pockets may share chainage;
- duplicate chainages can make interpolation ambiguous;
- landscape cells may be unsorted or malformed;
- one interpolation profile may incorrectly include off-channel pockets.

Use only mainstem solver cells for the continuous profile:

```python
def _landscape_profile(
    landscape: list[dict[str, Any]],
) -> list[tuple[float, float]]:
    cells = []

    for cell in landscape:
        if cell.get("river_id") == "tributary":
            continue

        if cell.get("kind") == "pocket":
            continue

        if "s_m" not in cell or "temperature_c" not in cell:
            continue

        s = float(cell["s_m"])
        temperature = float(cell["temperature_c"])

        if not math.isfinite(s) or not math.isfinite(temperature):
            continue

        cells.append((s, temperature))

    cells.sort()
    return cells
```

Then test duplicate chainage explicitly.

For pockets, use a separate comparison method:

```python
def _pocket_temperature_at_chainage(...):
    ...
```

Do not interpolate across an off-channel pocket as if it were a mainstem cell.

---

## 13. Cross-family comparison may be comparing different quantities

`check_cross_family()` compares:

```python
reach temperature
```

against:

```python
replay field temperature
```

at the reach midpoint.

That can be useful, but only if:

- both represent the same time;
- both use the same forcing;
- `reach.temperature_c` is not a time mean while the replay field is a final state;
- chainage offsets are correct;
- the reach is truly represented by the replay field.

The function should accept an explicit comparison time/statistic:

```python
"profile_kind": "time_mean|final_state|initial_state"
```

and report it:

```python
metrics = {
    "comparison_statistic": "replay_time_mean_vs_lumped_final",
}
```

If `river_state` is from the legacy quasi-steady model and `landscape` comes from the replay time mean, a 2°C tolerance is arbitrary. The check should either:

- compare time means to time means;
- compare final states to final states;
- or be marked diagnostic-only.

---

# `equations.py`

## 14. The M01 equation is dimensionally unclear

Current text:

```text
d(ViTi)/dt = inflow enthalpy + lateral enthalpy - outflow enthalpy
+ Vi(Tair-Ti)/tau_i
```

`V_i T_i` has units:

```text
m³ °C
```

but “enthalpy” has energy units. The equation needs either:

```text
d(rho cp V_i T_i)/dt
```

or an explicit statement that the equation is normalized by volumetric heat capacity.

Also:

```text
Qout = Qin + Qhot
```

suggests `Qhot` is a water discharge, not heat. Rename it:

```text
Qout = Qin + Qlateral
```

and write the thermal equation separately.

Suggested replacement:

```python
"equations": (
    "rho*cp*d(V_i*T_i)/dt = "
    "rho*cp*(Q_in*T_in - Q_out*T_i) + "
    "rho*cp*sum(Q_l*T_l - Q_l*T_i) + "
    "A_i*h_i*(T_air - T_i); "
    "Q_out = Q_in + sum(Q_l)"
),
```

---

## 15. The M01b replay equation omits important factors

Current text:

```text
d(V_i T_i)/dt =
Q(T_{i-1} - T_i)
+ D A (T_{i+1} - 2T_i + T_{i-1})/dx
+ Phi_i
```

Problems:

- `Q(T_{i-1} - T_i)` assumes constant flow and omits face indexing;
- the dispersion term has questionable dimensional form;
- `Phi_i` is not defined as a power, flux, or normalized source;
- boundary conditions are not represented;
- lateral source terms are omitted;
- it does not mention variable cross-sectional areas or harmonic face conductance.

The actual implementation is closer to a finite-volume temperature-volume balance:

```text
rho*cp*V_i*dT_i/dt =
rho*cp*(F_in,i - F_out,i)
+ rho*cp*sum(Q_l*T_l)
+ A_surface,i*Phi_surface,i
+ P_cell,i
```

with dispersive/advective face fluxes defined separately.

A better inventory entry:

```python
"equations": (
    "rho*cp*V_i*dT_i/dt = "
    "rho*cp*(F_in,i - F_out,i) + "
    "rho*cp*sum(Q_l*T_l) + "
    "A_surface,i*Phi_surface,i + P_cell,i; "
    "F_j = Q_j*T_upwind + G_j*(T_left - T_right); "
    "G_j = harmonic dispersion conductance; "
    "backward Euler; tridiagonal solve"
),
```

Add:

```python
"variables": {
    "V_i": "cell water volume, m3",
    "Q_j": "face discharge, m3/s",
    "G_j": "face dispersive conductance, m3/s",
    "Phi_surface": "surface heat flux, W/m2",
    "P_cell": "cell heat power, W",
}
```

---

## 16. The equation inventory is stale about the surface solver

Current entry:

```python
"model_level": "lumped Newton exchange by default; explicit budget optional",
```

That is broadly correct, but it should mention:

```text
explicit budget solved by damped Newton iteration
```

Update:

```python
"model_level": (
    "lumped Newton exchange by default; explicit nonlinear surface "
    "budget solved by damped Newton iteration"
),
```

Update limits:

```python
"limits": (
    "winter ice cover outside scope; radiation and transfer coefficients "
    "require local calibration; convergence is numerical, not validation"
),
```

---

## 17. The pool equation does not match `pool_crust.py`

Current inventory says:

```text
T(r) = ... for r <= rw
```

but `radial_temp()` returns `t_edge` for all `r > r_water`. The docstring says it “relaxes toward edge,” but the implementation is actually constant beyond the water edge.

Make the inventory match the code:

```python
"equations": (
    "T(r)=T_edge+(T_center-T_edge)*(1-(r/r_water)^2) "
    "for 0<=r<=r_water; T=T_edge for r>r_water; "
    "pigment bands are authored mappings"
),
```

Or change the implementation to actually relax across the apron.

---

## 18. The snow equation lacks units and state definitions

Current text:

```text
melt = k_melt max(0, T - tbase) + thermal ground flux
```

This is ambiguous:

- Is melt in mm/day?
- Is thermal ground flux converted to mm/day?
- Is `T` daily mean, maximum, or hourly temperature?
- Is snow water equivalent or snow depth the state?
- Is precipitation liquid-equivalent?

Add explicit units:

```python
"equations": (
    "SWE_{t+1}=max(0,SWE_t+P_t-M_t); "
    "M_t=k_melt*max(0,TAVG_t-T_base)+"
    "ground_energy_mm_d; "
    "soil_{t+1}=clip(soil_t+infiltration-ET-drainage)"
),
```

And:

```python
"assumptions": (
    "daily TAVG forcing; precipitation is liquid-equivalent daily "
    "accumulation; habitat modifiers authored"
),
```

---

## 19. The equation inventory does not identify source authority

The same concept appears in multiple implementations:

- legacy `hydro_thermal.py`;
- replay `river_transport.py`;
- `surface_flux.py`;
- `snow_season.py`;
- foodweb mapping.

Add fields:

```python
ENTRY_FIELDS = (
    "component",
    "module",
    "model_level",
    "equations",
    "variables",
    "units",
    "assumptions",
    "limits",
    "validation_status",
)
```

Example:

```python
{
    "component": "M01b 1-D advection-dispersion replay",
    ...
    "validation_status": "numerical_conservation_tested_not_field_validated",
}
```

This would prevent users from confusing:

```text
equation documented
```

with:

```text
equation validated against field observations
```

---

## 20. Add implementation checks to `equations.py`

Current `validate_inventory()` checks only field presence and duplicate names.

Add:

```python
from pathlib import Path

def validate_inventory(root: Path | None = None) -> list[str]:
    errors = []

    for entry in COMPONENTS:
        name = entry.get("component", "?")

        for field in ENTRY_FIELDS:
            value = entry.get(field)

            if value is None:
                errors.append(
                    f"component {name}: missing {field}"
                )
            elif isinstance(value, str) and not value.strip():
                errors.append(
                    f"component {name}: empty {field}"
                )

        module = entry.get("module")
        if root is not None and isinstance(module, str):
            module_path = root / module

            if not module_path.is_file():
                errors.append(
                    f"component {name}: module not found: "
                    f"{module_path}"
                )

    names = [
        entry.get("component")
        for entry in COMPONENTS
        if entry.get("component") is not None
    ]

    if len(names) != len(set(names)):
        errors.append("duplicate component in inventory")

    return errors
```

Then run it from `build.py`.

---

# Recommended coupling redesign

The current contract mixes several categories:

```text
transfer
mapping
prescription
```

That is reasonable, but add explicit authority and validation fields:

```python
EXCHANGE_FIELDS = (
    "exchange_id",
    "quantity",
    "units",
    "sign_convention",
    "spatial_support",
    "temporal_support",
    "kind",
    "source",
    "destination",
    "method",
    "conservation",
    "authority",
    "validation_status",
)
```

Example:

```python
{
    "exchange_id": "landscape_temperature",
    ...
    "authority": "river_transport.replay",
    "validation_status": (
        "numerical_time_mean_mapping_tested; "
        "field_temperature_not_validated"
    ),
}
```

For `pocket_holding`:

```python
{
    "authority": "authored_scenario_or_tributary_evidence",
    "validation_status": "prescribed_not_solver_simulated",
}
```

This is especially important given the current refuge-cell script, which incorrectly appends prescribed pockets to solver replay cells.

---

# Priority order

## Immediate fixes

1. Make `check_coupling()` robust to malformed records.
2. Fix unreachable pocket-collision check.
3. Fix NaN handling in budget checks.
4. Update the explicit-budget contract for damped Newton.
5. Run actual coupling checks from `build.py`.
6. Update `snow_runoff_discharge` wording and validation.
7. Separate solver cells from prescribed pockets.

## Equation inventory fixes

8. Correct dimensional notation.
9. Add variables and units.
10. Update surface-budget solver description.
11. Correct pool and snow equations.
12. Add validation status and module-existence checks.

## Architecture

13. Define one authoritative replay temperature field.
14. Distinguish final state versus time mean in landscape mapping.
15. Represent scheduled forcing and scalar prescribed increments separately.
16. Add actual exchange-level validation results to the build artifact.

The central issue is that the contracts are becoming more sophisticated, but the build still needs to execute them. A declaration such as:

```python
"conservation": "conserved"
```

is not evidence of conservation. It should be paired with an actual check and a recorded result.