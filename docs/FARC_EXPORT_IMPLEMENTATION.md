# 实现总结：FARC → PNG 直接导出

## 目标

✅ **已完成**

- [x] 实现 FARC 到 PNG 的直接导出（无中间文件）
- [x] 提供方便的 Python 函数供其他代码调用
- [x] CLI 命令支持
- [x] 示例代码和文档

## 核心实现

### 1. 新函数：`export_sprites_from_farc(farc_path, output_dir)`

**位置：** `tools/txp_parser.py` (约 200 行代码)

**功能流程：**
```
FARC 文件 (in)
    ↓
[解析 FARC 头部] → 读取条目表
    ↓
[解压 BIN 数据] → GZip 解压到内存缓冲区
    ↓
[解析 SpriteSet] → 从内存读取精灵和纹理数据
    ↓
[解码纹理] → DXT1/DXT5 → RGBA 图像
    ↓
[导出精灵] → 裁剪 + PNG 保存
    ↓
PNG 文件列表 (out)
```

**特点：**
- ✅ 完全在内存中处理，无中间文件
- ✅ 支持所有三种 FARC 格式（FARC, FArC, FArc）
- ✅ 自动检测字节序（Big-endian/Little-endian）
- ✅ 详细的进度输出

### 2. CLI 命令

```bash
python tools/txp_parser.py export-sprites-from-farc archive.farc -o output_dir/
```

**与原有命令对比：**

| 命令 | 输入 | 输出 | 中间文件 |
|------|------|------|--------|
| `extract-farc` | FARC | BIN | 否（可选输出） |
| `export-sprites` | BIN | PNG | 无 |
| `export-sprites-from-farc` | FARC | PNG | 无 ✅ |

### 3. Python API 使用

```python
from txp_parser import export_sprites_from_farc

# 简单调用
export_sprites_from_farc('archive.farc', 'output/')
```

## 测试结果

### 测试命令
```bash
.venv\Scripts\python.exe tools/txp_parser.py export-sprites-from-farc testfiles/spr_sel_pv1172.farc -o testfiles/sprites_direct
```

### 输出
```
Extracted spr_sel_pv1172.bin from FARC (2098200 bytes)
Found 3 sprites and 2 textures
  Texture 0 (MERGE_D5COMP_0): (2048, 1024)
  Texture 1 (MERGE_D5COMP_1): (1024, 512)
  Exported: SONG_BG001 ((1280, 720)) x=2,y=2,w=1280,h=720 (MERGE_D5COMP_0)
  Exported: SONG_JK001 ((500, 500)) x=1286,y=2,w=500,h=500 (MERGE_D5COMP_0)
  Exported: SONG_LOGO001 ((860, 420)) x=2,y=2,w=860,h=420 (MERGE_D5COMP_1)

Exported 3 sprites to testfiles/sprites_direct
```

### 验证
```
testfiles/sprites_direct/
├── SONG_BG001.png (1220453 bytes)
├── SONG_JK001.png (318190 bytes)
└── SONG_LOGO001.png (229383 bytes)
```

✅ 所有精灵正确导出，尺寸和坐标信息正确。

## 文件变更

### 修改的文件
- **`tools/txp_parser.py`**
  - 添加 `export_sprites_from_farc()` 函数（~200 行）
  - 添加 CLI 命令 `export-sprites-from-farc`
  - 改进 `extract_farc()` 以支持所有三种 FARC 格式

### 新建的文件
- **`examples/sprite_export_example.py`** - 使用示例
- **`docs/SPRITE_EXPORT.md`** - 使用文档和 API 参考

## 性能对比

### 方式 1：分离操作（旧）
```bash
extract-farc archive.farc -o temp/    # 生成 temp/archive.bin
export-sprites temp/archive.bin -o output/  # 读取 temp/archive.bin
```
- ⚠️ 需要生成中间 BIN 文件
- ⚠️ 额外的磁盘 I/O
- ⚠️ 需要清理临时文件

### 方式 2：直接导出（新）
```bash
export-sprites-from-farc archive.farc -o output/
```
- ✅ 无中间文件
- ✅ 所有数据在内存中处理
- ✅ 更快速更简洁

## 支持的 FARC 格式

### FARC（完整格式）
- 签名：`"FARC"`
- 包含：flags, padding, alignment, entry_padding, header_padding
- 特点：支持加密（Future Tone）和标志字段
- 状态：⚠️ 不含加密的部分支持

### FArC（老格式）
- 签名：`"FArC"`
- 包含：alignment, 条目列表
- 特点：GZip 压缩，较简洁
- 状态：✅ 完全支持

### FArc（最简格式）
- 签名：`"FArc"`
- 包含：alignment, 条目列表
- 特点：无压缩
- 状态：✅ 完全支持

## 下一步可能的改进

1. **加密支持** - 添加 AES 解密用于 Future Tone FARC 文件
2. **批处理** - 支持一次性处理多个 FARC 文件
3. **配置文件** - 支持导出选项配置（如输出格式、质量等）
4. **Web UI** - 创建简单的 Web 界面
5. **性能优化** - 多线程纹理解码

## 总结

通过实现 `export_sprites_from_farc()` 函数，我们现在可以：

1. ✅ **直接从 FARC 导出 PNG**，无需生成中间文件
2. ✅ **在 Python 代码中调用**，提供清晰的 API
3. ✅ **支持 CLI**，方便命令行使用
4. ✅ **完整的文档和示例**，易于集成

整个二进制解析工具链现在完整可用，可用于：
- 游戏资源提取和分析
- 贴图编辑和替换工作流
- 自动化资源处理流程
