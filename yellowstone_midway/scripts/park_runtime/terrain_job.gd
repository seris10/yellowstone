extends RefCounted
## Worker produces only arrays and metadata. No Nodes, Meshes, Textures or physics resources.
const FeatureSource = preload("res://scripts/park_runtime/feature_source.gd")
const TileWater = preload("res://scripts/park_runtime/tile_water.gd")
var descriptor: Dictionary
var base_path: String
var dataset_revision: String
var features: Dictionary = {}
var task_id: int = -1
var result: Dictionary = {}
var _mutex := Mutex.new()
var _cancelled: bool = false

func configure(tile: Dictionary, root_path: String, revision: String) -> void:
    descriptor = tile.duplicate(true)
    base_path = root_path
    dataset_revision = revision

## Bind verified FeatureSource.load_index output; absent indexes yield no tile water cut.
func configure_features(source: Dictionary) -> void:
    features = source

func cancel() -> void:
    _mutex.lock()
    _cancelled = true
    _mutex.unlock()

func cancelled() -> bool:
    _mutex.lock()
    var value: bool = _cancelled
    _mutex.unlock()
    return value

func _fail(reason: String) -> void:
    result = {"error": reason, "key": descriptor.get("key", ""), "revision": dataset_revision}

func _safe(relative: String) -> bool:
    return not relative.is_absolute_path() and not ".." in relative and not ":" in relative

func run() -> void:
    if cancelled():
        return
    var page_path: String = str(descriptor.page)
    if not _safe(page_path):
        _fail("Unsafe page path")
        return
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(base_path.path_join(page_path)))
    if not parsed is Dictionary:
        _fail("Missing or invalid tile page: " + page_path)
        return
    var page: Dictionary = parsed
    if page.get("schema") != "yellowstone.terrain_tiles.v1" or page.get("tile", {}).get("key") != descriptor.key:
        _fail("Tile identity/schema mismatch")
        return
    if page.get("tile", {}) != descriptor:
        _fail("Page descriptor differs from requested source identity")
        return
    var child_value: Variant = page.get("children", [])
    if not child_value is Array:
        _fail("Children must be an array")
        return
    var children: Array = child_value
    var lod: int = int(descriptor.lod)
    if children.size() != (4 if lod > 0 else 0):
        _fail("Incomplete child cover")
        return
    for i: int in children.size():
        if not children[i] is Dictionary:
            _fail("Invalid child descriptor")
            return
        var child: Dictionary = children[i]
        var half: float = float(descriptor.size_m) * 0.5
        if not child.has_all(["key", "page", "lod", "mesh_cells", "size_m", "origin_x_m", "origin_z_m", "min_y_m", "max_y_m", "error_m"]):
            _fail("Missing child metadata")
            return
        if int(child.lod) != lod - 1 or int(child.mesh_cells) != int(descriptor.mesh_cells) or not is_equal_approx(float(child.size_m), half):
            _fail("Invalid child level or size")
            return
        if absf(float(child.origin_x_m) - (float(descriptor.origin_x_m) + (i % 2) * half)) > 0.000001 or absf(float(child.origin_z_m) - (float(descriptor.origin_z_m) + int(i / 2) * half)) > 0.000001:
            _fail("Child cover has an overlap or gap")
            return
    var cells: int = int(descriptor.mesh_cells)
    if cells < 4 or cells > 128:
        _fail("Unsupported mesh resolution")
        return
    var header_value: Variant = page.get("heights", {})
    if not header_value is Dictionary:
        _fail("Invalid height metadata")
        return
    var header: Dictionary = header_value
    var relative: String = str(header.get("path", ""))
    if not _safe(relative) or header.get("dtype") != "<f4":
        _fail("Unsafe or unsupported height source")
        return
    var path: String = base_path.path_join(relative)
    var bytes: PackedByteArray = FileAccess.get_file_as_bytes(path)
    if bytes.size() != (cells + 1) * (cells + 1) * 4 or bytes.size() != int(header.get("bytes", -1)):
        _fail("Height dimensions do not match")
        return
    var hashing := HashingContext.new()
    hashing.start(HashingContext.HASH_SHA256)
    hashing.update(bytes)
    if hashing.finish().hex_encode() != str(header.get("sha256", "")):
        _fail("Height checksum mismatch")
        return
    var heights: PackedFloat32Array = bytes.to_float32_array()
    for height: float in heights:
        if not is_finite(height):
            _fail("NoData is not a valid height")
            return
    if cancelled():
        return
    var n: int = cells + 1
    var spacing: float = float(descriptor.size_m) / float(cells)
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var indices := PackedInt32Array()
    vertices.resize(n * n)
    normals.resize(n * n)
    uvs.resize(n * n)
    for z: int in n:
        if cancelled():
            return
        for x: int in n:
            var i: int = z * n + x
            vertices[i] = Vector3(x * spacing, heights[i], z * spacing)
            var left: int = maxi(0, x - 1)
            var right: int = mini(cells, x + 1)
            var top: int = maxi(0, z - 1)
            var bottom: int = mini(cells, z + 1)
            var dx: float = (heights[z*n+right] - heights[z*n+left]) / (float(right-left)*spacing)
            var dz: float = (heights[bottom*n+x] - heights[top*n+x]) / (float(bottom-top)*spacing)
            normals[i] = Vector3(-dx, 1.0, -dz).normalized()
            uvs[i] = Vector2(float(x)/cells, float(z)/cells)
    for z: int in cells:
        for x: int in cells:
            var a: int = z*n+x
            indices.append_array(PackedInt32Array([a,a+1,a+n,a+1,a+n+1,a+n]))
    var origin_x: float = float(descriptor.origin_x_m)
    var origin_z: float = float(descriptor.origin_z_m)
    var size: float = float(descriptor.size_m)
    var pool_ids: Array[String] = []
    var routes: Array = []
    var shoreline_arrays: Array = []
    var water_report: Dictionary = {}
    var regions: Array = []
    if not features.is_empty():
        var found: Dictionary = FeatureSource.collect(features, "pools", origin_x, origin_z, origin_x + size, origin_z + size)
        if found.has("error"):
            _fail(str(found.error))
            return
        var local_pools: Array = []
        local_pools = TileWater.localize(found.features, origin_x, origin_z)
        var meeting: Array = []
        for k: int in found.features.size():
            var b: Array = found.features[k].bounds_m
            if b[0] <= origin_x + size and b[2] >= origin_x and b[1] <= origin_z + size and b[3] >= origin_z:
                meeting.append(local_pools[k])
                pool_ids.append(str(local_pools[k].id))
        if lod == 0:
            var walk: Dictionary = FeatureSource.collect(features, "routes", origin_x, origin_z, origin_x + size, origin_z + size)
            if walk.has("error"):
                _fail(str(walk.error))
                return
            routes = walk.features
        if not meeting.is_empty():
            var grid_arrays: Array = []
            grid_arrays.resize(Mesh.ARRAY_MAX)
            grid_arrays[Mesh.ARRAY_VERTEX] = vertices
            grid_arrays[Mesh.ARRAY_NORMAL] = normals
            grid_arrays[Mesh.ARRAY_TEX_UV] = uvs
            grid_arrays[Mesh.ARRAY_INDEX] = indices
            var cut: Dictionary = TileWater.cut(grid_arrays, meeting)
            if not cut.ok:
                _fail("Water cut failed: " + str(cut.get("reason", "unknown")))
                return
            if cut.arrays.is_empty():
                indices = PackedInt32Array()
            else:
                vertices = cut.arrays[Mesh.ARRAY_VERTEX]
                normals = cut.arrays[Mesh.ARRAY_NORMAL]
                uvs = cut.arrays[Mesh.ARRAY_TEX_UV]
                indices = cut.arrays[Mesh.ARRAY_INDEX]
            shoreline_arrays = cut.shoreline_arrays
            regions = TileWater.regions(meeting)
            water_report = cut.duplicate()
            water_report.erase("arrays")
            water_report.erase("shoreline_arrays")
    # Visual skirts hide dyadic T-junctions. They are never collision geometry.
    var perimeter := PackedInt32Array()
    for x: int in n:
        perimeter.append(x)
    for z: int in range(1,n):
        perimeter.append(z*n+cells)
    for x: int in range(cells-1,-1,-1):
        perimeter.append(cells*n+x)
    for z: int in range(cells-1,0,-1):
        perimeter.append(z*n)
    var skirt_depth: float = maxf(2.0, float(descriptor.error_m) * 2.0 + 0.5)
    var skirts_omitted: int = 0
    for i: int in perimeter.size():
        var a: int = perimeter[i]
        var b: int = perimeter[(i+1)%perimeter.size()]
        if not regions.is_empty() and TileWater.edge_over_water(regions, vertices[a], vertices[b]):
            skirts_omitted += 1
            continue
        var c: int = vertices.size()
        vertices.append(vertices[a]-Vector3.UP*skirt_depth)
        vertices.append(vertices[b]-Vector3.UP*skirt_depth)
        normals.append(normals[a])
        normals.append(normals[b])
        uvs.append(uvs[a])
        uvs.append(uvs[b])
        indices.append_array(PackedInt32Array([a,c,b,b,c,c+1]))
    if cancelled():
        return
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_INDEX] = indices
    var shoreline_bytes: int = 0
    if not shoreline_arrays.is_empty():
        shoreline_bytes = shoreline_arrays[Mesh.ARRAY_VERTEX].size()*32 + shoreline_arrays[Mesh.ARRAY_INDEX].size()*4
    result = {"key": descriptor.key, "revision": dataset_revision, "page": page,
              "arrays": arrays, "heights": heights, "shoreline_arrays": shoreline_arrays,
              "pools": pool_ids, "routes": routes, "water": water_report, "skirts_omitted": skirts_omitted,
              "bytes_estimate": vertices.size()*32+indices.size()*4+heights.size()*4+shoreline_bytes}
