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

def generate_signal(data_1h, data_4h, data_1d):
    """
    完整移植自 ai选股/index.html 的 generateSignal()
    参数：
      data_1h, data_4h, data_1d: {"closes":[], "highs":[], "lows":[]}
    返回: dict — 完整的信号对象
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
    # CoinGecko 免费 API 已挂，暂时使用默认分
    fund_score = 10  # 中性默认

    # ── 消息面评分 (20 pts) ──
    # 新闻 RSS 不适合高频轮询，暂时使用默认分
    news_score = 10  # 中性默认

    total_score = round(min(100, tech_score + fund_score + news_score))

    # ── 风险收益计算 ──
    # 优化参数: 止损 2.0×ATR, 止盈 5.0×ATR, R:R≥1.5
    entry_price = cur_price
    signal, sig_class = "", ""

    if direction == 'bullish' and total_score >= 65:
        signal = '做多 LONG'
        sig_class = 'long'
        atr_stop = entry_price - cur_atr * 2.0
        sr_stop = nearest_support * 0.995  # 0.5% 缓冲
        stop_loss = min(atr_stop, sr_stop)  # 取更宽的止损（更低价）

        atr_target1 = entry_price + cur_atr * 4
        atr_target2 = entry_price + cur_atr * 5
        if (nearest_resistance - entry_price) / (entry_price - stop_loss) >= 1.5:
            take_profit = nearest_resistance * 0.995
        elif (next_resistance - entry_price) / (entry_price - stop_loss) >= 1.5:
            take_profit = next_resistance * 0.995
        elif (atr_target1 - entry_price) / (entry_price - stop_loss) >= 1.5:
            take_profit = atr_target1
        else:
            take_profit = atr_target2
        rr_ratio = (take_profit - entry_price) / (entry_price - stop_loss)

    elif direction == 'bearish' and total_score >= 65:
        signal = '做空 SHORT'
        sig_class = 'short'
        atr_stop = entry_price + cur_atr * 2.0
        sr_stop = nearest_resistance * 1.005
        stop_loss = max(atr_stop, sr_stop)

        atr_target1 = entry_price - cur_atr * 4
        atr_target2 = entry_price - cur_atr * 5
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
            stop_loss = entry_price - cur_atr * 2.0
            take_profit = entry_price + cur_atr * 4.0
        else:
            stop_loss = entry_price + cur_atr * 2.0
            take_profit = entry_price - cur_atr * 4.0
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

    # ── 置信度 ──
    if total_score >= 80:
        confidence = '高'
    elif total_score >= 65:
        confidence = '中高'
    elif total_score >= 50:
        confidence = '中'
    else:
        confidence = '低'

    win_rate_est = 72 if total_score >= 80 else 65 if total_score >= 70 else 58 if total_score >= 60 else 50 if total_score >= 50 else 40
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
        "fundScore": fund_score, "newsScore": news_score,
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
    """获取 Binance 24小时行情统计（用于基本面数据）"""
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/24hr",
                            params={"symbol": symbol}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
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


def should_notify(asset, signal_info, state):
    """
    判断是否应该发送通知
    规则：
      1. 信号方向改变（WAIT→LONG, LONG→SHORT 等）→ 立即通知
      2. 同一方向但距上次通知超过 4 小时 → 再次通知
      3. 首次检测到信号 → 立即通知
      4. WAIT 信号 → 不通知（但记录状态变化）
    """
    prev = state.get(asset, {})
    prev_class = prev.get("sigClass", "unknown")
    prev_time = prev.get("lastNotified", 0)
    curr_class = signal_info["sigClass"]

    # WAIT 信号不通知
    if curr_class == "wait":
        return False

    # 方向改变 → 立即通知
    if prev_class != curr_class:
        return True

    # 同一方向，检查时间间隔（4小时 = 14400秒）
    if prev_class == curr_class:
        elapsed = time.time() - prev_time
        if elapsed > 14400:  # 4 小时
            return True
        return False

    return True


# ============================================================
# 日志
# ============================================================

def log_signal(asset, sig):
    """记录信号到日志文件"""
    log_file = os.path.join(LOG_DIR, "monitor.log")
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

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


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

    for asset, symbol in SYMBOL_MAP.items():
        print(f"\n  📡 获取 {asset} ({symbol}) 1H K线数据...")

        # 1. 获取 1H 数据
        hourly = fetch_klines_binance(symbol, "1h", 1000)
        if not hourly:
            print(f"    ❌ {asset} 数据获取失败")
            continue

        print(f"    ✓ {len(hourly['closes'])} 根 1H K线")

        # 2. 推导时间框架
        tf = derive_timeframes(hourly)
        print(f"    1H: {len(tf['tf1h']['closes'])} 根, "
              f"4H: {len(tf['tf4h']['closes'])} 根, "
              f"1D: {len(tf['tf1d']['closes'])} 根")

        # 3. 生成信号
        sig = generate_signal(tf["tf1h"], tf["tf4h"], tf["tf1d"])
        results[asset] = sig

        # 4. 日志输出
        log_signal(asset, sig)

        # 5. 判断是否需要通知
        if send_email and should_notify(asset, sig, state):
            print(f"    📧 触发通知条件，发送邮件...")
            try:
                from scripts.send_email import send_signal_email, is_configured
                if is_configured():
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
                        news_score=sig["newsScore"],
                    )
                    if success:
                        state[asset] = {
                            "sigClass": sig["sigClass"],
                            "direction": sig["direction"],
                            "totalScore": sig["totalScore"],
                            "lastNotified": time.time(),
                            "lastSignal": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                else:
                    print(f"    ⚠️ 邮件未配置（设置 AI_MONITOR_EMAIL_FROM 和 AI_MONITOR_EMAIL_PASSWORD 环境变量）")
            except ImportError:
                print(f"    ⚠️ 邮件模块导入失败")
            except Exception as e:
                print(f"    ❌ 邮件发送异常: {e}")
        elif not send_email:
            print(f"    🔇 跳过通知（邮件已禁用）")
        else:
            reason = "WAIT不通知" if sig["sigClass"] == "wait" else "未到通知间隔"
            print(f"    🔇 跳过通知（{reason}）")

        # 短暂休息避免 API 限速
        time.sleep(1)

    # 保存状态
    save_state(state)

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
