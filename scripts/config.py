"""
投资标配置
根据需要修改以下列表，GitHub Actions 会每天自动拉取数据

也支持通过 data/watchlist.json 文件动态配置（优先级更高）
在 admin.html 页面可以直接编辑并下载 watchlist.json
"""

import json
import os

# ============================================================
# 尝试加载 data/watchlist.json（优先于内置配置）
# ============================================================
_config_dir = os.path.dirname(os.path.abspath(__file__))
_watchlist_path = os.path.join(os.path.dirname(_config_dir), "data", "watchlist.json")

_loaded_a = None
_loaded_hk = None
_loaded_us = None
_loaded_crypto = None

if os.path.exists(_watchlist_path):
    try:
        with open(_watchlist_path, "r", encoding="utf-8") as f:
            wl = json.load(f)
        _loaded_a = wl.get("A_STOCKS") or wl.get("a_stocks")
        _loaded_hk = wl.get("HK_STOCKS") or wl.get("hk_stocks")
        _loaded_us = wl.get("US_STOCKS") or wl.get("us_stocks")
        _loaded_crypto = wl.get("CRYPTO") or wl.get("crypto")
        if _loaded_a or _loaded_hk or _loaded_us or _loaded_crypto:
            print(f"[配置] 已从 {_watchlist_path} 加载自定义标的")
    except Exception as e:
        print(f"[配置] watchlist.json 加载失败: {e}")

# ============================================================
# A股（格式：代码 + 名称）
# 代码格式：6位数字
# ============================================================
A_STOCKS = _loaded_a if _loaded_a is not None else [
    {"code": "002050", "name": "三花智控"},
    {"code": "601727", "name": "上海电气"},
]

# ============================================================
# 港股（格式：代码 + 名称）
# 代码格式：4-5位数字
# ============================================================
HK_STOCKS = _loaded_hk if _loaded_hk is not None else [
    {"code": "01810", "name": "小米集团-W"},
]

# ============================================================
# 美股（格式：ticker + 名称）
# ============================================================
US_STOCKS = _loaded_us if _loaded_us is not None else [
    {"code": "NVDA", "name": "NVIDIA"},
    {"code": "GOOG", "name": "Alphabet (Google)"},
    {"code": "CRCL", "name": "Circle"},
    {"code": "MP", "name": "MP Materials"},
    {"code": "PLTR", "name": "Palantir"},
    {"code": "NOW", "name": "ServiceNow"},
    {"code": "DDOG", "name": "Datadog"},
]

# ============================================================
# 加密货币（格式：CoinGecko ID + 名称 + 简称）
# CoinGecko ID 查找：https://www.coingecko.com
# ============================================================
CRYPTO = _loaded_crypto if _loaded_crypto is not None else [
    {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC"},
    {"id": "ethereum", "name": "Ethereum", "symbol": "ETH"},
]

# ============================================================
# 技术指标参数
# ============================================================
MACD_FAST = 12       # MACD 快线周期
MACD_SLOW = 26       # MACD 慢线周期
MACD_SIGNAL = 9      # MACD 信号线周期
RSI_PERIOD = 14      # RSI 计算周期
MA_PERIODS = [5, 10, 20, 60]  # 均线周期

# ============================================================
# 数据源设置
# ============================================================
# A股使用 akshare（免费，无需 API key）
# 港股/美股使用 yfinance（免费，无需 API key）
# 加密货币使用 CoinGecko（免费，无需 API key）
# 新闻使用 RSS feeds + web scraping
