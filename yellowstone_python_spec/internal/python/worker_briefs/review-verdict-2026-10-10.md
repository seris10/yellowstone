# Adversarial review verdict: pycl session 2026-10-10 (O. Zeugen)

Read-only review. All numbers below were recomputed with independent commands
against the artifacts; cited commands are the actual checks run, not prose
quotes from session reports. Project cwd: `yellowstone/yellowstone_python/`.

## Per-claim verdict table

### 1. SNOTEL fit (609 k=1.0/w=0.0 112 vs 293/472; 924 k=0.75/w=0.0 45 vs 179/194)

| Sub-claim | Verdict | Evidence (command + number) |
|---|---|---|
| Holdout RMSE 112 / nulls 293 / 472 (609) | SUPPORTED | `fit['sites']['609']['holdout_swe_mm']['rmse']=112.02`, `null_persistence=293.29`, `null_nomelt=471.58`; independent `daily_swe_series` + `score_paired_series` recompute = **112.02 / 293.29 / 471.58** exactly |
| Holdout RMSE 45 / nulls 179 / 194 (924) | SUPPORTED | artifact `45.04 / 179.04 / 194.36`; recompute = **45.04 / 179.04 / 194.36** exactly |
| Fitted params k=1.0/w=0.0, k=0.75/w=0.0; train 10.52 / 7.88 | SUPPORTED | `fit_snow_params` refit from `snotel_obs` bundle returns **(1.0, 0.0, 10.52)** and **(0.75, 0.0, 7.88)** exactly |
| Unit conversions (in→mm ×25.4, F→C) | SUPPORTED | spot: `45.1F→7.2778C` code `air[0]=7.2778`; `0.1in→2.54mm` code `prec[0]=2.54` |
| Split dates (train 151 / holdout 153, split 2026-03-01) | SUPPORTED | `train_holdout_split` on sorted bundle dates → **151/153**, both sites, 304 days `2025-10-01–2026-07-31` |
| Null definitions (persistence = last-train-obs; no-melt k=0 at fitted wind) | SUPPORTED | `validate_site` source lines confirm; persistence recompute **293.29/179.04**, no-melt **471.58/194.36** match |
| Gap counts (609 0/1, 924 1/0) | SUPPORTED | `prepare_forcing` recompute `{'tavg_filled':0,'prcp_zeroed':1}` / `{1,0}` = artifact |
| wind=0.0 is a boundary optimum the grid cannot see past | SUPPORTED (concern valid) | 609 at k=1.0: train RMSE **10.52 (w=0) → 112.08 (w=0.02) → 211.01 (w=0.15)**; 924 same shape (7.88 → 51.23 → 92.56). `WIND_GRID=(0.0,0.02,0.05,0.1,0.15)` — strictly increasing away from the **grid edge**; negative wind (net gain) untestable |
| k=1.0 at 609 "near the 0.5 floor" | CONTRADICTED (as a worry) | k-neighbors at w=0 (609): **0.5→23.71, 0.75→13.76, 1.0→10.52, 1.25→11.04, 1.5→11.25** train RMSE — minimum is interior, 2 grid steps above floor |
| Train split identifies melt params vs holdout does the work | CONTRADICTED (method limitation, HIGH interest) | Holdout RMSE at w=0 **decreases past the train pick**: 609: k=1.0→112.02 but **k=1.5→44.76**; 924: k=0.75→45.04 but **k=1.25→18.34, k=1.5→18.56**. Train (Oct–Feb: mean −3.2/−2.8C, only 27%/36% days >0C) is accumulation-dominated with a shallow minimum (10.52 vs 11.04); melt-season k is set by the holdout the report evaluates on. Reported holdout RMSEs are thus **pessimistic vs holdout-optimal k**; "fitted k" is an accumulation-fit. README's caveats (bias +67mm, peak +48d late, wind-boundary) already disclose symptoms — credit |

### 2. Hot low-flow (+2357m downstream, drive 0→1, feeding 0.66→0, no sub-24C cell, diet 0.40→0.70, −221/+1.85)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| +2357m shift is DOWNSTREAM (chainage convention) | SUPPORTED | `mapping.chain_order=[river_5998_0…river_5856_0]`, `s=0` upstream → max 5469.78; control s=**2872.50** → pulse s=**5229.90**, recomputed shift **2357.399** = artifact `2357.4` |
| Drive 0.0→1.0, feeding 0.657→0.0, U −0.025→−1.227 | SUPPORTED | fresh `run_foodweb(thermal_landscape(hot))` trout = **cell_00263 s=5229.90 T=27.81 U=−1.227 feeding=0.0**; control `run_foodweb(thermal_landscape(base))` = **cell_00145 s=2872.50 T=17.37 U=−0.025 feeding=0.657 drive=0.0** |
| Trout-selected cell is max-U over all cells | NOT TESTED | `run_foodweb` was re-executed end-to-end and reproduces the reported best cell, but an independent per-cell U re-sort from final food states was not performed (foods are dynamic inside the run). Selection logic not disproven; just not independently re-sorted |
| Lethal flag (27.81C vs UILT 26.0) | SUPPORTED | `thermal_performance(27.81,brown_trout)` = **lethal_flag=1, refuge_drive=1.0, feeding=0.0**; at 25.0 flag=0 (threshold behavior confirmed) |
| "No refuge on the map" (no sub-24C cell among 276) | SUPPORTED (stronger than README) | Full-run means min **25.045** max **28.499**, 0/276 below 24; per-frame minima over all **721 frames** = **24.951–25.092**, **0 frames** with any sub-24 cell. True at every frame, not just the mean — chronic-scenario framing concern is answered: no transient refuge either |
| Diet emergent 0.40→0.70 | SUPPORTED | `trout_diet_at_temp(17.37)={'emergent':0.3975}`, `(27.81)={'emergent':0.7}` |
| Emergence −221, dipper +1.85 | SUPPORTED | base emergence **1027.562** vs hot **806.614** → **−220.9487**; dipper **13.510→15.362** → **+1.8519** |
| In-chain water 25.1–28.5 mean 26.6 (README) | SUPPORTED (approx) | Means recomputed 25.05–28.50; frame0 25.09–28.54; README range/mean consistent to rounding (mean itself not recomputed) |

### 3. Shear null (uniform 15.08Pa, 273+3, default == disturbance-free; thr10 −30% → cell_00024; thr5 −51%/−27%)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| 273 cells + 3 null | SUPPORTED | `Counter` on `thermal_landscape`: **177+39+34+23=273 non-null + 3 None** (baseline and hot identical) |
| Mapped shear "uniform 15.08Pa" | CONTRADICTED | Distinct reach-averaged values: **15.0787×177, 13.6167×39, 12.3265×34, 8.1226×23, None×3**; mean **13.94**, not 15.08. Only the largest reach is 15.08 |
| Default runs identical to disturbance-free | SUPPORTED | `max(shear_to_disturbance(s,20.0))=0.0`; `run_foodweb(land0,thr=20.0)` emergence **1027.6** == `thr=None` **1027.6**, same refuge cell_00145 |
| thr10 → emergence −30% (1028→720), refuge cell_00024 (s=470) | SUPPORTED (numbers) | `thr=10.0` → emergence **720.0**, trout **cell_00024 s=470**, dipper 13.50 |
| thr10 → "uniform 0.51 disturbance" | CONTRADICTED | Actual disturbances at thr10: **{0.0, 0.2326, 0.3617, 0.5079}** — four levels, not uniform |
| thr5 → −51%, dipper −27% | SUPPORTED | `thr=5.0` → emergence **500.1** (−51.3%), dipper **9.90** (−26.7%), refuge cell_00001 s=21 |
| Mechanism "uniform tax reshuffles refuge via nonlinear regrowth, not spatial contrast" | CONTRADICTED (misleading) | Shear **does** vary spatially by reach (4 levels + nulls), so spatial contrast exists; refuge move cannot be attributed to nonlinearity alone. `run_foodweb` docstring itself now notes the tax is global-*ish* "until cell-scale hydraulics vary" — but reach-scale contrast is already present |

### 4. Fischer-D (D85 control s=2236 vs D1 s=2873, 636m upstream, ecology nil; hot-at-D85 repeats D1)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| Dispersion-alone shift 636m upstream (2873→2236, same 17.4C, drive silent) | SUPPORTED | `run_foodweb` D1 trout **cell_00145 s=2872.50** vs D85 **cell_00113 s=2236.05** → **−636.45**; artifact `refuge_shift_m=-636.4`; temps 17.37/17.39, drive 0/0 |
| Ecology nil (+1.5, +0.01) | SUPPORTED | emergence diff **+1.4825**, dipper **+0.0066** (≈+0.01 after rounding) |
| Hot-at-D85 repeats D1 (+2357m, −221, +1.85) | MISLEADING (omission) | Hot-D85 vs its own D85 baseline: trout **s=5229.90**, shift **+2993.8** (artifact `refuge_shift_m=2993.8`), emergence **−219.79**, dipper **+1.849**. README prose quotes **"+2357m"** — that is D1's shift, not hot-D85's. Emergence/dipper round to the same values, so "same qualitative outcome" holds, but the report never states hot-D85's own +2994m shift and does not flag the baseline difference in prose (artifacts do: hot-D85 control = D85 s=2236) |

### 5. Game clock (system default, three overrides, baseline pinned, byte-identical)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| river_replay byte-identical 8b9199d0fb0a vs 36af79bcf281 | SUPPORTED | `cmp …/river_replay.json` → **identical** |
| ecosystem.variant byte-identical | SUPPORTED | `cmp …/ecosystem.variant.json` → **identical** |
| aquatic_foodweb byte-identical | CONTRADICTED | `cmp` **differs at char 52983**: one added line `"shear_coupling": "bed_shear_pa -> disturbance ramp 0@20.0Pa … mean applied 0.0000 over 276 cells (3 shear-null)"`. Code rev also differs (`9b2e838` → `4e9d45b`) — expected, since the session added the coupling between builds |
| season.json sources config/config for pinned build | PARTIAL | Both builds: `clock_source=config` + `season_source=config` (pinned 16.2h/summer from `configs/baseline.yaml` confirmed) — but `date_source=system_clock`, and `as_of_local_date` differs (**2026-10-09 vs 2026-10-10**). Pinned 2/3: numbers reproduce, date stamp does not |
| System default + three overrides | NOT TESTED (sighted only) | `clock_hour`/`as_of_date`/`season` keys sighted in `build.py`; live-clock fallback not executed here |

### 6. Tests (inverse-crime label, ledger tolerances, wind-override circularity)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| "Optimizer check" tests labeled inverse-crime | SUPPORTED | `test_fit_recovers_synthetic_params_optimizer_check_only` comment: **"Inverse crime by construction: identical model generates and fits… says nothing about the real snowpack"** — label accurate |
| Tests would FAIL if optimizer broke | SUPPORTED | Mutation probe: grid without truth → best **(2.5, 0.1, 63.33)** ≠ (3.0, 0.05, 0.0), assert fires. Test is load-bearing for the optimizer |
| Ledger tolerances (0.01 chained, 0.05 spot) loosened to pass | CONTRADICTED (tolerances derive from rounding) | `run_season` rounds state to **1e-3**; measured 1-day residual **0.0**, 10-day spot **5e-05** — both ≪ tolerances. 0.01 = 20× the documented 5e-4/day, i.e. headroom, not a fit-to-pass |
| Wind-override test circular (`out_none == out_zero`, same path both sides) | CONTRADICTED (not vacuous) | `run_season`: `wl = m["wind_loss"] if wind_loss is None else float(wind_loss)` — the None→authored-0.15 branch **is** the load-bearing mapping under test; downstream path shared by design. Second half (`wind_loss=0.02` retains more pack than 0.15) exercises distinct values. Weak test, but not circular |

### 7. Provenance (status vocabulary; README numbers match artifacts)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| Every new derived artifact carries an in-vocabulary status | SUPPORTED | `tools/audit_provenance.py`: 22 files, only 2 FAILs — both **pre-existing** `sinter_*_2026-10-09.json` (absent status), none from 2026-10-10. All eleven `*2026-10-10.json` bundles carry statuses (`fitted_not_validated_single_window` / `measured_remote_not_calibrated` / `illustrative_not_calibrated` / `numerical_experiment_not_field_validation`) |
| Every README number matches an artifact value exactly | SUPPORTED to rounding; two prose drifts | 112/112.02, 293/293.29, 472/471.58, 45/45.04, 179/179.04, 194/194.36, +67/67.04, 48d/48, 27.8/27.81, 2357/2357.4, −221/−220.95, +1.85/1.8519 — all rounding-only. Real drifts: shear "uniform 15.08" (claim 3) and hot-D85 "+2357m" (claim 4) |

### 8. Out-of-scope check (tools/ dated 2026-10-10 00:02–00:14 by a concurrent lane)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| 00:02–00:14 tools written by concurrent lane, claims don't depend on them | SUPPORTED | `stat`: `execute_notebook 00:02`, `audit_provenance 00:09`, `fetch_firehole_obs 00:11`, `usgs_nwis 00:14`, `check_terrain/compare_bundles/validate_obs_bundles/plot_fit/fetch_met_forcing 00:16–00:17`. None is imported by `snow_validate.py` / `aquatic_foodweb.py` / `fetch_snotel_obs.py` / `run_hot_lowflow.py` (only docstring mention of the audit vocabulary). `run_hot_lowflow.py` itself is **00:20** (this session); `fetch_snotel_obs.py` is prior-session (09-23:31). No claim depends on the concurrent-lane files |

## Severity-ranked issue list

1. **High — SNOTEL train/holdout identifiability (claim 1).** Train-selected k is pessimistic on the melt holdout at both sites (609: 112 vs 44.76 at k=1.5; 924: 45 vs 18.34 at k=1.25). The Oct–Feb train split cannot identify melt energy; the holdout does the work while also serving as the reported score. README discloses the symptoms (bias, late peak, wind boundary) but not this mechanism. Fix: report holdout-as-selection honestly, or fit on a melt-inclusive split / two-season validation; keep the "beats both nulls" framing, which survives.
2. **High — Shear "uniform 15.08 Pa" misstatement (claim 3).** Artifact has 4 reach-level shears + nulls; "no spatial contrast" and "uniform 0.51 disturbance" are factually wrong, and the no-contrast conclusion is wrong at reach scale. The null result (default == disturbance-free) still stands because all values sit below 20 Pa, but the mechanism sentence needs rewriting.
3. **Medium — Hot-at-D85 shift elision (claim 4).** README prints D1's +2357m inside the hot-D85 sentence; the artifact's own shift is +2993.8m vs the D85 baseline. Qualitative conclusion ("no sub-24C water at either dispersion") is unaffected, but the numbers as printed invite a direct comparison the baselines don't support. State both shifts with baselines.
4. **Medium — "Byte-identical build" overclaim (claim 5).** Replay and variant are identical; foodweb legitimately differs by the session's own shear-coupling provenance line (code rev changed). "Baseline pinned" is 2/3 true (`date_source=system_clock` leaks the wall date into season.json). Narrow the claim to replay/variant + numeric reproducibility.
5. **Low — wind=0.0 boundary (claim 1).** Grid edge optimum confirmed (train RMSE explodes off zero); negative-wind (net deposition gain) untestable by construction. One-sided grid search should be stated as such; no conclusion changes since README already flags the boundary fit.
6. **Low — README rounding drift (claim 7).** All numeric drifts are rounding-only (112/112.02, 27.8/27.81, etc.) — acceptable if the README declares rounding. No action beyond a "rounded" note.

## Do the headline conclusions stand?

Yes, with the shear-uniformity and shift-comparability prose corrected. The load-bearing results all recompute exactly: SNOTEL fits beat both nulls at both sites with correctly handled units/splits/gaps (though the train split under-identifies melt k, making the reported holdout scores conservative, not inflated); the hot low-flow run truly offers no sub-24C water in any of 276 cells at any of 721 frames with the refuge drive firing and diet/emergence/dipper numbers reproducing to the decimal; shear-default == disturbance-free reproduces while the sensitivity end-numbers (720/cell_00024, −51%/−27%) reproduce; Fischer-D85 moves placement −636m with nil ecology and hot-at-D85 still strands the trout at s=5230 in lethal water. The failures found are overstatements about uniformity/identity/comparability and an unacknowledged train/holdout identifiability gap — none overturns the session's substantive conclusions, but issues 1–4 should be fixed in the README before the next lane builds on these numbers.
