#!/usr/bin/env python3
"""
Example: How to use the sprite export functions from other Python code.

This demonstrates calling the txp_parser module functions to export sprites
from FARC archives or BIN files programmatically.
"""

import sys
import os

# Add the tools directory to the path so we can import txp_parser
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from txp_parser import export_sprites_to_png


def example_1_farc_direct():
    """Example 1: Export sprites directly from FARC file (no intermediate BIN)."""
    print("=" * 60)
    print("Example 1: Direct FARC → PNG (no intermediate file)")
    print("=" * 60)
    
    farc_path = "testfiles/spr_sel_pv1172.farc"
    output_dir = "output/sprites_from_farc"
    
    # This is the main function you'd use
    export_sprites_to_png(farc_path, output_dir)
    
    print(f"\n✓ Sprites saved to {output_dir}\n")


def example_2_bin_file():
    """Example 2: Export sprites from an already-extracted BIN file."""
    print("=" * 60)
    print("Example 2: BIN file → PNG (if you already have .bin)")
    print("=" * 60)
    
    bin_path = "testfiles/spr_sel_pv1172.bin"
    output_dir = "output/sprites_from_bin"
    
    # Use this if you already have the .bin file extracted
    export_sprites_to_png(bin_path, output_dir)
    
    print(f"\n✓ Sprites saved to {output_dir}\n")


def example_3_batch_farc():
    """Example 3: Process multiple FARC files in batch."""
    print("=" * 60)
    print("Example 3: Batch process multiple FARC files")
    print("=" * 60)
    
    # List of FARC files to process
    farc_files = [
        "testfiles/spr_sel_pv1172.farc",
        # "testfiles/other_archive.farc",
        # "testfiles/another_archive.FArC",
    ]
    
    for farc_path in farc_files:
        if not os.path.exists(farc_path):
            print(f"⚠ File not found: {farc_path}")
            continue
        
        # Create output directory based on filename
        base_name = os.path.splitext(os.path.basename(farc_path))[0]
        output_dir = f"output/sprites_{base_name}"
        
        try:
            print(f"\nProcessing: {farc_path}")
            export_sprites_to_png(farc_path, output_dir)
        except Exception as e:
            print(f"✗ Error processing {farc_path}: {e}")
    
    print("\n✓ Batch processing complete\n")


if __name__ == '__main__':
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    
    # Run examples
    example_1_farc_direct()
    
    # Uncomment to run other examples:
    # example_2_bin_file()
    # example_3_batch_farc()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)
