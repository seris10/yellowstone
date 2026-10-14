# fixes-48: what the public repository shows a reader

Scope: tracked files in the `yellowstone` repository (remote `seris10/yellowstone`, visibility PUBLIC per `gh repo view`), judged as the first thing a reader sees of a project meant to demonstrate Python in science. Covers stray files, internal process documents, absolute paths, documentation voice, and missing repository metadata. Audit 2026-10-13 at the request of KJR.
Method: the git index of tracked files (two commits on record, 92e1706 and 858e497; 435 paths currently modified or untracked), `git grep` for home-directory paths and credential references, and the README files read in full.

## Items

### 1. Scratch and handoff files tracked at the Python project root and inside the package
Tracked: `yellowstone_python/temp_fix_snow_season.py` (18 lines, a copy of `snow_season.date_to_season`, which exists at `snow_season.py:19`; nothing imports it), `SECURITY_HARDENED_TRIBUTARY_IMPL.md`, `TASK_1_TTRIBUTARY_COLD_REFUGE_SUMMARY.md`, `progress.md` (a fixes-16 tracker), `worker_briefs/` (6 review briefs and verdicts), `research_notes/` (26 files, mostly research prompt sets and phase summaries), `yellowstone_python/yellowstone_python/HANDOFF.md` and `HANDOFF_TRACKER.json` (session handoff inside the importable package), `yellowstone_python/yellowstone_python/stubs/README.md`, `yellowstone_python/yellowstone_python/derived/met.json` (a data file inside the package), and `.opencode`.
### Fix
- Remove from the repository (move to `trash`): `temp_fix_snow_season.py`, `stubs/`.
- Move to `yellowstone_python_spec/` (internal working documents): `progress.md`, `worker_briefs/`, `research_notes/`, `SECURITY_HARDENED_TRIBUTARY_IMPL.md`, `TASK_1_TTRIBUTARY_COLD_REFUGE_SUMMARY.md`, `yellowstone_python/HANDOFF.md`, `HANDOFF_TRACKER.json`.
- Move `yellowstone_python/derived/met.json` to the project `derived/` and update its reader.
- Add `.opencode/`, `.pytest_cache/` and `.venv/` to `.gitignore`.
Then decide whether `yellowstone_python_spec/`, `archive/` (32 tracked files) and `dashboard/` belong in the public repository at all (item 7).
### Test
The tracked files directly under `yellowstone_python/` are `README.md`, `AGENTS.md`, `requirements.txt`, `pyproject.toml` and `.gitignore`, with every other tracked path inside `yellowstone_python/`, `tools/`, `tests/`, `configs/`, `notebooks/`, `derived/` or `data/`; the suite and build pass.
### Cost
Cheap.

### 2. Absolute home-directory paths in tracked files
`git grep -l 'owner home directory'` finds 159 lines: 15 files under `yellowstone_python_spec/fixes`, 5 under `ai-tells`, the tooling specs, `00_OVERVIEW_AND_VERDICT.md`, and three published data files the game loads: `yellowstone_midway/data/asset_manifest.json`, `firehole_control.json`, `firehole_pulse.json`. The project rule is no absolute paths in code, configs, tests or docs.
### Fix
Data files: the writers record paths relative to the project root (find the writer for each key that holds a path; the replay pair is written by the study runner and `asset_manifest.json` by the bake tools). Spec documents: replace with paths relative to the project root.
### Test
`git grep -n 'owner home-directory prefix'` returns nothing.
### Cost
Cheap.

### 3. Credential reference in a tracked deploy script
`dashboard/deploy.sh:16` exports `CLOUDFLARE_API_TOKEN` from a password-manager reference (`password-manager reference: ...`). It contains no secret value, but it publishes the vault item name and account label.
### Fix
Read the token from the environment in the script (`: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"`) and keep the vault lookup in a local, untracked wrapper; or untrack `dashboard/deploy.sh`.
### Test
`git grep -n 'password-manager reference: '` returns nothing.
### Cost
Cheap.

### 4. No license, no top-level README, no citation file
The repository root has none of `LICENSE`, `README.md` or `CITATION.cff`. Code licensing, data licensing (NAIP, USGS, NRCS and NPS sources are public domain or federal; the vendored Yale Bright Star Catalog has its own terms) and the illustrative status of results are not stated at the root.
### Fix
Add `LICENSE` (owner's choice of code license), a short root `README.md` (what the project is; the three parts: Python model, Godot world, atmosphere; how to run the build and the game; the illustrative and `not_yet_accepted` status of claims; data sources with licenses), and `CITATION.cff`. Data provenance per source already exists in the sidecars; the README links to it.
### Test
Files exist; README commands run as written on a clean checkout.
### Cost
Cheap (license choice is the owner's).

### 5. README voice and stale statements
`yellowstone_python/README.md`: em dashes (`:1`, `:26`, `:42`, `:85`), ranges written with U+2013 en dashes and a U+00D7 multiplication sign (the snow window dates, `Oct` to `Feb`, `1.4` to `2x`), operational timestamps (`verified live 2026-10-10`, `:49`), defensive asides aimed at a reviewer (`reported honestly` `:67`, `Caveats (not hidden)` `:84`, `Null result, stated plainly` `:179`), process labels (`backlog A`, `backlog B`, `stretch C`, `B3`), a claim that Godot hot-loads at F5 (`:32`, false, fixes-44 item 1), and section order that puts results (snow, hot low flow, tributaries, shear, Fischer) before "Run it". `yellowstone_python/yellowstone_python/replay/README.md:3` opens with "(audit Phase 2 core)" and uses Unicode arrows throughout. `AGENTS.md` uses em dashes in its own headings while its section 2 forbids them.
### Fix
Restructure `yellowstone_python/README.md`: what it is; install and run; model components (one paragraph each, naming the module and the `equations.py` component id); results as a "Findings" section with each result's run mode, status and artifact path; limitations. ASCII hyphens, "to" in ranges, no operational dates in prose (dates go in artifact metadata), no process labels. Same pass on `replay/README.md` and `AGENTS.md` headings. Extend `tools/check_comment_style.py` to Markdown (fixes-49 item 6) so this holds.
### Test
The Markdown rules in fixes-49 report zero findings on the three files; every command in the README runs.
### Cost
Cheap to medium.

### 6. Committed figures and notebooks
`figs/` holds 8 tracked PNGs (three figures appear twice, under `figs/` and `figs/notebook/`). `notebooks/reach_fit.ipynb` and `census_explorer.ipynb` are tracked; their markdown cells use em dashes and Unicode arrows, and saved outputs, if present, go stale with every rebuild.
### Fix
Keep the notebooks (they are the clearest public demonstration of the fitting workflow), strip outputs on commit (`nbstripout` as a pre-commit hook, or `jupyter nbconvert --clear-output`), and apply the comment house style to their markdown. Generate `figs/` from `tools/plot_fit.py` or the notebook with a documented command, drop the duplicate `figs/notebook/` copies, and either untrack `figs/` or keep only the figures the README embeds.
### Test
`nbstripout --verify` (or a test that loads each notebook and asserts empty outputs) passes; README image links resolve.
### Cost
Cheap.

### 7. What belongs in the public repository
The repository carries the Godot world (679 tracked files), the Python project (274), the internal spec and fixes queue (137), `archive/` (32), `research/` (21), `dashboard/` (8). The spec and fixes documents are working notes written for agents; they reference internal roles, sessions and paths and read as process rather than science.
### Fix
Owner decision. Recommendation: keep `yellowstone_python/`, `yellowstone_midway/`, `yellowstone_atmosphere/`, `hydrology/` and `research/` (sources) public; move `yellowstone_python_spec/`, `archive/` and `dashboard/` to a private repository or untrack them, and keep a short public `docs/` with the design notes a reader needs (model overview, coupling map, validation results). History already contains these files, so removing them from history needs a rewrite; untracking going forward is the reversible first step.
### Test
The top-level directories in the tracked-file index match the decision.
### Cost
Cheap to decide; history rewrite optional.

## Order
Items 3 and 2 first (published references to the owner's machine and accounts), then 1, 4, 6, 5; item 7 once the owner decides.
