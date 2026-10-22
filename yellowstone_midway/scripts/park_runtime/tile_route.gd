extends RefCounted
## Route geometry for one terrain tile on raw arrays, replicating bake_world.gd make_routes.

## Height sampler for one tile leaf; the b-c triangle split matches tile_visual.gd.
static func _height(heights: PackedFloat32Array, cells: int, size_m: float, x: float, z: float) -> float:
    var n: int = cells + 1
    var spacing: float = size_m / cells
    var gx: float = clampf(x / spacing, 0.0, cells)
    var gz: float = clampf(z / spacing, 0.0, cells)
    var ix: int = mini(int(floor(gx)), cells - 1)
    var iz: int = mini(int(floor(gz)), cells - 1)
    var fx: float = gx - ix
    var fz: float = gz - iz
    var a: float = heights[iz * n + ix]
    var b: float = heights[iz * n + ix + 1]
    var c: float = heights[(iz + 1) * n + ix]
    var d: float = heights[(iz + 1) * n + ix + 1]
    return a + fx * (b - a) + fz * (c - a) if fx + fz <= 1.0 else d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d)

## Merges route chunks by global point index; tangent and span context crosses tile edges.
static func _merge(chunks: Array, origin_x_m: float, origin_z_m: float) -> Dictionary:
    var by_route: Dictionary = {}
    for chunk: Dictionary in chunks:
        var route_id := str(chunk.id)
        if not by_route.has(route_id):
            by_route[route_id] = {"points": {}, "arcs": {}, "spans": [],
                "kind": str(chunk.get("kind", "")), "name": str(chunk.get("name", "")),
                "surface": str(chunk.get("surface", "")), "width_m": float(chunk.get("width_m", 1.0)),
                "source_id": chunk.get("source_id"), "count": int(chunk.get("route_point_count", 0))}
        var entry: Dictionary = by_route[route_id]
        var first := int(chunk.first_point)
        for k: int in chunk.points.size():
            var p: Array = chunk.points[k]
            entry.points[first + k] = Vector3(float(p[0]) - origin_x_m, float(p[1]), float(p[2]) - origin_z_m)
            entry.arcs[first + k] = float(chunk.arcs[k]) if chunk.has("arcs") else 0.0
        for span: Array in chunk.get("bridge_spans", []):
            entry.spans.append([int(span[0]), int(span[1])])
    for route_id: String in by_route:
        by_route[route_id].spans = _merge_spans(by_route[route_id].spans)
    return by_route

static func _merge_spans(spans: Array) -> Array:
    var sorted: Array = spans.duplicate()
    sorted.sort()
    var merged: Array = []
    for span: Array in sorted:
        if not merged.is_empty() and span[0] <= merged[-1][1] + 1:
            merged[-1][1] = maxi(merged[-1][1], span[1])
        else:
            merged.append([span[0], span[1]])
    return merged

static func _tangent(points: Dictionary, index: int) -> Vector3:
    var p: Vector3 = points[index]
    var before: Vector3 = points.get(index - 1, p)
    var after: Vector3 = points.get(index + 1, p)
    var tangent: Vector3 = after - before
    return tangent.normalized() if tangent.length_squared() > 0.000000000001 else Vector3.FORWARD

## Ribbon quad strip over owned segments, matching the bake_world.gd ribbon() vertex layout.
static func _ribbon(points: Dictionary, arcs: Dictionary, indices: Array, width: float,
        size_m: float, rect_only: bool) -> Array:
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var colors := PackedColorArray()
    var face_indices := PackedInt32Array()
    var emitted: Dictionary = {}
    for index: int in indices:
        if not points.has(index + 1):
            continue
        if rect_only:
            var middle: Vector3 = (points[index] + points[index + 1]) * 0.5
            if middle.x < 0.0 or middle.x >= size_m or middle.z < 0.0 or middle.z >= size_m:
                continue
        for k: int in [index, index + 1]:
            if emitted.has(k):
                continue
            var tangent := _tangent(points, k)
            var side := Vector3(-tangent.z, 0.0, tangent.x)
            side = side.normalized() if side.length_squared() > 0.000000000001 else Vector3.RIGHT
            var normal: Vector3 = side.cross(tangent).normalized()
            emitted[k] = vertices.size()
            for s: int in 2:
                vertices.append(points[k] + side * (float(s) - 0.5) * width)
                normals.append(normal)
                uvs.append(Vector2(float(s), float(arcs.get(k, 0.0))))
                colors.append(Color(1, 1, 1))
        var a: int = emitted[index]
        var b: int = emitted[index + 1]
        face_indices.append_array(PackedInt32Array([a, b, a + 1, a + 1, b, b + 1]))
    if face_indices.is_empty():
        return []
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_COLOR] = colors
    arrays[Mesh.ARRAY_INDEX] = face_indices
    return arrays

## Axis-aligned box triangles appended to arrays in progress; one twelve-triangle block per call.
static func _append_box(vertices: PackedVector3Array, normals: PackedVector3Array, uvs: PackedVector2Array,
        indices: PackedInt32Array, center: Vector3, size: Vector3) -> void:
    var half := size * 0.5
    var base := vertices.size()
    for corner: int in 8:
        var offset := Vector3(half.x * (1.0 if corner & 1 else -1.0),
            half.y * (1.0 if corner & 2 else -1.0), half.z * (1.0 if corner & 4 else -1.0))
        vertices.append(center + offset)
        normals.append(Vector3.ZERO)
        uvs.append(Vector2(float(corner & 1), float(corner & 2) * 0.5))
    for face: int in 6:
        var axis: int = face / 2
        var sign_value: float = 1.0 if face % 2 == 0 else -1.0
        var normal := Vector3.ZERO
        normal[axis] = sign_value
        var quad: Array[int] = []
        for corner: int in 8:
            if (sign_value > 0.0) == ((corner >> axis) & 1 == 1):
                quad.append(corner)
        for corner: int in quad:
            normals[base + corner] = normal
        var order := [quad[0], quad[1], quad[2], quad[3]]
        indices.append_array(PackedInt32Array([base + order[0], base + order[1], base + order[2],
            base + order[0], base + order[2], base + order[3]]))

## Swept rail profile with mitered joints, matching the bake_world.gd swept_beam().
static func _swept_beam(centerline: Array, y_off: float, height: float, depth: float) -> Array:
    var n: int = centerline.size()
    if n < 2:
        return []
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var indices := PackedInt32Array()
    for i: int in n:
        var dir_prev: Vector3 = (centerline[i] - centerline[maxi(i - 1, 0)]).normalized() if i > 0 else (centerline[1] - centerline[0]).normalized()
        var dir_next: Vector3 = (centerline[mini(i + 1, n - 1)] - centerline[i]).normalized() if i < n - 1 else dir_prev
        var tangent: Vector3 = dir_prev + dir_next
        tangent = tangent.normalized() if tangent.length_squared() > 0.0001 else dir_next
        var side := Vector3(-tangent.z, 0.0, tangent.x)
        side = side.normalized() if side.length_squared() > 0.0001 else Vector3.RIGHT
        var up: Vector3 = side.cross(tangent).normalized()
        var miter := 1.0 / maxf(tangent.dot(dir_next), 0.5)
        var c: Vector3 = centerline[i] + Vector3.UP * y_off
        var hh := height * 0.5
        var hd := depth * 0.5 * miter
        var corners: Array[Vector3] = [c + up * hh + side * hd, c + up * hh - side * hd,
            c - up * hh - side * hd, c - up * hh + side * hd]
        var corner_normals: Array[Vector3] = [up, up, -up, -up]
        for k: int in 4:
            vertices.append(corners[k])
            normals.append(corner_normals[k])
        if i > 0:
            var a := (i - 1) * 4
            var b := i * 4
            for face: int in 4:
                var f2 := (face + 1) % 4
                indices.append_array(PackedInt32Array([a + face, b + face, b + f2, a + face, b + f2, a + f2]))
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_INDEX] = indices
    return arrays

## All route pieces for one tile: ribbons, decks, skirts, endcaps, stringers and bridge rails.
static func build(chunks: Array, heights: PackedFloat32Array, cells: int,
        origin_x_m: float, origin_z_m: float, size_m: float) -> Array:
    var pieces: Array = []
    var routes: Dictionary = _merge(chunks, origin_x_m, origin_z_m)
    for route_id: String in routes:
        var route: Dictionary = routes[route_id]
        var points: Dictionary = route.points
        var indices: Array = points.keys()
        indices.sort()
        var width := float(route.width_m)
        var kind := str(route.kind)
        var surface := str(route.surface)
        var mat_key := "asphalt" if kind == "road" or surface == "Asphalt" else "gravel"
        if surface == "Wood":
            mat_key = "wood"
        var meta := {"source_name": route.name, "source_object_id": route.source_id}
        var spans: Array = route.spans
        if kind == "trail" and surface == "Native":
            # Dirt tread follows the carved tile heights; bridge spans keep authored deck height.
            var bridged: Dictionary = {}
            for span: Array in spans:
                for k: int in range(int(span[0]), int(span[1]) + 1):
                    bridged[k] = true
            for index: int in indices:
                if not bridged.has(index):
                    var p: Vector3 = points[index]
                    points[index] = Vector3(p.x, _height(heights, cells, size_m, p.x, p.z) + 0.035, p.z)
        if kind == "trail" and surface != "Wood":
            # Deck runs cover bridge spans and lifted tread; the dirt tread itself stays unpaved.
            var keep: Dictionary = {}
            for span: Array in spans:
                for k: int in range(maxi(0, int(span[0]) - 2), mini(int(route.count), int(span[1]) + 3)):
                    keep[k] = true
            for index: int in indices:
                var p: Vector3 = points[index]
                if p.y - _height(heights, cells, size_m, p.x, p.z) > 0.35:
                    keep[index] = true
            var run: Array = []
            var runs: Array = []
            for index: int in indices:
                if keep.has(index):
                    if not run.is_empty() and index != run[-1] + 1:
                        runs.append(run)
                        run = []
                    run.append(index)
                elif not run.is_empty():
                    runs.append(run)
                    run = []
            if not run.is_empty():
                runs.append(run)
            var first_piece := true
            for run_indices: Array in runs:
                if run_indices.size() < 2:
                    continue
                var arrays: Array = _ribbon(points, route.arcs, run_indices, width, size_m, true)
                if not arrays.is_empty():
                    pieces.append({"name": route_id, "piece": "deck", "mat": mat_key, "width_m": width,
                        "collision": true, "arrays": arrays,
                        "meta": meta if first_piece else {}})
                    first_piece = false
                pieces.append_array(_skirts(points, run_indices, width, size_m, heights, cells, mat_key))
                pieces.append_array(_endcaps(points, route, run_indices, width, size_m, heights, cells, mat_key))
        else:
            var arrays: Array = _ribbon(points, route.arcs, indices, width, size_m, true)
            if not arrays.is_empty():
                pieces.append({"name": route_id, "piece": "ribbon", "mat": mat_key, "width_m": width,
                    "collision": true, "arrays": arrays, "meta": meta})
            if str(route.name) == "Grand Loop Road":
                pieces.append_array(_center_lines(points, route.arcs, indices, size_m))
            if surface == "Wood":
                pieces.append_array(_stringers(points, indices, heights, cells, size_m))
                var skirt_indices := indices
                pieces.append_array(_wood_skirts(points, skirt_indices, width, size_m, heights, cells))
        if not spans.is_empty():
            pieces.append_array(_bridge_rails(points, spans, width, size_m))
    return pieces

## Deck side walls dropping to the ground, owned by midpoint.
static func _skirts(points: Dictionary, run_indices: Array, width: float, size_m: float,
        heights: PackedFloat32Array, cells: int, mat_key: String) -> Array:
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var indices := PackedInt32Array()
    var k: int = 0
    while k + 1 < run_indices.size():
        var i: int = run_indices[k]
        var j: int = run_indices[k + 1]
        k += 2
        if j != i + 1 or not points.has(i) or not points.has(j):
            continue
        var a: Vector3 = points[i]
        var b: Vector3 = points[j]
        var middle: Vector3 = (a + b) * 0.5
        if middle.x < 0.0 or middle.x >= size_m or middle.z < 0.0 or middle.z >= size_m:
            continue
        var tangent: Vector3 = (b - a).normalized()
        if tangent.length_squared() < 0.000001:
            continue
        var side := Vector3(-tangent.z, 0.0, tangent.x).normalized()
        for sign_value: float in [-1.0, 1.0]:
            var offset: Vector3 = side * (width * 0.5 * sign_value)
            var top_a: Vector3 = a + offset
            var top_b: Vector3 = b + offset
            var low_a := Vector3(top_a.x, _height(heights, cells, size_m, top_a.x, top_a.z) - 0.12, top_a.z)
            var low_b := Vector3(top_b.x, _height(heights, cells, size_m, top_b.x, top_b.z) - 0.12, top_b.z)
            var base := vertices.size()
            vertices.append_array(PackedVector3Array([top_a, top_b, low_b, low_a]))
            var n: Vector3 = (top_b - top_a).cross(low_a - top_a).normalized()
            for c: int in 4:
                normals.append(n)
                uvs.append(Vector2(c % 2, c / 2))
            indices.append_array(PackedInt32Array([base, base + 2, base + 1, base, base + 3, base + 2]))
    if indices.is_empty():
        return []
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_INDEX] = indices
    return [{"name": "", "piece": "skirt", "mat": mat_key, "collision": false, "arrays": arrays, "meta": {}}]

## Run-end caps only where the run truly ends inside the merged window.
static func _endcaps(points: Dictionary, route: Dictionary, run_indices: Array, width: float, size_m: float,
        heights: PackedFloat32Array, cells: int, mat_key: String) -> Array:
    var pieces: Array = []
    var keep: Dictionary = {}
    for index: int in run_indices:
        keep[index] = true
    var ends: Array[int] = []
    var first: int = run_indices[0]
    var last: int = run_indices[-1]
    if first == 0 or (points.has(first - 1) and not keep.has(first - 1)):
        ends.append(first)
    if last == int(route.count) - 1 or (points.has(last + 1) and not keep.has(last + 1)):
        ends.append(last)
    for end_index: int in ends:
        var p: Vector3 = points[end_index]
        if p.x < 0.0 or p.x >= size_m or p.z < 0.0 or p.z >= size_m:
            continue
        var neighbor: int = run_indices[1] if end_index == first else run_indices[-2]
        var q: Vector3 = points[neighbor]
        var tangent: Vector3 = (p - q).normalized()
        if tangent.length_squared() < 0.000001:
            continue
        var side := Vector3(-tangent.z, 0.0, tangent.x).normalized() * width * 0.5
        var gy: float = _height(heights, cells, size_m, p.x, p.z) - 0.12
        var verts := PackedVector3Array([p - side, p + side,
            Vector3(p.x + side.x, gy, p.z + side.z), Vector3(p.x - side.x, gy, p.z - side.z)])
        var normals := PackedVector3Array()
        var uvs := PackedVector2Array()
        for c: int in 4:
            normals.append(-tangent if end_index == last else tangent)
            uvs.append(Vector2(c % 2, c / 2))
        var arrays: Array = []
        arrays.resize(Mesh.ARRAY_MAX)
        arrays[Mesh.ARRAY_VERTEX] = verts
        arrays[Mesh.ARRAY_NORMAL] = normals
        arrays[Mesh.ARRAY_TEX_UV] = uvs
        arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 0, 2, 3])
        pieces.append({"name": "", "piece": "endcap", "mat": mat_key, "collision": false, "arrays": arrays, "meta": {}})
    return pieces

## Paired center-line strips for the Grand Loop Road.
static func _center_lines(points: Dictionary, arcs: Dictionary, indices: Array, size_m: float) -> Array:
    var pieces: Array = []
    for offset: float in [-0.14, 0.14]:
        var offset_points: Dictionary = {}
        for index: int in indices:
            var tangent := _tangent(points, index)
            var side := Vector3(-tangent.z, 0.0, tangent.x).normalized()
            offset_points[index] = points[index] + side * offset + Vector3.UP * 0.015
        var arrays: Array = _ribbon(offset_points, arcs, indices, 0.08, size_m, true)
        if not arrays.is_empty():
            pieces.append({"name": "CenterLine", "piece": "ribbon", "mat": "paint", "collision": false, "arrays": arrays, "meta": {}})
    return pieces

## Boardwalk stringers at every third global point, merged as box triangles.
static func _stringers(points: Dictionary, indices: Array, heights: PackedFloat32Array,
        cells: int, size_m: float) -> Array:
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var face_indices := PackedInt32Array()
    for index: int in indices:
        if index % 3 != 0:
            continue
        var top: Vector3 = points[index]
        if top.x < 0.0 or top.x >= size_m or top.z < 0.0 or top.z >= size_m:
            continue
        var ground: float = _height(heights, cells, size_m, top.x, top.z)
        var size := Vector3(1.8, maxf(top.y - ground, 0.25), 0.13)
        _append_box(vertices, normals, uvs, face_indices,
            Vector3(top.x, top.y - size.y * 0.5 - 0.05, top.z), size)
    if face_indices.is_empty():
        return []
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_INDEX] = face_indices
    return [{"name": "Stringer", "piece": "boxes", "mat": "timber_stringer", "collision": false, "arrays": arrays, "meta": {}}]

## Boardwalk side walls for wood decks, paired by global index parity like the bake.
static func _wood_skirts(points: Dictionary, indices: Array, width: float, size_m: float,
        heights: PackedFloat32Array, cells: int) -> Array:
    var present: Dictionary = {}
    for index: int in indices:
        present[index] = true
    var run_indices: Array = []
    for index: int in indices:
        if index % 2 == 0 and present.has(index + 1):
            run_indices.append(index)
            run_indices.append(index + 1)
    return _skirts(points, run_indices, width, size_m, heights, cells, "wood")

## Swept bridge rails and evenly spaced posts for each span, owned by midpoint or position.
static func _bridge_rails(points: Dictionary, spans: Array, width: float, size_m: float) -> Array:
    var pieces: Array = []
    var post_vertices := PackedVector3Array()
    var post_normals := PackedVector3Array()
    var post_uvs := PackedVector2Array()
    var post_indices := PackedInt32Array()
    for span: Array in spans:
        var span_indices: Array = []
        for index: int in range(int(span[0]), int(span[1]) + 1):
            if points.has(index):
                span_indices.append(index)
        if span_indices.size() < 2:
            continue
        for sign_value: float in [-1.0, 1.0]:
            var edge: Dictionary = {}
            for index: int in span_indices:
                var before: Vector3 = points.get(maxi(index - 1, int(span[0])), points[index])
                var after: Vector3 = points.get(mini(index + 1, int(span[1])), points[index])
                var tangent: Vector3 = after - before
                tangent = tangent.normalized() if tangent.length_squared() > 0.000000000001 else Vector3.FORWARD
                var side := Vector3(-tangent.z, 0.0, tangent.x).normalized()
                edge[index] = points[index] + side * (width * 0.5 + 0.065) * sign_value
            for beam: Array in [[1.05, 0.12, 0.12, true], [0.53, 0.08, 0.08, true], [-0.05, 0.20, 0.05, false]]:
                pieces.append_array(_swept_beam_owned(edge, span_indices, float(beam[0]), float(beam[1]),
                    float(beam[2]), bool(beam[3]), size_m))
            # Space posts uniformly along each deck edge.
            var spacing := 1.8
            var next := 0.0
            var arc := 0.0
            for k: int in range(1, span_indices.size()):
                var a: Vector3 = edge[span_indices[k - 1]]
                var b: Vector3 = edge[span_indices[k]]
                var seg: float = a.distance_to(b)
                while next <= arc + seg and seg > 0.0001:
                    var t := (next - arc) / seg
                    var p: Vector3 = a.lerp(b, t)
                    if p.x >= 0.0 and p.x < size_m and p.z >= 0.0 and p.z < size_m:
                        _append_box(post_vertices, post_normals, post_uvs, post_indices,
                            p + Vector3.UP * 0.55, Vector3(0.12, 1.12, 0.12))
                    next += spacing
                arc += seg
    if not post_indices.is_empty():
        var arrays: Array = []
        arrays.resize(Mesh.ARRAY_MAX)
        arrays[Mesh.ARRAY_VERTEX] = post_vertices
        arrays[Mesh.ARRAY_NORMAL] = post_normals
        arrays[Mesh.ARRAY_TEX_UV] = post_uvs
        arrays[Mesh.ARRAY_INDEX] = post_indices
        pieces.append({"name": "BridgePost", "piece": "boxes", "mat": "timber_post", "collision": true, "arrays": arrays, "meta": {}})
    return pieces

## One swept beam limited to segments whose midpoint lies in the tile rect.
static func _swept_beam_owned(edge: Dictionary, span_indices: Array, y_off: float, height: float,
        depth: float, collision: bool, size_m: float) -> Array:
    var owned: Array = []
    for k: int in range(span_indices.size() - 1):
        var a: Vector3 = edge[span_indices[k]]
        var b: Vector3 = edge[span_indices[k + 1]]
        var middle: Vector3 = (a + b) * 0.5
        if middle.x >= 0.0 and middle.x < size_m and middle.z >= 0.0 and middle.z < size_m:
            if owned.is_empty() or span_indices[k] != owned[-1] + 1:
                owned.append(span_indices[k])
            owned.append(span_indices[k + 1])
    if owned.size() < 2:
        return []
    var context: Array = owned.duplicate()
    if points_before(span_indices, owned):
        context.push_front(owned[0] - 1)
    if points_after(span_indices, owned):
        context.append(owned[-1] + 1)
    var centerline: Array = []
    var owned_set: Dictionary = {}
    for index: int in owned:
        owned_set[index] = true
    for index: int in context:
        if edge.has(index):
            centerline.append(edge[index])
    var full: Array = _swept_beam(centerline, y_off, height, depth)
    if full.is_empty():
        return []
    # Keep only the quads whose segment belongs to this tile.
    var vertices: PackedVector3Array = full[Mesh.ARRAY_VERTEX]
    var normals: PackedVector3Array = full[Mesh.ARRAY_NORMAL]
    var source_indices: PackedInt32Array = full[Mesh.ARRAY_INDEX]
    var kept := PackedInt32Array()
    for quad: int in range(0, source_indices.size(), 24):
        var segment: int = quad / 24
        var center_index: int = context[segment]
        var next_index: int = context[segment + 1]
        if owned_set.has(center_index) and owned_set.has(next_index):
            kept.append_array(source_indices.slice(quad, quad + 24))
    if kept.is_empty():
        return []
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_INDEX] = kept
    return [{"name": "BridgeRailSwept", "piece": "rail", "mat": "timber_beam", "collision": collision, "arrays": arrays, "meta": {}}]

static func points_before(span_indices: Array, owned: Array) -> bool:
    return not owned.is_empty() and owned[0] > span_indices[0]

static func points_after(span_indices: Array, owned: Array) -> bool:
    return not owned.is_empty() and owned[-1] < span_indices[-1]
