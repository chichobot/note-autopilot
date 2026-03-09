#!/usr/bin/env bash
# 快速初始化 note-autopilot（重装 OpenClaw 后使用）

set -euo pipefail

echo "=========================================="
echo "Note Autopilot - 快速初始化"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# 1. 检查 Python
echo "✓ 检查 Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 未安装"
    exit 1
fi
echo "  Python: $(python3 --version)"

# 2. 检查 playwright
echo ""
echo "✓ 检查 playwright..."
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "⚠️  playwright 未安装"
    echo "   运行: pip install playwright"
    echo "   然后: playwright install chromium"
    MISSING_DEPS=1
else
    echo "  playwright: 已安装"
fi

# 3. 创建 content-hub 目录结构
echo ""
echo "✓ 创建 content-hub 目录结构..."
python3 "$SCRIPT_DIR/content_pipeline.py" ensure_dirs
echo "  目录结构已创建"

# 4. 检查环境变量
echo ""
echo "✓ 检查环境变量..."
ENV_FILE="$HOME/.openclaw/.env"
MISSING_ENV=0

if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  .env 文件不存在: $ENV_FILE"
    MISSING_ENV=1
else
    if ! grep -q "^GEMINI_API_KEY=" "$ENV_FILE"; then
        echo "⚠️  缺少 GEMINI_API_KEY"
        MISSING_ENV=1
    fi
    if ! grep -q "^NOTE_SESSION=" "$ENV_FILE"; then
        echo "⚠️  缺少 NOTE_SESSION"
        MISSING_ENV=1
    fi
    if ! grep -q "^TELEGRAM_TARGET=" "$ENV_FILE"; then
        echo "⚠️  缺少 TELEGRAM_TARGET"
        MISSING_ENV=1
    fi
    
    if [ $MISSING_ENV -eq 0 ]; then
        echo "  环境变量: 已配置"
    fi
fi

# 5. 检查 nano-banana-pro skill
echo ""
echo "✓ 检查依赖 skills..."
if [ ! -d "$HOME/.openclaw/skills/nano-banana-pro" ]; then
    echo "⚠️  nano-banana-pro 未安装"
    echo "   运行: clawhub install nano-banana-pro"
    MISSING_DEPS=1
else
    echo "  nano-banana-pro: 已安装"
fi

# 6. 测试热点扫描
echo ""
echo "✓ 测试热点扫描..."
if bash "$SCRIPT_DIR/topic_scan.sh" >/dev/null 2>&1; then
    echo "  热点扫描: 正常"
else
    echo "⚠️  热点扫描失败（可能需要配置数据源）"
fi

# 总结
echo ""
echo "=========================================="
echo "初始化完成"
echo "=========================================="

if [ ${MISSING_DEPS:-0} -eq 1 ] || [ $MISSING_ENV -eq 1 ]; then
    echo ""
    echo "⚠️  还需要完成以下步骤："
    echo ""
    if [ ${MISSING_DEPS:-0} -eq 1 ]; then
        echo "1. 安装依赖："
        echo "   pip install playwright"
        echo "   playwright install chromium"
        echo "   clawhub install nano-banana-pro"
        echo ""
    fi
    if [ $MISSING_ENV -eq 1 ]; then
        echo "2. 配置环境变量（编辑 ~/.openclaw/.env）："
        echo "   GEMINI_API_KEY=your_key"
        echo "   NOTE_SESSION=your_session"
        echo "   TELEGRAM_TARGET=your_user_id"
        echo ""
    fi
    echo "3. 启用 Telegram inline buttons（编辑 ~/.openclaw/openclaw.json）："
    echo '   "channels": {"telegram": {"capabilities": {"inlineButtons": "allowlist"}}}'
    echo ""
    echo "4. 重启 OpenClaw："
    echo "   openclaw gateway restart"
    echo ""
    exit 1
else
    echo ""
    echo "✅ 所有检查通过！"
    echo ""
    echo "下一步："
    echo "  1. 重启 OpenClaw: openclaw gateway restart"
    echo "  2. 测试完整流程: 扫描热点并生成草稿"
    echo ""
fi
