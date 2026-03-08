# PolyRadar - Polymarket 智能情报监控与推送系统

## 快速开始

```bash
cd /root/.openclaw/workspace/polyradar
pip install -r requirements.txt
python main.py init        # 初始化数据库
python main.py digest      # 手动触发整点简报
python main.py alert       # 手动触发爆点检查
```

## 目录结构

```
polyradar/
├── config.py              # 配置
├── main.py                # 主入口
├── requirements.txt       # 依赖
├── src/
│   ├── collector/         # 数据采集
│   ├── processor/         # 数据处理 + 规则引擎
│   └── notifier/          # 推送
└── data/
    └── polyradar.db       # SQLite
```
