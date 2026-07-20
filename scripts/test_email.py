"""
邮件配置测试 — 验证 QQ 邮箱 SMTP 是否能正常发送
用法：设置环境变量后运行
  AI_MONITOR_EMAIL_FROM=你的QQ邮箱
  AI_MONITOR_EMAIL_PASSWORD=你的QQ授权码
  python scripts/test_email.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 从环境变量读取
EMAIL_FROM = os.environ.get("AI_MONITOR_EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("AI_MONITOR_EMAIL_PASSWORD", "")
EMAIL_TO = os.environ.get("AI_MONITOR_EMAIL_TO", EMAIL_FROM)

print("=" * 60)
print("📧 邮件配置诊断")
print("=" * 60)

# 1. 检查环境变量
print(f"\n1️⃣ 环境变量检查：")
print(f"   AI_MONITOR_EMAIL_FROM    = {'✅ ' + EMAIL_FROM if EMAIL_FROM else '❌ 未设置！'}")
print(f"   AI_MONITOR_EMAIL_PASSWORD = {'✅ ***' + EMAIL_PASSWORD[-4:] if EMAIL_PASSWORD else '❌ 未设置！'}")
print(f"   AI_MONITOR_EMAIL_TO      = {'✅ ' + EMAIL_TO if EMAIL_TO else '❌ 未设置！'}")

if not EMAIL_FROM or not EMAIL_PASSWORD:
    print("\n❌ 请先设置环境变量！")
    print("   Windows CMD:")
    print('     set AI_MONITOR_EMAIL_FROM=你的QQ邮箱@qq.com')
    print('     set AI_MONITOR_EMAIL_PASSWORD=你的QQ授权码')
    print('     python scripts/test_email.py')
    sys.exit(1)

# 2. 测试 SMTP 连接
print(f"\n2️⃣ SMTP 连接测试 (smtp.qq.com:465)...")
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

try:
    server = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10)
    print("   ✅ SMTP 连接成功")

    print(f"\n3️⃣ 登录测试 (QQ邮箱认证)...")
    server.login(EMAIL_FROM, EMAIL_PASSWORD)
    print("   ✅ 登录成功")

    print(f"\n4️⃣ 发送测试邮件...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🧪 [测试邮件] 加密货币监控系统 — {datetime.now().strftime('%H:%M:%S')}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    html = f"""
    <html><body style="font-family:sans-serif;padding:20px;">
    <h2>✅ 邮件配置测试成功！</h2>
    <p>如果你收到这封邮件，说明 QQ 邮箱 SMTP 配置正确。</p>
    <table style="border-collapse:collapse;">
      <tr><td style="padding:6px 12px;color:#666">发件人</td><td>{EMAIL_FROM}</td></tr>
      <tr><td style="padding:6px 12px;color:#666">收件人</td><td>{EMAIL_TO}</td></tr>
      <tr><td style="padding:6px 12px;color:#666">时间</td><td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
      <tr><td style="padding:6px 12px;color:#666">状态</td><td style="color:green;font-weight:bold">✅ 配置正确</td></tr>
    </table>
    <p style="color:#999;margin-top:16px;">之后当 BTC/ETH 出现交易信号（做多/做空，评分≥65），系统会自动发送交易通知。</p>
    </body></html>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))
    server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
    server.quit()
    print(f"   ✅ 邮件已发送到 {EMAIL_TO}")
    print(f"\n🎉 一切正常！请检查收件箱（包括垃圾邮件文件夹）")

except smtplib.SMTPAuthenticationError as e:
    print(f"   ❌ QQ邮箱认证失败！")
    print(f"   错误: {e}")
    print(f"   👉 请检查：")
    print(f"      1. 使用的是SMTP授权码，不是QQ密码")
    print(f"      2. 授权码是否正确（QQ邮箱→设置→账户→POP3/SMTP服务→生成授权码）")
    print(f"      3. 邮箱地址是否完整（包含@qq.com）")
except smtplib.SMTPException as e:
    print(f"   ❌ SMTP错误: {e}")
except Exception as e:
    print(f"   ❌ 未知错误: {type(e).__name__}: {e}")
