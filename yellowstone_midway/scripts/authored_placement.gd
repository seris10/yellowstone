@tool
class_name MidwayAuthoredPlacement
extends Node3D
## Add this node in handcrafted_details.tscn, choose a PackedScene, and position it normally. Transform is authored scene data.
@export var stable_id: String = "detail_001"
@export var asset: PackedScene:
	set(value):
		asset=value
		if is_inside_tree():
			refresh()
@export_enum("forest", "meadow", "riparian", "thermal_margin", "infrastructure") var habitat := "forest"
@export_multiline var author_note: String = ""
var preview: Node3D

func _ready() -> void:
	refresh()

func refresh() -> void:
	if is_instance_valid(preview):
		preview.queue_free()
		preview = null
	if asset == null:
		return
	preview = asset.instantiate() as Node3D
	if preview != null:
		preview.name = "AssetPreview"
		add_child(preview)
		# Ownership stays with this authored wrapper.
