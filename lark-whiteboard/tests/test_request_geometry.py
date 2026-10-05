"""Batch rejection and protection boundaries; native business trials are separate."""
import copy
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_nodes import compile_diagram
from whiteboard import (VerificationError, check_raw_preservation, check_scope, projection,
                        reject_nested_groups, validate_local_operation,
                        validate_request_operations, validate_target, Runner)
from test_captions import board, line
import test_local_edits as local_edits


class RequestGeometry(unittest.TestCase):
    def request(self, operations):
        return {'document_url': 'https://tenant.feishu.cn/docx/Abc123',
                'whiteboard_token': 'Board123', 'operations': operations}

    def test_valid_predecessor_does_not_hide_illegal_final_step(self):
        valid = {'kind': 'text', 'id': 'a', 'text': 'valid first edit'}
        for last in ({'kind': 'unknown', 'id': 'a'}, {'kind': 'move', 'ids': ['a'], 'dx': True, 'dy': 0},
                     {'kind': 'font', 'id': 'a', 'font_size': math.inf},
                     {'kind': 'resize', 'id': 'a', 'width': -1, 'height': 50},
                     {'kind': 'arrow', 'id': 'line', 'start': 'none', 'end': 'invented'},
                     {'kind': 'caption', 'id': 'line', 'text': 'x', 'point': {'x': 0, 'y': 0}}):
            with self.subTest(last=last), self.assertRaises(VerificationError):
                validate_target(self.request([valid, last]))

    def test_every_selection_is_typed_unique_and_complete(self):
        for ids in ([], 'a', ['a', 'a'], ['a', 1], [None], ['']):
            with self.subTest(ids=ids), self.assertRaises(VerificationError):
                validate_request_operations(self.request([{'kind': 'move', 'ids': ids, 'dx': 0, 'dy': 1}]))
        for op in ({'kind': 'group', 'ids': ['a']}, {'kind': 'align_top', 'ids': ['a']},
                   {'kind': 'distribute_horizontal', 'ids': ['a', 'b']},
                   {'kind': 'delete', 'ids': ['a'], 'delete_ids': ['b']}):
            with self.subTest(op=op), self.assertRaises(VerificationError):
                validate_request_operations(self.request([op]))

    def test_caption_then_format_is_static_valid_and_runtime_sequential(self):
        operations = [{'kind': 'caption', 'id': 'line', 'text': 'new label'},
                      {'kind': 'caption_format', 'id': 'line', 'font_size': 20.5, 'width': 140},
                      {'kind': 'caption_position', 'id': 'line', 'placement': 'above_line'}]
        validate_target(self.request(operations))
        nodes = projection(board())
        line({'nodes': nodes})['caption_texts'] = []
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, operations[1])
        line({'nodes': nodes})['caption_texts'] = ['new label']
        validate_local_operation(nodes, operations[1])

    def test_undo_order_is_checked_across_the_complete_batch(self):
        delete = {'kind': 'delete', 'ids': ['a'], 'delete_ids': ['a', 'line', 'other-line']}
        undo = {'kind': 'undo'}
        validate_request_operations(self.request([delete, undo]))
        for operations in ([undo], [delete, {'kind': 'font', 'id': 'b', 'font_size': 20}, undo],
                           [delete, undo, undo]):
            with self.subTest(operations=operations), self.assertRaises(VerificationError):
                validate_request_operations(self.request(operations))

    def test_single_end_reconnect_checks_the_final_other_endpoint(self):
        nodes = projection(board())
        for changes in ({'start_id':'b'}, {'end_id':'a'}):
            with self.subTest(changes=changes), self.assertRaisesRegex(VerificationError,'Self connection'):
                validate_local_operation(nodes, {'kind':'reconnect','id':'line',**changes})
        third = copy.deepcopy(line({'nodes':nodes},'a'))
        third.update(id='third', x=400)
        nodes.append(third)
        validate_local_operation(nodes, {'kind':'reconnect','id':'line','end_id':'third'})

    def test_cascade_cannot_remove_a_connector_from_a_retained_group(self):
        nodes = projection(board())
        line({'nodes':nodes})['parent_id'] = 'g'
        nodes.append(dict(id='g',kind='group',children=['line'],x=0,y=0,width=200,height=80))
        op = dict(kind='delete',ids=['a'],delete_ids=['a','line','other-line'])
        with self.assertRaisesRegex(VerificationError,'retained group'):
            validate_local_operation(nodes,op)
        validate_local_operation(nodes,dict(kind='delete',ids=['g'],delete_ids=['g','line']))

    def test_anchor_refresh_rejects_unbound_or_locked_endpoint_before_write(self):
        op = {'kind': 'anchors', 'id': 'line', 'end': {'snap_to': 'top', 'position': {'x': 0.5, 'y': 0}}}
        nodes = projection(board())
        validate_local_operation(nodes, op)
        line({'nodes': nodes}, 'a')['locked'] = True
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, op)
        del line({'nodes': nodes}, 'a')['locked']
        line({'nodes': nodes})['start_id'] = ''
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, op)
        for anchor in ({'snap_to': 'left', 'position': {'x': 0.5, 'y': 0.5}},
                       {'snap_to': 'top', 'position': {'x': True, 'y': 0}},
                       {'snap_to': 'top', 'position': {'x': 0.5, 'y': math.nan}}):
            with self.subTest(anchor=anchor), self.assertRaises(VerificationError):
                validate_request_operations(self.request([{**op, 'end': anchor}]))

    def grouped(self):
        nodes = projection(board())
        for ident in ('a', 'b'):
            line({'nodes': nodes}, ident)['parent_id'] = 'g'
        nodes.append({'id': 'g', 'kind': 'group', 'x': 0, 'y': 0, 'width': 300, 'height': 80,
                      'children': ['a', 'b'], 'style': {}})
        return nodes

    def test_one_group_member_edit_is_allowed_and_membership_changes_refused(self):
        nodes = self.grouped()
        for op in ({'kind': 'text', 'id': 'a', 'text': 'new'},
                   {'kind': 'font', 'id': 'a', 'font_size': 24},
                   {'kind': 'move', 'ids': ['a'], 'dx': 10, 'dy': 0},
                   {'kind': 'resize', 'id': 'a', 'width': 110, 'height': 80}):
            validate_local_operation(nodes, op)
        for op in ({'kind': 'move', 'ids': ['g', 'a'], 'dx': 10, 'dy': 0},
                   {'kind': 'group', 'ids': ['a', 'b']},
                   {'kind': 'delete', 'ids': ['a'], 'delete_ids': ['a', 'line', 'other-line']}):
            with self.subTest(op=op), self.assertRaises(VerificationError):
                validate_local_operation(nodes, op)
        nodes[-1]['parent_id'] = 'nested'
        with self.assertRaises(VerificationError):
            reject_nested_groups(nodes, {'kind': 'text', 'id': 'a', 'text': 'new'})

    def test_group_move_checks_locked_descendants_and_each_world_displacement(self):
        nodes = self.grouped()
        op = {'kind': 'move', 'ids': ['g'], 'dx': 10, 'dy': 20}
        line({'nodes': nodes}, 'b')['locked'] = True
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, op)
        del line({'nodes': nodes}, 'b')['locked']
        after = copy.deepcopy(nodes)
        for ident in ('g', 'a', 'b'):
            target = line({'nodes': after}, ident)
            target['x'] += 10
            target['y'] += 20
        # Bound lines may refresh their geometry independently.
        check_scope(nodes, after, op)
        for damage in ('child_did_not_move', 'child_size_changed'):
            bad = copy.deepcopy(after)
            target = line({'nodes': bad}, 'b')
            target['x' if damage == 'child_did_not_move' else 'width'] += 5
            with self.subTest(damage=damage), self.assertRaises(VerificationError):
                check_scope(nodes, bad, op)

    def test_move_preserves_dimensions_angle_and_layer(self):
        before = board()
        op = {'kind': 'move', 'ids': ['a'], 'dx': 10, 'dy': 0}
        after = copy.deepcopy(before)
        after['nodes'][0]['x'] += 10
        for field in ('width', 'height', 'angle', 'z_index'):
            damaged = copy.deepcopy(after)
            damaged['nodes'][0][field] = damaged['nodes'][0].get(field, 0) + 0.01
            with self.subTest(field=field), self.assertRaises(VerificationError):
                check_raw_preservation(before, damaged, op)
        damaged = copy.deepcopy(after)
        damaged['nodes'][1]['z_index'] = 77
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, damaged, op)

    def test_alignment_and_distribution_keep_unrequested_geometry(self):
        before = [{'id': 'a', 'kind': 'shape', 'x': 0, 'y': 30, 'width': 100, 'height': 80},
                  {'id': 'b', 'kind': 'shape', 'x': 150, 'y': 20, 'width': 100, 'height': 80},
                  {'id': 'c', 'kind': 'shape', 'x': 400, 'y': 10, 'width': 100, 'height': 80}]
        aligned = copy.deepcopy(before)
        for n in aligned:
            n['y'] = 10
        align = {'kind': 'align_top', 'ids': ['a', 'b', 'c']}
        check_scope(before, aligned, align)
        aligned[0]['height'] = 100
        with self.assertRaises(VerificationError):
            check_scope(before, aligned, align)
        distributed = copy.deepcopy(before)
        distributed[1]['x'] = 200
        op = {'kind': 'distribute_horizontal', 'ids': ['a', 'b', 'c']}
        check_scope(before, distributed, op)
        for n in distributed:
            n['x'] += 10
        with self.assertRaises(VerificationError):
            check_scope(before, distributed, op)

    def arrangement_board(self, specs):
        """Standalone shapes and their independently observed native outer boxes."""
        raw = {'nodes': []}
        bounds = {}
        for rank, (ident, angle, width, height, visible_x, visible_y) in enumerate(specs):
            radians = math.radians(angle)
            outer_width = abs(width * math.cos(radians)) + abs(height * math.sin(radians))
            outer_height = abs(width * math.sin(radians)) + abs(height * math.cos(radians))
            raw['nodes'].append({'id': ident, 'type': 'composite_shape',
                                 'x': visible_x + (outer_width-width)/2,
                                 'y': visible_y + (outer_height-height)/2,
                                 'width': width, 'height': height, 'angle': angle,
                                 'z_index': rank, 'composite_shape': {'type': 'rect'},
                                 'text': {'text': ident, 'font_size': 18},
                                 'style': {'border_color': '#000000', 'fill_color': '#ffffff'}})
            bounds[ident] = dict(x=visible_x, y=visible_y, width=outer_width, height=outer_height)
        raw['nodes'].append({'id': 'keep', 'type': 'composite_shape', 'x': 900, 'y': 700,
                             'width': 80, 'height': 50, 'angle': 30, 'z_index': len(specs),
                             'composite_shape': {'type': 'rect'}, 'text': {'text': 'untouched'}})
        return raw, bounds

    def arrangement_result(self, before, bounds, axis, positions, order):
        after, fresh = copy.deepcopy(before), copy.deepcopy(bounds)
        for ident, position in positions.items():
            line(after, ident)[axis] += position - bounds[ident][axis]
            fresh[ident][axis] = position
        return after, {'before': bounds, 'after': fresh, 'order': order}

    def verify_arrangement(self, before, after, op, evidence):
        check_scope(projection(before), projection(after), op, arrangement_evidence=evidence)
        self.assertEqual(check_raw_preservation(before, after, op, arrangement_evidence=evidence), [])

    def test_top_alignment_uses_visible_tops_for_mixed_rotations(self):
        before, bounds = self.arrangement_board([
            ('a', 0, 120, 50, 10, 0), ('b', 30, 80, 40, 200, 100),
            ('c', -30, 60, 110, 400, 200), ('d', 90, 150, 40, 600, 70)])
        op = {'kind': 'align_top', 'ids': ['a', 'b', 'c', 'd']}
        after, evidence = self.arrangement_result(before, bounds, 'y',
                                                 {'a': 0, 'b': 0, 'c': 0, 'd': 0},
                                                 ['d', 'b', 'a', 'c'])
        self.verify_arrangement(before, after, op, evidence)
        # Native outer tops agree even though serialized base y values differ.
        self.assertGreater(len({n['y'] for n in after['nodes'] if n['id'] != 'keep'}), 1)
        self.assertEqual(after['nodes'][-1], before['nodes'][-1])
        for damage in ('x', 'width', 'height', 'angle', 'z_index', 'text', 'unrelated'):
            bad = copy.deepcopy(after)
            if damage == 'text':
                line(bad, 'b')['text']['text'] = 'accidental rewrite'
            elif damage == 'unrelated':
                line(bad, 'keep')['x'] += 1
            else:
                line(bad, 'b')[damage] += 1
            with self.subTest(damage=damage), self.assertRaises(VerificationError):
                self.verify_arrangement(before, bad, op, evidence)
        wrong_position = copy.deepcopy(after)
        line(wrong_position, 'b')['y'] += 1
        with self.assertRaises(VerificationError):
            self.verify_arrangement(before, wrong_position, op, evidence)
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, wrong_position, op, arrangement_evidence=evidence)
        wrong_visible_top = copy.deepcopy(evidence)
        wrong_visible_top['after']['b']['y'] += 1
        with self.assertRaises(VerificationError):
            self.verify_arrangement(before, after, op, wrong_visible_top)

    def test_horizontal_distribution_handles_unequal_outer_widths_and_overlap(self):
        scenarios = [
            # Visible widths are 100, 40, 60; the two gaps must both be 80.
            ([('a', 0, 100, 50, 0, 0), ('b', 90, 80, 40, 120, 50),
              ('c', 0, 60, 50, 300, 100)], ['a', 'b', 'c'], {'a': 0, 'b': 180, 'c': 300}),
            # The widest first object defines the right edge, not the last
            # sorted object's edge. Negative spacing is valid native behavior.
            ([('a', 90, 20, 200, 0, 0), ('b', 0, 40, 50, 20, 50),
              ('c', 0, 60, 50, 50, 100)], ['c', 'b', 'a'], {'a': 0, 'b': 150, 'c': 140}),
            # Equal left edges retain the actual native selection order.
            ([('a', 90, 80, 160, 0, 0), ('b', 0, 40, 50, 0, 50),
              ('c', 0, 60, 50, 20, 100)], ['b', 'a', 'c'], {'a': -10, 'b': 0, 'c': 100})]
        op = {'kind': 'distribute_horizontal', 'ids': ['a', 'b', 'c']}
        for specs, order, positions in scenarios:
            with self.subTest(specs=specs):
                before, bounds = self.arrangement_board(specs)
                after, evidence = self.arrangement_result(before, bounds, 'x', positions, order)
                self.verify_arrangement(before, after, op, evidence)
                bad = copy.deepcopy(after)
                line(bad, 'b')['x'] += 1
                with self.assertRaises(VerificationError):
                    self.verify_arrangement(before, bad, op, evidence)
                shifted = copy.deepcopy(after)
                shifted_evidence = copy.deepcopy(evidence)
                for ident in op['ids']:
                    line(shifted, ident)['x'] += 10
                    shifted_evidence['after'][ident]['x'] += 10
                with self.assertRaises(VerificationError):
                    self.verify_arrangement(before, shifted, op, shifted_evidence)
        before, bounds = self.arrangement_board(scenarios[-1][0])
        after, evidence = self.arrangement_result(before, bounds, 'x', scenarios[-1][2], scenarios[-1][1])
        wrong_order = copy.deepcopy(evidence)
        wrong_order['order'] = ['a', 'b', 'c']
        with self.assertRaises(VerificationError):
            self.verify_arrangement(before, after, op, wrong_order)

    def test_rotated_arrangement_requires_complete_native_boxes_and_selection(self):
        before, bounds = self.arrangement_board([
            ('a', 0, 100, 50, 0, 0), ('b', 90, 80, 40, 120, 50),
            ('c', 0, 60, 50, 300, 100)])
        op = {'kind': 'distribute_horizontal', 'ids': ['a', 'b', 'c']}
        after, evidence = self.arrangement_result(before, bounds, 'x',
                                                 {'a': 0, 'b': 180, 'c': 300}, ['a', 'b', 'c'])
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)
        for order in (None, 'a,b,c', ['a', 'b'], ['a', 'a', 'c'], ['a', 'b', 'other']):
            invalid = copy.deepcopy(evidence)
            invalid['order'] = order
            with self.subTest(order=order), self.assertRaises(VerificationError):
                self.verify_arrangement(before, after, op, invalid)
            with self.subTest(raw_order=order), self.assertRaises(VerificationError):
                check_raw_preservation(before, after, op, arrangement_evidence=invalid)
        for phase in ('before', 'after'):
            for invalid_box in (None, {}, {'x': 120, 'y': 50, 'width': 40},
                                {'x': True, 'y': 50, 'width': 40, 'height': 80},
                                {'x': math.nan, 'y': 50, 'width': 40, 'height': 80},
                                {'x': 120, 'y': 50, 'width': 0, 'height': 80},
                                {'x': 120, 'y': 50, 'width': 40, 'height': -1}):
                invalid = copy.deepcopy(evidence)
                invalid[phase]['b'] = invalid_box
                with self.subTest(phase=phase, box=invalid_box), self.assertRaises(VerificationError):
                    self.verify_arrangement(before, after, op, invalid)
            missing = copy.deepcopy(evidence)
            del missing[phase]['b']
            with self.subTest(phase=phase, missing='b'), self.assertRaises(VerificationError):
                self.verify_arrangement(before, after, op, missing)
        for field in ('y', 'width', 'height'):
            invalid = copy.deepcopy(evidence)
            invalid['after']['b'][field] += 1
            with self.subTest(unrequested_visible_field=field), self.assertRaises(VerificationError):
                self.verify_arrangement(before, after, op, invalid)

    def test_arrangement_preserves_native_world_geometry_after_moving(self):
        before, bounds = self.arrangement_board([
            ('a', 0, 100, 50, 0, 0), ('b', 90, 80, 40, 120, 50),
            ('c', 0, 60, 50, 300, 100)])
        for kind, axis, positions in (
                ('align_top', 'y', {'a': 0, 'b': 0, 'c': 0}),
                ('distribute_horizontal', 'x', {'a': 0, 'b': 180, 'c': 300})):
            op = {'kind': kind, 'ids': ['a', 'b', 'c']}
            after, evidence = self.arrangement_result(before, bounds, axis, positions, op['ids'])
            for phase, raw in (('world_before', before), ('world_after', after)):
                evidence[phase] = {ident: {k: line(raw, ident)[k]
                                           for k in ('x', 'y', 'width', 'height', 'angle')}
                                   for ident in op['ids']}
                for world in evidence[phase].values():
                    world['x'] += 500
                    world['y'] += 300
            with self.subTest(kind=kind, result='correct_world_displacement'):
                self.verify_arrangement(before, after, op, evidence)
            # The saved raw nodes and visible outer boxes remain correct; the
            # independent native world read must still reject these changes.
            for field in ('width', 'height', 'angle', 'x', 'y'):
                invalid = copy.deepcopy(evidence)
                invalid['world_after']['b'][field] += 1
                with self.subTest(kind=kind, changed_world_field=field), self.assertRaises(VerificationError):
                    self.verify_arrangement(before, after, op, invalid)
            for phase in ('world_before', 'world_after'):
                missing_phase = copy.deepcopy(evidence)
                del missing_phase[phase]
                with self.subTest(kind=kind, missing_phase=phase), self.assertRaises(VerificationError):
                    self.verify_arrangement(before, after, op, missing_phase)
                missing_node = copy.deepcopy(evidence)
                del missing_node[phase]['b']
                with self.subTest(kind=kind, missing_node=phase), self.assertRaises(VerificationError):
                    self.verify_arrangement(before, after, op, missing_node)
                missing_field = copy.deepcopy(evidence)
                del missing_field[phase]['b']['angle']
                with self.subTest(kind=kind, missing_field=phase), self.assertRaises(VerificationError):
                    self.verify_arrangement(before, after, op, missing_field)
                for field in ('x', 'y', 'width', 'height', 'angle'):
                    for value in (math.nan, math.inf, -math.inf):
                        invalid = copy.deepcopy(evidence)
                        invalid[phase]['b'][field] = value
                        with self.subTest(kind=kind, phase=phase, field=field, value=value), self.assertRaises(VerificationError):
                            self.verify_arrangement(before, after, op, invalid)

    def test_creation_font_rejects_boolean(self):
        with self.assertRaises(ValueError):
            compile_diagram({'shapes': [{'id': 'a', 'x': 0, 'y': 0, 'width': 100, 'height': 80,
                                        'font_size': True}]})

    def test_member_move_accepts_only_derived_parent_envelope(self):
        before = self.grouped()
        after = copy.deepcopy(before)
        line({'nodes': after}, 'a')['x'] = 40
        line({'nodes': after}, 'g').update(x=40, width=260)
        op = {'kind': 'move', 'ids': ['a'], 'dx': 40, 'dy': 0}
        check_scope(before, after, op)
        for damage in ('width', 'member_identity', 'sibling_position'):
            bad = copy.deepcopy(after)
            if damage == 'width':
                line({'nodes': bad}, 'g')['width'] += 1
            elif damage == 'member_identity':
                line({'nodes': bad}, 'g')['children'] = ['a']
            else:
                line({'nodes': bad}, 'b')['x'] += 1
            with self.subTest(damage=damage), self.assertRaises(VerificationError):
                check_scope(before, bad, op)
        unchanged = copy.deepcopy(before)
        line({'nodes': unchanged}, 'a')['text'] = 'new'
        line({'nodes': unchanged}, 'g')['width'] += 1
        with self.assertRaises(VerificationError):
            check_scope(before, unchanged, {'kind': 'text', 'id': 'a', 'text': 'new'})

    def test_grouped_raw_member_edit_preserves_siblings_and_parent_properties(self):
        before = board()
        for ident in ('a', 'b'):
            line(before, ident)['parent_id'] = 'g'
        before['nodes'].append({'id': 'g', 'type': 'group', 'x': 0, 'y': 0, 'width': 300,
                                'height': 80, 'angle': 0, 'z_index': 5, 'children': ['a', 'b']})
        after = copy.deepcopy(before)
        line(after, 'a')['x'] = 40
        line(after, 'g').update(x=40, width=260)
        op = {'kind': 'move', 'ids': ['a'], 'dx': 40, 'dy': 0}
        self.assertEqual(check_raw_preservation(before, after, op), [])
        for ident, key in (('g', 'angle'), ('g', 'z_index'), ('b', 'width')):
            bad = copy.deepcopy(after)
            line(bad, ident)[key] += 1
            with self.subTest(ident=ident,key=key), self.assertRaises(VerificationError):
                check_raw_preservation(before, bad, op)

    def test_delete_allows_only_measured_sibling_layer_compaction(self):
        before = board()
        after = {'nodes': [copy.deepcopy(line(before, 'b'))]}
        after['nodes'][0]['z_index'] = 0
        op = {'kind': 'delete', 'ids': ['a'], 'delete_ids': ['a', 'line', 'other-line']}
        changes = check_raw_preservation(before, after, op)
        self.assertEqual(changes[0]['normalization'], 'delete_sibling_layer_compaction')
        after['nodes'][0]['z_index'] = 77
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_grouped_font_curve_roundoff_requires_complete_native_evidence(self):
        before = board()
        before['nodes'] = [n for n in before['nodes'] if n['id'] != 'other-line']
        for n in before['nodes']:
            n['parent_id'] = 'g'
        line(before)['connector'].update(shape='curve',turning_points=[{'x':110,'y':0.8789432644844055}])
        before['nodes'].append({'id':'g','type':'group','x':0,'y':0,'width':300,'height':80,
                                'angle':0,'z_index':5,'children':['a','b','line']})
        after = copy.deepcopy(before)
        line(after,'a')['text']['font_size'] = 26
        line(after)['connector']['turning_points'][0]['y'] = 0.878943145275116
        bounds = {n['id']:{k:n[k] for k in ('x','y','width','height')} for n in before['nodes']}
        points = [{'x':v,'y':10} for v in (10,30,110,170,190)]
        ends = {'line':{'start':{'x':0,'y':10},'end':{'x':300,'y':10}}}
        evidence = {'before':bounds,'after':copy.deepcopy(bounds),
                    'native_before':[{'id':'line','points':points}],
                    'native_after':[{'id':'line','points':copy.deepcopy(points)}],
                    'native_endpoints_before':ends,'native_endpoints_after':copy.deepcopy(ends),
                    'bindings_before':[{'id':'line','valid':True}], 'bindings_after':[{'id':'line','valid':True}]}
        evidence['native_after'][0]['points'][0]['y'] += 4e-6
        op = {'kind':'font','id':'a','font_size':26}
        receipt = check_raw_preservation(before,after,op,group_evidence=evidence)
        self.assertEqual(receipt[0]['normalization'],'grouped_text_curve_turning_point_roundoff')
        for key in ('native_before','native_endpoints_before','bindings_before'):
            bad = copy.deepcopy(evidence)
            bad.pop(key)
            with self.subTest(key=key),self.assertRaises(VerificationError):
                check_raw_preservation(before,after,op,group_evidence=bad)
        bad = copy.deepcopy(evidence)
        bad['native_after'][0]['points'][0]['y'] += 1e-4
        with self.assertRaises(VerificationError):
            check_raw_preservation(before,after,op,group_evidence=bad)
        line(after)['connector']['turning_points'][0]['y'] += 1e-4
        with self.assertRaises(VerificationError):
            check_raw_preservation(before,after,op,group_evidence=evidence)

    def test_grouped_text_allows_only_measured_curve_zero_height_roundoff(self):
        before = board()
        before['nodes'] = [n for n in before['nodes'] if n['id'] != 'other-line']
        for n in before['nodes']:
            n['parent_id'] = 'g'
        line(before)['connector']['shape'] = 'curve'
        before['nodes'].append({'id': 'g', 'type': 'group', 'x': 0, 'y': 0, 'width': 300,
                                'height': 80, 'angle': 0, 'z_index': 5, 'children': ['a', 'b', 'line']})
        after = copy.deepcopy(before)
        line(after, 'a')['text']['text'] = 'changed'
        line(after)['height'] = 1.7634914253709943e-14
        op = {'kind': 'text', 'id': 'a', 'text': 'changed'}
        changes = check_raw_preservation(before, after, op)
        self.assertEqual(changes[0]['normalization'], 'grouped_text_curve_zero_height_roundoff')
        for changed_height in (0.01, -1e-14):
            line(after)['height'] = changed_height
            with self.subTest(height=changed_height), self.assertRaises(VerificationError):
                check_raw_preservation(before, after, op)

    def test_group_and_ungroup_allow_only_measured_noncontiguous_layer_order(self):
        before = {'nodes': [{'id': ident, 'type': 'composite_shape', 'x': rank*200, 'y': 0,
                             'width': 100, 'height': 80, 'angle': 0, 'z_index': rank,
                             'composite_shape': {'type': 'rect'}}
                            for rank, ident in enumerate(('other', 'a', 'middle', 'b', 'last'))]}
        after = copy.deepcopy(before)
        for ident, rank in (('a', 0), ('b', 1)):
            line(after, ident).update(parent_id='g', z_index=rank)
        line(after, 'middle')['z_index'] = 1
        line(after, 'last')['z_index'] = 3
        after['nodes'].append({'id': 'g', 'type': 'group', 'x': 200, 'y': 0, 'width': 500,
                                'height': 80, 'angle': 0, 'z_index': 2, 'children': ['a', 'b']})
        group = {'kind': 'group', 'ids': ['a', 'b']}
        self.assertTrue(check_raw_preservation(before, after, group))
        bad = copy.deepcopy(after)
        line(bad, 'middle')['z_index'], line(bad, 'g')['z_index'] = 2, 1
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, bad, group)
        ungrouped = copy.deepcopy(after)
        ungrouped['nodes'] = [n for n in ungrouped['nodes'] if n['id'] != 'g']
        for ident in ('a', 'b'):
            line(ungrouped, ident).pop('parent_id')
        for rank, ident in enumerate(('other', 'middle', 'a', 'b', 'last')):
            line(ungrouped, ident)['z_index'] = rank
        self.assertTrue(check_raw_preservation(after, ungrouped, {'kind': 'ungroup', 'id': 'g'}))
        line(ungrouped, 'b')['z_index'] = 77
        with self.assertRaises(VerificationError):
            check_raw_preservation(after, ungrouped, {'kind': 'ungroup', 'id': 'g'})

    def test_label_visible_bounds_can_expand_group_without_changing_line_base(self):
        before = board()
        before['nodes'] = [n for n in before['nodes'] if n['id'] != 'other-line']
        for n in before['nodes']:
            n['parent_id'] = 'g'
        before['nodes'].append({'id': 'g', 'type': 'group', 'x': 0, 'y': 0, 'width': 300,
                                'height': 80, 'angle': 0, 'z_index': 5, 'children': ['a', 'b', 'line']})
        after = copy.deepcopy(before)
        line(after)['connector']['captions']['data'][0]['font_size'] = 24
        line(after, 'g').update(y=-40, height=120)
        geometry = lambda raw: {n['id']: {k:n[k] for k in ('x', 'y', 'width', 'height')} for n in raw['nodes']}
        evidence = {'before': geometry(before), 'after': geometry(after)}
        evidence['before']['line'].update(y=0, height=80)
        evidence['after']['line'].update(y=-40, height=120)
        op = {'kind': 'caption_format', 'id': 'line', 'font_size': 24}
        check_scope(projection(before), projection(after), op, group_evidence=evidence)
        self.assertEqual(check_raw_preservation(before, after, op, group_evidence=evidence)[0]['normalization'],
                         'native_derived_group_bounds_cache')
        # A native caption can save while the serialized parent cache stays old.
        stale = copy.deepcopy(after)
        line(stale, 'g').update({k:line(before, 'g')[k] for k in ('x','y','width','height')})
        self.assertEqual(check_raw_preservation(before, stale, op, group_evidence=evidence), [])
        self.assertTrue(Runner.server_equivalent(projection(stale), projection(after), evidence['after']))
        self.assertFalse(Runner.server_equivalent(projection(stale), projection(after)))
        bad_native = projection(after)
        line({'nodes':bad_native}, 'g')['height'] += 1
        self.assertFalse(Runner.server_equivalent(projection(stale), bad_native, evidence['after']))
        damaged_member = copy.deepcopy(stale)
        line(damaged_member, 'b')['x'] += 10
        self.assertFalse(Runner.server_equivalent(projection(damaged_member), projection(after), evidence['after']))
        bad = copy.deepcopy(after)
        line(bad, 'g')['height'] += 1
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, bad, op, group_evidence=evidence)
        bad_evidence = copy.deepcopy(evidence)
        bad_evidence['after']['b']['x'] += 10
        with self.assertRaises(VerificationError):
            check_scope(projection(before), projection(after), op, group_evidence=bad_evidence)

    def test_delayed_server_group_cache_requires_exact_member_and_other_property_preservation(self):
        before = board()
        before['nodes'] = [n for n in before['nodes'] if n['id'] != 'other-line']
        for n in before['nodes']:
            n['parent_id'] = 'g'
        before['nodes'].append({'id':'g','type':'group','x':0,'y':-40,'width':300,'height':120,
                                'angle':0,'z_index':0,'children':['a','b','line']})
        latest = copy.deepcopy(before)
        line(latest,'g').update(y=0,height=80)
        bounds = {n['id']:{k:n[k] for k in ('x','y','width','height')} for n in latest['nodes']}
        state = {'nodes':projection(latest),'object_bounds':bounds}
        receipts = Runner.verified_group_cache_catchup(before,latest,state)
        self.assertEqual(receipts[0]['normalization'],'delayed_native_group_bounds_cache')
        # A real reopen returned an empty native map before the saved cache
        # catchup appeared. It must wait for full proof instead of conflict.
        runner = object.__new__(Runner)
        runner.timeout,runner.index = 3,0
        states = iter([{'nodes':[],'object_bounds':{},'seq':0,'savedSeq':0},
                       {**state,'seq':1,'savedSeq':1}])
        runner.editor = lambda op: next(states)
        runner.export = lambda: (latest,'latest.json')
        runner.write = lambda *args: None
        with patch('whiteboard.time.sleep'):
            reopened = runner.hydrate(before)
        self.assertEqual(reopened['server_group_cache_catchup'][0]['id'],'g')
        self.assertEqual(Runner.verified_group_cache_catchup(before,latest,
                         {'nodes':[],'object_bounds':{}}),[])
        for ident,field,value in (('b','x',201),('g','height',79),('g','z_index',1),('g','angle',1)):
            bad = copy.deepcopy(latest)
            line(bad,ident)[field] = value
            self.assertEqual(Runner.verified_group_cache_catchup(before,bad,state),[])

    def test_bound_connector_uniform_move_requires_its_bound_shapes(self):
        nodes = projection(board())
        for ids in (['line'], ['line', 'a']):
            with self.subTest(ids=ids), self.assertRaises(VerificationError):
                validate_local_operation(nodes, {'kind': 'move', 'ids': ids, 'dx': 20, 'dy': 0})
        validate_local_operation(nodes, {'kind': 'move', 'ids': ['line', 'a', 'b'], 'dx': 20, 'dy': 0})
        for ident in ('a', 'b', 'line'):
            line({'nodes': nodes}, ident)['parent_id'] = 'g'
        nodes.append({'id': 'g', 'kind': 'group', 'children': ['a', 'b', 'line'],
                      'x': 0, 'y': 0, 'width': 300, 'height': 80, 'style': {}})
        validate_local_operation(nodes, {'kind': 'move', 'ids': ['g'], 'dx': 20, 'dy': 0})

    def test_group_rejects_selected_bound_line_with_endpoint_outside_selection(self):
        raw = board()
        raw['nodes'] = [n for n in raw['nodes'] if n['id'] != 'other-line']
        third = copy.deepcopy(line(raw, 'a'))
        third.update(id='third', x=400)
        raw['nodes'].append(third)
        nodes = projection(raw)
        for ids in (['a','third','line'], ['b','third','line'], ['third','line']):
            with self.subTest(ids=ids), self.assertRaisesRegex(VerificationError, 'all its bound endpoints'):
                validate_local_operation(nodes, {'kind':'group','ids':ids})
        validate_local_operation(nodes, {'kind':'group','ids':['a','b','line']})
        for side, endpoint in (('start','a'), ('end','b')):
            half = copy.deepcopy(line({'nodes':nodes}))
            half.update(id='half-'+side, start_id='' if side=='end' else 'a',
                        end_id='' if side=='start' else 'b')
            nodes.append(half)
            with self.subTest(single_bound_side=side), self.assertRaisesRegex(VerificationError, 'all its bound endpoints'):
                validate_local_operation(nodes, {'kind':'group','ids':['third',half['id']]})
            validate_local_operation(nodes, {'kind':'group','ids':[endpoint,half['id']]})
        free = copy.deepcopy(line({'nodes':nodes}))
        free.update(id='free-line', start_id='', end_id='')
        nodes.append(free)
        validate_local_operation(nodes, {'kind':'group','ids':['third','free-line']})

    def test_invalid_group_never_reaches_mutating_editor_command(self):
        for ids in (['a','line'], ['b','line'], ['line','other-line']):
            with self.subTest(ids=ids), patch('whiteboard.time.sleep'):
                runner = local_edits.DeleteUndoRunnerTests('runTest').make_runner(
                    [{'kind':'group','ids':ids}], curve=None)
                with self.assertRaises(VerificationError):
                    runner.run()
                self.assertFalse(any(e[0]=='editor' and e[2]=='group' for e in runner.events))
                step = runner.report['steps'][0]
                self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']),
                                 ('not_written','failed','preflight'))
                self.assertFalse(runner.uncertain)


if __name__ == '__main__':
    unittest.main()
