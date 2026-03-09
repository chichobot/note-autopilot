# Content Pipeline 设计文档

**创建时间：** 2026-03-09  
**状态：** 生产运行中  
**负责人：** main agent  

## 1. 系统概述

### 1.1 目标
自动化 note.com 内容生产流水线：热点扫描 → 草稿生成 → 人工审批 → 自动发布

### 1.2 核心原则
- **半自动化**：机器生产，人工把关
- **质量优先**：宁可慢，不能差
- **可追溯**：每个环节都有状态记录
- **可回滚**：任何环节失败都能恢复

### 1.3 架构
```
┌─────────────┐
│   main      │  协调中枢
└──────┬──────┘
       │
   ┌───┴────┬────────┬────────┐
   │        │        │        │
┌──▼──┐ ┌──▼──┐ ┌───▼───┐ ┌──▼───┐
│studio│ │note │ │ coder │ │ 大哥 │
└──────┘ └─────┘ └───────┘ └──────┘
   │        │        │         │
   └────────┴────────┴─────────┘
              │
        ┌─────▼──────┐
        │ content-hub│  唯一真源
        └────────────┘
```

## 2. 数据流

### 2.1 content-hub 目录结构
```
content-hub/
├── 00-收件箱/           # 原始素材
├── 01-灵感与素材库/     # 精选素材
├── 02-选题池/           # 待生成草稿
├── 03-内容工厂/         # 草稿生成中
├── 04-分发与审批/       # 待审批/已审批
├── 05-已发布归档/       # 已发布
└── 06-复盘与模式/       # 数据分析
```

### 2.2 状态流转
```
扫描热点 → 02-选题池/
         ↓
生成草稿 → 03-内容工厂/
         ↓
推送审批 → 04-分发与审批/pending/
         ↓
人工审批 → 04-分发与审批/approved/ (批了)
         → 04-分发与审批/rejected/ (驳回)
         ↓
自动发布 → 05-已发布归档/
```

## 3. 核心流程

### 3.1 热点扫描
**脚本：** `scripts/content/note_auto_monitor.sh`

**输入：**
- 数据源：Reddit, X (Twitter), 小红书
- 扫描数量：30 个候选

**输出：**
- 候选列表（JSON）
- 最高分 topic_id
- 存储位置：`02-选题池/`

**验证点：**
- ✅ 必须输出候选数量
- ✅ 必须输出最高分和来源
- ✅ 必须生成 topic_id

**失败处理：**
- 数据源不可用 → 降级到其他源
- 全部失败 → 通知大哥，人工介入

### 3.2 草稿生成
**脚本：** `content_pipeline.py note_draft`

**输入：**
- topic_id（从选题池）
- 模板：`templates/draft_template.md`

**输出：**
- 草稿文件（Markdown，日文）
- 封面图（PNG）
- 存储位置：`03-内容工厂/`

**验证点：**
- ✅ 必须检测语言（中文直接中止）
- ✅ 必须生成封面图
- ✅ 必须包含标题、正文、CTA
- ✅ 字数 ≥ 800

**失败处理：**
- 语言检测失败 → 中止，要求重跑
- 封面生成失败 → 使用默认封面
- 内容质量差 → 标记为 low_quality，不推送审批

### 3.3 审批推送
**脚本：** `scripts/content/approval_push.sh`

**输入：**
- draft_id
- Discord 频道 ID

**输出：**
- Discord 审批卡（带封面 + 按钮）
- messageId
- 存储位置：`04-分发与审批/pending/`

**验证点：**
- ✅ 必须拿到 messageId
- ✅ 封面必须成功上传
- ✅ 按钮必须可点击（虽然实际不生效）

**失败处理：**
- Discord API 失败 → 重试 3 次
- 封面上传失败 → 纯文本审批卡
- 全部失败 → 通知大哥，人工推送

### 3.4 审批监控
**脚本：** `scripts/content/discord_approval_monitor.py`

**输入：**
- Discord 频道 ID
- 待审批列表

**输出：**
- 审批结果（approved / rejected）
- 更新状态文件

**验证点：**
- ✅ 必须检测到回复内容
- ✅ 必须更新 content-hub 状态
- ✅ 必须记录审批时间和审批人

**失败处理：**
- Discord API 失败 → 跳过本次检查
- 状态更新失败 → 记录到日志，下次重试

### 3.5 自动发布
**脚本：** `content_pipeline.py note_publish_window`

**输入：**
- draft_id（已审批）
- note.com session

**输出：**
- 公开 URL
- 存储位置：`05-已发布归档/`

**验证点：**
- ✅ 必须拿到公开 URL
- ✅ 必须验证 URL 可访问
- ✅ 必须更新 content-hub 状态为 published

**失败处理：**
- API 发布失败 → 重试 3 次
- 全部失败 → 标记为 publish_unverified，通知大哥

## 4. 配置管理

### 4.1 环境变量
```bash
GEMINI_API_KEY          # Gemini API 密钥
NOTE_SESSION            # note.com session cookie
DISCORD_TOKEN           # Discord bot token
DISCORD_CHANNEL_ID      # 审批频道 ID
REDDIT_CLIENT_ID        # Reddit API
REDDIT_CLIENT_SECRET    # Reddit API
```

### 4.2 配置文件
- `content-hub/99-系统配置/pipeline_config.json`
- `workspace/scripts/content/config.py`

## 5. 监控与告警

### 5.1 关键指标
- 热点扫描成功率
- 草稿生成成功率
- 审批响应时间
- 发布成功率
- 公开 URL 可访问率

### 5.2 告警规则
- 连续 3 次扫描失败 → 通知大哥
- 草稿生成失败 → 记录日志
- 审批卡推送失败 → 立即通知大哥
- 发布失败 → 立即通知大哥

## 6. 已知问题与限制

### 6.1 小红书接口不稳定
- 现象：`status` 返回 `NOT_LOGGED_IN`，`feeds/search` 超时
- 临时方案：降级到 `feeds_cached` 或 `history_fallback`
- 长期方案：等官方接口稳定

### 6.2 Discord 按钮不生效
- 现象：按钮可以显示，但点击无效（需要公网端口）
- 临时方案：文字回复 + 定期轮询
- 长期方案：考虑使用 Tailscale 或 ngrok

### 6.3 note.com 发布偶尔超时
- 现象：API 调用超时，但文章实际已发布
- 临时方案：检查草稿列表，手动确认
- 长期方案：增加幂等性检查

## 7. 未来优化方向

### 7.1 短期（1-2 周）
- [ ] 补全所有验证检查点
- [ ] 增加根因分析日志
- [ ] 优化审批监控频率

### 7.2 中期（1 个月）
- [ ] 打包成标准 OpenClaw Skill
- [ ] 增加数据分析和周报
- [ ] 优化封面生成质量

### 7.3 长期（3 个月）
- [ ] 支持多平台发布（X, 小红书）
- [ ] 增加 A/B 测试
- [ ] 自动化数据复盘

## 8. 参考资料

- [OpenClaw Skills 文档](https://docs.openclaw.ai/tools/skills.md)
- [obra/superpowers](https://github.com/obra/superpowers)
- content-hub 实际运行数据

---

**最后更新：** 2026-03-09  
**下次审查：** 2026-03-16
