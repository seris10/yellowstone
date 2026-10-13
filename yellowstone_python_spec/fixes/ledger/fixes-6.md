# fixes-6 ledger
Doc: fixes/fixes-6.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/microclimate.py sha256:0ebbb16da902 ; yellowstone_python/yellowstone_python/overland_flow.py sha256:4143b33a8ffc ; yellowstone_python/yellowstone_python/param_registry.py sha256:3f42f03b765c ; yellowstone_python/yellowstone_python/pool_crust.py sha256:532c72dd294d ; yellowstone_python/tests/test_microclimate.py sha256:b4982ffeb44d ; yellowstone_python/tests/test_param_registry.py sha256:(see fixes-6)
Summary: 40 items: 40 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| micro.1 | split duplicate load_real_weather into fetch_real_weather + load_weather_bundle | implemented | microclimate.py:28, 241, 252 | load_real_weather kept as alias to load_weather_bundle for callers | cheap |
| micro.2 | avoid repeated sys.path.insert in microclimate | implemented | microclimate.py:32 | plain `from tools.fetch_met_forcing import ...`, no sys.path mutation | cheap |
| micro.3 | fix wrong UTC = local - lon/15 sign in bundle_weather | implemented | microclimate.py:271-278 | removed longitude conversion; hour path now treated as plain UTC-hour offset from first row | cheap |
| micro.4 | select bundle row by actual epoch timestamp | implemented | microclimate.py:271-285 | epoch_s_utc keyword arg + nearest-row search with tolerance | cheap |
| micro.5 | represent measured absolute temperature with distinct forcing_mode | implemented | microclimate.py:bundle_weather returns forcing_mode=measured_absolute_temperature at both top level and met_bundle | explicit forcing_mode field present; note describes why day_warming_c stays zero | medium |
| micro.6 | preserve wind direction when bundling scalar speed | implemented | microclimate.py:286-294 | default_wind unit-vector scaled to measured speed; wind_direction_source noted as authored fallback | cheap |
| micro.7 | derive gust from bundle or label provenance | implemented | microclimate.py:314 | gust_source: authored fallback is tagged in met_bundle | cheap |
| micro.8 | rename evap_flux_kpa_weighted and supersaturation_kpa to proxy-labeled names | implemented | microclimate.py:condensation_potential; tests/test_microclimate.py:test_condensation_potential_proxy_label_key | deprecated aliases retired; only evap_pressure_index_kpa_weighted and supersat_pressure_kpa remain | cheap |
| micro.9 | validate RH consistently once | implemented | microclimate.py:_validate_rh; dewpoint_c, condensation_potential, metpy_wet_bulb_temperature, _validate_met_bundle all route through _validate_rh | shared validator; dewpoint and wet-bulb use (0, 1], condensation and bundle use [0, 1] | cheap |
| micro.10 | validate time-series args (seconds, dt, gust) | implemented | microclimate.py:169-186 | _validate_time_args and _sample_count raise on invalid inputs | cheap |
| micro.11 | wind_series first sample equals prevailing base | implemented | microclimate.py:209 | `out = [(bx, bz)]` then n OU updates appended | cheap |
| micro.12 | NWS precip conversion using unitCode | implemented | microclimate.py:407-415 | _nws_quantity factor dict handles mm/m/in correctly | cheap |
| micro.13 | NWS missing values stay None not physical defaults | implemented | microclimate.py:366-372 | returns None when value is None; raises on unknown unit | cheap |
| micro.14 | relabel solar fallback as illustrative or remove | implemented | microclimate.py:323-336 | fallback removed; pvlib required; raises on naive timestamp | cheap |
| over.1 | selected soil must drive the simulation | implemented | overland_flow.py:156-171 | validates soil against hs.SOILS, builds uniform smap of the requested soil | cheap |
| over.2 | _downsample must not drop final row/column | implemented | overland_flow.py:98-104 | per-cell bounds r*src//dst..(r+1)*src//dst cover whole extent | cheap |
| over.3 | _downsample validates dimensions | implemented | overland_flow.py:88-96 | checks src>0, dst>0, dst<=src, field size == src*src | cheap |
| over.4 | returned seconds equals actual simulated duration | implemented | overland_flow.py:180-186, 198, 214 | while-loop trailing partial step, elapsed tracked | cheap |
| over.5 | validate rain, dt, sim_s, grid, cell, soil | implemented | overland_flow.py:143-149 | _nonnegative/_positive/_positive_int helpers used | cheap |
| over.6 | handle numpy absence consistently with hydrosim | implemented | overland_flow.py:9-15,195-204 numpy wrapped in try/import; run_overland returns status=not_available with provenance when numpy absent | numpy optional; degradation path matches hydrosim | cheap |
| over.7 | avoid duplicate sys.path insertion for hydrosim | implemented | overland_flow.py:119-124 | `if d not in sys.path` guard before insert | cheap |
| over.8 | remove unused terrain_fns() call | implemented | overland_flow.py:162-166 | load_terrain only; no terrain_fns reference | cheap |
| over.9 | record effective configuration in output | implemented | overland_flow.py:217-227 | configuration block records infiltration, manning_overland, enable_et, perc_factor, init_wetness, max_substeps, source_dem, downsampling | cheap |
| over.10 | validate balance before serialization | implemented | overland_flow.py:194-201 | returns status: balance_invalid when any value is non-finite | cheap |
| param.1 | validator checks types and non-empty strings | implemented | param_registry.py:242-258 | every ENTRY_FIELD must be non-empty str; param_class and review set-checked | cheap |
| param.2 | registry_errors must not raise on missing param_id | implemented | param_registry.py:329-336 | uses isinstance+get; collects duplicate ids safely | cheap |
| param.3 | cross-check metadata against config files | implemented | param_registry.py:15, 267-323 | SOURCE_REF_FIELDS and source_ref_errors validate path/key/expected against supplied configs | cheap |
| param.4 | split compound units like "m3/s, C" | implemented | param_registry.py:126-146, 260-262 | excelsior now has discharge_m3s and temperature_c entries; validator rejects comma units | cheap |
| param.5 | centralize review-state vocabulary | implemented | param_registry.py:4, 255 | imports REVIEW_STATUSES from claims; validator uses it | cheap |
| pool.1 | radial buffering not conservative; prefer shapely | implemented | pool_crust.py:24-28, 203-237 | shapely Minkowski buffer when available; buffer_method() labels fallback as approximation_not_guaranteed | medium |
| pool.2 | render_apron_tiles must fill the apron region | implemented | pool_crust.py:418-422 | buffered polygon drawn at fill=255 then water ring at fill=200 | cheap |
| pool.3 | validate ring, center, recipe inputs | implemented | pool_crust.py:143-171, 283-291 | r_water_from_area, _validate_ring, center/recipe checks all raise ValueError | cheap |
| pool.4 | depth_at divides by zero for shelf_mult==1 | implemented | pool_crust.py:263-264 | raises ValueError if shelf_mult <= 1; validates r_water, depths | cheap |
| pool.5 | radial_temp docstring + validation | implemented | pool_crust.py:240-251 | docstring states t_edge is constant beyond r_water; r_water validated | cheap |
| pool.6 | make_ramp_stops must not mutate input shell | implemented | pool_crust.py:78-102 | returns {stops, ramp_params}; shell never touched by this function | cheap |
| pool.7 | ramp stop fractions validated and clamped | implemented | pool_crust.py:97, 105-114 | fractions clamped to [0,1.3]; validate_ramp_stops enforces monotonicity | cheap |
| pool.8 | diagnostic for pool area vs mapped-polygon disagreement | implemented | pool_crust.py:174-179, 301-305 | shoelace _ring_area and area_disagreement_pct recorded on shell | cheap |
| pool.9 | render_ramp fails for w<2; ensure parent dir | implemented | pool_crust.py:122-123, 136-138 | raises ValueError if w<2; os.makedirs parent | cheap |
| pool.10 | outflow id must not be hard-coded to pool_1030_0 | implemented | pool_crust.py:34-36, 329 | OUTFLOW_CHANNELS keyed by stable source_id (string "1030") | cheap |
| pool.11 | render_cross_section metadata disclosure | implemented | pool_crust.py:468-481 | sidecar .meta.json with section_geometry, radii_basis, represents_mapped_outline, depths_basis | cheap |

## Cross-project issues
- micro.5: callers of bundle_weather still get night_air_c/day_warming_c=0 named fields; downstream air_temp()/trace() cannot distinguish "measured absolute" from "synthetic diurnal" without reading met_bundle.note.
- over.6: unconditional `import numpy as np` means a numpy-less environment crashes at import even when the module should degrade to not_available (hydrosim path is protected but numpy is not).
- pool.5 radial_temp docstring uses an "X, not Y" contrast which violates yellowstone_python/AGENTS.md section 2 comment style; same style issue appears in several other docstrings but is out of scope for this doc.

## Scientific validity flags
- microclimate.condensation_potential still mixes vapor partial pressures (e_mix = 0.3*es_surf + 0.7*ea) rather than humidity ratios or moist-air enthalpy; the key evap_flux_kpa_weighted continues to label a kPa quantity as a "flux".
- overland_flow runs with authored uniform soil and no bathymetry; the module's own docstring (lines 8-13) states the field carries no runoff signal because outflow stays 0, so any downstream consumer of overland_flow.json is reading a null field dressed up as hydrology.
- param_registry source_refs only check scalar equality against YAML values; a config that renames a key but keeps the number will pass unnoticed, and no check binds the registry to the Python module that actually consumes the knob.
