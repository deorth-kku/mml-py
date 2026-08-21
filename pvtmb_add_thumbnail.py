"""
pvtmb_add_thumbnail.py -- add/update a PV thumbnail sprite in a PVTMB ``spr_sel`` .farc.

Reuses the existing read/write pipeline:
    * ``txp_parser``  -- read FArC + BIN (SpriteSet_from_file)
    * ``txp_writer``  -- PVTMB BIN (serialize_pvtmb_bin, serialize_mip_payload)
    * ``farc_writer`` -- FArC wrapper (write_farc)

See ``pvtmb_plan.md`` and ``memories/repo/pvtmb_format.md`` for the format spec.

Flow is auto-selected:
    * farc absent                       -> CREATE (fresh black sheets + sidecar PNGs)
    * farc present, pv not a sprite     -> ADD    (row-major free tile, new sheet if needed)
    * farc present, pv already a sprite -> UPDATE (overwrite that PV's tile)

The cached sidecar PNG (<farc_stem>_tex{k}.png) is the single source of truth for the
base sheets (stored UPRIGHT, as viewed). The mip chain + BIN are always regenerated
*from* the cached base, never re-decoded from the FArC (spec 4).
"""
from __future__ import annotations

import argparse
import os
from PIL import Image

import txp_parser as tp
import txp_writer as tw
import farc_writer as fw

try:
    from config import pvtmb_farc, mm_mod
except Exception:  # config.py may not define it yet
    pvtmb_farc = None
    mm_mod = None

# --- format constants (spec 0.2/0.3/0.4) -------------------------------------
SHEET_W, SHEET_H = 2048, 1024
TILE_W, TILE_H = 128, 64
GRID_COLS = GRID_ROWS = 16
RES_MODE = 14  # HDTV1080
TEX_PREFIX = "MERGE_D5COMP_"

# Parallelogram art-region mask (spec 0.3b-1): 128x64, transparent corners.
# Reuse the reference tool so the shape/zoom stays in one place.
from pvtmb_tile_preview import build_parallelogram_mask, cover_to, TL, TR, BL, BR
from PIL import ImageChops

FRAME_MASK = build_parallelogram_mask()

# Art bounding box of the parallelogram, in tile coords (spec 0.3b-1): (28,1)-(125,63).
_ART_MIN = (min(TL[0], TR[0], BL[0], BR[0]), min(TL[1], TR[1], BL[1], BR[1]))  # (28, 1)
_ART_SIZE = (
    max(TL[0], TR[0], BL[0], BR[0]) - _ART_MIN[0],  # 97
    max(TL[1], TR[1], BL[1], BR[1]) - _ART_MIN[1],  # 62
)


# --- image prep (spec 3) ------------------------------------------------------
def prepare_thumbnail(src, tile=(TILE_W, TILE_H)) -> Image.Image:
    """Mirror ``pvtmb_tile_preview.make_tile`` exactly.

    Center-crop the source to the parallelogram's art bbox aspect (97x62), then
    scale it to exactly that bbox (no warp), inscribe it at the bbox origin, and
    bake the transparent corners into the alpha. The builder and the reference
    preview therefore always produce the identical tile -- no divergence in zoom or crop.
    """
    img = Image.open(src).convert("RGBA")
    patch = cover_to(img, _ART_SIZE)  # 97x62, center-crop to ratio then scale to exact
    out = Image.new("RGBA", tile, (0, 0, 0, 0))
    out.alpha_composite(patch, _ART_MIN)
    out.putalpha(ImageChops.multiply(out.split()[3], FRAME_MASK))  # transparent corners
    return out


def paint_tile(base: Image.Image, thumb: Image.Image, x: int, y: int) -> None:
    """Place ``thumb`` (128x64 RGBA with baked parallelogram alpha) at sheet pixel (x,y).

    Paint at the sprite's real pixel origin ``x=2+132*col``, ``y=2+68*row`` (spec 0.4),
    NOT at ``(col*TILE_W, row*TILE_H)``. The game samples the sheet via the sprite's UV
    rect, which begins at (x, y); painting at the 128-pixel tile grid instead would drift
    the art by ``(2+132*col) - 128*col = 2 + 4*col`` px -- a few pixels for the first
    columns, growing each column to the right. That drift is exactly the "spacing between
    tiles is off" symptom.

    ``alpha_composite`` reads the thumb's own alpha, so the transparent corners (and all
    other tiles) are left untouched -- equivalent to pasting through FRAME_MASK.
    """
    base.alpha_composite(thumb, (x, y))


# --- coordinate helpers (spec 0.4) --------------------------------------------
def uv_for_tile(col: int, row: int):
    """Return (X, Y, rect_begin_UV, rect_end_UV) for a grid tile."""
    x = 2 + 132 * col
    y = 2 + 68 * row
    rb = (x / SHEET_W, y / SHEET_H)
    re = ((x + TILE_W) / SHEET_W, (y + TILE_H) / SHEET_H)
    return x, y, rb, re


def tile_from_xy(x: int, y: int):
    """Invert the coordinate formula to a (col, row) grid slot."""
    return round((x - 2) / 132), round((y - 2) / 68)


def occupancy_by_tex(ss) -> dict[int, set]:
    """Occupied (col,row) per texture, skipping origin-collapsed placeholders.

    Real tiles sit on the X>=2, Y>=2 grid; the degenerate placeholder sprites
    in lavverso all collapse to pixel (0,0) (and x=0 variants) and must not
    occupy a real slot (spec 5).
    """
    occ: dict[int, set] = {}
    for s in ss.sprites:
        x, y = int(s.x), int(s.y)
        if x < 2 or y < 2:
            continue
        col, row = tile_from_xy(x, y)
        if 0 <= col < GRID_COLS and 0 <= row < GRID_ROWS:
            occ.setdefault(s.texture_index, set()).add((col, row))
    return occ


def free_tile(occ_by_tex: dict[int, set], n_textures: int):
    """Row-major first free tile: for each tex, row 0..15, col 0..15 (spec 5)."""
    for ti in range(n_textures):
        used = occ_by_tex.get(ti, set())
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                if (col, row) not in used:
                    return ti, col, row
    return None


# --- base texture cache (spec 4) ----------------------------------------------
def sidecar_path(farc_path: str, idx: int) -> str:
    return f"{os.path.splitext(farc_path)[0]}_tex{idx}.png"


def load_base(farc_path: str, idx: int, ss) -> Image.Image:
    """Upright base PNG for texture ``idx``: sidecar if present, else extract once.

    Stored DX bytes are upside-down (spec 0.3b-2); read raw (no channel swap,
    spec 0.3b-3), flip upright, and cache as the upright sidecar PNG.
    """
    sc = sidecar_path(farc_path, idx)
    if os.path.exists(sc):
        return Image.open(sc).convert("RGBA")
    st = ss.texture_set.textures[idx].subtextures[0][0]
    stored = Image.frombytes("RGBA", (st.width, st.height), st.data)
    upright = stored.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    upright.save(sc)
    return upright.copy()


# --- main flow ----------------------------------------------------------------
def run(farc_path: str, pv: str, image_path: str, out_path: str):
    create = not os.path.exists(farc_path)
    ss = tp.SpriteSet_from_file(farc_path) if create is False else None
    existing = next((s for s in ss.sprites if s.name == pv), None) if ss else None
    n_textures = len(ss.texture_set.textures) if ss else 0

    # upright bases (sidecar-truth, or fresh black sheets on create)
    bases: list[Image.Image] = []
    if ss is not None:
        for i in range(n_textures):
            bases.append(load_base(farc_path, i, ss))
    else:
        bases.append(Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0)))

    if existing is not None:
        # UPDATE: repaint the PV's existing tile (spec 5.2).
        # Paint at the sprite's real pixel origin (existing.x, existing.y), not a 128-grid.
        ti = existing.texture_index
        col, row = tile_from_xy(int(existing.x), int(existing.y))
        paint_tile(bases[ti], prepare_thumbnail(image_path), int(existing.x), int(existing.y))
        sprites = list(ss.sprites)
        modes = list(ss.sprite_modes)
        action = "update"
    else:
        # ADD / CREATE: pick first free tile, growing sheets if all are full (spec 5.1)
        occ = occupancy_by_tex(ss) if ss else {}
        free = free_tile(occ, len(bases))
        while free is None:
            bases.append(Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0)))
            free = free_tile(occ, len(bases))
            if len(bases) >= GRID_COLS * GRID_ROWS:  # safety cap
                raise RuntimeError("out of thumbnail sheets (max 256 tiles/texture)")
        ti, col, row = free
        x, y, rb, re = uv_for_tile(col, row)
        paint_tile(bases[ti], prepare_thumbnail(image_path), x, y)
        new_sp = tw.SpriteRecord(
            name=pv, texture_index=ti, x=x, y=y,
            width=TILE_W, height=TILE_H, rect_begin=rb, rect_end=re,
        )
        sprites = (list(ss.sprites) if ss else []) + [new_sp]
        modes = (list(ss.sprite_modes) if ss else []) + [RES_MODE]
        action = "create" if create else "add"

    # texture names (reuse existing, append MERGE_D5COMP_k for new sheets)
    tex_names = [t.name for t in ss.texture_set.textures] if ss else []
    while len(tex_names) < len(bases):
        tex_names.append(TEX_PREFIX + str(len(tex_names)))

    # persist sidecars (upright source of truth)
    out_stem = os.path.splitext(out_path)[0]
    for i, base in enumerate(bases):
        base.save(f"{out_stem}_tex{i}.png")

    # regenerate mip chain + BIN from the cached upright base (spec 4)
    mip_textures = [
        tw.MipTexture(
            name=tex_names[i], width=SHEET_W, height=SHEET_H, format=2,
            mips=tuple(tw.serialize_mip_payload(base, format_id=2)),
        )
        for i, base in enumerate(bases)
    ]
    bin_data = tw.serialize_pvtmb_bin(sprites, mip_textures, sprite_modes=modes)

    entry_name = os.path.splitext(os.path.basename(out_path))[0] + ".bin"
    farc_data = fw.write_farc(bin_data, entry_name)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(farc_data)

    # Rebuild mod_spr_db.bin like pv_insert does, but only when the output farc
    # is written into the live mod's 2d folder (working/test copies are skipped).
    if mm_mod and out_path:
        mm_2d_abs = os.path.abspath(mm_mod + r"\rom\2d")
        if os.path.abspath(out_path).startswith(mm_2d_abs + os.sep):
            from pv_insert import do_create_db
            do_create_db(mm_mod + r"\rom\2d")

    print(f"action={action} pv={pv} tex_index={ti} tile=(col {col}, row {row}) "
          f"X={2 + 132 * col} Y={2 + 68 * row} mode={RES_MODE} textures={len(bases)} sprites={len(sprites)}")
    print(f"  bin={len(bin_data)} B  farc={len(farc_data)} B  -> {out_path}")
    print("  sidecars: " + ", ".join(f"{out_stem}_tex{i}.png" for i in range(len(bases))))
    return out_path


# --- visual validation helper (spec 7.3) --------------------------------------
def export_sheet_upright(farc_path: str, out_dir: str, idx: int = 0) -> str:
    """Faithfully export a stored sheet upright (raw RGBA, no channel swap, flip)."""
    st = tp.SpriteSet_from_file(farc_path).texture_set.textures[idx].subtextures[0][0]
    upright = Image.frombytes("RGBA", (st.width, st.height), st.data)\
        .transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    os.makedirs(out_dir, exist_ok=True)
    name = tp.SpriteSet_from_file(farc_path).texture_set.textures[idx].name or f"sheet{idx}"
    path = os.path.join(out_dir, f"{name}_upright.png")
    upright.save(path)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Add/update a PVTMB thumbnail sprite in a spr_sel .farc."
    )
    parser.add_argument("--farc", default=pvtmb_farc,
                        help="target spr_sel_pvtmb_*.farc (default: config.pvtmb_farc)")
    parser.add_argument("--pv", required=True, help="decimal PV id (also the sprite name)")
    parser.add_argument("--image", required=True, help="source image (jacket/thumbnail; alpha optional)")
    parser.add_argument("--out", default=None, help="output farc (default: overwrite --farc)")
    args = parser.parse_args()
    if not args.farc:
        parser.error("no --farc given and config.pvtmb_farc is unset")
    run(args.farc, args.pv, args.image, args.out or args.farc)


if __name__ == "__main__":
    main()
