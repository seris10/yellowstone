"""Parameter registry: class and evidence for model knobs."""
from __future__ import annotations

from .claims import REVIEW_STATUSES

PARAM_CLASSES = ("observed", "derived", "literature", "calibrated",
                  "assumed", "illustrative", "physical_constant")

ENTRY_FIELDS = ("param_id", "meaning", "units", "param_class", "source",
                "applicability", "uncertainty", "missingness", "review")

# Optional structured provenance: {path, key, expected} checked against a parsed config mapping.
SOURCE_REF_FIELDS = ("path", "key", "expected")

UNKNOWN = "unknown"

PARAMS = [
    {
        "param_id": "replay.hydraulics.manning_n",
        "meaning": "Manning roughness for trapezoidal diagnostic hydraulics",
        "units": "s/m^(1/3)",
        "param_class": "assumed",
        "source": "authored 0.035 gravel-bed value in configs/baseline.yaml",
        "applicability": "Firehole chainage cells, all flow regimes modeled",
        "uncertainty": UNKNOWN,
        "missingness": "no surveyed roughness; bathymetry absent",
        "review": "not_yet_accepted",
        "source_refs": [
            {"path": "configs/baseline.yaml",
             "key": "replay.hydraulics.manning_n", "expected": 0.035},
        ],
    },
    {
        "param_id": "replay.hydraulics.bank_slope_zh",
        "meaning": "Trapezoid bank slope for cross-section diagnostics",
        "units": "m/m",
        "param_class": "assumed",
        "source": "authored 1.5 in configs/baseline.yaml",
        "applicability": "Firehole chainage cells",
        "uncertainty": UNKNOWN,
        "missingness": "no surveyed banks",
        "review": "not_yet_accepted",
        "source_refs": [
            {"path": "configs/baseline.yaml",
             "key": "replay.hydraulics.bank_slope_zh", "expected": 1.5},
        ],
    },
    {
        "param_id": "replay.depth_m",
        "meaning": "Mean channel depth used by the replay solver",
        "units": "m",
        "param_class": "assumed",
        "source": "authored 1.1 in configs/baseline.yaml; DEM transects bound 0.3 to 1.0",
        "applicability": "Firehole chainage cells",
        "uncertainty": "DEM-derived per-feature profiles in configs/cross_sections.json",
        "missingness": "no surveyed bathymetry",
        "review": "not_yet_accepted",
        "source_refs": [
            {"path": "configs/baseline.yaml", "key": "replay.depth_m",
             "expected": 1.1},
        ],
    },
    {
        "param_id": "replay.dispersion_m2_s",
        "meaning": "Longitudinal dispersion coefficient",
        "units": "m2/s",
        "param_class": "illustrative",
        "source": "authored 1.0 in configs/baseline.yaml; 84.7 mapped Fischer median in sensitivity runs",
        "applicability": "Firehole chainage cells",
        "uncertainty": "D1 vs D85 sweep shifts refuge 636 m with nil ecology change",
        "missingness": "no tracer study",
        "review": "not_yet_accepted",
        "source_refs": [
            {"path": "configs/baseline.yaml",
             "key": "replay.dispersion_m2_s", "expected": 1.0},
        ],
    },
    {
        "param_id": "replay.exchange_w_m2_k",
        "meaning": "Newton surface exchange coefficient",
        "units": "W/m2/K",
        "param_class": "illustrative",
        "source": "authored 12.0 in configs/baseline.yaml",
        "applicability": "ice-free replay windows",
        "uncertainty": UNKNOWN,
        "missingness": "no eddy-covariance or surface flux survey",
        "review": "not_yet_accepted",
        "source_refs": [
            {"path": "configs/baseline.yaml",
             "key": "replay.exchange_w_m2_k", "expected": 12.0},
        ],
    },
    {
        "param_id": "hydro.boundary_m3s",
        "meaning": "Upstream discharge prescribed at the chain head",
        "units": "m3/s",
        "param_class": "assumed",
        "source": "authored 8.0 in configs/baseline.yaml; Burkhalter 1979 reports 2 to 3 baseflow",
        "applicability": "chain head cell, full run",
        "uncertainty": UNKNOWN,
        "missingness": "no gauge-anchored boundary series wired into baseline",
        "review": "not_yet_accepted",
        "source_refs": [
            {"path": "configs/baseline.yaml",
             "key": "hydro.boundary_m3s", "expected": 8.0},
        ],
    },
    {
        "param_id": "hydro.boundary_c",
        "meaning": "Upstream water temperature prescribed at the chain head",
        "units": "C",
        "param_class": "assumed",
        "source": "authored 17.5 in configs/baseline.yaml; observed max 29.5 in hot scenario notes",
        "applicability": "chain head cell, full run",
        "uncertainty": UNKNOWN,
        "missingness": "no gauge-anchored boundary series wired into baseline",
        "review": "not_yet_accepted",
        "source_refs": [
            {"path": "configs/baseline.yaml",
             "key": "hydro.boundary_c", "expected": 17.5},
        ],
    },
    {
        "param_id": "hydro.excelsior_discharge_m3s",
        "meaning": "Excelsior lateral inflow discharged into the mixing reach",
        "units": "m3/s",
        "param_class": "illustrative",
        "source": "authored 0.26; Excelsior above 4000 gpm (0.252 m3/s) order-magnitude ref",
        "applicability": "excelsior_mixing reach",
        "uncertainty": UNKNOWN,
        "missingness": "river-entry value, no vent measurement",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "hydro.excelsior_temperature_c",
        "meaning": "Temperature of the Excelsior lateral inflow",
        "units": "C",
        "param_class": "illustrative",
        "source": "authored 62.0 in configs/experiments/hot_surge.yaml; river_transport.py pulse series 62 to 80 to 62 C",
        "applicability": "excelsior_mixing reach",
        "uncertainty": UNKNOWN,
        "missingness": "river-entry value, no vent measurement",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "fish.thermal_species.anchors",
        "meaning": "Trout thermal anchor points by species and endpoint, with response as a [0, 1] index",
        "units": "C",
        "param_class": "literature",
        "source": "Kaya et al. 1977, Kaeding 1976, Kaeding and Kaya 1978 via fish.py",
        "applicability": "brown and rainbow trout, Firehole reach",
        "uncertainty": "per-study ranges carried in THERMAL_SPECIES records",
        "missingness": "curve shapes between anchors authored; lab CSV path unconfigured",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "fish.suitability.weights",
        "meaning": "Food, cover, temperature, velocity, depth weights in U",
        "units": "dimensionless",
        "param_class": "assumed",
        "source": "authored defaults wf 0.4, wc 0.3, wt 0.5, wv 0.4, wd 0.2",
        "applicability": "trout holding cells",
        "uncertainty": UNKNOWN,
        "missingness": "no selection experiment",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "snow.k_melt_fitted",
        "meaning": "Degree-day melt factor fitted per SNOTEL site",
        "units": "mm/C/day",
        "param_class": "calibrated",
        "source": "grid fit on WY2026 train split; 609 k 1.0, 924 k 0.75",
        "applicability": "sites 609 and 924, Oct to Jul window",
        "uncertainty": "holdout rmse 112 mm (609) and 45 mm (924); frozen-param WY2025 rmse 161 and 90",
        "missingness": "none on train window; three-day max forcing gap rule",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "hydro_thermal.RHO_CP",
        "meaning": "Volumetric heat capacity of water",
        "units": "J/(m3 K)",
        "param_class": "physical_constant",
        "source": "4.186e6 coded in hydro_thermal.py, profile helper scope",
        "applicability": "all water heat transport",
        "uncertainty": "constant value",
        "missingness": "none",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "snow.cover_full_depth_m",
        "meaning": "Snow depth at which snow_cover_fraction saturates to 1.0",
        "units": "m",
        "param_class": "assumed",
        "source": "authored 0.10 in snow_season.SNOW_COVER_FULL_DEPTH_M; "
                  "shared with exporters/godot_sidecars._snow_cover_fraction_from_depth",
        "applicability": "patch-level snow cover reporting for Godot overlay",
        "uncertainty": UNKNOWN,
        "missingness": "no vegetation-aware threshold study",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "runoff.catchment.coefficient",
        "meaning": "Runoff fraction of precipitation depth leaving as discharge",
        "units": "dimensionless",
        "param_class": "assumed",
        "source": "authored 0.4 default in overland_provider",
        "applicability": "synthetic upstream catchment",
        "uncertainty": UNKNOWN,
        "missingness": "no gauged runoff record for the catchment",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "runoff.discharge.spread_frac",
        "meaning": "Half-width fraction of the 90 percent discharge bounds",
        "units": "dimensionless",
        "param_class": "assumed",
        "source": "authored 0.3 default in overland_provider",
        "applicability": "synthetic upstream discharge series",
        "uncertainty": UNKNOWN,
        "missingness": "no ensemble spread to calibrate against",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "groundwater.lateral.flow_m3_s",
        "meaning": "Hand-authored lateral inflow attached to the reach",
        "units": "m3/s",
        "param_class": "illustrative",
        "source": "authored_lateral_not_modeled in groundwater_provider.STATUS",
        "applicability": "synthetic one-layer footprint under the reach",
        "uncertainty": UNKNOWN,
        "missingness": "no Darcy solve; no RIV budget read",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "groundwater.lateral.temperature_c",
        "meaning": "Temperature assigned to the authored lateral inflow",
        "units": "C",
        "param_class": "illustrative",
        "source": "authored_lateral_not_modeled in groundwater_provider.STATUS",
        "applicability": "synthetic receiving river cells",
        "uncertainty": UNKNOWN,
        "missingness": "no groundwater temperature logs; no Darcy solve",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "scenario.hot_lowflow.boundary_m3s",
        "meaning": "Upstream discharge used by the hot low-flow scenario",
        "units": "m3/s",
        "param_class": "illustrative",
        "source": "tools/scenario_constants.HOT_LOWFLOW_BOUNDARY_M3S "
                  "(Burkhalter 1979 MSc thesis, Montana State University)",
        "applicability": "hot low-flow scenario runners",
        "uncertainty": "citation chain only; primary source not verified "
                       "in repo",
        "missingness": "no gauge-anchored boundary record for the window",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "scenario.hot_lowflow.boundary_c",
        "meaning": "Upstream temperature used by the hot low-flow scenario",
        "units": "C",
        "param_class": "illustrative",
        "source": "tools/scenario_constants.HOT_LOWFLOW_BOUNDARY_C "
                  "(scenario-authored; Kaya et al. 1977 Prog. Fish-Cult. "
                  "39:37-39 observed max 29.5 C)",
        "applicability": "hot low-flow scenario runners",
        "uncertainty": "scenario-authored not measured; below 29.5 C "
                       "observed max",
        "missingness": "no co-measured boundary temperature series",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "scenario.hot_lowflow.boundary_c_sub_uilt",
        "meaning": "Upstream temperature variant 1 C below brown-trout UILT",
        "units": "C",
        "param_class": "illustrative",
        "source": "tools/scenario_constants.HOT_LOWFLOW_BOUNDARY_C_SUB_UILT "
                  "(authored flip test; UILT 26 C from "
                  "fish.THERMAL_SPECIES brown_trout.t_uilt_c)",
        "applicability": "hot low-flow flip test",
        "uncertainty": "scenario-authored flip test boundary",
        "missingness": "no co-measured boundary temperature series",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "scenario.hot_lowflow.refuge_threshold_c",
        "meaning": "Mean temperature threshold for refuge selection",
        "units": "C",
        "param_class": "literature",
        "source": "tools/scenario_constants.REFUGE_THRESHOLD_C "
                  "(Kaya, Kaeding, Burkhalter 1977 Prog. Fish-Cult. "
                  "39:37-39)",
        "applicability": "hot low-flow refuge analysis",
        "uncertainty": "citation chain only; abstract verified",
        "missingness": "no co-measured refuge selection record",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "river_world.pulse_temperature_upper_c",
        "meaning": "Upper physical guard on add_temperature_pulse inputs",
        "units": "C",
        "param_class": "assumed",
        "source": "river_world.add_temperature_pulse upper guard; site "
                  "boiling point near 93 C (microclimate.boiling_point_c "
                  "at SITE_PRESSURE_KPA)",
        "applicability": "study-pulse temperature forcing",
        "uncertainty": "authored physical ceiling, not measured",
        "missingness": "no co-measured pulse temperature series",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "groundwater.bed_conductivity_m_s",
        "meaning": "Bed conductivity used by the head-gradient exchange "
                   "q = C (h_aquifer - h_river)",
        "units": "m/s",
        "param_class": "assumed",
        "source": "authored head-gradient exchange input "
                  "(groundwater_provider head-gradient model)",
        "applicability": "river-aquifer exchange model",
        "uncertainty": UNKNOWN,
        "missingness": "no surveyed streambed sediment conductivity",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "groundwater.bed_thickness_m",
        "meaning": "Streambed thickness factor in head-gradient exchange",
        "units": "m",
        "param_class": "assumed",
        "source": "authored head-gradient exchange input "
                  "(groundwater_provider head-gradient model)",
        "applicability": "river-aquifer exchange model",
        "uncertainty": UNKNOWN,
        "missingness": "no surveyed streambed thickness",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "groundwater.aquifer_temperature_c",
        "meaning": "Aquifer temperature fed into river-aquifer exchange",
        "units": "C",
        "param_class": "assumed",
        "source": "aquifer_temperature_source: authored; replace with "
                  "well record when available",
        "applicability": "river-aquifer exchange model",
        "uncertainty": UNKNOWN,
        "missingness": "no co-measured aquifer temperature",
        "review": "not_yet_accepted",
    },
    {
        "param_id": "river_transport.courant_warning_threshold",
        "meaning": "Advective Courant number above which the transport "
                   "solver emits a numerical warning",
        "units": "dimensionless",
        "param_class": "physical_constant",
        "source": "river_transport.numerical_warnings threshold "
                  "(Courant-Friedrichs-Lewy stability bound 1.0)",
        "applicability": "river transport stability check",
        "uncertainty": "stability bound, not measurement",
        "missingness": "none",
        "review": "accepted",
    },
    {
        "param_id": "river_transport.diffusive_number_warning_threshold",
        "meaning": "Diffusive von Neumann number above which the transport "
                   "solver emits a numerical warning",
        "units": "dimensionless",
        "param_class": "physical_constant",
        "source": "river_transport.numerical_warnings threshold (von "
                  "Neumann stability bound 1.0 for explicit diffusion)",
        "applicability": "river transport stability check",
        "uncertainty": "stability bound, not measurement",
        "missingness": "none",
        "review": "accepted",
    },
]


def validate_entry(entry: dict) -> list:
    errors = []
    pid = entry.get("param_id") if isinstance(entry, dict) else None
    label = pid if isinstance(pid, str) and pid.strip() else "?"
    for f in ENTRY_FIELDS:
        value = entry.get(f)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"param {label}: {f} must be a non-empty string")
    if label != "?":
        for seg in pid.split("."):
            if not seg or not all(ch.isalnum() or ch == "_" for ch in seg):
                errors.append(f"param {pid}: param_id segments must be "
                              "dot-separated words")
                break
    if entry.get("param_class") not in PARAM_CLASSES:
        errors.append(f"param {label}: "
                      f"class {entry.get('param_class')!r} outside registry")
    if entry.get("review") not in REVIEW_STATUSES:
        errors.append(f"param {label}: "
                      f"review {entry.get('review')!r} unknown; "
                      f"have {list(REVIEW_STATUSES)}")
    units = entry.get("units")
    if isinstance(units, str) and units.strip() and "," in units:
        errors.append(f"param {label}: units {units!r} name two quantities; "
                      "use one record per quantity")
    errors += _validate_source_refs(entry.get("source_refs"), label)
    return errors


def _validate_source_refs(refs, label: str) -> list:
    if refs is None:
        return []
    errors = []
    if not isinstance(refs, list) or not refs:
        errors.append(f"param {label}: source_refs must be a nonempty list")
        return errors
    for ref in refs:
        if not isinstance(ref, dict):
            errors.append(f"param {label}: source_refs entry must be an "
                          "object")
            continue
        for f in SOURCE_REF_FIELDS:
            if f not in ref:
                errors.append(f"param {label}: source_refs missing {f!r}")
        for f in ("path", "key"):
            if not isinstance(ref.get(f), str) or not ref[f].strip():
                errors.append(f"param {label}: source_refs {f} must be a "
                              "non-empty string")
    return errors


def _lookup(mapping: dict, dotted: str):
    node = mapping
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def source_ref_errors(configs: dict) -> list:
    """Verify source_refs against configs (map of path -> parsed mapping).
    Missing path, missing key, or value mismatch is reported."""
    errors = []
    for entry in PARAMS:
        pid = entry.get("param_id") if isinstance(entry, dict) else None
        label = pid if isinstance(pid, str) and pid.strip() else "?"
        for ref in entry.get("source_refs") or []:
            path = ref.get("path")
            key = ref.get("key", "")
            expected = ref.get("expected")
            if path not in configs:
                errors.append(f"param {label}: no config supplied for "
                              f"{path!r}")
                continue
            value, found = _lookup(configs[path], key)
            if not found:
                errors.append(f"param {label}: {path} has no key {key!r}")
            elif value != expected:
                errors.append(f"param {label}: {path}:{key} is {value!r}, "
                              f"registry claims {expected!r}")
    return errors


def registry_errors() -> list:
    errors = []
    ids = []
    for e in PARAMS:
        errors += validate_entry(e)
        pid = e.get("param_id") if isinstance(e, dict) else None
        if isinstance(pid, str) and pid.strip():
            ids.append(pid)
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        errors.append(f"duplicate param_id in registry: {dupes}")
    return errors
