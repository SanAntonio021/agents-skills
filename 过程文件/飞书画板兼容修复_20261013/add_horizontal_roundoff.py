from pathlib import Path
ROOT=Path(r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard')
p=ROOT/'scripts/whiteboard.py';s=p.read_text(encoding='utf-8')
marker='def check_raw_preservation(before, after, op, *, group_evidence=None, arrangement_evidence=None):'
helper='''def bound_text_zero_height_roundoff(ident, left, right, op, evidence):
    """Explain only the observed horizontal straight-line attachment rounding."""
    if (op['kind'] not in ('text', 'caption') or not isinstance(evidence, dict)
            or left.get('type') != 'connector' or left.get('parent_id')
            or left.get('height') != 0 or not finite_number(right.get('height'))
            or not 0 < right['height'] < 1e-5
            or left.get('angle', 0) != 0 or right.get('angle', 0) != 0
            or any(left.get(k) != right.get(k) for k in ('x', 'y', 'width'))):
        return None
    connector = left.get('connector', {})
    if connector.get('shape') != 'straight' or connector.get('turning_points') != []:
        return None
    before = {n['id']: n for n in evidence.get('native_before', [])}
    after = {n['id']: n for n in evidence.get('native_after', [])}
    line_before, line_after = before.get(ident, {}), after.get(ident, {})
    target = before.get(op.get('id'), {})
    bound_ids = [line_before.get(side + '_id') for side in ('start', 'end')]
    if (not all(bound_ids) or len(set(bound_ids)) != 2 or target.get('parent_id')
            or op['kind'] == 'text' and op.get('id') not in bound_ids
            or op['kind'] == 'caption' and op.get('id') != ident
            or any(line_before.get(k) != line_after.get(k) for k in
                   ('kind', 'shape', 'x', 'width', 'start_id', 'end_id', 'start_anchor', 'end_anchor', 'points'))
            or line_before.get('kind') != 'connector' or line_before.get('shape') != 'straight'
            or line_before.get('points') != [] or line_before.get('height') != 0
            or not finite_number(line_after.get('height')) or not 0 < line_after['height'] < 1e-5):
        return None
    for bound in bound_ids:
        a, b = before.get(bound, {}), after.get(bound, {})
        if (a.get('kind') != 'shape' or a.get('parent_id')
                or any(not finite_number(a.get(k)) or a.get(k) != b.get(k) for k in ('x', 'y', 'width', 'height'))):
            return None
    ends_before = evidence.get('native_endpoints_before', {}).get(ident, {})
    ends_after = evidence.get('native_endpoints_after', {}).get(ident, {})
    binding_before = next((r for r in evidence.get('bindings_before', []) if r.get('id') == ident), {})
    binding_after = next((r for r in evidence.get('bindings_after', []) if r.get('id') == ident), {})
    if (set(ends_before) != {'start', 'end'} or set(ends_after) != {'start', 'end'}
            or not all(valid_point(v) for v in [*ends_before.values(), *ends_after.values()])
            or ends_before['start']['y'] != ends_before['end']['y']
            or binding_before.get('valid') is not True or binding_after.get('valid') is not True):
        return None
    maximum = 0
    for side in ('start', 'end'):
        a, b = binding_before.get(side, {}), binding_after.get(side, {})
        if (a.get('valid') is not True or b.get('valid') is not True
                or not all(valid_point(v.get(k)) for v in (a, b) for k in ('actual', 'expected'))
                or a['actual'] != ends_before[side] or b['actual'] != ends_after[side]
                or a['expected'] != b['expected']):
            return None
        for axis in ('x', 'y'):
            difference = abs(ends_before[side][axis] - ends_after[side][axis])
            if difference >= 1e-5 or abs(b['actual'][axis] - b['expected'][axis]) > 1e-10:
                return None
            maximum = max(maximum, difference)
    height = abs(ends_after['start']['y'] - ends_after['end']['y'])
    if (not 0 < height < 1e-5 or abs(height - line_after['height']) > 1e-10
            or abs(height - right['height']) > 1e-10
            or abs(min(p['y'] for p in ends_after.values()) - line_after.get('y', float('inf'))) > 1e-10):
        return None
    return {'id': ident, 'normalization': 'bound_text_horizontal_zero_height_roundoff',
            'before_raw_height': 0, 'after_raw_height': right['height'],
            'maximum_native_endpoint_difference': maximum,
            'native_endpoints_before': ends_before, 'native_endpoints_after': ends_after,
            'expected_attachment_points': {side: binding_after[side]['expected'] for side in ('start', 'end')}}


'''
assert s.count(marker)==1;s=s.replace(marker,helper+marker)
old='    derived_parents.update(e[\'id\'] for e in cache_exceptions)\n'
new=old+'''    horizontal_roundoff = {}
    for ident in a.keys() & b.keys():
        exception = bound_text_zero_height_roundoff(ident, a[ident], b[ident], op, group_evidence)
        if exception:
            horizontal_roundoff[ident] = exception
    cache_exceptions.extend(horizontal_roundoff.values())
'''
assert s.count(old)==1;s=s.replace(old,new)
old="    def strip_parent_bounds(ident, left, right):\n"
new=old+"        if ident in horizontal_roundoff:\n            left.pop('height', None)\n            right.pop('height', None)\n"
assert s.count(old)==1;s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
print('Added exact evidence-backed horizontal attachment roundoff check.')
