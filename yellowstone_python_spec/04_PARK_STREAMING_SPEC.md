# Full-park local loading design specification

Scope: growing the walkable world from the fixed 4,096 m Midway square to the whole of
Yellowstone National Park, with the Python model and the Godot renderer both working on a
loaded island around the player that moves with the direction of travel. This document fixes
the coordinate contract, the tile pyramid, the loading policy, the Python nesting scheme, the
wire protocol between the two sides, the data sources per tile, the measurements to take
first, and the migration order from the present Midway build. It does not change any
scientific claim: every model that runs inside a tile keeps its run mode, its prescribed
quantities and its `not_yet_accepted` status.

## 1. What exists today

The Midway world is one fixed domain: 4,096 x 4,096 m, one Godot unit per meter, a 1,025 x
1,025 elevation grid at 4 m spacing in `data/terrain.f32` read by `height_field.gd` and by
`common/coords.py`, with a 601 x 601 core at 1 m spacing (`data/core_terrain/`) stitched
into the 4 m grid through `stitch.json`. The frame is WGS 84 / UTM zone 12N (EPSG:32612),
origin easting 512952.5950985841, northing 4930199.044097667, vertical origin 2,200 m
NAVD88; x is easting minus origin, z is origin northing minus northing, y is elevation
minus 2,200 m. Terrain renders from 256 baked tile meshes of 256 m
(`assets/meshes/terrain/tile_RR_CC.res`) cut from one authored scene,
`scenes/authored_world.tscn`, which is 338 MB and stays outside git.

Python builds into `derived/<build-id>/` and publishes transactionally into
`yellowstone_midway/data/` (`publish.py`). Godot watches those files with
`data_watcher.gd`, which hashes every watched file's bytes once per second; `ecosystem.json`
is 81 MB and `river_replay.json` 52 MB. The live path is `live_python_client.gd` polling
`/api/live/frames` every 0.25 s and posting controls with a player location; the engine
(`service/live/engine.py`) steps the mapped Firehole, the foodweb, snow, soil, vegetation and
mammals in physical time with checkpointed lookahead frames and reports the effective rate
when solver capacity limits acceleration at 60x to 3600x.

The coast prototype in Downloads (`Seabright_to_Davenport/scripts/world.gd`) is the
working streaming reference: 1,330 packed sectors of 256 m, 766 height tiles, threaded
`ResourceLoader.load_threaded_request` with at most 6 loads pending and 2 sector attaches per
poll, load radii of 1,150 m for ground, 2,600 m for backdrop and 4,800 m for ocean sectors,
and an origin rebase every 1,024 m that moves player, live sectors, wildlife and shader
origins in the same frame. The shared world contract package in Downloads defines the chunk
lifecycle (requested, loading, ready for commit, committing, active, retiring) and the rule
that the logical model owns state independently of scene residency. Both are reused here.

## 2. Park scale

Yellowstone is 8,983 km2 (NPS: 2,219,791 acres), about 87 km east to west and 101 km north
to south at its widest. Keeping the Midway origin, the park spans roughly x from -25 km to
+80 km and z from -56 km to +44 km. The boundary polygon from the NPS data store is the
source for the exact tile set; the figures here size the design.

| Resolution | Cells over the bounding box | Float32 bytes | Source |
|---|---:|---:|---|
| 1 m | 8.8 x 10^9 | 35 GB | USGS 3DEP QL1 lidar (WY YellowstoneNP 2020) where flown |
| 4 m | 5.5 x 10^8 | 2.2 GB | resampled from 1 m where flown, 10 m elsewhere |
| 16 m | 3.4 x 10^7 | 137 MB | 3DEP 1/3 arc-second |
| 64 m | 2.1 x 10^6 | 8.6 MB | 3DEP 1/3 arc-second |
| 256 m | 1.3 x 10^5 | 0.5 MB | 3DEP 1/3 arc-second |

The 1 m level cannot be resident or shipped whole and is not needed everywhere; the 4 m
level fits on disk but not in memory; the 16 m level and coarser fit in memory. That is the
whole argument for a pyramid with a resident coarse base and streamed fine tiles.

Trees are the other scale problem. The lidar census found 33,764 automated crowns over the
1,280 m Midway window, about 20,000 per km2 of forest; roughly four fifths of the park is
forest, so the park holds on the order of 10^8 crowns. Individual authored placements cannot
scale; placement becomes a per-tile derived product (section 6).

## 3. Coordinate contract for the park

The Midway frame is kept unchanged: EPSG:32612, the same origin easting and northing, the
same 2,200 m vertical origin, the same axis convention. Every existing authored placement,
pool polygon, route and water graph keeps its coordinates. Positions are stored and exchanged
in this absolute local frame in meters; Python never sees a rebased coordinate.

Float32 limits the renderer. At 80 km from the origin a float32 position step is about
8 mm, enough for visible shimmer in shadows and skinned animation. The runtime therefore
rebases: an origin offset snapped to the 1,024 m tile grid is subtracted from every resident
node when the player crosses into a new 1,024 m cell, in one frame, for the player body,
every resident tile, every actor, every particle system and every world-position shader
uniform, following the coast prototype's `rebase()`. The rebase owner is `world.gd` and
nothing else moves nodes for that purpose. Rebased coordinates are never persisted. Origin
subtraction happens in float64 (Python) or GDScript doubles before a `Vector3` is built. A
double-precision engine build is noted as an alternative and not chosen: it needs a custom
engine build and shader changes for one benefit the rebase already gives.

Tile identity is `L<k>_<ix>_<iz>` with `ix = floor(x / S_k)` and `iz = floor(z / S_k)` where
`S_k` is the tile edge at level `k`. Negative indices are allowed; the origin stays inside
the Midway tile `L1_-1_-1` to `L1_0_0` corner set.

## 4. Tile pyramid

Every level uses 256 cells per tile edge (257 samples, the shared edge sample included) so
that one tile at level `k` covers exactly 4 x 4 tiles at level `k - 1`.

| Level | Cell | Tile edge | Tiles over the park | Heightfield per tile | Role |
|---|---:|---:|---:|---:|---|
| L0 | 1 m | 1,280 m core (as today) | tens, authored list | 6.6 MB | hero cores: developed basins, thermal areas, overlooks |
| L1 | 4 m | 1,024 m | about 9,000 | 264 KB | walkable ground, collision, placements |
| L2 | 16 m | 4,096 m | about 550 | 264 KB | mid distance, no collision |
| L3 | 64 m | 16,384 m | 42 | 264 KB | far distance |
| L4 | 256 m | 65,536 m | 4 | 264 KB | horizon, always resident |

L0 cores keep the present core terrain mechanism: a 1 m heightfield plus microrelief and
normal map stitched into the surrounding L1 tiles through recorded edge samples, exactly
as `core_terrain.gd` and `stitch.json` do now. Cores exist only where 1 m lidar and authored
detail exist; the list is authored and small.

Each tile package on disk holds the heightfield, a normal map, a material class raster, the
water mask and river surface strips clipped to the tile, road and trail ribbons clipped to
the tile, the placement set for the tile, the scientific sidecars that belong to the tile,
and a `tile.json` manifest with bounds, level, source hashes, provenance records, measured or
estimated budgets (triangles, instances, bytes) and the hashes of every file. Terrain meshes
are built on load from the heightfield, which keeps L1 at 264 KB per tile
on disk and leaves mesh construction to a worker thread. A packed scene per tile, baked by a
Godot tool from the package the way the coast prototype bakes sectors, is the runtime unit.

Seams: adjacent tiles at the same level share edge samples by construction. Between levels,
the finer tile's edge is resampled to the coarser spacing on its outer ring (a one-cell
stitch band, the same idea as the present core stitch) so that render and collision agree;
a skirt alone is not accepted because it hides the crack from the eye and not from physics.
Any road, trail or river that crosses a seam has one identity and one geometry in the
build, split into per-tile pieces only at bake time, so a crossing is never authored twice.

## 5. Visibility-driven residency and detail

Residency and detail are decided by what the player can see, not by distance alone. A hill
behind the player hides everything beyond it, and the budget that would have gone to the
hidden tiles goes to finer detail on the open expanse in front. Two sets are computed every
0.25 s, or sooner when the player moves more than 25 m or turns more than 15 degrees.

The reach set is where the player can be soon: the 3 x 3 L1 tiles around the tile holding
the player position `p`, and the 3 x 3 around the tile holding the lookahead point
`q = p + v * T`, with `v` the player velocity and `T` 20 s. These are always resident with
collision, whatever is visible, because the walker needs ground under it and because walking
over a ridge reveals the far side within seconds.

The visible set is the terrain viewshed from the eye point (`p` plus 1.7 m) over the
resident coarse heightfields: a march outward along azimuth rays, 0.5 degree bins on the
64 m level out to 20 km and 2 degree bins on the 256 m level out to 70 km, keeping the
running maximum elevation angle; a tile is visible when any sample inside its extent rises
above the running horizon along any ray that crosses it. Earth curvature and refraction are
in the test (a drop of about 0.87 d^2 / 2R, which is 250 m at 60 km), and a 30 m margin
on the horizon absorbs the smoothing of the coarse levels. Trees are not in the heightfield,
so the viewshed overstates visibility, which is the safe side. A tile that lies wholly below
the horizon, the hill behind the player included, is occluded: it is not loaded, not meshed
and not placed, whatever its distance. The march costs about 42,000 height samples per
update. In baked mode GDScript runs it on a worker thread at 1 Hz; with the live service
Python computes it in numpy from the same heightfields and returns it in the focus reply
(section 8), and Godot uses whichever result is fresher.

Detail is then allocated to visible tiles by importance under fixed budgets. Importance is
the tile's approximate screen footprint: visible area times the cosine of the angle between
the view direction and the direction to the tile, over distance squared, weighted 1 inside
the camera frustum, 0.3 within 30 degrees outside it (the head turns 180 degrees in about
half a second, so those tiles must already exist at a cheap level) and 0.05 beyond that
margin. The allocation walks the visible tiles in importance order and gives each the
finest tier the remaining budget allows.

| Tier | Which tiles | Terrain | Placements | Collision |
|---|---|---|---|---|
| A | the reach set, and visible in-frustum tiles within 2 km | L1 mesh at 4 m, L0 core where one exists | full MultiMesh per tile, impostors beyond 1 km | yes |
| B | visible in-frustum tiles beyond 2 km, by importance | L2 mesh at 16 m carrying a normal map baked from the 4 m data | impostors only, density from the coverage field | no |
| C | visible tiles outside the frustum within the 30 degree margin | L2 mesh, no normal map | none | no |
| D | visible tiles beyond the margin | L3 and L4 only, always resident | none | no |
| occluded | below the terrain horizon and outside the reach set | L4 only | none | no |

Budgets start at 3,000,000 resident terrain triangles, 500,000 placement instances and
1.5 GB of resident tile data, and are set by the frame-cost measurement in section 10. The
catalog records a world whose frame rate did not move when 70 percent of its triangles were
removed (`beach-walk-frame-rate-is-not-geometry-bound`), so the binding budget is measured,
not assumed. When a budget runs out, the remaining visible tiles stay at tier D, where the
256 m data already gives the horizon.

Promotion to a finer tier is immediate when the budget allows; demotion waits 5 s and unload
waits 10 s for L1 and 30 s for L2, so a turn of the head does not thrash the loader. Load
order is importance order. The loader keeps at most 6 threaded loads pending and attaches
at most 2 scenes per poll inside an 8 ms main-thread budget measured after each job; the
real worst case is the budget plus one job
(`a-budget-spent-from-the-drain-is-not-a-budget-on-the-tick`), which the attach measurement
in section 10 bounds. On arrival at a starting place the reach set loads synchronously, as
the coast prototype's `ensure_near` does, and the walker is held for the frames that takes.
A tile that leaves every tier after its hysteresis window is freed, its presentation only:
the logical state of what was inside it belongs to Python (section 7) and to the persistent
actor records, never to the scene node.

Both the viewshed test and the frustum test use the tile's bounding box: anything the world
decides per tile is asked of the tile's extent, not of its center sample
(`a-region-gate-is-asked-of-the-chunk-not-of-a-column`). Placements inside a tier A tile
are one `MultiMeshInstance3D` per tile and mesh kind with `visibility_range` set, which
keeps frustum culling, mesh LOD and batching together
(`a-technique-has-a-scope-not-a-price`).

## 6. Per-tile build in Python

The build pipeline keeps its stages (`pipeline/stages/`: weather, river, thermal, land,
vegetation, insects, fish, foodweb, grazers, mammals, finalize) and gains a tile scope. A
tile build job takes a pinned input snapshot, a tile id and level, and the dependency
closure the stage needs, and writes `derived/<build-id>/tiles/L<k>/<ix>_<iz>/`. Its build
key is content derived: source hashes, override revision, frame, model versions, settings,
seam policy. Hydrological influence crosses tile edges, so a change invalidates the affected
closure (the reach downstream, the sub-basin); the rest of the park and the
visible-only set stay untouched.

Placement is derived per tile from the canopy coverage field, the species rules already in
`land/vegetation.py` and a tile-seeded generator, so that a tile is reproducible from its
inputs and a reload places the same trees. Authored placements and the lidar crown census
override the generator where they exist, with their own provenance, and the override plan
stays reversible as it is today. There is one placement law shared by every scatterer
(catalog row `one-placement-law-not-six`): water, thermal apron, road, trail and slope
exclusions are asked once, of the tile raster.

Publishing writes tile packages under `yellowstone_midway/data/tiles/` and an index,
`data/tiles/index.json`, holding each tile's revision and hash. The index is the only file
the watcher hashes every second; a tile's files are read only when its index revision
changes. The present per-file hashing of an 81 MB document every second is replaced by this
index on the first migration step.

## 7. Python simulation island: two tiers

The model runs as two nested tiers that share one simulation clock.

The coarse tier runs over the whole park at all times, at an hourly step in simulation
time. Its state is small enough to stay resident: snow water equivalent per 100 m elevation
band and aspect class within each sub-basin (NHDPlus HUC-12 units, on the order of a
hundred in the park); a water balance per sub-basin routed along the NHD flowline network at
reach scale; soil storage and vegetation phenology per cover class from LANDFIRE; an air
temperature field from the station network (SNOTEL, Open-Meteo forcing) with a lapse rate by
elevation; and daylight and solar geometry from the existing atmosphere code. The coarse
tier is what the far terrain shows: snow line, river stage, green-up.

The fine tier is the present `LiveEngine`, with one instance per island. It
covers the resident L1 tiles: the mapped river reaches inside them with the existing
transport, oxygen, periphyton and foodweb models, the thermal outflow networks and mats of
any L0 core inside them, the vegetation patches, microclimate, insects, birds and mammal
actors. Its boundary conditions come from the coarse tier at the island edge: discharge and
temperature at every flowline entering the island, air temperature and humidity, snow state
on the ground. Where today the boundary is a prescribed forcing from configuration, in the
park it is the coarse tier's value, which is recorded as a prescribed quantity of the tile
build in the same way, so the validation split (`run_mode.check_split`) is unchanged.

Activation and retirement follow the reach set of section 5: the
simulation island is where the player can be, while a visible ridge 40 km away shows the
coarse tier's snow line and river stage and needs no fine state. When an L1 tile enters the
reach set, Python activates it: reaches,
cores and patches inside it join the island engine, initialized from the tile's last fine
checkpoint if that checkpoint is less than one simulation day old, otherwise from the coarse
tier's state with a spin-up of one simulation hour run ahead of the player clock. When a
tile leaves the reach set and its hysteresis window passes, Python retires it: the fine
state of everything inside it is written to `derived/live/tiles/<id>/checkpoint.json` with
its simulation time, and the tile's totals of water volume, heat content and biomass are
handed to the coarse tier's ledger. Conservation across the hand-off is a build check:
summed over tiers, water and heat change only by the fluxes the models declare. The
checkpoint, the ledger entry and the activation record all carry the tile id, the content
revision and a request generation, and the runtime discards a result whose generation is
stale, following the chunk lifecycle of the shared world contract.

Time scale keeps its present governor. At 3600x one real second is one simulation hour, so
the coarse tier steps once per real second and the fine tier must cover an hour per second
for every resident reach. When the measured effective rate falls below the requested rate
for 5 consecutive polls, the reach set shrinks from its two 3 x 3 blocks to the player's
block alone before the rate is held; when capacity returns for 20 polls the lookahead block
comes back. The reported effective rate and the current reach set are both shown in the
simulation panel, so a held rate is never silent.

Lakes are a model class the present engine does not have. Yellowstone Lake (352 km2) and the
other large lakes need a stratified water column model before their tiles can carry fine
state; until then their tiles carry coarse surface temperature only, labeled as such.

### 7.1 Predictive simulation residency and park-scale bounds

No component loads, steps or holds the whole park at fine resolution: Godot, the Python
fine tier, the coarse tier's inputs and the checkpoint history are all bounded by budgets
stated in bytes and in compute per wall-clock second. Simulation residency is a separate
loading problem from terrain and view residency. Terrain answers what the player can see
within seconds; simulation must answer what state the player will meet when they arrive,
which needs work started minutes ahead in wall time and, under time acceleration, hours
ahead in simulation time.

Measured baseline (Apple M4, one core, `LiveEngine.from_build` on build `db183e56a88e`,
276 mapped Firehole cells, 1 s solver step, 10 s frames): one simulated hour takes
11.6-13.0 s of wall time, about 300x real time and 13 us per cell per simulated second;
retaining that hour of lookahead holds 361 full-state checkpoints and 314 MiB of traced
allocations, about 0.9 MiB per checkpoint. Three consequences follow. The 3600x setting
already exceeds Midway's capacity by about twelve times. The two-block reach set of up to
1,500 cells in section 7 runs at about 50x on one core. Lookahead memory grows linearly
with domains and horizon, so full-state checkpoints at every frame cannot carry a park.

The anticipation set replaces the 20 s lookahead point for simulation. It is computed in
Python from the focus call (section 8) and contains, in priority order: the reach set;
the next reachable stretch along the trail or road graph from the player's position and
heading, out to the distance the player covers in the activation lead time `L` at the
current travel mode (walking 1.4 m/s, vehicle at the road's posted speed); destinations
the player has selected on the map; and the hydrological dependency closure of each of
those tiles, bounded by a propagation halo: the upstream reach whose travel time to the
tile is shorter than the activation lead time. `L` is the measured spin-up cost of a tile
divided by the capacity left after the active island, plus a margin, so a tile is
activated early enough to be ready on arrival.

Admission control decides what runs at fine resolution. Capacity is measured continuously
as cell-simulated-seconds per wall second (the engine's existing compute samples). The
fine tier admits tiles in priority order while the sum of cells times the requested time
scale stays inside that capacity; everything else runs at the coarse tier. When the
player's own tile cannot be admitted at the requested time scale, the rate is held and
reported, as today. A tile that is still spinning up when the player arrives shows coarse
state labeled as coarse, never blocks walking, and never shows fabricated fine state.

Domain lifecycle belongs to the runtime. `ParkRuntime` adds and removes domains at
quantum boundaries, records each membership change with the domain's water, heat and
solute stores, and keeps one checkpoint per rollback granule under a per-domain byte cap
(`fixes-67`). For the Firehole heat transport, `residency.py` keeps every segment resident
in one of two representations: fine segments inside the admitted anticipation set and
coarse segments of merged control volumes on the same solver elsewhere, with activation
spin-up in worker processes and a conservative hand-off at each change (`fixes-69`). The
LiveEngine bridge still holds the engine's own per-frame checkpoints, and LiveEngine
ecology, solutes and actors have no coarse representation. The six requirements of
`yellowstone_midway/docs/park_runtime/02_SIMULATION_AND_STATE.md` (control volume
identity, conservative restriction and prolongation, physical halos, synchronized
subcycling, flux reconciliation across level changes, fine, coarse and adaptive
comparison) gate any fine domain whose boundary is fed by the coarse tier.

History is bounded by bytes. Lookahead keeps sparse full checkpoints (one per rollback
granule, set by the intervention latency the player accepts) and light frames between
them; a domain's retained history has a stated byte cap, and the runtime refuses a horizon
that exceeds it. Retirement writes the portable checkpoint (`LiveEngine.export_state`) to
disk and frees the in-memory copies.

The coarse tier is also paged. Its resident state per sub-basin is small (snow bands,
storages, phenology, a reach-scale routing state), but its inputs are not: forcing grids,
the NHDPlus HR flowline network, LANDFIRE cover and gauge records are read per sub-basin
from frozen bundles with a byte budget, and only the sub-basins inside the anticipation
set's dependency closure, plus the ones the far terrain shows, hold forcing at full
temporal resolution. The rest step at the coarse hourly step from summary forcing.

Processes: one owner per domain; CPU-bound domains run in separate long-lived worker
processes with explicitly serialized regional state, sized to measured cores, because the
Python interpreter lock serializes work inside one process. Godot never waits on Python
to render or walk.

## 8. Wire protocol

The wire carries timing and conditions explicitly.

Godot to Python, `POST /api/live/focus`, sent every 1.0 s and immediately when the reach
set changes: `{t_s, position_m: [x, y, z], velocity_mps: [vx, vy, vz], view_dir: [dx, dy,
dz], fov_deg, reach: [ids], resident: {id: tier}, time_scale}`. Python answers `{active:
[ids], activating: [ids], retiring: [ids], effective_rate, reach, visible: {id:
margin_m}}`, where `visible` is the numpy viewshed of section 5 keyed by tile id with the
height by which the tile clears the horizon, so Godot can rank tiles without recomputing
the march.

Python to Godot, frames: `GET /api/live/frames?after_t_s=&player_t_s=&time_scale=&tiles=`
stays the present endpoint with a tile list; a frame carries state only for the listed
tiles, keyed by tile id, so that frame size scales with the island and not with the park. The
existing reset and truncate semantics on revision change are unchanged.

Baked mode: per-tile sidecars under `data/tiles/<id>/` and the index file; the watcher
applies a tile's sidecars within two seconds of a revision change, as today for the whole
world.

Conditions on the wire, in order of evaluation each poll: the reach set is computed from
`p` and `q`, then the visible set from the freshest viewshed, then the tier of every tile
from importance and budget; tiles newly in the reach set are requested from the loader and
reported to Python in the same second; a reach tile becomes walkable only when its packed
scene is attached and Python has reported it `active` or the world is in baked mode; a
visible tile shows at whatever tier is resident and never blocks on Python; a tile is
retired in Python only after it has left the reach set and the hysteresis window has
passed; a rebase happens on the frame the player crosses a 1,024 m cell edge and before any
attach on that frame.

## 9. Data sources per tile

Elevation: USGS 3DEP 1 m lidar products from the WY YellowstoneNP 2020 QL1 collection where
flown, fetched per tile window by a generalized `tools.fetch_lidar_canopy` (which already
takes a window and a cache); 3DEP 1/3 arc-second seamless elevation elsewhere and for L2 to
L4. Imagery: USDA NAIP for the chosen year, recorded per tile as the present
`MAT_IMAGERY_DATE_UTC` is recorded for Midway. Hydrography: NHDPlus HR flowlines,
waterbodies and HUC-12 boundaries, which also define the coarse tier's sub-basins. Roads and
trails: the NPS data store layers already used for Midway. Vegetation cover classes: LANDFIRE
existing vegetation type, public domain, for the generator and the coarse tier. Weather and
snow: the SNOTEL stations inside and around the park through the existing AWDB client, Open-
Meteo forcing for the air temperature field, and the USGS gauges for the hydrology tier,
starting with Firehole River at Old Faithful (06036805, already in use) and Yellowstone River
at Corwin Springs (06191500), the rest taken from the NWIS site list for the park. Thermal
features: the NPS thermal inventory where it is accessible per feature, otherwise the chloride
flux records at the gauges for basin totals; the fetched records carry their terms as the
star catalog does now. Every fetched input is a frozen bundle with a provenance sidecar,
hashed into the tile's build key.

## 10. Measurements before implementation

Each is the smallest action that settles a sizing assumption, with the expectation it tests.

1. Engine step cost per river cell at dt 1 s on this machine. Expectation: tens of
   microseconds per cell per step, so that a two-block reach set with up to 1,500 cells can
   run 3600x on one core; if it is hundreds, the reach set at high rates is one block from
   the start. Measured in section 7.1: the per-cell cost holds and the 3600x expectation
   does not.
2. Threaded load and attach of one L1 packed scene built from a 264 KB heightfield with its
   placements. Expectation: load under 60 ms on the worker, attach under 4 ms on the main
   thread; if attach is above 8 ms, mesh construction moves off the main thread or the tile
   is split into 512 m scenes.
3. Watcher cost of hashing `ecosystem.json` once per second as the code does today.
   Expectation: above 50 ms per poll, which is a frame hitch already present and the reason
   the index file replaces per-file hashing first.
4. Instance count per tier A tile from the census density at 20,000 crowns per km2.
   Expectation: 20,000 instances per tile and up to 500,000 across the tier A set, which
   requires the per-tile MultiMesh with impostors beyond 1,000 m; if the frame cost is still
   too high at that count, tier A placements outside the reach set become impostors only.
5. Rebase correctness: a scripted walk across the Midway domain with rebase every 1,024 m
   and the player's absolute position, velocity and look direction compared before and
   after each rebase. Expectation: continuity within float tolerance and no physics
   excursion; this test goes into `tests/` of the Godot project.
6. Viewshed cost: the azimuth march of section 5 over the 64 m and 256 m levels, timed in
   GDScript on a worker thread and in numpy. Expectation: under 40 ms in GDScript and under
   2 ms in numpy, so the baked-mode fallback updates at 1 Hz and the live path at every
   focus call; if GDScript is above 100 ms the fallback drops to 4 degree bins.
7. Viewshed correctness at Midway: from the Grand Prismatic overlook the basin tiles are
   visible; from the base of the Midway Bluff with the bluff behind the player, the tiles
   beyond it are occluded and are not resident. Expectation: both hold with the 30 m
   margin; if the second fails, the margin is too wide for the 64 m level and the test
   moves to the 16 m level inside 5 km.
8. Frame cost by tier mix: the same viewpoint rendered with every visible tile at tier D,
   then B, then A, with frame time, triangles and instances recorded. Expectation: the
   binding budget shows itself as the first tier change that moves frame time; that budget
   is the one section 5 enforces, and the other two are kept as ceilings.
9. Tile activation spin-up: wall time to bring one L1 tile from coarse state to a valid
   fine state, run in a worker process while the island steps. Expectation: under the
   time a walker needs to cross one L1 tile (about 12 minutes at 1.4 m/s); if it is
   longer, the anticipation horizon of section 7.1 grows or the tile is split.
   Measured on the Midway engine (build `db183e56a88e`, 276 cells, 1 s step, 10 s frames,
   Apple M4 shared with other processes at load average 6 to 7): building the fine engine
   from the published build takes 1.6-1.9 s and one simulated hour of spin-up takes
   4.8-6.1 s alone and 5.6 s while a second worker process steps an island. No coarse tier
   exists, so the engine starts from the published build state. The expectation holds
   with two orders of magnitude to spare for one Midway-sized domain.
10. Lookahead memory per domain with sparse checkpoints. Expectation: under 64 MiB for one
    simulated hour of the Midway domain, against 314 MiB measured with a full checkpoint
    per 10 s frame. Measured with traced allocations over one simulated hour at 10 s
    frames, above the 80.7 MiB built engine: 314 MiB with a checkpoint per frame (361),
    155 MiB with one per 60 s (61) and 129 MiB with one per 300 s (13, about 0.5 MiB
    each); the 361 frames alone hold 122.6 MiB, about 0.34 MiB per frame. The
    expectation does not hold: sparse checkpoints remove most checkpoint memory, and the
    frame payload becomes the limit, so lookahead frames need a lighter form or a longer
    interval before 64 MiB is reachable.
11. Coarse tier resident bytes and step cost over the whole park with paged inputs.
    Expectation: under 256 MiB resident and under 1 s of one core per simulated hour;
    above that, sub-basins outside the dependency closure step at a longer interval.
12. Multi-process scaling: two fine domains in two worker processes against one process.
    Expectation: near twofold capacity; if not, the transport or the lock is the limit.
    Measured with `LiveEngine._assess_max_dt_capacity` on two copies of the Midway engine,
    as simulated seconds per wall second at the maximum step: one engine alone 498-675,
    against about 300 in section 7.1 at the same settings, cause not isolated; two
    engines on two threads of one process 444-666 in aggregate, so the interpreter lock
    gives no gain; two engines in two worker processes 677-1034 in aggregate, 1.0-1.5
    times the single engine measured alongside. The machine carried other load (load
    average 6 to 7), so the process figure is a lower bound and a quiet-machine run
    settles whether the near-twofold expectation holds.

## 11. Migration order from Midway

Each step leaves Midway playable and is accepted by a stated check.

1. Tile index and rebase owner in `world.gd`, with the present domain treated as 16 L1 tiles
   around the existing origin. Accepted when the rebase walk test passes and the study scene
   renders unchanged.
2. The authored scene split into per-tile packed scenes by a bake tool, using the existing
   `cut_master_tiles` as the precedent; `authored_world.tscn` retired from the runtime path.
   Accepted when the baked Midway matches the previous render within an image tolerance
   from the four starting places and height probes at the existing QA points agree.
3. Park-wide L2 to L4 terrain from 3DEP 1/3 arc-second as horizon, with the far material,
   and the viewshed march over it driving residency and tiers. Accepted when known summit
   elevations are within 10 m of the source, the occlusion test of section 10 passes at the
   Midway Bluff, and the ridge lines from the Midway overlook agree with dated photographs;
   the last part is Keith's call.
4. The focus endpoint, per-tile sidecars and the index file, with the watcher reading the
   index. Accepted when the study scene behaves as before in both modes and the measured
   poll cost drops below 5 ms.
5. Simulation residency on Midway: the Firehole split into at least two domains with a
   conservative interface, `ParkRuntime` domain add and remove at quantum boundaries,
   sparse-checkpoint history under a byte cap, the anticipation set and admission control
   of section 7.1, and worker processes. Accepted when a walk along the Firehole activates
   the downstream domain before arrival, retires the upstream one with a passing ledger,
   the split run matches the single-domain run within tolerances set before the run, and
   measurements 9, 10 and 12 are recorded.
6. The first new ground: Lower Geyser Basin and the Upper Geyser Basin as L1 tiles with 1 m
   cores, joining the Firehole reach. Accepted when discharge is conserved across every tile
   seam on the river, the Grand Loop Road and trails are continuous across seams, and the
   fine tier activates and retires the new tiles with a passing conservation ledger.
7. The coarse hydrology tier over the whole park, with paged inputs (measurement 11).
   Accepted as a hindcast against the named gauges with evaluation datasets listed; the claim stays `not_yet_accepted` until a
   locked-final window is evaluated under the registry rules.

## 12. Risks and open points

Float precision is handled by the rebase, and the rebase is the one place a single missed
node produces a visible jump; the catalog of nodes that must move is enumerated in `world.gd`
and the walk test covers it. The viewshed is only as good as the coarse heightfield: a
narrow ridge smoothed away at 64 m can hide ground that is in fact visible, which the 30 m
margin and the 16 m fallback inside 5 km address, and a forest that does hide ground is
invisible to the test, which only costs budget. Seams between levels need the stitch band
and a physics check. Vegetation at park scale is only feasible as a derived per-tile product, which
means authored placements remain the exception. The coarse tier's sub-basin routing is a
new model class and arrives with the same evidence status as everything else: illustrative
until evaluated. Lakes are out of scope of the fine tier until a water column model exists.
Data volumes are fine on disk (about 2.5 GB at 4 m plus cores) but not in the public
repository; tile packages are a release asset, not git content.

An attention mode is a one-term change to the importance score of section 5: add the
cumulative time a tile has spent inside the frustum, decaying while it is unseen, so a place
grows finer the longer the player looks at it and the budget follows the gaze. The viewshed,
the tiers and the budgets are unchanged; only the ranking moves. Recorded as an option for
Keith to choose, with the weight and decay as the two knobs.

Decisions already taken in this document, each reversible: the tile edge is 1,024 m at L1
and quadruples per level; the Midway origin stays the park origin; the rebase cell is one
L1 tile; rendering residency follows the viewshed and the view direction, simulation
residency follows the reach set; the reach set is two 3 x 3 blocks with a one-block
fallback. The hero core list is Keith's to author.

## Prior art consulted

Game catalog rows: `a-region-gate-is-asked-of-the-chunk-not-of-a-column`,
`world-build-queue-with-synchronous-drain`,
`a-budget-spent-from-the-drain-is-not-a-budget-on-the-tick`,
`a-technique-has-a-scope-not-a-price`, `a-port-carries-the-source-worlds-scale`,
`one-placement-law-not-six`. The catalog has no rows yet on origin rebasing, LOD pyramids,
velocity prefetch or simulation region activation; the measurements in section 10 are what
would populate them. The coast prototype's streaming loop and the shared world contract's
chunk lifecycle are cited in sections 1, 5 and 7.
