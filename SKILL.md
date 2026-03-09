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

**风格参考：**
- 如果 `reference-covers/` 目录有参考图（`ref-*.png`），会随机选一张做风格迁移
- 没有参考图时，使用纯 text-to-image

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
- **推荐在 `reference-covers/` 目录放 10-20 张爆款封面作为风格参考**

## 爆款封面库

在 `reference-covers/` 目录维护参考图：

```bash
reference-covers/
├── README.md
├── ref-01.png  # note.com 热门文章封面
├── ref-02.png
└── ref-03.png
```

**推荐来源：**
- note.com 热门榜前 20
- 你自己的高赞文章
- 同领域大 V 的爆款封面

**质量标准：**
- 16:9 比例
- 高清（≥ 1280x720）
- 视觉风格统一
- 无文字或文字很少

## 爆款封面设计方法论

### 2026 年日本编辑设计趋势

#### 1. 极简主义 2.0（Neo-Minimalism）
- **特征：** 大量留白，单一视觉焦点，柔和渐变背景
- **色彩：** 莫兰迪色系（#D4A5A5, #9FA8A3, #E5C3A6）
- **适用：** 生活方式、个人成长、思考类内容
- **Prompt 关键词：** `minimalist composition, generous negative space, soft gradient background, muted pastel colors, single focal point, clean editorial style`

#### 2. 3D 软雕塑风格（Soft 3D）
- **特征：** 圆润的 3D 物体，玻璃/陶瓷质感，柔和光影
- **色彩：** 白色基调 + 单一强调色（#FF6B6B, #4ECDC4）
- **适用：** 科技、商业、创新类内容
- **Prompt 关键词：** `soft 3D render, rounded geometric shapes, glass material, ceramic texture, studio lighting, Blender style, pastel colors, floating objects`

#### 3. 扁平插画 + 纹理叠加
- **特征：** 扁平设计 + 细微纹理（纸张、布料），手绘感
- **色彩：** 温暖色调（#FFB347, #77DD77, #FFD1DC）
- **适用：** 教育、生活方式、亲子类内容
- **Prompt 关键词：** `flat illustration, paper texture overlay, hand-drawn feel, warm color palette, editorial illustration, Japanese lifestyle magazine style`

#### 4. 渐变网格（Gradient Mesh）
- **特征：** 流动的色彩过渡，抽象但有方向感
- **色彩：** 双色或三色渐变（#667EEA → #764BA2, #F093FB → #F5576C）
- **适用：** AI、未来、科技类内容
- **Prompt 关键词：** `gradient mesh, fluid color transition, abstract waves, holographic effect, modern tech aesthetic, vibrant gradients`

#### 5. 数据可视化美学
- **特征：** 图表、曲线、网格作为装饰元素
- **色彩：** 深色背景 + 荧光强调（#00D9FF, #FF006E）
- **适用：** 商业、分析、数据类内容
- **Prompt 关键词：** `data visualization aesthetic, abstract charts, grid patterns, infographic style, professional business design, clean lines, dark background`

### 爆款 Prompt 构建公式

```
[风格基调] + [主题元素] + [构图规则] + [色彩方案] + [质感细节] + [文字排版] + [参考风格]
```

**重要：note.com 爆款封面必须包含醒目的文字标题！**

### 文字排版规范（参考小红书爆款封面）

#### 1. 文字位置
- **上三分之一**：适合短标题（5-8 字）
- **居中**：适合中等标题（8-12 字）
- **左对齐/右对齐**：适合长标题（12-20 字）

#### 2. 字体风格
- **粗黑体**：冲击力强，适合数字、结论类（"90%的人不知道"）
- **圆体**：亲和力强，适合生活、教育类
- **宋体/明朝体**：专业感，适合商业、分析类

#### 3. 文字颜色
- **白色 + 黑色描边**：万能，任何背景都清晰
- **黄色/橙色**：警示感，适合"避坑"、"注意"类
- **红色**：紧迫感，适合"限时"、"必看"类
- **深色背景 + 荧光色文字**：科技感

#### 4. 文字大小层级
- **主标题**：占画面 30-40% 高度
- **副标题/数字**：主标题的 50-60%
- **装饰文字/标签**：主标题的 30-40%

#### 5. 文字效果
- **渐变填充**：时尚感（粉→紫，蓝→绿）
- **阴影/发光**：立体感
- **描边**：清晰度
- **倾斜/旋转**：动感（慎用，容易乱）

### Prompt 示例（带文字排版）

**示例 1（极简主义 + 醒目标题）：**
```
Minimalist editorial cover for a note article about [主题].
Visual: Soft gradient background (#F5F5F5 → #E8E8E8), single centered geometric shape (circle or rounded rectangle).
Typography: Bold sans-serif title in Japanese, centered, occupying 35% of canvas height.
Text style: White text with subtle black stroke (2px), clean and readable.
Text content: "[文章标题]" (e.g., "90%の人が知らないAI活用術")
Composition: Title in upper third, visual element in lower two-thirds, generous negative space.
Colors: Muted pastels (#D4A5A5, #9FA8A3), text in white with black outline.
Style: Clean Japanese editorial design, Kinfolk magazine aesthetic.
Technical: 16:9, high resolution, text must be prominent and legible.
```

**示例 2（3D 软雕塑 + 数字冲击）：**
```
Soft 3D render editorial cover for [主题].
Visual: Floating rounded 3D objects (sphere, torus), frosted glass material, pastel pink (#FFB6C1) accent.
Typography: Extra bold sans-serif, large number "90%" in top-left corner (占 40% 高度).
Text style: White number with pink gradient fill, soft drop shadow.
Secondary text: "の人が知らない" in smaller size below the number.
Composition: Number dominates top-left, 3D objects in bottom-right, diagonal visual flow.
Lighting: Studio lighting, soft shadows, clean white background.
Style: Blender/C4D aesthetic, modern minimalist, Dribbble featured work.
Technical: 16:9, 1920x1080, text must be sharp and eye-catching.
```

**示例 3（扁平插画 + 情感标题）：**
```
Flat illustration editorial cover for [主题].
Visual: Simple flat illustration (laptop, coffee cup, plant), warm color palette (#FFB347, #77DD77).
Typography: Rounded sans-serif (ゴシック体), centered title in two lines.
Text style: Dark navy (#2C3E50) text with cream (#FFF8E7) background box, rounded corners.
Text content: "[情感化标题]" (e.g., "疲れた心を癒す / AI活用法")
Composition: Title in center with semi-transparent background box, illustration elements around edges.
Paper texture overlay for warmth.
Style: Japanese lifestyle magazine, hand-drawn feel, approachable and friendly.
Technical: 16:9, text must be warm and inviting, easy to read at thumbnail size.
```

### 智能体使用指南

**当生成 image_plan 时：**

1. **分析文章主题**，选择最匹配的设计风格：
   - 生活/思考 → 极简主义
   - 科技/商业 → 3D 软雕塑
   - 教育/亲子 → 扁平插画
   - AI/未来 → 渐变网格
   - 数据/分析 → 数据可视化

2. **提取文章标题的核心信息**：
   - 如果有数字（"90%"、"3个方法"），必须突出显示
   - 如果有情感词（"疲れた"、"癒す"），用温暖色调
   - 如果有对比（"知らない vs 知ってる"），用视觉层级

3. **使用爆款 Prompt 构建公式**，填入：
   - 风格基调（从上面 5 种选）
   - 主题元素（从文章标题提取）
   - 构图规则（居中/三分法/对角线）
   - 色彩方案（具体 HEX 代码）
   - 质感细节（材质、光影）
   - **文字排版（位置、大小、颜色、效果）**
   - 参考风格（Dribbble, Behance, 日本设计奖）

4. **生成的 prompt 必须包含：**
   - ✅ 具体的色彩代码（#HEX）
   - ✅ 明确的构图规则
   - ✅ 材质/质感描述
   - ✅ **文字内容（日文标题）**
   - ✅ **文字样式（字体、大小、颜色、效果）**
   - ✅ **文字位置（上/中/下，左/中/右）**
   - ✅ 参考风格来源
   - ✅ 技术规格（16:9, text must be prominent）

5. **禁止使用模糊描述：**
   - ❌ "deep blue, warm gold"（太模糊）
   - ❌ "minimalist flat landscape"（太抽象）
   - ❌ "clean Japanese style"（太宽泛）
   - ❌ "no text overlay"（note.com 必须有文字！）

### 文字内容生成规则

**从文章标题提取核心信息：**

原标题：「完全保存版！90%の人が知らないAI活用術」

**提取策略：**
1. **数字优先**：如果有百分比/数量，放大显示
   - 主文字：「90%」（超大，占 40% 高度）
   - 副文字：「の人が知らない」（中等大小）
   
2. **关键词提取**：如果没有数字，提取核心动词/名词
   - 主文字：「AI活用術」
   - 副文字：「完全保存版」
   
3. **情感化改写**：让标题更有冲击力
   - 原：「AIを使いこなす方法」
   - 改：「AIで人生が変わる / 3つの秘訣」

### 验证检查点

生成 image_plan 后，必须验证：
- [ ] prompt 长度 ≥ 200 字符（加入文字排版后会更长）
- [ ] 包含至少 2 个具体色彩代码
- [ ] 包含明确的构图规则
- [ ] **包含具体的日文文字内容**
- [ ] **包含文字样式描述（字体、大小、颜色）**
- [ ] **包含文字位置描述**
- [ ] 包含参考风格来源
- [ ] 包含技术规格（16:9, text must be prominent and legible）

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
