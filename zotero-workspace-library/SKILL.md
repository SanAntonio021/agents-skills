---
name: zotero-workspace-library
description: 统一工作区中的 Zotero 分类、参考资料归属、跨工作区关联和项目入口。Use when deciding where a paper, standard, manufacturer document, device manual, or other external reference belongs in Zotero, or when setting a workspace README reference-library pointer. Actual Zotero reads and writes follow the existing Zotero operation guidance; paper search/download and laboratory-manual workflows remain with their specialist skills.
---

# Zotero 工作区资料归档

本技能统一 Zotero 的分类和工作区入口。Zotero 接口选择、查重、写入保护、超时恢复及回读按 [`paper-download` 的 Zotero 操作细则](../paper-download/references/zotero-storage.md)执行；论文检索和下载分别由 `paper-search`、`paper-download` 负责，设备手册由 `lab-resources` 负责。

## 分类

按“工作区 → 资料类型 → 必要时再细分”归档。常用类型为“论文”“标准”“器件手册”；其他资料类型只在有实际资料需要时建立，不预建空集合。

- 论文先进入工作区的“论文”集合。同一研究方向的多篇论文共用该集合，不按单篇文章或一次检索任务建集合。只有出现多个稳定、相对独立的研究方向时，才在“论文”下建立方向子集合。
- 器件手册先进入“器件手册”；当器件类别确实有助于查找时，再建立有资料的类别子集合。
- 标准及其他资料按资料本身的类型归档；不按下载批次、检索任务或文章引用状态建集合。
- 只读查询、临时搜索候选和用户明确要求不写库的任务保持只读。进入工作区参考资料、用于持续设计或研究的外部资料按需归档，不把搜索结果数量当作归档目标。

## 资料归属

- 论文、正式标准、公开厂家资料，以及无保密或存储限制的供应商技术手册和规格书，归 Zotero。
- 项目自产的代码、数据、仿真、实验记录和报告留在项目。外部参考文件不在项目中长期保留第二份 PDF；项目材料记录 Zotero 条目或集合入口。已有本地副本保持原样，本技能不触发历史文件迁移或删除。
- 报价、询价邮件、采购往来等商务记录不作为 Zotero 参考资料归档；按项目现有商务记录规则处理。存在保密、许可或存储限制的供应商资料，在限制明确前不入库。
- 同一资料在同一 Zotero 资料库中只保留一个条目和一份附件。多个工作区需要该资料时，把同一条目加入各自集合，不复制条目或 PDF。
- 若工作区对应不同 Zotero 资料库，不能用跨库集合关联；不要自动复制，先说明限制并确定共用资料库或其他处理方式。

## 工作区入口

工作区 `README.md` 可在对应集合建立后提供 Zotero 入口。先核实当前 Zotero 环境支持的集合链接形式；只有读回确认有效后才写可点击链接。若没有经验证的链接形式，写明集合层级名称和 Zotero 内检索方式，不猜 URI 或 key。

论文工程中的 `.bib`、DOI、引用键及具体章节用途仍留在论文工程或研究材料中；Zotero 集合用于资料归属，不代表条目已被某篇稿件引用。

## 写入边界

先判断请求是否允许写入。只读、讨论或仅要求候选清单时不改 Zotero；授权归档后再按上述操作细则检查接口和目标分类。Zotero 暂不可用时继续独立的研究工作，并说明尚未完成的归档项；不以项目内长期 PDF 副本替代 Zotero，也不声称已完成归档。
