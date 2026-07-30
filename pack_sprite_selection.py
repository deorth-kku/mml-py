"""High-level API and CLI for building a Sprite Selection FARC archive.

Composes atlas_builder → txp_writer → farc_writer into a single pipeline.

Usage as library:
    from pack_sprite_selection import build_sprite_selection_farc
    build_sprite_selection_farc('bg.png', 'jk.png', 'logo.png', '6901')

Usage as CLI:
    python pack_sprite_selection.py pack-sprite-selection \\
        --bg BG.png --jk JK.png --logo LOGO.png --pv 6901
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

from atlas_builder import build_atlas, AtlasInfo
from txp_writer import SpriteRecord, TextureBlock, serialize_spriteset
from farc_writer import write_farc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_BG_SIZE = (1280, 720)
REQUIRED_JK_SIZE = (502, 502)

TEXTURE_NAMES = ('MERGE_D5COMP_0', 'MERGE_D5COMP_1')


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def build_sprite_selection_farc(
    bg_path: str | os.PathLike[str],
    jk_path: str | os.PathLike[str],
    logo_path: str | os.PathLike[str],
    pv: str | int,
    output_dir: str | os.PathLike[str] | None = None,
    *,
    atlas_info: AtlasInfo | None = None,
    resolution_mode: int = 14,  # HDTV1080
) -> str:
    """Build a ``spr_sel_pv<pv>.farc`` archive from three PNG inputs.

    Args:
        bg_path: Path to the 1280x720 BG PNG.
        jk_path: Path to the 502x502 JK PNG.
        logo_path: Path to the LOGO PNG (variable size).
        pv: PV number as string or int (3 or 4 digits, no leading zeros).
        output_dir: Output directory. Defaults to current directory.
        atlas_info: Pre-computed AtlasInfo (skips atlas build).
        resolution_mode: Resolution mode (0=QVGA, 14=HDTV1080, etc.).
                         Default is 0 (QVGA).

    Returns:
        Path to the generated .farc file.
    """
    # --- Validate PV ---
    pv_str = str(pv).strip()
    if not pv_str.isdigit():
        raise ValueError(f"PV must be a decimal number, got {pv_str!r}")
    if len(pv_str) not in (3, 4):
        raise ValueError(
            f"PV must be 3 or 4 digits, got {len(pv_str)} digits: {pv_str}"
        )

    # --- Load images ---
    bg_img = Image.open(bg_path).convert('RGBA')
    jk_img = Image.open(jk_path).convert('RGBA')
    logo_img = Image.open(logo_path).convert('RGBA')

    # --- Build atlas (or use provided) ---
    suffix = f"{pv_str}"
    if atlas_info is None:
        atlas_info = build_atlas(bg_img, jk_img, logo_img, sprite_name_suffix=suffix)

    # --- Build sprite records ---
    sprites: list[SpriteRecord] = []
    for name, placement in atlas_info.placement.items():
        sprites.append(SpriteRecord(
            name=name,
            texture_index=0 if name.startswith('SONG_BG') or name.startswith('SONG_JK') else 1,
            x=placement.x,
            y=placement.y,
            width=atlas_info.sprite_widths[name],
            height=atlas_info.sprite_heights[name],
        ))

    # --- Build texture blocks ---
    # Texture 0 = BG+JK atlas payload, Texture 1 = LOGO atlas payload
    textures: list[TextureBlock] = [
        TextureBlock(
            name=TEXTURE_NAMES[0],
            width=atlas_info.atlas_w,
            height=atlas_info.atlas_h,
            payload=atlas_info.payload_0,
        ),
        TextureBlock(
            name=TEXTURE_NAMES[1],
            width=atlas_info.logo_atlas_w,
            height=atlas_info.logo_atlas_h,
            payload=atlas_info.payload_1,
        ),
    ]

    # --- Serialize BIN ---
    # All sprites use the same resolution mode
    sprite_modes = [resolution_mode, resolution_mode, resolution_mode]
    bin_data = serialize_spriteset(sprites, textures, sprite_modes=sprite_modes)

    # --- Build FArC ---
    entry_name = f'spr_sel_pv{pv_str}.bin'
    farc_data = write_farc(bin_data, entry_name)

    # --- Write output ---
    if output_dir is None:
        output_dir = os.getcwd()
    output_dir = str(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    farc_filename = f'spr_sel_pv{pv_str}.farc'
    output_path = os.path.join(output_dir, farc_filename)
    with open(output_path, 'wb') as f:
        f.write(farc_data)

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Build a Sprite Selection FARC archive from PNG inputs.',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # pack-sprite-selection
    pack = sub.add_parser('pack-sprite-selection',
                          help='Pack BG/JK/LOGO PNGs into a .farc archive.')
    pack.add_argument('--bg', required=True, help='Path to BG PNG (1280x720).')
    pack.add_argument('--jk', required=True, help='Path to JK PNG (502x502).')
    pack.add_argument('--logo', required=True, help='Path to LOGO PNG.')
    pack.add_argument('--pv', required=True,
                      help='PV number (3 or 4 digits, no leading zeros).')
    pack.add_argument('-o', '--output-dir', default='.',
                      help='Output directory (default: current directory).')

    args = parser.parse_args(argv)

    if args.command == 'pack-sprite-selection':
        try:
            path = build_sprite_selection_farc(
                bg_path=args.bg,
                jk_path=args.jk,
                logo_path=args.logo,
                pv=args.pv,
                output_dir=args.output_dir,
            )
            print(f'Wrote {path}')
            return 0
        except Exception as e:
            print(f'Error: {e}', file=sys.stderr)
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
