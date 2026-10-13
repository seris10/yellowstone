# fixes-4 ledger
Doc: fixes/fixes-4.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/gen_trail_mask.py sha256:4b153d516a8b ; yellowstone_python/yellowstone_python/geochemistry.py sha256:be0b8a3be939 ; yellowstone_python/yellowstone_python/grazers.py sha256:53d897869169 ; yellowstone_python/yellowstone_python/hydro_thermal.py sha256:c6c08a8a124b ; yellowstone_python/tests/test_gen_trail_mask.py ; yellowstone_python/tests/test_geochemistry.py ; yellowstone_python/tests/test_grazers.py ; yellowstone_python/tests/test_hydro.py
Summary: 32 items: 32 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| gtm.1 | Create output parent directory | implemented | gen_trail_mask.py:124 `out.parent.mkdir(parents=True, exist_ok=True)` | both main and build_mask covered | cheap |
| gtm.2 | Write .import note or remove from docs | implemented | gen_trail_mask.py:10 `Godot writes the .import note on first import` | doc reworded; Godot generates .import on first import | cheap |
| gtm.3 | Pixel scale 2 m/px convention | implemented | gen_trail_mask.py:26 `PIXEL_M = (2.0 * HALF) / SIZE  # exactly 2 m per pixel` | explicit pixel-center via `_px` subtracts 0.5 | cheap |
| gtm.4 | Trail width semantics explicit (full width) | implemented | gen_trail_mask.py:76 `wpx = max(MIN_TRAIL_PX, int(round(width_m / px_m)))` | treats width as full rendered pixel width per Pillow | cheap |
| gtm.5 | Reject malformed/degenerate routes | implemented | gen_trail_mask.py:53-75 point and width validation; `if len(pts) < 2: continue` | missing points, bad width, NaN rejected | cheap |
| gtm.6 | Reject or log out-of-bounds points | implemented | gen_trail_mask.py:60-63 raises `lies outside the baked world extent` | hard reject instead of silent Pillow clip | cheap |
| gtm.7 | Document/replace Image.composite with lighter | implemented | gen_trail_mask.py:80 `mask = ImageChops.lighter(core, soft)` | both callsites use lighter plus shoulder gain | cheap |
| geo.1 | Canonical Midway substrate | implemented | geochemistry.py:MIDWAY_SUBSTRATE_SYSTEM="siliceous_sinter"; MIDWAY_SUBSTRATE_SUFFIX="illustrative"; MIDWAY_SUBSTRATE joined from them; load-time ValueError if system not in SYSTEMS or not flagged for midway_use | cross-link enforced; label drift fails at import | medium |
| geo.2 | Defensive shell input access | implemented | geochemistry.py:74 `shell_id = s.get("id")` with type guard at :71 | KeyError-free | cheap |
| geo.3 | Palette validated by system id | implemented | geochemistry.py:81-90 `validate_palette(shell_id, system_id, palette)` | checks system membership and whitening | cheap |
| geo.4 | rules_doc returns deep copy | implemented | geochemistry.py:102-103 `copy.deepcopy(SYSTEMS)` | mutation of return cannot leak to module globals | cheap |
| geo.5 | Duplicate-feature detection at import | implemented | geochemistry.py:46-56 SubstrateError defined before the FEATURE_OWNERS loop that raises it | coordinator 2026-10-12: the class was defined after the loop, so a duplicate would have raised NameError; moved above it | cheap |
| grz.plan.A | Validate real endpoint segments (not cell center) | implemented | grazers.py:202-205,248-251 | step_clear(start,pt(sk)) + step_clear(pt(gk),goal) + final guarantee | medium |
| grz.plan.B | A* heuristic in correct world units | implemented | grazers.py:218,237 `nx,nz = pt(nxt)` ; `h = math.hypot(nx - goal[0], nz - goal[1])` | heuristic reads world coordinates | cheap |
| grz.plan.C | Start/goal in bounds | implemented | grazers.py:162-165 raises `plan_path: {name} ... outside bounds` | explicit range check | cheap |
| grz.plan.D | Same-cell start/goal returns [start, goal] | implemented | grazers.py:197-201 | guarded by step_clear(start, goal) | cheap |
| grz.plan.other | cell_m/segment_m/finite coords/stale-heap/cache/tie-break | implemented | grazers.py:plan_path heap now carries (priority, counter, cell) with monotonic insertion counter; cell_m, segment_m, _finite_xz, is_blocked cache and stale-pop skip retained | explicit tie-breaker fixes nondeterministic path flips | cheap |
| grz.seg | segment_samples rejects nonpositive step | implemented | grazers.py:48-49 `every_m must be finite and > 0` | raises ValueError | cheap |
| grz.chk | check_routes handles malformed records | implemented | grazers.py:86-99 `_route_xz` returns None; check_routes reports malformed and empty paths and gates a one-point path as a stationary anchor (point-in-apron), matching wildlife_actor.gd's single-point land route; tests/test_grazers.py test_single_point_anchor_is_gated_as_a_point | coordinator 2026-10-12: the earlier "route needs at least two points" rule failed every build on river_insects_01 (an insect swarm anchored at one point); builds 839a78f1c159 and a86bf030d6ec pass | cheap |
| grz.render | render_tracks filters empty paths and makes parent | implemented | grazers.py:259-261,266,273,291 | empty-point actors filtered, parent mkdir before save | cheap |
| grz.bio | Hypothesis provenance labeled by status | implemented | grazers.py:26-35,80 `model_context(HYPOTHESES)` | emits implemented/partial/not_modeled | cheap |
| ht.1 | step_heat ledger accumulates across substeps | implemented | hydro_thermal.py:141-146 init before loop; :173-179 += each substep | boundary/lateral/outlet/atm/dt all cumulative | medium |
| ht.2 | steady_state mirrors sequential chain | implemented | hydro_thermal.py:198-204 `up = ... temps[state[i-1]["id"]]`; refuses non-serial topology | branching upstream_id raises | medium |
| ht.3 | Reject empty reaches | implemented | hydro_thermal.py:62-63 `at least one reach is required` | via _validate_reaches | cheap |
| ht.4 | Shared input validation | implemented | hydro_thermal.py:27-84 `_finite`,`_positive`,`_positive_int`,`_validate_reaches` | boundary flow, lateral flow, cooling_s, temps checked | cheap |
| ht.5 | stable_dt validates volume | implemented | hydro_thermal.py:109-111 via `_validate_reaches` (vol > 0, finite) | | cheap |
| ht.6 | Remove dead last_dt in step_heat | implemented | hydro_thermal.py:147-185 (no last_dt variable) | | cheap |
| ht.7 | mixing_check rejects negative individual flows | implemented | hydro_thermal.py:122-125 `mixing flows must be >= 0` | | cheap |
| ht.8 | steady_profile parameter validation | implemented | hydro_thermal.py:258-266 q>0, he>=0, width>=0, xs finite | | cheap |
| ht.9 | render_plume_png validates dims and vmin!=vmax | implemented | hydro_thermal.py:301-310 len(field)==nx*nz; `vmin and vmax must differ` | | cheap |
| ht.10 | plume_field validates dims/params | implemented | hydro_thermal.py:280-289 nx,nz positive ints; extent_m>0; sigma_m>=0 | | cheap |
| tests.suite | Regression tests covering conservation/routing/raster | implemented | tests/test_hydro.py:19-83; test_grazers.py:28-73; test_gen_trail_mask.py:19-96; test_geochemistry.py:9-31 | hydro budget closure, planner block cases, mask core/shoulder covered; test_geochemistry.py:22-27 test_all_midway_shells_validate exercises Midway-canonical substrate mismatch via travertine_illustrative | cheap |

## Cross-project issues
- geochemistry.MIDWAY_SUBSTRATE value drifts from SYSTEMS key; downstream shell authors must spell `siliceous_sinter_illustrative` or fail check_midway_shells with no cross-reference to SYSTEMS.
- hydro_thermal.steady_state refuses any upstream_id that is not the previous reach; any caller or spec claim relying on branching Firehole topology will break here.
- gen_trail_mask duplicates logic between `build_mask` and `main`; refactoring risk if one path is updated without the other.

## Scientific validity flags
- hydro_thermal mixing form omits rho*cp (ledger units "m3 * degC"); any real power or evaporation claim will understate heat flux by rho*cp.
- `fish_activity` linear ramp (26 - T)/8 in hydro_thermal.step_heat is authored, not thermal-physiology; treats fish stress as a per-reach constant with no light or DO coupling.
- plume_field is 2-D advection-diffusion with authored Fischer diffusivity and no bathymetry; labeled illustrative but still drives habitat masks.
- grazers.plan_path heuristic uses straight-line Euclidean distance (admissible for 8-connected uniform cost), but corner-cut guard with step_clear can refuse diagonals in anisotropic terrain not matching the uniform-cost assumption.
