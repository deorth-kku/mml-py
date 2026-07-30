# FARC 构建指南

本文档介绍如何使用 Python API 和 CLI 工具将精灵图片打包为 FARC 归档文件。

## 概述

Sprite Selection FARC 归档文件包含三张精灵图片（BG、JK、LOGO），它们被编码为 DXT5 (BC3_UNORM) 纹理并嵌入 TXP 二进制格式，最终打包进 FArC 容器。

```
PNG 输入 (BG + JK + LOGO)
    │
    ▼
┌─────────────┐
│ atlas_builder │  构建纹理图集 + BC3_UNORM 编码 (texconv DLL)
└─────────────┘
    │
    ▼
┌─────────────┐
│  txp_writer  │  序列化 SpriteSet → TextureSet → SubTexture
└─────────────┘
    │
    ▼
┌─────────────┐
│ farc_writer  │  打包为 FArC 容器 (GZip 压缩)
└─────────────┘
    │
    ▼
spr_sel_pv6901.farc
```

## 文件结构

| 文件 | 职责 |
|------|------|
| `atlas_builder.py` | 构建纹理图集，通过 texconv.dll 编码为 DXT5 |
| `txp_writer.py` | 将精灵记录序列化为 TXP 二进制格式 |
| `farc_writer.py` | 将 TXP 数据打包进 FArC 容器 |
| `pack_sprite_selection.py` | 高层 API + CLI，组合上述三个模块 |

## Python API

### 基本用法

```python
from pack_sprite_selection import build_sprite_selection_farc

# 一行代码构建 FARC 文件
path = build_sprite_selection_farc(
    bg_path='bg.png',       # 1280x720 BG 精灵
    jk_path='jk.png',       # 502x502 JK 精灵
    logo_path='logo.png',   # LOGO 精灵 (可变尺寸)
    pv='6901',              # PV 编号 (3 或 4 位数字)
    output_dir='output',    # 输出目录 (可选，默认当前目录)
)
print(f'已生成: {path}')
# 输出: 已生成: output/spr_sel_pv6901.farc
```

### 使用预计算的 AtlasInfo

如果已经计算过图集信息，可以跳过 atlas 构建步骤：

```python
from atlas_builder import build_atlas
from pack_sprite_selection import build_sprite_selection_farc

# 预先构建 atlas
atlas = build_atlas(bg_img, jk_img, logo_img)

# 复用 atlas_info 构建 FARC
path = build_sprite_selection_farc(
    bg_path='bg.png',
    jk_path='jk.png',
    logo_path='logo.png',
    pv='6901',
    atlas_info=atlas,  # 跳过 atlas 构建
)
```

### 直接调用底层模块

```python
from atlas_builder import build_atlas, parse_dds
from txp_writer import SpriteRecord, TextureBlock, serialize_spriteset
from farc_writer import write_farc

# 1. 构建 atlas
atlas = build_atlas(bg_img, jk_img, logo_img)

# 2. 构建精灵记录
sprites = []
for name, placement in atlas.placement.items():
    sprites.append(SpriteRecord(
        name=name,
        texture_index=0 if name.startswith('SONG_BG') or name.startswith('SONG_JK') else 1,
        x=placement.x, y=placement.y,
        width=atlas.sprite_widths[name],
        height=atlas.sprite_heights[name],
    ))

# 3. 构建纹理块
textures = [
    TextureBlock(name='MERGE_D5COMP_0', width=atlas.atlas_w, height=atlas.atlas_h, payload=atlas.payload_0),
    TextureBlock(name='MERGE_D5COMP_1', width=atlas.logo_atlas_w, height=atlas.logo_atlas_h, payload=atlas.payload_1),
]

# 4. 序列化 TXP
bin_data = serialize_spriteset(sprites, textures)

# 5. 打包 FArC
farc_data = write_farc(bin_data, 'spr_sel_pv6901.bin')

# 6. 写入文件
with open('spr_sel_pv6901.farc', 'wb') as f:
    f.write(farc_data)
```

## CLI 用法

### 基本命令

```bash
python pack_sprite_selection.py pack-sprite-selection \
    --bg bg.png \
    --jk jk.png \
    --logo logo.png \
    --pv 6901 \
    -o output/
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--bg` | ✅ | BG 精灵 PNG 路径 (需 1280x720) |
| `--jk` | ✅ | JK 精灵 PNG 路径 (需 502x502) |
| `--logo` | ✅ | LOGO 精灵 PNG 路径 (可变尺寸) |
| `--pv` | ✅ | PV 编号 (3 或 4 位数字，无前导零) |
| `-o, --output-dir` | ❌ | 输出目录 (默认当前目录) |

### 批量处理

```bash
# 使用脚本批量处理多个 PV
python batch_pack.py --input-dir ./sprites/ --output-dir ./farc/
```

## texconv DLL 编码

图集编码使用 `texconv.dll` (通过 ctypes) 将 PNG 转换为 DXT5 (BC3_UNORM) DDS 纹理。

### 为什么使用 DLL 而非子进程？

- **更快**：无需启动新进程
- **更可靠**：避免子进程输出解析问题
- **无临时文件**：直接在内存中完成编码

### COM 初始化

DLL 内部的 COM 管理有 bug（第二次调用必崩），因此采用手动 COM 管理：

```python
# atlas_builder.py 内部处理
# 程序启动时调用一次 init_com()，之后所有 texconv() 调用使用 init_com=False
```

## 输出文件

生成的 FARC 文件包含：

- **FARC 签名**：`FArC` (注意大小写)
- **对齐填充**：0x10 字节对齐
- **入口元数据**：文件名、偏移、压缩大小
- **GZip 压缩数据**：TXP 二进制格式

## 与 MikuMikuLibrary 兼容

生成的 FARC 文件可与 MikuMikuLibrary 完全兼容：

- 使用 MikuMikuLibrary GUI 打开 FARC 文件
- 使用 `txp_parser.py` 解析和导出精灵
- 与其他 FARC 归档文件互换使用
