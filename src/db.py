"""数据库初始化与管理"""
import sqlite3
import time
import os
from config import Config


def get_conn():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            slug TEXT,
            category TEXT,
            liquidity REAL DEFAULT 0,
            volume REAL DEFAULT 0,
            volume_24h REAL DEFAULT 0,
            outcome_prices TEXT,
            active INTEGER DEFAULT 1,
            created_at INTEGER,
            updated_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            yes_price REAL,
            no_price REAL,
            volume_24h REAL,
            liquidity REAL,
            one_hour_change REAL,
            one_day_change REAL,
            timestamp INTEGER NOT NULL,
            FOREIGN KEY (market_id) REFERENCES markets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_snap_market_time
            ON market_snapshots(market_id, timestamp);

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            detail TEXT,
            triggered_at INTEGER NOT NULL,
            sent INTEGER DEFAULT 0,
            FOREIGN KEY (market_id) REFERENCES markets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_alert_market_time
            ON alerts(market_id, triggered_at);

        CREATE TABLE IF NOT EXISTS push_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            sent_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_push_time
            ON push_history(sent_at);
    """)
    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成:", Config.DB_PATH)


def cleanup_old_data():
    """清理过期数据"""
    conn = get_conn()
    now = int(time.time())
    conn.execute("DELETE FROM market_snapshots WHERE timestamp < ?",
                 (now - Config.RETENTION_SNAPSHOTS,))
    conn.execute("DELETE FROM alerts WHERE triggered_at < ?",
                 (now - Config.RETENTION_ALERTS,))
    conn.execute("DELETE FROM push_history WHERE sent_at < ?",
                 (now - Config.RETENTION_PUSH_HISTORY,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
