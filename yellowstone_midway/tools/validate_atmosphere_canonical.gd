extends SceneTree
## Verifies the published atmosphere bundle in yellowstone_atmosphere/ matches the canonical runtime copies in yellowstone_midway/scripts/ and yellowstone_midway/shaders/. Run: godot --headless --path yellowstone_midway --script tools/validate_atmosphere_canonical.gd

const PAIRS: Array = [
	["res://scripts/atmosphere_optics.gd", "../yellowstone_atmosphere/scripts/atmosphere_optics.gd"],
	["res://shaders/rainbow.gdshader", "../yellowstone_atmosphere/shaders/rainbow.gdshader"],
	["res://shaders/physical_daylight.gdshader", "../yellowstone_atmosphere/shaders/physical_daylight.gdshader"],
	["res://scripts/yellowstone_atmosphere.gd", "../yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd"],
	["res://scripts/weather_snapshot_reader.gd", "../yellowstone_atmosphere/scripts/weather_snapshot_reader.gd"],
	["res://scripts/weather_http_consumer.gd", "../yellowstone_atmosphere/scripts/weather_http_consumer.gd"],
	["res://shaders/yellowstone_cloud_shell.gdshader", "../yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader"],
]

func _init() -> void:
	var errors: Array = []
	for pair: Array in PAIRS:
		var canonical: String = pair[0]
		var package: String = pair[1]
		var canonical_sha: String = _sha_or_empty(canonical)
		var package_sha: String = _sha_or_empty(package)
		if canonical_sha.is_empty():
			errors.append("Canonical copy missing: " + canonical)
			continue
		if package_sha.is_empty():
			errors.append("Package copy missing: " + package)
			continue
		if canonical_sha != package_sha:
			errors.append("Drift detected between %s and %s" % [canonical, package])
	if errors.is_empty():
		print("ATMOSPHERE CANONICAL OK: ", PAIRS.size(), " pairs match.")
		quit(0)
	else:
		for message: String in errors:
			push_error(message)
		print("ATMOSPHERE CANONICAL FAIL: ", errors.size(), " drift(s). Reconcile from yellowstone_midway/ (canonical).")
		quit(1)

func _sha_or_empty(path: String) -> String:
	if path.begins_with("res://"):
		if not FileAccess.file_exists(path):
			return ""
		var ctx: HashingContext = HashingContext.new()
		if ctx.start(HashingContext.HASH_SHA256) != OK:
			return ""
		if ctx.update(FileAccess.get_file_as_bytes(path)) != OK:
			return ""
		return ctx.finish().hex_encode()
	var project_root: String = ProjectSettings.globalize_path("res://")
	var absolute: String = project_root + path if path.begins_with("../") else path
	var file: FileAccess = FileAccess.open(absolute, FileAccess.READ)
	if file == null:
		return ""
	var ctx: HashingContext = HashingContext.new()
	if ctx.start(HashingContext.HASH_SHA256) != OK:
		file.close()
		return ""
	if ctx.update(file.get_buffer(file.get_length())) != OK:
		file.close()
		return ""
	file.close()
	return ctx.finish().hex_encode()
