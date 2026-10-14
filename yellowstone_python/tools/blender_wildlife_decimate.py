"""Blender wildlife mesh reduction with source preservation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    """Reduce an imported asset to a declared triangle budget."""
    import bpy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--triangles", type=int, default=20000)
    args = parser.parse_args(argv)
    if args.source.resolve() == args.output.resolve():
        raise ValueError("Source and output must differ")
    if args.triangles < 100:
        raise ValueError("Triangle budget must be at least 100")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(args.source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    total = sum(len(obj.data.polygons) for obj in meshes)
    rows = []
    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        initial = len(obj.data.polygons)
        modifier = obj.modifiers.new("RuntimeCollapse", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = min(1, args.triangles / total)
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        rows.append({"object": obj.name, "initial_triangles": initial,
            "final_triangles": len(obj.data.polygons), "uv_layers": len(obj.data.uv_layers)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(args.output), export_format="GLB", export_apply=True, export_tangents=True)
    args.output.with_suffix(".decimation.json").write_text(json.dumps({
        "blender_version": bpy.app.version_string, "triangle_budget": args.triangles,
        "status": "authored", "method": "quadric_collapse_existing_UV_data",
        "source_file": args.source.name, "meshes": rows}, indent=2))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
