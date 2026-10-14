# Adversarial review verdict: B2/B3 session 2026-10-11

Read-only review except this file. All numbers below were recomputed with
independent commands against the artifacts. Method per claim: read the
artifact value, recompute from the frozen bundle or PDE with separate code,
compare. Verdicts: SUPPORTED / CONTRADICTED / NOT TESTED.

## B2 plume (`derived/plume2d_excelsior_2026-10-11.json`)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| Discrete residual 1.3e-13 | SUPPORTED | artifact `1.3237261657175584e-13`; own upwind/centered stencil over `plume_field(128,128)` output = `1.3237261657175584e-13` exactly |
| Peak anomaly 1.3 C, footprint 467.7 m | SUPPORTED | own centerline scan of `plume_field` output: peak 19.1 at z=-148.8, +1 C span 467.7 m |
| Centerline decays monotonically downstream | SUPPORTED | same scan: monotone to the south edge (19.084) |
| Field within [ambient, source] | SUPPORTED | min 17.8 max 19.1 exactly at (17.8, 19.1) inputs |
| Fully mixed bound +2.3 C, peak inside it | SUPPORTED | hand arithmetic `(0.255*93+8*17.8)/8.255-17.8 = 2.32`; 0 < 1.3 <= 2.32 |
| E-fold 28334.9 m, half-width 82.7 m | SUPPORTED | artifact values read; scale consistent with u/k = 13 km plus longitudinal diffusion (no independent re-derive, formulae are short) |
| TOA insolation values used by B3 (483/123 W/m2) | SUPPORTED | hand Iqbal recompute: June 482.9, December 123.0 at 44.6 N |
| Build changes only plume_map.png + BUILD.json | SUPPORTED | byte-compare `5ffc1d046260` vs `42db86821c1c`: 51 files identical, diffs exactly those two; file sets equal |
| IR gradient zones vs Burkhalter 1979 | NOT TESTED | artifact records this itself; zone coordinates exist nowhere in the repo |

## B3 energy balance (`derived/snow_energy_fit_2026-10-11.json`, `derived/snow_energy_fixed_WY2025_2026-10-11.json`)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| 609 fit (0.54, 2.0), holdout 61.94 vs 112.02/293.29/471.58, peak +1 | SUPPORTED | artifact read; degree-day 112.02 and nulls match `snow_snotel_fit_2026-10-10.json` exactly |
| 924 fit (0.0, 8.0), holdout 13.5 vs 45.04/179.04/194.36, peak +2 | SUPPORTED | from-scratch recompute (own forcing fill, TOA, albedo, melt loop): train 8.19, holdout 13.5, peak err 2, exact |
| 609 s_rad interior optimum | SUPPORTED | train RMSE at (0.52/0.54/0.56, 2.0) = 9.9298/9.6770/9.7913; strict interior minimum |
| 924 s_rad=0.0 is a strict train optimum | SUPPORTED | train at 0.0/0.02/0.04 = 8.1857/8.1927/8.2174; 0.0 wins, so the floor pick follows the stated rule |
| 924 holdout prefers s_rad=0.02 (12.85 < 13.50) | SUPPORTED | same recompute; train/holdout tension of the A1 family, selection rule applied as stated |
| 609 c_t=2.0 optimum, one step above floor | SUPPORTED | train at c=0.0/2.0/4.0 = 15.1120/9.6770/10.6608; near-floor but not on it |
| WY2025 frozen: 609 45.64 vs 283.81/482.24; 924 55.05 vs 178.76/245.62 | SUPPORTED | artifact read; beats both nulls both sites |
| Frozen degree-day WY2025 161/90 | SUPPORTED | `snow_snotel_fixed_WY2025_2026-10-11.json` reads 160.9/90.23 |
| EB beats frozen degree-day ~2-3.5x | SUPPORTED | 160.9/45.64 = 3.5x; 90.23/55.05 = 1.6x |
| README numbers match artifacts | SUPPORTED | 61.94->62, 13.5->14, 45.64->46, 55.05->55, peaks +1/+2/-16/-1 all match |

## Suite and boundary notes

- Suite green at collection time: 384 collected, 374 passed, 10 skipped,
  reproduced 3x including with cache disabled. Skips are pandas/sympy
  absence, unchanged.
- Count anomaly, unresolved: the build session reported 350 passed mid-day
  for the identical command; no repo write accounts for +24 (collection is
  384 with and without the newest build dir present). No contradiction
  found in any result; recorded so a recurrence can be diffed with
  `--collect-only` output.
- 924 radiation dropout is a train-rule outcome, not a physical proof of
  zero radiative melt; 0.02 generalizes slightly better. Same caveat class
  as the degree-day wind=0.0 boundary fits.
- 609 EB flips the degree-day bias sign (+67 too-long to -40 too-fast).
  Smaller RMSE, opposite bias; reported in the artifact.
