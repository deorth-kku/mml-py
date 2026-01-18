# 精灵导出工具 (Sprite Export Tools)

## 功能概述

`txp_parser.py` 现在支持直接从 FARC 档案导出精灵为 PNG，无需生成中间 BIN 文件。

## 快速开始

### 方式 1：直接从 FARC 导出精灵（推荐）

```bash
python tools/txp_parser.py export-sprites-from-farc archive.farc -o output_sprites/
```

**特点：**
- ✅ 一条命令完成：FARC → 解压 → 解析 → PNG
- ✅ 无需生成中间文件
- ✅ 内存中处理所有数据
- ✅ 支持所有 FARC 格式：FARC, FArC, FArc

**输出：** 每个精灵保存为一个 PNG 文件，带有完整的透明度信息

### 方式 2：分离 FARC 解包和精灵导出

```bash
# 步骤 1: 解包 FARC 文件
python tools/txp_parser.py extract-farc archive.farc -o extracted/

# 步骤 2: 从 BIN 文件导出精灵
python tools/txp_parser.py export-sprites extracted/archive.bin -o output_sprites/
```

## 在 Python 代码中使用

### 方式 1：直接导出（推荐）

```python
from txp_parser import export_sprites_from_farc

# 从 FARC 档案直接导出精灵
export_sprites_from_farc('archive.farc', 'output_sprites/')
```

### 方式 2：从 BIN 文件导出

```python
from txp_parser import export_sprites_to_png

# 如果已有 BIN 文件，可以直接导出
export_sprites_to_png('archive.bin', 'output_sprites/')
```

### 方式 3：低级别 API（高级用法）

```python
from txp_parser import SpriteSet, Reader
import io

# 手动解析 FARC 并处理精灵
with open('archive.farc', 'rb') as f:
    # ... FARC 解包逻辑 ...
    bin_data = gzip.decompress(compressed_data)
    
# 解析 BIN 数据
fobj = io.BytesIO(bin_data)
r = Reader(fobj)
r.set_endian(True)  # 或 False，取决于字节序

sprite_set = SpriteSet()
sprite_set.read(r)

# 访问精灵数据
for sprite in sprite_set.sprites:
    print(f"Sprite: {sprite.name}")
    print(f"  Position: ({sprite.x}, {sprite.y})")
    print(f"  Size: {sprite.width}x{sprite.height}")
    print(f"  Texture index: {sprite.texture_index}")
```

## 支持的格式

### FARC 档案格式

| 格式 | 签名 | 特点 | 支持状态 |
|------|------|------|--------|
| FARC | "FARC" | 完整格式，带标志和可选加密 | ✅ 支持（不含加密） |
| FArC | "FArC" | 老格式，GZip 压缩 | ✅ 完全支持 |
| FArc | "FArc" | 最简格式，无压缩 | ✅ 完全支持 |

### DXT 纹理格式

| 格式 | 说明 | 支持状态 |
|------|------|--------|
| DXT1 (BC1) | 无透明度压缩纹理 | ✅ 支持 |
| DXT5 (BC3) | 有透明度压缩纹理 | ✅ 支持 |
| 其他 | PNG、8位等 | ✅ 支持 |

## 输出文件格式

导出的 PNG 文件包含：

- **文件名：** `{精灵名称}.png`
- **格式：** PNG (RGBA)
- **颜色空间：** SRGB
- **透明度：** 完全支持 Alpha 通道
- **坐标信息：** 保存在导出日志中

### 导出日志示例

```
Exported: SONG_BG001 ((1280, 720)) x=2,y=2,w=1280,h=720 (MERGE_D5COMP_0)
Exported: SONG_JK001 ((500, 500)) x=1286,y=2,w=500,h=500 (MERGE_D5COMP_0)
Exported: SONG_LOGO001 ((860, 420)) x=2,y=2,w=860,h=420 (MERGE_D5COMP_1)
```

说明：
- `((1280, 720))` - 导出图片的像素尺寸
- `x=2,y=2,w=1280,h=720` - 精灵在原始纹理中的坐标和大小
- `(MERGE_D5COMP_0)` - 来源纹理名称

## API 文档

### `export_sprites_from_farc(farc_path, output_dir)`

从 FARC 档案直接导出所有精灵为 PNG 文件。

**参数：**
- `farc_path` (str): FARC 档案的路径（支持 .farc, .FArC, .FArc）
- `output_dir` (str): 输出目录

**异常：**
- `ValueError`: 无效的 FARC 文件或无法解析精灵
- `NotImplementedError`: 加密 FARC 文件不支持

**返回值：** 无（文件直接写入到 output_dir）

### `export_sprites_to_png(bin_path, output_dir)`

从 BIN 文件导出所有精灵为 PNG 文件。

**参数：**
- `bin_path` (str): BIN 文件的路径
- `output_dir` (str): 输出目录

**返回值：** 无（文件直接写入到 output_dir）

### `extract_farc(farc_path, output_dir)`

解包 FARC 档案到指定目录。

**参数：**
- `farc_path` (str): FARC 档案的路径
- `output_dir` (str): 输出目录

**返回值：** 无（文件直接写入到 output_dir）

## 常见问题

### Q: 为什么要直接从 FARC 导出而不是先解包？

**A:** 
- 更快：避免磁盘 I/O，所有数据在内存中处理
- 更简洁：一条命令完成整个流程
- 更清洁：不会留下中间文件

### Q: 支持加密的 FARC 文件吗？

**A:** 目前不支持。加密文件需要额外的密钥和解密逻辑（Future Tone 格式）。

### Q: 导出的 PNG 有 Alpha 通道吗？

**A:** 是的。所有导出的 PNG 都是 RGBA 格式，完全保留透明度信息。

### Q: 可以自定义输出图片的格式吗？

**A:** 目前只支持 PNG。如需其他格式，可修改 `sprite.crop_from_texture()` 后的保存逻辑。

## 示例代码

查看 `examples/sprite_export_example.py` 了解更多使用示例。

```bash
python examples/sprite_export_example.py
```

## 技术细节

### 处理流程

```
FARC 档案
  ↓
[读取头部] → 获取条目列表
  ↓
[对每个条目]
  ├─ 读取压缩数据
  ├─ GZip 解压（如果需要）
  └─ 提取为内存缓冲区
  ↓
[解析 BIN 数据]
  ├─ 识别字节序（Big-endian 或 Little-endian）
  ├─ 读取 SpriteSet 结构
  ├─ 读取 TextureSet 和所有 Texture
  └─ 读取 Sprite 数组
  ↓
[解码纹理]
  ├─ 对每个 Texture 读取 SubTexture（Mipmap）
  ├─ 使用 texture2ddecoder 库解码 DXT1/DXT5
  └─ 垂直翻转图像（DXT 输出是倒立的）
  ↓
[导出精灵]
  ├─ 对每个 Sprite
  ├─ 从纹理中裁剪（使用 x, y, width, height）
  └─ 保存为 PNG 文件
```

### 关键库

- `texture2ddecoder`: DXT 纹理解压缩
- `PIL/Pillow`: 图像处理和 PNG 保存
- `numpy`: 数组操作
- `gzip`: 数据解压缩

## 许可证

此工具是 MikuMikuLibrary 的 Python 移植版本。
