"""Operation results and preservation for existing native objects."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, VerificationError, check_scope, check_raw_preservation, projection, validate_local_operation, match_append
from test_captions import board, line


class LocalEdits(unittest.TestCase):
    def verify(self, before, after, op):
        check_scope(projection(before), projection(after), op)
        self.assertEqual(check_raw_preservation(before, after, op), [])

    def test_text_shape_has_its_own_kind_and_retains_text_style(self):
        raw = board()
        node = raw['nodes'][0]
        node['type'] = 'text_shape'
        del node['composite_shape']
        node['text']['text_color'] = '#AaBBcc'
        projected = line({'nodes': projection(raw)}, 'a')
        self.assertEqual(projected['kind'], 'text')
        self.assertEqual(projected['style']['text_color'], '#aabbcc')
        self.assertEqual(projected['text'], 'A')

    def test_append_can_resolve_a_new_text_shape_id(self):
        existing = [{'id': 'old', 'kind': 'shape', 'x': 0}]
        added = {'kind': 'text', 'x': 100, 'y': 100, 'text': 'independent text'}
        self.assertEqual(match_append(existing, [*existing, {'id': 'server-text', **added}],
                                      [{'id': 'local-text', **added}]), {'local-text': 'server-text'})

    def test_append_free_connector_keeps_empty_endpoint_ids_and_matches_strictly(self):
        added = {'kind': 'connector', 'start_id': '', 'end_id': '', 'x': 260, 'y': 145,
                 'width': 240, 'height': 0, 'style': {'border_color': '#334155'}, 'points': []}
        current = [{'id': 'server-line', **added}]
        intended = [{'id': 'local-line', **added}]
        self.assertEqual(match_append([], current, intended), {'local-line': 'server-line'})
        current[0]['style'] = {'border_color': '#ff0000'}
        with self.assertRaises(VerificationError):
            match_append([], current, intended)

    def test_text_shape_text_font_and_resize_outcomes(self):
        before = board()
        before['nodes'][0]['type'] = 'text_shape'
        del before['nodes'][0]['composite_shape']
        for op, updates in (
            ({'kind': 'text', 'id': 'a', 'text': 'new\nline'}, {'text': 'new\nline'}),
            ({'kind': 'font', 'id': 'a', 'font_size': 24}, {'font_size': 24}),
            ({'kind': 'resize', 'id': 'a', 'width': 120, 'height': 90}, {})):
            with self.subTest(operation=op):
                after = copy.deepcopy(before)
                if updates:
                    after['nodes'][0]['text'].update(updates)
                else:
                    after['nodes'][0].update(width=120, height=90)
                self.verify(before, after, op)
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(before), op)

    def test_text_resize_cannot_shift_position_or_change_font(self):
        before = board()
        before['nodes'][0]['type'] = 'text_shape'
        del before['nodes'][0]['composite_shape']
        op = {'kind': 'resize', 'id': 'a', 'width': 120, 'height': 90}
        for damaged in ('position', 'font'):
            with self.subTest(damage=damaged):
                after = copy.deepcopy(before)
                after['nodes'][0].update(width=120, height=90)
                if damaged == 'position':
                    after['nodes'][0]['x'] += 10
                else:
                    after['nodes'][0]['text']['font_size'] = 24
                with self.assertRaises(VerificationError):
                    self.verify(before, after, op)

    def test_only_standalone_text_edits_allow_native_auto_height(self):
        before = board()
        node = before['nodes'][0]
        node['type'] = 'text_shape'
        del node['composite_shape']
        for op, text_update in (({'kind': 'text', 'id': 'a', 'text': 'new\nsecond line'}, {'text': 'new\nsecond line'}),
                                ({'kind': 'font', 'id': 'a', 'font_size': 24}, {'font_size': 24})):
            with self.subTest(operation=op):
                after = copy.deepcopy(before)
                after['nodes'][0]['text'].update(text_update)
                after['nodes'][0]['height'] = 57.91999816894531
                self.verify(before, after, op)
                for field in ('x', 'y', 'width'):
                    with self.subTest(unowned_field=field):
                        damaged = copy.deepcopy(after)
                        damaged['nodes'][0][field] += 0.01
                        with self.assertRaises(VerificationError):
                            check_scope(projection(before), projection(damaged), op)
                        with self.assertRaises(VerificationError):
                            check_raw_preservation(before, damaged, op)
                shape_before, shape_after = copy.deepcopy(before), copy.deepcopy(after)
                for raw in (shape_before, shape_after):
                    raw['nodes'][0].update(type='composite_shape', composite_shape={'type': 'round_rect'})
                with self.assertRaises(VerificationError):
                    check_scope(projection(shape_before), projection(shape_after), op)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(shape_before, shape_after, op)
                invalid = copy.deepcopy(after)
                invalid['nodes'][0]['height'] = -1
                with self.assertRaises(VerificationError):
                    self.verify(before, invalid, op)
                noop = copy.deepcopy(after)
                noop['nodes'][0]['text'] = copy.deepcopy(before['nodes'][0]['text'])
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(noop), op)

    def test_small_requested_font_or_size_change_cannot_pass_as_a_noop(self):
        nodes = projection(board())
        for op in ({'kind': 'font', 'id': 'a', 'font_size': 18.01},
                   {'kind': 'resize', 'id': 'a', 'width': 100.01, 'height': 80}):
            with self.subTest(operation=op):
                with self.assertRaises(VerificationError):
                    check_scope(nodes, nodes, op)

    def test_text_font_and_resize_preserve_small_unrequested_numeric_properties(self):
        before = board()
        before['nodes'][0]['text']['line_height'] = 1.2
        cases = [({'kind': 'text', 'id': 'a', 'text': 'changed'}, 'font_size'),
                 ({'kind': 'font', 'id': 'a', 'font_size': 24}, 'line_height'),
                 ({'kind': 'resize', 'id': 'a', 'width': 120, 'height': 90}, 'line_height')]
        for op, field in cases:
            with self.subTest(operation=op):
                after = copy.deepcopy(before)
                target = after['nodes'][0]
                if op['kind'] == 'text':
                    target['text']['text'] = op['text']
                elif op['kind'] == 'font':
                    target['text']['font_size'] = op['font_size']
                else:
                    target.update(width=120, height=90)
                target['text'][field] += 0.01
                with self.assertRaises(VerificationError):
                    self.verify(before, after, op)
        after = copy.deepcopy(before)
        after['nodes'][0].update(width=120, height=90, x=0.01)
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(after), {'kind': 'resize', 'id': 'a', 'width': 120, 'height': 90})

    def test_style_changes_only_explicit_color_line_and_width_fields(self):
        before = board()
        line(before)['connector']['captions']['data'].append({'text': 'hidden', 'text_color': '#123456'})
        for style in ({'border_color': '#Ff8800'}, {'border_style': 'dash'}, {'border_width': 'bold'},
                      {'text_color': '#123456'}, {'border_color': '#ff8800', 'text_color': '#123456'}):
            with self.subTest(style=style):
                after = copy.deepcopy(before)
                for key, value in style.items():
                    if key == 'text_color':
                        line(after)['connector']['captions']['data'][0][key] = value.lower()
                        line(after)['connector']['captions']['data'][0]['text_color_type'] = 1
                    else:
                        line(after)['style'][key] = value.lower() if key.endswith('_color') else value
                        if key.endswith('_color'):
                            line(after)['style'][key + '_type'] = 1
                self.verify(before, after, {'kind': 'style', 'id': 'line', 'style': style})
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(before), {'kind': 'style', 'id': 'line', 'style': style})

    def test_shape_fill_and_text_color_preserve_all_other_text_fields(self):
        before = board()
        before['nodes'][0]['text'].update(text_color='#000000', italic=True)
        after = copy.deepcopy(before)
        after['nodes'][0]['style'] = {'fill_color': '#fff0cc', 'fill_color_type': 1}
        after['nodes'][0]['text'].update(text_color='#ff8800', text_color_type=1)
        op = {'kind': 'style', 'id': 'a', 'style': {'fill_color': '#fff0cc', 'text_color': '#ff8800'}}
        self.verify(before, after, op)
        after['nodes'][0]['text']['italic'] = False
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_explicit_text_color_allows_only_builtin_theme_reference_deletion(self):
        before = board()
        caption = line(before)['connector']['captions']['data'][0]
        caption.update(text_color='#1f2329', text_color_type=0, theme_text_color_code=-1)
        after = copy.deepcopy(before)
        changed = line(after)['connector']['captions']['data'][0]
        changed.update(text_color='#7c3aed', text_color_type=1)
        del changed['theme_text_color_code']
        op = {'kind': 'style', 'id': 'line', 'style': {'text_color': '#7c3aed'}}
        self.verify(before, after, op)
        changed['theme_text_color_code'] = 7
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)
        del changed['theme_text_color_code']
        caption['text_color_type'] = 1
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_text_color_cannot_remove_other_label_theme_or_unspecified_theme(self):
        before = board()
        labels = line(before)['connector']['captions']['data']
        labels[0].update(text_color='#1f2329', text_color_type=0, theme_text_color_code=-1)
        labels.append({'text': 'hidden', 'text_color_type': 0, 'theme_text_color_code': -1})
        after = copy.deepcopy(before)
        changed = line(after)['connector']['captions']['data']
        changed[0].update(text_color='#7c3aed', text_color_type=1)
        del changed[0]['theme_text_color_code']
        del changed[1]['theme_text_color_code']
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, {'kind': 'style', 'id': 'line', 'style': {'text_color': '#7c3aed'}})
        after = copy.deepcopy(before)
        line(after)['style']['border_width'] = 'bold'
        del line(after)['connector']['captions']['data'][0]['theme_text_color_code']
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, {'kind': 'style', 'id': 'line', 'style': {'border_width': 'bold'}})

    def test_invalid_style_fields_values_or_empty_change_are_rejected(self):
        before = projection(board())
        for style in ({}, {'opacity': 0}, {'border_color': 'red'}, {'border_style': 'dashed'},
                      {'border_width': 'wide'}, {'text_color': '#123'}):
            with self.subTest(style=style):
                with self.assertRaises(VerificationError):
                    check_scope(before, before, {'kind': 'style', 'id': 'line', 'style': style})

    def test_style_cannot_change_geometry_opacity_or_later_label(self):
        before = board()
        line(before)['connector']['captions']['data'].append({'text': 'hidden', 'font_size': 18})
        for damage in ('geometry', 'opacity', 'caption'):
            with self.subTest(damage=damage):
                after = copy.deepcopy(before)
                line(after)['style']['border_color'] = '#ff8800'
                if damage == 'geometry':
                    line(after)['x'] += 0.01
                elif damage == 'opacity':
                    line(after)['style']['border_opacity'] = 50
                else:
                    line(after)['connector']['captions']['data'][1]['text'] = 'damaged'
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, {'kind': 'style', 'id': 'line', 'style': {'border_color': '#ff8800'}})

    def test_reconnect_either_or_both_ends_preserves_the_other_side(self):
        before = board()
        for op in ({'kind': 'reconnect', 'id': 'line', 'start_id': 'b'},
                   {'kind': 'reconnect', 'id': 'line', 'end_id': 'a'},
                   {'kind': 'reconnect', 'id': 'line', 'start_id': 'b', 'end_id': 'a'}):
            with self.subTest(operation=op):
                after = copy.deepcopy(before)
                c = line(after)['connector']
                for side in ('start', 'end'):
                    if side + '_id' in op:
                        c[side + '_object']['id'] = op[side + '_id']
                        c[side]['attached_object']['id'] = op[side + '_id']
                self.verify(before, after, op)
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(before), op)

    def test_reconnect_cannot_change_anchor_or_unrequested_end(self):
        before = board()
        after = copy.deepcopy(before)
        c = line(after)['connector']
        c['start_object']['id'] = c['start']['attached_object']['id'] = 'b'
        op = {'kind': 'reconnect', 'id': 'line', 'start_id': 'b'}
        c['end_object']['id'] = c['end']['attached_object']['id'] = 'a'
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(after), op)
        c['end_object']['id'] = c['end']['attached_object']['id'] = 'b'
        c['start_object']['position']['y'] = 0.3
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_binding_a_free_endpoint_adds_only_its_default_attachment(self):
        for side in ('start', 'end'):
            with self.subTest(side=side):
                before = board()
                c = line(before)['connector']
                del c[side + '_object']
                del c[side]['attached_object']
                c[side]['position'] = {'x': 100 if side == 'start' else 200, 'y': 40}
                after = copy.deepcopy(before)
                target = 'a' if side == 'start' else 'b'
                anchor = {'id': target, 'snap_to': 'right' if side == 'start' else 'left',
                          'position': {'x': 1 if side == 'start' else 0, 'y': 0.5}}
                c = line(after)['connector']
                del c[side]['position']
                c[side + '_object'] = anchor
                c[side]['attached_object'] = copy.deepcopy(anchor)
                op = {'kind': 'reconnect', 'id': 'line', side + '_id': target}
                self.verify(before, after, op)
                c[side + '_object']['position']['y'] = 0.3
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(after), op)

    def test_four_line_types_preserve_bindings_text_and_style(self):
        before = board()
        line(before)['connector']['shape'] = 'polyline'
        for shape in ('straight', 'polyline', 'curve', 'right_angled_polyline'):
            with self.subTest(shape=shape):
                after = copy.deepcopy(before)
                line(after)['connector']['shape'] = shape
                self.verify(before, after, {'kind': 'line_type', 'id': 'line', 'shape': shape})
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(before), {'kind': 'line_type', 'id': 'line', 'shape': 'curve'})

    def test_line_type_cannot_modify_text_or_style(self):
        before = board()
        for damage in ('text', 'style'):
            with self.subTest(damage=damage):
                after = copy.deepcopy(before)
                line(after)['connector']['shape'] = 'curve'
                if damage == 'text':
                    line(after)['connector']['captions']['data'][0]['text'] = 'damaged'
                else:
                    line(after)['style']['border_width'] = 'bold'
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, {'kind': 'line_type', 'id': 'line', 'shape': 'curve'})

    def test_connect_without_template_adds_one_line_and_preserves_existing_nodes(self):
        before = board()
        after = copy.deepcopy(before)
        added = copy.deepcopy(line(after))
        added.update(id='new-line', z_index=5)
        after['nodes'].append(added)
        op = {'kind': 'connect', 'start_id': 'a', 'end_id': 'b'}
        self.verify(before, after, op)
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(before), op)
        line(after, 'a')['text']['text'] = 'damaged'
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_connect_template_must_retain_style_and_caption_in_new_line(self):
        before = board()
        after = copy.deepcopy(before)
        added = copy.deepcopy(line(after))
        added.update(id='new-line', z_index=5)
        after['nodes'].append(added)
        op = {'kind': 'connect', 'template_id': 'line', 'start_id': 'a', 'end_id': 'b'}
        self.verify(before, after, op)
        added['style']['border_color'] = '#ff0000'
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(after), op)

    def test_connect_and_reconnect_cannot_reroute_an_unrelated_existing_line(self):
        before = board()
        line(before, 'other-line')['connector']['shape'] = 'polyline'
        line(before, 'other-line')['connector']['turning_points'] = [{'x': 20, 'y': 30}]
        for kind in ('connect', 'reconnect'):
            with self.subTest(operation=kind):
                after = copy.deepcopy(before)
                if kind == 'connect':
                    added = copy.deepcopy(line(after))
                    added['id'] = 'new-line'
                    after['nodes'].append(added)
                    op = {'kind': kind, 'start_id': 'a', 'end_id': 'b'}
                else:
                    op = {'kind': kind, 'id': 'line', 'start_id': 'b'}
                    for endpoint in ('start_object',):
                        line(after)['connector'][endpoint]['id'] = 'b'
                    line(after)['connector']['start']['attached_object']['id'] = 'b'
                line(after, 'other-line')['connector']['turning_points'][0]['y'] += 10
                with self.assertRaises(VerificationError):
                    check_scope(projection(before), projection(after), op)
                with self.assertRaises(VerificationError):
                    check_raw_preservation(before, after, op)

    def test_local_preflight_rejects_invalid_targets_and_parameters(self):
        nodes = projection(board())
        cases = [
            {'kind': 'text', 'id': 'line', 'text': 'wrong object'},
            {'kind': 'font', 'id': 'a', 'font_size': True},
            {'kind': 'resize', 'id': 'a', 'width': -1, 'height': 90},
            {'kind': 'style', 'id': 'line', 'style': {'fill_color': '#ffffff'}},
            {'kind': 'line_type', 'id': 'line', 'shape': 'unknown'},
            {'kind': 'path', 'id': 'line', 'points': [{'x': 100, 'y': 50}]},
            {'kind': 'reconnect', 'id': 'line'},
            {'kind': 'reconnect', 'id': 'line', 'start_id': 'missing'},
            {'kind': 'connect', 'start_id': 'a', 'end_id': 'a'},
            {'kind': 'connect', 'start_id': 'a', 'end_id': 'b', 'template_id': 'a'}]
        for op in cases:
            with self.subTest(operation=op):
                with self.assertRaises(VerificationError):
                    validate_local_operation(nodes, op)
        text_nodes = copy.deepcopy(nodes)
        line({'nodes': text_nodes}, 'a')['kind'] = 'text'
        for op in ({'kind': 'reconnect', 'id': 'line', 'start_id': 'a'},
                   {'kind': 'connect', 'start_id': 'a', 'end_id': 'b'}):
            with self.subTest(text_endpoint=op):
                with self.assertRaises(VerificationError):
                    validate_local_operation(text_nodes, op)

    def test_path_preflight_requires_two_curve_controls_and_finite_points(self):
        raw = board()
        line(raw)['connector']['shape'] = 'curve'
        nodes = projection(raw)
        validate_local_operation(nodes, {'kind': 'path', 'id': 'line',
                                         'points': [{'x': 120, 'y': 30}, {'x': 180, 'y': 50}]})
        for points in ([], [{'x': 120, 'y': 30}], [{'x': True, 'y': 30}, {'x': 180, 'y': 50}],
                       [{'x': 120, 'y': float('nan')}, {'x': 180, 'y': 50}]):
            with self.subTest(points=points):
                with self.assertRaises(VerificationError):
                    validate_local_operation(nodes, {'kind': 'path', 'id': 'line', 'points': points})

    def test_curve_path_preflight_rejects_either_unbound_endpoint(self):
        raw = board()
        line(raw)['connector']['shape'] = 'curve'
        nodes = projection(raw)
        op = {'kind': 'path', 'id': 'line', 'points': [{'x': 120, 'y': 30}, {'x': 180, 'y': 50}]}
        validate_local_operation(nodes, op)
        for side in ('start', 'end'):
            with self.subTest(unbound_side=side):
                unbound = copy.deepcopy(nodes)
                line({'nodes': unbound})[side + '_id'] = ''
                with self.assertRaisesRegex(VerificationError, 'both endpoints'):
                    validate_local_operation(unbound, op)

    def test_curve_point_add_then_move_preserves_native_topology(self):
        raw = board()
        line(raw)['connector']['shape'] = 'curve'
        before = projection(raw)
        line({'nodes': before})['points'] = [{'x': 120, 'y': 40}, {'x': 180, 'y': 40}]
        op = {'kind': 'curve_point', 'id': 'line', 'point': {'x': 150, 'y': 10}}
        after = copy.deepcopy(before)
        line({'nodes': after})['points'] = [
            {'x': 100, 'y': 40}, {'x': 120, 'y': 10}, {'x': 150, 'y': 10},
            {'x': 180, 'y': 10}, {'x': 200, 'y': 40}]
        check_scope(before, after, op)
        moved = copy.deepcopy(after)
        next_op = {'kind': 'curve_point', 'id': 'line', 'point': {'x': 160, 'y': 20}}
        line({'nodes': moved})['points'][2] = next_op['point']
        check_scope(after, moved, next_op)
        for damaged in (after, before):
            with self.assertRaises(VerificationError):
                check_scope(after, damaged, next_op)
        extra = copy.deepcopy(moved)
        line({'nodes': extra})['points'].extend([{'x': 170, 'y': 30}]*3)
        with self.assertRaises(VerificationError):
            check_scope(after, extra, next_op)

    def test_curve_point_preflight_rejects_invalid_handles_and_grouped_curves(self):
        nodes = projection(board())
        op = {'kind': 'curve_point', 'id': 'line', 'point': {'x': 150, 'y': 10}}
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, op)
        target = line({'nodes': nodes})
        target.update(shape='curve', points=[{'x': 120, 'y': 40}, {'x': 180, 'y': 40}])
        validate_local_operation(nodes, op)
        for updates in ({'mode': 'turning'}, {'mode': 'other'}, {'index': 1}, {'index': True},
                        {'index': -1}, {'index': 0.5}, {'point': {'x': float('nan'), 'y': 10}},
                        {'point': {'x': 150, 'y': 10, 'z': 0}}):
            with self.subTest(parameters=updates), self.assertRaises(VerificationError):
                validate_local_operation(nodes, {**op, **updates})
        target['parent_id'] = 'group'
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, op)
        del target['parent_id']
        target['points'].append({'x': 150, 'y': 10})
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, op)

    def test_curve_point_raw_checks_pass_through_point_and_protects_other_fields(self):
        before = board()
        line(before)['connector']['shape'] = 'curve'
        after = copy.deepcopy(before)
        line(after).update(y=10, height=30)
        line(after)['connector']['turning_points'] = [{'x': 50, 'y': 0}]
        op = {'kind': 'curve_point', 'id': 'line', 'point': {'x': 150, 'y': 10}}
        self.assertEqual(check_raw_preservation(before, after, op), [])
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, before, op)
        moved = copy.deepcopy(after)
        line(moved)['connector']['turning_points'][0]['x'] = 60
        next_op = {**op, 'point': {'x': 160, 'y': 10}}
        self.assertEqual(check_raw_preservation(after, moved, next_op), [])
        for field in ('arrow', 'caption', 'style', 'binding', 'z_index', 'other'):
            damaged = copy.deepcopy(after)
            target = line(damaged)
            if field == 'arrow':
                target['connector']['end']['arrow_style'] = 'none'
            elif field == 'caption':
                target['connector']['captions']['data'][0]['text'] = 'lost'
            elif field == 'style':
                target['style']['border_width'] = 'bold'
            elif field == 'binding':
                target['connector']['end_object']['id'] = 'a'
            elif field == 'other':
                line(damaged, 'other-line')['y'] += 1
            else:
                target['z_index'] += 1
            with self.subTest(damage=field), self.assertRaises(VerificationError):
                check_raw_preservation(before, damaged, op)

    def test_curve_point_second_handle_preserves_the_other_pass_through_point(self):
        before = board()
        line(before)['connector'].update(shape='curve', turning_points=[{'x': 30, 'y': -30}])
        after = copy.deepcopy(before)
        line(after)['connector']['turning_points'].append({'x': 70, 'y': 10})
        op = {'kind': 'curve_point', 'id': 'line', 'mode': 'segment', 'index': 1,
              'point': {'x': 170, 'y': 50}}
        self.assertEqual(check_raw_preservation(before, after, op), [])
        moved = copy.deepcopy(after)
        line(moved)['connector']['turning_points'][1] = {'x': 80, 'y': 20}
        next_op = {'kind': 'curve_point', 'id': 'line', 'mode': 'turning', 'index': 1,
                   'point': {'x': 180, 'y': 60}}
        self.assertEqual(check_raw_preservation(after, moved, next_op), [])
        line(moved)['connector']['turning_points'][0]['x'] += 1
        with self.assertRaises(VerificationError):
            check_raw_preservation(after, moved, next_op)

    def test_path_checks_canvas_points_and_rejects_noop_or_binding_change(self):
        raw = board()
        line(raw)['connector']['shape'] = 'curve'
        before = projection(raw)
        line({'nodes': before})['points'] = [{'x': 120, 'y': 40}, {'x': 180, 'y': 40}]
        points = [{'x': 120, 'y': 40.01}, {'x': 180, 'y': 30}]
        op = {'kind': 'path', 'id': 'line', 'points': points}
        after = copy.deepcopy(before)
        line({'nodes': after})['points'] = copy.deepcopy(points)
        check_scope(before, after, op)
        with self.assertRaises(VerificationError):
            check_scope(before, before, op)
        line({'nodes': after})['end_id'] = 'a'
        with self.assertRaises(VerificationError):
            check_scope(before, after, op)

    def test_polyline_path_projects_local_points_as_canvas_coordinates(self):
        before = board()
        line(before)['connector']['shape'] = 'polyline'
        line(before)['connector']['turning_points'] = [{'x': 20, 'y': 30}]
        self.assertEqual(line({'nodes': projection(before)})['points'], [{'x': 120, 'y': 70}])
        after = copy.deepcopy(before)
        line(after)['connector']['turning_points'] = [{'x': 25, 'y': -10}, {'x': 75, 'y': 30}]
        op = {'kind': 'path', 'id': 'line', 'points': [{'x': 125, 'y': 30}, {'x': 175, 'y': 70}]}
        self.verify(before, after, op)
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, before, op)
        line(after)['connector']['end']['arrow_style'] = 'none'
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_curve_control_points_require_native_readback_when_absent_from_raw(self):
        raw = board()
        line(raw)['connector'].update(shape='curve', turning_points=[])
        points = [{'x': 120, 'y': 30}, {'x': 180, 'y': 50}]
        op = {'kind': 'path', 'id': 'line', 'points': points}
        nodes = projection(raw)
        # Raw cannot establish whether controls changed. The ordinary editor
        # snapshot path must continue to reject missing or stale controls.
        self.assertEqual(check_raw_preservation(raw, raw, op), [])
        check_scope(nodes, nodes, op, from_raw=True)
        with self.assertRaises(VerificationError):
            check_scope(nodes, nodes, op)
        native = copy.deepcopy(nodes)
        line({'nodes': native})['points'] = points
        check_scope(nodes, native, op)
        damaged = copy.deepcopy(raw)
        line(damaged)['connector']['end_object']['id'] = 'a'
        line(damaged)['connector']['end']['attached_object']['id'] = 'a'
        with self.assertRaises(VerificationError):
            check_raw_preservation(raw, damaged, op)
        damaged = copy.deepcopy(raw)
        line(damaged)['text'] = {'text': 'unrelated new text'}
        with self.assertRaises(VerificationError):
            check_raw_preservation(raw, damaged, op)

    def test_raw_path_exemption_does_not_apply_to_polyline_or_type_change(self):
        raw = board()
        line(raw)['connector']['shape'] = 'polyline'
        op = {'kind': 'path', 'id': 'line', 'points': [{'x': 150, 'y': 90}]}
        with self.assertRaises(VerificationError):
            check_scope(projection(raw), projection(raw), op, from_raw=True)
        line(raw)['connector']['shape'] = 'curve'
        op['points'] = [{'x': 120, 'y': 30}, {'x': 180, 'y': 50}]
        after = copy.deepcopy(raw)
        line(after)['connector']['shape'] = 'polyline'
        with self.assertRaises(VerificationError):
            check_raw_preservation(raw, after, op)

    def test_server_curve_comparison_ignores_only_controls_and_keeps_inputs(self):
        raw = board()
        line(raw)['connector']['shape'] = 'curve'
        server = projection(raw)
        native = copy.deepcopy(server)
        line({'nodes': native})['points'] = [{'x': 120, 'y': 30}, {'x': 180, 'y': 50}]
        originals = copy.deepcopy((server, native))
        self.assertTrue(Runner.server_equivalent(server, native))
        self.assertEqual((server, native), originals)
        for field, value in (('style', {'border_width': 'bold'}), ('start_id', 'b'),
                             ('start_anchor', {'snap_to': 'top', 'position': {'x': 0.5, 'y': 0}}),
                             ('caption', 'damaged'), ('shape', 'polyline')):
            with self.subTest(field=field):
                damaged = copy.deepcopy(native)
                line({'nodes': damaged})[field] = value
                self.assertFalse(Runner.server_equivalent(server, damaged))
        line({'nodes': server})['shape'] = 'polyline'
        line({'nodes': native})['shape'] = 'polyline'
        self.assertFalse(Runner.server_equivalent(server, native))

    def test_reopen_checks_restored_native_controls_before_entering_editor(self):
        raw = board()
        line(raw)['connector']['shape'] = 'curve'
        expected = projection(raw)
        line({'nodes': expected})['points'] = [{'x': 120, 'y': 30}, {'x': 180, 'y': 50}]
        for drift in (0, 0.01):
            with self.subTest(control_drift=drift):
                runner = Runner.__new__(Runner)
                runner.token, runner.task, runner.tab = 'old-token', 'old-task', 'old-tab'
                calls, writes = [], []
                state = {'nodes': copy.deepcopy(expected), 'seq': 2, 'savedSeq': 2}
                line({'nodes': state['nodes']})['points'][0]['x'] += drift
                runner.report = {}
                runner.call = lambda path, data: calls.append((path, data)) or {'taskId':runner.task,'state':'completed','keep':data['keep'],'closed':1,'released':0}
                def open_page():
                    self.assertEqual((runner.token, runner.task, runner.tab), (None, None, None))
                    runner.token, runner.task, runner.tab = 'new-token', 'new-task', 'new-tab'
                runner.open_page = open_page
                def hydrate(saved):
                    self.assertIs(saved, raw)
                    return state
                runner.hydrate = hydrate
                runner.editor = lambda op: calls.append(op)
                runner.write = lambda name, value: writes.append((name, value))
                if drift:
                    with self.assertRaisesRegex(VerificationError, 'Fresh-page native readback'):
                        runner.reopen_verified(raw, expected)
                    self.assertEqual(writes, [('reopen-mismatch.json', state)])
                    self.assertNotIn({'kind': 'enter'}, calls)
                else:
                    self.assertIs(runner.reopen_verified(raw, expected), state)
                    self.assertEqual(writes, [])
                    self.assertEqual(calls[-1], {'kind': 'enter'})
                self.assertEqual(calls[0], ('/v2/tasks/old-task/complete', {'keep': False}))
                self.assertEqual((runner.token, runner.task, runner.tab), ('new-token', 'new-task', 'new-tab'))

    def test_same_rgb_with_zero_alpha_cannot_satisfy_a_color_request(self):
        nodes = projection(board())
        alpha = {n['id']: {'border': 1, 'text': 1} for n in nodes}
        before = {'nodes': nodes, 'render_alpha': alpha}
        after = copy.deepcopy(before)
        op = {'kind': 'style', 'id': 'line', 'style': {'border_color': '#000000'}}
        check_scope(before['nodes'], after['nodes'], op)
        Runner.verify_render_alpha(before, after, op)
        after['render_alpha']['line']['border'] = 0
        # RGB, opacity in raw, and all projected properties are unchanged.
        check_scope(before['nodes'], after['nodes'], op)
        with self.assertRaisesRegex(VerificationError, 'transparent'):
            Runner.verify_render_alpha(before, after, op)

    def test_color_request_rejects_missing_object_or_component_alpha_evidence(self):
        nodes = projection(board())
        base = {'nodes': nodes, 'render_alpha': {n['id']: {'border': 1, 'text': 1} for n in nodes}}
        op = {'kind': 'style', 'id': 'line', 'style': {'border_color': '#000000'}}
        for missing in ('before-object', 'after-object', 'both-components'):
            with self.subTest(missing_evidence=missing):
                before, after = copy.deepcopy(base), copy.deepcopy(base)
                if missing == 'before-object':
                    del before['render_alpha']['line']
                elif missing == 'after-object':
                    del after['render_alpha']['other-line']
                else:
                    del before['render_alpha']['line']['border']
                    del after['render_alpha']['line']['border']
                with self.assertRaises(VerificationError):
                    Runner.verify_render_alpha(before, after, op)

    def test_save_wait_rejects_alpha_drift_before_export_even_if_rgb_matches(self):
        raw = board()
        expected = projection(raw)
        expected_alpha = {n['id']: {'border': 1, 'text': 1} for n in expected}
        for alpha in (1, 0):
            with self.subTest(alpha_during_save=alpha):
                runner = Runner.__new__(Runner)
                runner.timeout = 1
                state = {'nodes': copy.deepcopy(expected), 'render_alpha': copy.deepcopy(expected_alpha),
                         'seq': 2, 'savedSeq': 2}
                state['render_alpha']['line']['border'] = alpha
                inspections, exports = [], []
                runner.editor = lambda op: inspections.append(op) or state
                runner.export = lambda: exports.append(True) or (raw, 'saved.json')
                if alpha == 1:
                    self.assertEqual(runner.settle(expected, expected_alpha), (raw, 'saved.json'))
                    self.assertEqual(exports, [True])
                else:
                    with self.assertRaisesRegex(VerificationError, 'alpha changed during save'):
                        runner.settle(expected, expected_alpha)
                    self.assertEqual(exports, [])
                self.assertEqual(inspections, [{'kind': 'inspect'}])

    def test_unrequested_alpha_and_connection_alpha_are_preserved(self):
        nodes = projection(board())
        alpha = {n['id']: {'border': 1, 'text': 1} for n in nodes}
        alpha['a']['fill'] = 0.4
        before = {'nodes': nodes, 'render_alpha': alpha}
        op = {'kind': 'style', 'id': 'a', 'style': {'border_color': '#ff8800'}}
        for ident, component in (('a', 'fill'), ('a', 'text'), ('other-line', 'border')):
            with self.subTest(object=ident, component=component):
                after = copy.deepcopy(before)
                after['render_alpha'][ident][component] -= 1e-5
                with self.assertRaisesRegex(VerificationError, 'Unrequested rendering alpha'):
                    Runner.verify_render_alpha(before, after, op)
        self.assertTrue(Runner.alpha_equivalent({'a': {'fill': 0.4}}, {'a': {'fill': 0.4000001}}))
        self.assertFalse(Runner.alpha_equivalent({'a': {'fill': 0.4}}, {'a': {'fill': 0.40001}}))
        after = copy.deepcopy(before)
        added = copy.deepcopy(line({'nodes': nodes}))
        added['id'] = 'new-line'
        after['nodes'].append(added)
        after['render_alpha']['new-line'] = {'border': 1, 'text': 1}
        for template in (None, 'line'):
            with self.subTest(template=template):
                connect = {'kind': 'connect', 'start_id': 'a', 'end_id': 'b'}
                if template:
                    connect['template_id'] = template
                Runner.verify_render_alpha(before, after, connect)
                after['render_alpha']['new-line']['border'] = 0
                with self.assertRaises(VerificationError):
                    Runner.verify_render_alpha(before, after, connect)
                after['render_alpha']['new-line']['border'] = 1

    def test_save_rejects_endpoint_drift_even_if_binding_ids_and_boxes_match(self):
        raw = board()
        expected = projection(raw)
        endpoints = {'line': {'start': {'x': 100, 'y': 40}, 'end': {'x': 200, 'y': 40}}}
        runner = Runner.__new__(Runner)
        runner.timeout = 1
        state = {'nodes': expected, 'seq': 0, 'savedSeq': 0, 'line_endpoints': copy.deepcopy(endpoints)}
        state['line_endpoints']['line']['start']['x'] += 20
        runner.editor = lambda op: state
        runner.export = lambda: self.fail('Export cannot prove a hidden endpoint drift')
        with self.assertRaisesRegex(VerificationError, 'line endpoints changed'):
            runner.settle(expected, expected_endpoints=endpoints)

    def test_reopen_rejects_endpoint_drift_even_if_binding_ids_and_boxes_match(self):
        raw = board()
        expected = projection(raw)
        endpoints = {'line': {'start': {'x': 100, 'y': 40}, 'end': {'x': 200, 'y': 40}}}
        for drift in (0, 20):
            with self.subTest(endpoint_drift=drift):
                runner = Runner.__new__(Runner)
                runner.token, runner.task, runner.tab = 'old-token', 'old-task', 'old-tab'
                calls, writes = [], []
                state = {'nodes': expected, 'line_endpoints': copy.deepcopy(endpoints)}
                state['line_endpoints']['line']['end']['x'] += drift
                runner.report = {}
                runner.call = lambda path, data: calls.append((path, data)) or {'taskId':runner.task,'state':'completed','keep':data['keep'],'closed':1,'released':0}
                runner.open_page = lambda: None
                runner.hydrate = lambda saved: state
                runner.editor = lambda op: calls.append(op)
                runner.write = lambda name, value: writes.append((name, value))
                if drift:
                    with self.assertRaisesRegex(VerificationError, 'native line endpoints'):
                        runner.reopen_verified(raw, expected, expected_endpoints=endpoints)
                    self.assertEqual(writes, [('reopen-endpoints-mismatch.json', state)])
                    self.assertNotIn({'kind': 'enter'}, calls)
                else:
                    self.assertIs(runner.reopen_verified(raw, expected, expected_endpoints=endpoints), state)
                    self.assertEqual(calls[-1], {'kind': 'enter'})

    def test_reopen_rejects_alpha_drift_with_identical_rgb_and_nodes(self):
        raw = board()
        expected = projection(raw)
        expected_alpha = {n['id']: {'border': 1, 'text': 1} for n in expected}
        for restored_alpha in (1, 0.99999, 0):
            with self.subTest(alpha=restored_alpha):
                runner = Runner.__new__(Runner)
                runner.token, runner.task, runner.tab = 'old-token', 'old-task', 'old-tab'
                calls, writes = [], []
                state = {'nodes': copy.deepcopy(expected), 'render_alpha': copy.deepcopy(expected_alpha)}
                state['render_alpha']['line']['text'] = restored_alpha
                runner.report = {}
                runner.call = lambda path, data: calls.append((path, data)) or {'taskId':runner.task,'state':'completed','keep':data['keep'],'closed':1,'released':0}
                def open_page():
                    runner.token, runner.task, runner.tab = 'new-token', 'new-task', 'new-tab'
                runner.open_page = open_page
                runner.hydrate = lambda saved: state
                runner.editor = lambda op: calls.append(op)
                runner.write = lambda name, value: writes.append((name, value))
                if restored_alpha == 1:
                    self.assertIs(runner.reopen_verified(raw, expected, expected_alpha), state)
                    self.assertEqual(writes, [])
                    self.assertEqual(calls[-1], {'kind': 'enter'})
                else:
                    with self.assertRaisesRegex(VerificationError, 'rendering alpha'):
                        runner.reopen_verified(raw, expected, expected_alpha)
                    self.assertEqual(writes, [('reopen-alpha-mismatch.json', state)])
                    self.assertNotIn({'kind': 'enter'}, calls)


class DeleteUndoRunnerTests(unittest.TestCase):
    def make_runner(self, operations, curve='line', fail_operation=None):
        runner = Runner.__new__(Runner)
        runner.request = {'operations': operations}
        runner.timeout = 1
        runner.uncertain = False
        runner.report = {'status': 'running', 'steps': []}
        runner.token = runner.task = runner.tab = None
        runner.index = 0
        runner.events, runner.writes = [], {}
        current = board()
        if curve:
            line(current, curve)['connector']['shape'] = 'curve'
        history = None
        page_count = 0

        def snapshot():
            nodes = projection(current)
            for node in nodes:
                if node.get('shape') == 'curve':
                    node['points'] = [{'x': node['x'] + 20, 'y': node['y'] + 10},
                                      {'x': node['x'] + 80, 'y': node['y'] - 10}]
            return {'nodes': nodes, 'seq': 2, 'savedSeq': 2,
                    'render_alpha': {n['id']: {'border': 1, 'text': 1} for n in nodes},
                    'line_endpoints': {n['id']: {'start': {'x': n['x'], 'y': n['y']},
                                               'end': {'x': n['x'] + n['width'], 'y': n['y']}}
                                       for n in nodes if n['kind'] == 'connector'}}

        def export():
            runner.index += 1
            raw = copy.deepcopy(current)
            runner.events.append(('export', runner.task, raw))
            return raw, f'raw-{runner.index:03d}.json'

        def open_page():
            nonlocal history, page_count
            page_count += 1
            runner.token, runner.task, runner.tab = ('token-' + str(page_count),
                                                    'task-' + str(page_count), 'tab-' + str(page_count))
            history = None
            runner.events.append(('open', runner.task))

        def editor(op, expected=None):
            nonlocal history, current
            kind = op['kind']
            runner.events.append(('editor', runner.task, kind))
            if kind in ('inspect', 'enter'):
                return snapshot()
            self.assertEqual(expected, snapshot()['nodes'])
            if kind == 'delete':
                history = (copy.deepcopy(current), runner.task, {'task_id': runner.task})
                current['nodes'] = [n for n in current['nodes'] if n['id'] not in op['delete_ids']]
            elif kind == 'undo':
                if history is None or op.get('undo_receipt') != history[2] or runner.task != history[1]:
                    raise VerificationError('Undo receipt no longer belongs to the current editor')
                self.assertEqual(op['undo_count'], 2)
                current = copy.deepcopy(history[0])
                history = None
            elif kind == 'text':
                line(current, op['id'])['text']['text'] = op['text']
            else:
                self.fail('Unexpected fake editor operation: ' + kind)
            if kind == fail_operation:
                raise OSError('Result lost after the editor write')
            result = snapshot()
            if kind == 'delete':
                result.update(transaction_count=2, undo_receipt=history[2])
            return result

        runner.export, runner.open_page, runner.editor = export, open_page, editor
        runner.hydrate = lambda raw: snapshot()
        def complete(path, data):
            runner.events.append(('complete', runner.task, data))
            return {'taskId':runner.task, 'state':'completed', 'keep':data['keep'],
                    'closed':0 if data['keep'] else 1, 'released':1 if data['keep'] else 0}
        runner.call = complete
        runner.write = lambda name, data: runner.writes.update({name: copy.deepcopy(data)})
        return runner

    def test_delete_undo_preserves_editor_then_reopens_restored_board(self):
        delete = {'kind': 'delete', 'ids': ['other-line'], 'delete_ids': ['other-line']}
        for curve in ('line', 'other-line', None):
            with self.subTest(curve=curve):
                runner = self.make_runner([delete, {'kind': 'undo'}], curve=curve)
                runner.run()
                writes = [event for event in runner.events if event[0] == 'editor' and event[2] in ('delete', 'undo')]
                self.assertEqual(writes, [('editor', 'task-1', 'delete'), ('editor', 'task-1', 'undo')])
                completions = [event for event in runner.events if event[0] == 'complete']
                self.assertEqual(completions, [('complete', 'task-1', {'keep': False})])
                undo_index = runner.events.index(writes[1])
                reopen_index = runner.events.index(completions[0])
                self.assertLess(undo_index, reopen_index)
                deleted_exports = [event for event in runner.events[:undo_index] if event[0] == 'export'
                                   and 'other-line' not in {n['id'] for n in event[2]['nodes']}]
                self.assertGreaterEqual(len(deleted_exports), 2)
                restored_exports = [event for event in runner.events[undo_index:reopen_index] if event[0] == 'export']
                self.assertEqual(len(restored_exports), 1)
                self.assertEqual({n['id'] for n in restored_exports[0][2]['nodes']}, {'a', 'b', 'line', 'other-line'})
                self.assertNotIn('reopened-001.json', runner.writes)
                self.assertIn('reopened-002.json', runner.writes)
                self.assertEqual(runner.report['status'], 'verified')
                self.assertEqual(len(runner.report['steps']), 2)
                self.assertFalse(runner.uncertain)

    def test_curve_reload_remains_for_delete_without_undo_and_other_edits(self):
        for op in ({'kind': 'delete', 'ids': ['other-line'], 'delete_ids': ['other-line']},
                   {'kind': 'text', 'id': 'b', 'text': 'changed'}):
            with self.subTest(operation=op):
                runner = self.make_runner([op])
                runner.run()
                self.assertIn('reopened-001.json', runner.writes)
                self.assertEqual([e[0] for e in runner.events].count('open'), 2)
                self.assertEqual(runner.report['status'], 'verified')

    def test_undo_without_immediately_preceding_delete_is_rejected_before_write(self):
        delete = {'kind': 'delete', 'ids': ['other-line'], 'delete_ids': ['other-line']}
        for operations, successful_undos in (([{'kind': 'undo'}], 0),
                ([delete, {'kind': 'text', 'id': 'b', 'text': 'changed'}, {'kind': 'undo'}], 0),
                ([delete, {'kind': 'undo'}, {'kind': 'undo'}], 0)):
            with self.subTest(operations=operations):
                runner = self.make_runner(operations)
                with self.assertRaisesRegex(VerificationError, 'only allowed immediately'):
                    runner.run()
                self.assertEqual(sum(e[0] == 'editor' and e[2] == 'undo' for e in runner.events), successful_undos)
                self.assertFalse(runner.uncertain)
                self.assertEqual(runner.events, [])

    def test_lost_delete_or_undo_response_preserves_uncertain_page_without_retry(self):
        operations = [{'kind': 'delete', 'ids': ['other-line'], 'delete_ids': ['other-line']}, {'kind': 'undo'}]
        for failed in ('delete', 'undo'):
            with self.subTest(failed_operation=failed):
                runner = self.make_runner(operations, fail_operation=failed)
                with self.assertRaisesRegex(OSError, 'Result lost'):
                    runner.run()
                self.assertTrue(runner.uncertain)
                self.assertEqual([e for e in runner.events if e[0] == 'complete'], [])
                self.assertEqual(sum(e[0] == 'editor' and e[2] == failed for e in runner.events), 1)
                runner.close()
                self.assertEqual(runner.events[-1], ('complete', 'task-1', {'keep': True}))
                self.assertEqual(runner.report['released_tab'], 'tab-1')

    def test_deferred_reopen_does_not_skip_save_alpha_endpoints_or_raw_checks(self):
        operations = [{'kind': 'delete', 'ids': ['other-line'], 'delete_ids': ['other-line']}, {'kind': 'undo'}]
        for drift in ('alpha', 'endpoint', 'raw'):
            with self.subTest(drift=drift):
                runner = self.make_runner(operations)
                original_editor, original_export = runner.editor, runner.export
                deleted = False
                def editor(op, expected=None):
                    nonlocal deleted
                    state = original_editor(op, expected)
                    if op['kind'] == 'delete':
                        deleted = True
                    elif deleted and op['kind'] == 'inspect':
                        if drift == 'alpha':
                            state['render_alpha']['b']['text'] = 0
                        elif drift == 'endpoint':
                            state['line_endpoints']['line']['end']['x'] += 20
                    return state
                def export():
                    raw, name = original_export()
                    if deleted and drift == 'raw':
                        line(raw, 'b')['locked'] = True
                    return raw, name
                runner.editor, runner.export = editor, export
                with self.assertRaises(VerificationError):
                    runner.run()
                self.assertEqual(runner.uncertain, drift != 'raw')
                self.assertFalse(any(e[0] == 'editor' and e[2] == 'undo' for e in runner.events))
                self.assertEqual([e for e in runner.events if e[0] == 'complete'], [])

    def test_restored_board_still_requires_fresh_native_readback(self):
        operations = [{'kind': 'delete', 'ids': ['other-line'], 'delete_ids': ['other-line']}, {'kind': 'undo'}]
        for drift in ('controls', 'alpha', 'endpoint'):
            with self.subTest(drift=drift):
                runner = self.make_runner(operations)
                original_hydrate = runner.hydrate
                def hydrate(raw):
                    state = original_hydrate(raw)
                    if runner.task == 'task-2':
                        if drift == 'controls':
                            line({'nodes': state['nodes']})['points'][0]['x'] += 1
                        elif drift == 'alpha':
                            state['render_alpha']['other-line']['text'] = 0
                        else:
                            state['line_endpoints']['other-line']['end']['x'] += 20
                    return state
                runner.hydrate = hydrate
                with self.assertRaisesRegex(VerificationError, 'Fresh-page'):
                    runner.run()
                self.assertFalse(runner.uncertain)
                self.assertEqual(len(runner.report['steps']), 2)
                self.assertEqual(runner.report['steps'][1]['save_status'], 'confirmed')
                self.assertEqual(runner.report['steps'][1]['verification_status'], 'failed')
                self.assertEqual(runner.report['steps'][1]['failure_phase'], 'reopen')
                self.assertEqual(runner.report['status'], 'unverified')


if __name__ == '__main__':
    unittest.main()
