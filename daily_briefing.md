# 🗞️ 每日硬核情报简报 | 2026-11-28

> 💡 *"用最毒舌的视角，看最前沿的科技。"*

---

### 1. 📌 Google DeepCrossAttention：残差连接终于不再拖后腿 (来源: HackerNews / Google Research)
- **核心干货**：Google 对 Transformer 的残差连接动了刀，DeepCrossAttention 在保持模型质量的前提下把训练速度拉高到 3 倍。核心思路是让注意力层更高效地复用跨层信息，直击当下大模型"堆层数堆到电费爆炸"的痛点——同样效果，少烧三分之二的卡。
- **毒舌/硬核点评**：残差连接这个 2015 年的老古董终于被请去体检了。3 倍加速很香，但请先别急着吹"改变游戏规则"——等有人复现出同样曲线再开香槟，毕竟 Google 的 blog 图从来都画得比结果好看。
- **🔗 传送门**：[点击直达原链接](https://research.google/blog/supercharging-transformer-residual-connections/)

---

### 2. 📌 黑五惊魂：WebRTC 信用卡侧录脚本潜伏主流购物站 (来源: HackerNews / InfoHawk)
- **核心干货**：安全团队在多个热门电商站点发现利用 WebRTC 数据通道外传信用卡数据的侧录脚本，专门挑黑五流量高峰动手。相比传统偷 data 方式，走 WebRTC 能绕过不少基于 XHR/fetch 的监控规则——换句话说，你的卡号可能正被人用"视频通话"的姿势偷走。
- **毒舌/硬核点评**：黑五打折的是商品，不是你的银行卡余额。WebRTC 本是用来开会的，现在成了小偷的加密专线——技术无罪，用技术的人该进去了。今天下单前，先祈祷自己逛的不是"惊喜"站点。
- **🔗 传送门**：[点击直达原链接](https://www.infohawk.com/news/2026-11-27-black-friday-webrtc-skimmer)

---

### 3. 📌 Cacti 零日 4HTTP2SHELL：四个请求，从访客到 root (来源: Tech RSS / The Hacker News)
- **核心干货**：开源网络监控工具 Cacti 爆出未修补零日漏洞，攻击者仅凭访客权限、发四个 HTTP 请求即可远程执行代码直取 root，PoC 已被命名为 4HTTP2SHELL / 4HTTP2ROOT，尚无 CVE 编号。监控系统本身成了被监控对象的提权跳板，内网里跑 Cacti 的运维今晚别想睡了。
- **毒舌/硬核点评**：一个用来"监控"的工具，自己先被四个请求打穿了——这讽刺程度堪比保安队长带头翻墙。运维兄弟们，要么打补丁，要么今晚把 Cacti 从公网摘了，别等它变成你的 root 后门。
- **🔗 传送门**：[点击直达原链接](https://thehackernews.com/2026/11/unpatched-cacti-zero-day-enables-rce-in.html)

---

### 🗣️ 今日顶男金句
> 技术的护城河从来不是"我会用"，而是"我知道它什么时候会背刺我"——会调 API 的人满地都是，能预判零日的人才是稀缺资产。