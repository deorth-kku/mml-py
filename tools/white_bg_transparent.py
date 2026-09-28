"""
Remove a pure-white background from an image that contains both a light,
saturated foreground (pink watercolor) and a dark foreground (black text),
keeping soft edges ONLY where real gray transitions exist.

Key idea: a pixel is "foreground" if it is either DARK (black text) or
SATURATED (pink). Background is bright AND neutral (white). Combine two
signals with a max:

    alpha = max( darkness, saturation )

    darkness   = 255 - min(r, g, b)      # 0 on white, high on black text,
                                         # mid on neutral anti-alias gray
    saturation = ramp of (max - min)     # 0 on neutral tones, high on pink

So solid pink and solid text -> alpha 255, white -> 0, and neutral gray
edges (pink watercolor fade, text anti-aliasing) -> smooth intermediate alpha.
RGB values are kept unchanged, so colors are preserved.

Enclosed white:
White that is fully surrounded by foreground (the white inside a character
stroke, inside a black circle, ...) is NOT background. Only white connected
to the image border may become transparent. After computing the alpha ramp
above, we flood-fill from the border over the "would-be-transparent" pixels;
any white the fill never reaches is enclosed foreground and is forced back
to alpha 255.
"""

import argparse
import os
from collections import deque

import numpy as np
from PIL import Image


def _flood_from_border(mask: np.ndarray) -> np.ndarray:
    """Connected component(s) of `mask` that touch the image border.

    4-connectivity, so even diagonally touching black pixels block the fill.
    Uses scipy when available, otherwise a plain BFS (slower, no dependency).
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


def to_transparent(src_path: str, dst_path: str,
                   sat_low: float = 3.0, sat_high: float = 25.0,
                   white_mn: float = 180.0, dark_mn: float = 100.0,
                   keep_enclosed: bool = True,
                   bg_alpha_thresh: float = 128.0) -> None:
    img = Image.open(src_path).convert("RGBA")
    arr = np.asarray(img).astype(np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    sat = mx - mn

    # darkness ramp: fully opaque for the dark text body (mn <= dark_mn),
    # transparent for white bg (mn >= white_mn), soft linear ramp in between.
    # Saturating at dark_mn keeps the whole text solid, not just its darkest
    # pixels (a plain 255 - mn would leave mid-dark text semi-transparent).
    darkness = np.clip((white_mn - mn) / (white_mn - dark_mn) * 255.0, 0, 255)
    # saturation ramp: lifts saturated pink to opaque, keeps neutral tones soft
    sat_alpha = np.clip((sat - sat_low) / (sat_high - sat_low) * 255.0, 0, 255)

    alpha = np.maximum(darkness, sat_alpha)

    if keep_enclosed:
        # Pixels the ramp above would make (mostly) transparent.
        bg_candidate = alpha < bg_alpha_thresh
        if bg_candidate.any():
            outer_bg = _flood_from_border(bg_candidate)
            enclosed = bg_candidate & ~outer_bg
            # Enclosed white is foreground: force it fully opaque.
            alpha = np.where(enclosed, 255.0, alpha)

    out = arr.copy()
    out[..., 3] = alpha
    result = Image.fromarray(out.astype(np.uint8), "RGBA")
    result.save(dst_path, "PNG")
    print(f"Saved -> {dst_path}")


def auto_dst(src_path: str) -> str:
    base, ext = os.path.splitext(src_path)
    return f"{base}_tran{ext}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Make the white background transparent, keeping enclosed white opaque.")
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--no-enclose", action="store_true",
                    help="also make enclosed white regions transparent (old behavior)")
    ap.add_argument("--bg-thresh", type=float, default=128.0,
                    help="alpha below this counts as 'white' for the enclosed test")
    args = ap.parse_args()
    to_transparent(args.src, args.dst or auto_dst(args.src),
                   keep_enclosed=not args.no_enclose,
                   bg_alpha_thresh=args.bg_thresh)
