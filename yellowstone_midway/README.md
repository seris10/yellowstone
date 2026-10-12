# Yellowstone · Midway

A fixed, georeferenced Godot landscape centered on Grand Prismatic Spring, with walking, the Grand Loop Road, the Midway boardwalk, the overlook approach, connected waterways, and a small observational ecosystem.

**Built and tested with Godot 4.5.1. Open `project.godot` and press F5, or F6 on `scenes/main.tscn`.** The complete package contains baked world assets. Python is needed only if you rebuild the source geography. No online service is contacted during play. Godot is available from its [official archive](https://godotengine.org/download/archive/4.5.1-stable/).

## Explore

| Control | Action |
|---|---|
| WASD / left stick | Walk at 1.65 m/s |
| Mouse / right stick | Look |
| Shift | Brisk walk at 3.2 m/s |
| Space | Small jump |
| Esc | Starting places and menu |
| M | Map, drawn from the same geographic coordinates |
| I | Optional environmental field notes |
| F | Hide or show the interface |
| R | Return to the selected starting place |
| F3 | Authoring flight; Space/Control change height |
| T | Advance lighting/weather phase by two hours |

Four starting places shorten the time needed to inspect the build. Walking itself uses the actual distances. This is a desktop project. Touch controls, mobile exports, swimming, vehicles, quests, inventory and progression are not included.

## What the coordinates mean

The domain is **4,096 × 4,096 metres**. One Godot unit is one metre. The origin is WGS84 / UTM zone 12N, EPSG:32612, E=512952.5950985841, N=4930199.044097667, with a NAVD88 elevation offset of 2,200 m. Godot x points east and z points south. The reference geographic center is 44.525° N, 110.837° W.

The 1,025 × 1,025 elevation grid is sampled at 4 m spacing from USGS 3DEP data. July 19, 2022 USDA NAIP aerial imagery supplies macro ground color. Roads, trails and hydrography come from saved NPS GIS layers. See [the geographic research and provenance](docs/geography-research.md) for exact source dates, accuracy classes and acquisition details.

This is an executable landscape foundation with genuine geographic inputs. It is **not a finished photorealistic replica**. Specific plant transforms are a fixed authoring draft; the compact pine is a human-created generic pine visual, not a botanically authenticated lodgepole specimen. Animal meshes are simple articulated development stand-ins. Thirty fixed original botanical clumps add willow, sedge and lupine genus/guild stand-ins; their exact taxon and positions remain unverified. Road widths, road engineering, bridge structure, underwater depth, small drainage detail and material microstructure remain authored approximations. The core distinctions and the work to finish them are documented rather than hidden.

## Reading order

1. [Development specification and future directions](docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md)
2. [Geography: data, registration, routes and terrain](docs/geography-research.md)
3. [Ecology: habitats, evidence, models and interaction design](docs/ecology-research.md)
4. [Assets: included work, licenses and stronger replacements](docs/asset-research.md)
5. [Authoring and architecture](docs/AUTHORING.md)
6. [Validation record](docs/VALIDATION.md)

## Edit the world

`scenes/authored_world.tscn` is a normal, saved scene of fixed geometry. Its terrain tiles and instanced vegetation are baked ahead of time. The game does not generate a new world or scatter scenery when you launch it.

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
godot --headless --path . --fixed-fps 60 --script tools/validate_walk.gd
godot --headless --path . -- --smoke-test
```

Replace `godot` with the path to your Godot executable. The first compiler retains existing `placements.json`. Replacing that drafting layer requires the explicit `--placements-replace` option. The bake overwrites `scenes/authored_world.tscn`; keep direct edits in the separate handcrafted scene or save a renamed working scene first.

## Credits and code license

Original code and authored project structure: MIT license; see `LICENSE`. Creator assets, government data and recordings retain their own provenance. See `THIRD_PARTY.md` and `data/asset_manifest.json`. Poly Haven sources are CC0; NPS recordings and the included federal geographic sources are public domain. No restricted commercial asset is silently bundled.
