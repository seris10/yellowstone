# fixes-55 ledger

Specification: `fixes/fixes-55-toolchain-quality.md`.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| QA-01 | implemented | Stage C polishes only free discharge/temperature coordinates with c_mult fixed at 1; all optimizers share bounds. Full evaluated parameters, forcing/hash, recomputed scores and termination state are serialized. Rejected grids report no_valid_fit. |
| QA-02 | implemented | Channel eligibility, actual estimated parameters, optimizer convergence and local conditioning have separate fields. Stage D differentiates the actual weighted temperature residual and reports rank/confounding without claiming global or field identifiability. |
| QA-03 | implemented | Numerical rejection excludes grid and ensemble members. Forward runs are rechecked; valid top-N fallback and insufficient/unavailable ensembles are explicit. Reentry negative controls pass. |
| QA-04 | implemented | Query time derives from the scenario epoch, recorded offset and one explicit selector. Multi-day bundle tests match local, elapsed and absolute queries; cache windows cannot replace the date. Out-of-window fallback is labeled at the requested instant. |
| QA-05 | implemented | Complete bird/mammal contact maps are normalized and applied to walking, including serialized clips. Unknown, incomplete, nonfinite and incompatible maps refuse. |
| QA-06 | implemented | CLI validation checks real serialized finite geometry, indices, skin weights, required clips and loops. Failed required checks write a failed report and return nonzero; valid GLBs pass. |
| QA-07 | partial | Production uses selected source-bound reviewed rigs and controls, exact exported-surface budgets and hash-bound target-engine review. Current asset measurements and actual Godot Idle/Walk, terrain, turn, pause, speed and transition captures exist. Human anatomical review remains unavailable; deer/badger deformation budgets fail. Existing assets retain illustrative status. |
| QA-08 | implemented | Body drag scales with immersion; each foot's paddling force scales with actual wet fraction. Dry body/feet yield gravity alone; wet opposing drag and passive equilibrium retain positive controls. |
| QA-09 | implemented | Fish speed uses signed actual chainage displacement and current, including target arrival. Native Godot cases cover upstream, downstream, holding, drift and zero flow; tailbeat clock policy and pause state are explicit. |
| QA-10 | implemented | Both tree writers emit the canonical v2 layout; named adapters preserve both v1 source layouts and reject unknown versions. Replaced library bytes are archived by content hash. |
| QA-11 | implemented | The advertised selected-library command builds the selected graph and parameter set. Final mesh identities, transforms and wood attachments are recorded after envelope/root transforms; source graphs and stable IDs remain preserved. |
| QA-12 | partial | Source crown ratios are preserved by default; photo_floor is explicit. The actual 63,565-record bake cohort has source/display distributions. Variant topology, shoot placement and four-view far identity are retained. Actual bake materials are shared with the GPU fixture. At predeclared budgets, 32/32 near, 25/32 middle and 0/32 far pairs pass. The failed far silhouette/occupancy checks and subpixel foliage remain unresolved; the 12-second slow pass and raw captures are retained. |
| QA-13 | implemented | Exports retain the complete population model, dataset/model hashes, qualifiers, sampling seed and exact base reference. Wrong-reference transfers refuse; modified rigs require review and regenerated skin/deformation checks. |
| QA-14 | implemented | The flora compatibility entry point forwards to the maintained module. Selected documented CLI help and fixture commands run from outside the checkout; explicit output/source separation is enforced. |
| QA-15 | partial | Actual Blender export/reimport enforces the hard triangulated cap, finite/nonempty geometry, required UV/tangent/material/texture contracts and sampled surface error before replacement. The multi-mesh fixture produces 580 triangles under a 600 cap; empty and excessive-error controls preserve accepted output. The fixture contains no textures; acceptance of current textured species reductions and visual/deformation quality remains unavailable. |

Summary: 15 items: 12 implemented,0 shortcut,3 partial,0 missing,0 superseded,0 conflicts

The partial rows are acceptance work still open. Geometry ownership is confirmed by KJR; it does not substitute for deformation, visual or biological evidence. No failed visual budget is converted to a passed result, and no tolerance is widened after viewing the captures.
