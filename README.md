# Yellowstone Midway

An illustrative scientific world coupling a Python model with a walkable Godot landscape and an atmosphere renderer. Model claims remain `not_yet_accepted`; scenario and fit artifacts carry their own evidence status.

- `yellowstone_python/`: river transport, land water and energy budgets, foodwebs, thermal outflows, observations, and validation.
- `yellowstone_midway/`: terrain, thermal pools, vegetation, wildlife, and player controls in Godot.
- `yellowstone_atmosphere/`: atmosphere assets and rendering experiments.

## Run the model and world

From the repository root:

```bash
cd yellowstone_python
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e '.[science,fetch,dev]'
.venv/bin/python -m pytest
.venv/bin/python -m yellowstone_python.build --config configs/baseline.yaml
```

Open `yellowstone_midway/project.godot` with Godot 4.5.1 and run the project. Publishing a validated build uses `python -m yellowstone_python.publish --build derived/<build-id> --to ../yellowstone_midway` from the Python project. Build directories and source inputs retain their provenance.

The [Python README](yellowstone_python/README.md) describes the model components, frozen results, and test requirements. [The Godot README](yellowstone_midway/README.md) describes the world controls and asset pipeline.

## Data and licensing

Project code is licensed under [Apache-2.0](LICENSE). Third-party data retain their source terms. The world uses USGS elevation and gauge data, USDA NAIP imagery, NPS geographic features, and NRCS SNOTEL observations. Their federal-source records and retrieval details live beside the files in `yellowstone_midway/references/` and observation artifacts. The vendored Yale Bright Star Catalog has separate terms; inspect its accompanying source record before redistribution. The code license does not relicense those inputs.

## Local public export

Current working documents remain in this checkout. A future public export excludes internal notes, prose documents, notebooks, generated analysis, and local state. It preserves code, required assets, dependency files, and license notices:

```bash
cd yellowstone_python
.venv/bin/python -m tools.export_public --out /path/outside/the/repository
```

The destination must be fresh. This command copies files and writes a hash manifest; publication remains an owner action.
