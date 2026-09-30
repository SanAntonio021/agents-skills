"""Boundary checks; live acceptance remains required on an isolated board."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, VerificationError, validate_target, check_scope, match_append, check_raw_preservation, reject_nested_groups
from native_nodes import compile_diagram


class Boundaries(unittest.TestCase):
    def test_undo_only_accepts_observed_unlocked_default(self):
        before = {'nodes':[dict(id='line',type='connector')]}
        restored = {'nodes':[dict(id='line',type='connector',locked=False)]}
        self.assertEqual(len(check_raw_preservation(before, restored, {'kind':'undo'})),1)
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, {'nodes':[dict(id='line',type='connector',locked=True)]}, {'kind':'undo'})
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, restored, {'kind':'move','ids':[]})
    def test_host_and_url_boundary(self):
        for url in ('https://feishu.cn.attacker.test/docx/abc', 'https://feishu.cn@attacker.test/docx/abc', 'http://tenant.feishu.cn/docx/abc', 'https://tenant.feishu.cn/docx/abc?redirect=x', 'https://tenant.feishu.cn/wiki/abc'):
            with self.assertRaises(ValueError):
                validate_target(dict(document_url=url, whiteboard_token='abc'))
        validate_target(dict(document_url='https://tenant.feishu.cn/docx/abc', whiteboard_token='Abc123'))

    def test_delete_requires_exact_cascade(self):
        nodes = [dict(id='a'), dict(id='b'), dict(id='line', start_id='a', end_id='b')]
        with self.assertRaises(VerificationError):
            check_scope(nodes, [nodes[1]], dict(kind='delete', ids=['a'], delete_ids=['a']))
        check_scope(nodes, [nodes[1]], dict(kind='delete', ids=['a'], delete_ids=['a', 'line']))

    def test_unrelated_mutation_stops(self):
        with self.assertRaises(VerificationError):
            check_scope([dict(id='a', x=0), dict(id='b', x=0)], [dict(id='a', x=1), dict(id='b', x=2)], dict(kind='move', ids=['a']))

    def test_noop_is_not_a_successful_edit(self):
        nodes = [dict(id='a', text='old', x=0, y=0)]
        with self.assertRaises(VerificationError):
            check_scope(nodes, nodes, dict(kind='text', id='a', text='new'))
        with self.assertRaises(VerificationError):
            check_scope(nodes, nodes, dict(kind='move', ids=['a'], dx=10, dy=0))

    def test_raw_style_change_stops_even_when_projection_matches(self):
        before = {'nodes':[dict(id='a', text={'text':'old'},style={'fill_color':'red'})]}
        after = {'nodes':[dict(id='a', text={'text':'new'},style={'fill_color':'blue'})]}
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, dict(kind='text',id='a'))

    def test_nested_group_is_refused_before_write(self):
        with self.assertRaises(VerificationError):
            reject_nested_groups([dict(id='a', children=['b']),dict(id='b',children=['c'])],dict(kind='move',ids=['a']))

    def test_append_to_existing_shape_keeps_old_id(self):
        old = [dict(id='old',kind='shape',x=0)]
        intended = [dict(id='local',kind='shape',x=10),dict(id='line',kind='connector',start_id='old',end_id='local')]
        after = old+[dict(id='new',kind='shape',x=10),dict(id='newLine',kind='connector',start_id='old',end_id='new')]
        self.assertEqual(match_append(old,after,intended),{'local':'new','line':'newLine'})

    def test_connect_requires_correct_new_line_and_preserves_template(self):
        before=[dict(id='template',kind='connector',start_id='a',end_id='b')]
        after=before+[dict(id='new',kind='connector',start_id='a',end_id='c')]
        op=dict(kind='connect',template_id='template',start_id='a',end_id='c')
        check_scope(before,after,op)
        with self.assertRaises(VerificationError):
            check_scope(before,before,op)
        with self.assertRaises(VerificationError):
            check_scope(before,before+[dict(id='new',kind='connector',start_id='a',end_id='b')],op)
        with self.assertRaises(VerificationError):
            check_scope(before,[dict(id='template',kind='connector',start_id='a',end_id='c'),after[1]],op)

    def test_compiler_rejects_existing_endpoint_api_limitation(self):
        with self.assertRaisesRegex(ValueError,'cannot reference existing'):
            compile_diagram(dict(existing_shapes=[dict(id='old')]))

    def test_append_ambiguity_never_guesses(self):
        template = dict(kind='shape', x=0, text='same')
        with self.assertRaises(VerificationError):
            match_append([], [dict(id='server1', **template), dict(id='server2', **template)], [dict(id='local1', **template), dict(id='local2', **template)])

    def test_save_timeout_does_not_write_again(self):
        runner = object.__new__(Runner)
        runner.timeout = 0.001
        calls = []
        runner.editor = lambda op: calls.append(op) or dict(nodes=[], seq=2, savedSeq=1)
        runner.export = lambda: self.fail('No export before browser save')
        with patch('whiteboard.time.sleep', return_value=None):
            with self.assertRaises(VerificationError):
                runner.settle([])
        self.assertTrue(calls)
        self.assertTrue(all(c == {'kind': 'inspect'} for c in calls))

    def test_compiler_owns_multiline_text(self):
        raw = compile_diagram(dict(shapes=[dict(id='a', text='one\ntwo', x=0, y=0, width=100, height=80)]))
        self.assertEqual(len(raw['nodes']), 1)
        self.assertEqual(raw['nodes'][0]['text']['text'], 'one\ntwo')
        with self.assertRaises(ValueError):
            compile_diagram(dict(shapes=[dict(id='a', x=float('nan'), y=0, width=100, height=80)]))


if __name__ == '__main__':
    unittest.main()
