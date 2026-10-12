"""Three-compartment prey + bird diets."""
from __future__ import annotations

import copy
import math

HOVER_THRESHOLD = 0.035  # wildlife_actor.gd::_update_insects (legacy interface)


def sunlight(hour: float) -> float:
    return max(0.0, math.sin((float(hour) - 6.0) * math.pi / 12.0))


def wind_factor(wind_mps: float) -> float:
    """Exposed insects suppress flight in wind; calm → 1."""
    return math.exp(-max(0.0, float(wind_mps)) / 8.0)


def flowering_factor(stage: float) -> float:
    """0 = no bloom, 1 = full bloom; food baseline 0.5 even without bloom."""
    s = min(1.0, max(0.0, float(stage)))
    return 0.5 + 0.5 * s


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
    return "hover" if float(activity) > HOVER_THRESHOLD else "inactive"


def bird_timing(activity: float, base_perch_s: float,
                base_forage_s: float) -> tuple[float, float]:
    """High activity → shorter perch, longer forage bout (bounded)."""
    a = min(1.0, max(0.0, float(activity)))
    perch = float(base_perch_s) * (1.5 - a)
    forage = float(base_forage_s) * (0.5 + a)
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


def update_wildlife(wildlife: list, activity_by_patch: dict) -> list:
    """Retune dipper/raven cadence from shared activity. Kept because wildlife_actor.gd reads timer values from records. Prefer update_wildlife_from_intake() for intake-driven timing."""
    out = copy.deepcopy(wildlife)
    for rec in out:
        if rec.get("id") not in ("dipper_01", "raven_01"):
            continue
        a = activity_by_patch.get(rec.get("patch_id", ""), 0.0)
        perch, forage = bird_timing(a, rec.get("perch_seconds", 12.0),
                                    rec.get("forage_seconds", 18.0))
        rec["perch_seconds"] = round(perch, 2)
        rec["forage_seconds"] = round(forage, 2)
        rec["activity_basis"] = round(a, 4)
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
                    t_cutoff: float | None = None) -> tuple[float, float]:
    """Benthic larvae degree-day development to emergence flux."""
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
    nb2 = nb - emergence
    nb2 *= max(0.0, 1.0 - float(disturbance))
    hours = dt_s / 3600.0
    nb2 = min(capacity, nb2 + 0.01 * (1.0 - nb2 / capacity) * hours)
    return (max(0.0, nb2), emergence)


PREY_COMPARTMENTS = frozenset({
    "terrestrial", "benthic", "emergent",
})


def _finite(name: str, value):
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _nonnegative(name: str, value):
    value = _finite(name, value)
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _positive(name: str, value):
    value = _finite(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def _unit_interval(name: str, value):
    value = _finite(name, value)
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be in [0, 1]")
    return value


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


# Benthic insect groups: transferred thermal structure. Relative rates (dipteran faster, multivoltine) are an authored ordering.
INSECT_GROUPS = {
    "ept": {  # mayfly/stonefly/caddis proxy: cold fauna
        "tbase_c": 2.0, "rate_per_dd": 0.012, "t_cutoff_c": 22.0,
        "status": "transferred_structure_authored_rates",
        "sources": [
            "Kaeding & Kaya 1978 (cold-station benthic EPT diets)",
            "Mackey 1977 (developmental zeroes down to ~2 C)",
            "Benton 1987 (Ameletus development at 5-15 C)",
            "Sweeney & Vannote 1981 (thermal equilibrium hypothesis)",
        ],
    },
    "dipteran": {  # chironomid proxy: warm-tolerant, fast
        "tbase_c": 8.0, "rate_per_dd": 0.030, "t_cutoff_c": 30.0,
        "status": "transferred_structure_authored_rates",
        "sources": [
            "Kaeding & Kaya 1978 (warm-station dipteran diets)",
            "Maier et al. 1990 (lower limit 8-10 C, optimum ~20 C, "
            "upper tolerance 28-30 C)",
            "Mackey 1977 (lotic chironomid zeroes 2.4-9.7 C)",
        ],
    },
}


def trout_diet_at_temp(water_c: float) -> dict[str, float]:
    """Trout benthic-vs-emergent shares shift with temperature. Cold water: almost entirely benthic; warm water: heavily emerging (Kaeding & Kaya 1978). Linear transition 15 -> 21 C; shape authored, endpoints transferred. Molluscs not modeled."""
    t = float(water_c)
    frac = min(1.0, max(0.0, (t - 15.0) / (21.0 - 15.0)))
    return {"emergent": 0.2 + 0.5 * frac, "benthic": 0.8 - 0.5 * frac}


def step_compartments(state: dict, forcing: dict, dt_s: float,
                      consumers: dict | None = None) -> tuple[dict, dict]:
    """Advance {Nt, Nb, Ne} one step. forcing: sun/air/cloud/moisture/wind/
    flowering/water_c/disturbance. consumers: {dipper:{a,h,share}, ...}.
    Returns (new_state, ledger{emergence, consumed_by, activity})."""
    f = forcing
    sun = float(f.get("sun", 0.5))
    bloom = 0.5 + 0.5 * min(1.0, max(0.0, float(f.get("flowering", 0.5))))
    nt = max(0.0, float(state.get("Nt", 0.5)))
    hours = dt_s / 3600.0
    nt += (0.05 * sun * bloom * nt * (1.0 - nt) - 0.01 * nt) * hours
    nb, emergence = develop_benthic(
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
    ne *= math.exp(-max(0.0, float(f.get("wind_mps", 0.0))) / 8.0 * hours)
    new_state = {"Nt": round(max(0.0, nt), 6), "Nb": round(max(0.0, nb), 6),
                 "Ne": round(max(0.0, ne), 6)}
    activity = insect_activity(
        sun=sun, air_c=float(f.get("air_c", 15.0)),
        cloud=float(f.get("cloud", 0.2)), moisture=float(f.get("moisture", 0.6)),
        resource=new_state["Nt"], wind_mps=float(f.get("wind_mps", 0.0)),
        flowering=float(f.get("flowering", 0.5)))
    ledger = {"emergence": round(emergence, 6), "consumed_by": consumed_by,
              "activity": round(activity, 4),
              "state": foraging_state(activity)}
    return new_state, ledger


DEFAULT_DIETS = {
    # Dipper: benthic wading + emergent aerial; trout: emergent/drift;
    # raven: generalist background (never reducible to the insect signal).
    "dipper": {"a": 1.2, "h": 0.4, "diet": {"benthic": 0.7, "emergent": 0.3}},
    "trout": {"a": 1.0, "h": 0.5, "diet": {"emergent": 0.6, "benthic": 0.4}},
    "raven": {"a": 0.4, "h": 0.8, "diet": {"terrestrial": 0.6, "emergent": 0.4}},
}


def update_wildlife_from_intake(wildlife: list, intake_by_id: dict,
                                basis_by_consumer: dict | None = None) -> list:
    """Bout timing from Holling intake rate (satiation shortens foraging).
    intake_by_id: consumer id → prey/hour. Raven floor: generalist diet keeps
    a baseline bout regardless of insect intake."""
    basis_by_consumer = basis_by_consumer or {}
    out = copy.deepcopy(wildlife)
    for rec in out:
        rid = rec.get("id")
        if rid not in ("dipper_01", "raven_01"):
            continue
        consumer = "dipper" if "dipper" in rid else "raven"
        intake = float(intake_by_id.get(consumer, 0.0))
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
    """Hourly activity proving overcast+wind → inactive, calm sun → hover."""
    out = []
    for h in range(24):
        sun = sunlight(h)
        a = insect_activity(sun=sun, air_c=7.0 + 15.0 * sun,
                            cloud=weather.get("cloud", 0.16),
                            moisture=patch.get("moisture", 0.6),
                            resource=patch.get("insect_resource", 0.8),
                            wind_mps=wind_mps, flowering=flowering)
        out.append({"hour": h, "activity": round(a, 4),
                    "state": foraging_state(a)})
    return out
