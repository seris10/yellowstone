"""Illustrative broadleaf card texture."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    """Write a generic broadleaf texture and provenance."""
    target = Path(__file__).resolve().parents[1] / "assets/imported/forest_floor"
    target.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for stem, lean in [(105, -34), (235, 20), (365, -14)]:
        draw.line([(stem, 511), (stem + lean, 140)], fill=(69, 58, 34, 255), width=6)
        for level in range(6):
            y = 430 - level * 49
            center = stem + lean * (500 - y) / 360
            for side in [-1, 1]:
                x = center + side * 33
                draw.line([(center, y + 12), (x, y)], fill=(69, 58, 34, 255), width=3)
                draw.ellipse((x - 27, y - 17, x + 27, y + 17), fill=(57 + level * 2, 77 + level * 2, 32, 255))
                draw.line([(x - 17, y), (x + 17, y)], fill=(81, 94, 42, 255), width=2)
    path = target / "broadleaf.png"
    image.save(path)
    metadata = {"schema": "yellowstone.forest_floor_assets.v1", "license": "Apache-2.0", "geometry_class": "authored", "appearance_class": "illustrative_non_diagnostic", "local_species_presence_claim": "none", "uncertainty": "unknown", "scientific_acceptance": "not_yet_accepted", "files": [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}]}
    (target / "forest_floor_assets.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
