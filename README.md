# Yellowstone Midway

A walkable model of the Midway Geyser Basin in Yellowstone National Park, built in Godot 4.5.1 with a Python model behind it. Python simulates the Firehole River's heat and flow, snow and soil moisture, vegetation and grazing, thermal pool outflows and microbial mats, an aquatic food web and wildlife, and publishes the results into the Godot world. In Godot you walk the Grand Loop Road, the Midway boardwalk and the overlook approach at real distances, with the river, steam, weather and ecosystem running from the published data or from a live local Python service.

## Status

This project is unfinished and it is not yet a scientific tool. The terrain, roads, trails, river and pools are georeferenced from USGS, NPS and USDA sources, and the tree census comes from USGS lidar, but the models running on top of them are illustrative. Boundary discharge and upstream temperature are prescribed, several parameters are authored within literature ranges and were not measured here, and no model claim in the repository has been validated against an evaluation dataset. Each fit and scenario artifact carries its own evidence status, and the registries under `yellowstone_python/registry/` keep measured, literature, fitted and authored values apart. I intend to keep replacing the simpler methods with more accurate ones and to validate the results before calling any of this scientific.

## Where this is going

Midway is a small slice. A full scale Yellowstone is planned, and the same approach is in progress for other places with different geology and ecology: a stretch of the Pacific Coast Highway in Northern California, the Mono Lake basin, compressed versions of the Sierra Nevada and the Mojave, a rainforest, Colorado National Monument and Lava Beds National Monument. Some are to scale and some are compressed representations. The longer goal for the coast is a full length highway you can drive, pull over on and wander away from, with the world loaded locally around the player as an island of terrain, simulation and rendering that follows the direction of travel.

## Run it

```bash
cd yellowstone_python
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e '.[science,fetch,dev]'
.venv/bin/python -m pytest
.venv/bin/python -m yellowstone_python.build --config configs/baseline.yaml
```

The generated `yellowstone_midway/scenes/authored_world.tscn` exceeds GitHub's file-size limit and stays local. After cloning or exporting the repository, rebuild it once with Godot 4.5.1:

```bash
cd yellowstone_midway
godot --headless --editor --path . --import --quit
godot --headless --path . --script tools/bake_world.gd
```

Replace `godot` with the path to the Godot executable. Open `project.godot` and press F5 after the bake. Published simulation data are included, so the world runs without a Python service. From `yellowstone_python/`, publish a new build with `.venv/bin/python -m yellowstone_python.publish --build derived/<build-id> --to ../yellowstone_midway`. To drive the world live, start `.venv/bin/python -m yellowstone_python.service.live --build derived/<build-id>`; Godot probes `http://127.0.0.1:8765` at startup and falls back to the published data when nothing answers.

Walk with WASD, look with the mouse, hold Shift to walk faster. Esc opens the starting places and menu, M the map, Tab the conditions and weather panel, H a river and ground probe, and 1 through 4 set the simulation speed from 1x to 3600x. F1 lists every binding.

## Layout

`yellowstone_python/` holds the model, its tests, the build pipeline, observation fetchers for USGS, SNOTEL and Open-Meteo, and the publish step. `yellowstone_midway/` is the Godot project: terrain, pools, vegetation, wildlife and player controls. `yellowstone_atmosphere/` renders sky, clouds and precipitation from the weather snapshots Python writes. `hydrology/` is a small NumPy rainfall, infiltration, runoff and soil water model on a grid, used for experiments.

## Data and licensing

Code is licensed under Apache-2.0 (see `LICENSE`). Third-party data keep their own terms: USGS 3DEP elevation, lidar and stream gauge data, USDA NAIP imagery, NPS geographic layers, NRCS SNOTEL observations, Open-Meteo weather, and the Yale Bright Star Catalog, each with a source record beside the files that use it. The imported wildlife motion library is MIT licensed. The code license does not relicense any of those inputs.
