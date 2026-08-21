"""
pvtmb_tile_preview.py — reference preview tool for the PVTMB thumbnail parallelogram.

Given an arbitrary input image, fit the PVTMB tile art region (a horizontally-sheared
parallelogram) into it as LARGE AS POSSIBLE while preserving the image's aspect ratio
(NNO distortion / no warp), crop that parallelogram out, then scale (uniform, aspect
preserving) down to a 128x64 RGBA tile. The four corners stay transparent.

This mirrors exactly what the builder does when compositing: it produces a 128x64
"thumb" that is later pasted with `base.paste(thumb, pos, mask=FRAME_MASK)`.

Parallelogram corners (measured upright from testfiles/pvtmb_extract/8227.png,
edge-fit + confirmed against the article's manual measurement):
    TL=(28,1)  TR=(108,1)  BL=(45,63)  BR=(125,63)
Top & bottom edges are horizontal; left & right edges slant, shearing right
at slope ≈0.28 (both edges share the same slope). Bottom edge sits at y=63,
leaving 1px of transparent padding below.

Usage:
    python pvtmb_tile_preview.py input.png [output.png]
"""
import sys
from PIL import Image, ImageDraw, ImageChops

# Parallelogram corners in the 128x64 tile coordinate frame (upright).
# Both slanted edges shear right at slope ≈0.28; bottom edge at y=63 (1px padding).
TL, TR, BL, BR = (30, 1), (110, 1), (48, 63), (128, 63)
TW, TH = 128, 64


def build_parallelogram_mask(aa: bool = True, ssample: int = 8) -> Image.Image:
    """128x64 L-mode mask: alpha inside the parallelogram art region, 0 in the corners.

    With ``aa=True`` (default) the polygon is rendered at ``ssample``x supersample
    resolution and area-downscaled, which yields a smooth alpha gradient along the
    slanted left/right edges (anti-aliasing) instead of a hard 0/255 step. The four
    corners stay fully transparent either way.
    """
    pts = (TL, TR, BR, BL)
    if not aa:
        mask = Image.new("L", (TW, TH), 0)
        ImageDraw.Draw(mask).polygon(list(pts), outline=255, fill=255)
        return mask
    W, H = TW * ssample, TH * ssample
    big = Image.new("L", (W, H), 0)
    scaled = [(int(x * ssample), int(y * ssample)) for (x, y) in pts]
    ImageDraw.Draw(big).polygon(scaled, fill=255)
    # area-averaging downscale = correct coverage anti-aliasing on the slanted edges
    return big.resize((TW, TH), Image.BOX)


def cover_to(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Center-crop `img` to the target aspect ratio, then scale to exactly `size`.

    Order is crop-then-scale (not scale-then-crop): first cut the source down to
    the W:H ratio so no source detail is thrown away by an oversized cover-scale,
    then uniform-scale (LANCZOS) to the exact bounding box. Never distorts.
    """
    W, H = size
    iw, ih = img.size
    if iw * H > ih * W:
        # source wider than target -> keep full height, crop left/right
        new_w = max(1, round(ih * W / H))
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:
        # source taller than target -> keep full width, crop top/bottom
        new_h = max(1, round(iw * H / W))
        top = (ih - new_h) // 2
        img = img.crop((0, top, iw, top + new_h))
    return img.resize((W, H), Image.LANCZOS)


def make_tile(src_path: str, dst_path: str):
    img = Image.open(src_path).convert("RGBA")

    # Bounding box of the parallelogram art region, in tile coords.
    minx = min(TL[0], TR[0], BL[0], BR[0])  # 28
    miny = min(TL[1], TR[1], BL[1], BR[1])  # 1
    maxx = max(TL[0], TR[0], BL[0], BR[0])  # 125
    maxy = max(TL[1], TR[1], BL[1], BR[1])  # 63
    bw, bh = maxx - minx, maxy - miny       # 97 x 62

    # Cover-scale the input to the bounding box (max size, aspect preserved),
    # then place it at the bbox origin so the parallelogram is inscribed in it.
    patch = cover_to(img, (bw, bh))

    tile = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    tile.alpha_composite(patch, (minx, miny))

    # Keep only the parallelogram art region (transparent corners).
    mask = build_parallelogram_mask()
    tile.putalpha(ImageChops.multiply(tile.split()[3], mask))

    tile.save(dst_path)
    print(f"wrote {dst_path}  {tile.size}  (art bbox {bw}x{bh} at offset ({minx},{miny}))")
    return tile


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "input.png"
    dst = sys.argv[2] if len(sys.argv) > 2 else "tile_preview.png"
    make_tile(src, dst)
