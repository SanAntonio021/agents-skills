"""Guarded CLI readback and background editor runner (Python standard library)."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
from urllib.parse import urlparse
import uuid


class VerificationError(RuntimeError):
    pass


class NotReady(VerificationError):
    pass


LINE_SHAPES = {'straight', 'polyline', 'curve', 'right_angled_polyline'}
STYLE_FIELDS = {'border_color', 'fill_color', 'text_color', 'border_style', 'border_width'}
CAPTION_PLACEMENTS = {'on_line': 0, 'above_line': 1, 'below_line': 2}


def safe_cli_error(payload):
    """Keep diagnostic fields, never request bodies, context, or credentials."""
    details = []
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in ('code','subtype','type','message','msg','hint') and isinstance(item, (str,int)):
                    text = str(item)
                    text = re.sub(r'https?://\S+', '[URL]', text)
                    text = re.sub(r'(?i)(bearer\s+|(?:access[_-]?token|refresh[_-]?token|secret|password|authorization|cookie)\s*[:=]\s*)[^\s,;]+', r'\1[REDACTED]', text)
                    details.append({key:text[:1000]})
                elif key.lower() in ('error','errors','details'):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(payload)
    return details


def validate_target(request):
    u = urlparse(request['document_url'])
    host = u.hostname or ''
    if u.scheme != 'https' or u.username or u.password or u.port or not any(host == d or host.endswith('.' + d) for d in ('feishu.cn', 'larksuite.com')) or not re.fullmatch(r'/docx/[A-Za-z0-9]+/?', u.path) or u.query or u.fragment:
        raise ValueError('Expected a plain HTTPS Feishu/Lark docx URL')
    if not re.fullmatch(r'[A-Za-z0-9]+', request['whiteboard_token']):
        raise ValueError('Invalid whiteboard token')
    if not isinstance(request.get('operations', []), list):
        raise ValueError('operations must be a list')
    for key in ('block_id', 'section_id'):
        if key in request and not re.fullmatch(r'[A-Za-z0-9]+', request[key]):
            raise ValueError('Invalid document block identifier')


def projection(raw):
    nodes = raw['nodes']
    parents = {child: n['id'] for n in nodes for child in n.get('children', [])}
    result = []
    for n in nodes:
        kind = {'composite_shape': 'shape', 'text_shape': 'text', 'connector': 'connector', 'group': 'group'}.get(n.get('type'), 'other')
        v = dict(id=n['id'], kind=kind, **{k: n.get(k, 0) for k in ('x', 'y', 'width', 'height')})
        v['style'] = {k: value.lower() if k.endswith('_color') else value for k, value in n.get('style', {}).items() if k in STYLE_FIELDS}
        if 'text' in n:
            v.update(text=n['text'].get('text', ''), font_size=n['text'].get('font_size', 0))
            if 'text_color' in n['text']:
                v['style']['text_color'] = n['text']['text_color'].lower()
        if kind == 'shape':
            v['shape'] = n.get('composite_shape', {}).get('type', '')
        if kind == 'connector':
            c = n['connector']
            for side in ('start', 'end'):
                endpoint = c.get(side + '_object') or c.get(side, {}).get('attached_object', {})
                v[side + '_id'] = endpoint.get('id', '')
                if endpoint.get('position'):
                    v[side + '_anchor'] = {k:endpoint[k] for k in ('snap_to','position')}
                v[side + '_arrow'] = c.get(side, {}).get('arrow_style', 'none')
            caption_texts = [t.get('text', '') for t in c.get('captions', {}).get('data', [])]
            if caption_texts and 'text_color' in c['captions']['data'][0]:
                v['style']['text_color'] = c['captions']['data'][0]['text_color'].lower()
            v['points'] = [{'x': n.get('x', 0) + p['x'], 'y': n.get('y', 0) + p['y']}
                           for p in c.get('turning_points', [])]
            v.update(shape=c.get('shape', ''), caption='\n'.join(caption_texts), caption_texts=caption_texts,
                     caption_position=c.get('caption_position', 0.5) if caption_texts else None,
                     caption_position_type=c.get('caption_position_type', 0) if caption_texts else None,
                     caption_auto_direction=c.get('caption_auto_direction', False))
        if kind == 'group':
            v['children'] = sorted(n.get('children', []))
        if n['id'] in parents:
            v['parent_id'] = parents[n['id']]
        result.append(v)
    return sorted(result, key=lambda n: n['id'])


def caption_position_equivalent(a, b):
    if a is None or b is None:
        return a is None and b is None
    return (isinstance(a, (int, float)) and not isinstance(a, bool)
            and isinstance(b, (int, float)) and not isinstance(b, bool)
            and math.isfinite(a) and math.isfinite(b) and abs(a-b) <= 1e-6)


def point_equivalent(a, b):
    return (valid_point(a) and valid_point(b)
            and all(abs(a[k] - b[k]) <= 1e-3 for k in ('x', 'y')))


def points_equivalent(a, b):
    return (isinstance(a, list) and isinstance(b, list) and len(a) == len(b)
            and all(point_equivalent(x, y) for x, y in zip(a, b)))


def equivalent(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return math.isfinite(a) and math.isfinite(b) and abs(a-b) < 0.02
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(
            caption_position_equivalent(a[k], b[k]) if k == 'caption_position'
            else points_equivalent(a[k], b[k]) if k == 'points' else equivalent(a[k], b[k])
            for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    return a == b


def differences(before, after):
    a, b = ({n['id']: n for n in nodes} for nodes in (before, after))
    return dict(added=sorted(b.keys()-a.keys()), removed=sorted(a.keys()-b.keys()), changed=sorted(k for k in a.keys() & b.keys() if not equivalent(a[k], b[k])))


def check_scope(before, after, op, *, from_raw=False):
    delta = differences(before, after)
    ids = set(op.get('ids', [])) | ({op['id']} if 'id' in op else set())
    lookup = {n['id']: n for n in before}
    for ident in list(ids):
        ids.update(lookup.get(ident, {}).get('children', []))
    allowed = ids | {n['id'] for n in before if n.get('start_id') in ids or n.get('end_id') in ids}
    if op['kind'] in ('caption', 'caption_position', 'style', 'reconnect', 'line_type', 'path'):
        if len(lookup) != len(before) or len({n['id'] for n in after}) != len(after):
            raise VerificationError('Local edit requires unique object IDs')
        allowed = {op.get('id')}
    if op['kind'] == 'connect':
        if len(delta['added']) != 1 or delta['removed'] or delta['changed']:
            raise VerificationError('Connect must add exactly one line and preserve all existing objects')
    elif op['kind'] == 'group':
        allowed.update(delta['added'])
        if len(delta['added']) != 1 or delta['removed']:
            raise VerificationError('Unexpected group membership change')
    elif op['kind'] == 'ungroup':
        if delta['added'] or set(delta['removed']) != {op['id']}:
            raise VerificationError('Unexpected ungroup membership change')
    elif op['kind'] == 'delete':
        if delta['added'] or set(delta['removed']) != set(op['delete_ids']):
            raise VerificationError('Deletion did not match the explicit deletion set')
    elif delta['added'] or delta['removed']:
        raise VerificationError('Unexpected object creation/removal')
    if set(delta['changed']) - allowed:
        raise VerificationError('An unrelated object changed')
    check_intent(before, after, op, delta, from_raw=from_raw)
    return delta


def validate_caption_operation(node, op):
    if not node or node.get('kind') != 'connector':
        raise VerificationError('Caption operation requires an existing connector')
    texts = node.get('caption_texts')
    if not isinstance(texts, list) or any(not isinstance(t, str) for t in texts):
        raise VerificationError('Connector caption data must contain strings')
    if len(texts) > 1:
        raise VerificationError('Multiple connector captions cannot be safely edited by the native editor')
    if op['kind'] == 'caption':
        if not isinstance(op.get('text'), str):
            raise VerificationError('Caption text must be a string')
    else:
        position = op.get('position')
        if len(texts) != 1 or type(node.get('caption_position_type')) is not int or node['caption_position_type'] not in CAPTION_PLACEMENTS.values():
            raise VerificationError('Caption position requires one caption with a supported position type')
        if 'position' not in op and 'placement' not in op or 'point' in op:
            raise VerificationError('Caption position requires position or placement')
        if 'position' in op and (not isinstance(position, (int, float)) or isinstance(position, bool)
                                or not math.isfinite(position) or not 0 <= position <= 1):
            raise VerificationError('Caption position must be a finite number in [0, 1]')
        if 'placement' in op and (not isinstance(op['placement'], str) or op['placement'] not in CAPTION_PLACEMENTS):
            raise VerificationError('Unsupported caption placement')


def validate_style(style):
    if not isinstance(style, dict) or not style or set(style) - STYLE_FIELDS:
        raise VerificationError('Style must specify supported nonempty fields')
    for key, value in style.items():
        if key.endswith('_color') and (not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value)):
            raise VerificationError('Style colors must be #RRGGBB')
        if key == 'border_style' and value not in ('none', 'solid', 'dash', 'dot'):
            raise VerificationError('Unsupported border style')
        if key == 'border_width' and value not in ('extra_narrow', 'narrow', 'medium', 'bold'):
            raise VerificationError('Unsupported border width')


def finite_number(value, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (not positive or value > 0))


def valid_point(point):
    return isinstance(point, dict) and set(point) == {'x', 'y'} and all(finite_number(point[k]) for k in point)


def validate_local_operation(nodes, op):
    """Reject unsupported parameters before invoking a mutating editor command."""
    lookup = {n['id']: n for n in nodes}
    if len(lookup) != len(nodes):
        raise VerificationError('Local edit requires unique object IDs')
    kind = op['kind']
    node = lookup.get(op.get('id'))
    if kind in ('caption', 'caption_position'):
        validate_caption_operation(node, op)
    elif kind in ('text', 'font', 'resize'):
        if not node or node.get('kind') not in ('shape', 'text'):
            raise VerificationError('Text or size edit requires a native shape or text shape')
        if kind == 'text' and not isinstance(op.get('text'), str):
            raise VerificationError('Text must be a string')
        if kind == 'font' and not finite_number(op.get('font_size'), True):
            raise VerificationError('Font size must be positive and finite')
        if kind == 'resize' and not all(finite_number(op.get(k), True) for k in ('width', 'height')):
            raise VerificationError('Dimensions must be positive and finite')
    elif kind == 'style':
        validate_style(op.get('style'))
        if not node or node.get('kind') not in ('shape', 'text', 'connector'):
            raise VerificationError('Style edit requires a native shape, text shape or connector')
        if node['kind'] == 'connector' and ('fill_color' in op['style'] or
                'text_color' in op['style'] and not node.get('caption_texts')):
            raise VerificationError('Connector has no fill or no caption to recolor')
    elif kind in ('line_type', 'path', 'reconnect'):
        if not node or node.get('kind') != 'connector':
            raise VerificationError('Line edit requires an existing connector')
        if kind == 'line_type' and (not isinstance(op.get('shape'), str) or op['shape'] not in LINE_SHAPES):
            raise VerificationError('Unsupported line type')
        if kind == 'path':
            points = op.get('points')
            if not isinstance(points, list) or not all(valid_point(p) for p in points):
                raise VerificationError('Path points must be finite canvas x/y coordinates')
            if node.get('shape') not in ('polyline', 'right_angled_polyline', 'curve'):
                raise VerificationError('Path requires a polyline or curve')
            if node['shape'] == 'curve' and len(points) != 2:
                raise VerificationError('A curve path requires two control points')
            if node['shape'] == 'curve' and not all(node.get(side + '_id') for side in ('start', 'end')):
                raise VerificationError('Curve control edits require both endpoints to be bound')
        if kind == 'reconnect':
            sides = [side for side in ('start', 'end') if side + '_id' in op]
            if not sides:
                raise VerificationError('Reconnect requires a start_id or end_id')
            for side in sides:
                target = lookup.get(op[side + '_id'])
                if not target or target.get('kind') != 'shape':
                    raise VerificationError('Reconnect endpoint requires an existing native shape')
    elif kind == 'connect':
        for side in ('start', 'end'):
            target = lookup.get(op.get(side + '_id'))
            if not target or target.get('kind') != 'shape':
                raise VerificationError('Connection endpoint requires an existing native shape')
        if op['start_id'] == op['end_id']:
            raise VerificationError('Self connection is not supported')
        if op.get('template_id') and lookup.get(op['template_id'], {}).get('kind') != 'connector':
            raise VerificationError('Connection template requires an existing connector')


def check_intent(before, after, op, delta=None, *, from_raw=False):
    """Verify requested outcomes, rather than treating absence of damage as success."""
    a, b = ({n['id']: n for n in nodes} for nodes in (before, after))
    kind = op['kind']
    ident = op.get('id')
    def require(condition):
        if not condition:
            raise VerificationError('Requested operation postcondition failed: ' + kind)
    for field, operation, parameter in [('text','text','text'), ('shape','line_type','shape')]:
        if kind == operation:
            require(ident in b and equivalent(b[ident].get(field), op[parameter]))
    if kind == 'text':
        require(isinstance(op.get('text'), str))
    if kind == 'font':
        require(finite_number(op.get('font_size'), True))
        require(ident in b and caption_position_equivalent(b[ident].get('font_size'), op['font_size']))
    if kind in ('text', 'font'):
        validate_local_operation(before, op)
        require(ident in b)
        old, new = a[ident], b[ident]
        editable = {'text' if kind == 'text' else 'font_size'}
        if old['kind'] == 'text':
            editable.add('height')
            require(finite_number(new.get('height'), True))
        require(equivalent({k:v for k,v in old.items() if k not in editable},
                           {k:v for k,v in new.items() if k not in editable}))
        for field in {'x', 'y', 'width', 'height'} - editable:
            require(finite_number(old.get(field)) and finite_number(new.get(field))
                    and abs(old[field] - new[field]) <= 1e-3)
        if kind == 'text':
            require(caption_position_equivalent(old.get('font_size'), new.get('font_size')))
    if kind == 'line_type':
        require(isinstance(op.get('shape'), str) and op['shape'] in LINE_SHAPES and a.get(ident, {}).get('kind') == 'connector')
        require(all(equivalent(b[ident].get(k), a[ident].get(k)) for k in ('start_id', 'end_id', 'start_anchor', 'end_anchor')))
    if kind == 'path':
        validate_local_operation(before, op)
        require(ident in b and b[ident].get('kind') == 'connector')
        # CLI raw omits the curve's endpoint control vectors. Native snapshots
        # must still verify them, including after closing and reopening the page.
        if not (from_raw and a[ident].get('shape') == 'curve'):
            require(points_equivalent(b[ident].get('points'), op['points']))
        editable = {'points', 'x', 'y', 'width', 'height'}
        require(equivalent({k:v for k,v in a[ident].items() if k not in editable},
                           {k:v for k,v in b[ident].items() if k not in editable}))
    if kind in ('caption', 'caption_position'):
        validate_caption_operation(a.get(ident), op)
        require(ident in b and b[ident].get('kind') == 'connector')
        old, new = a[ident], b[ident]
        editable = set()
        if kind == 'caption':
            wanted = [op['text']] if op['text'] else []
            require(new.get('caption_texts') == wanted and new.get('caption') == '\n'.join(wanted))
            editable = {'caption', 'caption_texts'}
            if not wanted:
                require(new.get('caption_position') is None and new.get('caption_position_type') is None)
                editable.update(('caption_position', 'caption_position_type'))
            elif not old['caption_texts']:
                require(caption_position_equivalent(new.get('caption_position'), 0.5)
                        and type(new.get('caption_position_type')) is int and new['caption_position_type'] == 0)
                editable.update(('caption_position', 'caption_position_type'))
        else:
            require(new.get('caption_texts') == old['caption_texts'])
            if 'position' in op:
                require(caption_position_equivalent(new.get('caption_position'), op['position']))
                editable.add('caption_position')
            if 'placement' in op:
                require(type(new.get('caption_position_type')) is int
                        and new['caption_position_type'] == CAPTION_PLACEMENTS[op['placement']])
                editable.add('caption_position_type')
        old_rest = {k:v for k,v in old.items() if k not in editable}
        new_rest = {k:v for k,v in new.items() if k not in editable}
        if kind == 'caption' and (not wanted or not old['caption_texts']):
            old_rest['style'] = {k:v for k,v in old.get('style', {}).items() if k != 'text_color'}
            new_rest['style'] = {k:v for k,v in new.get('style', {}).items() if k != 'text_color'}
        require(equivalent(old_rest, new_rest))
    if kind == 'resize':
        require(all(finite_number(op.get(k), True) for k in ('width', 'height')))
        require(all(finite_number(b[ident].get(k)) and abs(b[ident][k] - op[k]) <= 1e-3 for k in ('width', 'height')))
        require(all(finite_number(b[ident].get(k)) and finite_number(a[ident].get(k))
                    and abs(b[ident][k] - a[ident][k]) <= 1e-3 for k in ('x', 'y')))
    if kind == 'move':
        for node_id in op['ids']:
            require(equivalent(b[node_id]['x'], a[node_id]['x'] + op['dx']) and equivalent(b[node_id]['y'], a[node_id]['y'] + op['dy']))
    if kind == 'arrow':
        require(b[ident]['start_arrow'] == op['start'] and b[ident]['end_arrow'] == op['end'])
    if kind == 'style':
        validate_style(op.get('style'))
        require(ident in a and ident in b)
        require(all(b[ident]['style'].get(k) == (v.lower() if k.endswith('_color') else v) for k,v in op['style'].items()))
    if kind == 'reconnect':
        require(ident in a and ident in b and a[ident].get('kind') == 'connector' and b[ident].get('kind') == 'connector')
        require(any(side + '_id' in op for side in ('start', 'end')))
        for side in ('start', 'end'):
            field = side + '_id'
            require(b[ident].get(field) == op.get(field, a[ident].get(field)))
            if field in op and not a[ident].get(field):
                wanted_anchor = {'snap_to': 'right' if side == 'start' else 'left',
                                 'position': {'x': 1 if side == 'start' else 0, 'y': 0.5}}
                require(equivalent(b[ident].get(side + '_anchor'), wanted_anchor))
            else:
                require(equivalent(b[ident].get(side + '_anchor'), a[ident].get(side + '_anchor')))
    if kind == 'anchors':
        require(all(equivalent(b[ident].get(side+'_anchor'),op[side]) for side in ('start','end') if side in op))
        require(all(b[ident].get(side+'_id') == a[ident].get(side+'_id') for side in ('start','end')))
    if kind == 'group':
        added = set(b) - set(a)
        require(len(added) == 1)
        group = b[next(iter(added))]
        require(group['kind'] == 'group' and set(group.get('children', [])) == set(op['ids']))
        require(all(b[i].get('parent_id') == group['id'] for i in op['ids']))
    if kind == 'connect':
        added = set(b) - set(a)
        require(len(added) == 1)
        line = b[next(iter(added))]
        require(line['kind'] == 'connector' and line['start_id'] == op['start_id'] and line['end_id'] == op['end_id'])
        if op.get('template_id'):
            template = a.get(op['template_id'])
            require(template is not None and template.get('kind') == 'connector')
            for field in ('style', 'shape', 'start_arrow', 'end_arrow', 'caption', 'caption_texts',
                          'caption_position', 'caption_position_type', 'caption_auto_direction'):
                if field in template:
                    require(equivalent(line.get(field), template[field]))
    if kind == 'ungroup':
        require(ident not in b and all(i in b and not b[i].get('parent_id') for i in a[ident].get('children', [])))
    if kind == 'align_top':
        top = min(a[i]['y'] for i in op['ids'])
        require(all(equivalent(b[i]['y'], top) for i in op['ids']))
    if kind == 'distribute_horizontal':
        nodes = sorted((b[i] for i in op['ids']), key=lambda n: n['x'])
        gaps = [right['x'] - left['x'] - left['width'] for left, right in zip(nodes, nodes[1:])]
        require(len(gaps) >= 2 and all(equivalent(gap, gaps[0]) for gap in gaps[1:]))
    if kind == 'delete':
        require(set(a) - set(b) == set(op['delete_ids']))


def reject_nested_groups(nodes, op):
    lookup = {n['id']: n for n in nodes}
    ids = op.get('ids', []) or ([op['id']] if op.get('id') else [])
    for ident in ids:
        n = lookup.get(ident, {})
        if n.get('parent_id'):
            raise VerificationError('Operate on the top-level group or ungroup first')
        if n.get('children') and any(lookup.get(child, {}).get('children') for child in n['children']):
            raise VerificationError('Nested group operations are not supported')
        if op['kind'] == 'group' and n.get('children'):
            raise VerificationError('Creating nested groups is not supported')


def check_raw_preservation(before, after, op):
    """Compare all raw properties, exempting only operation-owned fields."""
    import copy
    a, b = ({n['id']: n for n in raw['nodes']} for raw in (before, after))
    if op['kind'] in ('caption', 'caption_position'):
        if a.keys() != b.keys() or len(a) != len(before['nodes']) or len(b) != len(after['nodes']):
            raise VerificationError('Caption operation changed the object ID set or duplicated an ID')
        check_intent(projection(before), projection(after), op)
        target = op['id']
        for ident in a:
            left, right = copy.deepcopy(a[ident]), copy.deepcopy(b[ident])
            if ident == target:
                lc, rc = left['connector'], right['connector']
                if op['kind'] == 'caption_position':
                    for field, parameter in (('caption_position', 'position'), ('caption_position_type', 'placement')):
                        if parameter in op:
                            lc.pop(field, None)
                            rc.pop(field, None)
                elif not op['text']:
                    for field in ('captions', 'caption_position', 'caption_position_type'):
                        if field in rc:
                            raise VerificationError('Clearing a caption must remove its caption and position fields')
                        lc.pop(field, None)
                elif lc.get('captions', {}).get('data'):
                    lc['captions']['data'][0].pop('text', None)
                    rc['captions']['data'][0].pop('text', None)
                else:
                    for field in ('captions', 'caption_position', 'caption_position_type'):
                        if field != 'captions' and field in lc and lc[field] != rc.get(field):
                            raise VerificationError('Adding a caption changed an existing position field')
                        lc.pop(field, None)
                        rc.pop(field, None)
            # Caption edits do not move, restyle or restack any existing object.
            if json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
                raise VerificationError('Unexpected raw property change on object ' + ident)
        return []
    if op['kind'] in ('style', 'reconnect', 'line_type', 'path', 'connect'):
        if len(a) != len(before['nodes']) or len(b) != len(after['nodes']):
            raise VerificationError('Local edit requires unique object IDs')
        check_scope(projection(before), projection(after), op, from_raw=True)
        if op['kind'] != 'connect' and a.keys() != b.keys():
            raise VerificationError('Local edit changed the object ID set')
        target = op.get('id')
        for ident in a:
            left, right = copy.deepcopy(a[ident]), copy.deepcopy(b[ident])
            if ident == target:
                if op['kind'] == 'style':
                    for key in op['style']:
                        if key == 'text_color':
                            if left['type'] == 'connector':
                                old_text = left['connector'].get('captions', {}).get('data', [])
                                new_text = right['connector'].get('captions', {}).get('data', [])
                                if not old_text or len(old_text) != len(new_text):
                                    raise VerificationError('Text color requires preserving existing caption entries')
                                old_text, new_text = old_text[0], new_text[0]
                            else:
                                old_text, new_text = left.get('text', {}), right.get('text', {})
                            if (type(old_text.get('text_color_type')) is int and old_text['text_color_type'] == 0
                                    and type(new_text.get('text_color_type')) is int and new_text['text_color_type'] == 1
                                    and 'theme_text_color_code' not in new_text):
                                old_text.pop('theme_text_color_code', None)
                            for text in (old_text, new_text):
                                text.pop('text_color', None)
                                text.pop('text_color_type', None)
                        else:
                            for node in (left, right):
                                node.get('style', {}).pop(key, None)
                                if key.endswith('_color'):
                                    node.get('style', {}).pop(key + '_type', None)
                    for node in (left, right):
                        if node.get('style') == {}:
                            node.pop('style')
                else:
                    for node in (left, right):
                        c = node['connector']
                        if op['kind'] == 'reconnect':
                            for side in ('start', 'end'):
                                if side + '_id' in op:
                                    old_endpoint = (a[ident]['connector'].get(side + '_object') or
                                                    a[ident]['connector'].get(side, {}).get('attached_object', {}))
                                    if old_endpoint.get('id'):
                                        c.get(side + '_object', {}).pop('id', None)
                                        c.get(side, {}).get('attached_object', {}).pop('id', None)
                                    else:
                                        c.pop(side + '_object', None)
                                        c.get(side, {}).pop('attached_object', None)
                                        c.get(side, {}).pop('position', None)
                        if op['kind'] == 'line_type':
                            c.pop('shape', None)
                        c.pop('turning_points', None)
                        for field in ('x', 'y', 'width', 'height'):
                            node.pop(field, None)
            if json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
                raise VerificationError('Unexpected raw property change on object ' + ident)
        return []
    ids = set(op.get('ids', [])) | ({op['id']} if 'id' in op else set())
    for ident in list(ids):
        ids.update(a.get(ident, {}).get('children', []))
    kind = op['kind']
    exceptions = []
    def strip(node, path):
        current = node
        for key in path[:-1]:
            current = current.get(key, {})
        current.pop(path[-1], None)
    for ident in a.keys() & b.keys():
        left, right = copy.deepcopy(a[ident]), copy.deepcopy(b[ident])
        paths = [('z_index',)]
        if kind == 'undo' and 'locked' not in left and right.get('locked') is False:
            paths.append(('locked',))
            exceptions.append({'id':ident, 'normalization':'undo_missing_locked_to_false'})
        c = a[ident].get('connector', {})
        connected = any((c.get(side + '_object') or c.get(side, {}).get('attached_object', {})).get('id') in ids for side in ('start', 'end'))
        geometry = ident in ids and kind in ('move','resize','align_top','distribute_horizontal','group','ungroup') or connected and kind in ('move','resize','align_top','distribute_horizontal','group','ungroup')
        if geometry:
            paths += [(k,) for k in ('x','y','width','height')]
            if c:
                paths += [('connector','turning_points')]
        if ident in ids:
            if kind in ('text', 'font') and left.get('type') == 'text_shape':
                if not finite_number(right.get('height'), True):
                    raise VerificationError('Native text height must stay positive and finite')
                paths.append(('height',))
            if kind == 'anchors':
                paths += [('connector',side+'_object',k) for side in ('start','end') if side in op for k in ('position','snap_to')]
                paths += [('connector',side,'attached_object',k) for side in ('start','end') if side in op for k in ('position','snap_to')]
                paths += [('connector','turning_points')] + [(k,) for k in ('x','y','width','height')]
            paths += {'text':[('text','text')], 'font':[('text','font_size')],
                      'arrow':[('connector','start','arrow_style'),('connector','end','arrow_style')],
                      'group':[('parent_id',)], 'ungroup':[('parent_id',)]}.get(kind, [])
        # The editor canonicalizes a legacy one-pixel straight horizontal line.
        if c.get('shape') == 'straight' and left.get('height') == 1 and right.get('height') == 0 and left.get('x') == right.get('x') and left.get('y') == right.get('y') and left.get('width') == right.get('width'):
            paths.append(('height',))
            exceptions.append({'id':ident, 'normalization':'horizontal_straight_height_1_to_0'})
        for path in paths:
            strip(left, path)
            strip(right, path)
        preserved = (json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
                     if kind in ('text', 'font', 'resize') else equivalent(left, right))
        if not preserved:
            raise VerificationError('Unexpected raw property change on object ' + ident)
    # Absolute z indexes may be renumbered, but unrelated objects keep their order.
    untouched = (a.keys() & b.keys()) - ids
    order = lambda lookup: sorted(untouched, key=lambda i:(lookup[i].get('z_index',0), i))
    if order(a) != order(b):
        raise VerificationError('Unrelated object stacking order changed')
    return exceptions


def match_append(before, after, intended):
    """Resolve server-assigned IDs only when topology and geometry match uniquely."""
    old = {n['id']: n for n in before}
    current = {n['id']: n for n in after}
    if any(k not in current or not equivalent(v, current[k]) for k, v in old.items()):
        raise VerificationError('Append changed an existing object')
    added = {k: v for k, v in current.items() if k not in old}
    if len(added) != len(intended):
        raise VerificationError('Append object count has not converged')
    mapping = {ident:ident for ident in old}
    for kind in ('shape', 'text', 'connector'):
        for node in [n for n in intended if n['kind'] == kind]:
            wanted = {k: v for k, v in node.items() if k != 'id'}
            if kind == 'connector':
                for side in ('start', 'end'):
                    field = side + '_id'
                    if wanted[field]:
                        wanted[field] = mapping[wanted[field]]
            candidates = [ident for ident, obj in added.items() if equivalent(wanted, {k: v for k, v in obj.items() if k != 'id'})]
            if len(candidates) != 1:
                raise VerificationError('Append ID mapping is missing or ambiguous')
            mapping[node['id']] = candidates[0]
            del added[candidates[0]]
    if added:
        raise VerificationError('Unexpected appended object')
    return {ident:actual for ident,actual in mapping.items() if ident not in old}


class Runner:
    def __init__(self, request, output, proxy_url, timeout=45):
        validate_target(request)
        self.request, self.output, self.timeout = request, Path(output), timeout
        self.output.mkdir(parents=True, exist_ok=False)
        u = urlparse(proxy_url)
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
            raise ValueError('Proxy must be an existing loopback HTTP service')
        self.proxy = proxy_url.rstrip('/')
        self.token = self.task = self.tab = None
        self.uncertain = False
        self.index = 0
        self.report = {'status': 'running', 'steps': []}
        self.cli = shutil.which('lark-cli.exe') or shutil.which('lark-cli')
        if self.cli and Path(self.cli).suffix.lower() != '.exe' and __import__('os').name == 'nt':
            binary = Path(self.cli).parent / 'node_modules' / '@larksuite' / 'cli' / 'bin' / 'lark-cli.exe'
            if not binary.is_file():
                raise ValueError('Native lark-cli.exe not found next to the npm launcher')
            self.cli = str(binary)
        if not self.cli:
            raise ValueError('lark-cli is not installed')
        self.adapter = Path(__file__).with_name('editor.js').read_text(encoding='utf-8')

    def write(self, name, data):
        (self.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def command(self, args):
        result = subprocess.run([self.cli, *args], cwd=self.output, capture_output=True, text=True, encoding='utf-8', timeout=60, shell=False)
        try:
            payload = json.loads(result.stdout)
        except (ValueError, TypeError):
            try:
                payload = json.loads(result.stderr)
            except (ValueError, TypeError):
                raise VerificationError('CLI did not return JSON; inspect local CLI authentication') from None
        if result.returncode or payload.get('ok') is not True:
            details = safe_cli_error(payload)
            self.write(f'cli-error-{self.index:03d}.json', {'exit_code':result.returncode,'details':details})
            if '2890007' in json.dumps(payload):
                raise NotReady('Whiteboard export is not ready')
            raise VerificationError('CLI operation failed; no automatic write retry: ' + json.dumps(details, ensure_ascii=False))
        return payload

    def export(self):
        self.index += 1
        name = f'raw-{self.index:03d}.json'
        response = self.command(['whiteboard', '+export', '--whiteboard-token', self.request['whiteboard_token'], '--output-type', 'raw', '--output', name, '--as', 'user'])
        if not (self.output / name).exists() and response.get('data', {}).get('msg') == 'whiteboard is empty':
            self.write(name, {'nodes':[]})
        raw = json.loads((self.output / name).read_text(encoding='utf-8-sig'))
        return raw, name

    def call(self, path, data=None, auth=True):
        headers = {'Content-Type': 'application/json', 'Idempotency-Key': str(uuid.uuid4())}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.token
        req = urllib.request.Request(self.proxy + path, headers=headers, data=None if data is None else json.dumps(data).encode())
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)

    def editor(self, operation, expected=None):
        request = {k: self.request[k] for k in ('document_url', 'whiteboard_token')}
        request.update(operation=operation, expected=expected)
        expression = '(()=>{try{return (' + self.adapter.rstrip().rstrip(';') + ')(' + json.dumps(request, ensure_ascii=True) + ')}catch(e){return {adapter_error:String(e.message)}}})()'
        response = self.call('/v2/tabs/' + self.tab + '/eval', {'expression': expression})
        value = response.get('value')
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict) and value.get('adapter_error'):
            raise VerificationError('Editor: ' + value['adapter_error'])
        if not isinstance(value, dict) or value.get('error') or value.get('ok') is False:
            raise VerificationError('Editor rejected operation or returned an invalid response')
        return value

    def settle(self, expected, expected_alpha=None, minimum_stable_seconds=0, expected_endpoints=None):
        deadline = time.monotonic() + self.timeout
        stable_since = None
        while time.monotonic() < deadline:
            current = self.editor({'kind': 'inspect'})
            if not equivalent(current['nodes'], expected):
                raise VerificationError('Page changed during save verification')
            if expected_alpha is not None and not self.alpha_equivalent(current.get('render_alpha'), expected_alpha):
                raise VerificationError('Rendering alpha changed during save verification')
            if expected_endpoints is not None and not equivalent(current.get('line_endpoints'), expected_endpoints):
                raise VerificationError('Native line endpoints changed during save verification')
            if current.get('seq') == current.get('savedSeq') and current.get('seq') is not None:
                try:
                    raw, name = self.export()
                    if self.server_equivalent(projection(raw), expected):
                        if stable_since is None:
                            stable_since = time.monotonic()
                        if time.monotonic() - stable_since >= minimum_stable_seconds:
                            return raw, name
                    else:
                        stable_since = None
                except NotReady:
                    pass
            time.sleep(1)
        raise VerificationError('Save/readback did not converge; write was not retried')

    @staticmethod
    def server_equivalent(raw_nodes, page_nodes):
        # CLI raw omits the two Bezier controls; do not invent them from a box.
        # Edited curves also require a fresh-page native readback below.
        left, right = copy.deepcopy(raw_nodes), copy.deepcopy(page_nodes)
        for nodes in (left, right):
            for node in nodes:
                if node.get('kind') == 'connector' and node.get('shape') == 'curve':
                    node.pop('points', None)
        return equivalent(left, right)

    def reopen_verified(self, saved_raw, expected, expected_alpha=None, expected_endpoints=None):
        self.call('/v2/tasks/' + self.task + '/complete', {'keep':False})
        self.token = self.task = self.tab = None
        self.open_page()
        state = self.hydrate(saved_raw)
        if not equivalent(state['nodes'], expected):
            self.write('reopen-mismatch.json', state)
            raise VerificationError('Fresh-page native readback differs from the saved edit')
        if expected_alpha is not None and not self.alpha_equivalent(state.get('render_alpha'), expected_alpha):
            self.write('reopen-alpha-mismatch.json', state)
            raise VerificationError('Fresh-page rendering alpha differs from the saved edit')
        if expected_endpoints is not None and not equivalent(state.get('line_endpoints'), expected_endpoints):
            self.write('reopen-endpoints-mismatch.json', state)
            raise VerificationError('Fresh-page native line endpoints differ from the saved state')
        self.editor({'kind':'enter'})
        return state

    @staticmethod
    def alpha_equivalent(left, right):
        if not isinstance(left, dict) or not isinstance(right, dict) or left.keys()!=right.keys():
            return False
        for ident in left:
            if left[ident].keys()!=right[ident].keys():
                return False
            if any(not math.isclose(left[ident][component], right[ident][component], rel_tol=0, abs_tol=1e-6)
                   for component in left[ident]):
                return False
        return True

    @staticmethod
    def verify_render_alpha(before, after, op):
        left, right = before.get('render_alpha'), after.get('render_alpha')
        if left is None or right is None:
            raise VerificationError('Native rendering alpha evidence is missing')
        for state, values in ((before,left),(after,right)):
            if not isinstance(values,dict) or set(values)!={n['id'] for n in state.get('nodes',[])}:
                raise VerificationError('Native rendering alpha does not cover the full object set')
        owned = {k.removesuffix('_color') for k in op.get('style', {}) if k.endswith('_color')} if op['kind']=='style' else set()
        if any(right.get(op.get('id'),{}).get(component)!=1 for component in owned):
            raise VerificationError('Requested color alpha is missing or transparent')
        for ident in left.keys() & right.keys():
            for component in left[ident].keys() | right[ident].keys():
                if ident == op.get('id') and component in owned:
                    if right[ident].get(component) != 1:
                        raise VerificationError('Requested color became transparent')
                elif ident == op.get('id') and op['kind']=='caption' and component=='text':
                    if component not in left[ident] or component not in right[ident]:
                        continue
                    if not math.isclose(left[ident][component], right[ident][component], rel_tol=0, abs_tol=1e-6):
                        raise VerificationError('Caption edit changed text alpha')
                elif not Runner.alpha_equivalent({ident:{component:left[ident][component]}} if component in left[ident] else {ident:{}},
                                                 {ident:{component:right[ident][component]}} if component in right[ident] else {ident:{}}):
                    raise VerificationError('Unrequested rendering alpha changed on object ' + ident)
        if op['kind']=='connect':
            added = right.keys() - left.keys()
            for ident in added:
                if op.get('template_id'):
                    if not Runner.alpha_equivalent({ident:right[ident]}, {ident:left[op['template_id']]}):
                        raise VerificationError('Connection changed template rendering alpha')
                elif right[ident].get('border') != 1:
                    raise VerificationError('First connection is transparent')

    def open_page(self):
        session = self.call('/v2/tasks', {}, auth=False)
        self.token, self.task = session['taskToken'], session['taskId']
        target = self.call('/v2/tabs', {'url': self.request['document_url'], 'background': True})
        self.tab = target['targetId']
        base = '/v2/tabs/' + self.tab
        if self.request.get('section_id'):
            # Click only an actual document-outline link observed in this page.
            selector = 'a[href="#' + self.request['section_id'] + '"]'
            self.call(base + '/wait', {'selector': selector, 'timeoutMs': 15000})
            self.call(base + '/click', {'selector': selector})
        selector = '.whiteboard-canvas-container'
        if self.request.get('block_id'):
            block = '[data-record-id="' + self.request['block_id'] + '"]'
            self.call(base + '/wait', {'selector': block, 'timeoutMs': 15000})
            self.call(base + '/eval', {'expression': 'document.querySelector(' + json.dumps(block) + ').scrollIntoView({block:"center"})'})
            selector = block + ' .whiteboard-canvas-container'
        self.call(base + '/wait', {'selector': selector, 'timeoutMs': 15000})

    def hydrate(self, raw):
        if any(len(n.get('connector', {}).get('captions', {}).get('data', [])) > 1 for n in raw['nodes']):
            raise VerificationError('Native editor exposes only the first imported caption; use raw read-only inspection to preserve additional text')
        deadline = time.monotonic() + min(self.timeout, 20)
        attempt = 0
        while time.monotonic() < deadline:
            state = self.editor({'kind':'inspect'})
            attempt += 1
            self.write(f'prewrite-browser-{self.index:03d}-{attempt:03d}.json', state)
            try:
                latest, name = self.export()
            except NotReady:
                time.sleep(1)
                continue
            if not equivalent(projection(latest), projection(raw)):
                raise VerificationError('Server changed while loading the target; reread before submitting edits')
            if self.server_equivalent(projection(latest), state['nodes']) and state.get('seq') == state.get('savedSeq'):
                return state
            time.sleep(1)
        raise VerificationError('Document board and CLI snapshot did not converge before writing; inspect prewrite-browser evidence')

    def run(self):
        raw, name = self.export()
        self.report['initial_raw'] = name
        self.open_page()
        self.hydrate(raw)
        if self.request.get('operations'):
            self.editor({'kind': 'enter'})
            self.hydrate(raw)
        previous_delete = None
        for op in [None, *self.request.get('operations', [])]:
            state = self.editor({'kind': 'inspect'})
            raw, name = self.settle(state['nodes'], state['render_alpha'])
            if op is None:
                self.report['initial_nodes'] = state['nodes']
                continue
            actual = dict(op)
            reject_nested_groups(state['nodes'], op)
            validate_local_operation(state['nodes'], op)
            if op['kind'] == 'undo':
                if previous_delete is None:
                    raise VerificationError('Undo is only allowed immediately after this session\'s delete')
                actual['undo_count'] = previous_delete['transaction_count']
                actual['undo_receipt'] = previous_delete['undo_receipt']
            self.uncertain = True
            result = self.create_connection(actual, state, raw, name) if op['kind'] == 'connect' and not op.get('template_id') else self.editor(actual, state['nodes'])
            self.write(f'editor-{len(self.report["steps"])+1:03d}.json', result)
            self.verify_render_alpha(state, result, op)
            if op['kind'] == 'undo':
                if not equivalent(result['nodes'], previous_delete['before']):
                    raise VerificationError('Undo did not restore the pre-delete projection')
                delta = differences(state['nodes'], result['nodes'])
            else:
                delta = check_scope(state['nodes'], result['nodes'], op)
            # A theme-alpha-only correction is absent from CLI raw. Keep the
            # writer open for stable polling before a fresh-page confirmation.
            alpha_only = not any(delta.values()) and not self.alpha_equivalent(state['render_alpha'],result['render_alpha'])
            saved_raw, saved = self.settle(result['nodes'], result['render_alpha'], 3 if alpha_only else 0, result['line_endpoints'])
            raw_exceptions = check_raw_preservation(previous_delete['raw'] if op['kind'] == 'undo' else raw, saved_raw, {'kind':'undo'} if op['kind'] == 'undo' else op)
            if op['kind'] in ('style','connect','reconnect','anchors') or any(n.get('kind') == 'connector' and n.get('shape') == 'curve' for n in result['nodes']):
                reopened = self.reopen_verified(saved_raw, result['nodes'], result['render_alpha'], result['line_endpoints'])
                self.write(f'reopened-{len(self.report["steps"])+1:03d}.json', reopened)
            self.uncertain = False
            self.report['steps'].append({'operation': op, 'before_raw': name, 'after_raw': saved, 'diff': delta, 'raw_exceptions':raw_exceptions,
                                         'before_render_alpha':state['render_alpha'],'after_render_alpha':result['render_alpha']})
            previous_delete = {'before': state['nodes'], 'raw':raw, 'transaction_count': result['transaction_count'], 'undo_receipt':result['undo_receipt']} if op['kind'] == 'delete' else None
        self.report['status'] = 'verified'

    def create_connection(self, op, state, raw, name):
        """Append exactly one free line, then bind it through the native editor.

        The raw append endpoint cannot refer to pre-existing module IDs. Do not
        re-import those modules or replay an uncertain append to work around it.
        """
        lookup = {n['id']:n for n in state['nodes']}
        start, end = lookup[op['start_id']], lookup[op['end_id']]
        raw_lookup = {n['id']:n for n in raw['nodes']}
        for endpoint in (start, end):
            if raw_lookup[endpoint['id']].get('locked') or endpoint.get('parent_id'):
                raise VerificationError('First connection requires unlocked, ungrouped native modules')
        sx, sy = start['x'] + start['width'], start['y'] + start['height']/2
        ex, ey = end['x'], end['y'] + end['height']/2
        client_id = 'c' + str(uuid.uuid4().int % 1000000000) + ':1'
        payload = {'nodes':[{'id':client_id, 'type':'connector',
            'x':min(sx,ex), 'y':min(sy,ey), 'width':abs(ex-sx), 'height':abs(ey-sy),
            'style':{'border_color':'#334155','border_style':'solid','border_width':'narrow'},
            'connector':{'shape':'straight',
                'start':{'position':{'x':sx,'y':sy},'arrow_style':'none'},
                'end':{'position':{'x':ex,'y':ey},'arrow_style':'line_arrow'}}}]}
        step = len(self.report['steps']) + 1
        filename = f'connect-input-{step:03d}.json'
        receipt_name = f'connect-receipt-{step:03d}.json'
        key = str(uuid.uuid4())
        receipt = {'idempotent_token':key, 'before_raw':name, 'operation':op,
                   'status':'submitted_once'}
        self.write(filename, payload)
        self.write(receipt_name, receipt)
        self.command(['whiteboard', '+update', '--whiteboard-token', self.request['whiteboard_token'],
                      '--input_format','raw','--source','@'+filename,'--idempotent-token',key,'--as','user'])
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                latest, after_name = self.export()
                mapping = match_append(projection(raw), projection(latest), projection(payload))
                check_raw_preservation(raw, latest, {'kind':'append'})
                break
            except NotReady:
                time.sleep(1)
            except VerificationError as error:
                if 'count has not converged' not in str(error):
                    raise
                time.sleep(1)
        else:
            raise VerificationError('Connection append did not converge; inspect the receipt before resuming the same line')
        ident = mapping[client_id]
        receipt.update(created_id=ident, appended_raw=after_name, status='appended_readback_verified')
        self.write(f'connect-appended-{step:03d}.json', receipt)
        # Reload only this owned page so a cached pre-append board cannot write.
        self.call('/v2/tasks/' + self.task + '/complete', {'keep':False})
        self.token = self.task = self.tab = None
        self.open_page()
        self.hydrate(latest)
        self.editor({'kind':'enter'})
        loaded = self.hydrate(latest)
        result = self.editor({'kind':'reconnect','id':ident,
                              'start_id':op['start_id'],'end_id':op['end_id']}, loaded['nodes'])
        return result

    def append(self, filename):
        if self.request.get('operations'):
            raise ValueError('Append is standalone; inspect the saved board in a new editor session before editing')
        payload = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
        nodes = payload['nodes']
        ids = [n['id'] for n in nodes]
        if not nodes or len(ids) != len(set(ids)):
            raise ValueError('Append requires nonempty unique IDs')
        raw, name = self.export()
        existing = {n['id']:n for n in raw['nodes']}
        shape_lookup = {ident:n for ident,n in existing.items() if n.get('type') == 'composite_shape'}
        shape_lookup.update({n['id']:n for n in nodes if n.get('type') == 'composite_shape'})
        for n in nodes:
            if n.get('type') not in ('composite_shape', 'text_shape', 'connector'):
                raise ValueError('Append only supports native shapes, text shapes and bound connectors')
            if n['type'] in ('composite_shape', 'text_shape') and not isinstance(n.get('text', {}).get('text'), str):
                raise ValueError('Native shapes must own their text')
            if n['type'] == 'connector':
                c = n['connector']
                for side in ('start','end'):
                    endpoint = c.get(side + '_object', {})
                    if endpoint.get('id') not in ids:
                        raise ValueError('CLI append cannot reference existing shapes; append new shapes first, then use editor connect for existing modules')
                    if endpoint.get('id') not in shape_lookup or endpoint != c.get(side, {}).get('attached_object'):
                        raise ValueError('Append connector has missing or conflicting native shape endpoint')
                start,end = (shape_lookup[c[side + '_object']['id']] for side in ('start','end'))
                sp,ep = (c[side + '_object']['position'] for side in ('start','end'))
                sx,sy = start['x']+start['width']*sp['x'], start['y']+start['height']*sp['y']
                ex,ey = end['x']+end['width']*ep['x'],end['y']+end['height']*ep['y']
                if not equivalent([n['x'],n['y'],n['width'],n['height']], [min(sx,ex),min(sy,ey),abs(ex-sx),abs(ey-sy)]):
                    raise ValueError('Connector geometry is stale or uses unsupported anchors')
        before = projection(raw)
        self.open_page()
        self.hydrate(raw)
        if set(ids) & {n['id'] for n in before}:
            raise ValueError('Append IDs collide with existing IDs')
        intended = projection(payload)
        key = str(uuid.uuid4())
        self.write('append-input.json', payload)
        self.write('append-receipt.json', {'idempotent_token': key, 'before_raw': name})
        self.uncertain = True
        self.command(['whiteboard', '+update', '--whiteboard-token', self.request['whiteboard_token'], '--input_format', 'raw', '--source', '@append-input.json', '--idempotent-token', key, '--as', 'user'])
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                latest, after_name = self.export()
                mapping = match_append(before, projection(latest), intended)
                check_raw_preservation(raw, latest, {'kind':'append'})
                self.report.update(status='verified', before_raw=name, after_raw=after_name, id_mapping=mapping)
                self.uncertain = False
                return
            except NotReady:
                time.sleep(1)
                continue
            except VerificationError as error:
                if 'count has not converged' not in str(error):
                    raise
                time.sleep(1)
        raise VerificationError('Append save/readback did not converge; write was not retried')

    def close(self):
        if self.task:
            try:
                self.call('/v2/tasks/' + self.task + '/complete', {'keep': self.uncertain})
                self.report['released_tab'] = self.tab if self.uncertain else None
            except Exception:
                self.report['cleanup'] = 'Task release failed; inspect the existing browser task'
            finally:
                self.token = None
        self.write('result.json', self.report)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--proxy-url', required=True)
    p.add_argument('--timeout', type=int, default=45)
    p.add_argument('--append-raw', help='Standalone native append; request operations must be empty')
    a = p.parse_args()
    request = json.loads(Path(a.request).read_text(encoding='utf-8-sig'))
    runner = Runner(request, a.output_dir, a.proxy_url, a.timeout)
    code = 0
    try:
        if a.append_raw:
            runner.append(a.append_raw)
        else:
            runner.run()
    except Exception as e:
        runner.report.update(status='unverified', error=type(e).__name__, reason=str(e) if isinstance(e, (VerificationError, ValueError)) else 'Transport or runtime failure; no automatic write retry')
        code = 1
    finally:
        runner.close()
    print(json.dumps({'status': runner.report['status'], 'result': str(runner.output / 'result.json')}, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
