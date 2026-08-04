# TODO — AI 投资观察面板

> 最后更新: 2026-08-04 (🔥 信号引擎 V4: 硬性门槛制)

---

## ✅ 今日完成 (2026-08-04) — 🔥 信号引擎 V4: 硬性门槛制

### 背景

用户要求废除 V1-V3 的凑分逻辑，改为三道硬性闸门过滤：

【闸门 1】1H 大周期趋势过滤
- 做多环境: 1H Close > EMA50 > EMA200 且 1H RSI(14) > 50
- 做空环境: 1H Close < EMA50 < EMA200 且 1H RSI(14) < 50
- 均线纠缠/价格在均线之间 → 一票否决，不生成信号

【闸门 2】15min 入场 Setup
- 做多: 回调至 15min EMA50 (偏离<0.3%) 或 Spring 形态(跌破前低后收回)
- 做空: 反弹至 15min EMA50 (偏离<0.3%) 或 Upthrust 形态(突破前高后收回)

【闸门 3】OI + 量价方向绑定
- 做多: 最近3根15min K线中 Price↑+OI↑ → 主动开多
- 做空: 最近3根15min K线中 Price↓+OI↑ → 主动开空
- 拒绝: 价格涨但OI降(空头平仓驱动)、价格跌但OI降(多头平仓驱动)

【风控】
- SL: max(Swing ± 0.2%, 1.2 × ATR_15m) — 取更宽止损防插针
- TP1: 1.5 × Risk (平50%, 移保本)
- TP2: 2.5 × Risk 或 1H 前高/低阻力位 (平剩余50%)
- 时间止损: 16根15min (4小时) 未触发 TP1 → 市价平仓
- 摩擦成本: 0.08%/笔 (0.04% taker + 滑点)

### 修改的文件

| 文件 | 改动 |
|------|------|
| `scripts/monitor_crypto.py` | `generate_signal()` — V4 完全重写: 三道硬闸过滤、新风控规则; 新增 `find_swing_points()` / `check_spring_pattern()` / `check_upthrust_pattern()` / `_make_wait_signal()` / `_classify_regime_text()` / `_check_oi_confirmation()` 辅助函数; 新增 `fetch_oi_15min()` — 15min OI 历史数据获取; `run_detection()` — 新增 15min OI 获取步骤; `log_signal()` — 适配 V4 格式 |
| `scripts/send_email.py` | HTML 邮件模板重写: 评分栏→三道闸门状态栏; 新增时间止损/防插针说明; 总评分显示移除 |
| `scripts/backtest_v4_hardgate.py` | 新增: V4 完整回测引擎 (~650行) — 分批数据获取、时间对齐、V4 交易模拟(两段止盈+保本+时间止损+摩擦成本)、综合统计(年化/PF/MDD/多空胜率)、闸门拒绝原因分析 |

### ⚠️ 首次回测结果 (2026-08-04)

**数据范围**: 1H: 2026-06-03 ~ 08-04 (1500根), 15min: 2026-07-19 ~ 08-04 (1500根)

| 指标 | BTC | ETH |
|------|:--:|:--:|
| 交易数 | 27 | 22 |
| 胜率 | 29.6% | 22.7% |
| PF | 0.23 | 0.21 |
| 累计收益 | -6.08% | -8.15% |
| 年化收益 | -82.82% | -90.80% |
| 最大回撤 | 5.86% | 7.37% |
| 平均持仓 | 3.0h | 2.5h |
| 超时平仓率 | 48% | 36% |
| TP1 触发率 | 15% | 14% |
| 观望率 | 68.6% | 74.4% |

**主要问题诊断**:

1. **#1 数据窗口太短 (10天15min数据)** — 仅10天数据产生27笔交易，远不足150笔目标。1H数据覆盖2个月但15min只有10天。Binance 15min K线单次最多1000根。
2. **#2 1H EMA50/EMA200 趋势过滤太严格** — 68-74%的决策点被拒于闸门1。均线纠缠和EMA50/200关系矛盾占观望原因的30%+。
3. **#3 15min 入场Setup 太窄** — 0.3% EMA50偏离阈值在加密市场波动下极难命中。闸门2是最大的拒绝原因(占观望的50%+)。
4. **#4 时间止损 4H 过短** — 48%的BTC交易因时间止损出场，TP1在4H内难以触及。
5. **#5 OI数据不可用在回测中** — Binance `openInterestHist` 15min粒度数据回测中获取失败，闸门3在回测中完全跳过。
6. **#6 平均亏损(0.43-0.62%) 远超平均盈利(0.24-0.44%)** — R:R严重失衡。

### 🔧 建议的参数优化方向

| 参数 | 当前值 | 建议调整 |
|------|:--:|------|
| 15min EMA50 偏离阈值 | 0.3% | → 0.5%-0.8% |
| 时间止损 | 16根(4H) | → 24-32根(6-8H) |
| TP1 R倍数 | 1.5× | → 1.2× (更容易触发TP1移保本) |
| 1H RSI阈值 | 50 | → 45/55 (略微放松) |
| EMA50/EMA200纠缠阈值 | 1% | → 0.5% (更多识别为纠缠而非矛盾) |

### 不需要做的

- 不要回到打分制 — 硬性门槛的方向是对的，只是参数需要校准
- 不要删除 OI 闸门 — 生产环境中 OI 数据可用，回测中缺失是数据获取问题

### V3 vs V4 架构对比

```
V3 (打分制):                      V4 (硬性门槛制):
  15min EMA → 10pts                 闸门1: 1H EMA50/200 + RSI → 一票否决
  1H/4H 趋势 → 12pts                闸门2: 15min Setup → 必须满足
  15min MACD → 12pts                闸门3: OI+量价绑定 → 必须满足
  1H MACD → 8pts                    SL: max(Swing, 1.2ATR)
  15min RSI → 8pts                  TP1: 1.5R (50%平)
  1H RSI → 6pts                     TP2: 2.5R or 1H S/R
  波动率 → 9pts                     时间止损: 4H
  基本面 → 20pts                    摩擦成本: 0.08%
  ─────────────────
  总分85, 阈值58
```



## ✅ 今日完成 (2026-07-26) — 🔥 信号引擎优化：去除日线框架

### 背景

用户在做 1-3 天短线交易，质疑日线框架是否合理。

### 三轮回测结果

**回测环境**: Binance 1H K线, ~3000 根 (~125天), 每 4H 决策一次, 最多持仓 24H

#### 第一轮：有日线 vs 纯无日线

| 指标 | BTC 有日线 | BTC 无日线 | ETH 有日线 | ETH 无日线 |
|------|:--:|:--:|:--:|:--:|
| 交易数 | 148 | 133 | 161 | 178 |
| 胜率 | 61.5% | **62.4%** | 62.7% | 61.2% |
| PF | 1.45 | **1.57** | 1.17 | **1.26** |
| 累计收益 | +35.73% | **+37.58%** | +17.21% | **+25.60%** |
| 最大连亏 | 9次 | **4次** | - | - |

**结论**: 去掉日线后 BTC 全面改善, ETH 收益提升近 50%。

#### 第二轮：V1 vs V2（全量重构：+量价+背离+BB挤压）

- V2 阈值 60/100 时信号量暴增 2.4x, 收益虽高但质量下降
- V2 阈值 65/100 时完全不如 V1
- **结论**: 全新因子（量价、背离）效果不稳定，BTC 甚至退步

#### 第三轮：V1 vs V2 vs V2b（保守改进）

- V2b (V1骨架+去日线+量价微调+背离微调): ETH 有改善, BTC 退步
- **结论**: 量价和背离作为新因子在加密市场不稳定

### 最终方案：最小化改动

**只去掉日线，保留 V1 已验证的评分结构**：

1. ❌ 移除日线 — `trend_score = trend1h + trend4h`（原 `trend1h + trend4h + trendD`）
2. 🔧 方向阈值: `≥2 bullish / ≤-2 bearish`（原 `≥3 / ≤-3`）
3. 🔧 趋势一致性分数: 两个框架各 9 分（原 7+7+6=20 分分给三个框架）
4. ✅ 其他所有评分维度保持不变（80分制, 阈值 55）
5. ✅ 成交量提取已加入数据管道（`fetch_klines_binance` 现在也返回 `volumes`）

### 修改的文件

| 文件 | 改动 |
|------|------|
| `scripts/monitor_crypto.py` | `fetch_klines_binance()` — 新增 `volumes` 字段; `derive_timeframes()` — 4H/1D 聚合成交量; `generate_signal()` — V2 重写: 去日线+保留V1评分结构; `log_signal()` — 评分格式还原 80 分制; `send_signal_email()` 调用 — 适配新字段 |
| `scripts/send_email.py` | 评分显示还原 80 分制 |
| `scripts/backtest_compare_timeframes.py` | 新增: V1有/无日线对比回测 |
| `scripts/backtest_v1_vs_v2.py` | 新增: V1 vs V2 vs V2b 三版本对比 |

### 不需要做的

- ⬜ 量价因子 — 回测证实不稳定, 暂不加入
- ⬜ RSI 背离 — 同样不稳定
- ⬜ BB 挤压 — 效果不明显
- 这些因子可以后续单独回测优化后再考虑加入

### 新因子研究（已回测验证）

以下因子经过了系统性回测验证：

| 改进方向 | 方法 | 结果 | 结论 |
|----------|------|------|------|
| **15min 主框架** ✅ | 15min EMA/MACD/RSI 直接参与评分 | BTC 收益 +95%, ETH 收益 +80% | **已采纳 → V3** |
| 15min 过滤器 | 15min MACD 不满足就过滤 | 过滤太多好交易，收益 -18% | ❌ 不用 |
| 自适应 ATR | 高波动紧止损，低波动宽止损 | 胜率 -10%, 收益 -60% | ❌ 不用 |
| ADX 市场分类 | 趋势/震荡/过渡三种状态切换 | 过滤太狠，收益 -54% | ❌ 不用 |
| 量价因子 | 放量加分+量价方向一致性 | BTC 退步, ETH 不稳定 | ❌ 不用 |
| RSI 背离 | 价格与RSI的背离检测 | 效果不稳定 | ❌ 不用 |
| BB 挤压 | 带宽收窄加分 | 触发频率太低 | ❌ 不用 |

**核心发现**：
- ✅ **15min 作为评分维度（不是过滤器）**是唯一有效的改进，因为它提供了更细颗粒度的信息而不减少交易机会
- ❌ 任何形式的"过滤器"都会牺牲交易机会，被过滤的交易中往往包含大量盈利
- ❌ 自适应参数（ATR、状态切换）在短线尺度上过度拟合，固定参数更稳健
- 🧠 **简洁胜过复杂** — 当前策略的简单结构（趋势+Momentum+RSI+波动率+基本面）已经很好，每个新维度都要经过严格验证才能加入

---

## ✅ 今日完成 (2026-07-26) — 🔥 信号引擎 V3: 15min 主框架

### 背景

用户质疑只用 1H/4H 是否够精细，提出用 15min 作为主要判断标准。

### 回测验证

**回测环境**: Binance 15min + 1H K线, ~160 决策点, 对比 V2(1H主) vs V3(15min主)

| 指标 | BTC V2 | BTC V3 | ETH V2 | ETH V3 |
|------|:--:|:--:|:--:|:--:|
| 交易数 | 6 | **14** | 10 | **16** |
| 胜率 | 83.3% | 78.6% | 60.0% | **75.0%** |
| PF | 5.01 | 4.86 | 1.76 | **1.78** |
| **累计收益** | +4.73% | **+9.23%** | +2.88% | **+5.20%** |
| **提升幅度** | — | **+95%** | — | **+80%** |

### 关键设计

1. **15min 是评分维度不是过滤器** — 直接参与打分（10分微趋势+12分MACD+8分RSI），不像之前做门卫
2. **15min 数据不可用时自动降级** — GitHub Actions 如果获取不到 15min 数据，自动回到 1H 主框架模式
3. **三层权重**: 15min(±3) > 1H(±2) > 4H(±1)，微框架主导但大方向不丢

### V3 评分体系 (85分制, 阈值58)

| 维度 | 分数 | 说明 |
|------|:--:|------|
| 15min 微趋势 | 10 | EMA9/21 排列 + 发散度 |
| 1H+4H 背景趋势 | 12 | 大方向确认 |
| 15min MACD | 12 | 微动量信号 |
| 1H MACD | 8 | 主动量确认 |
| 15min RSI | 8 | 微超买超卖 |
| 1H RSI | 6 | 主超买超卖 |
| 1H 波动率 | 9 | ATR 适中检查 |
| 基本面 | 20 | 资金费率+OI |
| **合计** | **85** | |

### 修改的文件

| 文件 | 改动 |
|------|------|
| `scripts/monitor_crypto.py` | `generate_signal()` — V3 重写: 新增 `data_15m` 参数, 15min EMA/MACD/RSI 直接参与评分; `fetch_klines_binance()` — 多端点轮换 (api1/api2/api3); `run_detection()` — 新增 15min 数据获取步骤; 15min 数据不可用时自动降级 |
| `scripts/backtest_v3_15min.py` | 新增: V2 vs V3 对比回测 |

---

## ✅ 今日完成 (2026-07-26) — 🔧 每日简报 API Key / 参数修复

### 问题诊断

用户的每日硬核情报简报（`daily_briefing.py`）最近可能无法正常 AI 策展，回退到了启发式模式。排查发现 **3 个根因**：

### 根因 1：`temperature=0.85` 导致 Anthropic 备用 API 报 400 🔴

Claude Sonnet 5 **拒绝非默认的 `temperature` / `top_p` / `top_k` 值**（与 Opus 4.7+ 相同的 API 约束）。代码在 SDK 和 HTTP 两处 Anthropic 调用中传了 `temperature=0.85`，导致备用 API 每次调用都返回 400 错误。

**影响链**：
```
DeepSeek 主 API 挂了（余额用尽？）
  → 尝试 Anthropic 备用 API
    → temperature=0.85 → 400 错误 → 备用也挂了
      → 回退到启发式模式（没有 AI 毒舌点评）
```

**修复**：从 `_curate_with_claude_api()` 的 SDK 调用和 HTTP 调用两处移除 `temperature` 参数。DeepSeek API 仍保留 `temperature=0.85`（DeepSeek API 支持该参数）。

### 根因 2：`anthropic` 包被注释掉 🔴

`requirements.txt` 中 `anthropic>=0.30.0` 被注释为 `# anthropic>=0.30.0`，导致 GitHub Actions 环境中不安装 Anthropic SDK。虽然代码有 HTTP 回退路径，但 SDK 调用是优先路径，`ImportError` 后落到 HTTP 路径（同样受根因 1 影响）。

**修复**：取消注释，改为 `anthropic>=0.30.0`。

### 根因 3：错误诊断信息不够详细 🟡

原来的错误信息只打印 HTTP 状态码和响应前 200 字符，无法快速判断 API Key 是否过期、余额是否不足。

**修复**：
- DeepSeek API：按 HTTP 状态码分类诊断 — 401=Key 无效, 402=余额不足, 429=限流, timeout=超时
- Anthropic API：SDK 路径按异常内容分类，HTTP 路径按状态码分类，附修复链接
- `curate_with_llm()`：两个 API 都失败时打印具体修复步骤

### 修改的文件清单

| 文件 | 改动 |
|------|------|
| `scripts/daily_briefing.py` | `_curate_with_claude_api()` — SDK + HTTP 两处移除 `temperature=0.85`；新增 401/402/429/timeout 分类错误诊断；`curate_with_llm()` — 新增 API 名称日志 + 双失败时打印修复步骤 |
| `requirements.txt` | 取消注释 `anthropic>=0.30.0`（从 `# anthropic>=0.30.0` 改为 `anthropic>=0.30.0`） |

### ⚠️ 需要用户检查的事项

1. **DeepSeek 余额**：去 https://platform.deepseek.com 登录检查 API Key 余额。DeepSeek 是预付费的，¥1 够用几个月但余额总会花完
2. **GitHub Secrets 配置**：确认 `DEEPSEEK_API_KEY` 和 `ANTHROPIC_API_KEY` 在 GitHub → Settings → Secrets and variables → Actions 中正确且未过期
3. **提交推送后测试**：push 这组修复 → Actions → daily_briefing.yml → Run workflow 手动触发测试

### 各 provider 当前状态

| Provider | 模型 | 参数 | 状态 |
|----------|------|------|------|
| DeepSeek | `deepseek-chat` | `temperature=0.85` ✅ | 优先，可能余额已用尽 |
| Anthropic | `claude-sonnet-5` | 无 temperature ✅ 已修复 | 备用，修复后可正常工作 |
| Server酱 | — | — ✅ | 上次运行正常（2026-07-23） |

---

## ✅ 今日完成 (2026-07-24) — 🔥 数据加载修复：浏览器端直连

### 问题诊断

三个数据指标在网页上均无法加载，根因是 **GitHub Actions 服务器 IP 的网络限制**：

| 数据 | 数据源 | 问题 |
|------|--------|------|
| 恐惧贪婪指数 | `api.alternative.me` | API 本身正常（CORS ✅），但 GitHub Actions 运行时偶尔失败 |
| ETF 流入流出 | `farside.co.uk` | **Cloudflare 反爬虫保护** — 服务器端完全无法访问 |
| 资金费率 | `fapi.binance.com` | Binance 从 GitHub Actions 美国 IP 被墙 |

`data/signals.json` 和 `data/latest.json` 均缺少这三个字段。

### 解决方案：浏览器端直连

不再依赖 GitHub Actions 预计算这些数据，改为**浏览器端直接调用公开 API**：

```
  用户浏览器
    ├── https://api.alternative.me/fng/        → 恐惧贪婪指数 (CORS ✅)
    ├── https://fapi.binance.com/fapi/v1/      → 资金费率 + 标记价格 (CORS ✅)
    └── farside.co.uk (via CORS 代理)          → ETF 净流动 (尽力而为)
```

### 修改的文件清单

| 文件 | 改动 |
|------|------|
| `ai选股/index.html` | 新增 `fetchFearGreedDirect()` — 浏览器端直接调用 alternative.me；新增 `fetchFundingRatesDirect()` — 浏览器端直接调用 Binance Futures；新增 `fetchETFDirect()` — 通过 CORS 代理尝试获取 ETF 数据；新增 `injectFundingRates()` — 动态注入资金费率到已渲染的资产卡片；`renderSentiment()` 拆分为 `renderFearGreedGauge()` + `renderETFContent()`；`refreshAll()` 两分支都加入浏览器端回退调用 |
| `templates/index.html` | 新增 `fetchFearGreedDirect()` — 浏览器端恐惧贪婪指数获取；`init()` 中 `{% if not fear_greed %}` 条件触发浏览器端获取；`applyDataRefresh()` 中服务器端无数据时自动触发浏览器端获取 |
| `scripts/monitor_crypto.py` | `fetch_fear_greed_index()` 增加 3 次重试；`fetch_etf_flows_simple()` 增加 Cloudflare 保护检测 + 返回 None 以区分"未尝试"和"失败" |
| `scripts/fetch_crypto.py` | `fetch_fear_greed_index()` 增加 3 次重试；`_fetch_etf_flows()` 增加 Cloudflare 保护检测 |

### 关键设计决策

- **F&G 指数**：服务器端保留重试逻辑作为主路径，浏览器端作为 fallback（`signals.json` 无数据时自动触发）
- **资金费率**：`ai选股/index.html` 始终浏览器端获取（不依赖 signals.json），因为 Binance 从服务器端几乎不可达
- **ETF 数据**：服务器端放弃（Cloudflare 无解），浏览器端通过 CORS 代理尽力获取，失败时显示 "ETF 数据暂不可用" + 手动查看链接

---

## ✅ 今日完成 (2026-07-23) — 🌡️ 市场情绪指标新增

### 新增: 恐惧贪婪指数 + ETF 流入流出

为 AI 选股页面和主面板新增两个市场情绪指标。

**恐惧贪婪指数 (Crypto Fear & Greed Index):**
- 数据源: `https://api.alternative.me/fng/`（免费，无需 API Key）
- 返回 0-100 分 + 分类（Extreme Fear / Fear / Neutral / Greed / Extreme Greed）
- 展示位置:
  - `ai选股/index.html`: 页面顶部仪表盘卡片（SVG 弧形 + 渐变条形图 + 分类标签）
  - `templates/index.html`: 摘要卡片网格第 4 张卡片（彩色数值 + 渐变条形指示器）

**ETF 流入流出 (BTC/ETH 现货 ETF):**
- 数据源: `farside.co.uk`（已有后端逻辑，扩展至 signals.json）
- 展示位置: `ai选股/index.html` 页面顶部 ETF 流动卡片（BTC/ETH 分别显示净流动，绿色/红色编码）

### 修改的文件清单

| 文件 | 改动 |
|------|------|
| `scripts/monitor_crypto.py` | 新增 `fetch_fear_greed_index()` + `fetch_etf_flows_simple()`；扩展 `save_signals_json()` 输出 `fear_greed` 和 `etf_flows` 字段；`run_detection()` 调用市场情绪抓取 |
| `scripts/fetch_crypto.py` | 新增 `fetch_fear_greed_index()` 公开函数（主面板使用） |
| `scripts/main.py` | 导入并调用 `fetch_fear_greed_index()`；传入 `generate_html()` 和 `save_data_json()`；保存到 `data/latest.json` |
| `ai选股/index.html` | 新增市场情绪卡片 CSS + HTML（F&G SVG 仪表盘 + ETF 净流动）；新增 `renderSentiment()` JS 函数；集成到 signals.json 加载路径 |
| `templates/index.html` | 摘要卡片网格新增恐惧贪婪指数卡片（Jinja2 条件渲染 + 软刷新 JS 更新）；新增 `updateFearGreedCard()` 函数 |

### 数据流

```
monitor_crypto.py (~10min)          main.py (工作日 16:00/20:00)
  ├── fetch_fear_greed_index()        ├── fetch_fear_greed_index()
  ├── fetch_etf_flows_simple()        └── → data/latest.json
  └── → data/signals.json                  → index.html (Jinja2)
       → ai选股/index.html 读取
```

---

## ✅ 今日完成 (2026-07-23) — 🧹 卡点验证 + 代码质量优化

### 一、卡点状态确认

两个之前的卡点均已解决：

| 卡点 | 结果 |
|------|------|
| GitHub Actions 权限 "Read and write" | ✅ 用户已配置，self-ping 正常工作 |
| 邮件 Secrets（`AI_MONITOR_EMAIL_*`） | ✅ 已配置，`workflow_output.log` 证实邮件成功发送到 `1660669970@qq.com` |

**全链路验证通过**：信号检测 → 评分 → 触发通知 → QQ 邮箱推送，BTC/ETH 均正常。

### 二、代码质量优化

**`scripts/monitor_crypto.py`（4 处）：**

| 改动 | 说明 |
|------|------|
| `import math` 移到文件顶部 | 原来在 for 循环内重复 import |
| `from scripts.send_email import ...` 移到文件顶部 | 原来在 per-asset 循环里每次发邮件前才 import |
| `save_signals_json()` 外包 try/except | 原来 JSON 序列化失败会崩溃导致 state 也不保存 |
| 删除循环内的 `import math` | 配合第一项 |

**`scripts/main.py`（1 处）：**

| 改动 | 说明 |
|------|------|
| 删除未使用的 `from datetime import timedelta` | if 分支内 import 但从未使用，死代码 |

**`scripts/daily_briefing.py`（2 处）：**

| 改动 | 说明 |
|------|------|
| GitHub Trending 抓取逻辑简化 | 原来 2 层嵌套循环（section × lang = 4 次迭代），但 URL 生成逻辑有冗余。改为直接声明 2 个目标 URL |
| `push_to_wechat()` 增加 3 次重试 | 原来网络抖一下就失败，现在最多重试 3 次（间隔 2s），与 `send_email.py` 策略一致 |

### 三、当前完整功能概览

三个自动化系统 + 一个数据面板，全部跑在 GitHub Actions 免费额度上：

1. **🔔 加密货币交易信号监控**（每 ~10 分钟）
   - Binance → Kraken → CoinGecko 三层备选 → 1H/4H/日线技术指标 → 期货基本面验证 → 评分 ≥ 55 触发 → QQ 邮箱 HTML 邮件
   
2. **🗞️ 每日硬核科技情报简报**（每天 8:00 / 20:00）
   - 5 路数据并行抓取 → 启发式评分 → DeepSeek API 策展（优先）/ 启发式回退 → Markdown + JSON + 微信推送 + 网站展示
   
3. **📊 投资观察数据面板**（工作日 16:00 / 20:00）
   - A股/港股/美股/加密货币 → Jinja2 渲染 → GitHub Pages 部署
   
4. **🖥️ AI 选股面板**（`ai选股/index.html`）
   - 优先从 `data/signals.json` 加载，回退 CoinGecko API

三端覆盖：**邮箱**（交易信号）、**微信**（科技简报）、**网页**（数据面板 + 简报）。

---

## ✅ 今日完成 (2026-07-22) — 🔥 策略评分体系重构 + 简报系统全面升级

### 一、加密货币信号评分体系重构

**删除消息面评分** — 原来硬编码 10 分，无效占位符，从 `monitor_crypto.py`、`send_email.py`、`ai选股/index.html` 全部移除。

**基本面重新设计** — 从"循环论证的 24h 价格数据"改为"独立于价格的期货市场数据"：

| 旧基本面 (20分) | 新基本面 (20分) | 为什么改 |
|------|------|------|
| 24h 涨跌匹配度 (8分) | **资金费率 (12分)** | 旧：价格算信号方向→价格校验方向=循环论证。新：期货多空谁付钱=真独立情绪指标 |
| 24h 成交量 (6分) | **OI 持仓量变化 (8分)** | 旧：BTC/ETH 永远 +6，无区分度。新：资本进出速度=市场参与度 |
| 24h 振幅 (6分) | — | 旧：和 ATR 评分重叠。新：删掉 |

**资金费率逻辑**：正费率=多头付钱给空头（市场过热），负费率=空头付钱给多头（市场恐慌）。做多时费率越负分越高（反向做多），做空时费率越正分越高（反向做空）。

**OI 变化逻辑**：持仓量大幅变化=市场活跃=技术信号更可靠，不论方向。|OI|>3% = +8分。

**阈值同步调整**（有效满分 85→75）：

| 参数 | 旧值 | 新值 |
|------|:--:|:--:|
| 信号触发阈值 | 65 | **55** |
| 高置信度 | 80 | **60** |
| 中高置信度 | 65 | **50** |
| 中置信度 | 50 | **40** |

**数据源**：Binance 期货公开 API (`/fapi/v1/fundingRate` + `/fapi/v1/openInterestHist`)，无需 API Key。

### 二、每日简报系统升级

**DeepSeek API 策展**（优先，¥1/百万 token，中文原生）：
- `scripts/daily_briefing.py` 重构为多 provider 架构
- 优先级: DeepSeek (`deepseek-chat`) → Anthropic (`claude-sonnet-5`) → 启发式回退
- OpenAI 兼容 API，无需额外 SDK

**Server酱微信推送**：
- 新增 `push_to_wechat()` 函数，简报生成后自动推送到微信
- 通过 `SERVERCHAN_SEND_KEY` 环境变量配置
- 免费额度每天 5 条，完全够用

**GitHub Actions 修复**：
- `.gitignore` 添加 `!logs/briefing_output.log` 白名单（修复 `git add` 失败）
- `.github/workflows/daily_briefing.yml` 添加 `SERVERCHAN_SEND_KEY` 和 `DEEPSEEK_API_KEY` secrets

### 三、修改的文件清单

| 文件 | 改动 |
|------|------|
| `scripts/monitor_crypto.py` | 新增 `fetch_futures_data()` + 重写 `generate_signal()` 基本面评分 + 阈值调整 + 删消息面 |
| `scripts/send_email.py` | 删 `news_score` 参数 + 评分条从三色变两色 + 阈值调色 + 分数显示修正 |
| `scripts/daily_briefing.py` | 新增 DeepSeek provider + Server酱推送 + 重构为 `curate_with_llm()` 多 provider 架构 |
| `ai选股/index.html` | 删 `fetchNewsSafe()` + `renderNews()` + 消息面全部 UI/JS + 基本面简化 + 阈值同步 |
| `.github/workflows/daily_briefing.yml` | 添加 `DEEPSEEK_API_KEY` + `SERVERCHAN_SEND_KEY` secrets + 修复 git add |
| `.github/workflows/crypto_monitor.yml` | 7 cron + self-ping（前一版本） |
| `.gitignore` | 白名单 `!logs/briefing_output.log` |
| `templates/index.html` | 简报展示区 + CSS + JS 软刷新（前一版本） |
| `scripts/main.py` | 简报集成（前一版本） |

### 四、当前配置状态

用户已完成:
- ✅ DeepSeek API Key 已配置
- ✅ Server酱 SendKey 已配置
- ✅ GitHub Secrets 全部就位
- ✅ 手动触发成功 — DeepSeek 策展 + 微信推送正常

用户未配置:
- ⬜ Anthropic API Key（不需要，DeepSeek 已够用）
- ⬜ 邮件 Secrets（`AI_MONITOR_EMAIL_FROM/PASSWORD/TO`）— 信号通知邮件仍不可用

---

## ✅ 之前完成 (2026-07-21) — 🗞️ 每日硬核情报简报 + 调度修复

### 项目扩大：新增「硬核科技与情报首席分析师」系统

**新增模块：`scripts/daily_briefing.py`（~810 行）**

5 路数据源并行抓取 → 启发式评分 → AI 策展 → Markdown + JSON 输出：

| 数据源 | 方式 | 效果 |
|--------|------|------|
| Hacker News | Firebase API (免费) | Top stories + 评分/评论数 |
| GitHub Trending | HTML 抓取 + Search API 回退 | 今日热门开源项目 |
| ArXiv | Atom API → feedparser | AI/ML/量化金融最新论文 |
| Lobste.rs | JSON API (免费) | 邀请制社区，信噪比极高 |
| Tech RSS | feedparser (7 个源) | HN RSS / The Hacker News / The Register / Ars Technica / dev.to / Reddit |

**AI 策展引擎：**
- 启发式评分（高价值关键词 + 来源权重 + HN/Lobste.rs 社区信号）
- Claude API 策展（可选）：精选 3 条 → 中文翻译 → 毒舌点评 → 金句
- 无 API key 时自动回退到启发式模板模式，零成本运行

**输出格式（按用户指定的「硬核科技与情报首席分析师」prompt）：**
- `daily_briefing.md` — 格式化 Markdown 简报
- `data/daily_briefing.json` — 结构化数据（含 `briefing_items` 供网站渲染）

**新增文件：**
| 文件 | 说明 |
|------|------|
| `scripts/daily_briefing.py` | 核心模块 |
| `.github/workflows/daily_briefing.yml` | 定时工作流（每天 8:00 / 20:00 北京时间）|

**修改的文件：**
| 文件 | 改动 |
|------|------|
| `scripts/main.py` | 集成简报：加载 data/daily_briefing.json → 传入 Jinja2 模板 → 存入 data/latest.json |
| `templates/index.html` | 新增简报展示区：3 列卡片（来源标签 + 标题 + 核心干货 + 毒舌点评）+ 金句横幅 + CSS + JS 软刷新 |
| `requirements.txt` | 添加 `anthropic` 为可选依赖 |

**网站展示：**
- 简报区位于投资观察面板的摘要卡片下方
- 响应式：桌面 3 列，窄屏自动切换单列
- AI 策展模式下显示 🤖 标识
- 支持 JS 软刷新（无需整页重载）

**启用 AI 策展：** 在 GitHub Secrets 中设置 `ANTHROPIC_API_KEY`，即可解锁 Claude 深度策展和毒舌点评。

---

## ✅ 今日完成 (2026-07-21) — 🔥 调度稳定性二次修复

### 问题：crypto_monitor.yml 数小时只触发一次，邮件几小时只发一封

**第一次修复（`*/15` → `*/5` + 14min 去重守卫）效果不够。**

**🔥 第二次修复（三管齐下）：**

1. **7 条 Cron 规则饱和覆盖**
   ```yaml
   - cron: '*/5 * * * *'           # 0,5,10,15...
   - cron: '1,6,11,16... * * * *'  # 1,6,11,16...
   - cron: '2,7,12,17... * * * *'
   - cron: '3,8,13,18... * * * *'
   - cron: '4,9,14,19... * * * *'
   - cron: '0,10,20... * * * *'    # 双保险
   - cron: '5,15,25... * * * *'
   ```

2. **Self-ping 链式触发** — 每次成功执行后用 `gh workflow run` 触发下一次（9 分钟冷却），scheduler 罢工也能自保持

3. **冷却时间全面缩短**
   - 去重守卫: 14min → 8min
   - 同方向通知: 4h → 1h
   - 邮件失败冷却: 24h → 6h

**⚠️ 需用户操作：** Settings → Actions → General → Workflow permissions → 选 "Read and write permissions"（self-ping 需要）

**修改的文件：**
| 文件 | 改动 |
|------|------|
| `.github/workflows/crypto_monitor.yml` | 7 cron + self-ping step + 8min guard |
| `scripts/monitor_crypto.py` | 通知冷却 4h→1h，失败冷却 24h→6h |

---

## ✅ 之前完成 (2026-07-21) — 网站数据源迁移到 GitHub Actions 预计算

### 问题：ai选股/index.html 用 CoinGecko 数据经常加载失败

**解决方案：GitHub Actions 预计算 → JSON → 网站直接读**

```
刷新前:  浏览器 → CoinGecko API (经常挂, CORS代理慢, 加载需15-30s)
刷新后:  浏览器 → data/signals.json (同域 GitHub Pages, 加载<1s, 15分钟更新)
          ↑
GitHub Actions (每15分钟): Binance → Kraken → CoinGecko 三层备选 → 写入 signals.json
```

**修改了 3 个文件：**

1. **`scripts/monitor_crypto.py`** — 新增 `save_signals_json()` 函数
   - 每次检测完成后，把信号结果 + 三层 OHLC 数据 (1H/4H/1D) 写入 `data/signals.json`
   - 自动清理 NaN/Inf 值确保 JSON 兼容
   - 包含数据源标注 (Binance/Kraken/CoinGecko)

2. **`.github/workflows/crypto_monitor.yml`** — 自动提交 signals.json
   - `git add data/signals.json` 纳入每次自动提交
   - 诊断步骤显示 signals.json 当前内容

3. **`ai选股/index.html`** — 双数据源架构
   - 新增 `loadFromSignalsJSON()`: 从同域加载 JSON，检查新鲜度 (< 1h)
   - 新增 `buildAssetDataFromJSON()`: 将 JSON 转换为图表兼容格式 (含时间戳生成)
   - `refreshAll()` 优先走 signals.json，不可用时自动回退 CoinGecko API
   - 状态栏显示数据来源 (如 "GitHub Actions (BTC:Kraken, ETH:Binance)")

**用户体验改善：**
- 加载速度：15-30s → <1s（同域静态 JSON，无 API 延迟）
- 可用性：CoinGecko 免费 API 经常挂 → GitHub Actions 三层备选保证 99%+ 可用
- 数据质量：Kraken 真实 OHLC 比 CoinGecko 近似数据更准

---

## ✅ 之前完成 (2026-07-21) — 邮件通知系统排查和修复

### 问题：网站显示交易机会但 QQ 邮箱收不到

**排查出的 3 个根因：**

1. **Binance API 在 GitHub 服务器 IP 上被阻断**
   - 本地能正常访问 Binance，但 GitHub Actions（美国 IP）连不上
   - 解决：建立三层数据源备选链 **Binance → Kraken → CoinGecko**
   - Kraken 是美国合规交易所，GitHub 服务器能直连，且提供真实 OHLC 数据

2. **基本面评分 hardcoded 导致评分卡在阈值下**
   - 原来 `fund_score` 硬编码为 10 分（CoinGecko 免费 API 不稳定时加的 workaround）
   - 导致评分刚好 64/100（差 1 分到 65 阈值）
   - 解决：用 Binance 24h ticker 实时计算 fund_score，不可用时自动切 CoinGecko ticker
   - 修复前 64 分 → 修复后 74 分（+10 分来自真实基本面数据）

3. **邮件失败后 state 不保存 → 无限重试但不报错**
   - 之前代码只在邮件成功时更新 state，失败则状态永为空
   - 每次运行都重试但从不记录失败
   - 解决：无论邮件是否成功都更新 state，连续失败 3 次后冷却延长至 24h

**最终效果：**
- 手动触发 → Kraken 获取数据 → CoinGecko 补基本面 → 评分 74 → 邮件发送 ✅
- 定时调度 `*/15 * * * *`（每 15 分钟），24×7 自动运行
- 信号方向改变立即通知，同方向 4h 冷却防轰炸

**修改的文件：**
- `scripts/monitor_crypto.py` — state 管理 / 基本面评分 / Kraken+CoinGecko 备选 / 日志轮转
- `scripts/send_email.py` — SMTP 3 次重试 + QQ 异地 IP 诊断提示
- `.github/workflows/crypto_monitor.yml` — 诊断步骤 / workflow_output.log 捕获
- `.gitignore` — 放开 `logs/monitor.log` 和 `logs/workflow_output.log`

---

## ⚠️ 当前卡点 / 已知问题

### 🟢 已解决 (2026-07-23 确认)

1. ~~**GitHub Actions 定时调度稳定性**~~ ✅ **已解决**
   - 7 条 cron + self-ping 链式触发 + 8 分钟去重守卫 = 实际检测频率 ~10 分钟/次
   - Workflow permissions 已设为 "Read and write"（self-ping 需要）
   - 运行稳定，无需进一步操作

2. ~~**邮件 Secrets 未配置**~~ ✅ **已解决**
   - `AI_MONITOR_EMAIL_FROM` / `AI_MONITOR_EMAIL_PASSWORD` / `AI_MONITOR_EMAIL_TO` 全部就位
   - `logs/workflow_output.log` 证实：BTC/ETH 信号邮件成功发送到 `1660669970@qq.com`

### 🟡 中优先级

3. **策略参数自动调优**
   - 每季度用最新数据跑一次 `scan_eth.py` + `backtest_grid.py`
   - V3 的 85 分制各维度权重可以定期回测校准

4. **15min 数据在 GitHub Actions 的可用性**
   - Binance API 主站在大陆被墙，生产环境(GitHub Actions US IP)可能正常
   - 已添加多端点轮换 (api1/api2/api3.binance.com)
   - 如果 15min 数据不可用，V3 自动降级为 1H 主框架

5. **Kraken K 线数据与 Binance 有微小差异**
   - 当前 V3 阈值 58/85，Kraken 模式可考虑独立阈值

### 🟢 低优先级

6. 网页版显示策略参数版本号(V3)和 V3 专属的 15min 指标
7. 回测页面增加参数对比功能（V1/V2/V3）
8. 邮件增加更多细节（15min 框架状态、最近 N 次信号准确率统计）
9. 监控覆盖面扩展：考虑加入 SOL 等主流币种
10. 获取更长周期的 15min 数据做更充分回测（当前只回测了~41天）

---

## 🆕 每日硬核情报简报 (2026-07-21 新增)

### 功能概述

「硬核科技与情报首席分析师」—— 每日自动从全球顶级科技数据源抓取情报，精选 3 条最有价值的项目/动态，翻译为中文并配以"毒舌"风格点评。

### 数据源（5 路并行抓取）

| 数据源 | 方式 | 说明 |
|--------|------|------|
| **Hacker News** | Firebase API (免费) | Top stories + 评分/评论数 |
| **GitHub Trending** | HTML 抓取 + Search API 回退 | 今日热门开源项目 |
| **ArXiv** | Atom API → feedparser | AI/ML/量化金融最新论文 |
| **Lobste.rs** | JSON API (免费) | 邀请制社区，信噪比极高 |
| **Tech RSS** | feedparser (7 个源) | HN RSS / The Hacker News / The Register / Ars Technica / dev.to / Reddit r/programming / r/MachineLearning |

### AI 策展引擎

```
数据抓取 (5 源) → 启发式评分 (关键词 + 来源权重)
    → Top 20 候选
    → Claude API 策展 (需 ANTHROPIC_API_KEY)
        ├── 精选 3 条
        ├── 翻译为地道中文
        └── 配毒舌点评 + 金句
    → 输出 Markdown + JSON
```

**无 API key 时自动回退到启发式模式**（评分排序 + 模板点评），保证零成本运行。

### 新增文件

| 文件 | 说明 |
|------|------|
| `scripts/daily_briefing.py` | 核心模块：数据抓取 + 评分 + LLM 策展 + Markdown 生成 |
| `.github/workflows/daily_briefing.yml` | 定时工作流（每天 8:00 / 20:00 北京时间）|
| `daily_briefing.md` | 输出：格式化的每日简报 |
| `data/daily_briefing.json` | 输出：结构化数据（供网站渲染）|

### 修改的文件

| 文件 | 改动 |
|------|------|
| `scripts/main.py` | 集成简报生成（加载/生成 → 传入模板 → 存入 latest.json）|
| `templates/index.html` | 新增简报展示区（3 列卡片 + 金句横幅）+ CSS + JS 软刷新 |
| `requirements.txt` | 添加 `anthropic` 为可选依赖 |

### 网站展示

简报区位于投资观察面板的摘要卡片下方：
- 3 列卡片布局（每卡：来源标签 + 标题 + 核心干货 + 毒舌点评）
- 底部横幅：今日顶男金句
- AI 策展模式下显示 🤖 标识
- 响应式：窄屏自动切换为单列

### 启用 AI 策展

在 GitHub Secrets 中设置 `ANTHROPIC_API_KEY` 即可启用 Claude 深度策展：
1. 获取 key: https://console.anthropic.com/
2. GitHub → Settings → Secrets and variables → Actions → New repository secret
3. Name: `ANTHROPIC_API_KEY`, Value: `sk-ant-...`

不设置 key 也能正常运行（启发式模式），但点评质量有限。

### 本地测试

```bash
# 仅抓取数据，不生成简报
python scripts/daily_briefing.py --fetch-only

# 完整生成（启发式模式）
python scripts/daily_briefing.py

# 完整生成（AI 策展模式）
set ANTHROPIC_API_KEY=sk-ant-...
python scripts/daily_briefing.py
```

---

## 📊 技术架构（当前 — V3）

```
GitHub Actions
  ├── crypto_monitor.yml (7条cron + self-ping, 有效频率 ~10分钟/次)
  │   ├── 数据获取: Binance 15min/1H K线 (多端点轮换) → Kraken → CoinGecko
  │   ├── 期货基本面: Binance Futures API（资金费率 + OI 变化）
  │   ├── 信号引擎: generate_signal() V3 — 15min主框架 + 1H/4H背景 (85分制)
  │   ├── 邮件通知: QQ邮箱 SMTP（评分≥58且非观望时发送）
  │   ├── 状态持久化: logs/signal_state.json + logs/monitor.log
  │   └── 网站数据: data/signals.json → ai选股/index.html
  │
  ├── update.yml (工作日 16:00 / 20:00)
  │   ├── 市场数据: A股/港股/美股/加密货币
  │   ├── 市场新闻: RSS feeds
  │   ├── 简报加载: data/daily_briefing.json
  │   ├── HTML 生成: templates/index.html → index.html
  │   └── GitHub Pages 部署
  │
  └── daily_briefing.yml (每天 8:00 / 20:00)
      ├── 5 路数据抓取: HN + GitHub + ArXiv + Lobste.rs + RSS
      ├── AI 策展: DeepSeek API（优先）→ Claude API → 启发式回退
      ├── 微信推送: Server酱 → 手机微信直达
      ├── 输出: daily_briefing.md + data/daily_briefing.json
      └── 提交推送 → 网站自动展示
```

---

## 📝 日常使用

- **零操作** — GitHub Actions 全自动，电脑关机也运行
- **手机挂 QQ 邮箱** — 收到做多/做空信号后自行判断
- **微信收简报** — 每天早 8 点/晚 8 点，Server酱 推送毒舌科技情报
- **数据面板**: https://charminglyy.github.io/investment-tracker/
- **每日简报**: 数据面板摘要区下方（每天 8:00 / 20:00 更新）
- **查看运行记录**: https://github.com/CharmingLyy/investment-tracker/actions
- **手动触发**: Actions → 选择工作流 → Run workflow
- **AI 策展**: 已启用 DeepSeek API（¥1/百万 token，中文原生），回退链: DeepSeek → Anthropic → 启发式
