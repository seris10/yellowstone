class_name YellowstoneReleaseData
extends RefCounted

static var active: Dictionary = {}

static func prepare(pointer_path: String = "res://data/release.json") -> Dictionary:
	if not FileAccess.file_exists(pointer_path):
		return {}
	var pointer: Variant = JSON.parse_string(FileAccess.get_file_as_string(pointer_path))
	if not pointer is Dictionary or pointer.get("schema") != "yellowstone.release_pointer.v1":
		return {}
	var id: String = str(pointer.get("release_id", ""))
	var relative: String = str(pointer.get("manifest", ""))
	if id.length() != 64 or relative != "data/releases/" + id + "/RELEASE.json":
		return {}
	var root: String = pointer_path.get_base_dir().get_base_dir()
	var manifest_path: String = root.path_join(relative)
	if not FileAccess.file_exists(manifest_path) or FileAccess.get_sha256(manifest_path) != str(pointer.get("sha256", "")):
		return {}
	var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not document is Dictionary or document.get("schema") != "yellowstone.release.v1" or document.get("release_id") != id:
		return {}
	var generation: String = manifest_path.get_base_dir()
	var artifacts: Variant = document.get("artifacts")
	if not artifacts is Dictionary:
		return {}
	var parsed: Dictionary = {}
	for record: Variant in artifacts.values():
		if not record is Dictionary:
			return {}
		if record.get("state") != "present" or not record.has("path"):
			continue
		var path: String = str(record.path)
		if path.is_absolute_path() or ".." in path.split("/"):
			return {}
		var source: String = generation.path_join(path)
		if not FileAccess.file_exists(source) or FileAccess.get_sha256(source) != str(record.get("sha256", "")):
			return {}
		if path.ends_with(".json"):
			var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(source))
			if value == null:
				return {}
			parsed[path] = value
	for required: String in ["data/ecosystem.json", "data/river_replay.json", "BUILD.json", "CHECKS.json"]:
		if not parsed.get(required) is Dictionary:
			return {}
	return {"manifest": document, "root": generation, "parsed": parsed}

static func activate(candidate: Dictionary) -> void:
	active = candidate.duplicate(true)

static func resolve_path(path: String) -> String:
	if active.is_empty() or not path.begins_with("res://"):
		return path
	var relative: String = path.trim_prefix("res://")
	var artifacts: Dictionary = active.manifest.artifacts
	if artifacts.has(relative):
		var record: Dictionary = artifacts[relative]
		return str(active.root).path_join(str(record.path)) if record.get("state") == "present" and record.has("path") else ""
	for directory: String in artifacts:
		if directory.ends_with("/") and relative.begins_with(directory):
			return ""
	return path

static func file_exists(path: String) -> bool:
	var resolved: String = resolve_path(path)
	return not resolved.is_empty() and FileAccess.file_exists(resolved)

static func get_file_as_string(path: String) -> String:
	return FileAccess.get_file_as_string(resolve_path(path)) if file_exists(path) else ""

static func get_file_as_bytes(path: String) -> PackedByteArray:
	return FileAccess.get_file_as_bytes(resolve_path(path)) if file_exists(path) else PackedByteArray()

static func get_modified_time(path: String) -> int:
	return FileAccess.get_modified_time(resolve_path(path)) if file_exists(path) else 0

static func get_sha256(path: String) -> String:
	return FileAccess.get_sha256(resolve_path(path)) if file_exists(path) else ""

static func open(path: String, mode: FileAccess.ModeFlags) -> FileAccess:
	return FileAccess.open(resolve_path(path), mode) if file_exists(path) else null

static func texture(path: String) -> Texture2D:
	if not file_exists(path):
		return null
	var image: Image = Image.load_from_file(ProjectSettings.globalize_path(resolve_path(path)))
	return ImageTexture.create_from_image(image) if image != null else null
