# fixes-16-microclimate ledger
Doc: fixes/fixes-16-microclimate.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/microclimate.py sha256:0ebbb16da902 ; yellowstone_python/tests/test_microclimate.py sha256:b4982ffeb44d
Summary: 8 items: 8 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (R-b2 2026-10-12 moved items 2, 4, 5, 7, 8 to implemented)

Scope note: fixes-16 restates and extends fixes-6 for microclimate.py. Verdicts here are judged against fixes-16's own prescriptions (API shape, pressure units, timestamp selection, library wiring, physical contracts, regression tests). The local agent's progress.md marks fixes-16 "in progress"; the code shows substantially more than in-progress state, with every section at least partly applied.

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | separate fetch_real_weather from load_real_weather and validate bundles | implemented | microclimate.py:28-33, 45-69, 241-254 | fetch_real_weather, load_weather_bundle, _validate_met_bundle present; load_real_weather kept as alias; sys.path mutation removed | cheap |
| 2 | select weather by UTC timestamp, not array position | implemented | microclimate.py:273-343, tests/test_microclimate.py:272-320 | timestamp_utc (datetime, tz-required) and epoch_s_utc are primary; hour= remains deprecated with DeprecationWarning and single-time-arg validation; callers in build.py and llm_backend.py listed as handoffs | cheap |
| 3 | fix wet-bulb pressure units and remove the misleading proxy fallback | implemented | microclimate.py:380-404 | default pressure_pa = SITE_PRESSURE_KPA * 1000.0; metpy imported unconditionally; no proxy fallback; dewpoint via dewpoint_c | cheap |
| 4 | read NWS units via unitCode and preserve missing values | implemented | microclimate.py:456-504, tests/test_microclimate.py:335-337 | station_id is required (no KCPR default), User-Agent identifier is NWS_DEFAULT_USER_AGENT and overrideable, _nws_quantity preserves None for missing values; unit factor maps unchanged | cheap |
| 5 | exact OU sampling, validated durations, documented gust semantics | implemented | microclimate.py:201-240, tests/test_microclimate.py:287-290 | wind_series documents sigma=0.55*gust_mps and the unbounded Gaussian nature; max_samples cap (default 1_000_000) raises before allocating; existing exact-OU and _sample_count guards retained | cheap |
| 6 | remove fake solar fallback, require timezone-aware timestamp | implemented | microclimate.py:323-336 | pvlib called unconditionally; raises ValueError on naive timestamp; no sinusoidal elevation fallback | cheap |
| 7 | repair Herbie wiring and close datasets | implemented | microclimate.py:525-593, tests/test_microclimate.py:340-343 | date_str is required (no 20261011 default), fetched_at_utc is datetime.now(timezone.utc) and distinct from model_run_utc, status="variables_only_not_site_forcing" and note label the gap explicitly, model_run_fxx_hours exposed | medium |
| 8 | clarify physical and renderer contracts; add regression tests | implemented | microclimate.py:94-104, 149-194, 269-283, tests/test_microclimate.py:296-321 | evap_pressure_index_kpa_weighted is the proxy-labeled key, evap_flux_kpa_weighted kept as deprecated alias; rounds removed from condensation_potential; trace docstring states renderer-only and names steam_62C as artistic; existing dewpoint/boiling/wind_from_direction/mixed_relative_supersaturation guards retained | cheap |

## Cross-project issues
- Section 2 keeps `hour=` as a backward-compatible UTC-hour offset; the first-row epoch anchor silently reinterprets the semantics for any caller still passing `hour`. No caller inventory was done, so a stale caller could now get a different row than before without any error.
- Section 7 Herbie: `herbie_retrieve_hrrr_rtma` returns a variable list but no site-forcing values; downstream builders cannot use the result as forcing. `date_str` default "20261011" is a hard-coded today in the module and will drift.
- Progress tracker at yellowstone_python/progress.md marks fixes-16 "in progress (all fixes applied meticulously)" and lists every section as "in progress" simultaneously; the code is substantially applied, so the tracker understates completion while labeling it both in-progress and complete. Treat as stale narration.

## Scientific validity flags
- metpy_wet_bulb_temperature now uses correct Pa units but site pressure defaults from a barometric formula (SITE_PRESSURE_KPA at 2215 m) rather than measured station pressure; wet-bulb values are off from truth by the barometric-vs-measured delta.
- NWS fetch defaults station_id to "KCPR" (Casper, Wyoming), which is ~400 km from the Yellowstone Midway site; any caller using the default silently gets non-Yellowstone data.
- condensation_potential still mixes vapor partial pressures (e_mix = 0.3*es_surf + 0.7*ea); mixed_relative_supersaturation added but computed from the same proxy mixture rather than conserving water mass or moist-air enthalpy.
- herbie_retrieve_hrrr_rtma reports `model_run_utc == fetched_at_utc`, so provenance cannot distinguish the model init time from the retrieval time; conflating these breaks any later audit of forecast-vs-observed timing.
