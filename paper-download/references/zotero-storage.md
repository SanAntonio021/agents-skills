# Zotero 操作兼容入口

Zotero 的连接、查询、写入、保护和回读已统一迁入 [zotero-workspace-library](../../zotero-workspace-library/SKILL.md)，具体字段见 [公共接口契约](../../zotero-workspace-library/references/contract.md)。此文件保留旧引用；公共实现只维护一份。

## 连接与接口选择

调用公共命令，连接检查已内嵌。原 [状态脚本](../scripts/zotero_local_status.py) 仅转调公共连接模块，保留原状态字段与退出码；缺依赖时明确报错。

## 自动抓取与原操作检查

由 `archive/prune` 内部执行，参见 [公共执行层的失败与恢复](../../zotero-workspace-library/SKILL.md#失败与恢复)。不要自行读 token、暂停设置或切换接口重放。

## 已有条目补 PDF

按 [下载主流程](../SKILL.md#执行流程)复验交接身份和版本，本地文件使用 [zotero_archive.py](../scripts/zotero_archive.py) 的 `--request`，传入 `parent_key` 和 `pdf` 或 `reuse_pdf`；机构会话使用下载 CLI 的 `finalize --session --request`。两者调用公共归档；助手交接 key 用 `--parent-key-source assistant`，用户指定默认 `user`，明确版本用 `--required-version`。匹配算法与恢复语义只在公共层维护。

## 版本去重执行

业务层核实候选，执行层用 `prune --request` 复核阅读内容、文件与归属后移入回收站，未知保留。

## 工作区集合操作

分类政策由 [zotero-workspace-library](../../zotero-workspace-library/SKILL.md) 决定，查询及实际集合关系由公共命令执行。

## 隔离试跑与未验证项

历史隔离场景、当时限制和真实读写记录完整保留在 [迁移前记录](zotero-storage-history.md#隔离试跑与未验证项)。不以旧版验证替代新版真实验收。

## 已验证范围

[2026-09-10 等历史实测](zotero-storage-history.md#已验证范围) 保留当时条件；当前实施验收见公共层测试和本次交付记录。
