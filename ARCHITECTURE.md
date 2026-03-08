# PolyRadar 系统架构与技术选型

## 1. 系统架构设计

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      PolyRadar System                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │  数据采集层  │ →   │  数据处理层  │ →   │  推送通知层  │    │
│  │  Collector  │    │  Processor  │    │  Notifier   │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│         │                   │                   │            │
│         ▼                   ▼                   ▼            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ Polymarket  │    │   SQLite    │    │   飞书Bot   │    │
│  │   API      │    │  Database   │    │ (moltbot)   │    │
│  │ Gamma+CLOB  │    │             │    │             │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│                          │                                 │
│                          ▼                                 │
│                   ┌─────────────┐                          │
│                   │ Claude LLM  │                          │
│                   │ (OpenClaw)  │                          │
│                   └─────────────┘                          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
           │                          │
           │                          │
           ▼                          ▼
    ┌──────────────┐         ┌──────────────┐
    │ OpenClaw Cron│         │ 日志与监控   │
    │  调度器      │         │  (memory/)   │
    └──────────────┘         └──────────────┘
```

### 1.2 模块划分

#### 1.2.1 数据采集层 (Data Collector)
**职责**：高频、异步拉取Polymarket API数据

**核心组件**：
- `polymarket_client.py` - Polymarket API客户端
- `market_fetcher.py` - 市场数据拉取器
- `news_fetcher.py` - 新闻数据拉取器（可选扩展）

**主要功能**：
- 连接Gamma API获取市场列表
- 连接CLOB API获取实时订单簿和概率
- 缓存最新数据到SQLite

**技术细节**：
- 使用`aiohttp`进行异步请求
- 单次请求超时设置：10秒
- 失败重试机制：最多3次，指数退避

#### 1.2.2 数据处理层 (Data Processor)
**职责**：规则引擎、数据分析、LLM调用

**核心组件**：
- `rule_engine.py` - 爆点判断规则引擎
- `analyzer.py` - 市场数据分析器
- `llm_client.py` - LLM调用封装（基于OpenClaw）

**主要功能**：
- 对比前后周期数据，计算变化
- 执行爆点阈值判断
- 过滤低流动性市场
- 调用LLM生成摘要和洞察
- 去重机制（2小时内不重复推送）

**技术细节**：
- SQLite存储历史数据（保留24小时）
- 去重哈希：市场ID + 时间戳（按小时分组）

#### 1.2.3 推送通知层 (Notifier)
**职责**：将处理后的情报推送到飞书

**核心组件**：
- `formatter.py` - 消息格式化器
- `notifier.py` - 飞书推送封装
- `push_handler.py` - 推送调度器

**主要功能**：
- 格式化整点简报
- 格式化爆点预警
- 通过OpenClaw message工具推送

**技术细节**：
- 复用OpenClaw现有的飞书channel配置
- 支持富文本格式（Markdown）
- 推送失败重试机制

---

## 2. 技术选型

### 2.1 核心技术栈

| 层级 | 技术选择 | 说明 |
|------|---------|------|
| **开发语言** | Python 3.10+ | OpenClaw环境支持，生态丰富 |
| **HTTP客户端** | aiohttp | 异步IO，支持高并发请求 |
| **数据存储** | SQLite 3 | 轻量级，无需额外服务，易备份 |
| **调度系统** | OpenClaw Cron | 复用现有基础设施，统一管理 |
| **LLM服务** | Claude Opus 4.6 (mynewapi) | 通过OpenClaw调用 |
| **推送渠道** | 飞书 (moltbot) | OpenClaw message工具 |
| **日志系统** | OpenClaw memory/ | 统一记录到workspace memory |

### 2.2 Python依赖

```txt
# 核心依赖
aiohttp>=3.9.0          # 异步HTTP客户端
aiodns>=3.2.0           # 异步DNS解析（加速请求）
asyncio>=3.4.3          # 异步IO

# 数据处理
pandas>=2.1.0           # 数据分析
numpy>=1.26.0           # 数值计算

# 数据存储
sqlite3                 # Python内置

# 辅助工具
python-dotenv>=1.0.0    # 环境变量管理
pytz>=2023.3            # 时区处理
```

### 2.3 为什么不选择其他方案？

**不使用Redis/PostgreSQL**：
- SQLite足够支撑当前数据量（Polymarket市场数量有限）
- 避免引入额外服务依赖，降低运维复杂度

**不使用Celery/任务队列**：
- OpenClaw Cron已经提供调度能力
- 简化架构，减少故障点

**不使用自建LLM**：
- 复用OpenClaw现有的Claude配置
- 降低成本，统一模型管理

---

## 3. 数据流设计

### 3.1 整点简报流程

```
[整点触发]
    ↓
[Collector] 拉取全量市场数据
    ↓
[Rule Engine] 筛选Top5异动市场
    ↓
[Analyzer] 提取关键指标
    ↓
[LLM Client] 调用Claude生成摘要
    ↓
[Formatter] 格式化消息
    ↓
[Notifier] 推送到飞书
```

### 3.2 爆点预警流程

```
[每5分钟触发]
    ↓
[Collector] 增量拉取活跃市场数据
    ↓
[Rule Engine] 对比上一周期，检测爆点
    ↓
[判断]
    ├─ 无爆点 → 结束
    └─ 有爆点
         ↓
    [去重检查]
         ↓
    [判断]
         ├─ 已推送 → 结束
         └─ 未推送
              ↓
         [LLM Client] 生成快速洞察
              ↓
         [Formatter] 格式化预警消息
              ↓
         [Notifier] 立即推送到飞书
```

---

## 4. 数据库设计

### 4.1 数据表结构

```sql
-- 市场基本信息表
CREATE TABLE markets (
    id TEXT PRIMARY KEY,           -- Polymarket市场ID
    title TEXT NOT NULL,            -- 市场标题
    description TEXT,               -- 市场描述
    category TEXT,                  -- 分类（politics/finance/crypto/trending）
    liquidity REAL,                 -- 总流动性池
    created_at INTEGER,             -- 创建时间戳
    updated_at INTEGER,             -- 更新时间戳
    UNIQUE(id)
);

-- 市场快照表（记录周期性数据）
CREATE TABLE market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,        -- 关联markets.id
    yes_price REAL,                 -- Yes价格
    no_price REAL,                 -- No价格
    volume_24h REAL,               -- 24小时交易量
    volume_1h REAL,                -- 1小时交易量
    probability REAL,               -- 当前概率（基于价格计算）
    timestamp INTEGER NOT NULL,      -- 快照时间戳
    FOREIGN KEY (market_id) REFERENCES markets(id),
    INDEX idx_market_time (market_id, timestamp)
);

-- 爆点记录表（用于去重）
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,       -- 类型（volatility/volume/trending）
    threshold_value REAL,           -- 触发阈值
    triggered_at INTEGER NOT NULL,  -- 触发时间戳
    sent_at INTEGER,                -- 推送时间戳（NULL表示未推送）
    FOREIGN KEY (market_id) REFERENCES markets(id),
    INDEX idx_market_time (market_id, triggered_at)
);

-- 推送历史表
CREATE TABLE push_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_type TEXT NOT NULL,     -- 类型（hourly/alert）
    content TEXT NOT NULL,          -- 推送内容
    sent_at INTEGER NOT NULL,       -- 推送时间戳
    INDEX idx_time (sent_at)
);
```

### 4.2 数据保留策略

- `market_snapshots`：保留24小时（定时清理）
- `alerts`：保留7天
- `push_history`：保留30天
- `markets`：永久保留（定期更新）

---

## 5. 调度策略

### 5.1 Cron Job配置

使用OpenClaw Cron配置：

```json
{
  "name": "polyradar-hourly-digest",
  "schedule": {
    "kind": "cron",
    "expr": "0 * * * *",
    "tz": "Asia/Shanghai"
  },
  "payload": {
    "kind": "systemEvent",
    "text": "polyradar:hourly_digest"
  },
  "sessionTarget": "main",
  "enabled": true
}
```

```json
{
  "name": "polyradar-alert-check",
  "schedule": {
    "kind": "cron",
    "expr": "*/5 * * * *",
    "tz": "Asia/Shanghai"
  },
  "payload": {
    "kind": "systemEvent",
    "text": "polyradar:alert_check"
  },
  "sessionTarget": "main",
  "enabled": true
}
```

### 5.2 心跳集成

利用现有的HEARTBEAT.md机制，在心跳时检查PolyRadar状态：
- 最近一次推送时间
- 最近一次异常
- 数据库健康状态

---

## 6. 推送格式设计

### 6.1 整点简报格式

```
📊 【PolyRadar 一小时风向回顾】

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 Top 异动

1. 美联储6月降息概率 (Yes: 45%→55%, 交易量+$250k)
   📰 新闻：美联储暗示6月可能调整利率政策
   💡 AI洞察：市场预期转向鸽派，交易量激增反映分歧加剧

2. 比特币$100K概率 (Yes: 32%→41%, 交易量+$180k)
   📰 新闻：比特币ETF资金流入创新高
   💡 AI洞察：机构资金持续进场，短期情绪回暖

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 市场概览
- 活跃市场数：1,234
- 24h总交易量：$5.2M
- 爆发点数量：3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

查看详情：https://polymarket.com

[自动推送 | PolyRadar]
```

### 6.2 爆点预警格式

```
🚨 【PolyRadar 紧急爆点预警】🚨

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 标的：特朗普2024大选胜率
⚡ 异动类型：概率闪崩
📊 当前状态：
   - Yes概率：68%→53%（-15%）
   - 15分钟交易量：$128k

💡 快速分析：
   市场出现剧烈反转，可能有突发新闻影响选情预期。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 快速查看：
https://polymarket.com/event/xxx

[自动推送 | PolyRadar]
```

---

## 7. 配置管理

### 7.1 配置文件结构

```python
# config.py
class Config:
    # Polymarket API配置
    POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
    POLYMARKET_CLOB_API = "https://clob.polymarket.com"

    # 爆点阈值
    ALERT_VOLATILITY_THRESHOLD = 0.10  # 10%概率波动
    ALERT_VOLUME_THRESHOLD = 100000     # $100k交易量
    ALERT_MIN_LIQUIDITY = 50000        # $50k流动性池

    # 流动性过滤
    MIN_LIQUIDITY = 10000              # $10k最低流动性

    # 去重设置
    ALERT_DEDUP_WINDOW = 7200         # 2小时（秒）

    # 推送设置
    FEISHU_BOT_NAME = "moltbot"

    # 数据库
    DB_PATH = "/root/.openclaw/workspace/polyradar/data/polyradar.db"
```

### 7.2 环境变量

```bash
# .env
POLYMARKET_API_KEY=your_api_key_here
POLYMARKET_API_URL=https://gamma-api.polymarket.com
```

---

## 8. 监控与告警

### 8.1 健康检查指标

- API请求成功率
- 数据库连接状态
- 最近一次推送时间
- 爆点预警触发频率

### 8.2 日志记录

- 所有操作记录到`memory/YYYY-MM-DD.md`
- 异常日志单独记录
- 每日汇总报告

---

## 9. 部署清单

### 9.1 目录结构

```
/root/.openclaw/workspace/polyradar/
├── ARCHITECTURE.md          # 本文档
├── PRD.md                   # 产品需求文档
├── config.py                # 配置文件
├── requirements.txt         # Python依赖
├── src/
│   ├── collector/
│   │   ├── polymarket_client.py
│   │   ├── market_fetcher.py
│   │   └── news_fetcher.py
│   ├── processor/
│   │   ├── rule_engine.py
│   │   ├── analyzer.py
│   │   └── llm_client.py
│   └── notifier/
│       ├── formatter.py
│       ├── notifier.py
│       └── push_handler.py
├── data/
│   └── polyradar.db         # SQLite数据库
└── main.py                  # 主入口（处理systemEvent）
```

### 9.2 初始化步骤

1. 安装依赖：`pip install -r requirements.txt`
2. 创建数据库：`python src/db_init.py`
3. 配置OpenClaw Cron：添加两个cron job
4. 测试推送：`python src/notifier/test_push.py`

---

## 10. API 详细设计

### 10.1 Polymarket API 概览

三个API，全部公开端点无需认证：

| API | Base URL | 用途 | Rate Limit |
|-----|----------|------|------------|
| Gamma API | `https://gamma-api.polymarket.com` | 市场/事件/标签/搜索 | 4,000 req/10s |
| Data API | `https://data-api.polymarket.com` | 持仓/交易/活动/排行榜 | 1,000 req/10s |
| CLOB API | `https://clob.polymarket.com` | 订单簿/价格/价格历史 | 9,000 req/10s |

**重要：不需要API Key！** 所有读取端点完全公开。

### 10.2 核心API端点

#### 数据采集（每5分钟）

```
GET /events?active=true&closed=false&limit=100&order=volume24hr
→ 获取活跃事件列表，按24h交易量排序
→ 返回字段包含：volume24hr, volume1wk, liquidity, category, oneHourPriceChange, oneDayPriceChange
```

```
GET /markets?active=true&closed=false&limit=200
→ 获取活跃市场列表
→ 返回字段包含：outcomePrices, volume24hr, liquidityNum, volumeNum
→ 自带 oneHourPriceChange 和 oneDayPriceChange，无需自行计算
```

#### 价格历史（按需）

```
GET /prices-history?market={market_id}&interval=1h&fidelity=5
→ 获取市场价格历史
→ 用于爆点预警的趋势分析
```

#### 订单簿深度（按需）

```
GET /book?token_id={token_id}
→ 获取实时订单簿
→ 用于判断大资金入场
```

### 10.3 关键数据字段映射

Events API 已内置的计算字段（无需自行计算）：
- `volume24hr` → 24小时交易量
- `volume1wk` → 一周交易量
- `oneHourPriceChange` → 1小时价格变化
- `oneDayPriceChange` → 1天价格变化
- `oneWeekPriceChange` → 1周价格变化
- `liquidity` → 流动性池大小
- `category` → 分类（可用于四大领域筛选）

这意味着：
- **整点简报**：直接用 `oneHourPriceChange` 排序即可获取Top异动
- **爆点预警**：对比前后快照的 `outcomePrices` 变化
- **流动性过滤**：直接用 `liquidity` 字段过滤

### 10.4 简化后的架构

由于API已内置大量计算字段，架构可以大幅简化：

```
[Cron触发]
    ↓
[HTTP请求] → Gamma API /events + /markets
    ↓
[过滤] → liquidity > $10k, active=true
    ↓
[排序] → 按 oneHourPriceChange / volume24hr
    ↓
[对比] → 与SQLite中上一周期数据对比（爆点检测）
    ↓
[LLM] → Claude生成摘要（仅整点简报）
    ↓
[推送] → 飞书 moltbot
```

---

## 11. 下一步

1. **确认技术选型** - 有无异议或调整？
2. **开始开发** - 按模块逐步实现（不需要API Key）
3. **测试部署** - 本地测试 → 云端部署

---

*版本：v1.1*
*日期：2026-03-08*
*作者：AI Assistant*
