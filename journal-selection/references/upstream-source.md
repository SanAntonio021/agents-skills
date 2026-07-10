# 上游来源说明

本 skill 的方法论骨架和部分期刊画像改写自：

- **仓库**：brycewang-stanford/Awesome-Journal-Skills（https://github.com/brycewang-stanford/Awesome-Journal-Skills）
- **许可证**：MIT
- **本地镜像**：`D:\BaiduSyncdisk\.agents\upstream\brycewang-Awesome-Journal-Skills`（sparse checkout）
- **吸收时提交**：`d08b584`

## 对应关系

| 本地内容 | 上游来源 | 吸收方式 |
|---|---|---|
| SKILL.md 五步流程（画像→候选→五维→三档→阶梯） | `shared-resources/journal-selection/journal-match.md` | 结构改写：五信号画像本地化为太赫兹方向的信号（子方向/证据形态/贡献类型/实验数据/强度），去掉经管社科的 lane/DiD/IV 词汇；保留 reach/match/safe 三档、降级阶梯、"易变事实不凭记忆"硬规则 |
| journal-profiles.md 中 TWC 画像 | `Engineering-Technology-Journal-Skills/skills/ieee-transactions-on-wireless-communications/SKILL.md` | 红线与秒拒条目中文改写，保留原判据 |
| journal-profiles.md 中 TCOM 画像 | 上游镜像 `Engineering-Technology-Journal-Skills/skills/ieee-transactions-on-communications/SKILL.md` | 同上 |
| journal-profiles.md 中 NC 画像 | `English-NaturalScience-Journal-Skills/skills/nature-communications/SKILL.md` | 同上 |
| journal-profiles.md 中 TTST/TMTT 画像 | 上游无此二刊 | 借上游期刊 skill 的版式（定位→红线→秒拒→分流→官方核查）本地起草，标注 `[初稿待校准]` |
| 各刊"官方核查"条目 | `Engineering-Technology-Journal-Skills/resources/official-source-map.md` | 只保留 IEEE Author Center / nature.com 入口指向，具体页面现查 |

## 上游已知问题

- 上游 TAP skill 的改投表引用了不存在的 `ieee-transactions-on-microwave-theory-and-techniques` 条目（TMTT 在上游整个仓库中并不存在，属幽灵引用）。本地画像文件的兄弟刊分流表不沿用上游改投目标名，只指向本地画像库内的刊。

## 未吸收部分

- 上游 `venue-index.tsv`（185 个 depth pack 索引）：绑定其仓库结构，本地刊池小，直接写进 journal-profiles.md。
- 上游五维中的"录用率/周转数据读 source-map"机制：本地无 live-check 运营，改为输出"待核查"清单交给用户现查。
- 经管社科相关的 lane 体系、`*-topic-selection` 委托机制。
