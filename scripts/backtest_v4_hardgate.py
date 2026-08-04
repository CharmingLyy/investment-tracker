"""
V4 硬性门槛制回测 — 废除打分，三道硬闸过滤
==============================================

策略核心:
  【闸门 1】1H 趋势过滤: EMA50/EMA200 + RSI14 >/< 50
  【闸门 2】15min 入场 Setup: 回调至 EMA50 或 Spring/Upthrust 形态
  【闸门 3】OI + 量价方向绑定: Price↑+OI↑=主动开多, Price↓+OI↑=主动开空

风控:
  SL: max(Swing ± 0.2%, 1.2 × ATR_15m)
  TP1: 1.5 × Risk (平50%, 移保本)
  TP2: 2.5 × Risk 或 1H 前高/低
  时间止损: 16 × 15min (4小时)
  摩擦成本: 0.08%/笔 (0.04% taker + 滑点)

使用方式:
  python scripts/backtest_v4_hardgate.py
"""
import sys, os, time, io, json
from datetime import datetime, timedelta

import requests
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.monitor_crypto import (
    SMA, EMA, RSI, MACD, BB, ATR,
    generate_signal, find_swing_points,
    check_spring_pattern, check_upthrust_pattern,
    fetch_oi_15min,
)

# ============================================================
# 配置
# ============================================================

FRICTION_COST = 0.0008  # 0.08% 综合成本 (0.04% taker + 滑点)
POSITION_PCT_1 = 50     # TP1 平仓比例
TIME_STOP_BARS = 16     # 时间止损 (15min K线数 = 4小时)
TP1_R_MULT = 1.5        # TP1 = 1.5 × Risk
TP2_R_MULT = 2.5        # TP2 = 2.5 × Risk (上限)
SL_ATR_MULT = 1.2       # 止损 ATR 倍数

# ============================================================
# 数据获取
# ============================================================

def fetch_klines_paginated(symbol, interval, total_bars=3000):
    """分批获取历史 K 线数据"""
    all_data = []
    base_urls = [
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines",
        "https://api2.binance.com/api/v3/klines",
    ]

    limit = 1000
    end_time = None  # None = 最新

    for batch_idx in range(10):  # 最多 10 批次
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if end_time is not None:
            params["endTime"] = end_time

        for attempt in range(5):
            url = base_urls[attempt % len(base_urls)]
            try:
                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                klines = resp.json()
                if not klines or len(klines) < 2:
                    break
                all_data = klines + all_data  # 前面批次的数据在前面
                end_time = klines[0][0] - 1  # 下一批结束于这批第一条之前
                break
            except Exception as e:
                if attempt < 4:
                    time.sleep(3)
                else:
                    break

        if len(all_data) >= total_bars:
            break
        time.sleep(0.5)

    if len(all_data) < 200:
        print(f"    ⚠️ {interval} 数据不足 ({len(all_data)} 根)")
        return None

    all_data = all_data[-total_bars:]  # 取最近 total_bars 根

    return {
        "closes": [float(k[4]) for k in all_data],
        "highs": [float(k[2]) for k in all_data],
        "lows": [float(k[3]) for k in all_data],
        "volumes": [float(k[5]) for k in all_data],
        "timestamps": [k[0] / 1000 for k in all_data],
    }


def fetch_oi_15min_historical(symbol, limit=500):
    """获取 15min OI 历史（用于回测）"""
    try:
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/openInterestHist",
            params={"symbol": symbol, "period": "15m", "limit": limit},
            timeout=15
        )
        if resp.ok:
            data = resp.json()
            if data and len(data) >= 4:
                return {
                    "values": [float(d["sumOpenInterest"]) for d in data],
                    "timestamps": [d["timestamp"] / 1000 for d in data],
                }
    except Exception:
        pass
    return None


# ============================================================
# 交易模拟 (V4 规则)
# ============================================================

def simulate_trade_v4(entry, sl, tp1, tp2, direction, future_15m,
                      future_swings, friction=True):
    """
    V4 交易模拟:
      - TP1 触发: 平仓 50%, 止损移至保本 (entry)
      - TP2 触发: 平仓剩余 50%
      - 时间止损: 16 根后未触发 TP1 → 市价平仓
      - 摩擦成本: 0.08% 总成本
    """
    fh, fl = future_15m["highs"], future_15m["lows"]
    fc = future_15m["closes"]
    cost_rate = FRICTION_COST if friction else 0

    tp1_hit = False
    tp1_bar = -1
    breakeven_active = False

    for i in range(len(fh)):
        bar_high, bar_low = fh[i], fl[i]

        if direction == 'bullish':
            # 先检查止损
            current_sl = entry if breakeven_active else sl
            if bar_low <= current_sl:
                exit_price = current_sl
                if tp1_hit:
                    # 50% 在 TP1 已出, 50% 在保本/止损出
                    pnl_pct1 = (tp1 - entry) / entry - cost_rate
                    pnl_pct2 = (exit_price - entry) / entry - cost_rate
                    pnl_pct = 0.5 * pnl_pct1 + 0.5 * pnl_pct2
                    return {"result": "win" if pnl_pct > 0 else "loss",
                            "bars": i + 1, "exitPrice": exit_price,
                            "pnlPct": pnl_pct * 100,
                            "tp1_hit": True, "tp1_bar": tp1_bar,
                            "timeout": False}
                else:
                    pnl_pct = (exit_price - entry) / entry - cost_rate
                    return {"result": "loss", "bars": i + 1,
                            "exitPrice": exit_price,
                            "pnlPct": pnl_pct * 100,
                            "tp1_hit": False, "timeout": False}

            # TP2 触发
            if tp1_hit and bar_high >= tp2:
                # 50% 在 TP1 已出, 50% 在 TP2 出
                pnl_pct1 = (tp1 - entry) / entry - cost_rate
                pnl_pct2 = (tp2 - entry) / entry - cost_rate
                pnl_pct = 0.5 * pnl_pct1 + 0.5 * pnl_pct2
                return {"result": "win", "bars": i + 1,
                        "exitPrice": tp2,
                        "pnlPct": pnl_pct * 100,
                        "tp1_hit": True, "tp1_bar": tp1_bar,
                        "tp2_hit": True, "timeout": False}

            # TP1 触发
            if not tp1_hit and bar_high >= tp1:
                tp1_hit = True
                tp1_bar = i + 1
                breakeven_active = True
                # 不立即退出, 继续检查 TP2/止损

        else:  # bearish
            current_sl = entry if breakeven_active else sl
            if bar_high >= current_sl:
                exit_price = current_sl
                if tp1_hit:
                    pnl_pct1 = (entry - tp1) / entry - cost_rate
                    pnl_pct2 = (entry - exit_price) / entry - cost_rate
                    pnl_pct = 0.5 * pnl_pct1 + 0.5 * pnl_pct2
                    return {"result": "win" if pnl_pct > 0 else "loss",
                            "bars": i + 1, "exitPrice": exit_price,
                            "pnlPct": pnl_pct * 100,
                            "tp1_hit": True, "tp1_bar": tp1_bar,
                            "timeout": False}
                else:
                    pnl_pct = (entry - exit_price) / entry - cost_rate
                    return {"result": "loss", "bars": i + 1,
                            "exitPrice": exit_price,
                            "pnlPct": pnl_pct * 100,
                            "tp1_hit": False, "timeout": False}

            if tp1_hit and bar_low <= tp2:
                pnl_pct1 = (entry - tp1) / entry - cost_rate
                pnl_pct2 = (entry - tp2) / entry - cost_rate
                pnl_pct = 0.5 * pnl_pct1 + 0.5 * pnl_pct2
                return {"result": "win", "bars": i + 1,
                        "exitPrice": tp2,
                        "pnlPct": pnl_pct * 100,
                        "tp1_hit": True, "tp1_bar": tp1_bar,
                        "tp2_hit": True, "timeout": False}

            if not tp1_hit and bar_low <= tp1:
                tp1_hit = True
                tp1_bar = i + 1
                breakeven_active = True

        # 时间止损: 16 根后未触发 TP1 → 市价平仓
        if i + 1 >= TIME_STOP_BARS and not tp1_hit:
            exit_price = fc[i] if i < len(fc) else (fh[i] + fl[i]) / 2
            pnl_pct = (exit_price - entry) / entry - cost_rate if direction == 'bullish' \
                else (entry - exit_price) / entry - cost_rate
            return {"result": "win" if pnl_pct > 0 else "loss",
                    "bars": i + 1, "exitPrice": exit_price,
                    "pnlPct": pnl_pct * 100,
                    "tp1_hit": False, "timeout": True}

    # 数据用完, 未触及任何止盈止损 → 市价平仓
    if len(fh) > 0:
        last_close = fc[-1] if fc else (fh[-1] + fl[-1]) / 2
        if tp1_hit:
            pnl_pct1 = (tp1 - entry) / entry if direction == 'bullish' else (entry - tp1) / entry
            pnl_pct2 = (last_close - entry) / entry if direction == 'bullish' else (entry - last_close) / entry
            pnl_pct = (0.5 * pnl_pct1 + 0.5 * pnl_pct2) - cost_rate
        else:
            pnl_pct = (last_close - entry) / entry if direction == 'bullish' else (entry - last_close) / entry
            pnl_pct -= cost_rate
        return {"result": "win" if pnl_pct > 0 else "loss",
                "bars": len(fh), "exitPrice": last_close,
                "pnlPct": pnl_pct * 100,
                "tp1_hit": tp1_hit, "timeout": True}
    return None


# ============================================================
# 数据准备: 1H 和 15min 时间对齐
# ============================================================

def prepare_timeframes(h1_data, m15_data, oi_data=None):
    """
    从原始 1H 和 15min 数据推导决策所需的时间框架
    返回 dict 包含对齐后的数据
    """
    h1_c, h1_h, h1_l = h1_data["closes"], h1_data["highs"], h1_data["lows"]
    h1_ts = h1_data["timestamps"]
    m15_c, m15_h, m15_l = m15_data["closes"], m15_data["highs"], m15_data["lows"]
    m15_ts = m15_data["timestamps"]

    oi_vals = oi_data["values"] if oi_data else None
    oi_ts = oi_data["timestamps"] if oi_data else None

    return {
        "h1_c": h1_c, "h1_h": h1_h, "h1_l": h1_l, "h1_ts": h1_ts,
        "m15_c": m15_c, "m15_h": m15_h, "m15_l": m15_l, "m15_ts": m15_ts,
        "oi_vals": oi_vals, "oi_ts": oi_ts,
    }


def slice_at_1h_index(data, h1_idx):
    """在给定的 1H 索引处切片数据，对齐 15min"""
    # 1H 切片: 包含 h1_idx 及之前所有数据
    h1_slice = {
        "closes": data["h1_c"][:h1_idx + 1],
        "highs": data["h1_h"][:h1_idx + 1],
        "lows": data["h1_l"][:h1_idx + 1],
    }

    # 15min 对齐: 找到时间戳 <= 1H 当前时间的最新 15min bar
    ref_ts = data["h1_ts"][h1_idx]
    m15_idx = None
    for j in range(len(data["m15_ts"]) - 1, -1, -1):
        if data["m15_ts"][j] <= ref_ts:
            m15_idx = j
            break

    if m15_idx is None or m15_idx < 50:
        return None  # 15min 数据不足

    m15_slice = {
        "closes": data["m15_c"][:m15_idx + 1],
        "highs": data["m15_h"][:m15_idx + 1],
        "lows": data["m15_l"][:m15_idx + 1],
    }

    # OI 对齐
    oi_slice = None
    if data["oi_vals"] and data["oi_ts"]:
        oi_m15_idx = None
        for j in range(len(data["oi_ts"]) - 1, -1, -1):
            if data["oi_ts"][j] <= ref_ts:
                oi_m15_idx = j
                break
        if oi_m15_idx is not None and oi_m15_idx >= 4:
            oi_slice = data["oi_vals"][:oi_m15_idx + 1]

    return {"tf1h": h1_slice, "tf15m": m15_slice, "oi": oi_slice, "m15_idx": m15_idx}


# ============================================================
# 主回测
# ============================================================

def run_backtest_v4(asset, symbol, total_1h_bars=1500):
    """V4 策略回测"""
    print(f"\n{'═' * 70}")
    print(f"  🔬 {asset} V4 硬性门槛制回测")
    print(f"{'═' * 70}")

    # 1. 获取数据
    print("  [1/4] 获取历史数据...")
    h1_data = fetch_klines_paginated(symbol, "1h", total_1h_bars)
    m15_data = fetch_klines_paginated(symbol, "15m", 1500)

    if not h1_data or not m15_data:
        print(f"  ❌ 数据获取失败")
        return None

    print(f"    1H: {len(h1_data['closes'])} 根, "
          f"{datetime.fromtimestamp(h1_data['timestamps'][0]).strftime('%m-%d %H:%M')} ~ "
          f"{datetime.fromtimestamp(h1_data['timestamps'][-1]).strftime('%m-%d %H:%M')}")
    print(f"    15min: {len(m15_data['closes'])} 根, "
          f"{datetime.fromtimestamp(m15_data['timestamps'][0]).strftime('%m-%d %H:%M')} ~ "
          f"{datetime.fromtimestamp(m15_data['timestamps'][-1]).strftime('%m-%d %H:%M')}")

    # OI 数据
    print(f"    获取 15min OI 历史...")
    oi_data = fetch_oi_15min_historical(symbol, limit=500)
    if oi_data:
        print(f"    OI: {len(oi_data['values'])} 个快照 ({datetime.fromtimestamp(oi_data['timestamps'][0]).strftime('%m-%d %H:%M')} ~ {datetime.fromtimestamp(oi_data['timestamps'][-1]).strftime('%m-%d %H:%M')})")
    else:
        print(f"    OI: 不可用 (跳过 OI 确认)")

    # 2. 准备数据
    print(f"  [2/4] 时间对齐...")
    data = prepare_timeframes(h1_data, m15_data, oi_data)

    # 决策点: 1H 级别的每个 bar（需要足够的历史数据）
    MIN_1H_BARS = 250  # 需要 EMA200
    n_h1 = len(data["h1_c"])
    decision_indices = list(range(MIN_1H_BARS, n_h1 - 20, 4))  # 每 4H 决策
    print(f"    决策点: {len(decision_indices)} 个 (每 4H 一次)")

    # 3. 运行回测
    print(f"  [3/4] 运行回测...")
    trades = []
    waits = []
    signals_generated = 0

    for idx in decision_indices:
        sliced = slice_at_1h_index(data, idx)
        if sliced is None:
            continue

        # 推导 4H 时间框架
        h1_raw = {"closes": sliced["tf1h"]["closes"],
                  "highs": sliced["tf1h"]["highs"],
                  "lows": sliced["tf1h"]["lows"]}
        tf4h = derive_4h(h1_raw)

        # 准备 15min 数据给 V4
        data_15m = sliced["tf15m"]
        oi_list = sliced.get("oi")

        signals_generated += 1

        # 调用 V4 信号引擎
        sig = generate_signal(
            sliced["tf1h"], tf4h, None,
            asset=asset, data_15m=data_15m,
            oi_15m=oi_list,
        )

        if sig["sigClass"] == "wait":
            waits.append({
                "reason": sig.get("trendSummary", ""),
                "date": datetime.fromtimestamp(data["h1_ts"][idx]).strftime('%m-%d %H:%M'),
            })
            continue

        # 准备未来数据用于模拟 (最多 48 根 15min = 12 小时)
        m15_idx = sliced["m15_idx"]
        future_15m = {
            "highs": data["m15_h"][m15_idx + 1:m15_idx + 49],
            "lows": data["m15_l"][m15_idx + 1:m15_idx + 49],
            "closes": data["m15_c"][m15_idx + 1:m15_idx + 49],
        }

        if len(future_15m["highs"]) < 2:
            continue

        # 模拟交易 (V4 规则)
        outcome = simulate_trade_v4(
            sig["entryPrice"], sig["stopLoss"],
            sig["takeProfit1"], sig["takeProfit2"],
            sig["direction"],
            future_15m, None,
            friction=True,
        )

        if outcome:
            trades.append({
                "date": datetime.fromtimestamp(data["h1_ts"][idx]).strftime('%m-%d %H:%M'),
                "direction": sig["direction"],
                "entry": sig["entryPrice"],
                "sl": sig["stopLoss"],
                "tp1": sig["takeProfit1"],
                "tp2": sig["takeProfit2"],
                "rr": sig["rrRatio"],
                "gate1": sig.get("v4_gate1_env", ""),
                "gate2": sig.get("v4_gate2_entry", ""),
                "gate3": sig.get("v4_gate3_oi", ""),
                "result": outcome["result"],
                "pnlPct": outcome["pnlPct"],
                "bars": outcome["bars"],
                "exitPrice": outcome["exitPrice"],
                "tp1_hit": outcome.get("tp1_hit", False),
                "tp2_hit": outcome.get("tp2_hit", False),
                "timeout": outcome.get("timeout", False),
            })

        if len(trades) % 25 == 0 and len(trades) > 0:
            print(f"    已模拟 {len(trades)} 笔交易...")

    # 4. 统计
    print(f"  [4/4] 统计分析...")

    if not trades:
        print(f"  ❌ 无交易信号生成")
        print(f"     {signals_generated} 个决策点, {len(waits)} 个观望")
        return None

    stats = compute_stats(trades)

    # 5. 输出
    print_results(asset, trades, stats, waits, signals_generated, data)

    return {"asset": asset, "trades": trades, "stats": stats}


def derive_4h(h1_data):
    """从 1H 数据推导 4H"""
    c, h, l = h1_data["closes"], h1_data["highs"], h1_data["lows"]
    n = len(c)
    h4c, h4h, h4l = [], [], []
    for i in range(max(0, n - 336), n, 4):
        end = min(i + 4, n)
        h4c.append(c[end - 1])
        h4h.append(max(h[i:end]))
        h4l.append(min(l[i:end]))
    return {"closes": h4c, "highs": h4h, "lows": h4l}


# ============================================================
# 统计计算
# ============================================================

def compute_stats(trades):
    """计算回测统计指标"""
    if not trades:
        return None

    wins = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    total = len(wins) + len(losses)

    win_rate = len(wins) / total * 100 if total > 0 else 0
    avg_win = sum(t["pnlPct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(abs(t["pnlPct"]) for t in losses) / len(losses) if losses else 0
    pf = (avg_win * len(wins)) / (avg_loss * len(losses)) if avg_loss > 0 else (float('inf') if len(wins) > 0 else 0)

    # 累计收益（复合）
    cumulative = 1.0
    for t in trades:
        cumulative *= (1 + t["pnlPct"] / 100)
    total_return = (cumulative - 1) * 100

    # 最大回撤
    peak = 0
    mdd = 0
    equity = 1.0
    for t in trades:
        equity *= (1 + t["pnlPct"] / 100)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        if dd > mdd:
            mdd = dd

    # 年化收益
    if trades:
        first_date = datetime.strptime(trades[0]["date"], '%m-%d %H:%M')
        last_date = datetime.strptime(trades[-1]["date"], '%m-%d %H:%M')
        # 估算年数（跨年可能不准确，但 1H 数据跨度 < 1 年，使用天数近似）
        days_span = max((last_date - first_date).days, 1)
        years = days_span / 365
        ann_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100 if years > 0 else 0
    else:
        ann_return = 0
        years = 0

    # 最大连续亏损
    max_cl = 0
    cur_cl = 0
    for t in trades:
        if t["result"] == "loss":
            cur_cl += 1
            max_cl = max(max_cl, cur_cl)
        else:
            cur_cl = 0

    # 平均持仓时间 (15min bars → 小时)
    avg_bars = sum(t["bars"] for t in trades) / len(trades) if trades else 0
    avg_hours = avg_bars * 0.25

    # 长/短统计
    longs = [t for t in trades if t["direction"] == "bullish"]
    shorts = [t for t in trades if t["direction"] == "bearish"]
    long_wins = [t for t in longs if t["result"] == "win"]
    short_wins = [t for t in shorts if t["result"] == "win"]

    return {
        "total": total,
        "wins": len(wins), "losses": len(losses),
        "win_rate": win_rate,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "profit_factor": pf,
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": mdd,
        "max_consecutive_losses": max_cl,
        "avg_bars": avg_bars, "avg_hours": avg_hours,
        "timeout_trades": sum(1 for t in trades if t.get("timeout")),
        "long_count": len(longs), "long_wr": len(long_wins) / len(longs) * 100 if longs else 0,
        "short_count": len(shorts), "short_wr": len(short_wins) / len(shorts) * 100 if shorts else 0,
        "tp1_hit_count": sum(1 for t in trades if t.get("tp1_hit")),
        "tp2_hit_count": sum(1 for t in trades if t.get("tp2_hit")),
    }


# ============================================================
# 输出
# ============================================================

def print_results(asset, trades, stats, waits, signals_generated, data):
    """打印回测结果"""
    print(f"\n{'═' * 70}")
    print(f"  📊 {asset} V4 回测结果")
    print(f"{'═' * 70}")

    print(f"\n  【综合指标】")
    print(f"  {'─' * 50}")
    print(f"  总交易数:        {stats['total']}")
    print(f"  盈利 / 亏损:     {stats['wins']} / {stats['losses']}")
    print(f"  胜率:            {stats['win_rate']:.1f}%")
    print(f"  平均盈利:        {stats['avg_win']:+.2f}%")
    print(f"  平均亏损:        {stats['avg_loss']:.2f}%")
    pf_str = "∞" if stats['profit_factor'] == float('inf') else f"{stats['profit_factor']:.2f}"
    print(f"  获利因子 (PF):   {pf_str}")
    print(f"  累计收益率:      {stats['total_return']:+.2f}%")
    print(f"  年化收益率:      {stats['annualized_return']:+.2f}%")
    print(f"  最大回撤 (MDD):  {stats['max_drawdown']:.2f}%")
    print(f"  最大连续亏损:    {stats['max_consecutive_losses']} 次")
    print(f"  平均持仓时间:    {stats['avg_bars']:.0f} 根15min ({stats['avg_hours']:.1f}h)")
    print(f"  超时平仓:        {stats['timeout_trades']} 笔")
    print(f"  TP1 触发:        {stats['tp1_hit_count']} 笔")
    print(f"  TP2 触发:        {stats['tp2_hit_count']} 笔")

    print(f"\n  【多空统计】")
    print(f"  做多: {stats['long_count']} 笔, 胜率 {stats['long_wr']:.1f}%")
    print(f"  做空: {stats['short_count']} 笔, 胜率 {stats['short_wr']:.1f}%")

    # 信号分析
    print(f"\n  【信号分析】")
    print(f"  总决策点: {signals_generated}")
    print(f"  交易信号: {stats['total']} ({stats['total']/signals_generated*100:.1f}%)" if signals_generated else "")
    print(f"  观望信号: {len(waits)} ({len(waits)/signals_generated*100:.1f}%)" if signals_generated else "")

    # 闸门拒绝原因 Top 5
    if waits:
        from collections import Counter
        reasons = Counter(w["reason"] for w in waits)
        print(f"  Top 5 观望原因:")
        for reason, count in reasons.most_common(5):
            print(f"    - [{count:>4}次] {reason}")

    # 最近 15 笔交易
    if trades:
        recent = trades[-15:]
        print(f"\n  【最近 15 笔交易】")
        print(f"  {'日期':<12} {'方向':<6} {'入场':>10} {'出场':>10} {'盈亏':>8} {'K线':>4} {'TP1':>4} {'结果':<6}")
        print(f"  {'─' * 75}")
        for t in recent:
            dir_str = "多" if t["direction"] == "bullish" else "空"
            entry_fmt = f"${t['entry']:,.0f}" if t['entry'] >= 100 else f"${t['entry']:,.2f}"
            exit_fmt = f"${t['exitPrice']:,.0f}" if t['exitPrice'] >= 100 else f"${t['exitPrice']:,.2f}"
            tp1_str = "✓" if t.get("tp1_hit") else "—"
            emoji = "✅" if t["result"] == "win" else "❌"
            timeout_str = " ⏰" if t.get("timeout") else ""
            print(f"  {t['date']:<12} {dir_str:<6} {entry_fmt:>10} {exit_fmt:>10} "
                  f"{t['pnlPct']:>+7.2f}% {t['bars']:>4}{timeout_str} {tp1_str:>4} {emoji:<6}")

    # 结论
    print(f"\n  {'═' * 50}")
    buy_hold = ((data["h1_c"][-1] - data["h1_c"][250]) / data["h1_c"][250] * 100)
    print(f"  📌 V4 硬性门槛制结论:")
    print(f"     交易 {stats['total']} 笔 | 胜率 {stats['win_rate']:.1f}% | PF {pf_str}")
    print(f"     累计 {stats['total_return']:+.2f}% | 买入持有 {buy_hold:+.2f}%")
    if stats['total'] >= 150:
        print(f"     ✅ 样本量充足 ({stats['total']} 笔)")
    else:
        print(f"     ⚠️ 样本量不足 ({stats['total']} 笔 < 150), 结果仅供参考")
    print(f"     摩擦成本: {FRICTION_COST*100:.2f}% / 笔")
    print()


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("🔬 V4 硬性门槛制 — 回测报告")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   摩擦成本: {FRICTION_COST*100:.2f}% / 笔")
    print(f"   策略: 1H趋势过滤 → 15min入场Setup → OI量价绑定")
    print(f"   风控: SL(max(Swing±0.2%, 1.2×ATR)) | TP1(1.5R,50%) | TP2(2.5R) | 时间止损(4H)")
    print("=" * 70)

    assets = [("BTC", "BTCUSDT"), ("ETH", "ETHUSDT")]
    all_results = []

    for name, sym in assets:
        result = run_backtest_v4(name, sym)
        if result:
            all_results.append(result)
        time.sleep(2)

    # 综合对比
    if len(all_results) >= 2:
        print(f"\n{'═' * 70}")
        print(f"  ⚖️  BTC vs ETH 对比")
        print(f"{'═' * 70}")
        print(f"  {'指标':<20} {'BTC':>15} {'ETH':>15}")
        print(f"  {'─' * 50}")
        metrics = [
            ("交易数", "total"),
            ("胜率", "win_rate"),
            ("PF", "profit_factor"),
            ("累计收益", "total_return"),
            ("年化收益", "annualized_return"),
            ("最大回撤", "max_drawdown"),
            ("最大连亏", "max_consecutive_losses"),
            ("平均持仓(h)", "avg_hours"),
        ]
        for label, key in metrics:
            vals = []
            for r in all_results:
                s = r["stats"]
                v = s.get(key, 0)
                if key == "win_rate":
                    vals.append(f"{v:.1f}%")
                elif key == "total_return" or key == "annualized_return" or key == "max_drawdown":
                    vals.append(f"{v:+.2f}%")
                elif key == "profit_factor":
                    vals.append(f"{v:.2f}" if v != float('inf') else "∞")
                elif key == "avg_hours":
                    vals.append(f"{v:.1f}h")
                else:
                    vals.append(f"{v}")
            print(f"  {label:<20} {vals[0]:>15} {vals[1]:>15}")
        print()

    print("✅ V4 回测完成")
