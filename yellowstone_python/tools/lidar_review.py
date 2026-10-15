"""Frozen blind dominant-crown review and submitted-label evaluation."""
from __future__ import annotations

import argparse
from pathlib import Path

from yellowstone_python.common.io import load_json, write_json_atomic
from yellowstone_python.census.census_validate import evaluate_lidar_blind_crops, sample_lidar_blind_crops


def main(argv=None):
    """Freeze unmarked review crops or evaluate explicitly submitted reference labels."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--census", type=Path, required=True)
    sample.add_argument("--image", type=Path, required=True)
    sample.add_argument("--out", type=Path, required=True)
    sample.add_argument("--image-date", required=True)
    sample.add_argument("--chm", type=Path, required=True)
    sample.add_argument("--chm-metadata", type=Path, required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--validation-dir", type=Path, required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "sample":
        import yellowstone_python.census.canopy_census as detector
        sample_lidar_blind_crops(load_json(args.census), args.image, args.out,
            source_paths={"raw_chm": args.chm, "chm_metadata": args.chm_metadata,
                          "detector_module": Path(detector.__file__)},
            imagery_metadata={"acquisition_date": args.image_date})
    else:
        write_json_atomic(args.out, evaluate_lidar_blind_crops(args.validation_dir), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
