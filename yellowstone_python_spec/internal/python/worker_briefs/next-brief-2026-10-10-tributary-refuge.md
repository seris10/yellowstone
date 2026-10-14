# Next-session brief: tributary cold-refuge cells + second-window snow test

Project: `yellowstone/yellowstone_python/` (cwd). Suite is green
(322 passed); build verified. Read this whole brief before touching code.
Never commit unless asked. Derived artifacts are history — never rewrite
them; new runs get new filenames.

## State you inherit (verify, do not re-derive)

- Snow validation vs SNOTEL WY2026 is frozen: `derived/snotel_obs_2026-10-10.json`
  (bundle), `derived/snow_snotel_fit_2026-10-10.json` (fit), method
  `yellowstone_python/snow_validate.py`, fetcher `tools/fetch_snotel_obs.py`.
  Fitted: 609 k=1.0/wind=0.0 holdout RMSE 112mm; 924 k=0.75/wind=0.0 holdout
  45mm. Status `fitted_not_validated_single_window` everywhere.
- Hot low-flow: `tools/run_hot_lowflow.py`, artifacts
  `derived/aquatic_hot_lowflow_2026-10-10.json` (+2357m DOWNSTREAM hold,
  drive fires, no sub-24C cell on the map). Fischer-D85 repeat confirms it.
- Shear coupling wired with honest null (uniform 15.08Pa shear).
- Game clock: system default + `clock_hour` / `snow.season` / `snow.as_of_date`
  overrides; baseline pinned.
- Full methods + numbers + caveats: README sections "Snow validation",
  "Hot low-flow", "Shear-to-disturbance", "Fischer-D", "Game clock".

## Primary: tributary cold-refuge cells

The hot scenario's headline limitation: all 276 mainstem cells sit above
24C, so "refuge" can only be least-bad food and the model cannot show an
upstream escape. Give it the chance:

1. Find cold lateral inflows in the baseline ecosystem (check lateral
   sources / tributary temps in the world data; Fairy Creek and equivalents
   — discover actual values, do not invent). Determine which run colder
   than 24C under hot-lowflow conditions and where they join (chainage).
2. Extend the foodweb landscape with tributary refuge cells (confluence
   position, cold temperature, small habitat area for food scaling —
   state every assumption with provenance authored). Minimal honest design:
   N cold cells appended to the landscape the trout can select.
3. Re-run the hot-vs-control comparison at D1. Report: does the refuge flip
   upstream to a cold cell? At what tributary temperature/size threshold
   does it flip (sensitivity sweep, 3+ values)? Diet, emergence, dipper as
   before. If it never flips, say so with the U-math showing why.
4. Offline synthetic tests for the new landscape code (no network in unit
   tests). Keep suite green; re-run full build; confirm or update recorded
   numbers in README with new values. Status illustrative throughout.

## Stretch: second-window snow test (true out-of-sample)

Do NOT refit. Fetch WY2025 (2024-10-01–2025-07-31) with
`tools/fetch_snotel_obs.py --begin/--end` into a NEW bundle file, run
`yellowstone_python.snow_validate` with the FROZEN k/wind params
(hardcode or flag-override — implement a `--fixed-params` path rather than
hand-editing), and report holdout RMSE vs the WY2026 numbers. If it holds,
promote status toward validated; if not, report the delta honestly.

## Verify before finishing

`python3 -m pytest tests yellowstone_python/replay/tests -q` (322+ new),
full `build`, re-run any experiment whose code path you touched.
Every coefficient keeps provenance (measured/fitted/transferred/authored);
no wolves-elk-willow sliders, no fish in hot pools, no mortality sims.
