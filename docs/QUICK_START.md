# 快速参考 - 精灵导出工具

## 最常用的命令

### 1️⃣ FARC → PNG 直接导出（推荐）
```bash
python txp_parser.py export-sprites archive.farc -o sprites/
```

### 2️⃣ FARC 解包到 BIN
```bash
python txp_parser.py extract-farc archive.farc -o temp/
```

### 3️⃣ BIN → PNG（已有 BIN 文件）
```bash
python txp_parser.py export-sprites archive.bin -o sprites/
```

---

## Python API 调用

```python
from txp_parser import export_sprites_to_png

# 一行代码，搞定一切
export_sprites_to_png('archive.farc', 'output_sprites/')
```

---

## 支持的格式

| 格式 | 文件签名 | 压缩 | 支持 |
|------|---------|------|------|
| FARC | "FARC" | 可选 | ✅ 非加密 |
| FArC | "FArC" | GZip | ✅ |
| FArc | "FArc" | 无 | ✅ |

---

## 输出说明

每个精灵导出为一个 PNG 文件，带有完整的 Alpha 通道（透明度）。

### 日志格式示例
```
Exported: SONG_BG001 ((1280, 720)) x=2,y=2,w=1280,h=720 (MERGE_D5COMP_0)
         ①名称          ②尺寸        ③坐标信息          ④纹理来源
```

---

## 常见场景

### 场景 1：快速导出游戏精灵
```bash
cd MikuMikuLibrary-master
.venv\Scripts\python.exe txp_parser.py export-sprites "game_data/sprites.farc" -o "extracted_sprites/"
```

### 场景 2：在 Python 脚本中批量处理
```python
from txp_parser import export_sprites_to_png

for farc_file in Path('.').glob('*.farc'):
    output = f'sprites/{farc_file.stem}'
    export_sprites_to_png(str(farc_file), output)
```

### 场景 3：集成到现有工具
```python
# 在你的工具中导入使用
import sys
sys.path.insert(0, '.')
from txp_parser import export_sprites_to_png

export_sprites_to_png(input_file, output_dir)
```

---

## 故障排除

### 问题：FARC 文件无法识别
```
ValueError: Invalid FARC signature
```
**原因：** 文件不是 FARC/FArC/FArc 格式
**解决：** 检查文件类型和扩展名

### 问题：精灵导出失败
```
ValueError: Failed to parse sprites from FARC data
```
**原因：** FARC 内部数据无法解析
**解决：** 确保 FARC 文件完整且未损坏

### 问题：纹理显示为黑色
**原因：** 字节序检测失败
**解决：** 自动处理，应该不会发生（如有请报告）

---

## 性能提示

- 🚀 **直接导出模式**（export-sprites）最快
- 💾 **内存用量**：约为原始 BIN 文件大小 + 纹理缓冲区
- ⏱️ **耗时**：主要取决于纹理解码和 PNG 压缩

## 更多帮助

```bash
# 查看所有命令
python txp_parser.py -h

# 查看特定命令帮助
python txp_parser.py export-sprites -h
```

## 相关文件

- 📖 详细文档：[docs/SPRITE_EXPORT.md](docs/SPRITE_EXPORT.md)
- 📝 示例代码：[examples/sprite_export_example.py](examples/sprite_export_example.py)
- 🔧 工具源码：[txp_parser.py](txp_parser.py)
