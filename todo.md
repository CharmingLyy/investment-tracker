# TODO — AI 投资观察面板

> 最后更新: 2026-07-20 14:00 (GitHub Actions 全自动部署完成)

---

## ✅ 今日完成 (2026-07-20) — 最终版：全自动云端部署

### GitHub Actions 全自动监控 + 邮件通知（不再需要本地运行）

**架构变化：**
- ❌ 之前：需要本地运行 `monitor_loop.bat` / `python scripts/monitor_crypto.py --loop`
- ✅ 现在：全部跑在 GitHub 服务器上，电脑关机也正常运行

**创建的工作流文件：**

1. **`.github/workflows/crypto_monitor.yml`** — 交易信号定时监控
   - 每 15 分钟自动检测 BTC/ETH（`*/15 * * * *`，24×7 全年无休）
   - 调用 Binance 公开 API 获取 1H K线
   - 信号评分 ≥65 且非「观望」时自动发送邮件
   - 信号状态持久化到 `logs/signal_state.json`（方向翻转立即通知，同方向 4h 冷却）

2. **`.github/workflows/test_email.yml`** — 邮件配置测试
   - 手动触发，验证 QQ 邮箱 SMTP 是否配置正确
   - 发送测试邮件到配置的收件地址

3. **`scripts/test_email.py`** — 邮件诊断脚本
   - 检查环境变量、SMTP 连接、QQ 邮箱认证、发送测试邮件

**GitHub Secrets 配置（仓库 Settings → Secrets and variables → Actions）：**

| Secret 名称 | 说明 |
|-------------|------|
| `AI_MONITOR_EMAIL_FROM` | QQ 邮箱地址 |
| `AI_MONITOR_EMAIL_PASSWORD` | QQ 邮箱 SMTP 授权码（非 QQ 密码） |
| `AI_MONITOR_EMAIL_TO` | 接收信号的邮箱 |

**通知规则：**
- 只有评分 ≥65 且出现「做多 LONG」或「做空 SHORT」时才发邮件
- 「观望 WAIT」不通知（避免噪音）
- 方向改变立即通知，同方向最多每 4 小时通知一次

**当前实测（2026-07-20 13:57）：**
| 标的 | 信号 | 评分 | 价格 | 趋势 |
|------|------|------|------|------|
| BTC | 🟡 观望 WAIT | 49/100 | $64,156 | 1H空/4H空/日多 |
| ETH | 🟡 观望 WAIT | 53/100 | $1,856 | 1H空/4H空/日多 |

> 当前无信号是正常的 — 1H/4H 空头 + 日线多头矛盾，评分不足 65

---

## ✅ 今日完成 (2026-07-19)

### 策略参数优化 — BTC/ETH 短线交易信号

**问题诊断：**
- 原始参数（止损 1.5×ATR, 止盈 3.0×ATR, 评分≥50）在 ETH 上亏损（年 -$51, PF=0.97），BTC 勉强度日（年 +$89, PF=1.07）
- 根因：1H ATR 太小 → 止损 0.3-0.6%，加密货币随机噪声轻松扫损 → 胜率被拖垮
- 支撑位只留 0.2% 缓冲，影线频繁打穿
- 强制 R:R≥2 把止盈推到不切实际的位置

**做了什么：**
1. 写了两套 Python 回测脚本（`scripts/backtest_crypto.py` 单次回测 + `scripts/backtest_grid.py` 网格搜索）
2. 跑完 5×5×4=100 个参数组合的网格搜索，基于 Binance 1000 天日线实盘数据
3. 找到最优参数组合并应用到实盘引擎

**最终参数（少而精路线）：**

| 参数 | 旧值 | 新值 |
|------|------|------|
| 止损 ATR | 1.5× | **2.0×** |
| 止盈 ATR | 3.0× | **5.0×** |
| R:R 最低 | 2.0 | **1.5** |
| 支撑/阻力缓冲 | 0.2% | **0.5%** |
| 止损取法 | 取更紧 | **取更宽** |
| 回测评分阈值 | ≥50 | **≥55** |

**预期效果（每笔固定 100 USDT）：**

| 指标 | BTC | ETH |
|------|-----|-----|
| 年交易 | ~93 笔 | ~94 笔 |
| 胜率 | 58% | 42% |
| 每笔平均 | +$2.61 | +$1.88 |
| 年收益 | +$243 | +$177 |
| 最大连亏 | 6 次 | 11 次 |
| PF | 1.99x | 1.47x |

**修改的文件：**
- `ai选股/index.html` — 实盘信号 + 回测引擎参数更新
- `scripts/backtest_crypto.py` — Python 回测脚本
- `scripts/backtest_grid.py` — 新建，参数网格搜索脚本

---

## 📋 下一步计划

### 🔴 高优先级

- [x] **全自动云端监控**：✅ 已完成 — GitHub Actions 每 15 分钟检测，有信号自动邮件通知
- [x] **邮件通知测试**：✅ 已完成 — 测试邮件发送成功
- [x] **实盘跟踪记录**：✅ 信号日志自动保存到 `logs/monitor.log`，GitHub Actions 每次提交保留

### 🟡 中优先级 — 增强策略

- [ ] **ai选股/index.html 数据源修复**：网页版仍用 CoinGecko（经常挂），应切换到 Binance API 或复用 monitor_crypto.py 的数据
- [ ] **加入 1H/4H 多时间框架回测**：当前回测仅用日线模拟，用 Binance 1H K 线重写回测更准确
- [ ] **策略参数自动调优**：每个季度用最新数据跑一次网格搜索
- [ ] **监控覆盖面扩展**：考虑加入 SOL 等主流币种

### 🟢 低优先级 — 体验改进

- [ ] 网页版显示策略参数版本号
- [ ] 回测页面增加参数对比功能
- [ ] A 股/港股/美股的交易信号模块
- [ ] 邮件增加更多细节（如最近 N 次信号准确率统计）

---

## ⚠️ 已知痛点

1. **回测 ≠ 实盘**：回测用日线数据模拟，实盘用 1H 数据 + 支撑阻力位调整止损止盈。新参数在回测中验证过，但实盘需要观察。
2. **ai选股/index.html 的 CoinGecko API 不稳定**：网页版数据源仍是 CoinGecko（免费 API 经常限流），GitHub Actions 版已切换为 Binance。
3. **Yahoo Finance 限速**：yfinance 在短时间内多次调用会被封 IP。
4. **策略对趋势市依赖强**：震荡市中表现需要更长时间验证。
5. **GitHub Actions 免费额度**：每月 2000 分钟（私有仓库）/ 无限（公开仓库）。当前每 15 分钟跑一次 = ~2880 次/月，每次约 30 秒 = ~1440 分钟/月。如果是公开仓库则免费无限。

---

## 📝 使用指南

### 🎯 日常使用（零操作）
- **不需要做任何事** — GitHub Actions 全自动运行
- **手机挂 QQ 邮箱** — 收到交易信号邮件后自行判断是否操作
- **查看数据面板**：打开 `https://charminglyy.github.io/investment-tracker/`

### 🖥️ 本地操作（可选）
```bash
# 单次信号检测（不发送邮件）
python scripts/monitor_crypto.py --once --no-email

# 本地持续监控（需要开电脑）
python scripts/monitor_crypto.py --loop

# 测试邮件配置
set AI_MONITOR_EMAIL_FROM=你的QQ号@qq.com
set AI_MONITOR_EMAIL_PASSWORD=你的QQ授权码
python scripts/test_email.py

# 查看监控日志
type logs\monitor.log
```

### 🔧 GitHub 操作
- **手动触发监控**：Actions → Crypto Signal Monitor → Run workflow
- **测试邮件**：Actions → 测试邮件发送 → Run workflow
- **查看运行日志**：Actions → 点击具体运行记录
- **修改 Secrets**：Settings → Secrets and variables → Actions
