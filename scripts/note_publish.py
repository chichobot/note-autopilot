#!/usr/bin/env python3
"""
Note 发布脚本
从草稿文件读取内容并发布到 note.com
"""
import json
import subprocess
import sys
from pathlib import Path

DRAFTS_DIR = Path("/Users/chicho/.openclaw/workspace-studio/output/content-pipeline/drafts")
CONTENT_MANIFEST_DIR = Path("/Users/chicho/.openclaw/workspace/output/content-pipeline/content-manifests")

def publish_note(topic_id: str):
    """发布 note"""
    # 加载草稿
    draft_file = DRAFTS_DIR / f"{topic_id}.json"
    if not draft_file.exists():
        print(f"❌ 草稿不存在: {topic_id}", file=sys.stderr)
        return None
    
    with open(draft_file) as f:
        draft = json.load(f)
    
    # 提取标题和内容
    note_draft = draft.get("note_draft", "")
    if not note_draft:
        print(f"❌ 草稿内容为空: {topic_id}", file=sys.stderr)
        return None
    
    # 提取标题（第一行 # 标题）
    lines = note_draft.split("\n")
    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break
    
    if not title:
        print(f"❌ 无法提取标题: {topic_id}", file=sys.stderr)
        return None
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    
    # 检查是否有 content manifest（包含图片）
    manifest_file = CONTENT_MANIFEST_DIR / f"{topic_id}.json"
    
    # 调用 note_publish_api.py
    print(f"发布 note: {topic_id}", file=sys.stderr)
    print(f"标题: {title}", file=sys.stderr)
    
    cmd = [
        "python3", str(script_dir / "note_publish_api.py"),
        "--title", title,
    ]
    
    if manifest_file.exists():
        print(f"使用 content manifest: {manifest_file}", file=sys.stderr)
        cmd.extend(["--content-manifest", str(manifest_file)])
    else:
        print(f"未找到 content manifest，仅发布文本", file=sys.stderr)
        cmd.extend(["--content", note_draft])
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode != 0:
        print(f"❌ 发布失败: {result.stderr}", file=sys.stderr)
        return None
    
    # 提取 URL
    output = result.stdout
    print(output, file=sys.stderr)
    
    # 尝试解析 JSON 输出
    try:
        result_data = json.loads(output)
        if result_data.get("status") == "ok":
            url = result_data.get("url")
            if url:
                print(f"✅ 发布成功: {url}", file=sys.stderr)
                return url
    except json.JSONDecodeError:
        pass
    
    # 查找 URL（fallback）
    for line in output.split("\n"):
        if "note.com" in line or "https://" in line:
            url = line.strip()
            if url.startswith("http"):
                print(f"✅ 发布成功: {url}", file=sys.stderr)
                return url
    
    print(f"⚠️ 发布可能成功，但未找到 URL", file=sys.stderr)
    return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="发布 note")
    parser.add_argument("--topic-id", required=True, help="主题 ID")
    
    args = parser.parse_args()
    
    url = publish_note(args.topic_id)
    
    if url:
        print(json.dumps({"status": "ok", "url": url}))
        return 0
    else:
        print(json.dumps({"status": "error"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
