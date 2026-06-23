"""
港股 + 美股数据抓取模块
数据源：yfinance
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import HK_STOCKS, US_STOCKS, MACD_FAST, MACD_SLOW, MACD_SIGNAL, RSI_PERIOD, MA_PERIODS
from scripts.fetch_stocks import calc_macd, calc_rsi, calc_ma


def fetch_hk_stock_data():
    """获取港股数据"""
    if not HK_STOCKS:
        print("[港股] 未配置港股标的，跳过")
        return []

    print(f"[港股] 开始获取 {len(HK_STOCKS)} 只股票数据...")
    results = []

    for stock in HK_STOCKS:
        code = stock["code"]
        name = stock["name"]
        print(f"  → 正在处理 {name}({code})...")

        try:
            # 港股代码补零到4位 + .HK
            ticker_code = f"{code.zfill(4)}.HK"
            ticker = yf.Ticker(ticker_code)

            # 获取历史数据（180天）
            hist = ticker.history(period="6mo")
            if hist.empty:
                print(f"    ⚠ {name} 无历史数据，跳过")
                continue

            close_prices = hist["Close"]
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            change_pct = round(((latest["Close"] - prev["Close"]) / prev["Close"]) * 100, 2)
            macd_data = calc_macd(close_prices)
            rsi = calc_rsi(close_prices)
            ma_data = calc_ma(close_prices)

            # 基本面信息
            info = ticker.info
            market_cap = info.get("marketCap", None)
            pe = info.get("trailingPE", None) or info.get("forwardPE", None)
            industry = info.get("industry", None) or info.get("sector", None)
            volume = int(latest["Volume"]) if "Volume" in latest.index else None

            stock_data = {
                "market": "港股",
                "code": code,
                "name": name,
                "symbol": ticker_code,
                "industry": industry,
                "price": round(float(latest["Close"]), 2),
                "open": round(float(latest["Open"]), 2),
                "high": round(float(latest["High"]), 2),
                "low": round(float(latest["Low"]), 2),
                "change_pct": change_pct,
                "volume": volume,
                "turnover": None,
                "market_cap": round(float(market_cap) / 1e8, 2) if market_cap else None,
                "pe": round(float(pe), 2) if pe else None,
                "macd": macd_data["macd"],
                "macd_signal": macd_data["signal"],
                "macd_histogram": macd_data["histogram"],
                "rsi": rsi,
                "ma": ma_data,
                "main_net_flow": None,  # 港股无此数据
            }
            results.append(stock_data)
            print(f"    ✓ {name}: HK${stock_data['price']}, {change_pct:+.2f}%")

        except Exception as e:
            print(f"    ✗ {name}({code}) 数据获取失败: {str(e)[:100]}")
            continue

    print(f"[港股] 完成，成功获取 {len(results)}/{len(HK_STOCKS)} 只股票数据")
    return results


def fetch_us_stock_data():
    """获取美股数据"""
    if not US_STOCKS:
        print("[美股] 未配置美股标的，跳过")
        return []

    print(f"[美股] 开始获取 {len(US_STOCKS)} 只股票数据...")
    results = []

    for stock in US_STOCKS:
        code = stock["code"]
        name = stock["name"]
        print(f"  → 正在处理 {name}({code})...")

        try:
            ticker = yf.Ticker(code)
            hist = ticker.history(period="6mo")

            if hist.empty:
                print(f"    ⚠ {name} 无历史数据，跳过")
                continue

            close_prices = hist["Close"]
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            change_pct = round(((latest["Close"] - prev["Close"]) / prev["Close"]) * 100, 2)
            macd_data = calc_macd(close_prices)
            rsi = calc_rsi(close_prices)
            ma_data = calc_ma(close_prices)

            info = ticker.info
            market_cap = info.get("marketCap", None)
            pe = info.get("trailingPE", None) or info.get("forwardPE", None)
            industry = info.get("industry", None) or info.get("sector", None)
            volume = int(latest["Volume"]) if "Volume" in latest.index else None

            stock_data = {
                "market": "美股",
                "code": code,
                "name": name,
                "symbol": code,
                "industry": industry,
                "price": round(float(latest["Close"]), 2),
                "open": round(float(latest["Open"]), 2),
                "high": round(float(latest["High"]), 2),
                "low": round(float(latest["Low"]), 2),
                "change_pct": change_pct,
                "volume": volume,
                "turnover": None,
                "market_cap": round(float(market_cap) / 1e8, 2) if market_cap else None,
                "pe": round(float(pe), 2) if pe else None,
                "macd": macd_data["macd"],
                "macd_signal": macd_data["signal"],
                "macd_histogram": macd_data["histogram"],
                "rsi": rsi,
                "ma": ma_data,
                "main_net_flow": None,
            }
            results.append(stock_data)
            print(f"    ✓ {name}: ${stock_data['price']}, {change_pct:+.2f}%")

        except Exception as e:
            print(f"    ✗ {name}({code}) 数据获取失败: {str(e)[:100]}")
            continue

    print(f"[美股] 完成，成功获取 {len(results)}/{len(US_STOCKS)} 只股票数据")
    return results


if __name__ == "__main__":
    hk_data = fetch_hk_stock_data()
    us_data = fetch_us_stock_data()
    print(json.dumps({"hk": hk_data, "us": us_data}, ensure_ascii=False, indent=2))
