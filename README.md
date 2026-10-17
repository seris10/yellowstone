# Yellowstone

Yellowstone is a work in progress and is not finished. It combines a Godot landscape of Midway Geyser Basin, Python environmental models, and a browser interface for exploring model data.

The current scene covers a 4,096 by 4,096 meter area around Grand Prismatic Spring and the Firehole River. It includes walking routes, the overlook, connected waterways, vegetation, wildlife animation, weather, and a stored river-temperature experiment. Terrain and geographic layers use public source data. Small-scale terrain edits, material detail, plant forms, wildlife motion, and several environmental inputs are authored approximations.

[Open the data explorer](https://yellowstone-dashboard.pages.dev/dashboard/).

## Project layout

| Directory | Contents |
| --- | --- |
| `yellowstone_midway` | Godot project, shaders, assets, geographic inputs, scene authoring tools, and one checked model-data generation. |
| `yellowstone_python` | Coupled models, input preparation, numerical checks, experiment tools, and an optional local service. |
| `yellowstone_atmosphere` | Sky and weather components. |
| `hydrology` | Surface flow, infiltration, soil water, and reference checks. |
| `dashboard` | Editable website source, bundled public datasets, static site, builder, and tests. |

## Run the landscape

Use Godot 4.5.1. Python 3.11 or later is needed for the initial scene extraction; the extraction uses only the standard library. From the repository root:

```sh
python3 yellowstone_midway/tools/unpack_scene.py
godot --headless --editor --path yellowstone_midway --import --quit
godot --path yellowstone_midway
```

The baked scene is stored as `authored_world.tscn.gz` to fit GitHub's per-file limit. The extraction command checks the compressed and restored SHA-256 values, then writes the original scene. It refuses to replace a modified scene unless `--force` is supplied. Extraction does not reduce geometry or texture quality. Keep sufficient free disk space for the checkout, restored scene, and Godot import cache.

The included data generation supports offline exploration. A Python service is optional. At startup, the game checks the loopback service configured in `project.godot` and otherwise uses the stored trajectories. The interface identifies the active mode and model time.

On the tested macOS system, the visible renderer uses:

```sh
godot --path yellowstone_midway --rendering-method mobile --rendering-driver metal
```

| Control | Action |
| --- | --- |
| WASD and mouse | Walk and look. |
| Shift / Space | Brisk walk / small jump. |
| Esc | Starting places and menu. |
| Tab | Conditions and time controls. |
| `M` / `I` | Map / environmental field notes. |
| H | River and ground probe. |
| Q / period | Pause / advance one stored frame. |
| F1 | Full input bindings. |

The menu includes a guided river-temperature experiment. Display-hour controls change lighting; advancing physical model time changes the modeled state. Touch controls and mobile game exports are not implemented.

## Run or rebuild the website

The checked-in site can run without Godot, Python model dependencies, an API key, or a live model service:

```sh
python3 -m http.server 8000 --directory dashboard/public
```

Open `http://localhost:8000/dashboard/`. Select or zoom into a system, open a process, change time or location, and open its full dataset. The interface includes map layers, exchange filters, charts, CSV export, model results, and source/limitation details. Its bundled values are a model snapshot; live park monitoring requires a separate feed.

Edit `dashboard/src` and rebuild into an empty output directory:

```sh
python3 dashboard/build_public.py --out work/site
python3 -m http.server 8000 --directory work/site
```

The default builder verifies the bundled dataset and image hashes. `dashboard/deploy.sh` deploys a build through Wrangler; `CLOUDFLARE_PAGES_PROJECT` and `CLOUDFLARE_PAGES_BRANCH` select the destination. Deployment requires an authorized Cloudflare account.

## Run the Python models

The reference environment uses Python 3.14.7 on macOS arm64. Package metadata allows Python 3.11 or later; other versions and platforms require their own checks. From the repository root:

```sh
cd yellowstone_python
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-reference.lock -e .
.venv/bin/python -m yellowstone_python.build --config configs/portfolio.yaml
.venv/bin/python -m tools.audit_provenance --dir derived
```

Each model build writes an identified output directory under `derived`. `configs/baseline.yaml` defines an illustrative baseline. `configs/portfolio.yaml` adds a prescribed river-entry temperature pulse and a comparison with otherwise matching forcing and initial conditions. Processed geographic and canopy inputs are bundled; the complete source LiDAR point clouds and all optional external datasets are not.

To publish a newly checked build to the local Godot project, replace `BUILD_ID` with its output-directory name:

```sh
.venv/bin/python -m yellowstone_python.publish --build derived/BUILD_ID --to ../yellowstone_midway
```

Publication validates artifact hashes and switches an active-generation pointer. The original bundled generation remains available. A running local model service must match the selected build and model variant.

## Checks

From `yellowstone_python`, run the complete suite:

```sh
.venv/bin/python -m pytest -q
```

From the repository root:

```sh
python3 yellowstone_midway/tools/test_scene_archive.py
godot --headless --path yellowstone_midway --script tools/validate_release_generation.gd
godot --headless --path yellowstone_midway -- --smoke-test
node --test dashboard/test_*.mjs
yellowstone_python/.venv/bin/python -m pip install -r dashboard/requirements-dev.txt
yellowstone_python/.venv/bin/python -m pytest dashboard/test_public.py dashboard/test_domain_data.py -q
```

Use a virtual environment for Python dependencies. Tests requiring optional scientific libraries or raw observations may skip when those inputs are absent. Numerical, software, and rendering checks have separate scopes; a passing software test does not establish field accuracy.

## Current limitations

- Ecological and forecast claims remain `not_yet_accepted`. Prescribed discharge, upstream temperature, and authored weather are inputs to scenarios. Unknown parameter uncertainty remains unknown.
- The terrain uses a local UTM coordinate frame with one Godot unit per meter. Road widths, channel-bed cuts, small drainage details, and structural dimensions include approximations. The scene's geographic extent is Midway; whole-park coverage remains outside this build.
- Canopy placement combines processed LiDAR and authored interpretation. Local crown measurements, species assignments, plant detail, and wildlife biomechanics still require independent validation.
- Tree appearance and distance transitions need further work. Some crown shapes, exposed stems, and transitions remain visibly approximate.
- Performance remains unfinished. The current dense scene ran at roughly 20 frames per second in the measured M4 Metal views; the 30 FPS target was not met. Those measurements do not establish performance on other hardware.
- The game is a desktop landscape and simulation project. Quests, inventory, progression, and a complete game loop are not implemented. Physical mobile devices, Safari, and screen-reader behavior have not been verified for the website.

## Sources and licensing

The Python project uses [Apache-2.0](LICENSE). Original Godot project code and authoring work use the [Midway MIT license](yellowstone_midway/LICENSE), except where an individual file or asset specifies other terms. The [wildlife motion library](yellowstone_python/yellowstone_python/wildlife_motion/LICENSE) retains its MIT notice. Dependencies retain their own licenses.

Animal meshes are owned by KJR and included with permission. Inclusion does not grant a blanket open license to those meshes. Per-file source, modification, license, and ownership records are retained in [asset_manifest.json](yellowstone_midway/data/asset_manifest.json). Dataset and asset licenses are separate from the code licenses.

Included Poly Haven artwork uses [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/):

| Source | Creator credit |
| --- | --- |
| [Pine Bark](https://polyhaven.com/a/pine_bark) | Dimitrios Savva / Poly Haven. |
| [Forest Ground 04](https://polyhaven.com/a/forest_ground_04) | Rob Tuytel and Rico Cilliers / Poly Haven. |
| [Rock Boulder Dry](https://polyhaven.com/a/rock_boulder_dry) | Dimitrios Savva and Rico Cilliers / Poly Haven. |
| [Pine Tree 01](https://polyhaven.com/a/pine_tree_01) | Rico Cilliers and Rob Tuytel / Poly Haven. |
| [Grass Medium 01](https://polyhaven.com/a/grass_medium_01) | Rico Cilliers and Rob Tuytel / Poly Haven. |

Project derivatives include reduced geometry, foliage cards, texture-channel repacking, and distant views. Generic pine and grass source labels do not establish local species identity.

Geographic sources include USGS 3DEP elevation, USDA NAIP 2022 imagery distributed through USGS, and National Park Service Yellowstone roads, trails, hydrography, land cover, soils, and points of interest. These U.S. government source data are public domain. Reprojection, resampling, local offsets, terrain edits, and derived placement layers are project modifications. Source dates, service identifiers, credits, and transformations are retained in [geodata_manifest.json](yellowstone_midway/references/geodata_manifest.json) and the accompanying metadata. No claim is made to original U.S. government works, and agency attribution does not imply endorsement.

The public-domain [NPS Yellowstone Sound Library](https://www.nps.gov/yell/learn/photosmultimedia/soundlibrary.htm) supplies the Geyser Hill water and birds recordings and Lower Geyser Basin wind recording by NPS/Peter Comley, and the Firehole American Dipper and Canada Geese recording by NPS and MSU Acoustic Atlas/Jennifer Jerrett. Playback uses project-selected gain, looping, and placement; the original recording locations and dates remain in the asset metadata.

The Bright Star Catalogue retains its [source ReadMe](yellowstone_midway/references/bsc5_ReadMe.txt). Model equations, parameter sources, input hashes, units, and acceptance status remain in the registries and machine-readable data records.
