"""
A股数据抓取模块
数据源：baostock（主）+ akshare（备用）
"""
import pandas as pd
import numpy as np
import baostock as bs
from datetime import datetime, timedelta
import json
import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import A_STOCKS, MACD_FAST, MACD_SLOW, MACD_SIGNAL, RSI_PERIOD, MA_PERIODS


def calc_macd(close_series):
    """计算 MACD"""
    ema_fast = close_series.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close_series.ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    histogram = (macd_line - signal_line) * 2
    return {
        "macd": round(macd_line.iloc[-1], 4) if len(macd_line) > 0 else None,
        "signal": round(signal_line.iloc[-1], 4) if len(signal_line) > 0 else None,
        "histogram": round(histogram.iloc[-1], 4) if len(histogram) > 0 else None,
    }


def calc_rsi(close_series):
    """计算 RSI"""
    if len(close_series) < RSI_PERIOD + 1:
        return None
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
        ma_values[f"MA{period}"] = round(ma.iloc[-1], 2) if len(ma) > 0 and not pd.isna(ma.iloc[-1]) else None
    return ma_values


def _enrich_a_stock(results):
    """补充A股数据：业务描述和现金流（使用 akshare）"""
    import akshare as ak
    for r in results:
        code = r["code"]
        name = r["name"]
        # 预设默认值
        r["business"] = None
        r["cash_flow"] = None

        # 获取主营业务（使用 cninfo 源，不走 Eastmoney 代理）
        try:
            profile = ak.stock_profile_cninfo(symbol=code)
            if not profile.empty:
                row = profile.iloc[0]
                biz = row.get("主营业务", "") or row.get("经营范围", "")
                if biz and str(biz) != "nan" and str(biz).strip():
                    biz_str = str(biz).strip()
                    r["business"] = biz_str[:80] + "..." if len(biz_str) > 80 else biz_str
        except Exception:
            pass

        # 获取现金流数据（使用同花顺财务摘要）
        try:
            fin = ak.stock_financial_abstract_ths(symbol=code, indicator="按年度")
            if not fin.empty:
                # 使用最新年份（最后一行）
                latest_row = fin.iloc[-1]
                # 获取每股经营现金流
                for col in fin.columns:
                    col_str = str(col)
                    if "经营" in col_str and "现金流" in col_str:
                        cf_val = latest_row[col]
                        if cf_val is not None and str(cf_val) != "nan":
                            per_share_cf = float(cf_val)
                            # 尝试获取注册资金来估算总现金流（万元）
                            try:
                                reg_cap_raw = profile.iloc[0].get("注册资金", 0)
                                reg_cap = float(reg_cap_raw) if reg_cap_raw else 0
                                if reg_cap > 0:
                                    # 总现金流(亿) = 每股现金流 × 注册资本(万元) / 10000
                                    r["cash_flow"] = round(per_share_cf * reg_cap / 10000, 2)
                                else:
                                    r["cash_flow"] = None
                            except Exception:
                                r["cash_flow"] = None
                        break
        except Exception:
            pass

        if r.get("business"):
            print(f"    📋 {name}: 业务={r['business'][:40]}...")
        if r.get("cash_flow") is not None:
            print(f"    💰 {name}: 经营现金流={r['cash_flow']}亿")
        time.sleep(0.8)


def fetch_a_stock_data():
    """
    获取所有A股标的数据
    优先使用 baostock，失败时回退到 akshare
    """
    if not A_STOCKS:
        print("[A股] 未配置A股标的，跳过")
        return []

    print(f"[A股] 开始获取 {len(A_STOCKS)} 只股票数据...")
    results = []

    # 方法1: baostock
    bs_results = _fetch_via_baostock()
    if bs_results:
        results.extend(bs_results)

    # 方法2: 对 baostock 失败的标的使用 akshare 重试
    bs_codes = {r["code"] for r in bs_results}
    for stock in A_STOCKS:
        if stock["code"] not in bs_codes:
            print(f"  → {stock['name']}({stock['code']}) baostock 失败，尝试 akshare...")
            result = _fetch_via_akshare(stock["code"], stock["name"])
            if result:
                results.append(result)
                print(f"    ✓ akshare: ¥{result['price']}, {result['change_pct']:+.2f}%")
            else:
                print(f"    ✗ 所有数据源均失败")
            time.sleep(1)

    # 补充业务描述和现金流数据
    if results:
        print(f"\n[A股] 补充业务描述和现金流数据...")
        _enrich_a_stock(results)

    print(f"[A股] 完成，成功获取 {len(results)}/{len(A_STOCKS)} 只股票数据")
    return results


def _fetch_via_baostock():
    """使用 baostock 批量获取A股数据"""
    results = []
    try:
        lg = bs.login()
        if lg.error_code != '0':
            print(f"  ⚠ baostock 登录失败: {lg.error_msg}")
            return results

        for stock in A_STOCKS:
            code = stock["code"]
            name = stock["name"]
            print(f"  → {name}({code}) [baostock]")

            try:
                # 确定市场前缀
                if code.startswith("6") or code.startswith("688") or code.startswith("689"):
                    bs_code = f"sh.{code}"
                    market = "sh"
                elif code.startswith("0") or code.startswith("3"):
                    bs_code = f"sz.{code}"
                    market = "sz"
                elif code.startswith("8") or code.startswith("4"):
                    bs_code = f"bj.{code}"
                    market = "bj"
                else:
                    bs_code = f"sz.{code}"
                    market = "sz"

                # 计算日期范围（180天）
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=250)).strftime("%Y-%m-%d")

                # 获取历史K线
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount,turn",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="2",  # 前复权
                )
                if rs.error_code != '0':
                    print(f"    ⚠ baostock 查询失败: {rs.error_msg}")
                    continue

                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())

                if len(rows) < 30:
                    print(f"    ⚠ {name} 历史数据不足 ({len(rows)} 条)")
                    continue

                df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount", "turn"])
                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                df["open"] = pd.to_numeric(df["open"], errors="coerce")
                df["high"] = pd.to_numeric(df["high"], errors="coerce")
                df["low"] = pd.to_numeric(df["low"], errors="coerce")
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
                df["turn"] = pd.to_numeric(df["turn"], errors="coerce")
                df = df.dropna(subset=["close"])

                if len(df) < 2:
                    continue

                close_prices = df["close"]
                latest = df.iloc[-1]
                prev = df.iloc[-2]

                change_pct = round(((latest["close"] - prev["close"]) / prev["close"]) * 100, 2)
                macd_data = calc_macd(close_prices)
                rsi = calc_rsi(close_prices)
                ma_data = calc_ma(close_prices)

                # 获取行业分类
                industry = _get_baostock_industry(bs, code, market)

                # 获取市值和PE（通过股票基本信息）
                mcap, pe = _get_baostock_finance(bs, bs_code)

                stock_data = {
                    "market": "A股",
                    "code": code,
                    "name": name,
                    "symbol": bs_code,
                    "industry": industry,
                    "business": None,
                    "price": round(float(latest["close"]), 2),
                    "open": round(float(latest["open"]), 2) if not pd.isna(latest["open"]) else None,
                    "high": round(float(latest["high"]), 2) if not pd.isna(latest["high"]) else None,
                    "low": round(float(latest["low"]), 2) if not pd.isna(latest["low"]) else None,
                    "change_pct": change_pct,
                    "volume": int(latest["volume"]) if not pd.isna(latest["volume"]) else None,
                    "turnover": round(float(latest["amount"]) / 1e8, 2) if not pd.isna(latest["amount"]) else None,
                    "market_cap": mcap,
                    "pe": pe,
                    "cash_flow": None,
                    "macd": macd_data["macd"],
                    "macd_signal": macd_data["signal"],
                    "macd_histogram": macd_data["histogram"],
                    "rsi": rsi,
                    "ma": ma_data,
                    "main_net_flow": None,  # baostock 不提供资金流向
                }
                results.append(stock_data)
                print(f"    ✓ ¥{stock_data['price']}, {change_pct:+.2f}%")

            except Exception as e:
                print(f"    ✗ baostock 处理失败: {str(e)[:80]}")

        bs.logout()
    except Exception as e:
        print(f"  ⚠ baostock 整体失败: {str(e)[:80]}")
        try:
            bs.logout()
        except:
            pass

    return results


def _get_baostock_industry(bs, code, market):
    """获取行业信息"""
    try:
        rs = bs.query_stock_industry()
        while rs.next():
            row = rs.get_row_data()
            if row[1] == code:
                return row[3]  # 行业名称
    except:
        pass
    return None


def _get_baostock_finance(bs, bs_code):
    """获取市值和PE"""
    mcap, pe = None, None
    try:
        # 获取估值数据
        today = datetime.now().strftime("%Y-%m-%d")
        rs = bs.query_history_k_data_plus(
            bs_code, "date,peTTM", start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
            end_date=today, frequency="d", adjustflag="2"
        )
        if rs.error_code == '0':
            data = []
            while rs.next():
                data.append(rs.get_row_data())
            if data:
                pe_val = data[-1][1]
                if pe_val and pe_val != '' and pe_val != '0.000000':
                    pe = round(float(pe_val), 2)
    except:
        pass
    return mcap, pe


def _fetch_via_akshare(code, name):
    """使用 akshare 作为备用数据源"""
    try:
        import akshare as ak

        if code.startswith("6") or code.startswith("688") or code.startswith("689"):
            market = "sh"
        elif code.startswith("0") or code.startswith("3"):
            market = "sz"
        else:
            market = "sz"

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")

        hist_df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        if hist_df.empty:
            return None

        close_prices = hist_df["收盘"]
        latest = hist_df.iloc[-1]
        prev = hist_df.iloc[-2] if len(hist_df) > 1 else latest

        change_pct = round(((latest["收盘"] - prev["收盘"]) / prev["收盘"]) * 100, 2)
        macd_data = calc_macd(close_prices)
        rsi = calc_rsi(close_prices)
        ma_data = calc_ma(close_prices)

        market_cap = pe = volume = turnover = high = low = open_price = industry = None
        main_net_flow = None
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
            info = ak.stock_individual_info_em(symbol=code)
            ind_row = info[info["item"] == "行业"]
            if not ind_row.empty:
                industry = ind_row.iloc[0]["value"]
            flow_df = ak.stock_individual_fund_flow(stock=code, market=market)
            if not flow_df.empty:
                lf = flow_df.iloc[-1]
                mf = lf.get("主力净流入", None)
                if mf is not None:
                    main_net_flow = round(mf / 10000, 2)
        except:
            pass

        return {
            "market": "A股", "code": code, "name": name,
            "symbol": f"{market}{code}", "industry": industry,
            "business": None,
            "price": round(float(latest["收盘"]), 2),
            "open": round(float(open_price), 2) if open_price is not None else None,
            "high": round(float(high), 2) if high is not None else None,
            "low": round(float(low), 2) if low is not None else None,
            "change_pct": change_pct,
            "volume": int(volume) if volume is not None else None,
            "turnover": round(float(turnover) / 1e8, 2) if turnover is not None else None,
            "market_cap": round(float(market_cap) / 1e8, 2) if market_cap is not None else None,
            "pe": round(float(pe), 2) if pe is not None else None,
            "cash_flow": None,
            "macd": macd_data["macd"], "macd_signal": macd_data["signal"],
            "macd_histogram": macd_data["histogram"], "rsi": rsi, "ma": ma_data,
            "main_net_flow": main_net_flow,
        }
    except Exception:
        return None


if __name__ == "__main__":
    data = fetch_a_stock_data()
    print(json.dumps(data, ensure_ascii=False, indent=2))
