extends SceneTree
## Check headless Midway stream heights/water cut/routes against core, master raster and world data.
const Frame = preload("res://scripts/park_runtime/world_frame.gd")
const Streamer = preload("res://scripts/park_runtime/terrain_streamer.gd")
const Job = preload("res://scripts/park_runtime/terrain_job.gd")
const FeatureSource = preload("res://scripts/park_runtime/feature_source.gd")
const VegetationPager = preload("res://scripts/park_runtime/vegetation_pager.gd")
const WildlifePager = preload("res://scripts/park_runtime/wildlife_pager.gd")
const PythonReplay = preload("res://scripts/python_river_replay.gd")
const ReleaseData = preload("res://scripts/release_data.gd")
const TileWater = preload("res://scripts/park_runtime/tile_water.gd")
const HeightField = preload("res://scripts/height_field.gd")
const CoreTerrain = preload("res://scripts/core_terrain.gd")
const WaterCut = preload("res://scripts/water_polygon_cut.gd")
const CATALOG := "res://data/park_composed/catalog.json"
const WORLD := "res://data/world.json"
const CANOPY_DIR := "res://data/lidar_canopy"
const BRIDGE_ROUTES: Array[String] = ["trail_3227_0", "trail_3226_0"]
const MAX_FRAMES := 1200
const SAMPLES := 400
var failures: int = 0
var checks: int = 0
var master
var legacy
var extent: Dictionary
var catalog: Dictionary
var features: Dictionary
var world: Dictionary
var base_dir: String
var pages: Dictionary = {}
var water_covered_tiles: Dictionary = {}
var jobs: Dictionary = {}
var canopy_header: Dictionary = {}
var canopy_cells := PackedByteArray()
var canopy_excluded := PackedByteArray()

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool, message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error(message)

func settle(stream: Node, observer: Camera3D, frame: RefCounted, target: Vector3) -> bool:
    observer.global_position = frame.local_position(target.x, target.y, target.z)
    stream.velocity = Vector3.ZERO
    for _tick: int in MAX_FRAMES:
        frame.maybe_rebase(observer)
        await physics_frame
        await process_frame
        if stream.is_collision_ready(target.x, target.z) and stream.can_enter(observer.global_position, 0.5):
            return true
    return false

func page(path: String) -> Dictionary:
    if not pages.has(path):
        pages[path] = JSON.parse_string(FileAccess.get_file_as_string(base_dir.path_join(path)))
    return pages[path]

func covers(d: Dictionary, x: float, z: float) -> bool:
    return x >= float(d.origin_x_m) and x <= float(d.origin_x_m) + float(d.size_m) and z >= float(d.origin_z_m) and z <= float(d.origin_z_m) + float(d.size_m)

func leaf_descriptor(x: float, z: float) -> Dictionary:
    var node: Dictionary = {}
    for root_tile: Dictionary in catalog.roots:
        if covers(root_tile, x, z):
            node = root_tile
            break
    while not node.is_empty() and int(node.lod) > 0:
        var next: Dictionary = {}
        for child: Dictionary in page(str(node.page)).children:
            if covers(child, x, z):
                next = child
                break
        node = next
    return node

func run_job(d: Dictionary, with_features: bool = true) -> Dictionary:
    var key: String = str(d.key) + (":f" if with_features else ":b")
    if not jobs.has(key):
        var job = Job.new()
        job.configure(d, base_dir, str(catalog.dataset_revision))
        if with_features:
            job.configure_features(features)
        job.run()
        jobs[key] = job.result
    return jobs[key]

func bary(values: PackedFloat32Array, columns: int, gx: float, gz: float) -> float:
    var ix: int = clampi(int(floor(gx)), 0, columns - 2)
    var iz: int = clampi(int(floor(gz)), 0, columns - 2)
    var fx: float = gx - ix
    var fz: float = gz - iz
    var a: float = values[iz * columns + ix]
    var b: float = values[iz * columns + ix + 1]
    var c: float = values[(iz + 1) * columns + ix]
    var d: float = values[(iz + 1) * columns + ix + 1]
    return a + fx * (b - a) + fz * (c - a) if fx + fz <= 1.0 else d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d)

func inside_core(x: float, z: float) -> bool:
    return x >= float(extent.x_min_m) and x <= float(extent.x_max_m) and z >= float(extent.z_min_m) and z <= float(extent.z_max_m)

## Core heights inside the core footprint, master heights elsewhere.
func reference_height(x: float, z: float) -> float:
    if inside_core(x, z):
        return bary(legacy._heights_full, int(extent.nx), x - float(extent.x_min_m), z - float(extent.z_min_m))
    return master.sample(x, z)

func tile_height(result: Dictionary, x: float, z: float) -> float:
    var d: Dictionary = result.page.tile
    var cells: int = int(d.mesh_cells)
    var spacing: float = float(d.size_m) / cells
    return bary(result.heights, cells + 1, (x - float(d.origin_x_m)) / spacing, (z - float(d.origin_z_m)) / spacing)

func source_entry(pack_id: String) -> Dictionary:
    for source: Dictionary in catalog.sources:
        if str(source.pack_id) == pack_id:
            return source
    return {}

func audit_provenance() -> void:
    var core_hashes: Dictionary = source_entry("core").get("core_sources", {})
    var layers: Dictionary = legacy.core_meta.get("layers", {})
    check(core_hashes.get("core_terrain.json", "") == FileAccess.get_sha256("res://data/core_terrain/core_terrain.json"), "pack was built from a different core_terrain.json")
    check(core_hashes.get("core_heightfield.f32", "") == str(layers.core_heightfield_m.sha256), "pack core heightfield differs from the legacy layer")
    check(core_hashes.get("core_microrelief.f32", "") == str(layers.core_microrelief_m.sha256), "pack core microrelief differs from the legacy layer")
    check(str(source_entry("midway").get("source_sha256", "")) == FileAccess.get_sha256("res://data/terrain.f32"), "pack master differs from terrain.f32")

func audit_boundary() -> void:
    var worst: float = 0.0
    var count: int = 0
    var x0: float = float(extent.x_min_m)
    var x1: float = float(extent.x_max_m)
    var z0: float = float(extent.z_min_m)
    var z1: float = float(extent.z_max_m)
    for step: int in range(0, 601, 8):
        for offset: float in [-2.0, -0.5, 0.0, 0.5, 2.0]:
            var points: Array[Vector2] = [Vector2(x0 + step, z0 + offset), Vector2(x0 + step, z1 + offset), Vector2(x0 + offset, z0 + step), Vector2(x1 + offset, z0 + step)]
            for point: Vector2 in points:
                var d: Dictionary = leaf_descriptor(point.x, point.y)
                if d.is_empty() or int(d.lod) != 0:
                    check(false, "no leaf tile at boundary point " + str(point))
                    continue
                var result: Dictionary = run_job(d)
                if result.has("error"):
                    check(false, "boundary tile failed: " + str(result.error))
                    continue
                worst = maxf(worst, absf(tile_height(result, point.x, point.y) - reference_height(point.x, point.y)))
                count += 1
    check(count > 1000, "boundary audit sampled too few points")
    check(worst < 0.001, "pack differs from the legacy core cut at the core boundary by %f m" % worst)
    print("BOUNDARY samples=", count, " tiles=", jobs.size(), " worst_error_m=", worst)

func polygon_area(ring: Array) -> float:
    var polygon := PackedVector2Array()
    for point: Array in ring:
        polygon.append(Vector2(float(point[0]), float(point[1])))
    return absf(WaterCut.signed_area(polygon))

func audit_water() -> void:
    var cut_pools: int = 0
    for pool: Dictionary in world.pools:
        if not bool(pool.get("thermal", false)):
            continue
        cut_pools += 1
        var outline := PackedVector2Array()
        for point: Array in pool.ring:
            outline.append(Vector2(float(point[0]), float(point[1])))
        var box: Rect2 = WaterCut.bounds(outline)
        var tiles: Dictionary = {}
        var x: float = box.position.x - 16.0
        while x <= box.end.x + 16.0:
            var z: float = box.position.y - 16.0
            while z <= box.end.y + 16.0:
                var d: Dictionary = leaf_descriptor(x, z)
                if not d.is_empty():
                    tiles[str(d.key)] = d
                z += 16.0
            x += 16.0
        var removed: float = 0.0
        var shoreline_triangles: int = 0
        var omitted: int = 0
        for d: Dictionary in tiles.values():
            var result: Dictionary = run_job(d)
            check(not result.has("error"), "pool tile failed: " + str(result.get("error", "")))
            if result.has("error"):
                continue
            check(run_job(d, false).heights == result.heights, "pool cut altered the collision height source")
            if result.pools.has(str(pool.id)):
                removed += float(result.water.removed_xz_area_m2)
                shoreline_triangles += int(result.water.shoreline_closure_triangles)
                omitted += int(result.skirts_omitted)
                audit_skirts(result, pool, d)
        var expected: float = polygon_area(pool.ring)
        check(absf(removed - expected) < 0.01 + expected * 0.00001, "%s removed %f m2 of terrain, polygon is %f m2" % [str(pool.id), removed, expected])
        check(shoreline_triangles > 0, "%s has no shoreline surface" % str(pool.id))
        print("POOL ", pool.id, " tiles=", tiles.size(), " removed_m2=", removed, " polygon_m2=", expected, " shoreline_tris=", shoreline_triangles, " skirts_omitted=", omitted)
    check(cut_pools == 4, "expected four thermal pools")
    check(water_covered_tiles.size() == 3, "expected three water-covered leaf tiles, found %d" % water_covered_tiles.size())
    print("WATER_COVERED ", water_covered_tiles.keys())

func audit_skirts(result: Dictionary, pool: Dictionary, d: Dictionary) -> void:
    if bool(result.get("water_covered", false)):
        check(result.arrays.is_empty() and int(result.water.retained_triangles) == 0, "water-covered tile %s carries terrain arrays" % str(d.key))
        check(int(result.skirts_omitted) == 4 * int(d.mesh_cells), "water-covered tile %s kept a skirt" % str(d.key))
        water_covered_tiles[str(d.key)] = true
        return
    var indices: PackedInt32Array = result.arrays[Mesh.ARRAY_INDEX]
    var vertices: PackedVector3Array = result.arrays[Mesh.ARRAY_VERTEX]
    var grid_indices: int = int(result.water.retained_triangles) * 3
    var ring := PackedVector2Array()
    for point: Array in pool.ring:
        ring.append(Vector2(float(point[0]) - float(d.origin_x_m), float(point[1]) - float(d.origin_z_m)))
    var quads: int = (indices.size() - grid_indices) / 6
    check(quads + int(result.skirts_omitted) == 4 * int(d.mesh_cells), "skirt quads plus omitted segments do not cover the tile perimeter")
    for start: int in range(grid_indices, indices.size(), 6):
        var middle: Vector3 = (vertices[indices[start]] + vertices[indices[start + 2]]) * 0.5
        check(not Geometry2D.is_point_in_polygon(Vector2(middle.x, middle.z), ring), "skirt hangs across open water in " + str(d.key))

func audit_cut_parity() -> void:
    var rim: Array = []
    for pool: Dictionary in world.pools:
        if str(pool.id) == "pool_1034_0":
            rim = pool.ring[0]
    var d: Dictionary = leaf_descriptor(float(rim[0]), float(rim[1]))
    var result: Dictionary = run_job(d)
    var found: Dictionary = FeatureSource.collect(features, "pools", float(d.origin_x_m), float(d.origin_z_m), float(d.origin_x_m) + float(d.size_m), float(d.origin_z_m) + float(d.size_m))
    var local: Array = TileWater.localize(found.features, float(d.origin_x_m), float(d.origin_z_m))
    var cells: int = int(d.mesh_cells)
    var n: int = cells + 1
    var spacing: float = float(d.size_m) / cells
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var indices := PackedInt32Array()
    for z: int in n:
        for x: int in n:
            vertices.append(Vector3(x * spacing, result.heights[z * n + x], z * spacing))
            normals.append(Vector3.UP)
            uvs.append(Vector2(float(x) / cells, float(z) / cells))
    for z: int in cells:
        for x: int in cells:
            var a: int = z * n + x
            indices.append_array(PackedInt32Array([a, a + 1, a + n, a + 1, a + n + 1, a + n]))
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_INDEX] = indices
    var mesh := ArrayMesh.new()
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
    var mesh_cut: Dictionary = WaterCut.cut(mesh, Transform3D.IDENTITY, local)
    var raw_cut: Dictionary = WaterCut.cut_arrays(arrays, Transform3D.IDENTITY, local)
    check(bool(mesh_cut.ok) and bool(raw_cut.ok), "water cut failed on the Grand Prismatic tile")
    check(int(raw_cut.get("split_boundary_triangles", 0)) > 0 and mesh_cut.mesh.get_surface_count() == 1, "the parity tile must straddle the pool rim")
    if not (bool(mesh_cut.ok) and bool(raw_cut.ok)) or mesh_cut.mesh.get_surface_count() != 1:
        return
    var mesh_arrays: Array = mesh_cut.mesh.surface_get_arrays(0)
    check(mesh_arrays[Mesh.ARRAY_INDEX] == raw_cut.arrays[Mesh.ARRAY_INDEX] and mesh_arrays[Mesh.ARRAY_VERTEX] == raw_cut.arrays[Mesh.ARRAY_VERTEX], "raw-array cut differs from the mesh cut")
    check(mesh_cut.shoreline_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == raw_cut.shoreline_arrays[Mesh.ARRAY_VERTEX], "raw-array shoreline differs from the mesh cut")
    check(int(result.water.removed_triangles) == int(raw_cut.removed_triangles) and int(result.water.split_boundary_triangles) == int(raw_cut.split_boundary_triangles), "worker cut report differs from the mesh cut")
    print("CUT_PARITY removed=", raw_cut.removed_triangles, " split=", raw_cut.split_boundary_triangles, " shoreline_triangles=", raw_cut.shoreline_closure_triangles)

func audit_dry_tile() -> void:
    var d: Dictionary = leaf_descriptor(500.0, 500.0)
    var result: Dictionary = run_job(d)
    check(result.pools.is_empty() and result.shoreline_arrays.is_empty() and int(result.skirts_omitted) == 0, "a tile away from water must keep its full skirt and no shoreline")
    var second = Job.new()
    second.configure(d, base_dir, str(catalog.dataset_revision))
    second.configure_features(features)
    second.run()
    check(second.result.arrays[Mesh.ARRAY_VERTEX] == result.arrays[Mesh.ARRAY_VERTEX], "tile preparation is not deterministic")

func route_by_id(id: String) -> Dictionary:
    for route: Dictionary in world.routes:
        if str(route.id) == id:
            return route
    return {}

func run() -> void:
    var scene := Node3D.new()
    root.add_child(scene)
    var frame = Frame.new()
    var observer := Camera3D.new()
    observer.far = 30000.0
    scene.add_child(observer)
    observer.make_current()
    frame.register_root(observer)
    var stream = Streamer.new()
    scene.add_child(stream)
    check(stream.configure(CATALOG, frame, observer), "Midway catalog rejected; build data/park_composed with terrain_pack --core-dir")
    if failures > 0:
        quit(1)
        return
    var vegetation = VegetationPager.new()
    vegetation.name = "VegetationPager"
    scene.add_child(vegetation)
    check(vegetation.configure(stream), "vegetation pager rejected the feature index")
    canopy_header = JSON.parse_string(FileAccess.get_file_as_string(CANOPY_DIR + "/unresolved_render_canopy.json"))
    canopy_cells = FileAccess.get_file_as_bytes(CANOPY_DIR + "/unresolved_cells.u8")
    canopy_excluded = FileAccess.get_file_as_bytes(CANOPY_DIR + "/unresolved_cells_excluded.u8")
    check(canopy_cells.size() == int(canopy_header.width) * int(canopy_header.height) and canopy_excluded.size() == canopy_cells.size(), "canopy masks are missing or truncated")
    base_dir = CATALOG.get_base_dir()
    catalog = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
    features = FeatureSource.load_index(base_dir, catalog.features)
    check(not features.has("error"), "feature index rejected")
    world = JSON.parse_string(FileAccess.get_file_as_string(WORLD))
    master = HeightField.new()
    legacy = CoreTerrain.new()
    check(legacy._load_metadata() and legacy._load_heights(), "legacy core loader failed")
    extent = legacy.extent_rect()
    check(int(extent.nx) == 601 and float(extent.cell_m) == 1.0, "unexpected legacy core grid")
    if failures > 0:
        quit(1)
        return
    audit_provenance()
    audit_boundary()
    audit_water()
    audit_cut_parity()
    audit_dry_tile()
    var stops: Array[Vector3] = [Vector3(-242.0, 70.0, 160.0), Vector3(70.0, 30.0, -261.0), Vector3(260.0, 40.0, 950.0), Vector3(-1500.0, 60.0, -1900.0),
        Vector3(-340.0, 40.0, 0.0), Vector3(0.0, 40.0, -380.0), Vector3(260.0, 40.0, 100.0), Vector3(-100.0, 40.0, 220.0), Vector3(-59.9, 40.0, -186.4)]
    var bridge_indices: Dictionary = {}
    for id: String in BRIDGE_ROUTES:
        var route: Dictionary = route_by_id(id)
        var span: Array = route.bridge_spans[0]
        var middle: int = (int(span[0]) + int(span[1])) / 2
        var point: Array = route.points[middle]
        bridge_indices[id] = middle
        stops.append(Vector3(float(point[0]), 40.0, float(point[2])))
    for stop: Vector3 in stops:
        var ready: bool = await settle(stream, observer, frame, stop)
        check(ready, "collision not ready at " + str(stop))
        if not ready:
            continue
        var worst: float = 0.0
        var rng := RandomNumberGenerator.new()
        rng.seed = 5171
        for _i: int in SAMPLES:
            var x: float = stop.x + rng.randf_range(-30.0, 30.0)
            var z: float = stop.z + rng.randf_range(-30.0, 30.0)
            var streamed: float = stream.height_at(x, z)
            if is_nan(streamed):
                continue
            worst = maxf(worst, absf(streamed - reference_height(x, z)))
        check(worst < 0.001, "leaf height differs from the core cut or master raster by %f m at %s" % [worst, str(stop)])
        print("STOP ", stop, " worst_error_m=", worst)
    await audit_streamed_features(stream, observer, frame, bridge_indices)
    await audit_streamed_water(stream, observer, frame)
    await audit_streamed_vegetation(stream, observer, frame)
    await audit_streamed_wildlife(stream, observer, frame)
    check(int(stream.stats.get("failures", 0)) == 0, "tile jobs failed")
    check(float(stream.stats.get("resident_estimate_mib", 0.0)) <= stream.resident_limit_mib, "resident estimate exceeds budget")
    print("PARK_MIDWAY_STREAM checks=", checks, " failures=", failures, " resident=", stream.stats.get("resident_tiles"), " mib=", stream.stats.get("resident_estimate_mib"), " commit_ms_max=", stream.stats.get("commit_ms_max"))
    legacy.free()
    scene.queue_free()
    await process_frame
    quit(1 if failures else 0)

func audit_streamed_features(stream: Node, observer: Camera3D, frame: RefCounted, bridge_indices: Dictionary) -> void:
    for id: String in BRIDGE_ROUTES:
        var route: Dictionary = route_by_id(id)
        var middle: int = int(bridge_indices[id])
        var point: Array = route.points[middle]
        var ready: bool = await settle(stream, observer, frame, Vector3(float(point[0]), 40.0, float(point[2])))
        check(ready, "bridge tile not ready for " + id)
        var chunk: Dictionary = {}
        for candidate: Dictionary in stream.route_chunks_at(float(point[0]), float(point[2])):
            if str(candidate.id) == id and int(candidate.first_point) <= middle and middle <= int(candidate.last_point):
                chunk = candidate
        check(not chunk.is_empty(), "route chunk missing at the " + id + " bridge")
        if chunk.is_empty():
            continue
        check(chunk.points[middle - int(chunk.first_point)] == point, "route chunk point differs from world.json")
        check(not chunk.bridge_spans.is_empty(), "route chunk lost its bridge span at " + id)
        var min_clearance: float = INF
        var worst_error: float = 0.0
        var sampled: int = 0
        for span: Array in route.bridge_spans:
            for index: int in range(int(span[0]), int(span[1]) + 1):
                var p: Array = route.points[index]
                var streamed: float = stream.height_at(float(p[0]), float(p[2]))
                if is_nan(streamed):
                    continue
                sampled += 1
                worst_error = maxf(worst_error, absf(streamed - reference_height(float(p[0]), float(p[2]))))
                min_clearance = minf(min_clearance, float(p[1]) - streamed)
        check(sampled > 0, "no bridge samples resident for " + id)
        check(worst_error < 0.001, "%s bridge terrain differs from the legacy core cut by %f m" % [id, worst_error])
        print("BRIDGE ", id, " samples=", sampled, " worst_error_m=", worst_error, " min_deck_clearance_m=", min_clearance)
        var ribbon_found: bool = false
        var collision_found: bool = false
        var rail_count: int = 0
        for key: String in stream.resident:
            var tile: Node = stream.resident[key]
            if int(tile.descriptor.lod) != 0:
                continue
            for child: Node in tile.get_children():
                var child_name: String = str(child.name)
                if child_name.begins_with("Route_" + id + "_"):
                    ribbon_found = true
                    if child.get_node_or_null("RouteCollision") is StaticBody3D:
                        collision_found = true
                if child_name.begins_with("Route_BridgeRailSwept"):
                    rail_count += 1
        check(ribbon_found, id + " route mesh missing on resident leaf tiles")
        check(collision_found, id + " route mesh carries no collision")
        check(rail_count > 0, id + " swept bridge rails missing in streamed mode")
        print("ROUTE_MESH ", id, " rails=", rail_count, " collision=", collision_found)
    var pool_key: String = ""
    for key: String in stream.resident:
        var d: Dictionary = stream.resident[key].descriptor
        if int(d.lod) == 0 and covers(d, -59.9, -186.4):
            pool_key = key
    check(pool_key != "", "Turquoise Pool tile is not resident")
    if pool_key != "":
        var group: Dictionary = stream.tile_group(pool_key)
        check(bool(group.shoreline) and group.pools.has("pool_1028_0"), "pool tile lost its shoreline group")
        var shoreline_node: Node = stream.resident[pool_key].get_node_or_null("Shoreline")
        check(shoreline_node is MeshInstance3D and (shoreline_node as MeshInstance3D).mesh.get_surface_count() == 1, "shoreline surface was not committed with the tile")
        var pool_node: MeshInstance3D = null
        for node: Node in stream.tile_water_nodes(pool_key):
            if str(node.name) == "Water_pool_1028_0":
                pool_node = node as MeshInstance3D
        check(pool_node != null, "Turquoise Pool water surface missing in streamed mode")
        if pool_node != null:
            check(pool_node.is_in_group("thermal_surfaces"), "pool surface lost its thermal_surfaces group")

## Active display cells of a tile window under the batch-3 exclusion sidecar.
func expected_active_cells(d: Dictionary) -> int:
    var cell: float = float(canopy_header.cell_size_m)
    var width: int = int(canopy_header.width)
    var height: int = int(canopy_header.height)
    var gx0: float = float(canopy_header.first_cell_x_m) - cell * 0.5
    var gz0: float = float(canopy_header.first_cell_z_m) - cell * 0.5
    var c0: int = clampi(int(floor((float(d.origin_x_m) - gx0) / cell)), 0, width - 1)
    var c1: int = clampi(int(floor((float(d.origin_x_m) + float(d.size_m) - gx0) / cell)), 0, width - 1)
    var r0: int = clampi(int(floor((float(d.origin_z_m) - gz0) / cell)), 0, height - 1)
    var r1: int = clampi(int(floor((float(d.origin_z_m) + float(d.size_m) - gz0) / cell)), 0, height - 1)
    var count: int = 0
    for row: int in range(r0, r1 + 1):
        for column: int in range(c0, c1 + 1):
            var index: int = row * width + column
            if canopy_cells[index] == 1 and canopy_excluded[index] != 0:
                count += 1
    return count

func owned_records(layer: String, d: Dictionary, kind: String = "") -> int:
    var x0: float = float(d.origin_x_m)
    var z0: float = float(d.origin_z_m)
    var x1: float = x0 + float(d.size_m)
    var z1: float = z0 + float(d.size_m)
    var collected: Dictionary = FeatureSource.collect(features, layer, x0, z0, x1, z1)
    check(not collected.has("error"), layer + " page read failed in the vegetation audit")
    var count: int = 0
    for record: Dictionary in collected.features:
        var p: Array = record.position
        if p[0] >= x0 and p[0] < x1 and p[2] >= z0 and p[2] < z1 and (kind.is_empty() or str(record.kind) == kind):
            count += 1
    return count

## Resident leaf tiles carry their paged trees, canopy cells and floor records.
func audit_streamed_vegetation(stream: Node, observer: Camera3D, frame: RefCounted) -> void:
    var stop := Vector3(-340.0, 40.0, 0.0)
    var ready: bool = await settle(stream, observer, frame, stop)
    check(ready, "vegetation audit stop did not settle")
    if not ready:
        return
    var pager: Node = stream.get_parent().get_node_or_null("VegetationPager")
    var deadline: int = Time.get_ticks_msec() + 120000
    while pager != null and not pager.is_settled() and Time.get_ticks_msec() < deadline:
        await process_frame
    check(pager != null and pager.is_settled() and pager.preparation_error().is_empty(), "vegetation asset preparation did not complete")
    for _tick: int in MAX_FRAMES:
        if pager == null or pager.pending_count() == 0:
            break
        await process_frame
    check(pager != null and pager.pending_count() == 0, "vegetation pager queue did not drain")
    var active: int = 0
    for index: int in canopy_cells.size():
        if canopy_cells[index] == 1 and canopy_excluded[index] != 0:
            active += 1
    check(active == 158499, "canopy exclusion receipt changed: %d active cells" % active)
    var exclusion_sha: String = FileAccess.get_sha256(CANOPY_DIR + "/unresolved_cells_excluded.u8")
    var tiles_checked: int = 0
    for key: String in stream.resident:
        var tile: Node = stream.resident[key]
        var d: Dictionary = tile.descriptor
        if int(d.lod) != 0:
            continue
        var x0: float = float(d.origin_x_m)
        var z0: float = float(d.origin_z_m)
        var size: float = float(d.size_m)
        if x0 >= 640.0 or z0 >= 640.0 or x0 + size <= -640.0 or z0 + size <= -640.0:
            continue
        tiles_checked += 1
        var pines: int = owned_records("vegetation", d, "pine")
        var placed: int = owned_records("vegetation", d)
        var vegetation := tile.get_node_or_null("StreamedVegetation")
        check(vegetation != null or placed == 0, "resident tile lost its vegetation batches: " + key)
        if vegetation != null:
            check(int(vegetation.get_meta("records", -1)) == placed, "tile %s vegetation records differ from the pages" % key)
            check(int(vegetation.get_meta("tree_records", -1)) == pines, "tile %s pine records differ from the pages" % key)
            var pine_instances: int = 0
            for child: Node in vegetation.get_children():
                if child is MultiMeshInstance3D and child.has_meta("tree_archetype"):
                    pine_instances += child.multimesh.instance_count
            check(pine_instances == pines * 10, "tile %s renders %d pine instances for %d paged pines" % [key, pine_instances, pines])
        var expected: int = expected_active_cells(d)
        var canopy := tile.get_node_or_null("AuthoredCanopySurface")
        check(canopy != null, "resident tile lost its canopy window: " + key)
        if canopy != null:
            check(int(canopy.get_meta("active_cells", -1)) == expected, "tile %s canopy active cells differ from the excluded mask" % key)
            check(int(canopy.get_meta("cluster_display_count", -1)) == expected, "tile %s canopy clusters differ from active cells" % key)
            check(str(canopy.get_meta("exclusion_sha256", "")) == exclusion_sha, "tile %s canopy exclusion sidecar differs" % key)
        var floor_owned: int = owned_records("forest_floor", d)
        var floor_group := tile.get_node_or_null("AuthoredForestFloor")
        check(floor_group != null or floor_owned == 0, "resident tile lost its forest floor: " + key)
        if floor_group != null:
            check(int(floor_group.get_meta("records", -1)) == floor_owned, "tile %s forest-floor records differ from the pages" % key)
    check(tiles_checked >= 4, "vegetation audit found too few resident leaf tiles in the canopy footprint")
    var pager_stats: Dictionary = vegetation_stats(stream)
    print("VEGETATION_AUDIT tiles=", tiles_checked, " active_canopy_cells=", active, " pager=", pager_stats)

func vegetation_stats(stream: Node) -> Dictionary:
    var pager: Node = stream.get_parent().get_node_or_null("VegetationPager")
    return pager.stats() if pager != null else {}

## Streamed water surfaces follow the baked material contract for pools and rivers.
func audit_streamed_water(stream: Node, observer: Camera3D, frame: RefCounted) -> void:
    var prismatic: Dictionary = {}
    var firehole: Dictionary = {}
    for pool: Dictionary in world.pools:
        if str(pool.id) == "pool_1034_0":
            prismatic = pool
    for river: Dictionary in world.rivers:
        if str(river.get("name", "")) == "FIREHOLE RIVER" and river.points.size() > 500:
            firehole = river
    check(not prismatic.is_empty() and not firehole.is_empty(), "world.json lost the audit pool or river")
    if prismatic.is_empty() or firehole.is_empty():
        return
    var center: Array = prismatic.center
    var ready: bool = await settle(stream, observer, frame, Vector3(float(center[0]), 40.0, float(center[2])))
    check(ready, "Grand Prismatic tile not resident for the water audit")
    var pool_node: MeshInstance3D = null
    for key: String in stream.resident:
        for node: Node in stream.tile_water_nodes(key):
            if str(node.name) == "Water_pool_1034_0":
                pool_node = node as MeshInstance3D
    check(pool_node != null, "Grand Prismatic water surface missing in streamed mode")
    if pool_node != null:
        var pool_mat := pool_node.mesh.surface_get_material(0) as ShaderMaterial
        check(pool_mat != null and pool_mat.shader != null and pool_mat.shader.resource_path == "res://shaders/water.gdshader", "pool surface shader is not water.gdshader")
        if pool_mat != null:
            check(is_equal_approx(float(pool_mat.get_shader_parameter("pool")), 1.0), "pool surface lost the pool uniform")
            check(is_equal_approx(float(pool_mat.get_shader_parameter("temperature_c")), float(prismatic.temperature_c)), "pool surface temperature differs from world.json")
            check(is_equal_approx(float(pool_mat.get_shader_parameter("ramp_mix")), 1.0) and pool_mat.get_shader_parameter("band_ramp") is Texture2D, "pool surface lost its pigment ramp")
        check(pool_node.is_in_group("thermal_surfaces") and str(pool_node.get_meta("feature_name", "")) == str(prismatic.name), "pool surface lost its thermal group or feature name")
    var mid: Array = firehole.points[int(firehole.points.size() / 2)]
    ready = await settle(stream, observer, frame, Vector3(float(mid[0]), 40.0, float(mid[2])))
    check(ready, "Firehole reach tile not resident for the water audit")
    var river_node: MeshInstance3D = null
    var expected_name: String = "Water_" + str(firehole.id)
    for key: String in stream.resident:
        var d: Dictionary = stream.resident[key].descriptor
        if int(d.lod) != 0 or not covers(d, float(mid[0]), float(mid[2])):
            continue
        for node: Node in stream.tile_water_nodes(key):
            if str(node.name) == expected_name:
                river_node = node as MeshInstance3D
    check(river_node != null, "Firehole water ribbon missing at the mid-reach tile")
    if river_node != null:
        var river_mat := river_node.mesh.surface_get_material(0) as ShaderMaterial
        check(river_mat != null and river_mat.shader != null and river_mat.shader.resource_path == "res://shaders/river_water.gdshader", "river ribbon shader is not river_water.gdshader")
        if river_mat != null:
            check(is_equal_approx(float(river_mat.get_shader_parameter("core_width_m")), float(firehole.width)), "river ribbon width differs from world.json")
            check(is_equal_approx(float(river_mat.get_shader_parameter("flow_speed")), float(firehole.flow_mps)), "river ribbon flow differs from world.json")
        check(river_node.is_in_group("river_surfaces"), "river ribbon lost its river_surfaces group")
        check(str(river_node.get_meta("river_name", "")) == "FIREHOLE RIVER" and river_node.has_meta("sample_z"), "river ribbon lost its reach metadata")
    print("WATER_AUDIT pool=", pool_node != null, " river=", river_node != null)

## Wildlife actors spawn on resident habitat tiles; a revisit restores persistent state.
func audit_streamed_wildlife(stream: Node, observer: Camera3D, frame: RefCounted) -> void:
    var host: Node = stream.get_parent()
    # Mirror the world boot: activate the release so the replay and world hashes agree.
    if ReleaseData.active.is_empty() and FileAccess.file_exists("res://data/release.json"):
        var generation: Dictionary = ReleaseData.prepare("res://data/release.json")
        check(not generation.is_empty(), "release pointer failed integrity checks")
        if generation.is_empty():
            return
        ReleaseData.activate(generation)
    var ecosystem = PythonReplay.new()
    ecosystem.name = "WildlifeAuditEcosystem"
    ecosystem.replay_path = "res://data/river_replay.json"
    host.add_child(ecosystem)
    check(ecosystem.configuration_valid, "wildlife audit ecosystem rejected its configuration")
    var pager = WildlifePager.new()
    pager.name = "WildlifePager"
    host.add_child(pager)
    check(pager.configure(stream, frame, master, ecosystem, host), "wildlife pager rejected the roster")
    if not ecosystem.configuration_valid:
        return
    check(pager.present_ids().is_empty(), "actors appeared before any spawn pass")
    var roster: Array = ecosystem.params.get("wildlife", [])
    var bison: Dictionary = {}
    var trout: Dictionary = {}
    for record: Dictionary in roster:
        if str(record.get("id", "")) == "bison_01":
            bison = record
        if str(record.get("id", "")) == "trout_01":
            trout = record
    check(not bison.is_empty() and not trout.is_empty(), "wildlife audit records missing from the roster")
    if bison.is_empty() or trout.is_empty():
        return
    var bison_point: Array = bison.path_xz[0]
    var bison_stop := Vector3(float(bison_point[0]), 40.0, float(bison_point[1]))
    var ready: bool = await settle(stream, observer, frame, bison_stop)
    check(ready, "bison habitat stop did not settle")
    check(pager.present_ids().has("bison_01"), "bison_01 did not spawn on its resident habitat tile")
    var river_points: Array = []
    for river: Dictionary in ecosystem.world_data.get("rivers", []):
        if str(river.get("id", "")) == str(trout.get("river_id", "")):
            river_points = river.points
    check(not river_points.is_empty(), "trout river points missing from world.json")
    if river_points.is_empty():
        return
    var trout_point: Array = river_points[int(trout.get("start_point_index", 0))]
    var trout_stop := Vector3(float(trout_point[0]), 40.0, float(trout_point[2]))
    ready = await settle(stream, observer, frame, trout_stop)
    check(ready, "trout habitat stop did not settle")
    for id: String in ["trout_01", "trout_02", "trout_03", "trout_04"]:
        check(pager.present_ids().has(id), id + " did not spawn on its resident habitat tile")
    for _tick: int in 90:
        await physics_frame
    var actor: Node3D = pager.present_actor("trout_01")
    check(actor != null, "trout_01 was lost while its tile stayed resident")
    if actor == null:
        return
    check(is_finite(actor.chainage_m), "resident trout did not establish chainage")
    check(str(actor.get_meta("persistence_class", "")) == "tracked", "trout_01 lost its tracked persistence class")
    # Rebase with the actor resident: absolute state holds, the display position follows.
    var absolute_before: Vector3 = actor.site_position()
    var far := Vector3(-1500.0, 60.0, -1900.0)
    observer.global_position = frame.local_position(far.x, far.y, far.z)
    check(frame.maybe_rebase(observer), "no rebase triggered with actors resident")
    check(actor.site_position().is_equal_approx(absolute_before), "rebase moved the absolute actor position")
    var expected_local: Vector3 = frame.local_position(absolute_before.x, absolute_before.y, absolute_before.z)
    check(actor.position.distance_to(expected_local) < 0.001, "actor display position did not follow the rebase")
    # Retire the habitat tile; the store survives and the ecosystem keeps advancing.
    ready = await settle(stream, observer, frame, far)
    check(ready, "far stop did not settle")
    var suspended := false
    for _tick: int in 1800:
        await physics_frame
        if not pager.present_ids().has("trout_01"):
            suspended = true
            break
    check(suspended, "trout_01 did not suspend after its habitat tile retired")
    var stored: Dictionary = pager.stored_state("trout_01")
    check(stored.has("world_position") and stored.has("chainage_m"), "suspension lost the persistent store")
    check(host.get_node_or_null("trout_01") == null, "suspended actor node remains in the tree")
    if stored.is_empty():
        return
    var elapsed_hidden: float = ecosystem.elapsed
    for _tick: int in 60:
        await physics_frame
    check(ecosystem.elapsed > elapsed_hidden, "ecosystem state did not advance while the trout was hidden")
    # Revisit under a paused clock: the restored actor matches the store exactly.
    ecosystem.paused = true
    ready = await settle(stream, observer, frame, trout_stop)
    check(ready, "trout habitat stop did not settle on revisit")
    check(pager.present_ids().has("trout_01"), "trout_01 did not respawn on revisit")
    check(int(pager.stats().restored) >= 1, "revisit did not restore from the persistent store")
    var duplicates: int = 0
    var revived: Node3D = null
    for child: Node in host.get_children():
        if str(child.name) == "trout_01":
            duplicates += 1
            revived = child as Node3D
    check(duplicates == 1, "revisit duplicated trout_01")
    if revived != null:
        check(is_equal_approx(revived.chainage_m, float(stored.chainage_m)), "revisit reset the trout chainage")
        var stored_target: float = float(stored.target_s_m)
        var target_held: bool = (is_nan(stored_target) and is_nan(revived.target_s_m)) or is_equal_approx(revived.target_s_m, stored_target)
        check(target_held, "revisit reset the trout target")
        check(revived.site_position().distance_to(stored.world_position) < 0.001, "revisit moved the stored trout position")
        check(str(revived.state) == str(stored.state), "revisit reset the trout state")
    ecosystem.paused = false
    for _tick: int in 90:
        await physics_frame
    revived = pager.present_actor("trout_01")
    check(revived != null and is_finite(revived.chainage_m), "restored trout lost chainage after resume")
    var totals: Dictionary = pager.stats()
    check(int(totals.spawned) == int(totals.suspended) + pager.present_ids().size(), "spawn and suspend accounting diverged")
    print("WILDLIFE_AUDIT roster=", roster.size(), " spawned=", totals.spawned, " suspended=", totals.suspended, " restored=", totals.restored, " present=", pager.present_ids().size())
