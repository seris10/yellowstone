Picard/Newton iteration is a way to solve the **nonlinear implicit surface-heat equation** more accurately within each timestep.

## Why it is needed

Your solver currently uses backward Euler, but the explicit surface budget depends nonlinearly on the unknown new water temperature:

\[
\frac{V(T^{n+1}-T^n)}{\Delta t}
=
\text{transport}
+
F(T^{n+1})
\]

where \(F(T)\) may include:

- longwave radiation;
- sensible heat;
- latent heat;
- humidity-dependent evaporation.

Because \(F\) depends on the unknown \(T^{n+1}\), the equation is nonlinear.

The current implementation approximates it once around the old temperature:

\[
F(T^{n+1})
\approx
F(T^n) + F'(T^n)(T^{n+1}-T^n)
\]

That is effectively a **single Newton linearization**. It is usually adequate for small timesteps, but can be inaccurate for large timesteps or strong heat fluxes.

---

# Picard iteration

Picard iteration repeatedly solves a linear problem while updating the surface flux from the latest temperature estimate.

Given an initial guess:

```text
T_guess = T_old
```

repeat:

1. Evaluate the nonlinear surface flux using `T_guess`.
2. Build a linear transport system using that flux.
3. Solve for a new temperature.
4. Compare the new temperature with the previous guess.
5. Stop when the difference is small.

Conceptually:

\[
T^{(k+1)}
=
\text{Solve}\left[
\text{transport}
+
F(T^{(k)})
\right]
\]

### Advantages

- Simpler to implement.
- Generally robust.
- Easier to debug.
- Does not require an accurate derivative of the flux.

### Disadvantages

- Converges relatively slowly.
- May require several iterations per timestep.
- Can oscillate unless under-relaxed.

---

# Newton iteration

Newton iteration uses both the nonlinear flux and its derivative:

\[
F(T)
\approx
F(T^{(k)})
+
F'(T^{(k)})(T-T^{(k)})
\]

It then solves the resulting linearized system.

Repeat:

1. Evaluate `flux_at(T_guess)`.
2. Evaluate the derivative `dF/dT`.
3. Build the tridiagonal system.
4. Solve for `T_new`.
5. Check convergence.

### Advantages

- Usually converges much faster.
- More accurate for strongly nonlinear fluxes.
- Fits naturally with your existing `linearized()` function.

### Disadvantages

- Requires a correct derivative.
- Can be less robust when the derivative is poorly behaved.
- Needs safeguards for nonphysical temperatures or failed convergence.

---

# In your code

Your existing code already has:

```python
flux0, slope = linearized(
    self._temperature_c[i],
    met,
    self.surface_budget.params,
)
```

That is a Newton-style linearization around the **old timestep temperature**.

A full Newton solve would instead linearize around the current iteration’s guess:

```python
flux0, slope = linearized(
    guess[i],
    met,
    self.surface_budget.params,
)
```

The important change is:

```python
self._temperature_c[i]
```

becomes:

```python
guess[i]
```

during iteration.

---

# Recommended implementation: damped Newton iteration

For your solver, I recommend a **damped Newton/Picard hybrid**:

- use the derivative from `linearized()`;
- iterate several times;
- under-relax the update;
- fall back or fail clearly if it does not converge.

Add configuration values:

```python
DEFAULT_MAX_SURFACE_ITERATIONS = 12
DEFAULT_SURFACE_TOLERANCE_C = 1e-7
DEFAULT_SURFACE_RELAXATION = 0.8
```

Add these constructor parameters:

```python
max_surface_iterations: int = DEFAULT_MAX_SURFACE_ITERATIONS,
surface_tolerance_c: float = DEFAULT_SURFACE_TOLERANCE_C,
surface_relaxation: float = DEFAULT_SURFACE_RELAXATION,
```

Validate them:

```python
if not isinstance(max_surface_iterations, int):
    raise ValueError("max_surface_iterations must be an integer")
if max_surface_iterations < 1:
    raise ValueError("max_surface_iterations must be positive")

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
        "surface_relaxation must be in (0, 1]"
    )
```

---

# Core algorithm

Add a method like this:

```python
def _solve_implicit_step(
    self,
    start_s: float,
    dt_s: float,
) -> tuple[list[float], int]:
    """Solve one timestep, iterating nonlinear surface fluxes."""

    # For Newton/lumped linear models, one solve is sufficient.
    if self.surface_budget is None:
        return (
            solve_tridiagonal(
                *self._system(start_s, dt_s)
            ),
            1,
        )

    old_temperature = list(self._temperature_c)
    guess = old_temperature.copy()

    for iteration in range(1, self.max_surface_iterations + 1):
        # The linearization must be evaluated around `guess`, not the old
        # timestep state.
        lower, diagonal, upper, rhs = (
            self._system(
                start_s,
                dt_s,
                linearization_temperature=guess,
            )
        )

        candidate = solve_tridiagonal(
            lower,
            diagonal,
            upper,
            rhs,
        )

        update = max(
            abs(new - previous)
            for new, previous in zip(candidate, guess)
        )

        if update <= self.surface_tolerance_c:
            return candidate, iteration

        relaxation = self.surface_relaxation

        guess = [
            previous + relaxation * (new - previous)
            for previous, new in zip(guess, candidate)
        ]

    raise ArithmeticError(
        "surface-budget nonlinear iteration did not converge "
        f"after {self.max_surface_iterations} iterations; "
        f"last temperature update was {update:.6g} C"
    )
```

This requires `_system()` to accept a linearization temperature.

---

# Modify `_system()`

Change the signature:

```python
def _system(
    self,
    time_s: float,
    dt_s: float | None = None,
    linearization_temperature: list[float] | None = None,
) -> tuple[list[float], list[float], list[float], list[float]]:
```

Select the temperature used for linearization:

```python
if linearization_temperature is None:
    linearization_temperature = self._temperature_c

if len(linearization_temperature) != len(self.cells):
    raise ValueError(
        "linearization_temperature must match the cell count"
    )
```

Then update `_surface_linearization()`:

```python
def _surface_linearization(
    self,
    cell_index: int,
    time_s: float,
    linearization_temperature: float | None = None,
) -> tuple[float, float, dict[str, float] | None]:
    cell = self.cells[cell_index]
    area = cell.surface_area_m2
    air = self.air_c.at(time_s)

    if self.surface_budget is None:
        exchange = (
            cell.exchange_w_m2_k
            * area
            / self.rho_cp
        )
        return exchange, exchange * air, None

    if linearization_temperature is None:
        linearization_temperature = self._temperature_c[cell_index]

    met = self.surface_budget.met_at(time_s, air)

    flux0, slope = linearized(
        linearization_temperature,
        met,
        self.surface_budget.params,
    )

    exchange = -slope * area / self.rho_cp

    rhs = (
        flux0 - slope * linearization_temperature
    ) * area / self.rho_cp

    return exchange, rhs, {
        "linearization_temperature_c": (
            float(linearization_temperature)
        ),
        "flux_at_linearization_temperature_w_m2": float(flux0),
        "flux_temperature_slope_w_m2_k": float(slope),
    }
```

Then inside `_system()`:

```python
linearization_temperature = (
    self._temperature_c
    if linearization_temperature is None
    else linearization_temperature
)

for i, cell in enumerate(self.cells):
    exchange, surface_rhs, _metadata = (
        self._surface_linearization(
            i,
            time_s,
            linearization_temperature[i],
        )
    )
```

---

# Use it in `_advance_to()`

Replace:

```python
new = solve_tridiagonal(
    *self._system(start_s, dt_s)
)
```

with:

```python
new, iteration_count = self._solve_implicit_step(
    start_s,
    dt_s,
)
```

Track the iteration count:

```python
self.max_surface_iterations_used = max(
    self.max_surface_iterations_used,
    iteration_count,
)
```

Initialize this in `__init__()`:

```python
self.max_surface_iterations_used = 0
```

Include it in the budget:

```python
"max_surface_iterations_used": (
    self.max_surface_iterations_used
),
```

---

# Accounting after convergence

After Newton converges, calculate the final physical surface flux using the converged temperature:

```python
met_now = self.surface_budget.met_at(
    start_s,
    self.air_c.at(start_s),
)

fluxes = [
    flux_at(
        temperature,
        met_now,
        self.surface_budget.params,
    )
    for temperature in new
]
```

Then use:

```python
base_surface_power_w = [
    cell.surface_area_m2 * parts["net"]
    for cell, parts in zip(self.cells, fluxes)
]
```

This is now appropriate because the state was iterated until it is consistent with the nonlinear flux.

The energy residual should then represent actual nonlinear implicit closure, subject mainly to solver tolerance and floating-point error.

---

# Picard versus Newton in practical terms

For your project:

| Method | Best use |
|---|---|
| One linearization | Small timesteps, quick baseline |
| Picard | Robust fallback, less trusted derivative |
| Newton | Production explicit-budget solver |
| Damped Newton | Recommended default |
| Full nonlinear solve | Large timesteps or strong evaporation/radiation |

A sensible policy is:

```python
if surface_budget is None:
    one linear solve

elif dt_s <= 10.0:
    one Newton linearization may be enough

else:
    damped Newton iteration
```

However, avoid silently changing algorithms based only on timestep. Record the method in the replay metadata.

---

# Recommended metadata

Add to the replay:

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
}
```

And distinguish:

```python
"heat_relative_residual": 
    "implicit nonlinear surface solve closure"
```

from:

```python
"surface_nonlinear_iteration_converged": True
```

---

# Important caveat

Do not use a nonlinear iterative solve to disguise an invalid surface-flux model. It improves consistency with the equations, but it does not calibrate:

- exchange coefficients;
- turbulent transfer coefficients;
- humidity corrections;
- radiation inputs;
- cloud effects;
- bathymetry;
- meteorological forcing.

It answers:

> “Did the numerical state converge to the specified nonlinear model?”

It does not answer:

> “Is the specified nonlinear model scientifically accurate for the Firehole?”

For your current code, I would implement **damped Newton iteration**, retain the one-pass linearized method as a diagnostic mode, and report both convergence and physical parameter provenance.