#!/usr/bin/env python3
import os
import struct
import json
import argparse
import io
import numpy as np
from PIL import Image
from texture2ddecoder import decode_bc1, decode_bc3

TXP_TEXSET_SIG = 0x03505854  # 'TXP' type 3
TXP_TEXTURE_SIG_V4 = 0x04505854
TXP_TEXTURE_SIG_V5 = 0x05505854
TXP_SUBTEXTURE_SIG = 0x02505854
TXP_SPRITESET_SIG = 0x00000000  # SpriteSet signature (all zeros)


class FarcEntry:
    """Represents a single entry in a FARC archive."""
    def __init__(self, name: str, offset: int, compressed_size: int, uncompressed_size: int, is_compressed: bool):
        self.name = name
        self.offset = offset
        self.compressed_size = compressed_size
        self.uncompressed_size = uncompressed_size
        self.is_compressed = is_compressed


class FarcArchive:
    """Base class for parsing FARC/FArC/FArc archives."""
    def __init__(self):
        self.signature = None
        self.header_size = None
        self.entries = []
        self.alignment = 1
    
    @staticmethod
    def _read_cstring(f) -> str:
        """Read null-terminated string from file."""
        name_bytes = bytearray()
        while True:
            b = f.read(1)
            if not b or b[0] == 0:
                break
            name_bytes.extend(b)
        return name_bytes.decode('utf-8', errors='ignore')
    
    @classmethod
    def from_file(cls, farc_path: str) -> 'FarcArchive':
        """Create a FarcArchive from a file path."""
        archive = cls()
        with open(farc_path, 'rb') as f:
            archive.parse(f)
        return archive
    
    def parse(self, f):
        """Parse FARC archive from file object."""
        # Read signature and header size
        self.signature = f.read(4).decode('ascii')
        if self.signature not in ('FARC', 'FArC', 'FArc'):
            raise ValueError(f'Invalid FARC signature: {self.signature}')
        
        header_size_value = struct.unpack('>I', f.read(4))[0]
        self.header_size = header_size_value + 0x08
        
        print(f"FARC signature: {self.signature}, header size: {self.header_size}")
        
        # Parse format-specific entries
        if self.signature == 'FARC':
            self._parse_farc(f)
        elif self.signature == 'FArC':
            self._parse_farc_lowercase(f)
        elif self.signature == 'FArc':
            self._parse_farc_minimal(f)
    
    def _parse_farc(self, f):
        """Parse FARC format (full format with flags)."""
        flags = struct.unpack('>I', f.read(4))[0]
        is_compressed_archive = (flags & 2) != 0
        is_encrypted = (flags & 4) != 0
        padding = struct.unpack('>I', f.read(4))[0]
        self.alignment = struct.unpack('>I', f.read(4))[0]
        
        print(f"  Compressed: {is_compressed_archive}, Encrypted: {is_encrypted}, Alignment: {self.alignment}")
        
        if is_encrypted:
            raise NotImplementedError("Encrypted FARC files not yet supported")
        
        entry_padding = struct.unpack('>I', f.read(4))[0]
        header_padding = struct.unpack('>I', f.read(4))[0]
        
        if header_padding > 0:
            f.read(header_padding)
        
        # Read entries
        while f.tell() < self.header_size:
            name = self._read_cstring(f)
            offset = struct.unpack('>I', f.read(4))[0]
            compressed_size = struct.unpack('>I', f.read(4))[0]
            uncompressed_size = struct.unpack('>I', f.read(4))[0]
            
            if entry_padding > 0:
                f.read(entry_padding)
            
            entry = FarcEntry(
                name=name,
                offset=offset,
                compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                is_compressed=is_compressed_archive and compressed_size != uncompressed_size
            )
            self.entries.append(entry)
            print(f"  Entry: {name} (offset={offset}, size={uncompressed_size})")
    
    def _parse_farc_lowercase(self, f):
        """Parse FArC format (older format)."""
        self.alignment = struct.unpack('>I', f.read(4))[0]
        print(f"  Alignment: {self.alignment}")
        
        # Read entries
        while f.tell() < self.header_size:
            name = self._read_cstring(f)
            offset = struct.unpack('>I', f.read(4))[0]
            compressed_size = struct.unpack('>I', f.read(4))[0]
            uncompressed_size = struct.unpack('>I', f.read(4))[0]
            
            # In FArC format: if uncompressed_size == 0, data is not compressed
            is_compressed = (uncompressed_size != 0 and compressed_size != uncompressed_size)
            if uncompressed_size == 0:
                uncompressed_size = compressed_size
            
            entry = FarcEntry(
                name=name,
                offset=offset,
                compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                is_compressed=is_compressed
            )
            self.entries.append(entry)
            print(f"  Entry: {name} (offset={offset}, compressed={compressed_size}, uncompressed={uncompressed_size}, is_compressed={is_compressed})")
    
    def _parse_farc_minimal(self, f):
        """Parse FArc format (minimal format, no compression)."""
        self.alignment = struct.unpack('>I', f.read(4))[0]
        print(f"  Alignment: {self.alignment}")
        
        # Read entries
        while f.tell() < self.header_size:
            name = self._read_cstring(f)
            offset = struct.unpack('>I', f.read(4))[0]
            size = struct.unpack('>I', f.read(4))[0]
            
            entry = FarcEntry(
                name=name,
                offset=offset,
                compressed_size=size,
                uncompressed_size=size,
                is_compressed=False
            )
            self.entries.append(entry)
            print(f"  Entry: {name} (offset={offset}, size={size})")
    
    def extract_entry_data(self, f, entry: FarcEntry) -> bytes:
        """Extract and decompress data for a single entry."""
        f.seek(entry.offset)
        data = f.read(entry.compressed_size)
        
        if entry.is_compressed:
            import gzip
            try:
                data = gzip.decompress(data)
            except Exception as e:
                print(f"  GZip decompression failed for {entry.name}: {e}")
        
        return data


# TextureFormat enum mapping from C# MikuMikuLibrary
TEXTURE_FORMAT_MAP = {
    0: "A8",
    1: "RGB8",
    2: "RGBA8",
    3: "RGB5",
    4: "RGB5A1",
    5: "RGBA4",
    6: "DXT1",
    7: "DXT1a",
    8: "DXT3",
    9: "DXT5",
    10: "ATI1",
    11: "ATI2",
    12: "L8",
    13: "L8A8",
    15: "BC7",
    127: "BC6H",
}


def read_cstring(f):
    s = bytearray()
    while True:
        c = f.read(1)
        if not c or c == b"\x00":
            break
        s += c
    return s.decode('utf-8', errors='replace')


class Reader:
    def __init__(self, f):
        self.f = f
        # default assume little-endian; will switch if header indicates big
        self.endian = '<'
        self.base_stack = [0]

    def tell(self):
        return self.f.tell()

    def seek(self, pos, whence=0):
        self.f.seek(pos, whence)

    def push_base(self, offset=None):
        if offset is None:
            self.base_stack.append(self.tell())
        else:
            self.base_stack.append(offset)

    def pop_base(self):
        return self.base_stack.pop()

    @property
    def base(self):
        return self.base_stack[-1]

    def set_endian(self, little=True):
        self.endian = '<' if little else '>'

    def read_fmt(self, fmt):
        size = struct.calcsize(fmt)
        data = self.f.read(size)
        if len(data) != size:
            raise EOFError('Unexpected EOF')
        return struct.unpack(self.endian + fmt, data) if fmt != 's' else data

    def read_int32(self):
        return self.read_fmt('i')[0]

    def read_uint32(self):
        return self.read_fmt('I')[0]

    def read_float(self):
        return self.read_fmt('f')[0]

    def read_bytes(self, n):
        return self.f.read(n)

    def read_offset(self):
        # assume 32-bit offsets like in the C# code (AddressSpace.Int32)
        return self.read_uint32()

    def read_at_offset(self, offset, func):
        if offset == 0:
            return None
        cur = self.tell()
        self.seek(self.base + offset)
        res = func()
        self.seek(cur)
        return res

    def read_string_at_offset(self, offset):
        if offset == 0:
            return None
        cur = self.tell()
        self.seek(self.base + offset)
        s = read_cstring(self.f)
        self.seek(cur)
        return s


def extract_farc(farc_path: str, output_dir: str):
    """Extract files from a FARC archive."""
    # Parse FARC archive
    archive = FarcArchive.from_file(farc_path)
    
    # Extract all entries
    os.makedirs(output_dir, exist_ok=True)
    
    with open(farc_path, 'rb') as f:
        for entry in archive.entries:
            data = archive.extract_entry_data(f, entry)
            
            # Write file
            out_path = os.path.join(output_dir, entry.name)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'wb') as out:
                out.write(data)
            print(f"Extracted: {entry.name} ({len(data)} bytes)")


class SubTexture:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.format = 0
        self.id = 0
        self.data = b''

    def read(self, r: Reader):
        sig = r.read_int32()
        if sig != TXP_SUBTEXTURE_SIG:
            raise ValueError(f'Invalid SubTexture signature: 0x{sig:08X}')
        self.width = r.read_int32()
        self.height = r.read_int32()
        self.format = r.read_int32()
        self.id = r.read_int32()
        data_size = r.read_int32()
        self.data = r.read_bytes(data_size)

    def dump(self, out_dir, name_prefix):
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{name_prefix}_w{self.width}_h{self.height}_f{self.format}_id{self.id}.bin")
        with open(path, 'wb') as wf:
            wf.write(self.data)
        return path


def decode_dxt_to_image(dxt_data: bytes, width: int, height: int, format_id: int) -> Image.Image:
    """Decode DXT compressed data and return a PIL Image (RGBA)."""
    if format_id == 6:  # DXT1 = BC1 (no alpha channel, but decode_bc1 returns RGBA anyway)
        rgba_bytes = decode_bc1(dxt_data, width, height)
    elif format_id == 9:  # DXT5 = BC3 (with alpha channel)
        rgba_bytes = decode_bc3(dxt_data, width, height)
    else:
        raise ValueError(f'Unsupported DXT format: {format_id}')
    
    # Convert bytes to numpy array
    rgba_array = np.frombuffer(rgba_bytes, dtype=np.uint8).reshape((height, width, 4))
    
    # Convert to PIL Image (RGBA)
    img = Image.fromarray(rgba_array, mode='RGBA')
    
    # Rotate 180 degrees to fix upside-down image
    #img = img.rotate(180, expand=False)
    #img = img.transpose(Image.FLIP_TOP_BOTTOM)
    
    return img


class Texture:
    def __init__(self):
        self.subtextures = []  # 2D flattened as [array_index][mip]
        self.name = None

    def read(self, r: Reader):
        # Set base to current position (start of Texture)
        texture_base = r.tell()
        r.push_base(texture_base)
        
        sig = r.read_int32()
        if sig not in (TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5):
            r.pop_base()
            raise ValueError(f'Invalid Texture signature: 0x{sig:08X}')
        subcount = r.read_int32()
        info = r.read_int32()
        mip_count = info & 0xFF
        array_size = (info >> 8) & 0xFF
        if array_size == 1 and mip_count != subcount:
            # C# logic: if only arraySize==1 and subTextureCount != mipMapCount
            mip_count = subcount

        # prepare container
        self.array_size = max(1, array_size)
        self.mip_count = max(1, mip_count)
        self.subtextures = [[None for _ in range(self.mip_count)] for _ in range(self.array_size)]

        # read offsets table and load subtextures
        # offsets are stored sequentially for (array_index, mip)
        for i in range(self.array_size):
            for j in range(self.mip_count):
                offset = r.read_offset()
                if offset != 0:
                    cur = r.tell()
                    r.seek(r.base + offset)
                    st = SubTexture()
                    st.read(r)
                    self.subtextures[i][j] = st
                    r.seek(cur)
        
        r.pop_base()

    def dump_subtextures(self, out_dir, tex_idx):
        paths = []
        for i in range(self.array_size):
            for j in range(self.mip_count):
                st = self.subtextures[i][j]
                if st:
                    namep = f"tex{tex_idx}_arr{i}_mip{j}"
                    paths.append(st.dump(out_dir, namep))
        return paths
    
    def get_base_texture_image(self):
        """Get the base (full resolution) texture as a PIL Image."""
        if (len(self.subtextures) > 0 and len(self.subtextures[0]) > 0 and 
            self.subtextures[0][0] is not None):
            st = self.subtextures[0][0]
            return decode_dxt_to_image(st.data, st.width, st.height, st.format)
        return None


class TextureSet:
    def __init__(self):
        self.textures = []
        self.texture_names = {}  # idx -> name

    def read(self, r: Reader, texture_names_offset=0):
        # When called by SpriteSet, base is already set to TextureSet start
        sig = r.read_int32()
        # auto-detect endianness if needed
        if sig != TXP_TEXSET_SIG:
            # try swapping
            r.set_endian(False)
            r.seek(r.tell() - 4)
            sig_be = r.read_int32()
            if sig_be != TXP_TEXSET_SIG:
                raise ValueError('Invalid TextureSet signature (expected TXP type 3)')
        # keep whatever endian now in reader
        tex_count = r.read_int32()
        _ = r.read_int32()  # textureCountWithRubbish
        # offsets to textures (relative to TextureSet base)
        offsets = [r.read_offset() for _ in range(tex_count)]
        for off in offsets:
            if off != 0:
                cur = r.tell()
                r.seek(r.base + off)
                tex = Texture()
                tex.read(r)
                self.textures.append(tex)
                r.seek(cur)
        
        # Read texture names if provided
        if texture_names_offset != 0:
            cur = r.tell()
            # First, read all name offsets
            r.seek(texture_names_offset)
            name_offsets = []
            for i in range(tex_count):
                name_offset = struct.unpack('<I', r.f.read(4))[0]
                name_offsets.append(name_offset)
            
            # Then, read each name from its offset
            for i, name_offset in enumerate(name_offsets):
                if name_offset != 0:
                    r.seek(name_offset)
                    name = read_cstring(r.f)
                    if i < len(self.textures):
                        self.textures[i].name = name
                    self.texture_names[i] = name
            
            r.seek(cur)

    def dump_all(self, out_dir):
        all_paths = []
        for idx, tex in enumerate(self.textures):
            all_paths += tex.dump_subtextures(out_dir, idx)
        return all_paths


class Sprite:
    def __init__(self):
        self.texture_index = 0
        self.rect_begin = (0.0, 0.0)
        self.rect_end = (0.0, 0.0)
        self.x = 0.0
        self.y = 0.0
        self.width = 0.0
        self.height = 0.0
        self.name = None

    def read(self, r: Reader):
        self.texture_index = r.read_uint32()
        _ = r.read_uint32()  # reserved
        bx = r.read_float(); by = r.read_float()
        ex = r.read_float(); ey = r.read_float()
        self.rect_begin = (bx, by)
        self.rect_end = (ex, ey)
        self.x = r.read_float(); self.y = r.read_float()
        self.width = r.read_float(); self.height = r.read_float()
    
    def crop_from_texture(self, texture_image: Image.Image) -> Image.Image:
        """Crop this sprite from the texture using x, y, width, height."""
        if texture_image is None:
            return None
        
        # Flip the texture vertically first (decode produces upside-down image)
        texture_image = texture_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        
        # Use x, y, width, height directly (they are in pixel coordinates)
        x1 = int(self.x)
        y1 = int(self.y)
        x2 = x1 + int(self.width)
        y2 = y1 + int(self.height)
        
        # Crop using (left, top, right, bottom)
        return texture_image.crop((x1, y1, x2, y2))


class SpriteSet:
    def __init__(self):
        self.sprites = []
        self.texture_set = None

    def read(self, r: Reader):
        # SpriteSet is at file position 0, so base is 0
        sig = r.read_int32()  # signature (usually 0x00000000)
        textures_offset = r.read_uint32()
        texture_count = r.read_int32()
        sprite_count = r.read_int32()
        sprites_offset = r.read_offset()
        texture_names_offset = r.read_offset()
        sprite_names_offset = r.read_offset()
        sprite_modes_offset = r.read_offset()

        # Read TextureSet at textures_offset (absolute file position)
        if textures_offset != 0:
            cur = r.tell()
            r.seek(textures_offset)
            r.push_base(textures_offset)  # Set base to TextureSet start
            self.texture_set = TextureSet()
            # Pass absolute texture_names_offset to TextureSet.read()
            self.texture_set.read(r, texture_names_offset=texture_names_offset)
            r.pop_base()
            r.seek(cur)

        # Read sprite data structures (40 bytes each)
        if sprites_offset != 0:
            cur = r.tell()
            r.seek(r.base + sprites_offset)
            for _ in range(sprite_count):
                s = Sprite()
                s.read(r)
                self.sprites.append(s)
            r.seek(cur)

        # Read sprite name offsets (point to absolute file positions)
        if sprite_names_offset != 0:
            cur = r.tell()
            r.seek(r.base + sprite_names_offset)
            name_offsets = []
            for _ in range(sprite_count):
                offset = r.read_offset()
                name_offsets.append(offset)
            
            # Read names from their absolute file positions
            for i, offset in enumerate(name_offsets):
                if offset != 0:
                    r.seek(offset)  # absolute position
                    name = read_cstring(r.f)
                    self.sprites[i].name = name
            
            r.seek(cur)


def parse_txd(path):
    with open(path, 'rb') as f:
        r = Reader(f)
        # detect whether file is TextureSet, single Texture, or SubTexture
        cur = f.tell()
        raw = f.read(4)
        if len(raw) < 4:
            raise ValueError('File too small')
        le = struct.unpack('<I', raw)[0]
        be = struct.unpack('>I', raw)[0]
        f.seek(cur)

        if le == TXP_TEXSET_SIG or be == TXP_TEXSET_SIG:
            # texture set
            if be == TXP_TEXSET_SIG and le != TXP_TEXSET_SIG:
                r.set_endian(False)
            ts = TextureSet()
            ts.read(r)
            out = os.path.join(os.path.dirname(path), os.path.basename(path) + '_subtextures')
            paths = ts.dump_all(out)
            print(f'Wrote {len(paths)} subtexture blobs to {out}')

        elif le == TXP_TEXTURE_SIG_V4 or le == TXP_TEXTURE_SIG_V5 or be == TXP_TEXTURE_SIG_V4 or be == TXP_TEXTURE_SIG_V5:
            # single texture
            if be in (TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5) and le not in (TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5):
                r.set_endian(False)
            # parse a single Texture at file start
            tex = Texture()
            tex.read(r)
            out = os.path.join(os.path.dirname(path), os.path.basename(path) + '_subtextures')
            paths = tex.dump_subtextures(out, 0)
            print(f'Wrote {len(paths)} subtexture blobs to {out}')

        elif le == TXP_SUBTEXTURE_SIG or be == TXP_SUBTEXTURE_SIG:
            if be == TXP_SUBTEXTURE_SIG and le != TXP_SUBTEXTURE_SIG:
                r.set_endian(False)
            st = SubTexture()
            st.read(r)
            out = os.path.join(os.path.dirname(path), os.path.basename(path) + '_subtextures')
            os.makedirs(out, exist_ok=True)
            p = st.dump(out, 'sub0')
            print(f'Wrote subtexture blob to {p}')

        else:
            # try scanning file for embedded TXP signatures
            f.seek(0)
            data = f.read()
            hits = []
            patterns = [
                struct.pack('<I', TXP_TEXSET_SIG),
                struct.pack('<I', TXP_TEXTURE_SIG_V4),
                struct.pack('<I', TXP_TEXTURE_SIG_V5),
                struct.pack('<I', TXP_SUBTEXTURE_SIG),
            ]
            # also consider big-endian byte sequences
            patterns_be = [p[::-1] for p in patterns]
            all_patterns = set(patterns + patterns_be)

            for pat in all_patterns:
                start = 0
                while True:
                    idx = data.find(pat, start)
                    if idx == -1:
                        break
                    hits.append(idx)
                    start = idx + 1

            if not hits:
                raise ValueError(f'Unknown signature: LE=0x{le:08X} BE=0x{be:08X} and no embedded TXP found')

            found_any = 0
            for off in sorted(set(hits)):
                try:
                    # determine endianness for this candidate by peeking raw bytes
                    raw = data[off:off+4]
                    le_sig = struct.unpack('<I', raw)[0]
                    be_sig = struct.unpack('>I', raw)[0]

                    valid_sigs = (TXP_TEXSET_SIG, TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5, TXP_SUBTEXTURE_SIG)

                    if le_sig in valid_sigs and be_sig not in valid_sigs:
                        r.set_endian(True)
                    elif be_sig in valid_sigs and le_sig not in valid_sigs:
                        r.set_endian(False)
                    elif le_sig in valid_sigs:
                        r.set_endian(True)
                    elif be_sig in valid_sigs:
                        r.set_endian(False)
                    else:
                        # nothing to do
                        continue

                    # seek to the signature start and set base for in-block offsets
                    r.seek(off)
                    r.push_base(off)

                    sig = r.read_int32()
                    base_name = os.path.basename(path)
                    outdir = os.path.join(os.path.dirname(path), f"{base_name}_embedded_{off}_subtextures")

                    if sig == TXP_TEXSET_SIG:
                        # ensure reader positioned at start of texture set
                        r.seek(off)
                        ts = TextureSet()
                        ts.read(r)
                        paths = ts.dump_all(outdir)
                        print(f'At offset {off}: wrote {len(paths)} subtexture blobs to {outdir}')
                        found_any += 1

                    elif sig in (TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5):
                        r.seek(off)
                        tex = Texture()
                        tex.read(r)
                        paths = tex.dump_subtextures(outdir, 0)
                        print(f'At offset {off}: wrote {len(paths)} subtexture blobs to {outdir}')
                        found_any += 1

                    elif sig == TXP_SUBTEXTURE_SIG:
                        r.seek(off)
                        st = SubTexture()
                        st.read(r)
                        os.makedirs(outdir, exist_ok=True)
                        p = st.dump(outdir, f'sub_{off}')
                        print(f'At offset {off}: wrote subtexture blob to {p}')
                        found_any += 1

                except Exception as ex:
                    # ignore parse errors for this hit and continue
                    print(f'Failed to parse at offset {off}: {ex}')
                finally:
                    # restore base stack (pop the push done earlier if present)
                    try:
                        r.pop_base()
                    except Exception:
                        pass

            if found_any == 0:
                raise ValueError('Found candidate signatures but failed to parse any TXP blocks')


def parse_spr(path):
    with open(path, 'rb') as f:
        r = Reader(f)
        ss = SpriteSet()
        ss.read(r)
        print(f'Parsed {len(ss.sprites)} sprites')
        for i, s in enumerate(ss.sprites):
            print(i, s.name, 'tex=', s.texture_index, 'x,y,w,h=', s.x, s.y, s.width, s.height)


def collect_txp_blocks(path):
    """Scan file and return list of TXP-like blocks with offsets and TextureSet/Texture info."""
    blocks = []
    with open(path, 'rb') as f:
        data = f.read()
    patterns = [
        struct.pack('<I', TXP_TEXSET_SIG),
        struct.pack('<I', TXP_TEXTURE_SIG_V4),
        struct.pack('<I', TXP_TEXTURE_SIG_V5),
        struct.pack('<I', TXP_SUBTEXTURE_SIG),
    ]
    patterns_be = [p[::-1] for p in patterns]
    all_patterns = set(patterns + patterns_be)
    hits = []
    for pat in all_patterns:
        start = 0
        while True:
            idx = data.find(pat, start)
            if idx == -1:
                break
            hits.append(idx)
            start = idx + 1

    with open(path, 'rb') as f:
        r = Reader(f)
        for off in sorted(set(hits)):
            try:
                raw = data[off:off+4]
                le_sig = struct.unpack('<I', raw)[0]
                be_sig = struct.unpack('>I', raw)[0]
                valid_sigs = (TXP_TEXSET_SIG, TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5, TXP_SUBTEXTURE_SIG)
                if le_sig in valid_sigs and be_sig not in valid_sigs:
                    r.set_endian(True)
                elif be_sig in valid_sigs and le_sig not in valid_sigs:
                    r.set_endian(False)
                elif le_sig in valid_sigs:
                    r.set_endian(True)
                elif be_sig in valid_sigs:
                    r.set_endian(False)
                else:
                    continue

                r.seek(off)
                r.push_base(off)
                sig = r.read_int32()
                if sig == TXP_TEXSET_SIG:
                    # parse texture set summary
                    r.seek(off)
                    
                    # Try to find SpriteSet header before this TextureSet to get texture_names_offset
                    texture_names_offset_to_use = 0
                    # Look backwards for SpriteSet header (offset typically 0x00 or nearby)
                    for search_off in range(max(0, off - 1000), off, 4):
                        try:
                            r.seek(search_off)
                            test_sig = r.read_int32()
                            if test_sig == TXP_SPRITESET_SIG:
                                # Found SpriteSet, read its header to get texture_names_offset
                                r.seek(search_off + 4)  # skip sig
                                r.read_uint32()  # textures_offset (4 bytes)
                                r.read_int32()  # tex_count (4 bytes)
                                r.read_int32()  # sprite_count (4 bytes)
                                r.read_uint32()  # sprites_offset (4 bytes)
                                texture_names_offset_to_use = r.read_uint32()  # texture_names_offset (4 bytes)
                                break
                        except:
                            pass
                    
                    r.seek(off)
                    ts = TextureSet()
                    ts.read(r, texture_names_offset=texture_names_offset_to_use)
                    texs = []
                    for ti, tex in enumerate(ts.textures):
                        # get base mip subtexture (array 0, mip 0) if exists
                        st = None
                        if getattr(tex, 'subtextures', None):
                            if len(tex.subtextures) > 0 and len(tex.subtextures[0]) > 0:
                                st = tex.subtextures[0][0]
                        format_id = st.format if st else None
                        format_name = TEXTURE_FORMAT_MAP.get(format_id, f'UNKNOWN_{format_id}') if format_id is not None else None
                        tex_name = getattr(tex, 'name', None)
                        texs.append({
                            'index': ti,
                            'name': tex_name,
                            'array_size': getattr(tex, 'array_size', 1),
                            'mip_count': getattr(tex, 'mip_count', 1),
                            'base_width': st.width if st else None,
                            'base_height': st.height if st else None,
                            'base_format': format_name or format_id,
                        })
                    blocks.append({'offset': off, 'type': 'TextureSet', 'textures': texs})

                elif sig in (TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5):
                    r.seek(off)
                    tex = Texture()
                    tex.read(r)
                    st = None
                    if len(tex.subtextures) > 0 and len(tex.subtextures[0]) > 0:
                        st = tex.subtextures[0][0]
                    format_id = st.format if st else None
                    format_name = TEXTURE_FORMAT_MAP.get(format_id, f'UNKNOWN_{format_id}') if format_id is not None else None
                    tex_name = getattr(tex, 'name', None)
                    blocks.append({'offset': off, 'type': 'Texture', 'textures': [{
                        'index': 0,
                        'name': tex_name,
                        'array_size': getattr(tex, 'array_size', 1),
                        'mip_count': getattr(tex, 'mip_count', 1),
                        'base_width': st.width if st else None,
                        'base_height': st.height if st else None,
                        'base_format': format_name or format_id,
                    }]})

                elif sig == TXP_SUBTEXTURE_SIG:
                    r.seek(off)
                    st = SubTexture()
                    st.read(r)
                    blocks.append({'offset': off, 'type': 'SubTexture', 'width': st.width, 'height': st.height, 'format': st.format, 'id': st.id})

            except Exception:
                pass
            finally:
                try:
                    r.pop_base()
                except Exception:
                    pass

    return blocks


def export_base_mips(path, out_dir_base):
    """Export only base mip (array 0, mip 0) for each texture found in TXP blocks."""
    blocks = collect_txp_blocks(path)
    exported = []
    with open(path, 'rb') as f:
        r = Reader(f)
        data = f.read()
        for block in blocks:
            off = block['offset']
            # only handle TextureSet or single Texture blocks
            if block['type'] not in ('TextureSet', 'Texture'):
                continue
            # parse again to access subtextures and dump base mip
            r.seek(off)
            r.push_base(off)
            try:
                sig = r.read_int32()
                base_name = os.path.basename(path)
                outdir = os.path.join(os.path.dirname(path), f"{base_name}_base_{off}")
                if sig == TXP_TEXSET_SIG:
                    r.seek(off)
                    ts = TextureSet()
                    ts.read(r)
                    for ti, tex in enumerate(ts.textures):
                        st = None
                        if getattr(tex, 'subtextures', None) and len(tex.subtextures) > 0 and len(tex.subtextures[0]) > 0:
                            st = tex.subtextures[0][0]
                        if st:
                            os.makedirs(outdir, exist_ok=True)
                            p = st.dump(outdir, f"tex{ti}_base")
                            exported.append(p)
                elif sig in (TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5):
                    r.seek(off)
                    tex = Texture()
                    tex.read(r)
                    if len(tex.subtextures) > 0 and len(tex.subtextures[0]) > 0:
                        st = tex.subtextures[0][0]
                        os.makedirs(outdir, exist_ok=True)
                        p = st.dump(outdir, "tex0_base")
                        exported.append(p)
            except Exception:
                pass
            finally:
                try:
                    r.pop_base()
                except Exception:
                    pass

    return blocks, exported


def export_sprites_to_png(bin_path: str, output_dir: str):
    """Parse sprites from .bin file and export each sprite as PNG."""
    os.makedirs(output_dir, exist_ok=True)
    
    with open(bin_path, 'rb') as f:
        data = f.read()
    
    # Try to parse SpriteSet
    sprite_set = None
    for little in (True, False):
        try:
            fobj = io.BytesIO(data)
            r = Reader(fobj)
            r.set_endian(little)
            ss = SpriteSet()
            ss.read(r)
            if ss.sprites and ss.texture_set:
                sprite_set = ss
                break
        except:
            pass
    
    if not sprite_set or not sprite_set.sprites:
        print(f"Failed to parse sprites from {bin_path}")
        return
    
    print(f"Found {len(sprite_set.sprites)} sprites and {len(sprite_set.texture_set.textures)} textures")
    
    # Decode base textures
    texture_images = []
    for idx, tex in enumerate(sprite_set.texture_set.textures):
        try:
            img = tex.get_base_texture_image()
            if img:
                texture_images.append(img)
                tex_name = tex.name or f"texture_{idx}"
                print(f"  Texture {idx} ({tex_name}): {img.size}")
            else:
                texture_images.append(None)
        except Exception as e:
            print(f"  Failed to decode texture {idx}: {e}")
            texture_images.append(None)
    
    # Export sprites
    exported = []
    for sprite in sprite_set.sprites:
        sprite_name = sprite.name or f"sprite_{sprite.texture_index}_{len(exported)}"
        tex_idx = sprite.texture_index
        
        if tex_idx >= len(texture_images) or texture_images[tex_idx] is None:
            print(f"  Skipping {sprite_name}: texture {tex_idx} not available")
            continue
        
        try:
            # Crop sprite from texture
            sprite_img = sprite.crop_from_texture(texture_images[tex_idx])
            if sprite_img is None:
                print(f"  Skipping {sprite_name}: failed to crop")
                continue
            
            # Save as PNG
            out_path = os.path.join(output_dir, f"{sprite_name}.png")
            sprite_img.save(out_path)
            exported.append(out_path)
            texture_name = sprite_set.texture_set.textures[tex_idx].name or f"texture_{tex_idx}"
            print(f"  Exported: {sprite_name} ({sprite_img.size}) x={int(sprite.x)},y={int(sprite.y)},w={int(sprite.width)},h={int(sprite.height)} ({texture_name})")
        except Exception as e:
            print(f"  Failed to export {sprite_name}: {e}")
    
    print(f"\nExported {len(exported)} sprites to {output_dir}")


def export_sprites_from_farc(farc_path: str, output_dir: str):
    """
    Extract sprites directly from FARC archive and export as PNG files.
    No intermediate .bin file is created.
    
    This function:
    1. Opens FARC file
    2. Decompresses BIN data in memory
    3. Parses sprites from BIN data
    4. Exports all sprites as PNG files
    
    Args:
        farc_path: Path to .farc/.FArC/.FArc file
        output_dir: Output directory for PNG files
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Step 1: Extract BIN data from FARC (in memory, no file I/O)
    bin_data = None
    
    with open(farc_path, 'rb') as f:
        # Parse FARC archive
        archive = FarcArchive()
        archive.parse(f)
        
        if not archive.entries:
            raise ValueError("No entries found in FARC archive")
        
        # Extract first entry as BIN data
        entry = archive.entries[0]
        bin_data = archive.extract_entry_data(f, entry)
        print(f"Extracted {entry.name} from FARC ({len(bin_data)} bytes)")
    
    if not bin_data:
        raise ValueError("No valid BIN file found in FARC archive")
    
    # Step 2: Parse sprites from BIN data (in memory)
    fobj = io.BytesIO(bin_data)
    
    sprite_set = None
    for little in (True, False):
        try:
            fobj.seek(0)
            r = Reader(fobj)
            r.set_endian(little)
            ss = SpriteSet()
            ss.read(r)
            if ss.sprites and ss.texture_set:
                sprite_set = ss
                break
        except:
            pass
    
    if not sprite_set or not sprite_set.sprites:
        raise ValueError("Failed to parse sprites from FARC data")
    
    print(f"Found {len(sprite_set.sprites)} sprites and {len(sprite_set.texture_set.textures)} textures")
    
    # Step 3: Decode textures
    texture_images = []
    for idx, tex in enumerate(sprite_set.texture_set.textures):
        try:
            img = tex.get_base_texture_image()
            if img:
                texture_images.append(img)
                tex_name = tex.name or f"texture_{idx}"
                print(f"  Texture {idx} ({tex_name}): {img.size}")
            else:
                texture_images.append(None)
        except Exception as e:
            print(f"  Failed to decode texture {idx}: {e}")
            texture_images.append(None)
    
    # Step 4: Export sprites
    exported = []
    for sprite in sprite_set.sprites:
        sprite_name = sprite.name or f"sprite_{sprite.texture_index}_{len(exported)}"
        tex_idx = sprite.texture_index
        
        if tex_idx >= len(texture_images) or texture_images[tex_idx] is None:
            print(f"  Skipping {sprite_name}: texture {tex_idx} not available")
            continue
        
        try:
            sprite_img = sprite.crop_from_texture(texture_images[tex_idx])
            if sprite_img is None:
                print(f"  Skipping {sprite_name}: failed to crop")
                continue
            
            out_path = os.path.join(output_dir, f"{sprite_name}.png")
            sprite_img.save(out_path)
            exported.append(out_path)
            texture_name = sprite_set.texture_set.textures[tex_idx].name or f"texture_{tex_idx}"
            print(f"  Exported: {sprite_name} ({sprite_img.size}) x={int(sprite.x)},y={int(sprite.y)},w={int(sprite.width)},h={int(sprite.height)} ({texture_name})")
        except Exception as e:
            print(f"  Failed to export {sprite_name}: {e}")
    
    print(f"\nExported {len(exported)} sprites to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description='TXP/TXD/Sprite summary and extract tool')
    sub = parser.add_subparsers(dest='command')

    p_txd = sub.add_parser('txd', help='parse texture file and dump subtextures')
    p_txd.add_argument('path')

    p_spr = sub.add_parser('spr', help='parse sprite file and print sprites')
    p_spr.add_argument('path')

    p_sum = sub.add_parser('summary', help='produce JSON summary of TXP blocks and optionally export base mips')
    p_sum.add_argument('path')
    p_sum.add_argument('--export-base-mip', action='store_true', help='export only base mip blobs')
    
    p_export = sub.add_parser('export-sprites', help='extract and save all sprites as PNG files')
    p_export.add_argument('path', help='path to .bin file with sprites')
    p_export.add_argument('-o', '--output', help='output directory (default: ./sprites_export)')
    
    p_export_farc = sub.add_parser('export-sprites-from-farc', help='extract sprites directly from FARC archive as PNG files')
    p_export_farc.add_argument('path', help='path to .farc/.FArC/.FArc file')
    p_export_farc.add_argument('-o', '--output', help='output directory (default: ./sprites_export)')
    
    p_farc = sub.add_parser('extract-farc', help='extract files from FARC archive')
    p_farc.add_argument('path', help='path to .farc file')
    p_farc.add_argument('-o', '--output', help='output directory (default: ./farc_extract)')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == 'txd':
        parse_txd(args.path)
    elif args.command == 'spr':
        parse_spr(args.path)
    elif args.command == 'export-sprites':
        export_sprites_to_png(args.path, args.output or 'sprites_export')
    elif args.command == 'export-sprites-from-farc':
        export_sprites_from_farc(args.path, args.output or 'sprites_export')
    elif args.command == 'extract-farc':
        extract_farc(args.path, args.output or 'farc_extract')
    elif args.command == 'summary':
        blocks = collect_txp_blocks(args.path)
        out = {'file': args.path, 'txp_blocks': blocks, 'sprites': []}
        # if the file itself is a sprite set, parse sprites
        # Attempt to parse SpriteSet using both endiannesses and from root
        def try_parse_sprites_file(path):
            sprites = []
            with open(path, 'rb') as f:
                data = f.read()

            # try parsing from the file root with both endian modes
            for little in (True, False):
                try:
                    fobj = io.BytesIO(data)
                    r = Reader(fobj)
                    r.set_endian(little)
                    ss = SpriteSet()
                    ss.read(r)
                    if ss.sprites:
                        for i, s in enumerate(ss.sprites):
                            sprites.append({
                                'index': i,
                                'name': s.name,
                                'texture_index': s.texture_index,
                                'x': s.x,
                                'y': s.y,
                                'width': s.width,
                                'height': s.height,
                            })
                        return sprites
                except Exception:
                    pass

            # if root parse failed, try parsing SpriteSet located at offsets near TXP blocks
            blocks_offsets = [b['offset'] for b in blocks]
            # common sprite table might be near start; also try offset 0 explicitly above
            candidate_offsets = [0] + blocks_offsets
            for off in sorted(set(candidate_offsets)):
                for little in (True, False):
                    try:
                        fobj = io.BytesIO(data)
                        r = Reader(fobj)
                        r.set_endian(little)
                        # set base to the candidate offset so ReadOffset uses BaseOffset+offset
                        r.seek(off)
                        r.push_base(off)
                        ss = SpriteSet()
                        ss.read(r)
                        if ss.sprites:
                            for i, s in enumerate(ss.sprites):
                                sprites.append({
                                    'index': i,
                                    'name': s.name,
                                    'texture_index': s.texture_index,
                                    'x': s.x,
                                    'y': s.y,
                                    'width': s.width,
                                    'height': s.height,
                                })
                            return sprites
                    except Exception:
                        pass
                    finally:
                        try:
                            r.pop_base()
                        except Exception:
                            pass

            return sprites

        try:
            sprites = try_parse_sprites_file(args.path)
            out['sprites'] = sprites
        except Exception:
            out['sprites'] = []

        # optionally export base mips
        if getattr(args, 'export_base_mip', False):
            blocks2, exported = export_base_mips(args.path, None)
            out['exported_base_mips'] = exported

        json_path = os.path.splitext(args.path)[0] + '.summary.json'
        with open(json_path, 'w', encoding='utf-8') as jf:
            json.dump(out, jf, indent=2, ensure_ascii=False)

        print('Wrote summary to', json_path)


if __name__ == '__main__':
    main()
