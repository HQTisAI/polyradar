"""Polymarket 数据采集器"""
import aiohttp
import asyncio
import json
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


# 关键词分类规则
KEYWORD_RULES = [
    # politics
    (r"(?i)(trump|biden|election|president|congress|senate|vote|governor|mayor|democrat|republican|party|political|nato|war|iran|israel|ukraine|russia|china|tariff|sanction|ceasefire|peace|military|strike|invasion|strait|hormuz|gaza|taiwan|korea)", "politics"),
    # finance
    (r"(?i)(fed\b|interest rate|inflation|gdp|recession|stock|s&p|nasdaq|dow|treasury|bond|oil|gold|commodity|cpi|unemployment|jobs|payroll|rate cut|rate hike|bps)", "finance"),
    # crypto
    (r"(?i)(bitcoin|btc|ethereum|eth|crypto|solana|sol|defi|nft|token|blockchain|coinbase|binance|stablecoin|usdc|usdt)", "crypto"),
]


def classify_by_keywords(text):
    """基于关键词推断分类"""
    if not text:
        return Config.DEFAULT_CATEGORY
    for pattern, category in KEYWORD_RULES:
        if re.search(pattern, text):
            return category
    return Config.DEFAULT_CATEGORY


async def fetch_events(session, limit=None, offset=0):
    """获取活跃事件列表，按24h交易量排序"""
    limit = limit or Config.EVENTS_LIMIT
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "offset": offset,
        "order": "volume24hr",
        "ascending": "false",
    }
    url = f"{Config.GAMMA_API}/events"
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)) as resp:
            if resp.status != 200:
                print(f"⚠️ fetch_events 失败: HTTP {resp.status}")
                return []
            return await resp.json()
    except Exception as e:
        print(f"⚠️ fetch_events 异常: {e}")
        return []


async def fetch_markets(session, limit=None, offset=0):
    """获取活跃市场列表"""
    limit = limit or Config.MARKETS_LIMIT
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "offset": offset,
        "order": "volume24hr",
        "ascending": "false",
    }
    url = f"{Config.GAMMA_API}/markets"
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)) as resp:
            if resp.status != 200:
                print(f"⚠️ fetch_markets 失败: HTTP {resp.status}")
                return []
            return await resp.json()
    except Exception as e:
        print(f"⚠️ fetch_markets 异常: {e}")
        return []


def parse_outcome_prices(raw_prices):
    """解析 outcomePrices 字段"""
    yes_price = 0.0
    no_price = 0.0
    if not raw_prices:
        return yes_price, no_price
    try:
        prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
        if len(prices) >= 2:
            yes_price = float(prices[0])
            no_price = float(prices[1])
        elif len(prices) == 1:
            yes_price = float(prices[0])
            no_price = 1.0 - yes_price
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return yes_price, no_price


def parse_market(raw, event_title=""):
    """解析市场数据为标准格式"""
    outcome_prices = raw.get("outcomePrices", "")
    yes_price, no_price = parse_outcome_prices(outcome_prices)

    # 分类：先用API字段，再用关键词推断
    raw_category = (raw.get("category") or "").lower().strip()
    category = Config.CATEGORY_MAP.get(raw_category) if raw_category else None
    if not category:
        question = raw.get("question", "")
        category = classify_by_keywords(f"{question} {event_title}")

    return {
        "id": raw.get("id", ""),
        "question": raw.get("question", ""),
        "slug": raw.get("slug", ""),
        "category": category,
        "liquidity": float(raw.get("liquidityNum") or raw.get("liquidity") or 0),
        "volume": float(raw.get("volumeNum") or raw.get("volume") or 0),
        "volume_24h": float(raw.get("volume24hr") or 0),
        "yes_price": yes_price,
        "no_price": no_price,
        "outcome_prices": outcome_prices if isinstance(outcome_prices, str) else json.dumps(outcome_prices),
        "one_hour_change": float(raw.get("oneHourPriceChange") or 0),
        "one_day_change": float(raw.get("oneDayPriceChange") or 0),
        "active": 1 if raw.get("active") else 0,
        "created_at": raw.get("createdAt", ""),
        "event_title": event_title,
    }


async def collect_all():
    """采集所有活跃市场数据（通过events端点获取，包含子市场）"""
    async with aiohttp.ClientSession() as session:
        # 同时拉取events和markets
        events_raw, markets_raw = await asyncio.gather(
            fetch_events(session),
            fetch_markets(session),
        )

        # 从events中提取市场（带event title用于分类）
        event_markets = {}
        for e in events_raw:
            event_title = e.get("title", "")
            for m in e.get("markets", []):
                mid = m.get("id", "")
                if mid:
                    event_markets[mid] = event_title

        # 合并：以markets端点为主，补充event_title
        markets = []
        seen = set()
        for m in markets_raw:
            mid = m.get("id", "")
            if mid in seen:
                continue
            seen.add(mid)
            event_title = event_markets.get(mid, "")
            parsed = parse_market(m, event_title)
            if parsed["liquidity"] >= Config.MIN_LIQUIDITY:
                markets.append(parsed)

        print(f"📊 采集到 {len(markets_raw)} 个市场，过滤后 {len(markets)} 个（流动性 >= ${Config.MIN_LIQUIDITY:,}）")
        return markets


if __name__ == "__main__":
    results = asyncio.run(collect_all())
    cat_emoji = {"politics": "🏛️", "finance": "💰", "crypto": "₿", "trending": "📈"}
    for m in results[:10]:
        cat = m.get("category", "trending")
        emoji = cat_emoji.get(cat, "📌")
        print(f"  {emoji} [{cat}] {m['question'][:55]}  Yes:{m['yes_price']:.2f}  Vol24h:${m['volume_24h']:,.0f}")
