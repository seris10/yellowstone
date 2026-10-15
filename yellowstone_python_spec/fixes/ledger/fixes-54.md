# fixes-54 ledger

Specification: `fixes/fixes-54-portfolio-coherence.md`.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| YS-A01 | implemented | Physical advance, display lighting and checkpoint reset have separate operations. Phase/clock and live-engine controls test stock preservation, reset idempotence and date/hour ordering. |
| YS-A02 | implemented | `snow_season.step_land` records solid snow export separately from liquid runoff; subfreezing wind-only and wet drainage controls preserve the phase distinction and water balance. |
| YS-A03 | implemented | Replay records the full solver configuration and post-equilibrium initial state. Live execution preserves strategy and fixed solver step. Synthetic Newton/explicit cases and the mapped published/live comparison test trajectories. |
| YS-A04 | implemented | Publisher stages immutable generations, records optional absence and atomically switches one pointer. Godot hashes/parses the complete selected generation before activation. Actual reader reload tests cover A, B with missing optional fields and rejected C. |
| YS-A05 | implemented | CHECKS binds evaluated inputs, model and artifact bytes; BUILD binds CHECKS. JSON, binary and check-report substitutions refuse publication before activation. |
| YS-A06 | implemented | Portable identity uses normalized configuration, logical inputs, content hashes, seeds and model code. Paths and environment belong to execution receipts. Relocation and changed-input controls exercise identity. |
| YS-A07 | implemented | Source/fixture-bound command receipts distinguish execution, skips, missing evidence and stale sources. The dashboard labels declarations and ledger assertions separately. Reader tests execute actual Godot field access. |
| YS-A08 | implemented | Land stage imports its own physics/export dependencies; the CLI forwards publication to its single implementation. Unrelated/self dependencies are removed and characterization checks remain. |
| YS-A09 | implemented | Shared baked/live land stepping assigns one ET owner, preceding spin-up support and elapsed-time fluxes. Overland rates apply over their finite source window; the 6 m3/120 s case routes exactly 6 m3 during a 600 s replay. |
| YS-A10 | implemented | The exact-lock isolated installation, portable Godot package and offline startup path have separate instructions. Cold headless and Metal startup pass with the Python service unavailable and all four floor anchors grounded. Native executable export and other-platform testing remain unavailable. |
| YS-A11 | implemented | Code scopes and per-file asset permissions are explicit. KJR's animal ownership and release permission are recorded. Unknown permission or mismatched bytes exclude an asset; geometry quality and biological acceptance remain separate. |
| YS-A12 | implemented | README leads with actual Godot images, a recorded intervention, architecture and three evidence-bounded case studies. Performance, forest labels, artistic assumptions and unaccepted visual work remain explicit. |

Implementation status does not confer scientific acceptance. The current release manifest, receipts, numerical comparison and package report provide the executed evidence. Earlier receipts remain present and become stale when implementation or fixtures change.
