#!/usr/bin/env python3
"""PolyRadar 基础测试"""
import sys
import os
import time
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config import Config
from src.db import init_db, get_conn
from src.processor.rule_engine import (
    save_snapshots, detect_alerts, get_top_movers,
    get_category_summary, check_is_duplicate, save_alert,
    enrich_with_price_change,
)
from src.collector.polymarket_client import classify_by_keywords
from src.notifier.formatter import format_digest, format_alert

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1


def test_classification():
    """测试关键词分类"""
    print("\n📋 测试：关键词分类")
    test("Fed rate → finance", classify_by_keywords("Will the Fed cut interest rates") == "finance")
    test("Trump election → politics", classify_by_keywords("Will Trump win the 2024 election") == "politics")
    test("Bitcoin price → crypto", classify_by_keywords("Bitcoin above $100K by December") == "crypto")
    test("Iran regime → politics", classify_by_keywords("Will the Iranian regime fall") == "politics")
    test("S&P 500 → finance", classify_by_keywords("S&P 500 above 6000") == "finance")
    test("Ethereum ETF → crypto", classify_by_keywords("Will SEC approve spot ETH ETF") == "crypto")
    test("Oil price → finance", classify_by_keywords("Oil price above $100") == "finance")
    test("Ukraine war → politics", classify_by_keywords("Ukraine Russia ceasefire by June") == "politics")
    test("Random topic → trending", classify_by_keywords("Will it rain tomorrow in NYC") == "trending")
    test("GPT release → trending", classify_by_keywords("GPT-5 released by March") == "trending")


def test_volatility_alert():
    """测试概率反转检测"""
    print("\n📋 测试：概率反转检测")

    # 使用临时数据库
    original_db = Config.DB_PATH
    Config.DB_PATH = os.path.join(ROOT, "data", "test_alerts.db")

    try:
        # 清理
        if os.path.exists(Config.DB_PATH):
            os.remove(Config.DB_PATH)
        init_db()

        # 第一次快照：Yes = 50%
        markets_t1 = [{
            "id": "test-market-1",
            "question": "Test volatility market",
            "slug": "test-volatility",
            "category": "politics",
            "liquidity": 60000,  # > $50k
            "volume": 100000,
            "volume_24h": 50000,
            "yes_price": 0.50,
            "no_price": 0.50,
            "outcome_prices": '["0.50", "0.50"]',
            "one_hour_change": 0,
            "one_day_change": 0,
            "active": 1,
        }]
        save_snapshots(markets_t1)

        # 等一秒确保时间戳不同
        time.sleep(1)

        # 第二次快照：Yes = 65%（+15%，超过10%阈值）
        markets_t2 = [{
            "id": "test-market-1",
            "question": "Test volatility market",
            "slug": "test-volatility",
            "category": "politics",
            "liquidity": 60000,
            "volume": 100000,
            "volume_24h": 55000,
            "yes_price": 0.65,
            "no_price": 0.35,
            "outcome_prices": '["0.65", "0.35"]',
            "one_hour_change": 0,
            "one_day_change": 0,
            "active": 1,
        }]
        save_snapshots(markets_t2)

        # 检测爆点（需要调整 min_age 为0）
        conn = get_conn()
        # 手动修改第一个快照的时间戳，使其满足 min_age 要求
        conn.execute("UPDATE market_snapshots SET timestamp = timestamp - 300 WHERE id = 1")
        conn.commit()
        conn.close()

        alerts = detect_alerts(markets_t2)
        test("检测到概率反转", len(alerts) > 0)
        if alerts:
            test("类型为 volatility", alerts[0]["alert_type"] == "volatility")
            test("方向为拉升", alerts[0]["direction"] == "拉升")
            test("变化幅度 >= 10%", alerts[0]["change"] >= 0.10)

    finally:
        Config.DB_PATH = original_db
        # 清理测试数据库
        test_db = os.path.join(ROOT, "data", "test_alerts.db")
        if os.path.exists(test_db):
            os.remove(test_db)


def test_volume_surge_alert():
    """测试资金突袭检测"""
    print("\n📋 测试：资金突袭检测")

    original_db = Config.DB_PATH
    Config.DB_PATH = os.path.join(ROOT, "data", "test_volume.db")

    try:
        if os.path.exists(Config.DB_PATH):
            os.remove(Config.DB_PATH)
        init_db()

        # 第一次快照
        markets_t1 = [{
            "id": "test-market-2",
            "question": "Test volume market",
            "slug": "test-volume",
            "category": "finance",
            "liquidity": 100000,
            "volume": 500000,
            "volume_24h": 200000,
            "yes_price": 0.60,
            "no_price": 0.40,
            "outcome_prices": '["0.60", "0.40"]',
            "one_hour_change": 0,
            "one_day_change": 0,
            "active": 1,
        }]
        save_snapshots(markets_t1)
        time.sleep(1)

        # 第二次快照：交易量增加 $150k（超过 $100k 阈值）
        markets_t2 = [{
            "id": "test-market-2",
            "question": "Test volume market",
            "slug": "test-volume",
            "category": "finance",
            "liquidity": 100000,
            "volume": 650000,
            "volume_24h": 350000,  # +$150k
            "yes_price": 0.62,
            "no_price": 0.38,
            "outcome_prices": '["0.62", "0.38"]',
            "one_hour_change": 0,
            "one_day_change": 0,
            "active": 1,
        }]
        save_snapshots(markets_t2)

        conn = get_conn()
        conn.execute("UPDATE market_snapshots SET timestamp = timestamp - 300 WHERE id = 1")
        conn.commit()
        conn.close()

        alerts = detect_alerts(markets_t2)
        test("检测到资金突袭", len(alerts) > 0)
        if alerts:
            test("类型为 volume_surge", alerts[0]["alert_type"] == "volume_surge")
            test("交易量增量 >= $100k", alerts[0]["volume_diff"] >= 100000)

    finally:
        Config.DB_PATH = original_db
        test_db = os.path.join(ROOT, "data", "test_volume.db")
        if os.path.exists(test_db):
            os.remove(test_db)


def test_dedup():
    """测试去重机制"""
    print("\n📋 测试：去重机制")

    original_db = Config.DB_PATH
    Config.DB_PATH = os.path.join(ROOT, "data", "test_dedup.db")

    try:
        if os.path.exists(Config.DB_PATH):
            os.remove(Config.DB_PATH)
        init_db()

        # 先插入 market 记录
        conn = get_conn()
        conn.execute("INSERT INTO markets (id, question, active) VALUES (?, ?, 1)", ("test-market-3", "Test dedup"))
        conn.commit()
        conn.close()

        # 保存一个已推送的 alert
        save_alert("test-market-3", "volatility", "{}", sent=1)

        # 检查去重
        is_dup = check_is_duplicate("test-market-3", "volatility")
        test("同类型同市场被去重", is_dup == True)

        # 不同类型不去重
        is_dup2 = check_is_duplicate("test-market-3", "volume_surge")
        test("不同类型不去重", is_dup2 == False)

        # 不同市场不去重
        is_dup3 = check_is_duplicate("test-market-999", "volatility")
        test("不同市场不去重", is_dup3 == False)

    finally:
        Config.DB_PATH = original_db
        test_db = os.path.join(ROOT, "data", "test_dedup.db")
        if os.path.exists(test_db):
            os.remove(test_db)


def test_formatter():
    """测试消息格式化"""
    print("\n📋 测试：消息格式化")

    markets = [
        {"question": "Test market 1", "slug": "test-1", "category": "politics",
         "yes_price": 0.75, "one_hour_change": -0.05, "volume_24h": 500000, "liquidity": 100000},
        {"question": "Test market 2", "slug": "test-2", "category": "finance",
         "yes_price": 0.30, "one_hour_change": 0.03, "volume_24h": 200000, "liquidity": 50000},
    ]
    summary = {"politics": {"count": 5, "total_volume_24h": 1000000, "total_liquidity": 500000},
               "finance": {"count": 3, "total_volume_24h": 800000, "total_liquidity": 300000}}

    msg = format_digest(markets, summary, 100)
    test("简报包含标题", "PolyRadar" in msg)
    test("简报包含市场数据", "Test market 1" in msg)
    test("简报包含分类汇总", "时事政治" in msg or "金融市场" in msg)

    alert = {
        "question": "Test alert market",
        "slug": "test-alert",
        "alert_type": "volatility",
        "direction": "闪崩",
        "prev_price": 0.80,
        "curr_price": 0.65,
        "change": 0.15,
        "liquidity": 80000,
    }
    alert_msg = format_alert(alert)
    test("预警包含🚨", "🚨" in alert_msg)
    test("预警包含方向", "闪崩" in alert_msg)
    test("预警包含链接", "polymarket.com" in alert_msg)


if __name__ == "__main__":
    print("🧪 PolyRadar 测试套件\n" + "=" * 40)

    test_classification()
    test_volatility_alert()
    test_volume_surge_alert()
    test_dedup()
    test_formatter()

    print(f"\n{'=' * 40}")
    print(f"📊 结果: {passed} 通过 / {failed} 失败 / {passed + failed} 总计")
    if failed > 0:
        sys.exit(1)
    else:
        print("🎉 全部通过！")
