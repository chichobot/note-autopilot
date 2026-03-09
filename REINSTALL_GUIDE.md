# Note Autopilot - 重装指南

重装 OpenClaw 后，快速恢复 note-autopilot skill 的完整指南。

## 1. 安装 Skill

```bash
# 从 GitHub 克隆
git clone https://github.com/chichobot/note-autopilot.git ~/.openclaw/skills/note-autopilot

# 或者从本地备份复制
cp -r /path/to/backup/note-autopilot ~/.openclaw/skills/
```

## 2. 安装 Python 依赖

```bash
# 只需要 playwright（用于 note.com 发布）
pip install playwright>=1.40.0
playwright install chromium
```

## 3. 配置环境变量

编辑 `~/.openclaw/.env`：

```bash
# 必需
GEMINI_API_KEY=your_gemini_api_key          # 用于图片生成
NOTE_SESSION=your_note_session_cookie       # note.com 登录 cookie
TELEGRAM_TARGET=your_telegram_user_id       # Telegram 审批接收人

# 可选（热点扫描数据源）
AISA_API_KEY=your_aisa_api_key             # Twitter/X 抓取（可选）
```

### 获取 NOTE_SESSION

1. 登录 note.com
2. 打开浏览器开发者工具（F12）
3. 进入 Application → Cookies → https://note.com
4. 复制 `_note_session_v5` 的值

## 4. 配置 OpenClaw

编辑 `~/.openclaw/openclaw.json`，启用 Telegram inline buttons：

```json5
{
  "channels": {
    "telegram": {
      "capabilities": {
        "inlineButtons": "allowlist"  // 或 "all"
      }
    }
  }
}
```

## 5. 安装依赖 Skills

```bash
# nano-banana-pro（图片生成）
clawhub install nano-banana-pro

# 或者手动安装
git clone https://github.com/xxx/nano-banana-pro.git ~/.openclaw/skills/nano-banana-pro
```

## 6. 安装外部工具（可选）

### 6.1 Twitter/X 抓取

**方案 A（推荐）：使用 OpenClaw browser 工具**
- ✅ 无需 API key
- ✅ 无需额外安装
- ✅ 支持英文关键词搜索

**方案 B（fallback）：安装 twclaw**
```bash
npm install -g twclaw
# 配置 AISA_API_KEY 到 .env
```

### 6.2 小红书抓取（可选）

```bash
# 下载二进制文件
cd ~/.openclaw/skills/xiaohongshu-mcp/bin
wget https://github.com/xpzouying/xiaohongshu-mcp/releases/download/v0.x.x/xiaohongshu-mcp-darwin-arm64
wget https://github.com/xpzouying/xiaohongshu-mcp/releases/download/v0.x.x/xiaohongshu-login-darwin-arm64
chmod +x xiaohongshu-*

# 扫码登录
./xiaohongshu-login-darwin-arm64

# 启动服务
./xiaohongshu-mcp-darwin-arm64 -headless=true -port=:18060
```

## 7. 创建内容目录

```bash
mkdir -p ~/.openclaw/content-hub/{00-收件箱,01-灵感与素材库,02-选题池,03-内容工厂,04-分发与审批,05-已发布归档}
```

## 8. 添加爆款封面参考（可选）

```bash
mkdir -p ~/.openclaw/skills/note-autopilot/reference-covers

# 从 note.com 热门榜下载 10-20 张封面
# 文件名格式：ref-01.png, ref-02.png, ...
```

## 9. 验证安装

```bash
# 测试热点扫描
bash ~/.openclaw/skills/note-autopilot/scripts/topic_scan.sh

# 测试图片生成
python3 ~/.openclaw/skills/note-autopilot/scripts/generate_images.py --help

# 测试 note.com 发布
python3 ~/.openclaw/skills/note-autopilot/scripts/note_publish.py --help
```

## 10. 重启 OpenClaw

```bash
openclaw gateway restart
```

---

## 最小可用配置

**如果只想快速测试，最少需要：**

1. ✅ Python 3.10+（系统自带）
2. ✅ `playwright`（`pip install playwright`）
3. ✅ `GEMINI_API_KEY`（图片生成）
4. ✅ `NOTE_SESSION`（note.com 发布）
5. ✅ Telegram inline buttons 配置

**热点扫描会降级到 Reddit + RSS + 模板 fallback，整个流程仍然可用！**

---

## 数据源优先级

### 完整配置（推荐）
1. 小红书（需要扫码登录）
2. Twitter/X（浏览器方案，无需 API key）
3. Reddit（公开 API，无需认证）
4. RSS Feed（公开 feed，无需认证）

### 最小配置（无外部 API）
1. Reddit（公开 API）
2. RSS Feed（公开 feed）
3. 模板 fallback（内置 5 个固定选题）

---

## 常见问题

### Q: 小红书登录失效怎么办？
A: 重新运行 `xiaohongshu-login-darwin-arm64` 扫码登录。

### Q: Twitter 抓取失败怎么办？
A: 浏览器方案失败会自动降级到 twclaw（如果有 API key），再失败会跳过 Twitter，使用其他数据源。

### Q: 没有任何外部 API key 能用吗？
A: 可以！热点扫描会使用 Reddit + RSS + 模板 fallback，仍然能生成草稿和发布。

### Q: 图片生成失败怎么办？
A: 检查 `GEMINI_API_KEY` 是否配置正确，或者手动上传封面图片。

---

## 总结

**重装后 5 分钟恢复流程：**
1. 复制 skill 目录
2. `pip install playwright`
3. 配置 3 个环境变量
4. 启用 Telegram inline buttons
5. 重启 OpenClaw

**完成！** 🎉
