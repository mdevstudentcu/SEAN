"""Dithered topographic backgrounds for the deck (run once; writes ../public/topo-*.png).

A smooth random height field is cut into contour bands; alternate bands are filled and the fill is
ordered-dithered (8x8 Bayer) at a coarse pixel, so the shapes read as a dithered contour map. A
mask keeps them to chosen corners. Rendered at 960x540 and shown at 1920x1080 with
`image-rendering: pixelated`, so each dither dot is 2x2 screen pixels.

    python tools/topo.py
"""

from pathlib import Path

import numpy as np
from PIL import Image

W, H = 960, 540
OUT = Path(__file__).resolve().parent.parent / "public"
BAYER = (
    np.array(
        [
            [0, 32, 8, 40, 2, 34, 10, 42],
            [48, 16, 56, 24, 50, 18, 58, 26],
            [12, 44, 4, 36, 14, 46, 6, 38],
            [60, 28, 52, 20, 62, 30, 54, 22],
            [3, 35, 11, 43, 1, 33, 9, 41],
            [51, 19, 59, 27, 49, 17, 57, 25],
            [15, 47, 7, 39, 13, 45, 5, 37],
            [63, 31, 55, 23, 61, 29, 53, 21],
        ]
    )
    / 64.0
)
FG = (138, 150, 163)  # grey-blue contour colour; alpha carries the dither


def field(seed: int, scale: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((H, W))
    fy = np.fft.fftfreq(H)[:, None]
    fx = np.fft.fftfreq(W)[None, :]
    k = np.exp(-(fx**2 + fy**2) * (scale**2))
    f = np.real(np.fft.ifft2(np.fft.fft2(z) * k))
    return (f - f.min()) / (f.max() - f.min())


def corner_mask(corners: list[tuple[float, float, float]]) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W]
    m = np.zeros((H, W))
    for cx, cy, r in corners:  # centre as a fraction of the frame, radius in px
        d = np.hypot(xx - cx * W, yy - cy * H)
        m = np.maximum(m, np.clip(1.2 - d / r, 0, 1))
    return m


def render(name, seed, corners, bands=7, density=0.6, scale=230.0):
    f = field(seed, scale)
    m = corner_mask(corners)
    level = f * bands
    band = np.floor(level).astype(int)
    frac = level - band
    filled = band % 2 == 0
    # Tone per band: lighter towards the peaks; a thin dark gap at every contour edge.
    tone = (0.35 + 0.65 * (band / bands)) * density
    edge = (frac < 0.06) | (frac > 0.94)
    tone = np.where(filled & ~edge, tone, 0.0) * m
    th = np.tile(BAYER, (H // 8 + 1, W // 8 + 1))[:H, :W]
    on = tone > th
    # Contour lines on the unfilled side: a single-pixel dotted line, the template's dashed rule.
    dots = ((np.arange(W)[None, :] + np.arange(H)[:, None]) // 3) % 2 == 0
    line = (np.abs(frac - 0.5) < 0.035) & ~filled & (m > 0.15) & dots
    a = np.zeros((H, W), np.uint8)
    a[on] = 255
    a[line] = 150
    img = np.zeros((H, W, 4), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = FG
    img[..., 3] = a
    OUT.mkdir(exist_ok=True)
    Image.fromarray(img, "RGBA").save(OUT / f"topo-{name}.png", optimize=True)


render("title", 7, [(-0.02, -0.04, 330), (1.02, 1.04, 360), (1.03, -0.05, 170)])
render("content", 11, [(1.03, -0.06, 220), (1.04, 1.07, 150)], density=0.5)
render("section", 3, [(1.04, 0.5, 400), (-0.03, -0.05, 160)], density=0.55)
render("cover", 23, [(1.1, 0.55, 470), (0.62, 1.12, 150)], density=0.6)
render("light", 19, [(1.04, 1.06, 200)], density=0.4)
print("wrote", sorted(p.name for p in OUT.glob("topo-*.png")))
