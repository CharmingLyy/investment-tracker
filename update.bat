@echo off
chcp 65001 >nul
cd /d E:\AI_investment_observation
echo ============================================================
echo 📊 投资观察面板 - 数据更新中...
echo ============================================================
python scripts\main.py
echo.
echo ✅ 更新完成！正在打开网页...
start index.html
