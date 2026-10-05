"""Compiler anchor input checks; no CLI, browser or content writes."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_nodes import compile_diagram


class NativeAnchorInput(unittest.TestCase):
    def specification(self):
        return {'shapes': [{'id': 'a', 'x': 0, 'y': 0, 'width': 100, 'height': 80},
                           {'id': 'b', 'x': 200, 'y': 0, 'width': 100, 'height': 80}],
                'connectors': [{'id': 'line', 'start_id': 'a', 'end_id': 'b'}]}

    def test_missing_null_and_empty_object_keep_default_anchors(self):
        expected = compile_diagram(self.specification())
        for side in ('start_anchor', 'end_anchor'):
            for value in (None, {}):
                with self.subTest(side=side, value=value):
                    specification = self.specification()
                    specification['connectors'][0][side] = value
                    self.assertEqual(compile_diagram(specification), expected)

    def test_false_zero_and_wrong_containers_are_not_defaults(self):
        for side in ('start_anchor', 'end_anchor'):
            for value in (False, True, 0, 0.0, [], '', 'right', ['right']):
                with self.subTest(side=side, value=value), self.assertRaises(ValueError):
                    specification = self.specification()
                    specification['connectors'][0][side] = value
                    compile_diagram(specification)

    def test_valid_edge_and_offset_keep_input_and_native_geometry(self):
        specification = self.specification()
        specification['connectors'][0].update(start_anchor={'side': 'bottom', 'offset': 0.25},
                                               end_anchor={'side': 'top', 'offset': 0.75})
        original = copy.deepcopy(specification)
        node = compile_diagram(specification)['nodes'][-1]
        self.assertEqual(specification, original)
        self.assertEqual(node['connector']['start_object'],
                         {'id': 'a', 'position': {'x': 0.25, 'y': 1}, 'snap_to': 'bottom'})
        self.assertEqual(node['connector']['end_object'],
                         {'id': 'b', 'position': {'x': 0.75, 'y': 0}, 'snap_to': 'top'})
        self.assertEqual((node['x'], node['y'], node['width'], node['height']), (25, 0, 250, 80))


if __name__ == '__main__':
    unittest.main()
