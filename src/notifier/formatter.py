"""消息格式化器"""
import time
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def format_pct(value):
    """格式化百分比"""
    if value is None:
        return "N/A"
    return f"{value * 100:+.1f}%" if value != 0 else "0%"


def format_usd(value):
    """格式化美元金额"""
    if value is None:
        return "N/A"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def polymarket_url(slug):
    """生成Polymarket链接"""
    if slug:
        return f"https://polymarket.com/event/{slug}"
    return "https://polymarket.com"


def format_digest(top_movers, category_summary, total_markets):
    """格式化整点简报"""
    now = datetime.now(CST)
    time_str = now.strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 【PolyRadar 一小时风向回顾】",
        f"⏰ {time_str} CST",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔥 Top 异动",
        "",
    ]

    cat_emoji = {
        "politics": "🏛️",
        "finance": "💰",
        "crypto": "₿",
        "trending": "📈",
    }

    for i, m in enumerate(top_movers, 1):
        cat = m.get("category", "trending")
        emoji = cat_emoji.get(cat, "📌")
        question = m["question"]
        if len(question) > 50:
            question = question[:47] + "..."

        yes_pct = f"{m['yes_price'] * 100:.0f}%"
        change = format_pct(m.get("one_hour_change"))
        vol = format_usd(m.get("volume_24h"))
        liq = format_usd(m.get("liquidity"))
        url = polymarket_url(m.get("slug"))

        lines.append(f"{i}. {emoji} {question}")
        lines.append(f"   Yes: {yes_pct} ({change}) | 24h量: {vol} | 池: {liq}")
        lines.append(f"   🔗 {url}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("📈 市场概览")

    cat_names = {"politics": "时事政治", "finance": "金融市场", "crypto": "加密货币", "trending": "热度飙升"}
    for cat, data in category_summary.items():
        name = cat_names.get(cat, cat)
        lines.append(f"  {cat_emoji.get(cat, '📌')} {name}: {data['count']}个市场 | 24h量: {format_usd(data['total_volume_24h'])}")

    lines.append(f"  📊 活跃市场总数: {total_markets}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("[自动推送 | PolyRadar]")

    return "\n".join(lines)


def format_alert(alert):
    """格式化爆点预警"""
    now = datetime.now(CST)
    time_str = now.strftime("%H:%M")

    question = alert["question"]
    if len(question) > 60:
        question = question[:57] + "..."

    url = polymarket_url(alert.get("slug"))

    if alert["alert_type"] == "volatility":
        direction = alert.get("direction", "异动")
        prev_pct = f"{alert['prev_price'] * 100:.0f}%"
        curr_pct = f"{alert['curr_price'] * 100:.0f}%"
        change_pct = f"{alert['change'] * 100:+.1f}%"
        liq = format_usd(alert.get("liquidity"))

        lines = [
            "🚨 【PolyRadar 紧急爆点预警】🚨",
            "",
            f"📍 标的: {question}",
            f"⚡ 异动类型: 概率{direction}",
            f"📊 当前状态:",
            f"   Yes概率: {prev_pct} → {curr_pct} ({change_pct})",
            f"   流动性池: {liq}",
            "",
            f"🔗 快速查看: {url}",
            "",
            f"[{time_str} | PolyRadar]",
        ]

    elif alert["alert_type"] == "volume_surge":
        vol_diff = format_usd(alert.get("volume_diff"))
        curr_vol = format_usd(alert.get("curr_volume_24h"))

        lines = [
            "🚨 【PolyRadar 紧急爆点预警】🚨",
            "",
            f"📍 标的: {question}",
            f"⚡ 异动类型: 巨量资金入场",
            f"📊 当前状态:",
            f"   短时新增交易量: {vol_diff}",
            f"   24h总交易量: {curr_vol}",
            "",
            f"🔗 快速查看: {url}",
            "",
            f"[{time_str} | PolyRadar]",
        ]

    else:
        lines = [
            "🚨 【PolyRadar 爆点预警】🚨",
            "",
            f"📍 标的: {question}",
            f"⚡ 异动类型: {alert['alert_type']}",
            "",
            f"🔗 快速查看: {url}",
            "",
            f"[{time_str} | PolyRadar]",
        ]

    return "\n".join(lines)


def format_digest_with_ai(top_movers, category_summary, total_markets, ai_insights=None):
    """格式化带AI洞察的整点简报"""
    base = format_digest(top_movers, category_summary, total_markets)

    if ai_insights:
        lines = base.split("\n")
        # 在 "[自动推送]" 之前插入AI洞察
        insert_idx = len(lines) - 1
        ai_section = [
            "",
            "💡 AI 洞察",
            "",
            ai_insights,
            "",
        ]
        lines = lines[:insert_idx] + ai_section + lines[insert_idx:]
        return "\n".join(lines)

    return base
