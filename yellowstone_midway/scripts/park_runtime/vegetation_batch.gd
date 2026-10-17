extends RefCounted
## Bounded regional instance batch built from source-supplied placements.

static func create(shared_mesh: Mesh, transforms: PackedFloat32Array, instance_count: int,
        bounds: AABB, tile_local_origin: Vector3, shared_material: Material = null,
        use_colors: bool = true, use_custom: bool = true) -> MultiMeshInstance3D:
    var stride: int = 12 + (4 if use_colors else 0) + (4 if use_custom else 0)
    assert(instance_count>=0 and instance_count<=4096,"Split vegetation pages into bounded batches")
    assert(transforms.size()==instance_count*stride,"Invalid packed instance stride")
    assert(shared_mesh!=null and bounds.size.x>=0.0 and bounds.size.y>=0.0 and bounds.size.z>=0.0)
    var multimesh := MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_3D
    multimesh.use_colors = use_colors
    multimesh.use_custom_data = use_custom
    multimesh.mesh = shared_mesh
    multimesh.instance_count = instance_count
    multimesh.buffer = transforms
    multimesh.custom_aabb = bounds
    var instance := MultiMeshInstance3D.new()
    instance.multimesh = multimesh
    instance.material_override = shared_material
    instance.position = tile_local_origin
    return instance

static func set_visible_prefix(instance: MultiMeshInstance3D, count: int) -> void:
    # Optional preordered-density LOD. Do not reorder thousands of records per camera step.
    assert(count>=0 and count<=instance.multimesh.instance_count)
    instance.multimesh.visible_instance_count = count
