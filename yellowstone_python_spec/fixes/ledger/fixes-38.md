# fixes-38 ledger
Doc: fixes/fixes-38-tools-validators.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_midway/tools/bake_botany.gd sha256:08e3a9903844 ; yellowstone_midway/tools/bake_world.gd sha256:e45a69da42a0 ; yellowstone_midway/tools/inspect_fauna_glb.gd sha256:673ada7c284a ; yellowstone_midway/tools/recolor_goose_texture.gd sha256:e90e53d8e59d ; yellowstone_midway/tools/render_fauna_preview.gd sha256:4ebdaaecd99a ; yellowstone_midway/tools/validate_baked.gd sha256:aa6e841ad0d2 ; yellowstone_midway/tools/validate_ecology.gd sha256:5b9a03a3fecb ; yellowstone_midway/tools/validate_multimesh.gd sha256:514ddd608588 ; yellowstone_midway/tools/validate_walk.gd sha256:877e4b18bdcf ; yellowstone_midway/tools/prepare_world.py sha256:7f68c816b889 ; yellowstone_midway/tools/validate_world.py sha256:1cf164cf2f28
Summary: 9 items: 9 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | validate_ecology looks up reaches by id and sums lateral sources | implemented | tools/validate_ecology.gd:29-38 uses config.river_reaches[0].id and sums lateral_sources | Config reorderings now safe. | cheap |
| 2 | validate_walk gravity sourced from ProjectSettings | implemented | Covered by fixes-36 item 1 in player.gd; validate_walk unchanged. | Delegated to the player fix. | cheap |
| 3 | bake_botany foliage_material writes a wind_vector default | implemented | tools/bake_botany.gd:36-37 sets wind_vector = Vector2(1.8, 0.6) with "Overwritten by world.update_environment at runtime." | Explicit default. | cheap |
| 4 | bake_world.append_instance has a buffer-size safety limit | implemented | tools/bake_world.gd:63-66 push_error and return when buffer.size() > 1_000_000 | 62k instance cap. | cheap |
| 5 | validate_multimesh JSON consumed by run_smoke_test or startup | implemented | scripts/world.gd:688-706 adds `report_multimesh_validation()` called at the end of `run_smoke_test`; tolerant of file absence | Smoke-test only (no runtime cost), reads tests/multimesh_validation.json when the operator ran the validator. | cheap |
| 6 | prepare_world.py reindented with 4 spaces | implemented | tools/prepare_world.py:1-500 reindented via scratchpad/g2/fix_prepare_world.py | File is 4-space-per-level throughout; AST sha256 matches between the one-space-fixed intermediate and the four-space rewrite (7e6d65ab018a6da1); the pre-pass source did not parse under Python 3.11-3.14 (contrary to the prior "file parses today" claim) because the carve_water_support docstring sat at col 2 while its body sat at col 1, and 20 further comment/code lines were over-indented by one space. Fix step 1 moved those lines to the correct levels before the 4-space pass; both intermediate and final parse under python3 -m py_compile. | refactor |
| 7 | validate_world.py wraps module-level code in main() with __main__ guard | implemented | tools/validate_world.py def main() at :10; `if __name__ == "__main__": raise SystemExit(main())` at :73-74 | Importable without side effects. | cheap |
| 8 | inspect_fauna_glb and render_fauna_preview guard null load() | implemented | tools/inspect_fauna_glb.gd:17-23 guards; tools/render_fauna_preview.gd:37-45 guards both packed and inst | Already present in pre-run tree; kept. | cheap |
| 9 | recolor_goose_texture hue thresholds pulled to named constants | implemented | tools/recolor_goose_texture.gd:11-19 constants; :37-43 uses them | Also fixes a pre-existing Color API drift (`.h/.s/.v` properties). | cheap |

## Cross-project issues
- Item 5 reads the test output only during smoke runs so the main process never depends on tests/.
- Item 6 reindent exposed that the pre-pass source did not parse at all; the fix repairs the parse errors as part of the 4-space normalization.

## Scientific validity flags
- None.
