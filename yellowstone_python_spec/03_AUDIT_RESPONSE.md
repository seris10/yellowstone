# Audit response — python-audit.txt dispositions (2026-10-09)

External static audit reviewed the scaffold pre-shim. Every Phase 1
(truthfulness/reliability) item is now addressed in code + tests. Phase 2–4
(vertical slice depth, Python-central replay/service, Yellowstone
specialization) remain scoped future work, explicitly.

## Fixed

- **Shims (were future):** pool pigment ramps (`water.gdshader band_ramp`,
  `scripts/pool_overlay.gd`, `pool_ramps/*.png`, baker forward-compat) and
  snow overlay (`terrain.gdshader snow_amount/mask`, `world.gd apply_season`
  from `season.json`). All defaults preserve legacy look; scripts parse-check
  under Godot 4.4.1 `--check-only`; 4.5.1 runtime check pending.
- **Proposals reviewed:** 20/40 lodgepole candidates accepted with per-record
  ledger (slope/DEM, suitability, 6 m separation, existing-stand distance);
  staged into `placement_overrides.json::{add}` as bake-schema records with
  terrain-sampled elevations. Bake deferred (installed Godot 4.4.1 ≠ 4.5.1).
- **Pool geometry:** shells carry mapped rings; water/apron tests are
  polygon-exact (ray-cast + radial buffer, method recorded); edge temperature
  exactly attained (quadratic); cross-section uses the shell's own shelf
  ratio; per-pool ramp stops (depth + gradient); world mask draws polygons +
  per-pool hi-res tiles.
- **Vegetation:** proposals evaluate terrain slope + patch moisture + canopy
  + exclusion per candidate; separation enforced by spatial hash; suitability
  map rendered from the model (DEM + patches + aprons); per-candidate RNG
  (`seed:guild:cell`) so rejections never shift others.
- **Insects:** three compartments (terrestrial/benthic/emergent), water
  degree-day development, Holling-II depletion by real consumer diets, raven
  generalist floor, abundance separated from flight activity; wind strips
  adults, never benthos. Legacy timer interface kept and labeled as Godot
  transcription.
- **Fish:** chainage-window refuge SELECTION (argmax suitability, reason
  recorded — hot test now asserts relocation, not tolerance); nondimensional
  suitability with preferred velocity/depth ranges; segment + lateral-offset
  pool checks every 2 m; deterministic world-coordinate refuge map.
- **Grazers:** full-segment apron checks; no diagonal corner-cutting;
  blocked endpoints raise; doc corrected (8-connected Euclidean); planner
  re-walks a live corridor in every build; timing uses biomass/capacity.
- **Snow:** canopy intercepts accum, wind runs off, aspect slows melt only,
  thermal ground is a melt flux (heavy snow can whiten, budgeted), rain feeds
  soil, ET + drainage losses, snowpack/soil sub-ledgers with gated residuals,
  per-patch phenology with drought stress.
- **Microclimate:** trace takes the full weather config (was: silent
  defaults); Tmax lags to ~15:00 (Godot noon-curve divergence documented in
  sidecar); seeded OU wind; Magnus dew-point, site-pressure boiling point,
  evaporation + supersaturation condensation metrics beside the legacy index.
- **Hydro:** analytical T* regression, timestep convergence, full-run budget
  closure history, zero-duration defined, invalid inputs rejected.
- **Study:** model-internal wording, surge merges (never resets) tributaries,
  exact-key typed schema, `compare.py` endpoint-outcome metrics.
- **Geochemistry:** `fumarole` ambiguity now raises instead of silent
  first-match; scope qualifiers added; shell substrate gated in build.
  Palette-level material validation still awaits PBR asset work (white ≠
  travertine is recorded in the rules).
- **Build:** explicit multirate timeline in BUILD.json; content-complete deps
  (world, placements, catalogue, terrain, code fingerprint, config);
  `validate_config` rejects nonphysical input; named-ID lookups fail loudly;
  lazy fallbacks removed; `simulate_all` is file-free and unit-tested.
- **Publish:** transactional (stage → back up all targets → copy →
  hash-verify → receipt; rollback on failure); build-hash check; project-root
  guard; absent sidecars are warnings; forced publishes recorded.
- **README:** simulates/Godot/precomputed/live/measured/authored/unvalidated
  split; 4.4.1-vs-4.5.1 bake boundary stated.

## Deferred (with reasons)

- **1-D advection–dispersion river + energy budget** (Phase 2 slice): needs
  cross-section survey data (P0 asset gap) before equations are honest.
- **Timestamped replay / live service** (Phase 3): `compare.py` + variant
  configs are the replay seed; a player-visible A/B instrument needs the
  Godot UI pass and topo-bathymetry first.
- **PHREEQC silica chemistry, bioenergetics trout, snow energy balance:**
  research-gated (audit §6 list stands as the shopping list).
- **Physical/held-out validation:** no new observations exist; all
  coefficients remain labeled illustrative.
