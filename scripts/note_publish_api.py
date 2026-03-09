#!/usr/bin/env python3
"""
note.com API 发布脚本
优先走 API 创建/保存/发布，避免 editor.note.com/new 前端初始化链不稳定。
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional
from uuid import uuid4

ROOT = Path("/Users/chicho/.openclaw")
sys.path.insert(0, str(ROOT / "workspace-coder"))
from note_api_publish import NotePublisher  # type: ignore


def parse_env_file() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        return env
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def ensure_env_loaded() -> dict[str, str]:
    env = parse_env_file()
    for key, value in env.items():
        os.environ.setdefault(key, value)
    return env


def load_content_manifest(manifest_path: Optional[str]) -> Optional[dict]:
    if not manifest_path:
        return None
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"content_manifest 不存在: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("content_blocks"), list):
        raise ValueError("content_manifest 缺少 content_blocks")
    return payload


def html_escape(text: str) -> str:
    return html.escape(text, quote=True)


def make_uuid() -> str:
    return str(uuid4())


def append_paragraph(chunks: list[str], lines: list[str]) -> None:
    text = " ".join(line.strip() for line in lines if line.strip())
    if not text:
        return
    uid = make_uuid()
    chunks.append(f'<p name="{uid}" id="{uid}">{html_escape(text)}</p>')


def render_markdown_block(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    chunks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_kind: Optional[str] = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        append_paragraph(chunks, paragraph)
        paragraph = []

    def flush_list() -> None:
        nonlocal list_items, list_kind
        if list_items and list_kind:
            uid = make_uuid()
            body = "".join(f"<li>{html_escape(item)}</li>" for item in list_items)
            chunks.append(f'<{list_kind} name="{uid}" id="{uid}">{body}</{list_kind}>')
        list_items = []
        list_kind = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        if stripped == "---":
            flush_paragraph()
            flush_list()
            uid = make_uuid()
            chunks.append(f'<hr name="{uid}" id="{uid}"/>')
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            uid = make_uuid()
            chunks.append(f'<h2 name="{uid}" id="{uid}">{html_escape(stripped[3:].strip())}</h2>')
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            uid = make_uuid()
            chunks.append(f'<h3 name="{uid}" id="{uid}">{html_escape(stripped[4:].strip())}</h3>')
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if unordered:
            flush_paragraph()
            if list_kind not in {None, "ul"}:
                flush_list()
            list_kind = "ul"
            list_items.append(unordered.group(1).strip())
            continue
        if ordered:
            flush_paragraph()
            if list_kind not in {None, "ol"}:
                flush_list()
            list_kind = "ol"
            list_items.append(ordered.group(1).strip())
            continue

        if list_kind:
            flush_list()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return chunks


def upload_note_image(publisher: NotePublisher, note_id: int, image_path: str) -> str:
    image_url = publisher.upload_eyecatch(note_id, image_path)
    if not image_url:
        raise RuntimeError(f"image_upload_failed path={image_path}")
    return image_url


def build_html_body_from_manifest(
    publisher: NotePublisher,
    note_id: int,
    manifest: dict,
) -> tuple[str, Optional[str]]:
    chunks: list[str] = []
    cover_image_path = manifest.get("cover_image") or ""
    cover_url: Optional[str] = None

    # 先上传正文插图，再上传封面，确保最终 eyecatch 仍是 cover。
    uploaded_image_urls: dict[str, str] = {}
    for block in manifest.get("content_blocks", []):
        if block.get("type") != "image":
            continue
        image_path = str(block.get("image_path") or "")
        if not image_path:
            continue
        uploaded_image_urls[image_path] = upload_note_image(publisher, note_id, image_path)

    if cover_image_path and Path(cover_image_path).exists():
        cover_url = upload_note_image(publisher, note_id, str(cover_image_path))

    # 插入目录标签
    toc_id = make_uuid()
    chunks.append(f'<table-of-contents name="{toc_id}" id="{toc_id}"><br></table-of-contents>')

    for block in manifest.get("content_blocks", []):
        if block.get("type") == "text":
            chunks.extend(render_markdown_block(str(block.get("markdown") or "")))
            continue
        if block.get("type") == "image":
            image_path = str(block.get("image_path") or "")
            image_url = uploaded_image_urls.get(image_path, "")
            if not image_url:
                continue
            uid = make_uuid()
            alt_text = block.get("section_heading") or block.get("target_section") or "illustration"
            chunks.append(
                f'<figure name="{uid}" id="{uid}"><img src="{html_escape(image_url)}" alt="{html_escape(str(alt_text))}" /></figure>'
            )

    return "".join(chunks), cover_url


def verify_note_url(note_url: str, title: str) -> bool:
    req = urllib.request.Request(note_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    return title in body


def verify_note_via_author_page(author_url: str, title: str) -> str:
    if not author_url:
        return ""
    req = urllib.request.Request(author_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    escaped_title = re.escape(title.strip())
    patterns = [
        rf'href="(https://note\.com/[^"]+/n/[A-Za-z0-9]+)"[^>]*>[^<]*{escaped_title}',
        rf'href="(/[^"]+/n/[A-Za-z0-9]+)"[^>]*>[^<]*{escaped_title}',
    ]
    for pattern in patterns:
        match = re.search(pattern, body)
        if match:
            href = match.group(1)
            return href if href.startswith("http") else f"https://note.com{href}"
    return ""


def publish_via_api(
    *,
    title: str,
    content: Optional[str],
    cover: Optional[str],
    content_manifest_path: Optional[str],
) -> dict:
    ensure_env_loaded()
    email = os.getenv("NOTE_EMAIL", "")
    password = os.getenv("NOTE_PASSWORD", "")
    author_url = os.getenv("NOTE_AUTHOR_URL", "")
    if not email or not password:
        return {"status": "error", "error": "NOTE_EMAIL or NOTE_PASSWORD missing"}

    manifest = load_content_manifest(content_manifest_path)
    publisher = NotePublisher(email=email, password=password)
    if not publisher.sign_in():
        return {"status": "error", "error": "sign_in_failed"}

    note_id = publisher._create_note(title)
    if not note_id:
        return {"status": "error", "error": "create_note_failed"}

    try:
        if manifest:
            html_body, cover_url = build_html_body_from_manifest(publisher, note_id, manifest)
        else:
            html_body = publisher._convert_to_html(content or "", enable_toc=True)
            cover_url = upload_note_image(publisher, note_id, cover) if cover and Path(cover).exists() else None
        if not publisher._save_draft(note_id, title, html_body, True):
            return {"status": "error", "error": "save_draft_failed", "note_id": note_id}

        note_url = publisher._publish_note(note_id, title, html_body, cover_url, True)
        if note_url:
            for _ in range(3):
                try:
                    if verify_note_url(note_url, title):
                        return {"status": "ok", "url": note_url, "verified_via": "publish_response", "note_id": note_id}
                except Exception:
                    pass
                time.sleep(2)

        verified_url = ""
        for _ in range(3):
            try:
                verified_url = verify_note_via_author_page(author_url, title)
                if verified_url and verify_note_url(verified_url, title):
                    return {"status": "ok", "url": verified_url, "verified_via": "author_page", "note_id": note_id}
            except Exception:
                pass
            time.sleep(2)

        return {
            "status": "unverified",
            "error": "publish_completed_but_url_not_verified",
            "note_id": note_id,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"api_publish_failed: {exc}", "note_id": note_id}


def main():
    parser = argparse.ArgumentParser(description="note.com API publish script")
    parser.add_argument("--title", required=True)
    parser.add_argument("--content")
    parser.add_argument("--cover")
    parser.add_argument("--content-manifest")
    args = parser.parse_args()

    result = publish_via_api(
        title=args.title,
        content=args.content,
        cover=args.cover,
        content_manifest_path=args.content_manifest,
    )
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
