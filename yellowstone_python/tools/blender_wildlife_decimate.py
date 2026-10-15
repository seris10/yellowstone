"""Blender mesh reduction with verified hard caps and staged output."""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile


def digest(path):
    """Hash a source or derivative without loading its binary container."""
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def scene_geometry(bpy):
    """Read actual triangulated world-space geometry and UV presence."""
    vertices, triangles, rows = [], [], []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        offset = len(vertices)
        vertices.extend(obj.matrix_world @ vertex.co for vertex in mesh.vertices)
        triangles.extend(tuple(offset+index for index in triangle.vertices) for triangle in mesh.loop_triangles)
        rows.append({'object': obj.name, 'triangles': len(mesh.loop_triangles), 'uv_layers': len(mesh.uv_layers), 'material_slots': len(mesh.materials)})
    if not triangles or not vertices:
        raise ValueError('Source or exported scene contains no triangulated mesh geometry')
    if any(not all(math.isfinite(value) for value in vertex) for vertex in vertices):
        raise ValueError('Mesh contains nonfinite transformed vertices')
    return vertices, triangles, rows


def image_signatures(bpy):
    """Identify decoded image pixels separately from encoded file bytes."""
    signatures = []
    for image in bpy.data.images:
        if image.type != 'IMAGE' or not image.has_data:
            continue
        values = array('f', [0.])*len(image.pixels)
        image.pixels.foreach_get(values)
        signatures.append({'size': list(image.size), 'pixels_sha256': hashlib.sha256(values.tobytes()).hexdigest()})
    return sorted(signatures, key=lambda row: (row['size'], row['pixels_sha256']))


def export_attributes(path):
    """Inspect independent serialized primitive attributes in a GLB export."""
    with Path(path).open('rb') as stream:
        magic, version, _, length, chunk = struct.unpack('<4sIIII', stream.read(20))
        if magic != b'glTF' or version != 2 or chunk != 0x4e4f534a or length > 64*1024*1024:
            raise ValueError('Unsupported exported GLB container')
        document = json.loads(stream.read(length))
    return [set(primitive['attributes']) for mesh in document.get('meshes', []) for primitive in mesh['primitives']]


def sampled_surface_error(original, reduced):
    """Measure bounded two-way vertex-to-triangle surface distance samples."""
    from mathutils.bvhtree import BVHTree
    distances = []
    for source, target in ((original, reduced), (reduced, original)):
        tree = BVHTree.FromPolygons(target[0], target[1], all_triangles=True)
        for vertex in source[0][::max(1, math.ceil(len(source[0])/4096))]:
            nearest = tree.find_nearest(vertex)
            if nearest is None or nearest[0] is None:
                raise ValueError('Exported surface has no nearest triangle')
            distances.append(float(nearest[3]))
    distances.sort()
    extent = max(max(vertex[axis] for vertex in original[0])-min(vertex[axis] for vertex in original[0]) for axis in range(3))
    if extent <= 0:
        raise ValueError('Source geometry has zero spatial extent')
    return {'samples': len(distances), 'maximum_m_or_asset_units': max(distances),
        'p95_m_or_asset_units': distances[math.ceil(.95*len(distances))-1],
        'maximum_fraction_of_source_extent': max(distances)/extent,
        'method': 'deterministic_sampled_vertex_to_triangle; not exact Hausdorff distance'}


def main(argv=None):
    """Refuse failed derivatives before replacing an accepted output file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--triangles', type=int, default=20000, help='Hard cap after export and reimport')
    parser.add_argument('--max-surface-error-fraction', type=float, default=.025)
    parser.add_argument('--texture-policy', choices=['preserve_pixels', 'allow_reencode'], default='preserve_pixels')
    args = parser.parse_args(argv)
    if args.source.resolve() == args.output.resolve():
        raise ValueError('Source and output must differ')
    if args.triangles < 100 or not math.isfinite(args.max_surface_error_fraction) or not 0 < args.max_surface_error_fraction <= .25:
        raise ValueError('Budget requires at least 100 triangles and an error fraction in (0,.25]')
    import bpy
    source_hash = digest(args.source)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.source))
    if any(obj.type == 'ARMATURE' for obj in bpy.context.scene.objects):
        raise ValueError('Reduce unskinned geometry, then transfer and review the rig against the derivative hash')
    original = scene_geometry(bpy)
    source_images = image_signatures(bpy)
    source_materials = sum(row['material_slots'] for row in original[2])
    import bmesh
    extent = max(max(vertex[axis] for vertex in original[0])-min(vertex[axis] for vertex in original[0]) for axis in range(3))
    merge_distance = 1e-8*extent
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            mesh = bmesh.new()
            mesh.from_mesh(obj.data)
            bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=merge_distance)
            mesh.to_mesh(obj.data)
            mesh.free()
    attempts = 0
    while len(scene_geometry(bpy)[1]) > args.triangles and attempts < 5:
        total = len(scene_geometry(bpy)[1])
        for obj in list(bpy.context.scene.objects):
            if obj.type != 'MESH':
                continue
            bpy.context.view_layer.objects.active = obj
            modifier = obj.modifiers.new('RuntimeCollapse', 'DECIMATE')
            modifier.decimate_type = 'COLLAPSE'
            modifier.ratio = min(.95, .97*args.triangles/total)
            modifier.use_collapse_triangulate = True
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        attempts += 1
    if len(scene_geometry(bpy)[1]) > args.triangles:
        raise ValueError('Hard triangle cap unavailable after bounded reduction attempts')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mesh-stage-', dir=args.output.parent) as directory:
        staged = Path(directory)/'candidate.glb'
        bpy.ops.export_scene.gltf(filepath=str(staged), export_format='GLB', export_apply=True, export_tangents=True)
        required = {'POSITION', 'NORMAL'} | ({'TEXCOORD_0', 'TANGENT'} if all(row['uv_layers'] for row in original[2]) else set())
        attributes = export_attributes(staged)
        if not attributes or any(not required <= values for values in attributes):
            raise ValueError('Serialized output lost required normals, UVs or tangents')
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(staged))
        reduced = scene_geometry(bpy)
        if len(reduced[1]) > args.triangles:
            raise ValueError('Reimported derivative exceeds the hard triangle cap')
        if sum(row['material_slots'] for row in reduced[2]) < source_materials:
            raise ValueError('Reimported derivative lost material slots')
        output_images = image_signatures(bpy)
        if args.texture_policy == 'preserve_pixels' and source_images != output_images:
            raise ValueError('Reimported derivative changes decoded source texture pixels')
        error = sampled_surface_error(original, reduced)
        if error['maximum_fraction_of_source_extent'] > args.max_surface_error_fraction:
            raise ValueError(f"Reduced surface error {error['maximum_fraction_of_source_extent']:.6g} exceeds {args.max_surface_error_fraction:.6g}")
        if digest(args.source) != source_hash:
            raise ValueError('Original source changed during reduction')
        report = {'schema': 'yellowstone.mesh_reduction.v2', 'blender_version': bpy.app.version_string,
            'triangle_budget': args.triangles, 'budget_kind': 'hard_cap', 'final_triangles': len(reduced[1]),
            'status': 'numerically_checked; visual_and_deformation_acceptance_unassessed',
            'source_sha256': source_hash, 'output_sha256': digest(staged), 'attempts': attempts,
            'original_meshes': original[2], 'output_meshes': reduced[2], 'surface_error': error,
            'surface_error_budget_fraction': args.max_surface_error_fraction, 'texture_policy': args.texture_policy,
            'source_image_pixels': source_images, 'output_image_pixels': output_images,
            'required_serialized_attributes': sorted(required), 'rig_review_required_for_new_identity': True}
        report['coincident_vertex_weld_distance_asset_units'] = merge_distance
        pending_report = Path(directory)/'candidate.decimation.json'
        pending_report.write_text(json.dumps(report, indent=1))
        os.replace(staged, args.output)
        os.replace(pending_report, args.output.with_suffix('.decimation.json'))
        print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
