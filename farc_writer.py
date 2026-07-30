"""FArC container writer (Python-only, no C# dependency).

Writes the FArC archive wrapper around a GZip-compressed BIN payload.
Format: FArC signature + big-endian header size + alignment + entry name/
offset/size fields + aligned entry data.
"""

from __future__ import annotations

import gzip
import struct
from typing import NamedTuple


# ---------------------------------------------------------------------------
# FArC constants
# ---------------------------------------------------------------------------

FARC_SIGNATURE = b'FArC'
DEFAULT_ALIGNMENT = 0x10  # 16 bytes


# ---------------------------------------------------------------------------
# FArC entry
# ---------------------------------------------------------------------------

class FarcEntry(NamedTuple):
    """Metadata for a single FArC entry."""
    name: str
    offset: int
    compressed_size: int
    uncompressed_size: int


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _align_up(value: int, alignment: int) -> int:
    """Round value up to the next multiple of alignment."""
    return (value + alignment - 1) // alignment * alignment


def _compute_header_size(entry_name: str) -> int:
    """Compute header size field (big-endian) for FArC.

    Header size field = size of everything after the 8-byte
    (signature + header_size_field) prefix, up to and including the
    uncompressed_size field. Does NOT include padding.
    """
    # alignment (4) + name with null (len+1) + offset (4) + compressed (4) + uncompressed (4)
    return 4 + (len(entry_name) + 1) + 4 + 4 + 4


def write_farc(
    bin_data: bytes,
    entry_name: str,
    alignment: int = DEFAULT_ALIGNMENT,
    compressed: bool = True,
) -> bytes:
    """Build a complete FArC archive in memory.

    Args:
        bin_data: Uncompressed BIN payload (raw bytes).
        entry_name: Entry name, e.g. ``spr_sel_pv6901.bin``.
        alignment: Data alignment for entry offset (default 16).
        compressed: Whether to GZip-compress the payload.

    Returns:
        Complete FArC archive bytes.
    """
    # --- Compress if needed ---
    if compressed:
        payload = gzip.compress(bin_data)
    else:
        payload = bin_data

    compressed_size = len(payload)
    uncompressed_size = len(bin_data)

    # --- Compute offsets ---
    header_size_field = _compute_header_size(entry_name)
    # Header starts at byte 8 (after signature + header_size_field)
    header_end = 8 + header_size_field
    entry_offset = _align_up(header_end, alignment)

    # --- Build ---
    buf = bytearray()

    # Signature
    buf += FARC_SIGNATURE

    # Header size field (big-endian, value is header_size_field)
    buf += struct.pack('>I', header_size_field)

    # Alignment
    buf += struct.pack('>I', alignment)

    # Entry name (null-terminated)
    buf += entry_name.encode('utf-8') + b'\x00'

    # Entry offset (big-endian)
    buf += struct.pack('>I', entry_offset)

    # Compressed size (big-endian)
    buf += struct.pack('>I', compressed_size)

    # Uncompressed size (big-endian)
    buf += struct.pack('>I', uncompressed_size)

    # Padding to alignment
    padding = entry_offset - header_end
    if padding > 0:
        buf += b'\x00' * padding

    # Entry data
    buf += payload

    return bytes(buf)
