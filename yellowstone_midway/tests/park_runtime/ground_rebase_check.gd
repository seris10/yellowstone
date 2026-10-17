extends SceneTree
## Headless checks that ground texture lookups follow absolute geography across render-origin rebases.
const Materials = preload("res://scripts/terrain_materials.gd")
const INCLUDE := "res://shaders/ground_surface.gdshaderinc"
const TERRAIN := "res://shaders/terrain.gdshader"
const APRON := "res://shaders/thermal_apron.gdshader"
const UV_TOLERANCE := 5.0e-4
const ROTATION_C := 0.8
const ROTATION_S := 0.6
var failures: int = 0
var checks: int = 0

class FakeFrame extends RefCounted:
    signal rebased(delta_local: Vector3)
    var origin_x_m: float = 0.0
    var origin_z_m: float = 0.0

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool, message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error(message)

func read_text(path: String) -> String:
    return FileAccess.get_file_as_string(path)

func f32(value: float) -> float:
    return PackedFloat32Array([value])[0]

func wrapped_distance(a: float, b: float) -> float:
    var d: float = absf(fposmod(a, 1.0) - fposmod(b, 1.0))
    return minf(d, 1.0 - d)

func vec_close(a: Vector2, b: Vector2, tolerance: float) -> bool:
    return a.distance_to(b) <= tolerance

func uniform_names(path: String) -> Dictionary:
    var names: Dictionary = {}
    for entry: Dictionary in (load(path) as Shader).get_shader_uniform_list():
        names[entry.name] = true
    return names

func check_shader_sources() -> void:
    var body: String = read_text(INCLUDE)
    var function_text: String = body.substr(body.find("struct GroundSurface"))
    check(function_text.find("2048.0") < 0 and function_text.find("4096.0") < 0, "Ground functions hard-code the Midway square")
    var periods: Dictionary = {}
    var lookup := RegEx.new()
    lookup.compile("p\\.xz / ([0-9.]+)")
    for hit: RegExMatch in lookup.search_all(function_text):
        periods[float(hit.get_string(1))] = true
    var tabulated: Dictionary = {}
    for entry: Array in Materials.REPEAT_PHASES:
        if not entry[1] is String:
            tabulated[float(entry[1])] = true
    check(periods.keys().size() == tabulated.keys().size(), "Shader literal periods %s differ from the phase table %s" % [periods.keys(), tabulated.keys()])
    for period: float in periods:
        check(tabulated.has(period), "Shader period %s has no CPU phase" % period)
    var declared := RegEx.new()
    declared.compile("uniform float (\\w+) = (-?[0-9.]+);")
    var defaults: Dictionary = {}
    for path: String in [INCLUDE, TERRAIN, APRON]:
        for hit: RegExMatch in declared.search_all(read_text(path)):
            defaults[hit.get_string(1)] = float(hit.get_string(2))
    for name: String in Materials.SHIFTED_SCALARS:
        check(defaults.has(name), "Shader lacks uniform " + name)
        if defaults.has(name):
            check(is_equal_approx(defaults[name], float(Materials.SHIFTED_SCALARS[name][1])), "Default for %s differs from the shader" % name)
    var terrain: Dictionary = uniform_names(TERRAIN)
    var apron: Dictionary = uniform_names(APRON)
    for names: Dictionary in [terrain, apron]:
        for layer: String in Materials.VEC2_LAYERS:
            for name: String in Materials.VEC2_LAYERS[layer]:
                check(names.has(name), "Shader lacks uniform " + name)
        for entry: Array in Materials.REPEAT_PHASES:
            check(names.has(entry[0]), "Shader lacks uniform " + str(entry[0]))
    for layer: String in Materials.SCALAR_LAYERS:
        for name: String in Materials.SCALAR_LAYERS[layer]:
            check(apron.has(name) or terrain.has(name), "No shader declares " + name)

func new_material(path: String) -> ShaderMaterial:
    var mat := ShaderMaterial.new()
    mat.shader = load(path)
    return mat

func check_midway_square(mat: ShaderMaterial) -> void:
    check(Materials.bind_ground_material(mat), "bind_ground_material failed")
    for layer: String in Materials.VEC2_LAYERS:
        var names: Array = Materials.VEC2_LAYERS[layer]
        check(mat.get_shader_parameter(names[0]) == Vector2(-2048.0, -2048.0), layer + " origin differs from the Midway square")
        check(mat.get_shader_parameter(names[1]) == Vector2(4096.0, 4096.0), layer + " extent differs from the Midway square")
    for entry: Array in Materials.REPEAT_PHASES:
        check(mat.get_shader_parameter(entry[0]) == Vector2.ZERO, str(entry[0]) + " is not zero at the Midway origin")

## Return each repeating shader lookup's float32 coordinate for a local point.
func lookups(mat: ShaderMaterial, local: Vector2) -> Dictionary:
    var out: Dictionary = {}
    for entry: Array in Materials.REPEAT_PHASES:
        var period: float = float(mat.get_shader_parameter(entry[1])) if entry[1] is String else float(entry[1])
        var base := Vector2(f32(local.x / period), f32(local.y / period))
        if entry[2]:
            base = Vector2(f32(ROTATION_C) * base.x + f32(ROTATION_S) * base.y, -f32(ROTATION_S) * base.x + f32(ROTATION_C) * base.y)
        base *= f32(float(entry[3]))
        var phase: Vector2 = mat.get_shader_parameter(entry[0])
        out[entry[0]] = Vector2(f32(base.x + phase.x), f32(base.y + phase.y))
    for layer: String in Materials.VEC2_LAYERS:
        var names: Array = Materials.VEC2_LAYERS[layer]
        var origin: Vector2 = mat.get_shader_parameter(names[0])
        var extent: Vector2 = mat.get_shader_parameter(names[1])
        out[layer] = (local - origin) / extent
    return out

func ideal_lookups(absolute: Vector2) -> Dictionary:
    var out: Dictionary = {}
    for entry: Array in Materials.REPEAT_PHASES:
        var period: float = Materials.TILE_DEFAULTS[entry[1]] if entry[1] is String else float(entry[1])
        var base: Vector2 = absolute / period
        if entry[2]:
            base = Vector2(ROTATION_C * base.x + ROTATION_S * base.y, -ROTATION_S * base.x + ROTATION_C * base.y)
        out[entry[0]] = base * float(entry[3])
    for layer: String in Materials.VEC2_LAYERS:
        out[layer] = (absolute - Vector2(-2048.0, -2048.0)) / 4096.0
    return out

func compare_lookups(a: Dictionary, b: Dictionary) -> float:
    var worst: float = 0.0
    for key: String in a:
        if Materials.VEC2_LAYERS.has(key):
            worst = maxf(worst, (a[key] - b[key]).length())
        else:
            worst = maxf(worst, maxf(wrapped_distance(a[key].x, b[key].x), wrapped_distance(a[key].y, b[key].y)))
    return worst

func check_rebase_continuity(mat: ShaderMaterial) -> void:
    var origins: Array[Vector2] = [Vector2.ZERO, Vector2(512.0, -1024.0), Vector2(-3072.0, 2560.0), Vector2(102400.0, -51200.0), Vector2(1.0e6, 7.5e5)]
    var points: Array[Vector2] = [Vector2(0.0, 0.0), Vector2(137.31, -402.77), Vector2(-955.5, 818.25), Vector2(12.0, 903.125)]
    for first: Vector2 in origins:
        for second: Vector2 in origins:
            Materials.set_render_origin(mat, first.x, first.y)
            var before: Array[Dictionary] = []
            for local: Vector2 in points:
                before.append(lookups(mat, local))
            Materials.set_render_origin(mat, second.x, second.y)
            for index: int in points.size():
                var local_after: Vector2 = points[index] - (second - first)
                var worst: float = compare_lookups(before[index], lookups(mat, local_after))
                check(worst <= 0.002 * maxf(1.0, (first - second).length() / 4096.0), "Ground lookups moved %.6f across rebase %s to %s" % [worst, first, second])
    var reference := Vector2(300.0, -200.0)
    Materials.set_render_origin(mat, 20480.0, -10240.0)
    var ideal: Dictionary = ideal_lookups(reference + Vector2(20480.0, -10240.0))
    var local: Dictionary = lookups(mat, reference)
    for key: String in ideal:
        if not Materials.VEC2_LAYERS.has(key):
            check(wrapped_distance(ideal[key].x, local[key].x) <= UV_TOLERANCE and wrapped_distance(ideal[key].y, local[key].y) <= UV_TOLERANCE, "%s disagrees with the absolute lookup" % key)
    Materials.set_render_origin(mat, 0.0, 0.0)
    var unchanged: Dictionary = lookups(mat, Vector2(10.0, 20.0))
    Materials.set_render_origin(mat, 5120.0, 0.0)
    for entry: Array in Materials.REPEAT_PHASES:
        mat.set_shader_parameter(entry[0], Vector2.ZERO)
    var control: float = compare_lookups(unchanged, lookups(mat, Vector2(10.0, 20.0) - Vector2(5120.0, 0.0)))
    check(control > 0.05, "Zero phases should slide the ground after a rebase; measured %.4f" % control)

func check_rectangles(apron: ShaderMaterial) -> void:
    Materials.set_render_origin(apron, 0.0, 0.0)
    Materials.set_layer_rect(apron, "extent", -340.0, -380.0, 600.0, 600.0)
    Materials.set_layer_rect(apron, "pigment", -640.0, -640.0, 1280.0, 1280.0)
    Materials.set_layer_rect(apron, "core_cut", -340.0, -380.0, 600.0, 600.0)
    Materials.set_render_origin(apron, 512.0, -512.0)
    check(float(apron.get_shader_parameter("extent_x_min_m")) == -852.0, "Extent x minimum is not origin-relative")
    check(float(apron.get_shader_parameter("extent_z_min_m")) == 132.0, "Extent z minimum is not origin-relative")
    check(float(apron.get_shader_parameter("extent_width_m")) == 600.0, "Extent width should not move with the origin")
    check(float(apron.get_shader_parameter("pigment_x_min_m")) == -1152.0, "Pigment x minimum is not origin-relative")
    check(float(apron.get_shader_parameter("core_cut_x_max_m")) == -252.0, "Core cut maximum is not origin-relative")
    check(float(apron.get_shader_parameter("core_cut_z_max_m")) == 132.0 + 600.0, "Core cut z maximum is not origin-relative")
    apron.set_shader_parameter("outflow_x_min_m", 100.0)
    Materials.set_render_origin(apron, 1024.0, -512.0)
    check(float(apron.get_shader_parameter("outflow_x_min_m")) == 100.0 - 512.0, "A rectangle written outside the class lost its geography")
    Materials.set_render_origin(apron, 0.0, 0.0)
    check(float(apron.get_shader_parameter("extent_x_min_m")) == -340.0, "Returning to the Midway origin does not restore the rectangle")
    check(Materials.get_render_origin(apron) == [0.0, 0.0], "Render origin was not recorded")

func check_follow_frame() -> void:
    var mat: ShaderMaterial = new_material(TERRAIN)
    var frame := FakeFrame.new()
    Materials.follow_frame(frame, mat)
    check(mat.get_shader_parameter("soil_phase") == Vector2.ZERO, "Fresh frame should leave the phase at zero")
    frame.origin_x_m = 1024.0
    frame.origin_z_m = 512.0
    frame.rebased.emit(Vector3(1024.0, 0.0, 512.0))
    check(Materials.get_render_origin(mat) == [1024.0, 512.0], "Rebase signal did not move the material origin")
    check(vec_close(mat.get_shader_parameter("soil_phase"), Materials.repeat_phase(1024.0, 512.0, 3.15, false, 1.0), 1.0e-6), "Rebase signal did not update the soil phase")

func run() -> void:
    check_shader_sources()
    var terrain: ShaderMaterial = new_material(TERRAIN)
    check_midway_square(terrain)
    check_rebase_continuity(terrain)
    var apron: ShaderMaterial = new_material(APRON)
    check(Materials.bind_ground_material(apron), "bind_ground_material failed on the apron")
    check_rectangles(apron)
    check_follow_frame()
    print("GROUND_REBASE %d checks; %d failures" % [checks, failures])
    quit(1 if failures > 0 else 0)
