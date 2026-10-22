# 03. Acceptance and measurement

## Reproduce the executed Python checks

From the extracted package directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

The package's recorded run is in `reports/python_tests.txt` and
`reports/validation.json`. These tests exercise the new infrastructure and illustrative
network. They do not run the entire existing Yellowstone Python suite or establish
field accuracy. The baseline's native solver tests remain mandatory after integration.

## Godot compile/API gate: must run locally

The build sandbox did not contain a working Godot executable. Source preloads and
Python-side contracts were checked, but **GDScript was not engine-compiled or run**.
Do not relabel this package's scripts as engine-validated until the following pass:

```sh
python tools/prepare_demo.py
GODOT=/path/to/Godot-4.5.1
"$GODOT" --headless --editor --path demo --import --quit
"$GODOT" --headless --path demo --script tests/park_runtime/run_tests.gd
"$GODOT" --path demo
```

On the user's tested Mac renderer, keep the project's existing Mobile/Metal choice
for apples-to-apples comparisons. The standalone fixture intentionally uses a simple
material and synthetic terrain; it is not a before/after Yellowstone FPS comparison.

The supplied Godot tests check source loading, task cancellation, terrain winding,
height queries, origin shifting and frustum-plane orientation. Add actual physics
raycasts and GPU/state lifecycle tests below. A frustum-sign failure must be fixed
before enabling hard culling or promoting the integration.

## Generate Midway input tiles without baking meshes

After installing the overlay, from the repository root with its environment active:

```sh
cd yellowstone_python
python -m yellowstone_python.park_runtime.terrain_pack \
  --source ../yellowstone_midway/data/terrain.f32 \
  --nx 1025 --nz 1025 --cell 4 --origin-x -2048 --origin-z -2048 \
  --mesh-cells 32 --root-cells 1024 --pack-id midway-master \
  --out ../yellowstone_midway/data/park
```

This uses the explicit file passed to it. Resolve the active release first when it
differs from `data/terrain.f32`. This command alone omits the current 1 m core
composition/water cuts. Treat it as a terrain infrastructure test until section B
of the edit guide is completed. Never publish it as visual/scientific parity.

For larger source regions, `--nx/--nz` may be rectangular whole multiples of root
cells plus one. NumPy memmap avoids materializing the complete raster. Roots are
compiled independently. All values must be finite; provide a deliberate no-data
mask extension rather than filling gaps with fabricated heights. `--append` adds
non-overlapping roots with a shared coordinate frame. Immutable pack IDs may not be
overwritten. Uncovered terrain remains explicitly unavailable.

## Test the separated service

```sh
# Package root; this is an explicitly illustrative reference service.
PYTHONPATH=overlay/yellowstone_python python -m yellowstone_python.park_runtime \
  --port 8766 --state /tmp/yellowstone-park-reference.sqlite3
```

Start the Godot demo separately. Stop the service while moving in the demo: terrain
and camera should remain responsive, and the HUD should show disconnected/stale
physical state. Restart: a new session ID appears and persisted committed state is
restored. Never pretend that the illustrative network is the native Firehole model.

## Required regression matrix

| Case | Required observation | Failure |
|---|---|---|
| Sudden 180-degree turn | Coarse fallback covers newly visible space; detail follows asynchronously | Void, missing whole terrain, synchronous loading pause |
| Ridge with narrow gap | Hidden regions lose detailed priority; the gap and skyline remain represented | Hard occlusion deleting the gap |
| Crest/overlook arrival | Predicted travel requests detail before exposure; fallback remains complete | Only a radial ring or a visible hole |
| Parent-to-children switch | Parent OR complete four-child cover; no mixed partial cover | Z-fighting full overlays or missing quadrants |
| Missing/corrupt child page | Explicit error plus parent fallback; retry after repair | Silent height zero or an uncaught task that blocks progress |
| Move out and back repeatedly | Residency plateaus; stale job results do not reappear | Resident meshes/colliders grow with visited area |
| Origin shift during jobs | New and existing terrain align; absolute source queries unchanged | Seams, jumps, shifted noise/materials or stale-local transforms |
| Collision delay | Movement held before an unsafe swept footprint; camera remains active | Falling through a pending chunk |
| Tile seam raycast | Both halves match source triangular interpolation; no skirt collision | Different height/diagonal across a boundary |
| Teleport | Prepare, verify collision/features, then relocate | Naked teleport into unloaded terrain |
| Hidden upstream region | Downstream water/heat/solute continue with the same forcing | Flow changes because camera turned away |
| Revisit hidden wildlife | Persistent IDs and stores survive; visual phase reconstructed | New identical animals or reset consumption |
| Intervention during lookahead | New revision discards invalid future; old packets rejected | Weather/river oscillate between incompatible histories |
| Model worker failure | No partial cross-domain commit; physical clock held | One subsystem displays a future the others never reached |
| Service restart | Compatible committed checkpoint or explicit reset choice | Automatic unrelated replay silently substituted |
| Accelerated time | Stable numerical steps and measured compute capacity; responsive renderer | FPS selects PDE timestep or event history is skipped |
| Native adapter parity | Native and wrapped runs agree within existing tolerances | Reference reservoir substituted or timestep policy changed |
| Core/water parity | Existing core contact, shoreline and outflow tests still pass | Master-only tiles erase current detailed work |

## Performance protocol

Record exact hardware, OS, engine, renderer/driver, viewport pixels, resolution scale,
AA, shadow settings, source revision, simulation scenario/time, display hour, route,
seed, warmup and cache state. Keep them equal between legacy and streamed modes.

The supplied `tests/park_runtime/benchmark_route.gd` records render-frame intervals,
draw calls, primitives, static memory and streamer accounting. Run it in a visible
renderer, not headless, for performance work:

```sh
"$GODOT" --path demo --script tests/park_runtime/benchmark_route.gd -- \
  --frames=1800 --duration=30 --out=user://park-demo-benchmark.json
```

For the integrated Yellowstone scene, provide a georeferenced route JSON and select
`--scene=res://scenes/main.tscn`. Verify camera/control ownership and pass actual
motion velocity to the streamer during a scripted route; the fixture benchmark
repositions the camera and does not model a walker's swept physics. Use a second
walker-driven benchmark for collision deadlines and predictive loading.

Measure CPU script time and GPU time separately using the Godot profiler/platform
GPU tooling. The supplied report does not claim to attribute GPU milliseconds.
Record p50/p95/p99 and maximum frame times; initial boot, warm steady views, continuous
travel and teleport recovery are separate workloads. Report resource creation and
retirement spikes, not only averages.

Provisional engineering targets, not claimed achieved results: ordinary 60 Hz frames
fit within 16.67 ms, or a deliberately chosen 30 Hz tier within 33.33 ms; main-thread
stream commits target 1.5 ms total per frame with one small mesh commit; no steady
resident-memory growth after repeated routes. An individual API upload can exceed
the target because it is not preemptible. Tune bounded tile sizes using measurements.

At low memory, retain safety/coarse coverage and stop admitting fine detail. The
first implementation reports pressure; a fully adaptive quality governor is an
explicit follow-on. A budget that cannot hold bootstrap/safety coverage is a
configuration failure, not permission to unload the ground beneath the player.

## Promotion gate

No default switch until: Godot compile/runtime checks pass; all native scientific
tests pass; core/water/material and vegetation/wildlife parity reports exist; memory
plateaus on revisit; interrupted service/job scenarios recover; and actual frame-time
traces demonstrate the intended benefit. A successful synthetic demo is necessary
infrastructure evidence, not sufficient evidence of full-world readiness.
