"""
加密货币数据抓取模块
数据源：CoinGecko + Binance + Farside + Blockchain.com
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys
import time
import re
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import CRYPTO, MACD_FAST, MACD_SLOW, MACD_SIGNAL, RSI_PERIOD, MA_PERIODS
from scripts.fetch_stocks import calc_macd, calc_rsi, calc_ma

COINGECKO_API = "https://api.coingecko.com/api/v3"
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"

# ETF 流动数据映射：CoinGecko ID → Farside slug
ETF_FLOW_SYMBOLS = {
    "bitcoin": "btc",
    "ethereum": "eth",
}

# 资金费率映射：CoinGecko ID → Binance 永续合约 symbol
FUNDING_RATE_SYMBOLS = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
}


def _fetch_etf_flows():
    """获取 BTC/ETH 现货 ETF 净流入/流出（来源：Farside）"""
    import re as _re
    etf_data = {}

    for cg_id, fs_slug in ETF_FLOW_SYMBOLS.items():
        try:
            # 方法1：尝试 Farside 的简单 HTML 页面
            url = f"https://farside.co.uk/{fs_slug}/"
            resp = requests.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,*/*",
            }, timeout=15)
            if resp.status_code != 200:
                # 方法2：WP REST API
                wp_url = f"https://farside.co.uk/wp-json/wp/v2/pages?slug={fs_slug}"
                resp = requests.get(wp_url, headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                }, timeout=15)
                if resp.status_code != 200:
                    continue
                pages = resp.json()
                if not pages:
                    continue
                content = pages[0].get("content", {}).get("rendered", "")
            else:
                content = resp.text

            # 从 HTML 中提取表格数据
            # 找到 Total 行（累积总流动）
            total_match = _re.search(
                r'<tr[^>]*>.*?<td[^>]*>\s*Total\s*</td>((?:<td[^>]*>.*?</td>)*)',
                content, _re.DOTALL | _re.IGNORECASE
            )
            if not total_match:
                # 尝试找 "Total" 或 "Cumulative"
                total_match = _re.search(
                    r'<tr[^>]*>.*?(?:Total|Cumulative).*?</tr>',
                    content, _re.DOTALL | _re.IGNORECASE
                )

            # 更简单的办法：找所有包含数字的 td
            # 提取所有数值（可能带 $ 和括号）
            all_numbers = _re.findall(r'\$?\(?([\d,]+(?:\.\d+)?)\)?', content)

            # 找最近一天的数据行（通常包含日期格式）
            date_rows = _re.findall(
                r'<tr[^>]*>.*?(\d{1,2}-[A-Za-z]{3}-\d{2,4}).*?</tr>',
                content, _re.DOTALL
            )

            # 最稳健做法：找 table 中最后一行的数值
            tables = _re.findall(r'<table[^>]*>(.*?)</table>', content, _re.DOTALL)
            daily_net = None

            for table_html in tables:
                rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, _re.DOTALL)
                # 从倒数第二行找日数据（最后一行通常是 Total）
                search_rows = rows[-3:] if len(rows) >= 3 else rows

                for row_html in search_rows:
                    # 跳过标题行和 Total 行
                    if '<th' in row_html or 'otal' in row_html or 'OTAL' in row_html:
                        continue
                    cells = _re.findall(r'<td[^>]*>(.*?)</td>', row_html, _re.DOTALL)
                    clean_cells = []
                    for c in cells:
                        c = _re.sub(r'<[^>]+>', '', c).strip()
                        c = c.replace('$', '').replace(',', '').replace(' ', '')
                        clean_cells.append(c)

                    # 第一个cell是日期，后面的都是数值
                    if len(clean_cells) >= 2:
                        nums = []
                        for val in clean_cells[1:]:
                            # 处理负数括号格式：(123) = -123
                            if val.startswith('(') and val.endswith(')'):
                                val = '-' + val[1:-1]
                            try:
                                nums.append(float(val))
                            except ValueError:
                                pass
                        if nums:
                            daily_net = round(sum(nums), 1)  # 单位：百万美元

            if daily_net is not None:
                # 转为亿美元
                net_billion = round(daily_net / 100, 2)
                etf_data[cg_id] = {
                    "etf_net_flow": net_billion,
                    "etf_inflow": round(net_billion, 2) if net_billion > 0 else None,
                    "etf_outflow": round(abs(net_billion), 2) if net_billion < 0 else None,
                }
                print(f"    📊 {fs_slug.upper()} ETF 净流动: {net_billion:+.2f}亿$")
        except Exception as e:
            print(f"    ⚠ ETF {fs_slug} 数据获取失败: {str(e)[:60]}")

    return etf_data


def _fetch_funding_rates():
    """获取永续合约资金费率 + OI（多源：Bybit → OKX → CoinGecko）"""
    funding_data = {}
    for cg_id, symbol in FUNDING_RATE_SYMBOLS.items():
        rate = None
        oi_value = None

        # === 来源1: Bybit API（免费，通常可从US访问）===
        try:
            url = "https://api.bybit.com/v5/market/tickers"
            resp = requests.get(url, params={"category": "linear", "symbol": symbol}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                tickers = data.get("result", {}).get("list", [])
                if tickers:
                    t = tickers[0]
                    rate = float(t.get("fundingRate", 0)) * 100
                    oi_raw = float(t.get("openInterest", 0))
                    oi_value = round(oi_raw, 2)
                    print(f"    💰 [Bybit] {symbol} 资金费率: {rate:.4f}%, OI: {oi_value}")
        except Exception as e:
            pass

        # === 来源2: OKX API ===
        if rate is None:
            try:
                okx_inst = symbol.replace("USDT", "-USDT-SWAP")
                url = "https://www.okx.com/api/v5/market/ticker"
                resp = requests.get(url, params={"instId": okx_inst}, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    t = (data.get("data") or [{}])[0]
                    rate_raw = t.get("fundingRate")
                    oi_raw = t.get("openInterest")
                    if rate_raw:
                        rate = float(rate_raw) * 100
                    if oi_raw:
                        oi_value = round(float(oi_raw), 2)
                    if rate is not None:
                        print(f"    💰 [OKX] {symbol} 资金费率: {rate:.4f}%, OI: {oi_value}")
            except Exception as e:
                pass

        # === 来源3: CoinGecko 衍生品数据 ===
        if rate is None:
            try:
                cg_id_map = {"bitcoin": "bitcoin", "ethereum": "ethereum"}
                cg_name = cg_id_map.get(cg_id, cg_id)
                url = f"{COINGECKO_API}/coins/{cg_name}/tickers"
                resp = requests.get(url, params={"exchange_ids": "binance_futures"}, timeout=15)
                if resp.status_code == 200:
                    tickers_data = resp.json().get("tickers", [])
                    for t in tickers_data:
                        if "PERP" in (t.get("market", {}).get("identifier", "")) or "USDT" in t.get("base", ""):
                            # CoinGecko doesn't directly provide funding rate in tickers
                            pass
            except Exception:
                pass

        if rate is not None:
            funding_data[cg_id] = round(rate, 4)
        if oi_value is not None:
            funding_data[cg_id + "_oi"] = oi_value
        else:
            # OI 从 CoinGecko 获取（合约未平仓量，但这是期货OI，不是永续）
            pass

    return funding_data


def _fetch_onchain_btc():
    """获取BTC链上数据（来源：Blockchain.com API，免费）"""
    onchain = {}
    try:
        # 哈希率
        resp = requests.get("https://api.blockchain.info/charts/hash-rate?timespan=1day&format=json", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            pts = data.get("values", [])
            if pts:
                onchain["hash_rate"] = round(pts[-1]["y"], 2)  # TH/s

        # 活跃地址数
        resp = requests.get("https://api.blockchain.info/charts/n-unique-addresses?timespan=1day&format=json", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            pts = data.get("values", [])
            if pts:
                onchain["active_addresses"] = int(pts[-1]["y"])

        # 交易手续费（均值，USD）
        resp = requests.get("https://api.blockchain.info/charts/transaction-fees-usd?timespan=1day&format=json", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            pts = data.get("values", [])
            if pts:
                onchain["tx_fee_usd"] = round(pts[-1]["y"], 2)
    except Exception as e:
        print(f"    ⚠ BTC链上数据获取失败: {str(e)[:60]}")

    return onchain


def _fetch_onchain_eth():
    """获取ETH链上数据"""
    onchain = {}
    try:
        # Gas 价格（从 Etherscan 公开 API 估算）
        resp = requests.get(
            "https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey=YourApiKeyToken",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "1":
                result = data.get("result", {})
                onchain["gas_gwei"] = result.get("ProposeGasPrice") or result.get("SafeGasPrice")

        # 使用 Beaconcha.in API 获取ETH质押数据
        resp = requests.get(
            "https://beaconcha.in/api/v1/ethstore/latest",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "OK":
                ethstore = data.get("data", {})
                onchain["staking_apr"] = ethstore.get("apr")  # 质押年化收益率
                onchain["validators"] = ethstore.get("validatorscount")  # 验证者数量
    except Exception as e:
        print(f"    ⚠ ETH链上数据获取失败: {str(e)[:60]}")

    return onchain


def fetch_crypto_data():
    """获取加密货币数据"""
    if not CRYPTO:
        print("[加密货币] 未配置加密货币标的，跳过")
        return []

    print(f"[加密货币] 开始获取 {len(CRYPTO)} 个币种数据...")

    # 并行获取各类数据
    etf_flows = _fetch_etf_flows()
    if etf_flows:
        print(f"  📊 ETF 流动: {len(etf_flows)} 个币种")

    funding_rates = _fetch_funding_rates()
    if funding_rates:
        print(f"  💰 资金费率+OI: {len([k for k in funding_rates if not k.endswith('_oi')])} 个币种")

    btc_onchain = _fetch_onchain_btc()
    if btc_onchain:
        print(f"  ⛓️ BTC链上: 哈希率={btc_onchain.get('hash_rate', '?')}TH/s, 活跃地址={btc_onchain.get('active_addresses', '?')}")

    eth_onchain = _fetch_onchain_eth()
    if eth_onchain:
        print(f"  ⛓️ ETH链上: Gas={eth_onchain.get('gas_gwei', '?')}gwei, 质押APR={eth_onchain.get('staking_apr', '?')}%")

    results = []
    ids = ",".join([c["id"] for c in CRYPTO])

    try:
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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

                # 历史K线 → 技术指标
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

                # CoinGecko 详情（7d/30d/ATH/赛道等）
                onchain_data = {}
                try:
                    time.sleep(1.5)
                    dev_url = f"{COINGECKO_API}/coins/{cid}"
                    dev_params = {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "true"}
                    dev_resp = requests.get(dev_url, params=dev_params, timeout=30, headers=headers)
                    if dev_resp.status_code == 200:
                        coin_info = dev_resp.json()
                        mkt = coin_info.get("market_data", {})
                        onchain_data["price_change_7d"] = mkt.get("price_change_percentage_7d")
                        onchain_data["price_change_30d"] = mkt.get("price_change_percentage_30d")
                        onchain_data["categories"] = coin_info.get("categories", [])[:3]
                        ath = mkt.get("ath", {})
                        ath_price = ath.get("usd")
                        if ath_price and current_price:
                            onchain_data["ath_pct"] = round(((current_price - ath_price) / ath_price) * 100, 2)
                            onchain_data["ath_date"] = ath.get("usd_date", "")[:10] if ath.get("usd_date") else None
                        if circulating_supply and total_supply and total_supply > 0:
                            onchain_data["circ_ratio"] = round((circulating_supply / total_supply) * 100, 2)
                except Exception:
                    pass

                # === 汇总链上数据 ===
                # BTC特有
                if cid == "bitcoin":
                    onchain_data.update(btc_onchain)
                # ETH特有
                elif cid == "ethereum":
                    onchain_data.update(eth_onchain)

                # ETF 数据
                etf = etf_flows.get(cid, {})

                # 资金费率
                funding_rate = funding_rates.get(cid)
                open_interest = funding_rates.get(cid + "_oi")

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
                    # 新增指标
                    "funding_rate": funding_rate,          # 资金费率 (%)
                    "open_interest": open_interest,         # 持仓量 (币本位)
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
                        # BTC链上
                        "hash_rate": onchain_data.get("hash_rate"),
                        "active_addresses": onchain_data.get("active_addresses"),
                        "tx_fee_usd": onchain_data.get("tx_fee_usd"),
                        # ETH链上
                        "gas_gwei": onchain_data.get("gas_gwei"),
                        "staking_apr": onchain_data.get("staking_apr"),
                        "validators": onchain_data.get("validators"),
                    },
                }
                results.append(crypto_data)
                extra = []
                if funding_rate is not None:
                    extra.append(f"费率={funding_rate:.4f}%")
                if etf.get("etf_net_flow") is not None:
                    extra.append(f"ETF={etf['etf_net_flow']:+.2f}亿")
                extra_str = ", ".join(extra)
                print(f"    ✓ {name}: ${crypto_data['price']}, {change_pct:+.2f}%{' | ' + extra_str if extra_str else ''}")

            except Exception as e:
                print(f"    ✗ {name}({symbol}) 数据获取失败: {str(e)[:100]}")
                continue

    except Exception as e:
        print(f"[加密货币] CoinGecko API 请求失败: {str(e)[:100]}")
        market_data = _fetch_crypto_fallback()
        if market_data:
            for crypto in CRYPTO:
                cid = crypto["id"]
                for item in market_data:
                    if item.get("id") == cid:
                        name = crypto["name"]
                        symbol = crypto["symbol"]
                        etf = etf_flows.get(cid, {})
                        funding_rate = funding_rates.get(cid)
                        onchain_data = {}
                        if cid == "bitcoin":
                            onchain_data.update(btc_onchain)
                        elif cid == "ethereum":
                            onchain_data.update(eth_onchain)
                        results.append({
                            "market": "加密货币",
                            "code": cid,
                            "name": name,
                            "symbol": symbol.upper(),
                            "industry": None,
                            "price": round(item.get("current_price", 0), 4),
                            "open": None, "high": None, "low": None,
                            "change_pct": round(item.get("price_change_percentage_24h", 0), 2),
                            "volume": round(item.get("total_volume", 0), 2),
                            "turnover": None,
                            "market_cap": round(item.get("market_cap", 0) / 1e8, 2),
                            "market_cap_rank": item.get("market_cap_rank"),
                            "pe": None,
                            "funding_rate": funding_rate,
                            "open_interest": funding_rates.get(cid + "_oi"),
                            "etf_inflow": etf.get("etf_inflow"),
                            "etf_outflow": etf.get("etf_outflow"),
                            "etf_net_flow": etf.get("etf_net_flow"),
                            "macd": None, "macd_signal": None, "macd_histogram": None,
                            "rsi": None, "ma": {},
                            "main_net_flow": None,
                            "onchain": {
                                "hash_rate": onchain_data.get("hash_rate"),
                                "active_addresses": onchain_data.get("active_addresses"),
                                "gas_gwei": onchain_data.get("gas_gwei"),
                                "staking_apr": onchain_data.get("staking_apr"),
                                "categories": [],
                                "price_change_7d": None, "price_change_30d": None,
                                "ath_pct": None, "ath_date": None,
                                "circ_ratio": None,
                            },
                        })
                        print(f"    ✓ {name}({symbol}): ${item.get('current_price', 0)} (备用源)")
                        break

    print(f"[加密货币] 完成，成功获取 {len(results)}/{len(CRYPTO)} 个币种数据")
    return results


def _fetch_crypto_fallback():
    """备用数据源：CoinGecko simple API"""
    try:
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
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        resp = requests.get(url, params=params, timeout=30, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
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
