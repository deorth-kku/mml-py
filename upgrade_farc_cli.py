"""Standalone CLI for upgrading a Sprite Selection FARC between PV numbers.

Usage:
    python upgrade_farc_cli.py <src_pv> <dst_pv> [--logo logo.png] [--bg bg.png]
                              [--bg-jk-format {dxt5,rgb8}]

Examples:
    python upgrade_farc_cli.py 874 1874
    python upgrade_farc_cli.py 874 1874 --logo custom_logo.png --bg custom_bg.png
    python upgrade_farc_cli.py 874 1874 --bg-jk-format rgb8
"""

from __future__ import annotations

import argparse
import sys

import pv_insert


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Upgrade a Sprite Selection FARC from src_pv to dst_pv with optional LOGO/BG override.',
    )
    parser.add_argument('src_pv', help='Source PV number (3 or 4 digits).')
    parser.add_argument('dst_pv', help='Destination PV number (3 or 4 digits).')
    parser.add_argument('--logo', help='PNG file to use as LOGO, overriding the extracted one.')
    parser.add_argument('--bg', help='PNG file to use as BG, overriding the extracted one.')
    parser.add_argument('--bg-jk-format', default='dxt5',
                        choices=['dxt5', 'rgb8'],
                        help='Encoding for the merged BG+JK texture (default: dxt5). '
                             'rgb8 = uncompressed RGB8 (no alpha).')

    args = parser.parse_args(argv)

    try:
        pv_insert.do_farc_upgrade(
            args.src_pv, args.dst_pv,
            logo_path=args.logo, bg_path=args.bg,
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
