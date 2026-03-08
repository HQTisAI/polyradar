import os

class Config:
    # Polymarket API
    GAMMA_API = "https://gamma-api.polymarket.com"
    DATA_API = "https://data-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"

    # 数据采集
    EVENTS_LIMIT = 100
    MARKETS_LIMIT = 200
    REQUEST_TIMEOUT = 15

    # 流动性过滤（美元）
    MIN_LIQUIDITY = 10000

    # 爆点阈值
    ALERT_VOLATILITY_THRESHOLD = 0.10    # 10% 概率波动
    ALERT_VOLATILITY_MIN_LIQUIDITY = 50000  # $50k 流动性池
    ALERT_VOLUME_THRESHOLD = 100000      # $100k 15分钟交易量
    ALERT_TRENDING_MAX_AGE_HOURS = 12    # 新市场最大年龄
    ALERT_TRENDING_TOP_N = 3             # Trending 前N

    # 去重窗口（秒）
    ALERT_DEDUP_WINDOW = 7200  # 2小时

    # 整点简报
    DIGEST_TOP_N = 5  # Top N 异动

    # 数据库
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "polyradar.db")

    # 数据保留（秒）
    RETENTION_SNAPSHOTS = 86400      # 24小时
    RETENTION_ALERTS = 604800        # 7天
    RETENTION_PUSH_HISTORY = 2592000 # 30天

    # 分类映射（Polymarket category → 四大领域）
    CATEGORY_MAP = {
        "politics": "politics",
        "elections": "politics",
        "geopolitics": "politics",
        "world": "politics",
        "finance": "finance",
        "economics": "finance",
        "fed": "finance",
        "crypto": "crypto",
        "bitcoin": "crypto",
        "ethereum": "crypto",
        "defi": "crypto",
    }

    # 默认分类
    DEFAULT_CATEGORY = "trending"
