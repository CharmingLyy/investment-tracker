# 🗞️ 每日硬核情报简报 | 2026-09-12

> 💡 *"用最毒舌的视角，看最前沿的科技。"*

---

### 1. 📌 Shopify 从 React Native 撤回原生开发 (来源: HackerNews)
- **核心干货**：Shopify 工程团队正式宣布将主力 App 从 React Native 迁回 Swift 和 Kotlin 原生开发。核心原因在于跨平台方案在复杂业务场景下的性能瓶颈、调试地狱以及对平台新特性（如实时活动、灵动岛）的适配延迟，已经严重拖累了迭代速度。这是继 Airbnb、Dropbox 之后，又一家巨头用脚投票的"回头是岸"案例。
- **毒舌/硬核点评**：跨平台框架的经典生命周期——"Write once, debug everywhere, rewrite natively"。Meta 自己都在给 RN 团队缩编，你还指望它替你扛住日活千万的电商流量？省下来的那点人力成本，最后都加倍还给了用户流失率。
- **🔗 传送门**：[点击直达原链接](https://shopify.engineering/back-to-native)

---

### 2. 📌 Cisco FMC 满分漏洞遭在野利用，Qilin 勒索软件趁火打劫 (来源: 科技新闻)
- **核心干货**：Cisco Secure Firewall Management Center 爆出 CVSS 10.0 满分的认证绕过漏洞（CVE-2026-20079），已被至少三个威胁团伙用于窃取凭证并投递 Qilin 勒索软件，其中包含国家背景 APT。安全设备自己成了最大的攻击入口——这已经不是黑色幽默，而是行业常态。
- **毒舌/硬核点评**：防火墙管理平台被打穿，相当于你请的保镖自己先把门打开了。CVSS 10.0 的漏洞配上"已修复但你没打补丁"的经典剧本，建议各位运维今天别摸鱼了，先去把 FMC 的补丁打上，不然明天摸鱼的就是勒索软件了。
- **🔗 传送门**：[点击直达原链接](https://thehackernews.com/2026/09/cisco-fmc-flaws-exploited-to-steal.html)

---

### 3. 📌 微软将 Rust 列为一级语言 (来源: Lobste.rs)
- **核心干货**：Rust 基金会发文确认，微软内部已将 Rust 提升为 Tier-1 语言，与 C#、C++ 平起平坐。这意味着 Windows 内核、Azure 基础设施、Office 核心组件等关键路径将大规模采用 Rust 重构。考虑到微软过去几年在 Windows 内核中用 Rust 重写组件、以及 Azure 上 Rust 服务的扩张，这一步更像是"官宣既成事实"。
- **毒舌/硬核点评**：C++ 在微软的地位，大概就像当年的 IE——还在用，但没人想维护了。Rust 的借用检查器虽然让程序员写代码时痛不欲生，但总比半夜被内存安全漏洞的 P0 告警叫醒要强。微软这波操作，本质上是给过去二十年 C++ 留下的技术债买了一份保险。
- **🔗 传送门**：[点击直达原链接](https://rustfoundation.org/media/guest-post-rust-is-tier-1-language-at-microsoft/)

---

### 🗣️ 今日顶男金句
**"技术选型最大的陷阱不是选错了框架，而是选了一个让你在第三年才发现选错的框架——那时候，重写成本已经够你再选错三次了。"**