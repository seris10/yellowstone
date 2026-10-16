#!/usr/bin/env python3
"""Bake a compact foliage-card derivative of Poly Haven Pine Tree 01 variant b."""

from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from collections import deque

BASE = Path(__file__).resolve().parent / "pine_tree_01"
SOURCE = json.loads((BASE / "pine_tree_01_source.json").read_text())


def main(source_path: str, lod: int = 0) -> None:
    raw = np.memmap(source_path, mode="r", dtype="uint8")
    if len(raw) != 948849556:
        raise ValueError("Wrong original source length; use the recorded Poly Haven binary.")

    def read_acc(index: int) -> np.ndarray:
        a = SOURCE["accessors"][index]
        v = SOURCE["bufferViews"][a["bufferView"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        dtype = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}[a["componentType"]]
        return np.ndarray((a["count"], width), dtype=dtype, buffer=raw,
                          offset=v.get("byteOffset", 0) + a.get("byteOffset", 0))

    result = {
        "asset": {"version": "2.0", "generator": "Yellowstone Midway offline asset conversion",
                  "copyright": "Pine Tree 01: Rico Cilliers, Rob Tuytel / Poly Haven, CC0. "
                               "Variant b; original woody meshes plus source-density foliage cards."},
        "scene": 0, "scenes": [{"name": "Pine b compact", "nodes": [0]}],
        "nodes": [{"name": "PineBCompact", "mesh": 0}], "meshes": [{"name": "PineBCompact", "primitives": []}],
        "accessors": [], "bufferViews": [], "buffers": [], "materials": [],
        "images": [], "textures": [], "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "extensionsUsed": ["KHR_texture_transform"],
    }
    binary = bytearray()

    def append_acc(a: np.ndarray, kind: str, component: int, target: int) -> int:
        a = np.ascontiguousarray(a)
        while len(binary) % 4:
            binary.append(0)
        view = len(result["bufferViews"])
        result["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": a.nbytes, "target": target})
        binary.extend(a.tobytes())
        desc = {"bufferView": view, "componentType": component, "count": len(a), "type": kind}
        if kind == "VEC3" and component == 5126:
            desc["min"] = a.min(axis=0).tolist()
            desc["max"] = a.max(axis=0).tolist()
        result["accessors"].append(desc)
        return len(result["accessors"]) - 1

    def primitive(positions: np.ndarray, normals: np.ndarray, uvs: np.ndarray, indices: np.ndarray, material: int) -> dict:
        return {"attributes": {"POSITION": append_acc(positions.astype("<f4"), "VEC3", 5126, 34962),
                               "NORMAL": append_acc(normals.astype("<f4"), "VEC3", 5126, 34962),
                               "TEXCOORD_0": append_acc(uvs.astype("<f4"), "VEC2", 5126, 34962)},
                "indices": append_acc(indices.reshape(-1).astype("<u4"), "SCALAR", 5125, 34963), "material": material}

    texture_map = {}

    def remap_texture(old_index: int) -> int:
        source_image = SOURCE["textures"][old_index]["source"]
        uri = SOURCE["images"][source_image]["uri"]
        if uri in texture_map:
            return texture_map[uri]
        im = copy.deepcopy(SOURCE["images"][source_image])
        result["images"].append(im)
        result["textures"].append({"sampler": 0, "source": len(result["images"]) - 1})
        i = len(result["textures"]) - 1
        texture_map[uri] = i
        return i

    def material_from_source(old: int) -> int:
        mat = copy.deepcopy(SOURCE["materials"][old])
        mat.pop("extensions", None)
        mat["doubleSided"] = False
        def walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.endswith("Texture") and isinstance(value, dict) and "index" in value:
                        value["index"] = remap_texture(value["index"])
                    else:
                        walk(value)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)
        walk(mat)
        result["materials"].append(mat)
        return len(result["materials"]) - 1

    woody_triangles = 0
    budgets = {0: None, 1: {0: 1200, 4: 2400, 3: 250}, 2: {0: 120, 4: 280, 3: 40}}[lod]
    for source_primitive in SOURCE["meshes"][1]["primitives"]:
        if source_primitive["material"] == 2 or (lod == 2 and source_primitive["material"] == 3):
            continue
        a = source_primitive["attributes"]
        indices = read_acc(source_primitive["indices"])
        positions = read_acc(a["POSITION"])
        normals = read_acc(a["NORMAL"])
        uvs = read_acc(a["TEXCOORD_0"])
        if budgets is not None:
            import fast_simplification
            _, _, collapses = fast_simplification.simplify(
                positions.astype(np.float64), indices.reshape(-1, 3).astype(np.int32),
                target_count=budgets[source_primitive["material"]], return_collapses=True)
            reduced_pos, reduced_ix, mapping = fast_simplification.replay_simplification(
                positions.astype(np.float32), indices.reshape(-1, 3).astype(np.int32), collapses)
            valid = mapping >= 0
            group_count = np.bincount(mapping[valid], minlength=len(reduced_pos)).clip(1)
            reduced_uv = np.column_stack([
                np.bincount(mapping[valid], weights=uvs[valid, j], minlength=len(reduced_pos))/group_count
                for j in range(2)])
            reduced_norm = np.column_stack([
                np.bincount(mapping[valid], weights=normals[valid, j], minlength=len(reduced_pos))/group_count
                for j in range(3)])
            reduced_norm /= np.linalg.norm(reduced_norm, axis=1, keepdims=True).clip(1e-8)
            positions, indices, normals, uvs = reduced_pos, reduced_ix, reduced_norm, reduced_uv
        woody_triangles += indices.size // 3
        result["meshes"][0]["primitives"].append(
            primitive(positions, normals, uvs, indices, material_from_source(source_primitive["material"])))

    # Density cells sample only the source tree's needle geometry.
    points = read_acc(36)[::8].astype(np.float64)
    cell = {0: 0.37, 1: 0.72, 2: 1.6}[lod]
    keys = np.floor(points / cell).astype(np.int32)
    unique, inv, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    centers = np.column_stack([np.bincount(inv, weights=points[:,j], minlength=len(unique)) for j in range(3)]) / counts[:,None]
    covs = np.empty((len(unique), 3, 3), dtype=np.float64)
    for j in range(3):
        for k in range(3):
            covs[:,j,k] = np.bincount(inv, weights=points[:,j]*points[:,k], minlength=len(unique))/counts-centers[:,j]*centers[:,k]
    _, axes = np.linalg.eigh(covs)
    keep = counts >= 6
    centers, axes, counts = centers[keep], axes[keep], counts[keep]
    positions, normals, uvs, indices = [], [], [], []
    crop_uv = [[0,0],[1,0],[1,1],[0,1]]
    for ci, (center, axis, density) in enumerate(zip(centers, axes, counts)):
        along = axis[:,2]
        radial = center.copy(); radial[1] = 0.2
        if np.dot(along, radial) < 0:
            along *= -1
        across = axis[:,1]
        depth = np.cross(along, across)
        length = min(cell * 1.97, cell * 1.24 + 0.024 * np.sqrt(density))
        width = length * 0.50
        for side in (across, depth):
            normal = np.cross(side, along)
            normal /= max(np.linalg.norm(normal), 1e-8)
            offset = len(positions)
            # V=0 is the twig tip; V=1 points to the base.
            corners = [center + along*length/2-side*width/2,
                       center + along*length/2+side*width/2,
                       center - along*length/2+side*width/2,
                       center - along*length/2-side*width/2]
            positions.extend(corners); normals.extend([normal]*4); uvs.extend(crop_uv)
            indices.extend([offset,offset+2,offset+1,offset,offset+3,offset+2])

    diffuse = Image.open(BASE/'textures/pine_tree_01_twig_diff_1k.jpg').convert('RGBA')
    alpha = Image.open(BASE/'textures/pine_tree_01_alpha_1k.png').convert('L')
    if diffuse.size != alpha.size:
        raise ValueError('Source alpha size differs from color map.')
    diffuse.putalpha(alpha)
    diffuse.save(BASE/'textures/pine_tree_01_twig_rgba_1k.png')
    # The source atlas contains opaque bleed for other UV islands. Keep only the connected twig.
    values = np.asarray(alpha)
    allowed = values > 90
    connected = np.zeros(values.shape, dtype=np.uint8)
    queue = deque([(137, 300)])
    connected[300,137] = 255
    while queue:
        x,y = queue.popleft()
        for xx,yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= xx < values.shape[1] and 0 <= yy < values.shape[0] and allowed[yy,xx] and not connected[yy,xx]:
                connected[yy,xx] = 255
                queue.append((xx,yy))
    margin = np.asarray(Image.fromarray(connected).filter(ImageFilter.MaxFilter(3))) > 0
    card_alpha = Image.fromarray(np.where(margin,values,0).astype(np.uint8))
    card = diffuse.copy(); card.putalpha(card_alpha)
    card = card.crop((32,40,230,460))
    card.save(BASE/'textures/pine_tree_01_twig_card.png')
    image_index = len(result['images'])
    result['images'].append({'mimeType':'image/png','uri':'textures/pine_tree_01_twig_card.png'})
    texture_index = len(result['textures'])
    result['textures'].append({'sampler':0,'source':image_index})
    foliage_material = {'name':'PineNeedleCards','doubleSided':True,'alphaMode':'MASK','alphaCutoff':0.4,
                        'pbrMetallicRoughness':{'baseColorTexture':{'index':texture_index},'metallicFactor':0,'roughnessFactor':0.87}}
    result['materials'].append(foliage_material)
    # Keep physical canopy bounds identical at every LOD.
    card_positions = np.array(positions)
    source_min = np.array(SOURCE['accessors'][36]['min'])
    source_max = np.array(SOURCE['accessors'][36]['max'])
    old_min = card_positions.min(axis=0)
    old_max = card_positions.max(axis=0)
    scale = (source_max-source_min)/(old_max-old_min)
    card_positions = source_min + (card_positions-old_min)*scale
    card_normals = np.array(normals)/scale
    card_normals /= np.linalg.norm(card_normals,axis=1,keepdims=True).clip(1e-8)
    result['meshes'][0]['primitives'].append(primitive(card_positions,card_normals,np.array(uvs),
                                                    np.array(indices),len(result['materials'])-1))
    stem = 'pine_b_compact' if lod == 0 else 'pine_b_lod%d' % lod
    result['nodes'][0]['name'] = stem
    result['buffers']=[{'uri':stem+'.bin','byteLength':len(binary)}]
    (BASE/(stem+'.bin')).write_bytes(binary)
    (BASE/(stem+'.gltf')).write_text(json.dumps(result,separators=(',',':')))
    report={'source':'https://polyhaven.com/a/pine_tree_01','source_variant':'b', 'source_tree_triangles':4234432,
            'lod':lod, 'woody_triangles':woody_triangles, 'woody_geometry_unchanged':lod==0, 'foliage_cards':len(centers)*2,
            'foliage_triangles':len(indices)//3,'total_triangles':woody_triangles+len(indices)//3,
            'runtime_mesh_bytes':len(binary),'source_height_m':14.794495582580566,
            'canopy_bounds_m':[source_min.tolist(),source_max.tolist()],
            'pivot':'Ground-centered; vertical Y in meters; no root transform',
            'limitations':['Pine species unspecified by creator; not certified Pinus contorta.',
                           'Foliage is a derived approximation of the original measured canopy.',
                           'LOD0 retains original woody geometry; LOD1/2 simplify it and LOD2 omits fine dead branches.']}
    (BASE/(stem+'_conversion.json')).write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
