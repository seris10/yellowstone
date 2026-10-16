"""Human-made natural canopy shoot identity, root attachment and mip transport."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets/imported/canopy_shoot"


def test_natural_shoot_preserves_cc0_source_and_rooted_component():
    metadata = json.loads((ASSETS / "pine_shoot.json").read_text())
    assert metadata["source_class"] == "human_made_cc0"
    assert metadata["license"] == "CC0-1.0"
    assert metadata["dimension_class"] == "authored_unknown_uncertainty"
    assert metadata["display_dimensions_m"] == [.48, .64]
    assert metadata["component_dimensions_m"] == [.18, .36]
    assert metadata["assembly"]["photos"] == 5
    for source in metadata["sources"]:
        assert hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    image = np.asarray(Image.open(ASSETS / "pine_shoot.png"))
    assert image.shape == (512, 256, 4)
    assert image[-1, 128, 3] >= 82
    assert not image[:94, :, 3].any()
    assert np.count_nonzero(image[:, :, 3]) == 22215
    source_alpha = np.asarray(Image.open(ROOT / metadata["sources"][1]["path"]).convert("L"))
    source_color = np.asarray(Image.open(ROOT / metadata["sources"][0]["path"]).convert("RGB"))
    visible = image[94:, :, 3] > 0
    np.testing.assert_array_equal(image[94:, :, 3][visible], source_alpha[35:453, 12:268][visible])
    np.testing.assert_array_equal(image[94:, :, :3][visible], source_color[35:453, 12:268][visible])


def test_canopy_cutout_mips_have_verified_complete_chain_and_filtering_contract():
    entry = json.loads((ASSETS / "pine_shoot.json").read_text())["mips"]
    data = (ASSETS / entry["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    assert hashlib.sha256((ASSETS / "pine_bough.png").read_bytes()).hexdigest() == entry["source_sha256"]
    assert entry["filter_address_mode"] == "clamp_to_edge"
    assert entry["color_filter_space"] == "linear_sRGB"
    assert len(data) == entry["bytes"] == sum(item["bytes"] for item in entry["levels"])
    assert entry["levels"][-1]["width"] == entry["levels"][-1]["height"] == 1
    image = np.asarray(Image.open(ASSETS / "pine_bough.png"))
    assert image[-1, 192, 3] == 255
    assert np.count_nonzero(image[:, :, 3] >= 82) > 22000
