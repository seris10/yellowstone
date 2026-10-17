"""Three-compartment prey + bird diets."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite, nonnegative as _nonnegative, positive as _positive, fraction as _unit_interval

import copy
import math

HOVER_THRESHOLD = 0.035  # wildlife_actor.gd::_update_insects; strict > threshold matches the renderer.
WIND_DECAY_SCALE = 8.0  # m/s scale for wind mortality on emergent prey
# Civil-twilight band in degrees: light fades to zero at -6 deg elevation.
SUNLIGHT_CIVIL_TWILIGHT_DEG = -6.0


def _solar_elevation_deg_from_hour(hour: float) -> float:
    """Nominal solar elevation (deg) from local solar hour.
Cosine profile peaking at hour 12 with 90 deg amplitude."""
    return 90.0 * math.cos((float(hour) - 12.0) * math.pi / 12.0)


def sunlight(hour: float) -> float:
    """Smooth sunlight weight in [0, 1] from solar elevation.
Linear ramp from zero at -6 deg civil twilight to one at zenith; no hard clip at sunrise/sunset."""
    hour = _finite("hour", hour)
    elev = _solar_elevation_deg_from_hour(hour)
    span = 90.0 - SUNLIGHT_CIVIL_TWILIGHT_DEG
    return min(1.0, max(0.0, (elev - SUNLIGHT_CIVIL_TWILIGHT_DEG) / span))


def wind_factor(wind_mps: float) -> float:
    """Exposed insects suppress flight in wind; calm returns 1."""
    wind_mps = _nonnegative("wind_mps", wind_mps)
    return math.exp(-wind_mps / WIND_DECAY_SCALE)


def flowering_factor(stage: float) -> float:
    """0 = no bloom, 1 = full bloom; food baseline 0.5 even without bloom."""
    stage = _unit_interval("stage", stage)
    return 0.5 + 0.5 * stage


def insect_activity(*, sun: float, air_c: float, cloud: float,
                    moisture: float, resource: float, wind_mps: float = 0.0,
                    flowering: float = 0.5) -> float:
    sun = _unit_interval("sun", sun)
    cloud = _unit_interval("cloud", cloud)
    moisture = _unit_interval("moisture", moisture)
    resource = _unit_interval("resource", resource)
    flowering = _unit_interval("flowering", flowering)
    wind_mps = _nonnegative("wind_mps", wind_mps)
    air_c = _finite("air_c", air_c)
    base = (float(sun) * min(1.0, max(0.0, (float(air_c) - 8.0) / 14.0))
            * (1.0 - min(1.0, max(0.0, float(cloud))))
            * min(1.0, max(0.0, float(moisture)))
            * min(1.0, max(0.0, float(resource))))
    return min(1.0, max(0.0, base * wind_factor(wind_mps)
                        * flowering_factor(flowering)))


def foraging_state(activity: float) -> str:
    activity = _finite("activity", activity)
    return "hover" if activity > HOVER_THRESHOLD else "inactive"


def bird_timing(activity: float, base_perch_s: float,
                base_forage_s: float) -> tuple[float, float]:
    """High activity -> shorter perch, longer forage bout (bounded)."""
    activity = _unit_interval("activity", activity)
    base_perch_s = _nonnegative("base_perch_s", base_perch_s)
    base_forage_s = _nonnegative("base_forage_s", base_forage_s)
    perch = base_perch_s * (1.5 - activity)
    forage = base_forage_s * (0.5 + activity)
    return (max(2.0, perch), max(2.0, forage))


def step_resource(resource: float, recovery_per_hour: float, sun: float,
                  moisture: float, consumed: float, dt_s: float) -> float:
    resource = _finite("resource", resource)
    recovery_per_hour = _nonnegative("recovery_per_hour", recovery_per_hour)
    sun = _finite("sun", sun)
    moisture = _finite("moisture", moisture)
    consumed = _nonnegative("consumed", consumed)
    dt_s = _nonnegative("dt_s", dt_s)
    if not 0.0 <= resource <= 1.0:
        raise ValueError("resource must be in [0, 1]")
    if not 0.0 <= sun <= 1.0:
        raise ValueError("sun must be in [0, 1]")
    if not 0.0 <= moisture <= 1.0:
        raise ValueError("moisture must be in [0, 1]")
    hours = dt_s / 3600.0
    gain = (float(recovery_per_hour) * sun * min(1.0, max(0.0, moisture))
            * (1.0 - min(1.0, max(0.0, resource))) * hours)
    return min(1.0, max(0.0, resource + gain - max(0.0, consumed)))


def _validate_wildlife_records(wildlife: list) -> None:
    """Raise if wildlife list contains non-mapping entries."""
    if not isinstance(wildlife, list):
        raise ValueError("wildlife must be a list")
    for i, rec in enumerate(wildlife):
        if not isinstance(rec, dict):
            raise ValueError(f"wildlife[{i}] must be a mapping")


def update_wildlife(wildlife: list, activity_by_patch: dict) -> list:
    """Retune dipper/raven cadence from shared activity.
Prefer update_wildlife_from_intake() for intake-driven timing."""
    _validate_wildlife_records(wildlife)
    out = copy.deepcopy(wildlife)
    for rec in out:
        if rec.get("id") not in ("dipper_01", "raven_01"):
            continue
        activity = _finite("activity", float(activity_by_patch.get(rec.get("patch_id", ""), 0.0)))
        perch, forage = bird_timing(activity, rec.get("perch_seconds", 12.0),
                                    rec.get("forage_seconds", 18.0))
        rec["perch_seconds"] = round(perch, 2)
        rec["forage_seconds"] = round(forage, 2)
        rec["activity_basis"] = round(activity, 4)
    return out


# --- Three-compartment prey dynamics ---

def holling_type_ii(n: float, attack_rate: float,
                    handling_time: float) -> float:
    """C(N) = aN/(1+ahN). Saturates; never exceeds 1/h. All illustrative."""
    n = _nonnegative("prey availability", n)
    a = _nonnegative("attack_rate", attack_rate)
    h = _nonnegative("handling_time", handling_time)
    denominator = 1.0 + a * h * n
    if not math.isfinite(denominator) or denominator <= 0:
        raise ValueError("invalid Holling type-II denominator")
    rate = a * n / denominator
    if not math.isfinite(rate) or rate < 0:
        raise ValueError("Holling intake must be finite and >= 0")
    return rate


def develop_benthic(nb: float, water_c: float, dt_s: float,
                    tbase: float = 4.0, rate: float = 0.02,
                    capacity: float = 1.0, disturbance: float = 0.0,
                    t_cutoff: float | None = None
                    ) -> tuple[float, float, float]:
    """Benthic degree-day development to emergence flux.
Returns (nb_new, emergence, disturbance_loss); disturbance_loss is the stock removed by shear."""
    nb = _finite("nb", nb)
    # Float noise from prior steps reads as tiny negatives; clamp those.
    if -1e-12 < nb < 0.0:
        nb = 0.0
    capacity = _positive("capacity", capacity)
    if not 0.0 <= nb <= capacity:
        raise ValueError(f"nb must be in [0, capacity], got {nb}")
    water_c = _finite("water_c", water_c)
    dt_s = _nonnegative("dt_s", dt_s)
    tbase = _finite("tbase", tbase)
    rate = _nonnegative("rate", rate)
    disturbance = _finite("disturbance", disturbance)
    if not 0.0 <= disturbance <= 1.0:
        raise ValueError("disturbance must be in [0, 1]")
    water_c = float(water_c)
    if t_cutoff is not None and water_c >= float(t_cutoff):
        dd = 0.0
    else:
        dd = max(0.0, water_c - tbase) * dt_s / 86400.0
    emergence = min(nb, float(rate) * dd * nb)
    remaining = nb - emergence
    disturbance_loss = remaining * float(disturbance)
    remaining -= disturbance_loss
    hours = dt_s / 3600.0
    nb2 = min(capacity, remaining + 0.01 * (1.0 - remaining / capacity) * hours)
    return (max(0.0, nb2), emergence, disturbance_loss)


def develop_benthic_grid(nb_cells: list, water_c_cells: list, dt_s: float,
                         tbase: float = 4.0, rate: float = 0.02,
                         capacity: float = 1.0, disturbance: float = 0.0,
                         t_cutoff: float | None = None) -> dict:
    """Per-cell develop_benthic driven by a per-cell temperature array.
Lengths must match; returns dict with nb, emergence, disturbance_loss lists."""
    if not isinstance(nb_cells, (list, tuple)):
        raise ValueError("nb_cells must be a list or tuple")
    if not isinstance(water_c_cells, (list, tuple)):
        raise ValueError("water_c_cells must be a list or tuple")
    if len(nb_cells) != len(water_c_cells):
        raise ValueError(
            f"nb_cells length {len(nb_cells)} != water_c_cells "
            f"length {len(water_c_cells)}")
    nb_out: list[float] = []
    emergence_out: list[float] = []
    disturb_out: list[float] = []
    for nb_i, t_i in zip(nb_cells, water_c_cells):
        nb_new, emergence, disturb_loss = develop_benthic(
            nb_i, t_i, dt_s, tbase=tbase, rate=rate, capacity=capacity,
            disturbance=disturbance, t_cutoff=t_cutoff)
        nb_out.append(nb_new)
        emergence_out.append(emergence)
        disturb_out.append(disturb_loss)
    return {"nb": nb_out, "emergence": emergence_out,
            "disturbance_loss": disturb_out}


PREY_COMPARTMENTS = frozenset({
    "terrestrial", "benthic", "emergent",
})










def _validate_consumer(cid: str, consumer: dict) -> dict:
    if not isinstance(consumer, dict):
        raise ValueError(f"consumer {cid!r} must be an object")
    attack = _nonnegative(f"{cid}.attack_rate", consumer.get("a", 1.0))
    handling = _nonnegative(f"{cid}.handling_time", consumer.get("h", 0.5))
    diet = consumer.get("diet", {})
    if not isinstance(diet, dict) or not diet:
        raise ValueError(f"{cid}.diet must be a nonempty mapping")
    normalized = {}
    for compartment, share in diet.items():
        if compartment not in PREY_COMPARTMENTS:
            raise ValueError(f"{cid}.diet has unknown compartment {compartment!r}")
        share = _nonnegative(f"{cid}.diet.{compartment}", share)
        normalized[compartment] = share
    total = sum(normalized.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"{cid}.diet shares must sum to 1, got {total}")
    return {"a": attack, "h": handling, "diet": normalized}


# Transferred benthic thermal structure; faster, multivoltine dipteran rates are authored.
INSECT_GROUPS = {
    "ept": {  # mayfly/stonefly/caddis proxy: cold fauna
        "tbase_c": 2.0, "rate_per_dd": 0.012, "t_cutoff_c": 22.0,
        "status": "transferred_structure_authored_rates",
        "sources": [
            'Kaeding & Kaya (1978) (cold-station benthic EPT diets)',
            'Mackey (1977) (developmental zeroes down to ~2 C)',
            'Benton (1987) (Ameletus development at 5-15 C)',
            'Sweeney & Vannote (1981) (thermal equilibrium hypothesis)',
        ],
    },
    "dipteran": {  # chironomid proxy: warm-tolerant, fast
        "tbase_c": 8.0, "rate_per_dd": 0.030, "t_cutoff_c": 30.0,
        "status": "transferred_structure_authored_rates",
        "sources": [
            'Kaeding & Kaya (1978) (warm-station dipteran diets)',
            'Maier et al. (1990) (lower limit 8-10 C, optimum ~20 C, upper tolerance 28-30 C)',
            'Mackey (1977) (lotic chironomid zeroes 2.4-9.7 C)',
        ],
    },
}


def trout_diet_at_temp(water_c: float) -> dict[str, float]:
    """Trout benthic-vs-emergent shares shift with temperature (Kaeding & Kaya (1978)).
Linear transition 15 to 21 C; molluscs omitted."""
    water_c = _finite("water_c", water_c)
    frac = min(1.0, max(0.0, (water_c - 15.0) / (21.0 - 15.0)))
    return {"emergent": 0.2 + 0.5 * frac, "benthic": 0.8 - 0.5 * frac}


def step_compartments(state: dict, forcing: dict, dt_s: float,
                      consumers: dict | None = None) -> tuple[dict, dict]:
    """Advance {Nt, Nb, Ne} one step."""
    f = forcing
    sun = _unit_interval("sun", float(f.get("sun", 0.5)))
    cloud = _unit_interval("cloud", float(f.get("cloud", 0.2)))
    moisture = _unit_interval("moisture", float(f.get("moisture", 0.6)))
    flowering_forced = _unit_interval("flowering", float(f.get("flowering", 0.5)))
    bloom = 0.5 + 0.5 * min(1.0, max(0.0, flowering_forced))
    nt = _unit_interval("Nt", float(state.get("Nt", 0.5)))
    dt_s = _nonnegative("dt_s", dt_s)
    hours = dt_s / 3600.0
    nt += (0.05 * sun * bloom * nt * (1.0 - nt) - 0.01 * nt) * hours
    nt = min(1.0, max(0.0, nt))
    nb, emergence, disturbance_loss = develop_benthic(
        float(state.get("Nb", 0.5)), float(f.get("water_c", 15.0)), dt_s,
        disturbance=float(f.get("disturbance", 0.0)))
    ne = max(0.0, float(state.get("Ne", 0.2)) + emergence)
    prey = {
        "terrestrial": nt,
        "benthic": nb,
        "emergent": ne,
    }
    validated_consumers = {
        cid: _validate_consumer(cid, consumer)
        for cid, consumer in (consumers or {}).items()
    }
    demands: dict[str, dict[str, float]] = {}
    for cid, consumer in validated_consumers.items():
        demands[cid] = {}
        for compartment, share in consumer["diet"].items():
            available = prey[compartment]
            rate = holling_type_ii(
                available,
                consumer["a"],
                consumer["h"],
            )
            demands[cid][compartment] = max(
                0.0,
                rate * share * hours,
            )
    allocated: dict[str, dict[str, float]] = {
        cid: {} for cid in validated_consumers
    }
    for compartment, available in prey.items():
        total_demand = sum(
            demand.get(compartment, 0.0)
            for demand in demands.values()
        )
        scale = (
            min(1.0, available / total_demand)
            if total_demand > 0.0
            else 1.0
        )
        for cid, demand in demands.items():
            amount = demand.get(compartment, 0.0) * scale
            allocated[cid][compartment] = amount
        consumed = min(available, total_demand * scale)
        prey[compartment] -= consumed
    consumed_by = {
        cid: round(sum(amounts.values()), 6)
        for cid, amounts in allocated.items()
    }
    nt = prey["terrestrial"]
    nb = prey["benthic"]
    ne = prey["emergent"]
    ne *= math.exp(-max(0.0, float(f.get("wind_mps", 0.0))) / WIND_DECAY_SCALE * hours)
    wind_loss = 1.0 - math.exp(-max(0.0, float(f.get("wind_mps", 0.0))) / WIND_DECAY_SCALE * hours)
    new_state = {"Nt": round(min(1.0, max(0.0, nt)), 6),
                 "Nb": round(max(0.0, nb), 6),
                 "Ne": round(max(0.0, ne), 6)}
    activity = insect_activity(
        sun=sun, air_c=_finite("air_c", float(f.get("air_c", 15.0))),
        cloud=_unit_interval("cloud", float(f.get("cloud", 0.2))),
        moisture=_unit_interval("moisture", float(f.get("moisture", 0.6))),
        resource=min(1.0, max(0.0, new_state["Nt"])),
        wind_mps=float(f.get("wind_mps", 0.0)),
        flowering=_unit_interval("flowering", float(f.get("flowering", 0.5))))
    ledger = {"emergence": round(emergence, 6), "consumed_by": consumed_by,
              "activity": round(activity, 4),
              "wind_loss": round(wind_loss, 6),
              "disturbance_loss": round(disturbance_loss, 6),
              "state": foraging_state(activity)}
    return new_state, ledger


DEFAULT_DIETS = {
    # Dipper: benthic + emergent; trout: emergent/drift; raven: generalist background.
    "dipper": {"a": 1.2, "h": 0.4, "diet": {"benthic": 0.7, "emergent": 0.3}},
    "trout": {"a": 1.0, "h": 0.5, "diet": {"emergent": 0.6, "benthic": 0.4}},
    "raven": {"a": 0.4, "h": 0.8, "diet": {"terrestrial": 0.6, "emergent": 0.4}},
}


# Aerial and riparian consumers of the emergent compartment; Firehole-reach intake rates unmeasured.
AERIAL_INSECTIVORE_DIETS = {
    "swallow": {
        "a": 0.9, "h": 0.35,
        "diet": {"emergent": 0.85, "terrestrial": 0.15},
        "status": "authored_illustrative",
        "sources": [
            'Nakano and Murakami (2001) Reciprocal subsidies: dynamic interdependence between terrestrial and aquatic food webs. PNAS 98:166 doi:10.1073/pnas.98.1.166',
            'Baxter Fausch and Saunders (2005) Tangled webs: reciprocal flows of invertebrate prey link streams and riparian zones. Freshwater Biology 50:201 doi:10.1111/j.1365-2427.2004.01328.x',
        ],
    },
    "bat": {
        "a": 0.7, "h": 0.4,
        "diet": {"emergent": 0.75, "terrestrial": 0.25},
        "status": "authored_illustrative",
        "sources": [
            'Nakano and Murakami (2001) Reciprocal subsidies: dynamic interdependence between terrestrial and aquatic food webs. PNAS 98:166 doi:10.1073/pnas.98.1.166 (aquatic emergence subsidizes riparian aerial insectivores including bats)',
            'Baxter Fausch and Saunders (2005) Tangled webs: reciprocal flows of invertebrate prey link streams and riparian zones. Freshwater Biology 50:201 doi:10.1111/j.1365-2427.2004.01328.x',
        ],
    },
    "riparian_spider": {
        "a": 0.5, "h": 0.6,
        "diet": {"emergent": 0.9, "terrestrial": 0.1},
        "status": "authored_illustrative",
        "sources": [
            'Baxter Fausch and Saunders (2005) Tangled webs: reciprocal flows of invertebrate prey link streams and riparian zones. Freshwater Biology 50:201 doi:10.1111/j.1365-2427.2004.01328.x',
            'Nakano and Murakami (2001) Reciprocal subsidies: dynamic interdependence between terrestrial and aquatic food webs. PNAS 98:166 doi:10.1073/pnas.98.1.166',
        ],
    },
}


def emergence_total_from_taxa(emergence_by_taxon: dict[str, float]) -> float:
    """Sum per-taxon emergence into the input to the emergent compartment.
Entries with no_emergence set are ignored; negative emergence rejected."""
    if not isinstance(emergence_by_taxon, dict):
        raise ValueError("emergence_by_taxon must be a mapping")
    total = 0.0
    for taxon_id, value in emergence_by_taxon.items():
        amount = _nonnegative(f"emergence.{taxon_id}", value)
        total += amount
    return total


def diets_with_aerial_insectivores(base: dict | None = None) -> dict:
    """Return a consumers dict combining base diets with aerial insectivores.
base defaults to DEFAULT_DIETS; AERIAL_INSECTIVORE_DIETS entries override on key collision."""
    merged = dict(base if base is not None else DEFAULT_DIETS)
    for cid, consumer in AERIAL_INSECTIVORE_DIETS.items():
        merged[cid] = {
            "a": consumer["a"],
            "h": consumer["h"],
            "diet": consumer["diet"],
        }
    return merged


def update_wildlife_from_intake(wildlife: list, intake_by_id: dict,
                                basis_by_consumer: dict | None = None) -> list:
    """Bout timing from Holling intake rate (satiation shortens foraging).
intake_by_id: consumer id -> prey/hour; raven floor keeps a baseline bout."""
    basis_by_consumer = basis_by_consumer or {}
    _validate_wildlife_records(wildlife)
    out = copy.deepcopy(wildlife)
    for rec in out:
        rid = rec.get("id")
        if rid not in ("dipper_01", "raven_01"):
            continue
        consumer = "dipper" if "dipper" in rid else "raven"
        intake = _nonnegative(f"{consumer} intake",
                            float(intake_by_id.get(consumer, 0.0)))
        satiety = min(1.0, intake * 4.0)
        base_p, base_f = rec.get("perch_seconds", 12.0), rec.get("forage_seconds", 18.0)
        if "raven" in rid:
            satiety = max(0.3, satiety)  # generalist floor
        rec["perch_seconds"] = round(max(2.0, base_p * (1.5 - satiety)), 2)
        rec["forage_seconds"] = round(max(2.0, base_f * (0.5 + satiety)), 2)
        rec["intake_basis_prey_per_h"] = round(intake, 4)
        if consumer in basis_by_consumer:
            rec["intake_basis"] = basis_by_consumer[consumer]
    return out


def daily_trace(patch: dict, weather: dict, wind_mps: float = 0.0,
                flowering: float = 0.5) -> list:
    """Hourly activity proving overcast+wind -> inactive, calm sun -> hover."""
    if not isinstance(patch, dict):
        raise ValueError("patch must be a mapping")
    if not isinstance(weather, dict):
        raise ValueError("weather must be a mapping")
    wind_mps = _nonnegative("wind_mps", wind_mps)
    flowering = _unit_interval("flowering", flowering)
    out = []
    for h in range(24):
        sun = sunlight(h)
        a = insect_activity(sun=sun, air_c=7.0 + 15.0 * sun,
                            cloud=_finite("cloud", float(weather.get("cloud", 0.16))),
                            moisture=_finite("moisture", float(patch.get("moisture", 0.6))),
                            resource=_finite("resource", float(patch.get("insect_resource", 0.8))),
                            wind_mps=wind_mps, flowering=flowering)
        out.append({"hour": h, "activity": round(a, 4),
                    "state": foraging_state(a)})
    return out
