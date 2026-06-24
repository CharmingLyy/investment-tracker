"""
加密货币数据抓取模块
数据源：CoinGecko API（免费）
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
from scripts.config import CRYPTO, MACD_FAST, MACD_SLOW, MACD_SIGNAL, RSI_PERIOD, MA_PERIODS
from scripts.fetch_stocks import calc_macd, calc_rsi, calc_ma

COINGECKO_API = "https://api.coingecko.com/api/v3"

# ETF 流动数据映射：CoinGecko ID → Farside slug
ETF_FLOW_SYMBOLS = {
    "bitcoin": "btc",
    "solana": "sol",
    "hyperliquid": "hyp",
}


def _fetch_etf_flows():
    """获取 BTC/ETH 现货 ETF 流入/流出数据（来源：Farside WordPress API + 解析）"""
    import re as _re
    etf_data = {}
    for cg_id, fs_slug in ETF_FLOW_SYMBOLS.items():
        try:
            # 使用 WordPress REST API 获取页面内容
            wp_url = f"https://farside.co.uk/wp-json/wp/v2/pages?slug={fs_slug}"
            resp = requests.get(wp_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }, timeout=15)
            if resp.status_code != 200:
                continue
            pages = resp.json()
            if not pages:
                continue
            content = pages[0].get("content", {}).get("rendered", "")

            # 提取所有表格行
            rows = _re.findall(r"<tr[^>]*>(.*?)</tr>", content, _re.DOTALL)

            # 取最后一行的 Total 行（累积总流动）
            total_cells = None
            for row in reversed(rows):
                if "otal" in row and "<td" in row:
                    cells = _re.findall(r"<td[^>]*>(.*?)</td>", row, _re.DOTALL)
                    clean = [_re.sub(r"<[^>]+>", "", c).strip().replace(",", "").replace("$", "") for c in cells]
                    # 第一个是 'Total' 标签，用最后一列作为累计净流动
                    total_cells = [c for c in clean if c and c != "Total"]
                    break

            # 提取最新一天的数据行（Total 行之前的那行）
            daily_cells = None
            rows_before_total = 0
            for row in reversed(rows):
                if "otal" in row:
                    continue
                if rows_before_total == 0 and "<td" in row:
                    cells = _re.findall(r"<td[^>]*>(.*?)</td>", row, _re.DOTALL)
                    clean = [_re.sub(r"<[^>]+>", "", c).strip().replace(",", "").replace("$", "") for c in cells]
                    daily_cells = [c for c in clean if c]
                    break

            # 从每日数据行计算净流动
            daily_net = None
            if daily_cells and len(daily_cells) >= 2:
                # 尝试将每个值转为数字并求和（排除日期列）
                nums = []
                for val in daily_cells[1:]:  # 跳过日期/第一列
                    try:
                        val_clean = val.replace("(", "-").replace(")", "")
                        nums.append(float(val_clean))
                    except ValueError:
                        pass
                if nums:
                    daily_net = round(sum(nums) / 100, 2)  # 百万美元 → 亿美元

            if daily_net is not None:
                etf_data[cg_id] = {
                    "etf_net_flow": daily_net,
                    "etf_inflow": round(daily_net, 2) if daily_net > 0 else None,
                    "etf_outflow": round(abs(daily_net), 2) if daily_net < 0 else None,
                }
        except Exception:
            pass
    return etf_data


def fetch_crypto_data():
    """获取加密货币数据"""
    if not CRYPTO:
        print("[加密货币] 未配置加密货币标的，跳过")
        return []

    print(f"[加密货币] 开始获取 {len(CRYPTO)} 个币种数据...")
    results = []

    # 获取 ETF 流动数据
    etf_flows = _fetch_etf_flows()
    if etf_flows:
        print(f"  📊 ETF 流动数据: {len(etf_flows)} 个币种")

    # CoinGecko 免费API限速：每分钟10-30次
    ids = ",".join([c["id"] for c in CRYPTO])

    try:
        # 批量获取行情
        url = f"{COINGECKO_API}/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": ids,
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        market_data = resp.json()

        if not market_data:
            print("    ⚠ CoinGecko 返回空数据")
            return []

        # 建立 id → 数据 映射
        market_map = {item["id"]: item for item in market_data}

        for crypto in CRYPTO:
            cid = crypto["id"]
            name = crypto["name"]
            symbol = crypto["symbol"]
            print(f"  → 正在处理 {name}({symbol})...")

            try:
                item = market_map.get(cid)
                if not item:
                    print(f"    ⚠ {name} 未找到行情数据，跳过")
                    continue

                current_price = item.get("current_price", 0)
                change_pct = round(item.get("price_change_percentage_24h", 0), 2)
                market_cap = item.get("market_cap", 0)
                total_volume = item.get("total_volume", 0)
                high_24h = item.get("high_24h", None)
                low_24h = item.get("low_24h", None)
                circulating_supply = item.get("circulating_supply", None)
                total_supply = item.get("total_supply", None)
                market_cap_rank = item.get("market_cap_rank", None)

                # 获取历史K线数据（用于计算技术指标）
                try:
                    time.sleep(1.5)  # 尊重API限速
                    hist_url = f"{COINGECKO_API}/coins/{cid}/market_chart"
                    hist_params = {
                        "vs_currency": "usd",
                        "days": "180",
                    }
                    hist_resp = requests.get(hist_url, params=hist_params, timeout=30)
                    if hist_resp.status_code == 200:
                        hist_data = hist_resp.json()
                        prices = hist_data.get("prices", [])
                        if prices:
                            close_prices = pd.Series([p[1] for p in prices])
                            macd_data = calc_macd(close_prices)
                            rsi = calc_rsi(close_prices)
                            ma_data = calc_ma(close_prices)
                        else:
                            macd_data = {"macd": None, "signal": None, "histogram": None}
                            rsi = None
                            ma_data = {}
                    else:
                        macd_data = {"macd": None, "signal": None, "histogram": None}
                        rsi = None
                        ma_data = {}
                except Exception:
                    macd_data = {"macd": None, "signal": None, "histogram": None}
                    rsi = None
                    ma_data = {}

                # 获取链上数据（大额转账、交易所余额等） - Whale Alert API
                onchain_data = {}
                try:
                    # 使用 CoinGecko 的开发者数据作为链上指标
                    dev_url = f"{COINGECKO_API}/coins/{cid}"
                    dev_params = {
                        "localization": "false",
                        "tickers": "false",
                        "community_data": "false",
                        "developer_data": "true",
                    }
                    time.sleep(1.5)
                    dev_resp = requests.get(dev_url, params=dev_params, timeout=30)
                    if dev_resp.status_code == 200:
                        coin_info = dev_resp.json()
                        market_data_detail = coin_info.get("market_data", {})
                        dev_data = coin_info.get("developer_data", {})

                        # 价格变动
                        onchain_data["price_change_7d"] = market_data_detail.get("price_change_percentage_7d")
                        onchain_data["price_change_30d"] = market_data_detail.get("price_change_percentage_30d")

                        # 市值占比
                        mcap_data = market_data_detail.get("market_cap", {})
                        onchain_data["market_cap_change_24h"] = round(mcap_data.get("market_cap_change_percentage_24h", 0), 2) if mcap_data else None

                        # 开发者活跃度（可作为基本面参考）
                        onchain_data["github_commits_4w"] = dev_data.get("commit_count_4_weeks")

                        # 流通/总量占比
                        if circulating_supply and total_supply and total_supply > 0:
                            onchain_data["circ_ratio"] = round((circulating_supply / total_supply) * 100, 2)

                        # 类别/赛道
                        categories = coin_info.get("categories", [])
                        onchain_data["categories"] = categories[:3] if categories else []

                        # ATH 距离
                        ath = market_data_detail.get("ath", {})
                        ath_price = ath.get("usd", None)
                        if ath_price and current_price:
                            onchain_data["ath_pct"] = round(((current_price - ath_price) / ath_price) * 100, 2)
                            onchain_data["ath_date"] = ath.get("usd_date", "")[:10] if ath.get("usd_date") else None

                except Exception:
                    onchain_data = {}

                # ETF 流动数据
                etf = etf_flows.get(cid, {})
                crypto_data = {
                    "market": "加密货币",
                    "code": cid,
                    "name": name,
                    "symbol": symbol.upper(),
                    "industry": onchain_data.get("categories", [])[0] if onchain_data.get("categories") else None,
                    "price": round(current_price, 4),
                    "open": None,
                    "high": round(high_24h, 4) if high_24h else None,
                    "low": round(low_24h, 4) if low_24h else None,
                    "change_pct": change_pct,
                    "volume": round(total_volume, 2) if total_volume else None,
                    "turnover": None,
                    "market_cap": round(market_cap / 1e8, 2) if market_cap else None,  # 转为亿美元
                    "market_cap_rank": market_cap_rank,
                    "pe": None,  # 加密货币无PE
                    "etf_inflow": etf.get("etf_inflow"),
                    "etf_outflow": etf.get("etf_outflow"),
                    "etf_net_flow": etf.get("etf_net_flow"),
                    "macd": macd_data.get("macd"),
                    "macd_signal": macd_data.get("signal"),
                    "macd_histogram": macd_data.get("histogram"),
                    "rsi": rsi,
                    "ma": ma_data,
                    "main_net_flow": None,
                    "onchain": {
                        "circulating_supply": circulating_supply,
                        "total_supply": total_supply,
                        "circ_ratio": onchain_data.get("circ_ratio"),
                        "price_change_7d": onchain_data.get("price_change_7d"),
                        "price_change_30d": onchain_data.get("price_change_30d"),
                        "ath_pct": onchain_data.get("ath_pct"),
                        "ath_date": onchain_data.get("ath_date"),
                        "categories": onchain_data.get("categories", []),
                        "github_commits_4w": onchain_data.get("github_commits_4w"),
                    },
                }
                results.append(crypto_data)
                print(f"    ✓ {name}: ${crypto_data['price']}, {change_pct:+.2f}%")

            except Exception as e:
                print(f"    ✗ {name}({symbol}) 数据获取失败: {str(e)[:100]}")
                continue

    except Exception as e:
        print(f"[加密货币] CoinGecko API 请求失败: {str(e)[:100]}")

    print(f"[加密货币] 完成，成功获取 {len(results)}/{len(CRYPTO)} 个币种数据")
    return results


if __name__ == "__main__":
    data = fetch_crypto_data()
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
