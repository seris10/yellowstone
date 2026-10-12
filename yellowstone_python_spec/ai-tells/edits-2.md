Fix AI tells in the GDScript, Python, and shader files under `/Users/kreed/Downloads/yellowstone_midway/`. For each file listed below, read the file, find the specific comment, and replace it with the proposed fix. Do NOT change any code logic — only comment text.

**Rules:**
- Only edit comments (lines starting with # or // or inside docstrings)
- Do NOT change any code logic
- Do NOT delete comments entirely unless specified
- Preserve indentation
- If a comment spans multiple lines, replace the entire block

**Files and fixes:**

1. `scripts/ecosystem.gd`
   - L3-6: Replace the 4-line comment block with: `## Reduced observational model. Transport units: seconds, m3/s, m3, Celsius. Water geometry fixed. River internal heat flux paired. Unknown tributary flows omitted from ecosystem.json.`
   - L25: Replace `# Kept for interface compatibility; transport is always 1:1.` with `# Transport is 1:1.`
   - L75: Replace `# This compact model deliberately supports one chain, not arbitrary branching.` with `# Supports one chain.`
   - L102: Replace `# Retain elapsed-time debt after a slow frame; never silently lose physical time.` with `# Retain elapsed-time debt after a slow frame.`
   - L171: Replace `# Newton exchange is an illustrative lumped heat-loss term, not full surface physics.` with `# Newton exchange is a lumped heat-loss term.`
   - L181: Replace `# Relative visual suitability only: this is not a mortality prediction.` with `# Relative visual suitability only.`
   - L263: Replace `# Missing habitat cannot silently become the first patch.` with `# Missing habitat raises.`
   - L267: Replace `# Artistic condensation visibility proxy; not a steam mass or thermal-hazard model.` with `# Artistic condensation visibility proxy.`
   - L271-272: Replace with: `# Magnus form, same convention as yellowstone_python.microclimate.`
   - L276-288: Replace the entire 13-line comment block with: `# Visible plume is condensed droplets. Mirrors yellowstone_python.microclimate.condensation_potential: entrained mixed parcel (30% surface-saturated, 70% ambient) is supersaturated when its vapor exceeds saturation. Returns relative supersaturation of the mixed parcel: (q_mix - es(t_mix)) / es_surf, bounded in [0,1]. Model output; renderer scales it (see STEAM_DENSITY_SCALE).`

2. `scripts/python_river_replay.gd`
   - L4-7: Replace with: `## Python owns river thermal state when replay_path is nonempty.` / `## Empty path uses the built-in ecosystem.` / `## Replay interpolation is presentation, not a second solver.`
   - L170: Replace `# Existing ecological transactions retain their physical-time update.` with `# Ecological transactions retain their physical-time update.`
   - L206: Replace `# Retained artistic activity proxy, NOT mortality or refuge behavior.` with `# Artistic activity proxy.`
   - L211: Replace `# Hold air forcing as Python did; do not independently evolve it.` with `# Hold air forcing as Python did.`
   - L220: Replace `# Keep the original six-reach consumer interface as point probes.` with `# Six-reach consumer interface as point probes.`
   - L231: Replace `# Use the last completed frame budget. Do not interpolate diagnostics.` with `# Use the last completed frame budget.`
   - L241: Replace `# Piecewise-constant spatial field; downstream cell owns an internal face.` with `# Piecewise-constant spatial field.`
   - L283: Replace `# This is a query extent for aquatic actors, not a surveyed bank test.` with `# Query extent for aquatic actors.`
   - L290: Replace `# Legacy z-only callers remain compatible. New fish calls use position.` with `# z-only callers use z; fish calls use position.`
   - L311: Replace `# Optional observation overlays can read the same authoritative state.` with `# Observation overlays read the same state.`

3. `scripts/world.gd`
   - L2-3: Replace with: `## Runtime assembles saved authored assets.`
   - L7-8: Replace with: `## Study scenes set this to a Python replay JSON (see scenes/study.tscn).` / `## Empty uses the live ecosystem.`
   - L33-34: Replace with: `# Bake-time environment sets; groups assigned once by bake_world.gd.`
   - L39-40: Replace with: `# Cap frame rate: uncapped Compatibility renderer cooks laptops.`
   - L94-95: Replace with: `# Study scenes play Python-owned thermal replays.`
   - L121-122: Replace with: `# Season switch alters surfaces only: snow cover from season.json.`
   - L402-403: Replace with: `# Condensation model (mirrors yellowstone_python.microclimate): humidity and wind drive the plume.`

4. `scripts/wildlife_actor.gd`
   - L3-5: Replace with: `## Articulated shape proxies at approximate real dimensions.` / `## Routes and counts authored in JSON.` / `## Actors never sample new habitat at runtime.`
   - L36-40: Replace with: `## Licensed third-party fauna models (data/asset_manifest.json).` / `## Models face +Z as shipped; yaw PI turns them to Godot-forward (-Z).` / `## "ground" places the AABB bottom at y=0; "center" centers vertically (fish).` / `## Per-individual tint from record.individual.tint_rgb.`
   - L85: Replace `# licensed model instantiated; proxy builders skipped` with `# Licensed model instantiated.`
   - L109-112: Replace with: `## Instantiate the licensed model, normalize to the record's body length, apply individual tint. Returns false when asset or record length missing.`
   - L211: Replace `# No fallbacks to thermal pools, lakes, unknown tributaries, or terrain height.` with `# No fallbacks to thermal pools or unknown tributaries.`
   - L331: Replace `# Travel time is separate from the observable stationary foraging bout.` with `# Travel time separate from foraging bout.`
   - L401: Replace `# River routes interpolate saved water elevations, never the terrain bed.` with `# River routes interpolate saved water elevations.`
   - L436: Replace `# Asset-backed model has no articulated tail node; gentle whole-body roll.` with `# Asset-backed model has no tail node; whole-body roll.`
   - L564-565: Replace with: `# Mesh construction has a 0.31m beak-to-tail envelope before scaling.` / `# Species sizes: 0.20m dipper, 0.55m raven.`
   - L604: Replace `# Offsets are recorded individually, not randomly scattered at startup.` with `# Offsets recorded individually.`

5. `scripts/height_field.gd`
   - L3-4: Replace with: `## Shared terrain authority, row zero is north. Triangle interpolation matches rendered/collision diagonals.`

6. `scripts/authored_placement.gd`
   - L4-5: Replace with: `## Add this node in handcrafted_details.tscn, choose a PackedScene, and position it normally. Transform is authored scene data.`
   - L29-30: Replace with: `# Ownership stays with this authored wrapper.`

7. `scripts/pool_overlay.gd`
   - L3-7: Replace with: `## Runtime shim: assigns Python-authored pigment ramps to baked thermal pools.` / `## Reads res://data/pool_shells.json and res://assets/textures/pool_ramps/<shell_id>.png.` / `## Guarded: without sidecars, two-color water look is used.`

8. `scripts/thermal_probe_overlay.gd`
   - L3-5: Replace with: `## Optional simulated-temperature markers.` / `## Fixed color scale supports comparison between control and pulse runs.`
   - L20-21: Replace with: `# Ecosystem node created at runtime by world.gd; resolve lazily in _process.`

9. `scripts/player.gd`
   - L3: Replace `## Distances in metres, velocities in metres/second. Camera never bobs by default.` with `## Distances in meters, velocities in meters/second. Camera does not bob by default.`
   - L41: Replace `# Probe head height ahead, then down: step onto ground within reach.` with `# Probe head height ahead, then down.`
   - L82-83: Replace with: `# Step-up assist for boardwalk lips and deck edges: snap alone pulls downward.`

10. `tools/bake_botany.gd`
    - L2-4: Replace with: `## Offline authoring tool. Every clump has a fixed JSON record and identity.` / `## Creates genus/guild shape proxies.` / `## Run after terrain changes: godot --headless --path . --script tools/bake_botany.gd`
    - L188: Replace `# Bake every individual stem base on exactly the same triangle terrain as walking.` with `# Bake stem bases on the same triangle terrain as walking.`
    - L306: Replace `# Separate banner, two wing petals, and a small pale keel form a pea-like flower.` with `# Banner, two wing petals, and a pale keel form a pea-like flower.`

11. `tools/validate_walk.gd`
    - L2-6: Replace with: `## Focused collision integration test.` / `## godot --headless --fixed-fps 60 --path . --script tools/validate_walk.gd` / `## The player class supplies its capsule, floor angle, snap and safe margin.` / `## Acceleration/gravity driven by deterministic waypoint input.`
    - L33: Replace `# Match player.gd ordinary walking, with jump/flight/input capture omitted.` with `# Match player.gd walking.`
    - L97: Replace `# Allow static native collision shapes to register with the physics server.` with `# Allow static collision shapes to register.`
    - L112: Replace `# Negative controls: the same probe and gates, aimed where walking must fail.` with `# Negative controls: probe aimed where walking must fail.`
    - L149: Replace `# This is the one initial placement for this independent case.` with `# One initial placement for this case.`

12. `tools/validate_baked.gd`
    - L2-3: Replace with: `## Validate exported mesh/collision resources. Detects reversed rows, wrong offsets and seams.`

13. `tools/bake_world.gd`
    - L2-3: Replace with: `## Offline only. Produces native .tscn/.res assets.` / `## Run: godot --headless --path . --script tools/bake_world.gd`
    - L60-62: Replace with: `# RenderingServer bulk layout: three row-major vec4s, then color/custom.` / `# Bulk assignment retains CPU data in headless bakes.`
    - L179: Replace `# Tint stores source→mouth fraction in COLOR.r (1 at source).` with `# Tint stores source-to-mouth fraction in COLOR.r.`
    - L210-212: Replace with: `# Dirt tread is ground, not deck: drape to terrain.` / `# Bridge spans keep deck height.`
    - L222-225: Replace with: `# Tread lives in the terrain mask; mesh survives where the engineered profile leaves the ground. Deck where gap exceeds 0.35 m, with dirt skirts. Step-up (0.55 m) covers joints.`
    - L264: Replace `# Native mesh supports and endcaps are authored at fixed path stations.` with `# Mesh supports and endcaps at fixed path stations.`
    - L280-281: Replace with: `# Close both ribbon ends with quads dropping to ground.`
    - L303-304: Replace with: `# Drop both deck edges to ground so the boardwalk has sides.`
    - L344-345: Replace with: `# Reuse every bend and the surface ribbon's shared offset vertices.`
    - L400: Replace `# A hot outflow remains a flowing ribbon; the thermal flag selects color.` with `# Hot outflow is a flowing ribbon; thermal flag selects color.`
    - L409-410: Replace with: `# Visible current: faster ripple drift; cooling and foam from tinted COLOR.r.`
    - L446-447: Replace with: `# Ear-clip the saved polygon for a concave shoreline.`
    - L463-464: Replace with: `# Forward path for Python-authored pigment ramps.`
    - L524-525: Replace with: `# The mapped spur enters from the east. A short ramp connects its surface to the raised deck.`
    - L537-538: Replace with: `# Explicit timber members with an open southern approach.`
    - L568: Replace `# Fixed explicit asset geometry, reused by authored scene instances.` with `# Fixed asset geometry reused by scene instances.`
    - L674-675: Replace with: `# Replace cutout surfaces with the shared wind shader.`
    - L724: Replace `# Sparse trunk colliders stay at the same fixed placement as meshes.` with `# Trunk colliders at the same placement as meshes.`

14. `tools/recolor_goose_texture.gd`
    - L2-5: Replace with: `## Recolor the CC-BY mallard base texture into a Canada goose palette.` / `## Derivation: green head -> black, orange bill/feet -> black, body gray-brown -> Canada brown, white ring kept.` / `## godot --fixed-fps 60 --path . --script tools/recolor_goose_texture.gd`
    - L40: Replace `# Mallard drake green head -> Canada goose near-black head/neck.` with `# Green head -> near-black head/neck.`
    - L44: Replace `# Orange bill/feet -> dark (goose bill/legs are black).` with `# Orange bill/feet -> dark.`
    - L48: Replace `# Neutral gray-brown body -> warmer Canada brown-gray.` with `# Gray-brown body -> Canada brown-gray.`

15. `tools/validate_multimesh.gd`
    - L2-5: Replace with: `## Validate saved instance arrays without dummy-renderer getters.` / `## Run: godot --headless --path . --script tools/validate_multimesh.gd` / `## Requires a complete offline bake. Does not mutate the world.` / `## Buffer order: RenderingServer.multimesh_set_buffer.`
    - L76-77: Replace with: `# Three pine meshes plus one distant representation; each group occupies a 128 m tile.`
    - L120: Replace `# Read row-major serialization back into Godot's column-vector Basis.` with `# Read row-major serialization into column-vector Basis.`
    - L148-151: Replace with: `# Source mesh families disambiguate co-located tree/log/rock records. Source pines ~15 m high; grass clumps under 0.4 m. Node names unreliable after LOD renaming.`
    - L308-309: Replace with: `# Compose saved Node3D transforms on the CPU.`

16. `tools/prepare_world.py`
    - L2-6: Replace with: `"""Offline authoring compiler. Never run at game start.` / `Reads saved geodata, writes an explicit static world and reviewable placement list.` / `No synthetic terrain. --placements-replace required before overwriting existing placement authorship.`
    - L46-54: Replace with: `"""Keep the complete 4 m terrain triangles beneath narrow visible channels."""`
    - L80-85: Replace with: `"""Least-squares non-increasing profile using pooled adjacent violators."""`
    - L96: Replace `"""Cluster actual shared endpoints; leave unrelated nearby path interiors alone."""` with `"""Cluster shared endpoints."""`
    - L114: Replace `"""Fit connected Firehole reaches together, then pin tributary outlets to them."""` with `"""Fit connected Firehole reaches, then pin tributary outlets."""`
    - L126-127: Replace with: `# Each clipped component is independently continuous.`
    - L149-151: Replace with: `# Undirected tributary trees oriented toward an existing mainstem confluence, or toward their lowest boundary outlet.`
    - L194: Replace `"""Make intersecting route endpoints one level, with short smooth approach ramps."""` with `"""Make intersecting route endpoints one level."""`
    - L213-219: Replace with: `"""Extend bridge grades onto dry approaches."""`
    - L267: Replace `# Preserve shared endpoint levels and every existing bridge vertex exactly.` with `# Preserve shared endpoint levels and bridge vertices.`
    - L275-281: Replace with: `"""Remove coarse-grid protrusions through the actual ramp triangles."""`
    - L307-312: Replace with: `"""An explicitly authored representative outlet, tied to pool and river levels."""`
    - L349: Replace `# same physical alignment as Fairy Falls Trail` with `# Aligned with Fairy Falls Trail`
    - L357: Replace `# Plank thickness, bridge elevations and crossfall are art/engineering values.` with `# Plank thickness and bridge elevations are art/engineering values.`
    - L361: Replace `# Hydrology keeps the source centerline. Authored widths are not surveyed banks.` with `# Authored widths are not surveyed banks.`
    - L386: Replace `# Lakes use official polygons; unknown waterbodies remain unlabeled in game.` with `# Lakes use official polygons.`
    - L396-397: Replace with: `# DEMs do not measure bathymetry. Carve modest invisible bathymetry for visual integration.`
    - L406-407: Replace with: `# Grade roads to source cross-section center heights with a two-metre verge blend.`
    - L412: Replace `# Bridge detected only when path spans a mapped stream and has land endpoints.` with `# Bridge detected when path spans a mapped stream.`
    - L427: Replace `# preserve every channel support vertex` with `# Preserve channel support vertices`
    - L433-435: Replace with: `# Re-grade corrected road approaches after snapping endpoint levels. Stream exclusions preserved.`
    - L442-443: Replace with: `# Native/asphalt trail approaches receive local verge grading.`
    - L458: Replace `# Record the authored revision, retaining original DEM unmodified in references.` with `# Record the authored revision.`
    - L462-463: Replace with: `# Painted habitat support derived from photographed cover, overridden by explicit constraints.`
    - L471: Replace `# Fixed material noise is surface microdetail only, never geometry/placement.` with `# Material noise is surface microdetail only.`
    - L477: Replace `# Tangent normal map is x/right, y/up the texture, z/normal.` with `# Tangent normal map: x/right, y/up, z/normal.`
    - L480: Replace `# Cropped thermal apron photo uses real mineral drainage fingers and colors.` with `# Cropped thermal apron photo uses real mineral drainage colors.`
    - L482-483: Replace with: `# Explicit scene anchors, source-aligned where named.`
    - L498-499: Replace with: `# Offline proposals from measured cover.` / `# Editing uses placement_overrides.json; positions never sampled at run time.`
    - L507-508: Replace with: `# Jittered candidate cells are a drafting aid. Accepted transforms persisted with stable IDs.`
    - L518: Replace `# Walkable corridors receive close groundcover, leaving fragile thermal crust bare.` with `# Walkable corridors receive groundcover; thermal crust stays bare.`

17. `tools/validate_world.py`
    - L2: Replace `"""Checks invariants that can break a real-scale connected landscape."""` with `"""Checks invariants for a real-scale connected landscape."""`
    - L18: Replace `# Baked tile edges, normals and colliders are independently checked by validate_baked.gd.` with `# Baked tile edges checked by validate_baked.gd.`
    - L19: Replace `# Real geometry seams: test all endpoint pairs within .2m horizontally.` with `# Test endpoint pairs within .2m horizontally.`
    - L40: Replace `# Placement snapshots are data; authoring overrides preserve IDs and scene history.` with `# Placement snapshots are data.`
    - L48: Replace `# Photos are references/CC0 scans, and original source raster is retained.` with `# Photos are references/CC0 scans.`

18. `assets/imported/render_pine_billboards.py`
    - L2-6: Replace with: `"""Render CC0 source-derived distant tree impostors. Run offline.` / `Requires trimesh, pyrender, Pillow, numpy; EGL.`
    - L30-31: Replace with: `# Moderate broad front illumination preserves readable bark.`

19. `assets/imported/prepare_pine_asset.py`
    - L2-13: Replace with: `"""Bake a compact foliage-card derivative of Poly Haven Pine Tree 01 variant b."""`
    - L137-138: Replace with: `# Density cells sample only the source tree's needle geometry.`
    - L166: Replace `# V=0 is the twig tip in this source atlas, V=1 points to the base.` with `# V=0 is the twig tip; V=1 points to the base.`
    - L180-182: Replace with: `# The source atlas contains opaque bleed for other UV islands. Keep only the connected twig.`
    - L206-207: Replace with: `# Keep physical canopy bounds identical at every LOD.`

20. `shaders/terrain.gdshader`
    - L10-12: Replace with: `// Optional snow overlay (season.json + snow_map.png).` / `// snow_amount 0 uses the default look; mask is world-extent with bare thermal holes.`
    - L15-16: Replace with: `// Foot-trail tread painted from mapped polylines (2 m/px). Dirt trails are ground here.`
    - L42-43: Replace with: `// Art direction of the photographed mat colors.`

21. `shaders/water.gdshader`
    - L12-15: Replace with: `// Optional per-pool authored pigment ramp (pool_shells.json + pool_ramps/).` / `// ramp_mix 0 uses the default two-color look. Ramp x=0 is hot center, x=1 outer rim.`
    - L26-28: Replace with: `// Ribbon UV.y is metre arc length in the saved downhill point order.` / `// Pools use slow local wind ripples.`
    - L45-47: Replace with: `// Thermal outflow ribbon: tinted COLOR.r runs 1 at source to 0 at mouth.`

22. `shaders/steam.gdshader`
    - L10-11: Replace with: `// Camera-facing vapor cards advect in the shared world wind. Rotating the card must not rotate its wind direction.`

23. `shaders/trail.gdshader`
    - L4-5: Replace with: `// Saved ribbon UV.y is metres. The tread sits 3 cm proud of the ground.`

24. `shaders/boardwalk.gdshader`
    - L12: Replace `// Once a board is smaller than a pixel, use its area-averaged seam/color.` with `// Below one pixel, use area-averaged seam/color.`
    - L16-17: Replace with: `// Weathered-gray composite decking, dark timber rails on bark_mat. Seams read as narrow shadow gaps.`

25. `shaders/foliage.gdshader`
    - L13: Replace `// Wind is east/south in world space, independent of an authored plant's yaw.` with `// Wind is east/south in world space.`

Make all these edits. Read each file first, then edit.