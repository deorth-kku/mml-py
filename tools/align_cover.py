#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把翻唱(cover)对齐到原唱(original)：时间偏移 + 音量匹配。

原理
----
1. 时间对齐（粗到细互相关）
   - 粗搜：两者降采样到 8 kHz 做全长度互相关，找峰值 → 粗偏移
   - 细搜：从原唱取多个 3 秒窗口与翻唱互相关，在粗偏移 ±1 秒范围内
     搜索 → 样本级精度的偏移
   - 前提：两者使用同一伴奏轨（音乐部分高度相关，人声差异不影响）
2. 音量匹配
   - global  ：单一增益 = RMS(原唱) / RMS(翻唱)
   - dynamic ：1 秒帧 RMS 增益，移动平均平滑后插值到逐样本增益，
               保留动态（响的部分跟着变响，轻的部分跟着变轻）
3. 峰值保护：tanh 软削峰，防止削波
4. 声道处理：4ch 游戏源（(L+R)×(伴奏+人声)）先混成立体声
   （L=ch0+ch2，R=ch1+ch3，直接叠加不减半），保证响度与游戏内播放一致

用法
----
    python tools/align_cover.py original.wav cover.wav -o cover_aligned.wav
    python tools/align_cover.py original.wav cover.wav -o out.wav --mode dynamic
    python tools/align_cover.py --selftest

依赖：numpy scipy soundfile
注意：mp3 等压缩格式需先转成 wav（ffmpeg -i in.mp3 out.wav）
"""
from __future__ import annotations

import argparse

import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve, resample_poly


# ---------------------------------------------------------------------------
# 读取 / 基础工具
# ---------------------------------------------------------------------------

def load_audio(path: str, sr: int) -> np.ndarray:
    """读取音频文件并重采样到目标采样率，返回 (n, ch) 数组。

    注意：sf.read(always_2d=True) 返回的已经是 (frames, channels)，勿转置。
    """
    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    y = data.astype(np.float64)
    if file_sr != sr:
        g = np.gcd(file_sr, sr)
        y = resample_poly(y, sr // g, file_sr // g, axis=0)
    return y


def to_mono(y: np.ndarray) -> np.ndarray:
    """多声道取均值混成单声道（1D 输入原样返回）。"""
    return y.mean(axis=1) if y.ndim > 1 else y


def mix_to_stereo(y: np.ndarray) -> np.ndarray:
    """混成立体声。

    2ch：原样；4ch 游戏源（(L+R)×(伴奏+人声) 布局）：
    L = ch0 + ch2，R = ch1 + ch3（直接叠加不减半，与游戏内播放一致）。
    其它声道数：均值混到双声道。
    """
    if y.ndim == 1:
        return y
    ch = y.shape[1]
    if ch == 2:
        return y
    if ch == 4:
        return np.stack([y[:, 0] + y[:, 2], y[:, 1] + y[:, 3]], axis=1)
    m = y.mean(axis=1)
    return np.stack([m, m], axis=1)


def rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(y)))) if len(y) else 0.0


def db(x: float) -> float:
    return 20.0 * np.log10(max(x, 1e-9))


def trim_silence(y: np.ndarray, threshold_db: float = -40.0) -> np.ndarray:
    """裁掉首尾静音（阈值相对峰值，按单声道混合判断）。"""
    m = to_mono(y)
    peak = float(np.max(np.abs(m))) if len(m) else 0.0
    if peak <= 0:
        return y
    thresh = peak * 10.0 ** (threshold_db / 20.0)
    idx = np.nonzero(np.abs(m) > thresh)[0]
    if len(idx) == 0:
        return y
    return y[idx[0] : idx[-1] + 1]


def leading_silence_samples(y: np.ndarray, threshold_db: float = -40.0) -> int:
    """返回前导静音的样本数（按单声道混合判断）。"""
    m = to_mono(y)
    peak = float(np.max(np.abs(m))) if len(m) else 0.0
    if peak <= 0:
        return len(y)
    thresh = peak * 10.0 ** (threshold_db / 20.0)
    idx = np.nonzero(np.abs(m) > thresh)[0]
    if len(idx) == 0:
        return len(y)
    return int(idx[0])


def _normalize(y: np.ndarray) -> np.ndarray:
    r = rms(y)
    return y / r if r > 0 else y


# ---------------------------------------------------------------------------
# 偏移估计
# ---------------------------------------------------------------------------

def estimate_offset(orig: np.ndarray, cover: np.ndarray, sr: int,
                    coarse_sr: int = 8000, window_s: float = 3.0,
                    margin_s: float = 1.0) -> float:
    """估计原唱与翻唱的时间偏移。

    返回偏移量（样本）：
      d > 0 → 翻唱比原唱晚 d 个样本（需裁掉翻唱开头 d 个样本）
      d < 0 → 翻唱比原唱早（需在翻唱开头补 |d| 个样本静音）
    """
    orig = to_mono(orig)
    cover = to_mono(cover)
    # ---- 粗搜：降采样后全长度互相关
    # 约定：corr[n] = sum_k a[k]*b[k+lag]，其中 lag = len(b)-1-n
    g = np.gcd(coarse_sr, sr)
    oc = _normalize(resample_poly(orig, coarse_sr // g, sr // g))
    cc = _normalize(resample_poly(cover, coarse_sr // g, sr // g))
    corr = fftconvolve(oc, cc[::-1], mode="full")
    d_coarse = (len(cc) - 1) - int(np.argmax(corr))     # 粗采样率下的样本数
    d_coarse_s = d_coarse / coarse_sr

    # ---- 细搜：在粗偏移 ±margin_s 范围内做样本级精度搜索
    # 窗口 w 从原唱 start 处截取；正确对齐时 w 匹配翻唱中 start+d 处内容，
    # 故相关峰值位于 lag = d + start，真实偏移 d = lag_peak - start
    c = _normalize(cover)
    win_n = int(window_s * sr)
    d_center = int(round(d_coarse_s * sr))
    margin = int(margin_s * sr)
    best_score, best_d = -np.inf, d_center
    for frac in (0.3, 0.5, 0.7):
        mid = int(len(orig) * frac)
        start = max(0, mid - win_n // 2)
        w = orig[start : start + win_n]
        if len(w) < win_n // 2:
            continue
        w = _normalize(w)
        corr = fftconvolve(w, c[::-1], mode="full")
        lo = max(d_center - margin, -(len(w) - 1) - start)
        hi = min(d_center + margin, len(c) - 1 - start)
        if hi < lo:
            continue
        ds = np.arange(lo, hi + 1)
        lags = ds + start
        vals = corr[(len(c) - 1) - lags]
        j = int(np.argmax(vals))
        if vals[j] > best_score:
            best_score, best_d = float(vals[j]), int(ds[j])
    return float(best_d)


def shift_signal(y: np.ndarray, d: float) -> np.ndarray:
    """把信号移动 d 个样本（d>0 裁掉开头，d<0 开头补静音），支持小数样本。"""
    n = len(y)
    src = np.arange(n) - d
    if y.ndim == 1:
        out = np.interp(src, np.arange(n), y)
    else:
        out = np.empty_like(y)
        for ch in range(y.shape[1]):
            out[:, ch] = np.interp(src, np.arange(n), y[:, ch])
    out[(src < 0) | (src >= n)] = 0.0
    return out


# ---------------------------------------------------------------------------
# 音量匹配
# ---------------------------------------------------------------------------

def match_level_global(orig: np.ndarray, cover: np.ndarray):
    """全局单一增益匹配（按单声道混合计算，应用到所有声道）。返回 (新信号, 增益)。"""
    g = rms(to_mono(orig)) / max(rms(to_mono(cover)), 1e-9)
    return cover * g, float(g)


def match_level_dynamic(orig: np.ndarray, cover: np.ndarray, sr: int,
                        frame_s: float = 1.0, hop_s: float = 0.1,
                        smooth_s: float = 1.0):
    """帧级 RMS 增益匹配（要求两者已对齐、同一时间轴）。

    返回 (新信号, 逐样本增益数组)。
    """
    o = to_mono(orig)
    c = to_mono(cover)
    n = len(o)
    frame = int(frame_s * sr)
    hop = int(hop_s * sr)
    if n < frame:
        g = rms(o) / max(rms(c), 1e-9)
        return cover * g, float(g)

    nfr = (n - frame) // hop + 1
    centers = np.arange(nfr) * hop + frame / 2.0

    def frame_rms(y: np.ndarray) -> np.ndarray:
        c = np.concatenate([[0.0], np.cumsum(np.square(y))])
        e = c[hop * np.arange(nfr) + frame] - c[hop * np.arange(nfr)]
        return np.sqrt(np.maximum(e, 0.0) / frame)

    gain = frame_rms(o) / np.maximum(frame_rms(c), 1e-9)
    k = int(round(smooth_s / hop_s))
    if k % 2 == 0:
        k += 1
    half = k // 2
    gain = np.convolve(np.pad(gain, half, mode="edge"),
                       np.ones(k) / k, mode="valid")
    gsamp = np.interp(np.arange(n), centers, gain)
    if cover.ndim > 1:
        gsamp = gsamp[:, None]
    return cover * gsamp, gsamp


def soft_clip(y: np.ndarray, limit: float = 0.995):
    """tanh 软削峰。返回 (新信号, 是否发生削峰)。"""
    if len(y) and np.max(np.abs(y)) > limit:
        return limit * np.tanh(y / limit), True
    return y, False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _ffmpeg_available() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None


def _ffmpeg_encode(cover_path: str, cover_sr: int, d_abs: float,
                   n_orig: int, sr: int, gain: float,
                   limit: float, out_path: str) -> None:
    """让 ffmpeg 直接对翻唱源按绝对偏移裁剪/补零、加增益、重采样到 sr 并编码 OGG。

    d_abs / n_orig 均为 sr 域；内部换算到输入采样率域（样本级精度）。
    """
    import subprocess
    scale = cover_sr / sr
    D = int(round(d_abs * scale))     # 输入采样率域下的偏移（样本）
    N = int(round(n_orig * scale))    # 输出长度（输入采样率域，样本）
    ch = sf.info(cover_path).channels
    if D >= 0:
        # 裁掉开头 D 个样本（样本级精度），尾部补零到总长 D+N
        shift_f = f"atrim=start_sample={D}:end_sample={D + N},apad=whole_len={D + N}"
    else:
        # 开头补 |D| 个样本静音（样本级精度）
        P = -D
        exprs = ":".join(f"c{i}='if(lt(n,{P}),0,src(n-{P}))'" for i in range(ch))
        shift_f = f"aeval={exprs},atrim=end_sample={N},apad=whole_len={N}"
    af = f"{shift_f},volume={gain:.6f},alimiter=limit={limit}"
    cmd = ["ffmpeg", "-y", "-i", cover_path, "-af", af,
           "-ar", str(sr), "-c:a", "libvorbis", "-q:a", "0", out_path]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"ffmpeg 失败:\n{err}")


def align(orig_path: str, cover_path: str, out_path: str,
          sr: int | None = None, mode: str = "global",
          trim: bool = True, limit: float = 0.995) -> None:
    if sr is None:
        sr = sf.info(orig_path).samplerate   # 默认匹配原唱采样率
    # 4ch 游戏源先混成立体声（直接叠加不减半），保证响度与游戏内播放一致
    orig_full = mix_to_stereo(load_audio(orig_path, sr))
    cover_full = mix_to_stereo(load_audio(cover_path, sr))
    n_orig = len(orig_full)

    if trim:
        L_o = leading_silence_samples(orig_full)
        L_c = leading_silence_samples(cover_full)
        orig = trim_silence(orig_full)
        cover = trim_silence(cover_full)
    else:
        L_o = L_c = 0
        orig, cover = orig_full, cover_full

    # 1) 偏移：裁剪域估计，再换算为两个输入文件的绝对偏移
    #    d_abs = d_trim + L_c - L_o（>0 表示翻唱整体晚于原唱）
    d_trim = estimate_offset(orig, cover, sr)
    d_abs = d_trim + L_c - L_o

    # 2) 音量匹配（裁剪域，对齐后的翻唱）
    aligned = shift_signal(cover, -d_trim)
    n = len(orig)
    if len(aligned) < n:
        pad = np.zeros((n - len(aligned), aligned.shape[1]))
        aligned = np.concatenate([aligned, pad])
    else:
        aligned = aligned[:n]
    if mode == "global":
        aligned, info = match_level_global(orig, aligned)
    else:
        aligned, info = match_level_dynamic(orig, aligned, sr)

    # 3) 输出：放在原唱文件的绝对时间轴上（长度 = 原唱完整时长）
    use_ffmpeg = (mode == "global"
                  and out_path.lower().endswith((".ogg", ".oga"))
                  and _ffmpeg_available())
    if use_ffmpeg:
        cover_sr = sf.info(cover_path).samplerate
        _ffmpeg_encode(cover_path, cover_sr, d_abs, n_orig, sr,
                       float(info), limit, out_path)
        out, clipped = None, False
    else:
        out = np.zeros((n_orig, cover_full.shape[1]))
        out[L_o : L_o + n] = aligned
        out, clipped = soft_clip(out, limit)
        sf.write(out_path, out.astype(np.float32), sr)

    # 报告
    print(f"采样率     : {sr} Hz（匹配原唱）")
    ch_out = out.shape[1] if out is not None else cover_full.shape[1]
    print(f"声道       : 原唱 {orig_full.shape[1]} → 输出 {ch_out}")
    print(f"原唱时长   : {n_orig / sr:.2f} s（前导静音 {L_o / sr:.2f} s）")
    print(f"翻唱时长   : {len(cover_full) / sr:.2f} s（前导静音 {L_c / sr:.2f} s）")
    print(f"裁剪偏移   : {d_trim / sr:+.3f} s")
    print(f"绝对偏移   : {d_abs / sr:+.3f} s（翻唱{'晚' if d_abs > 0 else '早'}于原唱，{d_abs:+.0f} 样本）")
    if mode == "global":
        print(f"增益       : {db(float(info)):+.2f} dB")
    else:
        info_arr = np.asarray(info)
        print(f"增益范围   : {db(float(np.min(info_arr))):+.2f} ~ {db(float(np.max(info_arr))):+.2f} dB")
    print(f"RMS 原唱   : {db(rms(to_mono(orig_full))):.2f} dBFS（单声道混合，含前导静音）")
    if out is not None:
        print(f"RMS 对齐后 : {db(rms(to_mono(out))):.2f} dBFS（单声道混合）")
        print(f"峰值 对齐后 : {db(float(np.max(np.abs(out)))):.2f} dBFS"
              + ("（已软削峰）" if clipped else ""))
    print(f"输出       : {out_path}"
          + ("（ffmpeg 直编）" if use_ffmpeg else ""))


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------

def selftest() -> None:
    sr = 44100
    dur = 10.0
    n = int(dur * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(42)
    # 带限噪声（移动平均低通）——非周期，模拟真实音乐的瞬态/宽带成分
    noise = rng.standard_normal(n)
    k = 101
    noise = np.convolve(noise, np.ones(k) / k, mode="same")
    # 缓慢非周期的动态包络（响度起伏）
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 0.13 * t + 1.0) * np.sin(2 * np.pi * 0.07 * t)
    env = np.clip(env, 0.05, None)
    y = noise * env
    y /= np.max(np.abs(y))

    d_true_s = 1.73
    d_true = int(d_true_s * sr)
    rng = np.random.default_rng(42)
    cover = np.zeros(d_true + len(y))
    cover[d_true:] = 0.4 * y
    cover += rng.normal(0.0, 1e-4, cover.size)

    d = estimate_offset(y, cover, sr)
    print(f"真实偏移   : {d_true_s:.3f} s")
    print(f"估计偏移   : {d / sr:.6f} s（误差 {abs(d - d_true):.1f} 样本）")

    aligned = shift_signal(cover, -d)
    if len(aligned) < len(y):
        aligned = np.concatenate([aligned, np.zeros(len(y) - len(aligned))])
    else:
        aligned = aligned[: len(y)]
    aligned, g = match_level_global(y, aligned)
    ratio = rms(aligned) / rms(y)
    err = float(np.max(np.abs(aligned - y)))
    print(f"增益       : {db(float(g)):+.2f} dB")
    print(f"RMS 比值   : {ratio:.4f}（目标 1.0000）")
    print(f"最大样本误差: {err:.5f}")

    assert abs(d - d_true) <= 2, "偏移误差过大"
    assert abs(ratio - 1.0) < 0.02, "音量未对齐"
    print("自测通过 ✓")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="把翻唱对齐到原唱：时间偏移 + 音量匹配")
    ap.add_argument("original", nargs="?", help="原唱音频文件")
    ap.add_argument("cover", nargs="?", help="翻唱音频文件")
    ap.add_argument("-o", "--output", help="输出文件（WAV，默认 cover_aligned.wav）")
    ap.add_argument("--sr", type=int, default=None,
                    help="处理/输出采样率（默认与原唱相同）")
    ap.add_argument("--mode", choices=["global", "dynamic"], default="global",
                    help="音量匹配模式：global=单一增益，dynamic=逐帧增益（默认 global）")
    ap.add_argument("--no-trim", action="store_true", help="不裁剪首尾静音")
    ap.add_argument("--no-limit", action="store_true", help="禁用峰值保护")
    ap.add_argument("--selftest", action="store_true", help="用合成信号自测算法")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.original or not args.cover:
        ap.error("需要提供 original 和 cover（或使用 --selftest）")
    align(args.original, args.cover,
          args.output or "cover_aligned.wav",
          sr=args.sr, mode=args.mode,
          trim=not args.no_trim,
          limit=0.995 if not args.no_limit else 1.0)


if __name__ == "__main__":
    main()
