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
                      tech_score=0, fund_score=0, news_score=0):
    """
    发送交易信号邮件通知

    参数：
      asset: str — 资产名称 "BTC" / "ETH"
      signal: str — "做多 LONG" / "做空 SHORT"
      direction: str — "bullish" / "bearish"
      score: int — 综合评分 0-100
      entry_price: float — 入场价
      stop_loss: float — 止损价
      take_profit: float — 止盈价
      rr_ratio: float — 盈亏比
      risk_pct: float — 风险百分比
      reward_pct: float — 收益百分比
      confidence: str — 置信度 "高"/"中高"/"中"/"低"
      win_rate_est: int — 预估胜率
      trend_summary: str — 趋势摘要
      cur_price: float — 当前价格
      atr_pct: float — ATR 波动率百分比
      tech_score: int — 技术面得分
      fund_score: int — 基本面得分
      news_score: int — 消息面得分

    返回: True/False — 是否发送成功
    """

    # ── 构建邮件 ──
    direction_emoji = "🟢" if direction == "bullish" else "🔴"
    rr_color = "✅" if rr_ratio >= 2 else "⚠️" if rr_ratio >= 1.5 else "❌"
    score_color = "🟢" if score >= 70 else "🟡" if score >= 55 else "🔴"

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M Beijing")
    subject = f"{direction_emoji} [{asset}] {signal} — 评分 {score}/100 | {datetime.now().strftime('%H:%M')}"

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
          <div style="font-size: 32px; font-weight: 900;">{score_color} {score}<span style="font-size: 16px; color: #8b949e;">/100</span></div>
          <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">
            置信度: <b style="color: #e6edf3;">{confidence}</b> &nbsp;|&nbsp;
            预估胜率: <b style="color: #e6edf3;">{win_rate_est}%</b>
          </div>
          <div style="display: flex; height: 4px; border-radius: 2px; overflow: hidden; margin-top: 8px;">
            <div style="background: #58a6ff; width: {tech_score/100*100}%;"></div>
            <div style="background: #3fb950; width: {fund_score/100*100}%;"></div>
            <div style="background: #d2991d; width: {news_score/100*100}%;"></div>
          </div>
          <div style="font-size: 10px; color: #555d68; margin-top: 3px;">
            技术{tech_score}/60 &nbsp; 基本{fund_score}/20 &nbsp; 消息{news_score}/20
          </div>
        </div>

        <!-- 交易计划 -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
          <tr>
            <td style="background: #181f2a; border-radius: 6px; padding: 10px; text-align: center; width: 25%;">
              <div style="font-size: 10px; color: #8b949e;">💰 入场价</div>
              <div style="font-size: 16px; font-weight: 800; color: #58a6ff;">${entry_price:,.2f}</div>
            </td>
            <td style="width: 4px;"></td>
            <td style="background: rgba(248,81,73,.1); border-radius: 6px; padding: 10px; text-align: center; width: 25%;">
              <div style="font-size: 10px; color: #8b949e;">🛑 止损</div>
              <div style="font-size: 16px; font-weight: 800; color: #f85149;">${stop_loss:,.2f}</div>
              <div style="font-size: 10px; color: #555d68;">风险 {risk_pct:.2f}%</div>
            </td>
            <td style="width: 4px;"></td>
            <td style="background: rgba(63,185,80,.1); border-radius: 6px; padding: 10px; text-align: center; width: 25%;">
              <div style="font-size: 10px; color: #8b949e;">🎯 止盈</div>
              <div style="font-size: 16px; font-weight: 800; color: #3fb950;">${take_profit:,.2f}</div>
              <div style="font-size: 10px; color: #555d68;">收益 {reward_pct:.2f}%</div>
            </td>
            <td style="width: 4px;"></td>
            <td style="background: #181f2a; border-radius: 6px; padding: 10px; text-align: center; width: 25%;">
              <div style="font-size: 10px; color: #8b949e;">📊 盈亏比</div>
              <div style="font-size: 16px; font-weight: 800; color: #d2991d;">{rr_ratio:.1f}:1</div>
              <div style="font-size: 10px; color: #555d68;">{rr_color}</div>
            </td>
          </tr>
        </table>

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

    # ── 发送 ──
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

        print(f"[邮件] ✅ 已发送 → {EMAIL_TO}")
        return True

    except smtplib.SMTPAuthenticationError:
        print(f"[邮件] ❌ QQ 邮箱认证失败！请检查授权码是否正确（不是 QQ 密码）")
        print(f"[邮件]    获取授权码: QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码")
        return False
    except Exception as e:
        print(f"[邮件] ❌ 发送失败: {e}")
        return False
