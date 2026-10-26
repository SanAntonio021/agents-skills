"""Batch font, the eight alignment modes and the four layer-order actions."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import (ALIGN_MODES, ORDER_ACTIONS, VerificationError,
                        check_raw_preservation, check_scope, projection,
                        validate_local_operation, validate_operation_parameters)


def board():
    """Four shapes on one row plus one connector, all ungrouped."""
    nodes = []
    for index, (x, height) in enumerate(((0, 60), (200, 90), (420, 60), (640, 90)), start=1):
        nodes.append({
            'id': f's{index}', 'type': 'composite_shape', 'composite_shape': {'type': 'rect'},
            'x': x, 'y': 100 - height / 2, 'width': 120, 'height': height, 'angle': 0,
            'z_index': index, 'locked': False,
            'style': {'border_color': '#2457a7', 'fill_color': '#e8f0fe', 'border_style': 'solid',
                      'border_width': 'narrow', 'text_color': '#1f2329'},
            'text': {'text': f'模块{index}', 'font_size': 16, 'angle': 0, 'font_weight': 'regular',
                     'horizontal_align': 'center', 'vertical_align': 'mid', 'italic': False,
                     'line_through': False, 'underline': False, 'text_color': '#1f2329',
                     'text_color_type': 1, 'text_background_color_type': 0,
                     'theme_text_background_color_code': -1},
        })
    nodes.append({
        'id': 'line', 'type': 'connector', 'x': 120, 'y': 70, 'width': 80, 'height': 0, 'angle': 0,
        'z_index': 5, 'locked': False,
        'style': {'border_color': '#000000', 'border_style': 'solid', 'border_width': 'narrow'},
        'connector': {'shape': 'straight', 'specified_coordinate': True, 'caption_auto_direction': False,
                      'start_object': {'id': 's1', 'position': {'x': 1, 'y': 0.5}, 'snap_to': 'right'},
                      'end_object': {'id': 's2', 'position': {'x': 0, 'y': 0.5}, 'snap_to': 'left'},
                      'start': {'arrow_style': 'none', 'attached_object': {'id': 's1', 'position': {'x': 1, 'y': 0.5}, 'snap_to': 'right'}},
                      'end': {'arrow_style': 'line_arrow', 'attached_object': {'id': 's2', 'position': {'x': 0, 'y': 0.5}, 'snap_to': 'left'}},
                      'turning_points': []},
    })
    return {'nodes': nodes}


def lookup(raw):
    return {n['id']: n for n in raw['nodes']}


def move(raw, ident, axis, delta):
    lookup(raw)[ident][axis] += delta


class BatchFont(unittest.TestCase):
    def test_accepts_ids_or_id_but_not_both(self):
        validate_operation_parameters({'kind': 'font', 'ids': ['s1', 's2'], 'font_size': 16})
        validate_operation_parameters({'kind': 'font', 'id': 's1', 'font_size': 16})
        for op in ({'kind': 'font', 'font_size': 16},
                   {'kind': 'font', 'id': 's1', 'ids': ['s2'], 'font_size': 16},
                   {'kind': 'font', 'ids': [], 'font_size': 16},
                   {'kind': 'font', 'ids': ['s1', 's1'], 'font_size': 16},
                   {'kind': 'font', 'ids': ['s1'], 'font_size': True},
                   {'kind': 'font', 'ids': ['s1'], 'font_size': 3}):
            with self.subTest(operation=op):
                with self.assertRaises(VerificationError):
                    validate_operation_parameters(op)

    def test_targets_must_be_native_shapes_or_text(self):
        nodes = projection(board())
        validate_local_operation(nodes, {'kind': 'font', 'ids': ['s1', 's2'], 'font_size': 16})
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, {'kind': 'font', 'ids': ['s1', 'line'], 'font_size': 16})

    def test_batch_font_intent_requires_every_target(self):
        before = projection(board())
        after = copy.deepcopy(before)
        for node in after:
            if node['id'] in ('s1', 's2'):
                node['font_size'] = 20
        op = {'kind': 'font', 'ids': ['s1', 's2'], 'font_size': 20}
        check_scope(before, after, op)
        partial = copy.deepcopy(after)
        for node in partial:
            if node['id'] == 's2':
                node['font_size'] = 16
        with self.assertRaises(VerificationError):
            check_scope(before, partial, op)


class AlignmentModes(unittest.TestCase):
    def aligned(self, kind):
        raw = board()
        before = projection(raw)
        ids = ['s1', 's2', 's3', 's4'] if kind.startswith('distribute') else ['s1', 's2']
        axis, mode = ALIGN_MODES[kind]
        size = 'width' if axis == 'x' else 'height'
        box = {i: before[[n['id'] for n in before].index(i)] for i in ids}
        if mode == 'distribute':
            ordered = sorted(ids, key=lambda i: box[i][axis])
            position = min(box[i][axis] for i in ordered)
            span = max(box[i][axis] + box[i][size] for i in ordered) - position
            gap = (span - sum(box[i][size] for i in ordered)) / (len(ordered) - 1)
            for i in ordered:
                move(raw, i, axis, position - box[i][axis])
                position += box[i][size] + gap
        else:
            if mode == 'min_edge':
                target = min(box[i][axis] for i in ids)
            elif mode == 'max_edge':
                target = max(box[i][axis] + box[i][size] for i in ids)
            else:
                target = (min(box[i][axis] for i in ids)
                          + max(box[i][axis] + box[i][size] for i in ids)) / 2
            for i in ids:
                offset = 0 if mode == 'min_edge' else (box[i][size] if mode == 'max_edge' else box[i][size] / 2)
                move(raw, i, axis, target - offset - box[i][axis])
        return raw, before, projection(raw), {'kind': kind, 'ids': ids}

    def test_every_mode_satisfies_its_own_postcondition(self):
        self.assertEqual(set(ALIGN_MODES), {'align_left', 'align_right', 'align_horizontal_center',
                                            'align_top', 'align_bottom', 'align_vertical_center',
                                            'distribute_horizontal', 'distribute_vertical'})
        for kind in ALIGN_MODES:
            with self.subTest(kind=kind):
                _, before, after, op = self.aligned(kind)
                check_scope(before, after, op)

    def test_mode_rejects_the_opposite_axis(self):
        for kind, wrong_axis in (('align_left', 'y'), ('align_top', 'x'),
                                 ('align_vertical_center', 'x'), ('distribute_vertical', 'x')):
            with self.subTest(kind=kind):
                _, before, _, op = self.aligned(kind)
                wrong = copy.deepcopy(before)
                for node in wrong:
                    if node['id'] in op['ids']:
                        node[wrong_axis] += 30
                with self.assertRaises(VerificationError):
                    check_scope(before, wrong, op)

    def test_left_alignment_rejects_a_right_edge_move(self):
        _, before, _, op = self.aligned('align_left')
        edge = copy.deepcopy(before)
        target = max(n['x'] + n['width'] for n in before if n['id'] in op['ids'])
        for node in edge:
            if node['id'] in op['ids']:
                node['x'] = target - node['width']
        with self.assertRaises(VerificationError):
            check_scope(before, edge, op)

    def test_selection_minimum_matches_the_native_command(self):
        for kind, minimum in (('align_left', 2), ('distribute_vertical', 3)):
            with self.subTest(kind=kind):
                with self.assertRaises(VerificationError):
                    validate_operation_parameters({'kind': kind, 'ids': ['s1'] * minimum})
        validate_operation_parameters({'kind': 'align_left', 'ids': ['s1', 's2']})
        validate_operation_parameters({'kind': 'distribute_vertical', 'ids': ['s1', 's2', 's3']})

    def test_alignment_requires_native_shapes(self):
        nodes = projection(board())
        for kind in ALIGN_MODES:
            with self.subTest(kind=kind):
                with self.assertRaises(VerificationError):
                    validate_local_operation(nodes, {'kind': kind, 'ids': ['s1', 'line']})


class LayerOrder(unittest.TestCase):
    def order(self, raw):
        return sorted((n['id'] for n in raw['nodes']),
                      key=lambda i: (lookup(raw)[i]['z_index'], i))

    def reorder(self, raw, order):
        after = copy.deepcopy(raw)
        table = lookup(after)
        for position, ident in enumerate(order):
            table[ident]['z_index'] = position
        return after

    def test_four_actions_are_defined(self):
        self.assertEqual(ORDER_ACTIONS, {'bring_to_front': 'BringToFront', 'send_to_back': 'SendToBack',
                                         'bring_forward': 'BringForward', 'send_backward': 'SendBackward'})

    def test_front_and_back_move_only_the_requested_objects(self):
        raw = board()
        order = self.order(raw)
        front = self.reorder(raw, [i for i in order if i != 's1'] + ['s1'])
        op = {'kind': 'bring_to_front', 'ids': ['s1']}
        check_scope(projection(raw), projection(front), op)
        check_raw_preservation(raw, front, op)
        back = self.reorder(raw, ['s1'] + [i for i in order if i != 's1'])
        check_scope(projection(raw), projection(back), {'kind': 'send_to_back', 'ids': ['s1']})
        check_raw_preservation(raw, back, {'kind': 'send_to_back', 'ids': ['s1']})

    def test_single_step_moves_shift_by_one_position(self):
        # Live-board behaviour: BringForward raises the rank (nearer the front);
        # SendBackward lowers it. Each moves exactly one position.
        raw = board()
        order = self.order(raw)
        index = order.index('s2')
        forward = self.reorder(raw, order[:index] + [order[index + 1], 's2'] + order[index + 2:])
        check_scope(projection(raw), projection(forward), {'kind': 'bring_forward', 'ids': ['s2']})
        check_raw_preservation(raw, forward, {'kind': 'bring_forward', 'ids': ['s2']})
        backward = self.reorder(raw, order[:index - 1] + ['s2', order[index - 1]] + order[index + 1:])
        check_scope(projection(raw), projection(backward), {'kind': 'send_backward', 'ids': ['s2']})
        check_raw_preservation(raw, backward, {'kind': 'send_backward', 'ids': ['s2']})

    def test_layer_order_cannot_move_geometry_text_or_bindings(self):
        raw = board()
        order = self.order(raw)
        front = self.reorder(raw, [i for i in order if i != 's1'] + ['s1'])
        op = {'kind': 'bring_to_front', 'ids': ['s1']}
        check_scope(projection(raw), projection(front), op)
        for damage in ('geometry', 'text', 'binding'):
            with self.subTest(damage=damage):
                broken = copy.deepcopy(front)
                if damage == 'geometry':
                    move(broken, 's1', 'x', 40)
                elif damage == 'text':
                    lookup(broken)['s1']['text']['text'] = 'damaged'
                else:
                    lookup(broken)['line']['connector']['start_object']['id'] = 's3'
                with self.assertRaises(VerificationError):
                    check_scope(projection(raw), projection(broken), op)

    def test_unrequested_objects_keep_their_relative_layer_order(self):
        raw = board()
        order = self.order(raw)
        scrambled = self.reorder(raw, list(reversed(order)))
        with self.assertRaises(VerificationError):
            check_raw_preservation(raw, scrambled, {'kind': 'bring_to_front', 'ids': ['s1']})

    def test_layer_targets_must_be_supported_native_objects(self):
        nodes = projection(board())
        validate_local_operation(nodes, {'kind': 'bring_to_front', 'ids': ['s1']})
        validate_local_operation(nodes, {'kind': 'send_to_back', 'ids': ['line']})
        with self.assertRaises(VerificationError):
            validate_local_operation(nodes, {'kind': 'bring_to_front', 'ids': ['missing']})
        for kind in ORDER_ACTIONS:
            with self.subTest(kind=kind):
                with self.assertRaises(VerificationError):
                    validate_operation_parameters({'kind': kind, 'ids': []})


if __name__ == '__main__':
    unittest.main()
