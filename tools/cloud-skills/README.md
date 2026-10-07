# ask-first 云端单一来源试验

本试验只更新已安装的 ask-first。唯一行为源码仍为 `ask-first/SKILL.md`；兼容差异在同仓库 `ask-first.json` 中逐项列出。原文及 Windows / CC Switch 发布流程不变。没有自动同步、后台任务或新增认证。

## 构建约定

- 仅 Python 3.9+ 标准库。`build.py` 离线运行，不调用 Git、联网、提交或推送。
- 原文 SHA-256 必须与配置相同。原文更新后先审查差异、适配锚点、评测，再显式更新 pin；不自动接受新内容。
- 去掉 `disable-model-invocation: true`，生成 `agents/openai.yaml` 的 `policy.allow_implicit_invocation: false`，保留显式调用行为。
- 只替换配置列出的环境/联网入口段落，再附加宿主消息和权限边界。其余正文逐字保持；单元测试反向恢复原文验证。
- 生成 `references/cloud-build.json`：源提交、源哈希、适配器版本、代码与配置哈希、生成文件哈希。不写时间戳，输入相同则输出相同。
- 每次更新传入人工检查过的完整目标快照哈希。无解释的目标变化会停止。第二次同输入运行无变化，不重复写入。配置不存账户、技能身份、令牌或本机私有路径。
- 只管理上述三个文件。已有宿主 UI 图标等其他文件保留，但全部纳入漂移检查。生成的 UI 元数据不引用旧图标；图标文件本身不删除。

## 显式更新流程

先读取宿主当前 skill-creator 说明，使用其支持的 personal-skills Git checkout。已有技能必须沿用同一目录身份；本工具不负责新建安装，不可在普通临时目录初始化或验证安装。

1. 通过已授权 GitHub 连接或已有仓库获取准确提交的源码及本目录，确认 `ask-first/SKILL.md` 内容与该提交对应。源提交参数是来源声明，工具校验源内容哈希，不代替远端提交真实性核验。
2. 测试：`python3 -m unittest discover -s tools/cloud-skills -p 'test_*.py' -v`。
3. 从宿主支持的 checkout 中按 frontmatter 名称找到已有 ask-first，读取全部目标文件并查看差异，再记录以下私有变量。不要把变量实际值提交到本仓库。

```sh
SKILLS_ROOT="<supported-personal-skills-checkout>"
TARGET="<existing-skill-directory>"
SOURCE_REV="<verified-full-source-commit-sha>"
EXPECTED_TARGET=$(python3 tools/cloud-skills/build.py \
  --skills-root "$SKILLS_ROOT" --target-dir "$TARGET" --inspect-target)

# 默认仅预览；检查适配配置及当前目标与生成内容的差异后才 apply。
python3 tools/cloud-skills/build.py --skills-root "$SKILLS_ROOT" \
  --target-dir "$TARGET" --source-revision "$SOURCE_REV" \
  --expected-target-sha256 "$EXPECTED_TARGET"
python3 tools/cloud-skills/build.py --skills-root "$SKILLS_ROOT" \
  --target-dir "$TARGET" --source-revision "$SOURCE_REV" \
  --expected-target-sha256 "$EXPECTED_TARGET" --apply
```

4. 在同一目标目录运行宿主 `quick_validate.py`，检查 Git diff，执行独立的无副作用行为测试。重复最后一个命令应返回 `unchanged`。只暂存该技能目录，再按宿主流程提交、推送和等待重整。
5. 重整后 fetch/read back：核对同一技能身份、完整文件集合、SKILL.md 和 manifest 字节，以及 YAML 中 interface 值和 `allow_implicit_invocation: false`。宿主可能重排 YAML、去除引号并补充 products，生成文件哈希记录的是重整前输出，因此应另存私有重整后快照并解释差异，不能把不同字节声称为相同。不可盲目刷新 expected hash 来覆盖未经审查的差异。
6. 如有非快进按宿主规则有限次 fetch/rebase/retry；冲突或意外内容变化时停止。不得 force push。仅源码提交不等于已安装；远端验证和独立行为测试也不证明当前 UI 缓存已刷新。

首次试验原文 pin 来自 `992a217f29cdc8e04dc06dcb8d5c113cb8d43bdb`。源码/适配器更改由原仓库审查、提交；云端只消费确定的提交。试验分支不自动合并 main，不改变 Windows 工作流。
