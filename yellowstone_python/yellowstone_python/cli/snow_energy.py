"""Command-line interface for snow energy."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite_param
from yellowstone_python.common.io import write_json_atomic
import argparse
import json
import math
from pathlib import Path
from yellowstone_python.river.hydraulics import score_paired_series
from yellowstone_python.land.snow_season import SNOW_TEMP_C, step_snow
from yellowstone_python.land.snow_validate import SPLIT_DATE, STATUS, in_to_mm, peak_timing_error_days, train_holdout_split
from yellowstone_python.land.snow_energy import evaluate_fixed_params, load_fixed_params, run_validation

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split-date", default=SPLIT_DATE)
    parser.add_argument("--fixed-params", type=Path, default=None,
                        help="prior fit artifact for a no-refit "
                             "second-window test; omit to fit")
    args = parser.parse_args()
    if args.fixed_params is not None:
        fixed = load_fixed_params(str(args.fixed_params))
        artifact = evaluate_fixed_params(str(args.bundle), fixed,
                                         split=args.split_date)
    else:
        artifact = run_validation(str(args.bundle), split=args.split_date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.out, artifact, indent=1)
    for triplet, site in artifact["sites"].items():
        params = site.get("fitted", site.get("frozen", {}))
        dd = site.get("degree_day_holdout_rmse_mm", "n/a")
        print(f"{triplet}: s_rad={params.get('s_rad')} "
              f"c_t={params.get('c_turb_w_m2_k')} "
              f"holdout_rmse={site['holdout_swe_mm']['rmse']}mm "
              f"vs persist={site['null_persistence_rmse_mm']}mm "
              f"vs nomelt={site['null_nomelt_rmse_mm']}mm "
              f"vs degreeday={dd}mm "
              f"peak_err={site['peak_timing_error_days']}d"
              + (" beats_nulls=" + str(site["beats_both_nulls"])
                 if "beats_both_nulls" in site else "")
              + (" beats_dd=" + str(site["beats_degree_day"])
                 if "beats_degree_day" in site else ""))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
