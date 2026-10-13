## Executive assessment

This is a substantial build orchestrator with good provenance intent, but it is currently **not a fully reproducible or scientifically coherent build boundary**.

The most important problems are:

1. **The terrain guard is not actually invoked.**
2. **External forcing files are not included in the build identity or dependency manifest.**
3. **The replay does not receive a full simulation timestamp.**
4. **Weather bundle integration is likely broken or stale relative to the newer microclimate API.**
5. **Overland flow is computed but not wired into river forcing.**
6. **Two different river models are run, but their relationship is not clearly controlled.**
7. **Validation is broad but shallow and sometimes casts invalid values before checking them.**
8. **The build writes scientifically meaningful outputs whose metadata can overstate their validity.**

I would classify the current build as:

```text
good integration prototype
not yet a trustworthy reproducible scientific build
```

---

# Critical findings

## 1. `check_terrain.py` is not integrated

`load_inputs()` directly does:

```python
deps = {
    ...
    "terrain.f32": sha256_file(world_root / "data" / "terrain.f32"),
    ...
}
```

and:

```python
tfns = terrain_fns(
    load_terrain(str(world_root / "data" / "terrain.f32"))
)
```

It does not call `check_terrain.guard_terrain()`.

Therefore the build trusts terrain based on:

- file existence;
- SHA-256 calculation;
- whatever `load_terrain()` accepts.

It does **not** enforce:

- exact dimensions;
- finite values;
- range;
- spatial plausibility;
- terrain guard status.

### Fix

Add a build-time guard:

```python
from ..tools.check_terrain import (
    DEFAULT_MAX_M,
    DEFAULT_MIN_M,
    guard_terrain,
)
```

Prefer moving the guard into a package module rather than importing from `tools`.

In `load_inputs()`:

```python
terrain_path = world_root / "data" / "terrain.f32"

terrain_report = guard_terrain(
    terrain_path,
    expect_sha256=None,
    min_m=DEFAULT_MIN_M,
    max_m=DEFAULT_MAX_M,
)

if not terrain_report["passed"]:
    failures = [
        guard["detail"]
        for guard in terrain_report["guards"]
        if not guard["passed"]
    ]
    raise ValueError(
        "terrain guard failed: " + "; ".join(failures)
    )
```

Return or store the report:

```python
deps["terrain_guard"] = terrain_report
```

For visual-only mode, permit warnings, but make the mode explicit.

---

## 2. Build identity excludes important external inputs

The build ID depends on:

```python
deps = {
    ...
    "config": sha256_json(cfg),
}
```

But many files used by the build are not hashed into `deps`:

- `replay.cross_sections_file`;
- `derived/met.json`;
- custom tributary data;
- weather snapshots;
- external observation bundles;
- potentially `requirements.txt`;
- terrain guard configuration;
- world-root YAML/config dependencies.

This creates a serious reproducibility bug:

```text
same config + changed met.json
    → same build_id
    → different build output
```

### Fix

Create a path-aware input registry:

```python
def hash_optional_file(path: Path) -> dict:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "sha256": None,
        }

    return {
        "path": str(path),
        "exists": True,
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }
```

Then collect:

```python
external_inputs = {
    "terrain": hash_optional_file(world_root / "data" / "terrain.f32"),
    "cross_sections": hash_optional_file(cross_sections_path),
    "met_bundle": hash_optional_file(PKG_ROOT / "derived" / "met.json"),
    "requirements": hash_optional_file(PKG_ROOT / "requirements.txt"),
}
```

Include them in the build hash:

```python
deps["external_inputs"] = external_inputs
deps["external_inputs_sha256"] = sha256_json(
    external_inputs
)
```

The build ID must include the content hash, not merely the configured path.

---

## 3. Cross-section files are not included in provenance or validated fully

`validate_config()` checks only:

```python
if "cross_sections_file" in rcfg and not isinstance(...):
```

Then `run_replay_solver()` loads it:

```python
cs_path = Path(rcfg["cross_sections_file"])
if not cs_path.is_absolute():
    cs_path = PKG_ROOT / cs_path
cross_sections = json.loads(cs_path.read_text())
```

Problems:

- missing file gives a raw `FileNotFoundError`;
- malformed JSON is not diagnosed clearly;
- relative paths are resolved relative to `PKG_ROOT`, not necessarily the config file or world root;
- content is not included in the build identity;
- no schema validation occurs here;
- the resulting profiles are not written into the manifest as an input artifact.

### Fix

Resolve paths consistently:

```python
def resolve_project_path(
    value: str,
    *,
    config_path: Path | None = None,
    world_root: Path | None = None,
) -> Path:
    path = Path(value)

    if path.is_absolute():
        return path

    candidates = []

    if config_path is not None:
        candidates.append(config_path.parent / path)

    if world_root is not None:
        candidates.append(world_root / path)

    candidates.append(PKG_ROOT / path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        f"could not resolve configured path {value!r}; "
        f"tried {candidates}"
    )
```

Then validate the cross-section schema before passing it to `build_mapped_replay()`.

---

## 4. Replay has no full simulation timestamp

`simulate_all()` obtains:

```python
clock_info = resolve_game_clock(...)
hour0 = clock_info["clock_hour"]
```

but `run_replay_solver()` receives only:

```python
hour0=hour0
```

The replay therefore knows a clock hour, but not:

- calendar date;
- UTC timestamp;
- timezone;
- leap-year context;
- exact end timestamp;
- relationship to weather snapshots;
- relationship to the Godot sky.

This directly conflicts with the timestamp-driven atmosphere and replay architecture discussed earlier.

### Fix

Add a canonical simulation timestamp to configuration:

```yaml
simulation_start_utc: "2026-07-15T22:20:00Z"
```

Validate and pass it:

```python
simulation_start_utc = cfg.get("simulation_start_utc")
if simulation_start_utc is None:
    raise ValueError(
        "simulation_start_utc is required for reproducible replay builds"
    )
```

Then:

```python
doc = build_mapped_replay(
    ...,
    simulation_start_utc=simulation_start_utc,
)
```

Use the same timestamp for:

- `resolve_game_clock`;
- `river_world.py`;
- weather bundle selection;
- solar angles;
- Godot atmosphere;
- star field;
- hydrology;
- snow forcing.

The build should fail or visibly downgrade to a non-reproducible mode when only `clock_hour` is supplied.

---

# Weather integration problems

## 5. The weather bundle path is hard-coded and probably incomplete

Current code:

```python
met_path = PKG_ROOT / "derived" / "met.json"
met_bundle = load_weather_bundle(str(met_path))
```

Problems:

- `fetch_firehole_obs.py` writes `firehole_obs.json`, not necessarily `met.json`;
- there is no configuration key for the weather bundle;
- a stale `derived/met.json` may silently override config;
- its hash is not in the build ID;
- there is no validation that its time window covers the replay;
- there is no timestamp-based row selection.

### Fix

Configuration should control the source:

```yaml
weather:
  met_bundle: derived/met.json
  mode: frozen_bundle
```

Then:

```python
met_path = resolve_project_path(
    wcfg["met_bundle"],
    world_root=world_root,
)
```

Validate:

```python
if not met_path.is_file():
    raise FileNotFoundError(...)
```

Record:

```python
weather_provenance = {
    "path": str(met_path),
    "sha256": sha256_file(met_path),
    "role": "forcing",
    "status": "remote_model_forcing_not_observation",
}
```

---

## 6. The bundle API is likely stale relative to `microclimate.py`

The build imports:

```python
from .microclimate import load_weather_bundle, bundle_weather
```

But the supplied `microclimate.py` defined `load_real_weather()` twice and did not define `load_weather_bundle()`.

If the current file has not since been changed, this is a runtime import failure.

Even if the loader exists in a newer branch, this call is problematic:

```python
bundle_weather(met_bundle, hour=hour0)
```

The improved weather design should select by an actual timestamp, not only a local hour. A multi-day bundle cannot reliably be indexed by hour alone.

### Fix

Use:

```python
bundle_weather(
    met_bundle,
    timestamp_utc=simulation_start,
)
```

or generate a complete time series for the replay window.

Do not collapse a multi-day forcing bundle to one weather snapshot for a multi-hour replay unless that is explicitly the intended approximation.

---

## 7. Open-Meteo is mislabeled as “measured”

Current code:

```python
weather_provenance = (
    "open-meteo hourly bundle "
    "(measured_remote_not_calibrated)"
    if met_bundle
    else ...
)
```

Open-Meteo data may be analysis, reanalysis, or forecast/model output, but it is not a local measurement.

Use:

```python
weather_provenance = {
    "source": "Open-Meteo",
    "role": "meteorological_model_forcing",
    "observation": False,
    "calibration_status": "not_calibrated_locally",
}
```

This matters because the build manifest is where downstream users may decide whether a claim is observationally supported.

---

## 8. Weather semantics are internally inconsistent

The build computes:

```python
air0 = air_temp(...)
```

and also uses:

```python
weather_frag = {**wcfg, ...}
```

If `bundle_weather()` returns measured absolute air temperature encoded as:

```python
night_air_c = measured_value
day_warming_c = 0.0
```

then `air_temp()` happens to return that value, but the field semantics are misleading.

More importantly, the replay’s `physical_weather()` independently reconstructs air temperature using:

```python
night_air_c
day_warming_c
```

while the weather bundle may represent absolute hourly forcing.

The build should choose one mode:

```text
synthetic_diurnal
absolute_scheduled
```

and pass it explicitly to the replay.

---

# Major model-wiring problem

## 9. Overland flow is computed but does not affect the river

`simulate_all()` calculates:

```python
overland_field = run_overland(...)
```

but boundary discharge was already determined earlier:

```python
boundary_m3s = baseflow_m3s + runoff_m3_s
```

where `runoff_m3_s` comes from:

```python
snow_season.catchment_runoff_m3_s(...)
```

The overland result is never used to modify:

- upstream boundary flow;
- lateral source flow;
- river temperature;
- catchment runoff artifact;
- landscape wetness.

So the build contains a hydrology product that is not causally connected to the river or terrain.

### Fix options

### Option A: keep it diagnostic

Explicitly say:

```python
"overland_flow_role": "diagnostic_not_wired_to_river"
```

and ensure it cannot be mistaken for active forcing.

### Option B: wire it properly

The sequence should be:

```text
rainfall time series
    ↓
overland hydrosim
    ↓
outlet discharge series
    ↓
routing/lag
    ↓
river boundary or lateral source
```

This requires:

- time-varying rainfall;
- open outlet configuration;
- outflow recording each step;
- outlet-to-river mapping;
- runoff temperature;
- scheduled discharge support in `river_transport.py`.

Do not add the overland outflow directly to `boundary_m3s` as a single scalar.

---

## 10. Snow runoff is wired as a scalar boundary increment

Current code:

```python
runoff_m3_s = float(runoff["runoff_m3_s"])
boundary_m3s = baseflow_m3s + runoff_m3_s
```

This may be acceptable for a simple illustrative scenario, but it is not time-resolved and does not connect to the replay’s timestamped forcing.

Add metadata:

```python
catchment["boundary_application"] = {
    "mode": "constant_scalar_increment",
    "scientific_status": "illustrative",
    "not_a_hydrograph": True,
}
```

Better: produce a discharge `Series` and pass it to a transport solver that supports dynamic flow.

---

# Duplicate river models

## 11. The build runs two separate river models

First:

```python
river_state, hydro_ledger = run_simulation(
    reaches_in,
    boundary_m3s,
    ...
)
```

Then:

```python
replay_doc = run_replay_solver(...)
```

These are distinct models:

- `hydro_thermal.run_simulation()` appears to be the legacy/lumped reach chain;
- `river_world.py` uses the finite-volume replay solver.

Yet both are used in the same build:

- `river_state` feeds legacy fish/wildlife and rendering;
- `replay_doc` feeds the aquatic food web;
- `bridge` temperature comes from `river_state`;
- thermal landscape comes from `replay_doc`.

This can produce internally inconsistent outputs where:

```text
fish legacy behavior uses one temperature model
foodweb uses another
rendered river uses another
```

### Fix

Declare authorities explicitly:

```python
model_authority = {
    "legacy_river_state": "display_compatibility_only",
    "replay_doc": "thermal_transport_authority",
    "foodweb": "replay_doc",
}
```

Preferably migrate consumers to the replay model and retain `run_simulation()` only for backward-compatible artifacts.

At minimum, compare the two models:

```python
{
    "legacy_vs_replay": {
        "max_temperature_difference_c": ...,
        "mean_temperature_difference_c": ...,
        "status": "diagnostic_not_validation"
    }
}
```

Do not let downstream modules silently mix them.

---

# Validation weaknesses

## 12. Many numeric values are cast before being properly validated

Examples:

```python
h = float(cfg.get("clock_hour", 16.2))
```

```python
if int(snow.get("days", 30)) < 0
```

```python
if float(olfg.get("rain_mm_h", 0.0)) < 0
```

Problems:

- `True` becomes `1.0`;
- `3.7` becomes `3` for `days`;
- strings may produce raw exceptions;
- NaN comparisons can pass;
- infinities are not consistently rejected.

Use shared validators:

```python
def _finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc

    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")

    return result
```

Then use `_finite_number()` everywhere before range checks.

For integers:

```python
def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")

    if value < 0:
        raise ValueError(f"{name} must be >= 0")

    return value
```

---

## 13. `validate_config()` mutates the loaded configuration

Current code:

```python
cfg["run_mode"] = normalize_run_mode(cfg.get("run_mode"))
cfg.setdefault("world_root", str(default_world_root()))
```

Mutation is not inherently wrong, but it creates ambiguity:

- configuration hash is calculated after mutation;
- caller may assume the original config remains unchanged;
- environment variable overrides occur later in `main()`;
- the same config may validate differently depending on call order.

Prefer:

```python
def normalized_config(cfg: dict) -> dict:
    result = copy.deepcopy(cfg)
    result["run_mode"] = normalize_run_mode(
        result.get("run_mode")
    )
    result.setdefault(
        "world_root",
        str(default_world_root()),
    )
    return result
```

Then:

```python
cfg = normalized_config(load_config(...))
validate_config(cfg)
```

Make the normalized config the canonical input to hashing and simulation.

---

## 14. Missing required input files are not diagnosed early

`load_inputs()` directly reads:

```python
ecosystem.json
world.json
placements.json
species_catalogue.json
terrain.f32
```

If one is missing, the build gets a raw error.

Add:

```python
required = [
    world_root / "data" / "ecosystem.json",
    world_root / "data" / "world.json",
    world_root / "data" / "placements.json",
    world_root / "data" / "species_catalogue.json",
    world_root / "data" / "terrain.f32",
]

missing = [str(path) for path in required if not path.is_file()]

if missing:
    raise FileNotFoundError(
        "missing world inputs: " + ", ".join(missing)
    )
```

---

## 15. `cross_sections_file` content is not validated against world features

`build_mapped_replay()` eventually validates feature names, but the build does not report:

- missing features;
- ignored profiles;
- depth range;
- source status;
- applicability to each feature.

Add a configuration-level report to the replay artifact.

---

# Reproducibility problems

## 16. `load_inputs()` uses `.pre-python` silently

```python
frozen = eco_path.with_suffix(".json.pre-python")
if frozen.exists():
    eco_path = frozen
```

This is potentially surprising. A file named:

```text
ecosystem.json
```

exists, but the build silently uses:

```text
ecosystem.json.pre-python
```

The manifest labels the dependency as:

```python
"ecosystem.json"
```

even though the actual file is different.

### Fix

Record the actual file:

```python
deps["ecosystem"] = {
    "path": str(eco_path),
    "sha256": sha256_file(eco_path),
    "role": (
        "frozen_pre_python_baseline"
        if eco_path.suffix == ".pre-python"
        else "active_baseline"
    ),
}
```

Better, make the selection explicit in configuration:

```yaml
baseline_file: data/ecosystem.json.pre-python
```

---

## 17. Code hash excludes important executable code

The code hash includes:

```python
for py in sorted((PKG_ROOT / "yellowstone_python").rglob("*.py")):
```

But not:

- `tools/*.py`;
- external hydrosim code;
- Godot scripts;
- shaders;
- configuration files except the main config;
- cross-section files;
- fetched weather artifacts.

If the build depends on those, the manifest should include their hashes.

At minimum:

```python
"tools": hash_tree(PKG_ROOT / "tools"),
"godot_scripts": hash_tree(world_root / "scripts"),
"shaders": hash_tree(world_root / "shaders"),
```

Only include relevant inputs, but make the dependency boundary explicit.

---

## 18. `BUILD.json` is written non-atomically and without strict JSON

Current code:

```python
(out / "BUILD.json").write_text(
    json.dumps(build_manifest(...), indent=2)
)
```

Use:

```python
_atomic_json_write(
    out / "BUILD.json",
    build_manifest(...),
)
```

and ensure:

```python
json.dumps(..., allow_nan=False)
```

The same applies to all output writers.

---

# Output and validation issues

## 19. The build does not validate the replay document against its own coupling contract

`run_all()` receives:

```python
replay_doc=res["replay_doc"]
```

but the build does not clearly call:

```python
check_coupling(...)
```

The coupling artifact is written later:

```python
write_sidecar(out / "coupling.json", ...)
```

That is just the contract declaration, not necessarily a coupling check.

Add:

```python
from .coupling import check_coupling

coupling_result = check_coupling(
    res["replay_doc"],
    thermal_landscape(res["replay_doc"]),
)
```

Then fail the build if:

```python
not coupling_result["passed"]
```

and write the actual result:

```python
write_sidecar(
    out / "coupling_check.json",
    coupling_result,
    ...
)
```

Do not confuse:

```text
coupling contract metadata
```

with:

```text
coupling validation result
```

---

## 20. Registry validation is not performed

The build writes:

```python
claims.json
param_registry.json
equations.json
```

but does not visibly run:

- `registry_errors()`;
- `validate_inventory()`;
- `validate_contract()`.

Add pre-gate validation:

```python
from .claims import registry_errors
from .coupling import validate_contract
from .equations import validate_inventory
from .param_registry import registry_errors as parameter_registry_errors

registry_failures = (
    registry_errors()
    + validate_contract()
    + validate_inventory()
    + parameter_registry_errors()
)
```

Then include them in `CHECKS.json`.

---

## 21. Replay numerical checks are duplicated and can drift

The replay has:

```python
"numerical_checks": {
    "passed": ...,
    "heat_relative_tolerance": 1e-9,
    "water_relative_tolerance": 1e-12,
}
```

But `build.py` separately assumes:

```python
if not res["replay_doc"].get("numerical_checks", {}).get("passed", False):
```

and the manifest separately records hardcoded values:

```python
"replay_heat_relative": 1e-9,
"replay_water_relative": 1e-12,
```

Centralize tolerances:

```python
REPLAY_HEAT_RELATIVE_TOLERANCE = 1e-9
REPLAY_WATER_RELATIVE_TOLERANCE = 1e-12
```

Pass them to the solver/checker and serialize the actual values used.

With damped Newton, also check:

```python
surface_iteration_failures == 0
```

and report:

```python
max_surface_iterations_used
max_surface_linearization_error_w
```

---

## 22. `build_manifest()` does not include overland configuration or weather

The manifest’s `parameter_set` includes:

```python
hydro
replay
fish
snow
foodweb
```

but omits:

- `weather`;
- `overland`;
- vegetation;
- insects;
- wind seed;
- terrain guard configuration;
- met bundle hash;
- catchment configuration;
- surface-budget/Newton settings.

This means the manifest does not fully describe the build.

Add:

```python
"weather": cfg.get("weather", {}),
"overland": cfg.get("overland", {}),
"vegetation": cfg.get("vegetation", {}),
"insects": cfg.get("insects", {}),
"wind_seed": cfg.get("wind_seed", 11),
```

and include the effective resolved weather, not only the authored config.

---

# Important semantic issues

## 23. Snow output is used before the updated snow state

The sequence is:

```python
patches1, snow_ledger = run_season(...)
...
runoff = catchment_runoff_m3_s(
    patches1,
    snow_ledger,
    ...
)
```

That is probably intentional if runoff should reflect the pre-runoff state, but it should be explicit. Later:

```python
patches2, ...
```

is used for the final season output.

Document:

```python
"runoff_state_source": "patches1_post_season_pre_final_output"
```

Otherwise the runoff and final snow state may appear inconsistent.

---

## 24. Overland rainfall default has a unit mismatch

This line is suspicious:

```python
rain_mm_h=float(
    olfg.get(
        "rain_mm_h",
        scfg.get("precip_mm_d", 2.0)
    )
)
```

If `snow.precip_mm_d` is millimetres per day, it is being passed as millimetres per hour.

Fix explicitly:

```python
if "rain_mm_h" in olfg:
    rain_mm_h = float(olfg["rain_mm_h"])
else:
    rain_mm_h = (
        float(scfg.get("precip_mm_d", 2.0))
        / 24.0
    )
```

Better still, require separate configured fields and reject implicit unit conversion.

---

## 25. The replay weather is not the same weather used by the legacy model

Legacy model:

```python
run_simulation(..., air0, sim_s)
```

uses one scalar `air0`.

Replay model receives:

```python
weather_frag
```

and may reconstruct a time-varying weather curve.

Therefore the two river models are not only numerically different; they have different forcing.

This further weakens comparisons between:

```python
river_state
replay_doc
```

Add a forcing-comparison artifact or make the legacy model consume the same `Series`.

---

## 26. The build’s “measured bundle wins” logic is not fully true

The comment says:

```python
measured bundle wins over authored defaults
```

But:

- the bundle is not configured;
- only one hour is selected;
- fields may be converted into synthetic day/night parameters;
- `humidity` and `cloud` may be read from inconsistent locations;
- replay does not necessarily use the complete measured series.

Use clearer wording:

```text
If a frozen meteorological bundle is present, its selected row overrides
authored visual-weather defaults; the replay may still use the synthetic
physical-clock approximation unless scheduled forcing is configured.
```

Or implement the full scheduled forcing path.

---

# Recommended structural refactor

The build currently does too much in one function:

```python
simulate_all()
```

Split it into explicit phases:

```python
def resolve_inputs(cfg) -> InputState:
    ...

def resolve_simulation_time(cfg, baseline) -> SimulationTime:
    ...

def resolve_weather(cfg, simulation_time) -> WeatherForcing:
    ...

def run_season_model(...):
    ...

def run_hydrology(...):
    ...

def run_thermal_models(...):
    ...

def run_foodweb(...):
    ...

def run_spatial_checks(...):
    ...

def export_artifacts(...):
    ...

def validate_build(...):
    ...
```

This would make authority and timing clear.

A better high-level flow:

```text
1. Normalize config
2. Validate input paths and schemas
3. Guard terrain
4. Resolve simulation timestamp
5. Load/hash external forcing
6. Build one canonical weather forcing
7. Run snow/hydrology
8. Run overland hydrology, if enabled
9. Run authoritative thermal replay
10. Run foodweb from replay
11. Run legacy model only as compatibility diagnostic
12. Run coupling/registry/terrain/numerical checks
13. Write artifacts atomically
14. Write manifest last
```

---

# Priority order

## Immediate bugs

1. Fix or add `load_weather_bundle()`.
2. Add `datetime`/timestamp authority to replay.
3. Fix overland precipitation unit fallback.
4. Integrate `check_terrain.py`.
5. Hash met/cross-section/external inputs.
6. Make `BUILD.json` atomic and strict JSON.
7. Add coupling validation.
8. Validate registry contents.
9. Check damped Newton failures.
10. Fix missing-file and malformed-JSON diagnostics.

## Scientific wiring

11. Make one thermal replay the authoritative temperature model.
12. Either wire overland runoff or label it diagnostic-only.
13. Make weather forcing mode explicit.
14. Pass full scheduled weather to the replay.
15. Distinguish model forcing from measured observations.
16. Add simulation timestamp to all artifacts.

## Reproducibility

17. Include all external artifact hashes in `BUILD.json`.
18. Record actual selected baseline file, not just logical name.
19. Include effective weather and hydrology settings in `parameter_set`.
20. Include solver iteration settings and actual convergence metrics.

---

## Bottom line

The build script has strong ambitions and good provenance scaffolding, but it currently acts as both:

```text
scientific workflow
visual content generator
legacy compatibility runner
artifact packager
validation gate
```

without fully separating those roles.

The most consequential issue is this:

```text
the build produces many artifacts and checks,
but some of the most important dependencies and forcing decisions
are not actually part of the build identity or validation gate.
```

Before relying on its `CHECKS.json` or `BUILD.json` as an acceptance artifact, I would first fix:

```text
terrain guard
external input hashing
full simulation timestamp
weather forcing authority
overland wiring
single thermal-model authority
coupling validation
```

After that, the build can become a credible reproducible orchestrator rather than merely a comprehensive one.