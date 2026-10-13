# fixes-38: tools and validators
Scope: yellowstone_midway/tools/bake_botany.gd sha256:b970c7e6d117 ; yellowstone_midway/tools/bake_world.gd sha256:2536fbd6d9c5 ; yellowstone_midway/tools/inspect_fauna_glb.gd sha256:ed55f74c2f56 ; yellowstone_midway/tools/recolor_goose_texture.gd sha256:0cc8173c58f1 ; yellowstone_midway/tools/render_fauna_preview.gd sha256:b8551d62d114 ; yellowstone_midway/tools/validate_baked.gd sha256:aa6e841ad0d2 ; yellowstone_midway/tools/validate_ecology.gd sha256:a018298af209 ; yellowstone_midway/tools/validate_multimesh.gd sha256:514ddd608588 ; yellowstone_midway/tools/validate_walk.gd sha256:877e4b18bdcf ; yellowstone_midway/tools/prepare_world.py sha256:7f68c816b889 ; yellowstone_midway/tools/validate_world.py sha256:a5abad34a814
Callers read: project README, yellowstone_midway/README.md, yellowstone_midway/scripts/world.gd

## Main problems

### 1. validate_ecology hardcodes reach indices and tolerances
validate_ecology.gd:29-30. `absf(float(model.river[2].flow_m3s) - 8.0) < 1e-9` and `absf(float(model.river[5].flow_m3s) - 8.26) < 1e-9` assume `river_reaches[2]` is upstream and `river_reaches[5]` carries one lateral source adding 0.26 m3/s. The test will break silently if ecosystem.json changes order even though the physics is still correct.
### Fix
Look up reaches by id and the lateral sources sum. Example:
```gdscript
var upstream_id: String = str(config["river_reaches"][0]["id"])
var upstream_reach: Dictionary = model.river[model._reach_indices[upstream_id]]
check(absf(float(upstream_reach.flow_m3s) - float(config["boundary_m3s"])) < 1e-9, ...)
```
### Test
Reorder `river_reaches` in ecosystem.json and re-run; the test should still pass.

### 2. validate_walk ignores jump and relies on gravity 9.81
validate_walk.gd:16-18, player.gd:78. The report line `"jump_enabled": false` is correct, but gravity reads straight from player.gd's hardcoded `9.81`. Changing project gravity should auto-propagate; see fixes-36 item 1.
### Fix
Covered by fixes-36 item 1.
### Test
Same test as fixes-36 item 1.

### 3. bake_botany.foliage_material does not populate wind_vector
bake_botany.gd:30-36. The returned foliage material sets `tint`, `wind_strength`, `use_texture` but not `wind_vector`. The shader default is `vec2(1.8, 0.6)`. If world.update_environment never collects the baked flora materials (which it does: world.gd:102-108), the wind would still animate correctly, but a shader-default wind value is a provenance smell during tests.
### Fix
```gdscript
mat.set_shader_parameter("wind_vector", Vector2(1.8, 0.6))
```
with a one-line comment that this gets overwritten at runtime by world.update_environment.
### Test
`tests/test_bake_botany_material.gd`: assert the saved material has `wind_vector` set.

### 4. bake_world.append_instance has no bounds check on buffer size
bake_world.gd:59-66. The function appends 16 floats per instance to a `PackedFloat32Array`. There is no cap on `buffer.size()`. A runaway placement file could blow memory. For a bake tool this is lower risk, but a bounds check would catch bad inputs.
### Fix
```gdscript
if buffer.size() > 1_000_000:  # 62k instances
	push_error("Instance buffer exceeded safety limit; abort.")
	return
```
### Test
Not required (bounds policy).

### 5. validate_multimesh runs for every bake but is write-only to tests/
validate_multimesh.gd:8 writes `res://tests/multimesh_validation.json`. The `tests/` dir is not scanned by CI; the file is read by no code. A validator with no consumer accrues drift.
### Fix
Have world.gd read `res://tests/multimesh_validation.json` at startup and push_error if `ok != true`. Or ship the file into the smoke-test harness.
### Test
Add a tool line to `run_smoke_test()` that reads this JSON and prints the summary.

### 6. prepare_world.py has mixed indentation
prepare_world.py:12-13,24-28 mix tabs and spaces (line 11 uses one space indent, line 24 uses two spaces, line 44 docstring indented with one space). Python 3 is strict about indentation; the file parses only because each block is self-consistent, but it is a style violation per `AGENTS.md` section 2 and a trap for later edits.
### Fix
Reindent with 4 spaces throughout; verify with `python3 -c "import ast; ast.parse(open('tools/prepare_world.py').read())"`.
### Test
`python3 -m py_compile yellowstone_midway/tools/prepare_world.py` returns 0.

### 7. validate_world.py raises SystemExit at module level
validate_world.py:52. `raise SystemExit(0 if not errors else 1)` sits at module scope so a `import tools.validate_world` would exit the importer. The script is meant to run directly but should be guarded by `if __name__ == "__main__":`.
### Fix
Wrap the `errors.append`-driven block, the write, and the exit in `def main():` plus the standard guard.
### Test
`python3 -c "import importlib.util, sys; spec = importlib.util.spec_from_file_location('vw','yellowstone_midway/tools/validate_world.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"` imports cleanly without triggering SystemExit.

### 8. inspect_fauna_glb and render_fauna_preview load packed scenes without failure path
inspect_fauna_glb.gd:17-23. If `ResourceLoader.exists(path)` is true but `load(path)` returns null (corrupt resource), the next `root: Node3D = packed.instantiate()` crashes with a null dereference. render_fauna_preview.gd:37-38 does not even check `load()` returning null.
### Fix
Both files: guard the result of `load(path)`, `continue` or `return` on null. Keep the existing `MISSING` branch.
### Test
Rename a GLB to a path that passes `exists` check but corrupt it; run both tools and assert they log the corrupt case instead of crashing.

### 9. recolor_goose_texture hue thresholds are undocumented
recolor_goose_texture.gd:38-50. The HSV cutoffs `h > 0.22 and h < 0.48` (green), `h >= 0.0 and h < 0.10 or h > 0.93` (orange), and `s <= 0.35` (gray-brown) are inline numbers with no reference. For a reproducible recolor pipeline these belong in named constants with a one-line source note.
### Fix
Extract constants:
```gdscript
# Hue ranges on [0, 1] for the mallard-base source texture.
const GREEN_HUE_RANGE := Vector2(0.22, 0.48)
const ORANGE_HUE_RANGES := [[0.0, 0.10], [0.93, 1.0]]
const GRAY_BROWN_SAT_MAX := 0.35
```
### Test
None (one-off tool).

# Wiring and rendering
- bake_world.gd and bake_botany.gd are offline tools. They produce `scenes/authored_world.tscn` and `scenes/botanical_details.tscn` plus `assets/materials/*.tres`.
- validate_baked, validate_multimesh, validate_walk, validate_ecology each produce a JSON report in `tests/`. Only validate_baked and validate_multimesh write a file consumed anywhere (`run_smoke_test` prints neither; the files are inspected by hand).
- inspect_fauna_glb, render_fauna_preview, recolor_goose_texture are one-off asset-prep scripts.
- prepare_world.py and validate_world.py are Python-side authoring tools, invoked from the project root as `python3 yellowstone_midway/tools/prepare_world.py`.

# Comment-style violations
| file:line | text | rule |
| yellowstone_midway/tools/bake_botany.gd:2 | `## Offline authoring tool. Every clump has a fixed JSON record and identity.` | "Every" comprehensiveness |
| yellowstone_midway/tools/bake_botany.gd:4 | `## Run after terrain changes: godot --headless --path . --script tools/bake_botany.gd` | addresses reader (Run) |
| yellowstone_midway/tools/bake_world.gd:3 | `## Run: godot --headless --path . --script tools/bake_world.gd` | addresses reader |
| yellowstone_midway/tools/bake_world.gd:60-61 | `# RenderingServer bulk layout: three row-major vec4s, then color/custom. # Bulk assignment retains CPU data in headless bakes.` | two inline sentences |
| yellowstone_midway/tools/validate_baked.gd | no file docstring | missing |
| yellowstone_midway/tools/validate_multimesh.gd:2-4 | `## Validate saved instance arrays without dummy-renderer getters. Run: ... Requires a complete offline bake. Does not mutate the world.` | addresses reader; what-it-does-not phrasing |
| yellowstone_midway/tools/validate_walk.gd:3-4 | `## Focused collision integration test. godot --headless ...` | addresses reader |
| yellowstone_midway/tools/validate_walk.gd:12 | `"Not the complete overlook-to-boardwalk route or all park routes."` | what-it-is-not; this is report prose, acceptable |
| yellowstone_midway/tools/inspect_fauna_glb.gd:2 | `## Inspect imported fauna GLBs: combined AABB, mesh/material inventory.` | passable |
| yellowstone_midway/tools/recolor_goose_texture.gd:2-3 | `## Recolor the CC-BY mallard base texture into a Canada goose palette. Derivation: green head -> black, orange bill/feet -> black, body gray-brown -> Canada brown, white ring kept.` | multi-line docstring |
| yellowstone_midway/tools/prepare_world.py:1-5 | starts with shebang then docstring across lines | passable |
| yellowstone_midway/tools/validate_world.py:1 | `"""Checks invariants for a real-scale connected landscape."""` | one-line, OK |

# Priority order
1. item 7 (validate_world.py main guard) - cheap
2. item 1 (validate_ecology hardcoded indices) - cheap
3. item 8 (fauna tool null-load guard) - cheap
4. item 3 (bake_botany wind_vector default) - cheap
5. item 6 (prepare_world.py indentation) - medium
6. item 9 (recolor_goose constants) - cheap
7. item 4 (bake_world buffer cap) - cheap
8. item 5 (consume validate_multimesh JSON) - medium
