"""Atlas texture construction and Texconv BC3/DXT5 encoding.

Builds two texture atlases from BG/JK/LOGO PNG inputs, encodes them
as DXT5 (BC3_UNORM) via texconv.exe subprocess, and extracts the raw
payload for embedding in TXP SubTexture blocks.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Atlas layout (pixel coordinates in the atlas)
ATLAS_BG_POS = (2, 2)
ATLAS_JK_POS = (1286, 2)
ATLAS_LOGO_POS = (2, 2)

ATLAS_BG_SIZE = (2048, 1024)
ATLAS_LOGO_DEFAULT_SIZE = (1024, 512)

# Maximum LOGO size before we refuse (generous upper bound)
LOGO_MAX_W = 2046  # 2048 - 2px margin
LOGO_MAX_H = 1022  # 1024 - 2px margin


class AtlasPlacement(NamedTuple):
    """Where a sprite sits inside its atlas texture."""
    x: int
    y: int
    w: int
    h: int


class AtlasInfo(NamedTuple):
    """Result of atlas construction and encoding."""
    atlas_w: int                       # texture 0 width
    atlas_h: int                       # texture 0 height
    logo_atlas_w: int                  # texture 1 (LOGO) width
    logo_atlas_h: int                  # texture 1 (LOGO) height
    payload_0: bytes                   # raw DXT5 payload for texture 0 (BG+JK)
    payload_1: bytes                   # raw DXT5 payload for texture 1 (LOGO)
    placement: dict                    # name -> AtlasPlacement
    sprite_widths: dict                # name -> int
    sprite_heights: dict               # name -> int


# ---------------------------------------------------------------------------
# Texconv subprocess helper
# ---------------------------------------------------------------------------

def _find_texconv() -> str:
    """Locate texconv.exe on PATH or next to this module."""
    for candidate in [
        shutil.which("texconv.exe"),
        str(Path(__file__).parent / "texconv" / "texconv.exe"),
    ]:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        "Cannot find texconv.exe — ensure it's on PATH or in texconv/."
    )


def _encode_png_to_dds(
    png_path: str,
    output_dir: str,
    fmt: str = "BC3_UNORM",
    mip: int = 1,
    vflip: bool = True,
) -> str:
    """Encode a PNG to DDS via texconv.exe subprocess. Returns DDS path."""
    exe = _find_texconv()
    args = [exe, "-f", fmt, "-m", str(mip), "-dx9", "-o", output_dir, "-y"]
    if vflip:
        args.append("-vflip")
    args.extend(["--", png_path])

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"texconv.exe failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    base = os.path.splitext(os.path.basename(png_path))[0]
    return os.path.join(output_dir, base + ".dds")


# ---------------------------------------------------------------------------
# DDS parsing
# ---------------------------------------------------------------------------

def parse_dds(
    dds_path: str,
    expected_w: int | None = None,
    expected_h: int | None = None,
    expected_fourcc: bytes = b"DXT5",
) -> tuple[int, int, bytes]:
    """Parse a DDS file. Returns (width, height, raw_payload_bytes)."""
    with open(dds_path, "rb") as f:
        data = f.read()

    if len(data) < 128:
        raise ValueError(f"DDS file too small: {len(data)} bytes")

    if data[:4] != b"DDS ":
        raise ValueError(f"DDS magic mismatch: {data[:4]!r}")

    height, width, _ = struct.unpack_from("<III", data, 12)
    four_cc_int = struct.unpack_from("<I", data, 84)[0]
    # DXT5 = BC3_UNORM, FourCC as integer: 0x35545844 ("DXT5" as LE uint32)
    DXT5_FOURCC = 0x35545844

    if expected_w is not None and width != expected_w:
        raise ValueError(f"DDS width {width} != expected {expected_w}")
    if expected_h is not None and height != expected_h:
        raise ValueError(f"DDS height {height} != expected {expected_h}")
    if four_cc_int != DXT5_FOURCC:
        raise ValueError(f"DDS FourCC 0x{four_cc_int:08X} != expected DXT5 (0x{DXT5_FOURCC:08X})")

    payload = data[128:]
    expected_size = math.ceil(width / 4) * math.ceil(height / 4) * 16
    if len(payload) != expected_size:
        raise ValueError(
            f"DDS payload size {len(payload)} != expected {expected_size}"
        )
    return width, height, payload


# ---------------------------------------------------------------------------
# Atlas construction
# ---------------------------------------------------------------------------

def _next_pow2(v: int) -> int:
    """Return the smallest power of 2 >= v."""
    if v <= 0:
        return 1
    return 1 << (v - 1).bit_length()


def build_atlas(
    bg_img: Image.Image,
    jk_img: Image.Image,
    logo_img: Image.Image,
    dds_out_dir: str | None = None,
    vflip: bool = True,
    sprite_name_suffix: str = "",
) -> AtlasInfo:
    """Build two atlas textures and encode them to DXT5.

    Args:
        bg_img: 1280x720 BG PNG (RGBA).
        jk_img: 502x502 JK PNG (RGBA).
        logo_img: LOGO PNG (RGBA), variable size.
        dds_out_dir: Directory for intermediate DDS files.
        vflip: Whether to apply vertical flip during encoding.

    Returns:
        AtlasInfo with payloads and placement data for all three sprites.
    """
    # --- Validate inputs ---
    if bg_img.size != (1280, 720):
        raise ValueError(f"BG must be 1280x720, got {bg_img.size}")
    if jk_img.size != (502, 502):
        raise ValueError(f"JK must be 502x502, got {jk_img.size}")

    logo_w, logo_h = logo_img.size
    if logo_w > LOGO_MAX_W or logo_h > LOGO_MAX_H:
        raise ValueError(
            f"LOGO {logo_w}x{logo_h} exceeds maximum {LOGO_MAX_W}x{LOGO_MAX_H}"
        )

    # --- Determine LOGO atlas size ---
    if logo_w <= 1020 and logo_h <= 510:
        logo_atlas_w, logo_atlas_h = ATLAS_LOGO_DEFAULT_SIZE
    else:
        need_w = _next_pow2(logo_w + 2)
        need_h = _next_pow2(logo_h + 2)
        logo_atlas_w, logo_atlas_h = need_w, need_h
        if logo_atlas_w > 2048 or logo_atlas_h > 1024:
            raise ValueError(f"LOGO atlas {logo_atlas_w}x{logo_atlas_h} too large")

    # --- Build atlas textures ---
    bg_atlas = Image.new("RGBA", ATLAS_BG_SIZE, (0, 0, 0, 0))
    bg_atlas.paste(bg_img, ATLAS_BG_POS)
    bg_atlas.paste(jk_img, ATLAS_JK_POS)

    logo_atlas = Image.new("RGBA", (logo_atlas_w, logo_atlas_h), (0, 0, 0, 0))
    logo_atlas.paste(logo_img, ATLAS_LOGO_POS)

    # --- Encode via Texconv ---
    if dds_out_dir is None:
        dds_out_dir = tempfile.mkdtemp(prefix="atlas_")

    # Encode BG atlas (contains BG + JK)
    bg_png = os.path.join(dds_out_dir, "atlas_bg.png")
    bg_atlas.save(bg_png)
    bg_dds = _encode_png_to_dds(bg_png, dds_out_dir, vflip=vflip)

    # Encode LOGO atlas
    logo_png = os.path.join(dds_out_dir, "atlas_logo.png")
    logo_atlas.save(logo_png)
    logo_dds = _encode_png_to_dds(logo_png, dds_out_dir, vflip=vflip)

    # --- Parse DDS payloads ---
    bg_w, bg_h, bg_payload = parse_dds(bg_dds)
    logo_w_actual, logo_h_actual, logo_payload = parse_dds(logo_dds)

    # --- Build placement data ---
    placements = {
        "SONG_BG" + sprite_name_suffix: AtlasPlacement(
            x=ATLAS_BG_POS[0], y=ATLAS_BG_POS[1],
            w=bg_img.width, h=bg_img.height,
        ),
        "SONG_JK" + sprite_name_suffix: AtlasPlacement(
            x=ATLAS_JK_POS[0], y=ATLAS_JK_POS[1],
            w=jk_img.width, h=jk_img.height,
        ),
        "SONG_LOGO" + sprite_name_suffix: AtlasPlacement(
            x=ATLAS_LOGO_POS[0], y=ATLAS_LOGO_POS[1],
            w=logo_w, h=logo_h,
        ),
    }

    sprite_widths = {
        "SONG_BG" + sprite_name_suffix: bg_img.width,
        "SONG_JK" + sprite_name_suffix: jk_img.width,
        "SONG_LOGO" + sprite_name_suffix: logo_w,
    }
    sprite_heights = {
        "SONG_BG" + sprite_name_suffix: bg_img.height,
        "SONG_JK" + sprite_name_suffix: jk_img.height,
        "SONG_LOGO" + sprite_name_suffix: logo_h,
    }

    return AtlasInfo(
        atlas_w=bg_w,
        atlas_h=bg_h,
        logo_atlas_w=logo_w_actual,
        logo_atlas_h=logo_h_actual,
        payload_0=bg_payload,
        payload_1=logo_payload,
        placement=placements,
        sprite_widths=sprite_widths,
        sprite_heights=sprite_heights,
    )
