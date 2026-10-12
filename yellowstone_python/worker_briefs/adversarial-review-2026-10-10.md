# Adversarial review brief: pycl session of 2026-10-10 (O. Zeugen)

You are reviewing, not building. Read-only: do NOT edit, create, or delete
any file except your report. Project cwd: `yellowstone/yellowstone_python/`.

## Method (/invalidate procedure)

Extract each factual claim below, verify it INDEPENDENTLY (recompute from
the artifacts with your own commands — never trust the cited command's
output prose), and report per-claim verdicts: SUPPORTED / CONTRADICTED /
NOT TESTED, each with the exact command/query and number. Seek a
disconfirming check for every important claim; a zero exit or passing test
proves only its explicit observation. Calibrate severity: wrong numbers in
README (high), weak tests that cannot fail (medium), style (low — skip it).

## Claims to check (from the session's reports + README)

1. SNOTEL fit: 609 k=1.0/wind=0.0 holdout RMSE 112mm vs nulls 293/472;
   924 k=0.75/wind=0.0 holdout 45mm vs 179/194. Recompute from
   `derived/snow_snotel_fit_2026-10-10.json` AND re-derive spot values from
   `derived/snotel_obs_2026-10-10.json` independently (unit conversions,
   split dates, null definitions). Check: is wind=0.0 a boundary optimum
   the grid cannot see past? Is k=1.0 at 609 near the 0.5 floor? Does the
   train split (Oct-Feb, accumulation-dominated) actually identify melt
   params, or does the holdout do all the work?
2. Hot low-flow: +2357m shift is DOWNSTREAM (chainage convention!), drive
   fires 0→1, feeding 0.66→0, no sub-24C cell among 276, diet emergent
   0.40→0.70, emergence −221, dipper +1.85. Verify chainage direction from
   the replay cells yourself; verify the trout-selected cell really is the
   max-U cell (recompute U for all cells); check the lethal-flag claim
   (27.81C vs UILT 26.0). Is "no refuge on the map" actually true at every
   frame, or only in the full-run mean (chronic-scenario framing)?
3. Shear null: mapped shear uniform 15.08Pa (273 cells + 3 null) under the
   20Pa default → default runs identical to disturbance-free. Verify from
   the replay + a fresh `run_foodweb` call; verify the sensitivity numbers
   (thr 10 → emergence −30%, refuge to cell_00024; thr 5 → −51%, dipper
   −27%). Is the "uniform tax reshuffles refuge via nonlinear regrowth"
   mechanism right, or is something else moving the refuge?
4. Fischer-D: D85 control refuge s=2236 vs D1 s=2873 (636m upstream,
   ecology nil); hot-at-D85 repeats D1 outcome. Recompute; check the two
   shifts are not directly comparable (different baselines) and confirm the
   report says so.
5. Game clock: system default, three overrides, baseline pinned, build
   byte-identical. Verify byte-identity claim for foodweb/variant/replay
   between builds `8b9199d0fb0a` and `36af79bcf281` with `cmp`; verify
   season.json sources say config/config for the pinned build.
6. Tests: are the "optimizer check" tests labeled inverse-crime (yes — but
   verify the label is accurate and the tests would FAIL if the optimizer
   broke, e.g. mutate the grid and watch)? Do the ledger tolerances
   (0.01 chained, 0.05 spot) derive from measured rounding or were they
   loosened to pass? Is the wind-override test (`out_none == out_zero`)
   circular (same code path both sides)?
7. Provenance: every new derived artifact carries a status in the
   `tools/audit_provenance.py` vocabulary — run it. Every README number
   must match an artifact value exactly; list any drift.
8. Out-of-scope check: `tools/` files dated 2026-10-10 00:02–00:14
   (plot_fit, audit_provenance, fetch_met_forcing, etc.) were written by a
   concurrent lane, NOT this session — confirm none of the claims above
   depend on those files, and flag it if any do.

## Deliverable

Write `yellowstone/yellowstone_python/worker_briefs/review-verdict-2026-10-10.md`:
per-claim verdict table with evidence (command + number), a severity-ranked
issue list, and one paragraph on whether the session's headline conclusions
stand. Then reply with the 5-line summary and stop. No follow-up work.
