#!/usr/bin/env python3
"""
Telegram 审批流程
替代 Discord 审批，使用 Telegram inline buttons
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# 路径配置
WORKSPACE = Path("/Users/chicho/.openclaw/workspace")
CONTENT_HUB = Path("/Users/chicho/.openclaw/content-hub")
STATE_FILE = WORKSPACE / "output/content-pipeline/state/approval_status.json"
DRAFTS_DIR = Path("/Users/chicho/.openclaw/workspace-studio/output/content-pipeline/drafts")

# Telegram 配置
TELEGRAM_TARGET = "6421742954"  # 你的 Telegram user ID


def load_state():
    """加载审批状态"""
    if not STATE_FILE.exists():
        return {"items": {}}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    """保存审批状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_draft(topic_id):
    """加载草稿"""
    draft_file = DRAFTS_DIR / f"{topic_id}.json"
    if not draft_file.exists():
        return None
    with open(draft_file) as f:
        return json.load(f)


def send_approval_card(topic_id, channel="note"):
    """
    发送审批卡到 Telegram
    
    Args:
        topic_id: 主题 ID
        channel: 渠道（note/x/xhs）
    
    Returns:
        message_id: Telegram 消息 ID
    """
    # 加载草稿
    draft = load_draft(topic_id)
    if not draft:
        print(f"❌ 草稿不存在: {topic_id}", file=sys.stderr)
        return None
    
    # 构造审批消息
    title = draft.get("title", "无标题")
    summary = draft.get("summary", "")[:200]
    
    message = f"""📝 **Note 待审批**

**Topic ID:** `{topic_id}`
**标题:** {title}

**摘要:**
{summary}

请点击下方按钮进行审批：
"""
    
    # 构造按钮
    buttons = [
        [
            {"text": "✅ 批准", "callback_data": f"approve:{topic_id}:{channel}"},
            {"text": "❌ 驳回", "callback_data": f"reject:{topic_id}:{channel}"}
        ],
        [
            {"text": "📝 修改", "callback_data": f"changes:{topic_id}:{channel}"}
        ]
    ]
    
    # 发送消息
    print(f"发送审批卡: {topic_id}", file=sys.stderr)
    
    result = subprocess.run(
        ["openclaw", "message", "send",
         "--channel", "telegram",
         "--target", TELEGRAM_TARGET,
         "--message", message,
         "--buttons", json.dumps(buttons)],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    if result.returncode != 0:
        print(f"❌ 发送失败: {result.stderr}", file=sys.stderr)
        return None
    
    # 提取 message_id
    output = result.stdout
    if "Message ID:" in output:
        message_id = output.split("Message ID:")[1].strip().split()[0]
        print(f"✅ 审批卡已发送: message_id={message_id}", file=sys.stderr)
        return message_id
    
    return None


def process_callback(callback_data):
    """
    处理按钮回调
    
    Args:
        callback_data: 格式 "action:topic_id:channel"
    
    Returns:
        dict: 处理结果
    """
    parts = callback_data.split(":")
    if len(parts) != 3:
        return {"status": "error", "message": "Invalid callback_data format"}
    
    action, topic_id, channel = parts
    
    # 加载状态
    state = load_state()
    key = f"{topic_id}:{channel}"
    
    # 更新状态
    if action == "approve":
        new_status = "approved"
        message = f"✅ 已批准: {topic_id}"
    elif action == "reject":
        new_status = "rejected"
        message = f"❌ 已驳回: {topic_id}"
    elif action == "changes":
        new_status = "changes_requested"
        message = f"📝 需要修改: {topic_id}"
    else:
        return {"status": "error", "message": f"Unknown action: {action}"}
    
    # 更新状态文件
    if key not in state["items"]:
        state["items"][key] = {}
    
    state["items"][key]["status"] = new_status
    state["items"][key]["updated_at"] = datetime.now().isoformat()
    state["items"][key]["approved_by"] = "telegram"
    
    save_state(state)
    
    print(message, file=sys.stderr)
    
    return {
        "status": "ok",
        "topic_id": topic_id,
        "channel": channel,
        "action": action,
        "new_status": new_status
    }


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Telegram 审批流程")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # 发送审批卡
    send_parser = subparsers.add_parser("send", help="发送审批卡")
    send_parser.add_argument("--topic-id", required=True, help="主题 ID")
    send_parser.add_argument("--channel", default="note", help="渠道")
    
    # 处理回调
    callback_parser = subparsers.add_parser("callback", help="处理按钮回调")
    callback_parser.add_argument("--data", required=True, help="callback_data")
    
    args = parser.parse_args()
    
    if args.command == "send":
        message_id = send_approval_card(args.topic_id, args.channel)
        if message_id:
            print(json.dumps({"status": "ok", "message_id": message_id}))
            return 0
        else:
            print(json.dumps({"status": "error"}))
            return 1
    
    elif args.command == "callback":
        result = process_callback(args.data)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "ok" else 1
    
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
