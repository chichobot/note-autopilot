#!/usr/bin/env python3
"""
验证检查点工具
用于在关键环节强制验证，符合铁律一：没有验证的完成是谎言
"""
import json
import sys
from pathlib import Path
from typing import Any, Optional


class VerificationError(Exception):
    """验证失败异常"""
    pass


def verify_topic_scan_output(topic_file: Path) -> dict[str, Any]:
    """
    验证 topic_scan 输出
    
    铁律一检查点：
    - 文件必须存在
    - 必须包含 candidates 列表
    - 必须有至少 1 个候选
    - 必须有 source_health 信息
    """
    if not topic_file.exists():
        raise VerificationError(f"Topic file not found: {topic_file}")
    
    try:
        data = json.loads(topic_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise VerificationError(f"Invalid JSON in topic file: {e}")
    
    candidates = data.get("candidates", [])
    if not candidates:
        raise VerificationError("No candidates found in topic scan output")
    
    if "source_health" not in data:
        raise VerificationError("Missing source_health in topic scan output")
    
    # 提取验证证据
    top = max(candidates, key=lambda x: x.get("score", 0))
    evidence = {
        "candidates_count": len(candidates),
        "top_id": top.get("id"),
        "top_score": top.get("score"),
        "top_source": top.get("source"),
        "source_health": data["source_health"],
    }
    
    print(f"✅ Topic scan verified: {evidence}", file=sys.stderr)
    return evidence


def verify_draft_output(draft_file: Path, cover_file: Optional[Path] = None) -> dict[str, Any]:
    """
    验证 draft 输出
    
    铁律一检查点：
    - 草稿文件必须存在
    - 必须是日文（不能是中文）
    - 字数 ≥ 800
    - 封面图必须存在（如果指定）
    """
    if not draft_file.exists():
        raise VerificationError(f"Draft file not found: {draft_file}")
    
    content = draft_file.read_text(encoding="utf-8")
    
    # 检测语言（简单规则：中文字符占比）
    chinese_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
    japanese_chars = sum(1 for c in content if '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
    
    if chinese_chars > japanese_chars * 2:
        raise VerificationError(f"Draft contains too much Chinese (CN:{chinese_chars} JP:{japanese_chars})")
    
    # 检查字数
    char_count = len(content)
    if char_count < 800:
        raise VerificationError(f"Draft too short: {char_count} chars (minimum 800)")
    
    # 检查封面
    if cover_file and not cover_file.exists():
        raise VerificationError(f"Cover image not found: {cover_file}")
    
    evidence = {
        "draft_file": str(draft_file),
        "char_count": char_count,
        "chinese_chars": chinese_chars,
        "japanese_chars": japanese_chars,
        "has_cover": cover_file.exists() if cover_file else False,
    }
    
    print(f"✅ Draft verified: {evidence}", file=sys.stderr)
    return evidence


def verify_approval_push(message_id: Optional[str]) -> dict[str, Any]:
    """
    验证审批卡推送
    
    铁律一检查点：
    - 必须拿到 messageId
    """
    if not message_id:
        raise VerificationError("No messageId returned from approval push")
    
    if not message_id.isdigit():
        raise VerificationError(f"Invalid messageId format: {message_id}")
    
    evidence = {
        "message_id": message_id,
    }
    
    print(f"✅ Approval push verified: {evidence}", file=sys.stderr)
    return evidence


def verify_publish_output(url: Optional[str]) -> dict[str, Any]:
    """
    验证发布输出
    
    铁律一检查点：
    - 必须拿到公开 URL
    - URL 必须是 note.com 域名
    - URL 必须可访问（简单检查格式）
    """
    if not url:
        raise VerificationError("No URL returned from publish")
    
    if not url.startswith("https://note.com/"):
        raise VerificationError(f"Invalid note.com URL: {url}")
    
    # 检查 URL 格式
    if "/n/" not in url:
        raise VerificationError(f"URL missing note ID: {url}")
    
    evidence = {
        "url": url,
        "domain": "note.com",
        "verified": True,
    }
    
    print(f"✅ Publish verified: {evidence}", file=sys.stderr)
    return evidence


def main():
    """CLI 入口"""
    if len(sys.argv) < 3:
        print("Usage: verify.py <check_type> <args...>", file=sys.stderr)
        print("  topic_scan <topic_file>", file=sys.stderr)
        print("  draft <draft_file> [cover_file]", file=sys.stderr)
        print("  approval_push <message_id>", file=sys.stderr)
        print("  publish <url>", file=sys.stderr)
        sys.exit(1)
    
    check_type = sys.argv[1]
    
    try:
        if check_type == "topic_scan":
            evidence = verify_topic_scan_output(Path(sys.argv[2]))
        elif check_type == "draft":
            cover = Path(sys.argv[3]) if len(sys.argv) > 3 else None
            evidence = verify_draft_output(Path(sys.argv[2]), cover)
        elif check_type == "approval_push":
            evidence = verify_approval_push(sys.argv[2])
        elif check_type == "publish":
            evidence = verify_publish_output(sys.argv[2])
        else:
            raise VerificationError(f"Unknown check type: {check_type}")
        
        # 输出 JSON 格式的证据
        print(json.dumps(evidence, ensure_ascii=False))
        sys.exit(0)
        
    except VerificationError as e:
        print(f"❌ Verification failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
