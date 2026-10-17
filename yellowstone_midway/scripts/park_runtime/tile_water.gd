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
