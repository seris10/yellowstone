"""Offline orthographic lodgepole impostors from authored geometry."""

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]


def pose(camera, center, azimuth: float, distance: float) -> None:
    """Aim the orthographic camera at the tree center."""
    camera.location = center + Vector((math.sin(azimuth) * distance, -math.cos(azimuth) * distance, 0.0))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    """Render four views per seeded variant and record physical plane dimensions."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, default=ROOT / "assets/imported/lodgepole")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    metadata_path = args.assets / "lodgepole_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 512
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.55, 0.62, 0.70, 1.0)
    background.inputs["Strength"].default_value = 0.75
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.sensor_fit = "HORIZONTAL"
    scene.camera = camera
    bpy.ops.object.light_add(type="AREA")
    light = bpy.context.object
    light.data.energy = 1600
    light.data.size = 9
    metadata["billboards"] = {}
    metadata["variant_billboards"] = {}
    for name in metadata["archetypes"]:
        metadata["variant_billboards"][name] = []
        for variant in range(4):
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(args.assets / metadata["near_variant_files"][name][variant]))
            objects = [obj for obj in bpy.data.objects if obj not in before]
            meshes = [obj for obj in objects if obj.type == "MESH"]
            points = [obj.matrix_world @ Vector(point) for obj in meshes for point in obj.bound_box]
            minimum = min(point.z for point in points)
            maximum = max(point.z for point in points)
            height = maximum - minimum + 0.12
            width = height * scene.render.resolution_x / scene.render.resolution_y
            center = Vector((0.0, 0.0, (maximum + minimum) / 2))
            camera.data.ortho_scale = width
            views = []
            for index in range(4):
                angle = math.pi * index / 2
                pose(camera, center, angle, 45.0)
                light.location = camera.location * 0.36 + Vector((5.0, 3.0, height * 0.65))
                light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
                filename = f"{name}_billboard_{index}.png" if variant == 0 else f"{name}_variant{variant}_billboard_{index}.png"
                scene.render.filepath = str(args.assets / filename)
                bpy.ops.render.render(write_still=True)
                views.append(filename)
            entry = {"views": views, "width_m": width, "height_m": height, "center_y_m": center.z, "azimuth_degrees": [0, 90, 180, 270], "resolution_px": [512, 1024], "lighting": "authored diffuse render for distant unshaded impostor"}
            metadata["variant_billboards"][name].append(entry)
            if variant == 0:
                metadata["billboards"][name] = entry
            for obj in objects:
                bpy.data.objects.remove(obj, do_unlink=True)
    metadata["billboard_mips_pending"] = True
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print("LODGEPOLE_IMPOSTORS", len(metadata["billboards"]), "archetypes, 80 variant images")


if __name__ == "__main__":
    main()
