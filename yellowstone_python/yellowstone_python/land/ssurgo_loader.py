"""Loader for ssurgo tabular soil data (Midway Geyser Basin, survey MT628).
Reads ssurgo tabular files and emits hydrosim-compatible soil preset tuples."""
from __future__ import annotations

import csv
import math
from pathlib import Path

SOIL_TUPLE_FIELDS = (
    "porosity", "suction_psi_mm", "effective_ks_mm_h",
    "theta_fc", "theta_wp",
)

# ssurgo tabular files participating in the loader.
SSURGO_FILE_MUAGGATT = "muaggatt.txt"
SSURGO_FILE_MAPUNIT = "mapunit.txt"
SSURGO_FILE_COMPONENT = "comp.txt"
SSURGO_FILE_CHORIZON = "chorizon.txt"

# Column indices for ssurgo tabular export v9 (schema version 2.3.3).
MUAGGATT_IDX = {
    "musym": 0, "muname": 1, "mukey": 39,
    # porosity-like fields are not in muaggatt; take drainage class only.
    "drclassdcd": 10,
}
MAPUNIT_IDX = {"musym": 0, "muname": 1, "mukey": 24, "lkey": 25}
COMPONENT_IDX = {
    "comppct_r": 1, "compname": 3, "majcompflag": 48,
    "cokey": 109, "mukey": 110,
}
CHORIZON_IDX = {
    "hzdept_r": 7, "hzdepb_r": 10, "hzthk_r": 4,
    "wsatiated_r": 85,       # saturated water content, cm3/cm3 (porosity)
    "wthirdbar_r": 76,       # water retention at 33 kPa, cm3/cm3 (fc)
    "wfifteenbar_r": 79,     # water retention at 1500 kPa, cm3/cm3 (wp)
    "ksat_r": 94,            # saturated hydraulic conductivity, um/s
    "cokey": 169,
}

# ksat conversion: Bouwer (1966) halves saturated Ks for green_ampt; 3.6 scales um/s to mm/h.
UM_S_TO_MM_H = 3.6


class SSURGOError(ValueError):
    """Raised when the ssurgo tabular export cannot be parsed into soils."""


def _read_pipe_table(path: Path) -> list[list[str]]:
    """Read a pipe-delimited ssurgo text file into a list of row lists."""
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="|", quoting=csv.QUOTE_NONE)
        for row in reader:
            rows.append(row)
    return rows


def _finite_or_none(value: str) -> float | None:
    """Coerce an ssurgo cell to float; empty or non-finite returns None."""
    cleaned = value.strip() if isinstance(value, str) else value
    if cleaned in (None, "", "NA", "N/A"):
        return None
    try:
        result = float(cleaned)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _get(row: list[str], idx: int) -> str:
    return row[idx] if 0 <= idx < len(row) else ""


def _horizon_weight(row: list[str]) -> float:
    """Horizon thickness (cm) weighting an average over a profile.
Falls back to depth difference when hzthk_r is absent."""
    thk = _finite_or_none(_get(row, CHORIZON_IDX["hzthk_r"]))
    if thk is not None and thk > 0.0:
        return thk
    top = _finite_or_none(_get(row, CHORIZON_IDX["hzdept_r"]))
    bot = _finite_or_none(_get(row, CHORIZON_IDX["hzdepb_r"]))
    if top is not None and bot is not None and bot > top:
        return bot - top
    return 1.0


def _profile_mean(horizons: list[list[str]], idx: int) -> float | None:
    """Thickness-weighted mean of column idx across a component's horizons."""
    numerator = 0.0
    denom = 0.0
    for row in horizons:
        value = _finite_or_none(_get(row, idx))
        if value is None:
            continue
        weight = _horizon_weight(row)
        numerator += value * weight
        denom += weight
    if denom <= 0.0:
        return None
    return numerator / denom


def _component_soil_tuple(horizons: list[list[str]]
                          ) -> tuple[float, float, float, float, float] | None:
    """Build a soils-compatible tuple from one component's horizons.
Returns None when any required field is missing."""
    porosity = _profile_mean(horizons, CHORIZON_IDX["wsatiated_r"])
    theta_fc = _profile_mean(horizons, CHORIZON_IDX["wthirdbar_r"])
    theta_wp = _profile_mean(horizons, CHORIZON_IDX["wfifteenbar_r"])
    ksat_um_s = _profile_mean(horizons, CHORIZON_IDX["ksat_r"])
    if (porosity is None or theta_fc is None or theta_wp is None
            or ksat_um_s is None):
        return None
    # Green-Ampt effective Ks per Bouwer (1966): one half of saturated Ks.
    effective_ks_mm_h = 0.5 * ksat_um_s * UM_S_TO_MM_H
    # Suction psi is absent from chorizon; emit a placeholder for downstream callers to replace.
    suction_psi_mm = 0.0
    return (float(porosity), float(suction_psi_mm),
            float(effective_ks_mm_h),
            float(theta_fc), float(theta_wp))


def load_ssurgo_soils(ssurgo_root: Path | str) -> dict[str, dict]:
    """Return {component_name: {tuple, musym, muname, mukey}} from a tabular export.
Required files: component.txt, chorizon.txt. Optional: mapunit.txt, muaggatt.txt."""
    root = Path(ssurgo_root)
    if not root.is_dir():
        raise SSURGOError(f"SSURGO root is not a directory: {root}")
    component_path = root / SSURGO_FILE_COMPONENT
    chorizon_path = root / SSURGO_FILE_CHORIZON
    if not component_path.is_file():
        raise SSURGOError(
            f"missing component file at {component_path}")
    if not chorizon_path.is_file():
        raise SSURGOError(
            f"missing chorizon file at {chorizon_path}")
    components = _read_pipe_table(component_path)
    chorizons = _read_pipe_table(chorizon_path)
    mapunit_rows: list[list[str]] = []
    mapunit_path = root / SSURGO_FILE_MAPUNIT
    if mapunit_path.is_file():
        mapunit_rows = _read_pipe_table(mapunit_path)
    mukey_to_musym: dict[str, str] = {}
    mukey_to_muname: dict[str, str] = {}
    for row in mapunit_rows:
        mukey = _get(row, MAPUNIT_IDX["mukey"]).strip()
        if not mukey:
            continue
        mukey_to_musym[mukey] = _get(row, MAPUNIT_IDX["musym"]).strip()
        mukey_to_muname[mukey] = _get(row, MAPUNIT_IDX["muname"]).strip()
    cokey_to_horizons: dict[str, list[list[str]]] = {}
    for row in chorizons:
        cokey = _get(row, CHORIZON_IDX["cokey"]).strip()
        if not cokey:
            continue
        cokey_to_horizons.setdefault(cokey, []).append(row)
    soils: dict[str, dict] = {}
    for row in components:
        cokey = _get(row, COMPONENT_IDX["cokey"]).strip()
        mukey = _get(row, COMPONENT_IDX["mukey"]).strip()
        compname = _get(row, COMPONENT_IDX["compname"]).strip()
        majflag = _get(row, COMPONENT_IDX["majcompflag"]).strip()
        if not compname or not cokey:
            continue
        if majflag and majflag.lower() not in ("yes", "y", "true", "1"):
            continue
        horizons = cokey_to_horizons.get(cokey, [])
        if not horizons:
            continue
        tup = _component_soil_tuple(horizons)
        if tup is None:
            continue
        key = compname.lower()
        soils[key] = {
            "tuple": tup,
            "musym": mukey_to_musym.get(mukey, ""),
            "muname": mukey_to_muname.get(mukey, ""),
            "mukey": mukey,
            "compname": compname,
        }
    if not soils:
        raise SSURGOError(
            f"no major components with complete horizons under {root}")
    return soils


def to_hydrosim_soils_table(soils: dict[str, dict]) -> dict:
    """Return {name: tuple} ready to merge into the hydrosim soils table."""
    return {name: info["tuple"] for name, info in soils.items()}


# Documented coverage for the Midway Geyser Basin, Yellowstone National Park.
MT628_SURVEY_AREA = {
    "state": "MT",
    "survey_area_id": "MT628",
    "name": ("Soil Survey Geographic Database (SSURGO) area MT628 "
             "covering Yellowstone National Park, Montana portion"),
    "primary_sources": [
        "USDA-NRCS Soil Survey Geographic (SSURGO) Database, tabular export",
        "Soil Survey Staff. Soil Survey Manual (USDA Handbook 18).",
    ],
    "status": ("dataset_not_present_on_this_machine: loader exercised against "
               "a synthetic tabular fixture; replace with the real MT628 "
               "download to activate the midway_soil_map on measured soils."),
}
