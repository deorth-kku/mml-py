"""
Extract a (near-)white background into alpha, decontaminating the color.

Difference from white_bg_transparent.py: that script keeps the RGB values
unchanged and only writes an alpha ramp. This script instead models every
pixel as a blend of a foreground color F and the background color bg:

    pixel = a * F + (1 - a) * bg

and solves both unknowns:

    a = clip( (bg_mn - mn) / (bg_mn - dark_mn) * 255, 0, 255 )  # coverage
    F = (pixel - (1 - a) * bg) / a                             # decontaminated color

so the "white" that was mixed into the pixel is moved into the alpha
channel, and the color is pushed back to its full strength.

Why: anti-aliased / chromatic-aberration fringes (e.g. the cyan/red lines
on the left edge of a logo) are blends of a saturated color and white.
Keeping their RGB unchanged leaves them looking like a washed-out solid
block over non-white backgrounds. After unwhitening they become a pure
color with a proper partial alpha, so the fringe keeps its "chromatic
aberration" feel over any background.

Properties:
- Only the OUTER silhouette is touched. A flood fill from the image border
  walks through ALL non-opaque pixels; everything it reaches (background +
  anti-aliased outer edges + fringe anti-aliasing on the background) is
  "outer". Everything else - e.g. the white text and its anti-aliased edges
  inside the black box - is interior and is left exactly as in the source
  (opaque, original color). This is what keeps enclosed text from getting
  jagged.
- Composited back over the background color, outer pixels reproduce the
  original image exactly (a*F + (1-a)*bg == pixel by construction).
- Enclosed white (white inside a character stroke, inside a black box,
  ...) is protected by the border flood fill, same as in
  white_bg_transparent.py.
- Assumes the foreground's darkest channel is near 0 (black text,
  saturated colors). Soft pastel foregrounds will be pushed toward full
  saturation - use white_bg_transparent.py for those instead.
- Special-cased (hardcoded) for the "Reversible" logo image: rows
  y >= 403 are the English text on the plain background, so no flood fill /
  enclosure protection applies there - enclosed white (e.g. inside the
  letter R) is background too and becomes transparent.
"""

import argparse
import os
from collections import deque

import numpy as np
from PIL import Image


def _flood_from_border(mask: np.ndarray) -> np.ndarray:
    """Connected component(s) of `mask` that touch the image border.

    4-connectivity, so even diagonally touching opaque pixels block the
    fill. Uses scipy when available, otherwise a plain BFS (slower).
    """
    try:
        from scipy import ndimage
        labels, _ = ndimage.label(mask)  # default structure: 4-connected
        border = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
        keep = np.zeros(int(labels.max()) + 1, dtype=bool)
        keep[border] = True
        keep[0] = False
        return keep[labels]
    except ImportError:
        pass

    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    flat_mask = mask.ravel()
    flat_vis = visited.ravel()
    dq = deque()

    def seed(p: int) -> None:
        if flat_mask[p] and not flat_vis[p]:
            flat_vis[p] = True
            dq.append(p)

    for x in range(w):
        seed(x)                 # top row
        seed((h - 1) * w + x)   # bottom row
    for y in range(h):
        seed(y * w)             # left column
        seed(y * w + (w - 1))   # right column

    while dq:
        p = dq.popleft()
        x = p % w
        if x > 0 and flat_mask[p - 1] and not flat_vis[p - 1]:
            flat_vis[p - 1] = True
            dq.append(p - 1)
        if x < w - 1 and flat_mask[p + 1] and not flat_vis[p + 1]:
            flat_vis[p + 1] = True
            dq.append(p + 1)
        if p >= w and flat_mask[p - w] and not flat_vis[p - w]:
            flat_vis[p - w] = True
            dq.append(p - w)
        if p < (h - 1) * w and flat_mask[p + w] and not flat_vis[p + w]:
            flat_vis[p + w] = True
            dq.append(p + w)
    return visited


def _estimate_bg(rgb: np.ndarray) -> np.ndarray:
    """Estimate the background color from the image border.

    Uses the median of the bright border pixels, so dark border artifacts
    (e.g. a black frame along the edge) do not pull the estimate down.
    Falls back to pure white when the border has no bright pixels.
    """
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bright = border[border.min(axis=1) >= 200]
    if len(bright) >= 32:
        return np.median(bright, axis=0).astype(np.float32)
    return np.array([255.0, 255.0, 255.0], dtype=np.float32)


def unwhite(src_path: str, dst_path: str,
            bg=None, dark_mn: float = 60.0, alpha_floor: float = 8.0,
            keep_enclosed: bool = True) -> None:
    img = Image.open(src_path).convert("RGBA")
    arr = np.asarray(img).astype(np.float32)
    rgb = arr[..., :3]
    mn = np.minimum(np.minimum(rgb[..., 0], rgb[..., 1]), rgb[..., 2])

    if bg is None:
        bg = _estimate_bg(rgb)
    bg = np.asarray(bg, dtype=np.float32).reshape(3)
    bg_mn = float(bg.min())
    if bg_mn - dark_mn <= 0:
        raise ValueError("bg.min() must be greater than dark_mn")

    # coverage: 0 where mn >= bg_mn (pure background),
    # 255 where mn <= dark_mn (solid dark/saturated foreground),
    # linear ramp in between.
    alpha = np.clip((bg_mn - mn) / (bg_mn - dark_mn) * 255.0, 0.0, 255.0)
    # Kill near-background noise before it gets amplified by unwhitening.
    alpha[alpha < alpha_floor] = 0.0

    # "Outer" = everything reachable from the image border through
    # non-opaque pixels: the background, the anti-aliased silhouette
    # boundary, and fringe anti-aliasing on the background. Everything
    # else (interior of the black box: white text + its anti-aliasing)
    # is left exactly as in the source.
    walkable = alpha < 255
    outer = (_flood_from_border(walkable) if walkable.any()
             else np.zeros_like(walkable))

    # Hardcoded for this image: the black box ends at y=396 and the English
    # "Reversible" text runs y=408..429. Below y=403 there is no flood fill /
    # enclosure protection: it is black text on the plain background, so
    # enclosed white (e.g. inside the letter R) is background and must
    # become transparent, and every semi-transparent pixel is unwhitened
    # like an outer one.
    h, w = arr.shape[:2]
    english = np.zeros((h, w), dtype=bool)
    english[403:, :] = True
    outer_eff = outer | english

    out = arr.copy()

    # Decontaminate ONLY outer semi-transparent pixels: subtract the white
    # contribution so the color comes out at full strength.
    unwhite_zone = (alpha > 0) & (alpha < 255) & outer_eff
    if unwhite_zone.any():
        a = alpha[unwhite_zone] / 255.0
        px = rgb[unwhite_zone]
        f = (px - (1.0 - a[:, None]) * bg[None, :]) / a[:, None]
        out[unwhite_zone, :3] = np.clip(f, 0.0, 255.0)

    new_alpha = alpha.copy()
    # Enclosed white is foreground: force it fully opaque.
    enclosed = (alpha == 0) & ~outer_eff
    if keep_enclosed:
        new_alpha[enclosed] = 255.0
    # Interior semi-transparent pixels are kept opaque with original color.
    new_alpha[(alpha > 0) & (alpha < 255) & ~outer_eff] = 255.0
    out[..., 3] = new_alpha

    result = Image.fromarray(out.astype(np.uint8), "RGBA")
    result.save(dst_path, "PNG")
    print(f"bg = ({bg[0]:.0f}, {bg[1]:.0f}, {bg[2]:.0f})")
    print(f"Saved -> {dst_path}")


def auto_dst(src_path: str) -> str:
    base, ext = os.path.splitext(src_path)
    return f"{base}_unwhite{ext}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Extract the white background into alpha and decontaminate "
                    "the color (keeps chromatic-aberration fringes as pure "
                    "color + partial alpha).")
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--bg", default=None, metavar="R,G,B",
                    help="background color to extract, e.g. 255,255,255 "
                         "(default: auto-estimated from the image border)")
    ap.add_argument("--dark-mn", type=float, default=60.0,
                    help="min-channel at or below this is fully opaque "
                         "(default 60)")
    ap.add_argument("--alpha-floor", type=float, default=8.0,
                    help="alpha below this is zeroed, kills near-white noise "
                         "(default 8)")
    ap.add_argument("--no-enclose", action="store_true",
                    help="also make enclosed white regions transparent")
    args = ap.parse_args()

    bg = None
    if args.bg:
        bg = np.array([float(x) for x in args.bg.split(",")], dtype=np.float32)

    unwhite(args.src, args.dst or auto_dst(args.src),
            bg=bg, dark_mn=args.dark_mn, alpha_floor=args.alpha_floor,
            keep_enclosed=not args.no_enclose)
