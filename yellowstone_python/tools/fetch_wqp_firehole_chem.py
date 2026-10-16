"""Water Quality Portal chemistry retrieval at the Firehole gauges."""
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yellowstone_python.observations.bundles import atomic_write_json

from yellowstone_python.river.solute_transport import fit_chloride_from_conductance

WQP_URL = "https://www.waterqualitydata.us/data/Result/search"
USER_AGENT = "yellowstone-python/0.1 (research calibration fetch)"
TIMEOUT_S = 180

SCHEMA_PAIRED = "yellowstone.firehole_chem_paired_samples.v1"
SCHEMA_UP = "yellowstone.firehole_upstream_sc_samples.v1"
SCHEMA_FIT = "yellowstone.firehole_chloride_sc_fit.v1"

SITES = ("USGS-06036805", "USGS-06036905")
CHARACTERISTICS = (
    "Chloride",
    "Specific conductance",
    "Arsenic",
    "Boron",
    "pH",
    "Dissolved oxygen (DO)",
)


def _query_url() -> str:
    params = [
        ("siteid", ";".join(SITES)),
        ("mimeType", "csv"),
        ("dataProfile", "narrowResult"),
    ]
    for name in CHARACTERISTICS:
        params.append(("characteristicName", name))
    return f"{WQP_URL}?{urllib.parse.urlencode(params, safe=';()')}"


def fetch_wqp_csv() -> str:
    url = _query_url()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read().decode("utf-8", errors="replace")


def pair_downstream_samples(csv_text: str) -> list[dict]:
    by_activity: dict[str, dict] = defaultdict(dict)
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        if row["MonitoringLocationIdentifier"] != "USGS-06036905":
            continue
        name = row["CharacteristicName"]
        if name not in ("Chloride", "Specific conductance"):
            continue
        text = row["ResultMeasureValue"].strip()
        if not text:
            continue
        try:
            vf = float(text)
        except ValueError:
            continue
        activity = row["ActivityIdentifier"]
        key = "chloride_mg_l" if name == "Chloride" else "sc_us_cm"
        if key in by_activity[activity]:
            continue
        by_activity[activity][key] = vf
        by_activity[activity]["date"] = row["ActivityStartDate"]
    paired = [
        {"activity_id": a, "date": r["date"],
         "sc_us_cm": r["sc_us_cm"],
         "chloride_mg_l": r["chloride_mg_l"]}
        for a, r in by_activity.items()
        if "chloride_mg_l" in r and "sc_us_cm" in r
    ]
    paired.sort(key=lambda r: r["date"])
    return paired


def upstream_sc_samples(csv_text: str) -> list[dict]:
    out: list[dict] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        if row["MonitoringLocationIdentifier"] != "USGS-06036805":
            continue
        if row["CharacteristicName"] != "Specific conductance":
            continue
        text = row["ResultMeasureValue"].strip()
        if not text:
            continue
        try:
            vf = float(text)
        except ValueError:
            continue
        out.append({
            "activity_id": row["ActivityIdentifier"],
            "date": row["ActivityStartDate"],
            "sc_us_cm": vf,
        })
    out.sort(key=lambda r: r["date"])
    return out


def build_fit(paired: list[dict]) -> dict[str, Any]:
    samples = [
        {"sc_us_cm": p["sc_us_cm"], "chloride_mg_l": p["chloride_mg_l"]}
        for p in paired
    ]
    fit = fit_chloride_from_conductance(samples)
    residuals = [
        s["chloride_mg_l"] - (
            fit["slope_mg_l_per_us_cm"] * s["sc_us_cm"]
            + fit["intercept_mg_l"]
        )
        for s in samples
    ]
    rms = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    return {
        "schema": SCHEMA_FIT,
        "status": "fitted_not_validated",
        "site_id": "USGS-06036905",
        "n_paired": fit["n"],
        "slope_mg_l_per_us_cm": fit["slope_mg_l_per_us_cm"],
        "intercept_mg_l": fit["intercept_mg_l"],
        "r_squared": fit["r_squared"],
        "residual_rms_mg_l": rms,
        "method": "ordinary_least_squares_chloride_on_sc",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="output directory for the three JSON files")
    args = parser.parse_args()

    text = fetch_wqp_csv()
    retrieved = datetime.now(timezone.utc).isoformat()

    paired = pair_downstream_samples(text)
    up_samples = upstream_sc_samples(text)
    fit = build_fit(paired) if len(paired) >= 2 else None

    sc_values = [r["sc_us_cm"] for r in up_samples]
    sc_median = (sorted(sc_values)[len(sc_values) // 2]
                 if sc_values else None)

    paired_doc = {
        "schema": SCHEMA_PAIRED,
        "status": "measured_remote_not_calibrated",
        "assembled_at_utc": retrieved,
        "site_id": "USGS-06036905",
        "n_paired": len(paired),
        "provenance": {
            "source": "Water Quality Portal (waterqualitydata.us)",
            "url": _query_url(),
            "agency": "USGS",
            "terms": "USGS Water Services and NWIS provisional terms.",
        },
        "paired_samples": paired,
    }

    up_doc = {
        "schema": SCHEMA_UP,
        "status": "measured_remote_not_calibrated",
        "assembled_at_utc": retrieved,
        "site_id": "USGS-06036805",
        "n": len(up_samples),
        "sc_min_us_cm": min(sc_values) if sc_values else None,
        "sc_max_us_cm": max(sc_values) if sc_values else None,
        "sc_median_us_cm": sc_median,
        "sc_mean_us_cm": (sum(sc_values) / len(sc_values)
                          if sc_values else None),
        "provenance": {
            "source": "Water Quality Portal (waterqualitydata.us)",
            "url": _query_url(),
            "agency": "USGS",
            "terms": "USGS Water Services and NWIS provisional terms.",
            "note": ("Site 06036805 has only discrete specific-conductance "
                     "samples in the Water Quality Portal; no discrete "
                     "chloride, arsenic or boron samples at this gauge."),
        },
        "samples": up_samples,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.out_dir / "firehole_chem_paired_samples.json",
                      paired_doc)
    atomic_write_json(args.out_dir / "firehole_upstream_sc_samples.json",
                      up_doc)
    if fit is not None:
        fit_doc = {
            **fit,
            "assembled_at_utc": retrieved,
            "paired_sample_source": str(
                args.out_dir / "firehole_chem_paired_samples.json"),
        }
        atomic_write_json(args.out_dir / "firehole_chloride_sc_fit.json",
                          fit_doc)
        print(f"paired={len(paired)} slope={fit['slope_mg_l_per_us_cm']:.6f} "
              f"intercept={fit['intercept_mg_l']:.3f} "
              f"r2={fit['r_squared']:.4f} "
              f"residual_rms={fit['residual_rms_mg_l']:.3f}")
    print(f"upstream SC samples: {len(up_samples)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
