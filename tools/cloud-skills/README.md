# 云端单一来源构建

唯一行为源码仍为本仓库顶层技能目录。云端差异只在本目录的 JSON 配置与小型运行边界文件中逐项维护；原 SKILL、参考、脚本及 Windows / CC Switch 分发行为不改。没有自动同步、后台任务、认证或网络配置。

## 本批范围

- ask-first：保留显式调用；原试验配置兼容。
- handoff：沿用已有安装身份，保留五段交接与证据边界。
- humanizer：完整原文、33 项模式、三种调用模式及 MIT 许可；只适配依赖查找和宿主字段。
- web-access：完整联网决策、来源核对、失败次数及收尾流程；浏览器与登录改用实际宿主能力，不携带 CDP / 凭据助手。
- paper-search：完整检索/引用流程、四个原始标准库脚本、引用参考和 MIT 许可；从原 paper-download 参考确定性截取公开发现及 Zotero 身份/分类章节，保留不可用回退。
- paper-review：保留 source_check、A/B/C、模拟与真实审稿边界、三套模板；捆绑公开工程检查、指标可行性、术语选择及选刊参考和来源许可。原提图脚本只走已授权云端 PDF 的离线路径。
- journal-submission：保留选刊、合规、生命周期、平台资料及原校验器；不假定私有作者库、全局规则或门户授权。

本批不安装 agent-rules：其 Windows 发布、来源登记与周期维护依赖不能用小型映射如实替代。其余本机硬件/认证链、私有词库链不在本批；docx/pdf/pptx/xlsx/skill-creator 使用宿主能力。技能安装不等于 Zotero、机构登录、用户浏览器或其他兄弟技能已经可用。

## 确定性与保留规则

- 构建用 Python 3.10+ 标准库；显式宿主 YAML 核验另需当前宿主已有的 PyYAML。工具不联网、不调用 Git、不提交或推送。
- 每个读取的源文件必须匹配配置 SHA-256；原文更新后先审查、测试，再显式更新 pin。源提交参数是来源声明，操作者仍须通过授权连接核实准确远端提交。
- 每个替换记录唯一 ID、精确 before/after 和出现次数；章节选择同时核对边界与选中内容哈希。其余内容逐字保留。测试反向恢复原文，检查完整 Humanizer 模式目录、引用与审查核心、内部链接和许可。
- 原 SKILL 原样保存在生成包 references/cloud-source/original-skill.md，仅供来源审计，不是云端运行入口。缺失技能按名称查找；跨包稳定参考直接捆绑并记录各自原路径，不依赖宿主分配的目录 ID。
- references/cloud-build.json 分别记录源文件哈希、源提交、适配器/配置哈希、生成文件哈希 generated_sha256，以及经显式核验后的宿主文件哈希 materialized_sha256。清单自身不参与自哈希；没有时间戳，相同输入输出相同。
- 只写配置明确生成的文件，不删除已有文件。完整目标快照包含保留资产；额外文件、未知 YAML 字段、语义变化、重复 YAML 键或未解释漂移均停止。配置不存用户技能身份、账户或令牌。
- 宿主 YAML 只允许已观察的重排/引号规范化、指向实际包内资产的 icon_small/icon_large，以及明确列出的 products。每次 no-op 仍重新校验全部生成内容和 YAML 语义，不把可编辑哈希清单当作内容证明。

## 显式部署流程

先读取宿主当前 skill-creator 指南，用其支持的 personal-skills checkout；不可在普通临时目录初始化或验证安装。已有技能按 frontmatter 名称定位并保留同一身份；新技能先由宿主 init_skill.py 在支持的 checkout 内创建同名目录。

1. 从一个已核实完整提交取得所需原文件与本目录；所有技能使用同一来源提交。先在独立分支修改本目录，核对源仓库 diff 没有原技能/Windows 改动，再按授权发布。
2. 运行 `python3 -B -m unittest discover -s tools/cloud-skills -p 'test_*.py' -v`。首次使用脚本还需阅读实现，并以离线合成材料测试相关工具。
3. 读取目标完整文件集合，审查当前内容与生成差异；记录完整快照。以下变量只是占位符，不写入公开仓库：

```sh
SKILLS_ROOT="<supported-personal-skills-checkout>"
TARGET="<existing-identity-or-host-initialized-name>"
CONFIG="handoff.json"
SOURCE_REV="<verified-full-commit-sha>"
EXPECTED=$(python3 tools/cloud-skills/build.py --config "$CONFIG" \
  --skills-root "$SKILLS_ROOT" --target-dir "$TARGET" --inspect-target)
python3 tools/cloud-skills/build.py --config "$CONFIG" \
  --skills-root "$SKILLS_ROOT" --target-dir "$TARGET" \
  --source-revision "$SOURCE_REV" --expected-target-sha256 "$EXPECTED"
# 审查预览后，以完全相同的参数增加 --apply。
```

4. 同一目标内运行宿主 quick_validate.py；检查完整 diff，并做独立无外部副作用的行为试跑。只暂存当前单个技能，按宿主流程提交、推送、等待重整、fetch/read back。
5. 根据 frontmatter 名称找到重整后身份。再次审查完整集合及实际 YAML，取得新的 EXPECTED。运行相同命令加 `--record-materialized` 先预览，再加 `--apply` 保存经语义验证的宿主哈希。仅提交/推送该技能的清单；再次等待并回读。
6. 用当前已审查目标快照运行普通构建应返回 `unchanged`，并且无文件写入。每次操作都要传与当前目标相符的已审查快照；不能盲目刷新快照来覆盖不明变化。非快进按宿主规则有限次 fetch/rebase/retry；冲突停止，不 force push、不删分支。
7. 每个技能完整核验后再保存下一个。远端内容正确与当前会话/界面缓存刷新是不同结论。

## 本批验证的真实边界

源配置依据 `d7fd64fd52406ad38eada3975adb33889979e4af` 的原文件制定；后续仅本目录变化，消费时仍核实选定提交与各文件哈希。

离线实测：paper-search 30 项、submission validator 23 项、figure helpers 17 项通过；合成 PDF 的 auto/page-render/embedded 路径在阻断网络取回的条件下通过。图像提取的 BeautifulSoup HTML 分支未验证；部分历史回归依赖 Windows 项目文件，不能当作云端通过证明。原 journal 文档契约测试依赖未安装兄弟技能，部分检查不适用于此独立包。

这些检查不证明真实第三方投稿、Zotero 入库、机构登录、外发或完整领域任务已执行。门户操作、共享及持续权限仍须满足宿主和用户对具体动作的授权。
