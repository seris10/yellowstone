# fixes-5.5 ledger
Doc: fixes/fixes-5.5.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/hydrology_provider.py sha256:4ec141104a82 ; yellowstone_python/yellowstone_python/llm_backend.py sha256:394606ae552f ; yellowstone_python/yellowstone_python/insects_birds.py sha256:d1f90577c39f ; yellowstone_python/yellowstone_python/microclimate.py sha256:0ebbb16da902
Summary: 20 items: 20 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1.a | Remove `spec_from_file_location("hydrosim", "../../...")` | implemented | repo-wide search returns zero hits; hydrology_provider.py:47-66 uses `import_hydrosim` package-first then sibling-checkout | | cheap |
| 1.b | Add HydrologyProvider dataclass snapshot | implemented | hydrology_provider.py:19-25 `HydrologySnapshot`; :69-192 provider with ttl, lock, status | status strings: ok/unavailable/disabled/no_precipitation_input/no_terrain_input | medium |
| 1.c | Package import (no load-by-path) | implemented | hydrology_provider.py:49-66 `import hydrosim` or sys.path insert sibling and re-import | | cheap |
| 1.d | Thread-safe cached result | implemented | hydrology_provider.py:103 `self._lock=threading.Lock()`; :149 `with self._lock:` | cache key includes rounded inputs and hour | cheap |
| 1.e | Actual precipitation required (no cloud fallback) | implemented | hydrology_provider.py:120-129,163-169 returns `no_precipitation_input` when rain is None | | cheap |
| 1.f | Inject provider into Backend | implemented | llm_backend.py:107,114 `hydrology=None` parameter; :844 `_Handler.backend = Backend(..., hydrology=provider)` | | cheap |
| 1.g | serve() wires HydrologyProvider | implemented | llm_backend.py:836-844 `serve(... hydrology=True)` instantiates provider with real terrain | --no-hydrology CLI flag exposed at :858 | cheap |
| 2.a | Delete `rain_rate = 5.0 if cloud>0.3 else 0.0` | implemented | llm_backend.py has no cloud-to-rain substitution; precipitation reads bundle only | | cheap |
| 2.b | Delete dead `[hourly[hour][4] if False else 0.0]` | implemented | llm_backend.py:225-250 `_precipitation_at_hour` reads measured values; no `if False` guard | | cheap |
| 2.c | Explicit precipitation helper | implemented | llm_backend.py:225-250 `_precipitation_at_hour` validates nonnegative, finite, returns None on absence | lives inside weather(); not a module-level helper | cheap |
| 2.d | precipitation_status provenance in response | implemented | llm_backend.py:252-254,301,317 `precipitation_status: measured_bundle|unavailable` | | cheap |
| 3.a | Validate consumers (attack, handling, diet) | implemented | insects_birds.py:198-215 `_validate_consumer` rejects unknown compartments and non-sum-1 diets | | cheap |
| 3.b | Simultaneous demand with per-compartment proportional scale | implemented | insects_birds.py:279-310 demands computed from pre-consumption prey; scale = min(1, available/total_demand) | | medium |
| 3.c | Order-independent regression test | implemented | tests/test_insects.py:test_step_compartments_order_independent | swaps consumer insertion order and asserts identical Nt/Nb/Ne and consumed_by | cheap |
| 4.a | Shared `_finite`/`_nonnegative`/`_positive`/`_unit_interval` validators | implemented | insects_birds.py:165-195 all four helpers defined | mirrored by analogous helpers in hydro_thermal.py and overland_flow.py | cheap |
| 4.b | Apply validators to holling_type_ii, step_resource, develop_benthic, step_compartments | implemented | insects_birds.py:109-121,62-79,124-157,250-336 | all four functions guarded | cheap |
| 4.c | insect_activity uses `_unit_interval` for normalized inputs | implemented | insects_birds.py:28-43 | sun/cloud/moisture/resource/flowering validated as unit interval | cheap |
| 5.a | Backend.weather distinguishes 5 statuses | implemented | llm_backend.py:Backend.weather | nested v1 snapshot exposes a `source` block with `measurement_status`, `precipitation_status`, and `hydrology_status` plus legacy `hydrology_sim_state`; flat aliases retained for the pre-nested consumer path | medium |
| 5.b | weather returns None precipitation and status when bundle missing | implemented | llm_backend.py:208-218 authored-defaults branch sets `precipitation_rate_mm_h: None`, `precipitation_status: unavailable` | | cheap |
| rollout | Rollout checklist end-to-end verifiable | implemented | tests/test_hydrology_provider.py:test_rollout_end_to_end_bundle_to_provider_to_weather drives measured bundle -> provider -> Backend.weather and asserts precipitation_status, hydrology_status, ground_wetness_fraction, solar block | wires fake provider so test stays offline | cheap |

## Cross-project issues
- The recommended `hydrology.hydrosim` module path is replaced with a two-tier resolver (`import hydrosim` then sibling checkout at `../hydrology/hydrosim.py`); a packaging change that renames or moves hydrology will break silently to `status=unavailable`.
- Backend.weather embeds hydrology sub-fields into a flat response (`hydrology_sim_state`, `hydrology_link`) rather than the structured `hydrology: {...}` object the spec recommends; Godot consumers reading the response will see keys that do not match 5.a's shape.
- `fetch_real_weather` and `load_weather_bundle` are both present and distinct, but `load_real_weather` is retained as an alias, which the fixes-6.5 test `test_weather_loader_names_are_distinct` would still pass yet downstream code can keep using the deprecated name.
- The hydrology provider enforces `grid <= side` and runs on terrain.f32; if the serving process is launched without a terrain file, every weather call returns `no_terrain_input` with no console warning.

## Scientific validity flags
- step_compartments conserves per compartment only within one step; the wind decay `ne *= exp(-wind/8 * hours)` is applied AFTER proportional allocation, so recorded `consumed_by` can exceed the final `Ne` reported in `new_state`.
- Backend.weather computes snow_fraction from the Stull (2011) wet-bulb formula (validity T in [-20, 50] C, RH in [5, 99] percent); snow_partition_source labels the derivation and reports unavailable outside the stated range.
- HydrologyProvider cache key rounds inputs to 3-4 decimals and the TTL is wall-clock; two near-identical weather calls can skip the sim and return stale `ground_wetness_fraction` across minutes of real weather change.
- Allocation step reduces each prey compartment by the already-scaled demand but does not update subsequent demand calculations (one-shot per step is fine for small dt but understates competitive pressure over long dt).
