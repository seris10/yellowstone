# Authoring and analysis contracts

The existing tools retain their own operational scopes. Numerical convergence, eligible parameters, geometric acceptance, human visual review and biological validation have separate fields. Source meshes, measurements, stable tree IDs and authored placement overrides are preserved.

## River calibration and weather

Stage C estimates lateral discharge and temperature with surface exchange fixed at `c_mult=1`. Grid, differential evolution and least squares share the caller's bounds. Each result includes the full evaluated vector, forcing bundle and hash, final recomputed scores, numerical checks and optimizer termination. Failed optimizers remain recorded attempts. A best rejected diagnostic candidate has `fit_status=no_valid_fit`.

Stage D uses a downstream temperature residual in C, with weight 1. Other observed channels define parameter eligibility; they do not automatically become objective terms. The reported scaled finite-difference Jacobian measures local conditioning of that actual objective. It does not establish global or empirical identifiability.

Uncertainty membership requires numerical checks and a valid forward recomputation. A valid top-N fallback is labeled; insufficient valid members yield unavailable intervals. Weather queries accept one of local hour, elapsed hours or absolute UTC epoch. A cached bundle cannot replace the scenario date. Out-of-window data are labeled unavailable while the authored fallback retains the requested instant.

## Animal export and review

KJR owns the supplied animal meshes and authorized their inclusion in project releases. This permission is independent of rig quality and biological evidence. Existing clips retain estimated rig status unless a review bound to the actual source mesh establishes otherwise.

Prepare landmarks with `python -m yellowstone_python.wildlife_motion inspect SOURCE.glb --species gray_wolf --outdir REVIEW`. The generated rig is editable. Review its source hash, axes, units, joints and contact surfaces before setting its review status. Controls from `calibrate` feed `animate --controls`; complete bird and mammal touchdown maps affect the exported clip. Unknown or incompatible controls fail.

The production builder requires `--review-manifest`. Its schema is `yellowstone.wildlife_motion_build_review.v1`, with `assets` keyed by exact unskinned source SHA256. Each record supplies `rig`, `controls`, `deformation_budget` and `target_engine_review`. Rig, controls and review may be JSON objects or relative JSON paths. Controls map Idle and Walk to engine overrides. The four required deformation limits are `maximum_edge_stretch_p99`, `maximum_stance_surface_slip_height_per_s`, `maximum_stance_surface_distance_height` and `maximum_loop_error_height`.

Target-engine review records the exact exported `asset_sha256`, status, reviewer, reviewer kind and captures with relative paths and SHA256. Reviewed cases include Idle, Walk, turn, ground_height, pause, speed_change and clip_transition. Production refuses missing or mismatched evidence. `--allow-unreviewed-development` explicitly exports unaccepted development assets for iteration; it does not confer acceptance.

`python -m yellowstone_python.wildlife_motion validate ASSET.glb --output REPORT.json` checks the serialized geometry, skin and animation contract. A required failure writes a failed report and returns a nonzero status. The richer surface report measures exported edge deformation and stance-region motion on the skinned surface. Flat canonical ground measurements and actual target-engine terrain captures have distinct scopes. Population-based variants retain the full model, dataset identity and exact same-reference asset binding, then regenerate skin/rig checks. Modified rigs require review again.

Current animal measurements and Godot captures are in `evidence/wildlife-surface-quality.json` and `evidence/wildlife-native.json`. Existing assets remain illustrative where a production review is unavailable. Failed budgets remain visible in those reports.

## Tree interchange and LOD

Both writers emit `yellowstone.tree_architecture_library.v2`. The canonical reader adapts the two v1 layouts, preserves source evidence and refuses unknown versions. Replaced library bytes are archived by content hash.

Export parameters with `python -m tools.tree_architecture --record TREE.json --variants 1 --parameters PARAMETERS.json --out LIBRARY.json`. Build that selected graph with `python yellowstone_midway/tools/author_lodgepole.py --architecture-library LIBRARY.json --variant-id TREE_ID:0 --output DERIVATIVE_DIRECTORY` from the repository root. The derivative directory must be empty. Graph, parameter, geometry and glTF identities are retained. Final mesh attachment checks run after render-space transforms.

Crown ratio defaults to `preserve_source`; `display_crown_policy=photo_floor` explicitly selects the artistic floor. Source crown cores and full display crown widths remain distinct. `python -m tools.tree_architecture --input RECORDS.json --distribution-only --archetype runtime --out DISTRIBUTIONS.json` reports supplied and display traits separately, including unavailable source fields. Runtime archetype selection follows stable IDs and existing record overrides.

The three existing distance boundaries remain 18, 65 and 180 m. Seeded shoot positions persist through the middle LODs; wood tessellation reduces separately. Far images derive from the same seeded variant, with four camera directions. Capture reports retain predeclared screen-space budgets, hashes and failures. A valid graph alone does not establish acceptable alpha cutout or LOD appearance.

## Mesh reduction and supported commands

`python -m yellowstone_python.authoring.gen_flora --help` is the maintained flora entry point; `python -m tools.gen_flora --help` forwards to it. Commands are tested from outside the checkout in an installed environment.

Run the existing reducer through Blender with `blender --background --python-exit-code 2 --python tools/blender_wildlife_decimate.py -- --source SOURCE.glb --output OUTPUT.glb --triangles 600`. The hard cap applies to the triangulated, exported and reimported file. The command stages the derivative, checks UVs, tangents, materials, decoded textures and a sampled bidirectional surface-error budget, then replaces accepted output. Empty input and failed quality budgets preserve the previous derivative. The original source is unchanged. Rigged input requires the unskinned source and a subsequent rig review.

The reduction fixture establishes the command and geometric contract. Its numerical error is sampled vertex-to-triangle distance, not exact Hausdorff distance or a visual-quality verdict. Current species reductions and reviewed clips need their own source-bound evidence.

The saved-array MultiMesh validator assumes four pine copies and uniform scalar dimensions. Its retained output cannot establish placement acceptance for the split LOD and residual-canopy representations. Shader-space bounds and complete placement validation remain open; source vector registration and terrain/collision checks have separate passing evidence.

## Reference test scopes

The macOS reference matrix uses separate isolated interpreter processes for `pytest -m 'not needs_world'` and `pytest -m needs_world`. The surface-update matrix reports 1,993 core passes, 14 optional-dependency skips, and 121 world passes. The two scopes have 2,128 disjoint cases: 2,114 executed passes and 14 skips. Their source-bound receipts and JUnit files are in `evidence/reference-test-matrix.json`.

The historical monolithic attempt and native PROJ/SQLite child-launch failures remain in the prior matrix and isolation records. The passing isolated scopes do not establish a green monolithic process.

The full Python scopes executed at `c13d620`. Five Godot render/test files changed afterward to expose mapped pool water. Every Python model, tool, configuration and test byte remains identical. `evidence/runtime-source-equivalence.json` lists those changed render files and preserves the original execution identities. Native water, color, canopy, batch, material and render checks execute the complete selected render inventory. This equivalence does not relabel the historical receipts as executions of a different full inventory.

Raw reduction sources for black bear and Canada lynx live in the ignored `assets/imported/wildlife_motion/sources/` directory. UV comparisons require the exact owner-provided files named by the source manifest and report unavailable when absent. The local reference matrix uses those supplied source files. Runtime exploration does not need them. Broader biological reference datasets remain unavailable.
