"""市场标题翻译器 - 将 Polymarket 英文标题翻译为可读中文"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import Config
from src.db import get_conn

# 翻译缓存表
_CACHE_TABLE_CREATED = False


def _ensure_cache_table():
    global _CACHE_TABLE_CREATED
    if _CACHE_TABLE_CREATED:
        return
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS translation_cache (
            question TEXT PRIMARY KEY,
            translated TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    _CACHE_TABLE_CREATED = True


def _get_cached(question):
    """从缓存获取翻译"""
    _ensure_cache_table()
    conn = get_conn()
    row = conn.execute(
        "SELECT translated FROM translation_cache WHERE question = ?",
        (question,)
    ).fetchone()
    conn.close()
    return row["translated"] if row else None


def _set_cache(question, translated):
    """写入翻译缓存"""
    _ensure_cache_table()
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO translation_cache (question, translated, created_at) VALUES (?, ?, ?)",
        (question, translated, int(time.time()))
    )
    conn.commit()
    conn.close()


def _call_llm(prompt):
    """调用智谱 GLM API 翻译"""
    url = f"{Config.LLM_BASE_URL}/chat/completions"
    payload = json.dumps({
        "model": Config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业翻译。将英文预测市场标题翻译成简洁易懂的中文。要求：1）人名保留英文但加中文通用译名（如有）；2）展开所有缩写；3）保持简洁，不超过原文长度的1.5倍；4）只输出翻译结果，不要解释。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 200,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {Config.LLM_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ 翻译API调用失败: {e}")
        return None


def translate_question(question):
    """翻译市场标题，带缓存"""
    if not question:
        return question

    # 如果已经是中文为主，不翻译
    chinese_chars = sum(1 for c in question if '\u4e00' <= c <= '\u9fff')
    if chinese_chars > len(question) * 0.3:
        return question

    # 查缓存
    cached = _get_cached(question)
    if cached:
        return cached

    # 调用LLM翻译
    translated = _call_llm(question)
    if translated:
        _set_cache(question, translated)
        return translated

    # 翻译失败，返回原文
    return question


def translate_batch(questions):
    """批量翻译（先查缓存，未命中的一次性翻译）"""
    results = {}
    to_translate = []

    for q in questions:
        if not q:
            results[q] = q
            continue
        chinese_chars = sum(1 for c in q if '\u4e00' <= c <= '\u9fff')
        if chinese_chars > len(q) * 0.3:
            results[q] = q
            continue
        cached = _get_cached(q)
        if cached:
            results[q] = cached
        else:
            to_translate.append(q)

    if not to_translate:
        return results

    # 批量翻译：一次请求翻译多个标题
    if len(to_translate) <= 8:
        numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(to_translate))
        prompt = f"逐行翻译以下预测市场标题为中文，保持编号格式，每行只输出翻译结果：\n{numbered}"
        result = _call_llm(prompt)
        if result:
            lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
            for i, q in enumerate(to_translate):
                if i < len(lines):
                    # 去掉编号前缀
                    translated = lines[i].lstrip("0123456789.、）) ").strip()
                    if translated:
                        _set_cache(q, translated)
                        results[q] = translated
                    else:
                        results[q] = q
                else:
                    results[q] = q
        else:
            for q in to_translate:
                results[q] = q
    else:
        # 太多了，逐个翻译
        for q in to_translate:
            results[q] = translate_question(q)

    return results
