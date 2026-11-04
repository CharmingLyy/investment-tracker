# 🗞️ 每日硬核情报简报 | 2026-11-05

> 💡 *"用最毒舌的视角，看最前沿的科技。"*

---

### 1. 📌 Nvidia RTX Spark 固件加密，Linux 上推理速度被砍至 35% (来源: HackerNews)
- **核心干货**：Nvidia 在新款 RTX Spark 笔记本上引入了加密固件，直接导致 Linux 下 AI 推理性能暴跌至原来的 35%。这不是驱动 bug，是设计层面的"锁"——厂商用加密把优化路径攥在自己手里，开源生态和本地部署用户被当成了二等公民。
- **毒舌/硬核点评**：卖你算力，再卖你"解锁算力"的资格，这商业模式比显卡还赚钱。Linux 玩家花全款买了个阉割版，黄氏刀法已经精确到固件层了。
- **🔗 传送门**：[点击直达原链接](https://www.mindstudio.ai/blog/linux-nvidia-rtx-spark-laptop)

---

### 2. 📌 AMD 预计 Q4 史上首次在销量上超越 Intel (来源: HackerNews)
- **核心干货**：AMD 给出 170 亿美元季度指引，首次在营收预期上压过 Intel。四十年的 x86 霸权格局正在实质性翻转，背后是数据中心 EPYC 的持续蚕食和 Intel 代工战略的持续失血。
- **毒舌/硬核点评**：Intel 花了四年讲"IDM 2.0 复兴故事"，AMD 用一张财报把它变成了"回忆录"。摩尔定律没死，死的是躺着收租的那位。
- **🔗 传送门**：[点击直达原链接](https://www.tomshardware.com/pc-components/cpus/amd-expects-to-outsell-intel-in-q4-for-the-first-time-in-history-usd17b-guidance-would-exceed-intels-projections)

---

### 3. 📌 Zig 重写 libc 反而让 SQLite 慢了 12000 倍：Shlemiel 画匠归来 (来源: Lobste.rs)
- **核心干货**：Zig 团队重写 libc 时踩了个经典性能坑——某个字符串/内存操作的复杂度从 O(n) 退化成 O(n²) 级别，直接把 SQLite 拖慢上万倍。这是"重写底层轮子"的教科书级反面案例：功能对了，渐进复杂度崩了。
- **毒舌/硬核点评**：重写 libc 的勇气值得敬佩，但 Shlemiel 画匠的故事告诉我们——不是所有轮子都该重造，尤其是你还没搞懂原轮子为什么那么圆的时候。性能测试不写，12000 倍教做人。
- **🔗 传送门**：[点击直达原链接](https://dennisforbes.ca/blog/microblog/2026/10/the_accidental_12000x_sqlite_slowdown/)

---

### 🗣️ 今日顶男金句
"重写底层不是勇气，是负债——你欠下的每一行复杂度，性能测试都会连本带利地讨回来。"