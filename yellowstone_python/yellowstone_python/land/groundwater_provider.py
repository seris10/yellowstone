"""Authored lateral inflows mapped to river Source dicts."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite

import math

STATUS = "authored_lateral_not_modeled"

# Volumetric heat capacity of water (J/m3/K) for the aquifer-to-river heat accounting.
RHO_CP_WATER_J_M3_K = 4.186e6




def _temperature_spec(value):
    """Series-spec dict accepted by the river Source temperature parser."""
    if isinstance(value, dict):
        if set(value) != {"times_s", "values"}:
            raise ValueError("temperature_c needs times_s and values only")
        times = tuple(_finite("temperature time", t, minimum=0.0) for t in value["times_s"])
        temps = tuple(_finite("temperature value", v) for v in value["values"])
        if not times or len(times) != len(temps):
            raise ValueError("temperature times and values must match")
        if times[0] != 0.0:
            raise ValueError("temperature series must begin at t=0")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("temperature times must strictly increase")
        return {"times_s": list(times), "values": list(temps)}
    return {"times_s": [0.0], "values": [_finite("temperature_c", value)]}


def authored_reaches_to_sources(
    reaches,
    *,
    t0_epoch_s=0.0,
    dt_s=3600.0,
    stress_period=0,
):
    """Per-receiving-cell lateral dicts from authored reach inflows."""
    t0 = _finite("t0_epoch_s", t0_epoch_s, minimum=0.0)
    step = _finite("dt_s", dt_s, minimum=0.0)
    period = int(stress_period)
    if period < 0:
        raise ValueError("stress_period must be >= 0")
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
        flow = _finite("flow_m3_s", reach.get("flow_m3_s"), minimum=0.0)
        spec = _temperature_spec(reach.get("temperature_c"))
        laterals.append({
            "source_id": source_id,
            "cell_id": cell_id,
            "flow_m3_s": flow,
            "temperature_c": spec,
            "status": STATUS,
            "provenance": {
                "gw_cell": list(gw_cell),
                "stress_period": period,
                "t0_epoch_s": t0,
                "t1_epoch_s": t0 + spec["times_s"][-1] + step,
            },
        })
    if not laterals:
        raise ValueError("reaches must be nonempty")
    return laterals


riv_reaches_to_sources = authored_reaches_to_sources


def with_chainage(laterals, chainage_by_id):
    """Stamp channel chainage onto provider laterals for mapped replay.
chainage_by_id maps source_id to meters along the solver channel; losing reaches rejected."""
    if not isinstance(chainage_by_id, dict):
        raise ValueError("chainage_by_id must be a mapping")
    out = []
    for lateral in laterals or []:
        if not isinstance(lateral, dict):
            raise ValueError("laterals must be objects")
        source_id = lateral.get("source_id")
        if source_id not in chainage_by_id:
            raise ValueError(f"no chainage for {source_id!r}")
        flow = _finite("flow_m3_s", lateral.get("flow_m3_s"))
        if flow < 0.0:
            raise ValueError(f"losing reach {source_id!r} has no "
                             f"river Source representation")
        location = _finite("chainage s_m", chainage_by_id[source_id], minimum=0.0)
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


def _validate_cell_record(cell, index):
    """Required inputs for a per-cell head-gradient exchange record."""
    if not isinstance(cell, dict):
        raise ValueError(f"cells[{index}] must be an object")
    for key in ("cell_id", "bed_conductivity_m_s", "bed_thickness_m",
                "width_m", "length_m", "h_aquifer_m", "h_river_m",
                "river_temperature_c", "aquifer_temperature_c",
                "aquifer_temperature_source"):
        if key not in cell:
            raise ValueError(f"cells[{index}] requires {key!r}")
    cell_id = cell["cell_id"]
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError(f"cells[{index}].cell_id must be a nonempty string")
    for name in ("bed_conductivity_m_s", "bed_thickness_m",
                 "width_m", "length_m"):
        value = _finite(f"cells[{index}].{name}", cell[name], minimum=0.0)
        if value <= 0.0:
            raise ValueError(
                f"cells[{index}].{name} must be positive, got {value}")
    _finite(f"cells[{index}].h_aquifer_m", cell["h_aquifer_m"])
    _finite(f"cells[{index}].h_river_m", cell["h_river_m"])
    _finite(f"cells[{index}].river_temperature_c", cell["river_temperature_c"])
    _finite(f"cells[{index}].aquifer_temperature_c", cell["aquifer_temperature_c"])
    label = cell["aquifer_temperature_source"]
    if not isinstance(label, str) or not label.strip():
        raise ValueError(
            f"cells[{index}].aquifer_temperature_source must be a "
            "nonempty label (for example "
            "authored_shallow_aquifer_8C_illustrative)")


def head_gradient_exchange(cells, *, source_id_prefix="gw_cell"):
    """Per-cell aquifer-river exchange with conductance C = K * W * L / b.
Gaining reach emits a Source at aquifer temperature; losing reach exports to a separate list."""
    if not cells:
        raise ValueError("cells must be nonempty")
    sources = []
    losing = []
    total_gain_m3_s = 0.0
    total_gain_j_s = 0.0
    total_loss_m3_s = 0.0
    total_loss_j_s = 0.0
    for index, record in enumerate(cells):
        _validate_cell_record(record, index)
        conductivity = float(record["bed_conductivity_m_s"])
        thickness = float(record["bed_thickness_m"])
        width = float(record["width_m"])
        length = float(record["length_m"])
        h_aq = float(record["h_aquifer_m"])
        h_r = float(record["h_river_m"])
        t_r = float(record["river_temperature_c"])
        t_aq = float(record["aquifer_temperature_c"])
        label = record["aquifer_temperature_source"]
        # Conductance C (m2/s): K * W * L / b. Flow q (m3/s): C * (h_aquifer - h_river).
        conductance = conductivity * width * length / thickness
        q = conductance * (h_aq - h_r)
        cell_id = record["cell_id"]
        provenance = {
            "cell_id": cell_id,
            "bed_conductivity_m_s": conductivity,
            "bed_thickness_m": thickness,
            "width_m": width,
            "length_m": length,
            "conductance_m2_s": conductance,
            "h_aquifer_m": h_aq,
            "h_river_m": h_r,
            "head_gradient_m": h_aq - h_r,
            "aquifer_temperature_source": label,
        }
        if q > 0.0:
            total_gain_m3_s += q
            total_gain_j_s += q * (t_aq - t_r) * RHO_CP_WATER_J_M3_K
            sources.append({
                "source_id": f"{source_id_prefix}_{cell_id}",
                "cell_id": cell_id,
                "flow_m3_s": q,
                "temperature_c": _temperature_spec(t_aq),
                "status": "head_gradient_gaining_reach_authored_aquifer_t",
                "provenance": provenance,
            })
        elif q < 0.0:
            loss = -q
            total_loss_m3_s += loss
            # Losing reach exports water at the river temperature; heat leaves at t_r by definition.
            total_loss_j_s += loss * (t_r - t_aq) * RHO_CP_WATER_J_M3_K
            losing.append({
                "cell_id": cell_id,
                "flow_m3_s": loss,
                "temperature_c": t_r,
                "status": "head_gradient_losing_reach_exports_at_river_t",
                "note": ("River.Source accepts only nonnegative flow; "
                         "the build pipeline applies this as an outflow"),
                "provenance": provenance,
            })
    totals = {
        "gaining_flow_m3_s": total_gain_m3_s,
        "losing_flow_m3_s": total_loss_m3_s,
        "net_flow_m3_s": total_gain_m3_s - total_loss_m3_s,
        "gaining_heat_j_s_vs_river": total_gain_j_s,
        "losing_heat_j_s_vs_river": -total_loss_j_s,
        "status": "head_gradient_conductance_exchange",
    }
    return {"sources": sources, "losing": losing, "totals": totals}


def synthetic_mf6_simulation(name="synthetic_gwf", nrow=3, ncol=3, dx_m=100.0):
    """Small one-layer MF6 simulation object for mapping tests."""
    try:
        import flopy
    except ImportError as exc:
        raise RuntimeError("flopy not available") from exc
    nrow = int(nrow)
    ncol = int(ncol)
    dx = _finite("dx_m", dx_m, minimum=0.0)
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
