"""Manifest compiler contract for native system diagrams."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_nodes import compile_diagram, normalise_manifest


def sample():
    return {
        'diagram': {'title': 'TX chain'},
        'nodes': [
            {'id': 'source', 'type': 'shape', 'shape': 'ellipse', 'x': 20, 'y': 40,
             'width': 160, 'height': 100, 'text': 'IF source\n750 MBaud',
             'ports': [{'id': 'out', 'side': 'right', 'offset': .5}]},
            {'id': 'filter', 'type': 'shape', 'shape': 'parallelogram', 'x': 260, 'y': 40,
             'width': 180, 'height': 100, 'text': 'BPF 98–105 GHz'},
            {'id': 'decision', 'type': 'shape', 'shape': 'diamond', 'x': 520, 'y': 30,
             'width': 160, 'height': 120, 'text': 'locked?'},
            {'id': 'note', 'type': 'text', 'x': 20, 'y': 210, 'width': 300, 'height': 40,
             'text': '标定时换接'},
        ],
        'groups': [{'id': 'tx', 'label': 'TX', 'members': ['source', 'filter']}],
        'connections': [
            {'id': 'c1', 'start_id': 'source', 'end_id': 'filter', 'start_anchor': {'side': 'right'},
             'end_anchor': {'side': 'left'}, 'label': '8× LO'},
            {'id': 'c2', 'start_id': 'filter', 'end_id': 'decision', 'shape': 'right_angled_polyline',
             'border_style': 'dash', 'start_arrow': 'none', 'end_arrow': 'triangle_arrow'},
        ],
    }


class ManifestCompiler(unittest.TestCase):
    def test_all_native_shapes_text_and_bound_connectors(self):
        raw = compile_diagram(sample())
        nodes = {n['id']: n for n in raw['nodes']}
        self.assertEqual([nodes[i]['composite_shape']['type'] for i in ('source', 'filter', 'decision')],
                         ['ellipse', 'parallelogram', 'diamond'])
        self.assertEqual(nodes['note']['type'], 'text_shape')
        self.assertEqual(nodes['source']['text']['text'], 'IF source\n750 MBaud')
        for key in ('c1', 'c2'):
            line = nodes[key]
            self.assertEqual(line['connector']['start_object']['id'], line['connector']['start']['attached_object']['id'])
            self.assertEqual(line['connector']['end_object']['id'], line['connector']['end']['attached_object']['id'])
        self.assertEqual(nodes['c1']['connector']['captions']['data'][0]['text'], '8× LO')
        self.assertEqual(nodes['c2']['connector']['shape'], 'right_angled_polyline')
        self.assertEqual(nodes['c2']['connector']['end']['arrow_style'], 'triangle_arrow')

    def test_port_aliases_are_recorded_without_guessing(self):
        spec = sample()
        spec['nodes'][0]['ports'].append({'id': 'monitor', 'side': 'bottom', 'offset': .25})
        raw, ports, groups = normalise_manifest(spec)
        self.assertEqual(ports['source']['monitor'], {'side': 'bottom', 'offset': .25})
        self.assertTrue(any(n['id'] == 'source' for n in raw))

    def test_groups_are_manifest_metadata_not_fake_raw_nodes(self):
        raw, ports, groups = normalise_manifest(sample())
        self.assertEqual(groups, [{'id': 'tx', 'label': 'TX', 'members': ['source', 'filter']}])
        self.assertFalse(any(n['type'] == 'group' for n in raw))

    def test_invalid_manifest_stops_before_raw(self):
        bad = sample()
        bad['connections'][0]['end_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'same manifest'):
            compile_diagram(bad)
        bad = sample()
        bad['nodes'][0]['ports'][0]['side'] = 'diagonal'
        with self.assertRaisesRegex(ValueError, 'Invalid shape port'):
            compile_diagram(bad)

    def test_connection_can_reference_a_declared_port(self):
        spec = sample()
        spec['nodes'][0]['ports'].append({'id': 'monitor', 'side': 'bottom', 'offset': .25})
        spec['connections'][0]['start_port'] = 'out'
        raw = compile_diagram(spec)
        line = next(n for n in raw['nodes'] if n['id'] == 'c1')
        self.assertEqual(line['connector']['start_object']['snap_to'], 'right')

    def test_connection_unknown_port_rejects_before_raw(self):
        spec = sample()
        spec['connections'][0]['start_port'] = 'not-a-port'
        with self.assertRaisesRegex(ValueError, 'unknown port'):
            compile_diagram(spec)

    def test_manifest_preserves_ports_and_container_intent_separately(self):
        raw, ports, groups = normalise_manifest(sample())
        self.assertEqual(ports['source']['out'], {'side': 'right', 'offset': .5})
        self.assertEqual(groups, [{'id': 'tx', 'label': 'TX', 'members': ['source', 'filter']}])
        self.assertFalse(any(n.get('type') == 'group' for n in raw))

    def test_manifest_rejects_cross_group_duplicate_membership(self):
        spec = sample()
        spec['groups'].append({'id': 'rx', 'members': ['filter']})
        with self.assertRaisesRegex(ValueError, 'only one container group'):
            compile_diagram(spec)

    def test_manifest_connection_requires_same_batch_shapes(self):
        spec = sample()
        spec['connections'][0]['start_id'] = 'old'
        with self.assertRaisesRegex(ValueError, 'same manifest'):
            compile_diagram(spec)

    def test_manifest_supports_reverse_and_orthogonal_connections(self):
        spec = sample()
        spec['connections'][0]['start_anchor'] = {'side': 'bottom', 'offset': .25}
        spec['connections'][0]['end_anchor'] = {'side': 'top', 'offset': .75}
        spec['connections'][0]['shape'] = 'right_angled_polyline'
        raw = compile_diagram(spec)
        connector = next(n for n in raw['nodes'] if n['id'] == 'c1')
        self.assertEqual(connector['connector']['start_object']['snap_to'], 'bottom')
        self.assertEqual(connector['connector']['end_object']['snap_to'], 'top')
        self.assertEqual(connector['connector']['shape'], 'right_angled_polyline')
    def test_legacy_input_still_compiles(self):
        raw = compile_diagram({'shapes': [{'id': 'a', 'x': 0, 'y': 0, 'width': 10, 'height': 10},
                                         {'id': 'b', 'x': 20, 'y': 0, 'width': 10, 'height': 10}],
                               'connectors': [{'id': 'c', 'start_id': 'a', 'end_id': 'b'}]})
        self.assertEqual([n['type'] for n in raw['nodes']], ['composite_shape', 'composite_shape', 'connector'])


if __name__ == '__main__':
    unittest.main()


