# 验证检查点使用说明

## 概述
`verify.py` 是一个验证工具，用于在关键环节强制验证，符合**铁律一：没有验证的完成是谎言**。

## 使用方法

### 1. 验证 topic_scan 输出
```bash
python3 scripts/content/verify.py topic_scan /path/to/topics/20260309.social_fast.json
```

**检查项：**
- ✅ 文件存在
- ✅ JSON 格式正确
- ✅ 至少有 1 个候选
- ✅ 包含 source_health 信息

**输出示例：**
```json
{
  "candidates_count": 30,
  "top_id": "20260309-01",
  "top_score": 9.5,
  "top_source": "reddit",
  "source_health": {"x": "ok", "reddit": "ok"}
}
```

### 2. 验证 draft 输出
```bash
python3 scripts/content/verify.py draft /path/to/draft.md /path/to/cover.png
```

**检查项：**
- ✅ 草稿文件存在
- ✅ 语言检测（日文，不能是中文）
- ✅ 字数 ≥ 800
- ✅ 封面图存在

**输出示例：**
```json
{
  "draft_file": "/path/to/draft.md",
  "char_count": 1523,
  "chinese_chars": 12,
  "japanese_chars": 1456,
  "has_cover": true
}
```

### 3. 验证审批卡推送
```bash
python3 scripts/content/verify.py approval_push "1480205890735833280"
```

**检查项：**
- ✅ messageId 存在
- ✅ messageId 格式正确

**输出示例：**
```json
{
  "message_id": "1480205890735833280"
}
```

### 4. 验证发布输出
```bash
python3 scripts/content/verify.py publish "https://note.com/chichoai/n/n98b53fd4e9e7"
```

**检查项：**
- ✅ URL 存在
- ✅ URL 是 note.com 域名
- ✅ URL 包含 note ID

**输出示例：**
```json
{
  "url": "https://note.com/chichoai/n/n98b53fd4e9e7",
  "domain": "note.com",
  "verified": true
}
```

## 集成到现有脚本

### 在 note_auto_monitor.sh 中使用
```bash
# 扫描完成后验证
python3 "$WORKSPACE/scripts/content/verify.py" topic_scan "$TOPIC_FILE" || {
    echo "❌ Topic scan verification failed"
    exit 1
}
```

### 在 content_pipeline.py 中使用
```python
# 草稿生成后验证
result = subprocess.run(
    ["python3", "scripts/content/verify.py", "draft", draft_file, cover_file],
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    raise Exception(f"Draft verification failed: {result.stderr}")
evidence = json.loads(result.stdout)
```

### 在 approval_push.sh 中使用
```bash
# 推送后验证
MESSAGE_ID=$(extract_message_id_from_response)
python3 "$WORKSPACE/scripts/content/verify.py" approval_push "$MESSAGE_ID" || {
    echo "❌ Approval push verification failed"
    exit 1
}
```

## 错误处理

验证失败时，脚本会：
1. 返回非零退出码
2. 在 stderr 输出错误信息
3. 不输出 JSON（stdout 为空）

示例：
```bash
$ python3 verify.py draft draft.md
❌ Verification failed: Draft too short: 500 chars (minimum 800)
$ echo $?
1
```

## 铁律对应

| 验证检查点 | 对应铁律 | 禁止的表述 |
|-----------|---------|-----------|
| topic_scan | 铁律一 | "应该扫到了热点" |
| draft | 铁律一 | "草稿应该没问题" |
| approval_push | 铁律一 | "审批卡应该发出去了" |
| publish | 铁律一 | "理论上已经发布了" |

**记住：没有验证证据 = 未完成**
