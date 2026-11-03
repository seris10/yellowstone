# Habitat patch dependency scoping and continuous-habitat migration

Read-only scoping study. Question: the dashboard shows
green authored habitat patches (circles with `center_xz` and `radius_m` in `ecosystem.json`).
Are they the only places animals appear, and what would a move to continuous habitat cost?

Evidence base: files read directly in the checkout (paths below), `jq` queries on
`yellowstone_midway/data/ecosystem.json` and `data/world.json`, and `rg` counts. Test suites were
not run. Items not checked are listed in section 9.

## 1. Answer

1. There are exactly three patches (`north_meadow` r=75 m, `bridge_riparian` r=70 m,
   `forest_edge` r=85 m) and 20 wildlife records. Every record carries one `patch_id`.
2. Animal positions are not confined to the circles. A position comes from an authored route
   (`path_xz` polyline for land animals, a river chainage range for fish, geese and the dipper).
   The only geometric limit in the renderer is a 200 m route-length cap. The `patch_id` binds
   an animal to one patch's food and activity state, wherever the animal stands.
3. Animals appear only at authored places, so the visible effect is close to confinement:
   20 hand-placed routes, none generated from habitat. Outside the three circles the Python
   lookup returns `unsuitable_matrix` with moisture 0.2.
4. Patches are a state-bearing unit in every land-ecology model (vegetation, snow, soil, ET,
   ground heat, grazing, insects, mammal populations), in the exporter schema, in the Godot
   wildlife and ecosystem scripts, in the dashboard, and in about 30 Python test files. A
   migration touches all of them, but most of the physics is per-point already and ports to a
   per-cell form without change of equations.
5. Several continuous fields already exist: a 4 m habitat mask (1025 x 1025), 2 m lidar canopy
   rasters (640 x 640), 1 m core terrain (601 x 601), a ground-heat function of (x, z), and a
   route qualifier (`RouteSupport.qualify`) that already judges any (x, z). The migration is
   mainly a replacement of the patch lookup layer, plus new physical-unit work for forage.

## 2. Verified: where animals can be

| Medium | Records | Position source | Inside patch circle? |
|---|---|---|---|
| Land, 3 `north_meadow` bison | 3 | `path_xz` 4-point loop, max 26 m from patch center | yes (r=75) |
| Land, `bridge_riparian` raven and insects | 2 | `path_xz`, max 44 m and 9 m | yes (r=70) |
| Land, 8 `forest_edge` mammal encounters | 8 | `path_xz` 4-point loop | 7 of 8 yes; `mammal_encounter_bison_01` reaches 208 m from center vs r=85 |
| River, 4 trout (`bridge_riparian`) | 4 | river points 374-377, about (110,-229) to (116,-222) | no: about 104 m from the patch center (69,-315) vs r=70 |
| River, 2 geese and 1 dipper (`bridge_riparian`) | 3 | river points 404-430, about (59,-292) to (19,-358) | yes (26 m to 53 m) |

Sources: `yellowstone_midway/data/ecosystem.json` (`patches`, `wildlife`), `data/world.json`
(`rivers[river_5856_0].points`), `yellowstone_midway/scripts/wildlife_actor.gd` `_build_route`
(lines 276-335), `_update_fish` (503-549). Distances computed with `jq` from those fields.

Consequences:

- The trout use the `bridge_riparian` insect resource while swimming outside its circle. The
  patch is an accounting key and carries no spatial limit.
- `patch_id` flows only into food and activity state: `_ecosystem.patch(_patch_id)` for
  ungulate graze decisions (`wildlife_actor.gd:379, 437, 461`), `set_grazer_activity` and
  `set_insect_forager_activity` (`:682, :685`, `ecosystem.gd:219-227`).
- Mammals already return per-actor state (`ecosystem.gd mammal_state(id, kind, position)`),
  keyed by actor and not by patch. That path is the closest existing model of an actor-keyed
  field.
- The authoring step does confine where routes start: `authoring/mammal_encounters.py:161-185`
  draws candidate centers inside `patch_candidate_radius_fraction` (0.65) or
  `forest_candidate_radius_fraction` (1.0) of a compatible patch, then `RouteSupport.qualify`
  accepts or rejects each sample point on mapped mask, slope, apron, route and river clearance.
  `qualify` is already position-continuous. Only the candidate sampler is patch-shaped.
- Insects and birds are single-patch: `PATCH_RIPARIAN = "bridge_riparian"`
  (`pipeline/shared.py:32`) is hard-coded into `pipeline/stages/insects.py:65-80`, and
  `world.gd:1338` and `:1516` name `bridge_riparian` directly.

## 3. Patch inventory by layer

Counts are `rg -i patch` line counts and include non-habitat uses (Godot render "patches",
`monkeypatch`, `update(patch)` in dashboard JS). They size the work and do not count defects.

### 3.1 Python model (`yellowstone_python/yellowstone_python/`)

| Module | Patch use | Class |
|---|---|---|
| `land/vegetation.py` (50) | `patch_step` logistic biomass, grazing debit, nitrogen, trampling, sinter per patch; `habitat_moisture_at`, `moisture_at` (circle lookup, default `unsuitable_matrix`/0.2); `propose_plantings*` take a center and radius | patch-bound state; per-point equations |
| `land/snow_season.py` (38) | `step_land`, `run_season` per-patch snow, soil bucket, GDD, phenology; `patch_modifiers` by habitat class (aspect, `canopy_keep`, `wind_loss`); `center_xz` for thermal test | patch-bound state; per-point equations; authored class constants |
| `land/snow_energy.py` (7), `land/snow_validate.py` (14) | single dry-meadow "patch" dict fitted to SNOTEL SWE | per-point calibration, already placeless |
| `land/evapotranspiration.py` (24) | `step_patches_et`, Kc by habitat class (`CROP_COEFFICIENTS`) | patch-bound state; per-point equations |
| `land/grazers.py` (34) | `select_patch`, `update_grazers`, `consumed_by_patch_from_grazers` | patch-bound decision logic |
| `land/mammals.py` (52) | `MammalEcology`: population, activity, consumption keyed `[patch][species]`; actor requires a known `patch_id` | patch-bound state |
| `common/mammal_forcing.py` (25) | `environmental_forcing` builds `by_patch` drivers; `apply_consumption` keyed by patch id | patch-bound |
| `insects_birds.py` (7) | `update_wildlife` activity by `patch_id`; `daily_trace(patch)` reads `moisture`, `insect_resource` | patch-bound |
| `thermal_features/ground_heat.py` (11) | `thermal_flux_mm_d_by_patch`, `soil_temperature_by_patch` call `heat_flux_at(cx, cz, shells)` | spatial function sampled at patch centers |
| `pipeline/stages/{vegetation,land,grazers,insects,mammals,finalize}.py` | state keys `patches0/1/2`, `thermal_by_patch`, `soil_t_by_patch`; stage `READS`/`WRITES` tuples | wiring |
| `pipeline/shared.py`, `pipeline/sidecars.py` (20), `pipeline/render.py`, `pipeline/manifest.py` | `PATCH_RIPARIAN`; writes `patch_state.json`, `season.json` patch rows, `soil_temperature` and `ground_heat` per-patch sidecars; copies optional `snow_patch_mask.png` | exporter wiring |
| `exporters/to_ecosystem.py` (8) | `REQUIRED_PATCH_KEYS`: id, biomass, capacity, moisture, growth_per_hour, insect_resource, insect_recovery_per_hour; errors if `patches` empty | schema gate |
| `exporters/runtime_series.py` (10) | `python_series` carries a full `patches` copy per replay frame | payload shape |
| `exporters/godot_sidecars.py` (10) | per-patch `snow_cover_fraction`; scene mean from patch rows | exporter |
| `service/live/engine.py` (56) | `_patch_heat_flux` at centers; `ecology["patches"]`; `step_land` over patches; mammal init from patches | live runtime |
| `service/llm_backend.py` (8), `compare.py` (10) | `/api` patches, `moisture_at`; `common_patches` compare keys | service and diff |
| `authoring/mammal_encounters.py` (18), `authoring/gen_flora.py` (11), `authoring/forest_floor.py` (6), `cli/gen_flora.py`, `cli/review_proposals.py`, `tools/build_mammal_catalogue.py` | candidate sampling in patch footprints; `moisture_at(x, z, patches)` for flora; `gen_flora` reads `ecosystem.json.pre-python` patches in four places | authoring |
| `registry/{coupling,param_registry,equations}.py` | `spatial_support: "patch"`, "patch compartment", "thermal patch" (about 10 exchanges); params with patch applicability (`param_registry.py` lines 323, 871-926, 1430, 1533-1539); component `"patch biomass"` | provenance text and IDs |
| `study_mode.py` (10) | `patch_laterals` is a different term (river lateral patching) | no change |
| `park_runtime/*` | no habitat-patch references (`rg patch` finds none); `legacy_adapter.py` wraps `LiveEngine`, so it inherits patches | indirect |

### 3.2 Data files and configs

| File | Patch content |
|---|---|
| `yellowstone_midway/data/ecosystem.json` | `patches[3]` (21 keys each, includes `center_xz`, `radius_m`, `habitat`, `status`), `wildlife[20]` with `patch_id`, `mammals.enabled/seed`, `python_series[].patches` |
| `data/ecosystem.json.pre-python` | pre-Python authored patches; read by `authoring/gen_flora.py` |
| `data/{grazer,fish,insect_bird,season,winter_grazing,evapotranspiration,mammals,param_registry,equations}.json`, `data/species_*.json`, `data/releases/<hash>/...` | per-patch rows, `by_patch` maps, patch-keyed provenance |
| `yellowstone_python/derived/<build>/patch_state.json`, `season.json`, `ground_heat.json`, `soil_temperature.json`, `BUILD.json` | per-patch outputs, hashed into the build manifest |
| `derived/mammals_authored.json`, `derived/llm_snapshot.json`, `yellowstone_python/data/mammal_*.json` | patch ids and eligible-patch lists |
| `configs/baseline.yaml`, `configs/portfolio.yaml`, `configs/experiments/*.yaml` | `habitat_id: forest_edge` (a habitat class that shares its spelling with a patch id; unrelated keys) and a `grazers` example with `patch_id` |
| `dashboard/public-content.json`, `dashboard/data/*.json` | patch labels, support strings, inventory entries |

### 3.3 Godot (`yellowstone_midway/`)

| File | Use |
|---|---|
| `scripts/ecosystem.gd` (27) | `patches`, `_patch_indices`, `patch(id)`, `set_grazer_activity`, `set_insect_forager_activity`, per-patch `grazed`, `grazer_pressure`, `insect_activity`, `insects_consumed`, `plant_budget_error`; `configuration_valid` requires non-empty patches |
| `scripts/wildlife_actor.gd` (6) | `_patch_id`; graze stop when patch `biomass` < 0.05; feeding registration |
| `scripts/world.gd` (17) | season sidecar patch mean for snow; `apply_snow_patch_mask` (optional `snow_patch_mask.png`); hard-coded `bridge_riparian` at two sites |
| `scripts/simulation_panel.gd` (4) | nearest patch to a point by `center_xz` |
| `scripts/python_river_replay.gd` (1) | copies `patches` array into frames |
| `tools/validate_{ecology,live_client,wildlife_motion}.gd` | patch fixtures |
| `tests/watcher_ecosystem_fixture.json` | patch fixture |
| docs: `docs/{AUTHORING,ecology-research,SURFACE_RENDERING,FOREST_FLOOR,DEVELOPMENT_AND_FUTURE_DIRECTIONS}.md` | patch wording |
| `scripts/canopy_surface.gd`, `canopy_support.gd`, `terrain_streamer.gd`, `tests/park_runtime/ground_rebase_render_check.gd` | "patch" means render geometry; unrelated |

`snow_patch_mask.png` is consumed in `world.gd:907-914` and copied by `pipeline/sidecars.py:31`
and `publish.py:28` when present. It is absent from `yellowstone_midway/data/`, and no
producer was found in `*.py`, `*.gd` or `*.md` (only `fixes-39-rendering-gaps.md` mentions the
intended bake). The snow overlay is therefore patch-keyed in data but its raster is missing in
the current checkout.

### 3.4 Dashboard

- `dashboard/build_public.py:110-155`: extracts `patches` (label, center, radius) into
  `geography`, and per-patch ecology rows.
- `dashboard/domain_data.py:245-322, 519-546`: `_patches` builds entities of type `patch`
  with `display_radius_m`, series per patch and key; wildlife metadata carries `patch_id`;
  table `population_by_patch`. Notes already state "Patch radius does not establish
  hydrologic contributing area" and that spin-up sums patch depths without areas.
- `dashboard/public/coverage.js:75-77`: draws each patch as an SVG circle labeled
  "Authored habitat patch".
- `dashboard/public/{science,workspace,workspace-model}.js`: bar charts per patch and
  patch-worded explanatory strings. (`workbench.js` and `systems-workbench.js` match only on
  an `update(patch)` argument name.)
- Tests asserting patch semantics: `dashboard/test_domain_data.py`, `test_systems_model.mjs`
  (support string "Individual authored patches"), `test_workspace_model.mjs`,
  `test_analysis_router.mjs`.

### 3.5 Python tests that exercise patch structure

`rg -l 'patch_id|patches|patch_step|by_patch|center_xz|PATCH_RIPARIAN'` over
`yellowstone_python/tests` returns 29 files plus `park_runtime/test_live_state_persistence.py`:
`test_{build,catchment_contract,evapotranspiration,exporters,forest_floor,grazer_nutrients,
grazers,ground_heat,hydrology_provider,insects,live_engine,live_realtime,llm_backend,
mammal_encounters,mammal_forcing,mammal_grazing,mammal_live_integration,mammals,
model_boundaries,outflow_network,phase_and_clock,pools,provenance,release_generations,snow,
snow_validate,study,vegetation,winter_grazing}.py`.
Heaviest by `rg -i patch` line count: `test_mammals.py` (51), `test_grazer_nutrients.py` (33),
`test_vegetation.py` (28), `test_winter_grazing.py` (25), `test_pipeline.py` (25),
`test_mammal_encounters.py` (20). Some matches in this set come from `center_xz` or
test-local helper names, so treat it as an upper bound.

## 4. Patch-bound versus spatial

| Quantity | Today | What is spatial already |
|---|---|---|
| Habitat class | patch `habitat` string; Kc and snow modifiers by class | `habitat_mask.png` 1025 x 1025 at 4 m (R mineral, G meadow), used by `habitat_mask_blocker` only for route qualification |
| Terrain, slope | spatial | `terrain.f32` 1025 x 1025 at 4 m; 1 m core heightfield 601 x 601 over x -340..260, z -380..220 |
| Canopy | authored `canopy_keep` per class; input to plantings | lidar rasters `cover_fraction.f32`, `valid_fraction.f32`, `canopy_top_scene_y.f32`: 640 x 640, 2 m cells, first cell at -639 m (metadata in `unresolved_cells_excluded.json`), so a 1280 m square |
| Biomass | scalar index per patch, capacity 1.0 | placed trees and flora (`placements.json`, `botanical_placements.json`) |
| Moisture | scalar per patch (the three shipped values differ by under 0.001: 0.6989 to 0.6992) | `HydrologyProvider` ground wetness; `overland_field.json` is `enabled: false` and `diagnostic_not_wired_to_river` |
| Snow, soil bucket | per patch | optional snow mask raster (missing) |
| Ground heat | function of (x, z) sampled at the patch center | `heat_flux_at`, `heat_flux_mask_field`, `pool_shells` |
| Insects | single patch (`bridge_riparian`) | `river_replay` cells carry water temperature and shear; `plume_field.json`, `steam_microclimate.json` |
| Mammal population | `[patch][species]`, initial 0.2 per eligible pair | none |
| Animal position | authored routes | `RouteSupport.qualify(x, z)` |
| Dashboard geography | circles | map layers exist for features and rivers |

Observation on the snow claim path: `claim_ids` in the newest builds include
`snow_swe_clearings`, validated by `land/snow_validate.py` with a placeless point model
against SNOTEL. That model survives a patch removal unchanged.

## 5. What a continuous habitat field would replace

Proposed unit: a raster `HabitatField` on the existing 4 m world grid (1025 x 1025, about
1.05 M cells), with 2 m lidar canopy resampled in where available and an explicit
`no_driver_data` mask elsewhere. Per-cell state arrays in numpy; patches become reporting
regions (zonal statistics) and stop owning state.

| Field (per cell) | Driver and source | Replaces |
|---|---|---|
| `canopy_cover` | lidar `cover_fraction.f32` (inside +-640 m), `valid_fraction.f32` as mask | authored `canopy_keep`, patch `canopy` argument |
| `habitat_class` | `habitat_mask.png` plus cover thresholds; needs a riparian and wet-meadow class | patch `habitat`, `Kc` lookup key, snow modifiers key, mammal eligibility key |
| `soil_moisture` | per-cell bucket (`step_soil_bucket`) with terrain-derived wetness and `HydrologyProvider` ground wetness | patch `moisture`, `soil_mm` |
| `snow_mm`, `snow_depth`, `snow_cover_fraction` | `step_snow` per cell with aspect and canopy | patch snow fields; `snow_patch_mask.png` bake |
| `ground_heat_flux`, `soil_temperature` | `heat_flux_at` evaluated per cell (vectorized) | `*_by_patch` outputs, `warm_ground_by_patch` |
| `forage_biomass`, `capacity`, `growth_per_hour` | `patch_step` equation per cell; capacity from class and cover | patch `biomass`, `capacity`, `growth_per_hour` |
| `insect_resource`, `insect_activity` | `step_resource` per cell with moisture, river proximity, plume | single `PATCH_RIPARIAN` |
| `suitability[species]` | catalog traits (`habitats`, slope, snow crater depth) combined with field values | `eligible_local_patches`, patch `habitat` eligibility |
| `density[species]` | state per cell | `MammalEcology.population` `[patch][species]` |

Animal-side replacements:

| Today | Continuous form |
|---|---|
| `patch_id` on each record | none; the actor samples the field at its own (x, z) each step |
| Authored `path_xz` loops | placement drawn from `suitability x density` (tile-seeded as in the placement law of `04_PARK_STREAMING_SPEC.md`), movement by steering within suitable cells, keeping `RouteSupport.qualify` as the hard-constraint test |
| `select_patch` warm-ground refuge | gradient search over a local window of cells for snow depth below crater depth and warm ground |
| Per-patch consumption `consumed_by_patch` | consumption at the occupied cell (and a feeding-radius kernel) |
| `set_grazer_activity(id, patch_id, ...)` | `(id, cell or position, ...)` |

## 6. Migration order that keeps builds passing

Principle: keep `patches` as a derived compatibility view until the last step, so the
exporter schema, Godot scripts, dashboard and tests keep passing while the interior moves.
Each step ends with `.venv/bin/python -m pytest -q`, a full `build`, and `audit_provenance`.

| Step | Change | Keeps passing because |
|---|---|---|
| 0 | Freeze a golden snapshot of the current `patch_state.json`, `season.json`, `ground_heat.json`, `soil_temperature.json` and mammal totals from build `75fe2157a3c1` (newest by mtime) | no code change; baseline for parity |
| 1 | Add a read-only `HabitatField` module (grid constants from `land/vegetation.py`: GRID 1025, STEP 4.0, HALF 2048.0) with `sample(x, z)` and `zonal_mean(center, radius)`, backed by habitat mask, lidar cover and terrain. Add provenance files for each raster. No model uses it yet | new module with its own tests |
| 2 | Make `habitat_moisture_at`, `moisture_at`, and the `RouteSupport` candidate sampler accept an optional field; default path unchanged | existing call sites keep their behavior |
| 3 | Vectorize the per-point equations over arrays: `step_snow`, `step_soil_bucket`, `patch_step` growth, `step_patch_soil_water`, `heat_flux_at`. Test: a one-cell array equals the scalar result for each of the three shipped patch records to float tolerance | scalar API stays; array API added next to it |
| 4 | Run the land stages on the field and derive `patches1/2` as zonal means over each patch footprint. Compare against the step-0 snapshot; differences are expected and documented. `REQUIRED_PATCH_KEYS` still satisfied | exporter and Godot see the same schema |
| 5 | Replace single-patch insects with a per-cell resource field; keep the `PATCH_RIPARIAN` output as a zonal view for Godot and the dashboard until step 8 | `world.gd` and `stages/insects.py` keep their interface |
| 6 | Mammals and grazers on density and suitability fields; actor-keyed state (the `mammal_state` pattern) replaces `[patch][species]` and `select_patch`. Authoring samples candidates from the whole domain with `qualify` as the filter | `MammalEcology` tests rewritten alongside; old class kept until removed |
| 7 | Godot: wildlife actors read field samples by position; `ecosystem.patch(id)` stays as a zonal view for panels. Transport: sparse per-actor samples and coarse field tiles via the existing `field_codec` (YSP1) or tile packages, with no per-frame full-grid arrays | `validate_ecology.gd`, `validate_wildlife_motion.gd`, `validate_live_client.gd` updated with the fixtures |
| 8 | Dashboard: replace the circle layer with a raster or contour layer plus probes; update `domain_data._patches`, support strings, and the four dashboard tests | JS and Python dashboard tests changed in the same commit |
| 9 | Retire patch state: remove `patches` from the exporter requirement, rename the equation component and coupling `spatial_support`, drop the `ecosystem.json.pre-python` dependence in `gen_flora.py` | last, after all consumers read the field |

Order rationale: steps 1-3 add capability with zero behavior change. Step 4 is the first
numeric change and is gated by the parity test. Godot and dashboard move after Python is
stable, because both read the published schema.

Cost note: the current dict-per-patch loops cannot be run per cell for 1.05 M cells. Array
state needs numpy vectorization (step 3). The park spec's two-tier design (coarse tier by
elevation band and aspect class; fine tier as the `LiveEngine` island, section 7 of
`04_PARK_STREAMING_SPEC.md`) is a place to fit the field: fine tier = cells in resident tiles,
coarse tier = class aggregates. That spec still names "the vegetation patches" as fine-tier
state, so it needs the same edit. No benchmark was run (section 9).

## 7. Test and provenance implications

Tests:

- Parity tests (step 3) preserve the validated point physics (`test_snow.py`,
  `test_snow_validate.py`, `test_vegetation.py`, `test_evapotranspiration.py`,
  `test_ground_heat.py`).
- The test set in 3.5 splits into: unchanged until step 9 (exporters, schema gates);
  rewritten at step 6 (`test_mammals.py`, `test_mammal_forcing.py`, `test_mammal_grazing.py`,
  `test_grazers.py`, `test_winter_grazing.py`, `test_mammal_encounters.py`,
  `test_mammal_live_integration.py`); rewritten at step 8 (dashboard).
- New tests needed: conservation of water and biomass summed over cells equals the old
  per-patch ledger within tolerance; zonal mean of a uniform field equals the scalar; domain
  edge behavior where `no_driver_data` is set; determinism of tile-seeded placement.
- `compare.py` keys on `season.patches`; it needs a field-aware path or zonal views.

Provenance and claims:

- `habitat_mask.png` has no sibling `.provenance.json` in `assets/textures/` (only
  `trail_mask.png.provenance.json` is present). Its thresholds are authored constants
  (`mineral_channel_max` 0.35, `meadow_channel_min` 0.35 in `mammal_encounters.py`). A field
  built on it needs a provenance record for the raster, thresholds, and class mapping so
  `tools/audit_provenance.py` can gate it.
- Current patch values carry `authored` provenance and the patch `status` text says species
  composition and capacity are uncalibrated. Moving to cells does not calibrate forage. A
  cell-level forage field built from the same authored `growth_per_hour` and capacity is still
  authored and must say so.
- Forage biomass is a dimensionless index (`units: dimensionless_index (not kg)` in
  `land/vegetation.py`), so grazing consumption is not mass-conserving in physical units.
  Per-cell grazing at animal scale makes that visible, because intake becomes a large
  fraction of a small cell. A true continuous model needs kg DM per m2 and intake rates in
  kg/day with citations. This is the largest scientific-grade item.
- Lidar canopy covers about 1280 m x 1280 m (`unresolved_cells_excluded.json` metadata).
  Outside it, canopy has no measured driver. The rule that a proxy is never presented as
  measured means the field needs a validity mask carried to outputs.
- Registry IDs: `"patch biomass"` is a join key in `dashboard/build_public.py:42` and
  `service/live/engine.py:70-71`. Rename with an alias in one change.
  `registry/coupling.py` `spatial_support` strings may be checked by `validate_contract`;
  whether they are an enumerated vocabulary was not checked.
- Run mode and claims: no claim becomes accepted by this migration. The five claim IDs in
  recent `BUILD.json` files stay as they are. Patch-to-cell changes alter hashed build
  outputs; the step-0 snapshot and step-4 diff documentation keep that traceable.
- Style gates: new modules and prose follow `AGENTS.md` section 2; run
  the prose pattern checker on new prose.

## 8. Open decisions for Keith

Each row is a yes/no question with the proposed answer. Rows 1-3, 5, 6, 8 and 9 are scoping
defaults that carry on unless overruled. Rows 4 and 7 change scientific meaning and wait for an
answer.

| # | Question | Proposed answer | Reason |
|---|---|---|---|
| 1 | Keep patches as a derived compatibility view until the last step? | Adopt | Every build passes at each step; the Godot and dashboard rewrite is deferred |
| 2 | Use the 4 m world raster (matches terrain and habitat mask), with 2 m canopy resampled? | Adopt | A 2 m or 1 m grid over the whole world is 4 to 16 times larger, and only the lidar and core terrain regions have that resolution |
| 3 | Limit the continuous domain to where drivers exist (lidar +-640 m and core terrain) and mark the rest `no_driver_data`? | Adopt | Filling the rest with class defaults produces authored proxies |
| 4 | Move forage to physical units (kg DM per m2, cited NPP and intake) as its own step before step 6? | Adopt after Keith confirms | It changes the meaning of every grazing number; the index stays until confirmed |
| 5 | Simulate animals as individuals, as density fields, or both? | Both: density field for population, individuals sampled from it for display | Matches the existing "authored representatives" framing in `ecosystem.json` |
| 6 | Keep the 20 authored routes as pinned fixtures for the Godot validators? | Adopt | Gives a regression baseline for motion and route contracts |
| 7 | Add a riparian and wet-meadow class to the habitat mask, plus a moisture source (terrain wetness or hydrology ground wetness)? | Adopt after Keith confirms | The mask resolves only mineral, meadow and forest-edge, so moisture has no raster source |
| 8 | Align with the park streaming plan (coarse tier by band and class, fine tier = island)? | Adopt: the field becomes fine-tier state | Avoids two competing spatial models |
| 9 | Bake the missing `snow_patch_mask.png`? | Skip | Snow becomes a raster field |

## 9. Not tested and not checked

- Not tested: pytest, build, `audit_provenance`, Godot validators.
- Not tested: runtime cost of a vectorized 1.05 M cell land model or of YSP1 field transport.
- Not checked: whether `registry/coupling.py` `validate_contract` enumerates allowed
  `spatial_support` values, and whether any test fails if a patch id is renamed.
- Not checked: Godot live-mode writes to `grazed`, `grazer_pressure`, `insects_consumed`
  (initialized in `ecosystem.gd:104-108`; only that file was searched).
- Not checked: the shipped Godot `data/` copy versus `derived/<build>/` for the newest build;
  patch geometry numbers come from `yellowstone_midway/data/ecosystem.json` as found.
- The "newest build" id `75fe2157a3c1` is from file modification time; it and `1588d5b8e183`
  both report `checks_passed: true` with the five claim IDs listed above.
- Distances in section 2 were computed with `jq` from stored coordinates; routes were not
  rendered in Godot.

Claude Code - 2026-10-17
