"""
加密货币短线交易信号监控
每 10 分钟自动检测 BTC/ETH，有交易机会时邮件通知

数据源: Binance 公开 API（无需 API Key）
信号逻辑: V4 硬性门槛制 — 废除打分，三道硬闸过滤

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
import math
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

# 延迟导入（避免循环依赖，仅在实际发送邮件时才使用）
from scripts.send_email import send_signal_email, is_configured


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
# V4 辅助函数：波段点检测
# ============================================================

def find_swing_points(highs, lows, lookback=5):
    """
    检测最近一个波段高点和波段低点（用于 V4 止损和入场 Setup）
    返回: {"swing_high": float or None, "swing_low": float or None,
           "swing_high_idx": int, "swing_low_idx": int}
    """
    n = len(highs)
    if n < lookback * 2 + 1:
        return {"swing_high": None, "swing_low": None,
                "swing_high_idx": -1, "swing_low_idx": -1}

    # 找最近的 swing high（从后往前找）
    swing_high, swing_high_idx = None, -1
    for i in range(n - lookback - 1, lookback - 1, -1):
        is_swing_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if highs[j] >= highs[i]:
                is_swing_high = False
                break
        if is_swing_high:
            swing_high = highs[i]
            swing_high_idx = i
            break

    # 找最近的 swing low（从后往前找）
    swing_low, swing_low_idx = None, -1
    for i in range(n - lookback - 1, lookback - 1, -1):
        is_swing_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if lows[j] <= lows[i]:
                is_swing_low = False
                break
        if is_swing_low:
            swing_low = lows[i]
            swing_low_idx = i
            break

    return {"swing_high": swing_high, "swing_low": swing_low,
            "swing_high_idx": swing_high_idx, "swing_low_idx": swing_low_idx}


def check_spring_pattern(lows, recent_swing_low, lookback=8):
    """
    检测 Spring 形态：跌破前一波段低点后收回（Wyckoff 弹簧）
    返回 True 如果在最近 lookback 根 K 线内出现过此形态
    """
    if recent_swing_low is None:
        return False
    n = len(lows)
    check_range = min(lookback, n - 2)
    for i in range(n - check_range, n):
        if lows[i] < recent_swing_low * 0.998:  # 跌破过（留 0.2% 容差）
            # 确认已收回：当前价格在波段低点上方
            return True
    return False


def check_upthrust_pattern(highs, recent_swing_high, lookback=8):
    """
    检测 Upthrust 形态：突破前一波段高点后收回（Wyckoff 上冲回落）
    返回 True 如果在最近 lookback 根 K 线内出现过此形态
    """
    if recent_swing_high is None:
        return False
    n = len(highs)
    check_range = min(lookback, n - 2)
    for i in range(n - check_range, n):
        if highs[i] > recent_swing_high * 1.002:  # 突破过（留 0.2% 容差）
            return True
    return False


# ============================================================
# 信号生成引擎 V4 — 硬性门槛制
# ============================================================

def generate_signal(data_1h, data_4h, data_1d=None, asset="BTC", futures_info=None, data_15m=None, oi_15m=None):
    """
    V4 — 硬性门槛制（2026-08-04）

    废除 V1-V3 的凑分逻辑，改为三道硬性闸门：

    【闸门 1】1H 大周期趋势过滤 (EMA50/EMA200 + RSI)
      - 做多环境: 1H Close > EMA50 > EMA200 且 1H RSI(14) > 50
      - 做空环境: 1H Close < EMA50 < EMA200 且 1H RSI(14) < 50
      - 观望: EMA50/EMA200 纠缠或价格处于均线之间 → 一票否决

    【闸门 2】15min 入场 Setup
      - 做多: 价格回调至 15min EMA50 附近 (偏离 < 0.3%) 或 Spring 形态(跌破前低后收回)
      - 做空: 价格反弹至 15min EMA50 附近 (偏离 < 0.3%) 或 Upthrust 形态(突破前高后收回)

    【闸门 3】OI + 量价方向绑定
      - 做多确认: 最近 3 根 15min K线中 (Price↑ AND OI↑) → 主力主动开多
      - 做空确认: 最近 3 根 15min K线中 (Price↓ AND OI↑) → 主力主动开空
      - 拒绝: 价格上涨但 OI 减少 → 空头平仓驱动，不入场

    【风控】
      - SL: max(Swing ± 0.2%, 1.2 × ATR15m) — 取更宽的止损防插针
      - TP1: 1.5 × Risk (盈亏比 1:1.5)，平仓 50%，移止损至保本
      - TP2: 2.5 × Risk 或 1H 前高/前低阻力位，平仓剩余 50%
      - 时间止损: 持仓超过 16 根 15min (4小时) 未触发 TP1 → 市价平仓
    """
    c1, h1, l1 = data_1h["closes"], data_1h["highs"], data_1h["lows"]

    # ── 15min 数据 ──
    has_15m = data_15m is not None and len(data_15m.get("closes", [])) >= 50
    if has_15m:
        c15 = data_15m["closes"]; h15 = data_15m["highs"]; l15 = data_15m["lows"]
        cur_price = c15[-1]
    else:
        # 无 15min 数据 → 观望（V4 必须依赖 15min）
        return _make_wait_signal(c1[-1], "15min 数据不可用")

    # ── OI 数据 ──
    has_oi = oi_15m is not None and len(oi_15m) >= 4

    # ═══════════════════════════════════════════════════════════
    # 闸门 1: 1H 大周期趋势过滤
    # ═══════════════════════════════════════════════════════════
    if len(c1) < 200:
        return _make_wait_signal(cur_price, "1H 数据不足 (需 ≥200 根)")

    ema50_1h = EMA(c1, 50); ce50 = ema50_1h[-1]
    ema200_1h = EMA(c1, 200); ce200 = ema200_1h[-1]
    rsi1h = RSI(c1, 14); cur_rsi1h = rsi1h[-1]

    if ce50 is None or ce200 is None or cur_rsi1h is None:
        return _make_wait_signal(cur_price, "1H 指标计算失败")

    # 做多环境: Close > EMA50 > EMA200 且 RSI > 50
    bull_env = (cur_price > ce50 > ce200) and (cur_rsi1h > 50)
    # 做空环境: Close < EMA50 < EMA200 且 RSI < 50
    bear_env = (cur_price < ce50 < ce200) and (cur_rsi1h < 50)

    if not bull_env and not bear_env:
        regime = _classify_regime_text(cur_price, ce50, ce200, cur_rsi1h)
        return _make_wait_signal(cur_price, f"1H 环境不满足: {regime}")

    direction = 'bullish' if bull_env else 'bearish'
    regime_text = "多头排列" if bull_env else "空头排列"

    # ═══════════════════════════════════════════════════════════
    # 闸门 2: 15min 入场 Setup
    # ═══════════════════════════════════════════════════════════
    ema50_15 = EMA(c15, 50)
    e50_15 = ema50_15[-1] if len(ema50_15) > 0 else None
    atr15 = ATR(h15, l15, c15, 14)
    cur_atr15 = atr15[-1] if atr15[-1] is not None else cur_price * 0.005

    if e50_15 is None:
        return _make_wait_signal(cur_price, "15min EMA50 计算失败")

    # 波段点检测
    swings15 = find_swing_points(h15, l15, lookback=5)
    swing_high_15 = swings15["swing_high"]
    swing_low_15 = swings15["swing_low"]

    # Entry Setup 判定
    entry_setup_ok = False
    entry_reason = ""

    if direction == 'bullish':
        # 条件 A: 价格在 15min EMA50 附近（偏离 < 0.3%）
        deviation_ema = abs(cur_price - e50_15) / e50_15 * 100 if e50_15 > 0 else 999
        near_ema = deviation_ema < 0.3
        # 条件 B: Spring 形态（跌破前低后收回）
        spring = check_spring_pattern(l15, swing_low_15, lookback=8)

        if near_ema:
            entry_setup_ok = True
            entry_reason = f"回调至 15min EMA50 (偏离 {deviation_ema:.2f}%)"
        elif spring:
            entry_setup_ok = True
            entry_reason = "Spring 形态: 跌破前低后收回"
    else:
        # 做空
        deviation_ema = abs(cur_price - e50_15) / e50_15 * 100 if e50_15 > 0 else 999
        near_ema = deviation_ema < 0.3
        upthrust = check_upthrust_pattern(h15, swing_high_15, lookback=8)

        if near_ema:
            entry_setup_ok = True
            entry_reason = f"反弹至 15min EMA50 (偏离 {deviation_ema:.2f}%)"
        elif upthrust:
            entry_setup_ok = True
            entry_reason = "Upthrust 形态: 突破前高后收回"

    if not entry_setup_ok:
        return _make_wait_signal(cur_price, "15min 入场 Setup 不满足")

    # ═══════════════════════════════════════════════════════════
    # 闸门 3: OI + 量价方向绑定
    # ═══════════════════════════════════════════════════════════
    oi_confirmed = False
    oi_detail = "OI 数据不可用 (跳过)"

    if has_oi:
        oi_confirmed, oi_detail = _check_oi_confirmation(c15, oi_15m, direction)

    # OI 不可用时仍然允许入场（不阻塞），但有 OI 且不满足时拒绝
    if has_oi and not oi_confirmed:
        return _make_wait_signal(cur_price, f"OI 拒绝: {oi_detail}")

    # ═══════════════════════════════════════════════════════════
    # 全部闸门通过 — 生成入场信号
    # ═══════════════════════════════════════════════════════════

    # 1H 前高/前低（用于 TP2 阻力判断）
    swings1h = find_swing_points(h1, l1, lookback=5)
    prev_high_1h = swings1h["swing_high"]
    prev_low_1h = swings1h["swing_low"]

    # ── 止损: max(Swing ± 0.2%, 1.2 × ATR_15m) ──
    atr_stop_dist = 1.2 * cur_atr15
    if direction == 'bullish':
        swing_stop_dist = cur_price - (swing_low_15 * 0.998) if swing_low_15 else 0
        stop_dist = max(swing_stop_dist, atr_stop_dist)
        # 至少留 0.3% 的止损距离
        stop_dist = max(stop_dist, cur_price * 0.003)
        stop_loss = cur_price - stop_dist
    else:
        swing_stop_dist = (swing_high_15 * 1.002) - cur_price if swing_high_15 else 0
        stop_dist = max(swing_stop_dist, atr_stop_dist)
        stop_dist = max(stop_dist, cur_price * 0.003)
        stop_loss = cur_price + stop_dist

    risk_dist = abs(cur_price - stop_loss)

    # ── 止盈: TP1 = 1.5 × Risk, TP2 = 2.5 × Risk (or 1H swing) ──
    tp1_dist = 1.5 * risk_dist
    tp2_dist_raw = 2.5 * risk_dist

    if direction == 'bullish':
        take_profit1 = cur_price + tp1_dist
        # TP2: min(2.5×Risk, 触及1H前高阻力)
        if prev_high_1h and prev_high_1h > cur_price:
            tp2_dist = min(tp2_dist_raw, prev_high_1h - cur_price)
        else:
            tp2_dist = tp2_dist_raw
        take_profit2 = cur_price + tp2_dist
        # 保本价
        breakeven_price = cur_price
    else:
        take_profit1 = cur_price - tp1_dist
        if prev_low_1h and prev_low_1h < cur_price:
            tp2_dist = min(tp2_dist_raw, cur_price - prev_low_1h)
        else:
            tp2_dist = tp2_dist_raw
        take_profit2 = cur_price - tp2_dist
        breakeven_price = cur_price

    # 仓位管理
    POSITION_PCT_1 = 50

    # ── R:R ──
    pct1 = POSITION_PCT_1 / 100
    pct2 = 1 - pct1
    weighted_reward = pct1 * tp1_dist + pct2 * tp2_dist
    rr_ratio = weighted_reward / risk_dist if risk_dist > 0 else 0

    # ── 百分比 ──
    risk_pct = risk_dist / cur_price * 100
    tp1_pct = tp1_dist / cur_price * 100
    tp2_pct = tp2_dist / cur_price * 100

    # ── 信号 ──
    if direction == 'bullish':
        signal = '做多 LONG'
        sig_class = 'long'
    else:
        signal = '做空 SHORT'
        sig_class = 'short'

    # ── 杠杆 ──
    if risk_pct < 1.5:
        leverage, lev_class = 3, 'l3'
    elif risk_pct < 3:
        leverage, lev_class = 2, 'l2'
    else:
        leverage, lev_class = 1, 'l1'

    # ── 趋势摘要 ──
    atr_pct_1h = (ATR(h1, l1, c1, 14)[-1] or cur_price * 0.01) / cur_price * 100
    trend_summary = f"V4 硬闸 | 1H: {regime_text} | {entry_reason}"

    # 获取 1H 的其他指标用于参考显示
    ema21_1h = EMA(c1, 21); ce21 = ema21_1h[-1]
    ema9_1h = EMA(c1, 9); ce9 = ema9_1h[-1]
    rsi4h = RSI(data_4h["closes"], 14); cur_rsi4h = rsi4h[-1]
    macd1h = MACD(c1)
    cm1 = macd1h["macdLine"][-1]; cs1 = macd1h["signalLine"][-1]
    macd4h = MACD(data_4h["closes"])
    cm4 = macd4h["macdLine"][-1]; cs4 = macd4h["signalLine"][-1]
    bb1h = BB(c1, 20, 2)
    bu = bb1h["upper"][-1]; bl = bb1h["lower"][-1]

    # 支撑阻力
    sr = find_sr_lines(c1, h1, l1)
    nearest_support = sr["supports"][0] if sr["supports"] else cur_price * 0.97
    nearest_resistance = sr["resistances"][0] if sr["resistances"] else cur_price * 1.03
    next_support = sr["supports"][1] if len(sr["supports"]) > 1 else cur_price * 0.95
    next_resistance = sr["resistances"][1] if len(sr["resistances"]) > 1 else cur_price * 1.05

    # 1H 趋势方向
    trend1h = 1 if cur_price > ce21 else -1
    trend4h = 1 if cur_price > EMA(data_4h["closes"], 21)[-1] else -1

    return {
        "signal": signal, "sigClass": sig_class, "direction": direction,
        "totalScore": 0,  # V4 废弃评分
        "confidence": "V4 硬闸",
        "winRateEst": 0,
        "entryPrice": cur_price, "stopLoss": stop_loss,
        "takeProfit": take_profit1, "takeProfit1": take_profit1, "takeProfit2": take_profit2,
        "positionPct1": POSITION_PCT_1, "breakevenPrice": breakeven_price,
        "rrRatio": rr_ratio,
        "riskPct": risk_pct, "rewardPct": tp1_pct,
        "tp1Pct": tp1_pct, "tp2Pct": tp2_pct,
        "leverage": leverage, "levClass": lev_class,
        # V4 闸门信息
        "v4_gate1_env": regime_text,
        "v4_gate1_ema50": ce50, "v4_gate1_ema200": ce200, "v4_gate1_rsi1h": cur_rsi1h,
        "v4_gate2_entry": entry_reason,
        "v4_gate2_ema50_15": e50_15, "v4_gate2_atr15": cur_atr15,
        "v4_gate2_swing_low": swing_low_15, "v4_gate2_swing_high": swing_high_15,
        "v4_gate3_oi": oi_detail,
        "v4_time_stop_bars": 16, "v4_time_stop_minutes": 240,
        # 兼容旧版字段
        "curRSI1h": cur_rsi1h, "curRSI4h": cur_rsi4h,
        "cm1": cm1, "cs1": cs1, "cm4": cm4, "cs4": cs4,
        "ce9": ce9, "ce21": ce21, "ce50": ce50,
        "ce21_4h": EMA(data_4h["closes"], 21)[-1],
        "bu": bu, "bl": bl, "curATR": cur_atr15, "atrPct": atr_pct_1h,
        "trend1h": trend1h, "trend4h": trend4h,
        "nearestSupport": nearest_support, "nearestResistance": nearest_resistance,
        "nextSupport": next_support, "nextResistance": next_resistance,
        "trendSummary": trend_summary,
        "fundingRate": futures_info.get("funding_rate") if futures_info else None,
        "fundingRatePct": futures_info.get("funding_rate_pct") if futures_info else None,
        "fundingTime": futures_info.get("funding_time") if futures_info else None,
    }


def _make_wait_signal(cur_price, reason=""):
    """生成观望信号"""
    return {
        "signal": f'观望 WAIT', "sigClass": "wait", "direction": "neutral",
        "totalScore": 0, "confidence": "观望", "winRateEst": 0,
        "entryPrice": cur_price,
        "stopLoss": cur_price, "takeProfit": cur_price,
        "takeProfit1": cur_price, "takeProfit2": cur_price,
        "positionPct1": 50, "breakevenPrice": cur_price,
        "rrRatio": 0, "riskPct": 0, "rewardPct": 0,
        "tp1Pct": 0, "tp2Pct": 0,
        "leverage": 0, "levClass": "l1",
        "v4_gate1_env": reason,
        "v4_gate2_entry": "", "v4_gate3_oi": "",
        "v4_time_stop_bars": 0, "v4_time_stop_minutes": 0,
        "curRSI1h": None, "curRSI4h": None,
        "cm1": None, "cs1": None, "cm4": None, "cs4": None,
        "ce9": None, "ce21": None, "ce50": None, "ce21_4h": None,
        "bu": None, "bl": None, "curATR": None, "atrPct": 0,
        "trend1h": 0, "trend4h": 0,
        "nearestSupport": cur_price * 0.97, "nearestResistance": cur_price * 1.03,
        "nextSupport": cur_price * 0.95, "nextResistance": cur_price * 1.05,
        "trendSummary": f"V4: {reason}",
        "fundingRate": None, "fundingRatePct": None, "fundingTime": None,
    }


def _classify_regime_text(price, ema50, ema200, rsi):
    """分类 1H 环境状态，返回中文描述"""
    if ema50 is None or ema200 is None:
        return "均线数据不足"
    ema_diff_pct = abs(ema50 - ema200) / ema200 * 100 if ema200 > 0 else 0
    if ema_diff_pct < 1.0:  # EMA50/200 距离 < 1% → 纠缠
        return f"均线纠缠 (EMA50/200 距 {ema_diff_pct:.1f}%)"
    if price > ema50:
        if ema50 > ema200:
            return f"多头排列但 RSI={rsi:.0f}≤50 (偏弱)"
        else:
            return f"价格在均线上方但 EMA50<EMA200 (矛盾)"
    elif price < ema50:
        if ema50 < ema200:
            return f"空头排列但 RSI={rsi:.0f}≥50 (偏强)"
        else:
            return f"价格在均线下方但 EMA50>EMA200 (矛盾)"
    return f"价格在均线之间 (EMA50/200 中间地带)"


def _check_oi_confirmation(c15, oi_15m, direction):
    """
    OI + 量价方向绑定检查
    返回: (confirmed: bool, detail: str)
    """
    n = min(len(c15), len(oi_15m))
    if n < 4:
        return False, "OI 数据不足 (<4)"

    # 最近 3 根 15min K 线的价格变化和 OI 变化
    checks = []
    for i in range(n - 3, n):
        if i < 1:
            continue
        price_chg = c15[i] - c15[i - 1]
        oi_chg = oi_15m[i] - oi_15m[i - 1]

        price_up = price_chg > 0
        price_down = price_chg < 0
        oi_up = oi_chg > 0
        oi_down = oi_chg < 0

        checks.append({
            "price_up": price_up, "price_down": price_down,
            "oi_up": oi_up, "oi_down": oi_down,
        })

    if len(checks) < 2:
        return False, "有效 OI 检查点不足"

    if direction == 'bullish':
        # 确认: 有 (Price↑ AND OI↑) → 主动开多
        active_long = any(c["price_up"] and c["oi_up"] for c in checks)
        # 拒绝: Price↑ 但 OI↓ → 空头平仓驱动上涨
        short_covering = any(c["price_up"] and c["oi_down"] for c in checks)

        if short_covering and not active_long:
            return False, "价格上涨但 OI 下降 (空头平仓驱动, 不追)"
        if active_long:
            return True, "OI 确认: 主动开多 (Price↑ + OI↑)"
        # 有涨有跌但没有明确的主动开多
        return False, "OI 未确认主动开多 (最近3根无 Price↑+OI↑)"

    else:
        # 做空确认: (Price↓ AND OI↑) → 主动开空
        active_short = any(c["price_down"] and c["oi_up"] for c in checks)
        # 拒绝: 价格下跌但 OI 下降 → 多头平仓驱动
        long_liquidation = any(c["price_down"] and c["oi_down"] for c in checks)

        if long_liquidation and not active_short:
            return False, "价格下跌但 OI 下降 (多头平仓驱动, 不追)"
        if active_short:
            return True, "OI 确认: 主动开空 (Price↓ + OI↑)"
        return False, "OI 未确认主动开空 (最近3根无 Price↓+OI↑)"


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
    # 多端点轮换（主站在大陆可能被墙）
    urls = [
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines",
        "https://api2.binance.com/api/v3/klines",
    ]
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    for attempt in range(3):
        url = urls[attempt % len(urls)]
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            klines = resp.json()
            if not klines or len(klines) < 60:
                raise Exception(f"数据不足 ({len(klines)} 条)")
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            volumes = [float(k[5]) for k in klines]
            timestamps = [k[0] / 1000 for k in klines]
            return {"closes": closes, "highs": highs, "lows": lows,
                    "volumes": volumes, "timestamps": timestamps}
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
    return None


def derive_timeframes(hourly_data):
    """从 1H 数据推导 4H 和 1D 时间框架（含成交量）"""
    closes = hourly_data["closes"]
    highs = hourly_data["highs"]
    lows = hourly_data["lows"]
    volumes = hourly_data.get("volumes", [])
    n = len(closes)

    # 1H: 最近 336 根（14天，确保 V4 EMA200 有足够数据）
    h1c = closes[-336:]; h1h = highs[-336:]; h1l = lows[-336:]
    h1v = volumes[-336:] if volumes else []

    # 4H: 每 4 根取收盘价，最高/最低取4根极值，成交量求和
    h4c, h4h, h4l, h4v = [], [], [], []
    for i in range(max(0, n - 336), n, 4):
        end = min(i + 4, n)
        h4c.append(closes[end - 1])
        h4h.append(max(highs[i:end]))
        h4l.append(min(lows[i:end]))
        if volumes:
            h4v.append(sum(volumes[i:end]))

    # 1D: 类似 4H，每 24 根聚合
    h1dc, h1dh, h1dl, h1dv = [], [], [], []
    for i in range(max(0, n - 336), n, 24):
        end = min(i + 24, n)
        h1dc.append(closes[end - 1])
        h1dh.append(max(highs[i:end]))
        h1dl.append(min(lows[i:end]))
        if volumes:
            h1dv.append(sum(volumes[i:end]))

    result = {
        "tf1h": {"closes": h1c, "highs": h1h, "lows": h1l},
        "tf4h": {"closes": h4c, "highs": h4h, "lows": h4l},
        "tf1d": {"closes": h1dc, "highs": h1dh, "lows": h1dl},
    }
    if volumes:
        result["tf1h"]["volumes"] = h1v
        result["tf4h"]["volumes"] = h4v
        result["tf1d"]["volumes"] = h1dv
    return result


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
# V4 新增: 15min OI 数据获取（用于闸门 3 OI+量价绑定）
# ============================================================

def fetch_oi_15min(symbol, limit=20):
    """
    获取 15min 粒度的 OI 历史数据（用于 V4 闸门 3：OI+量价方向绑定）
    返回: list[float] — 按时间排列的 sumOpenInterest 值，失败返回 None
    """
    try:
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/openInterestHist",
            params={"symbol": symbol, "period": "15m", "limit": limit},
            timeout=10
        )
        if resp.ok:
            data = resp.json()
            if data and len(data) >= 4:
                return [float(d["sumOpenInterest"]) for d in data]
    except Exception:
        pass
    return None


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


def fetch_fear_greed_index():
    """获取加密货币恐惧贪婪指数 (数据源: alternative.me, 免费无需API Key)
    重试 3 次，间隔递增（1s, 2s, 3s）"""
    for attempt in range(3):
        try:
            resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                item = data.get("data", [{}])[0]
                if not item:
                    raise Exception("API 返回空数据")
                ts = item.get("timestamp")
                return {
                    "value": int(item.get("value", 50)),
                    "classification": item.get("value_classification", "Neutral"),
                    "timestamp": datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S") if ts else None,
                }
            else:
                print(f"  ⚠️ 恐惧贪婪指数 HTTP {resp.status_code} (attempt {attempt+1}/3)")
        except Exception as e:
            print(f"  ⚠️ 恐惧贪婪指数获取失败 (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(attempt + 1)
    return None


def fetch_etf_flows_simple():
    """获取 BTC/ETH 现货 ETF 净流入/流出 (数据源: farside.co.uk)

    ⚠️ 已知限制: farside.co.uk 使用了 Cloudflare 反爬虫保护，
    从 GitHub Actions 服务器 IP 通常无法直接访问。
    浏览器端 (ai选股/index.html) 会通过 CORS 代理尝试获取。

    返回: {"BTC": {"net_flow": 1.25}, "ETH": {"net_flow": -0.35}}  (单位: 亿$)
          失败时返回 None（而非空 dict，以区分"未尝试"和"尝试失败"）"""
    import re as _re
    etf_data = {}
    symbol_map = {"BTC": "btc", "ETH": "eth"}

    for asset, fs_slug in symbol_map.items():
        try:
            url = f"https://farside.co.uk/{fs_slug}/"
            resp = requests.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,*/*",
            }, timeout=15)
            if resp.status_code != 200:
                print(f"  ⚠️ {asset} ETF: farside.co.uk 返回 HTTP {resp.status_code}")
                continue

            content = resp.text
            # Cloudflare 保护检测
            if 'Just a moment' in content or 'cf_chl' in content or 'challenge-platform' in content:
                print(f"  ⚠️ {asset} ETF: farside.co.uk 被 Cloudflare 保护，无法从服务器端访问（将依赖浏览器端获取）")
                continue

            # 提取所有表格中的数值行
            tables = _re.findall(r'<table[^>]*>(.*?)</table>', content, _re.DOTALL)
            daily_net = None

            for table_html in tables:
                rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, _re.DOTALL)
                search_rows = rows[-4:] if len(rows) >= 4 else rows

                for row_html in search_rows:
                    if '<th' in row_html or 'otal' in row_html or 'OTAL' in row_html:
                        continue
                    cells = _re.findall(r'<td[^>]*>(.*?)</td>', row_html, _re.DOTALL)
                    clean_cells = []
                    for c in cells:
                        c = _re.sub(r'<[^>]+>', '', c).strip()
                        c = c.replace('$', '').replace(',', '').replace(' ', '')
                        clean_cells.append(c)
                    if len(clean_cells) >= 2:
                        nums = []
                        for val in clean_cells[1:]:
                            if val.startswith('(') and val.endswith(')'):
                                val = '-' + val[1:-1]
                            try:
                                nums.append(float(val))
                            except ValueError:
                                pass
                        if nums:
                            daily_net = round(sum(nums), 1)

            if daily_net is not None:
                net_billion = round(daily_net / 100, 2)
                etf_data[asset] = {"net_flow": net_billion}
                print(f"  📈 {asset} ETF 净流动: {net_billion:+.2f}亿$")
        except Exception as e:
            print(f"  ⚠️ {asset} ETF 流动数据获取失败: {str(e)[:80]}")

    return etf_data if etf_data else None  # 返回 None 而非空 dict


def save_signals_json(results, ohlc_data, data_sources, fear_greed=None, etf_flows=None):
    """保存网站数据文件 — 包含信号结果和 OHLC 数据，供 GitHub Pages 直接读取"""
    data_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    signals_file = os.path.join(data_dir, "signals.json")

    output = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "update_ts": int(time.time()),
        "data_sources": data_sources,
    }

    if fear_greed is not None:
        output["fear_greed"] = fear_greed
    if etf_flows:
        output["etf_flows"] = etf_flows

    for asset, sig in results.items():
        # 清理信号中不能 JSON 序列化的值 (NaN, inf)
        sig_clean = {}
        for k, v in sig.items():
            if isinstance(v, float):
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
        f"V4 硬闸 | "
        f"${sig['entryPrice']:,.2f} | "
        f"R:R {sig['rrRatio']:.1f}:1 | "
        f"止损 {sig['riskPct']:.2f}% | "
        f"TP1 {sig['tp1Pct']:.2f}% TP2 {sig['tp2Pct']:.2f}% | "
        f"闸门: {sig.get('v4_gate1_env', '?')} | {sig.get('v4_gate2_entry', '?')}"
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

        # 1b. 获取 15min 数据（V4 入场 Setup 必需）
        data_15m = None
        if data_source == "Binance":
            try:
                m15 = fetch_klines_binance(symbol, "15m", 500)
                if m15 and len(m15.get("closes", [])) >= 50:
                    data_15m = {"closes": m15["closes"], "highs": m15["highs"], "lows": m15["lows"]}
                    print(f"    ✓ {len(data_15m['closes'])} 根 15min K线 (V4 入场 Setup)")
                else:
                    print(f"    ⚠️ 15min 数据不足，V4 将返回观望")
            except Exception:
                print(f"    ⚠️ 15min 数据获取失败，V4 将返回观望")

        # 1c. 获取 15min OI 数据（V4 闸门 3：OI+量价绑定）
        oi_15m = None
        if data_source == "Binance":
            try:
                oi_15m = fetch_oi_15min(symbol, limit=20)
                if oi_15m:
                    print(f"    ✓ {len(oi_15m)} 个 15min OI 快照 (V4 OI确认)")
                else:
                    print(f"    ⚠️ 15min OI 数据不可用，将跳过 OI 确认")
            except Exception:
                print(f"    ⚠️ 15min OI 数据获取异常，将跳过 OI 确认")

        # 2. 获取期货数据（资金费率 — 参考信息，不影响 V4 入场）
        time.sleep(0.5)
        futures = fetch_futures_data(symbol)

        if futures:
            fr_str = f"{futures.get('funding_rate_pct', 0):.4f}%"
            print(f"    ✓ 期货数据: 资金费率 {fr_str} ({futures.get('funding_time','?')})")
        else:
            print(f"    ⚠️ 期货数据不可用 (Binance Futures API)")

        # 3. 推导时间框架
        tf = derive_timeframes(hourly)
        print(f"    1H: {len(tf['tf1h']['closes'])} 根, "
              f"4H: {len(tf['tf4h']['closes'])} 根, "
              f"1D: {len(tf['tf1d']['closes'])} 根")

        # 4. 生成信号 (V4: 硬性门槛制 — 三道闸门过滤)
        sig = generate_signal(tf["tf1h"], tf["tf4h"], tf["tf1d"],
                             asset=asset, futures_info=futures,
                             data_15m=data_15m, oi_15m=oi_15m)
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
                        tech_score=0,  # V4 废弃评分
                        fund_score=0,  # V4 废弃评分
                        take_profit1=sig.get("takeProfit1"),
                        take_profit2=sig.get("takeProfit2"),
                        tp1_pct=sig.get("tp1Pct", 0),
                        tp2_pct=sig.get("tp2Pct", 0),
                        position_pct1=sig.get("positionPct1", 50),
                        breakeven_price=sig.get("breakevenPrice"),
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
    try:
        # 获取市场情绪数据（恐惧贪婪指数 + ETF 流动）
        print(f"\n  🌍 获取市场情绪数据...")
        fear_greed = fetch_fear_greed_index()
        if fear_greed:
            print(f"    😱 恐惧贪婪指数: {fear_greed['value']} — {fear_greed['classification']}")
        etf_flows = fetch_etf_flows_simple()
        save_signals_json(results, ohlc_data, data_sources, fear_greed=fear_greed, etf_flows=etf_flows)
    except Exception as e:
        print(f"  ⚠️ 网站数据保存失败（不影响主流程）: {e}")

    # 汇总
    print(f"\n{'─' * 80}")
    print(f"📊 V4 硬性门槛检测汇总:")
    for asset, sig in results.items():
        icon = "🟢" if sig["sigClass"] == "long" else "🔴" if sig["sigClass"] == "short" else "🟡"
        if sig["sigClass"] != "wait":
            print(f"  {icon} {asset}: {sig['signal']} | "
                  f"${sig['entryPrice']:,.2f} | "
                  f"TP1 ${sig['takeProfit1']:,.2f} → TP2 ${sig['takeProfit2']:,.2f} | "
                  f"R:R {sig['rrRatio']:.1f}:1 | "
                  f"闸1: {sig.get('v4_gate1_env','?')} | "
                  f"闸2: {sig.get('v4_gate2_entry','?')} | "
                  f"闸3: {sig.get('v4_gate3_oi','?')}")
        else:
            print(f"  {icon} {asset}: {sig['signal']} | {sig.get('trendSummary', '')}")
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
    print("🤖 AI 加密货币短线交易信号监控 V4 — 硬性门槛制")
    print(f"   标的: BTC, ETH")
    print(f"   数据源: Binance 公开 API (15min + 1H K线)")
    print(f"   信号逻辑: 三道硬闸 — 1H趋势过滤 → 15min入场Setup → OI量价绑定")
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
