extends SceneTree
## Decodes the golden Python field packet with the Godot field buffer.
const Fields = preload("res://scripts/park_runtime/field_buffer.gd")
const FIXTURE := "res://tests/park_runtime/fixtures/field_pair.bin"
var failures: int = 0
var checks: int = 0

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool, message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error(message)

func run() -> void:
    var packet: PackedByteArray = FileAccess.get_file_as_bytes(FIXTURE)
    check(packet.size() == 256, "fixture missing or resized")
    var buffer = Fields.new()
    check(buffer.accept(packet, "golden-session", 3), "valid packet rejected")
    check(not Fields.new().accept(packet, "other-session", 3), "wrong session accepted")
    check(not Fields.new().accept(packet, "golden-session", 4), "stale revision accepted")
    check(not Fields.new().accept(packet.slice(0, packet.size() - 4), "golden-session", 3), "truncated packet accepted")
    var midpoint: PackedFloat32Array = buffer.sample(5.0)
    check(midpoint.size() == 4, "sample size differs")
    if midpoint.size() == 4:
        check(is_equal_approx(midpoint[0], 11.0) and is_equal_approx(midpoint[1], 2.5), "entity a midpoint differs")
        check(is_equal_approx(midpoint[2], 16.0) and is_equal_approx(midpoint[3], 6.0), "entity b midpoint differs")
    check(is_equal_approx(buffer.sample(-5.0)[0], 10.0) and is_equal_approx(buffer.sample(99.0)[0], 12.0), "clamping differs")
    print("PARK_FIELD_CODEC checks=", checks, " failures=", failures)
    quit(1 if failures else 0)
