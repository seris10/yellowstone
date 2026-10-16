"""Score predicted chloride flux against observed specific conductance."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yellowstone_python.river.solute_transport import chloride_from_specific_conductance, fit_chloride_from_conductance, load_hydrothermal_solutes

SCHEMA = "yellowstone.solute_validation.v1"


@dataclass(frozen=True)
class GaugeRecord:
    """Single aligned sample of gauge discharge and specific conductance in epoch seconds."""
    epoch_s: float
    discharge_m3_s: float
    sc_us_cm: float


def _as_records(rows: Any) -> list[GaugeRecord]:
    out: list[GaugeRecord] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(GaugeRecord(
                epoch_s=float(row["epoch_s"]),
                discharge_m3_s=float(row["discharge_m3_s"]),
                sc_us_cm=float(row["sc_us_cm"]),
            ))
        else:
            epoch, q, sc = row
            out.append(GaugeRecord(
                epoch_s=float(epoch),
                discharge_m3_s=float(q),
                sc_us_cm=float(sc),
            ))
    return out


def load_relation(path: Path | None = None) -> dict[str, Any]:
    """Return the stored chloride-conductance relation and its provenance."""
    document = load_hydrothermal_solutes(path)
    return document["chloride_specific_conductance_relation"]


def observed_chloride_series(
    records: list[GaugeRecord],
    slope_mg_l_per_us_cm: float,
    intercept_mg_l: float,
) -> list[dict[str, float]]:
    """Convert each gauge record's specific conductance to chloride and chloride flux."""
    out: list[dict[str, float]] = []
    for record in records:
        chloride_mg_l = chloride_from_specific_conductance(
            record.sc_us_cm, slope_mg_l_per_us_cm, intercept_mg_l,
        )
        # Flux grams per second = concentration mg per L times discharge m3 per s times unit conversion.
        flux_g_s = chloride_mg_l * record.discharge_m3_s
        out.append({
            "epoch_s": record.epoch_s,
            "discharge_m3_s": record.discharge_m3_s,
            "sc_us_cm": record.sc_us_cm,
            "chloride_mg_l": chloride_mg_l,
            "chloride_flux_g_s": flux_g_s,
        })
    return out


def _match_predicted(
    predictions: list[dict[str, float]],
    epochs: list[float],
    key: str,
) -> list[float]:
    """Nearest-time join of predicted series onto gauge epochs by linear interpolation."""
    if not predictions:
        raise ValueError("no predicted samples supplied")
    pred_epochs = [float(p["epoch_s"]) for p in predictions]
    pred_values = [float(p[key]) for p in predictions]
    out: list[float] = []
    for t in epochs:
        # Linear interpolation; clamped at the ends.
        if t <= pred_epochs[0]:
            out.append(pred_values[0])
            continue
        if t >= pred_epochs[-1]:
            out.append(pred_values[-1])
            continue
        lo = 0
        hi = len(pred_epochs) - 1
        while hi - lo > 1:
            mid = (hi + lo) // 2
            if pred_epochs[mid] <= t:
                lo = mid
            else:
                hi = mid
        span = pred_epochs[hi] - pred_epochs[lo]
        if span == 0.0:
            out.append(pred_values[lo])
        else:
            frac = (t - pred_epochs[lo]) / span
            out.append(pred_values[lo] + frac * (pred_values[hi] - pred_values[lo]))
    return out


def score_chloride_prediction(
    predictions: list[dict[str, float]],
    gauge_records: list[dict[str, float]] | list[GaugeRecord],
    slope_mg_l_per_us_cm: float | None = None,
    intercept_mg_l: float | None = None,
    data_path: Path | None = None,
) -> dict[str, Any]:
    """Compare predicted chloride and chloride flux against gauge-derived observations."""
    if slope_mg_l_per_us_cm is None or intercept_mg_l is None:
        relation = load_relation(data_path)
        if slope_mg_l_per_us_cm is None:
            slope_mg_l_per_us_cm = float(relation["slope_mg_l_per_us_cm"])
        if intercept_mg_l is None:
            intercept_mg_l = float(relation["intercept_mg_l"])
    records = _as_records(gauge_records)
    observed = observed_chloride_series(
        records, slope_mg_l_per_us_cm, intercept_mg_l,
    )
    gauge_epochs = [r.epoch_s for r in records]
    predicted_c = _match_predicted(predictions, gauge_epochs, "chloride_mg_l")
    predicted_flux = _match_predicted(predictions, gauge_epochs, "chloride_flux_g_s")
    observed_c = [row["chloride_mg_l"] for row in observed]
    observed_flux = [row["chloride_flux_g_s"] for row in observed]

    n = len(gauge_epochs)
    if n == 0:
        raise ValueError("no gauge records supplied")
    bias_c = math.fsum(p - o for p, o in zip(predicted_c, observed_c)) / n
    rmse_c = math.sqrt(
        math.fsum((p - o) ** 2 for p, o in zip(predicted_c, observed_c)) / n
    )
    bias_flux = math.fsum(
        p - o for p, o in zip(predicted_flux, observed_flux)
    ) / n
    rmse_flux = math.sqrt(
        math.fsum((p - o) ** 2 for p, o in zip(predicted_flux, observed_flux)) / n
    )
    sum_observed_flux = math.fsum(observed_flux)
    sum_predicted_flux = math.fsum(predicted_flux)
    if sum_observed_flux == 0.0:
        ratio = math.inf if sum_predicted_flux > 0.0 else 1.0
    else:
        ratio = sum_predicted_flux / sum_observed_flux

    return {
        "schema": SCHEMA,
        "status": "fitted_not_validated_single_window",
        "n": n,
        "slope_mg_l_per_us_cm": slope_mg_l_per_us_cm,
        "intercept_mg_l": intercept_mg_l,
        "chloride_bias_mg_l": bias_c,
        "chloride_rmse_mg_l": rmse_c,
        "chloride_flux_bias_g_s": bias_flux,
        "chloride_flux_rmse_g_s": rmse_flux,
        "chloride_flux_sum_predicted_g_s": sum_predicted_flux,
        "chloride_flux_sum_observed_g_s": sum_observed_flux,
        "chloride_flux_predicted_over_observed": ratio,
        "window_epoch_s": [gauge_epochs[0], gauge_epochs[-1]],
    }


def fit_relation_from_paired_bundle(bundle_path: Path) -> dict[str, Any]:
    """Fit the conductance-to-chloride relation from paired samples in a chem bundle."""
    document = json.loads(bundle_path.read_text(encoding="utf-8"))
    paired = []
    for entry in document.get("paired_samples", []):
        if (
            entry.get("sc_us_cm") is None
            or entry.get("chloride_mg_l") is None
        ):
            continue
        paired.append({
            "sc_us_cm": float(entry["sc_us_cm"]),
            "chloride_mg_l": float(entry["chloride_mg_l"]),
        })
    if len(paired) < 2:
        raise ValueError(
            f"{bundle_path}: fewer than two paired samples; no fit possible"
        )
    fit = fit_chloride_from_conductance(paired)
    result: dict[str, Any] = {}
    for key, value in fit.items():
        result[key] = value
    result["schema"] = SCHEMA
    result["source"] = str(bundle_path)
    result["n_paired"] = len(paired)
    return result
