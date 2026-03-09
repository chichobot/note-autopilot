# 数据源详解

note-autopilot 支持多个数据源，每个数据源都有多层 fallback 机制。

## 数据源优先级

1. **小红书**（30 个候选）
2. **Twitter**（20 个候选）
3. **Reddit**（10 个候选）
4. **RSS feeds**（14 个候选）
5. **模板 fallback**（5 个候选）

---

## 1. 小红书（Xiaohongshu）

### 主方案：搜索 API

```python
xhs_client.search_notes(keyword="AI", sort="hot", limit=30)
```

**优点：**
- 实时热点
- 高质量内容
- 精准关键词匹配

**缺点：**
- 需要登录 cookie
- 可能被限流

### Fallback 1：Feeds API

```python
xhs_client.get_home_feed(limit=30)
```

**优点：**
- 不需要关键词
- 推荐算法优化

**缺点：**
- 内容可能不相关

### Fallback 2：历史缓存

```python
# 读取上次成功的结果
cached_results = load_cache("xhs_last_success.json")
```

**优点：**
- 永远不会失败
- 快速响应

**缺点：**
- 内容可能过时

### Fallback 3：跳过

如果所有方案都失败，跳过小红书数据源。

---

## 2. Twitter（X）

### 主方案：浏览器抓取（playwright）

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://x.com/search?q=AI&f=live")
    tweets = page.query_selector_all('[data-testid="tweet"]')
```

**优点：**
- 无需 API key
- 完全免费
- 可以抓取任何公开内容

**缺点：**
- 速度较慢（5-10 秒）
- 可能被反爬

### Fallback 1：twclaw API

```python
import requests
response = requests.get("https://api.twclaw.com/search?q=AI")
```

**优点：**
- 速度快
- 稳定

**缺点：**
- 需要 API key
- 可能有配额限制

### Fallback 2：跳过

如果所有方案都失败，跳过 Twitter 数据源。

---

## 3. Reddit

### 主方案：公开 API

```python
import requests
response = requests.get(
    "https://www.reddit.com/r/artificial/hot.json",
    headers={"User-Agent": "note-autopilot/1.0"}
)
```

**优点：**
- 无需认证
- 完全免费
- 稳定可靠

**缺点：**
- 有速率限制（60 请求/分钟）

### Fallback：跳过

Reddit API 很稳定，通常不会失败。

---

## 4. RSS Feeds

### 数据源列表

```python
RSS_FEEDS = [
    "https://note.com/feed",           # note.com 热门
    "https://zenn.dev/feed",           # Zenn 技术文章
    "https://qiita.com/popular-items/feed",  # Qiita 热门
    "https://b.hatena.ne.jp/hotentry/it.rss",  # Hatena IT
]
```

**优点：**
- 无需认证
- 完全免费
- 高质量内容

**缺点：**
- 更新频率较低
- 内容可能重复

### Fallback：跳过

RSS feeds 很稳定，通常不会失败。

---

## 5. 模板 Fallback

### 固定模板选题

当所有外部数据源都失败时，使用 5 个固定模板：

```python
TEMPLATES = [
    {
        "angle": "AI 工具推荐：提升工作效率的 5 个神器",
        "audience": "职场人士、创业者",
        "evidence_urls": ["https://example.com"],
        "risk_flags": [],
    },
    {
        "angle": "ChatGPT 使用技巧：10 个你不知道的隐藏功能",
        "audience": "AI 爱好者、学生",
        "evidence_urls": ["https://example.com"],
        "risk_flags": [],
    },
    # ... 3 more templates
]
```

**优点：**
- 永远不会失败
- 内容质量可控

**缺点：**
- 不是实时热点
- 可能重复

---

## 配置数据源

### 启用/禁用数据源

编辑 `scripts/content_pipeline.py`：

```python
# 禁用小红书
ENABLE_XHS = False

# 禁用 Twitter
ENABLE_TWITTER = False

# 只使用 Reddit + RSS
ENABLE_REDDIT = True
ENABLE_RSS = True
```

### 调整候选数量

```python
# 每个数据源的候选数量
XHS_LIMIT = 30
TWITTER_LIMIT = 20
REDDIT_LIMIT = 10
RSS_LIMIT = 14
```

---

## 测试数据源

### 测试所有数据源

```bash
python3 ~/.openclaw/skills/note-autopilot/scripts/test_fallback.py
```

**输出示例：**

```
Testing fallback mechanisms...

[小红书] 主方案（搜索）: ✅ 30 个候选
[小红书] Fallback 1（feeds）: ✅ 30 个候选
[小红书] Fallback 2（历史缓存）: ✅ 25 个候选

[Twitter] 主方案（浏览器）: ✅ 20 个候选
[Twitter] Fallback 1（twclaw）: ❌ 未配置

[Reddit] 主方案（公开 API）: ✅ 10 个候选

[RSS] 主方案（feeds）: ✅ 14 个候选

[模板] Fallback: ✅ 5 个候选

总计: 74 个候选
```

### 测试单个数据源

```bash
# 只测试小红书
python3 -c "from content_pipeline import fetch_xhs_topics; print(fetch_xhs_topics())"

# 只测试 Twitter
python3 -c "from content_pipeline import fetch_twitter_topics; print(fetch_twitter_topics())"

# 只测试 Reddit
python3 -c "from content_pipeline import fetch_reddit_topics; print(fetch_reddit_topics())"

# 只测试 RSS
python3 -c "from content_pipeline import fetch_rss_topics; print(fetch_rss_topics())"
```

---

## 故障排查

### 小红书失败

**症状：** `[小红书] 所有方案都失败`

**原因：**
1. 未配置 cookie
2. cookie 已过期
3. 被限流

**解决：**
1. 登录小红书网页版
2. 复制 cookie
3. 配置到环境变量或 MCP server

### Twitter 失败

**症状：** `[Twitter] 浏览器抓取失败`

**原因：**
1. playwright 未安装
2. chromium 未安装
3. 网络问题

**解决：**
```bash
pip install playwright
playwright install chromium
```

### Reddit 失败

**症状：** `[Reddit] 429 Too Many Requests`

**原因：**
- 超过速率限制（60 请求/分钟）

**解决：**
- 等待 1 分钟后重试
- 减少请求频率

### RSS 失败

**症状：** `[RSS] 无法解析 feed`

**原因：**
- 网络问题
- feed URL 失效

**解决：**
- 检查网络连接
- 更新 feed URL

---

## 最佳实践

### 1. 优先使用免费数据源

- ✅ Reddit（公开 API）
- ✅ RSS feeds（无需认证）
- ✅ Twitter 浏览器抓取（无需 API key）

### 2. 配置多层 fallback

不要依赖单一数据源，确保每个数据源都有 fallback。

### 3. 定期测试

```bash
# 每天运行一次测试
python3 ~/.openclaw/skills/note-autopilot/scripts/test_fallback.py
```

### 4. 监控失败率

如果某个数据源持续失败，考虑禁用或更换。

---

## 扩展数据源

### 添加新数据源

1. 在 `content_pipeline.py` 中添加函数：

```python
def fetch_new_source_topics(limit: int = 10) -> list[dict]:
    """从新数据源获取选题"""
    try:
        # 实现抓取逻辑
        return topics
    except Exception as e:
        print(f"[新数据源] 失败: {e}")
        return []
```

2. 在 `fetch_real_topics()` 中调用：

```python
def fetch_real_topics(profile: str = "full") -> tuple[list[dict], dict]:
    all_topics = []
    
    # 添加新数据源
    new_topics = fetch_new_source_topics(limit=10)
    all_topics.extend(new_topics)
    
    return all_topics, source_health
```

3. 测试：

```bash
python3 ~/.openclaw/skills/note-autopilot/scripts/test_fallback.py
```

---

**更新时间：** 2026-03-09
