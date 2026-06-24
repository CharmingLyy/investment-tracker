"""
港股 + 美股数据抓取模块
数据源：Yahoo Finance API（直接调用，绕过 yfinance 库限流）
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

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
})


def _yahoo_chart(ticker_symbol, period="6mo", interval="1d"):
    """
    直接调用 Yahoo Finance chart API
    返回 (history_df, meta_info)
    """
    # period 转换为 Yahoo API 参数
    period_map = {"6mo": "6mo", "1y": "1y"}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}"
    params = {
        "range": period_map.get(period, "6mo"),
        "interval": interval,
        "includePrePost": "false",
    }

    for attempt in range(3):
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            if resp.status_code == 429:
                wait = (attempt + 1) * 15
                print(f"    ⏳ 限流, 等待 {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            result = data["chart"]["result"][0]

            # 解析K线数据
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])

            # 构建 DataFrame
            df = pd.DataFrame({
                "Date": pd.to_datetime(timestamps, unit="s"),
                "Open": opens,
                "High": highs,
                "Low": lows,
                "Close": closes,
                "Volume": volumes,
            })
            df = df.set_index("Date")
            df = df.dropna(subset=["Close"])

            # meta 信息
            meta = result.get("meta", {})
            return df, meta
        except Exception as e:
            if attempt == 2:
                raise e
            time.sleep(5)

    return pd.DataFrame(), {}


def _yahoo_quote(ticker_symbol):
    """获取实时报价和基本面"""
    url = f"https://query1.finance.yahoo.com/v6/finance/quote?symbols={ticker_symbol}"
    try:
        resp = SESSION.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("quoteResponse", {}).get("result", [])
            if result:
                return result[0]
    except:
        pass
    return {}


_YAHOO_CRUMB = None


def _get_yahoo_crumb():
    """获取 Yahoo Finance API crumb（会话级缓存）"""
    global _YAHOO_CRUMB
    if _YAHOO_CRUMB:
        return _YAHOO_CRUMB
    try:
        SESSION.get("https://fc.yahoo.com/", timeout=10)
        resp = SESSION.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        if resp.status_code == 200 and resp.text.strip():
            _YAHOO_CRUMB = resp.text.strip()
            return _YAHOO_CRUMB
    except Exception:
        pass
    return None


def _yahoo_profile(ticker_symbol):
    """获取公司业务描述和财务数据（v10 API + crumb）"""
    crumb = _get_yahoo_crumb()
    if not crumb:
        return {}
    url = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/" + ticker_symbol
    params = {"modules": "assetProfile,financialData", "crumb": crumb}
    try:
        resp = SESSION.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("quoteSummary", {}).get("result", [])
            if result:
                profile = result[0].get("assetProfile", {}) or {}
                financial = result[0].get("financialData", {}) or {}
                fcf = financial.get("freeCashflow", {}) or {}
                ocf = financial.get("operatingCashflow", {}) or {}
                return {
                    "business": profile.get("longBusinessSummary", ""),
                    "free_cash_flow": fcf.get("raw") if fcf else None,
                    "operating_cash_flow": ocf.get("raw") if ocf else None,
                    "total_cash": (financial.get("totalCash", {}) or {}).get("raw"),
                    "total_debt": (financial.get("totalDebt", {}) or {}).get("raw"),
                }
    except Exception:
        pass
    return {}


def _process_stock(hist_df, quote_info, profile_info, code, name, market):
    """处理单只股票数据"""
    if hist_df.empty or len(hist_df) < 2:
        return None

    close_prices = hist_df["Close"]
    latest = hist_df.iloc[-1]
    prev = hist_df.iloc[-2]

    change_pct = round(((latest["Close"] - prev["Close"]) / prev["Close"]) * 100, 2)
    macd_data = calc_macd(close_prices)
    rsi = calc_rsi(close_prices)
    ma_data = calc_ma(close_prices)

    market_cap = quote_info.get("marketCap", None)
    pe = quote_info.get("trailingPE", None) or quote_info.get("forwardPE", None)
    industry = quote_info.get("industry", None) or quote_info.get("sector", None)
    volume = int(latest["Volume"]) if "Volume" in latest.index and not pd.isna(latest["Volume"]) else None

    # 业务描述
    business = profile_info.get("business", "") if profile_info else ""
    if business and len(business) > 80:
        business = business[:80] + "..."

    # 现金流（优先自由现金流，取绝对值并转亿）
    raw_cf = None
    if profile_info:
        raw_cf = profile_info.get("free_cash_flow") or profile_info.get("operating_cash_flow")
    cash_flow = round(abs(float(raw_cf)) / 1e8, 2) if raw_cf is not None else None

    return {
        "market": market,
        "code": code,
        "name": name,
        "symbol": code,
        "industry": industry,
        "business": business or None,
        "price": round(float(latest["Close"]), 2),
        "open": round(float(latest["Open"]), 2) if "Open" in latest.index and not pd.isna(latest["Open"]) else None,
        "high": round(float(latest["High"]), 2) if "High" in latest.index and not pd.isna(latest["High"]) else None,
        "low": round(float(latest["Low"]), 2) if "Low" in latest.index and not pd.isna(latest["Low"]) else None,
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
            # 获取K线
            hist_df, meta = _yahoo_chart(ticker)
            if hist_df.empty:
                print(f"    ⚠ K线数据为空")
                continue

            # 获取报价/基本面
            time.sleep(0.8)
            quote = _yahoo_quote(ticker)
            if not quote:
                # 从 meta 中提取价格
                quote = {
                    "regularMarketPrice": meta.get("regularMarketPrice"),
                    "marketCap": meta.get("marketCap"),
                    "trailingPE": meta.get("trailingPE"),
                }

            # 获取公司业务描述和财务数据
            time.sleep(0.5)
            profile = _yahoo_profile(ticker)

            result = _process_stock(hist_df, quote, profile, code, name, market_name)
            if result:
                results.append(result)
                currency = "HK$" if market_type == "hk" else "$"
                print(f"    ✓ {currency}{result['price']}, {result['change_pct']:+.2f}%")
            else:
                print(f"    ⚠ 数据处理失败")

        except Exception as e:
            print(f"    ✗ 失败: {str(e)[:100]}")

        # 间隔避免限流
        if i < len(stocks) - 1:
            time.sleep(1.5)

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
