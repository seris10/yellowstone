"""Terrain-qualified authored mammal encounter routes."""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import math
from pathlib import Path
import random

from yellowstone_python.common.checks import finite
from yellowstone_python.land.mammal_catalogue import FOREST, load_catalogue, mammal_seed
from yellowstone_python.land.grazers import route_length, segment_samples
from yellowstone_python.land.vegetation import habitat_moisture_at
from yellowstone_python.thermal_features.pool_crust import in_apron

CHOICES = {"encounter_probability": .45, "encounter_window_s": 300.,
           "behavior_bout_s": 30., "route_sample_m": 1., "max_slope_deg": 25.,
           "route_clearance_m": 7., "river_clearance_m": 6.,
           "candidate_attempts": 160, "route_radius_m": [6., 16.],
           "patch_candidate_radius_fraction": .65, "forest_candidate_radius_fraction": 1.,
           "mineral_channel_max": .35, "meadow_channel_min": .35,
           "preferred_prismatic_distance_m": [145., 235.]}


def habitat_mask_blocker(world_root):
    """Read the mapped mineral channel and expose authored meadow/forest classification."""
    from PIL import Image
    from yellowstone_python.land.vegetation import HALF, STEP
    path = Path(world_root) / "assets/textures/habitat_mask.png"
    image = Image.open(path).convert("RGB")
    def channels(x, z):
        ix, iz = math.floor((x + HALF) / STEP), math.floor((z + HALF) / STEP)
        return image.getpixel((ix, iz)) if 0 <= ix < image.width and 0 <= iz < image.height else None
    def blocked(x, z):
        value = channels(x, z)
        return value is None or value[0] / 255 >= CHOICES["mineral_channel_max"]
    def habitat_at(x, z):
        value = channels(x, z)
        if value is None or blocked(x, z):
            return "unsuitable_matrix"
        return "dry_meadow" if value[1] / 255 >= CHOICES["meadow_channel_min"] else "forest_edge"
    def disk(x, z, radius):
        for ix in range(math.floor((x - radius + HALF) / STEP), math.floor((x + radius + HALF) / STEP) + 1):
            for iz in range(math.floor((z - radius + HALF) / STEP), math.floor((z + radius + HALF) / STEP) + 1):
                x0, z0 = ix * STEP - HALF, iz * STEP - HALF
                distance = math.hypot(max(x0 - x, 0., x - x0 - STEP), max(z0 - z, 0., z - z0 - STEP))
                if distance <= radius and (not (0 <= ix < image.width and 0 <= iz < image.height)
                                          or image.getpixel((ix, iz))[0] / 255 >= CHOICES["mineral_channel_max"]):
                    return True
        return False
    blocked.habitat_at = habitat_at
    blocked.disk = disk
    return blocked


def _distance(x, z, a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dz * dz
    t = min(1., max(0., ((x - a[0]) * dx + (z - a[1]) * dz) / denominator)) if denominator else 0.
    return math.hypot(x - a[0] - t * dx, z - a[1] - t * dz)


class RouteSupport:
    """Indexed mapped polylines and body-clearance geometry."""

    def __init__(self, world, tfns, shells, patches, habitat_sampler, blocked):
        self.sample, self.slope = tfns
        self.shells, self.patches = shells, patches
        self.habitat = habitat_sampler or getattr(blocked, "habitat_at", None)
        self.blocked = blocked
        self.half = finite("world half extent", world.get("georeference", {}).get("extent", 4096.)) / 2
        self.segments = defaultdict(list)
        for group, features in [("visitor_route", world.get("routes", [])), ("open_water", world.get("rivers", []))]:
            for feature in features:
                points = [(finite("feature x", p[0]), finite("feature z", p[2])) for p in feature.get("points", [])]
                half_width = finite("feature width", feature.get("width", 2.), minimum=0.) / 2
                margin = CHOICES["route_clearance_m"] if group == "visitor_route" else CHOICES["river_clearance_m"]
                width = half_width + margin
                for a, b in zip(points, points[1:]):
                    for ix in range(math.floor((min(a[0], b[0]) - width - 3) / 64), math.floor((max(a[0], b[0]) + width + 3) / 64) + 1):
                        for iz in range(math.floor((min(a[1], b[1]) - width - 3) / 64), math.floor((max(a[1], b[1]) + width + 3) / 64) + 1):
                            self.segments[ix, iz].append((a, b, width, group))

    def qualify(self, x, z, record):
        """Reject unsupported habitat and mapped hazards at the body footprint."""
        radius = record["traits"]["approx_length_m"] / 2
        if abs(x) + radius >= self.half or abs(z) + radius >= self.half:
            return "world_edge"
        if self.blocked:
            if hasattr(self.blocked, "disk"):
                if self.blocked.disk(x, z, radius):
                    return "mineral_surface"
            else:
                for dx, dz in [(0., 0.)] + [(radius * math.cos(a * math.tau / 8), radius * math.sin(a * math.tau / 8)) for a in range(8)]:
                    if self.blocked(x + dx, z + dz):
                        return "mineral_surface"
        if self.habitat:
            habitat = self.habitat(x, z)
        else:
            habitat, _ = habitat_moisture_at(x, z, self.patches)
        if habitat not in record["traits"]["habitats"]:
            return "habitat_mismatch"
        for shell in self.shells:
            expanded = dict(shell, apron_margin_m=shell.get("apron_margin_m", 0.) + radius,
                            r_apron_m=shell["r_apron_m"] + radius)
            if in_apron(x, z, expanded):
                return "mapped_pool_apron"
        for a, b, width, reason in self.segments[math.floor(x / 64), math.floor(z / 64)]:
            if _distance(x, z, a, b) <= width + radius:
                return reason
        if finite("mammal terrain slope", self.slope(x, z), minimum=0., maximum=90.) > CHOICES["max_slope_deg"]:
            return "steep_terrain"
        finite("mammal terrain height", self.sample(x, z))
        return None

    def check(self, points, record):
        """Inspect complete closed route segments with body clearance."""
        if len(points) < 2 or route_length(points + [points[0]]) > 200.:
            return "route_length"
        for a, b in zip(points, points[1:] + [points[0]]):
            for x, z in segment_samples(a, b, CHOICES["route_sample_m"]):
                reason = self.qualify(x, z, record)
                if reason:
                    return reason
        return None


def author_encounters(world, tfns, shells, *, patches, existing_actors=(), seed=54173,
                      catalogue=None, habitat_sampler=None, blocked=None):
    """Produce reproducible display representatives with explicit observation authorship."""
    seed = mammal_seed(seed)
    catalogue = load_catalogue() if catalogue is None else catalogue
    kinds = {r["render_kind"]: r for r in catalogue["species"] if r.get("render_kind")}
    support = RouteSupport(world, tfns, shells, patches, habitat_sampler, blocked)
    rng, actors, rejected = random.Random(seed), [], Counter()
    source_ids, used_ids = [], {a["id"] for a in existing_actors}
    for original in existing_actors:
        if original.get("kind") not in kinds:
            continue
        rec, actor = kinds[original["kind"]], copy.deepcopy(original)
        actor.update(species_id=rec["species_id"], mammal_guild=rec["traits"]["mammal_guild"],
                     encounter_probability=CHOICES["encounter_probability"], encounter_window_s=CHOICES["encounter_window_s"],
                     encounter_class="authored", grazing_owner="legacy_grazers" if actor["kind"] in ("bison", "elk") else "mammals")
        reason = ("unconfirmed_occurrence" if not rec["supported_park_occurrence"] else
                  "unsupported_local_mode" if "midway" not in rec["traits"]["allowed_local_modes"] else
                  support.check(actor.get("path_xz", []), rec))
        actor["route_support"] = {"status": "authored", "qualified": reason is None, "rejection_reason": reason}
        if reason:
            actor["encounter_probability"] = 0.
            rejected["preserved_actor_" + reason] += 1
        actors.append(actor)
        source_ids.append(actor["id"])
    prismatic = next((p for p in world.get("pools", []) if p.get("name") == "Grand Prismatic Spring"), None)
    for kind, rec in sorted(kinds.items()):
        if not rec["supported_park_occurrence"]:
            rejected["unconfirmed_occurrence_" + kind] += 1
            continue
        if "midway" not in rec["traits"]["allowed_local_modes"]:
            rejected["unsupported_local_mode_" + kind] += 1
            continue
        compatible = [p for p in patches if p.get("habitat") in rec["traits"]["habitats"]]
        if not compatible:
            rejected["no_eligible_patch_" + kind] += 1
            continue
        found = None
        for attempt in range(CHOICES["candidate_attempts"]):
            patch = compatible[attempt % len(compatible)]
            cx, cz = patch["center_xz"]
            angle = rng.random() * math.tau
            if kind == "bison" and prismatic and support.habitat and attempt < 80:
                pc = prismatic["center"]
                radius = rng.uniform(*CHOICES["preferred_prismatic_distance_m"])
                cx, cz = pc[0] + radius * math.cos(angle), pc[2] + radius * math.sin(angle)
                patch = min(compatible, key=lambda p: math.hypot(cx - p["center_xz"][0], cz - p["center_xz"][1]))
            else:
                fraction = CHOICES["forest_candidate_radius_fraction"] if set(rec["traits"]["habitats"]) <= set(FOREST) else CHOICES["patch_candidate_radius_fraction"]
                radius = math.sqrt(rng.random()) * finite("patch radius", patch.get("radius_m", 30.), minimum=0.) * fraction
                cx, cz = cx + radius * math.cos(angle), cz + radius * math.sin(angle)
            size = rng.uniform(*CHOICES["route_radius_m"])
            points = [[cx + size * math.cos(angle + i * math.tau / 4), cz + size * math.sin(angle + i * math.tau / 4)] for i in range(4)]
            reason = support.check(points, rec)
            if reason:
                rejected[reason] += 1
                continue
            found = (patch, points)
            break
        if found is None:
            rejected["no_qualified_route_" + kind] += 1
            continue
        patch, points = found
        aid = f"mammal_encounter_{kind}_01"
        if aid in used_ids:
            raise ValueError("mammal encounter id collides with source actor")
        used_ids.add(aid)
        x, z = points[0]
        actor = {"id": aid, "kind": kind, "species_id": rec["species_id"], "medium": "land",
                 "mammal_guild": rec["traits"]["mammal_guild"], "patch_id": patch["id"], "path_xz": points,
                 "position": [x, float(support.sample(x, z)), z], "scale": 1., "ground_offset_m": 0.,
                 "approx_dimensions_m": {"length": rec["traits"]["approx_length_m"]},
                 "walk_mps": .56 if kind in ("bison", "elk", "deer") else .7,
                 "grazing_owner": "mammals", "encounter_probability": CHOICES["encounter_probability"],
                 "encounter_window_s": CHOICES["encounter_window_s"], "encounter_class": "authored",
                 "route_support": {"status": "authored", "qualified": True,
                     "habitat_classification": "authored mapped-mask proxy" if support.habitat else "authored patch footprint",
                     "patch_forcing": "existing patch environmental proxy; local transfer error unknown",
                     "terrain_y": "terrain.f32 surface sample", "full_segment_spacing_m": CHOICES["route_sample_m"]},
                 "population_measurement": None, "quantitative_uncertainty": "unknown"}
        actors.append(actor)
    return {"schema": "yellowstone.mammal_encounters.v1", "status": "authored",
            "scientific_acceptance": "not_yet_accepted", "quantitative_uncertainty": "unknown",
            "seed": seed, "actors": actors, "preserved_source_actor_ids": source_ids,
            "rejected_reasons": dict(rejected), "supplemental_mineral_mask": "bound" if blocked else "unavailable",
            "authoring_choices": {k: {"value": v, "status": "authored", "uncertainty": "unknown"} for k, v in CHOICES.items()},
            "count_scope": "display representatives; park inventory is not local abundance",
            "observation_method": "deterministic physical-time windows; Python ecology gates presence and behavior",
            "sources": catalogue["sources"]}
