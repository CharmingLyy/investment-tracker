# 🗞️ 每日硬核情报简报 | 2026-09-16

> 💡 *"用最毒舌的视角，看最前沿的科技。"*

---

### 1. 📌 Homebrew 7.0.0 正式发布 (来源: Tech RSS / Reddit r/programming)
- **核心干货**：Homebrew 迎来史诗级大版本更新——安装升级速度大幅提升、沙箱隔离更严格、终于有了原生 macOS 图形应用、内置漏洞检查和 advisory 数据库。同时正式抛弃 macOS 10.15，Intel Mac 被降级为 Tier 3 二等公民。Apple Silicon 用户享受预编译 bottle 的 Tier 1 待遇。
- **毒舌/硬核点评**：Homebrew 终于想起来自己是个包管理器而不是"每次 brew update 都能泡杯咖啡"的行为艺术。Intel Mac 被踢进 Tier 3，库克看了都想说："我早就不生产你们了，Homebrew 只是替我补了一刀。"
- **🔗 传送门**：[点击直达原链接](https://www.reddit.com/r/programming/comments/1wftm95/homebrew_700_faster_installations_and_upgrades/)

---

### 2. 📌 Capsule——单文件 Web 应用，数据直接存进 SQLite (来源: Hacker News | 115 分)
- **核心干货**：用 Rust 写的一个新工具，把整个 Web 应用打包成单个文件（扩展名就是 `.capsule`），数据直接内嵌 SQLite 存储。解决了"写 HTML 页面很简单，但一涉及存数据和分享就得部署服务器"的经典痛点。写完即分享，打开即运行。
- **毒舌/硬核点评**：这玩意儿的哲学是"你的数据不配拥有服务器"。对于做小工具、内部 demo、个人知识库的人来说，它可能比 Docker + Nginx + Postgres 三件套香一万倍。当然，如果你的应用需要 10 万并发，请自觉绕道——这不是给你准备的。
- **🔗 传送门**：[点击直达原链接](https://withcapsule.app/)

---

### 3. 📌 Red Heron 利用 Gitea RCE 漏洞攻陷六国 13 家组织 (来源: The Hacker News)
- **核心干货**：疑似中国背景的威胁组织 Red Heron 快速武器化了 Gitea 的一个远程代码执行漏洞，扫描了 7 个国家 1386 个 Gitea 实例，成功攻陷 13 家组织的面向公网实例。这是典型的"补丁空窗期"猎杀——漏洞刚披露就被大规模利用。
- **毒舌/硬核点评**：自建 Gitea 的人以为自己逃离了 GitHub 的"监控"，结果发现自己直接暴露在了攻击者的枪口下，连个 WAF 都没挂。你以为你在搞"代码自主可控"，实际上是在给黑客搞"资产自主可控"。自托管的第一课永远是：先学会打补丁，再谈自由。
- **🔗 传送门**：[点击直达原链接](https://thehackernews.com/2026/09/red-heron-exploits-gitea-rce-to.html)

---

### 🗣️ 今日顶男金句

> **"自托管不是自由的终点，而是运维责任的起点——你省下的 SaaS 订阅费，最终会以凌晨三点修漏洞的形式还回去。"**