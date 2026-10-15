# Model authority and temporal support

The build manifest identifies the scenario, resolved heat-exchange variant, effective input hashes, solver step policy and physical epoch. Execution receipts identify the source tree and completed command. A source change makes those receipts stale. Scientific acceptance remains separate.

| Quantity or state | Owner and producer | Consumer and interpretation | Interval and evidence |
|---|---|---|---|
| River temperature | `river.river_transport`, backward Euler mapped finite volume | Godot replay and probes; live frames preserve the selected solver | Physical seconds from explicit UTC epoch; budget and shared-state parity tests |
| Boundary discharge/temperature | Frozen prescribed forcing or declared intervention | River advection and lateral mixing | Right-continuous source schedule; scenario forcing, unmeasured local boundary accuracy |
| Snow and soil water | Shared `snow_season.step_land` kernel | Patch state, rendering and optional runoff adapter | Negative spin-up interval and hourly experiment intervals; zero-time and stock tests |
| Liquid runoff | Soil surface drainage | River discharge only when a catchment area is configured | Source integration window and mean patch depth; phase `liquid` |
| Wind snow loss | Snow erosion | Solid export ledger | Phase `solid`; no implicit river melting or energy transfer |
| Sublimation | Unavailable process | No inferred vapor flux | Unknown; distinct from solid transport and liquid drainage |
| ET stock debit | Snow/soil bucket | Soil water | One owner per interval; reference FAO ET remains diagnostic |
| Overland runoff | Local-inertial overland integration | Declared mean-rate river adapter | Rate denominator is the source window; discharge ends at its support boundary and the source volume is routed once |
| Biomass | Vegetation and enabled mammal consumption | Patch state and animal encounters | Initial-state preparation is declared separately; experiment steps share physical time |
| Canopy coverage / crown cores | USGS LiDAR extraction and inference | Coverage raster, census and render placement | 2020 acquisition; species/DBH transfers remain unvalidated |
| Mat pigment and pool ramps | Model-derived static sidecars | Visual mappings and frozen diagnostics | Build support; availability is generation-specific |
| Weather lighting hour | Display state | Sun and visual lighting | No physical stock debit, growth or epoch change |
| Scenario date reset | Identified initial checkpoint and declared spin-up | Fresh scenario state and buffers | Spin-up applied once from the initial state; repeated target is idempotent |

Godot's generation loader hashes and parses every selected artifact before activating the actual replay reader. Optional absence clears prior state. Static scenery retains geographic and authored layers. A new live service must identify the selected build and heat-exchange variant; changed controls create an identified scenario branch.

The runtime notes panel labels frozen diagnostics. A displayed diagnostic does not imply a physical model transfer. `data/consumers.json` declares readers; runtime contract tests exercise the replay field access independently of filename existence. Other declared readers retain their documented validation scope.
