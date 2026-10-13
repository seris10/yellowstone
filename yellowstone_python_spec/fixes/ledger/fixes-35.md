# fixes-35 ledger
Doc: fixes/fixes-35-ecosystem-replay.md | read 2026-10-12 | targets: yellowstone_midway/scripts/ecosystem.gd sha256:d3df05bcbf7b ; yellowstone_midway/scripts/python_river_replay.gd sha256:53636d9ad050 ; yellowstone_midway/scripts/pool_overlay.gd sha256:a4a8da8c1430 ; yellowstone_midway/scripts/thermal_probe_overlay.gd sha256:c4cea33a0ff9
Summary: 7 items: 7 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | condensation_visibility: rename q_mix to e_mix, divide by es(t_mix) | implemented | scripts/ecosystem.gd:271-283 variables are e_mix/es_mix, index is supersat/es_mix | Function renamed to _saturation_vapor_pressure_kpa (US spelling). | cheap |
| 2 | _advance_heat: comment explicit Euler + CFL stability loop | implemented | scripts/ecosystem.gd:155 "# Explicit Euler for a well-mixed cell. Stability holds under the stable_dt CFL loop." | Documents the scheme. | cheap |
| 3 | Replay respects day_rate for clock_hour advance | implemented | scripts/python_river_replay.gd:174 "elapsed * day_rate / 3600.0" | Matches live mode. | cheap |
| 4 | Per-frame flow in replay (q_cells_m3s interpolation) | implemented | scripts/python_river_replay.gd:198-213 lerp a_q,b_q when both frames carry q_cells_m3s; falls back to first-frame q_out_m3_s | Depends on R-d publishing the field; falls back silently when absent. | medium |
| 5 | pool_overlay class_name collision in temp_analysis/ | implemented | archive/midway-temp-analysis/ moved out of project (coordinator). | Owner-side handoff resolved pre-pass. | handoff |
| 6 | thermal_probe_overlay docstring and empty-path warning | implemented | scripts/thermal_probe_overlay.gd:3 docstring; :15-16 push_warning on empty path | Document plus a startup warning. | cheap |
| 7 | ecosystem.patch warns once per unknown ID | implemented | scripts/ecosystem.gd:263-266 push_warning once per unknown id via _warned_patch_ids | Pre-existing per pre-stash read. | cheap |

## Cross-project issues
- Item 4 is latent until R-d publishes `q_cells_m3s` per frame in `firehole_pulse.json` and `firehole_control.json`; current replays carry no such field, so flow stays at first-frame value with the fallback.

## Scientific validity flags
- None added; condensation_visibility is still a bounded index not a predicted plume mass.
