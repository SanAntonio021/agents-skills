import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import VerificationError, check_raw_preservation
from test_captions import board, line


class TextConnectorRoundoffTest(unittest.TestCase):
    """Editing a module's text may re-serialize bound connectors as float32."""

    def edited(self):
        before = board()
        after = copy.deepcopy(before)
        next(n for n in after['nodes'] if n['id'] == 'a')['text']['text'] = 'A2'
        return before, after, {'kind': 'text', 'id': 'a', 'text': 'A2'}

    def test_float32_drift_on_bound_connector_is_recorded(self):
        before, after, op = self.edited()
        moved = line(after)
        moved['x'], moved['width'] = 100.00006103515625, 99.99996948242188
        exceptions = check_raw_preservation(before, after, op)
        self.assertEqual([e['normalization'] for e in exceptions], ['text_bound_connector_float32_roundoff'])
        self.assertEqual(exceptions[0]['id'], 'line')

    def test_real_geometry_change_is_still_refused(self):
        before, after, op = self.edited()
        line(after)['x'] = 100.5
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_height_drift_is_not_covered(self):
        before, after, op = self.edited()
        moved = line(after)
        moved['x'], moved['height'] = 100.00006103515625, 0.00001
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_unbound_connector_drift_is_refused(self):
        before, after, op = self.edited()
        line(after, 'other-line')['x'] = 100.00006103515625
        for node in after['nodes'] + before['nodes']:
            if node['id'] == 'other-line':
                for side in ('start', 'end'):
                    node['connector'][side + '_object']['id'] = 'b'
                    node['connector'][side]['attached_object']['id'] = 'b'
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)

    def test_non_geometry_change_on_bound_connector_is_refused(self):
        before, after, op = self.edited()
        moved = line(after)
        moved['x'] = 100.00006103515625
        moved['style']['border_color'] = '#ff0000'
        with self.assertRaises(VerificationError):
            check_raw_preservation(before, after, op)


if __name__ == '__main__':
    unittest.main()
