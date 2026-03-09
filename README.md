# Note Autopilot

> 全自动 note.com 内容生产流水线

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-2026.3.7+-green.svg)](https://openclaw.ai)

## ✨ 特性

- 🔍 **多源热点扫描**：Reddit + Twitter + 小红书 + RSS feeds
- 🤖 **AI 内容生成**：自动改写 + 日文优化
- 🎨 **封面自动生成**：Gemini 3 Pro Image（Nano Banana Pro）
- ✅ **Telegram 审批**：inline buttons，无需公网端口
- 📤 **一键发布**：note.com API 直接发布

## 🚀 快速开始

```bash
# 1. 克隆 skill
git clone https://github.com/chichobot/note-autopilot.git ~/.openclaw/skills/note-autopilot

# 2. 运行快速初始化
bash ~/.openclaw/skills/note-autopilot/scripts/quick_init.sh

# 3. 按提示完成配置
# 4. 重启 OpenClaw
openclaw gateway restart
```

**5 分钟完成安装！** 详见 [REINSTALL_GUIDE.md](REINSTALL_GUIDE.md)

## 📋 前置要求

- Python 3.10+
- OpenClaw 2026.3.7+
- playwright（`pip install playwright && playwright install chromium`）
- Gemini API key（图片生成）
- note.com session cookie（发布）

## 🎯 使用流程

### 方式 1：一键生成（推荐）

```
用户：扫描热点并生成草稿
```

AI 会自动：
1. 扫描多个数据源（Reddit, Twitter, 小红书, RSS）
2. 选择最高分选题
3. 生成日文草稿 + 封面图片
4. 询问是否推送审批

### 方式 2：分步执行

```
用户：扫描热点
→ AI 返回候选列表（74 个候选）

用户：生成草稿
→ AI 生成日文草稿 + 封面

用户：推送审批
→ AI 发送 Telegram 审批卡

用户：点击 ✅ 批准按钮
→ AI 自动处理审批

用户：发布
→ AI 发布到 note.com
```

## 🛡️ 容错机制

**多层 fallback 保证稳定性：**

| 数据源 | 主方案 | Fallback 1 | Fallback 2 | Fallback 3 |
|--------|--------|------------|------------|------------|
| 小红书 | 搜索 | feeds | 历史缓存 | 跳过 |
| Twitter | 浏览器抓取 | twclaw API | - | 跳过 |
| Reddit | 公开 API | - | - | - |
| RSS | note/zenn/qiita/hatena | - | - | - |
| 最终 | - | - | - | 5 个固定模板 |

**即使所有外部数据源失败，仍然可以生成内容！**

## 📁 目录结构

```
note-autopilot/
├── SKILL.md                    # OpenClaw skill 定义
├── README.md                   # 本文档
├── REINSTALL_GUIDE.md          # 重装指南
├── LICENSE                     # MIT 许可证
├── .gitignore                  # Git 忽略规则
├── scripts/                    # 核心脚本
│   ├── content_pipeline.py     # 内容流水线（主脚本）
│   ├── topic_scan.sh           # 热点扫描
│   ├── note_outline.sh         # 大纲生成
│   ├── note_draft.sh           # 草稿生成
│   ├── generate_images.py      # 图片生成
│   ├── telegram_approval.py    # Telegram 审批
│   ├── note_publish.py         # note.com 发布
│   ├── quick_init.sh           # 快速初始化
│   └── test_fallback.py        # 容错测试
├── templates/                  # 模板文件
│   └── draft_template.md       # 草稿模板
├── docs/                       # 设计文档
│   ├── design.md               # 系统设计
│   └── data-sources.md         # 数据源详解
└── reference-covers/           # 参考封面
```

## 🔧 配置

### 环境变量（~/.openclaw/.env）

```bash
# 必需
GEMINI_API_KEY=xxx          # Gemini API 密钥
NOTE_SESSION=xxx            # note.com session cookie

# 可选
TELEGRAM_TARGET=xxx         # Telegram user ID（审批接收人）
```

### OpenClaw 配置（~/.openclaw/openclaw.json）

```json
{
  "channels": {
    "telegram": {
      "capabilities": {
        "inlineButtons": "allowlist"
      }
    }
  }
}
```

## 📊 数据源

### 默认启用（无需配置）

- ✅ Reddit（公开 API）
- ✅ RSS feeds（note.com, Zenn, Qiita, Hatena）
- ✅ Twitter（playwright 浏览器抓取）

### 可选启用（需要配置）

- 🔐 小红书（需要登录 cookie）
- 🔐 Twitter API（twclaw，作为浏览器抓取的 fallback）

详见 [docs/data-sources.md](docs/data-sources.md)

## 🧪 测试

```bash
# 测试容错机制
python3 ~/.openclaw/skills/note-autopilot/scripts/test_fallback.py

# 测试热点扫描
bash ~/.openclaw/skills/note-autopilot/scripts/topic_scan.sh

# 测试图片生成
python3 ~/.openclaw/skills/note-autopilot/scripts/generate_images.py --help
```

## 🐛 故障排查

### 问题：热点扫描失败

**检查：**
```bash
python3 ~/.openclaw/skills/note-autopilot/scripts/test_fallback.py
```

**常见原因：**
- playwright 未安装：`pip install playwright && playwright install chromium`
- 小红书未登录：会自动降级到历史缓存
- Twitter 浏览器失败：会自动降级到 twclaw

### 问题：图片生成失败

**检查：**
```bash
echo $GEMINI_API_KEY
```

**解决：**
- 确保 `GEMINI_API_KEY` 已配置
- 确保 nano-banana-pro skill 已安装：`clawhub install nano-banana-pro`

### 问题：发布失败

**检查：**
```bash
echo $NOTE_SESSION
```

**解决：**
- 确保 `NOTE_SESSION` 已配置
- 确保 session cookie 未过期（重新登录 note.com 获取）

## 📝 已知限制

1. 草稿必须是日文（中文会被拒绝）
2. 审批只支持 Telegram（Discord 需要公网端口）
3. 发布只支持 note.com（X 和小红书待实现）

## 🗺️ 开发计划

- [ ] 支持 X 和小红书发布
- [ ] 支持多语言草稿
- [ ] 增加数据分析和周报
- [ ] 发布到 ClawHub

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系

- GitHub: https://github.com/chichobot/note-autopilot
- Issues: https://github.com/chichobot/note-autopilot/issues

---

**Created by main agent, 2026-03-09**
