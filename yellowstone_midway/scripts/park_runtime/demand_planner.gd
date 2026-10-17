extends RefCounted
## Visibility changes visual detail and job priority, never the scientific clock.
var split_error_px: float = 6.0
var merge_error_px: float = 3.5
var safety_radius_m: float = 35.0
var lookahead_s: float = 2.5
var max_visits: int = 768
var _was_split: Dictionary = {}
var _visits: int = 0
var _roots: Array = []
var _resident: Dictionary = {}
var _frame: RefCounted
var _camera: Camera3D
var _planes: Array[Plane] = []
var _predicted: Vector3
var _position: Vector3
var _focal_px: float
var _radius: float
var _requests: Dictionary
var _collision: Dictionary

func plan(roots: Array, resident: Dictionary, frame: RefCounted, camera: Camera3D, velocity: Vector3) -> Dictionary:
    _roots = roots
    _resident = resident
    _frame = frame
    _camera = camera
    _planes = camera.get_frustum()
    _position = camera.global_position
    _predicted = _position + velocity * lookahead_s
    _radius = safety_radius_m + velocity.length() * lookahead_s
    var viewport_size: Vector2 = camera.get_viewport().get_visible_rect().size
    var axis_pixels: float = viewport_size.y if camera.keep_aspect == Camera3D.KEEP_HEIGHT else viewport_size.x
    _focal_px = axis_pixels / maxf(0.001, 2.0 * tan(deg_to_rad(camera.fov) * 0.5))
    _requests = {}
    _collision = {}
    _visits = 0
    var leaves: Array[String] = []
    var ordered: Array = roots.duplicate()
    ordered.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return _distance(a, _position) < _distance(b, _position))
    for root: Dictionary in ordered:
        leaves.append_array(_visit(root))
    # Prevent the split-memory dictionary from growing with the whole explored park.
    for key: String in _was_split.keys():
        if not _requests.has(key):
            _was_split.erase(key)
    return {"requests": _requests, "leaves": leaves, "collision": _collision,
            "visits": _visits, "safety_radius_m": _radius}

func _local_center(d: Dictionary) -> Vector3:
    return _frame.local_position(float(d.origin_x_m)+float(d.size_m)*0.5,
        (float(d.min_y_m)+float(d.max_y_m))*0.5, float(d.origin_z_m)+float(d.size_m)*0.5)

func _distance(d: Dictionary, p: Vector3) -> float:
    var center: Vector3 = _local_center(d)
    var half: float = float(d.size_m)*0.5
    return Vector2(maxf(absf(p.x-center.x)-half,0.0), maxf(absf(p.z-center.z)-half,0.0)).length()

func _in_frustum(d: Dictionary) -> bool:
    var center: Vector3 = _local_center(d)
    var half: Vector3 = Vector3(float(d.size_m), float(d.max_y_m)-float(d.min_y_m), float(d.size_m))*0.5
    # Frustum planes face outward; the box support radius keeps the test conservative.
    for plane: Plane in _planes:
        var radius: float = absf(plane.normal.x)*half.x + absf(plane.normal.y)*half.y + absf(plane.normal.z)*half.z
        if plane.distance_to(center) > radius:
            return false
    return true

func _coarse_lower_height(x: float, z: float) -> float:
    for d: Dictionary in _roots:
        if x >= float(d.origin_x_m) and x <= float(d.origin_x_m)+float(d.size_m) and z >= float(d.origin_z_m) and z <= float(d.origin_z_m)+float(d.size_m):
            var tile = _resident.get(str(d.key))
            if tile != null:
                return tile.sample_height(x,z) - float(d.error_m)
    return -INF

func _occlusion_weight(d: Dictionary) -> float:
    # The sampled horizon weights job priority; coarse cover, collision and simulation stay.
    var target: Vector3 = _local_center(d)
    target.y = float(d.max_y_m) + 2.0
    var distance_m: float = _position.distance_to(target)
    if distance_m < _radius * 2.0:
        return 1.0
    for i: int in range(1,9):
        var weight: float = float(i)/10.0
        var point: Vector3 = _position.lerp(target,weight)
        var absolute: Array[float] = _frame.absolute_xz(point)
        if _coarse_lower_height(absolute[0],absolute[1]) > point.y + 3.0:
            return 0.15
    return 1.0

func _request(d: Dictionary, priority: float) -> void:
    var key: String = str(d.key)
    if not _requests.has(key) or float(_requests[key].priority) < priority:
        _requests[key] = {"tile": d, "priority": priority}

func _visit(d: Dictionary) -> Array[String]:
    _visits += 1
    var key: String = str(d.key)
    var distance_m: float = _distance(d,_position)
    var predicted_distance: float = _distance(d,_predicted)
    var safety: bool = minf(distance_m,predicted_distance) <= _radius
    var visible_now: bool = _in_frustum(d)
    var score: float = float(d.error_m)*_focal_px/maxf(1.0,distance_m)
    var visibility_weight: float = _occlusion_weight(d) if visible_now and not safety else 1.0
    var priority: float = (1e9 if safety else 1e5 if visible_now else 1e3) + score*visibility_weight - distance_m*0.001
    _request(d,priority)
    var tile = _resident.get(key)
    if tile == null:
        return []
    var lod: int = int(d.lod)
    if lod == 0:
        if safety:
            _collision[key] = true
        return [key]
    var threshold: float = merge_error_px if _was_split.get(key,false) else split_error_px
    var weighted_score: float = score * (visibility_weight if visible_now else 0.025)
    var refine: bool = safety or weighted_score > threshold
    if not refine or _visits >= max_visits:
        _was_split[key] = false
        return [key]
    _was_split[key] = true
    var children: Array = tile.page.get("children",[])
    if children.size() != 4:
        return [key]
    var all_ready: bool = true
    var provisional: Array[String] = []
    for child: Dictionary in children:
        _request(child,priority+1.0)
        if not _resident.has(str(child.key)):
            all_ready = false
        else:
            provisional.append_array(_visit(child))
    # A parent stays until all four child covers are ready.
    if all_ready:
        return provisional
    return [key]
