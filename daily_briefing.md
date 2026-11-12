# 🗞️ 每日硬核情报简报 | 2026-11-13

> 💡 *"用最毒舌的视角，看最前沿的科技。"*

---

### 1. 📌 黄仁勋卸任英伟达 CEO (来源: HackerNews / AP News)
- **核心干货**：执掌英伟达三十余年的"皮衣刀客"Jensen Huang 正式宣布卸任 CEO，官方新闻稿已挂上 nvidianews，同时 Reuters 等媒体跟进报道。HN 上炸出 2000+ 评论、2000+ 分数，堪称年度最重量级人事地震。考虑到英伟达当前是全球 AI 算力供应链的绝对中枢，这次交棒直接牵动整个半导体与 AI 行业的资本叙事。
- **毒舌/硬核点评**：卖铲子的人要换掌柜了，而全世界还在排队抢铲子。真正的悬念不是"谁接班"，而是新 CEO 会不会把 CUDA 生态继续当护城河，还是转头就去追下一波叙事——毕竟华尔街只认增长，不认情怀。
- **🔗 传送门**：[点击直达原链接](https://apnews.com/article/nvidia-megaspeed-china-singapore-huang-5403f152a601cf82ce939f1d24fffa0f)

---

### 2. 📌 Rust 1.100.0 发布 (来源: GitHub Releases)
- **核心干货**：Rust 语言正式迈入"1.100"这个里程碑版本号。对一个以"稳定压倒一切"为信条的 systems 语言来说，三位数版本号本身就是个象征——从 2015 年 1.0 到今天，它已经从 Mozilla 的实验项目长成操作系统、浏览器引擎、云基础设施的底层主力。这个版本值得关注的是长期积累的 API 稳定性与工具链成熟度，而非某个单一特性。
- **毒舌/硬核点评**：别的语言在卷新语法新特性，Rust 在卷"我们又一次没有破坏任何东西"。在一个到处是 breaking change 的行业里，"无聊的稳定"反而是最稀缺的奢侈品——顺便，借用检查器依旧不会对你手下留情。
- **🔗 传送门**：[点击直达原链接](https://github.com/rust-lang/rust/releases/tag/1.100.0)

---

### 3. 📌 Humble Bundle 用"Vibe Coding"把自家安全体系干碎了 (来源: Lobste.rs)
- **核心干货**：Humble Bundle 被曝因大量依赖 AI 辅助的"氛围编程"（vibecoding）来改代码，导致大部分安全机制被实质性摧毁。这不是理论风险，而是"把安全交给 AI 生成、没人真正 review"的现实翻车案例，对当下所有"AI 写代码、人闭眼合并"的团队是一记响亮耳光。
- **毒舌/硬核点评**：当"让 AI 帮你写"遇上"没人看得懂也懒得看"，结果就是安全团队集体失业、攻击者集体上岗。Vibe coding 的尽头不是生产力革命，是 CVE 流水线——代码可以 vibe，安全不能 vibe。
- **🔗 传送门**：[点击直达原链接](https://forums.spacebattles.com/threads/humble-bundle-just-completely-killed-most-of-their-security-through-vibecoding.1346295/)

---

### 🗣️ 今日顶男金句
> "让 AI 帮你写代码是效率，让 AI 帮你写安全是自杀——工具越聪明，越考验用它的人到底有没有脑子。"