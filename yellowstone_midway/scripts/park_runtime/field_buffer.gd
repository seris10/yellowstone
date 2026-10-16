extends RefCounted
## Timestamped float32 snapshots. Interpolate only declared numeric fields, never IDs or ledgers.
var header: Dictionary = {}
var values := PackedFloat32Array()
var scratch := PackedFloat32Array()

func accept(packet: PackedByteArray, expected_session: String, minimum_revision: int) -> bool:
    if packet.size()<8 or packet.slice(0,4).get_string_from_ascii()!="YSP1":
        return false
    var header_size: int = packet.decode_u32(4)
    if header_size>65536 or packet.size()<8+header_size or packet.size()-8-header_size>16777216:
        return false
    var parsed: Variant = JSON.parse_string(packet.slice(8,8+header_size).get_string_from_utf8())
    if not parsed is Dictionary or parsed.get("schema")!="yellowstone.field_pair.v1":
        return false
    var h: Dictionary = parsed
    if h.get("session_id")!=expected_session or int(h.get("revision",-1))<minimum_revision or h.get("dtype")!="<f4":
        return false
    var entities: Array = h.get("entity_ids",[])
    var fields: Array = h.get("fields",[])
    var units: Array = h.get("units",[])
    if entities.is_empty() or fields.is_empty() or fields.size()!=units.size():
        return false
    var count: int = entities.size()*fields.size()
    var shape: Array = h.get("shape",[])
    if shape.size()!=3 or int(shape[0])!=2 or int(shape[1])!=entities.size() or int(shape[2])!=fields.size():
        return false
    if packet.size()-8-header_size!=count*8:
        return false
    if not is_finite(float(h.get("t0_s",NAN))) or not is_finite(float(h.get("t1_s",NAN))) or float(h.t1_s)<float(h.t0_s):
        return false
    var numbers: PackedFloat32Array = packet.slice(8+header_size).to_float32_array()
    for value: float in numbers:
        if not is_finite(value):
            return false
    header = h
    values = numbers
    scratch.resize(count)
    return true

func sample(time_s: float) -> PackedFloat32Array:
    if header.is_empty():
        return PackedFloat32Array()
    var span: float = float(header.t1_s)-float(header.t0_s)
    var weight: float = clampf((time_s-float(header.t0_s))/span,0.0,1.0) if span>0.0 else 0.0
    for i: int in scratch.size():
        scratch[i] = lerpf(values[i],values[scratch.size()+i],weight)
    return scratch
