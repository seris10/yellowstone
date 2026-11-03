# Park streaming gates and main-scene integration

## Scope

The park-scale streaming runtime landed as an opt-in architecture
(`fixes/progress.md`; `docs/park_runtime/`). The shipped game still boots
the static baked world, two of the repo's own integration checks are red,
and the package's promotion gate (`docs/park_runtime/03_ACCEPTANCE.md`)
requires green parity and rebase checks before any default-mode change.
This document covers the two red gates and the first integration step:
the streamed boot branch behind the existing opt-in settings. The default
world mode does not change under this document. No scientific claim
changes state.

## Findings and implementation

- Composed-pack parity failures. `stream_midway_check.gd` reports 6 of
  3066 checks failing against `data/park_composed`: deviation from the
  legacy 1 m core cut at the core boundary (worst 0.392 m over 1520
  samples), leaf-level height deviation up to 4.536 m, and bridge
  `trail_3226_0` terrain differing from the legacy cut by 4.148 m.
  `docs/park_runtime/04_IMPLEMENTATION_STATUS.md` claims 3066 checks with
  0 failures against the same data, so the doc is stale against committed
  code and data. Find whether the composed pack or the legacy core cut
  moved since the claim; regenerate `data/park_composed` (or repair the
  composition in `terrain_pack.py --core-dir`) so the parity check passes,
  and correct the status doc table to the measured result. The check must
  pass in CI-equivalent headless form before any integration work relies
  on the composed pack.
- Legacy shader rebase continuity. `ground_rebase_check.gd` reports 12 of
  237 checks failing: shader literal periods [67.0, 1.8] diverge from the
  phase table [67.0, 4.0, 19.0, 1.8], and ground texture lookups drift up
  to 0.094 across origin rebases. The ground compositor gained a
  close-range detail system in `fixes-58` batch 4
  (`ground_surface.gdshaderinc`, `terrain_materials.gd` repeat-phase
  table); the phase table and the shader literals must cover every lookup
  including the new detail, triplanar, and mineral phases, or the
  materials jump whenever the world origin moves. Bring every ground and
  thermal lookup under the repeat-phase contract, then pass
  `ground_rebase_check.gd` headless and run
  `ground_rebase_render_check.gd` on a visible renderer (it refuses
  headless; record the capture).
- Streamed boot branch behind the opt-in settings. `project.godot:269-274`
  declares `park_streaming/enabled=false` and companion settings that no
  script reads; `scenes/main.tscn` and `scripts/world.gd` contain no
  `park_runtime` reference; the edit map
  (`docs/park_runtime/01_CURRENT_FILE_EDITS.md`, section A2) specifies the
  integration that was never applied. Implement section A2 as specified:
  extract `_load_legacy_authored_world()` from the current inline load
  (`world.gd:144-164`), add the streamed boot branch selected by
  `park_streaming/enabled`, bind the movement guard, and apply
  `WorldFrame` rebasing in `_physics_process`. Default behavior with the
  setting off must remain byte-identical to the legacy path, proven by
  the smoke test and the saved-scene validators in both states.
- Integration prerequisites recorded. The boot branch depends on the two
  gates above: rebasing with rebase-unsafe shaders moves the ground
  textures visibly, and streaming from a non-parity composed pack shows
  the wrong heights at the core boundary and the bridge. Implement the
  gates first, in the order listed.

## Verification

- `stream_midway_check.gd`: 3066 checks, 0 failures; status doc table
  matches the measured result.
- `ground_rebase_check.gd`: 237 checks, 0 failures;
  `ground_rebase_render_check.gd` capture recorded from a visible run.
- Boot branch: `--smoke-test` passes with `park_streaming/enabled` off
  and on; `validate_baked.gd`, `validate_core_cut.gd`,
  `validate_multimesh.gd` and the smoke multimesh receipt pass in both
  states; the legacy scene loads byte-identical with the setting off.
- `python3 -m pytest tests/park_runtime -q` stays green;
  `check_comment_style.py` and the prose pattern checker clean on touched
  files.
- Frame-time comparison is not required by this document; the
  performance protocol in `docs/park_runtime/03_ACCEPTANCE.md` remains
  the promotion gate for any later default-mode change.

## Sources

- Migration package docs: `yellowstone_midway/docs/park_runtime/`
  (00 architecture contract, 01 edit map, 03 acceptance).
- Goal assessment: measured gate results against
  `data/park_composed` and `tests/park_runtime/` (parity 6 failures,
  rebase 12 failures, as recorded in `fixes/progress.md` discussion and
  the checker outputs).
- `yellowstone_python_spec/04_PARK_STREAMING_SPEC.md` for the full-park
  tile scheme (design; no tile packs beyond Midway are built under this
  document).
