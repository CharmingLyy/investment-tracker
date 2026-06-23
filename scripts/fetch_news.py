"""
新闻抓取模块
数据源：RSS feeds + Web API（免费）
"""
import requests
import feedparser
from datetime import datetime, timedelta
import json
import os
import sys
import hashlib
import re
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import A_STOCKS, HK_STOCKS, US_STOCKS, CRYPTO

# 新闻源配置
NEWS_SOURCES = {
    "zh": [
        # 中文财经新闻RSS
        "https://rss.sina.com.cn/finance/stock/usstock/c/0000.xml",
        "https://rss.sina.com.cn/news/marquee/ddt.xml",
    ],
    "en": [
        "https://feeds.marketwatch.com/marketwatch/topstories",
        "https://www.investing.com/rss/news.rss",
    ]
}


def fetch_rss_news(source_url, name):
    """抓取RSS新闻"""
    try:
        feed = feedparser.parse(source_url)
        entries = feed.entries[:15]  # 每个源取15条
        news_list = []
        for entry in entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            link = entry.get("link", "")
            published = entry.get("published", "") or entry.get("updated", "")

            # 清洗HTML标签
            summary = re.sub(r'<[^>]+>', '', str(summary))
            summary = summary[:200]  # 截取前200字

            # 生成唯一ID
            uid = hashlib.md5((title + link).encode()).hexdigest()[:10]

            news_list.append({
                "id": uid,
                "title": title.strip(),
                "summary": summary.strip(),
                "link": link,
                "source": name,
                "published": published,
            })
        return news_list
    except Exception as e:
        print(f"  ⚠ RSS源 {name} 抓取失败: {str(e)[:60]}")
        return []


def fetch_market_news():
    """获取市场宏观新闻"""
    print("[新闻] 开始抓取市场新闻...")
    all_news = []

    # RSS新闻
    for lang, sources in NEWS_SOURCES.items():
        for source_url in sources:
            name = source_url.split("/")[2]
            news = fetch_rss_news(source_url, name)
            all_news.extend(news)
            print(f"  → {name}: 获取 {len(news)} 条")

    # 加密货币新闻（CoinGecko 免费API）
    try:
        cg_news_url = "https://api.coingecko.com/api/v3/news"
        resp = requests.get(cg_news_url, timeout=15)
        if resp.status_code == 200:
            articles = resp.json().get("data", [])[:10]
            for a in articles:
                title = a.get("title", "")
                desc = a.get("description", "")[:200]
                url = a.get("url", "")
                uid = hashlib.md5((title + url).encode()).hexdigest()[:10]
                all_news.append({
                    "id": uid,
                    "title": title.strip(),
                    "summary": desc.strip(),
                    "link": url,
                    "source": "CoinGecko",
                    "published": a.get("updated_at", ""),
                })
            print(f"  → CoinGecko 加密新闻: 获取 {len(articles)} 条")
    except Exception as e:
        print(f"  ⚠ 加密新闻获取失败: {str(e)[:60]}")

    # 去重并排序
    seen = set()
    unique_news = []
    for n in all_news:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique_news.append(n)

    # 按时间排序（如果有时间的话），取前30条
    unique_news = unique_news[:30]

    print(f"[新闻] 完成，共 {len(unique_news)} 条新闻")
    return unique_news


def find_relevant_news(all_news, keywords, max_items=5):
    """根据关键词筛选相关新闻"""
    relevant = []
    for news in all_news:
        title_lower = news["title"].lower()
        for kw in keywords:
            if kw.lower() in title_lower:
                relevant.append(news)
                break
        if len(relevant) >= max_items:
            break
    return relevant


if __name__ == "__main__":
    news = fetch_market_news()
    print(json.dumps(news, ensure_ascii=False, indent=2))
