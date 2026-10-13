I’ll start with **`river_world.py`**. The main goals are:

- Make a full UTC timestamp authoritative for the replay.
- Preserve local timezone metadata separately.
- Generate weather on the physical simulation clock.
- Support scheduled air-temperature and source-temperature forcing.
- Reject malformed or ambiguous input early.
- Preserve exact forcing provenance in the replay document.
- Avoid silently treating unsupported scheduled flow as constant flow.

The changes below are intended as replacements/additions, not a complete reprint of the large file.

---

# 1. Add timestamp imports

Replace:

```python
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
from typing import Any
```

with:

```python
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any
```

---

# 2. Add timestamp and validation helpers

Add these after `SCHEMA`:

```python
UTC = timezone.utc

SUPPORTED_TIME_KEYS = (
    "simulation_start_utc",
    "simulation_start_epoch_unix",
)


def _finite_optional(value: Any, name: str) -> float | None:
    if value is None:
        return None
    return finite(value, name)


def parse_simulation_start(
    *,
    simulation_start_utc: Any = None,
    simulation_start_epoch_unix: Any = None,
) -> datetime:
    """Return an aware UTC datetime for the replay start.

    Exactly one timestamp representation may be provided. Naive ISO strings
    are rejected because they are ambiguous for astronomy and weather lookup.
    """
    if (
        simulation_start_utc is not None
        and simulation_start_epoch_unix is not None
    ):
        raise ValueError(
            "provide only one of simulation_start_utc or "
            "simulation_start_epoch_unix"
        )

    if simulation_start_epoch_unix is not None:
        epoch = finite(
            simulation_start_epoch_unix,
            "simulation_start_epoch_unix",
            0.0,
        )
        return datetime.fromtimestamp(epoch, tz=UTC)

    if simulation_start_utc is None:
        raise ValueError(
            "simulation start requires simulation_start_utc or "
            "simulation_start_epoch_unix"
        )

    if not isinstance(simulation_start_utc, str):
        raise ValueError("simulation_start_utc must be an ISO-8601 string")

    text = simulation_start_utc.strip()
    if not text:
        raise ValueError("simulation_start_utc must not be empty")

    # Accept the common JSON form ending in Z.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            "simulation_start_utc must be a valid ISO-8601 timestamp"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            "simulation_start_utc must include a timezone, for example "
            "2026-07-15T22:20:00Z"
        )

    return parsed.astimezone(UTC)


def timestamp_metadata(start: datetime, duration_s: float) -> dict[str, Any]:
    """Serialize the authoritative replay time range."""
    start = start.astimezone(UTC)
    end_epoch = start.timestamp() + duration_s
    end = datetime.fromtimestamp(end_epoch, tz=UTC)

    return {
        "start_epoch_unix": start.timestamp(),
        "end_epoch_unix": end.timestamp(),
        "start_utc": start.isoformat().replace("+00:00", "Z"),
        "end_utc": end.isoformat().replace("+00:00", "Z"),
        "timezone": "UTC",
    }


def validate_duration_and_step(
    duration_s: Any,
    dt_s: Any,
    sample_s: Any,
) -> tuple[float, float, float]:
    duration = positive(duration_s, "duration_s")
    dt = positive(dt_s, "dt_s")
    sample = positive(sample_s, "sample_s")

    if not math.isfinite(duration + dt + sample):
        raise ValueError("duration and timestep values must be finite")

    # The transport solver supports a final partial step, but a sample interval
    # must still be meaningful.
    if sample < dt:
        raise ValueError(
            "sample_s must be greater than or equal to dt_s"
        )

    return duration, dt, sample
```

## Why this matters

The existing code has no complete date. It only has:

```python
clock_hour
day_of_year
```

That is insufficient for:

- replaying across midnight;
- leap years;
- exact weather timestamps;
- daylight-saving metadata;
- matching river forcing to the sky;
- correctly identifying a snapshot’s valid time.

The replay should have one authoritative UTC start time.

---

# 3. Add strict ISO timestamp configuration support

Inside `build_mapped_replay()`, add a new argument:

```python
simulation_start_utc: Any = None,
simulation_start_epoch_unix: Any = None,
```

The function signature becomes:

```python
def build_mapped_replay(
    world: dict,
    ecosystem: dict,
    *,
    duration_s: float = 7200.0,
    maximum_cell_m: float = 20.0,
    depth_m: float = 1.1,
    dispersion_m2_s: float = 1.0,
    exchange_w_m2_k: float = 12.0,
    dt_s: float = 2.0,
    sample_s: float = 10.0,
    pulse_source: str = "",
    pulse_start_s: float = 300.0,
    pulse_end_s: float = 900.0,
    pulse_delta_c: float = 18.0,
    reach_anchors: dict[str, dict] | None = None,
    cross_sections: dict[str, dict] | None = None,
    energy_budget: bool = False,
    bank_slope_zh: float = DEFAULT_BANK_SLOPE_ZH,
    manning_n: float = DEFAULT_MANNING_N,
    simulation_start_utc: Any = None,
    simulation_start_epoch_unix: Any = None,
) -> dict[str, Any]:
```

At the start of the function, replace:

```python
duration_s = positive(duration_s, "duration")
depth_m = positive(depth_m, "assumed mean depth")
dispersion_m2_s = finite(dispersion_m2_s, "dispersion", 0.0)
exchange_w_m2_k = finite(exchange_w_m2_k, "exchange", 0.0)
bank_slope_zh = finite(bank_slope_zh, "bank_slope_zh", 0.0)
manning_n = positive(manning_n, "manning_n")
```

with:

```python
duration_s, dt_s, sample_s = validate_duration_and_step(
    duration_s,
    dt_s,
    sample_s,
)

maximum_cell_m = positive(
    maximum_cell_m,
    "maximum_cell_m",
)

depth_m = positive(
    depth_m,
    "assumed mean depth",
)

dispersion_m2_s = finite(
    dispersion_m2_s,
    "dispersion",
    0.0,
)

exchange_w_m2_k = finite(
    exchange_w_m2_k,
    "exchange",
    0.0,
)

bank_slope_zh = finite(
    bank_slope_zh,
    "bank_slope_zh",
    0.0,
)

manning_n = positive(
    manning_n,
    "manning_n",
)

simulation_start = parse_simulation_start(
    simulation_start_utc=simulation_start_utc,
    simulation_start_epoch_unix=simulation_start_epoch_unix,
)
```

---

# 4. Validate the main input documents

Add this helper:

```python
def validate_mapped_inputs(
    world: dict,
    ecosystem: dict,
) -> None:
    if not isinstance(world, dict):
        raise ValueError("world must be a JSON object")

    if not isinstance(ecosystem, dict):
        raise ValueError("ecosystem must be a JSON object")

    if not isinstance(world.get("rivers"), list):
        raise ValueError("world.rivers must be a list")

    if not isinstance(ecosystem.get("river_reaches"), list):
        raise ValueError("ecosystem.river_reaches must be a list")

    for key in ("boundary_m3s", "boundary_c"):
        if key not in ecosystem:
            raise ValueError(
                f"ecosystem requires {key!r}"
            )

    finite(
        ecosystem["boundary_m3s"],
        "ecosystem boundary_m3s",
        0.0,
    )
    finite(
        ecosystem["boundary_c"],
        "ecosystem boundary_c",
    )

    reach_ids: set[str] = set()

    for index, reach in enumerate(ecosystem["river_reaches"]):
        if not isinstance(reach, dict):
            raise ValueError(
                f"river_reaches[{index}] must be an object"
            )

        reach_id = reach.get("id")
        if not isinstance(reach_id, str) or not reach_id.strip():
            raise ValueError(
                f"river_reaches[{index}] requires a nonempty id"
            )

        if reach_id in reach_ids:
            raise ValueError(
                f"duplicate ecosystem river reach id {reach_id!r}"
            )

        reach_ids.add(reach_id)

        lateral_sources = reach.get("lateral_sources", [])
        if not isinstance(lateral_sources, list):
            raise ValueError(
                f"reach {reach_id!r}.lateral_sources must be a list"
            )

        for source_index, source in enumerate(lateral_sources):
            validate_source_record(
                source,
                f"reach {reach_id!r}.lateral_sources[{source_index}]",
            )


def validate_source_record(
    source: Any,
    location: str,
) -> None:
    if not isinstance(source, dict):
        raise ValueError(f"{location} must be an object")

    for key in ("id", "flow_m3s", "temperature_c"):
        if key not in source:
            raise ValueError(
                f"{location} requires {key!r}"
            )

    source_id = source["id"]
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError(f"{location}.id must be nonempty")

    flow = source["flow_m3s"]

    # River transport currently assumes constant lateral discharge.
    # Do not silently accept a flow schedule and use only one value.
    if isinstance(flow, dict):
        raise ValueError(
            f"{location}.flow_m3s cannot be scheduled yet; "
            "river_transport currently derives fixed face flows at "
            "initialization"
        )

    finite(flow, f"{location}.flow_m3s", 0.0)

    # Series.parse performs the detailed schedule validation.
    Series.parse(source["temperature_c"])
```

Call it immediately after parsing/validating the function arguments:

```python
validate_mapped_inputs(world, ecosystem)
```

This catches malformed source records before `source_connection()` produces a less useful `KeyError`.

---

# 5. Support scheduled source temperatures

The current code contains:

```python
temperature = finite(source["temperature_c"], "entry temperature")
forcing: Any = temperature
```

That rejects a valid scheduled temperature object.

Replace the entire source-temperature portion with:

```python
base_temperature = Series.parse(source["temperature_c"])
forcing: Any = {
    "times_s": list(base_temperature.times_s),
    "values": list(base_temperature.values),
}
```

For a pulse, use a helper that preserves schedules.

Add:

```python
def add_temperature_pulse(
    series: Series,
    start_s: float,
    end_s: float,
    delta_c: float,
) -> Series:
    """Add a temporary temperature offset to an existing Series.

    The source temperature is treated as right-continuous and piecewise
    constant. New breakpoints are inserted at the pulse boundaries.
    """
    if not 0.0 < start_s < end_s:
        raise ValueError(
            "temperature pulse requires 0 < start_s < end_s"
        )

    delta_c = finite(delta_c, "pulse temperature change")

    breakpoints = sorted(set(
        [0.0, start_s, end_s, *series.times_s]
    ))

    values: list[float] = []

    for time_s in breakpoints:
        base = series.at(time_s)
        active = start_s <= time_s < end_s
        values.append(base + delta_c if active else base)

    return Series(
        tuple(breakpoints),
        tuple(values),
    )
```

Then replace the pulse logic:

```python
if source["id"] == pulse_source:
    forcing = {
        "times_s": [0.0, pulse_start_s, pulse_end_s],
        "values": [
            temperature,
            temperature + pulse_delta_c,
            temperature,
        ],
    }
```

with:

```python
if source["id"] == pulse_source:
    base_temperature = add_temperature_pulse(
        base_temperature,
        pulse_start_s,
        pulse_end_s,
        pulse_delta_c,
    )

forcing = {
    "times_s": list(base_temperature.times_s),
    "values": list(base_temperature.values),
}
```

The complete loop should look like:

```python
solver_sources = []

for source, connection in zip(sources, connections):
    location = connection["s_m"]

    if location >= channel.length_m:
        raise ValueError(
            f"lateral source {source['id']!r} cannot enter "
            "after the last cell"
        )

    index = bisect_right(faces, location) - 1

    base_temperature = Series.parse(
        source["temperature_c"]
    )

    if source["id"] == pulse_source:
        base_temperature = add_temperature_pulse(
            base_temperature,
            pulse_start_s,
            pulse_end_s,
            pulse_delta_c,
        )

    solver_sources.append({
        "id": source["id"],
        "cell_id": cells[index]["id"],
        "flow_m3_s": finite(
            source["flow_m3s"],
            f"{source['id']} lateral flow",
            0.0,
        ),
        "temperature_c": {
            "times_s": list(base_temperature.times_s),
            "values": list(base_temperature.values),
        },
        "status": (
            "illustrative_river_entry_forcing_not_measured"
        ),
    })

    connection["receiving_cell_id"] = cells[index]["id"]
```

This now supports:

```json
{
  "temperature_c": {
    "times_s": [0, 1800, 3600],
    "values": [62, 80, 62]
  }
}
```

and can apply an additional intervention pulse to it.

---

# 6. Replace `physical_weather()`

The current implementation uses only synthetic weather:

```python
night_air_c + day_warming_c * sin(...)
```

It should support either:

1. explicitly scheduled air temperature; or
2. the existing synthetic approximation.

Replace the function with:

```python
def _forcing_series_from_weather(
    weather: dict,
    key: str,
    *,
    default: Any,
    name: str,
) -> Series:
    """Read a scalar or {times_s, values} weather forcing."""
    if key not in weather:
        return Series.parse(default)

    value = weather[key]

    if isinstance(value, dict):
        return Series.parse(value)

    return Series.parse(finite(value, name))


def _weather_times(
    duration_s: float,
    interval_s: float,
) -> list[float]:
    duration_s = finite(duration_s, "weather duration", 0.0)
    interval_s = positive(interval_s, "weather interval")

    times: list[float] = []
    time_s = 0.0

    while time_s < duration_s:
        times.append(time_s)
        next_time = time_s + interval_s

        if next_time <= time_s:
            raise ArithmeticError(
                "weather clock failed to advance"
            )

        time_s = next_time

    if not times:
        times.append(0.0)

    if not math.isclose(times[-1], duration_s):
        times.append(duration_s)
    else:
        times[-1] = duration_s

    return times


def physical_weather(
    ecosystem: dict,
    duration_s: float,
    interval_s: float = 60.0,
) -> tuple[Series, list[dict[str, Any]]]:
    """Build air-temperature and wind forcing on the physical clock.

    If weather.air_temperature_c is a scalar or Series-like object, it is
    used directly. Otherwise the legacy authored diurnal approximation is
    used.

    Scheduled values are right-continuous, matching river_transport.Series.
    """
    duration_s = finite(
        duration_s,
        "weather duration",
        0.0,
    )
    interval_s = positive(
        interval_s,
        "weather interval",
    )

    weather = ecosystem.get("weather", {})
    if not isinstance(weather, dict):
        raise ValueError("ecosystem.weather must be an object")

    hour0 = finite(
        ecosystem.get("clock_hour", 16.2),
        "clock_hour",
    )

    if not 0.0 <= hour0 < 24.0:
        raise ValueError("clock_hour must be in [0, 24)")

    times = _weather_times(duration_s, interval_s)

    scheduled_air: Series | None = None

    if "air_temperature_c" in weather:
        scheduled_air = Series.parse(
            weather["air_temperature_c"]
        )

    night = finite(
        weather.get("night_air_c", 7.0),
        "night air",
    )
    warming = finite(
        weather.get("day_warming_c", 15.0),
        "day warming",
    )

    wind_value = weather.get(
        "wind_xz_mps",
        [1.8, 0.6],
    )

    if (
        not isinstance(wind_value, (list, tuple))
        or len(wind_value) != 2
    ):
        raise ValueError(
            "weather.wind_xz_mps must be a two-element vector"
        )

    wx, wz = (
        finite(wind_value[0], "base wind x"),
        finite(wind_value[1], "base wind z"),
    )

    gust = finite(
        weather.get("gust_mps", 0.45),
        "gust",
        0.0,
    )

    records: list[dict[str, Any]] = []
    temperatures: list[float] = []

    for time_s in times:
        hour = (hour0 + time_s / 3600.0) % 24.0

        if scheduled_air is not None:
            air = scheduled_air.at(time_s)
            air_source = "scheduled_weather.air_temperature_c"
        else:
            sun = max(
                0.0,
                math.sin((hour - 6.0) * math.pi / 12.0),
            )
            air = night + warming * sun
            air_source = "authored_diurnal_approximation"

        # Existing authored wind behavior, sampled on the physical clock.
        wind_x = wx + gust * math.sin(time_s / 61.0)
        wind_z = wz + gust * math.cos(time_s / 87.0)

        air = finite(air, "weather air temperature")
        temperatures.append(air)

        records.append({
            "t_s": time_s,
            "hour": hour,
            "air_c": air,
            "air_source": air_source,
            "wind_xz_mps": [wind_x, wind_z],
        })

    return (
        Series(tuple(times), tuple(temperatures)),
        records,
    )
```

## Important behavior

A scheduled weather input such as:

```json
"weather": {
  "air_temperature_c": {
    "times_s": [0, 1800, 3600],
    "values": [4.0, 12.0, 6.0]
  }
}
```

now becomes a true solver forcing schedule.

---

# 7. Make the explicit weather budget use the same schedule

Replace `energy_met_series()` with:

```python
def energy_met_series(
    ecosystem: dict,
    duration_s: float,
    interval_s: float = 60.0,
    weather_records: list[dict[str, Any]] | None = None,
) -> dict:
    """Build explicit surface-budget met forcing.

    Scheduled humidity, wind speed, shortwave, and cloud values are honored
    when supplied. Missing fields retain the authored fallback behavior.
    """
    from .surface_flux import spec_from_series

    duration_s = finite(
        duration_s,
        "meteorology duration",
        0.0,
    )
    interval_s = positive(
        interval_s,
        "meteorology interval",
    )

    weather = ecosystem.get("weather", {})
    if not isinstance(weather, dict):
        raise ValueError("ecosystem.weather must be an object")

    hour0 = finite(
        ecosystem.get("clock_hour", 16.2),
        "clock_hour",
    )

    if not 0.0 <= hour0 < 24.0:
        raise ValueError("clock_hour must be in [0, 24)")

    if weather_records is None:
        _, weather_records = physical_weather(
            ecosystem,
            duration_s,
            interval_s,
        )

    if not weather_records:
        raise ValueError("weather_records must not be empty")

    times = tuple(
        finite(record["t_s"], "weather record time", 0.0)
        for record in weather_records
    )

    if times[0] != 0.0:
        raise ValueError(
            "weather records must begin at t=0"
        )

    if any(
        later <= earlier
        for earlier, later in zip(times, times[1:])
    ):
        raise ValueError(
            "weather record times must be strictly increasing"
        )

    humidity_series = _forcing_series_from_weather(
        weather,
        "relative_humidity",
        default=weather.get("humidity", 0.45),
        name="relative humidity",
    )

    cloud_series = _forcing_series_from_weather(
        weather,
        "cloud_fraction",
        default=weather.get("cloud", 0.16),
        name="cloud fraction",
    )

    wind_speed_series = _forcing_series_from_weather(
        weather,
        "wind_speed_mps",
        default=None,
        name="wind speed",
    )

    if "wind_speed_mps" in weather:
        wind_values = [
            wind_speed_series.at(time_s)
            for time_s in times
        ]
    else:
        wind_values = [
            math.hypot(
                record["wind_xz_mps"][0],
                record["wind_xz_mps"][1],
            )
            for record in weather_records
        ]

    shortwave_default = finite(
        weather.get("sw_noon_w_m2", 700.0),
        "sw_noon_w_m2",
        0.0,
    )

    if "shortwave_w_m2" in weather:
        shortwave_series = _forcing_series_from_weather(
            weather,
            "shortwave_w_m2",
            default=0.0,
            name="shortwave_w_m2",
        )
        shortwave_values = [
            shortwave_series.at(time_s)
            for time_s in times
        ]
    else:
        shortwave_values = []

        for time_s in times:
            hour = (hour0 + time_s / 3600.0) % 24.0
            sun = max(
                0.0,
                math.sin((hour - 6.0) * math.pi / 12.0),
            )
            shortwave_values.append(
                shortwave_default * sun ** 1.2
            )

    humidity_values = [
        humidity_series.at(time_s)
        for time_s in times
    ]

    cloud_values = [
        cloud_series.at(time_s)
        for time_s in times
    ]

    return spec_from_series(
        Series(tuple(times), tuple(humidity_values)),
        Series(tuple(times), tuple(wind_values)),
        Series(tuple(times), tuple(shortwave_values)),
        Series(tuple(times), tuple(cloud_values)),
    )
```

This allows weather configurations such as:

```json
"weather": {
  "relative_humidity": {
    "times_s": [0, 1800],
    "values": [0.45, 0.85]
  },
  "wind_speed_mps": {
    "times_s": [0, 1800],
    "values": [2.0, 8.0]
  },
  "cloud_fraction": {
    "times_s": [0, 1800],
    "values": [0.1, 0.9]
  },
  "shortwave_w_m2": {
    "times_s": [0, 1800],
    "values": [650.0, 100.0]
  }
}
```

---

# 8. Add timestamps to the generated replay config

After creating the simulation start:

```python
simulation_start = parse_simulation_start(...)
```

create:

```python
simulation_time = timestamp_metadata(
    simulation_start,
    duration_s,
)
```

Then add this to `config`:

```python
config = {
    "status": "mapped_illustrative_model_not_calibrated",

    "simulation_start_utc": simulation_time["start_utc"],
    "simulation_start_epoch_unix": (
        simulation_time["start_epoch_unix"]
    ),

    "boundary_m3_s": ecosystem["boundary_m3s"],
    "boundary_c": ecosystem["boundary_c"],
    ...
}
```

Also add the timestamp range to the returned document:

```python
document.update({
    "simulation_time": simulation_time,
    ...
})
```

The resulting document will contain:

```json
"simulation_time": {
  "start_epoch_unix": 1784154000.0,
  "end_epoch_unix": 1784161200.0,
  "start_utc": "2026-07-15T22:20:00Z",
  "end_utc": "2026-07-16T00:20:00Z",
  "timezone": "UTC"
}
```

This is the timestamp that should also drive:

- Godot solar position;
- star position;
- Moon/planet position;
- weather snapshot matching;
- river forcing;
- hydrology replay.

---

# 9. Include timestamped weather provenance

Add to `parameter_notes`:

```python
"simulation_time": {
    "authority": "UTC epoch timestamp",
    "start_utc": simulation_time["start_utc"],
    "end_utc": simulation_time["end_utc"],
    "weather_clock": "physical seconds from replay start",
    "scheduled_forcing": (
        "Right-continuous piecewise-constant Series; "
        "integration splits at forcing changes."
    ),
},
```

Add to the document:

```python
document["weather_forcing"] = {
    "records": weather_records,
    "air_temperature": {
        "times_s": list(air.times_s),
        "values": list(air.values),
    },
}
```

If using the explicit budget, also include:

```python
if budget_spec is not None:
    document["weather_forcing"]["surface_budget"] = budget_spec
```

This makes the final replay self-describing rather than requiring reconstruction from the source ecosystem file.

---

# 10. Update `make_replay()` metadata

In `river_transport.py`, `make_replay()` currently derives:

```python
explicit_budget = "surface_budget" in config
```

For the new mapped config, use:

```python
explicit_budget = (
    config.get("surface_budget") is not None
)
```

Also include the simulation timestamps:

```python
simulation_time = {}

if (
    "simulation_start_epoch_unix" in config
    and "duration_s" in config
):
    start_epoch = finite(
        config["simulation_start_epoch_unix"],
        "simulation_start_epoch_unix",
        0.0,
    )
    simulation_time = timestamp_metadata(
        datetime.fromtimestamp(start_epoch, tz=UTC),
        finite(config["duration_s"], "duration_s", 0.0),
    )
```

Then add:

```python
"simulation_time": simulation_time,
```

to the replay result.

If you want to avoid importing timestamp helpers from `river_world.py`, move the common timestamp utility to a small module such as:

```text
yellowstone_python/time_utils.py
```

That is preferable to creating a circular import.

---

# 11. Add CLI arguments

Add these arguments in `main()`:

```python
parser.add_argument(
    "--simulation-start-utc",
    default=None,
    help=(
        "Replay start as timezone-aware ISO-8601 UTC timestamp, "
        "for example 2026-07-15T22:20:00Z"
    ),
)

parser.add_argument(
    "--simulation-start-epoch",
    type=float,
    default=None,
    help="Replay start as Unix seconds since 1970-01-01 UTC",
)
```

Pass them into `build_mapped_replay()`:

```python
simulation_start_utc=args.simulation_start_utc,
simulation_start_epoch_unix=args.simulation_start_epoch,
```

Reject both automatically through `parse_simulation_start()`.

Example:

```bash
python -m yellowstone_python.river_world \
  --world data/world.json \
  --ecosystem data/ecosystem.json \
  --simulation-start-utc 2026-07-15T22:20:00Z \
  --duration 7200 \
  --out derived/firehole_control.json
```

---

# 12. Improve `feature_at()`

The existing method can map invalid chainages to the first or last feature. Replace:

```python
def feature_at(self, s_m: float) -> dict:
    index = min(
        bisect_right(self._feature_ends, s_m),
        len(self._feature_records) - 1,
    )
    return self._feature_records[index]
```

with:

```python
def feature_at(self, s_m: float) -> dict:
    s_m = finite(s_m, "chainage", 0.0)

    if s_m > self.length_m:
        raise ValueError(
            f"chainage {s_m} exceeds channel length {self.length_m}"
        )

    index = bisect_right(self._feature_ends, s_m)

    if index >= len(self._feature_records):
        index = len(self._feature_records) - 1

    return self._feature_records[index]
```

Also make feature ordering explicit in `Channel.__init__()`:

```python
self._feature_records = sorted(
    self.features.values(),
    key=lambda record: record["start_s_m"],
)

self._feature_ends = [
    record["end_s_m"]
    for record in self._feature_records
]
```

---

# 13. Validate weather ranges before creating a solver

Add:

```python
def validate_weather_configuration(
    ecosystem: dict,
) -> None:
    weather = ecosystem.get("weather", {})

    if not isinstance(weather, dict):
        raise ValueError("ecosystem.weather must be an object")

    for key, low, high in (
        ("humidity", 0.0, 1.0),
        ("cloud", 0.0, 1.0),
        ("gust_mps", 0.0, None),
        ("sw_noon_w_m2", 0.0, None),
    ):
        if key not in weather:
            continue

        value = weather[key]

        if isinstance(value, dict):
            series = Series.parse(value)
            values = series.values
        else:
            values = (finite(value, f"weather.{key}"),)

        for item in values:
            if item < low:
                raise ValueError(
                    f"weather.{key} must be >= {low}"
                )
            if high is not None and item > high:
                raise ValueError(
                    f"weather.{key} must be <= {high}"
                )
```

Call:

```python
validate_weather_configuration(ecosystem)
```

after `validate_mapped_inputs()`.

Do the same for:

- scheduled air temperature;
- scheduled wind speed;
- scheduled shortwave;
- scheduled cloud;
- scheduled humidity.

---

# 14. Avoid silent source-flow semantics

`river_transport.River` calculates face discharge once:

```python
self._lateral_q = [
    math.fsum(s.flow_m3_s for s in group)
    for group in self._sources_by_cell
]
```

Therefore scheduled source flow cannot be added merely by changing `river_world.py`. It requires a larger transport change because changing flow affects:

- all downstream face flows;
- advection coefficients;
- water-volume budget;
- residence time;
- boundary/export terms;
- possibly the thermal storage interpretation.

For now, the safest behavior is the explicit rejection above:

```text
scheduled source flow is not supported yet
```

Scheduled source **temperature** is safe because the existing solver already supports `Series`.

---

# 15. Fix the weather/snapshot timestamp distinction

A weather snapshot should ideally contain both:

```json
{
  "generated_at_unix": 1784154100,
  "valid_time_unix": 1784154000
}
```

Use:

- `generated_at_unix`: when the snapshot file/API response was produced;
- `valid_time_unix`: the actual observation/forecast valid time.

For a replay, `river_world.py` should select weather values by:

```text
simulation_start_epoch_unix + forcing_time_s
```

not by file generation time.

Add to the replay output:

```python
"forcing_time_reference": {
    "start_epoch_unix": simulation_time["start_epoch_unix"],
    "meaning": (
        "Forcing schedule times are physical seconds after "
        "simulation_start_epoch_unix."
    ),
}
```

---

# 16. Add tests

## Timestamp parsing

```python
def test_parse_simulation_start_requires_timezone():
    with pytest.raises(ValueError):
        parse_simulation_start(
            simulation_start_utc="2026-07-15T22:20:00"
        )
```

```python
def test_parse_simulation_start_normalizes_to_utc():
    result = parse_simulation_start(
        simulation_start_utc="2026-07-15T16:20:00-06:00"
    )

    assert result.isoformat() == "2026-07-15T22:20:00+00:00"
```

## Weather endpoint coverage

```python
def test_weather_times_include_exact_final_time():
    assert _weather_times(125.0, 60.0) == [
        0.0,
        60.0,
        120.0,
        125.0,
    ]
```

## Scheduled air temperature

```python
def test_scheduled_air_temperature_is_used():
    ecosystem = {
        "clock_hour": 12.0,
        "weather": {
            "air_temperature_c": {
                "times_s": [0.0, 60.0],
                "values": [2.0, 12.0],
            }
        },
    }

    series, records = physical_weather(
        ecosystem,
        duration_s=120.0,
        interval_s=60.0,
    )

    assert series.at(0.0) == 2.0
    assert series.at(60.0) == 12.0
    assert records[-1]["t_s"] == 120.0
```

## Scheduled source temperature

```python
def test_temperature_pulse_preserves_scheduled_source():
    source = Series(
        (0.0, 100.0),
        (60.0, 70.0),
    )

    result = add_temperature_pulse(
        source,
        start_s=30.0,
        end_s=80.0,
        delta_c=10.0,
    )

    assert result.at(0.0) == 60.0
    assert result.at(30.0) == 70.0
    assert result.at(50.0) == 80.0
    assert result.at(80.0) == 70.0
```

## Unsupported scheduled flow

```python
def test_scheduled_source_flow_is_rejected():
    source = {
        "id": "source_a",
        "flow_m3s": {
            "times_s": [0.0, 60.0],
            "values": [1.0, 2.0],
        },
        "temperature_c": 20.0,
    }

    with pytest.raises(ValueError, match="cannot be scheduled"):
        validate_source_record(source, "test source")
```

---

# Required `ecosystem.json` shape

A new replay configuration could look like:

```json
{
  "simulation_start_utc": "2026-07-15T22:20:00Z",
  "boundary_m3s": 8.0,
  "boundary_c": 17.5,
  "clock_hour": 16.333333,
  "weather": {
    "air_temperature_c": {
      "times_s": [0, 1800, 3600, 7200],
      "values": [8.0, 12.0, 10.0, 6.0]
    },
    "relative_humidity": 0.55,
    "wind_speed_mps": {
      "times_s": [0, 1800, 3600],
      "values": [2.0, 5.0, 3.0]
    },
    "cloud_fraction": {
      "times_s": [0, 3600],
      "values": [0.15, 0.8]
    },
    "shortwave_w_m2": {
      "times_s": [0, 1800, 3600, 7200],
      "values": [650.0, 720.0, 500.0, 0.0]
    },
    "humidity": 0.55,
    "cloud": 0.15,
    "gust_mps": 0.45
  }
}
```

For a scheduled lateral temperature:

```json
{
  "id": "excelsior_aggregate_outflow",
  "flow_m3s": 0.252,
  "temperature_c": {
    "times_s": [0, 900, 1800],
    "values": [62.0, 80.0, 62.0]
  }
}
```

---

## Most important changes

If implementing incrementally, prioritize:

1. Require `simulation_start_utc`.
2. Add `simulation_time` to replay output.
3. Support scheduled source temperatures.
4. Support scheduled air temperature.
5. Include exact final forcing time.
6. Validate and reject scheduled source flow until `river_transport.py` supports dynamic hydraulics.
7. Make weather and astronomy consume the same simulation epoch.

The next file, `river_transport.py`, needs a coordinated change to ensure all explicit surface-budget series are included in forcing-change detection and to resolve the current linearized-versus-nonlinear energy-accounting mismatch.