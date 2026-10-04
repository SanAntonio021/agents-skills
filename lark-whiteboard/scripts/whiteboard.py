"""Guarded CLI readback and background editor runner (Python standard library)."""
import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import struct
import time
import urllib.request
from urllib.parse import urlparse
import uuid
import zlib


class VerificationError(RuntimeError):
    pass


class NotReady(VerificationError):
    pass


def png_has_board_ink(data, rect, scale=1):
    """Reject a white transition frame; image review is still required.

    Proxy screenshots use 8-bit RGB/RGBA PNG. Unsupported encodings fail closed.
    The crop is the observed board viewport, not the document's surrounding UI.
    """
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    compressed, offset, header = bytearray(), 8, None
    while offset + 12 <= len(data):
        size = struct.unpack('>I', data[offset:offset+4])[0]
        kind, body = data[offset+4:offset+8], data[offset+8:offset+8+size]
        if len(body) != size:
            return False
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            compressed.extend(body)
        elif kind == b'IEND':
            break
        offset += size + 12
    if not header:
        return False
    width, height, depth, color, compression, filtering, interlace = header
    if depth != 8 or color not in (2, 6) or any((compression, filtering, interlace)) or width * height > 20_000_000:
        return False
    channels = 3 if color == 2 else 4
    stride = width * channels
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(bytes(compressed), (stride+1)*height+1)
    if len(pixels) != (stride+1)*height:
        return False
    left, top = max(0, int(rect['x']*scale)), max(0, int(rect['y']*scale))
    right = min(width, math.ceil((rect['x']+rect['width'])*scale))
    bottom = min(height, math.ceil((rect['y']+rect['height'])*scale))
    if left >= right or top >= bottom:
        return False
    previous, ink = bytearray(stride), 0
    for y in range(height):
        start = y*(stride+1)
        filter_type, row = pixels[start], bytearray(pixels[start+1:start+1+stride])
        if filter_type > 4:
            return False
        for i in range(stride):
            a = row[i-channels] if i >= channels else 0
            b = previous[i]
            c = previous[i-channels] if i >= channels else 0
            predictor = 0
            if filter_type == 1:
                predictor = a
            elif filter_type == 2:
                predictor = b
            elif filter_type == 3:
                predictor = (a+b)//2
            elif filter_type == 4:
                p = a+b-c
                predictor = min((a, b, c), key=lambda v: abs(p-v))
            row[i] = (row[i]+predictor) & 255
        if top <= y < bottom:
            for x in range(left, right):
                p = x*channels
                if (channels == 3 or row[p+3] >= 200) and min(row[p:p+3]) < 220:
                    ink += 1
                    if ink >= 24:
                        return True
        previous = row
    return False


LINE_SHAPES = {'straight', 'polyline', 'curve', 'right_angled_polyline'}
STYLE_FIELDS = {'border_color', 'fill_color', 'text_color', 'border_style', 'border_width'}
CAPTION_PLACEMENTS = {'on_line': 0, 'above_line': 1, 'below_line': 2}
CAPTION_DEFAULT_RAW_FIELDS = {'text', 'angle', 'font_size', 'font_weight', 'horizontal_align', 'vertical_align',
                              'italic', 'line_through', 'underline', 'text_color', 'text_color_type',
                              'text_background_color_type', 'theme_text_background_color_code'}
ARROW_STYLES = {'none', 'line_arrow', 'triangle_arrow', 'empty_triangle_arrow', 'circle_arrow',
                'empty_circle_arrow', 'diamond_arrow', 'empty_diamond_arrow', 'single_arrow',
                'multi_arrow', 'exact_single_arrow', 'zero_or_single_arrow', 'single_or_multi_arrow',
                'zero_or_multi_arrow', 'x_arrow'}
OPERATION_FIELDS = {
    'text': ({'id', 'text'}, set()), 'font': ({'id', 'font_size'}, set()),
    'resize': ({'id', 'width', 'height'}, set()), 'move': ({'ids', 'dx', 'dy'}, set()),
    'arrow': ({'id', 'start', 'end'}, set()), 'caption': ({'id', 'text'}, set()),
    'caption_position': ({'id'}, {'position', 'placement'}),
    'caption_format': ({'id'}, {'font_size', 'width', 'auto_width'}),
    'line_type': ({'id', 'shape'}, set()), 'path': ({'id', 'points'}, set()),
    'curve_point': ({'id', 'point'}, {'mode', 'index'}), 'style': ({'id', 'style'}, set()),
    'anchors': ({'id'}, {'start', 'end'}), 'reconnect': ({'id'}, {'start_id', 'end_id'}),
    'connect': ({'start_id', 'end_id'}, {'template_id'}), 'group': ({'ids'}, set()),
    'ungroup': ({'id'}, set()), 'align_top': ({'ids'}, set()),
    'distribute_horizontal': ({'ids'}, set()), 'delete': ({'ids', 'delete_ids'}, set()),
    'undo': (set(), set()),
}


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
    if not isinstance(request, dict) or not isinstance(request.get('document_url'), str):
        raise ValueError('Request requires a document_url string')
    u = urlparse(request['document_url'])
    host = u.hostname or ''
    if u.scheme != 'https' or u.username or u.password or u.port or not any(host == d or host.endswith('.' + d) for d in ('feishu.cn', 'larksuite.com')) or not re.fullmatch(r'/docx/[A-Za-z0-9]+/?', u.path) or u.query or u.fragment:
        raise ValueError('Expected a plain HTTPS Feishu/Lark docx URL')
    if not isinstance(request.get('whiteboard_token'), str) or not re.fullmatch(r'[A-Za-z0-9]+', request['whiteboard_token']):
        raise ValueError('Invalid whiteboard token')
    if not isinstance(request.get('operations', []), list):
        raise ValueError('operations must be a list')
    if 'capture_preview' in request and type(request['capture_preview']) is not bool:
        raise ValueError('capture_preview must be a boolean')
    for key in ('block_id', 'section_id'):
        if key in request and (not isinstance(request[key], str) or not re.fullmatch(r'[A-Za-z0-9]+', request[key])):
            raise ValueError('Invalid document block identifier')
    validate_request_operations(request)


def validate_request_operations(request):
    """Validate the whole batch without reading or opening a board.

    Object-dependent facts are deliberately checked later against each saved
    state, so adding a caption then formatting it remains a valid batch.
    """
    if not isinstance(request, dict) or not isinstance(request.get('operations', []), list):
        raise VerificationError('operations must be a list')
    operations = request.get('operations', [])
    for index, op in enumerate(operations):
        validate_operation_parameters(op)
        if op['kind'] == 'undo' and (index == 0 or operations[index-1]['kind'] != 'delete'):
            raise VerificationError('Undo is only allowed immediately after a delete in the same request')


def validate_operation_parameters(op):
    if not isinstance(op, dict) or not isinstance(op.get('kind'), str) or op['kind'] not in OPERATION_FIELDS:
        raise VerificationError('Unsupported operation kind')
    kind = op['kind']
    required, optional = OPERATION_FIELDS[kind]
    if required - op.keys() or set(op) - required - optional - {'kind'}:
        raise VerificationError('Missing or unsupported parameter for ' + kind)
    def identifier(value):
        return isinstance(value, str) and bool(value.strip())
    for key in ('id', 'start_id', 'end_id', 'template_id'):
        if key in op and not identifier(op[key]):
            raise VerificationError('Object identifier must be a nonempty string')
    for key in ('ids', 'delete_ids'):
        if key in op and (not isinstance(op[key], list) or not op[key]
                          or any(not identifier(i) for i in op[key]) or len(set(op[key])) != len(op[key])):
            raise VerificationError('Object list must contain unique nonempty string IDs')
    minimum = {'group': 2, 'align_top': 2, 'distribute_horizontal': 3}.get(kind, 1)
    if 'ids' in op and len(op['ids']) < minimum:
        raise VerificationError('Insufficient object selection for ' + kind)
    if kind in ('text', 'caption') and not isinstance(op['text'], str):
        raise VerificationError('Text must be a string')
    if kind == 'font' and (not finite_number(op['font_size']) or not 4 <= op['font_size'] <= 999):
        raise VerificationError('Font size must be a finite number in [4, 999]')
    if kind == 'resize' and not all(finite_number(op[k], True) for k in ('width', 'height')):
        raise VerificationError('Dimensions must be positive and finite')
    if kind == 'move' and not all(finite_number(op[k]) for k in ('dx', 'dy')):
        raise VerificationError('Movement must use finite numbers')
    if kind == 'arrow' and any(not isinstance(op[k], str) or op[k] not in ARROW_STYLES for k in ('start', 'end')):
        raise VerificationError('Unsupported arrow style')
    if kind in ('caption_position', 'caption_format'):
        # Reuse parameter validation without assuming the target already has a
        # caption: a preceding operation may create it.
        validate_caption_operation({'kind': 'connector', 'caption_texts': [''], 'caption_position_type': 0}, op)
    if kind == 'line_type' and (not isinstance(op['shape'], str) or op['shape'] not in LINE_SHAPES):
        raise VerificationError('Unsupported line type')
    if kind == 'path' and (not isinstance(op['points'], list) or not op['points'] or not all(valid_point(p) for p in op['points'])):
        raise VerificationError('Path points must be finite canvas x/y coordinates')
    if kind == 'curve_point':
        if not valid_point(op['point']):
            raise VerificationError('Curve point must be finite canvas x/y coordinates')
        if 'mode' in op and (not isinstance(op['mode'], str) or op['mode'] not in ('segment', 'turning')):
            raise VerificationError('Unsupported curve handle mode')
        if 'index' in op and (type(op['index']) is not int or op['index'] < 0):
            raise VerificationError('Curve handle index must be a nonnegative integer')
    if kind == 'style':
        validate_style(op['style'])
    if kind == 'anchors':
        if not {'start', 'end'} & op.keys():
            raise VerificationError('Anchor operation requires start or end')
        for side in ('start', 'end'):
            if side in op:
                anchor = op[side]
                if (not isinstance(anchor, dict) or set(anchor) != {'snap_to', 'position'}
                        or anchor['snap_to'] not in ('top', 'right', 'bottom', 'left')
                        or not valid_point(anchor['position']) or not all(0 <= v <= 1 for v in anchor['position'].values())):
                    raise VerificationError('Anchor needs a supported edge and position in [0, 1]')
                x, y = anchor['position']['x'], anchor['position']['y']
                if not {'top': y == 0, 'right': x == 1, 'bottom': y == 1, 'left': x == 0}[anchor['snap_to']]:
                    raise VerificationError('Anchor must lie on its specified edge')
    if kind == 'reconnect' and not {'start_id', 'end_id'} & op.keys():
        raise VerificationError('Reconnect requires a start_id or end_id')
    if kind in ('connect', 'reconnect') and 'start_id' in op and 'end_id' in op and op['start_id'] == op['end_id']:
        raise VerificationError('Self connection is not supported')
    if kind == 'delete' and not set(op['ids']) <= set(op['delete_ids']):
        raise VerificationError('Deletion set must include every selected object')


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
                     caption_auto_direction=c.get('caption_auto_direction', False),
                     caption_font_size=c['captions']['data'][0].get('font_size') if caption_texts else None)
            # CLI raw omits the native caption textBoxWidth and sizeMode. Leave
            # them unknown; save verification uses a fresh native page readback.
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


def caption_raw_font_equivalent(raw_value, native_value):
    # CLI serializes this field as an integer, while the native saved label can
    # retain a fraction. Fresh-page verification still compares the full value.
    return (caption_position_equivalent(raw_value, native_value)
            or type(raw_value) is int and finite_number(native_value)
            and raw_value == math.trunc(native_value))


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
            caption_position_equivalent(a[k], b[k]) if k in ('caption_position', 'caption_font_size', 'caption_width')
            else type(a[k]) is type(b[k]) and a[k] == b[k] if k == 'caption_size_mode'
            else points_equivalent(a[k], b[k]) if k == 'points' else equivalent(a[k], b[k])
            for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    return a == b


def differences(before, after):
    a, b = ({n['id']: n for n in nodes} for nodes in (before, after))
    return dict(added=sorted(b.keys()-a.keys()), removed=sorted(a.keys()-b.keys()), changed=sorted(k for k in a.keys() & b.keys() if not equivalent(a[k], b[k])))


def check_scope(before, after, op, *, from_raw=False, group_evidence=None):
    if len({n['id'] for n in before}) != len(before) or len({n['id'] for n in after}) != len(after):
        raise VerificationError('Local edit requires unique object IDs')
    delta = differences(before, after)
    ids = set(op.get('ids', [])) | ({op['id']} if 'id' in op else set())
    lookup = {n['id']: n for n in before}
    for ident in list(ids):
        ids.update(lookup.get(ident, {}).get('children', []))
    allowed = ids | {n['id'] for n in before if n.get('start_id') in ids or n.get('end_id') in ids}
    if op['kind'] in ('caption', 'caption_position', 'caption_format', 'style', 'reconnect', 'line_type', 'path', 'curve_point'):
        if len(lookup) != len(before) or len({n['id'] for n in after}) != len(after):
            raise VerificationError('Local edit requires unique object IDs')
        allowed = {op.get('id')}
    allowed.update(check_group_bounds(before, after, op, group_evidence=group_evidence))
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
    elif op['kind'] == 'caption_format':
        if len(texts) != 1:
            raise VerificationError('Caption format requires one caption')
        if set(op) - {'kind', 'id', 'font_size', 'width', 'auto_width'}:
            raise VerificationError('Unsupported caption format parameter')
        if not {'font_size', 'width', 'auto_width'} & op.keys():
            raise VerificationError('Caption format requires font_size, width or auto_width')
        if 'font_size' in op and (not finite_number(op['font_size']) or not 4 <= op['font_size'] <= 999):
            raise VerificationError('Caption font size must be a finite number in [4, 999]')
        if 'width' in op and (not finite_number(op['width']) or op['width'] < 10):
            raise VerificationError('Caption width must be a finite number at least 10')
        if 'auto_width' in op and op['auto_width'] is not True:
            raise VerificationError('auto_width must be true')
        if 'width' in op and 'auto_width' in op:
            raise VerificationError('width and auto_width are mutually exclusive')
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
        if key == 'border_style' and value not in ('solid', 'dash', 'dot'):
            raise VerificationError('Unsupported border style')
        if key == 'border_width' and value not in ('extra_narrow', 'narrow', 'medium', 'bold'):
            raise VerificationError('Unsupported border width')


def finite_number(value, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (not positive or value > 0))


def valid_point(point):
    return isinstance(point, dict) and set(point) == {'x', 'y'} and all(finite_number(point[k]) for k in point)


def curve_handle(node, op, *, from_raw=False):
    if not node or node.get('kind') != 'connector' or node.get('shape') != 'curve':
        raise VerificationError('Curve point edit requires a native curve')
    if not valid_point(op.get('point')):
        raise VerificationError('Curve point must be finite canvas x/y coordinates')
    points = node.get('points')
    if not isinstance(points, list) or not all(valid_point(p) for p in points):
        raise VerificationError('Curve point data is invalid')
    if not from_raw and (len(points) < 2 or (len(points)-2) % 3):
        raise VerificationError('Native curve point topology is invalid')
    turning_count = len(points) if from_raw else (len(points)-2)//3
    mode = op.get('mode', 'turning' if turning_count else 'segment')
    index = op.get('index', 0)
    if mode not in ('segment', 'turning') or type(index) is not int or index < 0:
        raise VerificationError('Curve handle requires segment/turning and a nonnegative integer index')
    if index >= turning_count + (mode == 'segment'):
        raise VerificationError('Curve handle index is not available')
    return mode, index


def validate_local_operation(nodes, op):
    """Reject unsupported parameters before invoking a mutating editor command."""
    validate_operation_parameters(op)
    lookup = {n['id']: n for n in nodes}
    if len(lookup) != len(nodes):
        raise VerificationError('Local edit requires unique object IDs')
    kind = op['kind']
    node = lookup.get(op.get('id'))
    reject_nested_groups(nodes, op)
    affected = operation_target_ids(nodes, op)
    for ident in affected:
        target = lookup.get(ident)
        if target is None:
            raise VerificationError('Requested object does not exist: ' + ident)
        current, visited = target, set()
        while current is not None:
            if current['id'] in visited:
                raise VerificationError('Cyclic group membership is not supported')
            visited.add(current['id'])
            if current.get('locked') is True:
                raise VerificationError('Requested object or affected group member is locked')
            current = lookup.get(current.get('parent_id'))
    if kind in ('caption', 'caption_position', 'caption_format'):
        validate_caption_operation(node, op)
    elif kind == 'curve_point':
        curve_handle(node, op)
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
        if node['kind'] == 'text' and set(op['style']) != {'text_color'}:
            raise VerificationError('Independent text style supports text_color only')
    elif kind in ('arrow', 'anchors'):
        if not node or node.get('kind') != 'connector':
            raise VerificationError('Line edit requires an existing connector')
        if kind == 'anchors':
            for side in ('start', 'end'):
                endpoint = lookup.get(node.get(side + '_id'))
                if not endpoint or endpoint.get('kind') != 'shape':
                    raise VerificationError('Anchor refresh requires both endpoints bound to existing native shapes')
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
    elif kind in ('align_top', 'distribute_horizontal'):
        if any(lookup[i].get('kind') != 'shape' for i in op['ids']):
            raise VerificationError('Alignment and distribution require native shapes')
    elif kind == 'move':
        if any(lookup[i].get('kind') not in ('shape', 'text', 'connector', 'group') for i in op['ids']):
            raise VerificationError('Movement requires supported native objects')
        moving = set(op['ids'])
        for ident in op['ids']:
            moving.update(lookup[ident].get('children', []))
        for ident in moving:
            target = lookup[ident]
            if target.get('kind') == 'connector' and any(target.get(side + '_id')
                    and target[side + '_id'] not in moving for side in ('start', 'end')):
                raise VerificationError('A bound connector can move uniformly only with all its bound shapes')
    elif kind == 'ungroup':
        if not node or node.get('kind') != 'group' or not node.get('children'):
            raise VerificationError('Ungroup requires an existing native group')
    elif kind == 'group':
        if any(lookup[i].get('kind') not in ('shape', 'text', 'connector') for i in op['ids']):
            raise VerificationError('Grouping requires supported ungrouped native objects')
    elif kind == 'delete':
        expected = set(op['ids'])
        for ident in list(expected):
            expected.update(lookup[ident].get('children', []))
        expected.update(n['id'] for n in nodes if n.get('kind') == 'connector'
                        and (n.get('start_id') in expected or n.get('end_id') in expected))
        if expected != set(op['delete_ids']):
            raise VerificationError('Deletion scope must exactly match selected objects, children and bound lines')


def check_intent(before, after, op, delta=None, *, from_raw=False):
    """Verify requested outcomes, rather than treating absence of damage as success."""
    a, b = ({n['id']: n for n in nodes} for nodes in (before, after))
    kind = op['kind']
    ident = op.get('id')
    def require(condition):
        if not condition:
            raise VerificationError('Requested operation postcondition failed: ' + kind)
    for node_id in a.keys() & b.keys():
        old_node, new_node = a[node_id], b[node_id]
        if old_node.get('kind') != 'connector':
            continue
        owned = set()
        if node_id == ident and kind == 'caption_format':
            if 'font_size' in op:
                owned.add('caption_font_size')
            if 'width' in op or 'auto_width' in op:
                owned.update(('caption_width', 'caption_size_mode'))
        elif node_id == ident and kind == 'caption' and (not op.get('text') or not old_node.get('caption_texts')):
            owned.update(('caption_font_size', 'caption_width', 'caption_size_mode'))
        for field in {'caption_font_size', 'caption_width', 'caption_size_mode'} - owned:
            require(equivalent({field: old_node.get(field)}, {field: new_node.get(field)}))
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
    if kind == 'curve_point':
        mode, index = curve_handle(a.get(ident), op, from_raw=from_raw)
        require(ident in b)
        old, new = a[ident], b[ident]
        points = new.get('points')
        require(isinstance(points, list) and len(points) == len(old['points']) + ((1 if from_raw else 3) if mode == 'segment' else 0))
        wanted = list(old['points'] if from_raw else old['points'][2::3])
        if mode == 'segment':
            wanted.insert(index, op['point'])
        else:
            wanted[index] = op['point']
        require(points_equivalent(points if from_raw else points[2::3], wanted))
        editable = {'points', 'x', 'y', 'width', 'height'}
        require(equivalent({k:v for k,v in old.items() if k not in editable},
                           {k:v for k,v in new.items() if k not in editable}))
    if kind in ('caption', 'caption_position', 'caption_format'):
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
                require(all(new.get(k) is None for k in ('caption_font_size', 'caption_width', 'caption_size_mode')))
                editable.update(('caption_position', 'caption_position_type', 'caption_font_size', 'caption_width', 'caption_size_mode'))
            elif not old['caption_texts']:
                require(caption_position_equivalent(new.get('caption_position'), 0.5)
                        and type(new.get('caption_position_type')) is int and new['caption_position_type'] == 0)
                require(finite_number(new.get('caption_font_size')) and 4 <= new['caption_font_size'] <= 999)
                if 'caption_width' in new or 'caption_size_mode' in new:
                    require(caption_position_equivalent(new.get('caption_width'), -1)
                            and type(new.get('caption_size_mode')) is int and new['caption_size_mode'] == 0)
                editable.update(('caption_position', 'caption_position_type', 'caption_font_size', 'caption_width', 'caption_size_mode'))
        elif kind == 'caption_position':
            require(new.get('caption_texts') == old['caption_texts'])
            if 'position' in op:
                require(caption_position_equivalent(new.get('caption_position'), op['position']))
                editable.add('caption_position')
            if 'placement' in op:
                require(type(new.get('caption_position_type')) is int
                        and new['caption_position_type'] == CAPTION_PLACEMENTS[op['placement']])
                editable.add('caption_position_type')
        else:
            require(new.get('caption_texts') == old['caption_texts'])
            if 'font_size' in op:
                compare = caption_raw_font_equivalent if from_raw else caption_position_equivalent
                require(compare(new.get('caption_font_size'), op['font_size']))
                editable.add('caption_font_size')
            if 'width' in op or 'auto_width' in op:
                if not from_raw:
                    require(caption_position_equivalent(new.get('caption_width'), op.get('width', -1)))
                    require(type(new.get('caption_size_mode')) is int and new['caption_size_mode'] == (1 if 'width' in op else 0))
                editable.update(('caption_width', 'caption_size_mode'))
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
        moving = set(op['ids'])
        for node_id in op['ids']:
            moving.update(a[node_id].get('children', []))
        for node_id in moving:
            require(node_id in b and equivalent(b[node_id]['x'], a[node_id]['x'] + op['dx'])
                    and equivalent(b[node_id]['y'], a[node_id]['y'] + op['dy']))
            editable = {'x', 'y', 'points'} if a[node_id].get('kind') == 'connector' else {'x', 'y'}
            require(equivalent({k:v for k,v in a[node_id].items() if k not in editable},
                               {k:v for k,v in b[node_id].items() if k not in editable}))
            if a[node_id].get('kind') == 'connector' and ('points' in a[node_id] or 'points' in b[node_id]):
                require(points_equivalent(b[node_id].get('points'),
                                          [{'x': p['x']+op['dx'], 'y': p['y']+op['dy']} for p in a[node_id].get('points', [])]))
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
                          'caption_position', 'caption_position_type', 'caption_auto_direction',
                          'caption_font_size', 'caption_width', 'caption_size_mode'):
                if field in template:
                    require(equivalent({field: line.get(field)}, {field: template[field]}))
    if kind == 'ungroup':
        require(ident not in b and all(i in b and not b[i].get('parent_id') for i in a[ident].get('children', [])))
    if kind == 'align_top':
        top = min(a[i]['y'] for i in op['ids'])
        require(all(equivalent(b[i]['y'], top) for i in op['ids']))
        require(all(equivalent({k:v for k,v in a[i].items() if k != 'y'},
                               {k:v for k,v in b[i].items() if k != 'y'}) for i in op['ids']))
    if kind == 'distribute_horizontal':
        ordered = sorted((a[i] for i in op['ids']), key=lambda n: n['x'])
        gap = (ordered[-1]['x'] + ordered[-1]['width'] - ordered[0]['x']
               - sum(n['width'] for n in ordered)) / (len(ordered)-1)
        position = ordered[0]['x']
        for old in ordered:
            require(equivalent(b[old['id']]['x'], position))
            require(equivalent({k:v for k,v in old.items() if k != 'x'},
                               {k:v for k,v in b[old['id']].items() if k != 'x'}))
            position += old['width'] + gap
    if kind == 'delete':
        require(set(a) - set(b) == set(op['delete_ids']))


def operation_target_ids(nodes, op):
    """Objects a native operation can write, including temporary anchor refreshes."""
    lookup = {n['id']: n for n in nodes}
    ids = set(op.get('ids', [])) | ({op['id']} if 'id' in op else set())
    if op['kind'] in ('connect', 'reconnect'):
        ids.update(op[k] for k in ('start_id', 'end_id', 'template_id') if k in op)
    if op['kind'] == 'anchors':
        line = lookup.get(op.get('id'), {})
        ids.update(line.get(side + '_id') for side in ('start', 'end') if line.get(side + '_id'))
    pending = list(ids)
    while pending:
        for child in lookup.get(pending.pop(), {}).get('children', []):
            if child not in ids:
                ids.add(child)
                pending.append(child)
    if op['kind'] in ('move', 'resize', 'align_top', 'distribute_horizontal', 'delete', 'anchors', 'reconnect', 'connect'):
        ids.update(n['id'] for n in nodes if n.get('kind') == 'connector'
                   and (n.get('start_id') in ids or n.get('end_id') in ids))
    return ids


def reject_nested_groups(nodes, op):
    lookup = {n['id']: n for n in nodes}
    ids = set(op.get('ids', [])) | ({op['id']} if op.get('id') else set())
    if op['kind'] in ('connect', 'reconnect'):
        ids.update(op[k] for k in ('start_id', 'end_id', 'template_id') if k in op)
    member_operations = {'text', 'font', 'style', 'arrow', 'caption', 'caption_position', 'caption_format',
                         'line_type', 'path', 'curve_point', 'move', 'resize'}
    for ident in ids:
        if set(lookup.get(ident, {}).get('children', [])) & ids:
            raise VerificationError('A group and its member cannot be selected together')
    for ident in ids:
        n = lookup.get(ident, {})
        if n.get('parent_id'):
            parent = lookup.get(n['parent_id'])
            if (not parent or parent.get('kind') != 'group' or parent.get('parent_id')
                    or ident not in parent.get('children', []) or op['kind'] not in member_operations):
                raise VerificationError('Only supported edits inside one existing group are allowed')
            if any(lookup.get(child, {}).get('children') for child in parent.get('children', [])):
                raise VerificationError('Nested group operations are not supported')
        if n.get('children') and any(lookup.get(child, {}).get('children') for child in n['children']):
            raise VerificationError('Nested group operations are not supported')
        if op['kind'] == 'group' and n.get('children'):
            raise VerificationError('Creating nested groups is not supported')


def canonical_group_projection(nodes, bounds):
    """Derive only one-level group envelopes from native member bounds.

    The server's group rectangle is a cache, not member placement. No member or
    other group property is removed from either comparison.
    """
    result = copy.deepcopy(nodes)
    lookup = {n['id']: n for n in result}
    geometry = ('x', 'y', 'width', 'height')
    if not isinstance(bounds, dict):
        raise VerificationError('Native member bounds are required for group cache comparison')
    for group in result:
        if group.get('kind') != 'group':
            continue
        children = group.get('children', [])
        if (group.get('parent_id') or not children or any(i not in lookup or lookup[i].get('children')
                or not isinstance(bounds.get(i), dict)
                or not all(finite_number(bounds[i].get(k)) for k in geometry)
                or bounds[i]['width'] < 0 or bounds[i]['height'] < 0 for i in children)):
            raise VerificationError('Only complete one-level native group bounds can be derived')
        x, y = min(bounds[i]['x'] for i in children), min(bounds[i]['y'] for i in children)
        group.update(x=x, y=y,
                     width=max(bounds[i]['x']+bounds[i]['width'] for i in children)-x,
                     height=max(bounds[i]['y']+bounds[i]['height'] for i in children)-y)
    return result


def check_group_bounds(before, after, op, *, group_evidence=None):
    """Allow only the native derived envelope of an affected one-level group.

    Native getRectNode includes curve labels and arrow padding; base rectangles
    alone cannot prove their envelope. Runtime passes the before/after native child bounds. Pure
    shape-only checks may use their already axis-aligned base rectangles.
    """
    a, b = ({n['id']: n for n in nodes} for nodes in (before, after))
    if op['kind'] in ('group', 'ungroup', 'delete', 'undo'):
        return set()
    affected = operation_target_ids(before, op)
    parents = {a[i]['parent_id'] for i in affected if i in a and a[i].get('parent_id')}
    allowed = set()
    geometry = {'x', 'y', 'width', 'height'}
    for ident in parents:
        old, new = a.get(ident), b.get(ident)
        if (not old or not new or old.get('kind') != 'group' or old.get('parent_id')
                or not old.get('children') or any(i not in a or i not in b for i in old['children'])):
            raise VerificationError('Parent group identity or members changed during member editing')
        if not equivalent({k:v for k,v in old.items() if k not in geometry},
                          {k:v for k,v in new.items() if k not in geometry}):
            raise VerificationError('Parent group properties changed during member editing')
        children = old['children']
        if group_evidence is not None:
            if (not isinstance(group_evidence, dict) or not all(isinstance(group_evidence.get(side), dict) for side in ('before', 'after'))
                    or any(not isinstance(group_evidence[side].get(i), dict)
                           or not all(finite_number(group_evidence[side][i].get(k)) for k in geometry)
                           for side in ('before', 'after') for i in children)):
                raise VerificationError('Complete native group member bounds are required')
            bounds_before, bounds_after = group_evidence['before'], group_evidence['after']
            for child in set(children) - affected:
                if not all(caption_position_equivalent(bounds_before[child][k], bounds_after[child][k]) for k in geometry):
                    raise VerificationError('An unrequested group member visible bound changed')
        else:
            bounds_before, bounds_after = a, b
        changed = any(any(not caption_position_equivalent(bounds_before[i].get(k), bounds_after[i].get(k))
                          for k in geometry) for i in children)
        if not changed:
            if not all(caption_position_equivalent(old.get(k), new.get(k)) for k in geometry):
                raise VerificationError('Parent bounds changed without member geometry changing')
            continue
        if any(not all(finite_number(bounds_after[i].get(k)) for k in geometry) for i in children):
            raise VerificationError('Group member geometry must be finite')
        if group_evidence is None and any(a[i].get('kind') == 'connector' for i in children):
            raise VerificationError('Native visible bounds are required for group connector edits')
        x, y = min(bounds_after[i]['x'] for i in children), min(bounds_after[i]['y'] for i in children)
        expected = {'x': x, 'y': y,
                    'width': max(bounds_after[i]['x']+bounds_after[i]['width'] for i in children)-x,
                    'height': max(bounds_after[i]['y']+bounds_after[i]['height'] for i in children)-y}
        if not all(finite_number(new.get(k)) and abs(new[k]-expected[k]) <= 1e-3 for k in geometry):
            raise VerificationError('Parent group bounds do not match its actual member envelope')
        if any(not caption_position_equivalent(old.get(k), new.get(k)) for k in geometry):
            allowed.add(ident)
    return allowed


def raw_parent_ids(nodes):
    parents = {n['id']: n.get('parent_id', '') for n in nodes}
    for node in nodes:
        for child in node.get('children', []):
            parents[child] = node['id']
    return parents


def deletion_layer_normalization(before, after, op):
    """A native deletion compacts surviving siblings to dense layer indices.

    Isolated delete/immediate-undo raw evidence showed this exact compaction;
    ordinary edits have no permission to change any absolute layer index.
    """
    if op['kind'] != 'delete':
        return {}
    a, b = ({n['id']: n for n in raw['nodes']} for raw in (before, after))
    parents = raw_parent_ids(before['nodes'])
    removed = a.keys() - b.keys()
    changed = {}
    for parent in {parents[i] for i in removed}:
        siblings = [i for i in a if parents[i] == parent]
        survivors = [i for i in siblings if i in b]
        if not any(a[i].get('z_index') != b[i].get('z_index') for i in survivors):
            continue
        if any(type(a[i].get('z_index')) is not int or a[i]['z_index'] < 0 for i in siblings):
            raise VerificationError('Deletion layer normalization requires integer sibling indices')
        if len({a[i]['z_index'] for i in siblings}) != len(siblings):
            raise VerificationError('Deletion layer normalization requires unique sibling indices')
        ordered = sorted(survivors, key=lambda i:a[i]['z_index'])
        if any(type(b[i].get('z_index')) is not int or b[i]['z_index'] != rank for rank, i in enumerate(ordered)):
            raise VerificationError('Deletion changed surviving sibling stacking order')
        changed.update((i, {'id': i, 'normalization': 'delete_sibling_layer_compaction',
                            'before_z_index': a[i]['z_index'], 'after_z_index': b[i]['z_index']})
                       for i in survivors if a[i]['z_index'] != b[i]['z_index'])
    return changed


def group_layer_normalization(before, after, op):
    """Validate measured native group/ungroup sibling ordering and dense ranks."""
    kind = op['kind']
    if kind not in ('group', 'ungroup'):
        return {}
    a, b = ({n['id']: n for n in raw['nodes']} for raw in (before, after))
    parents, current_parents = raw_parent_ids(before['nodes']), raw_parent_ids(after['nodes'])
    roots = [i for i in a if not parents[i]]
    if any(type(a[i].get('z_index')) is not int or a[i]['z_index'] < 0 for i in roots):
        raise VerificationError('Grouping requires integer root layer indices')
    if len({a[i]['z_index'] for i in roots}) != len(roots):
        raise VerificationError('Grouping requires unique root layer indices')
    roots.sort(key=lambda i:a[i]['z_index'])
    expected = {}
    if kind == 'group':
        added = b.keys() - a.keys()
        if len(added) != 1 or not set(op['ids']) <= set(roots):
            raise VerificationError('Grouping requires ungrouped existing objects')
        group = next(iter(added))
        members = [i for i in roots if i in op['ids']]
        if b[group].get('type') != 'group' or set(b[group].get('children', [])) != set(members):
            raise VerificationError('Native group membership changed unexpectedly')
        if any(current_parents.get(i) != group for i in members):
            raise VerificationError('Native group did not preserve member parent identity')
        # The new group replaces the highest selected layer after the other
        # selected objects have been removed from the root sibling order.
        highest = members[-1]
        ordered = [group if i == highest else i for i in roots if i not in members or i == highest]
        expected.update((i, rank) for rank, i in enumerate(members))
    else:
        group = op['id']
        if group not in roots or a[group].get('type') != 'group' or group in b:
            raise VerificationError('Ungroup did not remove the requested root group')
        members = list(a[group].get('children', []))
        if not members or any(i not in a or i not in b or parents[i] != group for i in members):
            raise VerificationError('Ungroup changed the existing member identity set')
        if any(type(a[i].get('z_index')) is not int for i in members) or len({a[i]['z_index'] for i in members}) != len(members):
            raise VerificationError('Ungroup requires unique native member layer indices')
        members.sort(key=lambda i:a[i]['z_index'])
        if any(current_parents.get(i) for i in members):
            raise VerificationError('Ungroup did not release members at the root')
        ordered = [member for i in roots for member in (members if i == group else [i])]
    if set(ordered) != {i for i in b if not current_parents[i]}:
        raise VerificationError('Grouping changed unrelated root membership')
    expected.update((i, rank) for rank, i in enumerate(ordered))
    if any(type(b[i].get('z_index')) is not int or b[i]['z_index'] != rank for i, rank in expected.items()):
        raise VerificationError('Native grouping changed the measured sibling stacking order')
    return {i: {'id': i, 'normalization': kind + '_sibling_layer_reindex',
                'before_z_index': a[i]['z_index'], 'after_z_index': b[i]['z_index']}
            for i in expected if i in a and a[i]['z_index'] != b[i]['z_index']}


def check_raw_preservation(before, after, op, *, group_evidence=None):
    """Compare all raw properties, exempting only operation-owned fields."""
    import copy
    a, b = ({n['id']: n for n in raw['nodes']} for raw in (before, after))
    if len(a) != len(before['nodes']) or len(b) != len(after['nodes']):
        raise VerificationError('Raw readback requires unique object IDs')
    kind = op['kind']
    added, removed = b.keys() - a.keys(), a.keys() - b.keys()
    if kind in ('group', 'connect'):
        if len(added) != 1 or removed:
            raise VerificationError('Raw readback changed the requested object creation set')
    elif kind == 'append':
        if not added or removed:
            raise VerificationError('Raw append must preserve all existing object IDs')
    elif kind == 'delete':
        if added or removed != set(op['delete_ids']):
            raise VerificationError('Raw deletion did not match the explicit deletion set')
    elif kind == 'ungroup':
        if added or removed != {op['id']}:
            raise VerificationError('Raw ungroup did not match the requested group')
    elif added or removed:
        raise VerificationError('Raw readback changed the object ID set')
    layer_normalizations = deletion_layer_normalization(before, after, op)
    layer_normalizations.update(group_layer_normalization(before, after, op))
    needs_projection = kind in ('style','reconnect','line_type','path','curve_point','connect') or (
        kind != 'undo' and any(n.get('type') == 'group' for n in before['nodes']))
    before_projection, after_projection = (projection(before), projection(after)) if needs_projection else ([], [])
    cache_exceptions = []
    if kind != 'undo' and group_evidence is not None and any(n.get('type') == 'group' for n in before['nodes']):
        before_projection = canonical_group_projection(before_projection, group_evidence.get('before'))
        after_projection = canonical_group_projection(after_projection, group_evidence.get('after'))
        affected = operation_target_ids(before_projection, op)
        parents = {n['parent_id'] for n in before_projection if n['id'] in affected and n.get('parent_id')}
        after_canonical = {n['id']:n for n in after_projection}
        for ident in parents:
            if ident not in a or ident not in b:
                continue
            geometry = ('x', 'y', 'width', 'height')
            if all(caption_position_equivalent(a[ident].get(k), b[ident].get(k)) for k in geometry):
                continue
            if not all(finite_number(b[ident].get(k)) and abs(b[ident][k]-after_canonical[ident][k]) <= 1e-3 for k in geometry):
                raise VerificationError('Changed raw group cache does not match native member bounds')
            cache_exceptions.append({'id':ident, 'normalization':'native_derived_group_bounds_cache',
                                     'raw_bounds':{k:b[ident][k] for k in geometry}})
    derived_parents = (check_group_bounds(before_projection, after_projection, op, group_evidence=group_evidence)
                       if op.get('kind') != 'undo' and any(n.get('type') == 'group' for n in before['nodes']) else set())
    derived_parents.update(e['id'] for e in cache_exceptions)
    def strip_parent_bounds(ident, left, right):
        if ident in derived_parents:
            for node in (left, right):
                for field in ('x', 'y', 'width', 'height'):
                    node.pop(field, None)
    if op['kind'] in ('caption', 'caption_position', 'caption_format'):
        if a.keys() != b.keys() or len(a) != len(before['nodes']) or len(b) != len(after['nodes']):
            raise VerificationError('Caption operation changed the object ID set or duplicated an ID')
        check_intent(projection(before), projection(after), op, from_raw=True)
        target = op['id']
        for ident in a:
            left, right = copy.deepcopy(a[ident]), copy.deepcopy(b[ident])
            strip_parent_bounds(ident, left, right)
            if ident == target:
                lc, rc = left['connector'], right['connector']
                if op['kind'] == 'caption_format':
                    if 'font_size' in op:
                        lc['captions']['data'][0].pop('font_size', None)
                        rc['captions']['data'][0].pop('font_size', None)
                elif op['kind'] == 'caption_position':
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
                    captions = rc.get('captions', {})
                    entries = captions.get('data', [])
                    if (set(captions) != {'data'} or len(entries) != 1
                            or set(entries[0]) - CAPTION_DEFAULT_RAW_FIELDS):
                        raise VerificationError('Adding a caption introduced unverified default format fields')
                    for field in ('captions', 'caption_position', 'caption_position_type'):
                        if field != 'captions' and field in lc and lc[field] != rc.get(field):
                            raise VerificationError('Adding a caption changed an existing position field')
                        lc.pop(field, None)
                        rc.pop(field, None)
            # Caption edits do not move, restyle or restack any existing object.
            if json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
                raise VerificationError('Unexpected raw property change on object ' + ident)
        if (op['kind'] == 'caption_format' and 'font_size' in op
                and not caption_position_equivalent(b[target]['connector']['captions']['data'][0].get('font_size'), op['font_size'])):
            return cache_exceptions + [{'id':target,'normalization':'cli_caption_font_size_truncation',
                     'requested_font_size':op['font_size'],
                     'raw_font_size':b[target]['connector']['captions']['data'][0].get('font_size'),
                     'native_reopen_required':True}]
        return cache_exceptions
    if op['kind'] in ('style', 'reconnect', 'line_type', 'path', 'curve_point', 'connect'):
        if len(a) != len(before['nodes']) or len(b) != len(after['nodes']):
            raise VerificationError('Local edit requires unique object IDs')
        check_scope(before_projection, after_projection, op, from_raw=True, group_evidence=group_evidence)
        if op['kind'] != 'connect' and a.keys() != b.keys():
            raise VerificationError('Local edit changed the object ID set')
        target = op.get('id')
        for ident in a:
            left, right = copy.deepcopy(a[ident]), copy.deepcopy(b[ident])
            strip_parent_bounds(ident, left, right)
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
        return cache_exceptions
    ids = set(op.get('ids', [])) | ({op['id']} if 'id' in op else set())
    for ident in list(ids):
        ids.update(a.get(ident, {}).get('children', []))
    kind = op['kind']
    exceptions = list(layer_normalizations.values()) + cache_exceptions
    def strip(node, path):
        current = node
        for key in path[:-1]:
            current = current.get(key, {})
        current.pop(path[-1], None)
    for ident in a.keys() & b.keys():
        left, right = copy.deepcopy(a[ident]), copy.deepcopy(b[ident])
        strip_parent_bounds(ident, left, right)
        paths = []
        if ident in layer_normalizations:
            paths.append(('z_index',))
        if kind == 'undo' and 'locked' not in left and right.get('locked') is False:
            paths.append(('locked',))
            exceptions.append({'id':ident, 'normalization':'undo_missing_locked_to_false'})
        if kind == 'undo':
            for field in ('h_flip', 'v_flip'):
                if field not in left.get('style', {}) and right.get('style', {}).get(field) is False:
                    paths.append(('style',field))
                    exceptions.append({'id':ident,'normalization':'undo_missing_'+field+'_to_false'})
        c = a[ident].get('connector', {})
        target_parent = a.get(op.get('id'), {}).get('parent_id')
        old_turning, new_turning = c.get('turning_points'), b[ident].get('connector', {}).get('turning_points')
        if (kind in ('text','font') and target_parent and left.get('parent_id') == target_parent
                and c.get('shape') == 'curve' and old_turning != new_turning
                and isinstance(group_evidence, dict)
                and all(a.get((c.get(side + '_object') or c.get(side, {}).get('attached_object', {})).get('id'), {}).get('parent_id')
                        == target_parent for side in ('start','end'))
                and isinstance(old_turning,list) and isinstance(new_turning,list)
                and len(old_turning) == len(new_turning)
                and all(valid_point(p) for p in old_turning+new_turning)
                and all(abs(p[k]-q[k]) <= 1e-6 for p,q in zip(old_turning,new_turning) for k in ('x','y'))):
            native_before = {n['id']:n for n in group_evidence.get('native_before', [])}
            native_after = {n['id']:n for n in group_evidence.get('native_after', [])}
            lp,rp = native_before.get(ident,{}).get('points'),native_after.get(ident,{}).get('points')
            endpoints_before = group_evidence.get('native_endpoints_before',{}).get(ident,{})
            endpoints_after = group_evidence.get('native_endpoints_after',{}).get(ident,{})
            valid_bindings = all(any(r.get('id')==ident and r.get('valid') is True
                                    for r in group_evidence.get(key,[]))
                                 for key in ('bindings_before','bindings_after'))
            if (isinstance(lp,list) and isinstance(rp,list) and len(lp)==len(rp)
                    and all(valid_point(p) for p in lp+rp)
                    and set(endpoints_before)==set(endpoints_after)=={'start','end'}
                    and all(valid_point(p) for p in [*endpoints_before.values(),*endpoints_after.values()])
                    and valid_bindings
                    and all(abs(p[k]-q[k]) <= 1e-5 for p,q in zip(lp,rp) for k in ('x','y'))
                    and all(abs(endpoints_before[s][k]-endpoints_after[s][k]) <= 1e-5
                            for s in ('start','end') for k in ('x','y'))):
                paths.append(('connector','turning_points'))
                exceptions.append({'id':ident,'normalization':'grouped_text_curve_turning_point_roundoff',
                                   'before':old_turning,'after':new_turning,'maximum_difference':
                                   max((abs(p[k]-q[k]) for p,q in zip(old_turning,new_turning) for k in ('x','y')),default=0)})
        if (kind == 'text' and target_parent and left.get('parent_id') == target_parent
                and c.get('shape') == 'curve' and left.get('height') == 0
                and finite_number(right.get('height')) and 0 < right['height'] <= 1e-12
                and all(left.get(k) == right.get(k) for k in ('x', 'y', 'width'))
                and all(a.get((c.get(side + '_object') or c.get(side, {}).get('attached_object', {})).get('id'), {}).get('parent_id')
                        == target_parent for side in ('start', 'end'))):
            # The isolated grouped-text command preserves curve geometry but
            # serializes horizontal zero height as floating-point roundoff.
            paths.append(('height',))
            exceptions.append({'id': ident, 'normalization': 'grouped_text_curve_zero_height_roundoff',
                               'raw_height': right['height']})
        connected = any((c.get(side + '_object') or c.get(side, {}).get('attached_object', {})).get('id') in ids for side in ('start', 'end'))
        if ident in ids and kind == 'move':
            paths += [('x',), ('y',)]
        elif ident in ids and kind == 'resize':
            paths += [('width',), ('height',)]
        elif ident in ids and kind == 'align_top':
            paths += [('y',)]
        elif ident in ids and kind == 'distribute_horizontal':
            paths += [('x',)]
        if connected and ident not in ids and kind in ('move','resize','align_top','distribute_horizontal'):
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
        preserved = json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
        if not preserved:
            raise VerificationError('Unexpected raw property change on object ' + ident)
    # Operations above preserve absolute layers as well as their order.
    untouched = (a.keys() & b.keys()) - ids
    old_parents, new_parents = raw_parent_ids(before['nodes']), raw_parent_ids(after['nodes'])
    for parent in {old_parents[i] for i in untouched}:
        siblings = {i for i in untouched if old_parents[i] == parent}
        if any(new_parents[i] != parent for i in siblings):
            raise VerificationError('Unrelated object parent changed')
        order = lambda lookup: sorted(siblings, key=lambda i:(lookup[i].get('z_index',0), i))
        if order(a) != order(b):
            raise VerificationError('Unrelated sibling stacking order changed')
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
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Timeout must be a positive finite number')
        u = urlparse(proxy_url)
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
            raise ValueError('Proxy must be an existing loopback HTTP service')
        self.proxy = proxy_url.rstrip('/')
        self.token = self.task = self.tab = None
        self.uncertain = False
        self.index = 0
        self.report = {'status': 'running', 'steps': [], 'pages': [], 'cleanup_receipts': []}
        self.cli = shutil.which('lark-cli.exe') or shutil.which('lark-cli')
        if self.cli and Path(self.cli).suffix.lower() != '.exe' and __import__('os').name == 'nt':
            binary = Path(self.cli).parent / 'node_modules' / '@larksuite' / 'cli' / 'bin' / 'lark-cli.exe'
            if not binary.is_file():
                raise ValueError('Native lark-cli.exe not found next to the npm launcher')
            self.cli = str(binary)
        if not self.cli:
            raise ValueError('lark-cli is not installed')
        self.adapter = Path(__file__).with_name('editor.js').read_text(encoding='utf-8')
        self.output.mkdir(parents=True, exist_ok=False)

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

    def screenshot(self, timeout=45):
        req = urllib.request.Request(self.proxy + '/v2/tabs/' + self.tab + '/screenshot?format=png',
                                     headers={'Authorization': 'Bearer ' + self.token})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read(16_000_001)
        if len(data) > 16_000_000:
            raise VerificationError('Preview exceeds the screenshot size limit')
        return data

    def capture_preview(self):
        """Observe the owned page without replaying edits or discarding undo."""
        baseline = self.editor({'kind':'inspect'})
        baseline_save = baseline.get('native_save')
        if baseline_save is not None and not self.native_save_ready(baseline):
            raise VerificationError('Board is not saved while establishing the preview baseline')
        self.editor({'kind':'observe'}, baseline['nodes'])
        affected = {ident for step in self.report.get('steps', [])
                    for field in ('changed', 'added') for ident in step.get('diff', {}).get(field, [])}
        label_ids = {n['id'] for n in baseline['nodes'] if n.get('kind') == 'connector' and n.get('caption_texts')
                     and (not self.request.get('operations') or n['id'] in affected)}
        previous = None
        # Native pixels avoid the browser capture target lock, which can remain
        # held after a client transport timeout. Both paths keep the same fences.
        native_fallback = getattr(self,'prefer_native_preview',True)
        fallback_reason = None
        attempts = 0
        # A fallback or viewport change may resample, but cannot extend the
        # overall observation budget.
        deadline = time.monotonic() + min(self.timeout, 20)

        def same_content(state):
            if baseline_save is not None:
                native_same = (self.native_save_ready(state, minimum_applied_version=baseline_save['applied_version'])
                               and state['native_save']['applied_version'] == baseline_save['applied_version'])
            else:
                native_same = state.get('native_save') is None
            return (native_same and equivalent(state.get('nodes'), baseline.get('nodes'))
                    and self.alpha_equivalent(state.get('render_alpha'), baseline.get('render_alpha'))
                    and equivalent(state.get('line_endpoints'), baseline.get('line_endpoints'))
                    and state.get('seq') == baseline.get('seq')
                    and state.get('savedSeq') == baseline.get('savedSeq')
                    and state.get('seq') is not None and state.get('seq') == state.get('savedSeq'))

        while time.monotonic() < deadline:
            time.sleep(1)
            current = self.editor({'kind':'inspect'})
            if not same_content(current):
                raise VerificationError('Board changed while capturing the saved preview; reread before editing')
            viewport = current.get('viewport') or {}
            rect = viewport.get('rect')
            if not rect or not all(finite_number(rect.get(k), k in ('width','height')) for k in ('x','y','width','height')):
                break
            geometry = current.get('label_geometry') or {}
            for ident in label_ids:
                label = geometry.get(ident) or {}
                box = label.get('screen_rect') or {}
                if (not label.get('available') or not all(finite_number(box.get(k), k in ('width','height')) for k in ('x','y','width','height'))
                        or box['x'] < rect['x']-1 or box['y'] < rect['y']-1
                        or box['x']+box['width'] > rect['x']+rect['width']+1
                        or box['y']+box['height'] > rect['y']+rect['height']+1):
                    self.report.update(visual_status='unavailable',visual_reason='Edited label is outside the visible board viewport: '+ident)
                    return
            attempts += 1
            self.report['preview_attempts'] = attempts
            if not native_fallback:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    break
                try:
                    # A slow browser transfer must leave time for the canvas
                    # fallback inside the same observation budget.
                    frame = self.screenshot(timeout=min(5,remaining))
                except Exception as error:
                    native_fallback = True
                    fallback_reason = 'browser_transport_error'
                    self.report.update(preview_fallback_reason=fallback_reason,
                                       preview_browser_error=type(error).__name__)
                    previous = None
            if native_fallback:
                try:
                    payload = self.editor({'kind':'canvas_preview'}, current['nodes'])
                    if payload.get('viewport') != viewport:
                        previous = None
                        continue
                    data_url = payload.get('data_url', '')
                    if not data_url.startswith('data:image/png;base64,') or len(data_url) > 22_000_000:
                        raise VerificationError('Native canvas preview is unavailable or too large')
                    frame = base64.b64decode(data_url.partition(',')[2], validate=True)
                except VerificationError:
                    native_fallback = False
                    fallback_reason = 'native_canvas_unavailable'
                    self.report['preview_fallback_reason'] = fallback_reason
                    previous = None
                    continue
            after = self.editor({'kind':'inspect'})
            if not same_content(after):
                raise VerificationError('Board changed while capturing the saved preview; reread before editing')
            if (after.get('viewport') != viewport
                    or not equivalent(after.get('label_geometry') or {}, geometry)):
                previous = None
                continue
            pixel_rect = dict(x=0,y=0,width=rect['width'],height=rect['height']) if native_fallback else rect
            try:
                visible = png_has_board_ink(frame, pixel_rect, viewport.get('device_pixel_ratio', 1))
                for ident in label_ids:
                    box = dict(geometry[ident]['screen_rect'])
                    if native_fallback:
                        box.update(x=box['x']-rect['x'],y=box['y']-rect['y'])
                    if not png_has_board_ink(frame, box, viewport.get('device_pixel_ratio', 1)):
                        visible = False
                        break
            except (ValueError, struct.error, zlib.error):
                visible = False
            digest = hashlib.sha256(frame).hexdigest()
            self.report['preview_last_frame_visible'] = visible
            # This excludes blank transitions and a changing frame. It does not
            # establish legibility, label correctness or absence of overlap.
            frame_identity = (digest, json.dumps(viewport, sort_keys=True), json.dumps(geometry, sort_keys=True))
            if visible and frame_identity == previous:
                (self.output / 'preview.png').write_bytes(frame)
                self.write('visual-feedback.json', current)
                self.report.update(visual_status='needs_review', preview='preview.png',
                                   visual_feedback='visual-feedback.json',
                                   preview_source='native_canvas' if native_fallback else 'browser_screenshot')
                if fallback_reason:
                    self.report['preview_fallback_reason'] = fallback_reason
                return
            previous = frame_identity if visible else None
            if not native_fallback and ((attempts >= 2 and not visible) or attempts >= 3):
                native_fallback = True
                fallback_reason = 'browser_blank_frames' if not visible else 'browser_unstable_frames'
                self.report['preview_fallback_reason'] = fallback_reason
                previous = None
        self.report.update(visual_status='unavailable', visual_reason='No stable nonwhite board frame; inspect a fresh read-only page')

    def observe_saved(self):
        try:
            self.capture_preview()
        except Exception as error:
            self.report.update(visual_status='unavailable', visual_error=type(error).__name__,
                               visual_reason=str(error) if isinstance(error, VerificationError)
                               else 'Preview transport or runtime failure; saved edits were not replayed')

    def editor(self, operation, expected=None):
        request = {k: self.request[k] for k in ('document_url', 'whiteboard_token')}
        request.update(operation=operation, expected=expected)
        expression = '(()=>{try{return (' + self.adapter.rstrip().rstrip(';') + ')(' + json.dumps(request, ensure_ascii=True) + ')}catch(e){return {adapter_error:String(e.message),content_write_started:typeof e.content_write_started==="boolean"?e.content_write_started:null}}})()'
        response = self.call('/v2/tabs/' + self.tab + '/eval', {'expression': expression})
        value = response.get('value')
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict) and value.get('adapter_error'):
            error = VerificationError('Editor: ' + value['adapter_error'])
            error.content_write_started = value.get('content_write_started')
            raise error
        if not isinstance(value, dict) or value.get('error') or value.get('ok') is False:
            raise VerificationError('Editor rejected operation or returned an invalid response')
        return value

    @staticmethod
    def native_save_ready(state, fence=None, minimum_applied_version=None):
        """The legacy page sequence can remain zero while an IO action is queued."""
        receipt = state.get('native_save')
        if receipt is None:
            if fence is not None or minimum_applied_version is not None:
                raise VerificationError('Native save evidence is missing')
            return True
        if receipt.get('available') is not True:
            if fence is None and receipt.get('reason') == 'NATIVE_SAVE_INTERFACE_UNAVAILABLE':
                return False
            raise VerificationError('Native save interface is unavailable or unverified')
        if receipt.get('signature') != 'b8586b42':
            raise VerificationError('Native save interface is unavailable or unverified')
        for key in ('applied_version', 'pending', 'ordered_pending', 'http_pending'):
            if type(receipt.get(key)) is not int or receipt[key] < 0:
                raise VerificationError('Native save counters are invalid')
        for key in ('initialized', 'processing', 'offline'):
            if type(receipt.get(key)) is not bool:
                raise VerificationError('Native save flags are invalid')
        if receipt.get('save_state') not in ('saved', 'saving'):
            raise VerificationError('Native save state is invalid')
        required = minimum_applied_version
        if fence is not None:
            if (not isinstance(fence, dict) or fence.get('signature') != receipt['signature']
                    or type(fence.get('before_applied_version')) is not int or fence['before_applied_version'] < 0
                    or type(fence.get('requires_ack')) is not bool):
                raise VerificationError('Native save fence is invalid')
            required = max(required or 0, fence['before_applied_version'] + int(fence['requires_ack']))
        if required is not None and (type(required) is not int or required < 0):
            raise VerificationError('Native save version floor is invalid')
        return (receipt['initialized'] and not receipt['pending'] and not receipt['ordered_pending']
                and not receipt['processing'] and not receipt['offline'] and not receipt['http_pending']
                and receipt['save_state'] == 'saved'
                and (required is None or receipt['applied_version'] >= required))

    @staticmethod
    def needs_native_persistence(before, after):
        """Fields absent or truncated in CLI raw require a fresh native witness."""
        left = {n['id']:n for n in before['nodes']}
        for node in after['nodes']:
            prior = left.get(node['id'], {})
            if not prior:
                continue
            if node.get('kind') == 'connector':
                if any(not equivalent(prior.get(k), node.get(k)) for k in ('caption_width', 'caption_size_mode')):
                    return True
                font = node.get('caption_font_size')
                if (not equivalent(prior.get('caption_font_size'), font) and finite_number(font)
                        and font != math.trunc(font)):
                    return True
                if (node.get('shape') == 'curve' and not equivalent(prior.get('points'), node.get('points'))):
                    return True
        alpha_before, alpha_after = before.get('render_alpha') or {}, after.get('render_alpha') or {}
        return any(not Runner.alpha_equivalent({ident:alpha_before[ident]}, {ident:alpha_after[ident]})
                   for ident in alpha_before.keys() & alpha_after.keys())

    def settle(self, expected, expected_alpha=None, minimum_stable_seconds=0, expected_endpoints=None, save_fence=None):
        deadline = time.monotonic() + self.timeout
        self.last_save_deadline = deadline
        stable_since = None
        while time.monotonic() < deadline:
            current = self.editor({'kind': 'inspect'})
            if not equivalent(current['nodes'], expected):
                raise VerificationError('Page changed during save verification')
            if expected_alpha is not None and not self.alpha_equivalent(current.get('render_alpha'), expected_alpha):
                raise VerificationError('Rendering alpha changed during save verification')
            if expected_endpoints is not None and not equivalent(current.get('line_endpoints'), expected_endpoints):
                raise VerificationError('Native line endpoints changed during save verification')
            if (current.get('seq') == current.get('savedSeq') and current.get('seq') is not None
                    and self.native_save_ready(current, save_fence)):
                try:
                    raw, name = self.export()
                    if self.server_equivalent(projection(raw), expected, current.get('object_bounds')):
                        if stable_since is None:
                            stable_since = time.monotonic()
                        if time.monotonic() - stable_since >= minimum_stable_seconds:
                            self.last_saved_state = current
                            self.last_save_evidence = {'fence':save_fence, 'native_save':current.get('native_save'), 'raw':name}
                            return raw, name
                    else:
                        stable_since = None
                except NotReady:
                    stable_since = None
            else:
                stable_since = None
            time.sleep(1)
        raise VerificationError('Save/readback did not converge; write was not retried')

    @staticmethod
    def server_equivalent(raw_nodes, page_nodes, group_bounds=None):
        # CLI raw omits the two Bezier controls; do not invent them from a box.
        # Edited curves also require a fresh-page native readback below.
        left, right = copy.deepcopy(raw_nodes), copy.deepcopy(page_nodes)
        if group_bounds is not None and any(n.get('kind') == 'group' for n in right):
            try:
                canonical = canonical_group_projection(right, group_bounds)
                groups = {n['id']:n for n in canonical if n.get('kind') == 'group'}
                for node in right:
                    if node['id'] in groups and any(not finite_number(node.get(k))
                            or abs(node[k]-groups[node['id']][k]) > 1e-3 for k in ('x','y','width','height')):
                        return False
                for node in left:
                    if node.get('kind') == 'group' and node['id'] in groups:
                        if (any(not finite_number(node.get(k)) for k in ('x','y','width','height'))
                                or node['width'] < 0 or node['height'] < 0):
                            return False
                        node.update({k:groups[node['id']][k] for k in ('x','y','width','height')})
            except VerificationError:
                return False
        raw_lookup = {n['id']: n for n in left}
        for node in right:
            if node.get('kind') == 'connector':
                raw_font = raw_lookup.get(node['id'], {}).get('caption_font_size')
                if caption_raw_font_equivalent(raw_font, node.get('caption_font_size')):
                    node['caption_font_size'] = raw_font
        for nodes in (left, right):
            for node in nodes:
                if node.get('kind') == 'connector':
                    for field in ('caption_width', 'caption_size_mode'):
                        if field not in raw_lookup.get(node['id'], {}):
                            node.pop(field, None)
                if node.get('kind') == 'connector' and node.get('shape') == 'curve':
                    node.pop('points', None)
        return equivalent(left, right)

    @staticmethod
    def group_cache_evidence(raw, state):
        lookup = {n['id']:n for n in projection(raw)}
        geometry = ('x','y','width','height')
        return [{'id':n['id'], 'normalization':'native_derived_group_bounds_cache',
                 'raw_bounds':{k:lookup[n['id']][k] for k in geometry},
                 'native_bounds':{k:n[k] for k in geometry},
                 'member_bounds':{i:state['object_bounds'][i] for i in n['children']}}
                for n in state['nodes'] if n.get('kind') == 'group' and n['id'] in lookup
                and any(abs(n[k]-lookup[n['id']][k]) > 1e-3 for k in geometry)]

    @staticmethod
    def raw_group_cache_changes(before, after):
        """Identify cache-only candidates; native evidence must still confirm them."""
        left, right = ({n['id']:n for n in raw['nodes']} for raw in (before,after))
        if (left.keys()!=right.keys() or len(left)!=len(before['nodes']) or len(right)!=len(after['nodes'])):
            return []
        geometry = ('x','y','width','height')
        receipts = []
        strict = lambda value: json.dumps(value,sort_keys=True)
        for ident in left:
            old,new = left[ident],right[ident]
            if strict(old) == strict(new):
                continue
            if (old.get('type')!='group' or new.get('type')!='group' or old.get('angle',0)!=0
                    or strict({k:v for k,v in old.items() if k not in geometry})!=strict({k:v for k,v in new.items() if k not in geometry})
                    or any(not finite_number(n.get(k)) for n in (old,new) for k in geometry)
                    or any(n[k]<0 for n in (old,new) for k in ('width','height'))):
                return []
            receipts.append({'id':ident,'normalization':'delayed_native_group_bounds_cache',
                             'saved_bounds':{k:old.get(k) for k in geometry},
                             'latest_bounds':{k:new[k] for k in geometry}})
        return receipts

    @staticmethod
    def verified_group_cache_catchup(before, after, state):
        """Accept only delayed server cache updates to the observed native union."""
        receipts = Runner.raw_group_cache_changes(before,after)
        if not receipts:
            return []
        try:
            canonical = {n['id']:n for n in canonical_group_projection(state['nodes'],state.get('object_bounds'))}
        except VerificationError:
            return []
        geometry = ('x','y','width','height')
        for receipt in receipts:
            native = canonical.get(receipt['id'],{})
            if native.get('kind')!='group' or any(abs(receipt['latest_bounds'][k]-native[k])>1e-3 for k in geometry):
                return []
            receipt['native_bounds'] = {k:native[k] for k in geometry}
        if not Runner.server_equivalent(projection(after),state['nodes'],state.get('object_bounds')):
            return []
        return receipts

    def reopen_verified(self, saved_raw, expected, expected_alpha=None, expected_endpoints=None, binding_ids=None):
        self.complete_page(False, 'saved_reopen')
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
        self.verify_native_bindings(state, binding_ids or set())
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

    @staticmethod
    def affected_bindings(before, after, op):
        if op['kind'] not in ('move', 'resize', 'align_top', 'distribute_horizontal',
                              'anchors', 'reconnect', 'connect', 'append'):
            return set()
        targets = set(op.get('ids', [])) | ({op['id']} if op.get('id') else set())
        for node in before:
            if node['id'] in targets:
                targets.update(node.get('children', []))
        if op['kind'] in ('connect', 'append'):
            targets.update({n['id'] for n in after} - {n['id'] for n in before})
        return {n['id'] for n in after if n.get('kind') == 'connector'
                and (n.get('start_id') or n.get('end_id'))
                and (n['id'] in targets or n.get('start_id') in targets or n.get('end_id') in targets)}

    @staticmethod
    def verify_native_bindings(state, ids):
        """Compare native attachment points, not only a previous endpoint copy."""
        if not ids:
            return
        records = {item.get('id'): item for item in state.get('binding_geometry', [])}
        nodes = {item['id']: item for item in state['nodes']}
        endpoints = state.get('line_endpoints') or {}
        for ident in ids:
            record, node = records.get(ident, {}), nodes.get(ident, {})
            if record.get('valid') is not True:
                raise VerificationError('Native attachment evidence is missing or invalid: ' + ident)
            for side in ('start', 'end'):
                if not node.get(side + '_id'):
                    continue
                evidence = record.get(side, {})
                actual, expected = evidence.get('actual'), evidence.get('expected')
                if (evidence.get('valid') is not True or not isinstance(actual, dict)
                        or not isinstance(expected, dict) or set(actual) != {'x', 'y'} or set(expected) != {'x', 'y'}
                        or not all(finite_number(point[axis]) for point in (actual, expected) for axis in ('x', 'y'))
                        or any(abs(actual[axis] - expected[axis]) > .02 for axis in ('x', 'y'))
                        or not point_equivalent(actual, endpoints.get(ident, {}).get(side))):
                    raise VerificationError('Native line does not meet its actual attachment point: ' + ident + ':' + side)

    @staticmethod
    def verify_group_world(before, after, op):
        nodes = {n['id']:n for n in before['nodes']}
        selected = set(op.get('ids', [])) | ({op['id']} if op.get('id') else set())
        groups = {ident for ident in selected if nodes.get(ident, {}).get('kind') == 'group'}
        groups.update(nodes[ident]['parent_id'] for ident in selected if ident in nodes and nodes[ident].get('parent_id'))
        if not groups or op['kind'] in ('group', 'ungroup', 'delete', 'undo'):
            return set()
        members = {member for ident in groups for member in nodes.get(ident, {}).get('children', [])}
        left, right = before.get('world_geometry') or {}, after.get('world_geometry') or {}
        moving = selected | {member for ident in selected if ident in groups for member in nodes[ident].get('children', [])}
        for ident in members:
            a, b = left.get(ident), right.get(ident)
            if (not isinstance(a, dict) or not isinstance(b, dict)
                    or set(a) != {'x','y','width','height','angle'} or set(b) != set(a)
                    or not all(finite_number(value) for geometry in (a,b) for value in geometry.values())):
                raise VerificationError('Group member world-coordinate evidence is missing: ' + ident)
            if op['kind'] == 'move' and ident in moving:
                expected = {**a, 'x':a['x']+op['dx'], 'y':a['y']+op['dy']}
                if any(abs(b[key] - expected[key]) > 1e-6 for key in expected):
                    raise VerificationError('Group member did not preserve its world-coordinate displacement: ' + ident)
            elif ident not in selected:
                # A selected group's binding line may reroute when a member
                # moves. All other siblings must retain their world geometry.
                if nodes.get(ident, {}).get('kind') == 'connector' and ident in Runner.affected_bindings(before['nodes'], after['nodes'], op):
                    continue
                if any(abs(b[key] - a[key]) > 1e-6 for key in a):
                    raise VerificationError('Unrequested group member world position or size changed: ' + ident)
        return members

    def complete_page(self, keep, reason):
        if not self.task:
            return
        record = {'task_id': self.task, 'tab_id': self.tab, 'reason': reason,
                  'requested_action': 'release' if keep else 'close', 'status': 'pending'}
        self.report.setdefault('cleanup_receipts', []).append(record)
        try:
            response = self.call('/v2/tasks/' + self.task + '/complete', {'keep': keep})
            if isinstance(response, dict):
                record['receipt'] = {key: response[key] for key in
                                     ('taskId', 'state', 'keep', 'closed', 'released', 'unknownResult', 'retainedAsUserTabs')
                                     if key in response}
            if (not isinstance(response, dict) or response.get('state') != 'completed'
                    or response.get('taskId') != record['task_id']
                    or response.get('keep') is not keep or response.get('unknownResult')
                    or not isinstance(response.get('closed'), int) or isinstance(response.get('closed'), bool)
                    or not isinstance(response.get('released'), int) or isinstance(response.get('released'), bool)
                    or response['closed'] < 0 or response['released'] < 0
                    or (response['closed'] if keep else response['released']) != 0
                    or (record['tab_id'] is not None and (response['released'] if keep else response['closed']) != 1)):
                raise VerificationError('Page completion did not confirm its requested close or release')
            record['status'] = 'confirmed'
            record['page_status'] = 'released' if keep else 'closed'
            self.report['released_tab'] = self.tab if keep else None
            self.report['page_status'] = record['page_status']
        except Exception as error:
            record.update(status='unknown', page_status='unknown', error=type(error).__name__)
            self.report.update(page_status='unknown', cleanup='Page close or release was not confirmed; use the recorded own-page identity')
            raise
        finally:
            # Tokens are deliberately never recorded. A terminal completion
            # timeout cannot authorize reacquiring the possibly released page.
            self.token = self.task = self.tab = None

    def open_page(self):
        session = self.call('/v2/tasks', {}, auth=False)
        self.token, self.task = session['taskToken'], session['taskId']
        page = {'task_id': self.task, 'tab_id': None, 'open_status': 'creating'}
        self.report.setdefault('pages', []).append(page)
        target = self.call('/v2/tabs', {'url': self.request['document_url'], 'background': True})
        self.tab = target['targetId']
        page.update(tab_id=self.tab, open_status='created')
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
        page['open_status'] = 'ready'

    def hydrate(self, raw, minimum_applied_version=None):
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
                catchup = self.verified_group_cache_catchup(raw,latest,state)
                if not catchup:
                    if not self.raw_group_cache_changes(raw,latest):
                        raise VerificationError('Server changed while loading the target; reread before submitting edits')
                    # A first inspect can still be empty while the cache has
                    # caught up. Wait for native proof; do not accept it yet.
                    time.sleep(1)
                    continue
                state['server_group_cache_catchup'] = catchup
                self.write(f'group-cache-catchup-{self.index:03d}.json',
                           {'latest_raw':name,'normalizations':catchup})
            if (self.server_equivalent(projection(latest), state['nodes'], state.get('object_bounds'))
                    and state.get('seq') == state.get('savedSeq')
                    and self.native_save_ready(state, minimum_applied_version=minimum_applied_version)):
                state['group_cache_normalizations'] = self.group_cache_evidence(latest, state)
                return state
            time.sleep(1)
        raise VerificationError('Document board and CLI snapshot did not converge before writing; inspect prewrite-browser evidence')

    def confirm_native_persistence(self, saved_raw, expected, number, binding_ids=None):
        """Keep the writer alive until a separate saved page witnesses hidden fields."""
        remaining = self.last_save_deadline - time.monotonic()
        if remaining <= 0:
            raise VerificationError('Native persistence confirmation exceeded the save deadline')
        folder = f'native-save-witness-{number:03d}'
        request = {k:self.request[k] for k in ('document_url', 'whiteboard_token', 'section_id', 'block_id') if k in self.request}
        request['operations'] = []
        reader = Runner(request, self.output / folder, self.proxy, timeout=remaining)
        try:
            reader.open_page()
            remaining = self.last_save_deadline - time.monotonic()
            if remaining <= 0:
                raise VerificationError('Native persistence confirmation exceeded the save deadline')
            reader.timeout = min(reader.timeout, remaining)
            receipt = self.last_saved_state.get('native_save') or {}
            floor = receipt.get('applied_version')
            state = reader.hydrate(saved_raw, minimum_applied_version=floor)
            reader.write('fresh-native.json', state)
            if (not equivalent(state['nodes'], expected['nodes'])
                    or not self.alpha_equivalent(state.get('render_alpha'), expected.get('render_alpha'))
                    or not equivalent(state.get('line_endpoints'), expected.get('line_endpoints'))):
                raise VerificationError('Fresh native persistence witness differs; save remains unknown')
            self.verify_native_bindings(state, binding_ids or set())
            if time.monotonic() >= self.last_save_deadline:
                raise VerificationError('Native persistence confirmation exceeded the save deadline')
            reader.report['status'] = 'readonly_verified'
            return {'status':'confirmed', 'inspect':folder + '/fresh-native.json',
                    'minimum_applied_version':floor, 'native_save':state.get('native_save')}
        finally:
            reader.close()
            reader.write('result.json', reader.report)
            self.report.setdefault('pages', []).extend(reader.report.get('pages', []))
            self.report.setdefault('cleanup_receipts', []).extend(reader.report.get('cleanup_receipts', []))

    def run(self):
        validate_request_operations(self.request)
        raw, name = self.export()
        self.report['initial_raw'] = name
        self.open_page()
        self.hydrate(raw)
        if self.request.get('operations') or self.request.get('capture_preview'):
            self.editor({'kind': 'enter'})
            self.hydrate(raw)
        previous_delete = None
        operations = [None, *self.request.get('operations', [])]
        for index, op in enumerate(operations):
            state = self.editor({'kind': 'inspect'})
            raw, name = self.settle(state['nodes'], state['render_alpha'])
            if op is None:
                self.report['initial_nodes'] = state['nodes']
                self.write('inspect-000.json', state)
                self.report['initial_inspect'] = 'inspect-000.json'
                continue
            step = {'operation': op, 'before_raw': name, 'save_status': 'not_written',
                    'verification_status': 'pending', 'failure_phase': None, 'execution_status': 'not_started'}
            self.report['steps'].append(step)
            number = len(self.report['steps'])
            phase = 'preflight'
            try:
                actual = dict(op)
                reject_nested_groups(state['nodes'], op)
                validate_local_operation(state['nodes'], op)
                if op['kind'] == 'undo':
                    if previous_delete is None:
                        raise VerificationError('Undo is only allowed immediately after this session\'s delete')
                    actual['undo_count'] = previous_delete['transaction_count']
                    actual['undo_receipt'] = previous_delete['undo_receipt']
                phase = 'execute'
                self.uncertain = True
                step.update(save_status='unknown', execution_status='submitted')
                result = self.create_connection(actual, state, raw, name) if op['kind'] == 'connect' and not op.get('template_id') else self.editor(actual, state['nodes'])
                step['execution_status'] = 'returned'
                self.write(f'editor-{number:03d}.json', result)
                delta = differences(state['nodes'], result['nodes'])
                alpha_only = not any(delta.values()) and not self.alpha_equivalent(state['render_alpha'], result['render_alpha'])
                phase = 'save_readback'
                fence = result.get('save_fence')
                if result.get('content_write_started') is True and fence is None:
                    raise VerificationError('Content call lacks its pre-submit native save fence')
                saved_raw, saved = self.settle(result['nodes'], result['render_alpha'], 3 if alpha_only else 0, result['line_endpoints'], save_fence=fence)
                step['save_evidence'] = self.last_save_evidence
                if self.needs_native_persistence(state, result):
                    phase = 'native_persistence'
                    step['native_persistence'] = self.confirm_native_persistence(saved_raw, result, number,
                        self.affected_bindings(state['nodes'], result['nodes'], op))
                # Saving is a fact even if a later protection or reopen fails.
                self.uncertain = False
                step.update(save_status='confirmed', after_raw=saved, diff=delta,
                            before_render_alpha=state['render_alpha'], after_render_alpha=result['render_alpha'],
                            group_cache_normalizations=self.group_cache_evidence(saved_raw, result))
                phase = 'protection'
                self.verify_render_alpha(state, result, op)
                world_ids = self.verify_group_world(state, result, op)
                self.verify_group_world(state, self.last_saved_state, op)
                bindings = self.affected_bindings(state['nodes'], result['nodes'], op)
                self.verify_native_bindings(result, bindings)
                self.verify_native_bindings(self.last_saved_state, bindings)
                if op['kind'] == 'curve_point':
                    left, right = state.get('line_endpoints'), result.get('line_endpoints')
                    if not isinstance(left, dict) or not isinstance(right, dict) or left.keys() != right.keys() or any(
                            not point_equivalent(left[i].get(s), right[i].get(s)) for i in left for s in ('start', 'end')):
                        raise VerificationError('Curve point edit changed native endpoints')
                if op['kind'] == 'undo':
                    if not equivalent(result['nodes'], previous_delete['before']):
                        raise VerificationError('Undo did not restore the pre-delete projection')
                else:
                    check_scope(state['nodes'], result['nodes'], op, group_evidence={'before':state.get('object_bounds'), 'after':result.get('object_bounds')})
                step['raw_exceptions'] = check_raw_preservation(previous_delete['raw'] if op['kind'] == 'undo' else raw,
                    saved_raw, {'kind':'undo'} if op['kind'] == 'undo' else op,
                    group_evidence={'before':state.get('object_bounds'), 'after':result.get('object_bounds'),
                                    'native_before':state['nodes'], 'native_after':result['nodes'],
                                    'native_endpoints_before':state.get('line_endpoints',{}),
                                    'native_endpoints_after':result.get('line_endpoints',{}),
                                    'bindings_before':state.get('binding_geometry',[]),
                                    'bindings_after':result.get('binding_geometry',[])})
                # The immediate undo must use the same editor and undo receipt.
                immediate_undo = (op['kind'] == 'delete' and index + 1 < len(operations)
                                  and operations[index + 1].get('kind') == 'undo')
                if immediate_undo:
                    step['reopen_status'] = 'deferred_for_immediate_undo'
                else:
                    phase = 'reopen'
                    reopened = self.reopen_verified(saved_raw, result['nodes'], result['render_alpha'], result['line_endpoints'], bindings)
                    for ident in world_ids:
                        expected_world, actual_world = result['world_geometry'][ident], reopened.get('world_geometry', {}).get(ident)
                        if not isinstance(actual_world, dict) or set(actual_world) != set(expected_world) or any(
                                not finite_number(actual_world[key]) or abs(actual_world[key] - expected_world[key]) > 1e-3 for key in expected_world):
                            raise VerificationError('Fresh-page group member world geometry differs: ' + ident)
                        if any(abs(actual_world[key]-expected_world[key]) > 1e-6 for key in expected_world):
                            step.setdefault('world_reopen_precision', []).append({'id':ident,'before':expected_world,'reopened':actual_world})
                    self.write(f'reopened-{number:03d}.json', reopened)
                    if reopened.get('server_group_cache_catchup'):
                        step['server_group_cache_catchup'] = reopened['server_group_cache_catchup']
                    step.update(reopen_status='passed', verification_status='passed')
                    if op['kind'] == 'undo':
                        previous_delete['step'].update(verification_status='passed', reopen_status='verified_after_immediate_undo')
                previous_delete = {'before': state['nodes'], 'raw':raw, 'transaction_count': result['transaction_count'],
                                   'undo_receipt':result['undo_receipt'], 'step':step} if op['kind'] == 'delete' else None
            except Exception as error:
                if phase == 'execute' and getattr(error, 'content_write_started', None) is False and not step.get('append_submitted'):
                    step.update(save_status='not_written', execution_status='rejected_before_content_call')
                    self.uncertain = False
                phase = getattr(error, 'failure_phase', phase)
                step.update(verification_status='failed', failure_phase=phase, error=type(error).__name__)
                if previous_delete is not None and previous_delete['step'].get('verification_status') == 'pending':
                    previous_delete['step'].update(verification_status='failed', failure_phase='deferred_reopen')
                self.report.update(status='unverified', failure_phase=phase)
                raise
        self.report['status'] = 'verified'
        if self.request.get('capture_preview'):
            self.observe_saved()

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
            'z_index':max((n.get('z_index',0) for n in raw['nodes'] if not n.get('parent_id')), default=-1)+1,
            'x':min(sx,ex), 'y':min(sy,ey), 'width':abs(ex-sx), 'height':abs(ey-sy),
            'style':{'border_color':'#334155','border_style':'solid','border_width':'narrow'},
            'connector':{'shape':'straight',
                'start':{'position':{'x':sx,'y':sy},'arrow_style':'none'},
                'end':{'position':{'x':ex,'y':ey},'arrow_style':'line_arrow'}}}]}
        step = len(self.report['steps'])
        filename = f'connect-input-{step:03d}.json'
        receipt_name = f'connect-receipt-{step:03d}.json'
        key = str(uuid.uuid4())
        receipt = {'idempotent_token':key, 'before_raw':name, 'operation':op,
                   'status':'submitted_once'}
        self.write(filename, payload)
        self.write(receipt_name, receipt)
        record = self.report['steps'][-1]
        record['append_submitted'] = True
        self.command(['whiteboard', '+update', '--whiteboard-token', self.request['whiteboard_token'],
                      '--input_format','raw','--source','@'+filename,'--idempotent-token',key,'--as','user'])
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                latest, after_name = self.export()
                mapping = match_append(projection(raw), projection(latest), projection(payload))
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
        self.uncertain = False
        record.update(save_status='confirmed', append_after_raw=after_name, append_id=ident)
        try:
            check_raw_preservation(raw, latest, {'kind':'append'})
        except Exception as error:
            error.failure_phase = 'append_protection'
            raise
        receipt.update(created_id=ident, appended_raw=after_name, status='appended_readback_verified')
        self.write(f'connect-appended-{step:03d}.json', receipt)
        # Reload only this owned page so a cached pre-append board cannot write.
        self.complete_page(False, 'connection_append_reload')
        self.open_page()
        self.hydrate(latest)
        self.editor({'kind':'enter'})
        loaded = self.hydrate(latest)
        self.uncertain = True
        record['save_status'] = 'unknown'
        try:
            result = self.editor({'kind':'reconnect','id':ident,
                                  'start_id':op['start_id'],'end_id':op['end_id']}, loaded['nodes'])
        except Exception as error:
            if getattr(error, 'content_write_started', None) is False:
                self.uncertain = False
                record['save_status'] = 'confirmed'
            raise
        return result

    def append(self, filename):
        validate_target(self.request)
        if self.request.get('operations'):
            raise ValueError('Append is standalone; inspect the saved board in a new editor session before editing')
        payload = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
        nodes = payload.get('nodes') if isinstance(payload, dict) else None
        if not isinstance(nodes, list) or not nodes or any(not isinstance(n, dict) or not isinstance(n.get('id'), str) or not n['id'] for n in nodes):
            raise ValueError('Append requires native objects with nonempty string IDs')
        ids = [n['id'] for n in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError('Append requires nonempty unique IDs')
        if any(type(n.get('z_index', 0)) is not int or n.get('z_index', 0) < 0 for n in nodes):
            raise ValueError('Append relative layers must be nonnegative integers')
        shape_lookup = {n['id']:n for n in nodes if n.get('type') == 'composite_shape'}
        for n in nodes:
            if n.get('type') not in ('composite_shape', 'text_shape', 'connector'):
                raise ValueError('Append only supports native shapes, text shapes and bound connectors')
            if n['type'] in ('composite_shape', 'text_shape') and not isinstance(n.get('text', {}).get('text'), str):
                raise ValueError('Native shapes must own their text')
            if (not all(finite_number(n.get(field)) for field in ('x','y','width','height'))
                    or n['width'] < 0 or n['height'] < 0
                    or n['type'] != 'connector' and (n['width'] == 0 or n['height'] == 0)):
                raise ValueError('Append geometry must be finite and have valid dimensions')
            if n['type'] == 'connector':
                c = n['connector']
                for side in ('start','end'):
                    endpoint = c.get(side + '_object', {})
                    if endpoint.get('id') not in ids:
                        raise ValueError('CLI append cannot reference existing shapes; append new shapes first, then use editor connect for existing modules')
                    if (endpoint.get('id') not in shape_lookup or endpoint != c.get(side, {}).get('attached_object')
                            or not isinstance(endpoint.get('position'), dict)
                            or set(endpoint['position']) != {'x','y'}
                            or any(not finite_number(endpoint['position'][axis]) or not 0 <= endpoint['position'][axis] <= 1 for axis in ('x','y'))):
                        raise ValueError('Append connector has missing or conflicting native shape endpoint')
                start,end = (shape_lookup[c[side + '_object']['id']] for side in ('start','end'))
                sp,ep = (c[side + '_object']['position'] for side in ('start','end'))
                sx,sy = start['x']+start['width']*sp['x'], start['y']+start['height']*sp['y']
                ex,ey = end['x']+end['width']*ep['x'],end['y']+end['height']*ep['y']
                if not equivalent([n['x'],n['y'],n['width'],n['height']], [min(sx,ex),min(sy,ey),abs(ex-sx),abs(ey-sy)]):
                    raise ValueError('Connector geometry is stale or uses unsupported anchors')
        raw, name = self.export()
        before = projection(raw)
        if set(ids) & {n['id'] for n in before}:
            raise ValueError('Append IDs collide with existing IDs')
        # The service inserts at z_index and shifts old objects above that slot.
        # Place new roots above all existing roots, retaining their relative order.
        layers = [n.get('z_index',0) for n in raw['nodes'] if not n.get('parent_id')]
        if any(type(z) is not int or z < 0 for z in layers):
            raise VerificationError('Existing root layers must be valid before appending')
        first_layer = max(layers, default=-1)+1
        ordered = sorted(enumerate(nodes), key=lambda pair:(pair[1].get('z_index',0),pair[0]))
        layer_assignment = {}
        for offset, (_, node) in enumerate(ordered):
            node['z_index'] = first_layer+offset
            layer_assignment[node['id']] = node['z_index']
        self.open_page()
        original = self.hydrate(raw)
        self.report.update(initial_raw=name, initial_nodes=original['nodes'], append_layer_assignment=layer_assignment)
        self.write('inspect-000.json', original)
        self.report['initial_inspect'] = 'inspect-000.json'
        intended = projection(payload)
        key = str(uuid.uuid4())
        self.write('append-input.json', payload)
        self.write('append-receipt.json', {'idempotent_token': key, 'before_raw': name})
        step = {'operation': {'kind':'append'}, 'before_raw':name, 'save_status':'unknown',
                'verification_status':'pending', 'failure_phase':None, 'execution_status':'submitted'}
        self.report.setdefault('steps', []).append(step)
        self.uncertain, phase = True, 'execute'
        try:
            self.command(['whiteboard', '+update', '--whiteboard-token', self.request['whiteboard_token'], '--input_format', 'raw', '--source', '@append-input.json', '--idempotent-token', key, '--as', 'user'])
            step['execution_status'] = 'returned'
            phase = 'save_readback'
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                try:
                    latest, after_name = self.export()
                    mapping = match_append(before, projection(latest), intended)
                    break
                except NotReady:
                    time.sleep(1)
                except VerificationError as error:
                    if 'count has not converged' not in str(error):
                        raise
                    time.sleep(1)
            else:
                raise VerificationError('Append save/readback did not converge; write was not retried')
            self.uncertain = False
            step.update(save_status='confirmed', after_raw=after_name, id_mapping=mapping)
            self.report.update(before_raw=name, after_raw=after_name, id_mapping=mapping)
            phase = 'protection'
            step['raw_exceptions'] = check_raw_preservation(raw, latest, {'kind':'append'})
            saved_lookup = {n['id']:n for n in latest['nodes']}
            if any(saved_lookup[mapping[ident]].get('z_index') != layer for ident,layer in layer_assignment.items()):
                raise VerificationError('Appended object layers differ from the planned top insertion')
            phase = 'reopen'
            self.complete_page(False, 'append_saved_reopen')
            self.open_page()
            fresh = self.hydrate(latest)
            self.write('reopened-001.json', fresh)
            old_ids = {n['id'] for n in original['nodes']}
            if not equivalent([n for n in fresh['nodes'] if n['id'] in old_ids], original['nodes']):
                raise VerificationError('Fresh-page append changed an original native object')
            old_alpha = {ident:value for ident,value in fresh.get('render_alpha', {}).items() if ident in old_ids}
            if not self.alpha_equivalent(old_alpha, original['render_alpha']):
                raise VerificationError('Fresh-page append changed original rendering alpha')
            added_ids = set(mapping.values())
            if {n['id'] for n in fresh['nodes']} != old_ids | added_ids:
                raise VerificationError('Fresh-page append object IDs do not match the saved mapping')
            for ident in added_ids:
                values = fresh.get('render_alpha', {}).get(ident)
                if not isinstance(values, dict) or not values or any(value != 1 for value in values.values()):
                    raise VerificationError('Appended native object has missing or nonopaque rendering alpha: ' + ident)
            bindings = self.affected_bindings(original['nodes'], fresh['nodes'], {'kind':'append'})
            self.verify_native_bindings(fresh, bindings)
            for ident, endpoints in original.get('line_endpoints', {}).items():
                if not equivalent(fresh.get('line_endpoints', {}).get(ident), endpoints):
                    raise VerificationError('Append changed an original native line endpoint')
            step.update(verification_status='passed', reopen_status='passed',
                        diff=differences(original['nodes'], fresh['nodes']), after_render_alpha=fresh['render_alpha'])
            self.report['status'] = 'verified'
            if self.request.get('capture_preview'):
                self.editor({'kind':'enter'})
                self.observe_saved()
        except Exception as error:
            step.update(verification_status='failed', failure_phase=phase, error=type(error).__name__)
            self.report.update(status='unverified', failure_phase=phase)
            raise

    def close(self):
        if self.task:
            try:
                self.complete_page(self.uncertain, 'unknown_writer' if self.uncertain else 'finished')
            except Exception:
                pass
        self.write('result.json', self.report)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--proxy-url', required=True)
    p.add_argument('--timeout', type=int, default=45)
    p.add_argument('--append-raw', help='Standalone native append; request operations must be empty')
    a = p.parse_args()
    runner = None
    code = 0
    try:
        request = json.loads(Path(a.request).read_text(encoding='utf-8-sig'))
        runner = Runner(request, a.output_dir, a.proxy_url, a.timeout)
        if a.append_raw:
            runner.append(a.append_raw)
        else:
            runner.run()
    except Exception as e:
        details = dict(status='unverified', error=type(e).__name__, reason=str(e) if isinstance(e, (VerificationError, ValueError)) else 'Transport or runtime failure; no automatic write retry')
        if runner is not None:
            runner.report.update(details)
        else:
            details.update(steps=[], save_status='not_written', verification_status='failed', failure_phase='preflight')
            destination = Path(a.output_dir)
            # Do not replace an existing run, even when initialization failed.
            if not destination.exists():
                destination.mkdir(parents=True, exist_ok=False)
                (destination / 'result.json').write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding='utf-8')
        code = 1
    finally:
        if runner is not None:
            runner.close()
    print(json.dumps({'status': runner.report['status'] if runner is not None else 'unverified', 'result': str(Path(a.output_dir) / 'result.json')}, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
