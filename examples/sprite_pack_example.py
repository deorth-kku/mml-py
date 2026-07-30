#!/usr/bin/env python3
"""
Example: How to build Sprite Selection FARC archives from PNG inputs.

Demonstrates using pack_sprite_selection API to create FARC files
from BG/JK/LOGO sprite images.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pack_sprite_selection import build_sprite_selection_farc
from atlas_builder import build_atlas, AtlasInfo
from txp_writer import SpriteRecord, TextureBlock, serialize_spriteset
from farc_writer import write_farc


def example_1_basic_pack():
    """Example 1: Basic FARC packing from PNG files."""
    print("=" * 60)
    print("Example 1: Basic FARC packing")
    print("=" * 60)
    
    output_path = build_sprite_selection_farc(
        bg_path='testfiles/test_bg.png',
        jk_path='testfiles/test_jk.png',
        logo_path='testfiles/test_logo.png',
        pv='6901',
        output_dir='output',
    )
    print(f"\n✓ Generated: {output_path}")
    print(f"  File size: {os.path.getsize(output_path)} bytes\n")


def example_2_with_precomputed_atlas():
    """Example 2: Using pre-computed AtlasInfo."""
    print("=" * 60)
    print("Example 2: With pre-computed AtlasInfo")
    print("=" * 60)
    
    from PIL import Image
    
    # Load images
    bg = Image.open('testfiles/test_bg.png').convert('RGBA')
    jk = Image.open('testfiles/test_jk.png').convert('RGBA')
    logo = Image.open('testfiles/test_logo.png').convert('RGBA')
    
    # Pre-compute atlas (may be useful for batch operations)
    atlas = build_atlas(bg, jk, logo, sprite_name_suffix='6901')
    print(f"  Atlas 0: {atlas.atlas_w}x{atlas.atlas_h}, payload={len(atlas.payload_0)} bytes")
    print(f"  Atlas 1: {atlas.logo_atlas_w}x{atlas.logo_atlas_h}, payload={len(atlas.payload_1)} bytes")
    
    # Use pre-computed atlas
    output_path = build_sprite_selection_farc(
        bg_path='testfiles/test_bg.png',
        jk_path='testfiles/test_jk.png',
        logo_path='testfiles/test_logo.png',
        pv='6901',
        atlas_info=atlas,
        output_dir='output',
    )
    print(f"\n✓ Generated: {output_path}\n")


def example_3_low_level_api():
    """Example 3: Low-level API for maximum control."""
    print("=" * 60)
    print("Example 3: Low-level API (maximum control)")
    print("=" * 60)
    
    from PIL import Image
    
    # Step 1: Build atlas
    bg = Image.open('testfiles/test_bg.png').convert('RGBA')
    jk = Image.open('testfiles/test_jk.png').convert('RGBA')
    logo = Image.open('testfiles/test_logo.png').convert('RGBA')
    
    atlas = build_atlas(bg, jk, logo, sprite_name_suffix='6901')
    
    # Step 2: Build sprite records
    sprites = []
    for name, placement in atlas.placement.items():
        sprites.append(SpriteRecord(
            name=name,
            texture_index=0 if name.startswith('SONG_BG') or name.startswith('SONG_JK') else 1,
            x=placement.x, y=placement.y,
            width=atlas.sprite_widths[name],
            height=atlas.sprite_heights[name],
        ))
    print(f"  Built {len(sprites)} sprite records:")
    for s in sprites:
        print(f"    - {s.name}: {s.width}x{s.height} @ ({s.x},{s.y}) on texture {s.texture_index}")
    
    # Step 3: Build texture blocks
    textures = [
        TextureBlock(
            name='MERGE_D5COMP_0',
            width=atlas.atlas_w,
            height=atlas.atlas_h,
            payload=atlas.payload_0,
        ),
        TextureBlock(
            name='MERGE_D5COMP_1',
            width=atlas.logo_atlas_w,
            height=atlas.logo_atlas_h,
            payload=atlas.payload_1,
        ),
    ]
    print(f"  Built {len(textures)} texture blocks")
    
    # Step 4: Serialize TXP
    bin_data = serialize_spriteset(sprites, textures)
    print(f"  TXP binary size: {len(bin_data)} bytes")
    
    # Step 5: Pack FArC
    farc_data = write_farc(bin_data, 'spr_sel_pv6901.bin')
    print(f"  FArC data size: {len(farc_data)} bytes")
    
    # Step 6: Write to file
    output_path = 'output/spr_sel_pv6901.farc'
    os.makedirs('output', exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(farc_data)
    print(f"\n✓ Generated: {output_path}\n")


def example_4_multiple_pv():
    """Example 4: Build FARC for multiple PV numbers."""
    print("=" * 60)
    print("Example 4: Multiple PV numbers")
    print("=" * 60)
    
    pv_numbers = ['6901', '6902', '6903']
    
    for pv in pv_numbers:
        output_path = build_sprite_selection_farc(
            bg_path='testfiles/test_bg.png',
            jk_path='testfiles/test_jk.png',
            logo_path='testfiles/test_logo.png',
            pv=pv,
            output_dir='output',
        )
        print(f"  ✓ PV {pv}: {os.path.basename(output_path)} ({os.path.getsize(output_path)} bytes)")
    
    print()


if __name__ == '__main__':
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    
    # Run examples
    example_1_basic_pack()
    example_2_with_precomputed_atlas()
    example_3_low_level_api()
    example_4_multiple_pv()
    
    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)
