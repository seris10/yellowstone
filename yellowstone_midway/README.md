# Yellowstone Midway

A fixed, georeferenced Godot landscape centered on Grand Prismatic Spring, with walking, the Grand Loop Road, the Midway boardwalk, the overlook approach, connected waterways, and a small observational ecosystem.

**Built and tested with Godot 4.5.1. Open `project.godot` and press F5, or F6 on `scenes/main.tscn`.** The complete package contains baked world assets. Python supplies published simulation trajectories. At startup the renderer probes the local live service at `yellowstone/live_url` (default `http://127.0.0.1:8765`) and selects live Python or the baked build. Baked mode retries the local service every five seconds. A matching service must identify the selected build and model variant. `DataWatcher` observes one release pointer; complete hashed generations are validated before activation. A failed activation retains the current generation. Godot is available from its [official archive](https://godotengine.org/download/archive/4.5.1-stable/).

## Explore

| Control | Action |
|---|---|
| WASD / left stick | Walk at 3.0 m/s |
| Mouse / right stick | Look |
| Shift | Brisk walk at 6.5 m/s |
| Space | Small jump |
| Esc | Starting places and menu |
| M | Map, drawn from the same geographic coordinates |
| `I` | Optional environmental field notes |
| F | Hide or show the interface |
| R | Return to the selected starting place |
| F3 | Authoring flight; Space/Control change height |
| T | Jump the simulation by two hours |
| Tab | Conditions, time, presets, measured weather and A/B |
| F1 | Bindings from InputMap, including gamepad layers |
| H | River/ground probe and buffered strip chart |
| Q / period | Pause / step one stored frame |
| 1 / 2 / 3 / 4 | 1x / 60x / 600x / 3600x |
| 5 / 6 / 7 / 8 | Shade reach / toggle outflow / open cold pocket / change grazing |

Four starting places shorten the time needed to inspect the build. Walking itself uses the actual distances. This is a desktop project. Touch controls, mobile exports, swimming, vehicles, quests, inventory and progression are not included.

## What the coordinates mean

The domain is **4,096 x 4,096 meters**. One Godot unit is one meter. The origin is WGS84 / UTM zone 12N, EPSG:32612, E=512952.5950985841, N=4930199.044097667, with a NAVD88 elevation offset of 2,200 m. Godot x points east and z points south. The reference geographic center is 44.525 degrees  N, 110.837 degrees  W.

The 1,025 x 1,025 elevation grid is sampled at 4 m spacing from USGS 3DEP data. July 19, 2022 USDA NAIP aerial imagery supplies macro ground color. Roads, trails and hydrography come from saved NPS GIS layers. See [the geographic research and provenance](docs/geography-research.md) for exact source dates, accuracy classes and acquisition details.

This is an executable landscape foundation with genuine geographic inputs. It is **not a finished photorealistic replica**. Dominant crown cores and canopy coverage are derived from 2020 USGS LiDAR; their local validation metrics remain unavailable without submitted labels. Specific render dimensions and species transfers remain unvalidated; the compact pine is a human-created generic pine visual whose lodgepole identity lacks botanical authentication. KJR-owned animated animal meshes have runtime bindings. Wolf, deer and elk retain shape-proxy labels; motion and rig checks do not establish measured biomechanics. Thirty fixed original botanical clumps add willow, sedge and lupine genus/guild stand-ins; their exact taxon and positions remain unverified. Road widths, road engineering, bridge structure, underwater depth, small drainage detail and material microstructure remain authored approximations. The documentation records these limits and the work needed to address them.

## Reading order

1. [Current case studies, recording and experiment](../docs/PORTFOLIO.md)
2. [Geography: data, registration, routes and terrain](docs/geography-research.md)
3. [Ecology: habitats, evidence, models and interaction design](docs/ecology-research.md)
4. [Assets: included work, licenses and stronger replacements](docs/asset-research.md)
5. [Authoring and architecture](docs/AUTHORING.md)
6. [Validation record](docs/VALIDATION.md)
7. [Development specification and future directions](docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md)

## Offline release and scientific controls

The complete demo package includes `scenes/authored_world.tscn`, a release pointer and one data generation. Import with Godot 4.5.1 and launch `godot --path .`; a Python service is optional. Source checkouts require the offline bake described below.

Mode, model time and release identity remain visible. Field notes distinguish frozen published diagnostics from unavailable data. In the portfolio scenario, **Guided river temperature experiment** selects the Firehole starting point and restarts the fixed baked trajectory at 120x. H opens the probe and Q pauses. The source pulse and comparison are in the selected generation's `portfolio_comparison.json`.

A display-hour change controls lighting only. T advances physical model time by two hours in live mode. Date controls reset from the identified initial state. The service and baked replay preserve the same heat-exchange strategy and physical timestep for a shared scenario.

On the tested macOS machine, use `godot --path . --rendering-method mobile --rendering-driver metal` for visible exploration and captures. The default compatibility renderer movie attempt timed out. [Measured render scope](../docs/PERFORMANCE.md) records platform and limits.

## Edit the world

`scenes/authored_world.tscn` is a normal, saved scene of fixed geometry. Its terrain tiles and instanced vegetation are baked ahead of time. Startup loads the saved geography and placements.

For new hand placements, edit **`scenes/handcrafted_details.tscn`**. Add `MidwayAuthoredPlacement` nodes, choose an imported PackedScene in the inspector and use the normal transform tools. That scene survives every terrain bake. `data/placement_overrides.json` provides persistent additions, removals and complete replacement records for the initial vegetation draft.

To rebuild geographic data after making a copy of the project:

```sh
python -m pip install -r tools/requirements.txt
python tools/prepare_world.py
godot --headless --editor --path . --import --quit
godot --headless --path . --script tools/bake_world.gd
godot --headless --path . --script tools/bake_botany.gd
python tools/validate_world.py
godot --headless --path . --script tools/validate_baked.gd
godot --headless --path . --script tools/validate_multimesh.gd
godot --headless --path . --script tools/validate_ecology.gd
godot --headless --path . --script tools/validate_live_client.gd
godot --headless --path . --script tools/validate_consumers.gd
godot --headless --path . --fixed-fps 60 --script tools/validate_walk.gd
godot --headless --path . -- --smoke-test
```

Substitute the installed Godot executable path for `godot`. The first compiler retains existing `placements.json`. Replacing that drafting layer requires the explicit `--placements-replace` option. The bake overwrites `scenes/authored_world.tscn`; keep direct edits in the separate handcrafted scene or save a renamed working scene first.

## Terrain quality and checks

Master and core terrain share geographic color, physically scaled soil/trail PBR, snow and wetness. Thermal pigment and film stay within mapped surfaces. The core mesh cuts aligned master triangles at runtime; original baked meshes remain unchanged. Core border heights match the rendered master surface, and the 12 m stitch band preserves the interior.

Intersected master tiles use static collision from their retained render triangles; fully covered master colliders are disabled. Mesh and collision replacements commit together after preflight. If collision cutting is unsupported, the world keeps the original master terrain and refuses core activation. Boundary validation checks outside edge/corner rays, inside ghost surfaces, ordinary walking and failure controls.

The `[yellowstone]` setting `shadows/preset` selects `economical` (120 m), `walking` (140 m, default) or `capture` (160 m). Restart the scene after a settings change. `shadows/range_override_m=0.0` uses the preset; a positive override selects 30-300 m. The atlas and filter remain explicit `[rendering]` budgets: 4096 and Soft Medium. Fine residual normal detail fades from 100-220 m; terrain height and collision remain unchanged.

```sh
godot --headless --path . --script tools/validate_shadow_quality.gd
godot --headless --path . --script tools/check_mat_and_core.gd
godot --headless --path . --script tools/validate_core_cut.gd
godot --headless --path . --script tools/validate_core_collision.gd
godot --path . --render-thread safe --audio-driver Dummy --script tools/validate_terrain_render.gd
```

The visible render fixture records nine view/sun-angle images, seasonal/wetness bindings and moving-camera timing in `tests/terrain_render/`. It rejects a missing core foreground and fragment-cut fallback. Headless checks cover bindings and numerics; visual review uses actual GPU captures. Record the fixed 72-second portfolio sequence with the same harness after selecting the portfolio generation:

```sh
godot --path . --rendering-method mobile --rendering-driver metal --audio-driver Dummy --fixed-fps 30 --write-movie ../work/portfolio.avi --script tools/validate_terrain_render.gd -- --portfolio --out=../work/portfolio-capture
ffmpeg -i ../work/portfolio.avi -c:v libx264 -crf 20 -pix_fmt yuv420p -an ../work/portfolio-demo.mp4
```

The comparison plot reads the checked model artifact. Movie frame timing includes recording overhead; the separate nine-view run measures normal frozen-scene camera timing.

## Credits and code license

Original code and authored project structure: MIT license; see `LICENSE`. Creator assets, government data and recordings retain their own provenance. See `THIRD_PARTY.md` and `data/asset_manifest.json`. Poly Haven sources are CC0; NPS recordings and the included federal geographic sources are public domain. All animal meshes are owned by KJR and their inclusion in the project release is authorized. Source-generation methods remain in the metadata. Rigs and species color textures are illustrative; geometry ownership does not establish local biological validation. The release package includes a per-file asset decision inventory.
