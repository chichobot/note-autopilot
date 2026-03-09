---
name: note-autopilot
description: 全自动 note.com 内容生产流水线：热点扫描 → 草稿生成 → Telegram 审批 → 自动发布
metadata: {"openclaw": {"requires": {"bins": ["python3"], "env": ["GEMINI_API_KEY", "NOTE_SESSION"]}, "primaryEnv": "GEMINI_API_KEY", "emoji": "📝"}}
---

# Note Autopilot Skill

全自动 note.com 内容生产流水线（半自动模式）。

## 触发条件

**用户说以下任何一句话时，使用此 skill：**
- "扫描热点"、"找爆款"、"note 选题"
- "生成草稿"、"写 note"
- "推送审批"、"发审批卡"
- "发布 note"
- "callback_data:xxx"（Telegram 按钮回调）

## 工作流程

### 1. 扫描热点
```bash
bash {baseDir}/scripts/topic_scan.sh
```

**输出：**
- 候选列表（JSON）
- 最高分 topic_id
- 数据源健康状态

**验证点：**
- ✅ 必须输出候选数量
- ✅ 必须输出最高分和来源

### 2. 生成大纲
```bash
bash {baseDir}/scripts/note_outline.sh
```

**输出：**
- 大纲文件（JSON）
- topic_id

**验证点：**
- ✅ 必须输出 topic_id

### 3. 生成草稿
```bash
bash {baseDir}/scripts/note_draft.sh
```

**输出：**
- 草稿文件（Markdown，日文）
- image_plan（图片生成计划）

**验证点：**
- ✅ 必须检测语言（中文直接中止）
- ✅ 字数 ≥ 800

### 4. 生成图片（封面 + 插图）
```bash
python3 {baseDir}/scripts/generate_images.py --topic-id <topic_id>
```

**输出：**
- 封面图（PNG，16:9）
- 正文插图（PNG，16:9）

**验证点：**
- ✅ 必须生成至少 1 张图片（封面）
- ✅ 图片路径必须正确

### 5. 构建 content manifest
```bash
python3 {baseDir}/scripts/content_pipeline.py build_content_manifest --topic-id <topic_id>
```

**输出：**
- content manifest（JSON，包含图片路径）

**验证点：**
- ✅ 必须包含 cover_image
- ✅ 必须包含 content_blocks

### 6. 推送审批（Telegram）
```bash
python3 {baseDir}/scripts/telegram_approval.py send --topic-id <topic_id> --channel note
```

**输出：**
- Telegram 审批卡（带按钮）
- message_id

**验证点：**
- ✅ 必须拿到 message_id

### 7. 处理审批回调
**当收到 `callback_data:xxx` 格式的消息时：**

```bash
python3 {baseDir}/scripts/telegram_approval.py callback --data "<callback_data>"
```

**回调格式：**
- `approve:<topic_id>:<channel>` - 批准
- `reject:<topic_id>:<channel>` - 驳回
- `changes:<topic_id>:<channel>` - 需要修改

**输出：**
- 更新审批状态
- 返回处理结果

### 8. 自动发布（带图片）
```bash
python3 {baseDir}/scripts/note_publish.py --topic-id <topic_id>
```

**输出：**
- 公开 URL
- 上传的图片 URL

**验证点：**
- ✅ 必须拿到公开 URL
- ✅ 必须验证 URL 可访问
- ✅ 必须包含封面和插图

## 配置

### 环境变量
```bash
GEMINI_API_KEY=xxx          # Gemini API 密钥（用于图片生成）
NOTE_EMAIL=xxx              # note.com 邮箱
NOTE_PASSWORD=xxx           # note.com 密码
NOTE_AUTHOR_URL=xxx         # note.com 作者页 URL
TELEGRAM_TARGET=xxx         # Telegram user ID（审批接收人）
```

### 数据目录
```
content-hub/
├── 00-收件箱/           # 原始素材
├── 01-灵感与素材库/     # 精选素材
├── 02-选题池/           # 待生成草稿
├── 03-内容工厂/         # 草稿生成中
├── 04-分发与审批/       # 待审批/已审批
└── 05-已发布归档/       # 已发布
```

## 审批流程（Telegram）

### 发送审批卡
审批卡包含：
- Topic ID
- 标题和摘要
- 三个按钮：
  - ✅ 批准
  - ❌ 驳回
  - 📝 修改

### 处理按钮点击
当用户点击按钮时，OpenClaw 会收到类似这样的消息：
```
callback_data:approve:20260309-01:note
```

**模型应该：**
1. 识别这是审批回调（格式：`callback_data:xxx`）
2. 提取 callback_data 内容
3. 调用处理脚本：
   ```bash
   python3 {baseDir}/scripts/telegram_approval.py callback --data "approve:20260309-01:note"
   ```
4. 根据处理结果回复用户

## 铁律（Iron Laws）

### 铁律一：没有验证的完成是谎言
- 任何"完成"声明必须附带验证证据
- 禁止"应该可以"、"理论上没问题"等模糊表述
- 验证失败 = 未完成，必须继续修复

### 铁律二：没有根因的修复是浪费
- 出问题先分析根因，不允许猜修
- 必须走完：读错误 → 复现 → 查变更 → 收集证据 → 形成假设 → 最小修复 → 验证
- 禁止散弹枪调试（同时改多处试试看）

### 铁律三：太简单不需要设计是 anti-pattern
- 任何工作开始前必须先设计，即使看起来很简单
- 必须提出 2-3 个方案并说明优劣
- 设计决策存档，方便未来回顾

## 依赖

- Python 3.10+
- requests, beautifulsoup4, lxml
- OpenClaw message 工具（Telegram 按钮）
- nano-banana-pro skill（图片生成，需要 GEMINI_API_KEY）
- uv（Python 包管理器）

## 安全注意

- 草稿必须是日文，检测到中文自动中止
- 审批卡必须拿到 messageId 才算成功
- 发布必须拿到公开 URL 才算 published
- 图片生成依赖 nano-banana-pro skill，需要 GEMINI_API_KEY
- 封面文件名必须是 `{topic_id}-note-cover.png`
- 插图文件名必须是 `illustration-{序号:02d}.png`
- 发布前必须先生成图片并构建 content manifest

## 环境变量

```bash
GEMINI_API_KEY=xxx          # Gemini API 密钥（用于图片生成）
NOTE_EMAIL=xxx              # note.com 邮箱
NOTE_PASSWORD=xxx           # note.com 密码
NOTE_AUTHOR_URL=xxx         # note.com 作者页 URL
TELEGRAM_TARGET=xxx         # Telegram user ID（审批接收人）
```

- 草稿必须是日文，检测到中文自动中止
- 审批卡必须拿到 messageId 才算成功
- 发布必须拿到公开 URL 才算 published

## 示例对话

**用户：** "扫描热点并生成草稿"

**模型：**
1. 调用 `topic_scan.sh`
2. 验证输出（候选数量、最高分）
3. 调用 `note_outline.sh`
4. 验证输出（topic_id）
5. 调用 `note_draft.sh`
6. 验证输出（语言、字数）
7. 调用 `generate_images.py --topic-id <topic_id>`
8. 验证输出（图片数量）
9. 调用 `content_pipeline.py build_content_manifest --topic-id <topic_id>`
10. 验证输出（cover_image, content_blocks）
11. 回复用户："已生成草稿 20260309-01（含封面和 2 张插图），是否推送审批？"

**用户：** "推送审批"

**模型：**
1. 调用 `telegram_approval.py send --topic-id 20260309-01 --channel note`
2. 验证输出（message_id）
3. 回复用户："审批卡已发送到 Telegram，请点击按钮审批"

**用户点击按钮后，OpenClaw 收到：** `callback_data:approve:20260309-01:note`

**模型：**
1. 识别这是审批回调
2. 调用 `telegram_approval.py callback --data "approve:20260309-01:note"`
3. 验证输出（status: ok）
4. 回复用户："已批准 20260309-01，是否立即发布？"

**用户：** "发布"

**模型：**
1. 调用 `note_publish.py --topic-id 20260309-01`
2. 验证输出（公开 URL，图片上传成功）
3. 回复用户："已发布：https://note.com/chichoai/n/xxx（含封面和 2 张插图）"

---

**核心原则：**
- 外部 API 调用 → 脚本
- 文本理解/判断 → 模型
- 验证必须有证据
- 失败必须分析根因
