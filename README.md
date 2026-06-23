# 📊 投资观察面板

跨市场投资数据自动追踪面板 — 覆盖 **A股、港股、美股、加密货币**，每天自动更新。

## ✨ 功能

| 功能 | A股 | 港股 | 美股 | 加密货币 |
|------|:--:|:--:|:--:|:--:|
| 实时价格 / 涨跌幅 | ✅ | ✅ | ✅ | ✅ |
| 市值 | ✅ | ✅ | ✅ | ✅ |
| PE 估值 | ✅ | ✅ | ✅ | - |
| MACD 技术指标 | ✅ | ✅ | ✅ | ✅ |
| RSI 技术指标 | ✅ | ✅ | ✅ | ✅ |
| 均线 (MA5/MA20) | ✅ | ✅ | ✅ | ✅ |
| 资金流向 | ✅ | - | - | - |
| 行业分类 | ✅ | ✅ | ✅ | ✅ |
| 新闻摘要 | ✅ | ✅ | ✅ | ✅ |
| 链上数据 | - | - | - | ✅ |

## 🚀 快速开始

### 1. 注册 GitHub 账号
前往 [github.com](https://github.com) 免费注册。

### 2. Fork / 上传本项目
将此项目上传到你的 GitHub 仓库。

### 3. 配置你的投资标的
编辑 `scripts/config.py`，添加你要跟踪的标的：

```python
A_STOCKS = [
    {"code": "600519", "name": "贵州茅台"},
    {"code": "300750", "name": "宁德时代"},
]

HK_STOCKS = [
    {"code": "00700", "name": "腾讯控股"},
]

US_STOCKS = [
    {"code": "AAPL", "name": "Apple"},
    {"code": "NVDA", "name": "NVIDIA"},
]

CRYPTO = [
    {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC"},
    {"id": "ethereum", "name": "Ethereum", "symbol": "ETH"},
]
```

### 4. 启用 GitHub Pages
1. 进入仓库 → **Settings** → **Pages**
2. **Source** 选择 **GitHub Actions**
3. 保存

### 5. 手动触发首次更新
1. 进入仓库 → **Actions** → **Daily Market Update**
2. 点击 **Run workflow** → **Run workflow**
3. 等待完成，你的网站就上线了！

### 6. 访问你的网站
`https://你的用户名.github.io/仓库名/`

## ⏰ 自动更新

- **A股/港股收盘后**: 北京时间 16:00（UTC 08:00）
- **美股收盘后**: 北京时间 20:00（UTC 12:00）
- 仅工作日运行
- 也可随时手动触发更新

## 📦 数据源

| 市场 | 数据源 |
|------|--------|
| A股 | akshare（东方财富/新浪财经） |
| 港股 | Yahoo Finance |
| 美股 | Yahoo Finance |
| 加密货币 | CoinGecko API |
| 新闻 | RSS feeds + CoinGecko News |

所有数据源均为 **免费**，无需 API Key。

## 🛠 本地运行

```bash
pip install -r requirements.txt
python scripts/main.py
# 完成后打开 index.html
```

## 📁 项目结构

```
├── .github/workflows/update.yml   # GitHub Actions 定时任务
├── scripts/
│   ├── config.py                  # ⭐ 你的投资标配置
│   ├── main.py                    # 主入口
│   ├── fetch_stocks.py            # A股数据抓取
│   ├── fetch_global.py            # 港股/美股数据抓取
│   ├── fetch_crypto.py            # 加密货币数据抓取
│   └── fetch_news.py              # 新闻抓取
├── templates/
│   └── index.html                 # HTML 模板
├── data/                          # 历史数据存档
├── index.html                     # 生成的网页（自动更新）
└── requirements.txt
```
