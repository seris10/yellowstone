"""geochemistry: sinter-vs-travertine guardrail.
Records fluid-chemistry to substrate to palette rules; Midway shells must validate as siliceous."""
from __future__ import annotations

SYSTEMS = {
    "siliceous_sinter": {
        "chemistry": "neutral-alkaline chloride, high dissolved silica",
        "setting": "rhyolite-hosted geyser basins (Midway, Upper, Lower)",
        "features": ["geyser", "hot_spring", "fumarole", "sinter_apron"],
        "palette": ["deep_blue", "teal", "green_mat", "ochre_mat",
                    "wet_sinter", "dry_sinter"],
        "midway_use": True,
    },
    "travertine": {
        "chemistry": "calcium-carbonate from limestone, CO2 degassing",
        "setting": "Mammoth Hot Springs terraces ONLY",
        "features": ["travertine_terrace", "rimstone_pool"],
        "palette": ["white_calcite", "cream", "pale_terrace_grey"],
        "midway_use": False,
    },
    "acid_sulfate": {
        "chemistry": "acid-sulfate, low silica, mud alteration",
        "setting": "mud pots / fumarole fields (NOT Midway core)",
        "features": ["mudpot", "fumarole_clay"],
        "palette": ["grey_mud", "ochre_clay", "sulfur_rind"],
        "midway_use": False,
    },
}

MIDWAY_POOLS = {"pool_1034_0", "pool_1030_0", "pool_1028_0", "pool_1029_0"}

# Asset schema label plus the mineral-system id; the two are checked together at import time.
MIDWAY_SUBSTRATE_SYSTEM = "siliceous_sinter"
MIDWAY_SUBSTRATE_SUFFIX = "illustrative"
MIDWAY_SUBSTRATE = f"{MIDWAY_SUBSTRATE_SYSTEM}_{MIDWAY_SUBSTRATE_SUFFIX}"
if MIDWAY_SUBSTRATE_SYSTEM not in SYSTEMS:
    raise ValueError(
        f"MIDWAY_SUBSTRATE_SYSTEM {MIDWAY_SUBSTRATE_SYSTEM!r} "
        f"must be a SYSTEMS key; have {sorted(SYSTEMS)}")
if not SYSTEMS[MIDWAY_SUBSTRATE_SYSTEM].get("midway_use", False):
    raise ValueError(
        f"MIDWAY_SUBSTRATE_SYSTEM {MIDWAY_SUBSTRATE_SYSTEM!r} is not "
        f"flagged for Midway use in SYSTEMS")


class SubstrateError(ValueError):
    pass


# Feature-to-system mapping: import-time duplicate detection.
FEATURE_OWNERS: dict[str, str] = {}
for _sys_id, _sys_info in SYSTEMS.items():
    for _feat in _sys_info.get("features", []):
        if _feat in FEATURE_OWNERS:
            raise SubstrateError(
                f"duplicate feature assignment: {_feat!r} maps to both "
                f"{FEATURE_OWNERS[_feat]!r} and {_sys_id!r}")
        FEATURE_OWNERS[_feat] = _sys_id


def system_for_feature(feature: str) -> str:
    for sys_id, s in SYSTEMS.items():
        if feature in s["features"]:
            return sys_id
    raise SubstrateError(f"unknown hydrothermal feature type: {feature!r} "
                         f"(add with cited source, never guess)")


def check_midway_shells(shells: list) -> list:
    """Each Midway shell must be siliceous_sinter; returns failure strings."""
    failures = []
    for s in shells:
        if not isinstance(s, dict):
            failures.append(f"shell entry is not a record: {s!r}")
            continue
        shell_id = s.get("id")
        if shell_id in MIDWAY_POOLS and s.get("substrate") != MIDWAY_SUBSTRATE:
            failures.append(f"shell {shell_id}: Midway requires siliceous "
                            f"sinter, got {s.get('substrate')}")
    return failures


def validate_palette(shell_id: str, system_id: str, palette: str) -> None:
    """Validate that a palette belongs to the selected mineral system."""
    if system_id not in SYSTEMS:
        raise SubstrateError(f"unknown mineral system: {system_id!r}")
    allowed = SYSTEMS[system_id].get("palette", [])
    if palette not in allowed:
        raise SubstrateError(
            f"palette {palette!r} is not valid for system {system_id!r}; "
            f"allowed: {allowed}")
    forbid_whitening(shell_id, palette)


def forbid_whitening(shell_id: str, palette: str) -> None:
    """Raise if anyone applies a travertine palette to a Midway pool."""
    if shell_id in MIDWAY_POOLS and palette in SYSTEMS["travertine"]["palette"]:
        raise SubstrateError(
            f"refusing: travertine palette {palette!r} on Midway {shell_id}. "
            f"Mammoth is a different mineral system (NPS G4)")


def rules_doc() -> dict:
    import copy
    return {"systems": copy.deepcopy(SYSTEMS),
            "midway_pools": sorted(MIDWAY_POOLS),
            "rule": "substrate is authored from fluid chemistry per basin; "
                    "never copy a palette across mineral systems",
            "sources": [
                {"id": "NPS_G4",
                 "url": "https://www.nps.gov/yell/learn/nature/hydrothermal-features.htm",
                 "use": "sinter vs travertine distinction"}]}


# --- Empirical silica solubility (diagnostic only) ---
import math as _math
from pathlib import Path as _Path

# Log10 silica solubility fits, C in mg/L as SiO2, TK in kelvin.
_QUARTZ_A = 1309.0
_QUARTZ_B = 5.19
_CHALCEDONY_A = 1032.0
_CHALCEDONY_B = 4.69
_AMORPHOUS_A = 731.0
_AMORPHOUS_B = 4.52
_T_K_OFFSET = 273.15
_SOLUBILITY_T_RANGE_C = (0.0, 350.0)
_SI_CONSISTENT_TOL = 0.2

SILICA_PROVENANCE = {
    "quartz_no_steam_loss": "Fournier 1977 Geothermics 5:41-50 "
                            "doi:10.1016/0375-6505(77)90007-4",
    "chalcedony": "Fournier 1977 Geothermics 5:41-50 "
                  "doi:10.1016/0375-6505(77)90007-4; "
                  "Fournier and Rowe 1966 Am J Sci 264:685-697 "
                  "doi:10.2475/ajs.264.9.685",
    "amorphous": "Fournier 1977 Geothermics 5:41-50 "
                 "doi:10.1016/0375-6505(77)90007-4; "
                 "Gunnarsson and Arnorsson 2000 Geochim Cosmochim Acta "
                 "64:2295-2310 doi:10.1016/S0016-7037(99)00426-3",
    "chalcedony_low_T": "Arnorsson 1975 Am J Sci 275:763-784 "
                        "doi:10.2475/ajs.275.7.763; "
                        "Arnorsson 1983 Geothermics 12:119-128 "
                        "doi:10.1016/0375-6505(83)90022-2",
    "mixing": "Truesdell and Fournier 1977 USGS J Res 5:49-52 "
              "silica-enthalpy mixing relation",
}

_SOLUBILITY_FNS = {
    "quartz": (_QUARTZ_A, _QUARTZ_B),
    "chalcedony": (_CHALCEDONY_A, _CHALCEDONY_B),
    "amorphous": (_AMORPHOUS_A, _AMORPHOUS_B),
}


def _require_finite(name: str, value: float) -> float:
    """Coerce to float, rejecting booleans and nonfinite values."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not _math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _solubility(t_c: float, coeffs: tuple) -> float:
    """Log10 solubility fit evaluated at t_c (C)."""
    t_c = _require_finite("t_c", t_c)
    lo, hi = _SOLUBILITY_T_RANGE_C
    if not lo <= t_c <= hi:
        raise ValueError(f"t_c {t_c} outside fit range {lo} to {hi} C")
    slope, intercept = coeffs
    return 10.0 ** (intercept - slope / (t_c + _T_K_OFFSET))


def quartz_solubility_mg_L(t_c: float) -> float:
    """Quartz solubility mg/L as SiO2 (Fournier (1977) no steam loss)."""
    return _solubility(t_c, _SOLUBILITY_FNS["quartz"])


def chalcedony_solubility_mg_L(t_c: float) -> float:
    """Chalcedony solubility mg/L as SiO2 (Fournier (1977))."""
    return _solubility(t_c, _SOLUBILITY_FNS["chalcedony"])


def amorphous_solubility_mg_L(t_c: float) -> float:
    """Amorphous silica solubility mg/L as SiO2 (Fournier (1977))."""
    return _solubility(t_c, _SOLUBILITY_FNS["amorphous"])


def silica_reservoir_T_C(sio2_mg_L: float) -> float:
    """Reservoir T (C) from SiO2 via inverted quartz no-steam-loss fit."""
    sio2 = _require_finite("sio2_mg_L", sio2_mg_L)
    if sio2 <= 0.0:
        raise ValueError("sio2_mg_L must be > 0")
    denom = _QUARTZ_B - _math.log10(sio2)
    if denom <= 0.0:
        raise ValueError("sio2_mg_L above quartz fit range")
    return _QUARTZ_A / denom - _T_K_OFFSET


def silica_saturation_index(sio2_mg_L: float, t_c: float,
                            phase: str = "quartz") -> float:
    """Log10 ratio of observed SiO2 to equilibrium solubility at t_c."""
    if phase not in _SOLUBILITY_FNS:
        raise ValueError(f"unknown silica phase: {phase!r}")
    sio2 = _require_finite("sio2_mg_L", sio2_mg_L)
    if sio2 <= 0.0:
        raise ValueError("sio2_mg_L must be > 0")
    return _math.log10(sio2 / _solubility(t_c, _SOLUBILITY_FNS[phase]))


def diagnose_replay_frame(cell_temps, sio2_obs_or_None=None,
                          phase_rule: str = "quartz") -> list:
    """Per-cell silica diagnostic from replay temperatures or landscape dicts.

Chemistry is diagnostic only and never writes back into solver state."""
    if phase_rule not in _SOLUBILITY_FNS:
        raise ValueError(f"unknown silica phase: {phase_rule!r}")
    coeffs = _SOLUBILITY_FNS[phase_rule]
    temps = []
    labels = []
    for i, cell in enumerate(cell_temps):
        if isinstance(cell, dict):
            temps.append(_require_finite(f"cell_temps[{i}]",
                                         cell["temperature_c"]))
            labels.append(cell.get("id", i))
        else:
            temps.append(_require_finite(f"cell_temps[{i}]", cell))
            labels.append(i)
    if sio2_obs_or_None is None:
        obs = [None] * len(temps)
    elif isinstance(sio2_obs_or_None, dict):
        raise ValueError("sio2 input must be scalar, sequence, or None")
    else:
        try:
            scalar = _require_finite("sio2", sio2_obs_or_None)
            obs = [scalar] * len(temps)
        except (ValueError, TypeError):
            obs = list(sio2_obs_or_None)
            if len(obs) != len(temps):
                raise ValueError("sio2 sequence length must match cells")
    out = []
    for label, t, o in zip(labels, temps, obs):
        eq = _solubility(t, coeffs)
        row: dict = {"cell": label, "temperature_c": t,
                     "phase": phase_rule, "equilibrium_mg_L": eq,
                     "sio2_obs_mg_L": None, "si": None,
                     "reservoir_T_C": None, "flag": "no_observation"}
        if o is not None:
            o = _require_finite("sio2 obs", o)
            if o <= 0.0:
                raise ValueError("sio2 obs must be > 0")
            si = _math.log10(o / eq)
            row["sio2_obs_mg_L"] = o
            row["si"] = si
            row["reservoir_T_C"] = silica_reservoir_T_C(o)
            if abs(si) <= _SI_CONSISTENT_TOL:
                row["flag"] = "consistent"
            elif si > 0.0:
                row["flag"] = "supersaturated"
            else:
                row["flag"] = "undersaturated"
        out.append(row)
    return out


def phreeqc_silica_si(temperature_c: float, sio2_mg_L: float,
                      database_path: str, phase: str = "Chalcedony",
                      ph: float = 7.0) -> dict:
    """Saturation index via IPhreeqc (optional phreeqpy dependency)."""
    try:
        from phreeqpy.iphreeqc.phreeqc_dll import IPhreeqc
    except ImportError as error:
        raise ImportError(
            "phreeqpy is not installed: pip install phreeqpy==0.6.0, "
            "then pass a version-matched database_path (v3.7.3-tagged "
            "phreeqc.dat loads cleanly; master-branch .dat fails). "
            "No .dat file is bundled with this repo.") from error
    temperature_c = _require_finite("temperature_c", temperature_c)
    sio2_mg_L = _require_finite("sio2_mg_L", sio2_mg_L)
    if sio2_mg_L <= 0.0:
        raise ValueError("sio2_mg_L must be > 0")
    db = _Path(database_path)
    if not db.is_file():
        raise ValueError(f"database not found: {database_path}")
    worker = IPhreeqc()
    worker.load_database(str(db))
    # Version-matched database required; unmatched files fail parsing.
    if worker.phc_database_error_count != 0:
        raise RuntimeError(
            f"database {database_path} failed to load "
            f"({worker.phc_database_error_count} errors); use a "
            f"version-matched .dat for the installed PHREEQC build")
    worker.run_string(f"""
SOLUTION 1
    temp {temperature_c}
    pH {ph}
    units mg/L
    Na 230
    Cl 350
    Si {sio2_mg_L} as SiO2
SELECTED_OUTPUT
    -reset false
    -saturation_indices {phase}
END
""")
    rows = worker.get_selected_output_array()
    header = [str(h).strip().lower() for h in rows[0]]
    target = f"si_{phase}".lower()
    if target not in header:
        raise RuntimeError(f"phase {phase!r} missing from output {header}")
    return {"si": float(rows[-1][header.index(target)]), "phase": phase,
            "temperature_c": temperature_c, "sio2_mg_L": sio2_mg_L,
            "database": str(db)}
