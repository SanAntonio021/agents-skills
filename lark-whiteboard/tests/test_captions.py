"""Caption outcomes and exact preservation; live editor acceptance is separate."""
import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import (VerificationError, check_raw_preservation, check_scope,
                        equivalent, projection, validate_caption_operation)


def board():
    start = {'id': 'a', 'snap_to': 'right', 'position': {'x': 1, 'y': 0.5}}
    end = {'id': 'b', 'snap_to': 'left', 'position': {'x': 0, 'y': 0.5}}
    line = {
        'id': 'line', 'type': 'connector', 'x': 100, 'y': 40, 'width': 100, 'height': 0,
        'z_index': 3, 'style': {'border_color': '#000000', 'border_width': 'narrow',
                               'border_style': 'solid', 'border_opacity': 100},
        'connector': {
            'shape': 'straight', 'specified_coordinate': True, 'turning_points': [],
            'start_object': start, 'end_object': end,
            'start': {'arrow_style': 'none', 'attached_object': copy.deepcopy(start)},
            'end': {'arrow_style': 'line_arrow', 'attached_object': copy.deepcopy(end)},
            'caption_auto_direction': False, 'caption_position': 0.5, 'caption_position_type': 0,
            'captions': {'data': [{'text': 'old', 'font_size': 18, 'text_color': '#000000',
                                   'italic': False, 'font_weight': 'regular'}]}}}
    other = copy.deepcopy(line)
    other.update(id='other-line', y=140, z_index=4)
    other['connector']['captions']['data'][0]['text'] = 'keep this label'
    return {'nodes': [
        {'id': 'a', 'type': 'composite_shape', 'x': 0, 'y': 0, 'width': 100, 'height': 80,
         'z_index': 1, 'text': {'text': 'A', 'font_size': 18}, 'composite_shape': {'type': 'rect'}},
        {'id': 'b', 'type': 'composite_shape', 'x': 200, 'y': 0, 'width': 100, 'height': 80,
         'z_index': 2, 'text': {'text': 'B', 'font_size': 18}, 'composite_shape': {'type': 'rect'}},
        line, other]}


def line(raw, ident='line'):
    return next(n for n in raw['nodes'] if n['id'] == ident)


def clear(raw):
    for field in ('captions', 'caption_position', 'caption_position_type'):
        line(raw)['connector'].pop(field, None)


class CaptionChecks(unittest.TestCase):
    def verify(self, before, after, op):
        check_scope(projection(before), projection(after), op)
        self.assertEqual(check_raw_preservation(before, after, op), [])

    def test_projection_preserves_text_boundaries_and_defaults(self):
        raw = board()
        c = line(raw)['connector']
        c['captions']['data'][0]['text'] = 'first\nsecond'
        del c['caption_position']
        del c['caption_position_type']
        del c['caption_auto_direction']
        p = line({'nodes': projection(raw)})
        self.assertEqual(p['caption_texts'], ['first\nsecond'])
        self.assertEqual(p['caption'], 'first\nsecond')
        self.assertEqual(p['caption_position'], 0.5)
        self.assertEqual(p['caption_position_type'], 0)
        self.assertIs(p['caption_auto_direction'], False)
        c['captions']['data'].append({'text': 'third'})
        self.assertEqual(line({'nodes': projection(raw)})['caption_texts'], ['first\nsecond', 'third'])
        clear(raw)
        p = line({'nodes': projection(raw)})
        self.assertEqual(p['caption_texts'], [])
        self.assertEqual(p['caption'], '')
        self.assertIsNone(p['caption_position'])
        self.assertIsNone(p['caption_position_type'])

    def test_position_tolerance_is_separate_from_geometry_tolerance(self):
        self.assertTrue(equivalent({'caption_position': 0.25}, {'caption_position': 0.25000001}))
        self.assertFalse(equivalent({'caption_position': 0.5}, {'caption_position': 0.51}))
        self.assertTrue(equivalent({'x': 0.5}, {'x': 0.51}))
        for value in (True, False, math.nan, math.inf, '0.5', None):
            with self.subTest(value=value):
                self.assertFalse(equivalent({'caption_position': 0.5}, {'caption_position': value}))

    def test_rewrite_preserves_label_format_position_and_topology(self):
        before = board()
        after = copy.deepcopy(before)
        line(after)['connector']['captions']['data'][0]['text'] = 'new\nsecond line'
        self.verify(before, after, {'kind': 'caption', 'id': 'line', 'text': 'new\nsecond line'})

    def test_clear_removes_only_caption_and_position_fields(self):
        before = board()
        after = copy.deepcopy(before)
        clear(after)
        self.verify(before, after, {'kind': 'caption', 'id': 'line', 'text': ''})
        self.assertIs(line(after)['connector']['caption_auto_direction'], False)

    def test_add_after_clear_and_retain_unrelated_caption(self):
        after = board()
        before = copy.deepcopy(after)
        clear(before)
        self.verify(before, after, {'kind': 'caption', 'id': 'line', 'text': 'old'})

    def test_position_accepts_endpoints_and_small_serialization_error(self):
        before = board()
        for requested, saved in ((0, 0), (1, 1), (0.25, 0.25000001)):
            with self.subTest(position=requested):
                after = copy.deepcopy(before)
                line(after)['connector']['caption_position'] = saved
                self.verify(before, after, {'kind': 'caption_position', 'id': 'line', 'position': requested})

    def test_noop_does_not_satisfy_new_text_clear_or_small_position_move(self):
        before = board()
        for op in ({'kind': 'caption', 'id': 'line', 'text': 'new'},
                   {'kind': 'caption', 'id': 'line', 'text': ''},
                   {'kind': 'caption_position', 'id': 'line', 'position': 0.51}):
            with self.subTest(operation=op):
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(before), op)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, before, op)

    def test_already_satisfied_requests_are_idempotent(self):
        before = board()
        self.verify(before, before, {'kind': 'caption', 'id': 'line', 'text': 'old'})
        self.verify(before, before, {'kind': 'caption_position', 'id': 'line', 'position': 0.5})
        clear(before)
        self.verify(before, before, {'kind': 'caption', 'id': 'line', 'text': ''})

    def test_wrong_text_and_wrong_label_target_fail(self):
        before = board()
        op = {'kind': 'caption', 'id': 'line', 'text': 'new'}
        for target, text in (('line', 'wrong'), ('other-line', 'new')):
            with self.subTest(target=target):
                after = copy.deepcopy(before)
                line(after, target)['connector']['captions']['data'][0]['text'] = text
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(after), op)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, op)

    def test_multilabel_is_rejected_before_edit_and_in_readback(self):
        before = board()
        line(before)['connector']['captions']['data'].append({'text': 'second label'})
        for op in ({'kind': 'caption', 'id': 'line', 'text': 'new'},
                   {'kind': 'caption_position', 'id': 'line', 'position': 0.25}):
            with self.subTest(operation=op):
                with self.assertRaises(VerificationError):
                    validate_caption_operation(line({'nodes': projection(before)}), op)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, before, op)
        before = board()
        after = copy.deepcopy(before)
        line(after)['connector']['captions']['data'] = [{'text': 'new'}, {'text': 'extra'}]
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(after), {'kind': 'caption', 'id': 'line', 'text': 'new'})

    def test_position_requires_single_caption_type_zero_and_valid_ratio(self):
        node = line({'nodes': projection(board())})
        for value in (-0.1, 1.1, math.nan, math.inf, True, '0.25', None):
            with self.subTest(value=value):
                with self.assertRaises(VerificationError):
                    validate_caption_operation(node, {'kind': 'caption_position', 'id': 'line', 'position': value})
        for changes in ({'caption_texts': []}, {'caption_position_type': 1}, {'caption_position_type': False}):
            with self.subTest(changes=changes):
                with self.assertRaises(VerificationError):
                    validate_caption_operation(dict(node, **changes), {'kind': 'caption_position', 'id': 'line', 'position': 0.25})

    def test_target_and_text_are_validated_before_edit(self):
        op = {'kind': 'caption', 'id': 'line', 'text': 'new'}
        for node in (None, {'kind': 'shape'}, {'kind': 'connector', 'caption_texts': [123]}):
            with self.subTest(node=node):
                with self.assertRaises(VerificationError):
                    validate_caption_operation(node, op)
        with self.assertRaises(VerificationError):
            validate_caption_operation(line({'nodes': projection(board())}), dict(op, text=123))

    def test_rewrite_cannot_change_any_label_format_field(self):
        before = board()
        for changes in ({'font_size': 8}, {'text_color': '#ff0000'}, {'italic': True},
                        {'italic': 0}, {'font_weight': 'bold'}):
            with self.subTest(changes=changes):
                after = copy.deepcopy(before)
                line(after)['connector']['captions']['data'][0].update(text='new', **changes)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, {'kind': 'caption', 'id': 'line', 'text': 'new'})

    def test_position_cannot_change_text_format_or_position_type(self):
        before = board()
        for field, value in (('text', 'changed'), ('font_size', 10)):
            with self.subTest(field=field):
                after = copy.deepcopy(before)
                line(after)['connector']['caption_position'] = 0.25
                line(after)['connector']['captions']['data'][0][field] = value
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, {'kind': 'caption_position', 'id': 'line', 'position': 0.25})
        after = copy.deepcopy(before)
        line(after)['connector'].update(caption_position=0.25, caption_position_type=1)
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(after), {'kind': 'caption_position', 'id': 'line', 'position': 0.25})

    def test_rewrite_cannot_move_or_reorient_caption(self):
        before = board()
        for changes in ({'caption_position': 0.51}, {'caption_position': 0.50000001},
                        {'caption_position_type': 1}, {'caption_auto_direction': True}):
            with self.subTest(changes=changes):
                after = copy.deepcopy(before)
                line(after)['connector']['captions']['data'][0]['text'] = 'new'
                line(after)['connector'].update(changes)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, {'kind': 'caption', 'id': 'line', 'text': 'new'})

    def test_clear_requires_real_field_deletion(self):
        before = board()
        for retained in ('captions', 'caption_position', 'caption_position_type'):
            with self.subTest(field=retained):
                after = copy.deepcopy(before)
                clear(after)
                line(after)['connector'][retained] = {'data': []} if retained == 'captions' else before['nodes'][2]['connector'][retained]
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, {'kind': 'caption', 'id': 'line', 'text': ''})

    def test_line_binding_geometry_style_and_all_stacking_are_protected(self):
        before = board()
        mutations = [
            ('start_object', lambda n: n['connector']['start_object'].update(id='b')),
            ('attached_object', lambda n: n['connector']['start']['attached_object'].update(id='b')),
            ('anchor', lambda n: n['connector']['end_object']['position'].update(y=0.2)),
            ('arrow', lambda n: n['connector']['end'].update(arrow_style='none')),
            ('line_type', lambda n: n['connector'].update(shape='polyline')),
            ('turning_points', lambda n: n['connector'].update(turning_points=[{'x': 150, 'y': 40}])),
            ('style', lambda n: n['style'].update(border_color='#ff0000')),
            ('geometry', lambda n: n.update(x=n['x'] + 0.01)),
            ('z_index', lambda n: n.update(z_index=n['z_index'] + 0.01))]
        for name, mutate in mutations:
            for kind in ('caption', 'caption_position'):
                with self.subTest(mutation=name, operation=kind):
                    after = copy.deepcopy(before)
                    target = line(after)
                    if kind == 'caption':
                        target['connector']['captions']['data'][0]['text'] = 'new'
                        op = {'kind': kind, 'id': 'line', 'text': 'new'}
                    else:
                        target['connector']['caption_position'] = 0.25
                        op = {'kind': kind, 'id': 'line', 'position': 0.25}
                    mutate(target)
                    with self.assertRaises(VerificationError):
                        check_raw_preservation(before, after, op)
        for ident in ('a', 'other-line'):
            after = copy.deepcopy(before)
            line(after)['connector']['captions']['data'][0]['text'] = 'new'
            line(after, ident)['z_index'] += 0.01
            with self.assertRaises(VerificationError):
                check_raw_preservation(before, after, {'kind': 'caption', 'id': 'line', 'text': 'new'})

    def test_unrelated_label_and_object_cannot_change(self):
        before = board()
        for ident in ('a', 'other-line'):
            with self.subTest(id=ident):
                after = copy.deepcopy(before)
                line(after)['connector']['captions']['data'][0]['text'] = 'new'
                other = line(after, ident)
                if ident == 'a':
                    other['text']['text'] = 'changed shape'
                else:
                    other['connector']['captions']['data'][0]['text'] = 'changed other label'
                op = {'kind': 'caption', 'id': 'line', 'text': 'new'}
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(after), op)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, op)

    def test_replaced_or_duplicate_ids_are_rejected(self):
        before = board()
        for replacement in (True, False):
            with self.subTest(replacement=replacement):
                after = copy.deepcopy(before)
                line(after)['connector']['captions']['data'][0]['text'] = 'new'
                if replacement:
                    line(after)['id'] = 'replacement'
                else:
                    after['nodes'].append(copy.deepcopy(line(after)))
                op = {'kind': 'caption', 'id': 'line', 'text': 'new'}
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(after), op)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, op)


if __name__ == '__main__':
    unittest.main()
