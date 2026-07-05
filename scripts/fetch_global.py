"""
港股 + 美股数据抓取模块
数据源：yfinance（主）+ Yahoo Finance API（备用）
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import HK_STOCKS, US_STOCKS, MACD_FAST, MACD_SLOW, MACD_SIGNAL, RSI_PERIOD, MA_PERIODS
from scripts.fetch_stocks import calc_macd, calc_rsi, calc_ma


def _fetch_via_yfinance(ticker_symbol):
    """使用 yfinance 库获取数据（处理 cookie/crumb 认证）"""
    import yfinance as yf
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo")
        if hist.empty:
            return None, None, None

        info = stock.info or {}

        # 获取业务描述和财务数据
        business = info.get('longBusinessSummary', '')
        if business and len(business) > 80:
            business = business[:80] + '...'

        raw_cf = info.get('freeCashflow') or info.get('operatingCashflow')
        cash_flow = round(abs(float(raw_cf)) / 1e8, 2) if raw_cf else None

        profile = {
            "business": business,
            "free_cash_flow": info.get('freeCashflow'),
            "operating_cash_flow": info.get('operatingCashflow'),
            "total_cash": info.get('totalCash'),
            "total_debt": info.get('totalDebt'),
        }

        quote = {
            "marketCap": info.get('marketCap'),
            "trailingPE": info.get('trailingPE'),
            "forwardPE": info.get('forwardPE'),
            "industry": info.get('industry') or info.get('sector'),
            "regularMarketPrice": info.get('regularMarketPrice') or info.get('currentPrice'),
        }

        return hist, quote, profile
    except Exception as e:
        print(f"    ⚠ yfinance 失败: {str(e)[:80]}")
        return None, None, None


def _process_stock(hist_df, quote_info, profile_info, code, name, market):
    """处理单只股票数据"""
    if hist_df is None or hist_df.empty or len(hist_df) < 2:
        return None

    close_prices = hist_df["Close"]
    latest = hist_df.iloc[-1]
    prev = hist_df.iloc[-2]

    change_pct = round(((latest["Close"] - prev["Close"]) / prev["Close"]) * 100, 2)
    macd_data = calc_macd(close_prices)
    rsi = calc_rsi(close_prices)
    ma_data = calc_ma(close_prices)

    market_cap = quote_info.get("marketCap", None) if quote_info else None
    pe = (quote_info.get("trailingPE") or quote_info.get("forwardPE")) if quote_info else None
    industry = quote_info.get("industry") if quote_info else None
    volume = int(latest["Volume"]) if "Volume" in latest.index and not pd.isna(latest["Volume"]) else None

    business = profile_info.get("business", "") if profile_info else ""
    raw_cf = None
    if profile_info:
        raw_cf = profile_info.get("free_cash_flow") or profile_info.get("operating_cash_flow")
    cash_flow = round(abs(float(raw_cf)) / 1e8, 2) if raw_cf is not None else None

    price_val = float(latest["Close"])
    open_val = float(latest["Open"]) if "Open" in latest.index and not pd.isna(latest["Open"]) else None
    high_val = float(latest["High"]) if "High" in latest.index and not pd.isna(latest["High"]) else None
    low_val = float(latest["Low"]) if "Low" in latest.index and not pd.isna(latest["Low"]) else None

    return {
        "market": market,
        "code": code,
        "name": name,
        "symbol": code,
        "industry": industry,
        "business": business or None,
        "price": round(price_val, 2),
        "open": round(open_val, 2) if open_val is not None else None,
        "high": round(high_val, 2) if high_val is not None else None,
        "low": round(low_val, 2) if low_val is not None else None,
        "change_pct": change_pct,
        "volume": volume,
        "turnover": None,
        "market_cap": round(float(market_cap) / 1e8, 2) if market_cap else None,
        "pe": round(float(pe), 2) if pe else None,
        "cash_flow": cash_flow,
        "macd": macd_data["macd"],
        "macd_signal": macd_data["signal"],
        "macd_histogram": macd_data["histogram"],
        "rsi": rsi,
        "ma": ma_data,
        "main_net_flow": None,
    }


def fetch_global_stocks(market_type):
    """通用全球股票数据抓取"""
    if market_type == "hk":
        stocks, suffix, market_name = HK_STOCKS, ".HK", "港股"
    else:
        stocks, suffix, market_name = US_STOCKS, "", "美股"

    if not stocks:
        print(f"[{market_name}] 未配置标的，跳过")
        return []

    print(f"[{market_name}] 开始获取 {len(stocks)} 只股票数据...")
    results = []

    for i, stock in enumerate(stocks):
        code = stock["code"]
        name = stock["name"]
        ticker = f"{str(int(code)).zfill(4)}{suffix}" if suffix else code
        print(f"  → {name}({ticker})")

        try:
            # 主要方法：yfinance
            hist_df, quote, profile = _fetch_via_yfinance(ticker)

            if hist_df is None or hist_df.empty:
                print(f"    ⚠ {name} 无法获取数据（API可能被限制）")
                continue

            result = _process_stock(hist_df, quote, profile, code, name, market_name)
            if result:
                results.append(result)
                currency = "HK$" if market_type == "hk" else "$"
                print(f"    ✓ {currency}{result['price']}, {result['change_pct']:+.2f}%")
            else:
                print(f"    ⚠ 数据处理失败")

        except Exception as e:
            print(f"    ✗ 失败: {str(e)[:100]}")

        if i < len(stocks) - 1:
            time.sleep(1.0)

    print(f"[{market_name}] 完成，成功获取 {len(results)}/{len(stocks)} 只股票数据")
    return results


def fetch_hk_stock_data():
    return fetch_global_stocks("hk")


def fetch_us_stock_data():
    return fetch_global_stocks("us")


if __name__ == "__main__":
    hk_data = fetch_hk_stock_data()
    us_data = fetch_us_stock_data()
    print(json.dumps({"hk": hk_data, "us": us_data}, ensure_ascii=False, indent=2))
