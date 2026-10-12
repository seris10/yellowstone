"""Synthetic MODFLOW laterals mapped to river Source dicts."""
from __future__ import annotations

import math

PACKAGE = "RIV"
STATUS = "synthetic_modeled_not_calibrated"
KNOWN_MF6_VERSION = "6.7.0"


def flopy_version():
    """Installed flopy version, or None where absent."""
    try:
        import flopy
    except ImportError:
        return None
    return getattr(flopy, "__version__", "unknown")


def _finite(value, name, minimum=None):
    """Checked float conversion for provider inputs."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _temperature_spec(value):
    """Series-spec dict accepted by the river Source temperature parser."""
    if isinstance(value, dict):
        if set(value) != {"times_s", "values"}:
            raise ValueError("temperature_c needs times_s and values only")
        times = tuple(_finite(t, "temperature time", 0.0) for t in value["times_s"])
        temps = tuple(_finite(v, "temperature value") for v in value["values"])
        if not times or len(times) != len(temps):
            raise ValueError("temperature times and values must match")
        if times[0] != 0.0:
            raise ValueError("temperature series must begin at t=0")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("temperature times must strictly increase")
        return {"times_s": list(times), "values": list(temps)}
    return {"times_s": [0.0], "values": [_finite(value, "temperature_c")]}


def riv_reaches_to_sources(
    reaches,
    *,
    t0_epoch_s=0.0,
    dt_s=3600.0,
    mf6_version=None,
    stress_period=0,
):
    """Per-receiving-cell lateral dicts from synthetic RIV reach flows."""
    t0 = _finite(t0_epoch_s, "t0_epoch_s", 0.0)
    step = _finite(dt_s, "dt_s", 0.0)
    period = int(stress_period)
    if period < 0:
        raise ValueError("stress_period must be >= 0")
    version = mf6_version or flopy_version() or KNOWN_MF6_VERSION
    laterals = []
    for reach in reaches:
        source_id = reach.get("source_id")
        cell_id = reach.get("cell_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("reach source_id must be a nonempty string")
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError("reach cell_id must be a nonempty string")
        gw_cell = reach.get("gw_cell")
        if (
            not isinstance(gw_cell, (list, tuple))
            or len(gw_cell) != 3
            or any(not isinstance(k, int) or k < 0 for k in gw_cell)
        ):
            raise ValueError("gw_cell must be three nonnegative ints")
        flow = _finite(reach.get("flow_m3_s"), "flow_m3_s")
        spec = _temperature_spec(reach.get("temperature_c"))
        laterals.append({
            "source_id": source_id,
            "cell_id": cell_id,
            "flow_m3_s": flow,
            "temperature_c": spec,
            "status": STATUS,
            "provenance": {
                "mf6_version": version,
                "package": PACKAGE,
                "gw_cell": list(gw_cell),
                "stress_period": period,
                "t0_epoch_s": t0,
                "t1_epoch_s": t0 + spec["times_s"][-1] + step,
            },
        })
    if not laterals:
        raise ValueError("reaches must be nonempty")
    return laterals


def with_chainage(laterals, chainage_by_id):
    """Stamp channel chainage onto provider laterals for mapped replay.

    chainage_by_id maps source_id to metres along the solver channel.
    Losing reaches (negative flow) are rejected: river Sources carry
    inflow only.
    """
    if not isinstance(chainage_by_id, dict):
        raise ValueError("chainage_by_id must be a mapping")
    out = []
    for lateral in laterals or []:
        if not isinstance(lateral, dict):
            raise ValueError("laterals must be objects")
        source_id = lateral.get("source_id")
        if source_id not in chainage_by_id:
            raise ValueError(f"no chainage for {source_id!r}")
        flow = _finite(lateral.get("flow_m3_s"), "flow_m3_s")
        if flow < 0.0:
            raise ValueError(f"losing reach {source_id!r} has no "
                             f"river Source representation")
        location = _finite(chainage_by_id[source_id], "chainage s_m", 0.0)
        out.append({
            "id": source_id,
            "s_m": location,
            "flow_m3_s": flow,
            "temperature_c": _temperature_spec(
                lateral.get("temperature_c")),
            "status": lateral.get("status", STATUS),
            "provenance": {**lateral.get("provenance", {}),
                           "s_m": location},
        })
    return out


def synthetic_mf6_simulation(name="synthetic_gwf", nrow=3, ncol=3, dx_m=100.0):
    """Small one-layer MF6 simulation object for mapping tests."""
    try:
        import flopy
    except ImportError as exc:
        raise RuntimeError("flopy not available") from exc
    nrow = int(nrow)
    ncol = int(ncol)
    dx = _finite(dx_m, "dx_m", 0.0)
    if nrow < 1 or ncol < 1:
        raise ValueError("model grid must have at least one cell")
    sim = flopy.mf6.MFSimulation(sim_name=name, exe_name="mf6")
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(1.0, 1, 1.0)])
    gwf = flopy.mf6.ModflowGwf(sim, modelname=name, save_flows=True)
    flopy.mf6.ModflowGwfdis(
        gwf, nlay=1, nrow=nrow, ncol=ncol, delr=dx, delc=dx, top=100.0, botm=90.0
    )
    flopy.mf6.ModflowGwfnpf(gwf, k=1.0)
    flopy.mf6.ModflowGwfic(gwf, strt=95.0)
    riv_cells = [[(0, r, ncol - 1), 95.0, 1.0, 94.0] for r in range(nrow)]
    flopy.mf6.ModflowGwfriv(gwf, stress_period_data={0: riv_cells})
    return sim
