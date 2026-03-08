#!/usr/bin/env python3
"""PolyRadar - Polymarket 智能情报监控与推送系统

用法:
    python main.py init      # 初始化数据库
    python main.py digest    # 整点简报
    python main.py alert     # 爆点检查
    python main.py collect   # 仅采集数据（不推送）
    python main.py test      # 测试采集并打印
"""
import sys
import os
import asyncio
import json
import time

# 确保项目根目录在 path 中
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from config import Config
from src.db import init_db, cleanup_old_data, get_conn
from src.collector.polymarket_client import collect_all
from src.processor.rule_engine import (
    save_snapshots, detect_alerts, get_top_movers,
    get_category_summary, save_alert, save_push_history,
    enrich_with_price_change,
)
from src.notifier.formatter import (
    format_digest, format_alert, format_digest_with_ai,
)
from src.notifier.push_handler import queue_message, send_pending, get_pending_messages, mark_sent


def ensure_db():
    """确保数据库已初始化"""
    if not os.path.exists(Config.DB_PATH):
        init_db()


async def cmd_collect():
    """仅采集数据，保存快照"""
    ensure_db()
    markets = await collect_all()
    if markets:
        save_snapshots(markets)
        print(f"✅ 已保存 {len(markets)} 个市场快照")
    else:
        print("⚠️ 未采集到数据")
    return markets


async def cmd_digest():
    """整点简报：采集 → 分析 → 格式化 → 输出"""
    ensure_db()
    cleanup_old_data()

    # 1. 采集
    markets = await collect_all()
    if not markets:
        print("⚠️ 未采集到数据，跳过简报")
        return None

    # 2. 保存快照
    save_snapshots(markets)

    # 3. 补充价格变化（基于历史快照）
    markets = enrich_with_price_change(markets)

    # 4. 分析
    top_movers = get_top_movers(markets)
    category_summary = get_category_summary(markets)

    # 5. 格式化
    message = format_digest(top_movers, category_summary, len(markets))

    # 6. 保存推送历史 & 写入队列
    save_push_history("hourly", message)
    qpath = queue_message(message, "digest")

    print(message)
    print(f"\n📤 已写入推送队列: {qpath}")
    return message


async def cmd_alert():
    """爆点检查：采集 → 对比 → 检测 → 输出"""
    ensure_db()

    # 1. 采集
    markets = await collect_all()
    if not markets:
        print("⚠️ 未采集到数据，跳过检查")
        return []

    # 2. 保存快照
    save_snapshots(markets)

    # 3. 检测爆点
    alerts = detect_alerts(markets)

    if not alerts:
        print("✅ 无爆点事件")
        return []

    # 4. 格式化并输出
    messages = []
    for a in alerts:
        save_alert(a["market_id"], a["alert_type"], a.get("detail", ""), sent=1)
        msg = format_alert(a)
        save_push_history("alert", msg)
        queue_message(msg, "alert")
        messages.append(msg)
        print(msg)
        print("---")

    print(f"🚨 检测到 {len(alerts)} 个爆点事件")
    return messages


async def cmd_test():
    """测试采集并打印前10个市场"""
    markets = await collect_all()
    if not markets:
        print("⚠️ 未采集到数据")
        return

    print(f"\n📊 共 {len(markets)} 个活跃市场（流动性 >= ${Config.MIN_LIQUIDITY:,}）\n")

    cat_emoji = {"politics": "🏛️", "finance": "💰", "crypto": "₿", "trending": "📈"}

    for i, m in enumerate(markets[:10], 1):
        cat = m.get("category", "trending")
        emoji = cat_emoji.get(cat, "📌")
        q = m["question"]
        if len(q) > 55:
            q = q[:52] + "..."
        print(f"{i:2d}. {emoji} {q}")
        print(f"    Yes: {m['yes_price']*100:.0f}%  1h变化: {m['one_hour_change']*100:+.1f}%  24h量: ${m['volume_24h']:,.0f}  池: ${m['liquidity']:,.0f}")
        print()

    # 分类汇总
    summary = get_category_summary(markets)
    print("📈 分类汇总:")
    cat_names = {"politics": "时事政治", "finance": "金融市场", "crypto": "加密货币", "trending": "热度飙升"}
    for cat, data in summary.items():
        name = cat_names.get(cat, cat)
        print(f"  {cat_emoji.get(cat, '📌')} {name}: {data['count']}个 | 24h量: ${data['total_volume_24h']:,.0f}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "init":
        init_db()
    elif cmd == "collect":
        asyncio.run(cmd_collect())
    elif cmd == "digest":
        asyncio.run(cmd_digest())
    elif cmd == "alert":
        asyncio.run(cmd_alert())
    elif cmd == "test":
        asyncio.run(cmd_test())
    elif cmd == "pending":
        # 输出待推送消息（供OpenClaw cron调用）
        msgs = get_pending_messages()
        if not msgs:
            print("NO_MESSAGES")
        else:
            for msg in msgs:
                print(json.dumps({
                    "type": msg["type"],
                    "message": msg["message"],
                    "filepath": msg["_filepath"],
                }, ensure_ascii=False))
    elif cmd == "mark-sent":
        # 标记消息已推送
        if len(sys.argv) < 3:
            print("用法: python3 main.py mark-sent <filepath>")
            sys.exit(1)
        mark_sent(sys.argv[2])
        print(f"✅ 已标记: {sys.argv[2]}")
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
