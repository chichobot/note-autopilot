# content_pipeline.py 重构执行计划

## 阶段一：标记可删除的代码

### 可以立即删除的命令（5 个）

```python
# 1. cmd_approval_status - 模型可以直接读 JSON
def cmd_approval_status(args: argparse.Namespace) -> int:
    # DELETE: 模型可以直接 read JSON 文件

# 2. cmd_metrics_rollup - 模型可以直接统计
def cmd_metrics_rollup(args: argparse.Namespace) -> int:
    # DELETE: 模型可以直接读数据并统计

# 3. cmd_weekly_review - 模型可以直接生成周报
def cmd_weekly_review(_: argparse.Namespace) -> int:
    # DELETE: 模型可以直接读数据并生成报告

# 4. cmd_note_outline - 模型可以直接生成大纲
def cmd_note_outline(args: argparse.Namespace) -> int:
    # DELETE: 模型可以直接生成大纲

# 5. cmd_x_draft - 模型可以直接生成推文
def cmd_x_draft(args: argparse.Namespace) -> int:
    # DELETE: 模型可以直接生成推文
```

### 可以删除的文本处理函数（15+ 个）

```python
# 提取类
def extract_markdown_title(markdown: str) -> str:
    # DELETE: 模型可以直接提取

def extract_markdown_bullets(markdown: str, limit: int = 3) -> list[str]:
    # DELETE: 模型可以直接提取

def extract_markdown_sections(markdown: str, limit: int = 4) -> list[str]:
    # DELETE: 模型可以直接提取

def extract_markdown_summary(markdown: str, limit: int = 220) -> str:
    # DELETE: 模型可以直接生成摘要

def extract_html_title(raw: bytes) -> str:
    # DELETE: 模型可以直接提取

# 推断类
def infer_article_type(title: str, summary: str) -> str:
    # DELETE: 模型可以直接推断

def infer_topic_status(topic: dict[str, Any]) -> tuple[str, list[str]]:
    # DELETE: 模型可以直接推断

# 指导类
def guidance_for_risk_flag(flag: str) -> str:
    # DELETE: 模型可以直接生成指导

def guidance_for_risk_flags(risk_flags: list[str]) -> str:
    # DELETE: 模型可以直接生成指导

def build_review_recommendation(draft: dict[str, Any], channel: str) -> tuple[str, str]:
    # DELETE: 模型可以直接生成建议

# 语言处理类
def is_likely_japanese_text(text: str) -> bool:
    # DELETE: 模型可以直接判断

def translate_risk_flag_to_ja(flag: str) -> str:
    # DELETE: 模型可以直接翻译

def normalize_japanese_audience(audience: str) -> str:
    # DELETE: 模型可以直接规范化

def localize_risk_flags_for_note(risk_flags: list[str]) -> list[str]:
    # DELETE: 模型可以直接本地化

# 评分和推荐类
def score_prompt_card(
    card: PromptCard,
    context: dict[str, Any],
    *,
    section_focus: str = "",
) -> float:
    # DELETE: 模型可以直接评分

def recommend_prompt_cards(
    context: dict[str, Any],
    prompt_type: str,
    *,
    section_focus: str = "",
    limit: int = 3,
) -> list[PromptCard]:
    # DELETE: 模型可以直接推荐
```

### 可以删除的格式转换函数（10+ 个）

```python
def render_frontmatter(data: dict[str, Any]) -> str:
    # DELETE: 模型可以直接生成

def render_prompt_template(template: str, variables: dict[str, str]) -> str:
    # DELETE: 模型可以直接渲染

def build_approval_markdown(topic_id: str, channel: str, draft: dict[str, Any]) -> str:
    # DELETE: 模型可以直接构造

def build_prompt_context(draft: dict[str, Any]) -> dict[str, Any]:
    # DELETE: 模型可以直接构造

def build_render_variables(context: dict[str, Any], card: PromptCard, *, section_focus: str = "") -> dict[str, str]:
    # DELETE: 模型可以直接构造

def build_image_plan_for_draft(draft: dict[str, Any]) -> Path:
    # DELETE: 模型可以直接生成图片计划

def build_content_manifest_for_draft(
    draft: dict[str, Any],
    *,
    note_draft: str,
    cover_path: Path | None = None,
    illustrations: list[Path] | None = None,
) -> Path:
    # DELETE: 模型可以直接生成 manifest

def build_frontmatter(
    canonical_id: str,
    topic: dict[str, Any],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # DELETE: 模型可以直接构造

def build_prompt_intake_body(seed: dict[str, Any], fetch_status: str, title: str, snippet: str) -> str:
    # DELETE: 模型可以直接构造
```

### 可以简化的过度封装（10+ 个）

```python
def now_jst() -> datetime:
    # SIMPLIFY: 直接用 datetime.now(ZoneInfo("Asia/Tokyo"))

def iso_now() -> str:
    # SIMPLIFY: 直接用 datetime.now().isoformat()

def date_str(dt: datetime | None = None) -> str:
    # SIMPLIFY: 直接用 strftime

def hub_rel(path: Path) -> str:
    # SIMPLIFY: 直接用 path.relative_to()

def json_scalar(value: Any) -> str:
    # SIMPLIFY: 直接用 json.dumps()

def normalize_list_field(value: Any) -> list[str]:
    # SIMPLIFY: 直接处理

def canonical_id_for_topic(topic: dict[str, Any]) -> str:
    # SIMPLIFY: 直接访问 topic["id"]

def card_ref(path: Path) -> str:
    # SIMPLIFY: 直接用字符串格式化

def source_family_from_url(url: str) -> str:
    # SIMPLIFY: 模型可以直接判断

def source_family_from_candidate(source: str, urls: list[str]) -> str:
    # SIMPLIFY: 模型可以直接判断
```

---

## 阶段二：保留的核心代码

### 必须保留的命令（5 个）

```python
# 1. cmd_topic_scan - 扫描热点（外部 API）
def cmd_topic_scan(args: argparse.Namespace) -> int:
    # KEEP: 调用 Reddit/X/小红书 API

# 2. cmd_note_draft - 生成草稿（简化版）
def cmd_note_draft(_: argparse.Namespace) -> int:
    # KEEP: 调用 Gemini API
    # SIMPLIFY: 提示词构造交给模型

# 3. cmd_note_publish_window - 发布到 note.com
def cmd_note_publish_window(_: argparse.Namespace) -> int:
    # KEEP: 调用 note.com API

# 4. cmd_x_publish - 发布到 X
def cmd_x_publish(_: argparse.Namespace) -> int:
    # KEEP: 调用 X API

# 5. cmd_xhs_publish - 发布到小红书
def cmd_xhs_publish(_: argparse.Namespace) -> int:
    # KEEP: 调用小红书 API
```

### 必须保留的工具函数（20+ 个）

```python
# 数据管理
def load_json(path: Path, default: Any) -> Any:
    # KEEP: 基础 IO

def save_json(path: Path, data: Any) -> None:
    # KEEP: 基础 IO

def load_state() -> dict[str, Any]:
    # KEEP: 状态管理

def save_state(state: dict[str, Any]) -> None:
    # KEEP: 状态管理

def load_draft(topic_id: str) -> dict[str, Any] | None:
    # KEEP: 草稿管理

def save_draft(draft: dict[str, Any]) -> Path:
    # KEEP: 草稿管理

def load_topics(day: str | None = None) -> dict[str, Any] | None:
    # KEEP: 主题加载

# 外部调用
def _run_cli(cmd: list[str], timeout: int = 30) -> str:
    # KEEP: 外部命令调用

def _run_json_cli(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    # KEEP: 外部命令调用

def _fetch_url_bytes(url: str, timeout: int = FEED_TIMEOUT) -> bytes:
    # KEEP: HTTP 请求

def _parse_feed_items(raw: bytes, limit: int = FEED_ITEM_LIMIT) -> list[dict[str, str]]:
    # KEEP: RSS 解析

def verify_note_post_by_title(author_url: str, expected_title: str, timeout: int = 20) -> str:
    # KEEP: note.com 验证

# 小红书相关
def _run_xiaohongshu_feeds_cli() -> dict[str, Any]:
    # KEEP: 小红书 API

def _check_xiaohongshu_health() -> tuple[bool, dict[str, Any]]:
    # KEEP: 小红书健康检查

def _load_xiaohongshu_feeds_cache() -> dict[str, Any] | None:
    # KEEP: 缓存管理

def _save_xiaohongshu_feeds_cache(payload: dict[str, Any]) -> None:
    # KEEP: 缓存管理

# 解析器（外部数据）
def _parse_twclaw_trending(output: str) -> list[dict[str, Any]]:
    # KEEP: 解析外部 CLI 输出

def _parse_twclaw_search(output: str, query: str) -> list[dict[str, Any]]:
    # KEEP: 解析外部 CLI 输出

def _parse_reddit_posts(output: str, subreddit: str) -> list[dict[str, Any]]:
    # KEEP: 解析外部 CLI 输出

def _parse_xiaohongshu_search(output: str, keyword: str) -> list[dict[str, Any]]:
    # KEEP: 解析外部 CLI 输出

def _parse_xiaohongshu_feeds(output: Any) -> list[dict[str, Any]]:
    # KEEP: 解析外部 API 输出

def _parse_video_watcher(output: str) -> list[dict[str, Any]]:
    # KEEP: 解析外部 CLI 输出
```

---

## 执行步骤

### 第一步：备份
```bash
cp content_pipeline.py content_pipeline.py.backup
```

### 第二步：标记删除
在每个可删除的函数前加注释：
```python
# DELETE: 模型可以直接处理
# Reason: 文本提取/判断/生成
```

### 第三步：创建精简版
```bash
# 创建新文件
cp content_pipeline.py content_pipeline_minimal.py

# 删除所有标记为 DELETE 的函数
# 简化所有标记为 SIMPLIFY 的函数
```

### 第四步：测试
```bash
# 测试核心命令是否正常
python3 content_pipeline_minimal.py topic_scan --profile social_fast
python3 content_pipeline_minimal.py note_publish_window
```

---

## 预期结果

**当前：** 4400 行  
**删除后：** ~1400 行  
**进一步简化后：** ~1000 行

**代码结构：**
```
content_pipeline_minimal.py
├── 核心命令（5 个）
│   ├── topic_scan
│   ├── note_draft
│   ├── note_publish
│   ├── x_publish
│   └── xhs_publish
├── 数据管理（10 个函数）
├── 外部调用（10 个函数）
└── 解析器（10 个函数）
```

**模型负责：**
- 所有文本理解和生成
- 所有判断和推理
- 所有格式转换
- 审批决策
- 数据分析
- 报告生成
