extends RefCounted
## Float64 scalar absolute coordinates. Do not store UTM in Vector3 on standard builds.
signal rebased(delta_local: Vector3)

var origin_x_m: float = 0.0
var origin_z_m: float = 0.0
var easting_m: float = 512952.5950985841
var northing_m: float = 4930199.044097667
var vertical_origin_m: float = 2200.0
var rebase_threshold_m: float = 1024.0
var rebase_grid_m: float = 512.0
var _roots: Array[Node3D] = []

func configure(metadata: Dictionary) -> void:
    assert(str(metadata.get("crs", "")) == "EPSG:32612", "Explicit CRS adapter required")
    easting_m = float(metadata.easting_m)
    northing_m = float(metadata.northing_m)
    vertical_origin_m = float(metadata.vertical_origin_m)

func absolute_xz(local: Vector3) -> Array[float]:
    return [origin_x_m + float(local.x), origin_z_m + float(local.z)]

func local_position(x_m: float, y_m: float, z_m: float) -> Vector3:
    return Vector3(x_m - origin_x_m, y_m, z_m - origin_z_m)

func projected(local: Vector3) -> Array[float]:
    return [easting_m + origin_x_m + float(local.x), northing_m - origin_z_m - float(local.z), vertical_origin_m + float(local.y)]

func register_root(node: Node3D) -> void:
    assert(not _roots.has(node))
    for other: Node3D in _roots:
        assert(not other.is_ancestor_of(node) and not node.is_ancestor_of(other), "Never shift a hierarchy twice")
    _roots.append(node)

func maybe_rebase(observer: Node3D) -> bool:
    # Call once at the beginning of a physics tick. Only horizontal origin shifting.
    var p: Vector3 = observer.global_position
    if Vector2(p.x, p.z).length() <= rebase_threshold_m:
        return false
    var shift := Vector3(roundf(p.x / rebase_grid_m) * rebase_grid_m, 0.0, roundf(p.z / rebase_grid_m) * rebase_grid_m)
    origin_x_m += float(shift.x)
    origin_z_m += float(shift.z)
    for node: Node3D in _roots:
        if is_instance_valid(node):
            node.global_position -= shift
            node.reset_physics_interpolation()
    rebased.emit(shift)
    return true
