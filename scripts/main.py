"""
主入口脚本
每天运行一次，抓取所有市场数据并生成HTML页面
"""
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
from scripts.fetch_crypto import fetch_crypto_data, fetch_fear_greed_index
from scripts.fetch_news import fetch_market_news, find_relevant_news
try:
    from scripts.daily_briefing import generate_daily_briefing
except ImportError:
    generate_daily_briefing = None
try:
    from scripts.generate_report import generate_report
except ImportError:
    generate_report = None


def generate_html(all_data, news_data, update_time, briefing_data=None, fear_greed=None):
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
        briefing=briefing_data,
        fear_greed=fear_greed,
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


def save_data_json(all_data, news_data, briefing_data=None, fear_greed=None):
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
    if briefing_data:
        full_data["briefing"] = briefing_data
    if fear_greed:
        full_data["fear_greed"] = fear_greed

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

    # 5a. 获取市场情绪指标（恐惧贪婪指数）
    fear_greed = None
    try:
        fear_greed = fetch_fear_greed_index()
        if fear_greed:
            print(f"[情绪] 恐惧贪婪指数: {fear_greed['value']} — {fear_greed['classification']}")
    except Exception as e:
        print(f"[情绪] 恐惧贪婪指数获取失败: {e}")

    # 5b. 尝试加载最新简报（由 daily_briefing.yml 生成）
    briefing_data = None
    briefing_json_path = os.path.join(PROJECT_ROOT, "data", "daily_briefing.json")
    if os.path.exists(briefing_json_path):
        try:
            with open(briefing_json_path, "r", encoding="utf-8") as f:
                briefing_data = json.load(f)
            # 检查新鲜度
            update_ts = briefing_data.get("update_time", "")
            print(f"[简报] 已加载现有简报 ({update_ts})")
        except Exception:
            pass

    # 如果简报太旧或不存在，尝试生成新的
    if generate_daily_briefing and not briefing_data:
        print()
        try:
            briefing_data = generate_daily_briefing()
        except Exception as e:
            print(f"[简报] 生成失败（非致命）: {e}")

    # 6. 保存原始数据
    print()
    save_data_json(all_data, news_data, briefing_data, fear_greed=fear_greed)

    # 7. 生成 Markdown 日报（可选）
    if generate_report:
        print()
        print("[报告] 正在生成 Markdown 投资日报...")
        generate_report()

    # 9. 生成HTML
    print()
    print("[生成] 正在生成HTML页面...")
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M UTC+8 (北京时间)")
    html_content = generate_html(all_data, news_data, update_time, briefing_data, fear_greed=fear_greed)

    output_path = os.path.join(PROJECT_ROOT, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 10. 汇总
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
