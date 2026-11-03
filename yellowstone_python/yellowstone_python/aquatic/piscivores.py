"""Trout predation by piscivorous birds and river otter, with a depth-refuge term and a Holling."""
from __future__ import annotations

from yellowstone_python.common.checks import nonnegative as _finite_nonnegative

import math

SCHEMA = "yellowstone.piscivore_predation.v1"
STATUS = "authored_illustrative_not_calibrated"

# Mass band endpoints are typical lotic trout sizes; labels follow age-class convention.
SIZE_CLASSES = {
    "yoy": {"mass_kg_lo": 0.005, "mass_kg_hi": 0.030, "label": "age-0"},
    "juvenile": {"mass_kg_lo": 0.030, "mass_kg_hi": 0.200, "label": "age-1"},
    "adult": {"mass_kg_lo": 0.200, "mass_kg_hi": 1.500, "label": "age-2+"},
}


# Piscivore densities, attack, and handling use the trout density's per-meter river support.
PISCIVORES = {
    "osprey": {
        "density_per_m_river": 0.0008,
        "density_status": "authored_illustrative",
        "max_kg_fish_per_day": 0.35,
        "handling_time_days_per_kg": 1.0 / 0.35,
        "attack_rate_m_per_day": 50.0,
        "attack_rate_status": "authored_illustrative",
        "foraging_mode": "aerial_plunge",
        "depth_scale_m": 0.7,
        "depth_scale_status": "authored_illustrative",
        "size_class_shares": {"yoy": 0.05, "juvenile": 0.55, "adult": 0.40},
        "sources": [
            'Poole (1989) Ospreys: a natural and unnatural history (adult osprey daily intake 300-500 g fish; plunge depths 0.5 to 1 m)',
        ],
    },
    "bald_eagle": {
        "density_per_m_river": 0.0003,
        "density_status": "authored_illustrative",
        "max_kg_fish_per_day": 0.50,
        "handling_time_days_per_kg": 1.0 / 0.50,
        "attack_rate_m_per_day": 30.0,
        "attack_rate_status": "authored_illustrative",
        "foraging_mode": "aerial_plunge",
        "depth_scale_m": 0.6,
        "depth_scale_status": "authored_illustrative",
        "size_class_shares": {"yoy": 0.02, "juvenile": 0.33, "adult": 0.65},
        "sources": [
            'Buehler (2000) Birds of North America account 506 (bald eagle daily food requirement roughly 489 g, 6 to 11 percent of body mass)',
        ],
    },
    "common_merganser": {
        "density_per_m_river": 0.005,
        "density_status": "authored_illustrative",
        "max_kg_fish_per_day": 0.30,
        "handling_time_days_per_kg": 1.0 / 0.30,
        "attack_rate_m_per_day": 80.0,
        "attack_rate_status": "authored_illustrative",
        "foraging_mode": "pursuit_dive",
        "depth_scale_m": 1.8,
        "depth_scale_status": "authored_illustrative",
        "size_class_shares": {"yoy": 0.20, "juvenile": 0.60, "adult": 0.20},
        "sources": [
            'Mallory and Metz (1999) Birds of North America account 442 (common merganser daily intake 250-400 g fish; pursuit dives to several meters)',
        ],
    },
    "belted_kingfisher": {
        "density_per_m_river": 0.006,
        "density_status": "authored_illustrative",
        "max_kg_fish_per_day": 0.06,
        "handling_time_days_per_kg": 1.0 / 0.06,
        "attack_rate_m_per_day": 60.0,
        "attack_rate_status": "authored_illustrative",
        "foraging_mode": "aerial_plunge",
        "depth_scale_m": 0.4,
        "depth_scale_status": "authored_illustrative",
        "size_class_shares": {"yoy": 0.55, "juvenile": 0.45, "adult": 0.00},
        "sources": [
            'Hamas (1994) Birds of North America account 84 (belted kingfisher daily intake 40-80 g fish, prey mostly less than 15 cm, plunge depth 60 cm or less)',
        ],
    },
    "river_otter": {
        "density_per_m_river": 0.0015,
        "density_status": "authored_illustrative",
        "max_kg_fish_per_day": 1.00,
        "handling_time_days_per_kg": 1.0,
        "attack_rate_m_per_day": 100.0,
        "attack_rate_status": "authored_illustrative",
        "foraging_mode": "pursuit_dive",
        "depth_scale_m": 2.5,
        "depth_scale_status": "authored_illustrative",
        "size_class_shares": {"yoy": 0.10, "juvenile": 0.45, "adult": 0.45},
        "sources": [
            'Melquist and Hornocker (1983) Wildlife Monographs 83 (river otter daily consumption approximately 15 percent of body mass, roughly 1 kg of fish per day)',
        ],
    },
}


# Depth-refuge evidence is cited; exponential shape and predator-specific scales are authored.
DEPTH_REFUGE_SOURCES = [
    "Power 1987 Predator avoidance by grazing fishes in temperate "
    "and tropical streams. In: Kerfoot and Sih eds. Predation: "
    "direct and indirect impacts on aquatic communities, University "
    "Press of New England (shallow habitats favor aerial piscivore "
    "attack on stream fishes)",
    "Harvey and Stewart 1991 Fish size and habitat depth "
    "relationships in headwater streams. Oecologia 87:336 "
    "doi:10.1007/BF00634588",
    "Lonzarich and Quinn 1995 Experimental evidence for the effect "
    "of depth and structure on the distribution growth and survival "
    "of stream fishes. Canadian Journal of Zoology 73:2223 "
    "doi:10.1139/z95-263",
]


# Trout density is authored illustrative for Firehole-like streams; local counts are unpublished.
TROUT_DENSITY_DEFAULT_PER_M2_WETTED = 0.2
TROUT_DENSITY_DEFAULT_STATUS = "authored_illustrative"
RIVER_WETTED_WIDTH_DEFAULT_M = 22.0
RIVER_WETTED_WIDTH_DEFAULT_STATUS = "authored_firehole_cross_section"




def _size_class_mean_mass_kg(size_class: str) -> float:
    """Geometric mean of the class mass band."""
    cls = SIZE_CLASSES.get(size_class)
    if cls is None:
        raise ValueError(f"unknown size_class {size_class!r}; "
                         f"have {sorted(SIZE_CLASSES)}")
    lo, hi = cls["mass_kg_lo"], cls["mass_kg_hi"]
    return math.sqrt(lo * hi)


def depth_refuge_factor(depth_m: float, scale_m: float) -> float:
    """Fractional predation accessibility at a given depth.
Returns exp(-depth/scale) in (0, 1]; scale_m sets the per-predator depth."""
    depth = _finite_nonnegative("depth_m", depth_m)
    scale = _finite_nonnegative("scale_m", scale_m)
    if scale == 0.0:
        raise ValueError("scale_m must be > 0")
    return math.exp(-depth / scale)


def _trout_density_per_m_river(trout_density_per_m2_wetted: float,
                                wetted_width_m: float) -> float:
    density_per_m2 = _finite_nonnegative(
        "trout_density_per_m2_wetted", trout_density_per_m2_wetted)
    width = _finite_nonnegative("wetted_width_m", wetted_width_m)
    if width == 0.0:
        raise ValueError("wetted_width_m must be > 0")
    return density_per_m2 * width


def predation_rate_per_day(size_class: str,
                            depth_m: float,
                            trout_density_per_m2_wetted: float = TROUT_DENSITY_DEFAULT_PER_M2_WETTED,
                            wetted_width_m: float = RIVER_WETTED_WIDTH_DEFAULT_M,
                            piscivores: dict | None = None,
                            density_overrides: dict | None = None) -> dict:
    """Fractional trout mortality rate per day in a reach cell of the given depth.
Sums over piscivores using Holling type II per predator and depth accessibility."""
    piscs = piscivores if piscivores is not None else PISCIVORES
    overrides = density_overrides or {}
    mean_mass_kg = _size_class_mean_mass_kg(size_class)
    trout_density_per_m_river = _trout_density_per_m_river(
        trout_density_per_m2_wetted, wetted_width_m)
    if trout_density_per_m_river == 0.0:
        raise ValueError("trout density per m river must be > 0")
    trout_biomass_kg_per_m_river = trout_density_per_m_river * mean_mass_kg
    trout_biomass_kg_per_m2_wetted = (
        trout_density_per_m2_wetted * mean_mass_kg)
    components: list[dict] = []
    total_rate = 0.0
    for cid, entry in piscs.items():
        pred_density = _finite_nonnegative(
            f"{cid}.density_per_m_river",
            overrides.get(cid, entry["density_per_m_river"]))
        shares = entry.get("size_class_shares", {})
        if not isinstance(shares, dict):
            raise ValueError(f"{cid}.size_class_shares must be a mapping")
        share = float(shares.get(size_class, 0.0))
        if share < 0.0 or share > 1.0:
            raise ValueError(
                f"{cid}.size_class_shares[{size_class!r}] out of [0,1]")
        scale_m = float(entry["depth_scale_m"])
        accessibility = depth_refuge_factor(depth_m, scale_m)
        if share == 0.0 or pred_density == 0.0:
            components.append({
                "id": cid, "rate_per_day": 0.0,
                "accessibility": accessibility,
                "density_per_m_river": pred_density,
                "size_class_share": share,
            })
            continue
        attack = _finite_nonnegative(
            f"{cid}.attack_rate_m_per_day", entry["attack_rate_m_per_day"])
        handling = _finite_nonnegative(
            f"{cid}.handling_time_days_per_kg",
            entry["handling_time_days_per_kg"])
        if handling == 0.0:
            raise ValueError(f"{cid}.handling_time_days_per_kg must be > 0")
        # Holling type II per predator: encounter * biomass accessible along the river reach.
        biomass_accessible = (
            trout_biomass_kg_per_m_river * share * accessibility)
        per_predator_kg_per_day = (
            attack * biomass_accessible
            / (1.0 + attack * handling * biomass_accessible))
        kg_removed_per_m_river = pred_density * per_predator_kg_per_day
        rate = kg_removed_per_m_river / trout_biomass_kg_per_m_river
        components.append({
            "id": cid, "rate_per_day": rate,
            "accessibility": accessibility,
            "density_per_m_river": pred_density,
            "size_class_share": share,
            "attack_rate_m_per_day": attack,
            "handling_time_days_per_kg": handling,
            "max_per_predator_kg_per_day": 1.0 / handling,
            "kg_removed_per_m_river_per_day": kg_removed_per_m_river,
            "foraging_mode": entry.get("foraging_mode"),
        })
        total_rate += rate
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "size_class": size_class,
        "size_class_mean_mass_kg": mean_mass_kg,
        "depth_m": float(depth_m),
        "trout_density_per_m2_wetted": trout_density_per_m2_wetted,
        "wetted_width_m": wetted_width_m,
        "trout_density_per_m_river": trout_density_per_m_river,
        "trout_biomass_kg_per_m_river": trout_biomass_kg_per_m_river,
        "trout_biomass_kg_per_m2_wetted": trout_biomass_kg_per_m2_wetted,
        "mortality_rate_per_day": total_rate,
        "components": components,
        "depth_refuge_sources": list(DEPTH_REFUGE_SOURCES),
    }


def refuge_predation_risk(cell_depth_m: float,
                           size_class: str = "adult",
                           trout_density_per_m2_wetted: float = TROUT_DENSITY_DEFAULT_PER_M2_WETTED,
                           wetted_width_m: float = RIVER_WETTED_WIDTH_DEFAULT_M,
                           piscivores: dict | None = None,
                           density_overrides: dict | None = None
                           ) -> float:
    """Predation risk (mortality fraction per day) for a candidate refuge cell at the given depth.
Depth is required; callers passing None get a ValueError and must supply the replay-cell depth."""
    if cell_depth_m is None:
        raise ValueError(
            "cell_depth_m is required; pass the replay-cell depth")
    depth = _finite_nonnegative("cell_depth_m", cell_depth_m)
    report = predation_rate_per_day(
        size_class=size_class, depth_m=depth,
        trout_density_per_m2_wetted=trout_density_per_m2_wetted,
        wetted_width_m=wetted_width_m,
        piscivores=piscivores, density_overrides=density_overrides)
    return report["mortality_rate_per_day"]


def predation_over_refuge(trout_record: dict,
                          cell_depth_m: float,
                          size_class: str = "adult",
                          trout_density_per_m2_wetted: float = TROUT_DENSITY_DEFAULT_PER_M2_WETTED,
                          wetted_width_m: float = RIVER_WETTED_WIDTH_DEFAULT_M,
                          piscivores: dict | None = None,
                          density_overrides: dict | None = None) -> dict:
    """Attach predation metrics to a trout record using an explicit cell depth.
cell_depth_m is required and must be provided by the caller (no silent default)."""
    if not isinstance(trout_record, dict):
        raise ValueError("trout_record must be a mapping")
    if cell_depth_m is None:
        raise ValueError(
            "cell_depth_m is required; pass the replay-cell depth")
    depth = _finite_nonnegative("cell_depth_m", cell_depth_m)
    report = predation_rate_per_day(
        size_class=size_class, depth_m=depth,
        trout_density_per_m2_wetted=trout_density_per_m2_wetted,
        wetted_width_m=wetted_width_m,
        piscivores=piscivores, density_overrides=density_overrides)
    report["trout_id"] = trout_record.get("id")
    return report


__all__ = [
    "DEPTH_REFUGE_SOURCES",
    "PISCIVORES",
    "RIVER_WETTED_WIDTH_DEFAULT_M",
    "RIVER_WETTED_WIDTH_DEFAULT_STATUS",
    "SCHEMA",
    "SIZE_CLASSES",
    "STATUS",
    "TROUT_DENSITY_DEFAULT_PER_M2_WETTED",
    "TROUT_DENSITY_DEFAULT_STATUS",
    "depth_refuge_factor",
    "predation_over_refuge",
    "predation_rate_per_day",
    "refuge_predation_risk",
]
