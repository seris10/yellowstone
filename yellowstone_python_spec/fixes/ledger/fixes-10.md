# fixes-10 ledger
Doc: fixes/fixes-10.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/replay/river_transport.py sha256:092c2a047750 ; yellowstone_python/yellowstone_python/replay/river_world.py sha256:b019618031e3
Summary: 29 items: 29 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| rt-1 | add surface_budget series (rh, wind_mps, shortwave, cloud) to River._forcing | implemented | river_transport.py:505-513 | `forcing_series.extend([self.surface_budget.rh, ...])` splits at met changes | cheap |
| rt-2 | resolve explicit-budget linearized-vs-nonlinear accounting mismatch | implemented | river_transport.py:662-716, 777-863 | damped Newton iteration (Option C) plus linearized accounting (Option A); diagnostic max_surface_linearization_error_w | refactor |
| rt-3 | share _system and _advance_to surface-power calculation via helpers | implemented | river_transport.py:611-660, 662-716 | `_surface_linearization` and `_surface_power_for_accounting` helpers extracted | medium |
| rt-4 | expose cell_heat_w through river_from_config and replay provenance | implemented | river_transport.py:1231, 1259, 1452-1463 | allowed key + kwarg + make_replay forcing block now serializes `cell_heat_w` per cell | cheap |
| rt-5 | determine explicit_budget from river.surface_budget rather than config key presence | implemented | river_transport.py:1365 | `explicit_budget = config.get("surface_budget") is not None` | cheap |
| rt-6 | fix module docstring overstating prescribed downstream discharge | implemented | river_transport.py:5-7 | docstring now reads "prescribed boundary discharge with lateral-source summation setting all downstream face flows" | cheap |
| rt-7 | normalize Series serialization in make_replay forcing block | implemented | river_transport.py:50-55, 1438-1463 | module-level series_dict() helper; make_replay forcing block routes boundary_m3_s, boundary_c, air_c, additional_heat_flux, sources.temperature_c, and cell_heat_w through it (lists, not tuples); SurfaceBudget.to_dict uses the same helper | cheap |
| rt-8 | add tests pinning Series right-continuous behavior | implemented | tests/test_river_transport.py:327-336 `test_series_is_right_continuous_at_change_times` | asserts Series.at at and across the change times | cheap |
| rt-9 | validate matrix coefficients and name offending cell on failure | implemented | river_transport.py:282-326, 738-741, 758-764, 822-826 | solve_tridiagonal accepts cell_ids and reports singular pivot with cell id plus lower/diagonal/upper/rhs dump; _solve_implicit_step, _system/steady_temperatures callers all pass the id list | cheap |
| rt-10 | add warning thresholds derived from Courant/diffusive numbers | implemented | river_transport.py:33-36, 1072-1086, 1113-1116, 1484-1492; test_river_transport.py NumericalWarningTests | COURANT_WARNING_THRESHOLD and DIFFUSIVE_WARNING_THRESHOLD constants; budget() emits numerical_warnings list; numerical_checks block carries both thresholds and the warnings | cheap |
| rw-1 | ensure river_transport honors explicit weather changes | implemented | river_transport.py:505-513 | prerequisite for mapped replay met forcing | cheap |
| rw-2 | physical_weather produces a row at the requested final time | implemented | river_world.py:624-647 | `_weather_times` appends duration or snaps last sample | cheap |
| rw-3 | validate interval_s and duration_s in weather generators | implemented | river_world.py:678-679, 745-746 | `positive(interval_s, ...)` and `finite(duration_s, ..., 0.0)` on entry | cheap |
| rw-4 | use microclimate authority instead of duplicating diurnal/wind math | implemented | river_world.py:27, 826-842 | `from ..microclimate import air_temp, wind_at`; physical_weather calls air_temp for the diurnal curve and wind_at for the wind oscillation; constants (gust period, lag) come from microclimate | cheap |
| rw-5 | read weather fields from one canonical location | implemented | river_world.py:1395-1397 | top-level document reads humidity/cloud from ecosystem.weather so the met bundle authority matches energy_met_series | cheap |
| rw-6 | validate weather_records nonempty, strictly increasing, starts at t=0 | implemented | river_world.py:759-769 | explicit nonempty, t[0]==0, strictly increasing checks | cheap |
| rw-7 | support scheduled source temperatures via Series.parse | implemented | river_world.py:977-996 | `base_temperature = Series.parse(source["temperature_c"])` and schedule-preserving pulse | cheap |
| rw-8 | fix pulse-semantics docstring (lateral source, not upstream boundary) | implemented | river_world.py:1-2 | module docstring reads "pulse adds a delta to its mapped lateral source"; no boundary claim | cheap |
| rw-9 | bound pulse temperature to physically plausible values | implemented | river_world.py:35-36, 184-209; test_river_world.py test_temperature_pulse_rejects_above_upper_guard | PULSE_TEMPERATURE_UPPER_C=100.0 constant; add_temperature_pulse raises when any active breakpoint exceeds the upper guard | cheap |
| rw-10 | validate cross-section optional field types/ranges | implemented | river_world.py:94-105 | `real_measurement_site` requires bool; `dem_cross_check_depth_m` runs through `positive` | cheap |
| rw-11 | guard parse_cross_sections against non-string feature keys | implemented | river_world.py:63-67 | nonempty-string check now runs before `feature_id.startswith("_")` | cheap |
| rw-12 | reject unknown reach_anchors explicitly | implemented | river_world.py:1050-1073 | unknown-anchor set subtracted from reach ids; river_id/vertex_index validated per entry | cheap |
| rw-13 | validate source and outlet schemas before use | implemented | river_world.py:439-479, 487 | `validate_outlet_record` runs before source_connection reads target_river_id / target_vertex_index / points | medium |
| rw-14 | report flow_comparison when ecosystem and world outlets both carry flow | implemented | river_world.py:504-517 | `flow_comparison` carries ecosystem_m3_s, world_outlet_m3_s, status, and difference_m3_s when both present | cheap |
| rw-15 | label hydraulic diagnostic vs solver geometry authority per cell | implemented | river_world.py:920-922 | per-cell record carries `volume_authority: solver_rectangular_length_width_depth` and `hydraulics_authority: diagnostic_trapezoidal_geometry` | cheap |
| rw-16 | make Channel feature ordering explicit, not dict insertion order | implemented | river_world.py:380-387 | `_feature_records = sorted(..., key=start_s_m)` | cheap |
| rw-17 | validate chainage before mapping to a feature | implemented | river_world.py:405-410 | `feature_at` calls `finite(s_m, "chainage", 0.0)` and rejects s_m beyond channel length | cheap |
| rw-18 | validate feature ids, duplicates and points in Channel.__init__ | implemented | river_world.py:328-347 | feature id type/non-empty checked; duplicate feature ids rejected; `points` presence and list type validated | cheap |
| rw-19 | clean up .tmp files when atomic write fails | implemented | river_world.py:1189-1197 | try/finally unlinks any lingering `.tmp` after the atomic replace | cheap |

## Cross-project issues
- fixes-10 was authored before fixes-14.5-riverworld, which added timestamp plumbing and validators that overlap with and partially satisfy its rw-6 and rw-7 recommendations.
- rw-4 would require either importing from `..microclimate` or extracting a shared forcing builder; microclimate.py uses a different signature (`air_temp(hour, night, warming, lag_hours)`) and no shared Series factory exists.
- rt-6 docstring text is also quoted into build.py and ecosystem documentation downstream; a doc-only fix needs grepping for the exact phrase.

## Scientific validity flags
- Hydraulic diagnostics assume reach-averaged grade; cells on flat/adverse reaches leave Manning undefined but velocity still uses face discharge over rectangular area (river_world.py:938-968).
- Explicit surface budget linearizes around the current temperature per iteration; the reported `heat_relative_residual` closes the linearized equation, not the nonlinear flux, by design (river_transport.py:662-716).
- Pulse composition adds a flat delta to the base series without preventing non-physical values; add_temperature_pulse neither clamps nor warns (river_world.py:208-231).
