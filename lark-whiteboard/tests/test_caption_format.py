"""Caption formatting contracts; offline checks do not replace live readback."""
import copy
import math
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import (Runner, VerificationError, check_raw_preservation,
                        check_scope, equivalent, projection,
                        validate_local_operation)
from test_captions import board, clear, line


def native(raw, width=-1, mode=2):
    nodes = projection(raw)
    for node in nodes:
        if node['kind'] == 'connector':
            node['caption_width'] = width if node['caption_texts'] else None
            node['caption_size_mode'] = mode if node['caption_texts'] else None
    return nodes


class CaptionFormatChecks(unittest.TestCase):
    def test_fractional_font_cli_truncation_requires_exact_native_reopen(self):
        before = board()
        after = copy.deepcopy(before)
        line(after)['connector']['captions']['data'][0]['font_size'] = 20
        op = dict(kind='caption_format',id='line',font_size=20.5)
        page = native(after)
        line({'nodes':page})['caption_font_size'] = 20.5
        self.assertTrue(Runner.server_equivalent(projection(after),page))
        evidence = check_raw_preservation(before,after,op)
        self.assertEqual(evidence[0]['normalization'],'cli_caption_font_size_truncation')
        check_scope(native(before),page,op)
        wrong = copy.deepcopy(page)
        line({'nodes':wrong})['caption_font_size'] = 20
        with self.assertRaises(VerificationError):
            check_scope(native(before),wrong,op)
        wrong = copy.deepcopy(after)
        line(wrong)['connector']['captions']['data'][0]['font_size'] = 21
        with self.assertRaises(VerificationError):
            check_raw_preservation(before,wrong,op)

    def test_raw_font_is_available_but_width_and_mode_remain_unknown(self):
        nodes = projection(board())
        caption = line({'nodes': nodes})
        self.assertEqual(caption['caption_font_size'], 18)
        self.assertNotIn('caption_width', caption)
        self.assertNotIn('caption_size_mode', caption)
        raw = board()
        clear(raw)
        self.assertIsNone(line({'nodes': projection(raw)})['caption_font_size'])

    def test_preflight_requires_one_caption_and_supported_parameters(self):
        nodes = native(board())
        valid = ({'font_size': 4}, {'font_size': 999}, {'font_size': 28.5},
                 {'width': 10}, {'width': 200.25}, {'auto_width': True},
                 {'font_size': 28, 'width': 180}, {'font_size': 28, 'auto_width': True})
        for params in valid:
            with self.subTest(valid=params):
                validate_local_operation(nodes, {'kind': 'caption_format', 'id': 'line', **params})
        invalid = ({}, {'font_size': 3.99}, {'font_size': 1000}, {'font_size': True},
                   {'font_size': math.nan}, {'font_size': math.inf}, {'font_size': '28'},
                   {'width': 9.99}, {'width': True}, {'width': math.inf}, {'width': None},
                   {'auto_width': False}, {'auto_width': 1}, {'auto_width': None},
                   {'width': 180, 'auto_width': True}, {'font_size': 28, 'height': 100})
        for params in invalid:
            with self.subTest(invalid=params), self.assertRaises(VerificationError):
                validate_local_operation(nodes, {'kind': 'caption_format', 'id': 'line', **params})
        for target in ('missing', 'a'):
            with self.subTest(target=target), self.assertRaises(VerificationError):
                validate_local_operation(nodes, {'kind': 'caption_format', 'id': target, 'font_size': 28})
        for texts in ([], ['first', 'second']):
            changed = copy.deepcopy(nodes)
            line({'nodes': changed})['caption_texts'] = texts
            with self.subTest(texts=texts), self.assertRaises(VerificationError):
                validate_local_operation(changed, {'kind': 'caption_format', 'id': 'line', 'width': 180})

    def test_font_change_requires_exact_requested_size_and_preserves_width(self):
        before_raw = board()
        after_raw = copy.deepcopy(before_raw)
        line(after_raw)['connector']['captions']['data'][0]['font_size'] = 28
        before, after = native(before_raw, 180, 1), native(after_raw, 180, 1)
        op = {'kind': 'caption_format', 'id': 'line', 'font_size': 28}
        check_scope(before, after, op)
        self.assertEqual(check_raw_preservation(before_raw, after_raw, op), [])
        for saved in (18, 28.001, True, math.nan):
            wrong = copy.deepcopy(after)
            line({'nodes': wrong})['caption_font_size'] = saved
            with self.subTest(saved=saved), self.assertRaises(VerificationError):
                check_scope(before, wrong, op)
        for field, saved in (('caption_width', 200), ('caption_size_mode', 0)):
            wrong = copy.deepcopy(after)
            line({'nodes': wrong})[field] = saved
            with self.subTest(field=field), self.assertRaises(VerificationError):
                check_scope(before, wrong, op)
        with self.assertRaises(VerificationError):
            check_raw_preservation(before_raw, before_raw, op)

    def test_fixed_width_requires_native_width_and_auto_height_mode(self):
        raw = board()
        before, after = native(raw), native(raw)
        line({'nodes': after}).update(caption_width=180, caption_size_mode=1)
        op = {'kind': 'caption_format', 'id': 'line', 'width': 180}
        check_scope(before, after, op)
        # Raw cannot prove width. It only proves that every exported field stayed
        # unchanged; native scope and fresh-page equality must prove the width.
        self.assertEqual(check_raw_preservation(raw, raw, op), [])
        self.assertTrue(Runner.server_equivalent(projection(raw), after))
        with self.assertRaises(VerificationError):
            check_scope(before, before, op)
        for width, mode in ((180.01, 1), (180, 0), (180, True)):
            wrong = copy.deepcopy(after)
            line({'nodes': wrong}).update(caption_width=width, caption_size_mode=mode)
            with self.subTest(width=width, mode=mode), self.assertRaises(VerificationError):
                check_scope(before, wrong, op)

    def test_auto_width_sets_minus_one_and_auto_width_mode(self):
        raw = board()
        before, after = native(raw, 180, 1), native(raw, 180, 1)
        line({'nodes': after}).update(caption_width=-1, caption_size_mode=0)
        op = {'kind': 'caption_format', 'id': 'line', 'auto_width': True}
        check_scope(before, after, op)
        check_raw_preservation(raw, raw, op)
        check_scope(after, after, op)
        wrong = copy.deepcopy(after)
        line({'nodes': wrong})['caption_size_mode'] = 2
        with self.assertRaises(VerificationError):
            check_scope(before, wrong, op)

    def test_font_and_width_can_change_together(self):
        before_raw = board()
        after_raw = copy.deepcopy(before_raw)
        line(after_raw)['connector']['captions']['data'][0]['font_size'] = 28
        before, after = native(before_raw), native(after_raw)
        line({'nodes': after}).update(caption_width=200, caption_size_mode=1)
        op = {'kind': 'caption_format', 'id': 'line', 'font_size': 28, 'width': 200}
        check_scope(before, after, op)
        check_raw_preservation(before_raw, after_raw, op)
        check_scope(after, after, op)

    def test_format_cannot_change_text_position_geometry_endpoints_or_unknown_raw(self):
        before = board()
        mutations = (
            lambda n: n.update(x=n['x'] + 0.01),
            lambda n: n.update(z_index=n['z_index'] + 0.01),
            lambda n: n['style'].update(border_color='#ff0000'),
            lambda n: n['connector'].update(caption_position=0.25),
            lambda n: n['connector'].update(caption_position_type=1),
            lambda n: n['connector'].update(caption_auto_direction=True),
            lambda n: n['connector']['start_object'].update(id='b'),
            lambda n: n['connector']['start']['attached_object']['position'].update(y=0.1),
            lambda n: n['connector']['captions']['data'][0].update(text='wrong'),
            lambda n: n['connector']['captions']['data'][0].update(italic=True),
            lambda n: n['connector']['captions']['data'][0].update(unverified_format=True))
        op = {'kind': 'caption_format', 'id': 'line', 'font_size': 28}
        for index, damage in enumerate(mutations):
            after = copy.deepcopy(before)
            line(after)['connector']['captions']['data'][0]['font_size'] = 28
            damage(line(after))
            with self.subTest(damage=index), self.assertRaises(VerificationError):
                check_raw_preservation(before, after, op)
        for target in ('a', 'other-line'):
            after = copy.deepcopy(before)
            line(after)['connector']['captions']['data'][0]['font_size'] = 28
            line(after, target)['locked'] = True
            with self.subTest(target=target), self.assertRaises(VerificationError):
                check_raw_preservation(before, after, op)

    def test_rewrite_position_and_whole_line_move_preserve_native_format(self):
        raw = board()
        before = native(raw, 180, 1)
        operations = (
            ({'kind': 'caption', 'id': 'line', 'text': 'new'},
             {'caption': 'new', 'caption_texts': ['new']}),
            ({'kind': 'caption_position', 'id': 'line', 'position': 0.25},
             {'caption_position': 0.25}),
            ({'kind': 'move', 'ids': ['line'], 'dx': 10, 'dy': 20},
             {'x': 110, 'y': 60}))
        for op, changes in operations:
            after = copy.deepcopy(before)
            line({'nodes': after}).update(changes)
            check_scope(before, after, op)
            for field, saved in (('caption_font_size', 20), ('caption_width', 200), ('caption_size_mode', 0)):
                wrong = copy.deepcopy(after)
                line({'nodes': wrong})[field] = saved
                with self.subTest(operation=op['kind'], field=field), self.assertRaises(VerificationError):
                    check_scope(before, wrong, op)

    def test_template_copy_requires_all_native_format_fields(self):
        before = native(board(), 180, 1)
        after = copy.deepcopy(before)
        added = copy.deepcopy(line({'nodes': before}))
        added['id'] = 'new-line'
        after.append(added)
        op = {'kind': 'connect', 'template_id': 'line', 'start_id': 'a', 'end_id': 'b'}
        check_scope(before, after, op)
        for field, value in (('caption_font_size', 20), ('caption_font_size', 18.01),
                             ('caption_width', -1), ('caption_width', 180.01), ('caption_size_mode', 0)):
            wrong = copy.deepcopy(after)
            line({'nodes': wrong}, 'new-line')[field] = value
            with self.subTest(field=field), self.assertRaises(VerificationError):
                check_scope(before, wrong, op)

    def test_clear_then_readd_can_restore_native_defaults_but_not_unknown_fields(self):
        before_raw = board()
        cleared_raw = copy.deepcopy(before_raw)
        clear(cleared_raw)
        before = native(before_raw, 180, 1)
        cleared = native(cleared_raw, 180, 1)
        clear_op = {'kind': 'caption', 'id': 'line', 'text': ''}
        check_scope(before, cleared, clear_op)
        check_raw_preservation(before_raw, cleared_raw, clear_op)
        readded_raw = copy.deepcopy(before_raw)
        line(readded_raw)['connector']['captions']['data'][0].update(text='restored', font_size=14)
        readded = native(readded_raw, 180, 1)
        line({'nodes': readded}).update(caption_width=-1, caption_size_mode=0)
        add_op = {'kind': 'caption', 'id': 'line', 'text': 'restored'}
        check_scope(cleared, readded, add_op)
        check_raw_preservation(cleared_raw, readded_raw, add_op)
        for field, value in (('caption_width', 180), ('caption_size_mode', 2)):
            wrong = copy.deepcopy(readded)
            line({'nodes': wrong})[field] = value
            with self.subTest(field=field), self.assertRaises(VerificationError):
                check_scope(cleared, wrong, add_op)
        wrong_raw = copy.deepcopy(readded_raw)
        line(wrong_raw)['connector']['captions']['data'][0]['unverified_format'] = True
        with self.assertRaisesRegex(VerificationError, 'unverified default format'):
            check_raw_preservation(cleared_raw, wrong_raw, add_op)

    def test_native_format_changes_on_unrelated_label_are_rejected(self):
        before = native(board(), 180, 1)
        after = copy.deepcopy(before)
        line({'nodes': after})['caption_font_size'] = 28
        op = {'kind': 'caption_format', 'id': 'line', 'font_size': 28}
        for field, value in (('caption_font_size', 20), ('caption_width', 200), ('caption_size_mode', 0)):
            wrong = copy.deepcopy(after)
            line({'nodes': wrong}, 'other-line')[field] = value
            with self.subTest(field=field), self.assertRaises(VerificationError):
                check_scope(before, wrong, op)

    def test_raw_equivalence_does_not_ignore_font_or_explicit_native_format(self):
        raw_nodes = projection(board())
        expected = native(board(), 180, 1)
        self.assertTrue(Runner.server_equivalent(raw_nodes, expected))
        line({'nodes': expected})['caption_font_size'] += 1.01
        self.assertFalse(Runner.server_equivalent(raw_nodes, expected))
        explicit = native(board(), 180, 1)
        expected = copy.deepcopy(explicit)
        line({'nodes': expected})['caption_width'] = 200
        self.assertFalse(Runner.server_equivalent(explicit, expected))
        self.assertFalse(equivalent({'caption_size_mode': 1}, {'caption_size_mode': True}))
        legacy = [{'id': 'line', 'kind': 'connector', 'x': 0, 'y': 0}]
        check_scope(legacy, legacy, {'kind': 'move', 'ids': ['line'], 'dx': 0, 'dy': 0})

    def test_fresh_page_rejects_width_or_mode_drift(self):
        raw = board()
        expected = native(raw, 180, 1)
        for field, value in (('caption_width', 200), ('caption_size_mode', 0)):
            runner = Runner.__new__(Runner)
            runner.token = runner.task = runner.tab = 'owned'
            state = {'nodes': copy.deepcopy(expected)}
            line(state)[field] = value
            runner.call = lambda path, data: None
            runner.open_page = lambda: None
            runner.hydrate = lambda saved: state
            runner.write = lambda name, value: None
            runner.editor = lambda op: self.fail('Failed native readback must not enter the editor')
            with self.subTest(field=field), self.assertRaisesRegex(VerificationError, 'Fresh-page'):
                runner.reopen_verified(raw, expected)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for native snapshot inspection')
    def test_adapter_inspection_reads_saved_native_format_without_mutation(self):
        source = Path(__file__).resolve().parents[1] / 'scripts' / 'editor.js'
        script = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let writes=0;const n={id:'line',type:15,lineProps:{points:[{x:0,y:0},{x:100,y:0}]},toGlobalPoint:p=>p};
const page={info:{baseV2:{x:0,y:0,width:100,height:0},connectorV2:{shape:0,
captions:{data:[{t:0.5,positionType:0,autoDirection:false,textBoxWidth:180,textStyle:{text:'label',fontSize:28,sizeMode:1}}]}}}};
const app={docState:{whiteboardToken:'BoardTest',docxToken:'DocTest',seq:0,savedSeq:0},
nodeManager:{nodeMap:new Map([['line',n]])},api:{graphicNodeToPageNode:()=>page},
commandManager:{handlers:new Map(),execute:()=>writes++},actionManager:{execAction:()=>writes++}};
const e={__reactFiberTest:{memoizedProps:{app}}};
const adapter=vm.runInNewContext('('+fs.readFileSync(process.argv[1],'utf8')+')',
{URL,Map,Set,location:{origin:'https://test.feishu.cn',pathname:'/docx/DocTest'},document:{querySelectorAll:()=>[e]}});
const r=adapter({document_url:'https://test.feishu.cn/docx/DocTest',whiteboard_token:'BoardTest',operation:{kind:'inspect'}});
assert.equal(r.nodes[0].caption_font_size,28);assert.equal(r.nodes[0].caption_width,180);
assert.equal(r.nodes[0].caption_size_mode,1);assert.equal(writes,0);
page.info.connectorV2.captions.data=[];
const empty=adapter({document_url:'https://test.feishu.cn/docx/DocTest',whiteboard_token:'BoardTest',operation:{kind:'inspect'}});
assert.equal(empty.nodes[0].caption_font_size,null);assert.equal(empty.nodes[0].caption_width,null);
assert.equal(empty.nodes[0].caption_size_mode,null);assert.equal(writes,0);
"""
        result = subprocess.run([shutil.which('node'), '-e', script, str(source)],
                                capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
