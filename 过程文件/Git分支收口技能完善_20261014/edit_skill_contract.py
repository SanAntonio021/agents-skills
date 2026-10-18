from pathlib import Path
import json
root=Path(r'D:\BaiduSyncdisk\.agents\skills\git-branch-consolidation');p=root/'SKILL.md';text=p.read_text(encoding='utf-8')
def replace(old,new):
 global text
 if old not in text:raise RuntimeError('Expected contract text missing '+old[:70])
 text=text.replace(old,new,1)
replace('- 本地与远端 branch heads 只剩默认分支，只保留根工作树，stash 和普通 git status 为空。','- 本地与选定远端 branch heads 只剩默认分支，只保留根工作树，已归并的 stash 清空。有效源码已提交；普通 status 只允许精确登记并核验的 retained-local 本地材料，不能遗留未集成源码。')
replace('- 冻结时默认分支是最终提交的祖先，各分支、stash 和未提交内容中的有效工作已纳入最终版本；仅留在恢复包不等于完成集成。','- 冻结时默认分支是最终提交的祖先；各分支、stash、主与辅助工作树的有效源码、测试、项目文档和必要依赖已纳入最终提交并推送。仅留在恢复包不等于完成集成。')
replace('用户明确要求保留某个长期分支、worktree、stash 或本地生成物时，把它写入例外清单，并相应修改完成合同。不要把“只留一个分支”解释成删除 tags。','用户明确要求保留某个长期分支、worktree、stash 或未定稿源码时，记录准确范围并修改对应完成条件；不把这一例外自动扩展到其他源码。数据、过程材料、凭据和本机配置按用途保留，使用 retained-local 记录证明其正常存续，不为清空 status 强行提交。不要把“只留一个分支”解释成删除 tags。')
replace('## 2. 明确 ignored 内容的归口','## 2. 分类源码与本地材料')
replace('git bundle 不能单独恢复 index、工作树、stash 各层状态、配置、hooks 或未跟踪文件。对每个 worktree 运行：','先读项目 README、AGENTS、目录职责和现有忽略规则，检查主工作树、辅助工作树及 stash 各层内容。有效源码、测试、项目文档、锁文件、构建配置和复现/编辑所需依赖默认进入最终提交；不能只按扩展名排除图片、压缩包或二进制依赖。实验数据、过程材料、可重建产物、凭据和本机配置默认保留，禁止因未跟踪就机械发布。\n\n使用准确文件清单暂存，不整库 git add，不为达到 clean status 批量扩大忽略规则。确有防止本机材料误提交的需要时，仅添加准确的本地 exclude 项并保存原规则；源码和旧规则含义不得被忽略项遮蔽。只有用途或内容含义无法由材料确认时才询问用户。\n\ngit bundle 不能单独恢复 index、工作树、stash 各层状态、配置、hooks 或未跟踪文件。对每个 worktree 运行：')
replace('即使没有 ignored 内容，也可以省略最后一个参数。脚本会：','即使没有 ignored 内容，也可以省略最后一个参数。嵌套独立仓库必须先单独封包和验证，再用 --nested-recovery-map 登记其准确路径与包摘要；父包嵌入已验证的子包，不替子仓库合并、推送或删除分支。同一 common Git 目录的 checkout 按 linked worktree 核对。未登记嵌套仓库仍拒绝封包，首版仅支持一层组合。\n\n脚本会：')
replace('- 保存 refs、reflog、stash、worktree、Git 元数据，以及受保护文件的模式和 SHA-256；纯可重建缓存只保存根记录与重建依据；','- 保存 refs、reflog、stash、worktree、Git 布局及元数据：.git 指针、common/admin 目录关系、core.worktree、config.worktree、info/exclude、hooks 和影响恢复的配置依赖；原始字节与隔离路径重映射分别记录；纯可重建缓存只保存根记录与重建依据；')
replace('存在指向工作树外的 junction/symlink 时默认拒绝隔离恢复；','新包使用 schema 4，固定恢复脚本与必要依赖随包保存。隔离恢复只读取封存包，在不存在的新目录重放，不依赖原仓库或当前技能安装位置；只映射恢复路径，保存 hooks 但不执行其动作。旧 schema 2/3 保持原保护语义，不用新登记追认旧包。\n\n存在指向工作树外的 junction/symlink 时默认拒绝隔离恢复；')
replace('3. **内容已覆盖**：只有路径、语义和相关测试共同证明后续版本完整覆盖时，标为仅备份。','3. **内容已覆盖**：只有路径、语义和相关测试共同证明后续版本完整覆盖时，记录 content-covered 及依据，保留当前更完整版本。')
replace('5. **无效或仅产物内容**：明确理由后留在恢复包；仍有效的改动不能因冲突就归为放弃。','5. **本地保留材料**：分类为 retained-local，绑定冻结内容摘要、最终提交和可用存续路径；根材料原位保留，辅助材料在移除工作树前建立正常存续副本，恢复包不能作为唯一存续位置。无效实验/候选材料注明依据并保留原有保存约定；仍有效的源码不能因冲突归为放弃。')
replace('4. 有效源码、stash 和未提交改动经检查后纳入最终版本；数据与产物按用途保留，不能只为工作树干净而丢弃。辅助 worktree 中的不可重建数据在移除前还须有可直接使用的存续副本，恢复包只负责兜底。','4. 从所有来源整合有效源码，用准确文件清单提交。数据、过程材料和本地配置按 retained-local 分类保留；通过 --integration-records 绑定冻结摘要、实际存续路径和最终提交并实际比较内容。不登记材料、遗漏源码、内容漂移或仅存恢复包均不能通过验收。')
replace('在干净的候选工作区先运行下文验收命令，并增加 --check-integration-only；','在源码和索引已提交的候选工作区先运行下文验收命令，并增加 --check-integration-only；')
replace('只有两份 package manifest、两份 bundle、所有受保护对象、每个 worktree 的状态/index/模式/哈希和 git fsck --full 全部通过，才进入集成。','只有两份 package manifest、两份 bundle、所有受保护对象、每个 worktree 与登记子仓库的状态/index/模式/哈希、配置布局和 git fsck --full 全部通过，才进入集成。')
replace('用户要求连 ignored 产物一起清空时增加 --require-no-ignored；','最终验收允许经 --integration-records 精确核验的 retained-local 项；已提交源码和索引仍必须完整，不放宽未知文件、未经确认的 dirty 源码或漂移。\n\n用户要求连 ignored 产物一起清空时增加 --require-no-ignored；')
p.write_text(text,encoding='utf-8',newline='\n')
e=root/'evals/evals.json';data=json.loads(e.read_text(encoding='utf-8'));ids={x['id'] for x in data['evals']}
new=[
 (17,'只说所有分支合到 main 并同步。主工作树有新增源码、分层修改的测试和 README，还有过程文件和实验数据，全部处理完，不要一个个问。','按项目用途把有效源码、测试、README 和必要依赖整合提交推送；数据和过程材料按 retained-local 保留且验证可用，不机械整库 git add 或隐去源码。',['所有有效未提交源码纳入 main 提交','本地数据有精确存续证据','无需对可由项目判断的分类重复询问']),
 (18,'主树 local-results 保留原位，辅助树 measurements 移到项目数据目录。这些材料已经在恢复包，直接写 status-clean 完成？','使用 retained-local 分类绑定冻结摘要、最终提交与正常存续路径并比较内容；允许被登记本地项仍显示 status，未登记材料、漂移或只剩恢复包失败。',['恢复包不是唯一数据副本','验收核对实际内容','源码必须提交']),
 (19,'工作区过程目录有独立 nested Git clone，已单独保存双恢复包并验证。父仓库收口时希望一起保全，但不要改子仓库分支。','用 nested-recovery-map 绑定准确相对根、包摘要和冻结状态；嵌入子包并复查漂移，组合恢复但不对子仓库提交/推送/删分支；未登记 .git 继续拒绝。',['准确登记和冻结检查','子包随父包可恢复','不自动收口子仓库']),
 (20,'这个仓库的 .git 是指针文件，Git 管理目录放在网盘外，core.worktree 与 info/exclude 有配置；原目录不可用时，恢复包必须仍能独立还原。','保存布局、配置、hooks 和必要依赖，schema4 包内恢复入口从封存配置重映射新目录；不读现仓、不执行hooks、不覆盖任何原路径，验证状态/索引/内容/EOL与元数据。',['正确识别真实根和分离Git目录','package-only恢复','保存原配置与重映射记录','旧schema保持原验证'])]
for ident,prompt,expected,expectations in new:
 if ident in ids:raise RuntimeError('Eval ID exists')
 data['evals'].append({'id':ident,'prompt':prompt,'expected_output':expected,'files':[],'expectations':expectations})
e.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Updated main contract and four representative behavior cases')
