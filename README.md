# Note Autopilot Skill

全自动 note.com 内容生产流水线（半自动模式）。

## 功能

- 扫描热点（Reddit, X, 小红书）
- 生成草稿（AI 改写 + 封面生成）
- Telegram 审批（inline buttons）
- 自动发布（note.com API）

## 安装

```bash
# 复制到 OpenClaw skills 目录
cp -r note-autopilot ~/.openclaw/skills/

# 或者通过 ClawHub 安装（未来）
clawhub install note-autopilot
```

## 配置

### 环境变量

```bash
# 必需
GEMINI_API_KEY=xxx          # Gemini API 密钥
NOTE_SESSION=xxx            # note.com session cookie

# 可选
TELEGRAM_TARGET=xxx         # Telegram user ID（审批接收人，默认从配置读取）
```

### OpenClaw 配置

确保 Telegram inline buttons 已启用：

```json5
{
  channels: {
    telegram: {
      capabilities: {
        inlineButtons: "allowlist"  // 或 "all"
      }
    }
  }
}
```

## 使用

### 基本流程

1. **扫描热点**
   ```
   用户：扫描热点
   模型：调用 topic_scan，返回候选列表
   ```

2. **生成草稿**
   ```
   用户：生成草稿
   模型：调用 draft_generate，生成日文草稿 + 封面
   ```

3. **推送审批**
   ```
   用户：推送审批
   模型：发送 Telegram 审批卡（带按钮）
   ```

4. **点击按钮审批**
   ```
   用户：点击 Telegram 按钮
   OpenClaw：收到 callback_data
   模型：自动处理审批回调，更新状态
   ```

5. **自动发布**
   ```
   用户：发布
   模型：调用 publish，发布到 note.com
   ```

### 一键流程

```
用户：扫描热点并生成草稿
模型：自动执行 1+2，然后询问是否推送审批
```

## 目录结构

```
note-autopilot/
├── SKILL.md              # Skill 定义（OpenClaw 读取）
├── README.md             # 使用文档（人类阅读）
├── scripts/              # 核心脚本
│   ├── telegram_approval.py   # Telegram 审批
│   └── verify.py              # 验证工具
├── templates/            # 模板文件
│   └── draft_template.md      # 草稿模板
└── docs/                 # 设计文档
    ├── design.md              # 系统设计
    ├── refactor.md            # 重构计划
    └── verification.md        # 验证检查点
```

## 依赖

- Python 3.10+
- OpenClaw 2026.3.7+
- Telegram bot（配置 inline buttons）

## 已知限制

1. 草稿必须是日文（中文会被拒绝）
2. 审批只支持 Telegram（Discord 需要公网端口）
3. 发布只支持 note.com（X 和小红书待实现）

## 开发计划

- [ ] 支持 X 和小红书发布
- [ ] 支持多语言草稿
- [ ] 增加数据分析和周报
- [ ] 打包到 ClawHub

## 许可

MIT

## 作者

Created by main agent, 2026-03-09
