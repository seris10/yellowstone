# fixes-52: terrain materials and shadow quality

Scope: core/master ground materials, mapped tread, directional shadows, normal/detail sampling and their regression checks. Run mode remains illustrative. Geographic inputs and scientific acceptance statuses are preserved.

## 1. Shared ground and trail layers

The core material omits the master trail mask and ground detail. Extract the terrain base into a shared shader include and bind the same habitat, soil, rock, detail, trail and snow textures on both geometries. Limit thermal pigment and wet-film effects by the mineral/outflow fields. Use physical material tile widths and authored procedural tread/litter variation. Verify spur and seam coverage, full binding and snow/wetness updates.

## 2. Directional shadow policy

The sun covers 280 m with normal bias 1.2. Controlled renders isolate foreground bands to core self-shadowing; normal bias 3.0 suppresses them in one fixed camera. Centralize authored shadow presets, use walking coverage with four cascades and Soft Medium filtering, and retain terrain/tree casting. Verify contact, movement, multiple sun angles and frame time. Preserve current Compatibility renderer.

## 3. Normal and image coordinates

The generated core normal uses world-space RGB while the material expects tangent-space residual detail. Correct the encoding and metadata before binding it, and orthonormalize the surface tangent frame. Detail imagery is resized from the entire 1280 m photo into an offset 600 m tile. Resample by world extent and pixel centers. Use analytical flat/tilt and georeferenced fixtures. Keep authored relief distinct from measured elevation.

## 4. Free PBR material detail

Reuse Forest Ground 04 and add its available roughness/AO data. Integrate a CC0 mapped trail surface where beneficial. Record exact asset URLs, authors, license, tile scale and hashes. Preserve geographical registration and measured terrain. Add stable mipmapped detail and restrained procedural variability before additional geometry.

## 5. Regression and verification

Extend core/material validation with trail and shared texture contracts, terrain normals and boundary sampling. Run Godot import, core checks, walk and consumer checks, visible fixed/moving-camera captures at multiple sun angles, the maintained Python suite, a full baseline build and provenance audit. Record automated verification separately from subjective visual acceptance.

## 6. Rendered terrain boundary authority

The core border is pinned to the unmodified reference DEM rather than rendered `data/terrain.f32`; exact 1 m perimeter samples differ by up to 3.27 m at an authored river carve. Reconcile the existing 12 m stitch margin to the rendered master triangle surface and taper authored microrelief to zero at the boundary. Preserve all core interior heights past the margin byte for byte. Record the authored correction and source hashes. Verify all boundary samples within numeric precision, unchanged interior, normal regeneration and walking across the boundary.

## 7. Validation prerequisites

The completed suite exposed two concurrent test-contract changes that prevent final verification. Make shared test path resolution session-scoped, matching its session-scoped roots and supporting cached module simulations; retain function-scoped monkeypatch fixtures. Resolve the study preset test's permitted paths from the registered slider schema, including aquatic controls, retaining prohibited routes/pools/placements and exact-key negative checks. Back up current tests before changing them. Run the affected catchment and study modules, then repeat the full suite against frozen sources. These repairs do not change physics or study models.

## 8. Geometry cut at the core footprint

A fine dotted boundary remains with 4x MSAA despite matching edge heights. Fragment discard clips a pixel while the replacement mesh covers samples at its geometric boundary. Remove the master triangles inside the grid-aligned core footprint at runtime, preserving outside vertices, normals, UVs and materials. Disable fragment cutting after all intersected tile cuts succeed. Verify the exact covered triangle counts, unchanged outside geometry, collision continuity and rendered edge with MSAA enabled.

## 9. Master collision at the core boundary

The inclusive sunken-height mask changes master collision triangles outside the core. Direct rays 1, 2 and 3 m west of the footprint miss the visible surface by 73.43, 48.79 and 24.40 m; the uncut master agrees within 0.000031 m. Replace supported partial master collision with the exact retained terrain triangles in tile-local coordinates, and disable collision for fully covered tiles. Prepare and validate collision replacements before committing the cut. Preserve outside triangles and remove inside ghost surfaces. Any unsupported fallback must preserve the exterior collision rather than sink boundary samples. The world must refuse core activation if collision cutting fails, retaining the original master as the visible and physical surface. Add actual raycasts across all four edges, corner and walking checks, including a negative control that detects the original sunken mask. Repeat rendered checks and record the corrected collision scope separately from the earlier walk record.

## Rollback and coordination

Target source files are backed up outside the repository before edits. Changes are surgical against the current dirty checkout. Existing live-state and unrelated source/data work is preserved. No full world bake or scientific data publish is required. Core boundary changes are limited to the existing stitch margin. Generated core outputs change only after numeric verification and a backup of the prior outputs.
