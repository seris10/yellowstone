## Assessment

These are useful governance/comparison utilities, but both have important issues:

- `claims.py` is still too permissive for a scientific registry and has unsafe artifact-path handling.
- `compare.py` is brittle against mismatched builds and currently reads a metric name that the build appears not to produce.
- The claim registry now includes claims for capabilities that are not implemented or wired: upstream discharge prediction, groundwater heat, and 2-D inundation.
- The comparison is still endpoint-only and can compare incompatible builds without detecting it.

---

# `claims.py`

## 1. The registry contains unsupported claims

These claims are currently marked:

```python
"review_status": "not_yet_accepted"
```

That is good, but their presence in the registry and build artifacts may still imply that they are active model capabilities:

```python
"upstream_discharge_predicted"
"groundwater_lateral_heat"
"channel_velocity_inundation_2d"
```

Based on the other scripts:

- upstream discharge is not currently connected to a validated dynamic rainfall-runoff model;
- groundwater exchange is not implemented in the supplied pipeline;
- 2-D velocity/inundation is not implemented;
- the overland module is currently diagnostic and often produces no outlet runoff;
- `river_transport.py` does not yet support dynamic flow forcing.

These should either be:

1. moved to a separate roadmap registry; or
2. given an explicit status such as:

```python
"implementation_status": "planned_not_implemented"
```

Add fields:

```python
"implementation_status",
"evidence_status",
```

For example:

```python
{
    "claim_id": "channel_velocity_inundation_2d",
    "implementation_status": "planned_not_implemented",
    "evidence_status": "no_evidence_artifacts",
    ...
}
```

A claim with no evidence artifacts and no calibration/evaluation datasets should not look like an active claim merely because it has a schema entry.

---

## 2. `MODEL_VERSION` is stale and global

Every claim uses:

```python
MODEL_VERSION = "yellowstone_python-0.1.0"
```

But the project now contains materially different components:

- legacy reach model;
- finite-volume replay;
- explicit surface budget;
- damped Newton iteration;
- hydrology prototypes;
- atmosphere integration.

A single version string is insufficient for traceability.

Use component versions:

```python
MODEL_VERSIONS = {
    "thermal_replay": "0.2.0",
    "surface_flux": "0.2.0",
    "snow_soil": "0.1.0",
    "overland_flow": "0.1.0",
}
```

Or require claims to reference a build manifest:

```python
"model_version": "from_build_manifest",
"required_components": {
    "river_transport": ">=0.2.0",
    "surface_flux": ">=0.2.0",
}
```

The actual build ID and input hashes should be part of evidence artifacts, not inferred from this constant.

---

## 3. Artifact IDs are vulnerable to traversal

Current validation rejects:

```python
path.startswith(("-", "/", "."))
```

but accepts:

```text
derived/../outside/file.json
```

It also rejects all paths beginning with `.`, which may be unnecessarily restrictive, while failing to enforce containment after resolution.

### Fix

```python
def resolve_artifact_id(
    artifact_id: str,
    root=None,
) -> Path:
    path, _split = split_artifact_id(artifact_id)

    if not path or "\x00" in path:
        raise ValueError(
            f"malformed artifact id {artifact_id!r}"
        )

    base = (
        Path(root).expanduser().resolve()
        if root is not None
        else Path(__file__).resolve().parents[1]
    )

    full = (base / path).resolve()

    try:
        full.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"artifact id {artifact_id!r} escapes project root"
        ) from exc

    if not full.is_file():
        raise FileNotFoundError(
            f"registry id {artifact_id!r} resolves to missing file {full}"
        )

    return full
```

Do not use only string-prefix checks for filesystem security.

---

## 4. `validate_claim()` can iterate strings character by character

For example:

```python
"evaluation_dataset_ids": "derived/file.json"
```

causes:

```python
for aid in record.get(key, []):
```

to iterate over individual characters.

Add schema/type validation:

```python
LIST_FIELDS = {
    "required_processes",
    "required_observations",
    "calibration_dataset_ids",
    "evaluation_dataset_ids",
    "metrics",
    "known_exclusions",
    "evidence_artifact_ids",
}

STRING_FIELDS = {
    "claim_id",
    "predicted_quantity",
    "intended_use",
    "spatial_domain",
    "temporal_domain",
    "supported_conditions",
    "model_version",
    "acceptance_criteria",
    "review_status",
}

for field in LIST_FIELDS:
    value = record.get(field)

    if not isinstance(value, list):
        errors.append(
            f"claim {record.get('claim_id', '?')}: "
            f"{field} must be a list"
        )
        continue

    if not all(isinstance(item, str) for item in value):
        errors.append(
            f"claim {record.get('claim_id', '?')}: "
            f"{field} must contain only strings"
        )
```

Also reject `None` and empty strings for required scalar fields.

---

## 5. Unknown fields are accepted

The registry has a fixed field list:

```python
CLAIM_FIELDS = (...)
```

but `validate_claim()` does not reject extra keys. That allows schema drift.

Add:

```python
unknown = set(record) - set(CLAIM_FIELDS)

for field in sorted(unknown):
    errors.append(
        f"claim {record.get('claim_id', '?')}: "
        f"unknown field {field}"
    )
```

If forward compatibility is desired, use an explicit `metadata` field rather than arbitrary keys.

---

## 6. Dataset split syntax is under-validated

Current syntax:

```python
derived/file.json:holdout
```

accepts any split name. It also uses `:` as a delimiter, which is awkward for Windows paths and future structured identifiers.

Add allowed split names:

```python
VALID_SPLITS = {
    "train",
    "dev",
    "holdout",
    "locked-final",
    "prior-window",
}
```

```python
if split not in VALID_SPLITS:
    raise ValueError(
        f"unknown dataset split {split!r}"
    )
```

Longer term, use structured IDs:

```python
{
    "path": "derived/firehole_obs.json",
    "split": "holdout",
}
```

This is easier to validate and serialize.

---

## 7. Validation resolves artifacts relative to the source file, not the build

Current code:

```python
resolve_artifact_id(aid)
```

uses the package root by default. That means a claim can only validate against files present in the source checkout, not necessarily the build directory being audited.

For build validation, accept an explicit root:

```python
def registry_errors(root=None) -> list[str]:
    ...
    errors += validate_claim(c, root=root)
```

Then:

```python
registry_errors(root=build_output_dir)
```

This matters because evidence artifacts such as:

```text
derived/reach_heat_fit_v300k.json
```

may exist in a particular build rather than the repository root.

---

## 8. Accepted claims need stronger acceptance checks

Current accepted check:

```python
if record.get("review_status") == "accepted" and not record.get(
    "evaluation_dataset_ids"
):
```

only verifies that evaluation IDs exist. It does not require:

- evidence artifacts;
- metrics;
- a locked final dataset;
- baseline/null comparisons;
- uncertainty;
- an acceptance result;
- a reviewer;
- a build ID.

Use structured acceptance metadata:

```python
"acceptance": {
    "status": "accepted",
    "reviewed_by": "...",
    "reviewed_at_utc": "...",
    "build_id": "...",
    "evaluation_result_artifact": "...",
}
```

Then require for accepted claims:

```python
ACCEPTED_REQUIRED_FIELDS = {
    "evaluation_dataset_ids",
    "evidence_artifact_ids",
    "metrics",
}
```

The current free-text `acceptance_criteria` is useful for human reading but difficult to verify automatically.

---

## 9. Claim semantics do not match actual outputs

Example:

```python
"metrics": [
    "bias_C",
    "mae_C",
    "rmse_C",
    "heat_relative_residual",
]
```

The build/replay artifacts use names such as:

```python
"heat_residual_j"
"heat_relative_residual"
"water_relative_residual"
```

and `compare.py` expects:

```python
"heat_budget_error"
```

The registry should use canonical metric names or an explicit mapping:

```python
"metric_sources": {
    "bias_C": "calibration.champion.train_bias",
    "rmse_C": "calibration.champion.holdout_rmse",
    "heat_relative_residual": "replay.final_budget.heat_relative_residual",
}
```

Otherwise claims may pass validation while referring to nonexistent fields.

---

## 10. The reach claim’s temporal scope is inconsistent

The claim says:

```python
"temporal_domain": "ice-free season, 2-hour replay windows"
```

But elsewhere:

- replay defaults to 7200 seconds;
- calibration uses multi-day windows;
- foodweb uses 14 days;
- weather bundles may cover 7 days;
- build clock is often only an hour plus synthetic forcing.

Separate:

```text
calibration temporal domain
prediction temporal domain
foodweb temporal domain
```

For example:

```python
"temporal_domain": {
    "thermal_replay": "ice-free, 2-hour windows",
    "calibration": "hourly observations over specified windows",
    "foodweb_projection": "14-day derived landscape run",
}
```

---

# `compare.py`

## 11. It assumes identical record IDs and crashes on structural differences

Current code:

```python
rb[rid]
fb[tid]
mb[pid]
```

A build with a missing or extra reach, fish, or patch raises `KeyError`.

Use indexed-record validation:

```python
def _index_records(
    records,
    label: str,
) -> dict[str, dict]:
    if not isinstance(records, list):
        raise ValueError(f"{label} must be a list")

    result = {}

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(
                f"{label}[{index}] must be an object"
            )

        record_id = record.get("id")

        if not isinstance(record_id, str) or not record_id:
            raise ValueError(
                f"{label}[{index}] lacks a valid id"
            )

        if record_id in result:
            raise ValueError(
                f"duplicate {label} id {record_id!r}"
            )

        result[record_id] = record

    return result
```

Then report:

```python
common = sorted(a_ids & b_ids)
only_a = sorted(a_ids - b_ids)
only_b = sorted(b_ids - a_ids)
```

Do not silently omit structural differences.

---

## 12. It does not verify build compatibility

Before comparing outcomes, compare:

- `world_id`;
- model version;
- configuration hash;
- input dataset hashes;
- simulation timestamps;
- replay duration;
- `dt_s`;
- surface solver method;
- weather forcing hash;
- terrain hash.

Add:

```python
def _load_build_manifest(directory: Path) -> dict:
    path = directory / "BUILD.json"
    if not path.is_file():
        raise ValueError(f"missing BUILD.json in {directory}")
    return json.loads(path.read_text(encoding="utf-8"))
```

Then:

```python
def _compatibility_report(a_manifest, b_manifest):
    keys = [
        ("world_id",),
        ("input_datasets", "terrain", "sha256"),
        ("grid_and_time_step", "replay_dt_s"),
        ("grid_and_time_step", "replay_duration_s"),
    ]
```

Return:

```json
{
  "compatibility": {
    "comparable": false,
    "differences": [
      "simulation windows differ",
      "terrain hashes differ"
    ]
  }
}
```

By default, fail or require `--allow-incompatible`.

---

## 13. The heat metric is likely still wrong

Current code:

```python
"d_heat_budget_error": round(
    cb.get("heat_budget_error", 0.0)
    - ca.get("heat_budget_error", 0.0),
    12),
```

But the build appears to write:

```python
"replay_heat_budget_error"
```

and the replay itself uses:

```python
"heat_residual_j"
"heat_relative_residual"
```

Therefore missing metrics silently become zero, producing a false result.

### Fix

Use a required lookup:

```python
def _required_metric(metrics: dict, *names: str) -> float:
    for name in names:
        if name in metrics:
            value = float(metrics[name])
            if not math.isfinite(value):
                raise ValueError(
                    f"metric {name!r} is non-finite"
                )
            return value

    raise ValueError(
        f"none of the required metric names found: {names}"
    )
```

Then:

```python
heat_a = _required_metric(
    ca,
    "replay_heat_budget_error",
    "heat_relative_residual",
)

heat_b = _required_metric(
    cb,
    "replay_heat_budget_error",
    "heat_relative_residual",
)
```

But choose whether the comparison is:

- absolute residual in joules;
- relative residual;
- residual magnitude;
- signed residual.

For scientific comparison, include all:

```python
"heat_budget": {
    "A": {
        "residual_j": ...,
        "relative_residual": ...,
    },
    "B": {...},
    "delta_residual_j": ...,
    "delta_relative_residual": ...,
}
```

Do not label a difference in residual as a scenario “heat response.”

---

## 14. Missing metrics must not default to zero

Current code:

```python
ib["activity"] - ia["activity"]
```

and:

```python
cb.get("heat_budget_error", 0.0)
```

A missing field should produce:

```text
missing metric
```

not:

```text
true zero
```

Use explicit validation for:

- insect activity;
- hold seconds;
- snow;
- phenology;
- heat budget;
- reach temperature;
- reach flow.

---

## 15. `relocated` is based on the wrong field

Current code:

```python
fa[tid]["start_point_index"] != fb[tid]["start_point_index"]
```

That reports a difference in starting point, not necessarily a change in selected refuge.

Use the actual outcome fields:

```python
def refuge_location(record: dict) -> tuple:
    return (
        record.get("reach_id"),
        record.get("end_point_index"),
        record.get("refuge_s_m"),
        record.get("start_point_index"),
    )
```

Then:

```python
"relocated": (
    refuge_location(fa[tid])
    != refuge_location(fb[tid])
)
```

If the output uses `start_point_index` as the actual selected location, rename the output field to:

```python
"selected_location_changed"
```

---

## 16. Snow comparison assumes matching patch IDs

Current code:

```python
for pid in ma
```

then:

```python
mb[pid]
```

Use common/addition/removal sets and report them.

Also compare:

- snow depth;
- SWE;
- moisture;
- phenology;
- `gdd`;
- stress.

Current output only includes:

```python
"d_snow_mm"
"phenology"
```

That is too narrow for the stated scope.

---

## 17. It should compare replay trajectories, not only endpoints

The script says:

```text
durations need replays
```

That is correct, but the tool could support both modes:

```bash
compare.py A B --mode endpoint
compare.py A B --mode trajectory
```

For trajectory mode:

- align frame timestamps;
- compare common cells;
- calculate maximum, mean, and integrated temperature differences;
- compare threshold exceedance duration;
- compare exposure degree-hours above thresholds;
- compare timing of peaks.

Example metrics:

```text
thermal exposure:
    hours T > 20 C
    hours T > 24 C
    degree-hours above 24 C
    peak temperature
    time of peak
```

This is especially important for trout claims, where duration above a threshold matters more than a final temperature.

---

## 18. Include uncertainty or calibration status

An A/B difference is not automatically meaningful if it is smaller than:

- calibration RMSE;
- parameter uncertainty;
- timestep error;
- cross-family discrepancy;
- observation error.

Add:

```json
{
  "interpretation": {
    "calibration_rmse_c": 1.4,
    "max_surface_linearization_error_w": 2.1,
    "difference_significance": "not_assessed"
  }
}
```

At minimum, report the uncertainty artifacts referenced by `claims.py`.

---

## 19. The CLI output is not atomic and lacks encoding

Current code:

```python
Path(args.output).write_text(text)
```

Use:

```python
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)

tmp = output.with_name(output.name + ".tmp")
tmp.write_text(text + "\n", encoding="utf-8")
tmp.replace(output)
```

Also use:

```python
json.dumps(out, indent=2, allow_nan=False)
```

---

# Suggested improved comparison structure

A better result shape:

```json
{
  "schema": "yellowstone.ab_comparison.v2",
  "A": {
    "name": "control",
    "build_id": "...",
    "simulation_time": {}
  },
  "B": {
    "name": "hot_lowflow",
    "build_id": "...",
    "simulation_time": {}
  },
  "compatibility": {
    "comparable": true,
    "differences": []
  },
  "structure": {
    "common_reaches": [],
    "reaches_only_A": [],
    "reaches_only_B": [],
    "common_trout": [],
    "trout_only_A": [],
    "trout_only_B": [],
    "common_patches": [],
    "patches_only_A": [],
    "patches_only_B": []
  },
  "reach_deltas": [],
  "trout": [],
  "insect": {
    "activity_A": 0.0,
    "activity_B": 0.0,
    "delta": 0.0
  },
  "snow": [],
  "heat_budget": {
    "A": {
      "residual_j": 0.0,
      "relative_residual": 0.0
    },
    "B": {
      "residual_j": 0.0,
      "relative_residual": 0.0
    }
  },
  "scope": {
    "comparison_type": "endpoint",
    "duration_metrics_included": false
  }
}
```

---

# Recommended changes to the claims

The claims should reference comparison outputs more explicitly:

```python
"evidence_artifact_ids": [
    "derived/reach_heat_fit_v300k.json",
    "derived/compare_control_vs_hot_lowflow.json",
]
```

But comparison output should not itself be treated as validation evidence unless:

- build compatibility passes;
- both builds use the intended input hashes;
- required metrics are present;
- model checks pass;
- uncertainty is reported.

---

# Priority order

## `claims.py`

1. Add strict type validation.
2. Fix artifact traversal protection.
3. Support build-specific roots.
4. Add implementation/evidence status.
5. Require structured acceptance metadata.
6. Align metric names with actual artifacts.
7. Move unimplemented claims to a roadmap registry.

## `compare.py`

1. Stop defaulting missing metrics to zero.
2. Detect mismatched IDs.
3. Validate build compatibility.
4. Fix refuge relocation semantics.
5. Compare the correct heat metrics.
6. Handle missing/extra snow patches.
7. Add trajectory/exposure mode.
8. Write output atomically.
9. Include uncertainty and calibration context.

The most serious current issue is that `compare.py` can produce a plausible-looking JSON result while silently comparing incomplete or incompatible artifacts. The most serious `claims.py` issue is that it gives planned or unsupported capabilities the same structural status as implemented, testable claims.