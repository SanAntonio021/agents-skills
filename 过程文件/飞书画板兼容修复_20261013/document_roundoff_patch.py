from pathlib import Path
p=Path(r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard/references/compatibility.md')
s=p.read_text(encoding='utf-8')
s+='''

2026-10-14 原有水平直线在相邻模块改字时刷新非中点附着：raw高度由0变为约2.4e-6；原生端点按未变锚点计算的既有期望位置产生同量级修正，模块几何、绑定、锚点、路径及其他raw属性保持，独立新页仍保留该微量高度且两端绑定有效。保护器仅对text操作的相邻线或caption操作的目标线，接受无组、零角度、双端绑定、无拐点直线的0→小于1e-5正高度；要求完整前后原生端点与有效绑定，端点差小于1e-5，绑定期望点严格不变，写后实际点与期望点一致，raw/native高度与实际竖差相符。只解释height一个字段，其他raw字段继续严格比较；raw_exceptions结构化记录前后高度、端点、最大差与期望附着点。缺证据、改变模块/锚点/绑定、非水平线、负高度、达到阈值或额外属性变化仍拒绝。原保存后保护失败记录保留，核对只读证据，不重放已保存文字。
'''
p.write_text(s,encoding='utf-8')
