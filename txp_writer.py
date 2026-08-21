"""TXP binary serialization for SpriteSet / TextureSet / Texture / SubTexture.

Writes a BIN file in the exact format expected by txp_parser.py's
SpriteSet_from_file() reader. Little-endian 32-bit fields throughout.
"""

from __future__ import annotations

import struct
from typing import NamedTuple


# ---------------------------------------------------------------------------
# TXP signatures
# ---------------------------------------------------------------------------

TXP_SPRITESET_SIG = 0x00000000
TXP_TEXSET_SIG = 0x03505854   # 'TPX\x03' little-endian
TXP_TEXTURE_SIG_V4 = 0x04505854
TXP_SUBTEXTURE_SIG = 0x02505854


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class SpriteRecord(NamedTuple):
    """A single sprite entry in the SpriteSet.

    ``rect_begin`` / ``rect_end`` are the UV corners of the tile in the sheet
    (spec 0.4). They default to (0, 0) so the legacy DXT5 / SPR_SEL path is
    unchanged; the PVTMB path fills them from the X/Y tile formula.
    """
    name: str
    texture_index: int
    x: int
    y: int
    width: int
    height: int
    rect_begin: tuple[float, float] = (0.0, 0.0)
    rect_end: tuple[float, float] = (0.0, 0.0)


class TextureBlock(NamedTuple):
    """A texture with its subtexture payload."""
    name: str
    width: int
    height: int
    payload: bytes  # raw DXT5/BC3 data (no DDS header)


class MipTexture(NamedTuple):
    """An RGBA8 (format 2) texture carrying a full power-of-two mip chain (PVTMB).

    ``mips`` holds the *storage-order* raw RGBA payloads (mip 0 first, each ``w*h*4``
    bytes). Storage order is vertically flipped (DX upside-down) per the PVTMB spec.
    """
    name: str
    width: int          # base width  (2048)
    height: int         # base height (1024)
    format: int         # 2 (RGBA8)
    mips: tuple[bytes, ...]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _encode_string(s: str) -> bytes:
    """Encode a string as UTF-8 null-terminated."""
    return s.encode('utf-8') + b'\x00'


def _align_up(value: int, alignment: int) -> int:
    """Round value up to the next multiple of alignment."""
    return (value + alignment - 1) // alignment * alignment


# ---------------------------------------------------------------------------
# SubTexture serialization
# ---------------------------------------------------------------------------

def _serialize_subtexture(st: TextureBlock) -> bytes:
    """Serialize one SubTexture: 6 int32 header + payload."""
    header = struct.pack(
        '<iiiiii',
        TXP_SUBTEXTURE_SIG,
        st.width,
        st.height,
        9,          # format ID 9 = DXT5
        0,          # id (always 0)
        len(st.payload),
    )
    return header + st.payload


# ---------------------------------------------------------------------------
# TextureSet serialization
# ---------------------------------------------------------------------------

def _serialize_texture_set(textures: list[TextureBlock]) -> bytes:
    """Serialize the TextureSet block.

    Layout:
        [TextureSet sig][count][rubbish_count][offsets...]
        [Texture sig][subcount][info][sub-offsets...]
        [SubTexture sig][w][h][fmt][id][size][payload]...
        (repeated for each subtexture in each texture)
    """
    parts = bytearray()

    # TextureSet header
    parts += struct.pack('<iii',
        TXP_TEXSET_SIG,
        len(textures),
        len(textures),  # textureCountWithRubbish = textureCount
    )

    # First, calculate all texture offsets (relative to TextureSet base)
    # We need to know where each texture will start
    # Header is 12 bytes, offset table is 8 bytes (2 * 4)
    offset_table_size = len(textures) * 4
    current_offset = 12 + offset_table_size  # after offset table
    offset_table = []
    for i, tex in enumerate(textures):
        offset_table.append(current_offset)
        # Calculate texture size: 12 bytes header + 4 bytes sub-offset + subtexture
        st_data = _serialize_subtexture(tex)
        current_offset += 12 + 4 + len(st_data)

    # Write offset table
    for off in offset_table:
        parts += struct.pack('<i', off)

    # Now write each texture
    for i, tex in enumerate(textures):
        # Texture header (12 bytes: sig + subcount + info)
        parts += struct.pack('<iii',
            TXP_TEXTURE_SIG_V4,
            1,  # subtexture count
            0x0101,  # info = (array_size << 8) | mip_count
        )

        # Subtexture offset table (4 bytes per subtexture)
        # SubTexture starts after the offset table
        sub_offset = 12 + 4  # 12 bytes for texture header + 4 bytes for offset table
        parts += struct.pack('<i', sub_offset)

        # SubTexture
        st_data = _serialize_subtexture(tex)
        parts += st_data

    return bytes(parts)


# ---------------------------------------------------------------------------
# SpriteSet root serialization
# ---------------------------------------------------------------------------

def _spriteset_prefix(
    num_sprites: int,
    num_textures: int,
    sprites: list[SpriteRecord],
    tex_name_bytes: list[bytes],
    sprite_name_bytes: list[bytes],
    sprite_modes: list[int],
) -> bytes:
    """Assemble everything up to (but not including) the TextureSet block.

    Root header (32 bytes) + sprite records (40 bytes each) + texture/sprite name
    offset tables + sprite mode table + string table. All offsets are absolute file
    positions. This is format-agnostic and shared by the DXT5 and RGBA8 (PVTMB) paths.
    """
    # --- Phase 1: compute relative string-table offsets ---
    tex_name_offsets_rel = []
    offset_cursor = 0
    for nb in tex_name_bytes:
        tex_name_offsets_rel.append(offset_cursor)
        offset_cursor += len(nb)
    tex_name_total = offset_cursor

    sprite_name_offsets_rel = []
    offset_cursor = tex_name_total  # sprite names follow texture names in the string table
    for nb in sprite_name_bytes:
        sprite_name_offsets_rel.append(offset_cursor)
        offset_cursor += len(nb)

    # --- Phase 2: compute structure offsets (all absolute) ---
    root_size = 32
    sprites_offset = root_size
    sprites_end = sprites_offset + num_sprites * 40

    tex_name_off_table_offset = sprites_end
    sprite_name_off_table_offset = tex_name_off_table_offset + num_textures * 4
    sprite_modes_offset = sprite_name_off_table_offset + num_sprites * 4

    string_table_offset = sprite_modes_offset + len(sprite_modes) * 8

    tex_name_offsets = [string_table_offset + off for off in tex_name_offsets_rel]
    sprite_name_offsets = [string_table_offset + off for off in sprite_name_offsets_rel]

    # --- Phase 3: assemble prefix ---
    buf = bytearray()
    buf += struct.pack('<IIIIIIII',
        TXP_SPRITESET_SIG,
        string_table_offset + offset_cursor,  # texture_set_offset = end of string table
        num_textures,
        num_sprites,
        sprites_offset,
        tex_name_off_table_offset,
        sprite_name_off_table_offset,
        sprite_modes_offset,
    )

    for sp in sprites:
        rb = getattr(sp, "rect_begin", (0.0, 0.0)) or (0.0, 0.0)
        re = getattr(sp, "rect_end", (0.0, 0.0)) or (0.0, 0.0)
        buf += struct.pack('<Iiffffffff',
            sp.texture_index,
            0,  # reserved
            float(rb[0]), float(rb[1]),   # rect_begin
            float(re[0]), float(re[1]),   # rect_end
            float(sp.x), float(sp.y),
            float(sp.width), float(sp.height),
        )

    for off in tex_name_offsets:
        buf += struct.pack('<I', off)
    for off in sprite_name_offsets:
        buf += struct.pack('<I', off)
    for mode in sprite_modes:
        buf += struct.pack('<II', 0, mode)

    for nb in tex_name_bytes + sprite_name_bytes:
        buf += nb

    return bytes(buf)


def serialize_spriteset(
    sprites: list[SpriteRecord],
    textures: list[TextureBlock],
    sprite_modes: list[int] | None = None,
) -> bytes:
    """Serialize a complete SpriteSet BIN (DXT5/BC3 single-subtexture textures).

    Args:
        sprites: Sprite records (names, positions, sizes).
        textures: Texture blocks (names, dimensions, DXT5 payload).
        sprite_modes: Optional list of sprite mode values.
                      Defaults to [0, 0, 0] matching the sample.

    Returns:
        Complete BIN bytes ready to be GZip-compressed and wrapped in FArC.
    """
    if sprite_modes is None:
        sprite_modes = [0, 0, 0]

    tex_name_bytes = [_encode_string(t.name) for t in textures]
    sprite_name_bytes = [_encode_string(s.name) for s in sprites]

    prefix = _spriteset_prefix(
        len(sprites), len(textures), sprites, tex_name_bytes, sprite_name_bytes, sprite_modes
    )
    return prefix + _serialize_texture_set(textures)


# ---------------------------------------------------------------------------
# PVTMB: RGBA8 (format 2) multi-mip texture serialization
# ---------------------------------------------------------------------------

def _mip_chain_sizes(width: int, height: int) -> list[tuple[int, int]]:
    """Full power-of-two mip chain from ``(width, height)`` down to 1x1.

    For a 2048x1024 base this yields 12 levels: 2048x1024, 1024x512, ..., 2x1, 1x1
    (both dimensions reach 1 on the same final level).
    """
    sizes = []
    w, h = width, height
    while True:
        sizes.append((w, h))
        if w <= 1 and h <= 1:
            break
        w = max(1, w // 2)
        h = max(1, h // 2)
    return sizes


def serialize_mip_payload(base_image, format_id: int = 2) -> list[bytes]:
    """Build the storage-order mip-chain payloads for an upright base texture.

    Generates a full power-of-two mip chain (LANCZOS down-sampling) from the
    ``base_image`` (which must be upright RGBA, as the user views it), then
    vertically flips each level for DX upside-down storage (spec 0.3b-2).

    Returns a list of raw ``w*h*4`` RGBA payloads, mip 0 first. Only format 2
    (raw RGBA8) is supported here; the payload is the raw bytes, no DDS/texconv.
    """
    from PIL import Image

    sizes = _mip_chain_sizes(base_image.width, base_image.height)
    payloads = []
    current = base_image
    for i, (w, h) in enumerate(sizes):
        level = current if i == 0 else current.resize((w, h), Image.LANCZOS)
        stored = level.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        # NOTE: use tobytes() with no encoder arg -- this PIL build lacks the raw
        # "RGBA" encoder, but the default (mode-based) encoder works fine for RGBA.
        payloads.append(stored.tobytes())
        current = level
    return payloads


def _serialize_mip_subtexture(width: int, height: int, format_id: int, mip_id: int, payload: bytes) -> bytes:
    """Serialize one format-2 SubTexture: 6 int32 header + raw RGBA payload."""
    header = struct.pack('<iiiiii',
        TXP_SUBTEXTURE_SIG,
        width,
        height,
        format_id,   # 2 = RGBA8 uncompressed
        mip_id,      # id == mip index
        len(payload),
    )
    return header + payload


def _serialize_mip_texture_set(textures: list[MipTexture]) -> bytes:
    """Serialize the PVTMB TextureSet block (spec 0.7): multi-subtexture, format 2.

    Layout:
        [TextureSet sig][count][rubbish_count][offsets...]
        [Texture sig][subcount][info=(1<<8)|mip_count][sub-offsets...]  (per texture)
        [SubTexture sig][w][h][fmt=2][id=mip][size][payload]...           (per mip)
    """
    parts = bytearray()

    # TextureSet header
    parts += struct.pack('<iii', TXP_TEXSET_SIG, len(textures), len(textures))

    # Per-texture total size (header + offset table + subtexture payloads)
    tex_sizes = []
    for t in textures:
        nsub = len(t.mips)
        subdata = sum(24 + len(p) for p in t.mips)  # 6 int32 header per subtexture
        tex_sizes.append(12 + nsub * 4 + subdata)

    # Global offset table: absolute offsets from TextureSet base to each texture header
    base = 12 + len(textures) * 4
    offset_table = []
    cursor = base
    for sz in tex_sizes:
        offset_table.append(cursor)
        cursor += sz
    for off in offset_table:
        parts += struct.pack('<i', off)

    # Per-texture data
    for t, rel_off in zip(textures, offset_table):
        sizes = _mip_chain_sizes(t.width, t.height)
        nsub = len(t.mips)
        # Texture header (12 bytes): sig, subcount=mip_count, info=(array_size<<8)|mip_count
        parts += struct.pack('<iii', TXP_TEXTURE_SIG_V4, nsub, (1 << 8) | nsub)

        # Sub-offset table (nsub uint32, relative to this texture header)
        rel = 12 + nsub * 4
        sub_positions = []
        for p in t.mips:
            sub_positions.append(rel)
            rel += 24 + len(p)
        for o in sub_positions:
            parts += struct.pack('<i', o)

        # Subtexture payloads
        for j, p in enumerate(t.mips):
            w, h = sizes[j]
            parts += _serialize_mip_subtexture(w, h, t.format, j, p)

    return bytes(parts)


def serialize_pvtmb_bin(
    sprites: list[SpriteRecord],
    textures: list[MipTexture],
    sprite_modes: list[int] | None = None,
) -> bytes:
    """Build a PVTMB BIN: shared SpriteSet root (spec 0.6) + mip-chain TextureSet (0.7).

    Reuses the proven root assembly from ``serialize_spriteset`` (32-byte root header,
    sprite records, name/mode offset tables, string table) and only swaps in the
    format-2 multi-subtexture TextureSet block.

    Args:
        sprites: SpriteRecord (name, texture_index, x, y, width, height).
        textures: MipTexture (name, width, height, format=2, mips=storage-order payloads).
        sprite_modes: resolution mode per sprite (default 0; caller usually passes 14).
    """
    if sprite_modes is None:
        sprite_modes = [0] * len(sprites)

    tex_name_bytes = [_encode_string(t.name) for t in textures]
    sprite_name_bytes = [_encode_string(s.name) for s in sprites]

    prefix = _spriteset_prefix(
        len(sprites), len(textures), sprites, tex_name_bytes, sprite_name_bytes, sprite_modes
    )
    return prefix + _serialize_mip_texture_set(textures)
