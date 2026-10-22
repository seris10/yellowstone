===
# Packaging and input contract repairs ledger

Specification: `fixes/fixes-61-packaging-and-input-contracts.md`.

Baseline ledger written at document creation, before implementation. Every
row is `missing` by construction; evidence cites the code as it stands in
the working tree.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| Public export excludes binary scene | implemented | `yellowstone_python/tools/export_public.py:28-29` adds `yellowstone_midway/scenes/authored_world.scn` to `EXCLUDED_PATHS` beside the `.tscn`; `yellowstone_python/tests/test_public_export.py:40` exports a fixture tree holding both scene files and asserts neither lands in the manifest. |
| Demo package scene contract | implemented | `yellowstone_python/tools/package_demo.py:91` requires `scenes/authored_world.scn` and line 108 keeps the text twin out of the walk, so the package ships exactly the binary scene; `yellowstone_python/tests/test_package_demo.py:43` refuses a world holding only the `.tscn`. |
| Verification receipt covers loaded scene | implemented | `yellowstone_midway/scripts/verification_receipt.gd:26-28` resolves the scene the way `world.gd:144-146` loads it, and `source_hashes()` hashes that file; `yellowstone_midway/tools/validate_multimesh.gd:504-505` records the resolved path and its hash in the report. |
| Gamepad conditions and step bindings | implemented | `yellowstone_midway/project.godot:131` binds `conditions` to joypad button 8 and line 149 binds `step_frame` to button 7; `yellowstone_midway/scripts/input_help.gd:7,10` assigns layers 1 and 2, making the pairs LB plus right-stick click and RB plus left-stick click. |
