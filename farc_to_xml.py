#!/usr/bin/env python3
"""
读取 farc 文件并生成 XML 输出（不含 PVTMB，仅 SPR_SEL）。
ID 分配策略：从指定的起始 ID 开始，Set → Sprite → Texture 连续分配。

用法:
  python _farc_to_xml.py <2d文件夹路径> --start-id <起始ID> [--output-dir <输出目录>]
"""

import os
import sys
import struct
import gzip
import argparse
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

# 添加项目路径，确保能导入 txp_parser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from txp_parser import (
    Reader, SpriteSet, TextureSet, Texture, SubTexture,
    TXP_TEXSET_SIG, TXP_TEXTURE_SIG_V4, TXP_TEXTURE_SIG_V5,
    TXP_SUBTEXTURE_SIG, read_cstring, FarcArchive,
)


def parse_farc_bin_data(farc_path: str):
    """
    从 farc 文件中提取 BIN 数据并解析 SpriteSet。

    Returns:
        (bin_data: bytes, sprite_set: SpriteSet)
    """
    archive = FarcArchive.from_file(farc_path)

    # 找到 .bin 条目
    bin_entry = None
    for entry in archive.entries:
        if entry.name.endswith('.bin'):
            bin_entry = entry
            break

    if bin_entry is None:
        raise ValueError(f"No .bin entry found in {farc_path}")

    # 提取 BIN 数据
    with open(farc_path, 'rb') as f:
        bin_data = archive.extract_entry_data(f, bin_entry)

    # 解析 BIN 数据中的 SpriteSet
    import io
    buf = io.BytesIO(bin_data)
    r2 = Reader(buf)
    r2.base_stack = [0]

    sprite_set = SpriteSet()
    sprite_set.read(r2)

    return bin_data, sprite_set


def _extract_pv_number(farc_name: str) -> str:
    """从 farc 文件名提取 PV 编号，如 spr_sel_pv6901.farc -> 6901"""
    import re
    m = re.search(r'pv(\d+)', farc_name, re.IGNORECASE)
    return m.group(1) if m else "0000"


def generate_xml(sprite_set: SpriteSet, farc_name: str, start_id: int):
    """
    生成 XML 内容。
    ID 分配：Set → Sprites → Textures，全部连续分配。
    命名规则与 DatabaseConverter 一致：
      Set: SPR_SEL_PV{pv}
      Sprite: SPR_SEL_PV{pv}_SONG_{type}{pv}
      Texture: SPRTEX_SEL_PV{pv}_MERGE_{format}_{idx}
    """
    pv = _extract_pv_number(farc_name)
    set_name = f"SPR_SEL_PV{pv}"

    # --- 分配 ID ---
    set_id = start_id
    sprite_id = start_id + 1
    texture_id = start_id + 1 + len(sprite_set.sprites)

    # --- 构建 XML ---
    root = ET.Element("SpriteDatabase")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")

    format_el = ET.SubElement(root, "Format")
    format_el.text = "DT"

    endian_el = ET.SubElement(root, "Endianness")
    endian_el.text = "Little"

    sprite_sets = ET.SubElement(root, "SpriteSets")

    # SpriteSetInfo
    set_info = ET.SubElement(sprite_sets, "SpriteSetInfo")
    set_id_el = ET.SubElement(set_info, "Id")
    set_id_el.text = str(set_id)

    set_name_el = ET.SubElement(set_info, "Name")
    set_name_el.text = set_name

    file_name_el = ET.SubElement(set_info, "FileName")
    file_name_el.text = farc_name.replace('.farc', '.bin') if farc_name.endswith('.farc') else farc_name

    # Sprites
    sprites_el = ET.SubElement(set_info, "Sprites")
    for idx, sprite in enumerate(sprite_set.sprites):
        sprite_info = ET.SubElement(sprites_el, "SpriteInfo")

        sid_el = ET.SubElement(sprite_info, "Id")
        sid_el.text = str(sprite_id)

        # 从 farc 原始名字构建完整名字: SPR_SEL_PV{pv}_{原始名字}
        raw_name = sprite.name if sprite.name else f"SPR_{farc_name}_{idx}"
        name_el = ET.SubElement(sprite_info, "Name")
        name_el.text = f"{set_name}_{raw_name}"

        index_el = ET.SubElement(sprite_info, "Index")
        index_el.text = str(idx)

        sprite_id += 1

    # Textures
    textures_el = ET.SubElement(set_info, "Textures")
    if sprite_set.texture_set:
        for idx, tex in enumerate(sprite_set.texture_set.textures):
            tex_info = ET.SubElement(textures_el, "SpriteTextureInfo")

            tid_el = ET.SubElement(tex_info, "Id")
            tid_el.text = str(texture_id)

            # 从 farc 原始纹理名字构建: SPRTEX_SEL_PV{pv}_{原始名字}
            raw_tex_name = tex.name if tex.name else f"MERGE_D5COMP_{idx}"
            name_el = ET.SubElement(tex_info, "Name")
            name_el.text = f"SPRTEX_SEL_PV{pv}_{raw_tex_name}"

            index_el = ET.SubElement(tex_info, "Index")
            index_el.text = str(idx)

            texture_id += 1

    return root


def write_xml(root, output_path: str, pretty: bool = True):
    """将 ElementTree root 写入 XML 文件。"""
    rough = ET.tostring(root, encoding='unicode')
    if pretty:
        dom = minidom.parseString(rough)
        pretty_xml = dom.toprettyxml(indent="  ", encoding='utf-8')
        # minidom adds <?xml version="1.0" ?> as first line, keep it
        with open(output_path, 'wb') as f:
            f.write(pretty_xml)
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(rough)


def main():
    parser = argparse.ArgumentParser(
        description="读取 farc 文件并生成 XML（仅 SPR_SEL，不含 PVTMB）"
    )
    parser.add_argument(
        "folder",
        help="包含 spr_sel_pv*.farc 文件的 2d 文件夹路径"
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=60000,
        help="起始 ID（默认 60000）"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="XML 输出目录（默认与 farc 同目录）"
    )
    parser.add_argument(
        "--farc-name",
        default=None,
        help="指定单个 farc 文件名（不含路径），用于调试"
    )
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"错误: 文件夹不存在: {folder}")
        sys.exit(1)

    # 查找所有 spr_sel_pv*.farc 文件
    farc_files = sorted(folder.glob("spr_sel_pv*.farc"))

    if not farc_files:
        print(f"在 {folder} 中未找到 spr_sel_pv*.farc 文件")
        sys.exit(1)

    print(f"找到 {len(farc_files)} 个 farc 文件:\n")
    for i, f in enumerate(farc_files, 1):
        print(f"  {i}. {f.name}")
    print()

    current_id = args.start_id

    for farc_path in farc_files:
        farc_name = farc_path.name

        # 如果指定了 --farc-name，只处理匹配的文件
        if args.farc_name and farc_name != args.farc_name:
            continue

        print(f"处理: {farc_name} (起始 ID: {current_id})")

        try:
            # 解析 farc
            bin_data, sprite_set = parse_farc_bin_data(str(farc_path))

            # 生成 XML
            root = generate_xml(sprite_set, farc_name, current_id)

            # 确定输出路径
            if args.output_dir:
                out_dir = Path(args.output_dir)
            else:
                out_dir = farc_path.parent

            out_dir.mkdir(parents=True, exist_ok=True)
            xml_name = farc_name.replace('.farc', '.xml')
            xml_path = out_dir / xml_name

            write_xml(root, str(xml_path))

            # 计算使用的 ID 范围
            num_sprites = len(sprite_set.sprites)
            num_textures = len(sprite_set.texture_set.textures) if sprite_set.texture_set else 0
            used_ids = 1 + num_sprites + num_textures
            next_id = current_id + used_ids

            print(f"  → 写入: {xml_path}")
            print(f"  → Set ID: {current_id}, Sprites: {current_id+1}~{current_id+num_sprites}, "
                  f"Textures: {current_id+1+num_sprites}~{current_id+num_sprites+num_textures}")
            print(f"  → 下一个起始 ID: {next_id}\n")

            current_id = next_id

        except Exception as e:
            print(f"  错误: {e}\n")


if __name__ == "__main__":
    main()
