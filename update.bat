@echo off
chcp 65001 >nul 2>&1
cd /d E:\AI_investment_observation
echo ============================================================
echo   投资观察面板 - 数据更新
echo   %date% %time%
echo ============================================================
echo.
echo 正在抓取全球市场数据，请稍候...
echo (A股/港股/美股/加密货币 + 新闻，约60秒)
echo.
python scripts\main.py
echo.
echo 正在打开网页...
start index.html
