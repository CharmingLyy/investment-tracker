"""
主入口脚本
每天运行一次，抓取所有市场数据并生成HTML页面
"""
import sys
import io

# 修复 Windows 下 emoji 编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json
import os
import sys
from datetime import datetime

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.config import A_STOCKS, HK_STOCKS, US_STOCKS, CRYPTO
from scripts.fetch_stocks import fetch_a_stock_data
from scripts.fetch_global import fetch_hk_stock_data, fetch_us_stock_data
from scripts.fetch_crypto import fetch_crypto_data
from scripts.fetch_news import fetch_market_news, find_relevant_news


def generate_html(all_data, news_data, update_time):
    """使用 Jinja2 模板生成HTML"""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    templates_dir = os.path.join(PROJECT_ROOT, "templates")
    if not os.path.exists(templates_dir):
        templates_dir = PROJECT_ROOT

    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("index.html")

    a_stocks = all_data.get("a_stocks", [])
    hk_stocks = all_data.get("hk_stocks", [])
    us_stocks = all_data.get("us_stocks", [])
    crypto_list = all_data.get("crypto", [])

    all_items = a_stocks + hk_stocks + us_stocks + crypto_list
    up_count = sum(1 for s in all_items if s.get("change_pct", 0) > 0)
    down_count = sum(1 for s in all_items if s.get("change_pct", 0) < 0)
    total_count = len(all_items)
    up_pct = round(up_count / total_count * 100, 1) if total_count > 0 else 0
    down_pct = round(down_count / total_count * 100, 1) if total_count > 0 else 0

    now = datetime.now()
    is_weekday = now.weekday() < 5
    markets_open = is_weekday

    html = template.render(
        update_time=update_time,
        a_stocks=a_stocks,
        hk_stocks=hk_stocks,
        us_stocks=us_stocks,
        crypto_list=crypto_list,
        news=news_data,
        total_count=total_count,
        up_count=up_count,
        down_count=down_count,
        up_pct=up_pct,
        down_pct=down_pct,
        a_count=len(a_stocks),
        hk_count=len(hk_stocks),
        us_count=len(us_stocks),
        crypto_count=len(crypto_list),
        news_count=len(news_data),
        markets_open=markets_open,
    )
    return html


def save_data_json(all_data, news_data):
    """保存原始数据到 data/ 目录"""
    data_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d")

    # 保存完整数据
    full_data = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stocks": all_data,
        "news": news_data,
    }
    with open(os.path.join(data_dir, f"data_{timestamp}.json"), "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2, default=str)

    # 同时保存为 latest.json（方便查看最新数据）
    with open(os.path.join(data_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"[保存] 数据已保存到 data/data_{timestamp}.json")


def main():
    print("=" * 60)
    print("📊 投资观察面板 - 数据更新")
    print(f"⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_data = {}

    # 1. 抓取A股数据
    print()
    all_data["a_stocks"] = fetch_a_stock_data()

    # 2. 抓取港股数据
    print()
    all_data["hk_stocks"] = fetch_hk_stock_data()

    # 3. 抓取美股数据
    print()
    all_data["us_stocks"] = fetch_us_stock_data()

    # 4. 抓取加密货币数据
    print()
    all_data["crypto"] = fetch_crypto_data()

    # 5. 抓取新闻
    print()
    news_data = fetch_market_news()

    # 6. 保存原始数据
    print()
    save_data_json(all_data, news_data)

    # 7. 生成HTML
    print()
    print("[生成] 正在生成HTML页面...")
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M UTC+8 (北京时间)")
    html_content = generate_html(all_data, news_data, update_time)

    output_path = os.path.join(PROJECT_ROOT, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 8. 汇总
    total = (
        len(all_data["a_stocks"])
        + len(all_data["hk_stocks"])
        + len(all_data["us_stocks"])
        + len(all_data["crypto"])
    )
    print(f"[完成] ✅ HTML已生成: {output_path}")
    print(f"[统计] 共 {total} 个标的, {len(news_data)} 条新闻")
    print("=" * 60)


if __name__ == "__main__":
    main()
