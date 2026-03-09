#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

TZ = ZoneInfo("Asia/Tokyo")
ROOT = Path("/Users/chicho/.openclaw")
WORKSPACE = ROOT / "workspace"
WORKSPACE_STUDIO = ROOT / "workspace-studio"
WORKSPACE_NOTE = ROOT / "workspace-note"
CONTENT_HUB = ROOT / "content-hub"

TOPICS_DIR = WORKSPACE_STUDIO / "output/content-pipeline/topics"
DRAFTS_DIR = WORKSPACE_STUDIO / "output/content-pipeline/drafts"
APPROVALS_DIR = WORKSPACE / "output/content-pipeline/approvals"
PUBLISH_LOG_DIR = WORKSPACE_NOTE / "output/content-pipeline/publish-log"
LEADS_DIR = WORKSPACE / "output/content-pipeline/leads"
STATE_DIR = WORKSPACE / "output/content-pipeline/state"
METRICS_DIR = WORKSPACE / "output/content-pipeline/metrics"
WEEKLY_DIR = WORKSPACE / "output/content-pipeline/weekly-reviews"
IMAGE_PLAN_DIR = WORKSPACE / "output/content-pipeline/image-plans"
CONTENT_MANIFEST_DIR = WORKSPACE / "output/content-pipeline/content-manifests"

STATE_FILE = STATE_DIR / "approval_status.json"
ENV_FILE = ROOT / ".env"
XHS_PYTHON = ROOT / "skills/xiaohongshu-mcp/venv/bin/python3"
XHS_CLIENT = ROOT / "skills/xiaohongshu-mcp/scripts/xhs_client.py"
XHS_STATUS_TIMEOUT = 10
XHS_FEEDS_TIMEOUT = 20
XHS_SEARCH_TIMEOUT = 25
XHS_SMOKE_KEYWORD = "AI入門"
XHS_FEEDS_CACHE_FILE = ROOT / "cache/xiaohongshu-feeds-cache.json"
XHS_FEEDS_CACHE_MAX_AGE_HOURS = 12
FEED_TIMEOUT = 12
FEED_ITEM_LIMIT = 5
HUB_INBOX_DIR = CONTENT_HUB / "00-收件箱"
HUB_SOURCES_DIR = CONTENT_HUB / "01-灵感与素材库/1-日常灵感剪报"
HUB_INSIGHTS_DIR = CONTENT_HUB / "01-灵感与素材库/2-爆款素材片段"
HUB_TOPICS_DIR = CONTENT_HUB / "02-选题池/待写选题库"
HUB_PATTERNS_DIR = CONTENT_HUB / "06-复盘与模式/模式库"
HUB_PRODUCTION_DIR = CONTENT_HUB / "03-内容工厂"
HUB_PRODUCTION_OUTLINE_DIR = HUB_PRODUCTION_DIR / "1-大纲挑选区"
HUB_PRODUCTION_DRAFT_DIR = HUB_PRODUCTION_DIR / "2-初稿打磨区"
HUB_PRODUCTION_FINAL_DIR = HUB_PRODUCTION_DIR / "3-终稿确认区"
HUB_DISTRIBUTION_DIR = CONTENT_HUB / "04-分发与审批"
HUB_FEEDBACK_DIR = CONTENT_HUB / "05-已发布归档/发布记录"
HUB_SYSTEM_DIR = CONTENT_HUB / "99-系统配置"
PROMPT_REPO_DIR = HUB_PATTERNS_DIR / "生图提示词库"
PROMPT_REPO_COVER_DIR = PROMPT_REPO_DIR / "cover"
PROMPT_REPO_ILLUSTRATION_DIR = PROMPT_REPO_DIR / "illustration"
PROMPT_REPO_EXAMPLES_DIR = PROMPT_REPO_DIR / "examples"
PROMPT_REPO_INTAKE_DIR = PROMPT_REPO_DIR / "intake"
PROMPT_REPO_SOURCE_FILE = PROMPT_REPO_DIR / "sources.json"

VALID_STATUS = {
    "drafted",
    "pending_approval",
    "approved",
    "changes_requested",
    "publish_failed_auth",
    "publish_unverified",
    "published",
    "rejected",
}


@dataclass
class TopicCandidate:
    topic_id: str
    source: str
    angle: str
    audience: str
    score: float
    evidence_urls: list[str]
    risk_flags: list[str]


@dataclass
class PromptCard:
    card_id: str
    title: str
    prompt_type: str
    recommended_for: str
    source_origin: str
    source_url: str
    model_family: list[str]
    text_policy: str
    visual_style: str
    subject_pattern: str
    mood: str
    color_palette: list[str]
    aspect_ratio: str
    resolution: str
    prompt_positive: str
    prompt_negative: str
    quality_notes: str
    failure_modes: list[str]
    tags: list[str]
    path: Path


def now_jst() -> datetime:
    return datetime.now(TZ)


def iso_now() -> str:
    return now_jst().isoformat(timespec="seconds")


def date_str(dt: datetime | None = None) -> str:
    target = dt or now_jst()
    return target.strftime("%Y-%m-%d")


def ensure_dirs() -> None:
    for path in [
        TOPICS_DIR,
        DRAFTS_DIR,
        APPROVALS_DIR,
        PUBLISH_LOG_DIR,
        IMAGE_PLAN_DIR,
        CONTENT_MANIFEST_DIR,
        LEADS_DIR,
        STATE_DIR,
        METRICS_DIR,
        WEEKLY_DIR,
        HUB_INBOX_DIR,
        HUB_SOURCES_DIR,
        HUB_INSIGHTS_DIR,
        HUB_TOPICS_DIR,
        HUB_PATTERNS_DIR,
        HUB_PRODUCTION_OUTLINE_DIR,
        HUB_PRODUCTION_DRAFT_DIR,
        HUB_PRODUCTION_FINAL_DIR,
        HUB_DISTRIBUTION_DIR,
        HUB_FEEDBACK_DIR,
        HUB_SYSTEM_DIR,
        PROMPT_REPO_DIR,
        PROMPT_REPO_COVER_DIR,
        PROMPT_REPO_ILLUSTRATION_DIR,
        PROMPT_REPO_EXAMPLES_DIR,
        PROMPT_REPO_INTAKE_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def parse_env(path: Path = ENV_FILE) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def note_env_report(env: dict[str, str]) -> tuple[bool, list[str]]:
    required = [
        "NOTE_PUBLISH_MODE",
        "NOTE_EMAIL",
        "NOTE_PASSWORD",
        "NOTE_AUTHOR_URL",
    ]
    missing = [key for key in required if not env.get(key)]
    return (len(missing) == 0, missing)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def topic_file_for_date(day: str, profile: str = "full") -> Path:
    if profile == "full":
        return TOPICS_DIR / f"{day}.json"
    return TOPICS_DIR / f"{day}.{profile}.json"


def latest_topic_file(profile: str = "full") -> Path | None:
    pattern = "*.json" if profile == "full" else f"*.{profile}.json"
    files = sorted(TOPICS_DIR.glob(pattern))
    return files[-1] if files else None


def load_topics(day: str | None = None) -> dict[str, Any] | None:
    if day:
        p = topic_file_for_date(day)
        if p.exists():
            return load_json(p, None)
    today = topic_file_for_date(date_str())
    if today.exists():
        return load_json(today, None)
    latest = latest_topic_file()
    if latest:
        return load_json(latest, None)
    return None


def draft_path(topic_id: str) -> Path:
    return DRAFTS_DIR / f"{topic_id}.json"


def load_draft(topic_id: str) -> dict[str, Any] | None:
    p = draft_path(topic_id)
    if not p.exists():
        return None
    return load_json(p, None)


def save_draft(draft: dict[str, Any]) -> Path:
    topic_id = draft["topic_id"]
    path = draft_path(topic_id)
    draft["updated_at"] = iso_now()
    save_json(path, draft)
    return path


def default_workflow_status() -> dict[str, str]:
    return {"note": "drafted"}


def blank_draft(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic_id": topic["id"],
        "topic_snapshot": topic,
        "created_at": iso_now(),
        "updated_at": iso_now(),
        "status": "drafted",
        "workflow_status": default_workflow_status(),
        "x_posts": [],
        "x_slices": [],
        "note_outline": [],
        "note_draft": "",
        "review_feedback": {
            "note": {
                "latest": "",
                "history": [],
            }
        },
        "compliance_checklist": [
            "无夸张收益承诺",
            "无未经证实数据",
            "包含明确 CTA",
            "语气客观，避免攻击性表达",
        ],
    }


def load_state() -> dict[str, Any]:
    state = load_json(
        STATE_FILE,
        {
            "updated_at": iso_now(),
            "items": {},
        },
    )
    if "items" not in state or not isinstance(state["items"], dict):
        state["items"] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = iso_now()
    save_json(STATE_FILE, state)


def state_key(topic_id: str, channel: str) -> str:
    return f"{topic_id}:{channel}"


def set_state_item(
    state: dict[str, Any],
    topic_id: str,
    channel: str,
    status: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if status not in VALID_STATUS:
        raise ValueError(f"invalid status: {status}")
    key = state_key(topic_id, channel)
    item = state["items"].get(
        key,
        {
            "topic_id": topic_id,
            "channel": channel,
            "status": "drafted",
            "updated_at": iso_now(),
        },
    )
    item["status"] = status
    item["updated_at"] = iso_now()
    if extra:
        item.update(extra)
    state["items"][key] = item


def update_draft_status(topic_id: str, channel: str, status: str) -> None:
    draft = load_draft(topic_id)
    if not draft:
        return
    if "workflow_status" not in draft or not isinstance(draft["workflow_status"], dict):
        draft["workflow_status"] = default_workflow_status()
    draft["workflow_status"][channel] = status
    draft["status"] = status
    save_draft(draft)


def ensure_review_feedback_bucket(draft: dict[str, Any], channel: str) -> dict[str, Any]:
    review_feedback = draft.get("review_feedback")
    if not isinstance(review_feedback, dict):
        review_feedback = {}
    bucket = review_feedback.get(channel)
    if not isinstance(bucket, dict):
        bucket = {}
    history = bucket.get("history")
    if not isinstance(history, list):
        history = []
    bucket["history"] = history
    bucket["latest"] = str(bucket.get("latest", "") or "")
    review_feedback[channel] = bucket
    draft["review_feedback"] = review_feedback
    return bucket


def latest_review_feedback(draft: dict[str, Any], channel: str) -> str:
    bucket = ensure_review_feedback_bucket(draft, channel)
    return str(bucket.get("latest", "") or "").strip()


def record_review_feedback(
    topic_id: str,
    channel: str,
    note: str,
    *,
    reviewed_via: str = "",
    review_message_id: str = "",
) -> None:
    cleaned = note.strip()
    if not cleaned:
        return
    draft = load_draft(topic_id)
    if not draft:
        return
    bucket = ensure_review_feedback_bucket(draft, channel)
    entry = {
        "note": cleaned,
        "reviewed_via": reviewed_via,
        "review_message_id": review_message_id,
        "recorded_at": iso_now(),
    }
    bucket["latest"] = cleaned
    bucket["history"].append(entry)
    save_draft(draft)


def clear_review_feedback(topic_id: str, channel: str) -> None:
    draft = load_draft(topic_id)
    if not draft:
        return
    bucket = ensure_review_feedback_bucket(draft, channel)
    if not bucket.get("latest"):
        return
    bucket["latest"] = ""
    save_draft(draft)


def ensure_csv_header(path: Path, header: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)


def append_csv_row(path: Path, header: list[str], row: list[str]) -> None:
    ensure_csv_header(path, header)
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def canonical_id_for_topic(topic: dict[str, Any]) -> str:
    return str(topic.get("id") or topic.get("topic_id") or "")


def hub_rel(path: Path) -> str:
    return path.relative_to(CONTENT_HUB).as_posix()


def json_scalar(value: Any) -> str:
    if value is None:
        return '""'
    return json.dumps(value, ensure_ascii=False)


def load_existing_created_at(path: Path) -> str:
    if not path.exists():
        return ""

    in_frontmatter = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "---":
            if in_frontmatter:
                break
            in_frontmatter = True
            continue
        if in_frontmatter and stripped.startswith("created_at:"):
            raw = stripped.split(":", 1)[1].strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw.strip('"')
    return ""


def render_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        lines.append(f"{key}: {json_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def write_hub_card(path: Path, frontmatter: dict[str, Any], body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(frontmatter)
    payload["created_at"] = load_existing_created_at(path) or payload.get("created_at") or iso_now()
    payload["updated_at"] = iso_now()
    content = f"{render_frontmatter(payload)}\n\n{body.rstrip()}\n"
    path.write_text(content, encoding="utf-8")
    return path


def load_frontmatter_document(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    frontmatter_raw = text[4:end]
    body = text[end + 5 :]
    payload: dict[str, Any] = {}
    for raw_line in frontmatter_raw.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed: Any
        value = value.strip()
        if not value:
            parsed = ""
        else:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = value.strip('"')
        payload[key.strip()] = parsed
    return payload, body


def image_plan_path(topic_id: str) -> Path:
    return IMAGE_PLAN_DIR / f"{topic_id}.json"


def load_image_plan(topic_id: str) -> dict[str, Any] | None:
    path = image_plan_path(topic_id)
    if not path.exists():
        return None
    return load_json(path, None)


def prompt_card_dirs(prompt_type: str) -> list[Path]:
    if prompt_type == "cover":
        return [PROMPT_REPO_COVER_DIR]
    if prompt_type == "illustration":
        return [PROMPT_REPO_ILLUSTRATION_DIR]
    return [PROMPT_REPO_COVER_DIR, PROMPT_REPO_ILLUSTRATION_DIR]


def normalize_list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_prompt_card(path: Path) -> PromptCard | None:
    frontmatter, _ = load_frontmatter_document(path)
    if not frontmatter:
        return None

    card_id = str(frontmatter.get("canonical_id") or path.stem)
    title = str(frontmatter.get("title") or card_id)
    prompt_type = str(frontmatter.get("prompt_type") or "")
    recommended_for = str(frontmatter.get("recommended_for") or "")
    source_origin = str(frontmatter.get("source_origin") or "manual")
    source_url = str(frontmatter.get("source_url") or "")
    model_family = normalize_list_field(frontmatter.get("model_family"))
    color_palette = normalize_list_field(frontmatter.get("color_palette"))
    failure_modes = normalize_list_field(frontmatter.get("failure_modes"))
    tags = [x.lower() for x in normalize_list_field(frontmatter.get("tags"))]
    prompt_positive = str(frontmatter.get("prompt_positive") or "")
    prompt_negative = str(frontmatter.get("prompt_negative") or "")
    if not card_id or not prompt_type or not recommended_for or not prompt_positive:
        return None

    return PromptCard(
        card_id=card_id,
        title=title,
        prompt_type=prompt_type,
        recommended_for=recommended_for,
        source_origin=source_origin,
        source_url=source_url,
        model_family=model_family,
        text_policy=str(frontmatter.get("text_policy") or "no_text"),
        visual_style=str(frontmatter.get("visual_style") or ""),
        subject_pattern=str(frontmatter.get("subject_pattern") or ""),
        mood=str(frontmatter.get("mood") or ""),
        color_palette=color_palette,
        aspect_ratio=str(frontmatter.get("aspect_ratio") or "16:9"),
        resolution=str(frontmatter.get("resolution") or "1K"),
        prompt_positive=prompt_positive,
        prompt_negative=prompt_negative,
        quality_notes=str(frontmatter.get("quality_notes") or ""),
        failure_modes=failure_modes,
        tags=tags,
        path=path,
    )


def load_prompt_cards(prompt_type: str) -> list[PromptCard]:
    cards: list[PromptCard] = []
    for directory in prompt_card_dirs(prompt_type):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            card = parse_prompt_card(path)
            if card:
                cards.append(card)
    return cards


def extract_markdown_title(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_markdown_bullets(markdown: str, limit: int = 3) -> list[str]:
    bullets = [
        line.replace("-", "", 1).replace("*", "", 1).strip()
        for line in markdown.splitlines()
        if re.match(r"^[-*]\s+", line.strip())
    ]
    return [x for x in bullets if x][:limit]


def extract_markdown_sections(markdown: str, limit: int = 4) -> list[str]:
    sections = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            sections.append(stripped[3:].strip())
        if len(sections) >= limit:
            break
    return sections


def extract_markdown_summary(markdown: str, limit: int = 220) -> str:
    summary_lines: list[str] = []
    for line in markdown.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        if re.match(r"^[-*]\s+", cleaned):
            continue
        summary_lines.append(cleaned)
    summary = " ".join(summary_lines).strip()
    if not summary:
        summary = markdown.replace("\n", " ").strip()
    return summary[:limit].strip()


def guidance_for_risk_flag(flag: str) -> str:
    if any(token in flag for token in ["英語圏", "英语圈", "サンプルバイアス", "样本偏差"]):
        return "建议补 1 条日文平台证据，或在文中明确样本主要来自英语圈。"
    if any(token in flag for token in ["收益", "誇張", "谨慎", "成果表現"]):
        return "建议删掉绝对化收益表述，改成条件化或案例化表达。"
    if any(token in flag for token in ["搜索", "品質", "质量不稳定"]):
        return "建议再补 1 条可复查证据，避免把单一搜索结果写成定论。"
    if any(token in flag for token in ["平台", "风格差异", "文体差"]):
        return "建议补一段平台差异说明，避免把别的平台经验直接套到 note。"
    if any(token in flag for token in ["时间投入", "投入低估", "時間投入"]):
        return "建议在正文里补充执行成本与适用前提，避免预期失真。"
    if any(token in flag for token in ["過度な自動化", "过度自动化"]):
        return "建议补一句人工兜底与审批边界，避免把流程写成无脑全自动。"
    if any(token in flag for token in ["アカウント安全", "账号安全"]):
        return "建议补一段账号安全提醒，明确哪些动作必须人工确认。"
    return f"建议在正文里明确“{flag}”对应的适用范围或限制条件。"


def guidance_for_risk_flags(risk_flags: list[str]) -> str:
    guidance: list[str] = []
    for flag in risk_flags:
        suggestion = guidance_for_risk_flag(flag)
        if suggestion not in guidance:
            guidance.append(suggestion)
        if len(guidance) >= 2:
            break
    return "；".join(guidance)


def build_review_recommendation(draft: dict[str, Any], channel: str) -> tuple[str, str]:
    if channel == "note":
        note_draft = str(draft.get("note_draft") or "")
        title = extract_markdown_title(note_draft)
        sections = extract_markdown_sections(note_draft)
        summary = extract_markdown_summary(note_draft)
        if not title:
            return ("revise", "标题为空，先补出明确标题再提审。")
        if len(sections) < 3:
            return ("revise", "结构偏薄，至少补足导入、方法/步骤、总结三段再提审。")
        if len(summary) < 80:
            return ("revise", "摘要信息量太薄，先把核心观点和具体动作写实再提审。")
        localized_flags = localize_risk_flags_for_note(draft.get("topic_snapshot", {}).get("risk_flags", []))
        if localized_flags:
            return ("risky", guidance_for_risk_flags(localized_flags))
        return ("approve", "可直接推进审批，发布前只需确认标题、封面与正文一致。")

    risk_flags = draft.get("topic_snapshot", {}).get("risk_flags", [])
    if risk_flags:
        return ("risky", guidance_for_risk_flags(risk_flags))
    return ("approve", "可直接推进审批。")


def infer_article_type(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if any(word in text for word in ["入門", "初心者", "完全保存版", "ガイド", "ステップ", "手順", "how", "guide"]):
        return "tutorial"
    if any(word in text for word in ["ビジネス", "創業", "副業", "収益", "growth", "content", "運営"]):
        return "business"
    if any(word in text for word in ["ai", "gpt", "chatgpt", "claude", "automation", "workflow", "技術", "自動化"]):
        return "tech"
    return "general"


def derive_prompt_tags(
    title: str,
    summary: str,
    risk_flags: list[str],
    source: str,
) -> list[str]:
    text = f"{title} {summary} {source}".lower()
    tags = {"note", "editorial"}
    mapping = {
        "tech": ["ai", "gpt", "chatgpt", "claude", "automation", "workflow", "技術", "自動化"],
        "tutorial": ["入門", "初心者", "完全保存版", "ステップ", "ガイド", "how"],
        "business": ["ビジネス", "収益", "副業", "growth", "運営", "creator"],
        "community": ["reddit", "x", "community", "trend", "forum"],
    }
    for tag, markers in mapping.items():
        if any(marker in text for marker in markers):
            tags.add(tag)

    if any("reddit" in flag.lower() for flag in risk_flags):
        tags.add("community")
    return sorted(tags)


def render_prompt_template(template: str, variables: dict[str, str]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def card_ref(path: Path) -> str:
    try:
        return hub_rel(path)
    except ValueError:
        return str(path)


def content_manifest_path(topic_id: str) -> Path:
    return CONTENT_MANIFEST_DIR / f"{topic_id}.json"


def illustration_output_dir(topic_id: str) -> Path:
    return WORKSPACE / "output" / "content-pipeline" / "illustrations" / topic_id


def illustration_output_path(topic_id: str, index: int) -> Path:
    return illustration_output_dir(topic_id) / f"illustration-{index + 1:02d}.png"


def split_note_draft_blocks(note_draft: str) -> list[dict[str, str]]:
    lines = note_draft.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    blocks: list[dict[str, str]] = []
    current_heading = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current_heading
        text = "\n".join(buffer).strip()
        if text:
            blocks.append({"type": "text", "section_heading": current_heading, "markdown": text})
        buffer = []

    for line in lines:
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            buffer.append(line)
            continue
        buffer.append(line)

    flush()
    return blocks


def build_content_manifest_for_draft(
    draft: dict[str, Any],
    image_plan: dict[str, Any],
    cover_path: Path | None,
    illustration_paths: list[Path],
) -> Path:
    topic_id = str(draft.get("topic_id") or "")
    if not topic_id:
        raise RuntimeError("content_manifest_requires_topic_id")

    blocks = split_note_draft_blocks(draft.get("note_draft", ""))
    if not blocks:
        raise RuntimeError("content_manifest_requires_note_draft")

    illustration_recs = image_plan.get("illustration_recommendations", [])
    content_blocks: list[dict[str, Any]] = []
    inserted = 0
    for block in blocks:
        content_blocks.append(block)
        if inserted >= min(2, len(illustration_recs), len(illustration_paths)):
            continue
        section_heading = block.get("section_heading", "")
        if not section_heading:
            continue
        rec = illustration_recs[inserted]
        image_path = illustration_paths[inserted]
        content_blocks.append(
            {
                "type": "image",
                "section_heading": section_heading,
                "image_path": str(image_path),
                "image_role": "illustration",
                "source_card_id": rec.get("card_id", ""),
                "target_section": rec.get("target_section", ""),
            }
        )
        inserted += 1

    payload = {
        "topic_id": topic_id,
        "title": extract_markdown_title(draft.get("note_draft", "")),
        "cover_image": str(cover_path) if cover_path and cover_path.exists() else "",
        "content_blocks": content_blocks,
    }
    path = content_manifest_path(topic_id)
    save_json(path, payload)
    return path


def load_prompt_source_seeds() -> list[dict[str, Any]]:
    payload = load_json(PROMPT_REPO_SOURCE_FILE, [])
    if isinstance(payload, list):
        return payload
    return []


def prompt_intake_card_path(day: str, seed: dict[str, Any], index: int) -> Path:
    origin = str(seed.get("source_origin", "manual")).strip().lower()
    slug = str(seed.get("slug", f"seed-{index:02d}")).strip().lower()
    return PROMPT_REPO_INTAKE_DIR / f"{day.replace('-', '')}-{origin}-{slug}.md"


def extract_html_title(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(match.group(1)).strip()


def build_prompt_intake_body(seed: dict[str, Any], fetch_status: str, title: str, snippet: str) -> str:
    return (
        "# 候选摘要\n\n"
        f"- source_origin: {seed.get('source_origin', '')}\n"
        f"- source_url: {seed.get('source_url', '')}\n"
        f"- fetch_status: {fetch_status}\n"
        f"- candidate_title: {title or seed.get('label', '')}\n\n"
        "## Prompt 片段\n\n"
        f"{snippet or '需人工补全 prompt 正文'}\n\n"
        "## 后续动作\n\n"
        "- 人工审阅是否值得升格为正式 prompt 卡\n"
        "- 若页面只抓到标题，补录 prompt 要点与适用场景\n"
    )


def run_generate_from_draft(
    *,
    draft_path: Path,
    output_path: Path,
    prompt_type: str = "cover",
    index: int = 0,
) -> tuple[bool, str]:
    cmd = [
        "node",
        str(ROOT / "workspace/tools/note-image-generator/generate_from_draft.js"),
        str(draft_path),
        str(output_path),
        "--prompt-type",
        prompt_type,
        "--index",
        str(index),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0 and output_path.exists(), output.strip()


def source_family_from_url(url: str) -> str:
    url_lower = url.lower()
    if "x.com" in url_lower or "twitter.com" in url_lower:
        return "x"
    if "reddit.com" in url_lower:
        return "reddit"
    if "xiaohongshu.com" in url_lower:
        return "xiaohongshu"
    if "note.com" in url_lower:
        return "note"
    if "qiita.com" in url_lower:
        return "qiita"
    if "zenn.dev" in url_lower:
        return "zenn"
    if "hatenablog" in url_lower or "b.hatena.ne.jp" in url_lower:
        return "hatebu"
    return "web"


def source_family_from_candidate(source: str, urls: list[str]) -> str:
    if urls:
        return source_family_from_url(urls[0])
    if source.startswith("x_"):
        return "x"
    if source.startswith("reddit"):
        return "reddit"
    if source.startswith("xiaohongshu"):
        return "xiaohongshu"
    if source.startswith("note"):
        return "note"
    return source


def build_frontmatter(
    *,
    title: str,
    kind: str,
    stage: str,
    canonical_id: str,
    source_urls: list[str],
    derived_from: list[str],
    source_role: list[str],
    platform_targets: list[str] | None = None,
    language_targets: list[str] | None = None,
    tags: list[str] | None = None,
    status: str = "active",
    origin_platform: str = "content-hub",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "kind": kind,
        "stage": stage,
        "canonical_id": canonical_id,
        "origin_platform": origin_platform,
        "source_role": source_role,
        "platform_targets": platform_targets or ["note"],
        "language_targets": language_targets or ["ja"],
        "source_urls": source_urls,
        "derived_from": derived_from,
        "tags": tags or [],
        "status": status,
        "created_at": iso_now(),
        "updated_at": iso_now(),
    }
    if extra:
        payload.update(extra)
    return payload


def source_card_path(canonical_id: str, url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return HUB_SOURCES_DIR / f"{canonical_id}--source-{digest}.md"


def insight_card_path(canonical_id: str) -> Path:
    return HUB_INSIGHTS_DIR / f"{canonical_id}--insight.md"


def topic_card_path(canonical_id: str) -> Path:
    return HUB_TOPICS_DIR / f"{canonical_id}--topic.md"


def production_card_path(canonical_id: str, stage: str, channel: str) -> Path:
    stage_dirs = {
        "outline": HUB_PRODUCTION_OUTLINE_DIR,
        "draft": HUB_PRODUCTION_DRAFT_DIR,
        "final": HUB_PRODUCTION_FINAL_DIR,
    }
    return stage_dirs[stage] / f"{canonical_id}--{channel}.md"


def distribution_card_path(canonical_id: str, channel: str) -> Path:
    return HUB_DISTRIBUTION_DIR / f"{canonical_id}--{channel}.md"


def feedback_card_path(canonical_id: str, channel: str) -> Path:
    return HUB_FEEDBACK_DIR / f"{canonical_id}--{channel}.md"


def pattern_card_path(canonical_id: str, channel: str) -> Path:
    return HUB_PATTERNS_DIR / f"{canonical_id}--{channel}.md"


def infer_topic_status(topic: dict[str, Any]) -> tuple[str, list[str]]:
    families = {
        source_family_from_url(url)
        for url in topic.get("evidence_urls", [])
        if isinstance(url, str) and url
    }
    if not families:
        families.add(source_family_from_candidate(topic.get("source", ""), topic.get("evidence_urls", [])))
    tags = sorted(f"source:{family}" for family in families if family)
    status = "active" if len(families) >= 2 else "needs_source_blend"
    return status, tags


def sync_topic_candidate_to_hub(topic: dict[str, Any]) -> None:
    canonical_id = canonical_id_for_topic(topic)
    if not canonical_id:
        return

    evidence_urls = [url for url in topic.get("evidence_urls", []) if isinstance(url, str) and url]
    source_paths: list[Path] = []
    source_families: set[str] = set()
    for index, url in enumerate(evidence_urls, start=1):
        family = source_family_from_url(url)
        source_families.add(family)
        path = source_card_path(canonical_id, url)
        frontmatter = build_frontmatter(
            title=f"{topic.get('angle', canonical_id)}｜来源 {index}",
            kind="source",
            stage="captured",
            canonical_id=canonical_id,
            source_urls=[url],
            derived_from=[],
            source_role=["research"],
            platform_targets=["note"],
            language_targets=["ja"],
            tags=[f"source:{family}", f"candidate:{topic.get('source', 'unknown')}"],
            status="active",
            origin_platform=family,
            extra={
                "audience": topic.get("audience", ""),
                "pain_point": "",
                "core_promise": "",
                "content_angle": topic.get("angle", ""),
                "evidence_bundle": [{"url": url, "family": family}],
            },
        )
        body = (
            "# Summary\n\n"
            f"- candidate_source: {topic.get('source', 'unknown')}\n"
            f"- evidence_url: {url}\n"
            f"- audience_hint: {topic.get('audience', '')}\n\n"
            "## Raw Notes\n\n"
            f"- 保留原始证据链接：{url}\n"
            f"- 当前候选角度：{topic.get('angle', '')}\n\n"
            "## Extraction Candidates\n\n"
            "- 可提炼为观点卡\n"
            "- 可用于选题证据链\n"
        )
        write_hub_card(path, frontmatter, body)
        source_paths.append(path)

    if not source_families:
        source_families.add(source_family_from_candidate(topic.get("source", ""), evidence_urls))

    insight_path = insight_card_path(canonical_id)
    insight_frontmatter = build_frontmatter(
        title=f"{topic.get('angle', canonical_id)}｜观点提炼",
        kind="insight",
        stage="distilled",
        canonical_id=canonical_id,
        source_urls=evidence_urls,
        derived_from=[hub_rel(path) for path in source_paths],
        source_role=["analysis"],
        tags=sorted({f"source:{family}" for family in source_families}),
        status="active",
        extra={
            "audience": topic.get("audience", ""),
            "pain_point": topic.get("audience", ""),
            "core_promise": topic.get("angle", ""),
            "content_angle": topic.get("angle", ""),
            "evidence_bundle": [{"path": hub_rel(path)} for path in source_paths],
        },
    )
    insight_body = (
        "# Insight Summary\n\n"
        f"{topic.get('angle', '')}\n\n"
        "## Core Claim\n\n"
        f"- 目标受众：{topic.get('audience', '')}\n"
        f"- 主题来源：{topic.get('source', '')}\n"
        f"- 当前评分：{topic.get('score', 0)}\n\n"
        "## Supporting Evidence\n\n"
        + "\n".join(f"- {hub_rel(path)}" for path in source_paths)
        + "\n\n## Reuse Notes\n\n"
        "- 可直接进入选题卡\n"
        "- 后续可复用到大纲与终稿\n"
    )
    write_hub_card(insight_path, insight_frontmatter, insight_body)

    topic_status, topic_tags = infer_topic_status(topic)
    topic_path = topic_card_path(canonical_id)
    topic_frontmatter = build_frontmatter(
        title=topic.get("angle", canonical_id),
        kind="topic",
        stage="proposed",
        canonical_id=canonical_id,
        source_urls=evidence_urls,
        derived_from=[hub_rel(insight_path)] + [hub_rel(path) for path in source_paths],
        source_role=["publish"],
        tags=topic_tags + [f"candidate:{topic.get('source', 'unknown')}"],
        status=topic_status,
        extra={
            "audience": topic.get("audience", ""),
            "pain_point": topic.get("audience", ""),
            "core_promise": topic.get("angle", ""),
            "content_angle": topic.get("angle", ""),
            "evidence_bundle": [{"path": hub_rel(path)} for path in source_paths],
            "priority_score": topic.get("score", 0),
        },
    )
    outline_directions = [
        f"从「{topic.get('angle', '')}」切入问题定义",
        "把证据链和受众痛点拆开说明",
        "结尾加入明确的下一步 CTA",
    ]
    topic_body = (
        "# Topic Brief\n\n"
        "## Why Now\n\n"
        f"- source: {topic.get('source', '')}\n"
        f"- score: {topic.get('score', 0)}\n"
        f"- audience: {topic.get('audience', '')}\n"
        f"- status: {topic_status}\n\n"
        "## Evidence\n\n"
        + "\n".join(f"- {hub_rel(path)}" for path in source_paths)
        + "\n\n## Outline Directions\n\n"
        + "\n".join(f"- {line}" for line in outline_directions)
        + "\n"
    )
    write_hub_card(topic_path, topic_frontmatter, topic_body)


def sync_topics_to_hub(topics_payload: dict[str, Any]) -> None:
    for candidate in topics_payload.get("candidates", []):
        sync_topic_candidate_to_hub(candidate)


def sync_production_card(draft: dict[str, Any], stage: str, channel: str) -> Path | None:
    topic = draft.get("topic_snapshot") or {}
    canonical_id = draft.get("topic_id") or canonical_id_for_topic(topic)
    if not canonical_id:
        return None

    topic_path = topic_card_path(canonical_id)
    derived_from = [hub_rel(topic_path)] if topic_path.exists() else []
    body = "# Production Brief\n\n"
    stage_title = stage
    stage_status = draft.get("workflow_status", {}).get(channel, draft.get("status", "drafted"))
    review_feedback = latest_review_feedback(draft, channel)

    if stage == "outline":
        content = draft.get("note_outline", [])
        body += (
            "## Input Context\n\n"
            f"- canonical_id: {canonical_id}\n"
            f"- channel: {channel}\n"
            f"- source_count: {len(topic.get('evidence_urls', []))}\n\n"
            "## Output\n\n"
            + "\n".join(
                f"- {section.get('section', '')}: {', '.join(section.get('points', []))}"
                for section in content
            )
            + "\n\n## Next Handoff\n\n"
            "- 等待确认后生成 draft\n"
        )
        if review_feedback:
            body += f"\n## Latest Review Feedback\n\n- {review_feedback}\n"
    elif stage == "draft":
        if channel == "note":
            body += (
                "## Input Context\n\n"
                f"- canonical_id: {canonical_id}\n"
                f"- source_count: {len(topic.get('evidence_urls', []))}\n\n"
                "## Output\n\n"
                f"{draft.get('note_draft', '')}\n\n"
                "## Next Handoff\n\n"
                "- 推送审批卡并等待审核\n"
            )
            if review_feedback:
                body += f"\n## Latest Review Feedback\n\n- {review_feedback}\n"
            outline_path = production_card_path(canonical_id, "outline", "note")
            if outline_path.exists():
                derived_from.insert(0, hub_rel(outline_path))
        else:
            x_posts = draft.get("x_posts", [])
            lines: list[str] = []
            for index, post in enumerate(x_posts, start=1):
                lines.append(f"### Slice {index}")
                lines.append(post.get("text", ""))
                lines.append("")
            body += (
                "## Input Context\n\n"
                f"- canonical_id: {canonical_id}\n"
                f"- source_count: {len(topic.get('evidence_urls', []))}\n\n"
                "## Output\n\n"
                + "\n".join(lines).rstrip()
                + "\n\n## Next Handoff\n\n- 推送审批卡并等待审核\n"
            )
    else:
        draft_path = production_card_path(canonical_id, "draft", channel)
        if draft_path.exists():
            derived_from.insert(0, hub_rel(draft_path))
        content = draft.get("note_draft", "") if channel == "note" else "\n\n".join(
            post.get("text", "") for post in draft.get("x_posts", [])
        )
        body += (
            "## Input Context\n\n"
            f"- canonical_id: {canonical_id}\n"
            f"- approved_channel: {channel}\n\n"
            "## Output\n\n"
            f"{content}\n\n"
            "## Next Handoff\n\n"
            "- 进入发布包与平台分发\n"
        )
        if review_feedback:
            body += f"\n## Latest Review Feedback\n\n- {review_feedback}\n"

    frontmatter = build_frontmatter(
        title=f"{topic.get('angle', canonical_id)}｜{channel} {stage_title}",
        kind="production",
        stage=stage,
        canonical_id=canonical_id,
        source_urls=topic.get("evidence_urls", []),
        derived_from=derived_from,
        source_role=["publish"],
        platform_targets=[channel],
        language_targets=["ja"],
        tags=[f"channel:{channel}", f"stage:{stage}"],
        status=stage_status,
        extra={
            "audience": topic.get("audience", ""),
            "pain_point": topic.get("audience", ""),
            "core_promise": topic.get("angle", ""),
            "content_angle": topic.get("angle", ""),
            "evidence_bundle": topic.get("evidence_urls", []),
            "channel": channel,
        },
    )
    return write_hub_card(production_card_path(canonical_id, stage, channel), frontmatter, body)


def sync_distribution_card(
    topic_id: str,
    channel: str,
    approval_status: str,
    *,
    package_ref: str = "",
    publish_target: str = "",
    draft: dict[str, Any] | None = None,
    review_note: str = "",
    reviewed_via: str = "",
    review_message_id: str = "",
) -> Path | None:
    draft = draft or load_draft(topic_id)
    if not draft:
        return None

    topic = draft.get("topic_snapshot") or {}
    canonical_id = topic_id or canonical_id_for_topic(topic)
    if not canonical_id:
        return None

    if channel == "x" and draft.get("x_posts"):
        sync_production_card(draft, "draft", "x")
    if channel == "note" and draft.get("note_draft"):
        sync_production_card(draft, "draft", "note")
        if approval_status in {"approved", "published"}:
            sync_production_card(draft, "final", "note")

    final_path = production_card_path(canonical_id, "final", channel)
    draft_path = production_card_path(canonical_id, "draft", channel)
    topic_path = topic_card_path(canonical_id)
    derived_from: list[str] = []
    for candidate in [final_path, draft_path, topic_path]:
        if candidate.exists():
            derived_from.append(hub_rel(candidate))

    frontmatter = build_frontmatter(
        title=f"{topic.get('angle', canonical_id)}｜{channel} distribution",
        kind="distribution",
        stage="packaged",
        canonical_id=canonical_id,
        source_urls=topic.get("evidence_urls", []),
        derived_from=derived_from,
        source_role=["publish"],
        platform_targets=[channel],
        language_targets=["ja"],
        tags=[f"channel:{channel}", "distribution"],
        status=approval_status,
        extra={
            "channel": channel,
            "approval_status": approval_status,
            "approval_target": "discord note review" if channel == "note" else "approval queue",
            "publish_target": publish_target or ("note.com" if channel == "note" else "x.com"),
            "package_ref": package_ref,
            "review_note": review_note,
            "reviewed_via": reviewed_via,
            "review_message_id": review_message_id,
        },
    )
    summary = draft.get("note_draft", "")[:220] if channel == "note" else (
        draft.get("x_posts", [{}])[0].get("text", "")[:220]
    )
    body = (
        "# Distribution Package\n\n"
        "## Package Summary\n\n"
        f"- channel: {channel}\n"
        f"- approval_status: {approval_status}\n"
        f"- package_ref: {package_ref or 'n/a'}\n"
        f"- summary: {summary}\n\n"
        "## Approval Notes\n\n"
        f"- 审批动作面：{'Discord note发布组 reply' if channel == 'note' else 'approval channel'}\n"
        f"- review_note: {review_note or 'none'}\n"
        f"- reviewed_via: {reviewed_via or 'n/a'}\n"
        f"- review_message_id: {review_message_id or 'n/a'}\n\n"
        "## Publish Notes\n\n"
        f"- publish_target: {publish_target or ('note.com' if channel == 'note' else 'x.com')}\n"
    )
    return write_hub_card(distribution_card_path(canonical_id, channel), frontmatter, body)


def performance_label_for_metrics(metrics_snapshot: dict[str, Any]) -> str:
    impressions = parse_float(str(metrics_snapshot.get("impressions_24h", "0") or "0"))
    engagement = parse_float(str(metrics_snapshot.get("engagement_rate", "0") or "0"))
    if impressions <= 0 and engagement <= 0:
        return "pending"
    if engagement >= 0.08 or impressions >= 5000:
        return "winner"
    if engagement >= 0.05 or impressions >= 1000:
        return "strong"
    return "normal"


def maybe_sync_pattern_card(
    topic_id: str,
    channel: str,
    feedback_path: Path,
    feedback_frontmatter: dict[str, Any],
    draft: dict[str, Any],
) -> bool:
    label = feedback_frontmatter.get("performance_label", "pending")
    if label not in {"strong", "winner"}:
        return False

    topic = draft.get("topic_snapshot") or {}
    canonical_id = topic_id or canonical_id_for_topic(topic)
    if not canonical_id:
        return False

    frontmatter = build_frontmatter(
        title=f"{topic.get('angle', canonical_id)}｜可复用模式",
        kind="pattern",
        stage="proven",
        canonical_id=canonical_id,
        source_urls=topic.get("evidence_urls", []),
        derived_from=[hub_rel(feedback_path)],
        source_role=["analysis"],
        platform_targets=[channel],
        language_targets=["ja"],
        tags=[f"channel:{channel}", f"performance:{label}", "pattern"],
        status="active",
        extra={
            "performance_label": label,
            "metrics_snapshot": feedback_frontmatter.get("metrics_snapshot", {}),
        },
    )
    body = (
        "# Pattern Summary\n\n"
        f"- label: {label}\n"
        f"- title: {topic.get('angle', canonical_id)}\n"
        f"- source_feedback: {hub_rel(feedback_path)}\n\n"
        "## Reusable Structure\n\n"
        "- 继续复用当前主题切入角度\n"
        "- 保留现有 CTA 与审批后再发布的节奏\n"
        "- 将后续高表现数据继续回流到本卡\n"
    )
    write_hub_card(pattern_card_path(canonical_id, channel), frontmatter, body)
    return True


def sync_feedback_card(
    topic_id: str,
    channel: str,
    *,
    published_url: str = "",
    metrics_snapshot: dict[str, Any] | None = None,
    draft: dict[str, Any] | None = None,
) -> Path | None:
    draft = draft or load_draft(topic_id)
    if not draft:
        return None

    topic = draft.get("topic_snapshot") or {}
    canonical_id = topic_id or canonical_id_for_topic(topic)
    if not canonical_id:
        return None

    distribution_path = distribution_card_path(canonical_id, channel)
    derived_from = [hub_rel(distribution_path)] if distribution_path.exists() else []
    metrics_snapshot = metrics_snapshot or {}
    performance_label = performance_label_for_metrics(metrics_snapshot)
    learnings = [
        "保留 source -> topic -> production -> distribution -> feedback 的完整链路",
        "优先复用已验证的内容结构，再根据平台反馈迭代",
    ]

    frontmatter = build_frontmatter(
        title=f"{topic.get('angle', canonical_id)}｜{channel} feedback",
        kind="feedback",
        stage="reviewed",
        canonical_id=canonical_id,
        source_urls=topic.get("evidence_urls", []),
        derived_from=derived_from,
        source_role=["feedback"],
        platform_targets=[channel],
        language_targets=["ja"],
        tags=[f"channel:{channel}", f"performance:{performance_label}", "feedback"],
        status="active",
        extra={
            "channel": channel,
            "published_url": published_url,
            "metrics_snapshot": metrics_snapshot,
            "performance_label": performance_label,
            "learnings": learnings,
            "fed_back_to_patterns": False,
        },
    )
    body = (
        "# Feedback Summary\n\n"
        "## Publish Result\n\n"
        f"- channel: {channel}\n"
        f"- published_url: {published_url or 'pending'}\n\n"
        "## Metrics\n\n"
        f"- metrics_snapshot: {json.dumps(metrics_snapshot, ensure_ascii=False)}\n"
        f"- performance_label: {performance_label}\n\n"
        "## Learnings\n\n"
        + "\n".join(f"- {line}" for line in learnings)
        + "\n"
    )
    feedback_path = write_hub_card(feedback_card_path(canonical_id, channel), frontmatter, body)
    fed_back = maybe_sync_pattern_card(topic_id, channel, feedback_path, frontmatter, draft)
    if fed_back:
        frontmatter["fed_back_to_patterns"] = True
        body = body.rstrip() + "\n- 已回流到 06-复盘与模式/模式库\n"
        write_hub_card(feedback_path, frontmatter, body)
    return feedback_path


def cmd_ensure_dirs(_: argparse.Namespace) -> int:
    ensure_dirs()
    print("content_pipeline_dirs_ready")
    return 0


def cmd_validate_env(_: argparse.Namespace) -> int:
    env = parse_env()
    ok, missing = note_env_report(env)
    if ok:
        print("note_env_ok keys=NOTE_PUBLISH_MODE,NOTE_EMAIL,NOTE_PASSWORD,NOTE_AUTHOR_URL")
        return 0
    print(f"note_env_missing keys={','.join(missing)}")
    return 1


def cmd_xhs_prewarm(args: argparse.Namespace) -> int:
    ensure_dirs()
    feed_candidates, feed_health = _fetch_xiaohongshu_feed_candidates()
    ready, health = _check_xiaohongshu_health()

    health_details = health.get("details") if isinstance(health.get("details"), dict) else {}
    health["details"] = {
        **(health_details or {}),
        "prewarm_attempted": True,
        "prewarm_items": len(feed_candidates),
        "prewarm_feed_health": feed_health,
    }

    read_health = health.get("read_health") if isinstance(health.get("read_health"), dict) else {}
    auth_health = health.get("auth_health") if isinstance(health.get("auth_health"), dict) else {}
    summary = (
        "xhs_prewarm_done "
        f"ready={'true' if ready else 'false'} "
        f"status={health.get('status', 'unknown')} "
        f"read={read_health.get('status', 'unknown')} "
        f"auth={auth_health.get('status', 'unknown')} "
        f"items={len(feed_candidates)}"
    )

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "ready": ready,
                    "health": health,
                    "feed_items": len(feed_candidates),
                    "feed_health": feed_health,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(summary)

    return 0 if ready or bool(feed_candidates) else 1


def build_topic_templates() -> list[dict[str, Any]]:
    return [
        {
            "source": "x_signal",
            "angle": "从 3 个真实工作流拆解 OpenClaw 的回本路径",
            "audience": "会用 LLM 聊天但不会落地工作流的创作者",
            "evidence_urls": [
                "https://x.com/search?q=openclaw",
                "https://x.com/search?q=vibe%20orchestration",
            ],
            "risk_flags": ["样本偏差", "收益描述需谨慎"],
        },
        {
            "source": "note_comment",
            "angle": "为什么 90% 的 AI 自动化最后都卡在审批环节",
            "audience": "想做副业自动化的个人开发者",
            "evidence_urls": [
                "https://note.com/",
                "https://x.com/search?q=ai%20automation%20approval",
            ],
            "risk_flags": ["概念泛化", "缺案例对照"],
        },
        {
            "source": "industry_trend",
            "angle": "内容业务如何从单人创作升级为多代理流水线",
            "audience": "运营负责人和小团队主理人",
            "evidence_urls": [
                "https://x.com/search?q=agentic%20workflow",
                "https://x.com/search?q=creator%20business",
            ],
            "risk_flags": ["术语误解", "执行门槛预期过高"],
        },
        {
            "source": "user_pain",
            "angle": "从选题到发布，哪些步骤必须人工把关",
            "audience": "已有内容产能但转化不稳定的运营者",
            "evidence_urls": [
                "https://x.com/search?q=content%20approval%20workflow",
                "https://note.com/",
            ],
            "risk_flags": ["过度自动化风险", "账号安全风险"],
        },
        {
            "source": "case_study",
            "angle": "一周 5 条 X + 1 篇 note 的稳健执行法",
            "audience": "日本市场内容创业者",
            "evidence_urls": [
                "https://x.com/search?q=note%20x%20growth",
                "https://x.com/search?q=content%20cadence",
            ],
            "risk_flags": ["时间投入低估", "选题重复"],
        },
        {
            "source": "x_signal",
            "angle": "如何设计可复用的审批卡，降低误发概率",
            "audience": "需要多人协同的增长团队",
            "evidence_urls": [
                "https://x.com/search?q=approval%20queue",
                "https://x.com/search?q=content%20ops",
            ],
            "risk_flags": ["流程过重", "反馈延迟"],
        },
        {
            "source": "industry_trend",
            "angle": "从流量到线索：内容 KPI 如何接到成交",
            "audience": "以私信咨询为主要转化路径的创作者",
            "evidence_urls": [
                "https://x.com/search?q=lead%20capture%20content",
                "https://x.com/search?q=creator%20funnel",
            ],
            "risk_flags": ["归因困难", "指标误读"],
        },
    ]


def _run_cli(cmd: list[str], timeout: int = 30) -> str:
    """Run a CLI command and return stdout. Raises on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"cmd {cmd} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _run_json_cli(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    """Run a CLI command that is expected to emit JSON to stdout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": 124,
            "json": {
                "success": False,
                "code": "SUBPROCESS_TIMEOUT",
                "error": "subprocess timed out",
                "details": str(exc),
            },
            "stdout": exc.stdout.strip() if exc.stdout else "",
            "stderr": exc.stderr.strip() if exc.stderr else "",
            "error": str(exc),
        }
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    payload: Any = None
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "json": payload,
        "stdout": stdout,
        "stderr": stderr,
        "error": stderr or stdout,
    }


def _make_component_health(
    status: str,
    *,
    stage: str,
    error_code: str = "",
    message: str = "",
    details: Any | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "stage": stage,
        "error_code": error_code,
        "message": message,
        "checked_at": iso_now(),
    }
    if details is not None:
        payload["details"] = details
    return payload


def _make_source_health(
    status: str,
    *,
    stage: str,
    error_code: str = "",
    message: str = "",
    details: Any | None = None,
    read_health: dict[str, Any] | None = None,
    auth_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _make_component_health(
        status,
        stage=stage,
        error_code=error_code,
        message=message,
        details=details,
    )
    payload["read_health"] = read_health or _make_component_health(
        status,
        stage=stage,
        error_code=error_code,
        message=message,
        details=details,
    )
    payload["auth_health"] = auth_health or _make_component_health(
        "not_required",
        stage="auth",
        message="auth not separately evaluated",
    )
    return payload


def _fetch_url_bytes(url: str, timeout: int = FEED_TIMEOUT) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) OpenClaw/2026.3"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def verify_note_post_by_title(author_url: str, expected_title: str, timeout: int = 20) -> str:
    if not author_url:
        return ""
    try:
        raw = _fetch_url_bytes(author_url, timeout=timeout)
    except Exception:  # noqa: BLE001
        return ""

    text = raw.decode("utf-8", errors="ignore")
    escaped_title = expected_title.strip()
    if not escaped_title:
        return ""

    title_pattern = re.escape(escaped_title)
    link_patterns = [
        rf'href="(https://note\.com/[^"]+/n/[A-Za-z0-9]+)"[^>]*>[^<]*{title_pattern}',
        rf'href="(/[^"]+/n/[A-Za-z0-9]+)"[^>]*>[^<]*{title_pattern}',
    ]
    for pattern in link_patterns:
        match = re.search(pattern, text)
        if match:
            href = html.unescape(match.group(1))
            if href.startswith("http"):
                return href
            return f"https://note.com{href}"

    loose_matches = re.findall(r'href="(/[^"]+/n/[A-Za-z0-9]+)"', text)
    for href in loose_matches:
        if escaped_title in text:
            return f"https://note.com{href}"
    return ""


def _parse_feed_items(raw: bytes, limit: int = FEED_ITEM_LIMIT) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise RuntimeError(f"feed_parse_failed: {exc}") from exc

    items: list[dict[str, str]] = []
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    if root.tag.endswith("rss") or root.tag.endswith("RDF"):
        feed_items = root.findall("./channel/item") or root.findall(".//item")
        for item in feed_items[:limit]:
            title = html.unescape((item.findtext("title") or "").strip())
            link = html.unescape((item.findtext("link") or "").strip())
            published = (
                (item.findtext("pubDate") or "").strip()
                or (item.findtext("dc:date", namespaces=ns) or "").strip()
            )
            summary = html.unescape((item.findtext("description") or "").strip())
            if title and link:
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "published": published,
                        "summary": summary,
                    }
                )
        return items

    feed_entries = root.findall("atom:entry", ns) or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for entry in feed_entries[:limit]:
        title = html.unescape((entry.findtext("atom:title", default="", namespaces=ns) or "").strip())
        published = (
            (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
            or (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
        )
        summary = html.unescape(
            (
                entry.findtext("atom:summary", default="", namespaces=ns)
                or entry.findtext("atom:content", default="", namespaces=ns)
                or ""
            ).strip()
        )
        link = ""
        for link_node in entry.findall("atom:link", ns):
            href = link_node.attrib.get("href", "").strip()
            rel = link_node.attrib.get("rel", "alternate").strip()
            if href and rel in {"alternate", ""}:
                link = href
                break
        if not link:
            first_link = entry.find("atom:link", ns)
            if first_link is not None:
                link = first_link.attrib.get("href", "").strip()
        if title and link:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "published": published,
                    "summary": summary,
                }
            )
    return items


def _build_feed_candidates(
    *,
    source: str,
    prefix: str,
    items: list[dict[str, str]],
    audience: str,
    risk_flags: list[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        title = item.get("title", "").strip()
        link = item.get("link", "").strip()
        if not title or not link:
            continue
        candidates.append(
            {
                "source": source,
                "angle": f"[{prefix}] {title}",
                "audience": audience,
                "evidence_urls": [link],
                "risk_flags": risk_flags,
                "engagement": max(90 - index * 8, 24),
            }
        )
    return candidates


def _build_japanese_feed_configs(env: dict[str, str]) -> list[dict[str, Any]]:
    note_author_url = env.get("NOTE_AUTHOR_URL", "").strip().rstrip("/")
    note_feed_url = f"{note_author_url}/rss" if note_author_url.startswith("http") else ""
    return [
        {
            "key": "note",
            "url": note_feed_url,
            "source": "note_feed",
            "prefix": "note",
            "audience": "note を読む日本の個人クリエイターと運営者",
            "risk_flags": ["自分の既存論点に寄りやすい"],
        },
        {
            "key": "zenn",
            "url": "https://zenn.dev/topics/ai/feed",
            "source": "zenn_feed",
            "prefix": "Zenn",
            "audience": "Zenn で技術情報を追う日本の開発者",
            "risk_flags": ["技術寄りに偏りやすい"],
        },
        {
            "key": "qiita",
            "url": "https://qiita.com/tags/AI/feed",
            "source": "qiita_feed",
            "prefix": "Qiita",
            "audience": "Qiita で実装知見を追う日本の開发者",
            "risk_flags": ["実装ノウハウに偏りやすい"],
        },
        {
            "key": "hatebu",
            "url": "https://b.hatena.ne.jp/hotentry/it.rss",
            "source": "hatebu_feed",
            "prefix": "はてブ",
            "audience": "はてなブックマークで話題を追う日本のIT読者",
            "risk_flags": ["話題性が強くノイズも混ざる"],
        },
    ]


def _fetch_feed_candidates(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = str(config.get("url", "") or "").strip()
    key = str(config.get("key", "feed"))
    if not url:
        return [], _make_source_health(
            "unconfigured",
            stage="feed",
            error_code="MISSING_URL",
            message=f"{key} feed url is not configured",
        )

    try:
        raw = _fetch_url_bytes(url)
        items = _parse_feed_items(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
        return [], _make_source_health(
            "feed_failed",
            stage="feed",
            error_code=type(exc).__name__.upper(),
            message=str(exc),
            details={"url": url},
        )

    candidates = _build_feed_candidates(
        source=str(config["source"]),
        prefix=str(config["prefix"]),
        items=items,
        audience=str(config["audience"]),
        risk_flags=list(config.get("risk_flags", [])),
    )
    if not candidates:
        return [], _make_source_health(
            "empty",
            stage="feed",
            message="feed fetched but no usable items were found",
            details={"url": url},
        )

    return candidates, _make_source_health(
        "ok",
        stage="feed",
        message=f"feed fetched: {len(candidates)} items",
        details={"url": url, "items_collected": len(candidates)},
    )


def _extract_xiaohongshu_feeds_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if payload.get("success") is False:
            return []
        data = payload.get("data", {})
        if isinstance(data, dict):
            feeds = data.get("feeds", [])
            if isinstance(feeds, list):
                return feeds
        if isinstance(payload.get("feeds"), list):
            return payload["feeds"]
    return []


def _parse_engagement_number(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        try:
            return max(int(float(value)), 0)
        except (TypeError, ValueError):
            return default

    text = str(value).strip().lower()
    if not text:
        return default

    text = text.replace(",", "").replace("+", "")
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("千"):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith("k"):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1000000
        text = text[:-1]

    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return default

    try:
        return max(int(float(match.group(0)) * multiplier), 0)
    except (TypeError, ValueError):
        return default


def _load_xiaohongshu_feeds_cache() -> dict[str, Any] | None:
    payload = load_json(XHS_FEEDS_CACHE_FILE, None)
    if not isinstance(payload, dict):
        return None

    cached_at_raw = str(payload.get("cached_at", "") or "").strip()
    feeds_payload = payload.get("payload")
    if not cached_at_raw or not isinstance(feeds_payload, dict):
        return None

    try:
        cached_at = datetime.fromisoformat(cached_at_raw)
    except ValueError:
        return None

    age = now_jst() - cached_at.astimezone(TZ)
    if age > timedelta(hours=XHS_FEEDS_CACHE_MAX_AGE_HOURS):
        return None

    return {
        "cached_at": cached_at.isoformat(),
        "payload": feeds_payload,
        "age_seconds": int(age.total_seconds()),
    }


def _save_xiaohongshu_feeds_cache(payload: dict[str, Any]) -> None:
    save_json(
        XHS_FEEDS_CACHE_FILE,
        {
            "cached_at": iso_now(),
            "payload": payload,
        },
    )


def _run_xiaohongshu_feeds_cli() -> dict[str, Any]:
    args = [
        str(XHS_PYTHON),
        str(XHS_CLIENT),
        "feeds",
        "--json",
        "--timeout",
        str(XHS_FEEDS_TIMEOUT),
    ]
    last_result: dict[str, Any] | None = None
    for attempt in range(3):
        result = _run_json_cli(args, timeout=XHS_FEEDS_TIMEOUT + 2)
        if result.get("ok"):
            return result
        last_result = result
        if attempt < 2:
            time.sleep(1.0)
    return last_result or {
        "ok": False,
        "returncode": 1,
        "json": None,
        "stdout": "",
        "stderr": "xiaohongshu feeds cli retry exhausted",
        "error": "xiaohongshu feeds cli retry exhausted",
    }


def _check_xiaohongshu_health() -> tuple[bool, dict[str, Any]]:
    status_result = _run_json_cli(
        [
            str(XHS_PYTHON),
            str(XHS_CLIENT),
            "status",
            "--json",
            "--timeout",
            str(XHS_STATUS_TIMEOUT),
        ],
        timeout=XHS_STATUS_TIMEOUT + 2,
    )
    status_payload = status_result.get("json") if isinstance(status_result.get("json"), dict) else {}
    status_code = status_payload.get("code", "STATUS_CHECK_FAILED")
    status_ok = bool(status_result["ok"])
    auth_status = "ok" if status_ok else ("not_logged_in" if status_code == "NOT_LOGGED_IN" else "auth_degraded")
    auth_message = (
        "login status passed"
        if status_ok
        else status_payload.get("message") or status_payload.get("error") or status_result["error"]
    )
    auth_details = status_payload.get("data") or status_payload.get("details")
    auth_health = _make_component_health(
        auth_status,
        stage="status",
        error_code="" if status_ok else status_code,
        message=auth_message,
        details=auth_details,
    )

    feeds_result = _run_xiaohongshu_feeds_cli()
    feeds_payload = feeds_result.get("json") if isinstance(feeds_result.get("json"), dict) else {}
    feeds_ok = bool(feeds_result["ok"])
    feed_items = _extract_xiaohongshu_feeds_from_payload(feeds_payload) if feeds_ok else []
    if feeds_ok and feed_items:
        _save_xiaohongshu_feeds_cache(feeds_payload)

    if not feeds_result["ok"]:
        cached_feed = _load_xiaohongshu_feeds_cache()
        if cached_feed:
            cached_payload = cached_feed["payload"]
            cached_items = _extract_xiaohongshu_feeds_from_payload(cached_payload)
            return True, _make_source_health(
                "feeds_cached",
                stage="feeds_cache",
                error_code=feeds_payload.get("code", status_code if not status_ok else ""),
                message="live feeds unavailable, using cached xiaohongshu feed snapshot",
                details={
                    "status_check": status_payload.get("data") or status_payload.get("details"),
                    "feeds_ready": True,
                    "search_ready": False,
                    "feed_items_collected": len(cached_items),
                    "cached_at": cached_feed["cached_at"],
                    "cache_age_seconds": cached_feed["age_seconds"],
                    "feeds_error": feeds_payload.get("details") or feeds_result["error"],
                },
                read_health=_make_component_health(
                    "feeds_cached",
                    stage="feeds_cache",
                    error_code=feeds_payload.get("code", status_code if not status_ok else ""),
                    message="live feeds unavailable, using cached xiaohongshu feed snapshot",
                    details={
                        "items_collected": len(cached_items),
                        "cached_at": cached_feed["cached_at"],
                        "cache_age_seconds": cached_feed["age_seconds"],
                    },
                ),
                auth_health=auth_health,
            )
        if not status_ok:
            status = "not_logged_in" if status_code == "NOT_LOGGED_IN" else "status_failed"
            return False, _make_source_health(
                status,
                stage="status",
                error_code=status_code,
                message=status_payload.get("message") or status_payload.get("error") or status_result["error"],
                details={
                    "status_check": status_payload.get("data") or status_payload.get("details"),
                    "feeds_ready": False,
                    "search_ready": False,
                },
                read_health=_make_component_health(
                    "unavailable",
                    stage="feeds",
                    error_code=feeds_payload.get("code", "LIST_FEEDS_FAILED"),
                    message="live xiaohongshu reads unavailable",
                ),
                auth_health=auth_health,
            )
        return False, _make_source_health(
            "feeds_failed",
            stage="feeds",
            error_code=feeds_payload.get("code", "LIST_FEEDS_FAILED"),
            message=feeds_payload.get("message") or feeds_payload.get("error") or feeds_result["error"],
            details={
                "status_check": status_payload.get("data") or status_payload.get("details"),
                "feeds_ready": False,
                "search_ready": False,
                "feed_items_collected": 0,
                "feeds_error": feeds_payload.get("details"),
            },
            read_health=_make_component_health(
                "feeds_failed",
                stage="feeds",
                error_code=feeds_payload.get("code", "LIST_FEEDS_FAILED"),
                message=feeds_payload.get("message") or feeds_payload.get("error") or feeds_result["error"],
                details=feeds_payload.get("details"),
            ),
            auth_health=auth_health,
        )

    smoke_result = _run_json_cli(
        [
            str(XHS_PYTHON),
            str(XHS_CLIENT),
            "search",
            XHS_SMOKE_KEYWORD,
            "--json",
            "--timeout",
            str(XHS_SEARCH_TIMEOUT),
        ],
        timeout=XHS_SEARCH_TIMEOUT + 2,
    )
    smoke_payload = smoke_result.get("json") if isinstance(smoke_result.get("json"), dict) else {}
    smoke_ok = bool(smoke_result["ok"])

    if not smoke_result["ok"]:
        code = smoke_payload.get("code", "SEARCH_FAILED")
        status = "feeds_only" if code == "REQUEST_TIMEOUT" else "search_degraded"
        return True, _make_source_health(
            status,
            stage="search_smoke",
            error_code=code,
            message=(
                "feeds 可用，但搜索烟雾测试失败"
                if code == "REQUEST_TIMEOUT"
                else smoke_payload.get("message") or smoke_payload.get("error") or smoke_result["error"]
            ),
            details={
                "status_check": status_payload.get("data") or status_payload.get("details"),
                "feeds_ready": True,
                "search_ready": False,
                "feed_items_collected": len(feed_items),
                "smoke_keyword": XHS_SMOKE_KEYWORD,
                "smoke_error": smoke_payload.get("details"),
            },
            read_health=_make_component_health(
                status,
                stage="search_smoke",
                error_code=code,
                message=(
                    "feeds 可用，但搜索烟雾测试失败"
                    if code == "REQUEST_TIMEOUT"
                    else smoke_payload.get("message") or smoke_payload.get("error") or smoke_result["error"]
                ),
                details={
                    "feed_items_collected": len(feed_items),
                    "smoke_keyword": XHS_SMOKE_KEYWORD,
                    "smoke_error": smoke_payload.get("details"),
                },
            ),
            auth_health=auth_health,
        )

    smoke_feeds = _extract_xiaohongshu_feeds_from_payload(smoke_payload)
    return True, _make_source_health(
        "ok" if status_ok else "degraded",
        stage="search_smoke",
        message=(
            "login status, feeds list, and smoke search passed"
            if status_ok
            else "status 接口未通过，但 feeds 与 smoke search 可用"
        ),
        details={
            "status_check": status_payload.get("data") or status_payload.get("details"),
            "feeds_ready": True,
            "search_ready": True,
            "feed_items_collected": len(feed_items),
            "smoke_keyword": XHS_SMOKE_KEYWORD,
            "smoke_result_count": len(smoke_feeds),
        },
        read_health=_make_component_health(
            "ok",
            stage="search_smoke",
            message="feeds list and smoke search passed",
            details={
                "feed_items_collected": len(feed_items),
                "smoke_keyword": XHS_SMOKE_KEYWORD,
                "smoke_result_count": len(smoke_feeds),
            },
        ),
        auth_health=auth_health,
    )


def _parse_twclaw_trending(output: str) -> list[dict[str, Any]]:
    """Parse twclaw trending output like '1. #Topic (#Topic)'."""
    candidates = []
    for line in output.splitlines():
        m = re.match(r"^\d+\.\s+(.+?)(?:\s+\(.*\))?\s*$", line.strip())
        if m:
            topic_text = m.group(1).strip()
            candidates.append({
                "source": "x_trending",
                "angle": f"X 热点趋势：{topic_text}",
                "audience": "关注社交媒体热点的创作者与运营者",
                "evidence_urls": [f"https://x.com/search?q={topic_text}"],
                "risk_flags": ["热点时效性强", "可能与品牌无关"],
                "engagement": 100,
            })
    return candidates


def _parse_twclaw_search(output: str, query: str) -> list[dict[str, Any]]:
    """Parse twclaw search output blocks separated by '---'."""
    candidates = []
    blocks = re.split(r"\n---\n?", output)
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        # First line: "1. DisplayName @handle"
        # Content is typically line index 2 (after date line)
        content = ""
        hearts = 0
        retweets = 0
        url = ""
        for line in lines:
            if line.strip().startswith("❤"):
                m = re.search(r"❤\s*(\d+)\s*🔁\s*(\d+)", line)
                if m:
                    hearts = int(m.group(1))
                    retweets = int(m.group(2))
            elif line.strip().startswith("URL:"):
                url = line.strip().split("URL:", 1)[1].strip()
            elif not re.match(r"^\d+\.\s", line) and not re.match(r"^\d+/\d+/\d+", line.strip()) and not line.strip().startswith("ID:") and not line.strip().startswith("❤"):
                if content:
                    content += " "
                content += line.strip()
        if not content:
            continue
        # Truncate long content for angle
        angle_text = content[:120].rstrip()
        if len(content) > 120:
            angle_text += "…"
        evidence = [url] if url else [f"https://x.com/search?q={query}"]
        candidates.append({
            "source": "x_search",
            "angle": f"[X/{query}] {angle_text}",
            "audience": "对该话题感兴趣的开发者与创作者",
            "evidence_urls": evidence,
            "risk_flags": ["搜索结果质量不稳定"],
            "engagement": hearts + retweets * 3,
        })
    return candidates


def _fetch_twitter_browser(queries: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Fetch Twitter/X content using playwright (no API key needed).
    Searches for English keywords and extracts trending topics.
    """
    all_candidates = []
    errors = []
    
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        print("[browser] playwright not installed, skipping browser method", file=sys.stderr)
        health = _make_source_health(
            "dependency_missing",
            stage="browser_search",
            error_code="PLAYWRIGHT_NOT_INSTALLED",
            message="playwright not installed, falling back to other sources",
            details={"items_collected": 0, "errors": ["playwright_not_installed"]},
        )
        return [], health
    
    for query in queries:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                )
                page = context.new_page()
                
                # Search Twitter (no login required for public content)
                search_url = f"https://twitter.com/search?q={query.replace(' ', '%20')}&src=typed_query&f=live"
                print(f"[browser] twitter search '{query}': {search_url}", file=sys.stderr)
                
                try:
                    page.goto(search_url, timeout=15000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)  # Wait for dynamic content
                    
                    # Extract tweet text from articles
                    tweets = page.query_selector_all('article[data-testid="tweet"]')
                    
                    for i, tweet in enumerate(tweets[:5]):  # Limit to 5 per query
                        try:
                            # Extract tweet text
                            text_elem = tweet.query_selector('[data-testid="tweetText"]')
                            if not text_elem:
                                continue
                            
                            tweet_text = text_elem.inner_text()
                            if len(tweet_text) < 20:  # Skip very short tweets
                                continue
                            
                            # Extract engagement metrics (if available)
                            engagement = 0
                            try:
                                likes_elem = tweet.query_selector('[data-testid="like"]')
                                if likes_elem:
                                    likes_text = likes_elem.get_attribute("aria-label") or ""
                                    likes_match = re.search(r"(\d+)", likes_text)
                                    if likes_match:
                                        engagement += int(likes_match.group(1))
                            except:
                                pass
                            
                            # Truncate for angle
                            angle_text = tweet_text[:120].rstrip()
                            if len(tweet_text) > 120:
                                angle_text += "…"
                            
                            all_candidates.append({
                                "source": "twitter_browser",
                                "angle": f"[X/{query}] {angle_text}",
                                "audience": "AI初心者・グローバル視点",
                                "evidence_urls": [search_url],
                                "risk_flags": ["英語コンテンツ", "翻訳が必要"],
                                "engagement": max(engagement, 50),  # Minimum score
                            })
                            
                        except Exception as e:
                            print(f"[browser] failed to parse tweet {i}: {e}", file=sys.stderr)
                            continue
                    
                    print(f"[browser] twitter search '{query}': extracted {len([c for c in all_candidates if query in c['angle']])} tweets", file=sys.stderr)
                    
                except PlaywrightTimeout:
                    errors.append(f"search:{query}:timeout")
                    print(f"[browser] twitter search '{query}': timeout", file=sys.stderr)
                except Exception as e:
                    errors.append(f"search:{query}:{e}")
                    print(f"[browser] twitter search '{query}': {e}", file=sys.stderr)
                finally:
                    browser.close()
                    
        except Exception as e:
            errors.append(f"search:{query}:{e}")
            print(f"[browser] twitter search '{query}' failed: {e}", file=sys.stderr)
    
    health = _make_source_health(
        "ok" if all_candidates else ("empty" if not errors else "feed_failed"),
        stage="browser_search",
        error_code="BROWSER_SEARCH_FAILED" if errors and not all_candidates else "",
        message=f"collected {len(all_candidates)} twitter candidates via browser" if all_candidates else "browser search returned no candidates",
        details={"items_collected": len(all_candidates), "errors": errors},
    )
    
    return all_candidates, health


def _parse_reddit_posts(output: str, subreddit: str) -> list[dict[str, Any]]:
    """Parse reddit-cli posts output."""
    candidates = []
    # Each post block starts with a number like "1. Title"
    blocks = re.split(r"\n(?=\d+\.)", output)
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        # Title line: "1. Some Title Here"
        title_m = re.match(r"^\d+\.\s+(.+)$", lines[0].strip())
        if not title_m:
            continue
        title = title_m.group(1).strip()
        upvotes = 0
        comments = 0
        url = ""
        for line in lines:
            m_votes = re.search(r"⬆️\s*(\d+)", line)
            if m_votes:
                upvotes = int(m_votes.group(1))
            m_comments = re.search(r"💬\s*(\d+)", line)
            if m_comments:
                comments = int(m_comments.group(1))
            m_url = re.search(r"🔗\s*(https?://\S+)", line)
            if m_url:
                url = m_url.group(1)
        evidence = [url] if url else [f"https://reddit.com/r/{subreddit}"]
        candidates.append({
            "source": "reddit",
            "angle": f"[r/{subreddit}] {title}",
            "audience": f"r/{subreddit} 社区关注者",
            "evidence_urls": evidence,
            "risk_flags": ["Reddit 视角偏英文圈"],
            "engagement": upvotes + comments * 2,
        })
    return candidates


def _parse_xiaohongshu_search(output: str, keyword: str) -> list[dict[str, Any]]:
    """Parse xiaohongshu search output."""
    candidates = []
    payload: Any = None
    if isinstance(output, (dict, list)):
        payload = output
    else:
        try:
            payload = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            payload = None

    if payload is not None:
        feeds = _extract_xiaohongshu_feeds_from_payload(payload)
        for feed in feeds:
            note_card = feed.get("noteCard", {}) or feed.get("note_card", {})
            title = (
                note_card.get("displayTitle")
                or note_card.get("title")
                or note_card.get("display_title")
                or ""
            )
            if not title:
                continue

            interact = note_card.get("interactInfo", {}) or note_card.get("interact_info", {})
            likes = (
                interact.get("likedCount")
                or interact.get("liked_count")
                or note_card.get("likedCount")
                or note_card.get("liked_count")
                or 100
            )
            likes = _parse_engagement_number(likes, default=100)

            candidates.append({
                "source": "xiaohongshu_search",
                "angle": f"[小紅書爆款] {title}",
                "audience": "AI初心者・入門者",
                "evidence_urls": [f"https://www.xiaohongshu.com/search_result?keyword={keyword}"],
                "risk_flags": [],
                "engagement": likes,
            })
        return candidates

    lines = output.splitlines()
    
    # 关键词过滤：标题必须包含这些词之一
    required_keywords = [
        "AI", "ai", "ChatGPT", "chatgpt", "Claude", "claude",
        "人工智能", "智能", "GPT", "gpt", "Agent", "agent",
        "自動化", "自动化", "教程", "入门", "入門", "初心者",
        "使い方", "使用", "学习", "學習"
    ]
    
    for line in lines:
        # 匹配格式：[1] 标题
        if re.match(r'^\[\d+\]', line):
            title = line.split(']', 1)[1].strip() if ']' in line else ""
            if not title:
                continue
            
            # 过滤：标题必须包含关键词
            if not any(kw in title for kw in required_keywords):
                continue
            
            # 默认点赞数（如果解析失败）
            likes = 100
            
            # 尝试从下一行获取点赞数
            try:
                idx = lines.index(line)
                if idx + 2 < len(lines):
                    likes_line = lines[idx + 2]
                    m = re.search(r'Likes:\s*(\d+)', likes_line)
                    if m:
                        likes = int(m.group(1))
            except:
                pass
            
            candidates.append({
                "source": "xiaohongshu_search",
                "angle": f"[小紅書爆款] {title}",
                "audience": "AI初心者・入門者",
                "evidence_urls": [f"https://www.xiaohongshu.com/search_result?keyword={keyword}"],
                "risk_flags": [],  # 移除风险提示，因为我们会生成日文内容
                "engagement": likes,
            })
    
    return candidates


def _parse_xiaohongshu_feeds(output: Any) -> list[dict[str, Any]]:
    """Parse xiaohongshu feeds output (JSON payload or text)."""
    candidates = []
    data: Any = None

    if isinstance(output, (dict, list)):
        data = output
    else:
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            data = None

    if data is not None:
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            items = data["data"].get("feeds", data["data"].get("items", []))
        else:
            items = data if isinstance(data, list) else data.get("items", data.get("feeds", []))
        for item in items:
            note_card = item.get("noteCard", {}) or item.get("note_card", {})
            title = (
                item.get("title")
                or note_card.get("displayTitle")
                or note_card.get("title", "")
            )
            interact = note_card.get("interactInfo", {}) or note_card.get("interact_info", {})
            likes = (
                item.get("likes")
                or item.get("liked_count")
                or interact.get("likedCount")
                or interact.get("liked_count")
                or 0
            )
            if not title:
                continue
            candidates.append({
                "source": "xiaohongshu",
                "angle": f"[小红书] {title}",
                "audience": "小红书用户群体",
                "evidence_urls": ["https://xiaohongshu.com"],
                "risk_flags": ["平台内容风格差异"],
                "engagement": _parse_engagement_number(likes, default=10),
            })
        return candidates

    if not isinstance(output, str):
        return candidates

    for line in output.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "Error", "Traceback")):
            candidates.append({
                "source": "xiaohongshu",
                "angle": f"[小红书] {line[:100]}",
                "audience": "小红书用户群体",
                "evidence_urls": ["https://xiaohongshu.com"],
                "risk_flags": ["平台内容风格差异"],
                "engagement": 10,
            })
    return candidates


def _load_recent_xiaohongshu_topic_candidates(
    *,
    max_age_days: int = 7,
    max_items: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    cutoff = (now_jst() - timedelta(days=max_age_days)).date()
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")

    for path in sorted(TOPICS_DIR.glob("*.json"), reverse=True):
        if not pattern.match(path.name):
            continue
        try:
            topic_date = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if topic_date < cutoff:
            continue

        payload = load_json(path, None)
        if not isinstance(payload, dict):
            continue
        raw_candidates = payload.get("candidates", [])
        if not isinstance(raw_candidates, list):
            continue

        cached_candidates: list[dict[str, Any]] = []
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            if raw.get("source") not in {"xiaohongshu", "xiaohongshu_search"}:
                continue
            candidate = dict(raw)
            risk_flags = list(candidate.get("risk_flags", []))
            if "小红书历史缓存，可能非实时" not in risk_flags:
                risk_flags.append("小红书历史缓存，可能非实时")
            candidate["risk_flags"] = risk_flags
            cached_candidates.append(candidate)
            if len(cached_candidates) >= max_items:
                break

        if cached_candidates:
            return cached_candidates, {
                "path": str(path),
                "date": topic_date.isoformat(),
                "items_collected": len(cached_candidates),
            }

    return [], None


def _fetch_xiaohongshu_feed_candidates() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    feeds_result = _run_xiaohongshu_feeds_cli()
    feeds_payload = feeds_result.get("json") if isinstance(feeds_result.get("json"), dict) else {}
    if not feeds_result["ok"]:
        cached_feed = _load_xiaohongshu_feeds_cache()
        if cached_feed:
            candidates = _parse_xiaohongshu_feeds(cached_feed["payload"])
            return candidates, _make_source_health(
                "feeds_cached" if candidates else "empty",
                stage="feeds_cache",
                message=(
                    f"live feeds unavailable, using cached xiaohongshu feeds: {len(candidates)} items"
                    if candidates
                    else "live feeds unavailable and cached xiaohongshu feeds were empty"
                ),
                details={
                    "items_collected": len(candidates),
                    "cached_at": cached_feed["cached_at"],
                    "cache_age_seconds": cached_feed["age_seconds"],
                    "feeds_error": feeds_payload.get("details") or feeds_result["error"],
                },
            )
        return [], _make_source_health(
            "feeds_failed",
            stage="feeds",
            error_code=feeds_payload.get("code", "LIST_FEEDS_FAILED"),
            message=feeds_payload.get("message") or feeds_payload.get("error") or feeds_result["error"],
            details=feeds_payload.get("details"),
        )

    live_items = _extract_xiaohongshu_feeds_from_payload(feeds_payload)
    if live_items:
        _save_xiaohongshu_feeds_cache(feeds_payload)
    candidates = _parse_xiaohongshu_feeds(feeds_payload)
    return candidates, _make_source_health(
        "ok" if candidates else "empty",
        stage="feeds",
        message=f"feeds fetched: {len(candidates)} items" if candidates else "feeds fetched but no usable items were found",
        details={"items_collected": len(candidates)},
    )


def _parse_video_watcher(output: str) -> list[dict[str, Any]]:
    """Parse video-watcher trending output (best-effort)."""
    candidates = []
    try:
        data = json.loads(output)
        items = data if isinstance(data, list) else data.get("items", [])
        for item in items:
            title = item.get("title", "")
            views = item.get("views", item.get("view_count", 0))
            if title:
                candidates.append({
                    "source": "bilibili",
                    "angle": f"[视频热点] {title}",
                    "audience": "视频平台观众",
                    "evidence_urls": [],
                    "risk_flags": ["视频内容需二次提炼"],
                    "engagement": int(views) if views else 10,
                })
    except (json.JSONDecodeError, TypeError):
        pass
    return candidates


def fetch_real_topics(profile: str = "full") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch topics from configured data sources. Profile controls source breadth."""
    all_candidates: list[dict[str, Any]] = []
    source_health: dict[str, Any] = {}
    env = parse_env()
    social_fast = profile == "social_fast"

    if not social_fast:
        # --- a) 小红书入门类爆款（优先级最高）---
        xhs_ready, xhs_health = _check_xiaohongshu_health()
        source_health["xiaohongshu"] = xhs_health
        xhs_details = source_health["xiaohongshu"].get("details") or {}
        xhs_search_ready = bool(xhs_details.get("search_ready"))
        xhs_feeds_ready = bool(xhs_details.get("feeds_ready"))
        xhs_history_candidates, xhs_history_meta = _load_recent_xiaohongshu_topic_candidates()

        if xhs_ready and xhs_search_ready:
            xhs_keyword_failures: list[dict[str, str]] = []
            xhs_total_items = 0
            for keyword in ["AI入門", "ChatGPT使い方", "AI初心者", "ゼロから始めるAI"]:
                result = _run_json_cli(
                    [
                        str(XHS_PYTHON),
                        str(XHS_CLIENT),
                        "search",
                        keyword,
                        "--sort",
                        "最多点赞",
                        "--json",
                        "--timeout",
                        str(XHS_SEARCH_TIMEOUT),
                    ],
                    timeout=XHS_SEARCH_TIMEOUT + 2,
                )
                payload = result.get("json") if isinstance(result.get("json"), dict) else {}
                if not result["ok"]:
                    code = payload.get("code", "SEARCH_FAILED")
                    xhs_keyword_failures.append({"keyword": keyword, "code": code})
                    print(
                        f"[topic_scan] xiaohongshu '{keyword}' failed: "
                        f"{payload.get('error') or payload.get('message') or result['error']}",
                        file=sys.stderr,
                    )
                    continue

                parsed = _parse_xiaohongshu_search(payload, keyword)
                xhs_total_items += len(parsed)
                all_candidates.extend(parsed)
                print(f"[topic_scan] xiaohongshu '{keyword}': {len(parsed)} items", file=sys.stderr)

            source_health["xiaohongshu"]["details"] = {
                **(source_health["xiaohongshu"].get("details") or {}),
                "keywords_checked": 4,
                "keyword_failures": xhs_keyword_failures,
                "items_collected": xhs_total_items,
            }
            if xhs_total_items == 0 and xhs_keyword_failures:
                if xhs_feeds_ready:
                    feed_candidates, feed_health = _fetch_xiaohongshu_feed_candidates()
                    all_candidates.extend(feed_candidates)
                    source_health["xiaohongshu"]["status"] = "feeds_only"
                    source_health["xiaohongshu"]["stage"] = "feeds_fallback"
                    source_health["xiaohongshu"]["message"] = "keyword search failed, fell back to feeds collection"
                    source_health["xiaohongshu"]["details"] = {
                        **(source_health["xiaohongshu"].get("details") or {}),
                        "feed_fallback_items": len(feed_candidates),
                        "feed_fallback_health": feed_health,
                    }
                    source_health["xiaohongshu"]["read_health"] = _make_component_health(
                        "feeds_only",
                        stage="feeds_fallback",
                        error_code=source_health["xiaohongshu"].get("error_code", ""),
                        message="keyword search failed, fell back to feeds collection",
                        details={
                            "feed_fallback_items": len(feed_candidates),
                            "feed_fallback_health": feed_health,
                        },
                    )
                    print(
                        f"[topic_scan] xiaohongshu fallback feeds: {len(feed_candidates)} items",
                        file=sys.stderr,
                    )
                else:
                    first_code = xhs_keyword_failures[0]["code"]
                    if xhs_history_candidates:
                        all_candidates.extend(xhs_history_candidates)
                        source_health["xiaohongshu"]["status"] = "history_fallback"
                        source_health["xiaohongshu"]["stage"] = "topics_cache"
                        source_health["xiaohongshu"]["error_code"] = first_code
                        source_health["xiaohongshu"]["message"] = "keyword search failed, fell back to recent xiaohongshu topic cache"
                        source_health["xiaohongshu"]["details"] = {
                            **(source_health["xiaohongshu"].get("details") or {}),
                            "history_fallback": xhs_history_meta,
                        }
                        source_health["xiaohongshu"]["read_health"] = _make_component_health(
                            "history_fallback",
                            stage="topics_cache",
                            error_code=first_code,
                            message="keyword search failed, fell back to recent xiaohongshu topic cache",
                            details={"history_fallback": xhs_history_meta},
                        )
                    else:
                        source_health["xiaohongshu"]["status"] = (
                            "search_timeout" if first_code == "REQUEST_TIMEOUT" else "search_failed"
                        )
                        source_health["xiaohongshu"]["stage"] = "keyword_search"
                        source_health["xiaohongshu"]["error_code"] = first_code
                        source_health["xiaohongshu"]["message"] = "health check passed but keyword search collection failed"
                        source_health["xiaohongshu"]["read_health"] = _make_component_health(
                            source_health["xiaohongshu"]["status"],
                            stage="keyword_search",
                            error_code=first_code,
                            message="health check passed but keyword search collection failed",
                        )
        elif xhs_feeds_ready:
            feed_candidates, feed_health = _fetch_xiaohongshu_feed_candidates()
            all_candidates.extend(feed_candidates)
            source_health["xiaohongshu"]["status"] = source_health["xiaohongshu"].get("status") or "feeds_only"
            source_health["xiaohongshu"]["stage"] = "feeds_fallback"
            source_health["xiaohongshu"]["message"] = (
                "xiaohongshu search unavailable, collected fallback feed candidates"
            )
            source_health["xiaohongshu"]["details"] = {
                **(source_health["xiaohongshu"].get("details") or {}),
                "feed_fallback_items": len(feed_candidates),
                "feed_fallback_health": feed_health,
            }
            source_health["xiaohongshu"]["read_health"] = _make_component_health(
                source_health["xiaohongshu"]["status"],
                stage="feeds_fallback",
                error_code=source_health["xiaohongshu"].get("error_code", ""),
                message="xiaohongshu search unavailable, collected fallback feed candidates",
                details={
                    "feed_fallback_items": len(feed_candidates),
                    "feed_fallback_health": feed_health,
                },
            )
            print(
                f"[topic_scan] xiaohongshu feeds fallback: {len(feed_candidates)} items",
                file=sys.stderr,
            )
        elif xhs_history_candidates:
            all_candidates.extend(xhs_history_candidates)
            source_health["xiaohongshu"]["status"] = "history_fallback"
            source_health["xiaohongshu"]["stage"] = "topics_cache"
            source_health["xiaohongshu"]["message"] = "live xiaohongshu unavailable, fell back to recent topic cache"
            source_health["xiaohongshu"]["details"] = {
                **(source_health["xiaohongshu"].get("details") or {}),
                "history_fallback": xhs_history_meta,
            }
            source_health["xiaohongshu"]["read_health"] = _make_component_health(
                "history_fallback",
                stage="topics_cache",
                error_code=source_health["xiaohongshu"].get("error_code", ""),
                message="live xiaohongshu unavailable, fell back to recent topic cache",
                details={"history_fallback": xhs_history_meta},
            )
            print(
                f"[topic_scan] xiaohongshu history fallback: {len(xhs_history_candidates)} items",
                file=sys.stderr,
            )
        else:
            print(
                "[topic_scan] xiaohongshu skipped: "
                f"{xhs_health.get('status')} code={xhs_health.get('error_code')}",
                file=sys.stderr,
            )

        # --- b) 日本平台 feed（best-effort）---
        for feed_config in _build_japanese_feed_configs(env):
            key = str(feed_config["key"])
            candidates, health = _fetch_feed_candidates(feed_config)
            source_health[key] = health
            if candidates:
                all_candidates.extend(candidates)
                print(f"[topic_scan] {key} feed: {len(candidates)} items", file=sys.stderr)
            else:
                print(
                    f"[topic_scan] {key} feed failed: "
                    f"{health.get('status')} code={health.get('error_code', '')}",
                    file=sys.stderr,
                )

    # --- c) X/Twitter trending + search ---
    # Try browser-based search first (no API key needed), fallback to twclaw if available
    x_items = 0
    x_errors: list[str] = []
    x_method = "none"
    
    # English keywords for broader reach (not limited to Japanese)
    twitter_queries = [
        "AI for beginners",
        "getting started with AI",
        "ChatGPT tutorial",
        "AI tools 2026"
    ]
    
    # Try browser method first
    browser_candidates, browser_health = _fetch_twitter_browser(twitter_queries)
    if browser_candidates:
        x_items += len(browser_candidates)
        all_candidates.extend(browser_candidates)
        x_method = "browser"
        source_health["x"] = browser_health
        print(f"[topic_scan] twitter browser: {len(browser_candidates)} items", file=sys.stderr)
    else:
        # Fallback to twclaw if available
        try:
            out = _run_cli(["twclaw", "trending", "-n", "10"])
            parsed = _parse_twclaw_trending(out)
            x_items += len(parsed)
            all_candidates.extend(parsed)
            x_method = "twclaw"
            print(f"[topic_scan] twclaw trending: {len(parsed)} items", file=sys.stderr)
        except Exception as e:
            x_errors.append(f"trending:{e}")
            print(f"[topic_scan] twclaw trending failed: {e}", file=sys.stderr)

        for query in twitter_queries[:2]:  # Limit to 2 queries for twclaw
            try:
                out = _run_cli(["twclaw", "search", query, "-n", "5"])
                parsed = _parse_twclaw_search(out, query)
                x_items += len(parsed)
                all_candidates.extend(parsed)
                x_method = "twclaw"
                print(f"[topic_scan] twclaw search '{query}': {len(parsed)} items", file=sys.stderr)
            except Exception as e:
                x_errors.append(f"search:{query}:{e}")
                print(f"[topic_scan] twclaw search '{query}' failed: {e}", file=sys.stderr)
        
        source_health["x"] = _make_source_health(
            "ok" if x_items else ("empty" if not x_errors else "feed_failed"),
            stage="search",
            error_code="X_SOURCE_FAILED" if x_errors and not x_items else "",
            message=f"collected {x_items} x candidates via {x_method}" if x_items else "x sources returned no candidates",
            details={"items_collected": x_items, "errors": x_errors, "method": x_method},
        )

    # --- d) Reddit 新手问题 ---
    reddit_items = 0
    reddit_errors: list[str] = []
    for subreddit in ["ChatGPT", "artificial"]:
        try:
            out = _run_cli(["reddit-cli", "posts", subreddit, "5", "hot"])
            parsed = _parse_reddit_posts(out, subreddit)
            reddit_items += len(parsed)
            all_candidates.extend(parsed)
            print(f"[topic_scan] reddit r/{subreddit}: {len(parsed)} items", file=sys.stderr)
        except Exception as e:
            reddit_errors.append(f"{subreddit}:{e}")
            print(f"[topic_scan] reddit r/{subreddit} failed: {e}", file=sys.stderr)
    source_health["reddit"] = _make_source_health(
        "ok" if reddit_items else ("empty" if not reddit_errors else "feed_failed"),
        stage="hot_posts",
        error_code="REDDIT_SOURCE_FAILED" if reddit_errors and not reddit_items else "",
        message=(
            f"collected {reddit_items} reddit candidates"
            if reddit_items
            else "reddit sources returned no candidates"
        ),
        details={"items_collected": reddit_items, "errors": reddit_errors},
    )

    source_health["profile"] = {"status": "ok", "stage": profile, "message": f"scan profile={profile}"}
    return all_candidates, source_health


def _score_candidate(raw: dict[str, Any], rank: int) -> float:
    """Compute a normalized score from engagement and rank position."""
    engagement = raw.get("engagement", 0)
    # Log-scale engagement + rank decay
    import math
    eng_score = min(math.log1p(engagement) * 1.2, 9.5)
    rank_penalty = rank * 0.08
    return round(max(eng_score - rank_penalty, 1.0), 2)


def cmd_topic_scan(args: argparse.Namespace) -> int:
    ensure_dirs()
    day = args.date or date_str()
    profile = args.profile

    # Fetch real topics from all sources
    raw_topics, source_health = fetch_real_topics(profile=profile)
    print(f"[topic_scan] profile={profile} total raw candidates: {len(raw_topics)}", file=sys.stderr)

    # Fallback to templates if all real sources failed
    if not raw_topics and profile == "full":
        print("[topic_scan] all real sources failed, using template fallback", file=sys.stderr)
        templates = build_topic_templates()
        random.seed(day)
        start = now_jst().weekday() % len(templates)
        for i in range(5):
            t = templates[(start + i) % len(templates)]
            raw_topics.append({
                "source": "template_fallback",
                "angle": t["angle"],
                "audience": t["audience"],
                "evidence_urls": t["evidence_urls"],
                "risk_flags": t["risk_flags"],
                "engagement": 50 - i * 5,
            })

    # Sort by engagement descending, then assign scores
    raw_topics.sort(key=lambda x: x.get("engagement", 0), reverse=True)

    candidates: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_topics):
        score = _score_candidate(raw, i)
        topic_id = f"{day.replace('-', '')}-{i + 1:02d}"
        candidate = TopicCandidate(
            topic_id=topic_id,
            source=raw["source"],
            angle=raw["angle"],
            audience=raw["audience"],
            score=score,
            evidence_urls=raw.get("evidence_urls", []),
            risk_flags=raw.get("risk_flags", []),
        )
        candidates.append(
            {
                "id": candidate.topic_id,
                "source": candidate.source,
                "angle": candidate.angle,
                "audience": candidate.audience,
                "score": candidate.score,
                "evidence_urls": candidate.evidence_urls,
                "risk_flags": candidate.risk_flags,
                "status": "drafted",
                "created_at": iso_now(),
            }
        )

    payload = {
        "date": day,
        "profile": profile,
        "timezone": "Asia/Tokyo",
        "generated_at": iso_now(),
        "source_health": source_health,
        "candidates": candidates,
    }
    path = topic_file_for_date(day, profile=profile)
    save_json(path, payload)
    if profile == "full":
        sync_topics_to_hub(payload)
    print(f"topic_scan_done profile={profile} date={day} count={len(candidates)} file={path}")
    return 0


def pick_topic_for_draft(topics: dict[str, Any]) -> dict[str, Any]:
    candidates = topics.get("candidates") or []
    if not candidates:
        raise RuntimeError("no topic candidates found")
    
    # 按分数排序，跳过已有草稿的选题
    sorted_candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
    for candidate in sorted_candidates:
        topic_id = candidate.get("id")
        draft_path = DRAFTS_DIR / f"{topic_id}.json"
        if not draft_path.exists():
            return candidate
    
    # 如果所有选题都有草稿了，返回分数最高的
    return sorted_candidates[0]


def generate_x_post(topic: dict[str, Any]) -> dict[str, Any]:
    angle = topic.get("angle", "")
    audience = topic.get("audience", "")
    
    # 爆款标题公式：数字 + 情绪 + 痛点 + 反直觉
    # 提取核心关键词
    if "小紅書爆款" in angle:
        # 去掉前缀，提取核心标题
        core_title = angle.replace("[小紅書爆款] ", "").strip()
    else:
        core_title = angle
    
    # 生成钩子（黄金3秒）
    hooks = [
        f"90%の人が知らない：{core_title}",
        f"たった3分で理解できる：{core_title}",
        f"初心者が見落としがちな：{core_title}",
        f"プロが教える：{core_title}",
    ]
    
    import random
    hook = random.choice(hooks)
    
    text = (
        f"{hook}\n\n"
        f"多くの人がAIを使いこなせない理由は、基礎を飛ばしているから。\n\n"
        f"この方法なら、今日から実践できます。\n\n"
        "完全版テンプレートが欲しい方は、DMで「テンプレ」と送ってください。"
    )
    
    return {
        "channel": "x",
        "hook": hook,
        "text": text,
        "cta": "DMで「テンプレ」",
        "hashtags": ["#AI初心者", "#ChatGPT", "#AI活用"],
        "created_at": iso_now(),
    }


def cmd_x_draft(args: argparse.Namespace) -> int:
    ensure_dirs()
    topics = load_topics(args.date)
    if not topics:
        raise RuntimeError("topics not found; run topic_scan first")

    topic = pick_topic_for_draft(topics)
    topic_id = topic["id"]
    draft = load_draft(topic_id) or blank_draft(topic)
    draft["x_posts"] = [generate_x_post(topic)]
    if "workflow_status" not in draft:
        draft["workflow_status"] = default_workflow_status()
    draft["workflow_status"]["x"] = "drafted"
    draft["status"] = "drafted"
    path = save_draft(draft)
    sync_production_card(draft, "draft", "x")
    print(f"x_draft_done topic_id={topic_id} file={path}")
    return 0


def cmd_note_outline(args: argparse.Namespace) -> int:
    ensure_dirs()
    topics = load_topics(args.date)
    if not topics:
        raise RuntimeError("topics not found; run topic_scan first")

    topic = pick_topic_for_draft(topics)
    topic_id = topic["id"]
    draft = load_draft(topic_id) or blank_draft(topic)

    outline = [
        {"section": "導入", "points": ["読者の課題", "この記事で得られる成果"]},
        {"section": "全体設計", "points": ["ワークフロー全体図", "重要な意思決定ポイント", "よくある失敗"]},
        {"section": "実行ステップ", "points": ["今週やること", "使うテンプレート", "品質チェック"]},
        {"section": "締め・CTA", "points": ["次のアクション", "保存/共有の導線"]},
    ]
    draft["note_outline"] = outline
    if "workflow_status" not in draft:
        draft["workflow_status"] = default_workflow_status()
    draft["workflow_status"]["note"] = "drafted"
    draft["status"] = "drafted"
    path = save_draft(draft)
    sync_production_card(draft, "outline", "note")
    print(f"note_outline_done topic_id={topic_id} file={path}")
    return 0


def normalize_japanese_audience(audience: str) -> str:
    if re.search(r"[\u3040-\u30ff]", audience):
        return audience
    if "日本" in audience:
        return audience
    return "日本でAI活用を実務に落とし込みたい個人クリエイターと小規模チーム"


def is_likely_japanese_text(text: str) -> bool:
    """检查文本是否主要是日文（使用 LLM 判断）"""
    # 快速检查：必须有假名
    has_hiragana = bool(re.search(r"[\u3040-\u309f]", text))
    if not has_hiragana:
        return False
    
    # 使用 gemini 快速判断
    prompt = f"""判断以下文本是否主要是日文（允许少量汉字，但不能有明显的中文词汇或句子）。

文本：
{text[:500]}

只回答 YES 或 NO。
- YES：主要是日文
- NO：包含明显中文或不是日文

回答："""
    
    try:
        result = subprocess.run(
            ["gemini", prompt],
            capture_output=True,
            text=True,
            timeout=10,
        )
        answer = result.stdout.strip().upper()
        return "YES" in answer
    except Exception:
        # fallback：如果 gemini 失败，用简单规则
        chinese_words = ["小红书", "原来", "这么", "一直", "被蒙在鼓里"]
        return not any(word in text for word in chinese_words)


def translate_risk_flag_to_ja(flag: str) -> str:
    mapping = {
        "样本偏差": "サンプルバイアス",
        "收益描述需谨慎": "成果表現は誇張を避ける",
        "概念泛化": "概念の一般化リスク",
        "缺案例对照": "比較事例が不足",
        "术语误解": "用語の誤解リスク",
        "执行门槛预期过高": "実行ハードルの見積もりが甘い",
        "过度自动化风险": "過度な自動化リスク",
        "账号安全风险": "アカウント安全性リスク",
        "时间投入低估": "工数見積もり不足",
        "选题重复": "テーマ重複リスク",
        "流程过重": "プロセス過多",
        "反馈延迟": "フィードバック遅延",
        "归因困难": "効果の因果特定が難しい",
        "指标误读": "指標の誤読リスク",
        "搜索结果质量不稳定": "検索結果の品質が不安定",
        "Reddit 视角偏英文圈": "Redditは英語圏バイアスが強い",
        "平台内容风格差异": "プラットフォームごとの文体差",
        "视频内容需二次提炼": "動画内容の再編集が必要",
    }
    return mapping.get(flag, flag)


def localize_risk_flags_for_note(risk_flags: list[str]) -> list[str]:
    return [translate_risk_flag_to_ja(x) for x in risk_flags]


def build_prompt_context(draft: dict[str, Any]) -> dict[str, Any]:
    note_draft = draft.get("note_draft", "")
    topic = draft.get("topic_snapshot") or {}
    title = extract_markdown_title(note_draft) or str(topic.get("angle") or draft.get("topic_id") or "タイトル")
    bullets = extract_markdown_bullets(note_draft, limit=3)
    sections = extract_markdown_sections(note_draft, limit=4)
    summary = extract_markdown_summary(note_draft)
    risk_flags = localize_risk_flags_for_note(topic.get("risk_flags", []))
    article_type = infer_article_type(title, summary)
    prompt_tags = derive_prompt_tags(title, summary, risk_flags, str(topic.get("source", "")))

    primary_keyword = title
    title_tokens = re.findall(r"[A-Za-z0-9\-\+]+|[\u3040-\u30ff\u4e00-\u9fff]{2,}", title)
    if title_tokens:
        primary_keyword = title_tokens[0]

    return {
        "topic_id": str(draft.get("topic_id") or ""),
        "title": title,
        "bullets": bullets,
        "sections": sections,
        "summary": summary,
        "article_type": article_type,
        "prompt_tags": prompt_tags,
        "risk_flags": risk_flags,
        "source": str(topic.get("source", "")),
        "audience": str(topic.get("audience", "")),
        "primary_keyword": primary_keyword,
    }


def score_prompt_card(
    card: PromptCard,
    *,
    prompt_type: str,
    context: dict[str, Any],
    section_focus: str = "",
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    context_tags = set(context.get("prompt_tags", []))
    card_tags = set(card.tags)

    if card.recommended_for == ("note_cover" if prompt_type == "cover" else "note_section_illustration"):
        score += 4
        reasons.append("用途匹配")

    article_type = context.get("article_type", "")
    if article_type and article_type in card_tags:
        score += 4
        reasons.append(f"文章类型匹配:{article_type}")

    overlap = sorted(context_tags & card_tags)
    if overlap:
        score += min(6, len(overlap) * 2)
        reasons.append(f"标签命中:{','.join(overlap[:3])}")

    if card.text_policy == "no_text":
        score += 2
        reasons.append("低文字风险")
    elif card.text_policy == "overlay_text" and prompt_type == "cover":
        score += 1
        reasons.append("适合后期叠字")
    elif card.text_policy == "short_text":
        score -= 1

    if section_focus:
        section_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9\-\+]+|[\u3040-\u30ff\u4e00-\u9fff]{2,}", section_focus)
        }
        section_overlap = sorted(section_tokens & card_tags)
        if section_overlap:
            score += min(4, len(section_overlap) * 2)
            reasons.append(f"段落焦点匹配:{','.join(section_overlap[:2])}")

    if "community" in context_tags and "editorial" in card_tags:
        score += 1
        reasons.append("适合资讯型选题")

    return score, reasons


def build_render_variables(context: dict[str, Any], card: PromptCard, *, section_focus: str = "") -> dict[str, str]:
    bullets = context.get("bullets", [])
    sections = context.get("sections", [])
    return {
        "title": str(context.get("title", "")),
        "summary": str(context.get("summary", "")),
        "primary_keyword": str(context.get("primary_keyword", "")),
        "bullet_points": "; ".join(bullets),
        "bullet_block": "\n".join(f"- {x}" for x in bullets),
        "section_focus": section_focus or (sections[0] if sections else context.get("summary", "")),
        "article_type": str(context.get("article_type", "")),
        "audience": str(context.get("audience", "")),
        "source": str(context.get("source", "")),
        "risk_hint": "、".join(context.get("risk_flags", [])),
        "color_hint": ", ".join(card.color_palette),
        "mood_hint": card.mood,
    }


def recommend_prompt_cards(
    cards: list[PromptCard],
    *,
    prompt_type: str,
    context: dict[str, Any],
    count: int,
    section_targets: list[str] | None = None,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    section_targets = section_targets or [""]

    if prompt_type == "cover":
        scored: list[tuple[int, PromptCard, list[str]]] = []
        for card in cards:
            score, reasons = score_prompt_card(card, prompt_type=prompt_type, context=context)
            scored.append((score, card, reasons))
        for score, card, reasons in sorted(scored, key=lambda item: item[0], reverse=True)[:count]:
            variables = build_render_variables(context, card)
            recommendations.append(
                {
                    "card_id": card.card_id,
                    "title": card.title,
                    "card_ref": card_ref(card.path),
                    "source_origin": card.source_origin,
                    "source_url": card.source_url,
                    "model_family": card.model_family,
                    "text_policy": card.text_policy,
                    "visual_style": card.visual_style,
                    "aspect_ratio": card.aspect_ratio,
                    "resolution": card.resolution,
                    "score": score,
                    "reasons": reasons,
                    "target_section": "",
                    "rendered_prompt_positive": render_prompt_template(card.prompt_positive, variables),
                    "rendered_prompt_negative": render_prompt_template(card.prompt_negative, variables),
                    "quality_notes": card.quality_notes,
                    "failure_modes": card.failure_modes,
                    "tags": card.tags,
                }
            )
        return recommendations

    for target in section_targets:
        scored: list[tuple[int, PromptCard, list[str]]] = []
        for card in cards:
            if card.card_id in used_ids:
                continue
            score, reasons = score_prompt_card(card, prompt_type=prompt_type, context=context, section_focus=target)
            scored.append((score, card, reasons))
        for score, card, reasons in sorted(scored, key=lambda item: item[0], reverse=True):
            if len(recommendations) >= count:
                break
            used_ids.add(card.card_id)
            variables = build_render_variables(context, card, section_focus=target)
            recommendations.append(
                {
                    "card_id": card.card_id,
                    "title": card.title,
                    "card_ref": card_ref(card.path),
                    "source_origin": card.source_origin,
                    "source_url": card.source_url,
                    "model_family": card.model_family,
                    "text_policy": card.text_policy,
                    "visual_style": card.visual_style,
                    "aspect_ratio": card.aspect_ratio,
                    "resolution": card.resolution,
                    "score": score,
                    "reasons": reasons,
                    "target_section": target,
                    "rendered_prompt_positive": render_prompt_template(card.prompt_positive, variables),
                    "rendered_prompt_negative": render_prompt_template(card.prompt_negative, variables),
                    "quality_notes": card.quality_notes,
                    "failure_modes": card.failure_modes,
                    "tags": card.tags,
                }
            )
            break
        if len(recommendations) >= count:
            break

    return recommendations[:count]


def build_image_plan_for_draft(draft: dict[str, Any]) -> Path:
    ensure_dirs()
    topic_id = str(draft.get("topic_id") or "")
    if not topic_id:
        raise RuntimeError("image_plan_requires_topic_id")

    context = build_prompt_context(draft)
    cover_cards = load_prompt_cards("cover")
    illustration_cards = load_prompt_cards("illustration")
    if len(cover_cards) < 10 or len(illustration_cards) < 10:
        raise RuntimeError("prompt_repo_not_ready expected_at_least_10_cards_per_type")

    section_targets = context.get("sections", [])[:2]
    if not section_targets:
        section_targets = context.get("bullets", [])[:2]
    if not section_targets:
        section_targets = [context.get("summary", ""), context.get("primary_keyword", "")]

    payload = {
        "topic_id": topic_id,
        "generated_at": iso_now(),
        "title": context.get("title", ""),
        "article_type": context.get("article_type", ""),
        "prompt_tags": context.get("prompt_tags", []),
        "source": context.get("source", ""),
        "cover_recommendations": recommend_prompt_cards(
            cover_cards,
            prompt_type="cover",
            context=context,
            count=3,
        ),
        "illustration_recommendations": recommend_prompt_cards(
            illustration_cards,
            prompt_type="illustration",
            context=context,
            count=2,
            section_targets=section_targets,
        ),
        "prompt_repo_stats": {
            "cover_cards": len(cover_cards),
            "illustration_cards": len(illustration_cards),
        },
    }
    path = image_plan_path(topic_id)
    save_json(path, payload)
    return path


def validate_prompt_repo() -> dict[str, Any]:
    required_fields = {
        "card_id",
        "title",
        "prompt_type",
        "recommended_for",
        "source_origin",
        "source_url",
        "model_family",
        "text_policy",
        "visual_style",
        "subject_pattern",
        "mood",
        "color_palette",
        "aspect_ratio",
        "resolution",
        "prompt_positive",
        "prompt_negative",
        "quality_notes",
        "failure_modes",
        "tags",
    }
    result: dict[str, Any] = {"cover": [], "illustration": []}
    for prompt_type in ["cover", "illustration"]:
        cards = load_prompt_cards(prompt_type)
        for card in cards:
            missing = [
                field
                for field in required_fields
                if not getattr(card, field)
            ]
            result[prompt_type].append({"card_id": card.card_id, "missing": missing, "path": str(card.path)})
    return result


def render_note_markdown(topic: dict[str, Any]) -> str:
    angle = topic.get("angle", "")
    audience = normalize_japanese_audience(topic.get("audience", ""))
    risk_flags = localize_risk_flags_for_note(topic.get("risk_flags", []))
    risk_str = "、".join(risk_flags) if risk_flags else "特になし"
    
    # 提取核心标题
    if "小紅書爆款" in angle:
        core_title = angle.replace("[小紅書爆款] ", "").strip()
        # 如果标题包含中文，使用通用日文标题
        if re.search(r'[\u4e00-\u9fff]', core_title):
            core_title = "AI初心者が知っておくべき基礎知識"
    else:
        core_title = angle
    
    # 爆款标题公式：数字 + 情绪 + 痛点 + 反直觉
    viral_title = f"【完全保存版】{core_title}｜初心者が3日で実践できる完全ガイド"

    return (
        f"# {viral_title}\n\n"
        "## 🔥 なぜ90%の人がAIを使いこなせないのか？\n\n"
        f"{audience}の多くが、AIツールを「難しい」と感じて挫折します。\n\n"
        "でも実は、正しい順序で学べば、たった3日で実践レベルに到達できます。\n\n"
        "この記事では、私が実際に試して効果があった方法だけを厳選してお伝えします。\n\n"
        "## ✅ この記事を読むとできるようになること\n\n"
        "- AIツールの基本操作（迷わず使える）\n"
        "- 実務で使える具体的なプロンプト\n"
        "- よくあるミスを避ける方法\n\n"
        "---\n\n"
        "## 📝 今日から実践できる3ステップ\n\n"
        "### ステップ1：まずはこれだけ覚える\n\n"
        "最初から全部理解しようとしないでください。\n\n"
        "まずは「質問の仕方」だけマスターすれば、80%の作業が楽になります。\n\n"
        "### ステップ2：テンプレートを使う\n\n"
        "ゼロから考えるのは時間の無駄です。\n\n"
        "すでに効果が実証されているテンプレートを使いましょう。\n\n"
        "### ステップ3：小さく始めて改善する\n\n"
        "完璧を目指さず、まず1回やってみる。\n\n"
        "そして結果を見ながら少しずつ改善していく。これが最速です。\n\n"
        "---\n\n"
        "## ⚠️ よくある失敗パターン（これだけは避けて）\n\n"
        f"注意点：{risk_str}\n\n"
        "焦って自動化しすぎると、かえって手間が増えます。\n\n"
        "最初は手動で試して、効果を確認してから自動化しましょう。\n\n"
        "---\n\n"
        "## 🎁 まとめ：今日からできること\n\n"
        "1. まずは1つのツールに絞って使ってみる\n"
        "2. テンプレートを活用して時間を節約\n"
        "3. 小さく始めて、結果を見ながら改善\n\n"
        "---\n\n"
        "**📩 完全版テンプレートが欲しい方へ**\n\n"
        "この記事で紹介した方法をすぐに実践できるテンプレートを用意しました。\n\n"
        "DMで「テンプレ」と送っていただければ、無料でお渡しします。\n\n"
        "---\n\n"
        "最後まで読んでいただき、ありがとうございました！\n\n"
        "この記事が役に立ったら、ぜひ「スキ」を押してください。\n\n"
        "あなたのAI活用が成功することを願っています🚀\n"
    )


def cmd_note_draft(_: argparse.Namespace) -> int:
    ensure_dirs()
    drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not drafts:
        raise RuntimeError("no draft found; run note_outline first")

    data = load_json(drafts[0], None)
    if not data:
        raise RuntimeError("draft parse failed")

    topic = data.get("topic_snapshot") or {}
    topic_id = data.get("topic_id")
    data["note_draft"] = render_note_markdown(topic)
    if not is_likely_japanese_text(data["note_draft"]):
        raise RuntimeError("note_draft_language_check_failed expected=japanese")
    data["x_slices"] = [
        f"{topic.get('angle', '今週のテーマ')}：公開前に承認フローを入れるだけで誤配信リスクを下げられます。",
        "成果指標を1つのシートに戻すと、次の改善が速くなります。",
        "投稿本数より、再現できる運用設計が差を作ります。",
    ]
    if "workflow_status" not in data:
        data["workflow_status"] = default_workflow_status()
    data["workflow_status"]["note"] = "drafted"
    data["status"] = "drafted"
    path = save_draft(data)
    image_plan = build_image_plan_for_draft(data)
    sync_production_card(data, "draft", "note")
    print(f"note_draft_done topic_id={topic_id} file={path} image_plan={image_plan}")
    return 0


def build_approval_markdown(topic_id: str, channel: str, draft: dict[str, Any]) -> str:
    topic = draft.get("topic_snapshot", {}) or {}
    if channel == "x":
        summary = draft.get("x_posts", [{}])[0].get("text", "")[:220]
        title = str(topic.get("angle") or topic_id)
    else:
        note_draft = str(draft.get("note_draft") or "")
        title = extract_markdown_title(note_draft) or str(topic.get("angle") or topic_id)
        summary = extract_markdown_summary(note_draft)

    review_recommendation, review_guidance = build_review_recommendation(draft, channel)

    approve_cmd = (
        f"bash /Users/chicho/.openclaw/workspace/scripts/content/approval_status.sh "
        f"approve {topic_id} {channel}"
    )
    reject_cmd = (
        f"bash /Users/chicho/.openclaw/workspace/scripts/content/approval_status.sh "
        f"reject {topic_id} {channel}"
    )

    scheduled_at = (now_jst() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S %Z")
    risk_flags = topic.get("risk_flags", [])
    if channel == "note":
        risk_flags = localize_risk_flags_for_note(risk_flags)
    risk_str = ", ".join(risk_flags) if risk_flags else "none"

    return (
        f"topic_id: {topic_id}\n"
        f"channel: {channel}\n"
        f"title: {title}\n"
        f"draft_summary: {summary}\n"
        f"risk_flags: {risk_str}\n"
        f"review_recommendation: {review_recommendation}\n"
        f"review_guidance: {review_guidance}\n"
        f"approve_action: {approve_cmd}\n"
        f"reject_action: {reject_cmd}\n"
        f"scheduled_at: {scheduled_at}\n"
    )


def cmd_approval_push(args: argparse.Namespace) -> int:
    ensure_dirs()
    channel = args.channel
    if channel not in {"x", "note"}:
        raise RuntimeError("channel must be x or note")

    state = load_state()
    pushed: list[str] = []

    for draft_file in sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        draft = load_json(draft_file, None)
        if not draft:
            continue
        topic_id = draft.get("topic_id")
        if not topic_id:
            continue

        workflow = draft.get("workflow_status", {})
        current = workflow.get(channel, "drafted")
        key = state_key(topic_id, channel)
        state_item = state["items"].get(key, {})
        state_status = state_item.get("status")

        if current != "drafted":
            continue
        if state_status in {"pending_approval", "approved", "published"}:
            continue
        if channel == "note" and not (draft.get("note_draft") or "").strip():
            print(f"approval_push_skip topic_id={topic_id} reason=no_note_draft", file=sys.stderr)
            continue

        md = build_approval_markdown(topic_id, channel, draft)
        approval_path = APPROVALS_DIR / f"{topic_id}-{channel}.md"
        approval_path.write_text(md, encoding="utf-8")

        set_state_item(
            state,
            topic_id,
            channel,
            "pending_approval",
            extra={"approval_file": str(approval_path)},
        )
        update_draft_status(topic_id, channel, "pending_approval")
        sync_distribution_card(
            topic_id,
            channel,
            "pending_approval",
            package_ref=str(approval_path),
            draft=draft,
        )
        pushed.append(topic_id)
        if len(pushed) >= args.max_items:
            break

    save_state(state)

    if not pushed:
        print(f"approval_push_done channel={channel} pushed=0")
        return 0

    print(
        "approval_push_done "
        f"channel={channel} pushed={len(pushed)} topic_ids={','.join(pushed)}"
    )
    return 0


def cmd_approval_status(args: argparse.Namespace) -> int:
    ensure_dirs()
    action = args.action
    topic_id = args.topic_id
    channel = args.channel

    action_to_status = {
        "approve": "approved",
        "reject": "rejected",
        "changes_requested": "changes_requested",
        "publish": "published",
        "fail_auth": "publish_failed_auth",
    }
    if action not in action_to_status:
        raise RuntimeError("invalid action")

    status = action_to_status[action]
    state = load_state()
    extra: dict[str, Any] = {}
    review_note = (args.review_note or "").strip()
    reviewed_via = (args.reviewed_via or "").strip()
    review_message_id = (args.review_message_id or "").strip()

    if action == "publish":
        post_url = args.post_url or ""
        if not post_url.strip():
            raise RuntimeError("manual_publish_requires_verified_post_url")
        extra["post_url"] = post_url
        log_path = PUBLISH_LOG_DIR / f"{date_str()}.csv"
        append_csv_row(
            log_path,
            [
                "topic_id",
                "channel",
                "post_url",
                "published_at",
                "impressions_24h",
                "engagement_rate",
            ],
            [topic_id, channel, post_url, iso_now(), "", ""],
        )
    elif action == "changes_requested":
        if not review_note:
            raise RuntimeError("changes_requested_requires_review_note")
        extra["review_note"] = review_note
        if reviewed_via:
            extra["reviewed_via"] = reviewed_via
        if review_message_id:
            extra["review_message_id"] = review_message_id
    elif review_note:
        extra["review_note"] = review_note
        if reviewed_via:
            extra["reviewed_via"] = reviewed_via
        if review_message_id:
            extra["review_message_id"] = review_message_id

    set_state_item(state, topic_id, channel, status, extra=extra)
    save_state(state)
    update_draft_status(topic_id, channel, status)
    if action == "changes_requested":
        record_review_feedback(
            topic_id,
            channel,
            review_note,
            reviewed_via=reviewed_via or "discord_reply",
            review_message_id=review_message_id,
        )
    elif action == "approve":
        clear_review_feedback(topic_id, channel)
    draft = load_draft(topic_id)
    item = state["items"].get(state_key(topic_id, channel), {})
    package_ref = (
        item.get("approval_file")
        or item.get("manual_publish_file")
        or item.get("post_url")
        or ""
    )
    sync_distribution_card(
        topic_id,
        channel,
        status,
        package_ref=package_ref,
        publish_target=item.get("platform", ""),
        draft=draft,
        review_note=item.get("review_note", ""),
        reviewed_via=item.get("reviewed_via", ""),
        review_message_id=item.get("review_message_id", ""),
    )
    if channel == "note" and action == "approve" and draft:
        sync_production_card(draft, "final", "note")
    if action == "publish":
        sync_feedback_card(
            topic_id,
            channel,
            published_url=post_url if action == "publish" else "",
            draft=draft,
        )
    elif status == "publish_unverified":
        sync_feedback_card(
            topic_id,
            channel,
            published_url="",
            draft=draft,
        )

    print(f"approval_status_updated topic_id={topic_id} channel={channel} status={status}")
    return 0


def cmd_x_publish(_: argparse.Namespace) -> int:
    """Publish approved X posts via twclaw tweet."""
    ensure_dirs()
    state = load_state()
    approved_x_items = [
        item
        for item in state["items"].values()
        if item.get("channel") == "x" and item.get("status") == "approved"
    ]

    if not approved_x_items:
        print("x_publish_done published=0 reason=no_approved_items")
        return 0

    published_count = 0
    for item in sorted(approved_x_items, key=lambda x: x.get("updated_at", "")):
        topic_id = item["topic_id"]
        draft = load_draft(topic_id)
        if not draft:
            print(f"x_publish_skip topic_id={topic_id} reason=draft_not_found", file=sys.stderr)
            continue

        x_posts = draft.get("x_posts", [])
        if not x_posts or not x_posts[0].get("text"):
            print(f"x_publish_skip topic_id={topic_id} reason=no_x_post_text", file=sys.stderr)
            continue

        tweet_text = x_posts[0]["text"]

        try:
            result = subprocess.run(
                ["twclaw", "tweet", tweet_text, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                # Try to extract post URL from JSON output
                post_url = ""
                try:
                    out = json.loads(result.stdout)
                    post_url = out.get("url", out.get("tweet_url", ""))
                except (json.JSONDecodeError, AttributeError):
                    pass

                set_state_item(
                    state, topic_id, "x", "published",
                    extra={"post_url": post_url, "published_at": iso_now()},
                )
                update_draft_status(topic_id, "x", "published")

                # Write to publish-log CSV
                log_path = PUBLISH_LOG_DIR / f"{date_str()}.csv"
                append_csv_row(
                    log_path,
                    ["topic_id", "channel", "post_url", "published_at", "impressions_24h", "engagement_rate"],
                    [topic_id, "x", post_url, iso_now(), "", ""],
                )
                sync_distribution_card(topic_id, "x", "published", package_ref=post_url, draft=draft)
                sync_feedback_card(topic_id, "x", published_url=post_url, draft=draft)
                published_count += 1
                print(f"x_publish_ok topic_id={topic_id} post_url={post_url}")
            else:
                # twclaw failed — likely auth issue, fall back to manual
                error_msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
                manual_path = _x_manual_fallback(topic_id, tweet_text, error_msg)
                set_state_item(
                    state, topic_id, "x", "publish_failed_auth",
                    extra={"error": error_msg, "manual_publish_file": str(manual_path)},
                )
                update_draft_status(topic_id, "x", "publish_failed_auth")
                sync_distribution_card(
                    topic_id,
                    "x",
                    "publish_failed_auth",
                    package_ref=str(manual_path),
                    draft=draft,
                )
                print(
                    f"x_publish_fallback topic_id={topic_id} "
                    f"reason=twclaw_error manual_file={manual_path}",
                    file=sys.stderr,
                )
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            manual_path = _x_manual_fallback(topic_id, tweet_text, error_msg)
            set_state_item(
                state, topic_id, "x", "publish_failed_auth",
                extra={"error": error_msg, "manual_publish_file": str(manual_path)},
            )
            update_draft_status(topic_id, "x", "publish_failed_auth")
            sync_distribution_card(
                topic_id,
                "x",
                "publish_failed_auth",
                package_ref=str(manual_path),
                draft=draft,
            )
            print(
                f"x_publish_fallback topic_id={topic_id} reason=exception error={error_msg}",
                file=sys.stderr,
            )

    save_state(state)
    print(f"x_publish_done published={published_count}")
    return 0


def _x_manual_fallback(topic_id: str, tweet_text: str, error: str) -> Path:
    """Generate a manual publish markdown for X when twclaw fails."""
    manual_path = APPROVALS_DIR / f"{topic_id}-x-manual-publish.md"
    publish_cmd = (
        f"bash /Users/chicho/.openclaw/workspace/scripts/content/approval_status.sh "
        f"publish {topic_id} x https://x.com/<your-handle>/status/<tweet-id>"
    )
    content = (
        f"# Manual X Publish - {topic_id}\n\n"
        f"- error: {error}\n"
        f"- fallback_reason: twclaw_auth_or_error\n"
        "- required_action: 手动登录 X 发布以下内容，然后回写 published 状态\n"
        f"- publish_action: {publish_cmd}\n\n"
        "## Tweet Text\n"
        f"```\n{tweet_text}\n```\n"
    )
    manual_path.write_text(content, encoding="utf-8")
    return manual_path


def cmd_xhs_publish(_: argparse.Namespace) -> int:
    """Publish approved note content to 小红书 via browser automation."""
    ensure_dirs()
    state = load_state()
    approved_note_items = [
        item
        for item in state["items"].values()
        if item.get("channel") == "note" and item.get("status") == "approved"
    ]

    if not approved_note_items:
        print("xhs_publish_done published=0 reason=no_approved_items")
        return 0

    published_count = 0
    for item in sorted(approved_note_items, key=lambda x: x.get("updated_at", "")):
        topic_id = item["topic_id"]
        draft = load_draft(topic_id)
        if not draft:
            print(f"xhs_publish_skip topic_id={topic_id} reason=draft_not_found", file=sys.stderr)
            continue

        note_body = draft.get("note_draft", "")
        if not note_body:
            print(f"xhs_publish_skip topic_id={topic_id} reason=no_note_draft", file=sys.stderr)
            continue

        topic_title = draft.get("topic_snapshot", {}).get("angle", topic_id)

        try:
            # Use openclaw invoke to trigger the xiaohongshu-publish skill
            # The skill is browser-based, so we call it via openclaw's skill runner
            result = subprocess.run(
                [
                    "openclaw", "skill", "run", "xiaohongshu-publish",
                    "--title", topic_title,
                    "--content", note_body,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                post_url = ""
                try:
                    out = json.loads(result.stdout)
                    post_url = out.get("url", out.get("post_url", ""))
                except (json.JSONDecodeError, AttributeError):
                    pass

                set_state_item(
                    state, topic_id, "note", "published",
                    extra={"post_url": post_url, "published_at": iso_now(), "platform": "xiaohongshu"},
                )
                update_draft_status(topic_id, "note", "published")

                log_path = PUBLISH_LOG_DIR / f"{date_str()}.csv"
                append_csv_row(
                    log_path,
                    ["topic_id", "channel", "post_url", "published_at", "impressions_24h", "engagement_rate"],
                    [topic_id, "note", post_url, iso_now(), "", ""],
                )
                sync_distribution_card(
                    topic_id,
                    "note",
                    "published",
                    package_ref=post_url,
                    publish_target="xiaohongshu",
                    draft=draft,
                )
                sync_feedback_card(topic_id, "note", published_url=post_url, draft=draft)
                published_count += 1
                print(f"xhs_publish_ok topic_id={topic_id} post_url={post_url}")
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
                manual_path = _xhs_manual_fallback(topic_id, topic_title, note_body, error_msg)
                set_state_item(
                    state, topic_id, "note", "publish_failed_auth",
                    extra={"error": error_msg, "manual_publish_file": str(manual_path), "platform": "xiaohongshu"},
                )
                update_draft_status(topic_id, "note", "publish_failed_auth")
                sync_distribution_card(
                    topic_id,
                    "note",
                    "publish_failed_auth",
                    package_ref=str(manual_path),
                    publish_target="xiaohongshu",
                    draft=draft,
                )
                print(
                    f"xhs_publish_fallback topic_id={topic_id} reason=skill_error manual_file={manual_path}",
                    file=sys.stderr,
                )
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            manual_path = _xhs_manual_fallback(topic_id, topic_title, note_body, error_msg)
            set_state_item(
                state, topic_id, "note", "publish_failed_auth",
                extra={"error": error_msg, "manual_publish_file": str(manual_path), "platform": "xiaohongshu"},
            )
            update_draft_status(topic_id, "note", "publish_failed_auth")
            sync_distribution_card(
                topic_id,
                "note",
                "publish_failed_auth",
                package_ref=str(manual_path),
                publish_target="xiaohongshu",
                draft=draft,
            )
            print(
                f"xhs_publish_fallback topic_id={topic_id} reason=exception error={error_msg}",
                file=sys.stderr,
            )

    save_state(state)
    print(f"xhs_publish_done published={published_count}")
    return 0


def _xhs_manual_fallback(topic_id: str, title: str, note_body: str, error: str) -> Path:
    """Generate a manual publish markdown for 小红书 when automation fails."""
    manual_path = APPROVALS_DIR / f"{topic_id}-xhs-manual-publish.md"
    publish_cmd = (
        f"bash /Users/chicho/.openclaw/workspace/scripts/content/approval_status.sh "
        f"publish {topic_id} note https://www.xiaohongshu.com/explore/<post-id>"
    )
    content = (
        f"# Manual 小红书 Publish - {topic_id}\n\n"
        f"- error: {error}\n"
        "- fallback_reason: xhs_publish_automation_failed\n"
        "- required_action: 手动登录小红书创作服务平台发布以下内容\n"
        "- publish_url: https://creator.xiaohongshu.com/publish/publish?source=official\n"
        f"- publish_action: {publish_cmd}\n\n"
        f"## Title\n{title}\n\n"
        "## Content\n"
        f"{note_body}\n\n"
        "## Suggested Tags\n"
        "- OpenClaw\n- AI工作流\n- 内容增长\n"
    )
    manual_path.write_text(content, encoding="utf-8")
    return manual_path


def cmd_note_publish_window(_: argparse.Namespace) -> int:
    ensure_dirs()
    env = parse_env()
    ok, missing = note_env_report(env)
    if not ok:
        raise RuntimeError(f"missing note env: {','.join(missing)}")

    mode = env.get("NOTE_PUBLISH_MODE", "").strip().lower()
    if mode not in {"semi_auto", "semi-auto", "semi", "auto"}:
        raise RuntimeError(f"unsupported NOTE_PUBLISH_MODE={mode}")

    state = load_state()
    approved_note_items = [
        item
        for item in state["items"].values()
        if item.get("channel") == "note" and item.get("status") == "approved"
    ]

    if not approved_note_items:
        print("note_publish_window_done approved_note=0")
        return 0

    item = sorted(approved_note_items, key=lambda x: x.get("updated_at", ""))[0]
    topic_id = item["topic_id"]
    draft = load_draft(topic_id)
    if not draft:
        raise RuntimeError(f"draft not found for topic_id={topic_id}")

    note_body = draft.get("note_draft", "")
    topic_title = draft.get("topic_snapshot", {}).get("angle", topic_id)
    x_slices = draft.get("x_slices", [])
    if isinstance(x_slices, list):
        x_block = "\n".join([f"- {x}" for x in x_slices])
    else:
        x_block = ""

    # Auto mode: attempt automated publish via note_publish_api.py
    if mode == "auto":
        try:
            env_vars = os.environ.copy()
            draft_json_path = DRAFTS_DIR / f"{topic_id}.json"
            image_plan = load_image_plan(topic_id)
            if not image_plan:
                build_image_plan_for_draft(draft)
                image_plan = load_image_plan(topic_id) or {}
            cover_path = WORKSPACE / "output" / "content-pipeline" / "covers" / f"{topic_id}-note-cover.png"
            illustration_dir = illustration_output_dir(topic_id)
            illustration_dir.mkdir(parents=True, exist_ok=True)

            if not cover_path.exists():
                ok_cover, cover_output = run_generate_from_draft(
                    draft_path=draft_json_path,
                    output_path=cover_path,
                    prompt_type="cover",
                    index=0,
                )
                print(
                    f"note_cover_generate topic_id={topic_id} ok={ok_cover} output={cover_output[:200]}",
                    file=sys.stderr,
                )

            illustration_paths: list[Path] = []
            for idx, _ in enumerate(image_plan.get("illustration_recommendations", [])[:2]):
                output_path = illustration_output_path(topic_id, idx)
                ok_image, image_output = run_generate_from_draft(
                    draft_path=draft_json_path,
                    output_path=output_path,
                    prompt_type="illustration",
                    index=idx,
                )
                print(
                    f"note_illustration_generate topic_id={topic_id} index={idx} "
                    f"ok={ok_image} output={image_output[:200]}",
                    file=sys.stderr,
                )
                if ok_image:
                    illustration_paths.append(output_path)

            manifest_path = build_content_manifest_for_draft(
                draft,
                image_plan,
                cover_path,
                illustration_paths,
            )
            cmd_args = [
                "python3",
                str(Path(__file__).parent / "note_publish_api.py"),
                "--title", topic_title,
                "--content-manifest", str(manifest_path),
            ]

            if cover_path.exists():
                cmd_args.extend(["--cover", str(cover_path)])
                print(f"note_publish_with_cover topic_id={topic_id} cover={cover_path}", file=sys.stderr)
            else:
                print(f"note_publish_no_cover topic_id={topic_id}", file=sys.stderr)
            
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=600,  # 增加到10分钟超时
                env=env_vars,
            )
            
            # 解析输出
            post_url = ""
            try:
                out = json.loads(result.stdout)
                if out.get("status") == "ok":
                    post_url = out.get("url", "")
                    verified_via = out.get("verified_via", "")
                else:
                    verified_via = ""
            except (json.JSONDecodeError, AttributeError):
                verified_via = ""
            
            # 如果有 URL，标记为已发布
            if post_url:
                set_state_item(
                    state, topic_id, "note", "published",
                    extra={"post_url": post_url, "published_at": iso_now(), "verified_via": verified_via},
                )
                update_draft_status(topic_id, "note", "published")
                log_path = PUBLISH_LOG_DIR / f"{date_str()}.csv"
                append_csv_row(
                    log_path,
                    ["topic_id", "channel", "post_url", "published_at", "impressions_24h", "engagement_rate"],
                    [topic_id, "note", post_url, iso_now(), "", ""],
                )
                sync_distribution_card(topic_id, "note", "published", package_ref=post_url, draft=draft)
                sync_feedback_card(topic_id, "note", published_url=post_url, draft=draft)
                save_state(state)
                if verified_via == "author_page":
                    print(f"note_publish_verified_from_author_page topic_id={topic_id} post_url={post_url}")
                else:
                    print(f"note_publish_verified_from_page topic_id={topic_id} post_url={post_url}")
                return 0
            else:
                print(f"note_publish_unverified topic_id={topic_id}", file=sys.stderr)
                unverified_path = APPROVALS_DIR / f"{topic_id}-note-unverified.md"
                unverified_path.write_text(
                    (
                        f"# Note Publish Unverified - {topic_id}\n\n"
                        f"- title: {topic_title}\n"
                        f"- note_author_url: {env.get('NOTE_AUTHOR_URL', '')}\n"
                        "- reason: publish completed but no verified public URL was found\n"
                        "- required_action: 手动检查作者页与草稿页，确认是否真的公开成功\n"
                    ),
                    encoding="utf-8",
                )
                set_state_item(
                    state, topic_id, "note", "publish_unverified",
                    extra={
                        "published_at": iso_now(),
                        "note": "No URL returned and author page verification failed",
                        "manual_publish_file": str(unverified_path),
                    },
                )
                update_draft_status(topic_id, "note", "publish_unverified")
                sync_distribution_card(topic_id, "note", "publish_unverified", package_ref=str(unverified_path), draft=draft)
                sync_feedback_card(topic_id, "note", draft=draft)
                save_state(state)
                print(f"note_publish_unverified topic_id={topic_id}")
                return 0
                
        except subprocess.TimeoutExpired:
            print(f"note_publish_timeout topic_id={topic_id} (5min timeout)", file=sys.stderr)
            raise RuntimeError(f"note publish timeout after 5 minutes")
        except Exception as e:
            print(f"note_publish_failed topic_id={topic_id} error={e}", file=sys.stderr)
            raise

    # Semi-auto or auto fallback: generate manual publish file
    manual_path = APPROVALS_DIR / f"{topic_id}-note-manual-publish.md"

    manual_content = (
        f"# Manual Publish Package - {topic_id}\n\n"
        f"- title: {topic_title}\n"
        f"- note_author_url: {env.get('NOTE_AUTHOR_URL', '')}\n"
        f"- fallback_reason: auth_challenge_or_2fa\n"
        "- required_action: 手动登录 note 发布本文，然后回写 published 状态\n"
        "- publish_action: bash /Users/chicho/.openclaw/workspace/scripts/content/approval_status.sh "
        f"publish {topic_id} note https://note.com/<your-account>/n/<post-id>\n\n"
        "## Suggested Tags\n"
        "- OpenClaw\n- AI工作流\n- 内容增长\n\n"
        "## Draft Body\n"
        f"{note_body}\n\n"
        "## X Slices\n"
        f"{x_block}\n"
    )
    manual_path.write_text(manual_content, encoding="utf-8")

    set_state_item(
        state,
        topic_id,
        "note",
        "publish_failed_auth",
        extra={"manual_publish_file": str(manual_path)},
    )
    save_state(state)
    update_draft_status(topic_id, "note", "publish_failed_auth")
    sync_distribution_card(
        topic_id,
        "note",
        "publish_failed_auth",
        package_ref=str(manual_path),
        draft=draft,
    )

    print(
        "note_publish_window_done "
        f"topic_id={topic_id} status=publish_failed_auth manual_file={manual_path}"
    )
    return 0


def parse_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def cmd_metrics_rollup(args: argparse.Namespace) -> int:
    ensure_dirs()
    day = args.date or date_str()

    publish_rows = load_csv_rows(PUBLISH_LOG_DIR / f"{day}.csv")
    leads_path = LEADS_DIR / f"{day}.csv"
    ensure_csv_header(
        leads_path,
        [
            "lead_id",
            "source_channel",
            "handle",
            "intent_level",
            "next_action",
            "owner",
            "status",
        ],
    )
    lead_rows = load_csv_rows(leads_path)

    note_published = [r for r in publish_rows if r.get("channel") == "note"]

    engagement_vals = [parse_float(r.get("engagement_rate", "0")) for r in note_published]
    avg_engagement = sum(engagement_vals) / len(engagement_vals) if engagement_vals else 0.0

    for row in note_published:
        metrics_snapshot = {
            "published_at": row.get("published_at", ""),
            "impressions_24h": row.get("impressions_24h", ""),
            "engagement_rate": row.get("engagement_rate", ""),
        }
        sync_distribution_card(
            row.get("topic_id", ""),
            row.get("channel", ""),
            "published",
            package_ref=row.get("post_url", ""),
        )
        sync_feedback_card(
            row.get("topic_id", ""),
            row.get("channel", ""),
            published_url=row.get("post_url", ""),
            metrics_snapshot=metrics_snapshot,
        )

    state = load_state()
    status_counts = {k: 0 for k in sorted(VALID_STATUS)}
    for item in state.get("items", {}).values():
        if item.get("channel") != "note":
            continue
        status = item.get("status")
        if status in status_counts:
            status_counts[status] += 1

    report = (
        f"# Content Metrics Rollup - {day}\n\n"
        f"- timezone: Asia/Tokyo\n"
        f"- note_published_today: {len(note_published)}\n"
        f"- leads_today: {len(lead_rows)}\n"
        f"- avg_note_engagement_rate: {avg_engagement:.3f}\n\n"
        "## Note Approval State\n"
        + "\n".join([f"- {k}: {v}" for k, v in status_counts.items()])
        + "\n"
    )

    path = METRICS_DIR / f"{day}.md"
    path.write_text(report, encoding="utf-8")
    print(
        "metrics_rollup_done "
        f"date={day} note_published={len(note_published)} leads={len(lead_rows)} file={path}"
    )
    return 0


def daterange_days(end_day: datetime, count: int) -> list[str]:
    return [date_str(end_day - timedelta(days=i)) for i in range(count - 1, -1, -1)]


def cmd_weekly_review(_: argparse.Namespace) -> int:
    ensure_dirs()
    today = now_jst()
    days = daterange_days(today, 7)

    total_note = 0
    total_leads = 0

    for d in days:
        publish_rows = load_csv_rows(PUBLISH_LOG_DIR / f"{d}.csv")
        total_note += sum(1 for r in publish_rows if r.get("channel") == "note")
        total_leads += len(load_csv_rows(LEADS_DIR / f"{d}.csv"))

    progress_note = f"{total_note}/1"
    progress_leads = f"{total_leads}/10-20"

    next_actions: list[str] = []
    if total_note < 1:
        next_actions.append("确保周三 note 发布窗口前完成审批，避免卡在发布环节。")
    if total_leads < 10:
        next_actions.append("优化 CTA 文案，增加私信关键词触发与案例型内容占比。")
    if not next_actions:
        next_actions.append("保持当前节奏，进入 A/B 测试阶段优化转化率。")

    report = (
        f"# Weekly Content Review ({days[0]} ~ {days[-1]})\n\n"
        "## KPI Progress\n"
        f"- note_posts: {progress_note}\n"
        f"- effective_leads: {progress_leads}\n\n"
        "## Next Week Focus\n"
        + "\n".join([f"- {x}" for x in next_actions])
        + "\n"
    )

    out_path = WEEKLY_DIR / f"{days[-1]}.md"
    out_path.write_text(report, encoding="utf-8")
    print(
        "weekly_review_done "
        f"range={days[0]}~{days[-1]} note={total_note} leads={total_leads} file={out_path}"
    )
    return 0


def cmd_image_plan(args: argparse.Namespace) -> int:
    ensure_dirs()
    draft: dict[str, Any] | None = None
    if args.topic_id:
        draft = load_draft(args.topic_id)
    else:
        drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if drafts:
            draft = load_json(drafts[0], None)

    if not draft:
        raise RuntimeError("image_plan_requires_existing_draft")

    path = build_image_plan_for_draft(draft)
    payload = load_json(path, {})
    print(
        "image_plan_done "
        f"topic_id={draft.get('topic_id')} "
        f"cover={len(payload.get('cover_recommendations', []))} "
        f"illustration={len(payload.get('illustration_recommendations', []))} "
        f"file={path}"
    )
    return 0


def cmd_validate_prompt_repo(_: argparse.Namespace) -> int:
    ensure_dirs()
    report = validate_prompt_repo()
    cover = report.get("cover", [])
    illustration = report.get("illustration", [])
    invalid = [
        item
        for group in [cover, illustration]
        for item in group
        if item.get("missing")
    ]
    print(
        "prompt_repo_validation "
        f"cover={len(cover)} illustration={len(illustration)} invalid={len(invalid)}"
    )
    if len(cover) < 10 or len(illustration) < 10 or invalid:
        return 1
    return 0


def cmd_build_content_manifest(args: argparse.Namespace) -> int:
    ensure_dirs()
    topic_id = args.topic_id
    if not topic_id:
        raise RuntimeError("build_content_manifest_requires_topic_id")

    draft = load_draft(topic_id)
    if not draft:
        raise RuntimeError(f"draft_not_found topic_id={topic_id}")

    image_plan = load_image_plan(topic_id)
    if not image_plan:
        raise RuntimeError(f"image_plan_not_found topic_id={topic_id}")

    cover_path = WORKSPACE / "output" / "content-pipeline" / "covers" / f"{topic_id}-note-cover.png"
    illustration_paths = [
        illustration_output_path(topic_id, idx)
        for idx, _ in enumerate(image_plan.get("illustration_recommendations", []))
    ]
    manifest = build_content_manifest_for_draft(draft, image_plan, cover_path, illustration_paths)
    print(f"content_manifest_done topic_id={topic_id} file={manifest}")
    return 0


def cmd_prompt_ingest(args: argparse.Namespace) -> int:
    ensure_dirs()
    day = args.date or date_str()
    seeds = load_prompt_source_seeds()
    if not seeds:
        raise RuntimeError("prompt_ingest_requires_seed_sources")

    created = 0
    for index, seed in enumerate(seeds, start=1):
        url = str(seed.get("source_url", "") or "")
        label = str(seed.get("label", "") or f"seed-{index:02d}")
        fetch_status = "ok"
        title = label
        snippet = str(seed.get("query_hint", "") or "")

        try:
            raw = _fetch_url_bytes(url, timeout=FEED_TIMEOUT)
            title = extract_html_title(raw) or title
        except Exception as exc:  # noqa: BLE001
            fetch_status = "fetch_failed"
            if not snippet:
                snippet = str(exc)

        canonical_id = f"prompt-intake-{day.replace('-', '')}-{index:02d}"
        frontmatter = {
            "title": f"候选｜{label}",
            "kind": "prompt_candidate",
            "stage": "captured",
            "canonical_id": canonical_id,
            "origin_platform": "content-hub",
            "source_role": ["pattern"],
            "platform_targets": ["note"],
            "language_targets": ["ja"],
            "source_urls": [url] if url else [],
            "derived_from": [],
            "tags": [
                "prompt-intake",
                str(seed.get("source_origin", "manual")).lower(),
                str(seed.get("suggested_prompt_type", "cover")).lower(),
            ],
            "status": "review_needed",
            "created_at": iso_now(),
            "updated_at": iso_now(),
            "source_origin": seed.get("source_origin", "manual"),
            "source_url": url,
            "suggested_prompt_type": seed.get("suggested_prompt_type", "cover"),
            "manual_review_required": True,
            "fetch_status": fetch_status,
        }
        body = build_prompt_intake_body(seed, fetch_status, title, snippet)
        path = prompt_intake_card_path(day, seed, index)
        write_hub_card(path, frontmatter, body)
        created += 1

    print(f"prompt_ingest_done date={day} created={created} dir={PROMPT_REPO_INTAKE_DIR}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw content pipeline helper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ensure_dirs")
    sub.add_parser("validate_env")
    p_xhs_prewarm = sub.add_parser("xhs_prewarm")
    p_xhs_prewarm.add_argument("--json", action="store_true")

    p_topic = sub.add_parser("topic_scan")
    p_topic.add_argument("--date", default="")
    p_topic.add_argument("--profile", choices=["full", "social_fast"], default="full")

    p_x = sub.add_parser("x_draft")
    p_x.add_argument("--date", default="")

    p_note_outline = sub.add_parser("note_outline")
    p_note_outline.add_argument("--date", default="")

    sub.add_parser("note_draft")

    p_image_plan = sub.add_parser("image_plan")
    p_image_plan.add_argument("--topic-id", default="")
    p_manifest = sub.add_parser("build_content_manifest")
    p_manifest.add_argument("--topic-id", required=True)

    p_push = sub.add_parser("approval_push")
    p_push.add_argument("channel", choices=["x", "note"])
    p_push.add_argument("--max-items", type=int, default=3)

    p_status = sub.add_parser("approval_status")
    p_status.add_argument("action", choices=["approve", "reject", "changes_requested", "publish", "fail_auth"])
    p_status.add_argument("topic_id")
    p_status.add_argument("channel", choices=["x", "note"])
    p_status.add_argument("post_url", nargs="?")
    p_status.add_argument("--review-note", default="")
    p_status.add_argument("--reviewed-via", default="")
    p_status.add_argument("--review-message-id", default="")

    sub.add_parser("note_publish_window")

    sub.add_parser("x_publish")

    sub.add_parser("xhs_publish")

    p_metrics = sub.add_parser("metrics_rollup")
    p_metrics.add_argument("--date", default="")

    sub.add_parser("weekly_review")
    sub.add_parser("validate_prompt_repo")
    p_ingest = sub.add_parser("prompt_ingest")
    p_ingest.add_argument("--date", default="")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "ensure_dirs": cmd_ensure_dirs,
        "validate_env": cmd_validate_env,
        "xhs_prewarm": cmd_xhs_prewarm,
        "topic_scan": cmd_topic_scan,
        "x_draft": cmd_x_draft,
        "note_outline": cmd_note_outline,
        "note_draft": cmd_note_draft,
        "image_plan": cmd_image_plan,
        "build_content_manifest": cmd_build_content_manifest,
        "approval_push": cmd_approval_push,
        "approval_status": cmd_approval_status,
        "note_publish_window": cmd_note_publish_window,
        "x_publish": cmd_x_publish,
        "xhs_publish": cmd_xhs_publish,
        "metrics_rollup": cmd_metrics_rollup,
        "weekly_review": cmd_weekly_review,
        "validate_prompt_repo": cmd_validate_prompt_repo,
        "prompt_ingest": cmd_prompt_ingest,
    }

    try:
        return handlers[args.command](args)
    except Exception as exc:  # noqa: BLE001
        print(f"content_pipeline_error command={args.command} message={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
