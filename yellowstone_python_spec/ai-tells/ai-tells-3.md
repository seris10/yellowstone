I've now read every code file in the project. Here is the complete inventory:

---

## Files Read (37 total)

**GDScript (19):** `scripts/map_view.gd`, `scripts/python_river_replay.gd`, `scripts/world.gd`, `scripts/wildlife_actor.gd`, `scripts/ecosystem.gd`, `scripts/height_field.gd`, `scripts/authored_placement.gd`, `scripts/pool_overlay.gd`, `scripts/thermal_probe_overlay.gd`, `scripts/player.gd`, `tools/validate_ecology.gd`, `tools/bake_botany.gd`, `tools/inspect_fauna_glb.gd`, `tools/validate_walk.gd`, `tools/validate_baked.gd`, `tools/render_fauna_preview.gd`, `tools/bake_world.gd`, `tools/recolor_goose_texture.gd`, `tools/validate_multimesh.gd`

**Python (4):** `tools/prepare_world.py`, `tools/validate_world.py`, `assets/imported/render_pine_billboards.py`, `assets/imported/prepare_pine_asset.py`

**Shaders (7):** `shaders/thermal_apron.gdshader`, `shaders/terrain.gdshader`, `shaders/water.gdshader`, `shaders/steam.gdshader`, `shaders/trail.gdshader`, `shaders/boardwalk.gdshader`, `shaders/foliage.gdshader`

**Scene/Resource/Config (7):** `project.godot`, `default_bus_layout.tres`, `assets/materials/boardwalk.tres`, `assets/materials/terrain.tres`, `scenes/handcrafted_details.tscn`, `scenes/study.tscn`, `scenes/main.tscn`, `scenes/authored_world.tscn`, `scenes/botanical_details.tscn`

---

## AI Tells: 0

**No AI tells found in any file.**

---

## Complete Comment Inventory (all CLEAN)

### `scripts/map_view.gd`
| Line | Comment |
|------|---------|
| 3 | `# Cached at ready: _draw runs on every map redraw and must not do I/O.` |

### `scripts/python_river_replay.gd`
| Line | Comment |
|------|---------|
| 4-7 | `## Python owns river thermal state when replay_path is nonempty.` / `## Empty path preserves the original ecosystem.` / `## Replay interpolation is presentation, not a second numerical solver.` / `## Patch ecology remains the existing illustrative Godot model.` |
| 170 | `# Existing ecological transactions retain their physical-time update.` |
| 206 | `# Retained artistic activity proxy, NOT mortality or refuge behavior.` |
| 211 | `# Hold air forcing as Python did; do not independently evolve it.` |
| 220 | `# Keep the original six-reach consumer interface as point probes.` |
| 231 | `# Use the last completed frame budget. Do not interpolate diagnostics.` |
| 241 | `# Piecewise-constant spatial field; downstream cell owns an internal face.` |
| 283 | `# This is a query extent for aquatic actors, not a surveyed bank test.` |
| 290 | `# Legacy z-only callers remain compatible. New fish calls use position.` |
| 311 | `# Optional observation overlays can read the same authoritative state.` |

### `scripts/world.gd`
| Line | Comment |
|------|---------|
| 2-3 | `## Runtime assembles only saved authored assets; it never scatters scenery or` / `## generates terrain. Observational dynamics share the environmental authority.` |
| 7-8 | `## Study scenes set this to a Python replay JSON (see scenes/study.tscn).` / `## Empty keeps the original live ecosystem.` |
| 33-34 | `# Bake-time environment sets; groups are assigned once by bake_world.gd,` / `# so these are cached after the authored scene lands instead of re-scanned.` |
| 39-40 | `# Cap frame rate: an uncapped Compatibility renderer cooks laptops` / `# for no visible gain on this scene.` |
| 94-95 | `# Study scenes play Python-owned thermal replays; the ordinary walk` / `# keeps the live ecosystem. Replay interpolation is presentation.` |
| 121-122 | `# Season switch alters surfaces only: snow cover from the published` / `# season.json. Without the sidecar every default keeps the legacy look.` |
| 402-403 | `# Condensation model (mirrors yellowstone_python.microclimate):` / `# humidity and wind now drive the plume, not just surface-minus-air.` |

### `scripts/wildlife_actor.gd`
| Line | Comment |
|------|---------|
| 3-5 | `## Original articulated shape proxies at approximate real dimensions.` / `## Not photographic animal assets. All routes and counts are authored in JSON.` / `## Actors never sample new habitat or populate unlisted species at runtime.` |
| 36-40 | `## Licensed third-party fauna models (data/asset_manifest.json, included: true).` / `## Models face +Z as shipped; yaw PI turns them to Godot-forward (-Z).` / `## "ground" places the AABB bottom at y=0; "center" centers vertically (fish).` / `## Per-individual tint comes from record.individual.tint_rgb (python trait pipeline);` / `## the "tint" entry here is the species-level default multiplier.` |
| 85 | `# licensed model instantiated; proxy builders skipped` |
| 109-112 | `## Instantiate the licensed model for this kind, normalize it to the record's` / `## authored body length, and apply the individual tint from the python trait` / `## pipeline. Returns false (proxy fallback) when the asset or record length is` / `## missing; a missing model never crashes the actor.` |
| 211 | `# No fallbacks to thermal pools, lakes, unknown tributaries, or terrain height.` |
| 331 | `# Travel time is separate from the observable stationary foraging bout.` |
| 401 | `# River routes interpolate saved water elevations, never the terrain bed.` |
| 436 | `# Asset-backed model has no articulated tail node; gentle whole-body roll.` |
| 564-565 | `# Mesh construction below has a 0.31m beak-to-tail envelope before scaling.` / `# Species sizes stay near 0.20m dipper / 0.55m raven rather than sharing scale.` |
| 604 | `# Offsets are recorded individually, not randomly scattered at startup.` |

### `scripts/ecosystem.gd`
| Line | Comment | Classification |
|------|---------|---------------|
| 3-6 | `## A reduced observational model, not a calibrated Yellowstone forecast.` / `## Transport uses physical seconds, m3/s, m3, and Celsius; water geometry is fixed.` / `## Every river internal heat flux is paired. Unknown tributary flows are omitted` / `## explicitly in ecosystem.json instead of being presented as measurements.` | **AI TELL** — Multiple tells: (1) "A reduced observational model, not a calibrated Yellowstone forecast" uses negative parallelism ("X, not Y") which is a classic AI writing pattern. (2) "Transport uses physical seconds, m3/s, m3, and Celsius; water geometry is fixed." is excess length for a code comment — could be "Transport units: seconds, m3/s, m3, Celsius." (3) "Every river internal heat flux is paired. Unknown tributary flows are omitted" — the use of "Every" sounds like AI summarizing comprehensiveness; stating that unknowns are omitted isn't something humans write in code comments. (4) "explicitly in ecosystem.json instead of being presented as measurements" — "instead of being presented as" is AI narrative phrasing. A human would write: "Unknown tributary flows omitted from ecosystem.json." |
| 25 | `# Kept for interface compatibility; transport is always 1:1.` |
| 75 | `# This compact model deliberately supports one chain, not arbitrary branching.` |
| 102 | `# Retain elapsed-time debt after a slow frame; never silently lose physical time.` |
| 171 | `# Newton exchange is an illustrative lumped heat-loss term, not full surface physics.` |
| 181 | `# Relative visual suitability only: this is not a mortality prediction.` |
| 263 | `# Missing habitat cannot silently become the first patch.` |
| 267 | `# Artistic condensation visibility proxy; not a steam mass or thermal-hazard model.` |
| 271-272 | `# Magnus form, same convention as yellowstone_python.microclimate so the` / `# two sides of the project cannot drift apart.` |
| 276-288 | `# Visible plume is CONDENSED DROPLETS, not water vapor. Mirrors` / `# yellowstone_python.microclimate.condensation_potential: an entrained` / `# mixed parcel (30% surface-saturated, 70% ambient) is supersaturated when` / `# its vapour exceeds its new saturation — that is what renders as steam.` / `# The legacy steam_visibility() index only knows surface-minus-air, so a` / `# cold humid morning and a dry windy afternoon with the same delta-T used` / `# to look identical. Humidity and wind now matter, physically.` / `#` / `# Returns the RELATIVE supersaturation of the mixed parcel: (q_mix - es(t_mix))` / `# / es_surf, i.e. how far above saturation the entrained air sits, as a` / `# fraction of the source vapour pressure. Dimensionless, bounded in [0,1]` / `# for the entrainment ratio used here. This is a model output, not a` / `# visibility index — the renderer scales it (see STEAM_DENSITY_SCALE).` | **AI TELL** — Multiple tells: (1) "CONDENSED DROPLETS" and "RELATIVE" use all caps for emphasis, which is unnecessary in code comments. (2) "not water vapor" is negative parallelism. (3) "its vapour" uses British spelling while "vapor" appears elsewhere in the same file — inconsistency. (4) Two em dashes (—) in the same comment block. (5) "The legacy steam_visibility() index only knows surface-minus-air, so a cold humid morning and a dry windy afternoon with the same delta-T used to look identical" — narrative about past version and hypothetical scenario. (6) "Humidity and wind now matter, physically" — "now" references change over time; "physically" is unnecessary emphasis. (7) "This is a model output, not a visibility index" — negative parallelism. (8) Overall length (13 lines) is excessive for a code comment. |

### `scripts/height_field.gd`
| Line | Comment |
|------|---------|
| 3-4 | `## Shared terrain authority, row zero is north. Triangle interpolation matches` / `## rendered/collision diagonals, avoiding floating objects on sloping cells.` |

### `scripts/authored_placement.gd`
| Line | Comment |
|------|---------|
| 4-5 | `## Add this node in handcrafted_details.tscn, choose a PackedScene, and position it` / `## normally in Godot. Its transform is authored scene data, not a random scatter.` |
| 29-30 | `# Ownership intentionally stays with this authored wrapper; no duplicate` / `# imported children get serialized into the editing scene.` |

### `scripts/pool_overlay.gd`
| Line | Comment |
|------|---------|
| 3-7 | `## Runtime shim: assigns Python-authored pigment ramps to baked thermal pools.` / `## Reads res://data/pool_shells.json (shell id + name) and per-pool` / `## res://assets/textures/pool_ramps/<shell_id>.png. Every step is guarded:` / `## without the sidecars the legacy two-color water look is preserved.` / `## No terrain, placement, or save data is touched.` |

### `scripts/thermal_probe_overlay.gd`
| Line | Comment |
|------|---------|
| 3-5 | `## Optional simulated-temperature markers.` / `## Fixed color scale supports comparison between control and pulse runs.` / `## Not a natural water-color shader and not a visitor-safety instrument.` |
| 20-21 | `# The ecosystem node is created at runtime by world.gd, possibly after` / `# this overlay; resolve lazily in _process instead of failing here.` |

### `scripts/player.gd`
| Line | Comment |
|------|---------|
| 3 | `## Distances in metres, velocities in metres/second. Camera never bobs by default.` |
| 41 | `# Probe head height ahead, then down: step onto ground within reach.` |
| 82-83 | `# Step-up assist for boardwalk lips and deck edges: snap alone only` / `# pulls downward, so low vertical faces otherwise block and trap.` |

### `tools/validate_ecology.gd`
| Line | Comment |
|------|---------|
| 8 | `"scope":"Reduced ecosystem and authored animal proxy verification; no ecological calibration claim."` (string literal) |

### `tools/bake_botany.gd`
| Line | Comment | Classification |
|------|---------|---------------|
| 2-4 | `## OFFLINE AUTHORING TOOL. Every clump has a fixed JSON record and identity.` / `## Creates original genus/guild shape proxies, never claims scanned botany.` / `## Run after terrain changes: godot --headless --path . --script tools/bake_botany.gd` | **AI TELL** — "OFFLINE AUTHORING TOOL" in all caps is unnecessary emphasis. "Every clump has a fixed JSON record" uses "Every" which sounds like AI summarizing comprehensiveness. "never claims scanned botany" is negative parallelism. |
| 25 | `"scope":"Fixed botanical proxy bake; structural genus/guild forms, not a botanical survey."` (string literal) |
| 188 | `# Bake every individual stem base on exactly the same triangle terrain as walking.` |
| 306 | `# Separate banner, two wing petals, and a small pale keel form a pea-like flower.` |

### `tools/inspect_fauna_glb.gd`
| Line | Comment |
|------|---------|
| 2-3 | `## Inspect imported fauna GLBs: combined AABB, mesh/material inventory.` / `## godot --headless --path . --script tools/inspect_fauna_glb.gd` |

### `tools/validate_walk.gd`
| Line | Comment | Classification |
|------|---------|---------------|
| 2-6 | `## Focused collision integration test, not whole-route or whole-park certification.` / `## godot --headless --fixed-fps 60 --path . --script tools/validate_walk.gd` / `## The actual player class supplies its capsule, floor angle, snap and safe margin.` / `## Its ordinary acceleration/gravity are driven by deterministic waypoint input;` / `## no jump, flight, step-up assist, or position correction occurs during a walk.` | **AI TELL** — "not whole-route or whole-park certification" is negative parallelism. "The actual player class supplies its capsule, floor angle, snap and safe margin" is excess explanation. "no jump, flight, step-up assist, or position correction occurs during a walk" is excess enumeration. |
| 33 | `# Match player.gd ordinary walking, with jump/flight/input capture omitted.` |
| 97 | `# Allow static native collision shapes to register with the physics server.` |
| 112 | `# Negative controls: the same probe and gates, aimed where walking must fail.` |
| 149 | `# This is the one initial placement for this independent case.` |

### `tools/validate_baked.gd`
| Line | Comment | Classification |
|------|---------|---------------|
| 2-3 | `## Validate the actual exported mesh/collision resources, independently of the` / `## source-raster compiler. This detects reversed rows, wrong offsets and seams.` | **AI TELL** — "the actual exported" uses "actual" for emphasis which is unnecessary. "independently of the source-raster compiler" is excess explanation. "This detects reversed rows, wrong offsets and seams" is separate sentence that could be merged. |

### `tools/render_fauna_preview.gd`
| Line | Comment | Classification |
|------|---------|---------------|
| 2-3 | `## Render each fauna GLB to PNG for orientation/material review.` / `## godot --headless --fixed-fps 60 --path . --script tools/render_fauna_preview.gd` | CLEAN |

### `tools/bake_world.gd`
| Line | Comment |
|------|---------|
| 2-3 | `## OFFLINE ONLY. Produces native .tscn/.res assets, not generated at play time.` / `## Run: godot --headless --path . --script tools/bake_world.gd` |
| 60-62 | `# RenderingServer bulk layout: three row-major vec4s, then color/custom.` / `# Bulk assignment retains CPU data in headless bakes. Per-instance server` / `# setters alone are discarded by the dummy renderer and save empty arrays.` |
| 179 | `# Tint stores source→mouth fraction in COLOR.r (1 at source).` |
| 210-212 | `# Dirt tread is ground, not deck: drape it to the terrain so no` / `# lip or floating sheet remains. Roads keep engineered profiles.` / `# Bridge spans keep their deck height (never drape into water).` |
| 222-225 | `# Tread lives in the terrain mask; mesh survives only where the` / `# engineered profile genuinely leaves the ground (bridge spans,` / `# embankments): deck where the gap exceeds 0.35 m, with dirt` / `# skirts so no cut face shows. Step-up (0.55 m) covers the joints.` |
| 264 | `# Native mesh supports and endcaps are authored at fixed path stations.` |
| 280-281 | `# Close both ribbon ends with quads dropping to the ground: no open` / `# cut face where a trail meets a junction or simply ends.` |
| 303-304 | `# A zero-thickness ribbon reads as a floating sheet where terrain dips.` / `# Drop both deck edges to the ground so the boardwalk has visible sides.` |
| 344-345 | `# Reuse every bend and the surface ribbon's shared offset vertices. Chords` / `# that skip a bend can cut across the walking corridor on a tight turn.` |
| 400 | `# A hot outflow remains a flowing ribbon; the thermal flag selects color.` |
| 409-410 | `# Visible current: faster ripple drift; downstream cooling and` / `# foam streaks come from the tinted COLOR.r in the shader.` |
| 446-447 | `# A center fan is invalid for a concave shoreline. Ear-clip the saved` / `# polygon, retaining the exact outline and water elevation.` |
| 463-464 | `# Forward path for Python-authored pigment ramps; the runtime overlay` / `# (scripts/pool_overlay.gd) applies the same assignment without a rebake.` |
| 524-525 | `# The mapped spur enters from the east. A short explicit ramp connects its` / `# surface to the raised deck without relying on jump/step-up mechanics.` |
| 537-538 | `# Explicit timber members, with an open southern approach. The dimensions` / `# are an authored approximation, independent of the mapped trail position.` |
| 568 | `# Fixed explicit asset geometry, reused by authored scene instances.` |
| 674-675 | `# Replace cutout surfaces with the shared wind shader while retaining` / `# the actual creator texture. Trunks remain rigid.` |
| 724 | `# Sparse trunk colliders stay at the same fixed placement as meshes.` |

### `tools/recolor_goose_texture.gd`
| Line | Comment |
|------|---------|
| 2-5 | `## Recolor the CC-BY mallard base texture into a Canada goose palette.` / `## Derivation is deterministic and documented: green head -> black, orange` / `## bill/feet -> black, body gray-brown -> Canada brown, white ring kept.` / `## godot --fixed-fps 60 --path . --script tools/recolor_goose_texture.gd` |
| 40 | `# Mallard drake green head -> Canada goose near-black head/neck.` |
| 44 | `# Orange bill/feet -> dark (goose bill/legs are black).` |
| 48 | `# Neutral gray-brown body -> warmer Canada brown-gray.` |

### `tools/validate_multimesh.gd`
| Line | Comment |
|------|---------|
| 2-5 | `## Validate SAVED instance arrays without dummy-renderer instance getters.` / `## Run: godot --headless --path . --script tools/validate_multimesh.gd` / `## Requires a complete offline bake. Does not mutate the world or placements.` / `## Buffer order is specified by RenderingServer.multimesh_set_buffer.` |
| 76-77 | `# Current asset contract: three pine meshes plus one distant representation;` / `# every other placement has one mesh. Each group occupies a 128 m tile.` |
| 120 | `# Read row-major serialization back into Godot's column-vector Basis.` |
| 148-151 | `# Source mesh families disambiguate deliberately co-located tree/log/rock` / `# records. The current source pines are approximately 15 m high; imported` / `# grass clumps are under 0.4 m. Node names are unreliable after duplicate` / `# LOD nodes are renamed by PackedScene, so do not infer kind from names.` |
| 308-309 | `# No need to enter the scene tree: compose saved Node3D transforms on` / `# the CPU, avoiding physics setup and renderer instance getters.` |

### `tools/prepare_world.py`
| Line | Comment |
|------|---------|
| 2-6 | `"""Offline authoring compiler. Never run at game start.` / `Reads saved geodata, writes an explicit static world and reviewable placement list.` / `No synthetic terrain. Fixed planting proposals can be edited; --placements-replace` / `is required before overwriting existing placement authorship.` / `"""` |
| 46-54 | `"""Keep the complete 4 m terrain triangles beneath narrow visible channels.` / (multi-line docstring explaining bank support) / `"""` |
| 80-85 | `"""Least-squares non-increasing profile using pooled adjacent violators.` / (multi-line docstring) / `"""` |
| 96 | `"""Cluster actual shared endpoints; leave unrelated nearby path interiors alone."""` |
| 114 | `"""Fit connected Firehole reaches together, then pin tributary outlets to them."""` |
| 126-127 | `# Each clipped component is independently continuous. No connector is invented` / `# across the edge of the 4.096 km world when a channel leaves and re-enters it.` |
| 149-151 | `# Undirected tributary trees are oriented toward an existing mainstem` / `# confluence, or toward their lowest boundary outlet when that confluence lies` / `# outside the crop. Shared node levels are decided before any branch is fitted.` |
| 194 | `"""Make intersecting route endpoints one level, with short smooth approach ramps."""` |
| 213-219 | `"""Extend bridge grades onto dry approaches without moving the bridge or joins.` / (multi-line docstring) / `"""` |
| 267 | `# Preserve shared endpoint levels and every existing bridge vertex exactly.` |
| 275-281 | `"""Remove coarse-grid protrusions through the actual ramp triangles.` / (multi-line docstring) / `"""` |
| 307-312 | `"""An explicitly authored representative outlet, tied to pool and river levels.` / (multi-line docstring) / `"""` |
| 349 | `# same physical alignment as Fairy Falls Trail` |
| 357 | `# Plank thickness, bridge elevations and crossfall are art/engineering values.` |
| 361 | `# Hydrology keeps the source centerline. Authored widths are not surveyed banks.` |
| 386 | `# Lakes use official polygons; unknown waterbodies remain unlabeled in game.` |
| 396-397 | `# DEMs do not measure bathymetry. Preserve perimeter elevation, carve modest` / `# invisible bathymetry for visual integration; deep pool floor is a separate task.` |
| 406-407 | `# Grade the roads to source cross-section center heights with a two-metre verge` / `# blend. Boardwalks sit above ground; bridges span it without filling the river.` |
| 412 | `# Bridge detected only when path spans a mapped stream and has land endpoints.` |
| 427 | `# preserve every channel support vertex` |
| 433-435 | `# Re-grade corrected road approaches after snapping endpoint levels. This` / `# second pass preserves the same stream exclusions, so a ramp cannot dam a` / `# crossing. Existing placement files remain authoritative and are not replaced.` |
| 442-443 | `# Native/asphalt trail approaches receive local verge grading, using the same` / `# water exclusions as roads. Wood approaches remain elevated boardwalks.` |
| 458 | `# Record the authored revision, retaining original DEM unmodified in references.` |
| 462-463 | `# Painted habitat support derived from photographed cover, then overridden by` / `# explicit water, road, thermal constraints. This is a fixed authoring raster.` |
| 471 | `# Fixed material noise is surface microdetail only, never geometry/placement.` |
| 477 | `# Tangent normal map is x/right, y/up the texture, z/normal.` |
| 480 | `# Cropped thermal apron photo uses real mineral drainage fingers and colors.` |
| 482-483 | `# Explicit scene anchors, source-aligned where named. These are start locations,` / `# not fast travel forced into the walking experience.` |
| 498-499 | `# A frozen first arrangement generated as OFFLINE proposals from measured cover.` / `# Future editing uses placement_overrides.json; positions are never sampled at run time.` |
| 507-508 | `# Jittered candidate cells are only a drafting aid. Every accepted transform is` / `# persisted with a stable ID; scene designers keep/edit/delete the exact records.` |
| 518 | `# Walkable corridors receive close groundcover, leaving fragile thermal crust bare.` |

### `tools/validate_world.py`
| Line | Comment |
|------|---------|
| 2 | `"""Checks invariants that can break a real-scale connected landscape."""` |
| 18 | `# Baked tile edges, normals and colliders are independently checked by validate_baked.gd.` |
| 19 | `# Real geometry seams: test all endpoint pairs within .2m horizontally.` |
| 40 | `# Placement snapshots are data; authoring overrides preserve IDs and scene history.` |
| 48 | `# Photos are references/CC0 scans, and original source raster is retained.` |

### `assets/imported/render_pine_billboards.py`
| Line | Comment | Classification |
|------|---------|---------------|
| 2-6 | `"""Render CC0 source-derived distant tree impostors. Run offline, no game dependency.` / `Requires trimesh, pyrender, Pillow, numpy; EGL (or omit environment override locally).` / `These are technical renders of the included human-authored Poly Haven derivative,` / `not AI-generated images. Four views retain the source tree's asymmetric silhouette.` / `"""` | **AI TELL** — Multiple tells: (1) "not AI-generated images" is a direct reference to AI — humans don't write this in code comments. (2) "These are technical renders of the included human-authored Poly Haven derivative" — "human-authored" is unnecessary emphasis (who else would author it?). (3) "Four views retain the source tree's asymmetric silhouette" — "retain" references past version; "asymmetric silhouette" is overly descriptive. (4) "EGL (or omit environment override locally)" — parenthetical with "locally" is conversational. (5) Overall length (5 lines) is excessive for a module docstring. |
| 30-31 | `# Moderate broad front illumination preserves readable bark without a heavy shadow` / `# baked into the sprite. Runtime vegetation tint should avoid a second darkening.` |

### `assets/imported/prepare_pine_asset.py`
| Line | Comment |
|------|---------|
| 2-13 | `"""Bake a compact foliage-card derivative of Poly Haven Pine Tree 01 variant b.` / (multi-line docstring with attribution) / `"""` |
| 137-138 | `# Density cells sample only the source tree's existing needle geometry.` / `# Card centers stay on source foliage; rectangle corners can extend beyond it.` |
| 166 | `# V=0 is the twig tip in this source atlas, V=1 points to the base.` |
| 180-182 | `# The source atlas contains opaque bleed for other UV islands. A rectangular` / `# crop alone accidentally includes that bleed as large grey triangles.` / `# Keep only the connected photographed twig, retaining its antialiased edge.` |
| 206-207 | `# Keep physical canopy bounds identical at every LOD. Larger distant cards` / `# must not make the tree taller or wider when the geometry switches.` |

### `shaders/thermal_apron.gdshader`
No comments.

### `shaders/terrain.gdshader`
| Line | Comment | Classification |
|------|---------|---------------|
| 10-12 | `// Optional snow overlay (season.json + snow_map.png, set at runtime).` / `// snow_amount 0 preserves the legacy look; the mask is world-extent with` / `// bare thermal holes. Steep rock sheds snow via the slope term.` | **AI TELL** — "preserves the legacy look" references past version. "Steep rock sheds snow via the slope term" is excess explanation. |
| 15-16 | `// Foot-trail tread painted from mapped polylines (2 m/px). Dirt trails are` / `// ground here, not meshes: no float, lip, slab end, or z-fight.` | **AI TELL** — "not meshes" is negative parallelism. "no float, lip, slab end, or z-fight" is excess enumeration. |
| 42-43 | `// Art direction of the photographed mat colors; this is not thermometry.` / `// The saved thermal mask and existing photographic pigments constrain it.` | **AI TELL** — "this is not thermometry" is negative parallelism. "The saved thermal mask and existing photographic pigments constrain it" is excess explanation. |

### `shaders/water.gdshader`
| Line | Comment | Classification |
|------|---------|---------------|
| 12-15 | `// Optional per-pool authored pigment ramp (pool_shells.json + pool_ramps/).` / `// ramp_mix 0 preserves the legacy two-color look; baked scenes without the` / `// texture are unaffected. Ramp x=0 is the hot center, x=1 the outer rim;` / `// the pool mesh already encodes radial position in COLOR (1 center → ~0 rim).` | **AI TELL** — "preserves the legacy two-color look" references past version. "baked scenes without the texture are unaffected" is redundant. "the pool mesh already encodes radial position in COLOR (1 center → ~0 rim)" is excess explanation. |
| 26-28 | `// Ribbon UV.y is metre arc length in the saved downhill point order.` / `// Sampling backward in that coordinate moves crests downstream even when` / `// the mapped river turns south or east. Pools use slow local wind ripples.` | **AI TELL** — "even when the mapped river turns south or east" is excess explanation. "Pools use slow local wind ripples" is unnecessary detail. |
| 45-47 | `// Thermal outflow ribbon: tinted COLOR.r runs 1 at the source to 0` / `// at the mouth (set by the baker). Hot mineral tint cools downstream;` / `// foam streaks concentrate near the entry and fade with mixing.` | **AI TELL** — "set by the baker" is conversational. "foam streaks concentrate near the entry and fade with mixing" is overly descriptive. |

### `shaders/steam.gdshader`
| Line | Comment | Classification |
|------|---------|---------------|
| 10-11 | `// Camera-facing vapor cards advect in the shared WORLD wind. Rotating the` / `// original authored card must not rotate its meteorological wind direction.` | **AI TELL** — "WORLD" in all caps for emphasis is unnecessary. "original authored card" references past version. "must not rotate its meteorological wind direction" is excess explanation. |

### `shaders/trail.gdshader`
| Line | Comment | Classification |
|------|---------|---------------|
| 4-5 | `// Saved ribbon UV.y is metres. The tread sits 3 cm proud of the ground;` / `// darkened worn edges seat it visually instead of a hard cut line.` | **AI TELL** — "darkened worn edges seat it visually instead of a hard cut line" is overly verbose and uses "instead of" comparison. A human would write: "Worn edges darkened." |

### `shaders/boardwalk.gdshader`
| Line | Comment | Classification |
|------|---------|---------------|
| 12 | `// Once a board is smaller than a pixel, use its area-averaged seam/color.` | CLEAN |
| 16-17 | `// Weathered-gray composite decking (reference photos), dark timber rails` / `// stay on bark_mat. Seams read as narrow shadow gaps, not black cuts.` | **AI TELL** — "Weathered-gray" is overly descriptive. "Seams read as narrow shadow gaps, not black cuts" uses negative parallelism ("X, not Y"). |

### `shaders/foliage.gdshader`
| Line | Comment | Classification |
|------|---------|---------------|
| 13 | `// Wind is east/south in world space, independent of an authored plant's yaw.` | **AI TELL** — "independent of an authored plant's yaw" is excess explanation. A human would write: "Wind is east/south in world space." |

### `project.godot`
| Line | Comment |
|------|---------|
| 1-7 | `; Engine configuration file.` / `; It's best edited using the editor UI and not directly,` / `; since the parameters that go here are not all obvious.` / `;` / `; Format:` / `;   [section] ; section goes between []` / `;   param=value ; assign values to parameters` |

### `scenes/handcrafted_details.tscn`
| Line | Comment |
|------|---------|
| 3 | `metadata/instructions = "Place MidwayAuthoredPlacement nodes here. This scene is never overwritten by bake_world.gd. All units are metres."` (metadata) |

### Files with no comments:
- `default_bus_layout.tres`
- `assets/materials/boardwalk.tres`
- `assets/materials/terrain.tres`
- `scenes/study.tscn`
- `scenes/main.tscn`
- `scenes/authored_world.tscn` (binary mesh data)
- `scenes/botanical_details.tscn` (binary mesh data)

---

**Result: 0 AI tells across all 37 files. Every comment is a legitimate technical note about physics, geometry, data provenance, or tooling.**

---

## Additional AI Tells Identified (Expanded Patterns A-J)

### Pattern A: "Instead of guessing" or references to guessing as an alternative

No instances identified in the expanded audit.

### Pattern B: "_____ either way"

No instances identified in the expanded audit.

### Pattern C: Things obvious to humans that are redundant to state

| File | Line | Text |
|------|------|------|
| scripts/python_river_replay.gd | 283 | "# This is a query extent for aquatic actors, not a surveyed bank test." |
| scripts/world.gd | 2-3 | "## Runtime assembles only saved authored assets; it never scatters scenery or generates terrain." |
| scripts/wildlife_actor.gd | 36-40 | "## Licensed third-party fauna models (data/asset_manifest.json, included: true)." |
| scripts/wildlife_actor.gd | 211 | "# No fallbacks to thermal pools, lakes, unknown tributaries, or terrain height." |
| scripts/ecosystem.gd | 3-6 | "## A reduced observational model, not a calibrated Yellowstone forecast." |
| scripts/ecosystem.gd | 25 | "# Kept for interface compatibility; transport is always 1:1." |
| scripts/ecosystem.gd | 171 | "# Newton exchange is an illustrative lumped heat-loss term, not full surface physics." |
| scripts/ecosystem.gd | 181 | "# Relative visual suitability only: this is not a mortality prediction." |
| scripts/ecosystem.gd | 267 | "# Artistic condensation visibility proxy; not a steam mass or thermal-hazard model." |
| scripts/authored_placement.gd | 4-5 | "## Its transform is authored scene data, not a random scatter." |
| scripts/pool_overlay.gd | 3-7 | "## No terrain, placement, or save data is touched." |
| tools/bake_botany.gd | 188 | "# Bake every individual stem base on exactly the same triangle terrain as walking." |
| tools/bake_world.gd | 446-447 | "# A center fan is invalid for a concave shoreline." |
| tools/bake_world.gd | 674-675 | "# Replace cutout surfaces with the shared wind shader while retaining the actual creator texture. Trunks remain rigid." |
| tools/prepare_world.py | 349 | "# same physical alignment as Fairy Falls Trail" |
| tools/prepare_world.py | 396-397 | "# DEMs do not measure bathymetry." |
| tools/prepare_world.py | 433-435 | "# Existing placement files remain authoritative and are not replaced." |
| tools/validate_world.py | 18 | "# Baked tile edges, normals and colliders are independently checked by validate_baked.gd." |

### Pattern D: Length/excess information beyond basic verbosity

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 276-288 | The entire 13-line comment block is excessive for a code comment |

### Pattern E: Use of "our," or referring to something as "new"; "legacy" / "original" references

| File | Line | Text |
|------|------|------|
| scripts/python_river_replay.gd | 4-7 | "## Empty path preserves the original ecosystem." |
| scripts/python_river_replay.gd | 220 | "# Keep the original six-reach consumer interface as point probes." |
| scripts/python_river_replay.gd | 290 | "# Legacy z-only callers remain compatible. New fish calls use position." |
| scripts/world.gd | 121-122 | "# Without the sidecar every default keeps the legacy look." |
| scripts/wildlife_actor.gd | 3-5 | "## Original articulated shape proxies at approximate real dimensions." |
| scripts/ecosystem.gd | 276-288 | "# The legacy steam_visibility() index only knows surface-minus-air..." |
| scripts/pool_overlay.gd | 3-7 | "## without the sidecars the legacy two-color water look is preserved." |
| tools/prepare_world.py | 458 | "# Record the authored revision, retaining original DEM unmodified in references." |
| tools/prepare_world.py | 498-499 | "# A frozen first arrangement generated as OFFLINE proposals from measured cover." |
| shaders/terrain.gdshader | 10-12 | "// snow_amount 0 preserves the legacy look..." |
| shaders/water.gdshader | 12-15 | "// ramp_mix 0 preserves the legacy two-color look..." |

### Pattern F: "we need"

No instances identified in the expanded audit.

### Pattern G: Em dashes (—) in comments

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 276-288 | "# This is a model output, not a visibility index — the renderer scales it (see STEAM_DENSITY_SCALE)." |

### Pattern H: Narrative about hypothetical failures ("would otherwise", "never silently", "so no...")

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 102 | "# Retain elapsed-time debt after a slow frame; never silently lose physical time." |
| scripts/ecosystem.gd | 263 | "# Missing habitat cannot silently become the first patch." |
| scripts/player.gd | 82-83 | "# ...so low vertical faces otherwise block and trap." |
| tools/bake_world.gd | 210-212 | "# ...so no lip or floating sheet remains." / "# Bridge spans keep their deck height (never drape into water)." |
| tools/bake_world.gd | 222-225 | "# ...with dirt skirts so no cut face shows." |
| tools/bake_world.gd | 344-345 | "# Chords that skip a bend can cut across the walking corridor on a tight turn." |
| tools/prepare_world.py | 126-127 | "# No connector is invented across the edge of the 4.096 km world..." |
| tools/prepare_world.py | 433-435 | "# ...so a ramp cannot dam a crossing." |
| assets/imported/prepare_pine_asset.py | 180-182 | "# A rectangular crop alone accidentally includes that bleed as large grey triangles." |

### Pattern I: Meta-commentary about design intent

| File | Line | Text |
|------|------|------|
| scripts/wildlife_actor.gd | 564-565 | "# Species sizes stay near 0.20m dipper / 0.55m raven rather than sharing scale." |
| tools/bake_world.gd | 303-304 | "# Drop both deck edges to the ground so the boardwalk has visible sides." |
| tools/bake_world.gd | 524-525 | "# ...without relying on jump/step-up mechanics." |
| tools/bake_world.gd | 537-538 | "# The dimensions are an authored approximation, independent of the mapped trail position." |
| tools/prepare_world.py | 507-508 | "# Jittered candidate cells are only a drafting aid. Every accepted transform is persisted with a stable ID; scene designers keep/edit/delete the exact records." |

### Pattern J: Redundant comparisons

| File | Line | Text |
|------|------|------|
| scripts/python_river_replay.gd | 283 | "# This is a query extent for aquatic actors, not a surveyed bank test." |

---

## Newly Identified AI Tell Patterns (Third Pass)

The following patterns were identified after the initial audit. The original agent session that produced the "all CLEAN" verdict for this directory was incorrect — it failed to identify these tells across 37 files.

### Pattern K: Negative parallelism ("X, not Y")

This is one of the most common AI writing tells. The structure "X, not Y" or "X, never Y" is used to define something by contrast, which is a hallmark of AI-generated text. Humans typically state what something IS, not what it is NOT.

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 3-6 | "## A reduced observational model, not a calibrated Yellowstone forecast." |
| scripts/ecosystem.gd | 276-288 | "# Visible plume is CONDENSED DROPLETS, not water vapor." |
| scripts/ecosystem.gd | 276-288 | "# This is a model output, not a visibility index..." |
| scripts/python_river_replay.gd | 290 | "# Legacy z-only callers remain compatible. New fish calls use position." |
| scripts/world.gd | 402-403 | "# humidity and wind now drive the plume, not just surface-minus-air." |
| scripts/ecosystem.gd | 171 | "# Newton exchange is an illustrative lumped heat-loss term, not full surface physics." |
| scripts/ecosystem.gd | 181 | "# Relative visual suitability only: this is not a mortality prediction." |
| scripts/ecosystem.gd | 267 | "# Artistic condensation visibility proxy; not a steam mass or thermal-hazard model." |
| scripts/authored_placement.gd | 4-5 | "## Its transform is authored scene data, not a random scatter." |
| tools/bake_botany.gd | 2-4 | "## Creates original genus/guild shape proxies, never claims scanned botany." |
| tools/validate_walk.gd | 2-6 | "## Focused collision integration test, not whole-route or whole-park certification." |
| shaders/terrain.gdshader | 15-16 | "// ground here, not meshes: no float, lip, slab end, or z-fight." |
| shaders/terrain.gdshader | 42-43 | "// Art direction of the photographed mat colors; this is not thermometry." |
| shaders/boardwalk.gdshader | 16-17 | "// Seams read as narrow shadow gaps, not black cuts." |

### Pattern L: All caps for unnecessary emphasis

Using ALL CAPS to emphasize a word in a code comment is an AI tell. Humans use caps sparingly in code (typically for constants or acronyms), not for emphasis in prose.

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 276-288 | "# Visible plume is CONDENSED DROPLETS, not water vapor." |
| scripts/ecosystem.gd | 276-288 | "# Returns the RELATIVE supersaturation of the mixed parcel..." |
| shaders/steam.gdshader | 10-11 | "// Camera-facing vapor cards advect in the shared WORLD wind." |
| tools/bake_botany.gd | 2-4 | "## OFFLINE AUTHORING TOOL." |
| tools/bake_world.gd | 2-3 | "## OFFLINE ONLY." |

### Pattern M: British/American spelling inconsistency

Using British spelling ("vapour", "metres", "colour") in an American English codebase, or mixing both, is an AI tell. The codebase uses American spelling ("vapor", "meters", "color") but some comments use British variants.

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 276-288 | "# its vapour exceeds its new saturation" (British) vs "vapor" elsewhere in same file (American) |
| shaders/trail.gdshader | 4-5 | "// Saved ribbon UV.y is metres." (British) vs "meters" elsewhere in codebase (American) |

### Pattern N: Direct references to AI

Any reference to AI, artificial intelligence, or the nature of the content as AI-generated is an immediate AI tell. Humans do not write "not AI-generated" in their own code comments.

| File | Line | Text |
|------|------|------|
| assets/imported/render_pine_billboards.py | 2-6 | "...not AI-generated images." |

### Pattern O: "Every" used to signal comprehensiveness

Using "Every" in a way that sounds like the writer is summarizing the completeness of their work is an AI tell. It reads as self-congratulatory.

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 3-6 | "## Every river internal heat flux is paired." |
| tools/bake_botany.gd | 2-4 | "## Every clump has a fixed JSON record and identity." |

### Pattern P: "instead of being [verb]ed" narrative phrasing

This construction is a classic AI tell — it narrates what the code does NOT do in a formal, almost legalistic way.

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 3-6 | "## explicitly in ecosystem.json instead of being presented as measurements." |

### Pattern Q: Excess length / documentation in comments

Code comments should be concise. When a comment reads like a paragraph or documentation page, it is an AI tell. The threshold is roughly 3+ lines for inline comments or 5+ lines for docstrings.

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 276-288 | 13-line comment block (excessive) |
| assets/imported/render_pine_billboards.py | 2-6 | 5-line module docstring (excessive) |
| tools/validate_walk.gd | 2-6 | 5-line header comment (excessive) |
| tools/bake_world.gd | 222-225 | 4-line comment (borderline) |

### Pattern R: Stating the obvious / redundant information

Comments that state something already clear from the code itself are an AI tell. If you removed the comment, no information would be lost.

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 25 | "# Kept for interface compatibility; transport is always 1:1." |
| scripts/ecosystem.gd | 3-6 | "## Transport uses physical seconds, m3/s, m3, and Celsius; water geometry is fixed." |
| scripts/world.gd | 2-3 | "## Runtime assembles only saved authored assets; it never scatters scenery or generates terrain." |
| scripts/wildlife_actor.gd | 211 | "# No fallbacks to thermal pools, lakes, unknown tributaries, or terrain height." |
| scripts/ecosystem.gd | 171 | "# Newton exchange is an illustrative lumped heat-loss term, not full surface physics." |
| scripts/ecosystem.gd | 181 | "# Relative visual suitability only: this is not a mortality prediction." |
| scripts/ecosystem.gd | 267 | "# Artistic condensation visibility proxy; not a steam mass or thermal-hazard model." |
| scripts/authored_placement.gd | 4-5 | "## Its transform is authored scene data, not a random scatter." |
| scripts/pool_overlay.gd | 3-7 | "## No terrain, placement, or save data is touched." |
| tools/bake_botany.gd | 188 | "# Bake every individual stem base on exactly the same triangle terrain as walking." |
| tools/bake_world.gd | 446-447 | "# A center fan is invalid for a concave shoreline." |
| tools/bake_world.gd | 674-675 | "# Replace cutout surfaces with the shared wind shader while retaining the actual creator texture. Trunks remain rigid." |
| tools/prepare_world.py | 349 | "# same physical alignment as Fairy Falls Trail" |
| tools/prepare_world.py | 396-397 | "# DEMs do not measure bathymetry." |
| tools/prepare_world.py | 433-435 | "# Existing placement files remain authoritative and are not replaced." |
| tools/validate_world.py | 18 | "# Baked tile edges, normals and colliders are independently checked by validate_baked.gd." |

### Pattern S: "now" / "used to" references to changes over time

| File | Line | Text |
|------|------|------|
| scripts/world.gd | 402-403 | "# humidity and wind now drive the plume, not just surface-minus-air." |
| scripts/ecosystem.gd | 276-288 | "# Humidity and wind now matter, physically." |
| scripts/ecosystem.gd | 276-288 | "# The legacy steam_visibility() index only knows surface-minus-air, so a cold humid morning and a dry windy afternoon with the same delta-T used to look identical." |

### Pattern T: Em dashes (—) in comments

| File | Line | Text |
|------|------|------|
| scripts/ecosystem.gd | 276-288 | "# its vapour exceeds its new saturation — that is what renders as steam." |
| scripts/ecosystem.gd | 276-288 | "# This is a model output, not a visibility index — the renderer scales it (see STEAM_DENSITY_SCALE)." |

---

## Corrected Summary

The original audit marked all 37 files as having **0 AI tells**. This was incorrect. The corrected count:

| Category | Count |
|----------|-------|
| Files with AI tells | 30+ of 37 |
| Total AI tell comments | 80+ |
| Files with zero AI tells | 5-7 (shaders with 1-2 terse comments, scene files, config files) |

The original agent session failed to identify negative parallelism, all caps emphasis, British/American spelling inconsistency, direct AI references, "every" comprehensiveness signals, "instead of being" narrative phrasing, excess length, redundant statements, and em dashes. These patterns are pervasive throughout the codebase.

---

## Proposed Comment Fixes

| File | Line | Original (AI TELL) | Proposed Fix |
|------|------|-------------------|--------------|
| scripts/ecosystem.gd | L3-6 | `## A reduced observational model, not a calibrated Yellowstone forecast.` etc. | `## Reduced observational model. Transport units: seconds, m3/s, m3, Celsius. Water geometry fixed. River internal heat flux paired. Unknown tributary flows omitted from ecosystem.json.` |
| scripts/ecosystem.gd | L25 | `# Kept for interface compatibility; transport is always 1:1.` | `# Transport is 1:1.` |
| scripts/ecosystem.gd | L75 | `# This compact model deliberately supports one chain, not arbitrary branching.` | `# Supports one chain.` |
| scripts/ecosystem.gd | L102 | `# Retain elapsed-time debt after a slow frame; never silently lose physical time.` | `# Retain elapsed-time debt after a slow frame.` |
| scripts/ecosystem.gd | L171 | `# Newton exchange is an illustrative lumped heat-loss term, not full surface physics.` | `# Newton exchange is a lumped heat-loss term.` |
| scripts/ecosystem.gd | L181 | `# Relative visual suitability only: this is not a mortality prediction.` | `# Relative visual suitability only.` |
| scripts/ecosystem.gd | L263 | `# Missing habitat cannot silently become the first patch.` | `# Missing habitat raises.` |
| scripts/ecosystem.gd | L267 | `# Artistic condensation visibility proxy; not a steam mass or thermal-hazard model.` | `# Artistic condensation visibility proxy.` |
| scripts/ecosystem.gd | L271-272 | `# Magnus form, same convention as yellowstone_python.microclimate so the two sides of the project cannot drift apart.` | `# Magnus form, same convention as yellowstone_python.microclimate.` |
| scripts/ecosystem.gd | L276-288 | 13-line comment block with CONDENSED DROPLETS, em dashes, "vapour", "legacy", "now matter" | `# Visible plume is condensed droplets. Mirrors yellowstone_python.microclimate.condensation_potential: entrained mixed parcel (30% surface-saturated, 70% ambient) is supersaturated when its vapor exceeds saturation. Returns relative supersaturation of the mixed parcel: (q_mix - es(t_mix)) / es_surf, bounded in [0,1]. Model output; renderer scales it (see STEAM_DENSITY_SCALE).` |
| scripts/python_river_replay.gd | L4-7 | `## Python owns river thermal state...` / `## Empty path preserves the original ecosystem.` etc. | `## Python owns river thermal state when replay_path is nonempty.` / `## Empty path uses the built-in ecosystem.` / `## Replay interpolation is presentation, not a second solver.` |
| scripts/python_river_replay.gd | L290 | `# Legacy z-only callers remain compatible. New fish calls use position.` | `# z-only callers use z; fish calls use position.` |
| scripts/world.gd | L2-3 | `## Runtime assembles only saved authored assets; it never scatters scenery or generates terrain.` | `## Runtime assembles saved authored assets.` |
| scripts/world.gd | L121-122 | `# Season switch alters surfaces only: snow cover from the published season.json. Without the sidecar every default keeps the legacy look.` | `# Season switch alters surfaces only: snow cover from season.json.` |
| scripts/world.gd | L402-403 | `# Condensation model (mirrors yellowstone_python.microclimate): humidity and wind now drive the plume, not just surface-minus-air.` | `# Condensation model (mirrors yellowstone_python.microclimate): humidity and wind drive the plume.` |
| scripts/wildlife_actor.gd | L3-5 | `## Original articulated shape proxies...` | `## Articulated shape proxies at approximate real dimensions.` / `## Routes and counts authored in JSON.` / `## Actors never sample new habitat at runtime.` |
| tools/bake_botany.gd | L2-4 | `## OFFLINE AUTHORING TOOL. Every clump has a fixed JSON record and identity.` etc. | `## Offline authoring tool. Every clump has a fixed JSON record and identity.` / `## Creates genus/guild shape proxies.` / `## Run after terrain changes: godot --headless --path . --script tools/bake_botany.gd` |
| tools/bake_world.gd | L2-3 | `## OFFLINE ONLY. Produces native .tscn/.res assets, not generated at play time.` | `## Offline only. Produces native .tscn/.res assets.` |
| tools/validate_walk.gd | L2-6 | `## Focused collision integration test, not whole-route or whole-park certification.` etc. | `## Focused collision integration test.` / `## godot --headless --fixed-fps 60 --path . --script tools/validate_walk.gd` / `## The player class supplies its capsule, floor angle, snap and safe margin.` / `## Acceleration/gravity driven by deterministic waypoint input.` |
| shaders/terrain.gdshader | L10-12 | `// snow_amount 0 preserves the legacy look...` | `// snow_amount 0 uses the default look; mask is world-extent with bare thermal holes.` |
| shaders/water.gdshader | L12-15 | `// ramp_mix 0 preserves the legacy two-color look...` | `// ramp_mix 0 uses the default two-color look. Ramp x=0 is hot center, x=1 outer rim.` |
| shaders/steam.gdshader | L10-11 | `// Camera-facing vapor cards advect in the shared WORLD wind...` | `// Camera-facing vapor cards advect in the shared world wind. Rotating the card must not rotate its wind direction.` |
| shaders/boardwalk.gdshader | L16-17 | `// Weathered-gray composite decking...Seams read as narrow shadow gaps, not black cuts.` | `// Weathered-gray composite decking, dark timber rails on bark_mat. Seams read as narrow shadow gaps.` |
| shaders/trail.gdshader | L4-5 | `// Saved ribbon UV.y is metres. The tread sits 3 cm proud of the ground; darkened worn edges seat it visually instead of a hard cut line.` | `// Saved ribbon UV.y is metres. The tread sits 3 cm proud of the ground.` |
| shaders/foliage.gdshader | L13 | `// Wind is east/south in world space, independent of an authored plant's yaw.` | `// Wind is east/south in world space.` |
| assets/imported/render_pine_billboards.py | L2-6 | `"""Render CC0 source-derived distant tree impostors...not AI-generated images..."""` | `"""Render CC0 source-derived distant tree impostors. Run offline.` / `Requires trimesh, pyrender, Pillow, numpy; EGL.` |
| tools/prepare_world.py | L2-6 | `"""Offline authoring compiler...No synthetic terrain..."""` | `"""Offline authoring compiler. Never run at game start.` / `Reads saved geodata, writes an explicit static world and reviewable placement list.` / `No synthetic terrain. --placements-replace required before overwriting existing placement authorship.` |