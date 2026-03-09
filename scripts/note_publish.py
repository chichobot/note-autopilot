#!/usr/bin/env python3
"""
Note 发布脚本（输出发布请求，由 main 代理执行）
"""
import json
import sys
from pathlib import Path

DRAFTS_DIR = Path("/Users/chicho/.openclaw/workspace-studio/output/content-pipeline/drafts")
CONTENT_MANIFEST_DIR = Path("/Users/chicho/.openclaw/workspace/output/content-pipeline/content-manifests")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="准备 note 发布数据")
    parser.add_argument("--topic-id", required=True, help="主题 ID")
    
    args = parser.parse_args()
    topic_id = args.topic_id
    
    # 加载草稿
    draft_file = DRAFTS_DIR / f"{topic_id}.json"
    if not draft_file.exists():
        print(json.dumps({"status": "error", "message": f"草稿不存在: {topic_id}"}))
        return 1
    
    with open(draft_file) as f:
        draft = json.load(f)
    
    note_draft = draft.get("note_draft", "")
    if not note_draft:
        print(json.dumps({"status": "error", "message": "草稿内容为空"}))
        return 1
    
    # 提取标题和正文
    lines = note_draft.split("\n")
    title = ""
    body_lines = []
    found_title = False
    
    for line in lines:
        if not found_title and line.startswith("# "):
            title = line[2:].strip()
            found_title = True
        elif found_title:
            body_lines.append(line)
    
    body = "\n".join(body_lines).strip()
    
    if not title:
        print(json.dumps({"status": "error", "message": "无法提取标题"}))
        return 1
    
    # 检查封面和插图
    images = []
    manifest_file = CONTENT_MANIFEST_DIR / f"{topic_id}.json"
    if manifest_file.exists():
        with open(manifest_file) as f:
            manifest = json.load(f)
            # 封面
            if manifest.get("cover_image"):
                images.append({
                    "type": "cover",
                    "path": manifest["cover_image"]
                })
            # 插图
            for block in manifest.get("content_blocks", []):
                if block.get("type") == "image" and block.get("image_path"):
                    images.append({
                        "type": "illustration",
                        "path": block["image_path"]
                    })
    
    # 输出发布数据
    result = {
        "status": "ready",
        "topic_id": topic_id,
        "title": title,
        "body": body,
        "images": images,
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
