"""Authored forest-floor display records bounded by observed canopy and mapped exclusions."""
from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import random

import numpy as np

from yellowstone_python.common.checks import finite, fraction, nonnegative, positive, positive_int
from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic

GUILDS = {
    "grouse_whortleberry": {"scientific_name": "Vaccinium scoparium", "source": "https://research.fs.usda.gov/feis/species-reviews/vacsco"},
    "elk_sedge": {"scientific_name": "Carex geyeri", "source": "https://research.fs.usda.gov/feis/species-reviews/cargey"},
    "pinegrass": {"scientific_name": "Calamagrostis rubescens", "source": "https://research.fs.usda.gov/feis/species-reviews/calrub"},
    "kinnikinnick": {"scientific_name": "Arctostaphylos uva-ursi", "source": "https://research.fs.usda.gov/feis/species-reviews/arcuva"},
}
DEFAULTS = {"seed": 54107, "candidate_spacing_m": 2.5,
            "moderate_cover_low": .15, "moderate_cover_peak": .45, "moderate_cover_high": .75,
            "minimum_valid_fraction": .95, "floor_slope_max_deg": 38.,
            "thermal_band_inner_m": 3., "thermal_band_outer_m": 30.,
            "snag_display_probability": .6, "log_display_probability": .09,
            "thermal_log_display_probability": .24,
            "understory_display_probability": .8,
            "litter_display_probability": .82, "max_litter_patches": 24000,
            "maximum_log_gap_m": .24, "maximum_floor_plane_error_m": .008,
            "max_understory_cards": 18000, "max_snags": 64, "max_logs": 1600}


def authoring_settings(overrides=None):
    """Validate explicit authored display choices without assigning a field density class."""
    options = dict(DEFAULTS)
    if set(overrides or {}) - set(options):
        raise ValueError("unknown forest-floor authoring setting")
    options.update(overrides or {})
    for name in ["seed", "max_understory_cards", "max_snags", "max_logs", "max_litter_patches"]:
        options[name] = positive_int(name, options[name])
    for name in ["candidate_spacing_m", "floor_slope_max_deg", "thermal_band_inner_m", "thermal_band_outer_m", "maximum_log_gap_m", "maximum_floor_plane_error_m"]:
        options[name] = positive(name, options[name])
    for name in ["moderate_cover_low", "moderate_cover_peak", "moderate_cover_high", "minimum_valid_fraction",
                 "snag_display_probability", "log_display_probability", "thermal_log_display_probability", "understory_display_probability", "litter_display_probability"]:
        options[name] = fraction(name, options[name])
    if not options["moderate_cover_low"] < options["moderate_cover_peak"] < options["moderate_cover_high"]:
        raise ValueError("moderate canopy cover bounds must enclose their peak")
    if options["thermal_band_outer_m"] <= options["thermal_band_inner_m"]:
        raise ValueError("thermal display band must have positive width")
    return options


def understory_weight(canopy_cover, options=None):
    """Return the authored triangular response to moderate observed canopy cover."""
    settings = authoring_settings(options)
    cover = fraction("canopy_cover", canopy_cover)
    low, peak, high = (settings[k] for k in ["moderate_cover_low", "moderate_cover_peak", "moderate_cover_high"])
    if cover <= low or cover >= high:
        return 0.
    return (cover - low) / (peak - low) if cover <= peak else (high - cover) / (high - peak)


def thermal_band_weight(distance_m, options=None):
    """Return an authored forest-side proximity proxy outside the mapped hot apron."""
    settings = authoring_settings(options)
    distance = nonnegative("apron_distance_m", distance_m)
    inner, outer = settings["thermal_band_inner_m"], settings["thermal_band_outer_m"]
    return (outer - distance) / (outer - inner) if inner <= distance <= outer else 0.


def rendered_terrain_fns(master_sample, core_height, core_microrelief, grid, *, decimation=2):
    """Sample the rendered core triangle surface, falling back to the master outside it."""
    decimation = positive_int("core_mesh_decimation", decimation)
    nx, nz = positive_int("core_nx", grid["nx"]), positive_int("core_nz", grid["nz"])
    spacing = positive("core_cell_m", grid["cell_m"])
    x0, z0 = finite("core_x_min", grid["x_min_m"]), finite("core_z_min", grid["z_min_m"])
    x1, z1 = finite("core_x_max", grid["x_max_m"]), finite("core_z_max", grid["z_max_m"])
    if nx < 2 or nz < 2 or (nx - 1) % decimation or (nz - 1) % decimation:
        raise ValueError("core vertex dimensions must contain complete decimated cells")
    if not math.isclose(x1 - x0, (nx - 1) * spacing) or not math.isclose(z1 - z0, (nz - 1) * spacing):
        raise ValueError("core grid extent differs from its vertex dimensions")
    arrays = [np.asarray(value, dtype=np.float32) for value in (core_height, core_microrelief)]
    if any(value.shape != (nz, nx) or not np.isfinite(value).all() for value in arrays):
        raise ValueError("core terrain layers require finite matching vertex arrays")
    surface = (arrays[0] + arrays[1])[::decimation, ::decimation].astype(np.float64)
    step = spacing * decimation
    rows, columns = surface.shape

    def sample(x, z):
        if not (x0 <= x <= x1 and z0 <= z <= z1):
            return master_sample(x, z)
        gx, gz = (x - x0) / step, (z - z0) / step
        i, j = min(columns - 2, int(gx)), min(rows - 2, int(gz))
        fx, fz = gx - i, gz - j
        a, b, c, d = surface[j, i], surface[j, i + 1], surface[j + 1, i], surface[j + 1, i + 1]
        return float(a + fx * (b - a) + fz * (c - a) if fx + fz <= 1
                     else d + (1 - fx) * (c - d) + (1 - fz) * (b - d))

    def slope(x, z):
        delta = .5
        dx = (sample(x + delta, z) - sample(x - delta, z)) / (2 * delta)
        dz = (sample(x, z + delta) - sample(x, z - delta)) / (2 * delta)
        return math.degrees(math.atan(math.hypot(dx, dz)))

    return sample, slope


class FloorContext:
    """Observed support, real terrain and protected footprints for independent floor records."""

    def __init__(self, coverage, masks, supported, apron_distance, clearance, terrain,
                 slope, heat_sampler, apron_heat, *, spacing=.5):
        if coverage.get("schema") != "yellowstone.canopy_coverage.v1" or coverage.get("status") != "derived_not_field_validated":
            raise ValueError("forest-floor support requires derived, unvalidated canopy coverage")
        self.coverage = coverage
        self.extent = coverage["extent_m"]
        self.cell_size = positive("canopy_cell_size", coverage["cell_size_m"])
        self.spacing = positive("support_spacing", spacing)
        self.cells = {(c["ix"], c["iz"]): c for c in coverage["cells"]}
        self.masks, self.supported = masks, supported
        self.apron_distance, self.clearance = apron_distance, clearance
        self.terrain, self.slope, self.heat_sampler = terrain, slope, heat_sampler
        self.apron_heat = nonnegative("apron_heat", apron_heat)

    def sample(self, x, z):
        """Return supported local context or the explicit exclusion reason."""
        x, z = finite("floor_x", x), finite("floor_z", z)
        x0, z0, x1, z1 = self.extent
        if not (x0 <= x < x1 and z0 <= z < z1):
            return None, "outside_canopy_window"
        ix, iz = math.floor((x - x0) / self.spacing), math.floor((z - z0) / self.spacing)
        if not self.supported[iz, ix]:
            return None, "missing_canopy_support"
        reason = next((name for name, mask in self.masks.items() if mask[iz, ix]), None)
        if reason:
            return None, reason
        cell = self.cells.get((math.floor((x - x0) / self.cell_size), math.floor((z - z0) / self.cell_size)))
        if cell is None or cell.get("canopy_cover_fraction") is None:
            return None, "missing_canopy_cell"
        return {"canopy_cell_id": cell["id"], "canopy_cover_fraction": fraction("cover", cell["canopy_cover_fraction"]),
                "canopy_valid_fraction": fraction("valid", cell["valid_fraction"]),
                "apron_distance_m": float(self.apron_distance[iz, ix]),
                "protected_clearance_m": float(self.clearance[iz, ix]),
                "terrain_y_m": finite("terrain_y", self.terrain(x, z)),
                "slope_deg": nonnegative("slope", self.slope(x, z)),
                "model_ground_heat_w_m2": nonnegative("ground_heat", self.heat_sampler(x, z)),
                "source_apron_heat_w_m2": self.apron_heat}, None


def floor_plane(context, x, z, radius):
    """Return a sampled terrain normal and maximum local planar residual in m."""
    delta = max(.25, radius)
    center = context.terrain(x, z)
    dx = (context.terrain(x + delta, z) - context.terrain(x - delta, z)) / (2 * delta)
    dz = (context.terrain(x, z + delta) - context.terrain(x, z - delta)) / (2 * delta)
    normal = np.array([-dx, 1., -dz])
    normal /= np.linalg.norm(normal)
    residual = max(abs(context.terrain(x + r * math.cos(a), z + r * math.sin(a))
                       - center - r * (dx * math.cos(a) + dz * math.sin(a)))
                   for r in [radius * .5, radius]
                   for a in np.linspace(0, math.tau, 16, endpoint=False))
    return normal.tolist(), float(residual)


def log_contacts(context, x, z, yaw, diameter, length, maximum_gap):
    """Fit a straight log above sampled terrain with bounded under-log clearance."""
    along = np.linspace(-length / 2, length / 2, max(9, math.ceil(length / .25) + 1))
    points = [(x + math.sin(yaw) * t, z + math.cos(yaw) * t) for t in along]
    if any(context.sample(a, b)[1] is not None for a, b in points):
        return None
    heights = np.array([context.terrain(a, b) for a, b in points])
    grade, intercept = np.polyfit(along, heights, 1)
    base = intercept + grade * along
    lift = float(np.max(heights - base))
    gaps = base + lift - heights
    if float(np.max(gaps)) > maximum_gap:
        return None
    radius_vertical = diameter / (2 * math.sqrt(1 + grade * grade))
    endpoints = [[a, float(h), b] for (a, b), h in zip([points[0], points[-1]], [heights[0], heights[-1]])]
    axis = [[a, float(h + lift + radius_vertical), b]
            for (a, b), h in zip([points[0], points[-1]], [base[0], base[-1]])]
    return {"end_positions": endpoints, "axis_end_positions": axis,
            "ground_profile_m": [[float(t), float(h)] for t, h in zip(along, heights)],
            "contact_clearance_m": gaps.tolist(), "contact_sample_spacing_m": float(along[1] - along[0])}


def author_records(context, settings=None):
    """Generate bounded display records without modifying observed tree or placement layers."""
    options = authoring_settings(settings)
    x0, z0, x1, z1 = context.extent
    step = options["candidate_spacing_m"]
    columns, rows = math.ceil((x1 - x0) / step), math.ceil((z1 - z0) / step)
    candidates = [(i, j) for j in range(rows) for i in range(columns)]
    random.Random(f"{options['seed']}:order").shuffle(candidates)
    records, rejected, counts, fallbacks = [], Counter(), Counter(), Counter()
    for i, j in candidates:
        rng = random.Random(f"{options['seed']}:{i}:{j}")
        x = x0 + (i + .5 + (rng.random() - .5) * .6) * step
        z = z0 + (j + .5 + (rng.random() - .5) * .6) * step
        support, reason = context.sample(x, z)
        if reason:
            rejected[reason] += 1
            continue
        if support["canopy_valid_fraction"] < options["minimum_valid_fraction"]:
            rejected["insufficient_canopy_support"] += 1
            continue
        if support["slope_deg"] > options["floor_slope_max_deg"]:
            rejected["authored_bare_scarp_slope"] += 1
            continue
        cover = support["canopy_cover_fraction"]
        if cover < options["moderate_cover_low"]:
            continue
        thermal = (thermal_band_weight(support["apron_distance_m"], options)
                   if context.apron_heat > support["model_ground_heat_w_m2"] else 0.)
        support = dict(support, thermal_band=thermal > 0, thermal_exposure_proxy=thermal,
                       proxy_evidence_class="authored", quantitative_uncertainty="unknown")
        choices = []
        if thermal > 0 and rng.random() < options["snag_display_probability"] * thermal:
            diameter, height = rng.uniform(.1, .3), rng.uniform(3, 9)
            choices.append(("snag", [diameter, height, diameter], None))
        log_probability = options["log_display_probability"] * cover ** 2 + options["thermal_log_display_probability"] * thermal
        if rng.random() < log_probability:
            diameter, length = rng.uniform(.12, .34), rng.uniform(2.5, 9)
            choices.append(("log", [diameter, diameter, length], None))
        if rng.random() < options["understory_display_probability"] * understory_weight(cover, options):
            guild = rng.choice(sorted(GUILDS))
            width, height = rng.uniform(.65, 1.35), rng.uniform(.16, .48)
            choices.append(("understory_card", [width, height, width], guild))
        if rng.random() < options["litter_display_probability"] * cover:
            width = rng.uniform(2.0, 3.0)
            choices.append(("litter", [width, width * .025, width], None))
        for kind, size, guild in choices:
            cap = options[{"snag": "max_snags", "log": "max_logs", "understory_card": "max_understory_cards", "litter": "max_litter_patches"}[kind]]
            if counts[kind] >= cap:
                rejected[f"{kind}_display_budget"] += 1
                continue
            radius = size[2] / 2 if kind == "log" else (size[1] * .1 if kind == "snag" else size[0] / 2)
            compact_litter = False
            if kind == "litter":
                _, preferred_error = floor_plane(context, x, z, radius)
                if preferred_error > options["maximum_floor_plane_error_m"] or support["protected_clearance_m"] < radius + context.spacing:
                    width = 1.1 + .8 * (size[0] - 2.)
                    size = [width, width * .025, width]
                    radius = width / 2
                    compact_litter = True
            if support["protected_clearance_m"] < radius + context.spacing:
                rejected[f"{kind}_footprint_clearance"] += 1
                continue
            yaw = rng.random() * math.tau
            contacts = None
            if kind == "log":
                contacts = log_contacts(context, x, z, yaw, size[0], size[2], options["maximum_log_gap_m"])
                if contacts is None:
                    rejected["log_terrain_or_profile_exclusion"] += 1
                    continue
            normal, plane_error = floor_plane(context, x, z, radius)
            if kind in {"understory_card", "litter"} and plane_error > options["maximum_floor_plane_error_m"]:
                rejected["floor_nonplanar_contact"] += 1
                continue
            record = {"id": f"floor_{kind}_{i:03d}_{j:03d}", "kind": kind,
                      "position": [x, support["terrain_y_m"], z], "anchor": "ground_contact",
                      "yaw": yaw, "size": size, "ground_normal": normal, "plane_error_m": plane_error,
                      "evidence_class": "authored", "support": support,
                      "quantitative_uncertainty": "unknown", "species_presence_class": "authored_representative"}
            if guild:
                record["guild"] = guild
            if kind == "log":
                record.update(contacts)
                record["mortality_display_basis"] = "authored canopy-crowding and apron-proximity proxy; cause unobserved"
            if kind == "snag":
                record.update({"height_m": size[1], "dbh_m": size[0], "crown_radius_m": size[1] * .1,
                               "crown_ratio": 0., "archetype": "snag"})
                record["mortality_display_basis"] = "authored proximity to mapped hot apron; death cause and local history unknown"
            records.append(record)
            counts[kind] += 1
            if compact_litter:
                fallbacks["litter_compact_footprint"] += 1
    records.sort(key=lambda r: r["id"])
    return records, {"counts": dict(counts), "rejected": dict(rejected), "fallbacks": dict(fallbacks), "candidate_cells": len(candidates)}


def validate_document(document, context=None):
    """Reject field claims, invalid geometry and exclusion violations in authored records."""
    if document.get("schema") != "yellowstone.forest_floor.v1" or document.get("status") != "authored":
        raise ValueError("forest-floor records must retain the authored schema and class")
    if document.get("scientific_acceptance") != "not_yet_accepted" or document.get("quantitative_uncertainty") != "unknown":
        raise ValueError("forest-floor quantitative acceptance and uncertainty must remain pending")
    declared = document.get("authoring_choices", {})
    if any(choice.get("status") != "authored" or choice.get("uncertainty") != "unknown" for choice in declared.values()):
        raise ValueError("floor display settings cannot claim calibrated or measured support")
    options = authoring_settings({key: choice["value"] for key, choice in declared.items()})
    ids = set()
    counts = Counter()
    for record in document["records"]:
        if record["id"] in ids:
            raise ValueError("forest-floor record IDs must be unique")
        ids.add(record["id"])
        if record.get("evidence_class") != "authored" or record.get("species_presence_class") != "authored_representative":
            raise ValueError("authored display records cannot claim measured species presence")
        if record.get("quantitative_uncertainty") != "unknown":
            raise ValueError("authored floor-record uncertainty must remain unknown")
        if record["kind"] not in {"snag", "log", "understory_card", "litter"}:
            raise ValueError("unsupported independent forest-floor kind")
        if len(record["position"]) != 3 or len(record["size"]) != 3:
            raise ValueError("forest-floor positions and dimensions require three values")
        for value in record["position"]:
            finite("floor_position", value)
        for value in record["size"]:
            positive("floor_size", value)
        finite("floor_yaw", record["yaw"])
        normal = record.get("ground_normal")
        if normal is None or len(normal) != 3 or not all(math.isfinite(x) for x in normal) or not math.isclose(sum(x*x for x in normal), 1., abs_tol=1e-8) or normal[1] <= 0:
            raise ValueError("forest-floor ground normal must be finite, unit and upward")
        if record["kind"] in {"understory_card", "litter"} and nonnegative("floor_plane_error", record["plane_error_m"]) > options["maximum_floor_plane_error_m"]:
            raise ValueError("forest-floor footprint deviates from its terrain plane")
        if record["kind"] == "log":
            if len(record.get("axis_end_positions", [])) != 2 or len(record.get("end_positions", [])) != 2:
                raise ValueError("log requires terrain and axis endpoints")
            for point in record["axis_end_positions"] + record["end_positions"]:
                if len(point) != 3:
                    raise ValueError("log endpoints require three coordinates")
                for value in point:
                    finite("log_endpoint", value)
            gaps = record.get("contact_clearance_m", [])
            if len(gaps) < 9 or len(gaps) != len(record.get("ground_profile_m", [])) or min(gaps) < -1e-8 or max(gaps) > options["maximum_log_gap_m"] + 1e-8 or min(gaps) > 1e-7:
                raise ValueError("log must contact sampled terrain with bounded clearance")
            axis_a, axis_b = np.asarray(record["axis_end_positions"], dtype=float)
            horizontal = float(np.linalg.norm((axis_b - axis_a)[[0, 2]]))
            if not math.isclose(horizontal, record["size"][2], abs_tol=1e-8) or horizontal <= 0:
                raise ValueError("log axis does not match its horizontal length")
            radius_vertical = record["size"][0] / 2 * horizontal / np.linalg.norm(axis_b - axis_a)
            for (t, ground), gap in zip(record["ground_profile_m"], gaps):
                finite("log_profile_position", t)
                finite("log_profile_ground", ground)
                if abs(t) > horizontal / 2 + 1e-8 or not math.isclose(axis_a[1] + (axis_b[1] - axis_a[1]) * (t / horizontal + .5) - radius_vertical - ground, gap, abs_tol=1e-8):
                    raise ValueError("log clearance does not match its sampled axis")
        if record["kind"] == "snag" and not record["support"]["thermal_band"]:
            raise ValueError("snags require the authored forest-side thermal display band")
        if record["kind"] == "snag":
            if thermal_band_weight(record["support"]["apron_distance_m"], options) <= 0:
                raise ValueError("snag position falls outside the authored thermal band")
            for key in ["height_m", "dbh_m", "crown_radius_m"]:
                positive(key, record[key])
            if record["crown_ratio"] != 0 or record["archetype"] != "snag":
                raise ValueError("authored snags must remain leafless")
        if record["kind"] == "understory_card" and record.get("guild") not in GUILDS:
            raise ValueError("unknown authored understory guild")
        if record["kind"] == "understory_card" and understory_weight(record["support"]["canopy_cover_fraction"], options) <= 0:
            raise ValueError("understory cards require moderate observed canopy support")
        if fraction("floor_valid_fraction", record["support"]["canopy_valid_fraction"]) < options["minimum_valid_fraction"]:
            raise ValueError("forest-floor record has insufficient observed support")
        counts[record["kind"]] += 1
        if context:
            support, reason = context.sample(record["position"][0], record["position"][2])
            if reason or not math.isclose(support["terrain_y_m"], record["position"][1], abs_tol=1e-8):
                raise ValueError("forest-floor geometry violates terrain or mapped exclusions")
            if record["kind"] in {"understory_card", "litter"}:
                expected_normal, expected_error = floor_plane(context, record["position"][0], record["position"][2], record["size"][0] / 2)
                if not np.allclose(expected_normal, normal, atol=1e-9, rtol=0) or not math.isclose(record["plane_error_m"], expected_error, abs_tol=1e-9):
                    raise ValueError("floor plane differs from the terrain samples")
            if record["kind"] == "log":
                expected = log_contacts(context, record["position"][0], record["position"][2], record["yaw"], record["size"][0], record["size"][2], options["maximum_log_gap_m"])
                if expected is None or any(not np.allclose(expected[key], record[key], atol=1e-8, rtol=0) for key in expected):
                    raise ValueError("log contact profile differs from terrain")
    for kind, setting in [("snag", "max_snags"), ("log", "max_logs"), ("understory_card", "max_understory_cards"), ("litter", "max_litter_patches")]:
        if counts[kind] > options[setting]:
            raise ValueError("forest-floor primitive count exceeds the authored display budget")
    return True


def build_forest_floor(project, world_root, *, settings=None, output=None):
    """Build a portable independent display layer from verified canopy and terrain inputs."""
    import rasterio
    from PIL import Image
    from scipy.ndimage import distance_transform_edt
    from yellowstone_python.authoring.canopy_placement import exclusion_masks
    from yellowstone_python.land.vegetation import load_terrain, terrain_fns
    project, world_root = Path(project), Path(world_root)
    options = authoring_settings(settings)
    paths = {"canopy_coverage": project / "derived/lidar_canopy/canopy_coverage.json",
             "canopy_provenance": project / "derived/lidar_canopy/canopy_height.provenance.json",
             "interpreted_height": project / "derived/lidar_canopy/interpreted_canopy_height.tif",
             "world": world_root / "data/world.json", "habitat": world_root / "assets/textures/habitat_mask.png",
             "terrain": world_root / "data/terrain.f32", "ground_heat": world_root / "data/ground_heat.json",
             "core_terrain": world_root / "data/core_terrain/core_terrain.json",
             "core_heightfield": world_root / "data/core_terrain/core_heightfield.f32",
             "core_microrelief": world_root / "data/core_terrain/core_microrelief.f32"}
    protected = {"census": project / "derived/census.json", "base_placements": world_root / "data/placements.json",
                 "overrides": world_root / "data/placement_overrides.json"}
    before = {key: sha256_file(path) for key, path in protected.items()}
    hashes = {key: sha256_file(path) for key, path in paths.items()}
    metadata = load_json(paths["canopy_provenance"])
    if metadata["artifacts"]["interpreted_canopy_height"]["sha256"] != hashes["interpreted_height"]:
        raise ValueError("canopy footprint checksum does not match its provenance")
    coverage = load_json(paths["canopy_coverage"])
    with rasterio.open(paths["interpreted_height"]) as raster:
        heights = raster.read(1, masked=True).filled(np.nan)
    spacing = positive("canopy_resolution", metadata["resolution_m"])
    masks = exclusion_masks(load_json(paths["world"]), np.asarray(Image.open(paths["habitat"]).convert("RGB"), dtype=float) / 255,
                            heights.shape, coverage["extent_m"], spacing)
    apron_distance = (distance_transform_edt(~masks["pool_apron"]) * spacing if masks["pool_apron"].any()
                      else np.full(heights.shape, options["thermal_band_outer_m"] + 1.))
    clearance = distance_transform_edt(~np.logical_or.reduce(list(masks.values()))) * spacing
    core = load_json(paths["core_terrain"])
    grid = core["grid"]
    for key, layer in [("core_heightfield", "core_heightfield_m"), ("core_microrelief", "core_microrelief_m")]:
        if core["layers"][layer]["sha256"] != hashes[key]:
            raise ValueError("rendered core terrain checksum differs from its provenance")
    master_sample, _ = terrain_fns(load_terrain(str(paths["terrain"])))
    sample, slope = rendered_terrain_fns(master_sample,
        np.fromfile(paths["core_heightfield"], dtype="<f4").reshape(grid["nz"], grid["nx"]),
        np.fromfile(paths["core_microrelief"], dtype="<f4").reshape(grid["nz"], grid["nx"]), grid)
    heat = load_json(paths["ground_heat"])
    if heat.get("schema") != "yellowstone.ground_heat.v1" or heat.get("status") != "authored":
        raise ValueError("ground-heat support must retain its authored model class")
    def heat_at(x, z):
        grid = heat["grid"]
        column = math.floor((x - grid["origin_xz_m"][0]) / grid["cell_m"])
        row = math.floor((z - grid["origin_xz_m"][1]) / grid["cell_m"])
        if not (0 <= column < grid["nx"] and 0 <= row < grid["nz"]):
            raise ValueError("authored ground-heat grid does not cover the floor display window")
        return heat["values_w_m2"][row][column]
    context = FloorContext(coverage, masks, np.isfinite(heights), apron_distance, clearance,
                           sample, slope, heat_at, heat["parameters"]["apron_w_m2"], spacing=spacing)
    records, diagnostics = author_records(context, options)
    source_paths = {key: f"{('yellowstone_python' if path.is_relative_to(project) else 'yellowstone_midway')}/{path.relative_to(project if path.is_relative_to(project) else world_root)}"
                    for key, path in paths.items()}
    document = {"schema": "yellowstone.forest_floor.v1", "version": 1, "status": "authored",
        "scientific_acceptance": "not_yet_accepted", "quantitative_uncertainty": "unknown",
        "extent_m": coverage["extent_m"], "records": records, "diagnostics": diagnostics,
        "sources": [{"id": key, "file": source_paths[key], "sha256": hashes[key]} for key in paths],
        "producer_sha256": sha256_file(Path(__file__)), "protected_input_sha256": before,
        "authoring_choices": {key: {"value": value, "status": "authored", "uncertainty": "unknown"} for key, value in options.items()},
        "shape_choices": {"status": "authored", "uncertainty": "unknown", "snag_height_m": [3, 9],
                          "snag_width_m": [.1, .3], "log_diameter_m": [.12, .34], "log_length_m": [2.5, 9],
                          "snag_stub_radius_height_ratio": .1,
                          "patch_width_m": [.65, 1.35], "patch_height_m": [.16, .48],
                          "litter_width_m": [1.1, 3.0], "litter_height_m": [.0275, .075],
                          "litter_preferred_width_m": [2.0, 3.0], "litter_compact_width_m": [1.1, 1.9],
                          "litter_width_rule": "prefer wider footprint; retain compact footprint if terrain plane or protected clearance fails",
                          "litter_bed_projected_footprint_fraction": [.60, .64]},
        "guild_context": [{"guild": key, **value, "context_class": "literature_qualitative",
                           "local_presence": "unknown", "render_identity": "authored"} for key, value in GUILDS.items()],
        "thermal_context_source": "https://pubs.usgs.gov/publication/70162720",
        "understory_context_source": "https://www.nps.gov/yell/learn/nature/forests.htm",
        "stand_context_source": "https://research.fs.usda.gov/silvics/lodgepole-pine",
        "method": "seeded display candidates; moderate measured canopy support; protected footprints; authored apron-distance proxy",
        "terrain_contact": {"core_mesh_decimation": 2, "core_height_rule": "float32_height_plus_microrelief",
                            "triangle_diagonal": "b_c", "outside_core": "master_4m_rendered_triangles",
                            "source_class": "rendered_terrain_with_authored_microrelief"},
        "quantity": "independent display primitives; no measured species, stem density or mortality count",
        "thermal_limitation": "mapped heat is authored; forest-side apron proximity does not measure soil heat or diagnose death cause",
        "display_geometry_budget": {"status": "authored", "maximum_primitives": sum(options[k] for k in ["max_understory_cards", "max_snags", "max_logs", "max_litter_patches"]),
                                    "uncertainty": "unknown", "field_density_target": None}}
    validate_document(document, context)
    if before != {key: sha256_file(path) for key, path in protected.items()} or hashes != {key: sha256_file(path) for key, path in paths.items()}:
        raise ValueError("forest-floor input changed during authoring")
    destination = Path(output) if output is not None else project / "derived/forest_floor.json"
    def compact_numbers(value):
        if isinstance(value, float):
            return round(value, 10)
        if isinstance(value, dict):
            return {key: compact_numbers(item) for key, item in value.items()}
        if isinstance(value, list):
            return [compact_numbers(item) for item in value]
        return value
    document = compact_numbers(document)
    validate_document(document, context)
    write_json_atomic(destination, document, indent=None)
    return document
