"""Primary occurrence records and authored mammal ecology traits."""
from __future__ import annotations

import copy
from numbers import Integral
from pathlib import Path

from yellowstone_python.common.io import load_json

CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "data" / "mammal_catalogue.json"
NPS_MAMMALS = "https://www.nps.gov/yell/learn/nature/mammals.htm"
NPS_BATS = "https://www.nps.gov/yell/learn/nature/bats.htm"
BATS = {
    "Myotis lucifugus", "Eptesicus fuscus", "Myotis evotis", "Myotis volans",
    "Corynorhinus townsendii", "Myotis thysanodes", "Lasiurus cinereus",
    "Lasionycteris noctivagans", "Euderma maculatum", "Antrozous pallidus",
    "Myotis californicus", "Myotis ciliolabrum", "Myotis yumanensis",
}
ALIASES = {f"Tamias {epithet}": f"Neotamias {epithet}"
           for epithet in ("amoenus", "minimus", "umbrinus")}
RENDER_KINDS = {
    "Bison bison": "bison", "Cervus elaphus": "elk",
    "Taxidea taxus": "badger", "Lynx rufus": "bobcat",
    "Ursus arctos": "grizzly", "Canis lupus": "wolf",
    "Odocoileus hemionus": "deer", "Ursus americanus": "black_bear",
    "Lynx canadensis": "canada_lynx",
}
SUPPLIED_RENDER_KINDS = {"bison", "grizzly", "black_bear", "bobcat", "badger", "canada_lynx"}
MEADOW = ["dry_meadow", "wet_meadow", "grassland", "forest_edge", "river_bank"]
FOREST = ["forest_edge", "forest_lodgepole", "forest_moist", "conifer_forest"]
RIPARIAN = ["river_bank", "riparian", "wet_meadow"]
SOURCES = {
    "bison": "https://www.nps.gov/yell/learn/nature/bison.htm",
    "elk": "https://www.nps.gov/yell/learn/nature/elk.htm",
    "grizzly": "https://www.nps.gov/yell/learn/nature/bear.htm",
    "black_bear": "https://www.nps.gov/yell/learn/nature/bear.htm",
    "canada_lynx": "https://www.nps.gov/yell/learn/nature/canada-lynx.htm",
    "badger": "https://www.nps.gov/yell/learn/nature/badger.htm",
    "bobcat": "https://www.nps.gov/yell/learn/nature/bobcat.htm",
    "wolf": "https://www.nps.gov/yell/learn/nature/wolf.htm",
    "deer": "https://www.nps.gov/yell/learn/nature/mule-deer.htm",
}


def mammal_seed(value):
    """Return a nonnegative integer seed and reject coercion."""
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("mammal seed must be a nonnegative integer")
    return int(value)


def species_id(name):
    """Return the stable identifier for a recorded species name."""
    return "_".join(name.lower().split()[:2])


def authored_traits(name, family):
    """Assign explicit guild proxies without treating park occurrence as local abundance."""
    kind = RENDER_KINDS.get(name)
    order = family.split("/")[0]
    guild, diet, habitats = "small_mammal", "herbivore", list(FOREST + MEADOW)
    if order == "Artiodactyla":
        guild = "grazer" if name in ("Bison bison", "Cervus elaphus") else "browser"
        habitats = list(MEADOW if guild == "grazer" else FOREST + RIPARIAN)
    elif order == "Carnivora":
        guild, diet, habitats = "carnivore", "carnivore", list(FOREST + MEADOW)
        if name.startswith("Ursus") or family.endswith(("Procyonidae", "Mephitidae")):
            guild, diet = "omnivore", "omnivore"
    elif order in ("Chiroptera", "Eulipotyphla"):
        diet, habitats = "insectivore", list(FOREST + RIPARIAN)
    elif name.startswith(("Peromyscus", "Zapus")):
        diet = "omnivore"
    modes = ["midway", "park_reference"]
    if name in ("Antilocapra americana", "Lepus townsendii", "Sylvilagus audubonii"):
        habitats, modes = ["sage_steppe", "dry_sagebrush"], ["northern_range", "park_reference"]
    if name in ("Oreamnos americanus", "Ovis canadensis", "Ochotona princeps",
                "Marmota flaviventris"):
        habitats, modes = ["alpine_talus", "rock_talus"], ["alpine", "park_reference"]
    if name == "Mus musculus":
        habitats, modes = ["human_structure"], ["developed_area", "park_reference"]
    if name in ("Castor canadensis", "Ondatra zibethicus", "Lutra canadensis",
                "Sorex palustris", "Microtus richardsoni", "Mustela vison"):
        habitats = list(RIPARIAN)
    if name == "Taxidea taxus":
        habitats = list(MEADOW)
    if name == "Ursus americanus":
        habitats = list(FOREST)
    if name in ("Martes americana", "Glaucomys sabrinus", "Tamiasciurus hudsonicus",
                "Lynx canadensis", "Gulo gulo"):
        habitats = list(FOREST)
    if name == "Odocoileus hemionus":
        habitats = list(FOREST + MEADOW + RIPARIAN)
    if name == "Odocoileus virginianus":
        habitats, modes = list(RIPARIAN), ["northern_range", "park_reference"]
    if name == "Lynx canadensis":
        habitats, modes = ["cold_conifer_forest"], ["alpine", "park_reference"]
    if name == "Gulo gulo":
        habitats, modes = ["alpine_talus", "cold_conifer_forest"], ["alpine", "park_reference"]
    if name == "Lepus americanus":
        habitats = list(FOREST + ["cold_conifer_forest"])
    diel = "nocturnal" if order == "Chiroptera" or name in ("Lynx rufus", "Taxidea taxus") else "mixed"
    winter = "denning" if name.startswith("Ursus") else "torpor" if order == "Chiroptera" or name.startswith(("Marmota", "Spermophilus", "Zapus")) else "active"
    prey = []
    if diet in ("carnivore", "omnivore"):
        prey = ["microtus_montanus", "peromyscus_maniculatus", "lepus_americanus"]
    if name == "Canis lupus":
        prey = ["cervus_elaphus", "odocoileus_hemionus", "bison_bison"]
    if name == "Taxidea taxus":
        prey = ["spermophilus_armatus", "thomomys_talpoides"]
    if name == "Ursus arctos":
        prey = ["cervus_elaphus", "peromyscus_maniculatus"]
    if name == "Lynx canadensis":
        prey = ["lepus_americanus"]
    if name == "Gulo gulo":
        prey = ["marmota_flaviventris", "ochotona_princeps", "lepus_americanus"]
    if name == "Taxidea taxus":
        prey = ["spermophilus_armatus", "thomomys_talpoides"]
    lengths = {"bison": 3., "elk": 2.4, "grizzly": 2.1, "badger": .65,
               "bobcat": .82, "wolf": 1.2, "deer": 1.6, "black_bear": 1.6,
               "canada_lynx": .75}
    return {
        "mammal_guild": guild, "diet_proxy": diet, "habitats": sorted(set(habitats)),
        "allowed_local_modes": modes, "diel_proxy": diel, "winter_proxy": winter,
        "prey_species_ids": prey, "snow_half_m": .6 if kind == "bison" else .4 if kind == "elk" else .25,
        "heat_start_c": 26., "heat_scale_c": 12., "cold_scale_c": 30.,
        "soil_heat_start_c": 32., "soil_heat_scale_c": 10., "soil_exclusion_c": 50.,
        "plant_food_units_per_hour": {"grazer": .00002, "browser": .00001,
                                     "omnivore": .000008, "carnivore": 0., "small_mammal": .000002}[guild],
        "birth_rate_per_year": .15 if order == "Chiroptera" else .3 if guild != "small_mammal" else 1.5,
        "mortality_rate_per_year": .05, "predation_rate_per_year": .8,
        "approx_length_m": lengths.get(kind, .2),
        "trait_evidence_class": "authored", "guild_basis": "family_and_primary_qualitative_context",
        "quantitative_uncertainty": "unknown",
        "qualitative_source": {"Odocoileus virginianus": "https://www.nps.gov/yell/learn/nature/white-tailed-deer.htm",
                               "Lynx canadensis": "https://www.nps.gov/yell/learn/nature/canada-lynx.htm",
                               "Gulo gulo": "https://www.nps.gov/yell/learn/nature/wolverine.htm"}.get(name,
                               SOURCES.get(kind, NPS_BATS if order == "Chiroptera" else NPS_MAMMALS)),
        "negative_gates": ["unconfirmed_occurrence", "unsupported_local_mode", "habitat_mismatch",
                           "mapped_pool_apron", "mineral_surface", "open_water", "visitor_route"],
    }


def build_catalogue(raw):
    """Reconcile recorded taxa while retaining every primary occurrence row."""
    entries = {}
    rows = []
    for section in raw["sections"]:
        for source_row in section["records"]:
            row = copy.deepcopy(source_row)
            row["section"] = section["section"]
            rows.append(row)
            recorded = row["scientific_name"]
            name = ALIASES.get(recorded, " ".join(recorded.split()[:2]))
            entry = entries.setdefault(name, {"species_id": species_id(name),
                "scientific_name": name, "preferred_recorded_name": recorded,
                "common_names": [], "occurrence_records": [], "supported_park_occurrence": False,
                "qualitative_bat_confirmation": False, "order_family": row["order_family"]})
            entry["occurrence_records"].append(row)
            if row.get("raw_values"):
                entry["common_names"] += [v.strip() for v in row["raw_values"][0].split(",")]
            if section["section"] == "main_list":
                entry["supported_park_occurrence"] = True
            if name in BATS:
                entry["supported_park_occurrence"] = True
                entry["qualitative_bat_confirmation"] = True
    for name, entry in entries.items():
        entry["common_names"] = sorted(set(entry["common_names"]))
        entry["traits"] = authored_traits(name, entry["order_family"])
        entry["render_kind"] = RENDER_KINDS.get(name)
        entry["model_availability"] = {"ecology": "authored_guild_model",
            "renderer": "available_reference_or_labeled_proxy" if entry["render_kind"] else "not_available",
            "render_geometry_class": ("supplied_mesh_authored_motion" if entry["render_kind"] in SUPPLIED_RENDER_KINDS
                                      else "authored_species_shape_proxy" if entry["render_kind"] else None),
            "local_population_measurement": None}
        entry["occurrence_evidence_class"] = "primary_park_inventory" if entry["supported_park_occurrence"] else "unconfirmed_primary_inventory_record"
    species = sorted(entries.values(), key=lambda e: e["species_id"])
    return {"schema": "yellowstone.mammal_catalogue.v1", "status": "authored",
        "scientific_acceptance": "not_yet_accepted", "quantitative_uncertainty": "unknown",
        "sources": {"npspecies": {k: raw[k] for k in ("source_url", "retrieved_utc", "source_sha256")},
                    "mammals_page": NPS_MAMMALS, "bats_page": NPS_BATS},
        "source_counts": {"headline": 67, "raw_occurrence_records": len(rows),
            "canonical_species": len(species), "supported_species": sum(e["supported_park_occurrence"] for e in species),
            "unconfirmed_supplemental_species": sum(not e["supported_park_occurrence"] for e in species)},
        "reconciliation": {"chipmunk_aliases": ALIASES,
            "alias_evidence": "matching specific epithet and common name in primary NPS occurrence records",
            "alias_crosswalk_class": "authored_primary_record_crosswalk",
            "subspecies_rule": "group the first two scientific-name tokens; retain the recorded subspecies",
            "count_discrepancy": "headline67 differs from main inventory plus three bats confirmed on NPS bat page"},
        "species": species, "raw_occurrence_records": rows}


def load_catalogue(path=None):
    """Load the packaged catalogue and validate stable species identifiers."""
    doc = load_json(CATALOGUE_PATH if path is None else path)
    if doc.get("schema") != "yellowstone.mammal_catalogue.v1":
        raise ValueError("unsupported mammal catalogue schema")
    records = doc.get("species")
    if not isinstance(records, list) or not records:
        raise ValueError("mammal catalogue must contain species")
    ids = [r["species_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate mammal species id")
    return doc
