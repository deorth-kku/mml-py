r"""
Insert a new PV property block into mod_pv_db.txt and copy related files.

Usage:
    python pv_insert_refactored.py <input_pv_number> <output_pv_number>

Example:
    python pv_insert_refactored.py 892 1892
    # Extracts the pv_892 block from mdata_pv_db.txt,
    # renames it to pv_1892, and inserts it into mod_pv_db.txt
"""

import sys
import os
import re
import glob
import shutil

# ── Configuration ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import aft_mdata, mm_mod

SRC_FILE = os.path.join(aft_mdata, "rom", "mdata_pv_db.txt")
DST_FILE = os.path.join(mm_mod, "rom", "mod_pv_db.txt")


# ── Utility Functions ──────────────────────────────────────

import pykakasi

def convert_to_hiragana(text: str) -> str:
    """
    将输入的日文文本（包含汉字、片假名、平假名等）统一转换为纯平假名标音。
    """
    # 初始化 pykakasi 转换器
    kaksi = pykakasi.kakasi()
    
    # 获取分词与转换结果
    result = kaksi.convert(text)
    
    # 提取每个词转换后的平假名 (hira) 并拼接
    hiragana_text = "".join([item['hira'] for item in result])
    
    return hiragana_text

def read_pv_db(filepath: str) -> dict[str, list[str]]:
    """
    Read a PV DB file and convert it to a dict(pv_key, [lines]).

    Key = pv_xxx (extracted from the leading 'pv_xxx.field=value' line).
    Value = all lines belonging to that key (pv_xxx.field=value as-is).
    """
    result: dict[str, list[str]] = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            # auto fix reading
            k,sp,v= line.partition("=")
            if sp=="":
                continue
            if k.endswith("song_name_reading"):
                v=convert_to_hiragana(v)
                line=k+sp+v
            if line.startswith("pv_") and "." in line:
                key = line.split(".", 1)[0]
                result.setdefault(key, []).append(line)
    return result


def replace_pv(text: str, old: str, new: str) -> str:
    """Replace pv_XXX. and pv_XXX_ patterns (compatible with existing regex)."""
    return re.sub(r'pv_' + old + r'([._])', r'pv_' + new + r'\1', text)


def copy_pv_files(src_pv: str, dst_pv: str) -> None:
    """Copy ogg and dsc files for the PV from source to destination."""
    src_song_dir = os.path.join(aft_mdata, "rom", "sound", "song")
    dst_song_dir = os.path.join(mm_mod, "rom", "sound", "song")
    src_script_dir = os.path.join(aft_mdata, "rom", "script")
    dst_script_dir = os.path.join(mm_mod, "rom", "script")

    # ogg
    src_ogg = os.path.join(src_song_dir, f"pv_{src_pv}.ogg")
    dst_ogg = os.path.join(dst_song_dir, f"pv_{dst_pv}.ogg")
    if not os.path.exists(src_ogg):
        print(f"ERROR: ogg file not found: {src_ogg}")
        sys.exit(1)
    os.makedirs(os.path.dirname(dst_ogg), exist_ok=True)
    shutil.copy2(src_ogg, dst_ogg)
    print(f"  ogg: {os.path.basename(src_ogg)} -> {os.path.basename(dst_ogg)}")

    # dsc
    src_pattern = os.path.join(src_script_dir, f"pv_{src_pv}_*.dsc")
    src_dsc_files = glob.glob(src_pattern)
    src_base = os.path.join(src_script_dir, f"pv_{src_pv}.dsc")
    if os.path.exists(src_base) and src_base not in src_dsc_files:
        src_dsc_files.append(src_base)
    if not src_dsc_files:
        print(f"ERROR: No dsc files found: {src_pattern}")
        sys.exit(1)
    os.makedirs(dst_script_dir, exist_ok=True)
    for src_file in src_dsc_files:
        filename = os.path.basename(src_file)
        dst_filename = filename.replace(f"pv_{src_pv}_", f"pv_{dst_pv}_", 1)
        if dst_filename == filename:
            dst_filename = filename.replace(f"pv_{src_pv}.", f"pv_{dst_pv}.", 1)
        dst_file = os.path.join(dst_script_dir, dst_filename)
        shutil.copy2(src_file, dst_file)
        print(f"  dsc: {filename} -> {dst_filename}")


def count_dsc_files(src_pv: str) -> int:
    """Count the number of dsc files for the given PV number."""
    src_script_dir = os.path.join(aft_mdata, "rom", "script")
    count = len(glob.glob(os.path.join(src_script_dir, f"pv_{src_pv}_*.dsc")))
    if os.path.exists(os.path.join(src_script_dir, f"pv_{src_pv}.dsc")):
        count += 1
    return count


def serialize_pv_db(db: dict[str, list[str]], filepath: str) -> None:
    """Serialize a PV DB dict back to a sorted text file."""
    sorted_keys = sorted(db.keys())
    with open(filepath, "w", encoding="utf-8") as f:
        for i, key in enumerate(sorted_keys):
            for line in db[key]:
                f.write(line + "\n")
            # Blank line between blocks (not after the last one)
            if i < len(sorted_keys) - 1:
                f.write("\n")


def upgrade_farc_archive(src_pv: str, dst_pv: str) -> str:
    """Upgrade the sprite selection farc archive for the new PV."""
    from upgrade_farc import upgrade_farc as run_upgrade_farc

    src_2d_dir = os.path.join(aft_mdata, "rom", "2d")
    dst_2d_dir = os.path.join(mm_mod, "rom", "2d")
    os.makedirs(dst_2d_dir, exist_ok=True)

    src_farc = os.path.join(src_2d_dir, f"spr_sel_pv{src_pv}.farc")
    if not os.path.exists(src_farc):
        print(f"ERROR: farc file not found: {src_farc}")
        sys.exit(1)

    print(f"  Converting: {src_farc}")
    dst_farc = run_upgrade_farc(
        input_path=src_farc,
        output_dir=dst_2d_dir,
        pv=dst_pv,
    )
    print(f"  Done: {dst_farc}")
    return dst_farc


# ── Main Logic ─────────────────────────────────────────────

def insert_pv_block(src_pv: str, dst_pv: str) -> None:
    """Extract the src_pv block, rename to dst_pv, and insert into DST."""
    print(f"Source: {SRC_FILE}")
    print(f"Target: {DST_FILE}")
    print(f"Extract: pv_{src_pv}...")
    print(f"Replace: pv_{dst_pv}...")

    # 1. Read source DB and extract the source PV block
    src_db = read_pv_db(SRC_FILE)
    if "pv_" + src_pv not in src_db:
        print(f"  pv_{src_pv} block not found.")
        sys.exit(0)

    # Rename keys and lines from src_pv to dst_pv
    inserted_block = []
    for line in src_db["pv_" + src_pv]:
        inserted_block.append(replace_pv(line, src_pv, dst_pv))

    print(f"  Extracted {len(inserted_block)} lines.")

    # 2. Read destination DB and insert the renamed block
    dst_db = read_pv_db(DST_FILE)
    dst_db["pv_" + dst_pv] = inserted_block

    # 3. Serialize back to file (sorted by key)
    serialize_pv_db(dst_db, DST_FILE)
    print(f"  pv_{dst_pv} block inserted.")


def copy_pv_assets(src_pv: str, dst_pv: str) -> None:
    """Copy ogg and dsc asset files for the new PV."""
    print()
    print("--- File Copy ---")
    copy_pv_files(src_pv, dst_pv)
    dsc_count = count_dsc_files(src_pv)
    print(f"Done: copied 1 ogg + {dsc_count} dsc files.")


def do_farc_upgrade(src_pv: str, dst_pv: str) -> None:
    """Upgrade the sprite selection farc archive."""
    print()
    print("--- FARC Upgrade ---")
    upgrade_farc_archive(src_pv, dst_pv)

from auto_creat_mod_spr_db import Manager,read_farc,add_farc_to_Manager
from pathlib import Path

def do_create_db(dir:str)->None:
    SPR_DB = Manager()
    spr_path = Path(dir)
    farc_list = []
    for spr in spr_path.iterdir():
        _temp_file = Path(spr)
        if _temp_file.suffix.upper() == ".FARC":
            farc_list.append(_temp_file)
    if len(farc_list) >0:
        for farc_file in farc_list:
            farc_reader = read_farc(farc_file)
            add_farc_to_Manager(farc_reader, SPR_DB)

    outfile=dir+r"\mod_spr_db.bin"
    print()
    print(f"writing db file to {outfile}")
    SPR_DB.write_db(outfile)


# ── Entry Point ────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <input_pv_number> <output_pv_number>")
        sys.exit(1)

    src_pv = sys.argv[1].strip()   # e.g. "892"
    dst_pv = sys.argv[2].strip()   # e.g. "1892"

    if not re.match(r'^\d{3,4}$', src_pv):
        print(f"ERROR: src_pv must be exactly 3 or 4 digits: '{src_pv}'")
        sys.exit(1)
    if not re.match(r'^\d{3,4}$', dst_pv):
        print(f"ERROR: dst_pv must be exactly 3 or 4 digits: '{dst_pv}'")
        sys.exit(1)

    insert_pv_block(src_pv, dst_pv)
    copy_pv_assets(src_pv, dst_pv)
    do_farc_upgrade(src_pv, dst_pv)
    do_create_db(mm_mod+r"\rom\2d")

    print()
    print("=== All done ===")
