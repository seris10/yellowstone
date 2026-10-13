Below is the stronger, internally consistent patch for `river_transport.py`.

It:

- Splits integration at all surface-budget forcing changes.
- Accounts for Newton/explicit surface exchange consistently.
- Separates `additional_heat_flux_j` from the surface budget.
- Reports nonlinear component fluxes as diagnostics, not as conservation terms.
- Tracks linearization error.
- Supports `cell_heat_w` through configuration.
- Corrects `explicit_budget` detection.
- Preserves near-machine-precision closure for the discretized equation.

---

# 1. Add a surface-accounting diagnostic

Add this field in `River.__init__()` after the existing numerical diagnostics:

```python
self.max_surface_linearization_error_w = 0.0
```

---

# 2. Include surface-budget series in forcing changes

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

This ensures that `run()` splits at changes to:

- humidity;
- wind;
- shortwave;
- cloud;
- air temperature;
- boundary temperature;
- source temperature;
- cell heat;
- additional prescribed heat flux.

---

# 3. Add `additional_heat_flux_j` to the totals

Replace the `_totals` declaration with:

```python
self._totals = {
    name: _Sum()
    for name in (
        "boundary_input_j",
        "lateral_input_j",
        "outlet_export_j",

        # Surface-budget or Newton exchange, excluding
        # net_heat_flux_w_m2.
        "surface_exchange_j",

        # Separate prescribed heat-flux contribution.
        "additional_heat_flux_j",

        "cell_heat_j",

        # Explicit-budget component diagnostics.
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

The distinction is now:

```text
surface_exchange_j
    Newton exchange or explicit surface budget

additional_heat_flux_j
    net_heat_flux_w_m2 applied over surface area

cell_heat_j
    per-cell volumetric heat power
```

---

# 4. Add a shared surface linearization helper

Add this method inside `River`:

```python
def _surface_linearization(
    self,
    cell_index: int,
    time_s: float,
) -> tuple[float, float, dict[str, float] | None]:
    """Return the surface terms used by the implicit transport equation.

    Returns:
        exchange:
            Matrix coefficient in temperature-volume units.
        rhs:
            Constant surface contribution in temperature-volume units.
        metadata:
            Linearization information for explicit-budget diagnostics.
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

    if not math.isfinite(flux0) or not math.isfinite(slope):
        raise ArithmeticError(
            f"nonfinite surface linearization at cell {cell_index}"
        )

    # F(T_new) ~= F(T_old) + slope * (T_new - T_old)
    #
    # F(T_new) ~= slope * T_new
    #             + F(T_old)
    #             - slope * T_old
    #
    # Move the slope*T_new term into the left-hand matrix.
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

# 5. Use the helper in `_system()`

Inside `_system()`, replace the existing surface-flux branch with:

```python
for i, cell in enumerate(self.cells):
    exchange, surface_rhs, _metadata = (
        self._surface_linearization(i, time_s)
    )

    area = cell.surface_area_m2

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

This keeps the matrix solve unchanged mathematically, but centralizes the surface-budget logic.

---

# 6. Add surface accounting helpers

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
    """Return surface-budget power and component diagnostics.

    The returned first list is the surface power used in conservation
    accounting. For an explicit budget, it uses the same first-order
    linearization as the implicit matrix.

    Component powers are evaluated from the nonlinear flux function and are
    diagnostics only. They are intentionally not used for heat closure,
    because the state was solved using the linearized net flux.
    """
    air = self.air_c.at(time_s)

    if self.surface_budget is None:
        powers = []

        for cell, temperature in zip(self.cells, temperatures):
            power = (
                cell.surface_area_m2
                * cell.exchange_w_m2_k
                * (air - temperature)
            )
            powers.append(power)

        return powers, None

    linearized_powers: list[float] = []
    component_power_w: dict[str, list[float]] = {
        "shortwave": [],
        "longwave": [],
        "sensible": [],
        "latent": [],
    }

    for index, (cell, temperature) in enumerate(
        zip(self.cells, temperatures)
    ):
        area = cell.surface_area_m2
        metadata = self._surface_linearization(
            index,
            time_s,
        )[2]

        if metadata is None:
            raise AssertionError(
                "explicit surface budget metadata is missing"
            )

        flux0 = metadata["flux_at_old_temperature_w_m2"]
        slope = metadata["flux_temperature_slope_w_m2_k"]
        old_temperature = self._temperature_c[index]

        # This is exactly the flux represented by the matrix solve.
        linearized_flux = (
            flux0
            + slope * (temperature - old_temperature)
        )

        if not math.isfinite(linearized_flux):
            raise ArithmeticError(
                f"nonfinite linearized surface flux at cell {index}"
            )

        linearized_powers.append(
            area * linearized_flux
        )

        # Nonlinear component breakdown is diagnostic only.
        met = self.surface_budget.met_at(time_s, air)

        nonlinear_parts = flux_at(
            temperature,
            met,
            self.surface_budget.params,
        )

        nonlinear_net = nonlinear_parts.get("net")
        if nonlinear_net is None:
            raise KeyError(
                "surface_flux.flux_at() did not return a 'net' component"
            )

        nonlinear_error_w = abs(
            float(nonlinear_net) - linearized_flux
        ) * area

        self.max_surface_linearization_error_w = max(
            self.max_surface_linearization_error_w,
            nonlinear_error_w,
        )

        for name in component_power_w:
            value = float(nonlinear_parts[name]) * area

            if not math.isfinite(value):
                raise ArithmeticError(
                    f"nonfinite nonlinear {name} surface power "
                    f"at cell {index}"
                )

            component_power_w[name].append(value)

    return linearized_powers, component_power_w
```

The important semantic separation is:

```text
linearized_powers
    used for conservation closure

component_power_w
    nonlinear diagnostic decomposition
```

---

# 7. Replace surface handling in `_advance_to()`

Remove the current surface-power block beginning with:

```python
surface_power_w = [
    cell.surface_area_m2 * (
        extra_flux
        + cell.exchange_w_m2_k * (air - temperature)
    )
    ...
]
```

Replace it with:

```python
if self.surface_budget is None:
    base_surface_power_w, component_power_w = (
        self._surface_power_for_accounting(
            new,
            start_s,
        )
    )
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
    base_power + additional_power
    for base_power, additional_power in zip(
        base_surface_power_w,
        additional_heat_power_w,
    )
]
```

The conditional is technically redundant because the helper handles both modes. It is clearer to use the simpler form:

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

surface_power_w = [
    base_power + additional_power
    for base_power, additional_power in zip(
        base_surface_power_w,
        additional_heat_power_w,
    )
]
```

---

# 8. Replace the increments dictionary

Replace the existing `increments` construction with:

```python
increments = {
    "boundary_input_j": (
        self.rho_cp * dt_s * faces[0]
    ),
    "lateral_input_j": (
        self.rho_cp
        * dt_s
        * math.fsum(source_qt)
    ),
    "outlet_export_j": (
        self.rho_cp * dt_s * faces[-1]
    ),

    # Only Newton or explicit surface-budget exchange.
    "surface_exchange_j": (
        dt_s * math.fsum(base_surface_power_w)
    ),

    # Separate from the surface budget.
    "additional_heat_flux_j": (
        dt_s * math.fsum(additional_heat_power_w)
    ),

    "cell_heat_j": (
        dt_s * math.fsum(cell_heat)
    ),

    "boundary_input_m3": dt_s * q[0],
    "lateral_input_m3": (
        dt_s * math.fsum(self._lateral_q)
    ),
    "outlet_export_m3": dt_s * q[-1],
}
```

Then retain the component diagnostics:

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

# 9. Update the step energy equation

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

The cell-level residual can continue using the combined `surface_power_w`:

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

# 10. Update `budget()`

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

Update `energy_scale`:

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

Add the diagnostic to the returned budget:

```python
"max_surface_linearization_error_w": (
    self.max_surface_linearization_error_w
),
```

---

# 11. Add explicit component diagnostics

Add these fields to `budget()` before the return:

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

Then include:

```python
"surface_component_sum_j": surface_component_sum_j,
"surface_component_difference_j": (
    surface_component_difference_j
),
```

These values should not be added to `expected_change_j`. They compare the nonlinear diagnostic decomposition with the linearized surface exchange used by the solver.

The interpretation is:

```text
heat_residual_j
    numerical closure of the solved discretized equation

surface_component_difference_j
    nonlinear diagnostic decomposition minus
    linearized surface exchange

max_surface_linearization_error_w
    maximum instantaneous per-cell flux difference
```

---

# 12. Fix `cell_heat_w` configuration support

In `river_from_config()`, add `"cell_heat_w"` to `allowed`:

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

Add it to `kwargs`:

```python
"cell_heat_w": config.get("cell_heat_w"),
```

The complete relevant section becomes:

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
}
```

---

# 13. Fix explicit-budget detection

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

This prevents:

```json
"surface_budget": null
```

from being reported as an active explicit budget.

---

# 14. Add replay metadata

Inside the `"model"` dictionary returned by `make_replay()`, add:

```python
"surface_accounting": {
    "conservation_surface_term": (
        "linearized_implicit_surface_flux"
        if explicit_budget
        else "newton_surface_flux"
    ),
    "additional_heat_flux_separate": True,
    "component_terms": (
        "nonlinear diagnostic components; not used for "
        "conservation closure"
        if explicit_budget
        else "not applicable"
    ),
    "linearization_error_metric": (
        "max_surface_linearization_error_w"
        if explicit_budget
        else None
    ),
},
```

Update the explicit-budget limitation:

```python
(
    "Explicit surface budget is linearized implicitly around the "
    "previous cell temperature. Budget closure applies to the "
    "linearized discretized equation; nonlinear-vs-linearized "
    "surface error is reported separately."
    if explicit_budget
    else
    "Surface exchange is a reduced Newton approximation."
),
```

---

# 15. Add regression tests

```python
def test_surface_budget_forcing_changes_split_run():
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
    assert river.time_s == pytest.approx(10.0)
```

```python
def test_explicit_surface_budget_closes():
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
    assert "max_surface_linearization_error_w" in budget
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
        10.0
        * 10.0
        * 2.0
        * 10.0
    )
    assert budget["heat_relative_residual"] < 1e-10
```

```python
def test_null_surface_budget_uses_newton_metadata():
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

    assert (
        document["model"]["surface_flux"]
        == "newton_lumped"
    )
```

```python
def test_cell_heat_w_round_trips_through_config():
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
        "cell_heat_w": {
            "c0": {
                "times_s": [0.0, 10.0],
                "values": [5.0, 10.0],
            }
        },
    }

    river = river_from_config(config)

    assert river._cell_heat[0] is not None
    assert river._cell_heat[0].at(0.0) == 5.0
```

---

# 16. Important interpretation

After this patch, the following are intentionally different:

```python
budget["heat_relative_residual"]
```

This measures conservation of the equation actually solved.

```python
budget["max_surface_linearization_error_w"]
```

This measures how far the nonlinear surface flux was from the first-order approximation used for the timestep.

```python
budget["surface_component_difference_j"]
```

This compares the nonlinear component diagnostic with the linearized net surface term.

Therefore, a small heat residual does **not** mean that the nonlinear surface physics is exact. It means the discrete linearized transport equation closes numerically.

For higher physical accuracy during large timesteps, the next enhancement would be a Picard/Newton iteration that repeatedly relinearizes the surface flux until the new temperature converges.