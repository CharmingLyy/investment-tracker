"""
邮件发送模块 — QQ 邮箱 SMTP
使用方式：
  from scripts.send_email import send_signal_email
  send_signal_email(asset="BTC", signal="做多 LONG", score=72, ...)

环境变量配置（推荐）：
  AI_MONITOR_EMAIL_FROM    发件人 QQ 邮箱地址
  AI_MONITOR_EMAIL_PASSWORD QQ 邮箱 SMTP 授权码（非 QQ 密码！）
  AI_MONITOR_EMAIL_TO      收件人邮箱（默认同发件人）
"""
import smtplib
import os
import sys
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


# ── 配置 ──
SMTP_SERVER = os.environ.get("AI_MONITOR_SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = int(os.environ.get("AI_MONITOR_SMTP_PORT", "465"))
EMAIL_FROM = os.environ.get("AI_MONITOR_EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("AI_MONITOR_EMAIL_PASSWORD", "")
EMAIL_TO = os.environ.get("AI_MONITOR_EMAIL_TO", EMAIL_FROM)  # 默认发给发件人自己


def is_configured():
    """检查邮件是否已配置"""
    return bool(EMAIL_FROM and EMAIL_PASSWORD)


def send_signal_email(asset, signal, direction, score, entry_price, stop_loss,
                      take_profit, rr_ratio, risk_pct, reward_pct, confidence,
                      win_rate_est, trend_summary, cur_price, atr_pct,
                      tech_score=0, fund_score=0,
                      take_profit1=None, take_profit2=None,
                      tp1_pct=0, tp2_pct=0, position_pct1=50,
                      breakeven_price=None):
    """
    发送交易信号邮件通知（两段式止盈 + 保本止损）

    参数：
      asset: str — 资产名称 "BTC" / "ETH"
      signal: str — "做多 LONG" / "做空 SHORT"
      ...
      take_profit1: float — 第一止盈价 (平仓 position_pct1%)
      take_profit2: float — 第二止盈价 (平仓剩余%)
      position_pct1: int — TP1 平仓比例
      breakeven_price: float — TP1 触发后的保本止损价
    """

    # ── 构建邮件 ──
    direction_emoji = "🟢" if direction == "bullish" else "🔴"
    rr_color = "✅" if rr_ratio >= 2 else "⚠️" if rr_ratio >= 1.5 else "❌"
    score_color = "🟢" if score >= 55 else "🟡" if score >= 40 else "🔴"

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M Beijing")
    subject = f"{direction_emoji} [{asset}] {signal} — 评分 {score} | {datetime.now().strftime('%H:%M')}"

    # HTML 格式邮件正文
    html_body = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0e14; color: #e6edf3; padding: 20px;">
      <div style="max-width: 480px; margin: 0 auto; background: #131820; border-radius: 12px; padding: 24px; border: 1px solid #1e293b;">

        <!-- 标题 -->
        <h2 style="margin: 0 0 16px 0; font-size: 20px;">
          {direction_emoji} {asset} · {signal}
        </h2>

        <!-- 价格 -->
        <div style="background: #181f2a; border-radius: 8px; padding: 12px; margin-bottom: 12px; text-align: center;">
          <span style="font-size: 12px; color: #8b949e;">当前价格</span><br>
          <span style="font-size: 28px; font-weight: 800; color: #58a6ff;">
            ${entry_price:,.2f}
          </span>
        </div>

        <!-- 评分 -->
        <div style="background: #181f2a; border-radius: 8px; padding: 12px; margin-bottom: 12px; text-align: center;">
          <div style="font-size: 32px; font-weight: 900;">{score_color} {score}<span style="font-size: 16px; color: #8b949e;"> 分</span></div>
          <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">
            置信度: <b style="color: #e6edf3;">{confidence}</b> &nbsp;|&nbsp;
            预估胜率: <b style="color: #e6edf3;">{win_rate_est}%</b>
          </div>
          <div style="display: flex; height: 4px; border-radius: 2px; overflow: hidden; margin-top: 8px;">
            <div style="background: #58a6ff; width: {tech_score/80*100}%;"></div>
            <div style="background: #3fb950; width: {fund_score/80*100}%;"></div>
          </div>
          <div style="font-size: 10px; color: #555d68; margin-top: 3px;">
            技术{tech_score}/60 &nbsp; 基本{fund_score}/20
          </div>
        </div>

        <!-- 交易计划 — 两段式止盈 + 保本止损 -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
          <tr>
            <td style="background: #181f2a; border-radius: 6px; padding: 10px; text-align: center; width: 24%;">
              <div style="font-size: 10px; color: #8b949e;">💰 入场</div>
              <div style="font-size: 16px; font-weight: 800; color: #58a6ff;">${entry_price:,.2f}</div>
            </td>
            <td style="width: 3px;"></td>
            <td style="background: rgba(248,81,73,.1); border-radius: 6px; padding: 10px; text-align: center; width: 24%;">
              <div style="font-size: 10px; color: #8b949e;">🛑 止损</div>
              <div style="font-size: 16px; font-weight: 800; color: #f85149;">${stop_loss:,.2f}</div>
              <div style="font-size: 10px; color: #555d68;">风险 {risk_pct:.2f}%</div>
            </td>
            <td style="width: 3px;"></td>
            <td style="background: rgba(63,185,80,.1); border-radius: 6px; padding: 10px; text-align: center; width: 24%;">
              <div style="font-size: 10px; color: #8b949e;">🎯 止盈① {position_pct1}%</div>
              <div style="font-size: 16px; font-weight: 800; color: #3fb950;">${take_profit1 or take_profit:,.2f}</div>
              <div style="font-size: 10px; color: #555d68;">+{tp1_pct:.2f}% → 保本</div>
            </td>
            <td style="width: 3px;"></td>
            <td style="background: rgba(63,185,80,.08); border-radius: 6px; padding: 10px; text-align: center; width: 24%;">
              <div style="font-size: 10px; color: #8b949e;">🚀 止盈② {100-position_pct1}%</div>
              <div style="font-size: 16px; font-weight: 800; color: #2ecc71;">${take_profit2 or take_profit:,.2f}</div>
              <div style="font-size: 10px; color: #555d68;">+{tp2_pct:.2f}% 零风险</div>
            </td>
          </tr>
        </table>
        <div style="background: #181f2a; border-radius: 6px; padding: 10px; margin-bottom: 12px; font-size: 11px; color: #8b949e; text-align: center;">
          💡 止盈①触发后平仓<b>{position_pct1}%</b>，止损上移至<b>${breakeven_price or entry_price:,.2f}</b>（保本），剩余仓位零风险博弈止盈② &nbsp;|&nbsp; 📊 加权 R:R <b style="color: #d2991d;">{rr_ratio:.1f}:1</b> {rr_color}
        </div>

        <!-- 趋势 -->
        <div style="background: #181f2a; border-radius: 8px; padding: 10px; font-size: 12px; color: #8b949e;">
          📈 {trend_summary} &nbsp;|&nbsp; 波动率 ATR: {atr_pct:.2f}%
        </div>

        <!-- 脚注 -->
        <div style="margin-top: 16px; font-size: 10px; color: #555d68; text-align: center;">
          AI 加密货币监控 · {update_time} · 仅供参考不构成投资建议
        </div>
      </div>
    </body>
    </html>
    """

    # ── 发送（带重试） ──
    last_error = None
    for attempt in range(3):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = EMAIL_TO
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

            print(f"[邮件] ✅ 已发送 → {EMAIL_TO}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            print(f"[邮件] ❌ QQ 邮箱认证失败！请检查授权码是否正确（不是 QQ 密码）")
            print(f"[邮件]    获取授权码: QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码")
            print(f"[邮件]    ⚠️ 如果授权码正确但仍失败，可能是 QQ 邮箱拦截了异地 IP（GitHub 服务器在美国）")
            print(f"[邮件]    解决方法: QQ邮箱 → 设置 → 账户 → 安全设置 → 开启「允许异地登录」")
            return False  # 认证错误不重试
        except smtplib.SMTPException as e:
            last_error = e
            if attempt < 2:
                wait = (attempt + 1) * 3
                print(f"[邮件] ⚠️ SMTP 错误 (第{attempt+1}次): {e}，{wait}秒后重试...")
                time.sleep(wait)
        except Exception as e:
            last_error = e
            if attempt < 2:
                wait = (attempt + 1) * 3
                print(f"[邮件] ⚠️ 临时错误 (第{attempt+1}次): {e}，{wait}秒后重试...")
                time.sleep(wait)

    print(f"[邮件] ❌ 发送失败（3次重试后仍失败）: {last_error}")
    return False
