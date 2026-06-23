"""
A股数据抓取模块
数据源：akshare（东方财富/新浪财经）
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys
import warnings
warnings.filterwarnings('ignore')

# 添加父目录以导入 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import A_STOCKS, MACD_FAST, MACD_SLOW, MACD_SIGNAL, RSI_PERIOD, MA_PERIODS


def calc_macd(close_series):
    """计算 MACD"""
    ema_fast = close_series.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close_series.ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    histogram = (macd_line - signal_line) * 2  # 柱状图（乘以2是常见做法）
    return {
        "macd": round(macd_line.iloc[-1], 4),
        "signal": round(signal_line.iloc[-1], 4),
        "histogram": round(histogram.iloc[-1], 4),
    }


def calc_rsi(close_series):
    """计算 RSI"""
    delta = close_series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)


def calc_ma(close_series):
    """计算均线"""
    ma_values = {}
    for period in MA_PERIODS:
        ma = close_series.rolling(window=period).mean()
        ma_values[f"MA{period}"] = round(ma.iloc[-1], 2) if not pd.isna(ma.iloc[-1]) else None
    return ma_values


def fetch_a_stock_data():
    """
    获取所有A股标的数据
    返回 list of dict
    """
    if not A_STOCKS:
        print("[A股] 未配置A股标的，跳过")
        return []

    print(f"[A股] 开始获取 {len(A_STOCKS)} 只股票数据...")
    results = []

    for stock in A_STOCKS:
        code = stock["code"]
        name = stock["name"]
        print(f"  → 正在处理 {name}({code})...")

        try:
            # 确定市场前缀
            if code.startswith("6") or code.startswith("688") or code.startswith("689"):
                symbol = f"sh{code}"
            elif code.startswith("0") or code.startswith("3"):
                symbol = f"sz{code}"
            elif code.startswith("8") or code.startswith("4"):
                symbol = f"bj{code}"
            else:
                symbol = f"sz{code}"

            # 获取历史K线（日线，最近120天用于计算指标）
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")

            hist_df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 前复权
            )

            if hist_df.empty:
                print(f"    ⚠ {name} 无历史数据，跳过")
                continue

            close_prices = hist_df["收盘"]
            latest = hist_df.iloc[-1]
            prev = hist_df.iloc[-2] if len(hist_df) > 1 else latest

            # 涨跌幅
            change_pct = round(((latest["收盘"] - prev["收盘"]) / prev["收盘"]) * 100, 2)

            # 技术指标
            macd_data = calc_macd(close_prices)
            rsi = calc_rsi(close_prices)
            ma_data = calc_ma(close_prices)

            # 获取实时行情（市值、PE、行业）
            try:
                realtime = ak.stock_zh_a_spot_em()
                stock_row = realtime[realtime["代码"] == code]
                if not stock_row.empty:
                    row = stock_row.iloc[0]
                    market_cap = row.get("总市值", None)
                    pe = row.get("市盈率-动态", None)
                    volume = row.get("成交量", None)
                    turnover = row.get("成交额", None)
                    high = row.get("最高", None)
                    low = row.get("最低", None)
                    open_price = row.get("今开", None)
                else:
                    market_cap = pe = volume = turnover = high = low = open_price = None
            except Exception:
                market_cap = pe = volume = turnover = high = low = open_price = None

            # 获取行业信息
            try:
                industry_info = ak.stock_individual_info_em(symbol=code)
                industry = None
                if not industry_info.empty:
                    ind_row = industry_info[industry_info["item"] == "行业"]
                    if not ind_row.empty:
                        industry = ind_row.iloc[0]["value"]
            except Exception:
                industry = None

            # 获取资金流向
            try:
                fund_flow_df = ak.stock_individual_fund_flow(stock=code, market="sh" if symbol.startswith("sh") else "sz")
                if not fund_flow_df.empty:
                    latest_flow = fund_flow_df.iloc[-1]
                    main_net_flow = latest_flow.get("主力净流入", None)
                    # 单位转换：万元 → 亿元
                    if main_net_flow is not None:
                        main_net_flow = round(main_net_flow / 10000, 2)  # 转为亿元
                else:
                    main_net_flow = None
            except Exception:
                main_net_flow = None

            stock_data = {
                "market": "A股",
                "code": code,
                "name": name,
                "symbol": symbol,
                "industry": industry,
                "price": round(float(latest["收盘"]), 2),
                "open": round(float(open_price), 2) if open_price is not None else None,
                "high": round(float(high), 2) if high is not None else None,
                "low": round(float(low), 2) if low is not None else None,
                "change_pct": change_pct,
                "volume": int(volume) if volume is not None else None,
                "turnover": round(float(turnover) / 1e8, 2) if turnover is not None else None,  # 转为亿元
                "market_cap": round(float(market_cap) / 1e8, 2) if market_cap is not None else None,  # 转为亿元
                "pe": round(float(pe), 2) if pe is not None else None,
                "macd": macd_data["macd"],
                "macd_signal": macd_data["signal"],
                "macd_histogram": macd_data["histogram"],
                "rsi": rsi,
                "ma": ma_data,
                "main_net_flow": main_net_flow,  # 主力资金净流入（亿元）
            }
            results.append(stock_data)
            print(f"    ✓ {name}: ¥{stock_data['price']}, {change_pct:+.2f}%")

        except Exception as e:
            print(f"    ✗ {name}({code}) 数据获取失败: {str(e)[:100]}")
            continue

    print(f"[A股] 完成，成功获取 {len(results)}/{len(A_STOCKS)} 只股票数据")
    return results


if __name__ == "__main__":
    data = fetch_a_stock_data()
    print(json.dumps(data, ensure_ascii=False, indent=2))
