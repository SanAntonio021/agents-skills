from pathlib import Path
ROOT=Path(r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard')
p=ROOT/'SKILL.md';s=p.read_text(encoding='utf-8')
s=s.replace('画板 token 与文档 token 不可互换。', '支持 Docx 与 Wiki 文档路由，包括同源 Docx 自动跳转到 Wiki；runner 先用 CLI fetch 解析并核对对应 Docx token、唯一目标画板和文档块，再核对实际页面 origin/path 与原生文档/画板身份。不同文档、跨源或未核实的路由写前拒绝。\n\n画板 token 与文档 token 不可互换。')
s=s.replace('旧图独立文字迁入形状、多标签编辑暂不自动处理。', '独立文字可以非空改写；其空字符串输入会触发原生删除整个文本节点，当前入口写前拒绝，不能当作保留文本框的清空。形状框内文字及单连线标签仍可清空。\n旧图独立文字迁入形状、多标签编辑暂不自动处理。')
p.write_text(s,encoding='utf-8')
p=ROOT/'references/operations.md';s=p.read_text(encoding='utf-8')
s=s.replace('请求明确指定文档和画板，不支持模糊搜索目标或自动迁移独立文本框。', '请求明确指定文档和画板，不支持模糊搜索目标或自动迁移独立文本框。`document_url` 支持同源的 `/docx/` 与 `/wiki/`；可选 `docx_token` 用于追加已知文档身份约束，不能替代 CLI fetch 核验。runner 每次打开或重开页面都读取请求和实际路由，核对两者对应同一 Docx、唯一目标画板及准确 `block_id`；结果的 `document_routes` 保留这些核验。')
s=s.replace('| text | id, text（形状自身文字或独立文本框） |', '| text | id, text（形状自身文字或独立文本框；独立文本框仅接受非空字符串，原生清空会删除节点，入口写前拒绝） |')
p.write_text(s,encoding='utf-8')
p=ROOT/'references/compatibility.md';s=p.read_text(encoding='utf-8')
old='该三接口的兼容性指纹为 `7e805832`，只接受已验证值；'
new='该三接口原兼容性指纹为 `7e805832`，当前同时接受隔离验证后的 `d309a450`；'
assert s.count(old)==1;s=s.replace(old,new)
s+='''

2026-10-13 文字接口兼容复核：在自建隔离文档的后台页仅读取 selectNodeText、processInput、blur 三函数；旧验收材料重算指纹为7e805832。selectNodeText和processInput原文完全相同，blur唯一差异是TextNodeFocusStateChange的打包模块别名w.C变为M.C，重算当前固定指纹d309a450。不做源码归一化，也不动态接受未知指纹；主命令54e7e6de及原生保存b8586b42保持匹配。

该隔离样本中，形状文字改写、清空、恢复，独立文字非空多行改写，单连线标签新增、多行改写、清空及再新增均取得真实保存回执与新页面回读；非目标模块、连线绑定、端点及其他格式继续严格保护。新标签的raw默认格式含theme_text_color_code=-1、text_color_type=0；仅新增标签接受这一int值及主题模式并记录具体例外，已有标签格式、未知字段和值仍拒绝。第一次新增因旧字段白名单在保存后验收失败，历史结果保留；此后按实际状态继续，未重放新增。一次重开CLI网络EOF通过独立只读补查确认已保存文字，不把原失败报告改为通过。

独立文字清空实测会删除整个text_shape，旧入口在调用后报UNEXPECTED_TRANSACTION_COUNT；新页及CLI确认节点已删除，其他对象未变。当前因此在Python对象预检及网页适配器中写前拒绝独立文字空字符串，未扩展删除恢复语义。该失败的原页按未知写入规则释放并保留，独立只读核验页正常关闭；不接管释放后的页面。

Docx/Wiki路由实测：新建文档返回Docx URL，网页自动进入同源Wiki。每次打开/重开前CLI fetch解析请求路由，加载后再fetch实际路由，要求同一Docx token、唯一目标whiteboard token和准确block_id；网页仍严格检查实际origin/path及原生app的Docx/画板token。跨源、未知路径、查询参数、错误文档或画板写前拒绝，不把个人文档标识写入技能源码。原生发送通道偶尔在页面加载后短暂入队，既有保护按真实未保存状态拒绝写入，不放宽队列/版本校验。
'''
p.write_text(s,encoding='utf-8')
print('Skill and compatibility documentation updated without private identifiers.')
