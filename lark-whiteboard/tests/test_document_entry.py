"""Entry routing contract: document requests must use native whiteboard."""
from pathlib import Path
import unittest

SKILLS = Path(__file__).resolve().parents[2]
DOC = SKILLS / 'lark-doc'
BOARD = SKILLS / 'lark-whiteboard'


class DocumentEntryRouting(unittest.TestCase):
    def text(self, path):
        return path.read_text(encoding='utf-8-sig')

    def test_document_whiteboard_reference_is_a_handoff(self):
        text = self.text(DOC / 'references/lark-doc-whiteboard.md')
        for phrase in ('系统架构', '硬件信号链', '接线图', '模块拓扑'):
            self.assertIn(phrase, text)
        self.assertIn('系统架构、硬件信号链、接线图、模块拓扑固定使用可编辑原生对象', text)
        self.assertIn('文档入口不得生成 SVG', text)
        self.assertIn('block_id', text)
        self.assertIn('block_token', text)
        self.assertIn('主 Agent', text)
        self.assertNotIn('<whiteboard type="svg">', text)
        self.assertNotIn('不需要读取 `lark-whiteboard`', text)
        self.assertNotIn('复杂图再启动 SubAgent', text)

    def test_document_skill_routes_diagrams_to_native_owner(self):
        text = self.text(DOC / 'SKILL.md')
        self.assertIn('画图一律交给 `lark-whiteboard`', text)
        self.assertIn('原生对象', text)
        self.assertIn('lark-whiteboard', text)

    def test_whiteboard_owner_defines_native_first_and_manifest(self):
        text = self.text(BOARD / 'SKILL.md')
        self.assertIn('系统拓扑不自动进入任何非原生格式', text)
        self.assertIn('图内容清单', text)
        self.assertIn('CLI RAW', text)
        self.assertIn('矩形、圆角矩形、椭圆、菱形、平行四边形', text)
        self.assertIn('原生写入或局部编辑失败', text)

    def test_local_structure_edits_are_documented(self):
        text = self.text(BOARD / 'references/operations.md')
        for phrase in ('已有图的局部结构编辑', '引用已有模块', '换标签', '级联删除', 'z_index', '实际预览'):
            self.assertIn(phrase, text)
        self.assertIn('不能通过整板覆盖', text)

    def test_operations_do_not_advertise_foreign_raw_groups(self):
        text = self.text(BOARD / 'references/operations.md')
        self.assertIn('图内容清单', text)
        self.assertIn('不要伪造 `type: "group"`', text)
        self.assertIn('同一批次里引用旧形状', text)
        self.assertIn('预览', text)


if __name__ == '__main__':
    unittest.main()
