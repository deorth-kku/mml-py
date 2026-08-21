# PVTMB 缩略图生成器 — 使用指南

本文档介绍新脚本 `pvtmb_add_thumbnail.py` 的功能与用法：给定**一张图片 + 一个 PV 号**，
为 PVTMB 的 `spr_sel_pvtmb_<mod>.farc` 新增或替换该 PV 的**缩略图 sprite**。

## 概述

`spr_sel_pvtmb` 里的缩略图是 format 2（RGBA8 未压缩）的 2048×1024 纹理片，每张含完整 12 级 mip，
片上 16×16 共 256 个 128×64 的平行四边形格子。本工具复用现有的解析/序列化管线，
只新增 PVTMB 所需部分，不动 SPR_SEL（DXT5 图集）的相关路径。

```
PNG 输入 (一张图) + PV 号
    │
    ▼
┌──────────────────┐
│ prepare_thumbnail │  cover 到 99x60 艺术区 → 内接平行四边形 → 斜边抗锯齿
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  paint_tile       │  alpha_composite 到底图指定格子 (mode 14 / HDTV1080)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ serialize_pvtmb_bin │  生成 12 级 mip +  SpriteSet/BIN (txp_writer)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ farc_writer       │  打包为 FArC 容器 (GZip + align 16)
└──────────────────┘
    │
    ▼
spr_sel_pvtmb_<mod>.farc
```

## 新脚本功能

- **一键增/改缩略图**：一个图片 + 一个 PV 号，自动判断是新建、新增还是覆盖。
- **三种流程自动选择**：

  | 条件 | 流程 | 行为 |
  |------|------|------|
  | farc 文件不存在 | **create** | 新建黑色 2048×1024 底图 + sidecar |
  | farc 存在，pv 不是 sprite | **add** | 行优先找空闲格子（满了自动加新底图 `MERGE_D5COMP_k`） |
  | farc 存在，pv 已是 sprite | **update** | 覆盖该 pv 已有格子，不新增记录 |

- **平行四边形艺术区 + 抗锯齿斜边**：128×64 tile 四角透明，斜边做 alpha 梯度抗锯齿。
- **底图缓存**：底图以 sidecar PNG 存在 farc 同目录（`<farc_stem>_tex{k}.png`，upright 可查看/手工修补），
  mip 与 BIN 始终从缓存底图重新生成，不直接从 farc 反解（避免反复编解码丢质量）。
- **幂等**：同一 pv + 同一图重复跑，输出字节一致。

## 前置配置

在 `config.py` 里设置目标 farc 路径：

```python
pvtmb_farc = r"testfiles\spr_sel_pvtmb_demo.farc"
```

不传 `--farc` 时自动读取该值。

## CLI 用法

```bash
# 新增 / 更新（--farc 不存在则创建，pv 不存在则新增，pv 存在则覆盖其 tile）
python pvtmb_add_thumbnail.py --farc testfiles\spr_sel_pvtmb_demo.farc ^
      --pv 7001 --image jacket.png

# 输出到别处（不覆盖原文件）
python pvtmb_add_thumbnail.py --farc path\spr_sel_pvtmb_mod.farc ^
      --pv 7001 --image jacket.png --out path\out.farc
```

| 参数 | 说明 |
|------|------|
| `--farc` | 目标 `spr_sel_pvtmb_*.farc`（默认读 `config.pvtmb_farc`） |
| `--pv` | **必须**：十进制 PV 号，也是 sprite 名字（如 `6916`） |
| `--image` | **必须**：源图片，带不带 alpha 均可 |
| `--out` | 输出 farc；默认覆盖 `--farc` |

运行后打印：`action / pv / tex_index / tile(col,row) / X,Y / mode / textures / sprites / 路径`。

## Python API

```python
import pvtmb_add_thumbnail as p

# 主入口：返回输出 farc 路径
p.run("testfiles\spr_sel_pvtmb_demo.farc", "7001", "jacket.png", "testfiles\spr_sel_pvtmb_demo.farc")

# 单 tile 预处理（与 pvtmb_tile_preview.make_tile 逐像素一致）
thumb = p.prepare_thumbnail("jacket.png")          # 128x64 RGBA，斜边已抗锯齿

# 校验用：把某个纹理原样导回 upright PNG
p.export_sheet_upright("testfiles\spr_sel_pvtmb_demo.farc", "out/", idx=0)
```

## 坐标与格子

- 公式：`X = 2 + 132·col`，`Y = 2 + 68·row`；`width/height = 128/64`。
- UV：`rect_begin_UV=(X/2048, Y/1024)`，`rect_end_UV=((X+128)/2048, (Y+64)/1024)`。
- 分辨率模式固定 **14 (HDTV1080)**（"add dummy" 默认 13，工具已覆盖）。
- 行优先找空闲格子：逐纹理 → row 0..15 → col 0..15，跳过已被占用（含原占位符）的格子。
  占位符 sprite（塌缩在 (0,0) 的 `x<2 or y<2`）不计入占用。

## 输出说明

- 生成 farc 的同时，在**同目录**写入/更新 sidecar 底图 `<farc_stem>_tex{k}.png`（upright，可直接用看图软件检查每个格子）。
- 每个 sprite 导出/显示为 128×64 平行四边形缩略图，四角透明、斜边抗锯齿。

运行示例输出：

```
action=add pv=7001 tex_index=0 tile=(col 2, row 0) X=266 Y=2 mode=14 textures=1 sprites=3
  bin=11185398 B  farc=31471 B  -> testfiles/spr_sel_pvtmb_demo.farc
  sidecars: testfiles/spr_sel_pvtmb_demo_tex0.png
```

## 示例

```bash
# 1) 新建一个空包，加入 PV 7001
python pvtmb_add_thumbnail.py --farc testfiles\spr_sel_pvtmb_new.farc ^
      --pv 7001 --image C:\Users\deort\Pictures\jk.png

# 2) 给已有包加第二个 PV（自动找下一个空闲格子）
python pvtmb_add_thumbnail.py --farc testfiles\spr_sel_pvtmb_new.farc ^
      --pv 7002 --image C:\Users\deort\Pictures\jk2.png

# 3) 用新图替换 7001 的缩略图（update）
python pvtmb_add_thumbnail.py --farc testfiles\spr_sel_pvtmb_new.farc ^
      --pv 7001 --image C:\Users\deort\Pictures\jk_new.png
```

## 注意事项

- **无 DDS / texconv 依赖**：PVTMB 是 format 2 原始 RGBA8，纯 Python 即可生成。
- **方向**：纹理存法是上下颠倒的，工具在写入前自动翻转，查看 sidecar 时已是正向。
- **不要手动改 sidecar 之外的事**：sidecar 是唯一事实源；改底图后重跑命令即可重建 farc。
- 参考工具 `pvtmb_tile_preview.py` 可用任意 PNG 预览该图的最终 tile 效果（与 builder 逐像素一致）。
