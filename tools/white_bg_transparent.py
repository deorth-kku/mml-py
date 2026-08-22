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
"""

import os
import sys
from PIL import Image
import numpy as np


def to_transparent(src_path: str, dst_path: str,
                   sat_low: float = 3.0, sat_high: float = 25.0,
                   white_mn: float = 230.0, dark_mn: float = 100.0) -> None:
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

    alpha = np.clip(np.maximum(darkness, sat_alpha), 0, 255)

    out = arr.copy()
    out[..., 3] = alpha
    result = Image.fromarray(out.astype(np.uint8), "RGBA")
    result.save(dst_path, "PNG")
    print(f"Saved -> {dst_path}")


def auto_dst(src_path: str) -> str:
    base, ext = os.path.splitext(src_path)
    return f"{base}_tran{ext}"


if __name__ == "__main__":
    if len(sys.argv) == 2:
        src = sys.argv[1]
        to_transparent(src, auto_dst(src))
    elif len(sys.argv) == 3:
        to_transparent(sys.argv[1], sys.argv[2])
    else:
        print(f"Usage: python {sys.argv[0]} SRC [DST]")
        sys.exit(1)
