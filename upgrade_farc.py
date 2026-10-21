"""Upgrade a Sprite Selection FARC archive.

Extracts sprites from an input FARC, pads JK to 502x502 if needed,
and repacks into a new FARC with DXT5 (BC3) encoding.

Usage:
    python upgrade_farc.py input.farc [output.farc] [--pv NEW_PV]

If output.farc is not specified, it defaults to input.farc (overwritten).
If --pv is specified, the PV number in the output filename is changed.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

from atlas_builder import BG_JK_FORMAT_IDS
from pack_sprite_selection import build_sprite_selection_farc
from txp_parser import export_sprites_to_png


def upgrade_farc(
    input_path: str,
    output_dir: str | None = None,
    pv: str | None = None,
    jk_padding: int = 2,  # pixels to add on each side (total: 2*padding)
    resolution_mode: int = 14,
    logo_path: str | None = None,
    bg_path: str | None = None,
    jk_path: str | None = None,
    bg_jk_format: str = "dxt5",
) -> str:
    """Upgrade a Sprite Selection FARC archive.

    Args:
        input_path: Path to the input .farc file. Only required when at least
            one of LOGO/BG/JK is not provided (i.e. it must be extracted from
            the source FARC).
        output_dir: Output directory. If None, uses the directory of input_path.
        pv: New PV number (3 or 4 digits). If None, uses the original PV.
        jk_padding: Pixels to add on each side of JK (default: 2 for 1px border).
        resolution_mode: Resolution mode (default: 14=HDTV1080).
        logo_path: Optional path to a PNG file to use as the LOGO, overriding
            the one extracted from the source FARC.
        bg_path: Optional path to a PNG file to use as the BG, overriding
            the one extracted from the source FARC.
        jk_path: Optional path to a PNG file to use as the JK, overriding
            the one extracted from the source FARC.
        bg_jk_format: Encoding for the merged BG+JK texture. One of the keys
            in ``atlas_builder.BG_JK_FORMAT_IDS`` (``"dxt5"``, ``"rgb8"``).
            ``"rgb8"`` stores the texture as uncompressed RGB8 (no alpha).

    Returns:
        Path to the generated .farc file.
    """
    # If all three textures are provided, we can skip unpacking the source FARC.
    all_overridden = logo_path is not None and bg_path is not None and jk_path is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        if all_overridden:
            print(f'All LOGO/BG/JK provided - skipping extraction from {input_path}')
            final_bg = bg_path
            final_logo = logo_path
            jk_path = jk_path
        else:
            # --- Extract sprites ---
            print(f'Extracting sprites from {input_path}...')
            export_sprites_to_png(input_path, tmpdir)

            # Find the 3 PNG files
            png_files = sorted(Path(tmpdir).glob('*.png'))
            if len(png_files) != 3:
                raise ValueError(
                    f'Expected 3 PNG files, found {len(png_files)}: {png_files}'
                )

            extracted_bg = str(png_files[0])
            extracted_jk = str(png_files[1])
            extracted_logo = str(png_files[2])

            print(f'  BG (extracted): {extracted_bg}')
            print(f'  JK (extracted): {extracted_jk}')
            print(f'  LOGO (extracted): {extracted_logo}')

            # Use override logo/bg/jk if provided, otherwise use extracted ones
            if logo_path is not None:
                print(f'  LOGO (override): {logo_path}')
            if bg_path is not None:
                print(f'  BG (override): {bg_path}')
            if jk_path is not None:
                print(f'  JK (override): {jk_path}')

            final_bg = bg_path if bg_path is not None else extracted_bg
            final_logo = logo_path if logo_path is not None else extracted_logo
            jk_path = jk_path if jk_path is not None else extracted_jk

        # --- Pad JK if needed ---
        jk_img = Image.open(jk_path).convert('RGBA')
        jk_w, jk_h = jk_img.size
        print(f'  JK original size: {jk_w}x{jk_h}')

        if jk_w != 502 or jk_h != 502:
            print(f'  Padding JK from {jk_w}x{jk_h} to 502x502...')
            padded = Image.new('RGBA', (502, 502), (0, 0, 0, 0))
            # Center the original image
            x_offset = (502 - jk_w) // 2
            y_offset = (502 - jk_h) // 2
            padded.paste(jk_img, (x_offset, y_offset))
            # Save to a temp file so we never modify the user's source file.
            padded_jk = os.path.join(tmpdir, 'jk_padded.png')
            padded.save(padded_jk)
            jk_path = padded_jk
            print(f'  JK padded to {padded.size}')

        # --- Determine PV ---
        if pv is None:
            # Extract PV from input filename
            input_name = Path(input_path).stem
            # Expected format: spr_sel_pvXXXX.farc
            if 'pv' in input_name.lower():
                pv_idx = input_name.lower().index('pv') + 2
                pv = input_name[pv_idx:]
                # Remove any trailing non-digit characters
                pv = ''.join(c for c in pv if c.isdigit())
            else:
                raise ValueError(
                    f'Cannot determine PV from filename: {input_name}. '
                    'Please specify --pv.'
                )

        # --- Pack ---
        print(f'Packing with PV={pv}...')
        # Use output_dir to control where the file is written
        if output_dir is None:
            output_dir = os.path.dirname(input_path)
        output = build_sprite_selection_farc(
            bg_path=final_bg,
            jk_path=jk_path,
            logo_path=final_logo,
            pv=pv,
            output_dir=output_dir,
            resolution_mode=resolution_mode,
            bg_jk_format=bg_jk_format,
        )

        print(f'Wrote {output}')
        return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Upgrade a Sprite Selection FARC archive to DXT5 encoding.',
    )
    parser.add_argument('input', help='Input .farc file.')
    parser.add_argument('output_dir', nargs='?', help='Output directory (default: same as input).')
    parser.add_argument('--pv', help='New PV number (3 or 4 digits).')
    parser.add_argument('--jk-padding', type=int, default=2,
                        help='Pixels to add on each side of JK (default: 2).')
    parser.add_argument('--resolution-mode', type=int, default=14,
                        help='Resolution mode (default: 14=HDTV1080).')
    parser.add_argument('--logo', help='PNG file to use as LOGO, overriding the extracted one.')
    parser.add_argument('--bg', help='PNG file to use as BG, overriding the extracted one.')
    parser.add_argument('--jk', dest='jk', help='PNG file to use as JK, overriding the extracted one.')
    parser.add_argument('--bg-jk-format', default='dxt5',
                        choices=sorted(BG_JK_FORMAT_IDS),
                        help='Encoding for the merged BG+JK texture (default: dxt5). '
                             'dxt5=DXT5/BC3, rgb8=uncompressed RGB8 (no alpha), '
                             'rgba8=uncompressed RGBA8 (has alpha), '
                             'bc5=BC5/ATI2 (2x 4-bit channels, no alpha).')

    args = parser.parse_args(argv)

    try:
        upgrade_farc(
            input_path=args.input,
            output_dir=args.output_dir,
            pv=args.pv,
            jk_padding=args.jk_padding,
            resolution_mode=args.resolution_mode,
            logo_path=args.logo,
            bg_path=args.bg,
            jk_path=args.jk,
            bg_jk_format=args.bg_jk_format,
        )
        return 0
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
