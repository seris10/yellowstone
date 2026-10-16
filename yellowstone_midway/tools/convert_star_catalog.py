"""Convert Yale Bright Star Catalog V/50 rows into the sky catalog."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "references" / "bsc5_catalog.gz"
DEFAULT_OUT = ROOT / "data" / "stars.json"
CATALOG_ID = "CDS V/50, Yale Bright Star Catalog 5th Revised Ed. (Hoffleit and Warren 1991)"


def _field(line: str, start: int, end: int) -> str:
    """Byte columns are 1-based and inclusive, as listed in the CDS ReadMe."""
    return line[start - 1:end].strip()


def parse_line(line: str) -> dict | None:
    ra_h, ra_m, ra_s = _field(line, 76, 77), _field(line, 78, 79), _field(line, 80, 83)
    de_sign, de_d = _field(line, 84, 84), _field(line, 85, 86)
    de_m, de_s = _field(line, 87, 88), _field(line, 89, 90)
    vmag = _field(line, 103, 107)
    if not (ra_h and ra_m and ra_s and de_d and de_m and de_s and vmag):
        return None
    ra_hours = int(ra_h) + int(ra_m) / 60.0 + float(ra_s) / 3600.0
    dec_deg = int(de_d) + int(de_m) / 60.0 + int(de_s) / 3600.0
    if de_sign == "-":
        dec_deg = -dec_deg
    elif de_sign != "+":
        raise ValueError(f"HR {_field(line, 1, 4)}: declination sign {de_sign!r}")
    magnitude = float(vmag)
    if not (0.0 <= ra_hours < 24.0) or not (-90.0 <= dec_deg <= 90.0) or not math.isfinite(magnitude):
        raise ValueError(f"HR {_field(line, 1, 4)}: coordinate or magnitude out of range")
    row: dict[str, int | float | str] = {
        "hr": int(_field(line, 1, 4)),
        "right_ascension_hours": round(ra_hours, 6),
        "declination_deg": round(dec_deg, 5),
        "visual_magnitude": magnitude,
    }
    name = _field(line, 5, 14)
    if name:
        row["name"] = name
    bv = _field(line, 110, 114)
    if bv:
        row["b_minus_v"] = float(bv)
    return row


def convert(source: Path, out: Path) -> dict:
    raw = source.read_bytes()
    lines = gzip.decompress(raw).decode("ascii").splitlines()
    stars = [row for row in (parse_line(line) for line in lines) if row is not None]
    stars.sort(key=lambda r: r["visual_magnitude"])
    document = {
        "schema": "yellowstone.star_catalog.v1",
        "catalog": CATALOG_ID,
        "source_file": source.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "equinox": "J2000.0",
        "epoch": "J2000.0",
        "proper_motion_applied": False,
        "catalog_rows": len(lines),
        "count": len(stars),
        "stars": stars,
    }
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(out)
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    document = convert(args.source, args.out)
    print(f"wrote {args.out}: {document['count']} stars from {document['catalog_rows']} catalog rows")


if __name__ == "__main__":
    main()
