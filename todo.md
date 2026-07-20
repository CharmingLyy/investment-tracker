# TODO — AI 投资观察面板

> 最后更新: 2026-07-21 01:30 (邮件通知系统全链路排查修复完成)

---

## ✅ 今日完成 (2026-07-21) — 邮件通知系统排查和修复

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

### 🔴 下次继续

1. **GitHub Actions 定时调度稳定性待观察**
   - 之前出现过 22 小时内只触发 1 次 schedule 的异常
   - 需要过几个小时去 https://github.com/CharmingLyy/investment-tracker/actions/workflows/crypto_monitor.yml 确认 schedule 触发频率正常

2. **网站版数据源仍是 CoinGecko**
   - `ai选股/index.html` 用 CoinGecko（经常挂，网页加载失败）
   - GitHub Actions 版已经用 Kraken + CoinGecko 双保险了
   - 网站版应切换到同样的多数据源方案，或直接展示 GitHub Actions 的最新结果

3. **Kraken K 线数据与 Binance 有微小差异**
   - 不同交易所价格和 K 线边界不同，会导致 RSI/MACD 等技术指标有偏差
   - 本地 Binance 评分 74，GitHub Kraken 评分也是 74（补上 ticker 后）
   - 但如果某次差异刚好跨过 65 阈值就会漏信号——可把阈值调到 60 作为 Kraken 模式的容错

### 🟡 中优先级

4. **ai选股/index.html 数据源切换到 Binance/Kraken**
   - 浏览器端没法直接调 Binance API（CORS），需要走代理或从 GitHub 仓库的 JSON 文件读
   - 方案：GitHub Actions 每次运行后把信号结果写到 JSON，网页读 JSON 显示

5. **1H/4H 多时间框架回测**
   - 当前回测用日线模拟，实盘用 1H 数据，两者之间存在 gap
   - 用 Binance 1H K 线重写回测，直接验证实盘信号质量

6. **策略参数自动调优**
   - 每季度用最新数据跑一次 `scan_eth.py` + `backtest_grid.py`

### 🟢 低优先级

7. 网页版显示策略参数版本号和各资产专属参数
8. 回测页面增加参数对比功能
9. 邮件增加更多细节（如最近 N 次信号准确率统计）
10. 监控覆盖面扩展：考虑加入 SOL 等主流币种

---

## 📊 技术架构（当前）

```
GitHub Actions (每15分钟)
  │
  ├── 数据获取链: Binance → Kraken(真实OHLC) → CoinGecko(近似)
  ├── ticker数据: Binance 24h → CoinGecko simple/price
  ├── 信号引擎: generate_signal() — 多时间框架(1H+4H+日线)
  ├── 邮件通知: QQ邮箱 SMTP（评分≥65且非观望时发送）
  └── 状态持久化: logs/signal_state.json + logs/monitor.log
```

---

## 📝 日常使用

- **零操作** — GitHub Actions 全自动，电脑关机也运行
- **手机挂 QQ 邮箱** — 收到做多/做空信号后自行判断
- **数据面板**: https://charminglyy.github.io/investment-tracker/
- **查看运行记录**: https://github.com/CharmingLyy/investment-tracker/actions/workflows/crypto_monitor.yml
- **手动触发**: Actions → Crypto Signal Monitor → Run workflow
- **测试邮件**: Actions → 测试邮件发送 → Run workflow
