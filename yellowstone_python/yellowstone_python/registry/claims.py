"""Claim registry: bounded scientific claims with acceptance state."""
from __future__ import annotations

from pathlib import Path

REQUIRED_CLAIM_FIELDS = (
    "claim_id",
    "predicted_quantity",
    "intended_use",
    "spatial_domain",
    "temporal_domain",
    "supported_conditions",
    "model_version",
    "implementation_status",
    "evidence_status",
    "required_processes",
    "required_observations",
    "calibration_dataset_ids",
    "evaluation_dataset_ids",
    "metrics",
    "acceptance_criteria",
    "known_exclusions",
    "evidence_artifact_ids",
    "review_status",
)
# Optional fields are typed; absence is not a missing-field error.
OPTIONAL_CLAIM_FIELDS = ("acceptance",)
CLAIM_FIELDS = REQUIRED_CLAIM_FIELDS + OPTIONAL_CLAIM_FIELDS

LIST_FIELDS = (
    "required_processes",
    "required_observations",
    "calibration_dataset_ids",
    "evaluation_dataset_ids",
    "metrics",
    "known_exclusions",
    "evidence_artifact_ids",
)

STRING_FIELDS = (
    "claim_id",
    "predicted_quantity",
    "intended_use",
    "supported_conditions",
    "model_version",
    "implementation_status",
    "evidence_status",
    "acceptance_criteria",
    "review_status",
)

REVIEW_STATUSES = ("not_yet_accepted", "accepted")
IMPLEMENTATION_STATUSES = ("implemented", "planned_not_implemented",
                           "partial")
EVIDENCE_STATUSES = ("evidence_artifacts_present",
                     "no_evidence_artifacts",
                     "partial_evidence_artifacts")

ACCEPTED_REQUIRED_FIELDS = (
    "evaluation_dataset_ids",
    "evidence_artifact_ids",
    "metrics",
)
ACCEPTANCE_SUBFIELDS = (
    "reviewed_by",
    "reviewed_at_utc",
    "build_id",
    "evaluation_result_artifact",
)

VALID_SPLITS = frozenset({"train", "dev", "holdout", "locked-final",
                          "prior-window"})

MODEL_VERSION = "yellowstone_python-0.1.0"

MODEL_VERSIONS = {
    "thermal_replay": "0.2.0",
    "surface_flux": "0.2.0",
    "snow_soil": "0.1.0",
    "overland_flow": "0.1.0",
    "hydro_chain": "0.1.0",
}

SPLIT_SEP = ":"

CLAIMS = [
    {
        "claim_id": "reach_water_temperature_ice_free",
        "predicted_quantity": "reach-mean water temperature, hourly",
        "intended_use": "thermal habitat input for trout refuge selection",
        "spatial_domain": "Firehole chainage cells, river_5856_0 and tributary junctions",
        "temporal_domain": "ice-free season, 2-hour replay windows",
        "supported_conditions": "upstream discharge and temperature prescribed, met forcing given",
        "model_version": MODEL_VERSIONS["thermal_replay"],
        "implementation_status": "implemented",
        "evidence_status": "evidence_artifacts_present",
        "required_processes": ["advection-dispersion transport", "tributary mixing",
                               "surface heat exchange"],
        "required_observations": ["upstream discharge series", "upstream temperature series",
                                  "downstream temperature series", "air temperature series"],
        "calibration_dataset_ids": ["derived/firehole_obs.json:train"],
        "evaluation_dataset_ids": ["derived/firehole_obs.json:holdout",
                                   "derived/usgs_06036805.json",
                                   "derived/firehole_obs_locked_final.json"],
        "metrics": ["replay_heat_budget_error", "heat_relative_residual",
                    "train_rmse", "train_bias",
                    "holdout_rmse", "holdout_bias"],
        "acceptance_criteria": "frozen calibration/dev/locked-final split; "
                               "holdout rmse below persistence, mixing-only, "
                               "and climatology nulls; "
                               "budget residuals within 1e-9",
        "known_exclusions": ["winter ice cover", "other reaches",
                             "sub-cell thermal refuges", "boiling conditions"],
        "evidence_artifact_ids": ["derived/reach_heat_fit_v300k.json",
                                  "derived/reach_polished_fit_v300k.json",
                                  "derived/reach_ensemble_uq_v300k.json"],
        "review_status": "not_yet_accepted",
    },
    {
        "claim_id": "snow_swe_clearings",
        "predicted_quantity": "daily snow water equivalent, mm",
        "intended_use": "season state for soil moisture and phenology",
        "spatial_domain": "SNOTEL sites 609 Madison Plateau and 924 West Yellowstone",
        "temporal_domain": "accumulation season train, melt season holdout",
        "supported_conditions": "daily air temperature and precipitation forcing given",
        "model_version": MODEL_VERSIONS["snow_soil"],
        "implementation_status": "implemented",
        "evidence_status": "evidence_artifacts_present",
        "required_processes": ["degree-day melt", "wind redistribution",
                               "soil bucket drainage"],
        "required_observations": ["daily WTEQ", "daily PRCP", "daily TAVG"],
        "calibration_dataset_ids": ["derived/snotel_obs.json:train"],
        "evaluation_dataset_ids": ["derived/snotel_obs.json:holdout",
                                   "derived/snotel_obs_prior_window.json"],
        "metrics": ["holdout_rmse_mm", "peak_timing_error_d", "null_beats"],
        "acceptance_criteria": "frozen params beat persistence and no-melt nulls "
                               "on a locked final window; bias sign reported",
        "known_exclusions": ["forested interception sites", "wind-scoured ridges",
                             "rain-on-snow events"],
        "evidence_artifact_ids": ["derived/snow_degree_day_fit.json",
                                  "derived/snow_degree_day_fit_prior_window.json",
                                  "derived/snow_energy_fit.json"],
        "review_status": "not_yet_accepted",
    },
    {
        "claim_id": "upstream_discharge_predicted",
        "predicted_quantity": "upstream discharge, hourly",
        "intended_use": "predictive inflow for the replay boundary cell",
        "spatial_domain": "synthetic catchment above the chain head cell",
        "temporal_domain": "single storm and interstorm windows, hourly steps",
        "supported_conditions": "precipitation forcing and catchment area given",
        "model_version": MODEL_VERSIONS["overland_flow"],
        "implementation_status": "planned_not_implemented",
        "evidence_status": "no_evidence_artifacts",
        "required_processes": ["upstream discharge prediction",
                               "runoff generation",
                               "flow accumulation routing"],
        "required_observations": ["precipitation series", "catchment area survey",
                                  "gauge discharge series"],
        "calibration_dataset_ids": [],
        "evaluation_dataset_ids": [],
        "metrics": ["bias_m3_s", "mae_m3_s", "coverage_90"],
        "acceptance_criteria": "holdout discharge within 90 percent bounds; "
                               "bias sign reported",
        "known_exclusions": ["snowmelt routing", "regulated releases",
                             "ungauged tributaries"],
        "evidence_artifact_ids": [],
        "review_status": "not_yet_accepted",
    },
    {
        "claim_id": "groundwater_lateral_heat",
        "predicted_quantity": "lateral groundwater inflow and temperature",
        "intended_use": "subsurface heat input for receiving river cells",
        "spatial_domain": "synthetic one-layer footprint under the Firehole reach",
        "temporal_domain": "per stress period, steady heads",
        "supported_conditions": "river stage and aquifer properties prescribed",
        "model_version": MODEL_VERSION,
        "implementation_status": "planned_not_implemented",
        "evidence_status": "no_evidence_artifacts",
        "required_processes": ["groundwater heat transport",
                               "river-aquifer exchange",
                               "subsurface advection"],
        "required_observations": ["piezometer head series",
                                  "groundwater temperature logs",
                                  "river stage series"],
        "calibration_dataset_ids": [],
        "evaluation_dataset_ids": [],
        "metrics": ["head_rmse_m", "lateral_temp_bias_C"],
        "acceptance_criteria": "heads within observation error; lateral "
                               "temperatures validated against logs",
        "known_exclusions": ["unsaturated flow", "fracture networks",
                             "reactive transport"],
        "evidence_artifact_ids": [],
        "review_status": "not_yet_accepted",
    },
    {
        "claim_id": "channel_velocity_inundation_2d",
        "predicted_quantity": "depth-averaged velocity and inundation extent",
        "intended_use": "floodplain exchange and habitat velocity input",
        "spatial_domain": "synthetic Firehole reach planform",
        "temporal_domain": "single high-flow event window",
        "supported_conditions": "bathymetry surveyed, inflow hydrograph given",
        "model_version": MODEL_VERSION,
        "implementation_status": "planned_not_implemented",
        "evidence_status": "no_evidence_artifacts",
        "required_processes": ["2-D hydraulics velocity",
                               "inundation mapping",
                               "shallow-water momentum"],
        "required_observations": ["surveyed bathymetry", "velocity transects",
                                  "mapped inundation extent"],
        "calibration_dataset_ids": [],
        "evaluation_dataset_ids": [],
        "metrics": ["velocity_rmse_m_s", "extent_f1"],
        "acceptance_criteria": "velocity within transect error; extent "
                               "overlap above agreed threshold",
        "known_exclusions": ["ice jams", "debris blockages",
                             "morphodynamic change"],
        "evidence_artifact_ids": [],
        "review_status": "not_yet_accepted",
    },
]


def split_artifact_id(artifact_id: str) -> tuple:
    """(file path, split or None) for a registry ID."""
    if SPLIT_SEP in artifact_id:
        path, _, split = artifact_id.partition(SPLIT_SEP)
        if not path or not split or SPLIT_SEP in split:
            raise ValueError(f"malformed artifact id {artifact_id!r}")
        if split not in VALID_SPLITS:
            raise ValueError(
                f"unknown dataset split {split!r} in {artifact_id!r}; "
                f"allowed: {sorted(VALID_SPLITS)}")
        return path, split
    return artifact_id, None


def resolve_artifact_id(artifact_id: str, root=None) -> Path:
    """Project-rooted path for a registry ID; raises when the file is absent
or when the resolved path escapes the project root."""
    path, _ = split_artifact_id(artifact_id)
    if not path or "\x00" in path or " " in path:
        raise ValueError(f"malformed artifact id {artifact_id!r}")
    candidate = Path(path)
    if candidate.is_absolute() or candidate.anchor:
        raise ValueError(
            f"artifact id {artifact_id!r} must be project-relative")
    base = (Path(root).expanduser().resolve() if root is not None
            else Path(__file__).resolve().parents[2])
    try:
        full = (base / candidate).resolve()
    except OSError as exc:
        raise ValueError(
            f"artifact id {artifact_id!r} is unresolvable: {exc}") from exc
    try:
        full.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"artifact id {artifact_id!r} escapes project root") from exc
    if not full.is_file():
        raise FileNotFoundError(
            f"registry id {artifact_id!r} resolves to missing file {full}")
    return full


def get_claim(claim_id: str) -> dict:
    for c in CLAIMS:
        if c["claim_id"] == claim_id:
            return c
    raise KeyError(f"unknown claim {claim_id!r}")


def validate_claim(record: dict, root=None) -> list:
    """Field presence, type checks, vocabularies, resolvable paths.
root selects where artifact paths resolve, defaulting to package root."""
    errors: list[str] = []
    label = record.get("claim_id", "?")
    for field in REQUIRED_CLAIM_FIELDS:
        if field not in record:
            errors.append(f"claim {label}: missing field {field}")
    unknown = set(record) - set(CLAIM_FIELDS)
    for field in sorted(unknown):
        errors.append(f"claim {label}: unknown field {field}")
    for field in LIST_FIELDS:
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"claim {label}: {field} must be a list")
            continue
        if not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(
                f"claim {label}: {field} must contain only non-empty strings")
    for field in STRING_FIELDS:
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"claim {label}: {field} must be a non-empty string")
    # spatial_domain and temporal_domain accept a non-empty string or a non-empty per-process mapping.
    for field in ("spatial_domain", "temporal_domain"):
        value = record.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            if not value.strip():
                errors.append(f"claim {label}: {field} must be non-empty")
        elif isinstance(value, dict):
            if not value:
                errors.append(f"claim {label}: {field} mapping is empty")
        else:
            errors.append(
                f"claim {label}: {field} must be a string or mapping")
    if record.get("review_status") not in REVIEW_STATUSES:
        errors.append(
            f"claim {label}: review_status "
            f"{record.get('review_status')!r} unknown")
    if ("implementation_status" in record
            and record["implementation_status"] not in IMPLEMENTATION_STATUSES):
        errors.append(
            f"claim {label}: implementation_status "
            f"{record.get('implementation_status')!r} unknown")
    if ("evidence_status" in record
            and record["evidence_status"] not in EVIDENCE_STATUSES):
        errors.append(
            f"claim {label}: evidence_status "
            f"{record.get('evidence_status')!r} unknown")
    if record.get("review_status") == "accepted":
        for field in ACCEPTED_REQUIRED_FIELDS:
            if not record.get(field):
                errors.append(
                    f"claim {label}: accepted claims require {field}")
        acceptance = record.get("acceptance")
        if not isinstance(acceptance, dict):
            errors.append(
                f"claim {label}: accepted claims require an "
                f"acceptance block with {list(ACCEPTANCE_SUBFIELDS)}")
        else:
            for sub in ACCEPTANCE_SUBFIELDS:
                value = acceptance.get(sub)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"claim {label}: acceptance.{sub} must be a "
                        f"non-empty string")
    acceptance = record.get("acceptance")
    if acceptance is not None and not isinstance(acceptance, dict):
        errors.append(f"claim {label}: acceptance must be a mapping")
    for key in ("calibration_dataset_ids", "evaluation_dataset_ids",
                "evidence_artifact_ids"):
        value = record.get(key, [])
        if not isinstance(value, list):
            continue
        for aid in value:
            if not isinstance(aid, str):
                continue
            try:
                resolve_artifact_id(aid, root=root)
            except (ValueError, FileNotFoundError) as exc:
                errors.append(f"claim {label}: {exc}")
    return errors


def registry_errors(root=None) -> list:
    """Per-claim errors plus duplicate-id detection. root routes artifact
resolution to a specific tree (for example, a build directory)."""
    errors: list[str] = []
    for c in CLAIMS:
        errors += validate_claim(c, root=root)
    ids = [c["claim_id"] for c in CLAIMS]
    if len(ids) != len(set(ids)):
        errors.append("duplicate claim_id in registry")
    return errors
