For `river_transport.py`, the main fixes are:

1. **Include all surface-budget series in forcing-change detection.**
2. **Use the same linearized surface flux for solving and accounting**, so numerical budget closure is meaningful.
3. **Avoid claiming a `1e-9` conservation result while accounting with a different nonlinear flux.**
4. **Serialize effective surface-budget behavior consistently.**
5. **Add tests for forcing discontinuities and budget closure.**

The current problem is here:

```python
self._forcing = (
    self.boundary_c,
    self.air_c,
    self.net_heat_flux,
    *(s.temperature_c for s in self.sources),
    *(s for s in self._cell_heat if s is not None),
)
```

The explicit surface-budget series are missing. Also, `_system()` solves using a linearized budget, while `_advance_to()` accounts using the nonlinear flux at the new temperature.

---

# 1. Add all surface-budget series to `_forcing`

Replace the current `_forcing` construction in `River.__init__()` with:

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
    forcing_series.extend([
        self.surface_budget.rh,
        self.surface_budget.wind_mps,
        self.surface_budget.shortwave_w_m2,
        self.surface_budget.cloud,
    ])

self._forcing = tuple(forcing_series)
```

Now `run()` will split integration at changes to:

- relative humidity;
- wind speed;
- shortwave;
- cloud fraction;
- boundary temperature;
- lateral-source temperature;
- cell heat;
- air temperature;
- additional heat flux.

Without this fix, a 60-second weather schedule can be integrated as though the first weather value remains active over the entire interval.

---

# 2. Validate `SurfaceBudget` series more strictly

The current `SurfaceBudget.__post_init__()` checks values, but it does not require the meteorological series to share the same time domain.

That is not necessarily wrong because `Series.at()` holds its final value indefinitely, but it can hide configuration mistakes.

Add this helper:

```python
def _series_end_times_match(
    series: tuple[Series, ...],
) -> bool:
    end_times = {
        item.times_s[-1]
        for item in series
    }
    return len(end_times) <= 1
```

Then add to `SurfaceBudget.__post_init__()`:

```python
met_series = (
    self.rh,
    self.wind_mps,
    self.shortwave_w_m2,
    self.cloud,
)

if not _series_end_times_match(met_series):
    raise ValueError(
        "surface budget meteorological series must have the "
        "same final forcing time"
    )
```

You may also require identical change times if the budget producer is expected to generate synchronized records:

```python
def _series_times_match(
    series: tuple[Series, ...],
) -> bool:
    first = series[0].times_s
    return all(item.times_s == first for item in series[1:])
```

Then:

```python
if not _series_times_match(met_series):
    raise ValueError(
        "surface budget meteorological series must share "
        "the same times_s grid"
    )
```

I recommend allowing different change times if the solver is intentionally designed to merge them. The `_forcing` fix above supports that. Requiring only valid, increasing series is more flexible.

---

# 3. Add a helper for linearized surface terms

The numerical solver currently calculates surface-budget terms inside `_system()`. Move that calculation into a helper so the solver and accounting use identical logic.

Add this method to `River`:

```python
def _surface_linearization(
    self,
    cell_index: int,
    time_s: float,
) -> tuple[float, float, dict[str, float] | None]:
    """Return surface matrix terms for one cell.

    Returns:
        exchange:
            Temperature coefficient in m3/s-like temperature-volume units.
        rhs:
            Constant surface contribution in temperature-volume units.
        metadata:
            Linearization details, or None for Newton mode.
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

    met = self.surface_budget.met_at(time_s, air)

    old_temperature = self._temperature_c[cell_index]

    flux0, slope = linearized(
        old_temperature,
        met,
        self.surface_budget.params,
    )

    # F(T_new) ≈ F(T_old) + dF/dT * (T_new - T_old)
    #
    # Rearranged:
    # F(T_new) ≈ dF/dT * T_new
    #             + F(T_old)
    #             - dF/dT * T_old
    #
    # The matrix uses -dF/dT as a positive diagonal contribution when
    # the flux decreases as water temperature increases.
    exchange = -slope * area / self.rho_cp

    rhs = (
        (flux0 - slope * old_temperature)
        * area
        / self.rho_cp
    )

    metadata = {
        "flux_at_old_temperature_w_m2": float(flux0),
        "flux_temperature_slope_w_m2_k": float(slope),
        "air_temperature_c": float(air),
        "relative_humidity": float(met.rh),
        "wind_mps": float(met.wind_mps),
        "shortwave_w_m2": float(met.shortwave_w_m2),
        "cloud": float(met.cloud),
    }

    return exchange, rhs, metadata
```

---

# 4. Replace the surface branch in `_system()`

Inside `_system()`, replace this entire block:

```python
area = cell.surface_area_m2
if self.surface_budget is None:
    exchange = (
        cell.exchange_w_m2_k
        * area
        / self.rho_cp
    )
    surface_rhs = exchange * air
else:
    met = self.surface_budget.met_at(time_s, air)
    flux0, slope = linearized(
        self._temperature_c[i], met,
        self.surface_budget.params)
    exchange = -slope * area / self.rho_cp
    surface_rhs = (
        (flux0 - slope * self._temperature_c[i])
        * area / self.rho_cp
    )
```

with:

```python
exchange, surface_rhs, _surface_metadata = (
    self._surface_linearization(i, time_s)
)
```

The complete loop section becomes:

```python
for i, cell in enumerate(self.cells):
    exchange, surface_rhs, _surface_metadata = (
        self._surface_linearization(i, time_s)
    )

    lower[i] = -(q[i] + g[i]) if i > 0 else 0.0
    diagonal[i] = (
        q[i + 1]
        + g[i]
        + g[i + 1]
        + exchange
    )
    upper[i] = -g[i + 1] if i + 1 < n else 0.0

    rhs[i] = math.fsum((
        source_qt[i],
        surface_rhs,
        area * extra_flux / self.rho_cp,
        cell_heat[i] / self.rho_cp,
    ))

    if dt_s is not None:
        storage = cell.volume_m3 / dt_s
        diagonal[i] += storage
        rhs[i] += storage * self._temperature_c[i]
```

There is one correction: the rewritten loop no longer declares `area`. Add:

```python
area = cell.surface_area_m2
```

before `rhs`:

```python
area = cell.surface_area_m2
rhs[i] = math.fsum((
    source_qt[i],
    surface_rhs,
    area * extra_flux / self.rho_cp,
    cell_heat[i] / self.rho_cp,
))
```

---

# 5. Add a helper for accounting surface power

Add this method to `River`:

```python
def _surface_power_for_accounting(
    self,
    temperatures: list[float],
    time_s: float,
) -> tuple[list[float], dict[str, list[float]] | None]:
    """Return surface power consistent with the solved equation.

    For explicit budgets, accounting intentionally uses the same first-order
    linearization used by the implicit matrix. This makes the reported
    residual a numerical conservation residual rather than a mixture of
    nonlinear and linearized equations.
    """
    air = self.air_c.at(time_s)
    extra_flux = self.net_heat_flux.at(time_s)

    surface_power_w: list[float] = []
    component_power_w: dict[str, list[float]] | None = None

    if self.surface_budget is None:
        for cell, temperature in zip(self.cells, temperatures):
            area = cell.surface_area_m2
            power = area * (
                cell.exchange_w_m2_k
                * (air - temperature)
                + extra_flux
            )
            surface_power_w.append(power)

        return surface_power_w, None

    component_power_w = {
        name: []
        for name in (
            "shortwave",
            "longwave",
            "sensible",
            "latent",
        )
    }

    for i, (cell, temperature) in enumerate(
        zip(self.cells, temperatures)
    ):
        area = cell.surface_area_m2

        _exchange, _rhs, metadata = (
            self._surface_linearization(i, time_s)
        )

        if metadata is None:
            raise AssertionError(
                "surface budget metadata unexpectedly missing"
            )

        flux0 = metadata["flux_at_old_temperature_w_m2"]
        slope = metadata["flux_temperature_slope_w_m2_k"]
        old_temperature = self._temperature_c[i]

        # Same approximation used in _system():
        linearized_flux = (
            flux0
            + slope * (temperature - old_temperature)
        )

        surface_power_w.append(
            area * (linearized_flux + extra_flux)
        )

        # The component breakdown cannot be exactly reconstructed from the
        # aggregate derivative without evaluating each component using the
        # same linearization. Use the current physical component evaluation
        # only as a diagnostic, not as the conservation total.
        met = self.surface_budget.met_at(time_s, air)
        parts = flux_at(
            temperature,
            met,
            self.surface_budget.params,
        )

        for name in component_power_w:
            component_power_w[name].append(
                parts[name] * area
            )

    return surface_power_w, component_power_w
```

This makes the energy total consistent with the matrix solve.

---

# 6. Replace surface accounting in `_advance_to()`

Remove this current block:

```python
surface_power_w = [
    cell.surface_area_m2 * (
        extra_flux
        + cell.exchange_w_m2_k * (air - temperature)
    )
    for cell, temperature in zip(self.cells, new)
]
if self.surface_budget is None:
    component_power_w: dict[str, list[float]] | None = None
else:
    met_now = self.surface_budget.met_at(start_s, air)
    fluxes = [flux_at(temperature, met_now,
                       self.surface_budget.params)
               for temperature in new]
    surface_power_w = [
        cell.surface_area_m2 * parts["net"] + area_extra
        for cell, parts, area_extra in zip(
            self.cells, fluxes,
            (cell.surface_area_m2 * extra_flux
             for cell in self.cells)
        )
    ]
    component_power_w = {
        name: [parts[name] * cell.surface_area_m2
               for cell, parts in zip(self.cells, fluxes)]
        for name in ("shortwave", "longwave",
                     "sensible", "latent")
    }
```

Replace it with:

```python
surface_power_w, component_power_w = (
    self._surface_power_for_accounting(
        new,
        start_s,
    )
)
```

This is the central accounting fix.

---

# 7. Clarify component totals

There is an important semantic issue: `surface_power_w` includes:

```python
extra_flux
```

but the component totals:

```python
surface_shortwave_j
surface_longwave_j
surface_sensible_j
surface_latent_j
```

do not include the additional prescribed flux. Therefore those component totals do not necessarily sum to:

```python
surface_exchange_j
```

That may be intended because `net_heat_flux_w_m2` is a separate forcing. Make it explicit by adding a separate total.

Add this name to `_totals`:

```python
"additional_heat_flux_j",
```

Then change the increment construction:

```python
increments = {
    ...
    "surface_exchange_j": dt_s * math.fsum(surface_power_w),
    "additional_heat_flux_j": (
        dt_s
        * math.fsum(
            cell.surface_area_m2 * extra_flux
            for cell in self.cells
        )
    ),
    ...
}
```

But then `surface_exchange_j` should represent only the surface-budget/Newton term, not the additional flux. A cleaner structure is:

```python
base_surface_power_w: list[float]
additional_heat_power_w: list[float]

if self.surface_budget is None:
    base_surface_power_w = [
        cell.surface_area_m2
        * cell.exchange_w_m2_k
        * (air - temperature)
        for cell, temperature in zip(self.cells, new)
    ]
else:
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

surface_power_w = [
    base + additional
    for base, additional in zip(
        base_surface_power_w,
        additional_heat_power_w,
    )
]
```

Then:

```python
increments = {
    ...
    "surface_exchange_j": (
        dt_s * math.fsum(base_surface_power_w)
    ),
    "additional_heat_flux_j": (
        dt_s * math.fsum(additional_heat_power_w)
    ),
    ...
}
```

And change the energy equation in `_advance_to()`:

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

Do the same in `budget()`.

This produces a clearer accounting model:

```text
total surface heating =
    Newton or explicit surface budget
    + additional prescribed heat flux
```

---

# 8. Update `_totals`

Replace:

```python
"surface_exchange_j",
"cell_heat_j",
```

with:

```python
"surface_exchange_j",
"additional_heat_flux_j",
"cell_heat_j",
```

The total dictionary should contain:

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

# 9. Update `_advance_to()` increments

Use this structure:

```python
air = self.air_c.at(start_s)
extra_flux = self.net_heat_flux.at(start_s)

if self.surface_budget is None:
    base_surface_power_w = [
        cell.surface_area_m2
        * cell.exchange_w_m2_k
        * (air - temperature)
        for cell, temperature in zip(self.cells, new)
    ]

    component_power_w = None
else:
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

surface_power_w = [
    base + additional
    for base, additional in zip(
        base_surface_power_w,
        additional_heat_power_w,
    ]
]
```

Then:

```python
increments = {
    "boundary_input_j": self.rho_cp * dt_s * faces[0],
    "lateral_input_j": (
        self.rho_cp * dt_s * math.fsum(source_qt)
    ),
    "outlet_export_j": self.rho_cp * dt_s * faces[-1],
    "surface_exchange_j": (
        dt_s * math.fsum(base_surface_power_w)
    ),
    "additional_heat_flux_j": (
        dt_s * math.fsum(additional_heat_power_w)
    ),
    "cell_heat_j": dt_s * math.fsum(cell_heat),
    "boundary_input_m3": dt_s * q[0],
    "lateral_input_m3": dt_s * math.fsum(self._lateral_q),
    "outlet_export_m3": dt_s * q[-1],
}
```

Keep the component totals:

```python
if component_power_w is not None:
    increments.update({
        f"surface_{name}_j": dt_s * math.fsum(powers)
        for name, powers in component_power_w.items()
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

# 10. Update the cell residual

The current cell residual uses:

```python
surface_power_w[i] / self.rho_cp
```

That remains correct after combining:

```python
base_surface_power_w + additional_heat_power_w
```

The expected cell equation is:

```python
expected = self.rho_cp * dt_s * math.fsum((
    faces[i],
    -faces[i + 1],
    source_qt[i],
    surface_power_w[i] / self.rho_cp,
    cell_heat[i] / self.rho_cp,
))
```

No other change is required.

---

# 11. Update `budget()`

Replace:

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

Also include the new term in `energy_scale`:

```python
abs(totals["surface_exchange_j"]),
abs(totals["additional_heat_flux_j"]),
abs(totals["cell_heat_j"]),
```

The returned budget will now distinguish:

```json
{
  "surface_exchange_j": 12345.0,
  "additional_heat_flux_j": 456.0,
  "surface_shortwave_j": 8000.0,
  "surface_longwave_j": -2000.0,
  "surface_sensible_j": -500.0,
  "surface_latent_j": -300.0
}
```

---

# 12. Fix `make_replay()` explicit-budget detection

Current code:

```python
explicit_budget = "surface_budget" in config
```

This incorrectly labels:

```python
{"surface_budget": null}
```

as an explicit-budget replay.

Replace it with:

```python
explicit_budget = config.get("surface_budget") is not None
```

Also add `cell_heat_w` to the configuration allowlist if the earlier feature is intended to be usable:

```python
allowed = {
    "cells",
    "sources",
    "boundary_m3_s",
    "boundary_c",
    "air_c",
    "net_heat_flux_w_m2",
    "rho_cp_j_m3_k",
    "surface_budget",
    "cell_heat_w",
    "duration_s",
    "dt_s",
    "sample_s",
    "initialize_steady",
    "status",
    "parameter_notes",
}
```

Pass it into `River`:

```python
"cell_heat_w": config.get("cell_heat_w"),
```

---

# 13. Add diagnostics for the linearized budget

Add these fields to `River.__init__()`:

```python
self.max_surface_linearization_error_w = 0.0
```

Inside `_surface_power_for_accounting()`, after computing the linearized flux:

```python
nonlinear_parts = flux_at(
    temperature,
    met,
    self.surface_budget.params,
)

nonlinear_flux = nonlinear_parts["net"]

linearized_flux = (
    flux0
    + slope * (temperature - old_temperature)
)

linearization_error = abs(
    nonlinear_flux - linearized_flux
) * area

self.max_surface_linearization_error_w = max(
    self.max_surface_linearization_error_w,
    linearization_error,
)
```

Then include it in `budget()`:

```python
"max_surface_linearization_error_w": (
    self.max_surface_linearization_error_w
),
```

This makes the distinction clear:

- `heat_relative_residual`: conservation of the discretized equation;
- `max_surface_linearization_error_w`: difference between nonlinear physics and the one-step linear approximation.

---

# 14. Consider nonlinear iteration for higher physical accuracy

The changes above make the budget close correctly, but explicit surface fluxes are still solved using one linearization around the old temperature.

For larger timesteps or strongly nonlinear latent/sensible heat fluxes, use Picard iteration.

A future `_advance_to()` implementation could:

```python
def _solve_step_iterated(
    self,
    start_s: float,
    dt_s: float,
    max_iterations: int = 8,
    tolerance_c: float = 1e-7,
) -> list[float]:
    guess = list(self._temperature_c)

    for _ in range(max_iterations):
        old_temperature = self._temperature_c
        self._temperature_c = guess

        candidate = solve_tridiagonal(
            *self._system(start_s, dt_s)
        )

        difference = max(
            abs(a - b)
            for a, b in zip(candidate, guess)
        )

        guess = candidate

        if difference <= tolerance_c:
            self._temperature_c = old_temperature
            return candidate

    self._temperature_c = old_temperature

    raise ArithmeticError(
        "explicit surface-budget nonlinear iteration did not converge"
    )
```

Then use the converged nonlinear flux for accounting.

However, do not add this casually: it changes solver behavior and performance. The linearized accounting fix should be applied first and covered by tests.

---

# 15. Add regression tests

## Surface-budget changes split integration

```python
def test_surface_budget_changes_split_integration():
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

    assert river.time_s == pytest.approx(10.0)
    assert river.steps == 2
```

Before the fix, the run can incorrectly use one step across the forcing change.

---

## Explicit-budget conservation closes

```python
def test_explicit_budget_closes_against_linearized_accounting():
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
    )

    river.run(
        duration_s=60.0,
        dt_s=1.0,
        sample_s=60.0,
    )

    budget = river.budget()

    assert budget["heat_relative_residual"] < 1e-10
```

Use a slightly looser tolerance if `surface_flux.py` introduces additional floating-point operations.

---

## Additional heat flux is separately accounted

```python
def test_additional_heat_flux_has_separate_budget_term():
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

    assert budget["additional_heat_flux_j"] > 0.0
    assert budget["heat_relative_residual"] < 1e-10
```

---

## Explicit budget is detected by effective state

```python
def test_null_surface_budget_is_not_explicit():
    config = {
        "cells": [
            {
                "id": "c0",
                "length_m": 10.0,
                "width_m": 2.0,
                "volume_m3": 20.0,
                "initial_c": 10.0,
            }
        ],
        "boundary_m3_s": 1.0,
        "boundary_c": 10.0,
        "surface_budget": None,
    }

    document = make_replay(config)

    assert document["model"]["surface_flux"] == "newton_lumped"
```

---

# 16. Update replay metadata

Add to `make_replay()`:

```python
surface_accounting = {
    "method": (
        "linearized_implicit_budget"
        if explicit_budget
        else "newton_lumped"
    ),
    "additional_heat_flux_separate": True,
    "nonlinear_surface_flux_diagnostic": (
        "max_surface_linearization_error_w"
        if explicit_budget
        else None
    ),
}
```

Then include:

```python
"surface_accounting": surface_accounting,
```

inside `"model"`.

Also update limitations:

```python
(
    "Explicit surface budget is linearized implicitly around the "
    "previous cell temperature; conservation closes for the "
    "discretized linearized equation, while nonlinear-vs-linearized "
    "flux error is reported separately."
    if explicit_budget
    else
    "Surface exchange is a reduced Newton approximation."
),
```

---

## Summary of the required fixes

The minimum correct patch is:

```python
if self.surface_budget is not None:
    forcing_series.extend([
        self.surface_budget.rh,
        self.surface_budget.wind_mps,
        self.surface_budget.shortwave_w_m2,
        self.surface_budget.cloud,
    ])
```

plus replacing nonlinear accounting:

```python
flux_at(new_temperature, ...)
```

with accounting based on the same linearized flux used by `_system()`.

The stronger version also:

- separates `additional_heat_flux_j`;
- adds linearization diagnostics;
- supports `cell_heat_w` through configuration;
- fixes explicit-budget detection;
- adds tests for forcing boundaries and closure;
- documents that closure is for the discretized equation, not necessarily the exact nonlinear surface physics.