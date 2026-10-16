"""Environmental forcing for authored mammal ecology at physical simulation time."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import copy

from yellowstone_python.common.checks import finite, fraction, nonnegative
from yellowstone_python.insects_birds import sunlight


def environmental_forcing(patches, weather, epoch_unix, *, utc_offset_hours=-6.0):
    """Map current patch and weather states to dimensionless mammal drivers."""
    epoch = finite("mammal epoch_unix", epoch_unix)
    offset = finite("mammal utc_offset_hours", utc_offset_hours, minimum=-14, maximum=14)
    local = datetime.fromtimestamp(epoch, timezone.utc) + timedelta(hours=offset)
    hour = local.hour + local.minute / 60 + local.second / 3600 + local.microsecond / 3.6e9
    start = datetime(local.year, 1, 1, tzinfo=timezone.utc)
    stop = datetime(local.year + 1, 1, 1, tzinfo=timezone.utc)
    phase = (local - start).total_seconds() / (stop - start).total_seconds()
    rows = {}
    for patch in patches:
        pid = str(patch["id"])
        if pid in rows:
            raise ValueError(f"duplicate mammal forcing patch {pid}")
        capacity = nonnegative(f"{pid}.capacity", patch.get("capacity", 1.0))
        biomass = nonnegative(f"{pid}.biomass", patch.get("biomass", 0.0))
        rows[pid] = {
            "habitat": patch.get("habitat", "unavailable"),
            "biomass": biomass,
            "capacity": capacity,
            "forage_fraction": min(1.0, biomass / capacity) if capacity else 0.0,
            "water_fraction": fraction(f"{pid}.moisture", patch.get("moisture", 0.0)),
            "snow_m": nonnegative(f"{pid}.snow_depth_m", patch.get("snow_depth_m", 0.0)),
            "soil_temperature_c": finite(f"{pid}.soil_temperature_c", patch.get("soil_temperature_c", 7.0)),
            "insect_fraction": min(1.0, nonnegative(f"{pid}.insect_activity", patch.get("insect_activity", 0.0))),
        }
    return {
        "epoch_unix": epoch,
        "local_hour": hour,
        "air_c": finite("mammal air_c", weather.get("air_c", weather.get("air_temperature_c", 18.0))),
        "snow_m": max((row["snow_m"] for row in rows.values()), default=0.0),
        "season_phase": phase,
        "daylight_fraction": sunlight(hour),
        "by_patch": rows,
        "status": "derived_from_simulation_states",
        "resource_units": "relative indices; water_fraction is soil moisture, not surveyed drinking-water access",
    }


def apply_consumption(patches, consumption_by_patch):
    """Remove allocated mammal forage once, retaining a normalized-stock ledger."""
    by_id = {str(patch["id"]): patch for patch in patches}
    if len(by_id) != len(patches) or set(consumption_by_patch) - set(by_id):
        raise ValueError("mammal consumption requires unique known patch IDs")
    amounts = {}
    initial = 0.0
    for pid, patch in by_id.items():
        stock = nonnegative(f"{pid}.biomass", patch.get("biomass", 0.0))
        amount = nonnegative(f"{pid}.mammal_consumption", consumption_by_patch.get(pid, 0.0))
        if amount > stock + 1e-12:
            raise ValueError(f"mammal consumption exceeds patch {pid} biomass")
        amounts[pid] = min(amount, stock)
        initial += stock
    updated = copy.deepcopy(patches)
    for patch in updated:
        patch["biomass"] = max(0.0, float(patch.get("biomass", 0.0)) - amounts[str(patch["id"])])
    final = sum(patch["biomass"] for patch in updated)
    removed = sum(amounts.values())
    return updated, {"initial_biomass_index": initial, "consumed_biomass_index": removed,
                     "final_biomass_index": final, "residual": final - initial + removed,
                     "units": "authored normalized vegetation biomass index"}
