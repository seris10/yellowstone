extends MeshInstance3D
## Construct and mutate only on the main thread.
var descriptor: Dictionary
var page: Dictionary
var heights := PackedFloat32Array()
var bytes_estimate: int = 0
var last_used_s: float = 0.0
var water_covered: bool = false
var vegetation_records: Dictionary = {}

## Return false when the terrain surface cannot be built.
func install(data: Dictionary, material: Material, frame: RefCounted) -> bool:
    page = data.page
    descriptor = page.tile
    heights = data.heights
    bytes_estimate = int(data.bytes_estimate)
    water_covered = bool(data.get("water_covered", false))
    vegetation_records = data.get("vegetation_records", {})
    var generated := ArrayMesh.new()
    if not water_covered:
        generated.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, data.arrays)
        if generated.get_surface_count() != 1:
            return false
    mesh = generated
    material_override = material
    name = "Tile_" + str(descriptor.key).replace(":", "_")
    visible = false
    rebase(frame)
    return true

func rebase(frame: RefCounted) -> void:
    position = frame.local_position(float(descriptor.origin_x_m), 0.0, float(descriptor.origin_z_m))
    reset_physics_interpolation()

func sample_height(x_m: float, z_m: float) -> float:
    return sample_heights(descriptor, heights, x_m, z_m)

## Height on the tile's render triangles from plain descriptor and height data; worker-safe.
static func sample_heights(descriptor: Dictionary, heights: PackedFloat32Array, x_m: float, z_m: float) -> float:
    var cells: int = int(descriptor.mesh_cells)
    var n: int = cells + 1
    var spacing: float = float(descriptor.size_m) / cells
    var gx: float = clampf((x_m-float(descriptor.origin_x_m))/spacing, 0.0, cells)
    var gz: float = clampf((z_m-float(descriptor.origin_z_m))/spacing, 0.0, cells)
    var ix: int = mini(int(floor(gx)), cells-1)
    var iz: int = mini(int(floor(gz)), cells-1)
    var fx: float = gx-ix
    var fz: float = gz-iz
    var a: float = heights[iz*n+ix]
    var b: float = heights[iz*n+ix+1]
    var c: float = heights[(iz+1)*n+ix]
    var d: float = heights[(iz+1)*n+ix+1]
    return a+fx*(b-a)+fz*(c-a) if fx+fz<=1.0 else d+(1.0-fx)*(c-d)+(1.0-fz)*(b-d)
