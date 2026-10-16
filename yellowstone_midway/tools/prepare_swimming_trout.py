"""Prepare rigged trout assets with reduced meshes and authored species colors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    import bpy

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    import sys
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("The source contains no mesh")
    source_count = sum(len(obj.data.vertices) for obj in meshes)
    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        modifier = obj.modifiers.new("mesh_budget", "DECIMATE")
        modifier.ratio = min(1.0, 2000 / source_count)
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        obj.select_set(False)
    for image in bpy.data.images:
        if image.size[0] > 1024 or image.size[1] > 1024:
            ratio = 1024 / max(image.size)
            image.scale(max(1, round(image.size[0] * ratio)), max(1, round(image.size[1] * ratio)))
    args.out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for species, color in [("brown_trout", (0.58, 0.43, 0.22, 1.0)), ("rainbow_trout", (0.40, 0.57, 0.52, 1.0))]:
        for obj in meshes:
            for material in obj.data.materials:
                material.use_nodes = True
                nodes = material.node_tree.nodes
                shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
                for link in list(material.node_tree.links):
                    if link.to_socket == shader.inputs["Base Color"]:
                        material.node_tree.links.remove(link)
                image = bpy.data.images.new(species + "_authored_skin", width=256, height=256)
                pixels = []
                for y in range(256):
                    for x in range(256):
                        spot = ((x * 31 + y * 17) % 137 < 5)
                        stripe = species == "rainbow_trout" and abs(y - 128) < 13
                        rgba = (0.55, 0.29, 0.33, 1.0) if stripe else color
                        pixels.extend(tuple(value * (0.25 if spot else 1.0) for value in rgba[:3]) + (1.0,))
                image.pixels = pixels
                image.pack()
                texture = nodes.new("ShaderNodeTexImage")
                texture.image = image
                material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
        path = args.out / (species + "_swim.glb")
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", export_animations=True, export_animation_mode="ACTIONS", export_nla_strips=True, export_materials="EXPORT", export_image_format="AUTO")
        counts[species] = sum(len(obj.data.vertices) for obj in meshes)
    (args.out / "asset_budget.json").write_text(json.dumps({"source_vertices": source_count, "vertices": counts, "texture_max_px": 1024, "texture_status": "authored illustrative species colors", "geometry_source": args.source.name}, indent=2) + "\n")


if __name__ == "__main__":
    main()
