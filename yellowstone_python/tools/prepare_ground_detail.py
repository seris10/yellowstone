"""Band-limited surface relief and mapped linear-light contrast."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.common.provenance import default_world_root


def mineral_field(size: int = 1024, width_m: float = 4.0) -> tuple[np.ndarray, np.ndarray, dict]:
    """Return periodic metric height, spectral derivatives, and authored parameters."""
    if size < 64 or width_m <= 0:
        raise ValueError("surface grid requires size >= 64 and positive physical width")
    rng = np.random.default_rng(991)
    frequency = np.fft.fftfreq(size, d=width_m / size)
    kx, kz = np.meshgrid(frequency, frequency)
    radial = np.hypot(kx, kz)
    band = (radial >= 1 / 1.5) & (radial <= 1 / .02)
    spectrum = np.fft.fft2(rng.normal(size=(size, size)))
    spectrum *= np.where(band, np.maximum(radial, 1 / width_m) ** -1.7, 0)
    height = np.fft.ifft2(spectrum).real
    scale = .0045 / np.sqrt(np.mean(height ** 2))
    spectrum *= scale
    height *= scale
    derivatives = np.stack([np.fft.ifft2(spectrum * 2j * np.pi * k).real for k in (kx, kz)], axis=-1)
    parameters = {"evidence_class": "authored_display_parameter", "physical_width_m": width_m,
        "pixel_spacing_m": width_m / size, "height_rms_m": float(np.sqrt(np.mean(height ** 2))),
        "height_range_m": [float(height.min()), float(height.max())], "seed": 991,
        "hurst_exponent": .7, "psd_slope": -3.4, "wavelength_band_m": [.02, 1.5],
        "local_measurement_status": "unavailable", "uncertainty": "unknown"}
    return height, derivatives, parameters


def mapped_contrast(srgb: np.ndarray, spacing_m: float) -> np.ndarray:
    """Return bounded linear-light color ratios against a twelve-meter Gaussian mean."""
    if spacing_m <= 0 or srgb.ndim != 3 or srgb.shape[2] != 3:
        raise ValueError("mapped contrast requires RGB and positive spacing")
    linear = np.where(srgb <= .04045, srgb / 12.92, ((srgb + .055) / 1.055) ** 2.4)
    mean = gaussian_filter(linear, sigma=(12 / spacing_m, 12 / spacing_m, 0), mode="reflect")
    return np.clip(1 + 1.6 * (linear / np.maximum(mean, .025) - 1), .45, 1.7)


def prepare(world: Path) -> dict:
    """Write reproducible display maps and hash-bound provenance."""
    directory = world / "assets/textures"
    directory.mkdir(parents=True, exist_ok=True)
    height, derivatives, parameters = mineral_field()
    normal = -derivatives / np.sqrt(1 + np.sum(derivatives ** 2, axis=-1, keepdims=True))
    grain = np.clip(.5 + height / (.0045 * 6), 0, 1)
    roughness = np.clip(.86 + .14 * (grain - .5), 0, 1)
    packed = np.dstack([normal * .5 + .5, grain, roughness])
    Image.fromarray(np.uint8(np.clip(packed, 0, 1) * 255 + .5)).save(directory / "mineral_surface.png")
    source = world / "references/midway_orthophoto_detail.jpg"
    pixels = np.asarray(Image.open(source).convert("RGB"), dtype=np.float64) / 255
    ratio = mapped_contrast(pixels, 1280 / pixels.shape[1])
    encoded = ratio * .5
    encoded = np.where(encoded <= .0031308, 12.92 * encoded, 1.055 * encoded ** (1 / 2.4) - .055)
    Image.fromarray(np.uint8(np.clip(encoded, 0, 1) * 255 + .5)).save(directory / "mapped_surface_detail.png")
    report = {"schema": "yellowstone.ground_display_detail.v1", "mineral_surface": parameters,
        "mapped_detail": {"source": "references/midway_orthophoto_detail.jpg",
            "source_sha256": sha256_file(source), "pixel_spacing_m": 1280 / pixels.shape[1],
            "lowpass_sigma_m": 12, "contrast_gain": 1.6, "linear_ratio_range": [.45, 1.7],
            "ratio_encoding": "srgb_of_half_linear_ratio", "evidence_class": "derived_display_contrast",
            "subpixel_geographic_features": "none inferred"},
        "sources": ["https://www.usgs.gov/observatories/yvo/news/better-understanding-whats-under-your-feet-hydrothermal-areas-neutral",
            "https://developer.nvidia.com/gpugems/gpugems2/part-iii-high-quality-rendering/chapter-27-advanced-high-quality-filtering"],
        "artifacts": {name: sha256_file(directory / name) for name in
            ("mineral_surface.png", "mapped_surface_detail.png")}}
    write_json_atomic(directory / "ground_detail.json", report, indent=2)
    return report


def main() -> int:
    """Prepare the production surface maps."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, default=default_world_root())
    args = parser.parse_args()
    report = prepare(args.world)
    print("GROUND_DETAIL", report["artifacts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
