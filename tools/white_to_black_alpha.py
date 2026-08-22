"""
Convert a white-text-on-black-background image to black-text-on-transparent-background.

The gray anti-aliased edges of the text become ALPHA transitions (partial
transparency) instead of gray, so the text stays black and only its opacity
varies from 0 (background) to 255 (solid text).
"""

import os
import sys
from PIL import Image


def to_black_alpha(src_path: str, dst_path: str) -> None:
    img = Image.open(src_path).convert("RGBA")

    # Luminance of the source: white text -> bright, black bg -> dark.
    gray = img.convert("L")

    # RGB becomes solid black; the source luminance drives the alpha channel,
    # so gray edges turn into smooth alpha transitions.
    black = Image.new("RGB", img.size, (0, 0, 0))
    rgba = Image.merge(
        "RGBA",
        (black.getchannel("R"), black.getchannel("G"), black.getchannel("B"), gray),
    )

    rgba.save(dst_path, "PNG")
    print(f"Saved -> {dst_path}")


def auto_dst(src_path: str) -> str:
    base, ext = os.path.splitext(src_path)
    return f"{base}_black_alpha{ext}"


if __name__ == "__main__":
    if len(sys.argv) == 2:
        src = sys.argv[1]
        to_black_alpha(src, auto_dst(src))
    elif len(sys.argv) == 3:
        to_black_alpha(sys.argv[1], sys.argv[2])
    else:
        print(f"Usage: python {sys.argv[0]} SRC [DST]")
        sys.exit(1)
