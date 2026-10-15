"""Authored lodgepole branch geometry and paired-needle cards."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "yellowstone_python"))
from yellowstone_python.authoring.tree_architecture import (
    ArchitectureParameters, BECHTOLD_MODEL, PHOTO_DISPLAY, generate_architecture,
    bechtold_crown_radius_m, stem_radius_m, validate_architecture,
)
from yellowstone_python.authoring.tree_library import read_library, write_library
from yellowstone_python.common.provenance import sha256_json
from yellowstone_python.common.io import sha256_file, write_json_atomic

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
        self.tubes = []

    def tube(self, points: np.ndarray, radii: list[float], sides: int, identity: str = "", parent: str | None = None) -> None:
        offset = len(self.positions)
        self.tubes.append({"identity": identity, "parent": parent, "offset": offset, "rings": len(points), "sides": sides})
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


def needle_cluster_atlas(path: Path, *, connected: bool = False) -> None:
    """Draw five paired-needle shoots for middle-distance cards."""
    scale = 3
    image = Image.new("RGBA", (512 * scale, 1024 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rng = np.random.default_rng(925)
    for origin, lean, height in [(105, -0.12, 520), (175, -0.10, 730), (256, 0.02, 860), (329, 0.12, 700), (402, 0.18, 530)]:
        def xy(x, y):
            return (int((origin + x + lean * (950 - y)) * scale), int(y * scale))
        if connected:
            draw.line([(256 * scale, 1023 * scale), xy(0, 975)], fill=(93, 82, 44, 255), width=5 * scale)
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


def build_tree(spec: dict, lod: int, seed: int, architecture: dict | None = None) -> tuple[list[Surface], dict]:
    """Build bole, branch axes and needle shoots from a seeded architecture graph."""
    parameters = ArchitectureParameters(**architecture["parameters"]) if architecture is not None else ArchitectureParameters(lower_branch_survival=.82 if spec["crown_ratio"] < .75 else .94)
    graph = copy.deepcopy(architecture) if architecture is not None else generate_architecture(spec, seed, parameters)
    validate_architecture(graph)
    if graph["dimensions_m"] != spec:
        raise ValueError("Selected graph dimensions differ from the mesh input")
    bole, branches, leaves = Surface(), Surface(), Surface()
    height, dbh = spec["height_m"], spec["dbh_m"]
    ys = np.unique(np.concatenate([np.linspace(0, height, [20, 10, 5][lod] + 1), [1.3]]))
    source_stem = np.array(graph["axes"][0]["points_m"])
    stem = np.column_stack([np.interp(ys,source_stem[:,1],source_stem[:,0]),ys,np.interp(ys,source_stem[:,1],source_stem[:,2])])
    radii = [stem_radius_m(height, dbh, y) for y in ys]
    bole.tube(stem, radii, [10, 6, 4][lod], "stem")
    axes = {axis["id"]: axis for axis in graph["axes"]}
    selected_primary = set()
    primary_index = 0
    for axis in graph["axes"][1:]:
        if axis["order"] == 1:
            selected = True
            primary_index += 1
            if selected:
                selected_primary.add(axis["id"])
        else:
            selected = lod == 0
        if not selected:
            continue
        points = np.array(axis["points_m"])
        if axis["order"] == 2 and np.allclose(points, np.linspace(points[0], points[-1], len(points)), rtol=0, atol=1e-10):
            points = points[[0, -1]]
        if lod:
            points = points.copy()
        taper = np.linspace(axis["radius_base_m"], .0015 if axis["order"] == 2 else .002, len(points))
        branches.tube(points, taper.tolist(), [5 if axis["order"] == 1 else 3, 3, 3][lod], axis["id"], axis["parent_id"])
    def spray(center, direction, length, width, roll):
        direction = np.array(direction, dtype=float)
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
            tip_scale = min(1., shoot["length_m"] / .25)
            spray(center, shoot["direction"], shoot["length_m"] + .09 * tip_scale,
                  .19 * tip_scale, index * 2.399963)
    else:
        groups = {}
        for shoot in graph["shoots"]:
            parent = axes[shoot["parent_id"]]
            identity = parent["parent_id"] if lod == 2 and parent["order"] == 2 else parent["id"]
            groups.setdefault(identity, []).append(shoot)
        for index, shoots in enumerate(groups.values()):
            points = np.array([s[k] for s in shoots for k in ("base_m", "tip_m")])
            lo, hi = points.min(axis=0), points.max(axis=0)
            center = (lo + hi) * .5
            apex_scale = min(1., max(.03, (height-center[1])/parameters.apex_taper_length_m))
            if lod == 1:
                direction = np.mean([s["direction"] for s in shoots], axis=0)
                length = np.linalg.norm(hi-lo) + .09*apex_scale
                width = max(.22*apex_scale, np.linalg.norm((hi-lo)[[0,2]]) * .65)
                spray(center, direction, length, width, index * 2.399963)
            else:
                length = max(.25*apex_scale, hi[1]-lo[1]+.12*apex_scale)
                width = max(.22*apex_scale, np.linalg.norm((hi-lo)[[0,2]])+.12*apex_scale)
                spray(center, [0,1,0], length, width, index * 2.399963)
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
              "architecture_shoots": len(graph["shoots"]), "architecture_status": graph["status"],
              "source_graph_sha256": sha256_json(graph), "render_transform": "identity_at_mesh_construction"}
    return [bole, branches, leaves], report


def render_attachment_report(surfaces: list[Surface], tolerance_m: float = 1e-6) -> dict:
    """Check connected wood surfaces from their final transformed mesh rings."""
    tubes = {}
    for surface in surfaces:
        for tube in surface.tubes:
            rings = np.asarray(surface.positions[tube["offset"]:tube["offset"]+tube["rings"]*(tube["sides"]+1)])
            rings = rings.reshape(tube["rings"], tube["sides"]+1, 3)[:, :-1]
            centers = rings.mean(axis=1)
            radii = np.linalg.norm(rings-centers[:, None, :], axis=2).max(axis=1)*math.cos(math.pi/tube["sides"])
            tubes[tube["identity"]] = {**tube, "centers": centers, "radii": radii}
    gaps = {}
    for identity, child in tubes.items():
        if child["parent"] is None:
            continue
        parent = tubes[child["parent"]]
        start, end = parent["centers"][:-1], parent["centers"][1:]
        edge = end-start
        fraction = np.clip(np.sum((child["centers"][0]-start)*edge, axis=1)/np.sum(edge*edge, axis=1), 0, 1)
        distance = np.linalg.norm(child["centers"][0]-(start+fraction[:, None]*edge), axis=1)
        radii = parent["radii"][:-1]*(1-fraction)+parent["radii"][1:]*fraction
        gaps[identity] = float(max(0., np.min(distance-radii-child["radii"][0])))
    maximum = max(gaps.values(), default=0.)
    if maximum > tolerance_m:
        raise ValueError(f"Final wood surface attachment gap {maximum:.6g} m at {max(gaps, key=gaps.get)}")
    return {"status": "numerically_checked", "maximum_gap_m": maximum, "tolerance_m": tolerance_m,
            "checked_attachments": len(gaps), "representation": "final_mesh_polygon_ring_inscribed_radius",
            "foliage_alpha_contact": "visual_review_required"}


def bind_primary_roots_to_bole(surfaces: list[Surface]) -> dict:
    """Join transformed branch root rings to the final bole centerline."""
    bole = surfaces[0]
    stem = bole.tubes[0]
    rings = np.asarray(bole.positions).reshape(stem["rings"], stem["sides"]+1, 3)[:, :-1]
    centers = rings.mean(axis=1)
    shifts = []
    for surface in surfaces[1:]:
        for tube in surface.tubes:
            if tube["parent"] != "stem":
                continue
            offset, count = tube["offset"], tube["sides"]+1
            root = np.asarray(surface.positions[offset:offset+count-1]).mean(axis=0)
            target = np.array([np.interp(root[1], centers[:, 1], centers[:, 0]),
                np.clip(root[1], centers[0, 1], centers[-1, 1]),
                np.interp(root[1], centers[:, 1], centers[:, 2])])
            shift = target-root
            for index in range(offset, offset+count):
                surface.positions[index] += shift
            shifts.append(float(np.linalg.norm(shift)))
    return {"policy": "primary_first_ring_to_final_bole_centerline", "maximum_shift_m": max(shifts, default=0.),
            "root_count": len(shifts), "source_graph": "preserved_before_render_space_repair"}


def write_gltf(path: Path, surfaces: list[Surface], lod: int, *, provenance: dict | None = None,
               bark_uri: str = "../pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg") -> int:
    """Write a glTF with separate instanced bole, branches and needle meshes."""
    document = {"asset": {"version": "2.0", "generator": "Yellowstone authored lodgepole geometry"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "Lodgepole", "children": []}], "meshes": [], "accessors": [], "bufferViews": [], "buffers": [], "images": [{"uri": "../pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg"}, {"uri": "needle_shoot.png"}], "textures": [{"sampler": 0, "source": 0}, {"sampler": 1, "source": 1}], "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}, {"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}], "materials": [{"name": "CC0Bark", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "baseColorFactor": [0.72, 0.72, 0.65, 1], "metallicFactor": 0, "roughnessFactor": 0.92}}, {"name": "AuthoredPairedNeedles", "doubleSided": True, "alphaMode": "MASK", "alphaCutoff": 0.32, "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}, "metallicFactor": 0, "roughnessFactor": 0.87}}]}
    if lod > 0:
        document["images"][1]["uri"] = "needle_cluster.png"
    binary = bytearray()
    document["images"][0]["uri"] = bark_uri
    if provenance is not None:
        document["extras"] = {"yellowstone_tree": provenance}
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


def export_selected_architecture(library_path: Path, variant_id: str | None, output: Path) -> dict:
    """Build all three representations from one selected canonical source graph."""
    library = read_library(library_path)
    selected = [variant for variant in library["variants"] if variant_id is None or variant["variant_id"] == variant_id]
    if len(selected) != 1:
        raise ValueError("Select exactly one canonical variant with --variant-id")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Selected-graph export requires an empty derivative directory")
    output.mkdir(parents=True, exist_ok=True)
    variant = selected[0]
    graph = variant["graph"]
    input_hash = sha256_file(library_path)
    needle_atlas(output / "needle_shoot.png")
    needle_cluster_atlas(output / "needle_cluster.png")
    shutil.copy2(ROOT / "assets/imported/pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg", output / "bark_diff_1k.jpg")
    provenance = {"variant_id": variant["variant_id"], "record_id": variant["record_id"],
        "input_library_sha256": input_hash, "source_graph_sha256": sha256_json(graph),
        "resolved_parameters": variant["resolved_parameters"], "render_transform": "identity",
        "status": "authored_graph_geometry_not_locally_validated"}
    reports = []
    for lod in range(3):
        surfaces, report = build_tree(graph["dimensions_m"], lod, 0, architecture=graph)
        report["final_attachment_checks"] = render_attachment_report(surfaces)
        path = output / ("selected_lod" + str(lod) + ".gltf")
        write_gltf(path, surfaces, lod, provenance=provenance, bark_uri="bark_diff_1k.jpg")
        report.update(path=path.name, gltf_sha256=sha256_file(path), geometry_sha256=sha256_file(path.with_suffix(".bin")))
        reports.append(report)
    write_library(output / "architecture_library.json", {"schema": library["schema"], "variants": selected,
        "records": [{"identity": variant["record_id"], "input_record": variant["source_record"],
                     "variant_ids": [variant["variant_id"]]}]})
    result = {**provenance, "representations": reports, "source_graph": graph,
        "post_transform_attachment_check": "final_mesh_ring_overlap_checked_after_identity_transform",
        "visual_acceptance": "unassessed", "biological_acceptance": "not_yet_accepted"}
    write_json_atomic(output / "selected_architecture.json", result, indent=1)
    return result



def _coverage_uv(side: int = 192) -> np.ndarray:
    """Return deterministic stratified UVs for offline filter calibration."""
    y, x = np.meshgrid(np.arange(side), np.arange(side), indexing="ij")
    jitter = np.random.default_rng(1643).random((side * side, 2))
    return (np.column_stack([x.ravel(), y.ravel()]) + jitter) / side


def _alpha_taps(alpha: np.ndarray, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return clamp-to-edge bilinear texels and weights at normalized UVs."""
    height, width = alpha.shape
    position = uv * np.array([width, height]) - .5
    index = np.floor(position).astype(int)
    u, v = (position - index).T
    x, y = index.T
    left, right = x.clip(0, width - 1), (x + 1).clip(0, width - 1)
    top, bottom = y.clip(0, height - 1), (y + 1).clip(0, height - 1)
    taps = np.array([alpha[top, left], alpha[top, right], alpha[bottom, left], alpha[bottom, right]])
    return taps, np.array([(1-u)*(1-v), u*(1-v), (1-u)*v, u*v])


def _sample_alpha(alpha: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Evaluate the bilinear alpha field used by the renderer."""
    taps, weights = _alpha_taps(alpha, uv)
    return (taps * weights).sum(axis=0)


def _filtered_alpha(alpha: np.ndarray, previous: np.ndarray, target: float,
                    cutoff: float, uv: np.ndarray) -> tuple[np.ndarray, dict]:
    """Fit quantized alpha against bilinear and adjacent trilinear coverage."""
    taps, weights = _alpha_taps(alpha, uv)
    def evaluate(scale):
        sampled = (np.rint(np.clip(taps * scale, 0, 1) * 255) / 255 * weights).sum(axis=0)
        coverages = [float((sampled >= cutoff).mean())]
        coverages.extend(float((previous * (1-fraction) + sampled * fraction >= cutoff).mean())
                         for fraction in (.25, .5, .75))
        return coverages
    low, high = 0., 1.
    while np.mean(evaluate(high)) < target and high < 4096:
        high *= 2
    for _ in range(22):
        middle = (low + high) * .5
        if np.mean(evaluate(middle)) < target:
            low = middle
        else:
            high = middle
    scale = min((low, high), key=lambda candidate: max(abs(value-target) for value in evaluate(candidate)))
    result = np.rint(np.clip(alpha * scale, 0, 1) * 255).astype(np.uint8)
    mode = "filtered_coverage_fit"
    if target > 0 and alpha.size == 1:
        result[:] = 255
        mode = "terminal_single_texel_conservative_visibility"
    elif target > 0 and result.max() < math.ceil(cutoff * 255):
        result.flat[int(alpha.argmax())] = math.ceil(cutoff * 255)
        mode = "subpixel_single_survivor"
    sampled = _sample_alpha(result / 255, uv)
    return result, {"alpha_scale": scale, "calibration_mode": mode,
        "bilinear_coverage": float((sampled >= cutoff).mean()),
        "trilinear_coverage_from_previous": [float((previous*(1-fraction)+sampled*fraction >= cutoff).mean())
                                              for fraction in (.25, .5, .75)]}


def cutout_mip_chain(path: Path, cutoff: float = .32) -> dict:
    """Export premultiplied-color mips calibrated after bilinear/trilinear filtering."""
    source = Image.open(path).convert("RGBA")
    pixels = np.array(source, dtype=np.float64) / 255
    rgb = pixels[:, :, :3]
    linear_rgb = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    if not 0 < cutoff < 1:
        raise ValueError("Alpha cutoff must lie strictly between zero and one")
    uv = _coverage_uv()
    previous = _sample_alpha(pixels[:, :, 3], uv)
    target = float((previous >= cutoff).mean())
    point_target = float((pixels[:, :, 3] >= cutoff).mean())
    width, height = source.size
    data = bytearray()
    levels = []
    offset = 0
    for level in range(int(math.log2(max(width, height))) + 1):
        w, h = max(1, width >> level), max(1, height >> level)
        if level == 0:
            rgba = np.array(source)
            calibration = {"alpha_scale": 1., "calibration_mode": "unaltered_source",
                           "bilinear_coverage": target, "trilinear_coverage_from_previous": []}
        else:
            alpha = np.array(Image.fromarray(pixels[:, :, 3].astype(np.float32)).resize((w, h), Image.Resampling.BOX))
            colors = []
            for channel in range(3):
                premult = linear_rgb[:, :, channel] * pixels[:, :, 3]
                average = np.array(Image.fromarray(premult.astype(np.float32)).resize((w, h), Image.Resampling.BOX))
                linear = np.divide(average, alpha, out=np.zeros_like(average), where=alpha > 1e-9)
                colors.append(np.where(linear <= .0031308, linear * 12.92, 1.055 * np.maximum(linear, 0) ** (1/2.4) - .055))
            corrected, calibration = _filtered_alpha(alpha, previous, target, cutoff, uv)
            rgba = np.dstack([np.uint8(np.clip(color, 0, 1) * 255) for color in colors] + [corrected])
        previous = _sample_alpha(rgba[:, :, 3] / 255, uv)
        block = rgba.tobytes()
        levels.append({"level": level, "width": w, "height": h, "offset": offset, "bytes": len(block),
            "alpha_test_coverage": float((rgba[:, :, 3] >= cutoff * 255).mean()), **calibration})
        data.extend(block)
        offset += len(block)
    output = path.with_suffix(".miprgba")
    output.write_bytes(data)
    return {"path": output.name, "sha256": hashlib.sha256(data).hexdigest(),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": len(data),
        "width": width, "height": height, "cutoff": cutoff, "base_coverage": point_target,
        "filtered_coverage_target": target, "calibration_samples": len(uv),
        "trilinear_fractions": [.25, .5, .75], "filter_address_mode": "clamp_to_edge",
        "levels": levels, "evidence_class": "authored", "color_filter_space": "linear_sRGB",
        "method": "Linear-light premultiplied RGB box filter; quantized alpha bisection against stratified bilinear and adjacent trilinear coverage",
        "method_source": "https://www.ludicon.com/castano/blog/articles/computing-alpha-mipmaps/",
        "limitations": ["Finite UV samples approximate filtered coverage; anisotropic projected geometry requires native checks.",
                        "Very small levels cannot reproduce every spatial coverage; a nonempty 1x1 source remains visible conservatively."]}


def export_mipmaps(output: Path, metadata: dict) -> None:
    """Bind coverage-preserving needle and impostor mip buffers to asset metadata."""
    paths = [output/"needle_shoot.png",output/"needle_cluster.png"]
    if (output / "needle_supported.png").is_file():
        paths.append(output / "needle_supported.png")
    paths += sorted(output.glob("*_billboard_*.png"))
    metadata["cutout_mips"] = {path.name:cutout_mip_chain(path) for path in paths}
    metadata["billboard_mips_pending"] = False
    (output/"lodgepole_metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")

def main() -> None:
    """Author the tree archetypes and their geometry metadata."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "assets/imported/lodgepole")
    parser.add_argument("--mipmaps-only", action="store_true")
    parser.add_argument("--supported-canopy-only", action="store_true")
    parser.add_argument("--architecture-library", type=Path)
    parser.add_argument("--variant-id", help="Canonical variant identity selected for the mesh build")
    args = parser.parse_args()
    if args.architecture_library:
        if args.mipmaps_only:
            parser.error("Selected-graph export and mipmap-only mode are separate operations")
        try:
            result = export_selected_architecture(args.architecture_library, args.variant_id, args.output)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps({"variant_id": result["variant_id"], "representations": len(result["representations"])}))
        return
    if args.variant_id:
        parser.error("--variant-id requires --architecture-library")
    args.output.mkdir(parents=True, exist_ok=True)
    old_metadata_path = args.output / "lodgepole_metadata.json"
    previous_metadata = json.loads(old_metadata_path.read_text()) if old_metadata_path.exists() else {}
    if args.supported_canopy_only:
        if not previous_metadata:
            parser.error("supported canopy export requires authored asset metadata")
        needle_cluster_atlas(args.output / "needle_supported.png", connected=True)
        previous_metadata.setdefault("cutout_mips", {})["needle_supported.png"] = cutout_mip_chain(args.output / "needle_supported.png")
        old_metadata_path.write_text(json.dumps(previous_metadata, indent=2) + "\n")
        return
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
    needle_cluster_atlas(args.output / "needle_supported.png", connected=True)
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
                scale = np.array([radial_scale, vertical_scale, radial_scale])
                translation = np.array([0., spec["height_m"]*(1-spec["crown_ratio"])-lower*vertical_scale if spec["crown_ratio"] else 0., 0.])
                for surface in surfaces[1:]:
                    surface.positions = [vertex*scale+translation for vertex in surface.positions]
                    surface.normals = [normal/scale/np.linalg.norm(normal/scale) for normal in surface.normals]
            for surface in surfaces[1:]:
                for vertex in surface.positions:
                    vertex[1] = min(spec["height_m"], vertex[1])
            bounds = np.array([vertex for surface in surfaces for vertex in surface.positions])
            report["bounds_m"] = [bounds.min(axis=0).tolist(), bounds.max(axis=0).tolist()]
            report["crown_bounds_m"] = [reference[0].tolist(), reference[1].tolist()]
            report["render_transform"] = {"scope": "branches_and_cards", "scale": [radial_scale, vertical_scale, radial_scale],
                "translation_y_m": spec["height_m"]*(1-spec["crown_ratio"])-lower*vertical_scale if spec["crown_ratio"] else 0.}
            report["primary_attachment_repair"] = bind_primary_roots_to_bole(surfaces)
            report["final_attachment_checks"] = render_attachment_report(surfaces)
            path = args.output / f"{name}_lod{lod}.gltf"
            report.update(archetype=name, path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name, buffer_bytes=write_gltf(path, surfaces, lod))
            reports.append(report)
    near_variants = {}
    architecture_lod_files = {}
    variant_attachment_reports = []
    architecture_graphs = []
    for index, (name, spec) in enumerate(ARCHETYPES.items()):
        paths = [f"{name}_lod0.gltf"]
        lod_files = [[f"{name}_lod{level}.gltf" for level in range(3)]]
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
            primary_repair = bind_primary_roots_to_bole(surfaces)
            variant_attachment_reports.append({"archetype": name, "variant": variant, "lod": 0,
                "source_graph_sha256": report["source_graph_sha256"],
                "primary_attachment_repair": primary_repair,
                "checks": render_attachment_report(surfaces), "render_transform": {
                    "scope": "branches_and_cards", "scale": [radial_scale, vertical_scale, radial_scale],
                    "translation_y_m": spec["height_m"]*(1-spec["crown_ratio"])-lower*vertical_scale if spec["crown_ratio"] else 0.}})
            write_gltf(args.output / filename, surfaces, 0)
            paths.append(filename)
            reference = (np.asarray(surfaces[1].positions+surfaces[2].positions).min(axis=0),
                         np.asarray(surfaces[1].positions+surfaces[2].positions).max(axis=0))
            selected_files = [filename]
            for level in (1, 2):
                lod_surfaces, lod_report = build_tree(spec, level, identity)
                scale = np.array([radial_scale, vertical_scale, radial_scale])
                translation = np.array([0., spec["height_m"]*(1-spec["crown_ratio"])-lower*vertical_scale if spec["crown_ratio"] else 0., 0.])
                for surface in lod_surfaces[1:]:
                    surface.positions = [point*scale+translation for point in surface.positions]
                    surface.normals = [normal/scale/np.linalg.norm(normal/scale) for normal in surface.normals]
                for surface in lod_surfaces[1:]:
                    for vertex in surface.positions:
                        vertex[1] = min(spec["height_m"], vertex[1])
                lod_filename = f"{name}_variant{variant}_lod{level}.gltf"
                selected_files.append(lod_filename)
                primary_repair = bind_primary_roots_to_bole(lod_surfaces)
                write_gltf(args.output/lod_filename, lod_surfaces, level)
                variant_attachment_reports.append({"archetype": name, "variant": variant, "lod": level,
                    "source_graph_sha256": lod_report["source_graph_sha256"],
                    "primary_attachment_repair": primary_repair,
                    "checks": render_attachment_report(lod_surfaces),
                    "render_transform": {"scope": "branches_and_cards", "scale": scale.tolist(),
                        "translation_m": translation.tolist()}})
            lod_files.append(selected_files)
        near_variants[name] = paths
        architecture_lod_files[name] = lod_files
    architecture_path = args.output / "architecture_library.json"
    write_library(architecture_path, {"schema":"yellowstone.tree_architecture_library.v1","variants":architecture_graphs})
    metadata = {"schema": "yellowstone.lodgepole_assets.v1", "scientific_name": "Pinus contorta var. latifolia", "geometry_license": "Apache-2.0", "needle_texture_license": "Apache-2.0", "near_architecture_variants": 4, "bark_texture_license": "CC0-1.0", "archetypes": ARCHETYPES, "dimension_provenance": "authored", "uncertainty": "unknown", "sources": SOURCES, "lod_ranges_m": [[0, 18], [18, 65], [65, 180], [180, 3000]], "lods": reports, "display_envelope_model": BECHTOLD_MODEL, "photo_display": PHOTO_DISPLAY, "architecture_method_sources": generate_architecture(ARCHETYPES["dense"], "metadata")["sources"], "display_envelope_reference_cases": [{"dbh_m": inches * .0254, "radius_m": bechtold_crown_radius_m(inches * .0254)} for inches in [5., 10., 20., 62.2]], "limitations": ["Archetype dimensions are authored rendering assumptions, not measured allometry.", "LiDAR-derived heights remain independent; full display crowns combine retained core radii with transferred or authored envelopes.", "Fallback DBH is authored; TreeMap DBH/crown ratio are transferred. Display crown base adds an authored photo-derived constraint.", "Needle cards approximate shoots; middle LODs aggregate attached shoots into bounded leafy sprays and reduce wood tessellation.", "Operator-supplied Tripo candidate is inspected separately and its unspecified license is not relabeled.", "Far impostors retain the selected archetype crown ratio beyond 180 m.", "Botanical acceptance and empirical allometry are not established by topology or rendering checks."]}
    signature = hashlib.sha256(b"".join(path.read_bytes() for path in sorted(args.output.glob("*_lod*.bin")))).hexdigest()
    metadata["geometry_sha256"] = signature
    metadata["near_variant_files"] = near_variants
    metadata["architecture_lod_files"] = architecture_lod_files
    metadata["variant_attachment_reports"] = variant_attachment_reports
    metadata["architecture_parameters_by_archetype"] = {name: graph["graph"]["parameters"] for name in ARCHETYPES for graph in architecture_graphs if graph["archetype"] == name and graph["variant"] == 0}
    metadata["architecture_library_sha256"] = hashlib.sha256(architecture_path.read_bytes()).hexdigest()
    metadata["near_variation_scope"] = "Each variant retains its seeded source graph through LOD0/1/2; far uses variant-specific four-direction impostors with retained envelope traits"
    billboard_inputs = sorted(args.output.glob("*_lod0.*")) + [args.output / "needle_shoot.png", ROOT / "assets/imported/pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg"]
    billboard_signature = hashlib.sha256(b"".join(path.read_bytes() for path in billboard_inputs if path.is_file() and path.suffix != ".import")).hexdigest()
    metadata["billboard_source_sha256"] = billboard_signature
    if billboard_signature == previous_billboard_signature and previous_metadata.get("billboards"):
        metadata["billboards"] = previous_metadata["billboards"]
        metadata["variant_billboards"] = previous_metadata.get("variant_billboards", {})
    export_mipmaps(args.output,metadata)
    print(json.dumps({"archetypes": len(ARCHETYPES), "lods": len(reports), "triangles": {f'{r["archetype"]}_{r["lod"]}': r["triangles"] for r in reports}}, indent=2))


if __name__ == "__main__":
    main()
