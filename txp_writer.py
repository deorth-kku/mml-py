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
    """A single sprite entry in the SpriteSet."""
    name: str
    texture_index: int
    x: int
    y: int
    width: int
    height: int


class TextureBlock(NamedTuple):
    """A texture with its subtexture payload."""
    name: str
    width: int
    height: int
    payload: bytes  # raw DXT5/BC3 data (no DDS header)


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

def serialize_spriteset(
    sprites: list[SpriteRecord],
    textures: list[TextureBlock],
    sprite_modes: list[int] | None = None,
) -> bytes:
    """Serialize a complete SpriteSet BIN.

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

    num_sprites = len(sprites)
    num_textures = len(textures)

    # --- Phase 1: compute all string data and offsets ---
    # Texture names - compute offsets relative to string table start
    tex_name_bytes = [_encode_string(t.name) for t in textures]
    tex_name_offsets_rel = []
    offset_cursor = 0
    for nb in tex_name_bytes:
        tex_name_offsets_rel.append(offset_cursor)
        offset_cursor += len(nb)
    tex_name_total_size = offset_cursor

    # Sprite names - compute offsets relative to string table start
    sprite_name_bytes = [_encode_string(s.name) for s in sprites]
    sprite_name_offsets_rel = []
    offset_cursor = tex_name_total_size  # start after texture names
    for nb in sprite_name_bytes:
        sprite_name_offsets_rel.append(offset_cursor)
        offset_cursor += len(nb)
    sprite_name_total_size = offset_cursor - tex_name_total_size

    # --- Phase 2: compute structure offsets ---
    root_size = 32  # 8 int32 fields
    sprites_offset = root_size
    sprites_size = num_sprites * 40
    sprites_end = sprites_offset + sprites_size

    tex_name_off_table_offset = sprites_end
    tex_name_off_table_size = num_textures * 4
    tex_name_off_table_end = tex_name_off_table_offset + tex_name_off_table_size

    sprite_name_off_table_offset = tex_name_off_table_end
    sprite_name_off_table_size = num_sprites * 4
    sprite_name_off_table_end = sprite_name_off_table_offset + sprite_name_off_table_size

    sprite_modes_offset = sprite_name_off_table_end
    sprite_modes_size = len(sprite_modes) * 4
    sprite_modes_end = sprite_modes_offset + sprite_modes_size

    # String table starts after sprite modes
    string_table_offset = sprite_modes_end
    string_table_size = tex_name_total_size + sprite_name_total_size
    string_table_end = string_table_offset + string_table_size

    # TextureSet comes after string table
    texture_set_offset = string_table_end

    # Convert relative offsets to absolute file positions
    tex_name_offsets = [string_table_offset + off for off in tex_name_offsets_rel]
    sprite_name_offsets = [string_table_offset + off for off in sprite_name_offsets_rel]

    # --- Phase 2: compute structure offsets ---
    root_size = 32  # 8 int32 fields
    sprites_offset = root_size
    sprites_size = num_sprites * 40
    sprites_end = sprites_offset + sprites_size

    tex_name_off_table_offset = sprites_end
    tex_name_off_table_size = num_textures * 4
    tex_name_off_table_end = tex_name_off_table_offset + tex_name_off_table_size

    sprite_name_off_table_offset = tex_name_off_table_end
    sprite_name_off_table_size = num_sprites * 4
    sprite_name_off_table_end = sprite_name_off_table_offset + sprite_name_off_table_size

    sprite_modes_offset = sprite_name_off_table_end
    sprite_modes_size = len(sprite_modes) * 4
    sprite_modes_end = sprite_modes_offset + sprite_modes_size

    # String table starts after sprite modes
    string_table_offset = sprite_modes_end
    string_table_size = offset_cursor  # total string data size
    string_table_end = string_table_offset + string_table_size

    # TextureSet comes after string table
    texture_set_offset = string_table_end

    # --- Phase 3: assemble ---
    buf = bytearray()

    # Root header (8 int32)
    buf += struct.pack('<IIIIIIII',
        TXP_SPRITESET_SIG,
        texture_set_offset,
        num_textures,
        num_sprites,
        sprites_offset,
        tex_name_off_table_offset,
        sprite_name_off_table_offset,
        sprite_modes_offset,
    )

    # Sprite records (40 bytes each: I + i + 8f)
    for sp in sprites:
        buf += struct.pack('<Iiffffffff',
            sp.texture_index,
            0,  # reserved
            0.0, 0.0,   # rect_begin
            0.0, 0.0,   # rect_end
            float(sp.x), float(sp.y),
            float(sp.width), float(sp.height),
        )

    # Texture name offset table
    for off in tex_name_offsets:
        buf += struct.pack('<I', off)

    # Sprite name offset table
    for off in sprite_name_offsets:
        buf += struct.pack('<I', off)

    # Sprite modes table
    for mode in sprite_modes:
        buf += struct.pack('<I', mode)

    # String table
    for nb in tex_name_bytes + sprite_name_bytes:
        buf += nb

    # TextureSet block
    texset_data = _serialize_texture_set(textures)
    buf += texset_data

    return bytes(buf)
