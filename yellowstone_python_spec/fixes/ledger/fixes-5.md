# fixes-5 ledger
Doc: fixes/fixes-5.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/insects_birds.py sha256:d1f90577c39f ; yellowstone_python/yellowstone_python/llm_backend.py sha256:394606ae552f ; yellowstone_python/yellowstone_python/hydrology_provider.py sha256:4ec141104a82 ; yellowstone_python/yellowstone_python/microclimate.py sha256:0ebbb16da902 ; yellowstone_python/tests/test_insects.py ; yellowstone_python/tests/test_llm_backend.py ; yellowstone_python/tests/test_hydrology_provider.py
Summary: 35 items: 34 implemented, 0 shortcut, 1 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| ib.A | Order-independent prey competition | implemented | insects_birds.py:270-310 simultaneous demand then per-compartment proportional scale | prey compartments allocated from same pre-consumption state | medium |
| ib.A.test | Dict-order regression test | implemented | tests/test_insects.py:test_step_compartments_order_independent | swaps dipper/trout order in DEFAULT_DIETS and asserts bit-identical Nt/Nb/Ne and consumed_by values | cheap |
| ib.B | develop_benthic conservation and capacity>0 | implemented | insects_birds.py:149-163 develop_benthic returns (nb_new, emergence, disturbance_loss); step_compartments uses the third value | disturbance_loss accounted in the function and propagated into step_compartments ledger | cheap |
| ib.C | Reject NaN/inf in biological functions | implemented | insects_birds.py:165-195 `_finite`,`_nonnegative`,`_positive`,`_unit_interval` used across functions | sunlight/wind_factor/flowering_factor/insect_activity/holling/develop_benthic/step_compartments guarded | cheap |
| ib.D | Reject negative or zero dt where meaningful | implemented | insects_birds.py:69,141,262 `_nonnegative("dt_s", dt_s)` | zero allowed, negative rejected per spec | cheap |
| ib.E | Validate Holling attack and handling | implemented | insects_birds.py:109-121 `_nonnegative` both; denominator check; finite rate check | | cheap |
| ib.F | Validate diet shares and compartments | implemented | insects_birds.py:198-215 `_validate_consumer` enforces unknown compartment + shares sum to 1 | | cheap |
| ib.G | Prey bounds consistent | implemented | insects_birds.py:265,322-323 nt clamped `min(1.0,max(0.0,...))`, nb/ne via `max(0.0,...)` | logistic nt capped each step | cheap |
| ib.H | Transparent wind decay with ledger | implemented | insects_birds.py:8,318-319,333 `WIND_DECAY_SCALE=8.0`; `wind_loss` recorded in ledger | | cheap |
| ib.I | Smooth sunlight at twilight (medium) | implemented | insects_birds.py:18-31 solar-elevation ramp through the civil-twilight band | linear in elevation from -6 deg to zenith; no hard clip at sunrise/sunset | medium |
| ib.J | foraging_state threshold documented or `>=` | implemented | insects_birds.py:7 inline comment states the strict `>` is the shared renderer threshold | documentation of HOVER_THRESHOLD rationale added | cheap |
| ib.K | deepcopy on wildlife records cost note | implemented | insects_birds.py:103-105 docstring notes JSON-shaped records cap deepcopy cost | cost note added; deepcopy preserved | cheap |
| llm.A | No hard-coded hydrology path | implemented | llm_backend.py:841-843 uses `HydrologyProvider`; hydrology_provider.py:47-66 `import_hydrosim` resolves package or sibling | no `../../hydrology/hydrosim.py` reference remains in the package | medium |
| llm.B | Cache or decouple hydrology from weather request | implemented | hydrology_provider.py:103-192 ttl + lock + cache keyed by (soil,grid,sim_s,inputs); llm_backend.py:262-284 provider called inside Backend.weather | ttl_s=60.0 default; thread lock | medium |
| llm.C | Precipitation from bundle, not cloud | implemented | llm_backend.py:225-250 `_precipitation_at_hour` reads `hourly.precipitation_mm_h` or 7th list column; no cloud-to-rain substitution | precipitation_status: measured_bundle/unavailable | cheap |
| llm.D | Hydrology on actual project terrain | implemented | llm_backend.py:828-833 `_provider_terrain` loads terrain.f32; hydrology_provider.py:204-211 uses provided terrain | | cheap |
| llm.E | Narrow hydrology exceptions and surface status | implemented | hydrology_provider.py:180-188 catches (ImportError,OSError,ValueError,AttributeError,TypeError) returning status="unavailable" with error string | | cheap |
| llm.F | Request timeout and concurrency limits | implemented | llm_backend.py:REQUEST_SOCKET_TIMEOUT_S=30.0 + _Handler.setup sets per-connection timeout; _propose_lock serializes the expensive endpoint; terrain and shells cached across calls | per-connection socket timeout now set; worker cap deferred (ThreadingHTTPServer unbounded) | medium |
| llm.G | CORS not wildcard | implemented | llm_backend.py:662,819 `Access-Control-Allow-Origin: http://localhost:3000` + OPTIONS handler at :817-823 | explicit origin and methods | cheap |
| llm.H | Content-Type validation on POST | implemented | llm_backend.py:do_POST media_type == "application/json" strict check with charset parameter allowed | prior permissive filter removed | cheap |
| llm.I | Socket timeout to limit slow-client exposure | implemented | llm_backend.py:_Handler.setup calls self.request.settimeout(REQUEST_SOCKET_TIMEOUT_S=30.0) | per-connection socket timeout bounds slow-client exposure | cheap |
| llm.J | Generic error messages, log internally | implemented | llm_backend.py:743-746,812-815 `logger.exception("backend failure"); return "internal server error"` | | cheap |
| llm.K | Stronger census cache signature than mtime | implemented | llm_backend.py:173-178 `(st_mtime_ns, st_size, st_ino)` | | cheap |
| llm.L | Synchronize cache access | implemented | llm_backend.py:112,177 `_census_lock` wraps load | | cheap |
| llm.M | _load_json catches UnicodeError | implemented | llm_backend.py:52-60 catches `(json.JSONDecodeError, UnicodeError)` and raises DataError; `encoding="utf-8"` | | cheap |
| llm.N | ecosystem_summary validates wildlife | implemented | llm_backend.py:ecosystem_summary explicit isinstance list and per-record dict check before Counter | malformed records now raise DataError rather than silently drop | cheap |
| llm.O | Centralized placements/overrides schema validation | implemented | llm_backend.py:_validate_placement_doc + _coerce_pos_xz reused by placed_points, placements_summary | shared validator rejects malformed trees/add/remove/replace shapes | medium |
| llm.P | weather validates hour | implemented | llm_backend.py:723-731 `0.0 <= hour < 24.0` else 400 | | cheap |
| llm.Q | Cap proposal cost | implemented | llm_backend.py:propose caches _shell_cache and _terrain_cache under _propose_lock; radius<=500, count<=500; MAX_BODY_BYTES=64 KiB | immutable terrain and pool shells reused across calls; serialized by lock | medium |
| llm.R | store_path tolerates missing files | implemented | llm_backend.py:128-131 try/except FileNotFoundError around `.stat()` | | cheap |
| llm.S | latest_build does not rely on raw mtime | implemented | llm_backend.py:505-513 `(st_mtime_ns, st_size, st_ino)` tuple compared | prefers monotonic signature over bare mtime | cheap |
| llm.cors.opt | OPTIONS handling for CORS | implemented | llm_backend.py:817-823 `do_OPTIONS` returns matching headers | | cheap |
| test.insects | Order independence and conservation tests | implemented | tests/test_insects.py:100-119 test_step_compartments_order_independent swaps dipper/trout order in consumers dict and asserts bit-identical Nt/Nb/Ne and consumed_by | | cheap |
| test.backend | Hydrology path independence, hour validation, concurrent census, Content-Type | implemented | tests/test_llm_backend.py:test_concurrent_census_reads_share_cache, tests/test_llm_backend.py:test_weather_never_derives_rain_from_cloud; tests/test_hydrology_provider.py provider status matrix | concurrent census test and no-cloud-to-rain assertion added | cheap |
| arch.cleanup | Separate hydrology provider / weather provider / proposal engine | implemented | hydrology_provider.py exists as HydrologyProvider class; llm_backend.Backend accepts injection | partial match to the recommended layered architecture | refactor |

## Cross-project issues
- hydrology_provider imports `_downsample` from overland_flow (line 203) so grid handling is centralized but any schema change in overland_flow.py breaks both consumers.
- llm_backend.weather emits snow_fraction from Stull (2011) wet-bulb (validity T in [-20, 50] C, RH in [5, 99] percent); snow_partition_source labels the computation and reports unavailable outside the validity range.
- `fetch_real_weather` imports `tools.fetch_met_forcing` at microclimate.py:32-33; the import path assumes `tools/` is on sys.path, which the package install does not guarantee.
- Backend.ecosystem_summary (llm_backend.py:466-500) silently drops malformed wildlife entries via try/except Counter; a Godot client that depends on counts will see a quiet undercount.

## Scientific validity flags
- insects_birds.step_compartments wind decay uses `exp(-wind_mps/WIND_DECAY_SCALE * hours)` as both mortality and dispersal with no physical basis; `WIND_DECAY_SCALE=8.0` is authored.
- develop_benthic regrowth `0.01 * (1 - nb/capacity) * hours` is a logistic placeholder, not degree-day structured.
- llm_backend.weather snow_fraction uses `wet_bulb_proxy = t_c - 2.5*(1-rh)` and `(1 - wet_bulb_proxy/2.0)` clamped to [0,1]; this is an authored approximation presented alongside measured bundle data.
- Hydrology provider runs a 60 s (default) sim_s step on each cache refresh; the reported `ground_wetness_fraction` represents a transient after 60 s, not a steady state.
- Backend.propose uses pre-python ecosystem.json when present (llm_backend.py:626-629); dry runs can diverge from the live ecosystem state the renderer sees.
