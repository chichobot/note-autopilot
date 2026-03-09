#!/usr/bin/env python3
"""
为 note 草稿生成图片（封面 + 插图）
使用 nano-banana-pro skill (Gemini 3 Pro Image)
支持参考图风格迁移
"""
import json
import random
import subprocess
import sys
from pathlib import Path

IMAGE_PLAN_DIR = Path("/Users/chicho/.openclaw/workspace/output/content-pipeline/image-plans")
COVERS_DIR = Path("/Users/chicho/.openclaw/workspace/output/content-pipeline/covers")
ILLUSTRATIONS_DIR = Path("/Users/chicho/.openclaw/workspace/output/content-pipeline/illustrations")
NANO_BANANA_SCRIPT = Path("/opt/homebrew/lib/node_modules/openclaw/skills/nano-banana-pro/scripts/generate_image.py")
REFERENCE_COVERS_DIR = Path(__file__).parent.parent / "reference-covers"

def pick_reference_cover():
    """随机选择一张参考封面"""
    if not REFERENCE_COVERS_DIR.exists():
        return None
    
    refs = list(REFERENCE_COVERS_DIR.glob("ref-*.png")) + list(REFERENCE_COVERS_DIR.glob("ref-*.jpg"))
    if not refs:
        return None
    
    return random.choice(refs)

def generate_viral_cover_prompt(title: str, topic: str) -> str:
    """生成爆款风格的封面 prompt"""
    prompt = f"""为 note.com 文章生成一个吸引眼球的封面图 prompt（Gemini 图片生成）。

文章标题：{title}
主题：{topic}

参考爆款风格：
- 配色：深色底（深蓝/黑色）+ 荧光色文字（青色/黄色/红色）
- 风格：YouTube 缩略图风格，高对比度，信息密度高
- 元素：科技感、神经网络、发光效果、3D 字体
- 文字：粗体黑体，加描边/阴影，居中或左右分割
- 整体：赛博朋克风或高饱和撞色

要求：
1. 英文 prompt
2. 适合 16:9 比例
3. 突出主题关键词
4. 视觉冲击力强

只输出 prompt，不要其他内容。"""
    
    try:
        result = subprocess.run(
            ["gemini", prompt],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()
    except Exception:
        # fallback
        return "Futuristic AI technology concept, neural networks, glowing cyan and purple lines, sleek, high-end, 8k, minimalistic, dark background with neon accents"


def generate_images(topic_id: str):
    """为指定 topic 生成所有图片"""
    # 加载 image plan
    plan_file = IMAGE_PLAN_DIR / f"{topic_id}.json"
    if not plan_file.exists():
        print(f"❌ Image plan 不存在: {topic_id}", file=sys.stderr)
        return False
    
    with open(plan_file) as f:
        plan = json.load(f)
    
    title = plan.get("title", "")
    topic = plan.get("article_type", "")
    
    # 创建输出目录
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    topic_illustrations_dir = ILLUSTRATIONS_DIR / topic_id
    topic_illustrations_dir.mkdir(parents=True, exist_ok=True)
    
    generated = []
    
    # 1. 生成封面（使用爆款风格 prompt）
    cover_path = COVERS_DIR / f"{topic_id}-note-cover.png"
    viral_prompt = generate_viral_cover_prompt(title, topic)
    
    print(f"生成封面: {cover_path}", file=sys.stderr)
    print(f"Prompt: {viral_prompt[:100]}...", file=sys.stderr)
    
    cmd = [
        "uv", "run", str(NANO_BANANA_SCRIPT),
        "--prompt", viral_prompt,
        "--filename", str(cover_path),
        "--aspect-ratio", "16:9",
        "--resolution", "1K"
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode == 0 and cover_path.exists():
        print(f"✅ 封面已生成: {cover_path}", file=sys.stderr)
        generated.append(str(cover_path))
    else:
        print(f"❌ 封面生成失败: {result.stderr}", file=sys.stderr)
    
    # 2. 生成插图
    illustration_recs = plan.get("illustration_recommendations", [])
    for i, illust in enumerate(illustration_recs, 1):
        prompt = illust.get("rendered_prompt_positive", "") or illust.get("prompt", "")
        if not prompt:
            print(f"⚠️ 插图 {i} prompt 为空", file=sys.stderr)
            continue
        
        illust_path = topic_illustrations_dir / f"illustration-{i:02d}.png"
        print(f"生成插图 {i}: {illust_path}", file=sys.stderr)
        print(f"Prompt: {prompt[:100]}...", file=sys.stderr)
        
        result = subprocess.run(
            ["uv", "run", str(NANO_BANANA_SCRIPT),
             "--prompt", prompt,
             "--filename", str(illust_path),
             "--aspect-ratio", "16:9",
             "--resolution", "1K"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0 and illust_path.exists():
            print(f"✅ 插图 {i} 已生成: {illust_path}", file=sys.stderr)
            generated.append(str(illust_path))
        else:
            print(f"❌ 插图 {i} 生成失败: {result.stderr}", file=sys.stderr)
    
    print(f"\n生成完成: {len(generated)} 张图片", file=sys.stderr)
    return len(generated) > 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="生成 note 图片")
    parser.add_argument("--topic-id", required=True, help="主题 ID")
    
    args = parser.parse_args()
    
    success = generate_images(args.topic_id)
    
    if success:
        print(json.dumps({"status": "ok", "topic_id": args.topic_id}))
        return 0
    else:
        print(json.dumps({"status": "error", "topic_id": args.topic_id}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
