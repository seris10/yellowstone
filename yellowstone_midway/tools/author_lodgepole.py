"""Authored lodgepole branch geometry and paired-needle cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "yellowstone_python"))
from yellowstone_python.authoring.tree_architecture import (
    ArchitectureParameters, BECHTOLD_MODEL, PHOTO_DISPLAY, generate_architecture,
    bechtold_crown_radius_m, stem_radius_m,
)

ARCHETYPES = {
    "dense": {"height_m": 18.0, "dbh_m": 0.26, "crown_radius_m": 2.5, "crown_ratio": 0.70},
    "edge": {"height_m": 18.0, "dbh_m": 0.32, "crown_radius_m": 2.7, "crown_ratio": 0.78},
    "open": {"height_m": 16.0, "dbh_m": 0.44, "crown_radius_m": 3.15, "crown_ratio": 0.85},
    "sapling": {"height_m": 5.0, "dbh_m": 0.07, "crown_radius_m": 0.8, "crown_ratio": 0.86},
    "snag": {"height_m": 14.0, "dbh_m": 0.24, "crown_radius_m": 0.8, "crown_ratio": 0.0},
}
SOURCES = [
    {"url": "https://www.fs.usda.gov/Internet/FSE_DOCUMENTS/fseprd1178128.pdf", "publisher": "USDA Forest Service", "supports": "clear slender bole and short upper crown in dense stands; paired needles 1-3 inches"},
    {"url": "https://www.nps.gov/romo/learn/nature/conifers.htm", "publisher": "National Park Service", "supports": "tall straight narrow crowns in dense stands, broader open-site crowns; two-needle fascicles"},
    {"url": "https://polyhaven.com/license", "publisher": "Poly Haven", "supports": "CC0 asset license"},
]


class Surface:
    def __init__(self) -> None:
        self.positions = []
        self.normals = []
        self.uvs = []
        self.indices = []

    def tube(self, points: np.ndarray, radii: list[float], sides: int) -> None:
        offset = len(self.positions)
        distance = 0.0
        for index, point in enumerate(points):
            tangent = points[min(index + 1, len(points) - 1)] - points[max(index - 1, 0)]
            tangent /= np.linalg.norm(tangent)
            axis = np.array([0.0, 1.0, 0.0]) if abs(tangent[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
            across = np.cross(tangent, axis)
            across /= np.linalg.norm(across)
            depth = np.cross(tangent, across)
            if index:
                distance += np.linalg.norm(point - points[index - 1])
            for side in range(sides + 1):
                angle = side * 2 * math.pi / sides
                normal = math.cos(angle) * across + math.sin(angle) * depth
                self.positions.append(point + radii[index] * normal)
                self.normals.append(normal)
                self.uvs.append([side / sides, distance / 1.6])
            if index:
                for side in range(sides):
                    a = offset + (index - 1) * (sides + 1) + side
                    b = a + sides + 1
                    self.indices.extend([a, a + 1, b, a + 1, b + 1, b])

    def card(self, center: np.ndarray, along: np.ndarray, across: np.ndarray, length: float, width: float) -> None:
        offset = len(self.positions)
        normal = np.cross(across, along)
        normal /= np.linalg.norm(normal)
        for x, y in [(-1, 1), (1, 1), (1, -1), (-1, -1)]:
            self.positions.append(center + along * length * y * 0.5 + across * width * x * 0.5)
            self.normals.append(normal)
        self.uvs.extend([[0, 0], [1, 0], [1, 1], [0, 1]])
        self.indices.extend([offset, offset + 2, offset + 1, offset, offset + 3, offset + 2])


def needle_atlas(path: Path) -> None:
    """Draw paired five-centimeter needles on an authored shoot."""
    scale = 3
    image = Image.new("RGBA", (512 * scale, 1024 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rng = np.random.default_rng(721)
    def line(points, color, width):
        draw.line([(int(x * scale), int(y * scale)) for x, y in points], fill=color, width=width * scale, joint="curve")
    line([(256, 970), (250, 85)], (92, 85, 48, 255), 5)
    for index in range(43):
        y = 105 + index * 19
        phase = index * 2.399963
        for side in [-1, 1]:
            start = 252 + math.sin(phase) * 6
            reach = 158 + rng.uniform(-24, 24)
            rise = 97 + rng.uniform(-23, 23)
            for needle in range(2):
                tip = start + side * (reach + needle * 13)
                color = (int(67 + rng.uniform(-9, 14)), int(104 + rng.uniform(-12, 22)), int(39 + rng.uniform(-6, 12)), 255)
                line([(start, y), (start + side * reach * 0.48, y - rise * 0.6), (tip, y - rise - needle * 13)], color, 3)
                line([(start + side * 2, y), (tip, y - rise - needle * 13)], (110, 133, 59, 205), 1)
    image.resize((512, 1024), Image.Resampling.LANCZOS).save(path)


def needle_cluster_atlas(path: Path) -> None:
    """Draw five paired-needle shoots for middle-distance cards."""
    scale = 3
    image = Image.new("RGBA", (512 * scale, 1024 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rng = np.random.default_rng(925)
    for origin, lean, height in [(105, -0.12, 520), (175, -0.10, 730), (256, 0.02, 860), (329, 0.12, 700), (402, 0.18, 530)]:
        def xy(x, y):
            return (int((origin + x + lean * (950 - y)) * scale), int(y * scale))
        draw.line([xy(0, 975), xy(0, 950 - height)], fill=(93, 82, 44, 255), width=4 * scale)
        for index in range(29):
            y = 940 - index * height / 29
            for side in [-1, 1]:
                for needle in range(2):
                    reach = 62 + rng.uniform(-9, 12) + needle * 7
                    rise = 46 + rng.uniform(-6, 8) + needle * 7
                    color = (int(65 + rng.uniform(-8, 15)), int(108 + rng.uniform(-8, 24)), int(40 + rng.uniform(-5, 12)), 255)
                    draw.line([xy(0, y), xy(side * reach * 0.5, y - rise * 0.65), xy(side * reach, y - rise)], fill=color, width=3 * scale)
    image.resize((512, 1024), Image.Resampling.LANCZOS).save(path)


def build_tree(spec: dict, lod: int, seed: int) -> tuple[list[Surface], dict]:
    """Build bole, branch axes and needle shoots from a seeded architecture graph."""
    parameters = ArchitectureParameters(lower_branch_survival=.82 if spec["crown_ratio"] < .75 else .94)
    graph = generate_architecture(spec, seed, parameters)
    bole, branches, leaves = Surface(), Surface(), Surface()
    height, dbh = spec["height_m"], spec["dbh_m"]
    ys = np.unique(np.concatenate([np.linspace(0, height, [20, 10, 5][lod] + 1), [1.3]]))
    source_stem = np.array(graph["axes"][0]["points_m"])
    stem = np.column_stack([np.interp(ys,source_stem[:,1],source_stem[:,0]),ys,np.interp(ys,source_stem[:,1],source_stem[:,2])])
    radii = [stem_radius_m(height, dbh, y) for y in ys]
    bole.tube(stem, radii, [10, 6, 4][lod])
    axes = {axis["id"]: axis for axis in graph["axes"]}
    selected_primary = set()
    primary_index = 0
    for axis in graph["axes"][1:]:
        if axis["order"] == 1:
            selected = lod == 0 or primary_index % [1, 2, 3][lod] == 0
            primary_index += 1
            if selected:
                selected_primary.add(axis["id"])
        else:
            selected = lod == 0
        if not selected:
            continue
        points = np.array(axis["points_m"])
        if lod:
            points = points[[0, len(points) // 2, -1]]
        taper = np.linspace(axis["radius_base_m"], .0015 if axis["order"] == 2 else .002, len(points))
        branches.tube(points, taper.tolist(), [5 if axis["order"] == 1 else 3, 3, 3][lod])
    def spray(center, direction, length, width, roll):
        direction = np.array(direction)
        direction /= np.linalg.norm(direction)
        across = np.cross(direction, np.array([0., 1., 0.]))
        if np.linalg.norm(across) < 1e-8:
            across = np.array([1., 0., 0.])
        across /= np.linalg.norm(across)
        depth = np.cross(direction, across)
        for angle in [roll, roll + math.pi / 2]:
            cross = across * math.cos(angle) + depth * math.sin(angle)
            leaves.card(np.array(center), direction, cross, length, width)
    if lod == 0:
        for index, shoot in enumerate(graph["shoots"]):
            center = (np.array(shoot["base_m"]) + np.array(shoot["tip_m"])) * .5
            spray(center, shoot["direction"], shoot["length_m"] + .09, .16, index * 2.399963)
    elif lod == 1:
        for index, axis in enumerate(graph["axes"]):
            if axis["order"] != 1 or not axis["alive"]:
                continue
            points = np.array(axis["points_m"])
            direction = points[-1] - points[0]
            size = np.linalg.norm(direction)
            spray(points[0] + direction * .65, direction, size * .82 + .25, size * .55 + .20, index * 2.399963)
    else:
        for index, axis in enumerate(graph["axes"]):
            if axis["id"] not in selected_primary or not axis["alive"]:
                continue
            points = np.array(axis["points_m"])
            direction = points[-1] - points[0]
            size = np.linalg.norm(direction)
            for u in [.38, .72, .96]:
                center = points[0] + direction * u
                spray(center, direction, max(.35, size * .42), max(.25, size * .28), index * 2.399963)
    for point in bole.positions:
        point[1] = min(height, max(0.0, point[1]))
    bounds = np.array(bole.positions + branches.positions + leaves.positions)
    report = {**spec, "live_crown_base_m": height * (1 - spec["crown_ratio"]) if spec["crown_ratio"] else None,
              "clear_bole_fraction": 1 - spec["crown_ratio"], "bounds_m": [bounds.min(axis=0).tolist(), bounds.max(axis=0).tolist()],
              "primary_branches": len(selected_primary), "twig_branches": sum(axis["order"] == 2 for axis in graph["axes"] if lod == 0),
              "needle_cards": len(leaves.indices) // 6, "triangles": sum(len(surface.indices) // 3 for surface in [bole, branches, leaves]),
              "lod": lod, "dimension_provenance": "authored", "needle_length_m": parameters.needle_length_m,
              "needle_fascicle_count": 2, "bole_profile_m": list(zip(ys.tolist(), radii)),
              "architecture_identity": graph["identity"], "architecture_axes": len(graph["axes"]),
              "architecture_shoots": len(graph["shoots"]), "architecture_status": graph["status"]}
    return [bole, branches, leaves], report


def write_gltf(path: Path, surfaces: list[Surface], lod: int) -> int:
    """Write a glTF with separate instanced bole, branches and needle meshes."""
    document = {"asset": {"version": "2.0", "generator": "Yellowstone authored lodgepole geometry"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "Lodgepole", "children": []}], "meshes": [], "accessors": [], "bufferViews": [], "buffers": [], "images": [{"uri": "../pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg"}, {"uri": "needle_shoot.png" if lod == 0 else "needle_cluster.png"}], "textures": [{"sampler": 0, "source": 0}, {"sampler": 1, "source": 1}], "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}, {"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}], "materials": [{"name": "CC0Bark", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "baseColorFactor": [0.72, 0.72, 0.65, 1], "metallicFactor": 0, "roughnessFactor": 0.92}}, {"name": "AuthoredPairedNeedles", "doubleSided": True, "alphaMode": "MASK", "alphaCutoff": 0.32, "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}, "metallicFactor": 0, "roughnessFactor": 0.87}}]}
    binary = bytearray()
    def accessor(values, kind, component, target):
        data = np.ascontiguousarray(values, dtype="<f4" if component == 5126 else "<u4")
        binary.extend(b"\0" * (-len(binary) % 4))
        view = len(document["bufferViews"])
        document["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": data.nbytes, "target": target})
        binary.extend(data.tobytes())
        desc = {"bufferView": view, "componentType": component, "count": len(data), "type": kind}
        if kind == "VEC3":
            desc.update(min=data.min(axis=0).tolist(), max=data.max(axis=0).tolist())
        document["accessors"].append(desc)
        return len(document["accessors"]) - 1
    for index, (name, surface) in enumerate(zip(["Bole", "Branches", "NeedleCards"], surfaces)):
        if not surface.indices:
            continue
        primitive = {"attributes": {"POSITION": accessor(surface.positions, "VEC3", 5126, 34962), "NORMAL": accessor(surface.normals, "VEC3", 5126, 34962), "TEXCOORD_0": accessor(surface.uvs, "VEC2", 5126, 34962)}, "indices": accessor(surface.indices, "SCALAR", 5125, 34963), "material": 1 if index == 2 else 0}
        mesh = len(document["meshes"])
        document["meshes"].append({"name": name, "primitives": [primitive]})
        document["nodes"][0]["children"].append(len(document["nodes"]))
        document["nodes"].append({"name": name, "mesh": mesh})
    document["buffers"] = [{"uri": path.with_suffix(".bin").name, "byteLength": len(binary)}]
    path.with_suffix(".bin").write_bytes(binary)
    path.write_text(json.dumps(document, separators=(",", ":")) + "\n")
    return len(binary)



def cutout_mip_chain(path: Path, cutoff: float = .32) -> dict:
    """Export premultiplied-color mip levels with conserved alpha-test occupancy."""
    source = Image.open(path).convert("RGBA")
    pixels = np.array(source, dtype=np.float64) / 255
    target = float((pixels[:,:,3] >= cutoff).mean())
    width, height = source.size
    data = bytearray()
    levels = []
    offset = 0
    for level in range(int(math.log2(max(width,height)))+1):
        w, h = max(1,width >> level), max(1,height >> level)
        if level == 0:
            rgba = np.array(source)
        else:
            alpha = np.array(Image.fromarray(pixels[:,:,3].astype(np.float32)).resize((w,h),Image.Resampling.BOX))
            colors = []
            for channel in range(3):
                premult = pixels[:,:,channel] * pixels[:,:,3]
                average = np.array(Image.fromarray(premult.astype(np.float32)).resize((w,h),Image.Resampling.BOX))
                colors.append(np.divide(average,alpha,out=np.zeros_like(average),where=alpha>1e-9))
            count = int(round(target * w * h))
            order = np.argsort(alpha.ravel(),kind="stable")
            corrected = np.zeros(w*h,dtype=np.uint8)
            if count:
                selected = order[-count:]
                pivot = max(float(alpha.ravel()[selected].min()),1e-9)
                corrected = np.minimum(255,np.round(alpha.ravel()*(cutoff+1/255)/pivot*255)).astype(np.uint8)
                corrected[order[:-count]] = np.minimum(corrected[order[:-count]],math.ceil(cutoff*255)-1)
                corrected[selected] = np.maximum(corrected[selected],math.ceil(cutoff*255))
            rgba = np.dstack([np.uint8(np.clip(color,0,1)*255) for color in colors]+[corrected.reshape(h,w)])
        block = rgba.tobytes()
        levels.append({"level":level,"width":w,"height":h,"offset":offset,"bytes":len(block),"alpha_test_coverage":float((rgba[:,:,3]>=cutoff*255).mean())})
        data.extend(block)
        offset += len(block)
    output = path.with_suffix(".miprgba")
    output.write_bytes(data)
    return {"path":output.name,"sha256":hashlib.sha256(data).hexdigest(),"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":len(data),"width":width,"height":height,"cutoff":cutoff,"base_coverage":target,"levels":levels,"evidence_class":"authored","method":"Box average of premultiplied RGB; ranked alpha-test coverage retention; quantization error below one pixel per level"}


def export_mipmaps(output: Path, metadata: dict) -> None:
    """Bind coverage-preserving needle and impostor mip buffers to asset metadata."""
    paths = [output/"needle_shoot.png",output/"needle_cluster.png"]
    paths += sorted(output.glob("*_billboard_*.png"))
    metadata["cutout_mips"] = {path.name:cutout_mip_chain(path) for path in paths}
    metadata["billboard_mips_pending"] = False
    (output/"lodgepole_metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")

def main() -> None:
    """Author the tree archetypes and their geometry metadata."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "assets/imported/lodgepole")
    parser.add_argument("--mipmaps-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    old_metadata_path = args.output / "lodgepole_metadata.json"
    previous_metadata = json.loads(old_metadata_path.read_text()) if old_metadata_path.exists() else {}
    if args.mipmaps_only:
        if not previous_metadata:
            parser.error("mipmap export requires authored asset metadata")
        export_mipmaps(args.output,previous_metadata)
        print("LODGEPOLE_MIPMAPS",len(previous_metadata["cutout_mips"]))
        return
    billboard_inputs = sorted(args.output.glob("*_lod0.*")) + [args.output / "needle_shoot.png", ROOT / "assets/imported/pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg"]
    previous_billboard_signature = previous_metadata.get("billboard_source_sha256", hashlib.sha256(b"".join(path.read_bytes() for path in billboard_inputs if path.is_file() and path.suffix != ".import")).hexdigest())
    needle_atlas(args.output / "needle_shoot.png")
    needle_cluster_atlas(args.output / "needle_cluster.png")
    reports = []
    for index, (name, spec) in enumerate(ARCHETYPES.items()):
        for lod in range(3):
            surfaces, report = build_tree(spec, lod, 4381 + index)
            if lod == 0:
                crown = np.array(surfaces[1].positions + surfaces[2].positions)
                radial_scale = spec["crown_radius_m"] / np.linalg.norm(crown[:, [0, 2]], axis=1).max()
                lower, upper = crown[:, 1].min(), crown[:, 1].max()
                vertical_scale = spec["height_m"] * spec["crown_ratio"] / (upper - lower) if spec["crown_ratio"] else 1.0
                for surface in surfaces[1:]:
                    for vertex in surface.positions:
                        vertex[[0, 2]] *= radial_scale
                        if spec["crown_ratio"]:
                            vertex[1] = spec["height_m"] * (1 - spec["crown_ratio"]) + (vertex[1] - lower) * vertical_scale
                    scale = np.array([radial_scale, vertical_scale, radial_scale])
                    surface.normals = [normal / scale / np.linalg.norm(normal / scale) for normal in surface.normals]
                crown = np.array(surfaces[1].positions + surfaces[2].positions)
                reference = (crown.min(axis=0), crown.max(axis=0))
            else:
                crown = np.array(surfaces[1].positions + surfaces[2].positions)
                lower, upper = crown.min(axis=0), crown.max(axis=0)
                scale = (reference[1] - reference[0]) / (upper - lower)
                for surface in surfaces[1:]:
                    surface.positions = [reference[0] + (vertex - lower) * scale for vertex in surface.positions]
                    surface.normals = [normal / scale / np.linalg.norm(normal / scale) for normal in surface.normals]
                bounds = np.array([vertex for surface in surfaces for vertex in surface.positions])
                report["bounds_m"] = [bounds.min(axis=0).tolist(), bounds.max(axis=0).tolist()]
            bounds = np.array([vertex for surface in surfaces for vertex in surface.positions])
            report["bounds_m"] = [bounds.min(axis=0).tolist(), bounds.max(axis=0).tolist()]
            report["crown_bounds_m"] = [reference[0].tolist(), reference[1].tolist()]
            path = args.output / f"{name}_lod{lod}.gltf"
            report.update(archetype=name, path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name, buffer_bytes=write_gltf(path, surfaces, lod))
            reports.append(report)
    near_variants = {}
    architecture_graphs = []
    for index, (name, spec) in enumerate(ARCHETYPES.items()):
        paths = [f"{name}_lod0.gltf"]
        for variant in range(4):
            identity = 4381 + index + variant * 10007
            architecture_graphs.append({"archetype": name, "variant": variant, "graph": generate_architecture(spec, identity, ArchitectureParameters(lower_branch_survival=.82 if spec["crown_ratio"] < .75 else .94))})
            if variant == 0:
                continue
            surfaces, report = build_tree(spec, 0, identity)
            crown = np.array(surfaces[1].positions + surfaces[2].positions)
            radial_scale = spec["crown_radius_m"] / np.linalg.norm(crown[:, [0, 2]], axis=1).max()
            lower, upper = crown[:,1].min(), crown[:,1].max()
            vertical_scale = spec["height_m"] * spec["crown_ratio"] / (upper-lower) if spec["crown_ratio"] else 1.0
            for surface in surfaces[1:]:
                for vertex in surface.positions:
                    vertex[[0,2]] *= radial_scale
                    if spec["crown_ratio"]:
                        vertex[1] = spec["height_m"]*(1-spec["crown_ratio"])+(vertex[1]-lower)*vertical_scale
                scale = np.array([radial_scale,vertical_scale,radial_scale])
                surface.normals = [normal/scale/np.linalg.norm(normal/scale) for normal in surface.normals]
            filename = f"{name}_variant{variant}_lod0.gltf"
            write_gltf(args.output / filename, surfaces, 0)
            paths.append(filename)
        near_variants[name] = paths
    architecture_path = args.output / "architecture_library.json"
    architecture_path.write_text(json.dumps({"schema":"yellowstone.tree_architecture_library.v1","variants":architecture_graphs},separators=(",",":"))+"\n")
    metadata = {"schema": "yellowstone.lodgepole_assets.v1", "scientific_name": "Pinus contorta var. latifolia", "geometry_license": "Apache-2.0", "needle_texture_license": "Apache-2.0", "near_architecture_variants": 4, "bark_texture_license": "CC0-1.0", "archetypes": ARCHETYPES, "dimension_provenance": "authored", "uncertainty": "unknown", "sources": SOURCES, "lod_ranges_m": [[0, 18], [18, 65], [65, 180], [180, 3000]], "lods": reports, "display_envelope_model": BECHTOLD_MODEL, "photo_display": PHOTO_DISPLAY, "architecture_method_sources": generate_architecture(ARCHETYPES["dense"], "metadata")["sources"], "display_envelope_reference_cases": [{"dbh_m": inches * .0254, "radius_m": bechtold_crown_radius_m(inches * .0254)} for inches in [5., 10., 20., 62.2]], "limitations": ["Archetype dimensions are authored rendering assumptions, not measured allometry.", "LiDAR-derived heights remain independent; full display crowns combine retained core radii with transferred or authored envelopes.", "Fallback DBH is authored; TreeMap DBH/crown ratio are transferred. Display crown base adds an authored photo-derived constraint.", "Needle cards approximate shoots; distant LODs aggregate needles into larger cards.", "Operator-supplied Tripo candidate is inspected separately and its unspecified license is not relabeled.", "Far impostors retain the selected archetype crown ratio beyond 180 m.", "Botanical acceptance and empirical allometry are not established by topology or rendering checks."]}
    signature = hashlib.sha256(b"".join(path.read_bytes() for path in sorted(args.output.glob("*_lod*.bin")))).hexdigest()
    metadata["geometry_sha256"] = signature
    metadata["near_variant_files"] = near_variants
    metadata["architecture_parameters_by_archetype"] = {name: graph["graph"]["parameters"] for name in ARCHETYPES for graph in architecture_graphs if graph["archetype"] == name and graph["variant"] == 0}
    metadata["architecture_library_sha256"] = hashlib.sha256(architecture_path.read_bytes()).hexdigest()
    metadata["near_variation_scope"] = "Four seeded branch graphs at LOD0; middle and far use canonical topology and view variation"
    billboard_inputs = sorted(args.output.glob("*_lod0.*")) + [args.output / "needle_shoot.png", ROOT / "assets/imported/pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg"]
    billboard_signature = hashlib.sha256(b"".join(path.read_bytes() for path in billboard_inputs if path.is_file() and path.suffix != ".import")).hexdigest()
    metadata["billboard_source_sha256"] = billboard_signature
    if billboard_signature == previous_billboard_signature and previous_metadata.get("billboards"):
        metadata["billboards"] = previous_metadata["billboards"]
    export_mipmaps(args.output,metadata)
    print(json.dumps({"archetypes": len(ARCHETYPES), "lods": len(reports), "triangles": {f'{r["archetype"]}_{r["lod"]}': r["triangles"] for r in reports}}, indent=2))


if __name__ == "__main__":
    main()
