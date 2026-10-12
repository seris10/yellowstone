# All modules implemented (M00–M11) — this file remains as an index

DONE: `common/` (M00), `hydro_thermal.py` (M01), `microclimate.py` (M02),
`pool_crust.py` (M03), `vegetation.py` (M04), `insects_birds.py` (M05),
`fish.py` (M06), `grazers.py` (M07), `snow_season.py` (M08),
`geochemistry.py` (M09), `study_mode.py` (M10), `build.py`/`publish.py` +
`exporters/`/`validation/` (M11) — all wired into `build.py`.

Plus `replay/` (offline 1-D flagship: `river_transport.py`,
`river_world.py`, mapped Firehole replays) driving the Godot study scene
(`scripts/python_river_replay.gd`, `scripts/thermal_probe_overlay.gd`).

Each stub becomes `yellowstone_python/<name>.py` with the listed function
signature, writing `derived/<build-id>/<output>` and merging via
`exporters/to_ecosystem.py`. Copy the provenance pattern from `build.py`
(`write_sidecar` + `parameter_provenance` + illustrative status).

| Module | Function | Output fragment |
|---|---|---|
| `pool_crust` (M03) | `shells(pool_defs) -> (pool_shells_json, apron_mask_png)` | pool rings/shelves/rim/outflow, hydrothermal exclusion mask |
| `vegetation` (M04) | `patch_step(patches, weather, dt) -> patch_state_json` + `propose(...) -> planting_proposal_json` (stable IDs, never resample `placements.json`) | `patches[]` drop-in |
| `insects_birds` (M05) | `activity(patch, weather, hour) -> float` gating dipper/raven/insect FSM rates | `patches[].insect_*` + wildlife durations |
| `fish` (M06) | `suitability(reach, hydraulics) -> Ui` + refuge map | trout `hold_seconds/walk_mps/indices` |
| `grazers` (M07) | `plan_paths(bison, exclusion_mask) -> grazer_json` (A*, no hot-pool crossing) | `wildlife[] path_xz` |
| `snow_season` (M08) | `accumulate(weather, aspect, canopy, apron_mask) -> season_json` (thermal stays bare) | `snow_depth_m/soil_moisture/phenology` |
| `geochemistry` (M09) | `substrate_rules() -> substrate_rules_json` (silica Midway vs travertine Mammoth guardrail) | rules doc, no Midway recolor |
| `study_mode` (M10) | `variants(base_cfg, slider_sets) -> experiments/*.json` (A/B, reset reproduces hash) | two `ecosystem.json` variants |
