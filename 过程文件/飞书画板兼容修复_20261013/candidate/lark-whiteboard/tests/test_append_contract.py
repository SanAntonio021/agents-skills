"""Append construction and saved-field regressions; fault injection is offline."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_nodes import compile_diagram
from whiteboard import VerificationError, check_appended_raw, validate_append_payload
import test_lifecycle as lifecycle


def payload():
    return compile_diagram(dict(shapes=[
        dict(id='a', text='start', x=200, y=0, width=100, height=80),
        dict(id='b', text='end', x=400, y=0, width=100, height=80)],
        connectors=[dict(id='c', start_id='a', end_id='b', label='signal')]))


def at(value, path):
    for key in path:
        value = value[key]
    return value


def altered(path, value):
    result = payload()
    at(result, path[:-1])[path[-1]] = value
    return result


def saved_copy(request):
    """Resolve IDs like the actual CLI while retaining every requested property."""
    mapping = {n['id']:'server-' + n['id'] for n in request['nodes']}
    result = copy.deepcopy(request)
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'id' and isinstance(child, str):
                    value[key] = mapping.get(child, child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(result)
    return result, mapping


def fresh_requests():
    """Exact 20261004 fresh-final requests, embedded without process-file dependencies.

    Evidence: fresh-final-20261004/{01-append-observer,02-append-main}/append-input.json
    and raw-004.json under the existing isolated-board acceptance directory.
    """
    observer = compile_diagram(dict(shapes=[dict(
        id='o410041:1', text='观察模块\n全程保持原样', shape='round_rect',
        x=80, y=540, width=240, height=100, font_size=20,
        border_color='#64748B', fill_color='#F1F5F9', text_color='#334155')]))
    observer['nodes'][0]['z_index'] = 0
    main = compile_diagram(dict(shapes=[
        dict(id='o410042:1', text='输入模块\n初始文本', shape='round_rect',
             x=80, y=240, width=180, height=100, font_size=20,
             border_color='#2563EB', fill_color='#DBEAFE', text_color='#1E3A8A'),
        dict(id='o410042:2', text='处理模块', shape='rect',
             x=660, y=240, width=220, height=100, font_size=20,
             border_color='#047857', fill_color='#D1FAE5', text_color='#064E3B'),
        dict(id='o410042:3', text='备用模块\n删除后立即撤销', shape='rect',
             x=660, y=540, width=220, height=100, font_size=20,
             border_color='#7C3AED', fill_color='#EDE9FE', text_color='#4C1D95')],
        connectors=[dict(id='c410042:1', start_id='o410042:1', end_id='o410042:2',
                         border_color='#2563EB', label='初始单箭头标签')]))
    for index, node in enumerate(main['nodes'], 1):
        node['z_index'] = index
    return observer, main


class AppendContract(unittest.TestCase):
    def alpha_runner(self, directory, text_shape=False, empty_text=False):
        runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
        request = json.loads(filename.read_text(encoding='utf-8'))
        def adjust(node):
            if node['id'] in ('a','server-a'):
                if text_shape:
                    node['type'] = 'text_shape'
                    del node['composite_shape'], node['style']
                if empty_text:
                    node['text']['text'] = ''
            if empty_text and node['type']=='connector':
                node['connector']['captions']['data'][0]['text'] = ''
        if text_shape or empty_text:
            if text_shape:
                # Native text shapes are independent; connector endpoints must
                # remain bound to composite shapes in the normal append path.
                request['nodes'] = [node for node in request['nodes'] if node['type']!='connector']
            for node in request['nodes']:
                adjust(node)
            filename.write_text(json.dumps(request),encoding='utf-8')
            export = runner.export
            def adjusted_export():
                raw,name = export()
                if text_shape:
                    raw['nodes'] = [node for node in raw['nodes'] if node['type']!='connector']
                for node in raw['nodes']:
                    adjust(node)
                return raw,name
            runner.export = adjusted_export
        return runner,filename

    def test_missing_each_required_alpha_component_keeps_confirmed_single_append(self):
        cases = [('server-a',False,component) for component in ('border','fill','text')]
        cases += [('server-a',True,'text'),('server-c',False,'border'),('server-c',False,'text')]
        for ident,text_shape,component in cases:
            with self.subTest(ident=ident,text_shape=text_shape,component=component), tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
                runner,filename = self.alpha_runner(directory,text_shape=text_shape)
                hydrate = runner.hydrate
                def missing_alpha(raw):
                    result = hydrate(raw)
                    if runner.opens==2:
                        del result['render_alpha'][ident][component]
                    return result
                runner.hydrate = missing_alpha
                with self.assertRaisesRegex(VerificationError,'missing or nonopaque'):
                    runner.append(filename)
                step = runner.report['steps'][0]
                self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']),
                                 ('confirmed','failed','reopen'))
                self.assertEqual(len(runner.mutations),1)
                self.assertFalse(runner.uncertain)

    def test_nonopaque_expected_or_additional_component_is_still_rejected(self):
        for component in ('border','fill','text','unexpected'):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
                runner,filename = self.alpha_runner(directory)
                hydrate = runner.hydrate
                def nonopaque(raw):
                    result = hydrate(raw)
                    if runner.opens==2:
                        result['render_alpha']['server-a'][component] = .5
                    return result
                runner.hydrate = nonopaque
                with self.assertRaisesRegex(VerificationError,'missing or nonopaque'):
                    runner.append(filename)
                self.assertEqual(runner.report['steps'][0]['save_status'],'confirmed')
                self.assertEqual(len(runner.mutations),1)

    def test_empty_shape_text_and_line_label_do_not_require_text_alpha(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner,filename = self.alpha_runner(directory,empty_text=True)
            hydrate = runner.hydrate
            def no_empty_text_alpha(raw):
                result = hydrate(raw)
                if runner.opens==2:
                    del result['render_alpha']['server-a']['text']
                    del result['render_alpha']['server-c']['text']
                return result
            runner.hydrate = no_empty_text_alpha
            runner.append(filename)
            self.assertEqual(runner.report['status'],'verified')
            self.assertEqual(runner.report['steps'][0]['verification_status'],'passed')
            self.assertEqual(len(runner.mutations),1)

    def test_independent_text_requires_only_text_alpha(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner,filename = self.alpha_runner(directory,text_shape=True)
            runner.append(filename)
            self.assertEqual(runner.report['status'],'verified')
            self.assertEqual(runner.report['steps'][0]['after_render_alpha']['server-a'],{'text':1})
            self.assertEqual(len(runner.mutations),1)

    def invalid_requests(self):
        cases = [
            ('angle_nan', ('nodes',0,'angle'), float('nan')),
            ('font_nan', ('nodes',0,'text','font_size'), float('nan')),
            ('shape_magic', ('nodes',0,'composite_shape','type'), 'magic'),
            ('width_negative', ('nodes',0,'width'), -1),
            ('width_boolean', ('nodes',0,'width'), True),
            ('layer_boolean', ('nodes',0,'z_index'), True),
            ('lock_number', ('nodes',0,'locked'), 1),
            ('font_string', ('nodes',0,'text','font_size'), '20'),
            ('font_weight_invalid', ('nodes',0,'text','font_weight'), 'normal'),
            ('text_angle_invalid', ('nodes',0,'text','angle'), 45),
            ('italic_number', ('nodes',0,'text','italic'), 1),
            ('text_color_invalid', ('nodes',0,'text','text_color'), 'blue'),
            ('style_border_invalid', ('nodes',0,'style','border_style'), 'magic'),
            ('opacity_outside_current_scope', ('nodes',0,'style','fill_opacity'), 50),
            ('line_shape_invalid', ('nodes',2,'connector','shape'), 'magic'),
            ('caption_position_invalid', ('nodes',2,'connector','caption_position'), 2),
            ('caption_placement_invalid', ('nodes',2,'connector','caption_position_type'), 3),
            ('coordinate_flag_number', ('nodes',2,'connector','specified_coordinate'), 1),
            ('arrow_invalid', ('nodes',2,'connector','end','arrow_style'), 'magic'),
            ('multiple_labels', ('nodes',2,'connector','captions','data'),
             [{'text':'first'},{'text':'second'}]),
            ('node_unknown', ('nodes',0,'opacity_typo'), 50),
            ('text_unknown', ('nodes',0,'text','font_szie'), 24),
            ('style_unknown', ('nodes',0,'style','fill_opaciy'), 100),
            ('shape_unknown', ('nodes',0,'composite_shape','radius'), 10),
            ('connector_unknown', ('nodes',2,'connector','caption_postion'), 0.5),
            ('end_unknown', ('nodes',2,'connector','end','arrow_stlye'), 'none'),
            ('anchor_unknown', ('nodes',2,'connector','start_object','snap_too'), 'right'),
            ('point_unknown', ('nodes',2,'connector','start_object','position','z'), 0),
            ('captions_unknown', ('nodes',2,'connector','captions','datum'), []),
            ('caption_unknown', ('nodes',2,'connector','captions','data',0,'font_szie'), 20),
            ('connector_text_wrong_type', ('nodes',2,'text'), 'bad'),
            ('connector_text_unknown_field', ('nodes',2,'text'), {'text':'bad','font_szie':20}),
            ('bound_start_duplicate_position', ('nodes',2,'connector','start','position'),
             {'x':300,'y':40}),
        ]
        for name, path, value in cases:
            yield name, altered(path, value)
        for value in (None, False, 0, [], ''):
            yield 'parent_id_' + repr(value), altered(('nodes',0,'parent_id'), value)
        conflict = payload()
        conflict['nodes'][2]['connector']['start_object']['snap_to'] = 'left'
        conflict['nodes'][2]['connector']['start']['attached_object']['snap_to'] = 'left'
        yield 'snap_to_position_edge_conflict', conflict
        self_connection = payload()
        connector = self_connection['nodes'][2]['connector']
        connector['end_object'] = copy.deepcopy(connector['start_object'])
        connector['end']['attached_object'] = copy.deepcopy(connector['start_object'])
        yield 'self_connection', self_connection

    def test_all_static_invalid_requests_reject_before_export_or_content(self):
        for name, request in self.invalid_requests():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
                filename.write_text(json.dumps(request), encoding='utf-8')
                with self.assertRaises(ValueError):
                    runner.append(filename)
                self.assertEqual((runner.index, runner.opens, len(runner.mutations)), (0,0,0))
                step = runner.report['steps'][0]
                self.assertEqual((step['save_status'], step['verification_status'], step['failure_phase']),
                                 ('not_written','failed','preflight'))

    def test_real_text_shape_without_style_remains_valid(self):
        # Exact native-probe/text-native-session-corrected/text-only-append.json.
        request = compile_diagram(dict(shapes=[dict(id='o94111:1',
            text='独立文字原生边界验证', x=1200,y=260,width=260,height=55,font_size=20)]))
        node = request['nodes'][0]
        node['type'] = 'text_shape'
        del node['composite_shape'], node['style']
        original = copy.deepcopy(request)
        self.assertEqual(validate_append_payload(request), original)
        saved, mapping = saved_copy(request)
        self.assertEqual(check_appended_raw(request, saved, mapping), [])

    def test_original_fresh_requests_and_observed_service_defaults_pass(self):
        for request in fresh_requests():
            with self.subTest(ids=[n['id'] for n in request['nodes']]):
                validate_append_payload(request)
                saved, mapping = saved_copy(request)
                def lowercase(value):
                    if isinstance(value, dict):
                        for key, child in value.items():
                            if key.endswith('_color') and isinstance(child, str):
                                value[key] = child.lower()
                            else:
                                lowercase(child)
                    elif isinstance(value, list):
                        for child in value:
                            lowercase(child)
                lowercase(saved)
                for node in saved['nodes']:
                    if node['type'] == 'connector':
                        connector = node['connector']
                        connector.update(caption_position=0.5, caption_position_type=0)
                        connector['captions']['data'][0].update(angle=0,font_weight='regular',
                            horizontal_align='center',vertical_align='mid',italic=False,
                            line_through=False,underline=False,text_background_color_type=0,
                            theme_text_background_color_code=-1)
                exceptions = check_appended_raw(request, saved, mapping)
                self.assertTrue(exceptions)
                expected = {'rgb_letter_case'}
                if any(n['type'] == 'connector' for n in request['nodes']):
                    expected.add('service_caption_default')
                self.assertEqual({e['normalization'] for e in exceptions}, expected)

    def test_every_explicit_requested_field_must_survive_save(self):
        request = fresh_requests()[1]
        saved, mapping = saved_copy(request)
        paths = []
        def fields(value, path):
            if isinstance(value, dict):
                for key, child in value.items():
                    paths.append((*path,key))
                    fields(child, (*path,key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    fields(child, (*path,index))
        for index, node in enumerate(request['nodes']):
            fields(node, ('nodes',index))
        for path in paths:
            with self.subTest(path=path):
                damaged = copy.deepcopy(saved)
                del at(damaged, path[:-1])[path[-1]]
                # A missing root ID cannot be indexed; either error still rejects the save.
                with self.assertRaises((VerificationError, KeyError)):
                    check_appended_raw(request, damaged, mapping)

    def test_changed_saved_angle_weight_or_italic_preserves_confirmed_single_append(self):
        for path, value in [(('angle',),45), (('text','font_weight'),'bold'),
                            (('text','italic'),True)]:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
                runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
                export = runner.export
                def damaged_export():
                    raw, name = export()
                    for node in raw['nodes']:
                        if node['id'] == 'server-a':
                            at(node,path[:-1])[path[-1]] = value
                    return raw, name
                runner.export = damaged_export
                with self.assertRaises(VerificationError):
                    runner.append(filename)
                step = runner.report['steps'][0]
                self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']),
                                 ('confirmed','failed','protection'))
                self.assertEqual(len(runner.mutations), 1)
                self.assertFalse(runner.uncertain)
                runner.close()
                self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'close')

    def test_unrequested_bold_or_italic_label_is_not_a_service_default(self):
        for key, value in [('font_weight','bold'), ('italic',True)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
                runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
                export = runner.export
                def damaged_export():
                    raw, name = export()
                    for node in raw['nodes']:
                        if node['id'] == 'server-c':
                            node['connector']['captions']['data'][0][key] = value
                    return raw, name
                runner.export = damaged_export
                with self.assertRaises(VerificationError):
                    runner.append(filename)
                step = runner.report['steps'][0]
                self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']),
                                 ('confirmed','failed','protection'))
                self.assertEqual(len(runner.mutations), 1)
                self.assertFalse(runner.uncertain)
                runner.close()

    def test_reopened_raw_detects_new_angle_weight_and_old_object_drift(self):
        for ident, path, value in [('server-a',('angle',),45),
                                   ('server-a',('text','font_weight'),'bold'),
                                   ('old',('text','text'),'background changed')]:
            with self.subTest(ident=ident,path=path), tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
                runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
                export = runner.export
                def damaged_export():
                    raw, name = export()
                    if runner.opens == 2:
                        for node in raw['nodes']:
                            if node['id'] == ident:
                                at(node,path[:-1])[path[-1]] = value
                    return raw, name
                runner.export = damaged_export
                with self.assertRaises(VerificationError):
                    runner.append(filename)
                step = runner.report['steps'][0]
                self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']),
                                 ('confirmed','failed','reopen'))
                self.assertEqual((len(runner.mutations),runner.opens,runner.polls), (1,2,3))
                self.assertFalse(runner.uncertain)
                runner.close()
                self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'close')


if __name__ == '__main__':
    unittest.main()
