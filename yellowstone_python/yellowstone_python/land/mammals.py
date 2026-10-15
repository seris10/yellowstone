"""Authored mammal population proxies, resources and display encounters."""
from __future__ import annotations

import copy
import hashlib
import json
import math

from yellowstone_python.common.checks import finite, fraction, nonnegative, positive
from yellowstone_python.land.mammal_catalogue import load_catalogue, mammal_seed
from yellowstone_python.land.grazers import grazing_eligible

YEAR_S = 365.25 * 86400.
SCHEMA = "yellowstone.mammal_ecology.v1"


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _unit_hash(seed, *parts):
    value = hashlib.sha256(":".join(map(str, (seed, *parts))).encode()).digest()
    return int.from_bytes(value[:8], "big") / 2**64


def _season(traits, phase):
    if traits["winter_proxy"] in ("denning", "torpor"):
        return max(0., math.sin(math.pi * (phase - .18) / .72)) if .18 < phase < .9 else 0.
    return 1.


def _diel(traits, light):
    return 1. - light if traits["diel_proxy"] == "nocturnal" else .5 + .5 * light


class MammalEcology:
    """Advance bounded authored population equivalents and normalized food demand."""

    def __init__(self, patches, actors=(), seed=54173, catalogue=None, local_mode="midway"):
        self.seed = mammal_seed(seed)
        self.catalogue = copy.deepcopy(load_catalogue() if catalogue is None else catalogue)
        self.catalogue_sha = _identity(self.catalogue)
        self.species = {r["species_id"]: r for r in self.catalogue["species"]}
        if local_mode not in ("midway", "park_reference", "northern_range", "alpine", "developed_area"):
            raise ValueError("unsupported mammal local mode")
        self.local_mode = local_mode
        self.patches = {}
        for row in patches:
            pid = str(row["id"])
            if not pid or pid in self.patches:
                raise ValueError("invalid or duplicate mammal patch id")
            self.patches[pid] = copy.deepcopy(row)
        self.actors = []
        ids = set()
        kinds = {r.get("render_kind"): r["species_id"] for r in self.species.values()
                 if r.get("render_kind")}
        aliases = {"gray_wolf": "canis_lupus", "mule_deer": "odocoileus_hemionus"}
        for original in actors:
            actor = copy.deepcopy(original)
            kind, claimed = actor.get("kind"), actor.get("species_id")
            if kind not in kinds and kind not in aliases and claimed not in self.species:
                if actor.get("mammal_guild") or actor.get("taxon_class") == "mammal":
                    raise ValueError("unknown claimed mammal species")
                continue
            aid = actor["id"]
            if not isinstance(aid, str) or not aid or aid in ids:
                raise ValueError("invalid or duplicate mammal actor id")
            ids.add(aid)
            if claimed in (None, kind):
                actor["species_id"] = kinds.get(kind, aliases.get(kind))
            elif claimed in aliases:
                actor["species_id"] = aliases[claimed]
            if actor["species_id"] not in self.species or actor.get("patch_id") not in self.patches:
                raise ValueError("mammal actor requires a catalogued species and known patch")
            expected = kinds.get(kind, aliases.get(kind))
            if expected is not None and actor["species_id"] != expected:
                raise ValueError("mammal render kind disagrees with species identity")
            actor.setdefault("encounter_probability", .45)
            actor.setdefault("encounter_window_s", 300.)
            fraction("encounter probability", actor["encounter_probability"])
            positive("encounter window", actor["encounter_window_s"])
            self.actors.append(actor)
        self.elapsed_s = 0.
        self.population = {pid: {sid: .2 if self._eligible(rec, patch.get("habitat", "")) else 0.
                                 for sid, rec in self.species.items()}
                           for pid, patch in self.patches.items()}
        self.environment = {}
        self.activity = {pid: {sid: 0. for sid in self.species} for pid in self.patches}
        self.risk = copy.deepcopy(self.activity)
        self.ledger = {}
        self.consumption_by_patch = {pid: 0. for pid in self.patches}

    def _eligible(self, record, habitat):
        traits = record["traits"]
        return bool(record["supported_park_occurrence"]
                    and self.local_mode in traits["allowed_local_modes"]
                    and habitat in traits["habitats"])

    def _forcing(self, environment):
        if not isinstance(environment, dict):
            raise ValueError("mammal forcing must be a mapping")
        source = copy.deepcopy(environment)
        air = finite("mammal air_c", source.get("air_c", 18.))
        light = fraction("mammal daylight_fraction", source.get("daylight_fraction", .5))
        phase = finite("mammal season_phase", source.get("season_phase", .5), minimum=0., maximum=math.nextafter(1., 0.))
        snow = nonnegative("mammal snow_m", source.get("snow_m", 0.))
        finite("mammal local_hour", source.get("local_hour", 12.), minimum=0., maximum=24.)
        by_patch = source.get("by_patch", {})
        if not isinstance(by_patch, dict) or set(by_patch) - set(self.patches):
            raise ValueError("mammal forcing contains unknown patch ids")
        external = source.get("external_grazing_by_patch", {})
        if not isinstance(external, dict) or set(external) - set(self.patches):
            raise ValueError("external grazing contains unknown patch ids")
        patches = {}
        for pid, original in self.patches.items():
            row = by_patch.get(pid, {})
            if not isinstance(row, dict):
                raise ValueError("mammal patch forcing must be a mapping")
            capacity = positive(f"{pid} mammal capacity", row.get("capacity", original.get("capacity", 1.)))
            biomass = nonnegative(f"{pid} mammal biomass", row.get("biomass", original.get("biomass", .5)))
            patches[pid] = {
                "habitat": str(row.get("habitat", original.get("habitat", ""))),
                "biomass": biomass, "capacity": capacity,
                "forage": fraction(f"{pid} forage_fraction", row.get("forage_fraction", min(1., biomass / capacity))),
                "water": fraction(f"{pid} water_fraction", row.get("water_fraction", original.get("moisture", .5))),
                "insect": fraction(f"{pid} insect_fraction", row.get("insect_fraction", original.get("insect_activity", .5))),
                "snow": nonnegative(f"{pid} snow_m", row.get("snow_m", snow)),
                "soil_c": finite(f"{pid} soil_temperature_c", row.get("soil_temperature_c", original.get("soil_temperature_c", air))),
                "external": nonnegative(f"{pid} external grazing", external.get(pid, 0.)),
            }
        return source, air, light, phase, patches

    def step(self, dt_s, environment):
        """Advance physical seconds and return the complete deterministic state."""
        dt = finite("mammal dt_s", dt_s, minimum=0., maximum=86400.)
        source, air, light, phase, forcing = self._forcing(environment)
        activities, risks, next_population = {}, {}, copy.deepcopy(self.population)
        totals = {"initial_population_equivalents": sum(sum(r.values()) for r in self.population.values()),
                  "births": 0., "deaths": 0., "predation": 0., "predator_intake": 0.}
        consumed, available, demands = {}, {}, {}
        external_ids = {a["id"] for a in self.actors if a.get("grazing_owner") == "legacy_grazers" and grazing_eligible(a)}
        external_species = {(a["patch_id"], a["species_id"]) for a in self.actors if a["id"] in external_ids}
        for pid, context in forcing.items():
            old = self.population[pid]
            activities[pid], risks[pid] = {}, {sid: 0. for sid in self.species}
            plant_demand = 0.
            for sid, record in self.species.items():
                traits = record["traits"]
                if not self._eligible(record, context["habitat"]):
                    activities[pid][sid] = 0.
                    continue
                prey = [p for p in traits["prey_species_ids"] if p in old]
                prey_food = min(1., sum(old[p] for p in prey) / max(1, len(prey)))
                diet = traits["diet_proxy"]
                food = (context["forage"] if diet == "herbivore" else context["insect"] if diet == "insectivore"
                        else prey_food if diet == "carnivore" else .6 * context["forage"] + .2 * context["insect"] + .2 * prey_food)
                warmth = math.exp(-max(0., air - traits["heat_start_c"]) / traits["heat_scale_c"])
                cold = math.exp(-max(0., -air) / traits["cold_scale_c"])
                access = 1. / (1. + context["snow"] / traits["snow_half_m"])
                ground = (0. if context["soil_c"] >= traits["soil_exclusion_c"] else
                          math.exp(-max(0., context["soil_c"] - traits["soil_heat_start_c"]) / traits["soil_heat_scale_c"]))
                activity = food * (.35 + .65 * context["water"]) * warmth * cold * access
                activity *= _season(traits, phase) * _diel(traits, light) * ground
                activities[pid][sid] = activity
                if prey and diet in ("carnivore", "omnivore"):
                    hazard = old[sid] * activity * traits["predation_rate_per_year"]
                    for target in prey:
                        risks[pid][target] += hazard / len(prey)
                if diet in ("herbivore", "omnivore") and (pid, sid) not in external_species:
                    plant_demand += traits["plant_food_units_per_hour"] * old[sid] * activity * dt / 3600.
            for sid, record in self.species.items():
                traits, initial = record["traits"], old[sid]
                activity = activities[pid][sid]
                birth = (1. - initial) * initial * -math.expm1(-traits["birth_rate_per_year"] * activity * dt / YEAR_S)
                death = (initial + birth) * -math.expm1(-(traits["mortality_rate_per_year"] + .5 * (1. - activity)) * dt / YEAR_S)
                predation = (initial + birth - death) * -math.expm1(-risks[pid][sid] * dt / YEAR_S)
                next_population[pid][sid] = initial + birth - death - predation
                totals["births"] += birth
                totals["deaths"] += death
                totals["predation"] += predation
                totals["predator_intake"] += predation
                activities[pid][sid] *= math.exp(-risks[pid][sid])
            available[pid] = max(0., context["biomass"] - context["external"])
            demands[pid] = plant_demand
            consumed[pid] = min(available[pid], plant_demand)
        totals["final_population_equivalents"] = sum(sum(r.values()) for r in next_population.values())
        totals["population_residual"] = (totals["final_population_equivalents"] - totals["initial_population_equivalents"]
                                         - totals["births"] + totals["deaths"] + totals["predation"])
        totals["predation_transfer_residual"] = totals["predation"] - totals["predator_intake"]
        totals.update(available_biomass_by_patch=available, demand_by_patch=demands,
                      consumption_by_patch=consumed, external_legacy_grazing_ids=sorted(external_ids),
                      food_units="vegetation_normalized_biomass_index", population_units="authored_population_equivalents",
                      predator_intake_units="removed_prey_population_equivalents",
                      predation_accounting="proxy removals only; no energetic or physical mass balance",
                      externally_owned_population_by_patch={pid: {sid: self.population[pid][sid] for p, sid in sorted(external_species) if p == pid}
                                                           for pid in self.patches},
                      external_ownership_policy="qualified grazer owner allocates the complete patch/species proxy stock; display counts do not add population",
                      ownership_evidence_class="authored")
        self.elapsed_s += dt
        self.environment, self.population = source, next_population
        self.activity, self.risk, self.ledger = activities, risks, totals
        self.consumption_by_patch = consumed
        return self.snapshot()

    def snapshot(self):
        """Return species proxies and Python-produced actor presence and behavior."""
        actors = {}
        for actor in self.actors:
            aid, sid, pid = actor["id"], actor["species_id"], actor["patch_id"]
            activity = self.activity[pid][sid]
            window = math.floor(self.elapsed_s / actor["encounter_window_s"])
            present = _unit_hash(self.seed, aid, window, "encounter") < actor["encounter_probability"]
            active = present and activity > 0. and self.population[pid][sid] > 0.
            risk = self.risk[pid][sid]
            bout = math.floor(self.elapsed_s / 30.)
            choice = _unit_hash(self.seed, aid, bout, "behavior")
            behavior = ("rest" if not active or choice < .15 else "flee" if risk > .1 else "alert" if risk > .03
                        else "walk" if choice > .65 else "graze" if actor.get("mammal_guild") in ("grazer", "browser") else "forage")
            actors[aid] = {"id": aid, "species_id": sid, "kind": actor["kind"], "patch_id": pid,
                "active": active, "activity_index": activity,
                "speed_multiplier": activity * (1.5 if behavior == "flee" else 1.) if behavior in ("walk", "flee") else 0.,
                "behavior": behavior, "predation_risk_index": risk,
                "encounter_class": "authored_observation_layer", "population_measurement": None}
        return {"schema": SCHEMA, "status": "authored", "scientific_acceptance": "not_yet_accepted",
                "quantitative_uncertainty": "unknown", "elapsed_s": self.elapsed_s,
                "catalogue_sha256": self.catalogue_sha, "actors": actors,
                "species": {sid: {"species_id": sid, "population_equivalents": sum(p[sid] for p in self.population.values()),
                                  "activity_index": max((p[sid] for p in self.activity.values()), default=0.),
                                  "predation_risk_index": max((p[sid] for p in self.risk.values()), default=0.),
                                  "model_availability": record["model_availability"],
                                  "eligible_local_patches": [pid for pid, patch in self.patches.items()
                                       if self._eligible(record, self.environment.get("by_patch", {}).get(pid, {}).get("habitat", patch.get("habitat", "")))],
                                  "supported_park_occurrence": record["supported_park_occurrence"]}
                            for sid, record in self.species.items()},
                "by_patch": copy.deepcopy(self.population), "consumption_by_patch": dict(self.consumption_by_patch),
                "ledger": copy.deepcopy(self.ledger)}

    def checkpoint(self):
        """Return complete state for deterministic checkpoint replay."""
        return {"schema": "yellowstone.mammal_checkpoint.v1", "catalogue_sha256": self.catalogue_sha,
                "seed": self.seed, "local_mode": self.local_mode, "actors_sha256": _identity(self.actors),
                "patches_sha256": _identity(self.patches),
                "elapsed_s": self.elapsed_s, "population": copy.deepcopy(self.population),
                "activity": copy.deepcopy(self.activity), "risk": copy.deepcopy(self.risk),
                "environment": copy.deepcopy(self.environment), "ledger": copy.deepcopy(self.ledger),
                "consumption_by_patch": dict(self.consumption_by_patch)}

    def restore(self, state):
        """Restore a compatible checkpoint without changing catalogue or actor identity."""
        if not isinstance(state, dict) or set(state) != set(self.checkpoint()):
            raise ValueError("mammal checkpoint fields mismatch")
        if (state.get("schema") != "yellowstone.mammal_checkpoint.v1" or state.get("catalogue_sha256") != self.catalogue_sha
                or state.get("seed") != self.seed or state.get("local_mode") != self.local_mode
                or state.get("actors_sha256") != _identity(self.actors) or state.get("patches_sha256") != _identity(self.patches)):
            raise ValueError("incompatible mammal checkpoint")
        mammal_seed(state["seed"])
        validated = copy.deepcopy(state)
        for field in ("population", "activity", "risk"):
            matrix = validated[field]
            if not isinstance(matrix, dict) or set(matrix) != set(self.patches):
                raise ValueError("mammal checkpoint patch mismatch")
            for row in matrix.values():
                if not isinstance(row, dict) or set(row) != set(self.species):
                    raise ValueError("mammal checkpoint species mismatch")
                for value in row.values():
                    (nonnegative if field == "risk" else fraction)(f"checkpoint {field}", value)
        consumption = validated["consumption_by_patch"]
        if not isinstance(consumption, dict) or set(consumption) != set(self.patches):
            raise ValueError("mammal checkpoint consumption patch mismatch")
        for value in consumption.values():
            nonnegative("checkpoint consumption", value)
        if not isinstance(validated["environment"], dict) or not isinstance(validated["ledger"], dict):
            raise ValueError("mammal checkpoint forcing and ledger require mappings")
        self._forcing(validated["environment"])
        def check_numbers(value):
            if isinstance(value, dict):
                for child in value.values():
                    check_numbers(child)
            elif isinstance(value, list):
                for child in value:
                    check_numbers(child)
            elif isinstance(value, (float, int)) or isinstance(value, bool):
                finite("checkpoint ledger number", value)
        check_numbers(validated["ledger"])
        if validated["ledger"]:
            for field in ("initial_population_equivalents", "final_population_equivalents", "births", "deaths", "predation", "predator_intake"):
                nonnegative(f"checkpoint {field}", validated["ledger"][field])
            for field in ("population_residual", "predation_transfer_residual"):
                finite(f"checkpoint {field}", validated["ledger"][field])
            for field in ("available_biomass_by_patch", "demand_by_patch", "consumption_by_patch"):
                rows = validated["ledger"][field]
                if not isinstance(rows, dict) or set(rows) != set(self.patches):
                    raise ValueError("mammal checkpoint ledger patch mismatch")
                for value in rows.values():
                    nonnegative("checkpoint ledger stock", value)
            if validated["ledger"]["consumption_by_patch"] != consumption:
                raise ValueError("mammal checkpoint consumption disagrees with ledger")
            if any(consumption[p] > validated["ledger"]["available_biomass_by_patch"][p] for p in self.patches):
                raise ValueError("mammal checkpoint consumption exceeds available stock")
        elapsed = nonnegative("checkpoint elapsed_s", state["elapsed_s"])
        self.elapsed_s, self.population = elapsed, validated["population"]
        for name in ("activity", "risk", "environment", "ledger", "consumption_by_patch"):
            setattr(self, name, validated[name])
        return self.snapshot()

    def clone(self):
        """Return an independent model with identical deterministic state."""
        return copy.deepcopy(self)


def author_midway_encounters(world, tfns, shells, *, patches, existing_actors=(), seed=54173,
                            catalogue=None, habitat_sampler=None, blocked=None):
    """Generate terrain-qualified authored encounter routes and enrich baseline mammal actors."""
    from yellowstone_python.authoring.mammal_encounters import author_encounters
    return author_encounters(world, tfns, shells, patches=patches, existing_actors=existing_actors,
                             seed=seed, catalogue=catalogue, habitat_sampler=habitat_sampler, blocked=blocked)
