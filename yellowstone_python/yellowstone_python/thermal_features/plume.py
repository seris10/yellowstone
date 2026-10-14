"""Steady plume rendering and authored tributary defaults."""
from __future__ import annotations
from yellowstone_python.common.checks import finite as _finite, positive_int as _positive_int

def plume_field(nx: int = 128, nz: int = 128, extent_m: float = 600.0,
                hot_c: float = 19.1, river_c: float = 17.8,
                sigma_m: float = 90.0) -> list:
    """Steady 2-D advection-diffusion plume at the Excelsior mouth.
Implicit upwind/centered solve; returns nx*nz row-major floats in degrees C."""
    nx = _positive_int("nx", nx)
    nz = _positive_int("nz", nz)
    extent_m = _finite("extent_m", extent_m)
    sigma_m = _finite("sigma_m", sigma_m)
    hot_c = _finite("hot_c", hot_c)
    river_c = _finite("river_c", river_c)
    if extent_m <= 0.0:
        raise ValueError(f"extent_m must be > 0, got {extent_m}")
    if sigma_m < 0.0:
        raise ValueError(f"sigma_m must be >= 0, got {sigma_m}")
    from yellowstone_python.river.plume2d import solve_steady
    sol = solve_steady(nx=nx, nz=nz, extent_m=extent_m,
                       ambient_c=river_c, source_c=hot_c,
                       source_xz=(0.0, -60.0), source_r_m=sigma_m)
    return sol["field"]


def render_plume_png(field: list, nx: int, nz: int, path: str,
                     vmin: float = 17.0, vmax: float = 20.0) -> str:
    """Blue to red ramp PNG, same extent convention as habitat_mask.png."""
    from pathlib import Path
    nx = _positive_int("nx", nx)
    nz = _positive_int("nz", nz)
    values = [_finite(f"field[{i}]", v) for i, v in enumerate(field)]
    if len(values) != nx * nz:
        raise ValueError(
            f"field length {len(values)} != nx*nz={nx * nz}")
    vmin = _finite("vmin", vmin)
    vmax = _finite("vmax", vmax)
    if vmax == vmin:
        raise ValueError(f"vmin and vmax must differ, got {vmin}")
    from PIL import Image
    img = Image.new("RGB", (nx, nz))
    px = img.load()
    span = vmax - vmin
    for iz in range(nz):
        for ix in range(nx):
            t = values[iz * nx + ix]
            f = min(1.0, max(0.0, (t - vmin) / span))
            px[ix, iz] = (int(120 + 135 * f), int(150 - 60 * f), int(200 - 150 * f))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


DEFAULT_TRIBUTARIES = {
    # Illustrative cold dilutions; 0.0 flow = omitted (baseline preserved).
    "fairy_creek": {"flow_m3s": 0.0, "temperature_c": 12.0},
    "white_creek": {"flow_m3s": 0.0, "temperature_c": 12.0},
    "rabbit_creek": {"flow_m3s": 0.0, "temperature_c": 11.0},
    "mallard_creek": {"flow_m3s": 0.0, "temperature_c": 11.0},
}

