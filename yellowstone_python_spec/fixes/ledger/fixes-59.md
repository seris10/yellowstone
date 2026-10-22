# Reviewed publication and controls ledger

Specification: `fixes/fixes-59-reviewed-publication-and-controls.md`.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| Authorized publication destination | implemented | Origin fetch and push URLs resolve to `seris10/yellowstone`. Public main is `cfd3ecc500b3c9e884893084476bccf6f7b5e62f`, with parent `c2b4c7923a6eeed61e2feca3946555826849ec67`. The GitHub API confirms all 38 changed file blob IDs match the local commit. |
| Modal input ownership | implemented | `world.gd::_modal_open` and `_sync_player_input` combine menu, notes, simulation, help, and calibration state. Real key-event checks preserve menu ownership after notes or study closes and preserve a visible cursor on Escape inside notes. |
| Notes pause ownership | implemented | `_requested_pause` and `_apply_pause_state` preserve the prior user pause while notes hold playback paused. Q reports the notes hold. Live clock adoption retains the local notes hold. The control regression checks running and previously paused sessions. |
| Rejected clock mutation | implemented | `park_runtime/service.py` validates proposed clock fields before assigning either field. `test_rejected_http_clock_preserves_state` exercises the HTTP route and a publication barrier. The same test rejects the pre-repair implementation. |
| Exported checker dependency and failure exit | implemented | The public exporter selects three named pattern libraries. Empty or invalid library loads exit 2 in each CLI mode. The exported CLI passes a clean input, rejects a bad comment, and rejects missing patterns. The pre-repair CLI fails the missing-library regression. |
| F4 metadata visibility | implemented | `simulation_status_text` gates identifiers on the perf probe, with verification status outside that gate. The control regression checks identifiers hidden, visible with F4, then hidden after F4 closes. |
| Replay endpoint feedback | implemented | The jump handler reports an unchanged clamped target. The control regression checks unchanged endpoint time and the visible endpoint toast. |

The published-tree Python suite reports 2291 passed, 16 skipped, and 29
warnings. The headless scene regression reports 31 checks and the native
Mobile/Metal regression reports 35 checks, with zero failures or engine
errors. Build `cdf6afb2416d` records the published commit and passes its
assessment in illustrative mode. All 538 maintained style paths are clean;
the 32 exported checker patterns pass their examples.

The standard provenance command checks 20 top-level artifacts with zero
findings. Direct build inspection retains the same 55 artifact-format and
status findings as the source audit. That broader checker limitation is
unchanged. Scientific claim acceptance remains separate from these checks.

Receipts reside in `work/public-native-check/verification/`. Internal
documents, unrelated vegetation work, development history, and historical
release payloads are absent from the publication commit.
