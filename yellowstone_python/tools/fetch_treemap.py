"""TreeMap site distributions."""
from __future__ import annotations

import argparse
from pathlib import Path

from yellowstone_python.common.io import load_json
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.observations.treemap import fetch_treemap


def main(argv=None):
    """Fetch the detail-window imputed species and tree-size references."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem-provenance", type=Path,
        default=default_world_root() / "references/dem_1m_core.tif.provenance.json")
    parser.add_argument("--out", type=Path, default=Path("derived/treemap_midway.json"))
    parser.add_argument("--cache", type=Path, default=Path("data/treemap/raw"))
    args = parser.parse_args(argv)
    metadata = load_json(args.dem_provenance)
    if metadata.get("coordinate_system") != "EPSG:32612":
        raise ValueError("TreeMap detail bounds must use EPSG:32612")
    bounds = metadata.get("bbox_utm_m", metadata.get("bbox_utm"))
    if bounds is None:
        raise ValueError("DEM provenance must provide UTM bounds")
    payload = fetch_treemap(bounds, args.out, cache=args.cache)
    print(f"Wrote {len(payload['profiles'])} imputed donor profiles to {args.out}")


if __name__ == "__main__":
    main()
