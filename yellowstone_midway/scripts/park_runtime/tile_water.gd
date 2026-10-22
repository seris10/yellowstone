extends RefCounted
## Pool cut and shoreline for one terrain tile on raw arrays; runs in a worker, creates no resources.
const WaterCut = preload("res://scripts/water_polygon_cut.gd")

## Tile-local pool dictionaries keep ring coordinates small, so float32 polygon tolerances hold.
static func localize(pools: Array, origin_x_m: float, origin_z_m: float) -> Array:
    var local: Array = []
    for pool: Dictionary in pools:
        var ring: Array = []
        for point: Array in pool.ring:
            ring.append([float(point[0]) - origin_x_m, float(point[1]) - origin_z_m])
        local.append({"thermal": true, "ring": ring, "center": [0.0, float(pool.water_y_m), 0.0], "id": pool.id})
    return local

## Cuts the grid triangles of one tile; the identity transform keeps vertices tile-local.
static func cut(arrays: Array, local_pools: Array) -> Dictionary:
    return WaterCut.cut_arrays(arrays, Transform3D.IDENTITY, local_pools)

## True when a skirt edge between two tile-local vertices lies over open water.
static func edge_over_water(regions: Array, a: Vector3, b: Vector3) -> bool:
    for region: Dictionary in regions:
        for t: float in [0.0, 0.5, 1.0]:
            var point := Vector2(lerpf(a.x, b.x, t), lerpf(a.z, b.z, t))
            if region.bounds.has_point(point) and Geometry2D.is_point_in_polygon(point, region.polygon):
                return true
    return false

static func regions(local_pools: Array) -> Array:
    var prepared: Dictionary = WaterCut.prepare_regions(local_pools)
    return prepared.regions if prepared.ok else []

const WATER_CAP_SEGMENTS := 20

## Fan arrays for one thermal pool in tile-local coordinates, matching the bake layout.
static func _thermal_fan(pool: Dictionary, origin_x_m: float, origin_z_m: float) -> Array:
    var water_y := float(pool.water_y_m)
    var cx: float = float(pool.get("center_x_m", 0.0)) - origin_x_m
    var cz: float = float(pool.get("center_z_m", 0.0)) - origin_z_m
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var colors := PackedColorArray()
    var indices := PackedInt32Array()
    vertices.append(Vector3(cx, water_y, cz))
    normals.append(Vector3.UP)
    uvs.append(Vector2(0.5, 0.5))
    colors.append(Color(1, 1, 1))
    var n: int = pool.ring.size()
    for k: int in 4:
        var fraction := float(k + 1) / 4.0
        for point: Array in pool.ring:
            var rim := Vector3(float(point[0]) - origin_x_m, water_y, float(point[1]) - origin_z_m)
            var v: Vector3 = Vector3(cx, water_y, cz).lerp(rim, fraction)
            vertices.append(v)
            normals.append(Vector3.UP)
            uvs.append(Vector2(v.x - cx, v.z - cz) / 100.0 + Vector2(0.5, 0.5))
            colors.append(Color(1.0 - fraction, 1, 1))
    for i: int in n:
        indices.append_array(PackedInt32Array([0, 1 + (i + 1) % n, 1 + i]))
    for k: int in 3:
        for i: int in n:
            var a := 1 + k * n + i
            var b := 1 + k * n + (i + 1) % n
            var c: int = a + n
            var d: int = b + n
            indices.append_array(PackedInt32Array([a, b, c, b, d, c]))
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_COLOR] = colors
    arrays[Mesh.ARRAY_INDEX] = indices
    return arrays

## Keeps only the triangle area inside the tile rect; barycentric attributes follow the cut edges.
static func _clip_to_rect(arrays: Array, size_m: float) -> Array:
    var rect := PackedVector2Array([Vector2.ZERO, Vector2(size_m, 0.0), Vector2(size_m, size_m), Vector2(0.0, size_m)])
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var builder := WaterCut.MeshBuilder.new(arrays)
    builder.clear_output()
    var original: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
    for start: int in range(0, original.size(), 3):
        var corners := PackedInt32Array([original[start], original[start + 1], original[start + 2]])
        var triangle := PackedVector2Array()
        for corner: int in corners:
            var v: Vector3 = vertices[corner]
            triangle.append(Vector2(v.x, v.z))
        for piece: PackedVector2Array in Geometry2D.clip_polygons(triangle, rect):
            if piece.size() < 3 or absf(WaterCut.signed_area(piece)) <= WaterCut.AREA_EPSILON:
                continue
            var mapped := PackedInt32Array()
            for point: Vector2 in piece:
                mapped.append(builder.append_vertex(point, triangle, corners))
            for index: int in range(1, piece.size() - 1):
                builder.indices.append_array(PackedInt32Array([mapped[0], mapped[index], mapped[index + 1]]))
    return [] if builder.indices.is_empty() else builder.output()

## Flat ear-clipped surface for one non-thermal pool, matching the bake layout.
static func _flat_pool(pool: Dictionary, origin_x_m: float, origin_z_m: float) -> Array:
    var outline := PackedVector2Array()
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var colors := PackedColorArray()
    var water_y := float(pool.water_y_m)
    for point: Array in pool.ring:
        outline.append(Vector2(float(point[0]) - origin_x_m, float(point[1]) - origin_z_m))
    for point: Vector2 in outline:
        vertices.append(Vector3(point.x, water_y, point.y))
        normals.append(Vector3.UP)
        uvs.append(Vector2(point.x + origin_x_m, point.y + origin_z_m) / 100.0)
        colors.append(Color(0.7, 1, 1))
    var indices: PackedInt32Array = Geometry2D.triangulate_polygon(outline)
    if indices.is_empty():
        return []
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_COLOR] = colors
    arrays[Mesh.ARRAY_INDEX] = indices
    return arrays

## Water surfaces for every pool meeting the tile rect, clipped to the tile footprint.
static func pool_surfaces(pools: Array, origin_x_m: float, origin_z_m: float, size_m: float) -> Array:
    var surfaces: Array = []
    for pool: Dictionary in pools:
        var b: Array = pool.bounds_m
        if b[0] > origin_x_m + size_m or b[2] < origin_x_m or b[1] > origin_z_m + size_m or b[3] < origin_z_m:
            continue
        var arrays: Array
        if bool(pool.get("thermal", false)):
            arrays = _clip_to_rect(_thermal_fan(pool, origin_x_m, origin_z_m), size_m)
        else:
            arrays = _clip_to_rect(_flat_pool(pool, origin_x_m, origin_z_m), size_m)
        if arrays.is_empty():
            continue
        surfaces.append({"id": str(pool.id), "name": str(pool.get("name", "")),
            "thermal": bool(pool.get("thermal", false)),
            "temperature_c": float(pool.get("temperature_c", 0.0)), "arrays": arrays})
    return surfaces

## Ribbon arrays for one river from merged station chunks; the midpoint tile owns each quad.
static func river_surface(river_id: String, stations: Dictionary, count: int, meta: Dictionary,
        origin_x_m: float, origin_z_m: float, size_m: float) -> Dictionary:
    var keys: Array = stations.keys()
    keys.sort()
    var needed: Dictionary = {}
    var owned := PackedInt32Array()
    for index: int in keys:
        if not stations.has(index + 1):
            continue
        var a := _station_local(stations[index], origin_x_m, origin_z_m)
        var b := _station_local(stations[index + 1], origin_x_m, origin_z_m)
        var middle := Vector2(a.x + b.x, a.z + b.z) * 0.5
        if middle.x < 0.0 or middle.x >= size_m or middle.y < 0.0 or middle.y >= size_m:
            continue
        owned.append(index)
        needed[index] = true
        needed[index + 1] = true
    var caps := PackedInt32Array()
    for end_index: int in [0, count - 1]:
        if not stations.has(end_index):
            continue
        if end_index == 0 and bool(meta.free_start):
            continue
        if end_index == count - 1 and bool(meta.free_end):
            continue
        needed[end_index] = true
        caps.append(end_index)
    if owned.is_empty() and caps.is_empty():
        return {}
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var colors := PackedColorArray()
    var tangents := PackedFloat32Array()
    var indices := PackedInt32Array()
    var emitted: Dictionary = {}
    var emit_keys: Array = needed.keys()
    emit_keys.sort()
    for index: int in emit_keys:
        var station: Dictionary = stations[index]
        var before: Dictionary = stations.get(index - 1, station)
        var after: Dictionary = stations.get(index + 1, station)
        var pa := _station_local(before, origin_x_m, origin_z_m)
        var pb := _station_local(after, origin_x_m, origin_z_m)
        var flat := Vector2(pb.x - pa.x, pb.z - pa.z)
        var direction := Vector3.ZERO
        if flat.length_squared() > 0.000000000001:
            var f: Vector2 = flat.normalized()
            direction = Vector3(f.x, 0.0, f.y)
        var side := Vector3(-direction.z, 0.0, direction.x)
        var sloped: Vector3 = (pb - pa).normalized() if pa.distance_squared_to(pb) > 0.000000000001 else Vector3.FORWARD
        var normal: Vector3 = side.cross(sloped).normalized()
        var p := _station_local(station, origin_x_m, origin_z_m)
        emitted[index] = vertices.size()
        for s: int in 2:
            vertices.append(p + side * (float(station.reach_p) if s == 1 else -float(station.reach_m)))
            normals.append(normal)
            uvs.append(Vector2(float(s), float(station.arc)))
            colors.append(Color(float(station.red), 1.0, clampf(float(station.fade), 0.0, 1.0)))
            tangents.append_array(PackedFloat32Array([direction.x, 0.0, direction.z, 1.0]))
    for index: int in owned:
        var row: int = emitted[index]
        var next_row: int = emitted[index + 1]
        indices.append_array(PackedInt32Array([row, next_row, row + 1, row + 1, next_row, next_row + 1]))
    for end_index: int in caps:
        var station: Dictionary = stations[end_index]
        var row: int = emitted[end_index]
        var direction := Vector3(tangents[row * 4], 0.0, tangents[row * 4 + 2])
        var p := _station_local(station, origin_x_m, origin_z_m)
        var cap_red := float(station.red)
        var arc := float(station.arc)
        var hub := vertices.size()
        vertices.append(p)
        normals.append(Vector3.UP)
        uvs.append(Vector2(0.5, arc))
        colors.append(Color(cap_red, 1.0, 1.0))
        tangents.append_array(PackedFloat32Array([direction.x, 0.0, direction.z, 1.0]))
        var half := float(meta.visual_half_m)
        for step: int in WATER_CAP_SEGMENTS:
            var angle := TAU * float(step) / float(WATER_CAP_SEGMENTS)
            vertices.append(p + Vector3(cos(angle), 0.0, sin(angle)) * half)
            normals.append(Vector3.UP)
            uvs.append(Vector2(1.0, arc))
            colors.append(Color(cap_red, 1.0, 0.0))
            tangents.append_array(PackedFloat32Array([direction.x, 0.0, direction.z, 1.0]))
        for step: int in WATER_CAP_SEGMENTS:
            indices.append_array(PackedInt32Array([hub, hub + 1 + step, hub + 1 + (step + 1) % WATER_CAP_SEGMENTS]))
    if indices.is_empty():
        return {}
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TANGENT] = tangents
    arrays[Mesh.ARRAY_COLOR] = colors
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_INDEX] = indices
    return {"id": river_id, "name": str(meta.get("name", "")), "thermal": bool(meta.get("thermal", false)),
        "width_m": float(meta.width_m), "flow_mps": float(meta.get("flow_mps", 0.0)),
        "sample_z": float(meta.get("sample_z", 0.0)), "tint": bool(meta.get("tint", false)),
        "arrays": arrays}

static func _station_local(station: Dictionary, origin_x_m: float, origin_z_m: float) -> Vector3:
    var p: Array = station.p
    return Vector3(float(p[0]) - origin_x_m, float(p[1]), float(p[2]) - origin_z_m)

## Groups river chunks by id and merges stations by global index for tangent context.
static func river_surfaces(chunks: Array, origin_x_m: float, origin_z_m: float, size_m: float) -> Array:
    var by_river: Dictionary = {}
    for chunk: Dictionary in chunks:
        var river_id := str(chunk.id)
        if not by_river.has(river_id):
            by_river[river_id] = {"stations": {}, "count": int(chunk.river_station_count),
                "meta": {"name": chunk.get("name", ""), "thermal": chunk.get("thermal", false),
                    "width_m": chunk.width_m, "flow_mps": chunk.get("flow_mps", 0.0),
                    "sample_z": chunk.get("sample_z", 0.0), "tint": chunk.get("tint", false),
                    "free_start": chunk.get("free_start", false), "free_end": chunk.get("free_end", false),
                    "visual_half_m": chunk.visual_half_m}}
        var entry: Dictionary = by_river[river_id]
        var first := int(chunk.first_station)
        for k: int in chunk.stations.size():
            entry.stations[first + k] = chunk.stations[k]
    var surfaces: Array = []
    for river_id: String in by_river:
        var entry: Dictionary = by_river[river_id]
        var surface: Dictionary = river_surface(river_id, entry.stations, entry.count, entry.meta,
            origin_x_m, origin_z_m, size_m)
        if not surface.is_empty():
            surfaces.append(surface)
    return surfaces
