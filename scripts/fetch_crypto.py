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

    ids = ",".join([c["id"] for c in CRYPTO])

    try:
        # 尝试 CoinGecko 免费 API
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
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        resp = requests.get(url, params=params, timeout=30, headers=headers)
        resp.raise_for_status()
        market_data = resp.json()

        if not market_data:
            print("    ⚠ CoinGecko 返回空数据，尝试备用API...")
            market_data = _fetch_crypto_fallback()

        if not market_data:
            print("[加密货币] 所有数据源均失败")
            return []

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

                # 获取历史K线数据
                macd_data = {"macd": None, "signal": None, "histogram": None}
                rsi = None
                ma_data = {}

                try:
                    time.sleep(1.5)
                    hist_url = f"{COINGECKO_API}/coins/{cid}/market_chart"
                    hist_params = {"vs_currency": "usd", "days": "180"}
                    hist_resp = requests.get(hist_url, params=hist_params, timeout=30, headers=headers)
                    if hist_resp.status_code == 200:
                        hist_data = hist_resp.json()
                        prices = hist_data.get("prices", [])
                        if prices:
                            close_prices = pd.Series([p[1] for p in prices])
                            macd_data = calc_macd(close_prices)
                            rsi = calc_rsi(close_prices)
                            ma_data = calc_ma(close_prices)
                except Exception:
                    pass

                # 链上数据（简化版）
                onchain_data = {}
                try:
                    time.sleep(1.5)
                    dev_url = f"{COINGECKO_API}/coins/{cid}"
                    dev_params = {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "true"}
                    dev_resp = requests.get(dev_url, params=dev_params, timeout=30, headers=headers)
                    if dev_resp.status_code == 200:
                        coin_info = dev_resp.json()
                        mkt = coin_info.get("market_data", {})
                        dev = coin_info.get("developer_data", {})
                        onchain_data["price_change_7d"] = mkt.get("price_change_percentage_7d")
                        onchain_data["price_change_30d"] = mkt.get("price_change_percentage_30d")
                        onchain_data["categories"] = coin_info.get("categories", [])[:3]
                        ath = mkt.get("ath", {})
                        ath_price = ath.get("usd")
                        if ath_price and current_price:
                            onchain_data["ath_pct"] = round(((current_price - ath_price) / ath_price) * 100, 2)
                            onchain_data["ath_date"] = ath.get("usd_date", "")[:10]
                        if circulating_supply and total_supply and total_supply > 0:
                            onchain_data["circ_ratio"] = round((circulating_supply / total_supply) * 100, 2)
                        onchain_data["github_commits_4w"] = dev.get("commit_count_4_weeks")
                except Exception:
                    pass

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
                    "market_cap": round(market_cap / 1e8, 2) if market_cap else None,
                    "market_cap_rank": market_cap_rank,
                    "pe": None,
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
        # 尝试备用数据源
        market_data = _fetch_crypto_fallback()
        if market_data:
            # 简单处理备用数据
            for crypto in CRYPTO:
                cid = crypto["id"]
                for item in market_data:
                    if item.get("id") == cid:
                        name = crypto["name"]
                        symbol = crypto["symbol"]
                        etf = etf_flows.get(cid, {})
                        results.append({
                            "market": "加密货币",
                            "code": cid,
                            "name": name,
                            "symbol": symbol.upper(),
                            "industry": None,
                            "price": round(item.get("current_price", 0), 4),
                            "open": None,
                            "high": None,
                            "low": None,
                            "change_pct": round(item.get("price_change_percentage_24h", 0), 2),
                            "volume": round(item.get("total_volume", 0), 2),
                            "turnover": None,
                            "market_cap": round(item.get("market_cap", 0) / 1e8, 2),
                            "market_cap_rank": item.get("market_cap_rank"),
                            "pe": None,
                            "etf_inflow": etf.get("etf_inflow"),
                            "etf_outflow": etf.get("etf_outflow"),
                            "etf_net_flow": etf.get("etf_net_flow"),
                            "macd": None, "macd_signal": None, "macd_histogram": None,
                            "rsi": None, "ma": {},
                            "main_net_flow": None,
                            "onchain": {},
                        })
                        print(f"    ✓ {name}({symbol}): ${item.get('current_price', 0)} (备用源)")
                        break

    print(f"[加密货币] 完成，成功获取 {len(results)}/{len(CRYPTO)} 个币种数据")
    return results


def _fetch_crypto_fallback():
    """备用数据源：使用 CoinGecko 的公共免费 API（无需 key）"""
    try:
        # 使用 CoinGecko 的简易 API 端点
        ids = ",".join([c["id"] for c in CRYPTO])
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
            "include_market_cap_rank": "true",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        resp = requests.get(url, params=params, timeout=30, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            # 转换为 coins/markets 格式
            result = []
            for cid, vals in data.items():
                result.append({
                    "id": cid,
                    "current_price": vals.get("usd"),
                    "market_cap": vals.get("usd_market_cap"),
                    "total_volume": vals.get("usd_24h_vol"),
                    "price_change_percentage_24h": vals.get("usd_24h_change"),
                    "market_cap_rank": vals.get("usd_market_cap_rank"),
                })
            if result:
                print(f"    📡 备用API成功获取 {len(result)} 个币种")
                return result
    except Exception as e:
        print(f"    ⚠ 备用API也失败了: {str(e)[:80]}")
    return None


if __name__ == "__main__":
    data = fetch_crypto_data()
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
