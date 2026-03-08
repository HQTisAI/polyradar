"""推送模块 - 通过文件队列与OpenClaw集成"""
import os
import json
import time
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 推送消息队列目录
QUEUE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "push_queue")


def ensure_queue_dir():
    os.makedirs(QUEUE_DIR, exist_ok=True)


def queue_message(message, message_type="digest"):
    """将消息写入队列文件，等待OpenClaw推送"""
    ensure_queue_dir()
    ts = int(time.time() * 1000)
    filename = f"{ts}_{message_type}.json"
    filepath = os.path.join(QUEUE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "type": message_type,
            "message": message,
            "created_at": ts,
        }, f, ensure_ascii=False)
    return filepath


def get_pending_messages():
    """获取待推送的消息"""
    ensure_queue_dir()
    messages = []
    for fname in sorted(os.listdir(QUEUE_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(QUEUE_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_filepath"] = fpath
                messages.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    return messages


def mark_sent(filepath):
    """删除已推送的消息文件"""
    try:
        os.remove(filepath)
    except OSError:
        pass


def send_pending():
    """输出待推送消息（供OpenClaw调用）"""
    messages = get_pending_messages()
    if not messages:
        print("NO_MESSAGES")
        return []

    results = []
    for msg in messages:
        print(f"PENDING:{msg['type']}:{msg['_filepath']}")
        print(msg["message"])
        print("---END---")
        results.append(msg)
    return results


if __name__ == "__main__":
    send_pending()
