"""Simulation clock helpers for the replay solver and its adapters.
Timestamps are UTC; local civil time comes from a recorded offset."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite

from datetime import datetime, timezone
import math
from typing import Any

UTC = timezone.utc

ISO_HINT = "for example 2026-07-15T22:20:00Z"




def parse_simulation_start(
    *,
    simulation_start_utc: Any = None,
    simulation_start_epoch_unix: Any = None,
) -> datetime:
    """Aware UTC start for a run, from exactly one timestamp representation."""
    if (
        simulation_start_utc is not None
        and simulation_start_epoch_unix is not None
    ):
        raise ValueError(
            "provide only one of simulation_start_utc or "
            "simulation_start_epoch_unix"
        )

    if simulation_start_epoch_unix is not None:
        epoch = _finite("simulation_start_epoch_unix", simulation_start_epoch_unix, minimum=0.0)
        try:
            return datetime.fromtimestamp(epoch, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError(
                "simulation_start_epoch_unix is outside the representable range"
            ) from exc

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

    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            "simulation_start_utc must be a valid ISO-8601 timestamp"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"simulation_start_utc must include a timezone, {ISO_HINT}"
        )

    return parsed.astimezone(UTC)


def timestamp_metadata(
    start: datetime, duration_s: float
) -> dict[str, Any]:
    """UTC start and end of a run, plus its duration."""
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("simulation start must be timezone aware")
    start = start.astimezone(UTC)
    duration = _finite("duration_s", duration_s, minimum=0.0)
    end = datetime.fromtimestamp(start.timestamp() + duration, tz=UTC)

    return {
        "start_epoch_unix": start.timestamp(),
        "end_epoch_unix": end.timestamp(),
        "start_utc": start.isoformat().replace("+00:00", "Z"),
        "end_utc": end.isoformat().replace("+00:00", "Z"),
        "duration_s": duration,
        "timezone": "UTC",
    }


def epoch_unix_for_local(
    as_of_date: str,
    local_hour: float,
    utc_offset_hours: float,
) -> float:
    """Epoch seconds for a local date and clock hour at a fixed UTC offset."""
    import datetime as _datetime

    day = _datetime.date.fromisoformat(str(as_of_date))
    hour = _finite("local_hour", local_hour)
    if not 0.0 <= hour < 24.0:
        raise ValueError("local_hour must be in [0, 24)")
    offset = _finite("utc_offset_hours", utc_offset_hours)
    if not -12.0 <= offset <= 14.0:
        raise ValueError("utc_offset_hours must be in [-12, 14]")
    local_seconds = hour * 3600.0
    start = _datetime.datetime(
        day.year, day.month, day.day, tzinfo=UTC
    ) - _datetime.timedelta(hours=offset)
    return start.timestamp() + local_seconds


def resolve_query_epoch(origin_epoch_unix: float | None, utc_offset_hours: float, *,
                        local_hour: float | None = None, elapsed_hours: float | None = None,
                        epoch_unix: float | None = None) -> float:
    """Resolve one weather query without changing the scenario's date."""
    if sum(value is not None for value in (local_hour, elapsed_hours, epoch_unix)) > 1:
        raise ValueError("Choose one of local hour, elapsed hours or absolute epoch")
    if epoch_unix is not None:
        return _finite("epoch_unix", epoch_unix, minimum=0.)
    if origin_epoch_unix is None:
        raise ValueError("A scenario epoch is required; a weather cache cannot supply the date")
    origin = _finite("simulation_epoch_unix", origin_epoch_unix, minimum=0.)
    if elapsed_hours is not None:
        return origin + 3600. * _finite("elapsed_hours", elapsed_hours, minimum=0.)
    if local_hour is None:
        return origin
    offset = _finite("utc_offset_hours", utc_offset_hours, minimum=-12., maximum=14.)
    day = datetime.fromtimestamp(origin + offset * 3600., UTC).date().isoformat()
    return epoch_unix_for_local(day, local_hour, offset)
