# TODO — AI 投资观察面板

> 最后更新: 2026-07-23 (市场情绪指标: 恐惧贪婪指数 + ETF 流入流出)

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

3. **1H/4H 多时间框架回测**
   - 当前回测用日线模拟，实盘用 1H 数据，两者之间存在 gap
   - 用 Binance 1H K 线重写回测，直接验证实盘信号质量

4. **策略参数自动调优**
   - 每季度用最新数据跑一次 `scan_eth.py` + `backtest_grid.py`

5. **Kraken K 线数据与 Binance 有微小差异**
   - 不同交易所价格和 K 线边界不同，会导致 RSI/MACD 等技术指标有偏差
   - 目前数据源自适应，差异可接受，但极端情况下可能跨阈值漏信号
   - 可考虑为 Kraken 模式设独立阈值（如 50 分，比 Binance 的 55 分低 5 分作为容错）

### 🟢 低优先级

6. 网页版显示策略参数版本号和各资产专属参数
7. 回测页面增加参数对比功能
8. 邮件增加更多细节（如最近 N 次信号准确率统计）
9. 监控覆盖面扩展：考虑加入 SOL 等主流币种

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

## 📊 技术架构（当前）

```
GitHub Actions
  ├── crypto_monitor.yml (7条cron + self-ping, 有效频率 ~10分钟/次)
  │   ├── 数据获取链: Binance → Kraken(真实OHLC) → CoinGecko(近似)
  │   ├── 期货基本面: Binance Futures API（资金费率 + OI 变化）
  │   ├── 信号引擎: generate_signal() — 多时间框架(1H+4H+日线)
  │   ├── 邮件通知: QQ邮箱 SMTP（评分≥55且非观望时发送）
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
