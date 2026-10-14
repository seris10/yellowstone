# fixes-47: package layout, module boundaries and consolidation

Scope: how `yellowstone_python/` is organized as code: the 3,100-line build module, a flat package of about 50 modules, files split where one module is natural, tools that are really library code, and the import mechanics. No change to model behavior. Audit 2026-10-13 at the request of KJR.
Method: module sizes, importers (`rg` over `yellowstone_python/`, `tools/`, `tests/`), the `build.py` outline, and the files cited below read where a judgment depends on content.

## Items

### 1. The package is not installable; 31 files patch `sys.path`
There is no `pyproject.toml`. Tools and tests start with `sys.path.insert(0, ...)` (31 files), and several tools use `try: from tools.observation_io import ... except ImportError:` to work from two working directories (`tools/assemble_firehole_obs.py`, `tools/fetch_firehole_obs.py`, `tools/fetch_snotel_obs.py`, `tools/fetch_met_forcing.py`). `tools/` has no `__init__.py`. The package itself imports from `tools` (`microclimate.py` imports `tools.fetch_met_forcing`), which works only when the repository root is on the path.
### Fix
Add `pyproject.toml` (setuptools, package `yellowstone_python`, version from `yellowstone_python/__init__.py`, optional-dependency groups `science`, `fetch`, `dev`; pytest `testpaths`). Install editable in `.venv`. Remove every `sys.path.insert` and dual-import block. Move the library parts that the package or several tools import into the package (item 4) so the package never imports `tools`. Tools run as `python -m tools.<name>` with `tools/__init__.py`, or as console scripts declared in `pyproject.toml`.
### Test
`rg -n 'sys\.path\.insert' yellowstone_python tools tests` returns nothing; `python -c "import yellowstone_python.microclimate"` succeeds from a directory outside the repository; the suite passes from the repository root and from `tests/`.
### Cost
Medium.

### 2. `build.py` is one 3,093-line module
Outline (line numbers): configuration and validation 47-240; input loading and hashing 241-688; replay setup and solver run 689-817; per-domain stage runners 818-1423 (shading, hyporheic, solutes, oxygen, periphyton, predation, outflow chain, Excelsior override, outflow foodweb, mat validation, pool ramps); `simulate_all` 1424-2088 (665 lines in one function); `render_all` and `main` 2089-2182; manifest 2183-2400; `_write_variant_and_gate` 2408-2709 (300 lines); fragment and integration sidecars and the mat appearance writer 2710-3093. Section banners inside `simulate_all` still carry milestone tags (`# --- M03 shells ---` and six more).
### Fix
Turn `build.py` into a package `yellowstone_python/pipeline/` (or keep the name `build/` so `python -m yellowstone_python.build` still works through `__main__.py`):
- `config.py` (load, normalize, validate; uses fixes-46 checks),
- `inputs.py` (load and hash inputs),
- `stages/` with one module per domain, each exposing `run(state, cfg) -> state` and declaring the keys it reads and writes,
- `pipeline.py` with an ordered stage list that replaces the body of `simulate_all`,
- `manifest.py`, `sidecars.py`, `render.py`.
The stage list with declared reads and writes is the same table the live engine needs (fixes-43 item 9); build it once and import it there.
### Test
Build 2a8c8948128c configuration rebuilt before and after: identical `BUILD.json` dependency hashes for inputs, identical outputs except the code hash; a test asserts every stage's declared reads are written by an earlier stage.
### Cost
Refactor (the largest item in this document; do it after fixes-46 so the moved code is already clean).

### 3. A flat package of about 50 modules
A public reader sees `fish.py`, `piscivores.py`, `thermal_curves.py`, `aquatic_foodweb.py`, `river_oxygen.py`, `periphyton.py` and `river_shading.py` beside `outflow_network.py`, `microbial_mats.py`, `mat_appearance.py`, `llm_backend.py` and `gen_flora.py`, with nothing showing which belong together. The river solver package is named `replay/`, which describes one of its outputs.
### Fix
Group by domain, one subpackage per commit, all imports updated in the same commit (nothing outside the repository imports these modules; Godot reads JSON):
- `river/` (rename of `replay/`): transport, mapped world, hydraulics, surface flux, solutes, calibration, uncertainty, observation model, benchmarks.
- `aquatic/`: `fish`, `thermal_curves`, `piscivores`, `aquatic_foodweb`, `river_oxygen`, `periphyton`, `river_shading`.
- `thermal_features/`: `outflow_network`, `outflow_thermal`, `outflow_foodweb`, `microbial_mats`, `mat_appearance`, `mat_validation`, `pool_crust`, `geochemistry`, `ground_heat`.
- `land/`: `vegetation`, `grazers`, `snow_season`, `snow_validate`, `snow_energy`, `evapotranspiration`, `overland_flow`, and the `hydrology`, `overland`, `groundwater` providers with `ssurgo_loader`.
- `atmosphere/`: `microclimate`, `steam_microclimate`, `time_utils`.
- `registry/`: `claims`, `param_registry`, `equations`, `run_mode`, `coupling`.
- `census/`: `canopy_census`, `census_validate`.
- `service/`: `llm_backend`, `analysis_store`, and the live engine from fixes-43.
- Top level: `pipeline` (item 2), `publish`, `compare`, `study_mode`.
Update `AGENTS.md`, `README.md`, the `/ystone` roadmap and the dashboard inventory paths in the same commits.
### Test
The suite passes after each move; `python -m yellowstone_python.<cli>` entry points documented in `README.md` still run with `--help`.
### Cost
Refactor (mechanical, wide).

### 4. Library code living in `tools/`
`tools/observation_io.py` is imported by five tools and has its own `atomic_write_json`; `tools/fetch_met_forcing.py` is imported by `microclimate.py`; `tools/usgs_nwis.py` (1,001 lines: HTTP and retry, parsing, hashing, CLI) is imported by `tools/assemble_firehole_obs.py`; `tools/scenario_constants.py` is imported by two runners.
### Fix
Move the importable parts into `yellowstone_python/observations/` (`usgs.py` client and parsers, `met.py` Open-Meteo client, `bundles.py` for the shared bundle I/O, using fixes-46 `common/io`); keep each tool a thin CLI over them. Scenario constants move with the scenario runner (item 6).
### Test
No module in `yellowstone_python/` imports `tools`; the fetch tests run offline against the package modules.
### Cost
Medium.

### 5. Small files that belong together
- `atmospheric_constants.py` (11 lines: site elevation and pressure) and the site coordinates scattered over six modules (fixes-46 item 3): one `common/site.py`.
- `common/units.py` (converters, plus deprecated `gpm_to_m3s` and `m3s_to_gpm` aliases that warn on each call, `units.py:43-60`) and `common/hydro_units.py` (pint-backed range checks): one `common/units.py`; drop the deprecated aliases after updating callers, since a public first release has no external callers to protect.
- `common/validate.py` (reach chain, heat ledger and provenance checks used by `validation/checks.py`): move those functions into `yellowstone_python/validation/`, leaving `common/` for helpers (`checks`, `io`, `coords`, `site`, `units`, `provenance`).
- `yellowstone_python/validation/` (gates) and the top-level `validation/` directory (census sampling data: `blind_crops/`, `census_frozen.json`, `sampling_plan.json`) share a name and are unrelated: move the data to `data/census_validation/` and point `census_validate.py` at it.
### Test
Imports updated; suite passes; `rg -n 'atmospheric_constants|hydro_units|gpm_to_m3s\b' yellowstone_python tools tests` returns nothing.
### Cost
Cheap.

### 6. Three overlapping scenario runners
`tools/run_hot_lowflow.py` (257 lines), `tools/run_hot_lowflow_tributary_refuge.py` (268) and `tools/run_hot_lowflow_with_tributaries_v2.py` (433) share setup and each define `_window` (`run_hot_lowflow.py:135`, `run_hot_lowflow_tributary_refuge.py:94`). The `_v2` suffix is a status suffix the naming standard excludes. `run_hot_lowflow_with_tributaries_v2.get_fallback_tributary_data` (`:45`) substitutes authored tributary values when the measured file is absent, labeled `scientific_use: prohibited`; the substitution is still a fallback that lets a run complete on data the run was meant to replace.
### Fix
One `tools/hot_lowflow.py` (or `python -m yellowstone_python.scenarios.hot_lowflow`) with subcommands `mainstem`, `tributary-pockets` and `measured-tributaries`, shared setup and one `_window`. `measured-tributaries` fails with the missing path when the measured file is absent; the authored pockets are the `tributary-pockets` subcommand, stated as authored. Constants from `scenario_constants.py` move into the module. Rewrite `tests/test_scenario_runners.py` to run the subcommands on a synthetic replay instead of searching source text (fixes-50 item 2).
### Test
Each subcommand reproduces its current artifact on the pinned inputs (`derived/aquatic_hot_lowflow.json`, `derived/aquatic_hot_lowflow_tributary_refuge.json`).
### Cost
Medium.

### 7. Command-line modules and library modules are mixed without a rule
Package modules with a `main()` and no importer other than their test: `snow_energy.py`, `census_validate.py`, `review_proposals.py`, `publish.py`; modules imported only by tools or tests: `gen_flora.py`, `gen_trail_mask.py`. Library modules such as `aquatic_foodweb.py`, `replay/river_transport.py` and `replay/calibrate.py` also carry a `main()`.
### Fix
Rule: a module either is a library (no `argparse`) or is a CLI (`main() -> int`, `if __name__ == "__main__": raise SystemExit(main())`, logic imported from libraries). Keep `python -m` entry points that `README.md` documents; move the CLI bodies of library modules (`aquatic_foodweb.main`, `river_transport.main`, `river_world.main`, `calibrate.main`) into `cli/` modules or console scripts. Move `gen_flora.py` and `gen_trail_mask.py` with `review_proposals.py` to an `authoring/` subpackage, since they write world placements and are not part of the simulation.
### Test
`rg -l 'import argparse' yellowstone_python` lists only CLI modules.
### Cost
Medium.

### 8. Output conventions differ by module
Console output: library modules call `print` (`canopy_census.py`, `census_validate.py`, `build.py`, `publish.py`), others use `logging`, and `tools/fetch_yellowstone_tributaries.py:17` configures logging at import. Test style: 14 test files use `unittest.TestCase` (most of them in `replay/tests/`), the rest use pytest functions.
### Fix
Libraries log through `logging.getLogger(__name__)`; CLIs configure logging in `main()` and print results. Tests: pytest functions throughout (fixes-50 item 3).
### Test
`rg -n '^\s*print\(' yellowstone_python --glob '!**/cli/**'` returns only `main()` bodies.
### Cost
Cheap to medium.

## Order
Item 1 first (it makes every later move testable from anywhere), then 5 and 6 (small, visible), then fixes-46, then 4, 7 and 8, then 3, then 2. Items 2 and 3 should not overlap in time with logic fixes to the same files.
