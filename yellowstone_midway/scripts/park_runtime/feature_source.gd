extends RefCounted
## Worker-safe readers for the shoreline, pool-cut and route feature pages. Plain data only.
const SCHEMA := "yellowstone.terrain_features.v1"

static func _safe(relative: String) -> bool:
    return not relative.is_absolute_path() and not ".." in relative and not ":" in relative

static func _sha256(bytes: PackedByteArray) -> String:
    var hashing := HashingContext.new()
    hashing.start(HashingContext.HASH_SHA256)
    hashing.update(bytes)
    return hashing.finish().hex_encode()

static func load_index(base_dir: String, reference: Dictionary) -> Dictionary:
    var relative: String = str(reference.get("index", ""))
    if reference.get("schema") != SCHEMA or not _safe(relative):
        return {"error": "Unsupported feature reference"}
    var bytes: PackedByteArray = FileAccess.get_file_as_bytes(base_dir.path_join(relative))
    if bytes.is_empty() or _sha256(bytes) != str(reference.get("sha256", "")):
        return {"error": "Feature index checksum mismatch"}
    var parsed: Variant = JSON.parse_string(bytes.get_string_from_utf8())
    if not parsed is Dictionary or parsed.get("schema") != SCHEMA:
        return {"error": "Invalid feature index"}
    return {"index": parsed, "base": base_dir.path_join("features")}

static func _cell_span(low: float, high: float, origin: float, cell: float, halo: float, count: int) -> Array[int]:
    var first: int = clampi(int(floor((low - halo - origin) / cell)), 0, count - 1)
    var last: int = clampi(int(floor((high + halo - origin) / cell)), 0, count - 1)
    return [first, last]

## Collects the features of one layer from every non-empty page meeting the padded rectangle.
static func collect(source: Dictionary, layer: String, x0: float, z0: float, x1: float, z1: float) -> Dictionary:
    var index: Dictionary = source.index
    var entries: Dictionary = index.get("layers", {}).get(layer, {})
    var cell: float = float(index.cell_m)
    var halo: float = float(index.halo_m)
    var count: int = int(index.cells_per_side)
    var columns: Array[int] = _cell_span(x0, x1, float(index.origin_x_m), cell, halo, count)
    var rows: Array[int] = _cell_span(z0, z1, float(index.origin_z_m), cell, halo, count)
    var features: Array = []
    var seen: Dictionary = {}
    var pages: int = 0
    for cz: int in range(rows[0], rows[1] + 1):
        for cx: int in range(columns[0], columns[1] + 1):
            var name: String = "%d_%d" % [cx, cz]
            if not entries.has(name):
                continue
            var entry: Dictionary = entries[name]
            var relative: String = str(entry.path)
            if not _safe(relative):
                return {"error": "Unsafe feature page path"}
            var bytes: PackedByteArray = FileAccess.get_file_as_bytes(str(source.base).path_join(relative))
            if bytes.size() != int(entry.bytes) or _sha256(bytes) != str(entry.sha256):
                return {"error": "Feature page failed verification: " + relative}
            var page: Variant = JSON.parse_string(bytes.get_string_from_utf8())
            if not page is Dictionary or page.get("layer") != layer:
                return {"error": "Invalid feature page: " + relative}
            pages += 1
            for feature: Dictionary in page.features:
                var identity: String = str(feature.id)
                if layer == "routes":
                    identity += ":%d" % int(feature.first_point)
                if not seen.has(identity):
                    seen[identity] = true
                    features.append(feature)
    return {"features": features, "pages": pages}
