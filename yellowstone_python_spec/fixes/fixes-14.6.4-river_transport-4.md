Below is a coherent implementation of **damped Newton iteration** for `river_transport.py`.

It solves the explicit surface-budget equation iteratively at every timestep:

```text
old temperature
    ↓
linearize surface flux around current guess
    ↓
solve tridiagonal system
    ↓
damp update
    ↓
repeat until temperature converges
```

Newton iteration is used only when `surface_budget` is active. The ordinary Newton-lumped exchange remains a direct linear solve.

---

# 1. Add solver defaults

Add near the existing constants:

```python
DEFAULT_MAX_SURFACE_ITERATIONS = 12
DEFAULT_SURFACE_TOLERANCE_C = 1e-7
DEFAULT_SURFACE_RELAXATION = 0.8
```

---

# 2. Extend `River.__init__()`

Add these parameters to the constructor:

```python
def __init__(
    self,
    cells: tuple[Cell, ...] | list[Cell],
    boundary_m3_s: float,
    boundary_c: Any,
    sources: tuple[Source, ...] | list[Source] = (),
    air_c: Any = 7.0,
    net_heat_flux_w_m2: Any = 0.0,
    rho_cp_j_m3_k: float = RHO_CP_J_M3_K,
    surface_budget: Any = None,
    cell_heat_w: dict[str, Any] | None = None,
    max_surface_iterations: int = DEFAULT_MAX_SURFACE_ITERATIONS,
    surface_tolerance_c: float = DEFAULT_SURFACE_TOLERANCE_C,
    surface_relaxation: float = DEFAULT_SURFACE_RELAXATION,
) -> None:
```

After validating `rho_cp`, add:

```python
if (
    isinstance(max_surface_iterations, bool)
    or not isinstance(max_surface_iterations, int)
):
    raise ValueError(
        "max_surface_iterations must be an integer"
    )

if max_surface_iterations < 1:
    raise ValueError(
        "max_surface_iterations must be positive"
    )

self.max_surface_iterations = max_surface_iterations

self.surface_tolerance_c = positive(
    surface_tolerance_c,
    "surface_tolerance_c",
)

self.surface_relaxation = finite(
    surface_relaxation,
    "surface_relaxation",
)

if not 0.0 < self.surface_relaxation <= 1.0:
    raise ValueError(
        "surface_relaxation must be in the interval (0, 1]"
    )
```

Add these diagnostics near the other numerical state:

```python
self.max_surface_iterations_used = 0
self.surface_iteration_failures = 0
self.max_surface_linearization_error_w = 0.0
```

---

# 3. Include surface-budget series in `_forcing`

Replace the existing `_forcing` assignment:

```python
self._forcing = (
    self.boundary_c,
    self.air_c,
    self.net_heat_flux,
    *(s.temperature_c for s in self.sources),
    *(s for s in self._cell_heat if s is not None),
)
```

with:

```python
forcing_series: list[Series] = [
    self.boundary_c,
    self.air_c,
    self.net_heat_flux,
]

forcing_series.extend(
    source.temperature_c
    for source in self.sources
)

forcing_series.extend(
    series
    for series in self._cell_heat
    if series is not None
)

if self.surface_budget is not None:
    forcing_series.extend((
        self.surface_budget.rh,
        self.surface_budget.wind_mps,
        self.surface_budget.shortwave_w_m2,
        self.surface_budget.cloud,
    ))

self._forcing = tuple(forcing_series)
```

This ensures the solver never steps across a change in the surface meteorology.

---

# 4. Replace `_surface_linearization()`

Add or replace the method inside `River`:

```python
def _surface_linearization(
    self,
    cell_index: int,
    time_s: float,
    temperature_for_linearization: float | None = None,
) -> tuple[float, float, dict[str, float] | None]:
    """Linearize the surface heat flux for one cell.

    Returns:
        exchange:
            Coefficient added to the transport matrix diagonal.

        rhs:
            Constant surface contribution added to the RHS.

        metadata:
            Surface linearization details, or None for Newton-lumped mode.

    The temperature used for linearization is the current Newton iterate,
    not necessarily the previous timestep temperature.
    """
    cell = self.cells[cell_index]
    area = cell.surface_area_m2
    air = self.air_c.at(time_s)

    if self.surface_budget is None:
        exchange = (
            cell.exchange_w_m2_k
            * area
            / self.rho_cp
        )

        rhs = exchange * air

        return exchange, rhs, None

    if temperature_for_linearization is None:
        temperature_for_linearization = (
            self._temperature_c[cell_index]
        )

    temperature_for_linearization = finite(
        temperature_for_linearization,
        f"surface linearization temperature cell {cell_index}",
    )

    met = self.surface_budget.met_at(time_s, air)

    flux0, slope = linearized(
        temperature_for_linearization,
        met,
        self.surface_budget.params,
    )

    flux0 = finite(
        flux0,
        f"surface flux cell {cell_index}",
    )

    slope = finite(
        slope,
        f"surface flux slope cell {cell_index}",
    )

    # F(T) ≈ F(Tk) + dF/dT * (T - Tk)
    #
    # F(T) ≈ dF/dT * T + F(Tk) - dF/dT * Tk
    #
    # Move the dF/dT*T term to the left side.
    exchange = -slope * area / self.rho_cp

    rhs = (
        flux0
        - slope * temperature_for_linearization
    ) * area / self.rho_cp

    return exchange, rhs, {
        "linearization_temperature_c": (
            float(temperature_for_linearization)
        ),
        "flux_at_linearization_temperature_w_m2": float(flux0),
        "flux_temperature_slope_w_m2_k": float(slope),
        "air_temperature_c": float(air),
        "relative_humidity": float(met.rh),
        "wind_mps": float(met.wind_mps),
        "shortwave_w_m2": float(met.shortwave_w_m2),
        "cloud": float(met.cloud),
    }
```

---

# 5. Update `_system()`

Change the signature from:

```python
def _system(
    self,
    time_s: float,
    dt_s: float | None = None,
) -> tuple[list[float], list[float], list[float], list[float]]:
```

to:

```python
def _system(
    self,
    time_s: float,
    dt_s: float | None = None,
    linearization_temperature: list[float] | None = None,
) -> tuple[list[float], list[float], list[float], list[float]]:
```

At the beginning of `_system()`, after `n = len(self.cells)`, add:

```python
if linearization_temperature is None:
    linearization_temperature = list(self._temperature_c)
elif len(linearization_temperature) != n:
    raise ValueError(
        "linearization_temperature must have one value per cell"
    )

if any(
    not math.isfinite(value)
    for value in linearization_temperature
):
    raise ValueError(
        "linearization_temperature contains a nonfinite value"
    )
```

Then replace the loop body’s surface-flux construction with:

```python
for i, cell in enumerate(self.cells):
    exchange, surface_rhs, _metadata = (
        self._surface_linearization(
            i,
            time_s,
            linearization_temperature[i],
        )
    )

    area = cell.surface_area_m2

    lower[i] = (
        -(q[i] + g[i])
        if i > 0
        else 0.0
    )

    diagonal[i] = (
        q[i + 1]
        + g[i]
        + g[i + 1]
        + exchange
    )

    upper[i] = (
        -g[i + 1]
        if i + 1 < n
        else 0.0
    )

    rhs[i] = math.fsum((
        source_qt[i],
        surface_rhs,
        area * extra_flux / self.rho_cp,
        cell_heat[i] / self.rho_cp,
    ))

    if dt_s is not None:
        storage = cell.volume_m3 / dt_s
        diagonal[i] += storage
        rhs[i] += (
            storage
            * self._temperature_c[i]
        )
```

Important: the storage term must continue to use:

```python
self._temperature_c[i]
```

That is the temperature at the start of the timestep. Only the surface-flux linearization uses the Newton iterate.

---

# 6. Add the damped Newton step solver

Add this method inside `River`:

```python
def _solve_implicit_step(
    self,
    start_s: float,
    dt_s: float,
) -> tuple[list[float], int]:
    """Solve one implicit timestep.

    Newton-lumped exchange is linear and requires one solve.

    An explicit surface budget is nonlinear in water temperature, so the
    surface flux is relinearized around the current temperature estimate
    until the solution converges.
    """
    if self.surface_budget is None:
        solution = solve_tridiagonal(
            *self._system(start_s, dt_s)
        )
        return solution, 1

    old_temperature = list(self._temperature_c)
    guess = old_temperature.copy()
    last_update = math.inf

    for iteration in range(
        1,
        self.max_surface_iterations + 1,
    ):
        lower, diagonal, upper, rhs = self._system(
            start_s,
            dt_s,
            linearization_temperature=guess,
        )

        candidate = solve_tridiagonal(
            lower,
            diagonal,
            upper,
            rhs,
        )

        if len(candidate) != len(guess):
            raise ArithmeticError(
                "surface iteration returned the wrong number "
                "of temperatures"
            )

        if any(
            not math.isfinite(value)
            for value in candidate
        ):
            raise ArithmeticError(
                "surface iteration produced a nonfinite temperature"
            )

        last_update = max(
            abs(new - previous)
            for new, previous in zip(candidate, guess)
        )

        if last_update <= self.surface_tolerance_c:
            self.max_surface_iterations_used = max(
                self.max_surface_iterations_used,
                iteration,
            )
            return candidate, iteration

        # Damped Newton update:
        #
        # guess_new =
        #     guess_old + relaxation * (candidate - guess_old)
        #
        # A relaxation below 1 reduces oscillations when latent or longwave
        # fluxes are strongly temperature-sensitive.
        relaxation = self.surface_relaxation

        guess = [
            previous
            + relaxation * (new - previous)
            for previous, new in zip(guess, candidate)
        ]

        if any(
            not math.isfinite(value)
            for value in guess
        ):
            raise ArithmeticError(
                "surface iteration produced a nonfinite damped guess"
            )

    self.surface_iteration_failures += 1

    raise ArithmeticError(
        "surface-budget Newton iteration did not converge after "
        f"{self.max_surface_iterations} iterations; "
        f"last maximum temperature update was "
        f"{last_update:.6g} C"
    )
```

This method does not mutate `self._temperature_c` during iteration. That is important: the old timestep state remains fixed while `_system()` builds the storage term.

---

# 7. Add final surface-flux accounting

Add this method inside `River`:

```python
def _surface_power_for_accounting(
    self,
    temperatures: list[float],
    time_s: float,
) -> tuple[
    list[float],
    dict[str, list[float]] | None,
]:
    """Evaluate final surface powers after the timestep solve.

    For an explicit surface budget, this uses the converged nonlinear flux.
    The numerical state has been iterated until this flux is consistent with
    the temperature solution.

    The component powers are returned as diagnostics and should sum to the
    nonlinear net surface-budget power, excluding net_heat_flux_w_m2.
    """
    if len(temperatures) != len(self.cells):
        raise ValueError(
            "surface accounting temperature count does not match cells"
        )

    air = self.air_c.at(time_s)

    if self.surface_budget is None:
        powers: list[float] = []

        for cell, temperature in zip(
            self.cells,
            temperatures,
        ):
            power = (
                cell.surface_area_m2
                * cell.exchange_w_m2_k
                * (air - temperature)
            )

            powers.append(
                finite(
                    power,
                    "Newton surface power",
                )
            )

        return powers, None

    met = self.surface_budget.met_at(
        time_s,
        air,
    )

    powers = []
    component_power_w: dict[str, list[float]] = {
        "shortwave": [],
        "longwave": [],
        "sensible": [],
        "latent": [],
    }

    for index, (cell, temperature) in enumerate(
        zip(self.cells, temperatures)
    ):
        parts = flux_at(
            temperature,
            met,
            self.surface_budget.params,
        )

        required_components = (
            "net",
            "shortwave",
            "longwave",
            "sensible",
            "latent",
        )

        for name in required_components:
            if name not in parts:
                raise KeyError(
                    f"surface flux result lacks {name!r}"
                )

        nonlinear_net = finite(
            parts["net"],
            f"nonlinear surface flux cell {index}",
        )

        power = cell.surface_area_m2 * nonlinear_net

        powers.append(
            finite(
                power,
                f"nonlinear surface power cell {index}",
            )
        )

        for name in component_power_w:
            component_value = finite(
                parts[name],
                f"surface component {name} cell {index}",
            )

            component_power_w[name].append(
                cell.surface_area_m2 * component_value
            )

        # Compare the converged nonlinear flux to the final local
        # linearization. This is a diagnostic, not an additional energy term.
        _exchange, _rhs, metadata = (
            self._surface_linearization(
                index,
                time_s,
                temperature_for_linearization=temperature,
            )
        )

        if metadata is not None:
            local_flux = metadata[
                "flux_at_linearization_temperature_w_m2"
            ]

            linearization_error_w = abs(
                nonlinear_net - local_flux
            ) * cell.surface_area_m2

            self.max_surface_linearization_error_w = max(
                self.max_surface_linearization_error_w,
                linearization_error_w,
            )

    return powers, component_power_w
```

Because the final flux is evaluated at the converged temperature, the nonlinear flux should be consistent with the final Newton iterate.

---

# 8. Replace `_advance_to()` solve and surface accounting

In `_advance_to()`, replace:

```python
new = solve_tridiagonal(
    *self._system(start_s, dt_s)
)
```

with:

```python
new, surface_iterations = (
    self._solve_implicit_step(
        start_s,
        dt_s,
    )
)
```

The `surface_iterations` local variable is useful for diagnostics, although the class-level maximum is also tracked.

Then replace the current surface-power block with:

```python
base_surface_power_w, component_power_w = (
    self._surface_power_for_accounting(
        new,
        start_s,
    )
)

additional_heat_power_w = [
    cell.surface_area_m2 * extra_flux
    for cell in self.cells
]

additional_heat_power_w = [
    finite(
        power,
        "additional surface heat power",
    )
    for power in additional_heat_power_w
]

surface_power_w = [
    base_power + additional_power
    for base_power, additional_power in zip(
        base_surface_power_w,
        additional_heat_power_w,
    )
]
```

Here:

```text
base_surface_power_w
    Newton or explicit nonlinear surface budget

additional_heat_power_w
    net_heat_flux_w_m2 contribution

surface_power_w
    total surface contribution used in cell residuals
```

---

# 9. Replace the increments block

Use:

```python
increments = {
    "boundary_input_j": (
        self.rho_cp
        * dt_s
        * faces[0]
    ),

    "lateral_input_j": (
        self.rho_cp
        * dt_s
        * math.fsum(source_qt)
    ),

    "outlet_export_j": (
        self.rho_cp
        * dt_s
        * faces[-1]
    ),

    # Does not include net_heat_flux_w_m2.
    "surface_exchange_j": (
        dt_s
        * math.fsum(base_surface_power_w)
    ),

    # Separate prescribed heat-flux contribution.
    "additional_heat_flux_j": (
        dt_s
        * math.fsum(additional_heat_power_w)
    ),

    "cell_heat_j": (
        dt_s
        * math.fsum(cell_heat)
    ),

    "boundary_input_m3": dt_s * q[0],
    "lateral_input_m3": (
        dt_s * math.fsum(self._lateral_q)
    ),
    "outlet_export_m3": dt_s * q[-1],
}
```

Retain the diagnostic component terms:

```python
if component_power_w is not None:
    increments.update({
        f"surface_{name}_j": (
            dt_s * math.fsum(power_values)
        )
        for name, power_values in component_power_w.items()
    })
else:
    increments.update({
        f"surface_{name}_j": 0.0
        for name in (
            "shortwave",
            "longwave",
            "sensible",
            "latent",
        )
    })
```

---

# 10. Update the step energy balance

Replace:

```python
expected_change_j = math.fsum((
    increments["boundary_input_j"],
    increments["lateral_input_j"],
    -increments["outlet_export_j"],
    increments["surface_exchange_j"],
    increments["cell_heat_j"],
))
```

with:

```python
expected_change_j = math.fsum((
    increments["boundary_input_j"],
    increments["lateral_input_j"],
    -increments["outlet_export_j"],
    increments["surface_exchange_j"],
    increments["additional_heat_flux_j"],
    increments["cell_heat_j"],
))
```

The cell residual should use the combined surface power:

```python
expected = self.rho_cp * dt_s * math.fsum((
    faces[i],
    -faces[i + 1],
    source_qt[i],
    surface_power_w[i] / self.rho_cp,
    cell_heat[i] / self.rho_cp,
))
```

---

# 11. Update `_totals`

Add these names to the totals dictionary:

```python
"additional_heat_flux_j",
```

For example:

```python
self._totals = {
    name: _Sum()
    for name in (
        "boundary_input_j",
        "lateral_input_j",
        "outlet_export_j",
        "surface_exchange_j",
        "additional_heat_flux_j",
        "cell_heat_j",
        "surface_shortwave_j",
        "surface_longwave_j",
        "surface_sensible_j",
        "surface_latent_j",
        "boundary_input_m3",
        "lateral_input_m3",
        "outlet_export_m3",
    )
}
```

---

# 12. Update `budget()`

Replace the expected-energy calculation:

```python
expected_change_j = math.fsum((
    totals["boundary_input_j"],
    totals["lateral_input_j"],
    -totals["outlet_export_j"],
    totals["surface_exchange_j"],
    totals["cell_heat_j"],
))
```

with:

```python
expected_change_j = math.fsum((
    totals["boundary_input_j"],
    totals["lateral_input_j"],
    -totals["outlet_export_j"],
    totals["surface_exchange_j"],
    totals["additional_heat_flux_j"],
    totals["cell_heat_j"],
))
```

Update the scale:

```python
energy_scale = max(
    1.0,
    abs(initial_j),
    abs(current_j),
    math.fsum(
        abs(totals[name])
        for name in (
            "boundary_input_j",
            "lateral_input_j",
            "outlet_export_j",
            "surface_exchange_j",
            "additional_heat_flux_j",
            "cell_heat_j",
        )
    ),
)
```

Add component diagnostics before the return:

```python
surface_component_sum_j = math.fsum(
    totals[name]
    for name in (
        "surface_shortwave_j",
        "surface_longwave_j",
        "surface_sensible_j",
        "surface_latent_j",
    )
)

surface_component_difference_j = (
    surface_component_sum_j
    - totals["surface_exchange_j"]
)
```

Add these fields to the returned dictionary:

```python
"surface_component_sum_j": surface_component_sum_j,
"surface_component_difference_j": (
    surface_component_difference_j
),
"max_surface_linearization_error_w": (
    self.max_surface_linearization_error_w
),
"max_surface_iterations_used": (
    self.max_surface_iterations_used
),
"surface_iteration_failures": (
    self.surface_iteration_failures
),
```

With full nonlinear accounting, `surface_component_difference_j` should be close to zero, subject to floating-point roundoff.

---

# 13. Add configuration support

In `river_from_config()`, add these keys to `allowed`:

```python
"cell_heat_w",
"max_surface_iterations",
"surface_tolerance_c",
"surface_relaxation",
```

Add them to `kwargs`:

```python
"cell_heat_w": config.get("cell_heat_w"),
"max_surface_iterations": config.get(
    "max_surface_iterations",
    DEFAULT_MAX_SURFACE_ITERATIONS,
),
"surface_tolerance_c": config.get(
    "surface_tolerance_c",
    DEFAULT_SURFACE_TOLERANCE_C,
),
"surface_relaxation": config.get(
    "surface_relaxation",
    DEFAULT_SURFACE_RELAXATION,
),
```

The relevant `kwargs` block becomes:

```python
kwargs = {
    "cells": tuple(
        Cell(**row)
        for row in config["cells"]
    ),
    "sources": tuple(
        Source(**row)
        for row in config.get("sources", [])
    ),
    "boundary_m3_s": config["boundary_m3_s"],
    "boundary_c": config["boundary_c"],
    "air_c": config.get("air_c", 7.0),
    "net_heat_flux_w_m2": config.get(
        "net_heat_flux_w_m2",
        0.0,
    ),
    "rho_cp_j_m3_k": config.get(
        "rho_cp_j_m3_k",
        RHO_CP_J_M3_K,
    ),
    "surface_budget": config.get(
        "surface_budget"
    ),
    "cell_heat_w": config.get(
        "cell_heat_w"
    ),
    "max_surface_iterations": config.get(
        "max_surface_iterations",
        DEFAULT_MAX_SURFACE_ITERATIONS,
    ),
    "surface_tolerance_c": config.get(
        "surface_tolerance_c",
        DEFAULT_SURFACE_TOLERANCE_C,
    ),
    "surface_relaxation": config.get(
        "surface_relaxation",
        DEFAULT_SURFACE_RELAXATION,
    ),
}
```

---

# 14. Fix explicit-budget detection

In `make_replay()`, replace:

```python
explicit_budget = "surface_budget" in config
```

with:

```python
explicit_budget = (
    config.get("surface_budget") is not None
)
```

---

# 15. Add replay metadata

Inside the returned `"model"` dictionary, add:

```python
"surface_solver": {
    "method": (
        "damped_newton"
        if explicit_budget
        else "direct_linear_newton_exchange"
    ),
    "max_iterations": river.max_surface_iterations,
    "temperature_tolerance_c": river.surface_tolerance_c,
    "relaxation": river.surface_relaxation,
    "max_iterations_used": budget[
        "max_surface_iterations_used"
    ],
    "iteration_failures": budget[
        "surface_iteration_failures"
    ],
    "max_surface_linearization_error_w": budget[
        "max_surface_linearization_error_w"
    ],
},
```

Update the limitations list:

```python
(
    "Explicit surface budget solved with damped Newton iteration. "
    "The reported heat residual measures convergence and closure "
    "of the nonlinear implicit discretization; it is not "
    "observational validation."
    if explicit_budget
    else
    "Surface exchange is a reduced Newton approximation."
),
```

---

# 16. Recommended tests

```python
def test_damped_newton_explicit_budget_converges():
    river = River(
        cells=(
            Cell(
                id="c0",
                length_m=10.0,
                width_m=2.0,
                volume_m3=20.0,
                initial_c=10.0,
            ),
        ),
        boundary_m3_s=1.0,
        boundary_c=10.0,
        surface_budget={
            "rh": 0.5,
            "wind_mps": 2.0,
            "shortwave_w_m2": 100.0,
            "cloud": 0.2,
        },
        max_surface_iterations=20,
        surface_tolerance_c=1e-8,
        surface_relaxation=0.8,
    )

    river.run(
        duration_s=60.0,
        dt_s=5.0,
        sample_s=60.0,
    )

    budget = river.budget()

    assert budget["surface_iteration_failures"] == 0
    assert budget["max_surface_iterations_used"] >= 1
    assert budget["heat_relative_residual"] < 1e-8
```

```python
def test_surface_budget_changes_split_run():
    river = River(
        cells=(
            Cell(
                id="c0",
                length_m=10.0,
                width_m=2.0,
                volume_m3=20.0,
                initial_c=10.0,
            ),
        ),
        boundary_m3_s=1.0,
        boundary_c=10.0,
        surface_budget={
            "rh": {
                "times_s": [0.0, 5.0],
                "values": [0.5, 0.8],
            },
            "wind_mps": 2.0,
            "shortwave_w_m2": 0.0,
            "cloud": 0.5,
        },
    )

    river.run(
        duration_s=10.0,
        dt_s=10.0,
        sample_s=10.0,
    )

    assert river.steps == 2
```

```python
def test_additional_heat_flux_is_separate():
    river = River(
        cells=(
            Cell(
                id="c0",
                length_m=10.0,
                width_m=2.0,
                volume_m3=20.0,
                initial_c=10.0,
            ),
        ),
        boundary_m3_s=1.0,
        boundary_c=10.0,
        net_heat_flux_w_m2=10.0,
    )

    river.run(
        duration_s=10.0,
        dt_s=1.0,
        sample_s=10.0,
    )

    budget = river.budget()

    assert budget["additional_heat_flux_j"] == pytest.approx(
        10.0 * 20.0 * 10.0
    )
    assert budget["heat_relative_residual"] < 1e-10
```

The area is:

```text
width × length = 2 × 10 = 20 m²
```

so the added heat is:

```text
10 W/m² × 20 m² × 10 s = 2,000 J
```

---

# Important caveat

This implementation evaluates the final nonlinear surface flux after Newton convergence. Therefore, the surface-budget accounting is more physically consistent than the one-pass linearized version.

However, the energy residual will still depend on:

- Newton tolerance;
- maximum iteration count;
- floating-point precision;
- how `linearized()` approximates `flux_at()`;
- whether the derivative is accurate.

A suitable production configuration is:

```json
{
  "max_surface_iterations": 12,
  "surface_tolerance_c": 1e-7,
  "surface_relaxation": 0.8
}
```

For difficult or highly nonlinear conditions:

```json
{
  "max_surface_iterations": 24,
  "surface_tolerance_c": 1e-8,
  "surface_relaxation": 0.5
}
```

The solver should fail clearly if convergence is not achieved rather than silently accepting a partially converged thermal state.