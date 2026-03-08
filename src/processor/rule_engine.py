"""规则引擎 - 爆点检测与整点简报生成"""
import time
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from src.db import get_conn


def save_snapshots(markets):
    """保存市场快照到数据库"""
    conn = get_conn()
    now = int(time.time())
    for m in markets:
        conn.execute("""
            INSERT INTO markets (id, question, slug, category, liquidity, volume, volume_24h, outcome_prices, active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                question=excluded.question, slug=excluded.slug, category=excluded.category,
                liquidity=excluded.liquidity, volume=excluded.volume, volume_24h=excluded.volume_24h,
                outcome_prices=excluded.outcome_prices, active=excluded.active, updated_at=excluded.updated_at
        """, (m["id"], m["question"], m["slug"], m["category"],
              m["liquidity"], m["volume"], m["volume_24h"],
              m["outcome_prices"], m["active"], now))

        conn.execute("""
            INSERT INTO market_snapshots (market_id, yes_price, no_price, volume_24h, liquidity, one_hour_change, one_day_change, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (m["id"], m["yes_price"], m["no_price"], m["volume_24h"],
              m["liquidity"], m["one_hour_change"], m["one_day_change"], now))

    conn.commit()
    conn.close()


def get_previous_snapshot(market_id, before_ts=None, min_age=240):
    """获取上一个周期的快照（至少 min_age 秒前）"""
    conn = get_conn()
    before_ts = before_ts or int(time.time())
    row = conn.execute("""
        SELECT * FROM market_snapshots
        WHERE market_id = ? AND timestamp < ? - ?
        ORDER BY timestamp DESC LIMIT 1
    """, (market_id, before_ts, min_age)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_snapshot_hours_ago(market_id, hours=1):
    """获取约N小时前的快照（用于计算小时变化）"""
    conn = get_conn()
    target_ts = int(time.time()) - hours * 3600
    # 找最接近目标时间的快照
    row = conn.execute("""
        SELECT * FROM market_snapshots
        WHERE market_id = ? AND timestamp BETWEEN ? - 600 AND ? + 600
        ORDER BY ABS(timestamp - ?) ASC LIMIT 1
    """, (market_id, target_ts, target_ts, target_ts)).fetchone()
    conn.close()
    return dict(row) if row else None


def calc_price_change(current_price, prev_snapshot):
    """计算价格变化"""
    if not prev_snapshot:
        return 0.0
    prev_price = prev_snapshot.get("yes_price", 0)
    return current_price - prev_price


def check_is_duplicate(market_id, alert_type):
    """检查是否在去重窗口内已推送"""
    conn = get_conn()
    cutoff = int(time.time()) - Config.ALERT_DEDUP_WINDOW
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM alerts
        WHERE market_id = ? AND alert_type = ? AND triggered_at > ? AND sent = 1
    """, (market_id, alert_type, cutoff)).fetchone()
    conn.close()
    return row["cnt"] > 0


def save_alert(market_id, alert_type, detail, sent=0):
    """保存爆点记录"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO alerts (market_id, alert_type, detail, triggered_at, sent)
        VALUES (?, ?, ?, ?, ?)
    """, (market_id, alert_type, detail, int(time.time()), sent))
    conn.commit()
    conn.close()


def detect_alerts(markets):
    """检测爆点事件"""
    alerts = []

    for m in markets:
        market_id = m["id"]
        prev = get_previous_snapshot(market_id)
        if not prev:
            continue

        # 1. 剧烈反转检测：流动性 >= $50k，价格变化 >= 10%
        if m["liquidity"] >= Config.ALERT_VOLATILITY_MIN_LIQUIDITY:
            price_change = abs(m["yes_price"] - prev["yes_price"])
            if price_change >= Config.ALERT_VOLATILITY_THRESHOLD:
                if not check_is_duplicate(market_id, "volatility"):
                    direction = "拉升" if m["yes_price"] > prev["yes_price"] else "闪崩"
                    detail = json.dumps({
                        "direction": direction,
                        "prev_price": prev["yes_price"],
                        "curr_price": m["yes_price"],
                        "change": price_change,
                        "liquidity": m["liquidity"],
                    }, ensure_ascii=False)
                    alerts.append({
                        "market_id": market_id,
                        "question": m["question"],
                        "slug": m["slug"],
                        "alert_type": "volatility",
                        "detail": detail,
                        "direction": direction,
                        "prev_price": prev["yes_price"],
                        "curr_price": m["yes_price"],
                        "change": price_change,
                        "liquidity": m["liquidity"],
                    })

        # 2. 资金突袭检测：短时新增交易量 >= $100k
        volume_diff = m["volume_24h"] - prev["volume_24h"]
        if volume_diff >= Config.ALERT_VOLUME_THRESHOLD:
            if not check_is_duplicate(market_id, "volume_surge"):
                detail = json.dumps({
                    "volume_diff": volume_diff,
                    "curr_volume_24h": m["volume_24h"],
                    "prev_volume_24h": prev["volume_24h"],
                }, ensure_ascii=False)
                alerts.append({
                    "market_id": market_id,
                    "question": m["question"],
                    "slug": m["slug"],
                    "alert_type": "volume_surge",
                    "detail": detail,
                    "volume_diff": volume_diff,
                    "curr_volume_24h": m["volume_24h"],
                })

    return alerts


def enrich_with_price_change(markets):
    """为市场数据补充价格变化（基于快照对比）"""
    for m in markets:
        # 如果API没返回 oneHourPriceChange，从快照计算
        if m["one_hour_change"] == 0:
            prev_1h = get_snapshot_hours_ago(m["id"], hours=1)
            if prev_1h:
                m["one_hour_change"] = calc_price_change(m["yes_price"], prev_1h)

        if m["one_day_change"] == 0:
            prev_24h = get_snapshot_hours_ago(m["id"], hours=24)
            if prev_24h:
                m["one_day_change"] = calc_price_change(m["yes_price"], prev_24h)

    return markets


def get_top_movers(markets, top_n=None):
    """获取Top异动市场（按价格变化绝对值排序）"""
    top_n = top_n or Config.DIGEST_TOP_N

    # 先尝试用1小时变化排序
    has_change = [m for m in markets if m.get("one_hour_change", 0) != 0]
    if has_change:
        sorted_markets = sorted(has_change, key=lambda m: abs(m["one_hour_change"]), reverse=True)
    else:
        # 没有变化数据时，按24h交易量排序
        sorted_markets = sorted(markets, key=lambda m: m.get("volume_24h", 0), reverse=True)

    return sorted_markets[:top_n]


def get_category_summary(markets):
    """按分类汇总"""
    summary = {}
    for m in markets:
        cat = m.get("category", "trending")
        if cat not in summary:
            summary[cat] = {"count": 0, "total_volume_24h": 0, "total_liquidity": 0}
        summary[cat]["count"] += 1
        summary[cat]["total_volume_24h"] += m.get("volume_24h", 0)
        summary[cat]["total_liquidity"] += m.get("liquidity", 0)
    return summary


def save_push_history(message_type, content):
    """保存推送历史"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO push_history (message_type, content, sent_at)
        VALUES (?, ?, ?)
    """, (message_type, content, int(time.time())))
    conn.commit()
    conn.close()
