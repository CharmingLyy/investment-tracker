"""网络诊断脚本 - 检测各数据源连通性"""
import sys, io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=" * 50)
print("🔍 网络诊断")
print("=" * 50)

# 1. 测试 yfinance
print("\n[1/4] yfinance (港股/美股)...")
try:
    import yfinance as yf
    t = yf.Ticker("AAPL")
    hist = t.history(period="5d")
    if not hist.empty:
        price = hist["Close"].iloc[-1]
        print(f"  ✅ yfinance 正常 - AAPL: ${price:.2f}")
    else:
        print(f"  ❌ yfinance 返回空数据")
except Exception as e:
    print(f"  ❌ yfinance 失败: {str(e)[:120]}")

# 2. 测试 akshare (A股)
print("\n[2/4] akshare (A股-东方财富)...")
try:
    import akshare as ak
    # 尝试获取单只股票日线
    df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20260601", end_date="20260624", adjust="qfq")
    if not df.empty:
        price = df["收盘"].iloc[-1]
        print(f"  ✅ akshare 正常 - 平安银行: ¥{price:.2f}")
    else:
        print(f"  ❌ akshare 返回空数据")
except Exception as e:
    print(f"  ❌ akshare 失败: {str(e)[:120]}")

# 3. 测试 baostock (A股备用)
print("\n[3/4] baostock (A股备用)...")
try:
    import baostock as bs
    lg = bs.login()
    if lg.error_code == '0':
        rs = bs.query_history_k_data_plus("sh.601727", "date,close", start_date='2026-06-20', frequency="d")
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        if rows:
            print(f"  ✅ baostock 正常 - 上海电气: ¥{rows[-1][1]}")
        else:
            print(f"  ⚠ baostock 无数据（可能未交易日）")
    else:
        print(f"  ❌ baostock 登录失败")
except ImportError:
    print(f"  ⚠ baostock 未安装")
except Exception as e:
    print(f"  ❌ baostock 失败: {str(e)[:120]}")

# 4. 测试 CoinGecko
print("\n[4/4] CoinGecko (加密货币)...")
try:
    import requests
    resp = requests.get("https://api.coingecko.com/api/v3/ping", timeout=15)
    if resp.status_code == 200:
        print(f"  ✅ CoinGecko 正常")
    else:
        print(f"  ❌ CoinGecko 状态码: {resp.status_code}")
except Exception as e:
    print(f"  ❌ CoinGecko 失败: {str(e)[:120]}")

print("\n" + "=" * 50)
print("诊断完成 — 把以上输出发给我")
