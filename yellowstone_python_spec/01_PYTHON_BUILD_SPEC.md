# Yellowstone Python Build Spec — 11 Modules to Write

Package root (new): `../../yellowstone_python/`
Build root: `yellowstone_midway/` = `../../yellowstone_midway/`
Rule: Python reads immutable inputs, writes `derived/<build-id>/`, validates, then *publishes* (copies) into `yellowstone_midway/data/` or `assets/textures/`. Never mutate `references/` or bake in place. Never resample `data/placements.json` at runtime — proposals become stable sidecars with persistent IDs.

Conventions for every module: inputs hashed (SHA256), outputs carry `{contract_version:"0.1.0", world_id:"yellowstone_midway", code_rev, deps, params, seed, units, status:"illustrative ...", parameter_provenance}` per `SHARED_WORLD_CONTRACT.md` §8.1. Clocks in physical seconds; `day_rate` only phases lighting. Conserve volume + heat; report boundary fluxes and state deltas separately.

Prereq read before coding: `yellowstone_midway/scripts/ecosystem.gd`, `scripts/world.gd::update_environment`, `data/ecosystem.json`, `tools/prepare_world.py` (esp. `carve_water_support, decreasing_fit, join_water_profiles`), `docs/ecology-research.md` §§5.1–5.6, `Yellowstone_Research_and_Future_Directions.md` Part 1 §5.

---

## M00 `common/` — coords, units, provenance, IO (write FIRST, ~0.5 day)

**Why:** every other module needs the same frame math; prevents datum/width/angle bugs flagged in `INTEGRATION_ORDER.md` M1.
**Inputs:** `data/world.json::georeference`, `PHYSICAL_FIELD_CATALOG.json`.
**Write:**
- `coords.py`: `local_to_utm(x,y,z) / utm_to_local(E,N,H)`, `sample_index(x,z)` as `floor((x-x0)/dx)` (no truncation/epsilon), triangle-diagonal `10-01` sampler matching `height_field.gd`, GDAL centre `(0.5,0.5)` note. Round-trip test vs `geoanchors.json` (Grand Prismatic −94.707,−10.608; Excelsior 15.812,−145.302).
- `units.py`: m, m³, m³/s, °C + K converters, mm water, dimensionless-index labeler. Fail on bare floats crossing interfaces.
- `provenance.py`: `write_sidecar(path, payload, sources[], params)` injecting hashes + `parameter_provenance`; `build_id = sha1(normalized_config + dep_hashes)[:12]`.
- `validate.py`: NaN/NoData/`null` (no fill, no non-finite), mask check, halo check, mass-residual check helpers.
**Outputs:** importable package; no Godot attach (foundational).
**Accept:** round-trip residual < 1e-6 m at anchors; `pytest` mismatched-units raises.

## M01 `hydro_thermal.py` — river + thermal mixing (FIRST visible payoff, 1–2 days)

**Replaces/extends:** 6-reach serial chain in `data/ecosystem.json::river_reaches` + `ecosystem.gd` advection + Newton cooling.
**Inputs:** `data/world.json::rivers` (Firehole 22 m + Rabbit/Fairy/White/Mallard 3.5 m + `authored_excelsior_outflow_01` 2.4 m), `data/ecosystem.json` (volumes, `boundary_m3s=8.0`, `boundary_c=17.5`, Excelsior lateral 0.26 m³/s @ 62 °C), `references/channel_support_qa.json`.
**Model (keep the paper's equations, add space):**
- Per-reach: `d(ViTi)/dt = ΣQjiTj + Qhot,iThot,i − Qout,iTi + Vi(Tair−Ti)/τi`, constant-volume requires `Qout = ΣQin + Qhot`. Mixing check `Tmixed=(Q1T1+Q2T2)/(Q1+Q2)`.
- Upgrade path (staged): (a) keep 6 reaches, add 4 cold tributary laterals (dilution + confluence T); (b) 1-D centerline profile `T(x)=Ta+(T0−Ta)·exp(−he·b·x/ρcpQ)` for plume viz; (c) 2-D shallow mixing field near Excelsior mouth for map overlay (do NOT claim calibration).
- Substep stability: `dt_sub ≤ 0.45/rate`; test low/high flow.
**Outputs:** `derived/<id>/river_state.json` (drop-in `river_reaches[]` + `boundary_*`) + `derived/<id>/plume_map.png` (plan-view T field, same extent/origin as `habitat_mask.png`).
**Godot attach (zero-change path):** overwrite `data/ecosystem.json::river_reaches` → F5; `world.gd` already routes `reach.temperature_c → river_surfaces:temperature_c`, `fish_activity=(26−T)/8 → trout hold/swim`, `steam_visibility(surface_c) → steam density`. Map overlay: place `plume_map.png` beside `assets/textures/midway_macro.jpg` and reference from field-notes (I key) or map (M key) shim — Phase 1 only.
**Accept:** volume conserved to 1e-9, heat residual ~1e-10 m³·°C (match `VALIDATION.md` ledger format); downstream-monotone stage; pause 10 min → stable; trout visibly slow near hot entry.

## M02 `microclimate.py` — one wind/time authority (0.5–1 day, high leverage)

**Replaces:** scattered sine waves; owns `weather` in `ecosystem.json`.
**Inputs:** `ecosystem.json::weather,clock_hour,day_rate,humidity,cloud`.
**Model:** `Tair(t)=night_air_c + day_warming_c·sin(2π(hour−9)/24)` (defaults 7 + 15); low-freq prevailing wind vector + gust detail; `steam_visibility(surface_c)` artistic proxy; expose `wind_xz_mps, gust_mps, air_c, humidity, cloud`. Same authority drives foliage (`foliage.gdshader:wind_vector`), steam drift, insect exposure, audio gain.
**Outputs:** `derived/<id>/weather.json` (drop-in `weather + clock_hour`) + `wind_rose.png` (optional viz).
**Godot attach:** zero-change via `ecosystem.json`. Verify foliage + steam + audio move together.
**Accept:** single prevailing direction across subsystems in a 60 s trace; no per-system phase drift.

## M03 `pool_crust.py` — Grand Prismatic / Excelsior shells + aprons (1–2 days, biggest visual)

**Problem today:** ordinary terrain cut = visual floor only; single painted pond is wrong (Grand Prismatic 61–101 m across, >37 m deep; Excelsior 61×91 m crater + drainage; mapped polygons 94×102 m bounding).
**Inputs:** `data/world.json::pools` (pool_1034_0, pool_1030_0, Turquoise/Opal), `midway_orthophoto_detail.jpg` (0.625 m/px core), `yell hydro lakes`, USGS thermal-area polygons (exclusion only).
**Model:** author (not survey) per-pool: crater wall profile, shallow shelf, wetted rim, drainage fingers, outflow channel connection. Radial temperature `T(r)` → pigment bands (temp + depth + substrate + light; NO universal T→rainbow equation). Depth is illustrative fill; state that bathymetry is unmeasured. Silica sinter only (Midway); travertine equations live in M09 stub, not applied here.
**Outputs:** `derived/<id>/pool_shells.json` (per-pool `center, ring_radii_m, shelf_depth_m, rim_w_m, outflow_id, T_center_C, T_edge_C, color_stops[]`, all illustrative) + `derived/<id>/apron_mask.png` (eligibility layer: hydrothermal ground vs vegetation) + `pool_cross_section.png` (diagram for field notes).
**Godot attach:** Phase 0: field-notes diagram + apron as map overlay. Phase 1 shim (small): new `pool_ring.gdshader` uniform read from `pool_shells.json` (requires 1-day GDScript task, spec'd but not blocking modeling).
**Accept:** mapped water outline preserved; no forest scatter crossing bright apron (mask test); before/after standing-height captures at overlook + boardwalk.

## M04 `vegetation.py` — suitability + biomass + planting proposals (2 days)

**Inputs:** `data/placements.json` (36,225 records — READ-ONLY draft), `placement_overrides.json`, `botanical_placements.json` (30 clumps), `species_catalogue.json` (56 entries, `runtime_implementation=not_asserted`), `habitat_mask.png`, `terrain.f32` (slope/aspect via full-grid derivatives).
**Model:**
- Suitability field per species/guild: `λs(p)=λs,0·Mhabitat(p)·fs(soil,moisture,slope,aspect,canopy,disturbance)·Mexclusion(p)`. Coefficients are artist/science inputs.
- Patch biomass (existing 3 patches + new riparian/wetland polygons only where sources support): `dB/dt = r·flight·fwater·B(1−B/K) − G` (units explicit; dimensionless index labeled as such).
- Proposal tool: min-separation / pair-correlation per category (NOT one Poisson radius); seed-tree clusters, recruitment patches, mortality gaps. Output is **stable records**, never a runtime probability field.
**Outputs:** `derived/<id>/patch_state.json` (drop-in `patches[]`) + `derived/<id>/planting_proposal.json` (`{stable_id, species_id, x,z,y, yaw, scale, variation_key, evidence_class, author_note}`) + `suitability_<sp>.png` previews.
**Godot attach:** `patch_state.json → patches[]` zero-change (grazing/insects respond). Proposals enter via `placement_overrides.json::{add}` + `handcrafted_details.tscn` review, or `botanical_details.tscn` for 2/20/200 m screenshots. Never overwrite `placements.json`.
**Accept:** `validate_ecology.gd` passes; no thermal/water exclusions violated; ID-level change list + screenshots at 2/20/200 m.

## M05 `insects_birds.py` — insect activity → foraging (1 day, cheap life)

**Inputs:** `patches[].biomass/moisture/insect_resource`, `weather` from M02, `wildlife[]` dipper/raven/goose/insects records.
**Model:** `insect_activity = f(Tair, wind, moisture, flowering_stage, sun/cloud, hour)`; recovery `dN/dt` style resource; bird query: `forage_probability = g(insect_activity, patch, time_of_day)` — NOT independent timers. Keep Dipper at river_bank stones, Raven perch/forage/return, Goose float/preen near `river_5856_0` indices.
**Outputs:** `derived/<id>/insect_bird.json` (drop-in `patches[].insect_*` + `wildlife[]` durations/rates).
**Godot attach:** zero-change. Walk to bridge_riparian (≈69,−315) and watch dipper/raven cadence follow weather sliders.
**Accept:** overcast + wind → activity < 0.035 → insects `inactive`, birds perch; sunny calm → hover/forage. Trace logged.

## M06 `fish.py` — trout suitability + refuge (1 day)

**Inputs:** M01 reach temps + hydraulic per-reach `depth/velocity` (authored cross-sections from Prompt 3; start with uniform + documented assumption), `wildlife[]` trout_01–04.
**Model:** `Ui = wf·Fi + wc·Ci − wt·φ(Ti) − wv·Vi − wd·Di` (food, cover, temp penalty, velocity, depth); `fish_activity=(26−T)/8` retained as visibility modulator, NEVER mortality prediction. Ordinary fish excluded from hot centers by mask. Refuge = nearest cold tributary cell / shaded bank (authored, verified).
**Outputs:** `derived/<id>/fish.json` (drop-in trout `hold_seconds, walk_mps, river_id indices, lateral_offset_m`) + `refuge_map.png`.
**Godot attach:** zero-change. Trout hold/swim visibly shifts with M01 plume.
**Accept:** no trout path through pool_1034_0/pool_1030_0 (mask test); high-T reach → hold longer, slower; conservation/stable-step tests from M01 pass.

## M07 `grazers.py` — bison/elk habitat-constrained movement (1–1.5 days)

**Inputs:** `north_meadow` + new meadow polygons, thermal/water/cliff/building exclusion mask, `wildlife[]` bison_01–03.
**Model:** graze/move/rest FSM driven by patch `biomass` (M04) with grazing debit `G`; path planner A* on eligibility grid (no straight line through hot pool/cliff/water). **No universal `wolves→elk→willow` slider** — keep multiple hypotheses + explicit `unknowns[]`. Sparse counts stay sparse.
**Outputs:** `derived/<id>/grazer.json` (drop-in `wildlife[] path_xz, graze/rest_seconds, grazing_index_per_second`) + `grazer_tracks.png`.
**Godot attach:** zero-change. Verify actors stay in valid habitat across tile interior; log tile-boundary crossings.
**Accept:** 10-min walk trace never enters exclusion; biomass declines with grazing then recovers (ledger).

## M08 `snow_season.py` — weather state + snow + seasons (1.5 days, high wow)

**Inputs:** M02 weather + M04 patches + apron mask (M03).
**Model:** degree-day or energy-balance (stated): accumulate/melt `snow_depth_m` with aspect/canopy/wind modifiers; **thermal ground excluded from uniform blanket**; soil moisture → vegetation/insect state (M04/M05). Season switch alters surfaces/phenology only — roads/trails/distances frozen. Summer/autumn/winter appearance layers authored as parameter sets, not geometry moves.
**Outputs:** `derived/<id>/season.json` (`snow_depth_m per patch, soil_moisture, phenology_stage`) + `snow_map.png` (thermal holes visible).
**Godot attach:** Phase 0: field-notes numbers. Phase 1 shim: snow-cover uniform + bare-thermal mask in `terrain` shader (spec'd, 1-day).
**Accept:** Midway apron stays bare while forest holds snow; reload preserves season; provenance lists illustrative vs observed params.

## M09 `geochemistry.py` — sinter vs travertine guardrail (0.5 day stub, prevents future error)

Midway is siliceous; Mammoth is travertine/calcite (NPS G4). This module does NOT recolor Midway. It records fluid-chemistry → substrate rules so a future basin can't be built by "whitening Grand Prismatic."
**Outputs:** `derived/<id>/substrate_rules.json` + one-page `substrate_note.md`.
**Accept:** imports without affecting Midway bake; cited by M03 apron.

## M10 `study_mode.py` — labeled experiments (1 day, demo gold)

Prompt 6 implementation, separate from ordinary walk. Sliders: air T, shade/cloud, upstream Q, Excelsior source strength. Same parameter authority drives M01/M02/M05/M06 responses. Fixed geography, reset + side-by-side replay, units + uncertainty shown. Include counterexample presets ("single variable ≠ whole habitat").
**Outputs:** `derived/<id>/experiments/*.json` + `study_app.py` (Streamlit or CLI → writes `ecosystem.json` variants A/B).
**Godot attach:** publish variant A/B as two `ecosystem.json` files; walk + compare; optional split-screen shim later.
**Accept:** reset reproduces baseline hash; A/B diff logged with params + time scale.

## M11 `exporters/` + `validation/` — publish + prove (0.5–1 day, required)

- `to_ecosystem.py`: merge M01/M02/M04–M08 fragments → schema-v1 `ecosystem.json`; run `validate_ecology.gd` equivalent in Python (reach topology, patch IDs, wildlife IDs resolve).
- `to_map.py`: reproject any field PNG to `midway_macro.jpg` frame for M-key map.
- `live_bridge.py` (optional Phase 1): file-watch or UDP push of `ecosystem.json` deltas to running Godot (fallback: manual copy + F5; do NOT block on this).
- `checks.py`: volume/heat conservation, downstream-monotone stage, exclusion-mask, ID-stability (`placements.json` untouched), provenance-completeness, determinism (`build_id` reproducible from config hash).
**Accept:** `python -m yellowstone_python.build --config configs/baseline.yaml` → `derived/<id>/` + `CHECKS.json` all-pass → `publish.py --to yellowstone_midway/` → F5 walk + `VALIDATION.md`-style before/after captures.

---

## Build order for speed (do in this sequence)

1. M00 → M01 + M02 (same day payoff: river temps + wind visible in steam/foliage/trout).
2. M05 + M06 (life responds, no art needed).
3. M04 patches-only (biomass numbers move; proposals can wait).
4. M03 shells + apron (needs the map-overlay shim; start modeling while shim is queued).
5. M07 → M08 → M10 (movement, snow, demo mode).
6. M09 + M11 throughout (guardrail + publish pipeline).
7. M04 full proposals + M03 shader shim when ready (art-gated, decoupled).
