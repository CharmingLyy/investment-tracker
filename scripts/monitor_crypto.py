"""
加密货币短线交易信号监控
每 10 分钟自动检测 BTC/ETH，有交易机会时邮件通知

数据源: Binance 公开 API（无需 API Key）
信号逻辑: 完整移植自 ai选股/index.html 的 generateSignal()

使用方式:
  python scripts/monitor_crypto.py           # 单次检测
  python scripts/monitor_crypto.py --loop    # 持续监控模式（每 10 分钟）
  python scripts/monitor_crypto.py --once    # 单次检测（默认）

环境变量:
  AI_MONITOR_EMAIL_FROM     发件人 QQ 邮箱
  AI_MONITOR_EMAIL_PASSWORD  QQ 邮箱 SMTP 授权码
  AI_MONITOR_EMAIL_TO       收件人邮箱
  AI_MONITOR_INTERVAL       检测间隔秒数（默认 600）
"""
import sys
import io
import os
import json
import time
import argparse
from datetime import datetime, timedelta

# 强制 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import warnings
warnings.filterwarnings('ignore')

# 项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


# ============================================================
# 技术指标函数（纯 Python，与 JS / backtest_crypto.py 完全一致）
# ============================================================

def SMA(data, period):
    result = []
    for i in range(len(data)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(data[i - period + 1:i + 1]) / period)
    return result


def EMA(data, period):
    if len(data) == 0:
        return []
    result = [data[0]]
    k = 2 / (period + 1)
    for i in range(1, len(data)):
        result.append(data[i] * k + result[i - 1] * (1 - k))
    return result


def RSI(closes, period=14):
    if len(closes) < period + 1:
        return [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(d if d > 0 else 0)
        losses.append(-d if d < 0 else 0)
    result = [None] * (period + 1)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        if avg_loss == 0:
            result.append(100.0)
        else:
            result.append(100 - 100 / (1 + avg_gain / avg_loss))
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    return result


def MACD(closes, fast=12, slow=26, signal=9):
    ef = EMA(closes, fast)
    es = EMA(closes, slow)
    macd_line = [ef[i] - es[i] if ef[i] is not None and es[i] is not None else None for i in range(len(closes))]
    valid = [v for v in macd_line if v is not None]
    if not valid:
        return {"macdLine": macd_line, "signalLine": [None] * len(closes), "histogram": [None] * len(closes)}
    sig_ema = EMA(valid, signal)
    signal_line, si = [], 0
    for v in macd_line:
        if v is not None:
            signal_line.append(sig_ema[si]); si += 1
        else:
            signal_line.append(None)
    hist = [macd_line[i] - signal_line[i] if macd_line[i] is not None and signal_line[i] is not None else None for i in range(len(closes))]
    return {"macdLine": macd_line, "signalLine": signal_line, "histogram": hist}


def BB(closes, period=20, std_mult=2):
    middle = SMA(closes, period)
    upper, lower = [], []
    for i in range(len(closes)):
        if middle[i] is None:
            upper.append(None); lower.append(None)
        else:
            w = closes[i - period + 1:i + 1]
            std = (sum((x - middle[i]) ** 2 for x in w) / period) ** 0.5
            upper.append(middle[i] + std_mult * std)
            lower.append(middle[i] - std_mult * std)
    return {"middle": middle, "upper": upper, "lower": lower}


def ATR(highs, lows, closes, period=14):
    tr = []
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    result = [None] * (period + 1)
    if len(tr) < period:
        return result
    avg = sum(tr[:period]) / period
    result.append(avg)
    for i in range(period, len(tr)):
        avg = (avg * (period - 1) + tr[i]) / period
        result.append(avg)
    return result


# ============================================================
# 支撑 / 阻力检测（完整移植自 JS findSRLines）
# ============================================================

def find_sr_lines(closes, highs, lows, n=5):
    """检测支撑位和阻力位"""
    lookback = 5
    swings_high, swings_low = [], []

    for i in range(lookback, len(closes) - lookback):
        is_high, is_low = True, True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if highs[j] >= highs[i]:
                is_high = False
            if lows[j] <= lows[i]:
                is_low = False
        if is_high:
            swings_high.append(highs[i])
        if is_low:
            swings_low.append(lows[i])

    def cluster(arr, threshold=0.01):
        if not arr:
            return []
        sorted_arr = sorted(arr)
        clusters, cur = [], [sorted_arr[0]]
        for i in range(1, len(sorted_arr)):
            if abs(sorted_arr[i] - cur[-1]) / cur[-1] < threshold:
                cur.append(sorted_arr[i])
            else:
                clusters.append(sum(cur) / len(cur))
                cur = [sorted_arr[i]]
        clusters.append(sum(cur) / len(cur))
        return clusters

    price = closes[-1]
    supports = cluster([v for v in swings_low if v < price], 0.01)
    supports.sort(reverse=True)
    supports = supports[:n]
    resistances = cluster([v for v in swings_high if v > price], 0.01)
    resistances.sort()
    resistances = resistances[:n]

    # 添加 EMA 动态支撑/阻力
    ema50 = EMA(closes, 50)
    e50 = ema50[-1]
    if e50 < price:
        supports.append(e50)
    else:
        resistances.append(e50)

    if len(closes) >= 200:
        ema200 = EMA(closes, 200)
        e200 = ema200[-1]
        if e200 < price:
            supports.append(e200)
        else:
            resistances.append(e200)

    # 整数关口
    magnitude = 10 ** (len(str(int(price))) - 1)
    for m in range(-3, 4):
        level = round(price / magnitude) * magnitude + m * magnitude
        if level < price * 0.995:
            supports.append(level)
        if level > price * 1.005:
            resistances.append(level)

    supports = sorted(list(set(round(s, 2) for s in supports)), reverse=True)[:n]
    resistances = sorted(list(set(round(r, 2) for r in resistances)))[:n]
    return {"supports": supports, "resistances": resistances}


# ============================================================
# 信号生成引擎（完整移植自 JS generateSignal）
# ============================================================

def generate_signal(data_1h, data_4h, data_1d, asset="BTC", futures_info=None):
    """
    完整移植自 ai选股/index.html 的 generateSignal()

    参数：
      data_1h, data_4h, data_1d: {"closes":[], "highs":[], "lows":[]}
      asset: "BTC" 或 "ETH" — 不同资产使用不同参数
      futures_info: dict — fetch_futures_data() 的返回值（资金费率 + 持仓量），可选

    返回: dict — 完整的信号对象

    ETH 专属参数 (2026-07-20 回测优化):
      - 止损 1.5×ATR (vs BTC 2.0×) — ETH 波动更大，紧止损控风险
      - 止盈 4.0×ATR (vs BTC 5.0×) — 匹配 ETH 更快的反转速度
      - 回测 1000 天: ETH +55.58% (1000天), 胜率 42.4%, PF 1.16
    """
    c1, h1, l1 = data_1h["closes"], data_1h["highs"], data_1h["lows"]
    c4, h4, l4 = data_4h["closes"], data_4h["highs"], data_4h["lows"]
    cd = data_1d["closes"]
    cur_price = c1[-1]

    # ── 1H 指标 ──
    rsi1h = RSI(c1, 14); cur_rsi1h = rsi1h[-1]
    macd1h = MACD(c1)
    cm1 = macd1h["macdLine"][-1]; cs1 = macd1h["signalLine"][-1]
    pm1 = macd1h["macdLine"][-2]; ps1 = macd1h["signalLine"][-2]
    ema9_1h = EMA(c1, 9); ema21_1h = EMA(c1, 21); ema50_1h = EMA(c1, 50)
    ce9 = ema9_1h[-1]; ce21 = ema21_1h[-1]; ce50 = ema50_1h[-1]
    bb1h = BB(c1, 20, 2)
    bu = bb1h["upper"][-1]; bl = bb1h["lower"][-1]
    atr1h = ATR(h1, l1, c1, 14)
    cur_atr = atr1h[-1] if atr1h[-1] is not None else cur_price * 0.01

    # ── 4H 指标 ──
    rsi4h = RSI(c4, 14); cur_rsi4h = rsi4h[-1]
    macd4h = MACD(c4)
    cm4 = macd4h["macdLine"][-1]; cs4 = macd4h["signalLine"][-1]
    ema21_4h = EMA(c4, 21); ce21_4h = ema21_4h[-1]

    # ── 日线指标 ──
    ema21_d = EMA(cd, 21); ce21_d = ema21_d[-1] if len(ema21_d) > 0 else cur_price
    rsiD = RSI(cd, 14); cur_rsiD = rsiD[-1]

    # ── 支撑/阻力 ──
    sr = find_sr_lines(c1, h1, l1)
    nearest_support = sr["supports"][0] if sr["supports"] else cur_price * 0.97
    nearest_resistance = sr["resistances"][0] if sr["resistances"] else cur_price * 1.03
    next_support = sr["supports"][1] if len(sr["supports"]) > 1 else cur_price * 0.95
    next_resistance = sr["resistances"][1] if len(sr["resistances"]) > 1 else cur_price * 1.05

    # ── 趋势方向判定 ──
    # 1H 趋势
    if cur_price > ce21:
        trend1h = 2 if (cur_price > ce9 and ce9 > ce21) else 1
    else:
        trend1h = -2 if (cur_price < ce9 and ce9 < ce21) else -1
    # 4H 趋势
    trend4h = 1 if cur_price > ce21_4h else -1
    # 日线趋势
    trendD = 1 if cur_price > ce21_d else -1

    trend_score = trend1h + trend4h + trendD  # Range: -5 to +5
    if trend_score >= 3:
        direction = 'bullish'
    elif trend_score <= -3:
        direction = 'bearish'
    else:
        direction = 'neutral'

    # ── 技术评分 (60 pts) ──
    tech_score = 0

    # 趋势一致性 (20 pts)
    if direction == 'bullish':
        tech_score += 7 if trend1h > 0 else 2
        tech_score += 7 if trend4h > 0 else 2
        tech_score += 6 if trendD > 0 else 2
    elif direction == 'bearish':
        tech_score += 7 if trend1h < 0 else 2
        tech_score += 7 if trend4h < 0 else 2
        tech_score += 6 if trendD < 0 else 2
    else:
        tech_score += 3 + 3 + 3

    # 动量 (20 pts) — 基于 1H MACD
    if cm1 is not None and cs1 is not None:
        if direction == 'bullish':
            if pm1 <= ps1 and cm1 > cs1:  # 金叉
                tech_score += 10
            elif cm1 > cs1:
                tech_score += 7
            else:
                tech_score += 3
        elif direction == 'bearish':
            if pm1 >= ps1 and cm1 < cs1:  # 死叉
                tech_score += 10
            elif cm1 < cs1:
                tech_score += 7
            else:
                tech_score += 3
        else:
            tech_score += 5
    else:
        tech_score += 5

    # 4H MACD 确认
    if cm4 is not None and cs4 is not None:
        if (direction == 'bullish' and cm4 > cs4) or (direction == 'bearish' and cm4 < cs4):
            tech_score += 5
        elif direction == 'neutral':
            tech_score += 3
        else:
            tech_score += 1
    else:
        tech_score += 3

    # RSI 位置 (10 pts)
    if cur_rsi1h is not None:
        if direction == 'bullish' and 30 <= cur_rsi1h <= 55:
            tech_score += 10
        elif direction == 'bearish' and 45 <= cur_rsi1h <= 70:
            tech_score += 10
        elif 35 <= cur_rsi1h <= 65:
            tech_score += 6
        elif cur_rsi1h < 25 or cur_rsi1h > 75:
            tech_score += 2
        else:
            tech_score += 4
    else:
        tech_score += 5

    # 波动率 (10 pts)
    atr_pct = (cur_atr / cur_price) * 100
    if 0.5 < atr_pct < 3:
        tech_score += 10
    elif atr_pct < 6:
        tech_score += 6
    else:
        tech_score += 2

    # ── 基本面评分 (20 pts) ──
    # 数据来源：Binance 期货公开 API（资金费率 + 持仓量）
    # 这两个指标独立于价格 K 线，提供真正的增量信息
    fund_score = 10  # 默认中性（futures 数据不可用时使用）

    if futures_info:
        try:
            # ═══ 子项 ①：资金费率 (12 pts) ═══
            # 机制：正费率 = 多头付钱给空头（市场过热偏多）
            #       负费率 = 空头付钱给多头（市场恐慌偏空）
            # 用法：反向指标 — 极端费率是反转信号
            fr_pct = float(futures_info.get("funding_rate_pct", 0))
            fr_time = futures_info.get("funding_time", "?")

            if direction == 'bullish':
                if fr_pct < -0.01:       fund_score += 12  # 极度恐慌，反向做多绝佳
                elif fr_pct < 0:         fund_score += 10  # 略偏空，做多有优势
                elif fr_pct < 0.005:     fund_score += 8   # 中性偏负
                elif fr_pct < 0.01:      fund_score += 6   # 中性
                elif fr_pct < 0.03:      fund_score += 3   # 偏多拥挤
                else:                    fund_score += 1   # 极度拥挤，危险
            elif direction == 'bearish':
                if fr_pct > 0.03:        fund_score += 12  # 极度贪婪，反向做空绝佳
                elif fr_pct > 0.01:      fund_score += 10
                elif fr_pct > 0.005:     fund_score += 8
                elif fr_pct > 0:         fund_score += 6
                elif fr_pct > -0.01:     fund_score += 3
                else:                    fund_score += 1   # 极度恐慌，做空危险
            else:
                # neutral 方向：费率越极端越说明有机会（矛盾越大概率越大）
                if abs(fr_pct) > 0.03:   fund_score += 10
                elif abs(fr_pct) > 0.01: fund_score += 8
                elif abs(fr_pct) > 0.005: fund_score += 6
                else:                    fund_score += 4

            # ═══ 子项 ②：持仓量变化 (8 pts) ═══
            # OI 变化 = 市场参与度增减
            # 大变化 = 市场活跃 = 技术信号更可靠（无论方向）
            oi_chg = abs(float(futures_info.get("oi_change_pct", 0)))

            if oi_chg > 3:       fund_score += 8   # 资本大幅进出，信号强
            elif oi_chg > 1:     fund_score += 6   # 活跃市场
            elif oi_chg > 0.5:   fund_score += 4   # 一般
            else:                fund_score += 2   # 死水，信号弱

            fund_score = min(20, fund_score)
        except Exception:
            pass  # 解析失败，保底 10 分

    total_score = round(min(100, tech_score + fund_score))

    # ── 资产专属参数 ──
    # ETH 波动更大(日均ATR 4.9% vs BTC 4.1%), 用更紧的止损和更近的止盈
    if asset == "ETH":
        sl_atr_mult = 1.5   # BTC 用 2.0
        tp_atr_mult = 4.0   # BTC 用 5.0
        tp_atr_t1 = 3.0     # BTC 用 4.0
    else:
        sl_atr_mult = 2.0
        tp_atr_mult = 5.0
        tp_atr_t1 = 4.0

    # ── 风险收益计算 ──
    entry_price = cur_price
    signal, sig_class = "", ""

    if direction == 'bullish' and total_score >= 55:
        signal = '做多 LONG'
        sig_class = 'long'
        atr_stop = entry_price - cur_atr * sl_atr_mult
        sr_stop = nearest_support * 0.995  # 0.5% 缓冲
        stop_loss = min(atr_stop, sr_stop)  # 取更宽的止损（更低价）

        atr_target1 = entry_price + cur_atr * tp_atr_t1
        atr_target2 = entry_price + cur_atr * tp_atr_mult
        if (nearest_resistance - entry_price) / (entry_price - stop_loss) >= 1.5:
            take_profit = nearest_resistance * 0.995
        elif (next_resistance - entry_price) / (entry_price - stop_loss) >= 1.5:
            take_profit = next_resistance * 0.995
        elif (atr_target1 - entry_price) / (entry_price - stop_loss) >= 1.5:
            take_profit = atr_target1
        else:
            take_profit = atr_target2
        rr_ratio = (take_profit - entry_price) / (entry_price - stop_loss)

    elif direction == 'bearish' and total_score >= 55:
        signal = '做空 SHORT'
        sig_class = 'short'
        atr_stop = entry_price + cur_atr * sl_atr_mult
        sr_stop = nearest_resistance * 1.005
        stop_loss = max(atr_stop, sr_stop)

        atr_target1 = entry_price - cur_atr * tp_atr_t1
        atr_target2 = entry_price - cur_atr * tp_atr_mult
        if (entry_price - nearest_support) / (stop_loss - entry_price) >= 1.5:
            take_profit = nearest_support * 1.005
        elif (entry_price - next_support) / (stop_loss - entry_price) >= 1.5:
            take_profit = next_support * 1.005
        elif (entry_price - atr_target1) / (stop_loss - entry_price) >= 1.5:
            take_profit = atr_target1
        else:
            take_profit = atr_target2
        rr_ratio = (entry_price - take_profit) / (stop_loss - entry_price)

    else:
        signal = '观望 WAIT'
        sig_class = 'wait'
        if direction == 'bullish':
            stop_loss = entry_price - cur_atr * sl_atr_mult
            take_profit = entry_price + cur_atr * tp_atr_t1
        else:
            stop_loss = entry_price + cur_atr * sl_atr_mult
            take_profit = entry_price - cur_atr * tp_atr_t1
        rr_ratio = 0 if direction == 'neutral' else (
            (take_profit - entry_price) / (entry_price - stop_loss) if direction == 'bullish'
            else (entry_price - take_profit) / (stop_loss - entry_price)
        )

    # ── 杠杆建议 ──
    sl_pct = abs((stop_loss - entry_price) / entry_price) * 100
    if sig_class == 'wait':
        leverage, lev_class = 0, 'l1'
    elif sl_pct < 1.5:
        leverage, lev_class = 3, 'l3'
    elif sl_pct < 3:
        leverage, lev_class = 2, 'l2'
    else:
        leverage, lev_class = 1, 'l1'

    # ── 置信度 (基于 75 分满分体系) ──
    if total_score >= 60:
        confidence = '高'
    elif total_score >= 50:
        confidence = '中高'
    elif total_score >= 40:
        confidence = '中'
    else:
        confidence = '低'

    win_rate_est = 72 if total_score >= 60 else 65 if total_score >= 50 else 58 if total_score >= 40 else 50 if total_score >= 30 else 40
    risk_pct = abs((stop_loss - entry_price) / entry_price) * 100 if sig_class != 'wait' else 0
    reward_pct = abs((take_profit - entry_price) / entry_price) * 100 if sig_class != 'wait' else 0

    # ── 趋势摘要 ──
    tf_parts = []
    tf_parts.append(f"1H: {'多头' if trend1h > 0 else '空头' if trend1h < 0 else '震荡'}")
    tf_parts.append(f"4H: {'多头' if trend4h > 0 else '空头' if trend4h < 0 else '震荡'}")
    tf_parts.append(f"日线: {'多头' if trendD > 0 else '空头' if trendD < 0 else '震荡'}")
    trend_summary = " / ".join(tf_parts)

    return {
        "signal": signal, "sigClass": sig_class, "direction": direction,
        "totalScore": total_score, "techScore": tech_score,
        "fundScore": fund_score,
        "confidence": confidence, "winRateEst": win_rate_est,
        "entryPrice": entry_price, "stopLoss": stop_loss,
        "takeProfit": take_profit, "rrRatio": rr_ratio,
        "riskPct": risk_pct, "rewardPct": reward_pct,
        "leverage": leverage, "levClass": lev_class,
        "curRSI1h": cur_rsi1h, "curRSI4h": cur_rsi4h, "curRSID": cur_rsiD,
        "cm1": cm1, "cs1": cs1, "cm4": cm4, "cs4": cs4,
        "ce9": ce9, "ce21": ce21, "ce50": ce50,
        "ce21_4h": ce21_4h, "ce21_d": ce21_d,
        "bu": bu, "bl": bl, "curATR": cur_atr, "atrPct": atr_pct,
        "trend1h": trend1h, "trend4h": trend4h, "trendD": trendD,
        "nearestSupport": nearest_support, "nearestResistance": nearest_resistance,
        "nextSupport": next_support, "nextResistance": next_resistance,
        "trendSummary": trend_summary,
    }


# ============================================================
# Kraken 备选数据源（提供真实 OHLC，比 CoinGecko 更准）
# ============================================================

KRAKEN_PAIRS = {"BTC": "XXBTZUSD", "ETH": "XETHZUSD"}

def fetch_klines_kraken(pair, interval=60, limit=720):
    """从 Kraken 获取 OHLC 数据（美国交易所，GitHub IP 可访问）"""
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": pair, "interval": interval, "since": 0}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise Exception(str(data["error"]))
            ohlc = data["result"].get(pair, [])
            if not ohlc or len(ohlc) < 60:
                # 尝试更大的 limit
                if attempt < 2:
                    continue
                raise Exception(f"数据不足 ({len(ohlc)} 条)")
            # Kraken OHLC: [time, open, high, low, close, vwap, volume, count]
            closes = [float(o[4]) for o in ohlc[-limit:]]
            highs = [float(o[2]) for o in ohlc[-limit:]]
            lows = [float(o[3]) for o in ohlc[-limit:]]
            timestamps = [float(o[0]) for o in ohlc[-limit:]]
            return {"closes": closes, "highs": highs, "lows": lows, "timestamps": timestamps}
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
    return None


# ============================================================
# CoinGecko 备选数据源（Binance 不可用时自动切换）
# ============================================================

COINGECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum"}

def fetch_ticker_coingecko(coin_id):
    """从 CoinGecko 获取 24h 行情（备选基本面数据）"""
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_24hr_high": "true",
        "include_24hr_low": "true",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get(coin_id, {})
        if data:
            return {
                "priceChangePercent": data.get("usd_24h_change", 0),
                "quoteVolume": data.get("usd_24h_vol", 0),
                "highPrice": data.get("usd_24h_high", 0),
                "lowPrice": data.get("usd_24h_low", 0),
            }
    except Exception:
        pass
    return None


def fetch_klines_coingecko(coin_id, hours=336):
    """从 CoinGecko 获取历史价格数据（备选方案）"""
    days = max(14, hours // 24 + 1)
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(5)
                continue
            resp.raise_for_status()
            data = resp.json()
            prices = data.get("prices", [])
            if len(prices) < 60:
                raise Exception(f"数据不足 ({len(prices)} 条)")

            # CoinGecko only provides closing prices; approximate OHLC
            closes = [p[1] for p in prices]

            # Approximate highs/lows from nearby window (same as website)
            highs = []
            lows = []
            for i in range(len(closes)):
                window = closes[max(0, i - 6):i + 1]
                highs.append(max(window))
                lows.append(min(window))

            timestamps = [p[0] / 1000 for p in prices]
            return {"closes": closes, "highs": highs, "lows": lows, "timestamps": timestamps}
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
    return None


# ============================================================
# Binance 数据获取
# ============================================================

def fetch_klines_binance(symbol, interval="1h", limit=1000):
    """获取 Binance K线数据（公开 API，无需 Key）"""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            klines = resp.json()
            if not klines or len(klines) < 60:
                raise Exception(f"数据不足 ({len(klines)} 条)")
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            timestamps = [k[0] / 1000 for k in klines]
            return {"closes": closes, "highs": highs, "lows": lows, "timestamps": timestamps}
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
    return None


def derive_timeframes(hourly_data):
    """从 1H 数据推导 4H 和 1D 时间框架"""
    closes = hourly_data["closes"]
    highs = hourly_data["highs"]
    lows = hourly_data["lows"]
    n = len(closes)

    # 1H: 最近 72 根
    h1c = closes[-72:]; h1h = highs[-72:]; h1l = lows[-72:]

    # 4H: 每 4 根取一根
    h4c, h4h, h4l = [], [], []
    for i in range(max(0, n - 336), n, 4):
        h4c.append(closes[i]); h4h.append(highs[i]); h4l.append(lows[i])

    # 1D: 每 24 根取一根
    h1dc, h1dh, h1dl = [], [], []
    for i in range(max(0, n - 336), n, 24):
        h1dc.append(closes[i]); h1dh.append(highs[i]); h1dl.append(lows[i])

    return {
        "tf1h": {"closes": h1c, "highs": h1h, "lows": h1l},
        "tf4h": {"closes": h4c, "highs": h4h, "lows": h4l},
        "tf1d": {"closes": h1dc, "highs": h1dh, "lows": h1dl},
    }


def fetch_24h_ticker(symbol):
    """获取 Binance 24小时行情统计（用于基本面数据），带重试"""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    for attempt in range(3):
        try:
            resp = requests.get(url, params={"symbol": symbol}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
    return None


# ============================================================
# 期货数据（资金费率 + 持仓量 — 独立于价格的基本面数据）
# ============================================================

def fetch_futures_data(symbol):
    """
    从 Binance 期货公开 API 获取两个独立于价格的数据：
      1. 资金费率 — 多空双方谁在付钱（反向情绪指标）
      2. 持仓量变化 — 市场参与度趋势
    无需 API Key，免费公开接口。
    返回 dict 或 None
    """
    result = {}

    # 1. 最新资金费率
    try:
        fr_resp = requests.get(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": 1},
            timeout=10
        )
        if fr_resp.ok and fr_resp.json():
            raw = fr_resp.json()[0]
            result["funding_rate"] = float(raw["fundingRate"])       # 小数, 如 0.0001 = 0.01%
            result["funding_rate_pct"] = result["funding_rate"] * 100  # 百分比
            result["funding_time"] = datetime.fromtimestamp(
                raw.get("fundingTime", 0) / 1000
            ).strftime("%H:%M")
    except Exception:
        pass

    # 2. 持仓量变化（取最近两笔 30 分钟快照算 OI 变化）
    try:
        oi_resp = requests.get(
            "https://fapi.binance.com/fapi/v1/openInterestHist",
            params={"symbol": symbol, "period": "30m", "limit": 3},
            timeout=10
        )
        if oi_resp.ok:
            oi_data = oi_resp.json()
            if len(oi_data) >= 2:
                cur = float(oi_data[-1]["sumOpenInterest"])
                prev = float(oi_data[-2]["sumOpenInterest"])
                result["oi_current"] = cur
                result["oi_change_pct"] = round((cur - prev) / prev * 100, 3) if prev > 0 else 0
    except Exception:
        pass

    return result if result else None


# ============================================================
# 去重 & 状态管理
# ============================================================

def load_state():
    """加载上次信号状态"""
    state_file = os.path.join(LOG_DIR, "signal_state.json")
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    """保存信号状态"""
    state_file = os.path.join(LOG_DIR, "signal_state.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def save_signals_json(results, ohlc_data, data_sources):
    """保存网站数据文件 — 包含信号结果和 OHLC 数据，供 GitHub Pages 直接读取"""
    data_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    signals_file = os.path.join(data_dir, "signals.json")

    output = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "update_ts": int(time.time()),
        "data_sources": data_sources,
    }

    for asset, sig in results.items():
        # 清理信号中不能 JSON 序列化的值 (NaN, inf)
        sig_clean = {}
        for k, v in sig.items():
            if isinstance(v, float):
                import math
                if math.isnan(v):
                    sig_clean[k] = None
                elif math.isinf(v):
                    sig_clean[k] = None
                else:
                    sig_clean[k] = round(v, 6)
            else:
                sig_clean[k] = v

        output[asset] = {
            "signal": sig_clean,
            "ohlc": ohlc_data.get(asset, {}),
        }

    with open(signals_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  📄 网站数据已保存: {signals_file}")


def should_notify(asset, signal_info, state):
    """
    判断是否应该发送通知
    规则：
      1. 信号方向改变（WAIT→LONG, LONG→SHORT 等）→ 立即通知
      2. 同一方向但距上次通知超过 4 小时 → 再次通知
      3. 首次检测到信号 → 立即通知
      4. WAIT 信号 → 不通知
      5. 邮件未配置时最多尝试 3 次，之后冷却 24 小时（避免日志噪音）
    """
    prev = state.get(asset, {})
    prev_class = prev.get("sigClass", "unknown")
    prev_time = prev.get("lastNotified", 0)
    prev_attempt = prev.get("lastAttempted", 0)
    fail_count = prev.get("notifyFailures", 0)
    curr_class = signal_info["sigClass"]

    # WAIT 信号不通知（但允许记录到日志）
    if curr_class == "wait":
        return False

    # 方向改变 → 立即通知（重置失败计数）
    if prev_class != curr_class:
        state[asset + "_failCount"] = 0  # 临时重置（方向变了值得重试）
        return True

    # 同一方向，检查时间间隔（1小时 = 3600秒）
    if prev_class == curr_class:
        # 如果之前多次失败，延长冷却到 6 小时
        cooldown = 21600 if fail_count >= 3 else 3600
        elapsed = time.time() - max(prev_time, prev_attempt)
        if elapsed > cooldown:
            return True
        return False

    return True


# ============================================================
# 日志
# ============================================================

def log_signal(asset, sig):
    """记录信号到日志文件（自动轮转，保留最近 2000 行）"""
    log_file = os.path.join(LOG_DIR, "monitor.log")
    MAX_LINES = 2000
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    direction_icon = "🟢" if sig["sigClass"] == "long" else "🔴" if sig["sigClass"] == "short" else "🟡"

    line = (
        f"[{timestamp}] {direction_icon} {asset:4s} | "
        f"{sig['signal']:12s} | "
        f"评分 {sig['totalScore']:3d}/100 | "
        f"${sig['entryPrice']:,.2f} | "
        f"R:R {sig['rrRatio']:.1f}:1 | "
        f"止损 {sig['riskPct']:.2f}% | "
        f"止盈 {sig['rewardPct']:.2f}% | "
        f"ATR {sig['atrPct']:.2f}% | "
        f"{sig['trendSummary']}"
    )

    # 读取现有行，追加新行，保留最近 MAX_LINES 行
    existing = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                existing = f.readlines()
        except Exception:
            pass
    existing.append(line + "\n")
    if len(existing) > MAX_LINES:
        existing = existing[-MAX_LINES:]

    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(existing)
    print(line)


def log_fetch_error(asset, error_msg):
    """记录数据获取错误到日志"""
    log_file = os.path.join(LOG_DIR, "monitor.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] ❌ {asset:4s} | 数据错误 | {error_msg}\n"
    print(line.strip())
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ============================================================
# 主流程
# ============================================================

SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


def run_detection(send_email=True):
    """执行一次完整的信号检测"""
    print(f"\n{'═' * 80}")
    print(f"🔍 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 80}")

    state = load_state()
    results = {}
    ohlc_data = {}  # 保存 OHLC 原始数据，供网站 signals.json 使用
    data_sources = {}  # 记录每个资产的数据源

    for asset, symbol in SYMBOL_MAP.items():
        print(f"\n  📡 获取 {asset} ({symbol}) 1H K线数据...")

        # 1. 获取 1H 数据（Binance → Kraken → CoinGecko 链式备选）
        hourly = fetch_klines_binance(symbol, "1h", 1000)
        data_source = "Binance"

        if not hourly:
            # 第二备选：Kraken（真实OHLC，美国服务器可访问）
            print(f"    ⚠️ Binance 不可用，尝试 Kraken 备选...")
            kp = KRAKEN_PAIRS.get(asset, "")
            if kp:
                hourly = fetch_klines_kraken(kp, interval=60)
                if hourly:
                    data_source = "Kraken"
                    print(f"    ✓ Kraken 备选成功")

        if not hourly:
            # 第三备选：CoinGecko（仅有收盘价，高低价近似）
            print(f"    ⚠️ Kraken 也不可用，尝试 CoinGecko 备选...")
            cg_id = COINGECKO_IDS.get(asset, "")
            if cg_id:
                hourly = fetch_klines_coingecko(cg_id)
                if hourly:
                    data_source = "CoinGecko"
                    print(f"    ✓ CoinGecko 备选成功")
                else:
                    print(f"    ❌ CoinGecko 也失败了")

        if not hourly:
            print(f"    ❌ {asset} 所有数据源均获取失败（Binance + Kraken + CoinGecko）")
            log_fetch_error(asset, "所有数据源获取失败")
            continue

        print(f"    ✓ {len(hourly['closes'])} 根 1H K线 (数据源: {data_source})")

        # 2. 获取期货数据（资金费率 + 持仓量 — 基本面评分的核心输入）
        time.sleep(0.5)
        futures = fetch_futures_data(symbol)

        if futures:
            fr_str = f"{futures.get('funding_rate_pct', 0):.4f}%"
            oi_str = f"{futures.get('oi_change_pct', 0):+.3f}%"
            print(f"    ✓ 期货数据: 资金费率 {fr_str} ({futures.get('funding_time','?')}), "
                  f"OI 变化 {oi_str}")
        else:
            print(f"    ⚠️ 期货数据不可用 (Binance Futures API), 基本面评分为默认值")

        # 3. 推导时间框架
        tf = derive_timeframes(hourly)
        print(f"    1H: {len(tf['tf1h']['closes'])} 根, "
              f"4H: {len(tf['tf4h']['closes'])} 根, "
              f"1D: {len(tf['tf1d']['closes'])} 根")

        # 4. 生成信号 (传入 asset 和期货数据)
        sig = generate_signal(tf["tf1h"], tf["tf4h"], tf["tf1d"], asset=asset, futures_info=futures)
        results[asset] = sig

        # 5. 保存 OHLC 数据（供网站 signals.json 使用）
        ohlc_data[asset] = {
            "1h": {
                "closes": tf["tf1h"]["closes"],
                "highs": tf["tf1h"]["highs"],
                "lows": tf["tf1h"]["lows"],
            },
            "4h": {
                "closes": tf["tf4h"]["closes"],
                "highs": tf["tf4h"]["highs"],
                "lows": tf["tf4h"]["lows"],
            },
            "1d": {
                "closes": tf["tf1d"]["closes"],
                "highs": tf["tf1d"]["highs"],
                "lows": tf["tf1d"]["lows"],
            },
        }
        data_sources[asset] = data_source

        # 5. 日志输出
        log_signal(asset, sig)

        # 6. 判断是否需要通知 & 更新状态
        if sig["sigClass"] != "wait":
            should_send = send_email and should_notify(asset, sig, state)
        else:
            should_send = False

        # 总是更新 state（即使不发送邮件），跟踪信号变化
        state_key = asset
        prev = state.get(state_key, {})
        prev_class = prev.get("sigClass", "unknown")
        fail_count = prev.get("notifyFailures", 0) if prev_class == sig["sigClass"] else 0

        state[state_key] = {
            "sigClass": sig["sigClass"],
            "direction": sig["direction"],
            "totalScore": sig["totalScore"],
            "lastSignal": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "lastNotified": prev.get("lastNotified", 0),
            "lastAttempted": prev.get("lastAttempted", 0),
            "notifyFailures": fail_count,
        }

        if should_send:
            print(f"    📧 触发通知条件，发送邮件...")
            try:
                from scripts.send_email import send_signal_email, is_configured
                if is_configured():
                    state[state_key]["lastAttempted"] = time.time()
                    success = send_signal_email(
                        asset=asset,
                        signal=sig["signal"],
                        direction=sig["direction"],
                        score=sig["totalScore"],
                        entry_price=sig["entryPrice"],
                        stop_loss=sig["stopLoss"],
                        take_profit=sig["takeProfit"],
                        rr_ratio=sig["rrRatio"],
                        risk_pct=sig["riskPct"],
                        reward_pct=sig["rewardPct"],
                        confidence=sig["confidence"],
                        win_rate_est=sig["winRateEst"],
                        trend_summary=sig["trendSummary"],
                        cur_price=sig["entryPrice"],
                        atr_pct=sig["atrPct"],
                        tech_score=sig["techScore"],
                        fund_score=sig["fundScore"],
                    )
                    if success:
                        state[state_key]["lastNotified"] = time.time()
                        state[state_key]["notifyFailures"] = 0
                        print(f"    ✅ 邮件已发送")
                    else:
                        state[state_key]["notifyFailures"] = fail_count + 1
                        print(f"    ❌ 邮件发送失败 (第{state[state_key]['notifyFailures']}次失败)")
                else:
                    state[state_key]["notifyFailures"] = fail_count + 1
                    state[state_key]["lastAttempted"] = time.time()
                    print(f"    ⚠️ 邮件未配置（缺少 AI_MONITOR_EMAIL_FROM / AI_MONITOR_EMAIL_PASSWORD 环境变量）")
                    print(f"    💡 请在 GitHub Settings → Secrets → Actions 中添加这三个 Secrets")
            except ImportError:
                state[state_key]["notifyFailures"] = fail_count + 1
                state[state_key]["lastAttempted"] = time.time()
                print(f"    ⚠️ 邮件模块导入失败")
            except Exception as e:
                state[state_key]["notifyFailures"] = fail_count + 1
                state[state_key]["lastAttempted"] = time.time()
                print(f"    ❌ 邮件发送异常: {e}")
        elif not send_email:
            print(f"    🔇 跳过通知（邮件已禁用）")
        elif sig["sigClass"] == "wait":
            print(f"    🔇 WAIT 信号，不通知")
        else:
            reason = "未到通知间隔"
            if fail_count >= 3:
                reason = f"冷却中（{fail_count}次发送失败，24小时冷却）"
            print(f"    🔇 跳过通知（{reason}）")

        # 短暂休息避免 API 限速
        time.sleep(1)

    # 保存状态
    save_state(state)

    # 保存网站数据文件 (data/signals.json) — 供 GitHub Pages 直接读取
    save_signals_json(results, ohlc_data, data_sources)

    # 汇总
    print(f"\n{'─' * 80}")
    print(f"📊 检测汇总:")
    for asset, sig in results.items():
        icon = "🟢" if sig["sigClass"] == "long" else "🔴" if sig["sigClass"] == "short" else "🟡"
        print(f"  {icon} {asset}: {sig['signal']} | 评分 {sig['totalScore']}/100 | "
              f"${sig['entryPrice']:,.2f} | R:R {sig['rrRatio']:.1f}:1 | "
              f"置信度 {sig['confidence']}")
    print(f"{'═' * 80}\n")

    return results


def main():
    parser = argparse.ArgumentParser(description="加密货币短线交易信号监控")
    parser.add_argument("--loop", action="store_true", help="持续监控模式")
    parser.add_argument("--once", action="store_true", default=True, help="单次检测（默认）")
    parser.add_argument("--interval", type=int, default=None,
                        help=f"监控间隔秒数（默认: {os.environ.get('AI_MONITOR_INTERVAL', '600')}）")
    parser.add_argument("--no-email", action="store_true", help="禁用邮件通知")
    args = parser.parse_args()

    interval = args.interval or int(os.environ.get("AI_MONITOR_INTERVAL", "600"))
    send_email_flag = not args.no_email

    print("=" * 80)
    print("🤖 AI 加密货币短线交易信号监控")
    print(f"   标的: BTC, ETH")
    print(f"   数据源: Binance 公开 API (1H K线)")
    print(f"   信号逻辑: 多时间框架分析 (1H + 4H + 日线)")
    print(f"   邮件通知: {'已配置' if send_email_flag else '已禁用'}")
    print(f"   日志文件: {os.path.join(LOG_DIR, 'monitor.log')}")
    print("=" * 80)

    if args.loop:
        print(f"\n🔄 持续监控模式，每 {interval} 秒检测一次 (Ctrl+C 停止)\n")
        error_count = 0
        while True:
            try:
                run_detection(send_email=send_email_flag)
                error_count = 0  # 成功则重置
                next_time = datetime.now() + timedelta(seconds=interval)
                print(f"⏰ 下次检测: {next_time.strftime('%H:%M:%S')} "
                      f"(等待 {interval} 秒)...")
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n\n👋 监控已停止")
                break
            except Exception as e:
                error_count += 1
                print(f"\n❌ 检测异常 ({error_count}): {e}")
                if error_count >= 5:
                    print("❌ 连续错误超过 5 次，停止监控")
                    break
                wait = min(60, interval)
                print(f"⏳ {wait} 秒后重试...")
                time.sleep(wait)
    else:
        # 单次检测
        results = run_detection(send_email=send_email_flag)

        # 提示
        print("💡 提示：")
        print("   python scripts/monitor_crypto.py --loop    持续监控模式")
        print("   python scripts/monitor_crypto.py --once    单次检测（默认）")
        if not send_email_flag:
            print("   设置 AI_MONITOR_EMAIL_FROM 和 AI_MONITOR_EMAIL_PASSWORD 环境变量以启用邮件通知")

        return results


if __name__ == "__main__":
    main()
