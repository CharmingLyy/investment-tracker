# 🗞️ 每日硬核情报简报 | 2026-11-09

> 💡 *"用最毒舌的视角，看最前沿的科技。"*

---

### 1. 📌 Rust + WebGPU 硬刚 SketchUp：KetchUp 开源了 (来源: Hacker News)
- **核心干货**：一个用 Rust 和 WebGPU 从零重写的 SketchUp 开源替代品，直接在浏览器里跑 3D 建模。老牌 CAD 软件靠授权费吃了几十年，Web 端原生 GPU 加速这条路终于有人认真走通了——不用装客户端、不用买 license，打开网页就能拉模型。
- **毒舌/硬核点评**：SketchUp 母公司 Trimble 看到这个 HN 338 分的项目，估计一边喝咖啡一边默默给法务部发消息。开源社区的逻辑永远是：你收费，我就重写一个；你重写不动，说明你该被重写了。
- **🔗 传送门**：[点击直达原链接](https://ketchup3d.github.io/app/)

---

### 2. 📌 OpenAI 推出 GPT-6 Cyber：AI 挖出 81 个 Firefox 漏洞、948 个 Linux 提权链 (来源: Tech News)
- **核心干货**：OpenAI 发布专攻安全研究的 GPT-6 Cyber，官方称其在漏洞发现与修复上实现"阶跃式"提升——辅助挖出 81 个 Firefox 缺陷、948 条 Linux 提权路径。这把"AI 安全研究员"从概念验证推到了量产阶段，红队/蓝队的成本结构要被重算。
- **毒舌/硬核点评**：一边是 AI 几小时扫出近千个提权链，一边是厂商补丁排期排到明年——攻防速度差正在被 AI 拉到荒谬的程度。以后的安全工程师不是写 exploit 的人，而是给 AI 的 exploit 写 PR 的人。
- **🔗 传送门**：[点击直达原链接](https://thehackernews.com/2026/11/openai-launches-gpt-6-cyber-after-ai.html)

---

### 3. 📌 OpenSSH "SSHole" 漏洞披露数小时内即遭在野利用，蜜罐被拿 root (来源: Tech News)
- **核心干货**：CVE-2026-123158（CVSS 8.1），代号 SSHole，影响无密码账户的 OpenSSH 登录逻辑，攻击者可借此直接登入并拿到 root。披露后数小时内就有攻击者拿蜜罐开刀——从 PoC 到武器化的窗口已经压缩到"小时级"。
- **毒舌/硬核点评**：漏洞代号起得像个段子，利用速度可一点不好笑。还在用"下周再打补丁"节奏运维的朋友，这次蜜罐里被 root 的说不定就是你。CVSS 8.1 配小时级在野利用，这组合比任何安全周报标题都刺激。
- **🔗 传送门**：[点击直达原链接](https://thehackernews.com/2026/11/hackers-exploited-openssh-sshole-flaw.html)

---

### 🗣️ 今日顶男金句
> 漏洞不会等你排期，AI 也不会等你学会用 AI——唯一稳赚不赔的复利，是把"下周再说"改成"现在就跑"。