"""
每日硬核情报简报生成器
========================
数据源: GitHub Trending / Hacker News / ArXiv / RSS feeds
AI 策展: Anthropic Claude API（可选，需 ANTHROPIC_API_KEY）
启发式回退: 无 API key 时用评分 + 模板生成基础简报

输出:
  - data/daily_briefing.json  结构化数据（网站用）
  - daily_briefing.md         格式化 Markdown（独立阅读）
"""

import json
import os
import re
import sys
import hashlib
import time
import html as html_mod
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
import feedparser

# ── Windows 终端编码兼容 ──────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 路径 ────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")      # DeepSeek API key（推荐，便宜且效果好）
SERVERCHAN_SEND_KEY = os.environ.get("SERVERCHAN_SEND_KEY", "")  # Server酱微信推送 key

# API / 抓取端点
HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
ARXIV_API = "http://export.arxiv.org/api/query"

# 若 GitHub Trending 抓取失败，用 GitHub Search API 替代（无需 key 有频率限制）
GITHUB_SEARCH = "https://api.github.com/search/repositories"

# 科技 RSS 源（补充 HN / ArXiv）
TECH_RSS_FEEDS = [
    "https://hnrss.org/frontpage?count=15",              # HN 的 RSS 版（更好解析）
    "https://feeds.feedburner.com/TheHackersNews",       # The Hacker News 安全博客
    "https://www.theregister.com/headlines.atom",        # The Register — 企业IT, 毒舌风格
    "https://feeds.arstechnica.com/arstechnica/index",   # Ars Technica — 深度科技分析
    "https://dev.to/feed",                                # dev.to — 开发者社区
    "https://www.reddit.com/r/programming/.rss",         # Reddit r/programming
    "https://www.reddit.com/r/MachineLearning/.rss",     # Reddit r/MachineLearning
]

# Lobste.rs — 邀请制社区，信噪比极高
LOBSTERS_HOTTEST = "https://lobste.rs/hottest.json"

# 预过滤：每个源保留的候选数量
MAX_PER_SOURCE = 15
# 最终送给 LLM 的候选数量
MAX_CANDIDATES_FOR_LLM = 20
# 简报条目数
BRIEFING_ITEMS = 3

# ═══════════════════════════════════════════════════════════════
# 数据抓取
# ═══════════════════════════════════════════════════════════════

def fetch_github_trending() -> list[dict]:
    """抓取 GitHub Trending 今日榜单（Python + 全语言）。

    优先从 trending page 抓取；失败则回退到 GitHub Search API。
    """
    items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DailyBriefing/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    # ── 方案 A: 直接抓取 trending 页面 ──
    for section in ["", "?since=daily"]:
        for lang in ["python", ""]:
            url = f"https://github.com/trending/{lang}{section}"
            if lang:
                url = f"https://github.com/trending/{lang}?since=daily"
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    continue
                # 简易 HTML 解析（避免引入 BeautifulSoup）
                html_text = resp.text
                # 找 repo 卡片: <h2 class="h3 lh-condensed">...<a href="/owner/repo">
                repo_pattern = re.compile(
                    r'<h2[^>]*class="[^"]*h3[^"]*"[^>]*>.*?'
                    r'<a\s+href="/([^/"]+)/([^/"]+)"[^>]*>.*?'
                    r'</h2>.*?'
                    r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>',
                    re.DOTALL
                )
                # 更简单的做法：分步提取
                # 提取 repo 链接
                link_pattern = re.compile(r'<a\s+href="/([^/"]+)/([^/"]+)"[^>]*>\s*(?:\1\s*/\s*)?\2\s*</a>')
                desc_pattern = re.compile(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', re.DOTALL)
                stars_pattern = re.compile(r'(\d[\d,]*)\s+stars\s+today', re.IGNORECASE)

                links = link_pattern.findall(html_text)
                descs = desc_pattern.findall(html_text)
                stars_today = stars_pattern.findall(html_text)

                for i, (owner, repo) in enumerate(links[:MAX_PER_SOURCE]):
                    desc = descs[i].strip() if i < len(descs) else ""
                    desc = re.sub(r'<[^>]+>', '', desc).strip()
                    stars = stars_today[i].replace(",", "") if i < len(stars_today) else "0"
                    items.append({
                        "id": f"gh:{owner}/{repo}",
                        "title": f"{owner}/{repo}",
                        "summary": desc[:300] if desc else "",
                        "url": f"https://github.com/{owner}/{repo}",
                        "source": "GitHub Trending",
                        "stars_today": int(stars) if stars.isdigit() else 0,
                        "owner": owner,
                        "repo": repo,
                    })
                if links:
                    break  # 成功抓取到一个 section 就不再继续
            except Exception:
                continue
        if items:
            break

    # ── 方案 B: GitHub Search API 回退 ──
    if not items:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            resp = requests.get(
                GITHUB_SEARCH,
                params={"q": f"pushed:>{today}", "sort": "stars", "order": "desc", "per_page": 20},
                headers={**headers, "Accept": "application/vnd.github.v3+json"},
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                for repo in (data.get("items") or [])[:MAX_PER_SOURCE]:
                    items.append({
                        "id": f"gh:{repo['full_name']}",
                        "title": repo["full_name"],
                        "summary": (repo.get("description") or "")[:300],
                        "url": repo["html_url"],
                        "source": "GitHub Search",
                        "stars_today": repo.get("stargazers_count", 0),
                        "owner": repo["full_name"].split("/")[0] if "/" in repo["full_name"] else "",
                        "repo": repo.get("name", ""),
                    })
        except Exception:
            pass

    return items


def fetch_hacker_news() -> list[dict]:
    """从 Hacker News 获取 top stories。

    用 Firebase API（免费、无需 key），获取 top 30 条。
    """
    items = []
    try:
        # 获取 top story IDs
        resp = requests.get(HN_TOP_STORIES, timeout=15)
        if resp.status_code != 200:
            return items
        top_ids = resp.json()[:40]

        # 逐条获取详情（HN API 每条请求很快）
        for story_id in top_ids:
            try:
                r = requests.get(HN_ITEM.format(story_id), timeout=10)
                if r.status_code != 200:
                    continue
                story = r.json()
                if not story:
                    continue
                # 只保留 story 类型（非评论/问答也保留，可能有价值）
                item_type = story.get("type", "")
                if item_type not in ("story", "job"):
                    continue
                title = story.get("title", "")
                if not title:
                    continue
                url = story.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                items.append({
                    "id": f"hn:{story_id}",
                    "title": title,
                    "summary": (story.get("text") or "")[:300],
                    "url": url,
                    "source": "Hacker News",
                    "score": story.get("score", 0),
                    "comments": story.get("descendants", 0),
                })
                if len(items) >= MAX_PER_SOURCE:
                    break
            except Exception:
                continue
            time.sleep(0.02)  # 微延迟，避免触发限流
    except Exception as e:
        print(f"  ⚠ Hacker News 抓取失败: {e}")

    return items


def fetch_lobsters() -> list[dict]:
    """从 Lobste.rs 获取热门故事（邀请制社区，信噪比极高）。"""
    items = []
    try:
        resp = requests.get(LOBSTERS_HOTTEST, timeout=15)
        if resp.status_code != 200:
            return items
        stories = resp.json()
        for story in stories[:MAX_PER_SOURCE]:
            title = story.get("title", "")
            if not title:
                continue
            url = story.get("url") or story.get("comments_url", "")
            items.append({
                "id": f"lob:{story.get('short_id', '')}",
                "title": title,
                "summary": (story.get("description") or "")[:300],
                "url": url,
                "source": "Lobste.rs",
                "score": story.get("score", 0),
                "comments": story.get("comment_count", 0),
                "tags": story.get("tags", []),
            })
    except Exception as e:
        print(f"  ⚠ Lobste.rs 抓取失败: {e}")
    return items


def fetch_arxiv_papers() -> list[dict]:
    """从 ArXiv 获取最新 AI/ML/量化金融 论文（使用 feedparser 解析）。

    检索: cs.AI, cs.CL, cs.LG, q-fin.TR, stat.ML
    按提交日期排序。
    """
    import urllib.parse
    items = []
    categories = ["cs.AI", "cs.CL", "cs.LG", "q-fin.TR", "stat.ML"]
    query = " OR ".join(f"cat:{c}" for c in categories)
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": "30",
        "start": "0",
    }
    api_url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    try:
        # 先用 requests 做 HTTP 调用（处理 URL 编码），再用 feedparser 解析
        resp = requests.get(api_url, timeout=30)
        if resp.status_code != 200:
            return items
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:MAX_PER_SOURCE]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            summary = re.sub(r"\s+", " ", entry.get("summary", ""))[:300]
            arxiv_id = entry.get("id", "").split("/")[-1]
            cats = [t.get("term", "") for t in entry.get("tags", [])]
            items.append({
                "id": f"arxiv:{arxiv_id}",
                "title": title,
                "summary": summary,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "source": "ArXiv",
                "categories": cats[:5],
                "arxiv_id": arxiv_id,
            })
    except Exception as e:
        print(f"  ⚠ ArXiv 抓取失败: {e}")

    return items


def fetch_tech_rss() -> list[dict]:
    """从科技 RSS 源抓取补充信息。"""
    items = []
    for feed_url in TECH_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:MAX_PER_SOURCE]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                # 清洗 HTML
                summary = re.sub(r"<[^>]+>", "", str(summary))[:300]
                uid = hashlib.md5((title + link).encode()).hexdigest()[:10]
                items.append({
                    "id": f"rss:{uid}",
                    "title": title.strip(),
                    "summary": summary.strip(),
                    "url": link,
                    "source": "Tech RSS",
                    "score": 0,
                })
        except Exception as e:
            print(f"  ⚠ RSS 源 {feed_url[:50]} 抓取失败: {e}")
    return items


# ═══════════════════════════════════════════════════════════════
# 评分 & 预过滤
# ═══════════════════════════════════════════════════════════════

# 高价值关键词（用于启发式评分）
HIGH_VALUE_KEYWORDS = [
    # 技术突破
    "transformer", "diffusion", "reinforcement learning", "llama", "gpt",
    "mixture of experts", "multimodal", "vector database", "rag", "agent",
    "fine-tun", "quantiz", "inference", "cuda", "gpu kernel",
    # 基础设施
    "compiler", "database", "kernel", "os", "linux", "rust", "wasm",
    "distributed", "postgres", "sqlite", "redis", "kafka",
    # 安全
    "vulnerability", "exploit", "cve", "zero-day", "supply chain",
    # 金融/量化
    "quantitative", "backtest", "order book", "market microstructure",
    "defi", "solidity", "consensus",
    # 开源重磅
    "open source", "release", "1.0", "2.0", "major", "rewrite",
    # 中国相关（增强中文读者关联）
    "deepseek", "qwen", "alibaba", "baidu", "moonshot", "zhipu",
    "bytedance", "tencent", "kuaishou", "ant group",
]


def score_item(item: dict) -> float:
    """启发式评分：标题+摘要中出现高价值关键词加分，来源影响力加分。"""
    score = 0.0
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()

    # 关键词匹配
    for kw in HIGH_VALUE_KEYWORDS:
        if kw.lower() in text:
            score += 2.0

    # 来源权重
    source = item.get("source", "")
    if source == "Hacker News":
        hn_score = item.get("score", 0)
        hn_comments = item.get("comments", 0)
        # HN 高票 + 高讨论 = 更有价值
        score += min(hn_score / 20, 10)  # 200 分以上封顶 10 分
        score += min(hn_comments / 10, 5)  # 50 评以上封顶 5 分
    elif source == "GitHub Trending":
        gh_stars = item.get("stars_today", 0)
        score += min(gh_stars / 50, 8)  # 400 星以上封顶 8 分
    elif source == "ArXiv":
        # ArXiv 论文更看重分类
        cats = item.get("categories", [])
        for c in cats:
            if c in ("cs.AI", "cs.CL", "cs.LG"):
                score += 2
            elif c == "q-fin.TR":
                score += 1.5
    elif source == "Lobste.rs":
        lob_score = item.get("score", 0)
        lob_comments = item.get("comments", 0)
        score += min(lob_score / 5, 8)     # Lobste.rs 分数一般较小（~30 就很高了）
        score += min(lob_comments / 3, 5)

    # 标题长度惩罚（太短或太长都不好）
    title_len = len(item.get("title", ""))
    if 30 <= title_len <= 120:
        score += 1.0

    return score


def pre_filter_candidates(all_items: list[dict]) -> list[dict]:
    """去重 + 评分 + 排序，返回 top candidates。"""
    # 去重（按 URL 前缀匹配）
    seen_urls = set()
    unique = []
    for item in all_items:
        url = item.get("url", "")
        # 生成短 URL 指纹
        url_key = re.sub(r"https?://(www\.)?", "", url).rstrip("/")
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        # 过滤明显无意义的条目
        title = item.get("title", "").strip()
        if not title or len(title) < 8:
            continue
        # 过滤纯营销类标题
        skip_patterns = [
            r"^buy\b", r"^get\b.*\b(free|discount)\b", r"sponsor",
            r"webinar", r"subscribe", r"newsletter",
        ]
        if any(re.search(p, title, re.IGNORECASE) for p in skip_patterns):
            continue
        unique.append(item)

    # 计算得分
    for item in unique:
        item["_score"] = score_item(item)

    # 排序
    unique.sort(key=lambda x: x.get("_score", 0), reverse=True)

    return unique[:MAX_CANDIDATES_FOR_LLM]


# ═══════════════════════════════════════════════════════════════
# AI 策展（Claude API）
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是我专属的「硬核科技与情报首席分析师」。

### 你的性格与设定
- **定位**：顶尖科技眼光、极客视角、洞察力极强。
- **语言风格**：言简意赅、拒绝废话、幽默且带有恰到好处的"毒舌/吐槽"风格（类似高端科技媒体的调侃，针针见血但不低俗）。
- **目标**：从海量的原始情报数据（GitHub Trending、Hacker News、ArXiv 论文、科技/财经新闻）中剔除噪音，只保留最具价值的信息。

### 数据处理与过滤规则
1. **去粗取精**：坚决过滤掉套壳项目、营销号水文、无实质突破的蹭热度话题，只精选 3 条具有技术突破、商业价值或行业影响力的核心情报。
2. **翻译与重构**：将英文标题与摘要精准翻译为地道、通俗易懂的中文，严禁生硬直译。
3. **格式约束**：直接输出最终生成的 Markdown 内容，绝对不要包含任何开场白或结束套话。

### 输出格式（严格按此 Markdown 渲染）

# 🗞️ 每日硬核情报简报 | {DATE}

> 💡 *"用最毒舌的视角，看最前沿的科技。"*

---

### 1. 📌 [项目/动态名称] (来源: GitHub/HackerNews/ArXiv/新闻)
- **核心干货**：用 2-3 句话解释这到底是什么、解决了什么核心痛点、为什么值得关注。
- **毒舌/硬核点评**：用 1-2 句犀利、幽默或富有行业洞察的话进行点评。
- **🔗 传送门**：[点击直达原链接](原文章或项目URL)

---

### 2. 📌 [项目/动态名称] ...
（同上）

---

### 3. 📌 [项目/动态名称] ...
（同上）

---

### 🗣️ 今日顶男金句
（给出一句关于技术演进、搞钱认知、自律或终身学习的幽默/硬核金句，给新的一天打打鸡血。）"""


def _build_candidates_text(candidates: list[dict]) -> tuple[list[str], str]:
    """构建候选情报的格式化文本。返回 (分段列表, 完整文本)。"""
    parts = []
    for i, item in enumerate(candidates):
        source = item.get("source", "Unknown")
        title = item.get("title", "")
        summary = item.get("summary", "")
        url = item.get("url", "")
        extra = ""
        if source == "Hacker News":
            extra = f" | HN 分数: {item.get('score', 0)} | 评论: {item.get('comments', 0)}"
        elif source == "GitHub Trending":
            extra = f" | 今日星数: {item.get('stars_today', 0)}"
        elif source == "ArXiv":
            extra = f" | 分类: {', '.join(item.get('categories', []))}"
        parts.append(
            f"[{i+1}] ({source}{extra})\n"
            f"标题: {title}\n"
            f"摘要: {summary}\n"
            f"链接: {url}\n"
        )
    return parts, "\n---\n".join(parts)


def _build_user_message(candidates_text: str, n_candidates: int, date_str: str) -> str:
    """构建发送给 LLM 的 user message。"""
    return f"""以下是今日（{date_str}）从 GitHub Trending、Hacker News、ArXiv 等渠道收集到的候选情报列表，共 {n_candidates} 条。

请从中精选 3 条最有价值的，按照你的输出格式生成今日简报。

候选情报列表：
---
{candidates_text}
---"""


def curate_with_llm(candidates: list[dict], date_str: str) -> str | None:
    """
    LLM 策展 — 多 provider 自动选择。
    优先级: DeepSeek > Anthropic > 回退到启发式
    DeepSeek: 便宜（¥1/百万 token），中文能力强，OpenAI 兼容 API
    Anthropic: 英语理解更强，毒舌风格更犀利
    """
    parts, candidates_text = _build_candidates_text(candidates)
    user_message = _build_user_message(candidates_text, len(candidates), date_str)

    # ── 优先 DeepSeek（便宜、中文好、OpenAI 兼容）──
    if DEEPSEEK_API_KEY:
        result = _curate_with_deepseek(user_message, date_str)
        if result:
            return result
        print("[简报] ⚠ DeepSeek 失败，尝试 Anthropic 备选...")

    # ── 备选 Anthropic ──
    if ANTHROPIC_API_KEY:
        result = _curate_with_claude_api(parts, user_message, date_str)
        if result:
            return result
        print("[简报] ⚠ Anthropic 也失败了")

    return None


def _curate_with_deepseek(user_message: str, date_str: str) -> str | None:
    """通过 DeepSeek API（OpenAI 兼容）策展。"""
    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "max_tokens": 4096,
                "temperature": 0.85,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT.replace("{DATE}", date_str)},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            print(f"  ⚠ DeepSeek API HTTP 错误 {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  ⚠ DeepSeek API 调用失败: {e}")
        return None


def _curate_with_claude_api(parts: list[str], user_message: str, date_str: str) -> str | None:
    """通过 Anthropic Claude API 策展（SDK 优先，HTTP 备选）。"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            temperature=0.85,
            system=SYSTEM_PROMPT.replace("{DATE}", date_str),
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except ImportError:
        pass
    except Exception as e:
        print(f"  ⚠ Claude SDK 调用失败: {e}")

    # HTTP 备选
    candidates_text = "\n---\n".join(parts)
    user_message_http = _build_user_message(candidates_text, len(parts), date_str)
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 4096,
                "temperature": 0.85,
                "system": SYSTEM_PROMPT.replace("{DATE}", date_str),
                "messages": [{"role": "user", "content": user_message_http}],
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["content"][0]["text"]
        else:
            print(f"  ⚠ Anthropic API HTTP 错误 {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  ⚠ Anthropic API HTTP 调用失败: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 启发式回退（无 LLM 时）
# ═══════════════════════════════════════════════════════════════

HEURISTIC_COMMENTARY = {
    "GitHub Trending": "开源社区用脚投票的结果——星星数不会说谎，但 README 里的 'production-ready' 可能会。",
    "Hacker News": "HN 老哥们吵得越凶，这个方向越值得关注。评论区永远比原文精彩。",
    "ArXiv": "论文发了 ≠ 能用。但连论文都不发的东西，八成是 PPT 造车。",
    "Tech RSS": "科技媒体的标题党浓度不低，这条我们帮你过了一遍滤镜。",
}

HEURISTIC_QUOTES = [
    "代码写得烂不丢人，丢人的是不写测试。技术债的利息比你想象的高。",
    "AI 不会让你失业，但会用 AI 的人会。学不会新工具才是真正的职业危机。",
    "牛市里人人都是股神，熊市里活下来的才是交易员。杠杆是双刃剑，别用它刮胡子。",
    "大多数「改变世界」的项目，最终只改变了创始人的简历。但少数成功的，真的改变了世界。",
    "你的竞争对手在熬夜读论文，你在熬夜刷短视频。一年后，差距不用解释。",
    "开源不是因为开发者闲，是因为他们受不了闭源软件的垃圾体验。这才叫用脚投票。",
    "投资的秘诀不是预测未来，而是比别人更快地理解现在。信息差 = 利润。",
]


def generate_heuristic_briefing(candidates: list[dict], date_str: str) -> str:
    """无 LLM 时的启发式简报生成。

    从 top candidates 中取前 3 条不同来源的，生成带模板点评的简报。
    """
    # 确保多样性：优先取不同来源
    selected = []
    used_sources = set()
    for item in candidates:
        src = item.get("source", "")
        if src not in used_sources or len(selected) < 3:
            selected.append(item)
            used_sources.add(src)
        if len(selected) >= BRIEFING_ITEMS:
            break

    # 补足 3 条
    if len(selected) < BRIEFING_ITEMS:
        for item in candidates:
            if item not in selected:
                selected.append(item)
            if len(selected) >= BRIEFING_ITEMS:
                break

    # 简单翻译标题（基础规则）
    def basic_translate(text: str) -> str:
        """对英文标题做最基础的关键词替换，尽可能让它看起来像中文。"""
        # 这只是一个 placeholder 级别的"翻译"，真正的翻译靠 LLM
        return text

    parts = [
        f"# 🗞️ 每日硬核情报简报 | {date_str}",
        "",
        '> 💡 *"用最毒舌的视角，看最前沿的科技。"*',
        "",
        "> ⚠️ 本简报由启发式算法自动生成（未配置 LLM API Key）。",
        "> 设置 `DEEPSEEK_API_KEY` 或 `ANTHROPIC_API_KEY` 即可启用 AI 深度策展与毒舌点评。",
        "",
        "---",
        "",
    ]

    for idx, item in enumerate(selected, 1):
        title = item.get("title", "Unknown")
        summary = item.get("summary", "")
        url = item.get("url", "")
        source = item.get("source", "Unknown")

        # 截取摘要前150字作为核心干货
        short_summary = summary[:200].strip() if summary else "详情请查看原链接"

        commentary = HEURISTIC_COMMENTARY.get(source, "信息量有限，建议查看原文自行判断。")

        parts.append(f"### {idx}. 📌 {title} (来源: {source})")
        parts.append(f"- **核心干货**：{short_summary}")
        parts.append(f"- **毒舌/硬核点评**：{commentary}")
        parts.append(f"- **🔗 传送门**：[点击直达原链接]({url})")
        parts.append("")
        parts.append("---")
        parts.append("")

    # 金句
    import random
    quote = random.choice(HEURISTIC_QUOTES)
    parts.append("### 🗣️ 今日顶男金句")
    parts.append(f"> {quote}")
    parts.append("")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 数据保存
# ═══════════════════════════════════════════════════════════════

def parse_briefing_md_to_items(briefing_md: str) -> list[dict]:
    """从 Markdown 简报中解析出结构化条目列表（供网站渲染）。

    Returns:
        [
            {"title": "...", "source": "...", "summary": "...", "commentary": "...", "url": "..."},
            ...
        ]
        以及最后一个元素可能是 {"quote": "..."}
    """
    items = []
    lines = briefing_md.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # 匹配条目标题行: ### N. 📌 title (来源: source)
        item_match = re.match(r'###\s+\d+\.\s*📌\s*(.+?)\s*\(来源:\s*(.+?)\)\s*$', line)
        if item_match:
            title = item_match.group(1).strip()
            source = item_match.group(2).strip()
            summary = ""
            commentary = ""
            url = ""

            # 读取接下来的几行找核心干货、点评、传送门
            for j in range(i + 1, min(i + 8, len(lines))):
                sub = lines[j]
                if sub.startswith("- **核心干货**"):
                    summary = re.sub(r'^- \*\*核心干货\*\*[：:]\s*', '', sub).strip()
                elif sub.startswith("- **毒舌") or sub.startswith("- **硬核"):
                    commentary = re.sub(r'^- \*\*(?:毒舌/硬核|硬核/毒舌|毒舌|硬核)点评\*\*[：:]\s*', '', sub).strip()
                elif "🔗 传送门" in sub and "点击直达原链接" in sub:
                    url_m = re.search(r'\]\((.+?)\)', sub)
                    if url_m:
                        url = url_m.group(1).strip()
                elif sub.startswith("---"):
                    break  # 条目结束

            items.append({
                "title": title,
                "source": source,
                "summary": summary,
                "commentary": commentary,
                "url": url,
            })
            i += 1
            continue

        # 匹配金句行
        if line.startswith("### 🗣️"):
            # 下一行是 > quote
            if i + 1 < len(lines) and lines[i + 1].startswith(">"):
                quote = lines[i + 1][1:].strip()
                items.append({"quote": quote})
            i += 2
            continue

        i += 1

    return items


def save_briefing_json(candidates: list[dict], briefing_md: str, date_str: str) -> dict:
    """保存结构化简报数据到 JSON（供网站读取）。

    Returns:
        保存的简报数据 dict。
    """
    # 去掉评分字段（内部使用）
    clean_candidates = []
    for item in candidates:
        c = {k: v for k, v in item.items() if not k.startswith("_")}
        clean_candidates.append(c)

    # 解析 Markdown 为结构化条目
    briefing_items = parse_briefing_md_to_items(briefing_md)

    briefing_data = {
        "date": date_str,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": len(candidates),
        "briefing_markdown": briefing_md,
        "briefing_items": briefing_items,
        "candidates": clean_candidates,
        "ai_curated": bool(DEEPSEEK_API_KEY or ANTHROPIC_API_KEY),
    }

    path = os.path.join(DATA_DIR, "daily_briefing.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(briefing_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"[简报] 结构化数据已保存到 {path}")
    return briefing_data


def save_briefing_md(briefing_md: str) -> str:
    """保存 Markdown 简报文件。"""
    path = os.path.join(PROJECT_ROOT, "daily_briefing.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(briefing_md)
    print(f"[简报] Markdown 已保存到 {path}")
    return path


# ═══════════════════════════════════════════════════════════════
# 微信推送 (Server酱)
# ═══════════════════════════════════════════════════════════════

def push_to_wechat(briefing_md: str, date_str: str):
    """
    通过 Server酱 将简报推送到微信。
    需要设置 SERVERCHAN_SEND_KEY 环境变量。

    获取 Key: https://sct.ftqq.com/ → 微信扫码登录 → 获取 SendKey
    免费额度: 每天 5 条推送（完全够用）
    """
    if not SERVERCHAN_SEND_KEY:
        print("[推送] 🔇 未配置 SERVERCHAN_SEND_KEY，跳过微信推送")
        print("[推送] 💡 获取 Key: https://sct.ftqq.com/ → 微信扫码 → 复制 SendKey")
        return False

    # 提取纯文本摘要（微信卡片不支持 Markdown 渲染，取前几行）
    lines = briefing_md.strip().split("\n")
    title = f"🗞️ 硬核科技情报 | {date_str}"

    # 提取简报核心内容作为推送正文（去掉 Markdown 标记符号）
    body_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            body_lines.append("")
            continue
        # 移除 Markdown 符号，保留可读文本
        clean = stripped.lstrip("#>-* ")
        body_lines.append(clean)

    desp = "\n".join(body_lines[:60])  # 限制长度
    if len(body_lines) > 60:
        desp += f"\n\n... (共 {len(body_lines)} 行，完整内容见 GitHub)"

    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_SEND_KEY}.send",
            data={"title": title, "desp": desp},
            timeout=15
        )
        # 记录完整响应用于调试
        print(f"[推送] HTTP {resp.status_code}")
        result = resp.json()
        print(f"[推送] 完整响应: {json.dumps(result, ensure_ascii=False)}")
        data_field = result.get("data", {})
        if isinstance(data_field, dict):
            data_errno = data_field.get("errno", 0)
        else:
            data_errno = 0
        print(f"[推送] Server酱响应: code={result.get('code')}, errno={result.get('errno')}, "
              f"data.errno={data_errno}, message={result.get('message', 'N/A')}")

        # Server酱 v2 API: code=0 且 data.errno=0 才是真正成功
        if result.get("code") == 0 and data_errno == 0:
            print(f"[推送] ✅ 微信推送成功")
            return True
        elif result.get("code") == 0:
            # code=0 但 data.errno != 0: 假成功
            print(f"[推送] ⚠️ Server酱部分失败: code=0 但 data.errno={data_errno}, "
                  f"message={data_field.get('message', '?')}")
            return False
        else:
            print(f"[推送] ⚠️ Server酱返回错误: code={result.get('code')}, message={result.get('message', '未知')}")
            return False
    except requests.exceptions.JSONDecodeError:
        print(f"[推送] ❌ Server酱返回非JSON响应: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[推送] ❌ 微信推送失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def generate_daily_briefing() -> dict:
    """生成每日情报简报。"""
    now = datetime.now(timezone.utc)
    beijing_now = now + timedelta(hours=8)
    date_str = beijing_now.strftime("%Y-%m-%d")
    print(f"[简报] ⏰ 生成每日情报简报 — {date_str}")

    # ── 1. 数据抓取 ──
    print("[简报] 📥 正在抓取数据...")

    print("  → GitHub Trending...")
    gh_items = fetch_github_trending()
    print(f"    获取 {len(gh_items)} 条")

    print("  → Hacker News...")
    hn_items = fetch_hacker_news()
    print(f"    获取 {len(hn_items)} 条")

    print("  → ArXiv...")
    arxiv_items = fetch_arxiv_papers()
    print(f"    获取 {len(arxiv_items)} 条")

    print("  → Tech RSS...")
    rss_items = fetch_tech_rss()
    print(f"    获取 {len(rss_items)} 条")

    print("  → Lobste.rs...")
    lob_items = fetch_lobsters()
    print(f"    获取 {len(lob_items)} 条")

    # ── 2. 合并 + 预过滤 ──
    all_items = gh_items + hn_items + arxiv_items + rss_items + lob_items
    print(f"[简报] 📊 合并共 {len(all_items)} 条，开始评分筛选...")
    candidates = pre_filter_candidates(all_items)
    print(f"[简报] 🎯 筛选出 {len(candidates)} 条候选 (top score: {candidates[0]['_score']:.1f})" if candidates else "[简报] ⚠ 无候选条目！")

    # ── 3. AI 策展（或启发式回退）──
    provider = "DeepSeek" if DEEPSEEK_API_KEY else "Claude" if ANTHROPIC_API_KEY else None
    if provider:
        print(f"[简报] 🤖 使用 {provider} API 策展...")
        briefing_md = curate_with_llm(candidates, date_str)
        if briefing_md:
            print(f"[简报] ✅ {provider} 策展完成")
        else:
            print(f"[简报] ⚠ {provider} 策展失败，回退到启发式模式")
            briefing_md = generate_heuristic_briefing(candidates, date_str)
    else:
        print("[简报] 🔧 未配置 LLM API Key（DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY），使用启发式模式")
        print("[简报] 💡 DeepSeek 推荐: https://platform.deepseek.com → API Keys → 充值 ¥1 够用几个月")
        briefing_md = generate_heuristic_briefing(candidates, date_str)

    # ── 4. 保存 ──
    save_briefing_md(briefing_md)
    briefing_data = save_briefing_json(candidates, briefing_md, date_str)

    # ── 5. 微信推送 ──
    push_to_wechat(briefing_md, date_str)

    print("[简报] ✅ 每日情报简报生成完毕")
    return briefing_data


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="每日硬核情报简报生成器")
    parser.add_argument("--fetch-only", action="store_true", help="只抓取数据，不生成简报")
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 路径（可选）")
    args = parser.parse_args()

    if args.fetch_only:
        items = (
            fetch_github_trending()
            + fetch_hacker_news()
            + fetch_arxiv_papers()
            + fetch_tech_rss()
            + fetch_lobsters()
        )
        candidates = pre_filter_candidates(items)
        # 清理评分字段后输出
        clean = []
        for item in candidates:
            c = {k: v for k, v in item.items() if not k.startswith("_")}
            clean.append(c)
        out_path = args.output or os.path.join(DATA_DIR, "raw_candidates.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2, default=str)
        print(f"[简报] 原始候选数据已保存到 {out_path} ({len(clean)} 条)")
    else:
        generate_daily_briefing()
