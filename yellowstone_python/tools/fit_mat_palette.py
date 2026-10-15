"""Command line: fit a mat color palette from reference imagery by k-means in Lab space."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
from yellowstone_python.thermal_features.mat_appearance import srgb_to_lab  # noqa: E402

# Warm mat pixels: chroma floor and hue window in degrees; authored.
CHROMA_MIN = 15.0
HUE_MIN_DEG = 10.0
HUE_MAX_DEG = 95.0


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    """sRGB in [0, 1] from Lab (D65 white)."""
    lab = np.asarray(lab, dtype=np.float64)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0

    def inv(f):
        f3 = f ** 3
        return np.where(f3 > eps, f3, (116.0 * f - 16.0) / kappa)

    xyz = np.stack([inv(fx), inv(fy), inv(fz)], axis=-1) * np.array(
        [0.95047, 1.0, 1.08883])
    m = np.array([[3.2404542, -1.5371385, -0.4985314],
                  [-0.9692660, 1.8760108, 0.0415560],
                  [0.0556434, -0.2040259, 1.0572252]])
    lin = np.clip(xyz @ m.T, 0.0, 1.0)
    return np.where(lin <= 0.0031308, 12.92 * lin,
                    1.055 * lin ** (1.0 / 2.4) - 0.055)


def kmeans(x: np.ndarray, k: int, seed: int, iters: int = 50) -> tuple:
    """Lloyd k-means with k-means++ seeding; returns (centers, labels)."""
    rng = np.random.default_rng(seed)
    centers = [x[rng.integers(len(x))]]
    for _ in range(1, k):
        d2 = np.min([((x - c) ** 2).sum(1) for c in centers], axis=0)
        centers.append(x[rng.choice(len(x), p=d2 / d2.sum())])
    centers = np.array(centers)
    labels = np.zeros(len(x), dtype=int)
    for _ in range(iters):
        d2 = ((x[:, None, :] - centers[None]) ** 2).sum(-1)
        labels = d2.argmin(1)
        new = np.array([x[labels == i].mean(0) if (labels == i).any()
                        else centers[i] for i in range(k)])
        if np.allclose(new, centers):
            break
        centers = new
    return centers, labels


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--max-pixels", type=int, default=200000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    from PIL import Image
    pix = []
    for path in args.images:
        rgb = np.asarray(Image.open(path).convert("RGB"),
                         dtype=np.float64).reshape(-1, 3) / 255.0
        pix.append(rgb)
    rgb = np.concatenate(pix)
    lab = srgb_to_lab(rgb)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0
    warm = lab[(chroma >= CHROMA_MIN) & (hue >= HUE_MIN_DEG)
               & (hue <= HUE_MAX_DEG)]
    rng = np.random.default_rng(args.seed)
    if len(warm) > args.max_pixels:
        warm = warm[rng.choice(len(warm), args.max_pixels, replace=False)]
    centers, labels = kmeans(warm, args.k, args.seed)
    shares = np.bincount(labels, minlength=args.k) / len(labels)
    order = np.argsort(-shares)
    out = []
    for i in order:
        srgb = lab_to_srgb(centers[i])
        out.append({"rgb_0_255": [int(round(v * 255.0)) for v in srgb],
                    "lab": [round(float(v), 2) for v in centers[i]],
                    "chroma": round(float(np.hypot(*centers[i][1:])), 2),
                    "share": round(float(shares[i]), 4)})
    print(json.dumps({"warm_pixels": int(len(warm)),
                      "images": [Path(p).name for p in args.images],
                      "clusters": out}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
