"""CF-conformant NetCDF export of replay temperature frames (CF-1.11, Standard Name Table v83)."""
from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any, Sequence

SCHEMA = "yellowstone.replay_netcdf.v1"
CF_CONVENTIONS = "CF-1.11"


def _reference_datetime(frames: Sequence[dict[str, Any]]
                        ) -> datetime.datetime:
    """Reference datetime for the CF time axis."""
    first = frames[0] if frames else {}
    wall = first.get("wall_time") if isinstance(first, dict) else None
    if isinstance(wall, (int, float)) and not isinstance(wall, bool):
        return datetime.datetime.fromtimestamp(
            float(wall), tz=datetime.timezone.utc).replace(tzinfo=None)
    if wall:
        text = str(wall).rstrip("Z")
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    return datetime.datetime(1970, 1, 1)


def write_replay_netcdf(frames: Sequence[dict[str, Any]],
                        cell_ids: Sequence[str],
                        path: str | Path) -> Path:
    """Write replay frames to NetCDF with time and cell dimensions."""
    try:
        import xarray as xr
    except ImportError as exc:
        raise ImportError(
            "replay.nc_export needs xarray and netCDF4: install them "
            "(pip install xarray netCDF4) or keep using the JSON replay") \
            from exc
    import numpy as np
    ids = [str(v) for v in cell_ids]
    if not frames or not ids:
        raise ValueError("frames and cell_ids must be nonempty")
    for i, frame in enumerate(frames):
        row = frame.get("temperature_c")
        if row is None:
            raise ValueError(f"frame {i}: missing temperature_c")
        if len(row) != len(ids):
            raise ValueError(
                f"frame {i}: temperature_c length {len(row)} "
                f"does not match cell_ids length {len(ids)}")
    times = np.array([float(f["t_s"]) for f in frames], dtype=np.float64)
    temps = np.array([list(f["temperature_c"]) for f in frames],
                     dtype=np.float64)
    reference_dt = _reference_datetime(frames)
    time_units = (f"seconds since "
                  f"{reference_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    data = xr.Dataset(
        {"water_temperature": (
            ("time", "cell"), temps,
            {"units": "degree_Celsius",
             "standard_name": "water_temperature",
             "long_name": "replay cell water temperature"})},
        coords={
            "time": ("time", times, {
                "units": time_units,
                "standard_name": "time",
                "calendar": "standard",
                "axis": "T"}),
            "cell_id": ("cell", np.array(ids, dtype=object), {
                "long_name": "replay cell identifier",
                "cf_role": "timeseries_id"})})
    data.attrs = {"Conventions": CF_CONVENTIONS,
                  "title": "Yellowstone replay water temperature",
                  "source": "yellowstone_python replay solver",
                  "schema": SCHEMA}
    out = Path(path)
    tmp = out.with_suffix(out.suffix + ".tmp")
    data.to_netcdf(tmp)
    os.replace(tmp, out)
    return out


def read_replay_netcdf(path: str | Path) -> dict[str, Any]:
    """Read a replay NetCDF file into times, ids, and temperatures."""
    try:
        import xarray as xr
    except ImportError as exc:
        raise ImportError(
            "replay.nc_export needs xarray and netCDF4: install them "
            "(pip install xarray netCDF4) or keep using the JSON replay") \
            from exc
    with xr.open_dataset(path) as data:
        return {"times_s": [float(v) for v in data["time"].to_numpy()],
                "cell_ids": [str(v) for v in data["cell_id"].to_numpy()],
                "temperature_c": [[float(v) for v in row]
                                  for row in
                                  data["water_temperature"].to_numpy()]}
