#!/usr/bin/env bash
set -euo pipefail

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/content_pipeline.py" ensure_dirs >/dev/null
python3 "$SCRIPT_DIR/content_pipeline.py" topic_scan "$@"
