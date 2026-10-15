# Supported canopy and ground detail

The production overlook contains disconnected residual-canopy cards. Ground material
detail is weak at walking distance, and thermal pigment replaces the underlying
surface detail. The residual coverage mask, measured elevations, source imagery,
simulation fields, original meshes, and existing scene features remain inputs.

| Change | Contract | Evidence |
|---|---|---|
| Residual canopy | Connect every near shoot to an authored woody scaffold rooted at its matched ground elevation. Keep all observed residual cells and all existing distance ranges. Reconstructed supports make no measured stem-count claim. | Independent endpoint, root, bounds, source-area, packed-scene, and negative-control checks; native overlook captures. |
| Ground | Use physical texture widths, a reproducible band-limited height field, derivative normals, roughness, and coverage-preserving distance filtering. | Spectral, derivative, unit, determinism, and mip behavior checks; walking-height captures under three sun angles. |
| Basin | Retain mapped color structure beneath changing model pigment. Separate measured imagery from authored subpixel relief. | Source hashes, bounded linear-light contrast, live pigment transition and reset checks; native basin captures. |
| Rendering | Precompute the fixed linear outflow stencil when a field changes. Preserve source precision, clamped boundaries, dynamic reloads, and feature coverage. | Independent numerical equivalence including edges, source-change invalidation, and complete native before/after timings. |
| Distant trees | Pack four variants into a texture array and select the variant per instance. Preserve frames, physical dimensions, camera direction, alpha occupancy, placements, and distance limits. | Native pixel comparison over five forms, four variants, and eight views; baked counts and complete timings. |
| Spring color | Bind published ramps from the selected generation; cover the complete radial range. Use linear-light transport, the depth-integrated backward-scattering term, and one sRGB texture encoding. | Independent quadrature, passive-energy and zero-scattering limits, texture encoding anchors, actual runtime ramp hashes, and mesh endpoint checks. |
| Sunny atmosphere | Remove the clear-sky gray fog overlay and increase the clear-day direct-to-diffuse ratio. Preserve weather and astronomical inputs. | Clear, overcast, reduced-visibility, and night checks; native basin and sky captures. |
| Delivery | Bind the actual runtime, bake, checked build, package, and GitHub release to the revised source. | Full test scopes, build/provenance checks, cold packaged startup, file hashes, pushed commit and release asset verification. |

Height spectrum, relief amplitude, support dimensions, and display contrast are authored
rendering parameters with unknown local uncertainty. They are not field measurements
or biological validation. Performance claims require complete comparable native runs.
