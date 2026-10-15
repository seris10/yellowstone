# Portfolio coherence

Source: Yellowstone portfolio audit, reviewed revision `9f81c3c873a45bb974af78cd1d58a0e90b9b0d1c`.

## Contracts and acceptance

| Finding | Owner and boundary | Positive control | Negative control |
|---|---|---|---|
| YS-A01 | LiveEngine owns physical time and stocks; display hour owns lighting. Scenario reset restores an identified initial state. | Explicit advance integrates elapsed seconds; reset applies spin-up once. | Display hour preserves stocks and budgets; repeated reset and reordered date/hour agree. |
| YS-A02 | Snow owns solid export; soil owns liquid drainage and ET. Only liquid drainage reaches the river. | Rain or melt above field capacity produces liquid discharge. | Cold wind erosion produces solid export and zero liquid runoff. |
| YS-A03 | Replay forcing and exchange strategy identify the river model in both execution paths. | Newton and explicit-budget trajectories agree with the same solver step and forcing. | Starting the service preserves strategy; speed changes preserve the numerical step. |
| YS-A04 | Publisher stages immutable generations; Godot activates one validated generation. | A complete generation loads at cold start and reload. | Omitted optional fields clear; interruption preserves the active generation. |
| YS-A05 | BUILD authenticates outputs and CHECKS; CHECKS names evaluated inputs and artifacts. | Verified bytes activate. | JSON, binary and check-report tampering refuse activation. |
| YS-A06 | Content identity uses logical input IDs and hashes; execution receipts record paths and environment. | Relocated inputs preserve content identity. | Changed input bytes change content identity. |
| YS-A07 | Command receipts bind execution evidence to source and fixture hashes. Consumer tests exercise actual readers. | Current receipts show executed and skipped counts separately. | Changed source makes evidence stale; absent evidence is unavailable. |
| YS-A08 | Land stage imports only its physical and export dependencies. | Characterization retains unrelated outputs. | Self-import and unrelated dependencies are absent. |
| YS-A09 | Spin-up precedes the experiment; each land flux has one interval and owner. | Shared land kernel conserves water and converges under refinement. | Zero duration preserves stocks; outlet rates use the source interval. |
| YS-A10 | Demo startup and model reproduction have separate entry paths. | Clean reference environment runs isolated and compact integration checks. | Service absence preserves baked operation; missing inputs report acquisition requirements. |
| YS-A11 | Code scopes and per-asset release decisions are explicit. | Bundled assets have identified permission evidence. | Unknown geometry rights block public redistribution. |
| YS-A12 | Current captures, experiment and limitations lead the repository entry. | Actual Godot captures and a frozen intervention trace share an identity. | Missing visual or performance evidence remains unavailable. |

## Scientific timeline

The initial ecosystem is the identified stock state. The configured snow days are a spin-up interval preceding experiment time. The snow/soil kernel owns evaporation during that interval. Reference ET is a diagnostic unless selected as the sole soil-water loss model for a declared experiment interval. Wind erosion exports solid water from a patch; redeposition and sublimation are unresolved, and solid export has no liquid-river destination. Pomeroy and Li (2000), doi:10.1029/2000JD900149 distinguish snow transport and sublimation from melt.

Overland outlet volume carries its own integration interval. Its mean boundary rate divides by that interval and applies only over that support window. A longer river experiment returns to baseflow after the event; it cannot extrapolate the finite outlet volume over the whole replay.

The published replay defines the initial river state, forcing and solver strategy. Resuming it preserves those definitions. Weather interventions create labeled forcing revisions. Starting a new scenario and resetting its date are explicit operations. Playback speed affects scheduling only.

## Verification

Use independent phase, zero-time, stock and tampering controls; a small fixed river fixture; actual Godot reader checks; the complete pytest tree; baseline build; and provenance audit. Execution receipts record the exact commands, source/fixture hashes, executed/skipped/unavailable status and results. Empirical claims remain `not_yet_accepted`. GPU visual review and redistribution decisions require their own evidence.
