"""
LLM-based song_name_reading converter.

Uses local Qwen LLM to convert English words/numbers in song titles
to katakana, then pykakasi normalizes to hiragana.

Only calls LLM when the title contains English words; otherwise uses
pykakasi directly (no LLM overhead).
"""

import os
import re
import time

import pykakasi

# 加载配置
sys_path = os.path.dirname(os.path.abspath(__file__))
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)
from config import OPENAI_URL, OPENAI_MODEL, OPENAI_KEY


# ── LLM 调用 ──────────────────────────────────────────────

def call_llm(prompt: str, max_retries: int = 3) -> str:
    """调用本地 Qwen LLM，返回文本。"""
    import httpx

    url = f"{OPENAI_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500,
    }

    for attempt in range(max_retries):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"  LLM 调用失败 (第{attempt+1}次), 重试: {e}")
            time.sleep(1)


# ── 英文检测 ──────────────────────────────────────────────

def has_english_words(text: str) -> bool:
    """检测文本中是否包含英文字母。"""
    return bool(re.search(r'[A-Za-z]', text))


# ── 核心: LLM片假名转换 ───────────────────────────────────

KATAKANA_PROMPT = """Given a song title, output the Japanese katakana reading for the entire title.
Keep existing Japanese characters (hiragana/katakana/kanji) as-is.
Convert English words and numbers to katakana.
Output ONLY the katakana reading, nothing else.

Song title: {title}

Katakana:"""


def title_to_katakana(song_name: str) -> str:
    """调用 LLM 将完整 song_name 转换为片假名。"""
    prompt = KATAKANA_PROMPT.format(title=song_name)
    katakana = call_llm(prompt)
    return katakana.strip()


# ── pykakasi 平假名转换 ────────────────────────────────────

_kakasi_instance = None


def _get_kakasi():
    global _kakasi_instance
    if _kakasi_instance is None:
        _kakasi_instance = pykakasi.kakasi()
    return _kakasi_instance


def convert_to_hiragana(text: str) -> str:
    """pykakasi 将日文文本转换为纯平假名。"""
    kaksi = _get_kakasi()
    result = kaksi.convert(text)
    return "".join([item['hira'] for item in result])


# ── 主入口: 智能转换 ──────────────────────────────────────

def convert_reading(song_name: str) -> str:
    """
    从 song_name 生成 song_name_reading:
    - 如果标题包含英文单词 → 发送完整标题给 LLM 转片假名 → pykakasi 转平假名
    - 如果标题没有英文 → 直接用 pykakasi 转平假名（跳过 LLM）
    """
    if has_english_words(song_name):
        print(f"  [LLM] 检测到英文，调用 LLM: {song_name}")
        katakana = title_to_katakana(song_name)
        print(f"  [LLM] 片假名结果: {katakana}")
        hiragana = convert_to_hiragana(katakana)
    else:
        print(f"  [pykakasi] 无英文，直接转换: {song_name}")
        hiragana = convert_to_hiragana(song_name)

    return hiragana
