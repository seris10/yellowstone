"""CF-style NetCDF export of replay temperature frames."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

SCHEMA = "yellowstone.replay_netcdf.v1"


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
    times = np.array([float(f["t_s"]) for f in frames], dtype=np.float64)
    temps = np.array([list(f["temperature_c"]) for f in frames],
                     dtype=np.float64)
    if temps.shape != (len(frames), len(ids)):
        raise ValueError("frame widths do not match cell_ids")
    # Float64 storage preserves replay values bit-identically.
    data = xr.Dataset(
        {"water_temperature": (
            ("time", "cell"), temps,
            {"units": "degree_Celsius",
             "standard_name": "sea_water_temperature",
             "long_name": "replay cell water temperature"})},
        coords={"time": ("time", times,
                         {"units": "s", "standard_name": "time"}),
                "cell_id": ("cell", np.array(ids, dtype=object),
                            {"long_name": "replay cell identifier"})})
    data.attrs = {"Conventions": "CF-1.8",
                  "title": "Yellowstone replay water temperature",
                  "source": "yellowstone_python replay solver",
                  "schema": SCHEMA}
    out = Path(path)
    data.to_netcdf(out)
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
