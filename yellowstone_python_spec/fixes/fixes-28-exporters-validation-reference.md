# fixes-28: exporters, validation gate, and the FiPy reference
Scope:
- yellowstone_python/yellowstone_python/exporters/to_ecosystem.py (89d3e60a6e66)
- yellowstone_python/yellowstone_python/exporters/to_map.py (b381cfd47da5)
- yellowstone_python/yellowstone_python/validation/checks.py (94317d0c285e)
- yellowstone_python/yellowstone_python/replay/fipy_reference.py (525e068d737b)
- yellowstone_python/yellowstone_python/replay/nc_export.py (64051106c4f0)

Callers read:
- yellowstone_python/yellowstone_python/build.py (lines 14, 196-227, 439-453, 602-610, 929-938)
- yellowstone_python/yellowstone_python/publish.py (lines 23, 71)
- yellowstone_python/yellowstone_python/hydro_thermal.py (run_simulation at 211)
- yellowstone_python/yellowstone_python/common/validate.py (check_reach_chain, check_heat_ledger, check_provenance)
- yellowstone_python/yellowstone_python/run_mode.py (RUN_MODES, check_split)
- yellowstone_python/yellowstone_python/replay/river_transport.py (steady_temperatures, _system)
- yellowstone_python/yellowstone_python/replay/tests/test_fipy_reference.py
- yellowstone_python/yellowstone_python/replay/tests/test_nc_export.py
- yellowstone_midway/scripts/ecosystem.gd (configure, _derive_flows, _update_weather, _advance_heat, _advance_patches)
- yellowstone_midway/scripts/python_river_replay.gd (configure, _apply_replay)
- yellowstone_midway/scripts/world.gd (patches reader, reach probe)
- yellowstone_midway/scripts/thermal_probe_overlay.gd (temperature_c reader)
- yellowstone_python/requirements.txt (optional-deps state)

## Main problems

### 1. The FiPy reference shares the production discretization and is not run by the suite
`replay/fipy_reference.py:70-115` builds the reference solve with
`UpwindConvectionTerm` plus `ImplicitSourceTerm`. The production river solver
in `replay/river_transport.py:718-776` builds the same first-order upwind
convection matrix: `lower[i] = -(q[i] + g[i])` for `i > 0` with the implicit
Newton exchange on the diagonal and the air term on the right-hand side.
Both solvers are first-order cell-centered finite volume with upwinded
advection and lumped Newton source. A sign or coefficient error in the
upwind operator would appear identically in both, so matching to within a
hair of the hand-rolled error (test at `tests/test_fipy_reference.py:42-46`,
`solve_steady(n)["max_abs_error_c"] <= hand_rolled_error_c(n) + 1e-9`)
proves agreement, not independence.

The convergence check in `tests/test_fipy_reference.py:48-52` accepts rates
in `[0.7, 1.3]`, 30 percent slack around the first-order target of 1.0 on a
smooth problem. The production centered-harmonic dispersion
(`replay/river_transport.py:484-492`, used in `_system` through `g`) is
switched off here: `DEPTH_M`, `WIDTH_M`, `H_W_M2_K` are hard-coded and
`Cell(..., dispersion_m2_s=0.0)` is implicit in `hand_rolled_error_c`
(`fipy_reference.py:122-126`). The dispersive term the production solver
exposes to replay runs is never exercised against FiPy.

The reference is also an orphan at runtime. `requirements.txt` does not list
`fipy`, both FiPy test classes are gated on `skipUnless(HAS_FIPY)`
(`tests/test_fipy_reference.py:32`), and `validation/checks.py:42-50`
calls `run_all_benchmarks`, not `run_convergence`. So the standard pytest
run advertised in `AGENTS.md` section 7 silently skips the entire
independent-reference claim on any machine that has not opted in.

### Fix
Make the reference actually independent, exercise dispersion, and wire it
into checks.

- Add a method-of-manufactured-solutions (MMS) harness alongside the
  FiPy case. Pick `T(x) = Tair + (T0 - Tair) * exp(-k * x) + A * sin(pi * x
  / L)` and derive the forcing `S(x)` that closes `Q * dT/dx + h_eff * (T -
  Tair) - D * d2T/dx2 = S(x)` by substitution; test with a hand-rolled
  solver that supports a per-cell internal heat source. Grid refinement
  then measures the true discretization error of `river_transport.py`
  against a solution that does not depend on its own operator. MMS as a
  code verification technique: Roache, P. J., *Verification and Validation
  in Computational Science and Engineering*, Hermosa, 1998, chapters 3-4.
- Add a FiPy case that enables dispersion by setting `coeff` on
  `DiffusionTerm` with `D` matched to a `dispersion_m2_s` on
  `Cell(...)`, so both solvers run the same transport operator the
  production replay carries. Keep the convection coefficient `face_velocity`.
- Rename the hard-coded parameter block as a `SYNTHETIC_*` module constant
  with a one-line docstring that states the case is not the Firehole, so
  readers do not confuse it with a reach-tuned test.
- Add `fipy` to `requirements.txt` under a `[reference]` extras group or
  mark the convergence rate band tightly (expected 1.0, slack 0.05 for a
  linear scheme on a smooth problem), and have
  `validation/checks.py:run_all` call `run_convergence` behind
  `metrics["reference_convergence_rate"]`. Fail the check when fipy is
  absent in `run_mode in ("hindcast", "observed_replay")`, and pass with a
  recorded `"reference_skipped": true` metric for `illustrative`.

### Test
`tests/replay/test_fipy_reference.py::ReferenceDispersionTests::test_dispersion_term_matches_production` and
`tests/replay/test_fipy_reference.py::ReferenceMMSTests::test_mms_convergence_rate_is_first_order` plus
`tests/test_build.py::ChecksMetricsTests::test_reference_convergence_logged`.
A failure on either case fails the build in hindcast and replay modes.

---

### 2. nc_export writes a file no pipeline consumes, declares CF-1.8 while violating CF time encoding, and tags river water with an ocean standard_name
`replay/nc_export.py:30-47` sets `Conventions = "CF-1.8"` and writes the
`time` coordinate with `{"units": "s", "standard_name": "time"}`. CF-1.11
section 4.4 ("Time Coordinate") requires the units string to be
`"<time unit> since <reference datetime>"` and recommends a `calendar`
attribute. Bare `"s"` is not a CF-conformant time unit. Any downstream CF
tool (xarray with `decode_times=True`, netCDF4 `num2date`, Panoply) will
either fail or treat the axis as "seconds since 1970-01-01" by convention,
which disagrees with the solver clock. CF Conventions v1.11, section 4.4:
https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#time-coordinate.

Line 35 sets `standard_name: "sea_water_temperature"` on a Firehole river
variable. That standard name is for ocean water (CF Standard Name Table
v83, entry `sea_water_temperature`). The correct choices for inland water
are `water_temperature` or no standard_name with a self-documenting
`long_name`.

Lines 10-47 are never called by `build.py` or `publish.py`. The only
caller is `tests/test_nc_export.py:14-31`, and the test asserts
bit-identical values but asserts nothing about the CF attributes or time
encoding. The NetCDF export is an orphan writer and the test is a
plumbing round-trip, not a conformance gate.

### Fix
Make the file CF conformant and wire it into the build when the user asks
for it.

```python
# Reference epoch is the resolved game clock start.
reference_dt = datetime.datetime.strptime(
    frames[0]["wall_time"], "%Y-%m-%dT%H:%M:%SZ"
) if "wall_time" in frames[0] else datetime.datetime(1970, 1, 1)
time_units = f"seconds since {reference_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"
data = xr.Dataset(
    {"water_temperature": (
        ("time", "cell"), temps,
        {"units": "degree_Celsius",
         "standard_name": "water_temperature",
         "long_name": "replay cell water temperature",
         "_FillValue": np.float64("nan")})},
    coords={
        "time": ("time", times, {
            "units": time_units,
            "standard_name": "time",
            "calendar": "standard",
            "axis": "T"}),
        "cell_id": ("cell", np.array(ids, dtype=object),
                    {"long_name": "replay cell identifier",
                     "cf_role": "timeseries_id"})})
```

Wire into `build.py` next to the JSON replay write:

```python
if cfg.get("replay", {}).get("netcdf", False):
    from .replay.nc_export import write_replay_netcdf
    write_replay_netcdf(replay_doc["frames"], [c["id"] for c in replay_doc["cells"]],
                        out / "replay.nc")
```

Validate at the gate (`validation/checks.py:run_all`): when
`cfg.replay.netcdf` is on, re-read `replay.nc` and assert
`cell_ids == [c["id"] for c in replay_doc["cells"]]` and
`times_s[0] == 0.0`. Make the write atomic (`out.with_suffix(".nc.tmp")`
then `os.replace`) to match `AGENTS.md` section 7 artifact rules.

Line 28 (`if temps.shape != (len(frames), len(ids))`) runs AFTER
`np.array(..., dtype=np.float64)`, which converts ragged input to an
object array and raises `ValueError` with an obscure message. Replace with
`if any(len(f["temperature_c"]) != len(ids) for f in frames)` before the
`np.array` call so the shape check reports the offending frame.

Standard-name authority: CF Standard Name Table v83,
https://cfconventions.org/Data/cf-standard-names/83/build/cf-standard-name-table.html.

### Test
`tests/replay/test_nc_export.py::CfComplianceTests::test_time_units_have_reference_epoch`,
`tests/replay/test_nc_export.py::CfComplianceTests::test_standard_name_is_water_temperature`, and
`tests/test_build.py::ArtifactsTests::test_netcdf_optional_write_round_trips` for the end-to-end wire-in.

---

### 3. validation/checks.py gates plumbing, not scientific claims
`validation/checks.py:9-73` composes `run_all` out of `check_reach_chain`
(topology), `check_heat_ledger` (floating-point closure at `1e-9`),
`check_provenance` (metadata-key presence), `check_split` (prescribed
vs validated non-overlap), `fish_activity in [0, 1]` (sanity bound),
`run_all_benchmarks` from `replay/benchmarks` (numerics), and the coupling
and cross-family passes from `coupling.py`. None of these touch an
observational claim. In particular:

- No RMSE threshold vs the observed USGS reach temperatures that the build
  already loads (`derived/firehole_obs.json`, see `README.md`).
- No comparison to the SNOTEL hold-out RMSEs stated in the README (609 and
  924 numbers for both windows), even though those artifacts are present
  under `derived/`.
- No convergence-rate check for the replay solver (the orphan
  `run_convergence` from fixes 1 above would be the natural call site).
- No tolerance on the exponential-decay fit for the illustrative
  `steady_profile` solver.

The checks module is accurately described by its own line 1 docstring
("conservation, topology, provenance, determinism gates") but the module
name and its position inside the build gate (`build.py:929-938`) frame it
as the scientific gate. It is not.

Additional problems inside the module as it stands:

- `checks.py:69-70` runs the determinism check only when the caller
  supplies `build_id_b`. `build.py:933-938` never passes it. The branch is
  dead in production; a non-deterministic build will not fail here.
- `checks.py:19-24` tests `run_mode not in RUN_MODES`, but
  `run_mode.normalize_run_mode` (used in `build.py:932`) already raises on
  `"forecast"` and on unknown modes. The branch is dead unless a caller
  passes a raw string. If that caller exists, the `elif run_mode ==
  "forecast"` is unreachable because the outer `if` already fired.
- `checks.py:51-53` only catches `ValueError` and `ArithmeticError` from
  `run_all_benchmarks`. Any `ImportError`, `AssertionError`, or `OSError`
  propagates. The partial-swallow pattern is inconsistent and either
  leaks or hides errors depending on which benchmark fails.
- `metrics["heat_budget_error"]` on `checks.py:38` reads
  `ledger.get("heat_budget_error")`. The `common/validate.check_heat_ledger`
  helper accepts either `"heat_budget_error"` or `"residual"`
  (`common/validate.py:36`). If a ledger carries only `"residual"`, the
  gate passes but the metric is `None`. The two helpers should agree on a
  single key.

### Fix
Split the gate into two files and wire the scientific one explicitly.

- Rename this module to `validation/plumbing.py` and keep the current
  contents under that honest name.
- Add `validation/claims.py` holding, at minimum:
  - `check_usgs_reach_temperatures(replay_doc, obs_path, max_rmse_c)`
    that reads `derived/firehole_obs.json`, finds the gauge-adjacent
    cell by chainage, and asserts RMSE below the claim threshold stated
    in the matching `claims.py` entry. Pass `max_rmse_c` from the
    `claim` registry, never from a config.
  - `check_snotel_holdout_rmses(fit_artifact, sites, thresholds)` that
    opens the frozen fit artifact and asserts the two reported holdout
    RMSEs are still better than the persistence and no-melt nulls, so a
    silent model regression trips the build. Both numbers are already
    recorded; this is a non-regression gate.
  - `check_replay_convergence_rate()` that calls the fixed
    `fipy_reference.run_convergence` and asserts rate near 1.0 (see
    fix 1).
- In `build.py:929`, call `plumbing.run_all(...)` and
  `claims.run_all(...)` in sequence; concatenate `failures`; carry two
  metric namespaces (`metrics["plumbing_*"]`, `metrics["claims_*"]`).
- Fix the dead branches: delete `checks.py:20-24`; drop `"heat_budget_error"`
  as a key and use `"residual"` across the ledger pipeline, including
  `hydro_thermal.step_heat:183` and `hydro_thermal.run_simulation:226-227`.
- Make determinism real: `build.py` either runs the build twice (expensive)
  or compares `build_id` against the last recorded `build_id` of an
  identical config hash. Record the second build id in `meta.sqlite` and
  pass it in to `plumbing.run_all`.
- Narrow the benchmark exception: `except Exception as exc:` is still
  broad, but it should at least include `ImportError, AssertionError,
  OSError` explicitly so a vanished benchmark module does not silently
  pass. Append the exception class name to the failure line for triage.

### Test
`tests/validation/test_claims.py::UsgsClaimTests::test_rmse_above_threshold_fails_build`,
`tests/validation/test_claims.py::SnotelHoldoutTests::test_regression_against_prior_fit_fails`,
`tests/validation/test_plumbing.py::DeterminismTests::test_non_deterministic_build_fails`,
`tests/validation/test_plumbing.py::LedgerKeyTests::test_residual_key_populates_metric`.

---

### 4. merge_fragments exports the baseline boundary flow, not the computed effective boundary
`exporters/to_ecosystem.py:16-33` copies the baseline deep and overwrites,
for each matched reach, only `temperature_c`, `volume_m3`, `cooling_seconds`,
and `lateral_sources`. Top-level `boundary_m3s` is never updated.

`build.py:439-453` computes `boundary_m3s = baseflow_m3s + runoff_m3_s`
and feeds that effective boundary into `run_simulation`. `_prepare_replay_ecosystem`
at `build.py:208` separately writes the effective boundary into `eco`
(the dict handed to the replay solver), but the `variant` dict written to
`ecosystem.variant.json` and `ecosystem.godot.json` at
`build.py:892,900` comes from `merge_fragments(baseline, river_state, ...)`
at `build.py:602`, which keeps `baseline["boundary_m3s"]`.

Downstream consumer: `yellowstone_midway/scripts/ecosystem.gd:108`
reads `float(params.get("boundary_m3s", 8.0))` and drives
`_derive_flows` from it, which sets `flow_m3s` on every reach, which is
then used by `_advance_heat:155-166` and by the Python-replay subclass
(`python_river_replay.gd` inherits `_derive_flows` through `super.configure`).
So any Godot session running a build with a nonzero snow runoff increment
uses the baseline flow, not the computed one. For replay-driven runs the
replay frames override `temperature_c` on probed reaches, but the derived
`flow_m3s` (and the budget it closes against) is wrong.

The same bug applies to `boundary_c` for a scenario that overrides
upstream temperature in `cfg.hydro.boundary_c`: `_prepare_replay_ecosystem`
patches `eco` but `merge_fragments` leaves `variant["boundary_c"]` on the
baseline.

### Fix
Propagate the effective boundary and overrides through the exporter:

```python
def merge_fragments(baseline: dict, river_state: list | None = None,
                    weather: dict | None = None,
                    clock_hour: float | None = None,
                    boundary_m3s: float | None = None,
                    boundary_c: float | None = None) -> dict:
    out = copy.deepcopy(baseline)
    if boundary_m3s is not None:
        out["boundary_m3s"] = float(boundary_m3s)
    if boundary_c is not None:
        out["boundary_c"] = float(boundary_c)
    # ... existing river_state/weather/clock_hour merges
    return out
```

Change `build.py:602-607` to pass the effective values:

```python
variant = merge_fragments(baseline, river_state,
                          {k: v for k, v in weather_frag.items()
                           if k in ("night_air_c", "day_warming_c",
                                    "wind_xz_mps", "gust_mps",
                                    "humidity", "cloud")},
                          clock_hour=hour0,
                          boundary_m3s=boundary_m3s,
                          boundary_c=hcfg.get("boundary_c",
                                              baseline["boundary_c"]))
```

Add a validation line to `validate_for_godot`:

```python
if replay_boundary is not None and abs(float(doc["boundary_m3s"])
                                       - replay_boundary) > 1e-9:
    errors.append(
        f"ecosystem boundary_m3s {doc['boundary_m3s']} disagrees with "
        f"solver boundary_m3s {replay_boundary}")
```

### Test
`tests/exporters/test_to_ecosystem.py::BoundaryPropagationTests::test_runoff_augmented_boundary_appears_in_variant`,
`tests/test_build.py::EcosystemConsistencyTests::test_ecosystem_boundary_matches_replay_doc_boundary`.

---

### 5. validate_for_godot is a smoke check that misses most invariants Godot assumes
`exporters/to_ecosystem.py:36-45` runs `check_reach_chain` and three
top-level assertions (`schema_version == 1`, non-empty patches, positive
`boundary_m3s`). It omits every per-reach and per-patch field the Godot
scripts actually read:

- `ecosystem.gd:60-74` reads `volume_m3` (already checked), `upstream_id`
  (unchecked beyond chain order), `id` (checked). It asserts chain shape
  that `check_reach_chain` already covers, so that part is fine.
- `ecosystem.gd:108-121` reads `lateral_sources` entries' `flow_m3s` and
  `temperature_c`. If any source lacks `flow_m3s`, Godot defaults to 0.0
  and silently drops it. The exporter does not check source shape.
- `ecosystem.gd:130` reads `cooling_seconds` and clamps to `maxf(1.0, ...)`.
  A zero or negative value is silently clamped. The exporter does not check.
- `ecosystem.gd:146-152` reads `weather.night_air_c`, `weather.day_warming_c`,
  `weather.wind_xz_mps` (expects a 2-array), `weather.gust_mps`. The
  exporter does not check `weather` exists or has those keys.
- `ecosystem.gd:165-187` reads `params.boundary_c` with default 17.5. The
  exporter does not check `boundary_c` is present or finite.
- `ecosystem.gd:200-229` reads per-patch `biomass`, `capacity`, `moisture`,
  `growth_per_hour`, `insect_resource`, `insect_recovery_per_hour`. The
  exporter checks only that `patches` is non-empty; patches lacking any
  of these fields fall through Godot's defaults silently.
- `ecosystem.gd:149-152` reads `humidity` and `cloud` at the top level
  (`params.get("humidity", 0.45)` through `clampf`). `merge_fragments:28-30`
  writes humidity/cloud both inside `weather` and at the top level. The
  weather-dict copies are ghost writes (never read), but worse, there is
  no exporter check that the top-level values exist. Default fallbacks
  can hide a weather fragment that failed to load.

The dict passed by `merge_fragments:17-25` keys off `r["id"]` without
guarding `KeyError`. If any baseline reach has no `id`, the exporter
raises instead of reporting a validation error.

### Fix
Tighten the exporter contract.

```python
REQUIRED_PATCH_KEYS = ("id", "biomass", "capacity", "moisture",
                       "growth_per_hour", "insect_resource",
                       "insect_recovery_per_hour")
REQUIRED_WEATHER_KEYS = ("night_air_c", "day_warming_c", "wind_xz_mps",
                         "gust_mps")
REQUIRED_SOURCE_KEYS = ("flow_m3s", "temperature_c")


def validate_for_godot(doc: dict) -> list[str]:
    from ..common.validate import check_reach_chain
    errors = check_reach_chain(doc.get("river_reaches", []))
    if doc.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    for reach in doc.get("river_reaches", []):
        if float(reach.get("cooling_seconds", 0.0)) <= 0.0:
            errors.append(f"reach {reach.get('id')!r}: cooling_seconds must be > 0")
        for source in reach.get("lateral_sources", []):
            for key in REQUIRED_SOURCE_KEYS:
                if key not in source:
                    errors.append(
                        f"reach {reach.get('id')!r}: lateral source missing {key!r}")
    for patch in doc.get("patches", []):
        for key in REQUIRED_PATCH_KEYS:
            if key not in patch:
                errors.append(f"patch {patch.get('id')!r}: missing {key!r}")
    weather = doc.get("weather", {})
    for key in REQUIRED_WEATHER_KEYS:
        if key not in weather:
            errors.append(f"weather missing {key!r}")
    wind = weather.get("wind_xz_mps", [])
    if not (isinstance(wind, list) and len(wind) == 2):
        errors.append("weather.wind_xz_mps must be a 2-array")
    for key in ("humidity", "cloud", "boundary_c"):
        if key not in doc:
            errors.append(f"missing top-level {key!r}")
    if float(doc.get("boundary_m3s", 0)) <= 0:
        errors.append("boundary_m3s must be > 0")
    if not doc.get("patches"):
        errors.append("patches must be non-empty")
    return errors
```

Also harden the merge: skip reaches with no `id` and record them.

```python
if "id" not in r:
    continue
```

Remove the ghost humidity/cloud write at `to_ecosystem.py:28-30`: the
weather dict already receives them through the spread on line 27, and
the top-level write is the authoritative one.

### Test
`tests/exporters/test_to_ecosystem.py::ValidateForGodotTests::test_missing_patch_fields_fail`,
`::test_missing_weather_keys_fail`,
`::test_zero_cooling_seconds_fails`,
`::test_source_without_flow_m3s_fails`,
`::test_missing_boundary_c_fails`.

---

### 6. to_map.py is a stub that silently copies files instead of reprojecting
`exporters/to_map.py:1-9` claims to "reproject field PNGs into the
midway_macro frame" (line 1), then performs `shutil.copyfile` with the
one-line docstring "Fields are already authored in macro extent; plain copy"
(line 6). No caller exists in the repository: `rg "reproject_to_macro"
yellowstone_python/` returns only the definition. The module is dead code
whose docstring misrepresents its behavior.

If a future caller passes a field PNG that is NOT already in the macro
extent, the function silently copies pixels across frames. There is no
check on image size, no projection metadata read, no sidecar comparison.

### Fix
Either remove the module and the empty `exporters/` folder entry it
contributes to, or make it a real check:

```python
def reproject_to_macro(field_png: str, out_png: str,
                       expected_size_px: tuple[int, int]) -> str:
    """Copy a field that is already in the macro frame; verify size matches."""
    from PIL import Image
    import shutil
    with Image.open(field_png) as src:
        if src.size != expected_size_px:
            raise ValueError(
                f"{field_png} is {src.size}; macro frame is {expected_size_px}")
    shutil.copyfile(field_png, out_png)
    return out_png
```

The repository's active practice is to delete dead modules once their
replacement is live. The field-PNG workflow does not exist (no caller
references `exporters/to_map.py` anywhere in `yellowstone_python/` or
`yellowstone_midway/`). Delete `exporters/to_map.py` and leave a one-line
note in `stubs/README.md` that reprojection is not needed because fields
are authored in the macro frame.

### Test
On removal, no test is needed; the audit tool `tools/audit_provenance.py`
should ignore the deletion. If the module stays, add
`tests/exporters/test_to_map.py::SizeMismatchTests::test_wrong_size_raises`.

---

### 7. Comment block in checks.py breaks the AGENTS.md section 2 rules in several ways
`validation/checks.py:29-33` (quoted intact):

```
# Downstream monotone temperature is NOT required (hot lateral warms mid-chain);
# instead assert no NaN and fish_activity in [0,1]. Monotone STAGE (water surface
# never climbs downstream) is a baked-geometry invariant and lives where the
# geometry lives: yellowstone_midway/tools/validate_world.py (Firehole
# northward-order + climb check). Do not re-add a temperature version here.
```

Rules violated: ALL-CAPS emphasis (`NOT`, `STAGE`), "X, not Y" contrast
(`NOT required ... instead assert`), hypothetical-failure narrative
(`never climbs`), addressing the reader (`Do not re-add`), multi-line
inline comment, temporal reference (`re-add` implies prior state).

### Fix
Replace with the state the code implements, in one or two lines, under
the function docstring instead of as an inline block, and move the
cross-reference to a line comment on the first assertion:

```python
# Positivity constraints: fish_activity in [0, 1]; no NaN.
# Monotone stage is a geometry invariant; see
# yellowstone_midway/tools/validate_world.py.
```

### Test
No test; the lint pass in `tools/audit_comment_style.py` (not yet
written; see fixes-24 open items) should flag the current form and pass
the replacement.

---

# Wiring and rendering

- `exporters/to_ecosystem.merge_fragments` is called by `build.py:602` and
  produces the `variant` dict written to `derived/<build>/ecosystem.variant.json`
  (`build.py:892`) and `derived/<build>/ecosystem.godot.json` (`build.py:900`).
  `publish.py:23,71` imports `validate_for_godot` and runs it on the
  staged `ecosystem.json` immediately before transactional publish into
  `../yellowstone_midway/data/ecosystem.json`.
- `exporters/to_map.reproject_to_macro` has no callers. The sibling comment
  in `stubs/README.md` claims `exporters/validation/ (M11) all wired into
  build.py`, which is only partly true: `to_ecosystem` is wired,
  `to_map` is not.
- `validation/checks.run_all` is called by `build.py:933-942`. Its result
  dict feeds `BUILD.json` and gates the publish. The determinism branch
  (`checks.py:69-70`) is never exercised because `build.py` passes no
  `build_id_b`.
- `replay/fipy_reference` is called ONLY from
  `replay/tests/test_fipy_reference.py`. `validation/checks.run_all`
  does not reach it. `requirements.txt` does not list `fipy`, so the
  tests silently skip on the base interpreter.
- `replay/nc_export.write_replay_netcdf` has no non-test caller. The
  build pipeline writes the replay as JSON only (`derived/<build>/replay.json`
  via `replay/run_replay_solver`). `requirements.txt` lists neither
  `xarray` nor `netCDF4`.
- Godot renders `ecosystem.gd:107-194` from `variant`:
  `boundary_m3s`, `boundary_c`, `river_reaches[*].id`, `upstream_id`,
  `volume_m3`, `cooling_seconds`, `lateral_sources[*].{flow_m3s,temperature_c}`,
  `patches[*].{biomass,capacity,moisture,growth_per_hour,insect_resource,
  insect_recovery_per_hour}`, top-level `humidity`, `cloud`, `clock_hour`,
  `weather.{night_air_c,day_warming_c,wind_xz_mps,gust_mps}`.
  `thermal_probe_overlay.gd:66` reads reach `temperature_c` for the
  probe markers. `python_river_replay.gd:195-217` reads the replay JSON
  fields (`t_s`, `temperature_c`, `clock_hour0`, `weather_trace`,
  `humidity`, `cloud`, `legacy_queries`, `cells`, `frames`,
  `river_features`, `input_files.world.sha256`, `schema`,
  `numerical_checks.passed`). The NetCDF file is unread.

# Comment-style violations

| file:line | text | rule |
| --- | --- | --- |
| yellowstone_python/validation/checks.py:29 | `# Downstream monotone temperature is NOT required (hot lateral warms mid-chain);` | ALL-CAPS (`NOT`); X-not-Y contrast with the following line |
| yellowstone_python/validation/checks.py:30 | `# instead assert no NaN and fish_activity in [0,1]. Monotone STAGE (water surface` | X-not-Y contrast (`instead assert`); ALL-CAPS (`STAGE`); multi-line inline |
| yellowstone_python/validation/checks.py:31 | `# never climbs downstream) is a baked-geometry invariant and lives where the` | hypothetical-failure narrative (`never climbs`) |
| yellowstone_python/validation/checks.py:32 | `# geometry lives: yellowstone_midway/tools/validate_world.py (Firehole` | multi-line inline (continues 29-33) |
| yellowstone_python/validation/checks.py:33 | `# northward-order + climb check). Do not re-add a temperature version here.` | addresses the reader (`Do not re-add`); temporal reference (`re-add` implies prior state) |
| yellowstone_python/exporters/to_ecosystem.py:11 | `"""Return a new ecosystem dict; baseline never mutated.` | hypothetical-failure narrative (`never mutated`) |
| yellowstone_python/replay/nc_export.py:30 | `# Float64 storage preserves replay values bit-identically.` | NOT VERIFIED as a violation; descriptive and allowed, included here for completeness because "preserves X bit-identically" borders on hypothetical-failure framing |

# Priority order

1. Finding 1 (FiPy reference not independent and not run) - refactor.
2. Finding 2 (nc_export orphan and CF non-conformant) - medium.
3. Finding 3 (checks.py gates plumbing only; dead branches) - refactor.
4. Finding 4 (boundary not propagated through merge_fragments) - cheap.
5. Finding 5 (validate_for_godot too shallow) - cheap.
6. Finding 6 (to_map stub, dead code) - cheap.
7. Finding 7 (comment-style violations in checks.py:29-33) - cheap.

{"doc":"fixes-28","files":["yellowstone_python/yellowstone_python/exporters/to_ecosystem.py","yellowstone_python/yellowstone_python/exporters/to_map.py","yellowstone_python/yellowstone_python/validation/checks.py","yellowstone_python/yellowstone_python/replay/fipy_reference.py","yellowstone_python/yellowstone_python/replay/nc_export.py"],"findings":7,"severe":3,"wiring_gaps":["nc_export has no caller outside its own test","to_map stub has no caller anywhere","fipy_reference is not called by validation.checks and fipy is absent from requirements.txt","merge_fragments does not propagate the effective boundary_m3s or boundary_c overrides into the exported ecosystem.json"],"science_flags":["FiPy reference shares the production first-order upwind discretization, so it is not an independent reference","checks.run_all gates topology, conservation closure, and provenance; it gates no observational claim (USGS reach temps, SNOTEL holdout RMSEs)","nc_export declares CF-1.8 while writing time with no reference epoch and tagging river water with sea_water_temperature","build.py never passes build_id_b, so the determinism branch in checks.py:69-70 is inert in production"]}
