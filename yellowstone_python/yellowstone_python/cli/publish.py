"""Command-line interface for publish."""
from __future__ import annotations

import argparse
from pathlib import Path
from yellowstone_python.common.provenance import default_world_root

def main() -> int:
    import logging
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--to", default=str(default_world_root()))
    ap.add_argument("--force", action="store_true", help="Activate an explicitly unverified development generation")
    ap.add_argument("--unverified-development", action="store_true")
    args = ap.parse_args()
    from yellowstone_python.publish import publish_generation
    try:
        release = publish_generation(Path(args.build), Path(args.to),
            unverified=args.force or args.unverified_development)
    except (OSError, ValueError, KeyError) as exc:
        print(f"refusing: {exc}")
        return 3
    print(f"activated release {release['release_id']} from build {release['build_id']}")
    print(f"verification: {release['verification']['status']}")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
