# PVTMB Thumbnail Builder — Implementation Plan

Goal: a script that, given **one image + a PV id** (and a target PVTMB `.farc` path from config),
creates or updates the FArC to add/replace that PV's **thumbnail sprite**. Reuses the existing
parser/writer pipeline; changes only what SPR_SEL doesn't already cover.

Run it repeatedly: each run adds one new PV, or repaints the tile at an existing PV's slot with new art.

---

## 0. Format facts (self-contained — no re-analysis needed)

Verified against `testfiles/spr_sel_pvtmb_lavverso_song_pack.farc` and the community article
(`pvtmb.md`). Little-endian throughout unless noted.

### 0.1 FARC container
- Signature `FArC` (lowercase). Single `.bin` entry. gzip-compressed. Alignment `0x10` (16).
- `.bin` name = `.farc` name minus extension.
- Build the wrapper with the existing `farc_writer.write_farc(bin_data, entry_name)`
  (defaults: compressed=True, alignment=16). No change needed there.

### 0.2 PVTMB is RGBA8 (format 2) — NO DDS / NO texconv
- **Critical correction:** PVTMB textures are **format 2 = RGBA8 uncompressed**, so the payload
  is *raw bytes* = `Image.tobytes("RGBA")`. There is **no DDS conversion and no texconv.dll**
  (those belong to the SPR_SEL DXT5 pipeline). This is a simplification, not a dependency.
- Every texture carries a **full 12-level mip chain**, all format 2:
  `2048x1024, 1024x512, 512x256, 256x128, 128x64, 64x32, 32x16, 16x8, 8x4, 4x2, 2x1, 1x1`.
  (12 mips: width halves 2048→1, height halves 1024→1, both hit 1 at the same level.)
- Each mip payload bytes = `w*h*4`. Total per 2048x1024 texture = 11,184,812 bytes.
- The `id` field of each SubTexture == its mip index (0..11) in the source.

### 0.3 Sprite sheet / tile
- Sheet used by SEGA/lavverso: **2048x1024** per texture. **16 cols x 16 rows = 256 slots/texture.**
- Tile = **128 x 64 px** (2:1). A song's thumbnail art == its jacket art, scaled into one tile.
- Texture names: `MERGE_D5COMP_0` (index 0), `MERGE_D5COMP_1` (index 1), … new sheet = `_2`, `_3`…
- Resolution mode for every sprite = **14 (HDTV1080)**. ("Add dummy sprite" defaults to 13/HDTV720 — must override.)

### 0.3b Three verified gotchas (do not skip)
1. **Tile art is a *parallelogram*, not a full rectangle.** Each 128×64 tile has fixed transparent
   corners; the opaque art region is a horizontally-sheared parallelogram with **four straight edges**
   (top & bottom stay horizontal; left & right edges slant, shearing right going downward). When adding a
   thumbnail you must composite through this fixed parallelogram alpha-mask — `base.paste(thumb, pos, mask=FRAME_MASK)`,
   **not** fill the whole 128×64 tile.
   **Finalized corners (measured upright from `testfiles/pvtmb_extract/8227.png`, edge-fit + confirmed against the
   article's manual measurement):** top edge `y=1` x∈[28,108], bottom edge `y=61` x∈[45,127]; left edge shears
   `(28,1)→(45,61)`, right edge shears `(108,1)→(127,61)` (slope ≈ 0.28 left, ≈ 0.32 right). Full parallelogram:
   `TL=(28,1), TR=(108,1), BL=(45,61), BR=(127,61)`. See `pvtmb_tile_preview.py` (reference tool: arbitrary input
   PNG → **no warp/distortion** — inscribe this parallelogram as large as possible preserving aspect, crop it out,
   then uniform-scale to 128×64 → tile PNG with transparent corners) to visually verify the shape before finalizing
   `FRAME_MASK`. Confirmed visually (see `testfiles/pvtmb_extract/tile_preview_out.png`).
2. **DX textures are stored *upside-down* (vertically flipped).** Raw stored rows are bottom-to-top. You must
   `FLIP_TOP_BOTTOM` before viewing, measuring, or painting so coordinates match what the game shows. Any corner/
   shear numbers measured must be in this **upright** frame (the user's eye-measured `[(27,1),(107,1),(45,61),(127,61)]`
   was taken upright — confirm against code in the impl session, do not trust the eyeball value).
3. **Existing `txp_parser.decode_dxt_to_image` corrupts format-2 colors.** For fmt 2 (raw RGBA8) it does an
   unnecessary R/B channel swap (line ~365), so exported sprites come out with red/blue swapped (and
   `export_sprites_to_png` additionally applies `FLIP_TOP_BOTTOM`, line ~527). Correct decode is **raw RGBA, no
   channel swap**: `Image.frombuffer("RGBA", (W,H), raw_bytes)`. Use this for reading/painting base textures.

### 0.4 Coordinate formula (from the article, confirmed by lavverso sprite `875` → (2,2))
- `X_px = 2 + 132 * col`   (col = number of tiles to the left / "in front")
- `Y_px = 2 + 68  * row`   (row = number of tiles above   / "on top")
- `rect_begin_UV = (X/sheet_w, Y/sheet_h)`
- `rect_end_UV   = ((X+128)/sheet_w, (Y+64)/sheet_h)`
- `width_px = 128`, `height_px = 64` (always).
- Sheet dims in the UV math are the dims of the texture that tile lives on (2048x1024 here).

### 0.5 Sprite record — 40 bytes, little-endian
`struct '<I i f f f f f f f f'` →
`texture_index(uint32), reserved(uint32=0), rect_begin_x, rect_begin_y, rect_end_x, rect_end_y, x, y, width, height`
(all 8 tail fields are float32, in that order).
- **name = PV id** string, e.g. `"6916"`. (The `.PSD` folder names literally encode the X/Y to enter.)

### 0.6 BIN layout (SpriteSet root → TextureSet)
Root header (32 bytes = 8 int32):
`sig(0), textures_offset, texture_count, sprite_count, sprites_offset,
 tex_name_table_offset, sprite_name_table_offset, sprite_mode_table_offset`
All offsets are **absolute file offsets**.

Layout order (each section back-to-back):
1. Sprite records: `sprite_count × 40` bytes.
2. Texture name offset table: `texture_count × uint32` (absolute offsets into string table).
3. Sprite name offset table: `sprite_count × uint32` (absolute offsets into string table).
4. Sprite mode table: `sprite_count × 8` bytes = `(uint32=0, uint32=mode)` per sprite.
5. String table: texture names then sprite names, each **UTF-8 null-terminated**.
6. TextureSet block (see 0.7).

### 0.7 TextureSet block
Header: `sig(0x03505854), texture_count, texture_count_with_rubbish(=texture_count)`
then `texture_count × uint32` **offsets relative to the TextureSet base**.

Each texture:
- Header: `sig(V4=0x04505854 or V5), subcount(=mip_count), info=(array_size<<8)|mip_count)`
  → for PVTMB: `subcount=12, info=0x010C` (array=1, mip=12).
- Offset table: `(array_size*mip_count) × uint32` relative to texture-header start.
- Each SubTexture: `sig(0x02505854), width, height, format(2), id(=mip idx), data_size, data`.
  `data` = raw RGBA of that mip (`w*h*4` bytes).

### 0.8 Size sanity check
2 textures × 11,184,812 (mip payloads) + ~8KB (sprites/strings/tables) ≈ 22,377,588 = lavverso's
uncompressed BIN length. ✓ Use this as a round-trip assertion.

---

## 1. Existing code reuse map (exact APIs)

| Need | Reuse | Notes |
|---|---|---|
| Parse FArC container + gunzip `.bin` | `txp_parser.FarcArchive` / `_load_bin_data` | unchanged |
| Parse BIN → SpriteSet (sprites, textures w/ raw RGBA, modes) | `txp_parser.SpriteSet_from_file` | For format 2, `SubTexture.data` is raw RGBA (lossless) |
| Write FArC wrapper around BIN | `farc_writer.write_farc(bin_data, entry_name)` | default gzip + align 16 |
| Sprite-record packing (`<I i f×8`) | `txp_parser.Sprite.read` / `txp_writer` | identical for PVTMB |
| Root layout (0.6) | `txp_writer.serialize_spriteset` | **reuse the root**, but NOT its DXT5-only texture set |

**Do NOT reuse:** `pack_sprite_selection.build_sprite_selection_farc` / `atlas_builder` / texconv
— those build the SPR_SEL DXT5 atlas (BG+JK+LOGO). PVTMB is a different beast (RGBA8 mip sheets).

---

## 2. Abstraction change (writer) — additive, non-breaking

The one gap in existing code: `txp_writer` can only emit a **single DXT5 (fmt 9) subtexture per
texture**. PVTMB needs **format 2 + a multi-mip chain per texture**. Rather than refactor the
SPR_SEL path (risk), add a **new, self-contained serializer** that reuses the *proven root layout*
(0.6) and string handling, and only differs in the TextureSet block (0.7).

New API in `txp_writer.py` (keep old functions intact):

```python
class MipTexture(NamedTuple):
    name: str
    width: int          # base width  (2048)
    height: int         # base height (1024)
    format: int         # 2 (RGBA8)
    mips: list[bytes]   # [mip0, mip1, ... mip11], each w*h*4 raw RGBA

def serialize_mip_payload(width, height, format_id) -> list[bytes]:
    """Return the mip-chain payload list for a base texture (see 0.2/0.5)."""

def serialize_pvtmb_bin(sprites: list[dict], textures: list[MipTexture]) -> bytes:
    """Build a PVTMB BIN: identical SpriteSet root (0.6) + mip-chain TextureSet (0.7)."""
```

`serialize_pvtmb_bin` reuses `_encode_string`, `_align_up`, and the exact root assembly from
`serialize_spriteset` (copy the 32-byte root + 4 offset tables + string table; they are identical).
Only the TextureSet section differs (multi-subtexture, fmt 2).

Sprite record dict fields: `{name, texture_index, x, y, width, height}` — the caller fills
rect_begin/rect_end UV from the formula (0.4). Keep `SpriteRecord` for SPR_SEL as-is.

---

## 3. Image prep — trim + crop-to-ratio + scale (decisions 1&2)

`prepare_thumbnail(src, tile=(128,64)) -> PIL RGBA 128x64`:
1. `img = Image.open(src).convert("RGBA")`.
2. **Trim** surrounding fully-transparent border: `img = img.crop(img.trim())` (fallback: manual bbox).
3. **Crop to 2:1** (center) instead of adding bars:
   - ratio = w/h. If ratio > 2 → shrink height (`new_h = round(w/2)`); else if < 2 → shrink width.
   - Center-crop, never pad.
4. **Scale** to exactly `tile` with `Image.LANCZOS`.

Paint onto a base texture (RGBA, transparent bg). **Work in UPRIGHT coordinates** (flip the DX-stored
sheet once, per 0.3b-2):
- Build the fixed parallelogram FRAME_MASK (128×64, upright, per 0.3b-1).
- `base.paste(thumb, (col*128, row*64), mask=FRAME_MASK)` — alpha-composite; preserves all other tiles
  and leaves the tile's transparent corners intact. Do NOT paste with `mask=thumb` (that would fill the
  whole rectangle).
Mips regenerated from the modified base: `gen_mips(base)` halves until 1×1 (12 levels), LANCZOS.
Because the sheet is stored upside-down, apply the same `FLIP_TOP_BOTTOM` when reading the cached PNG back
into raw bytes before serializing, so the mip payloads match game orientation.

---

## 4. Caching strategy (decision 3 — avoid repeated farc↔PNG quality loss)

Keep the base texture sheets as **sidecar PNGs next to the farc**:
`<farc_stem>_tex0.png`, `<farc_stem>_tex1.png`, …  (human-inspectable; can be hand-patched too.)

Rule: **the cached base PNG is the single source of truth.** The mip chain and BIN are always
regenerated *from* the cached base, never re-decoded from the FArC. Cache PNGs are stored **upright**
(as viewed); when converting a cached PNG back to raw mip bytes for serialization, apply the DX
`FLIP_TOP_BOTTOM` (0.3b-2) so stored orientation matches the game.

Load/refresh per run:
- **Create (farc absent):** start fresh black `2048x1024` RGBA sheets; write sidecar PNGs.
- **Modify (farc present) + cache exists:** load sidecar PNG(s) → authoritative base.
- **Modify (farc present) + cache missing:** extract base once via `SpriteSet_from_file`
  (`tex.subtextures[0][0].data` → `Image.frombytes("RGBA",(2048,1024),data)`), save sidecar PNG.
  (Lossless for format 2, but we only do this once to establish the cache.)

Downstream of the cache is identical every run: paint tile(s) → gen mips → `serialize_pvtmb_bin`
→ `write_farc` → overwrite farc.

---

## 5. Flows: create / add / update (decisions 1 & 4)

Occupancy set per texture = tiles already used by existing sprites. Derive from parsed sprites:
`col = round((rect_begin_UV.x*sheet_w - 2)/132)`, `row = round((rect_begin_UV.y*sheet_h - 2)/68)`;
keep only `0<=col<16 and 0<=row<16` (this drops the origin-collapsed placeholders seen in lavverso,
which all sit at (0,0) with degenerate rects).

- **Add new PV** (`pv` not present):
  1. Row-major free-tile search: for tex in textures (in order), scan row→col; pick first
     tile not in occupancy. (Decision 1.) If a texture has no free tile, add a new `MERGE_D5COMP_k`
     sheet and use it.
  2. `col,row` → X,Y via (0.4). Paint thumbnail. Append sprite record `name=pv`.
- **Update existing PV** (pv already a sprite; decision 4):
  1. Find sprite by `name==pv`; read its `texture_index, col, row`.
  2. Overwrite that tile with the new image (same X,Y, mode 14). Do NOT add a new record.
- **Always**: mode=14 on the touched/added sprite; re-serialize and overwrite the farc (decision 3).

Idempotency: running twice for the same PV with the same image yields the same result (update path).

---

## 6. CLI (`pvtmb_add_thumbnail.py`)

```
python pvtmb_add_thumbnail.py --farc PATH/spr_sel_pvtmb_<mod>.farc \
      --pv 6916 --image jacket.png [--out PATH/farc.farc]
```
- `--farc` from config (`config.pvtmb_farc`). If it doesn't exist → **create** (new sheet + sidecar PNGs).
- `--pv` decimal (the game PV id). `--image` any image with/without alpha.
- `--out` defaults to `--farc` (overwrite in place).
- Behavior auto-selects add vs update by whether `pv` already exists.
- Print: action (create/add/update), tex index, col,row, X,Y, mode, output path.

Config (`config.py`): add `pvtmb_farc = r"<path to target spr_sel_pvtmb_*.farc>"`.

---

## 7. Validation (before declaring done)
1. Round-trip: parse the produced farc with `SpriteSet_from_file`; assert sprite count +1 (or updated),
   sprite exists with `name==pv`, mode==14, and size 128x64.
2. Size assertion ≈ 2 textures × 11,184,812 + overhead (0.8).
3. Visual: re-export the changed sheet with `export_textures_to_png` and confirm the new tile shows
   the image in the right slot and no other tile changed.
4. SPR_SEL untouched: `python pack_sprite_selection.py pack-sprite-selection …` still produces a
   farc that round-trips (guards the additive-writer change).

---

## 8. Implementation order
1. `txp_writer`: `MipTexture`, `serialize_mip_payload`, `serialize_pvtmb_bin` (additive).
2. `pvtmb_add_thumbnail.py`: `prepare_thumbnail`, `gen_mips`, occupancy + free-tile, add/update, cache load/save.
3. CLI + `config.pvtmb_farc`.
4. Write a **brand-new** farc from one image (exercises create flow + sidecar cache).
5. Re-run with the same pv + new image (exercises update flow).
6. Add a second pv (exercises add flow, row-major free tile).
7. Round-trip + size + visual checks (§7).
