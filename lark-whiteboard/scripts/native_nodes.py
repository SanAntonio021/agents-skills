"""Compile a native whiteboard diagram manifest into Feishu RAW nodes.

The public :func:`compile_diagram` accepts the original ``shapes`` /
``connectors`` input and a newer ``nodes`` / ``anchors`` / ``connections`` /
``groups`` manifest.  Both forms produce the same native RAW shape.
"""
import argparse
import json
import math
import re
from pathlib import Path


SHAPES = {
    'rect': 'rect',
    'round_rect': 'round_rect',
    'ellipse': 'ellipse',
    'diamond': 'diamond',
    'parallelogram': 'parallelogram',
}
LINE_SHAPES = ('straight', 'right_angled_polyline')
LINE_STYLES = ('solid', 'dash', 'dot')
ARROW_STYLES = (
    'none', 'line_arrow', 'triangle_arrow', 'empty_triangle_arrow',
    'circle_arrow', 'empty_circle_arrow', 'diamond_arrow',
    'empty_diamond_arrow', 'single_arrow', 'multi_arrow',
    'exact_single_arrow', 'zero_or_single_arrow',
    'single_or_multi_arrow', 'zero_or_multi_arrow', 'x_arrow',
)
ANCHOR_SIDES = ('left', 'right', 'top', 'bottom')
DEFAULT_STYLE = {
    'border_color': '#2457a7',
    'border_color_type': 1,
    'border_opacity': 100,
    'border_style': 'solid',
    'border_width': 'narrow',
    'fill_color': '#e8f0fe',
    'fill_color_type': 1,
    'fill_opacity': 100,
}
TEXT_DEFAULTS = {
    'font_size': 20,
    'angle': 0,
    'font_weight': 'regular',
    'horizontal_align': 'center',
    'vertical_align': 'mid',
    'italic': False,
    'line_through': False,
    'underline': False,
    'text_color': '#1f2329',
    'text_color_type': 1,
    'text_background_color_type': 0,
    'theme_text_background_color_code': -1,
}
COLOR_KEYS = ('border_color', 'fill_color', 'text_color')


def _obj(value, name):
    if not isinstance(value, dict):
        raise ValueError(name + ' must be an object')
    return value


def _list(value, name):
    if not isinstance(value, list):
        raise ValueError(name + ' must be an array')
    return value


def _string(value, name, *, empty=False):
    if not isinstance(value, str) or (not empty and not value):
        raise ValueError(name + ' must be a nonempty string' if not empty else name + ' must be a string')
    return value


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ' must be a finite number')
    if positive and value <= 0:
        raise ValueError(name + ' must be positive')
    return value


def _bool(value, name):
    if type(value) is not bool:
        raise ValueError(name + ' must be a boolean')
    return value


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Colors must be #RRGGBB')
    return value


def _anchor_value(node, value, default):
    if value is None:
        value = {'side': default}
    value = _obj(value, 'anchor')
    side, offset = value.get('side', default), value.get('offset', 0.5)
    if side not in ANCHOR_SIDES:
        raise ValueError('Anchor side must be left, right, top or bottom')
    offset = _number(offset, 'Anchor offset')
    if not 0 <= offset <= 1:
        raise ValueError('Anchor offset must be in [0, 1]')
    px, py = {'left': (0, offset), 'right': (1, offset),
              'top': (offset, 0), 'bottom': (offset, 1)}[side]
    return (dict(id=node['id'], position=dict(x=px, y=py), snap_to=side),
            (node['x'] + px * node['width'], node['y'] + py * node['height']))


def anchor(node, value, default):
    """Compatibility wrapper for the original native compiler API."""
    return _anchor_value(node, value, default)


def _style(item):
    style = dict(DEFAULT_STYLE)
    for key in ('border_color', 'fill_color'):
        if key in item:
            style[key] = color(item[key])
    if 'border_style' in item:
        if item['border_style'] not in LINE_STYLES:
            raise ValueError('border_style must be solid, dash or dot')
        style['border_style'] = item['border_style']
    if 'border_width' in item:
        if item['border_width'] not in ('extra_narrow', 'narrow', 'medium', 'bold'):
            raise ValueError('Unsupported border_width')
        style['border_width'] = item['border_width']
    return style


def _text(item):
    text = dict(TEXT_DEFAULTS)
    text['text'] = item.get('text', '')
    if not isinstance(text['text'], str):
        raise ValueError('text must be a string')
    if 'font_size' in item:
        text['font_size'] = _number(item['font_size'], 'font_size', positive=True)
    if 'text_color' in item:
        text['text_color'] = color(item['text_color'])
    return text


def _shape_record(item, *, group_id=None):
    ident = _string(item.get('id'), 'Shape id')
    shape = item.get('shape', 'rect')
    if shape not in SHAPES:
        raise ValueError('Unsupported native shape: ' + str(shape))
    geometry = {key: _number(item.get(key), key) for key in ('x', 'y', 'width', 'height')}
    if geometry['width'] <= 0 or geometry['height'] <= 0:
        raise ValueError('Shape dimensions must be positive')
    node = dict(id=ident, type='composite_shape', composite_shape={'type': SHAPES[shape]},
                angle=0, z_index=item.get('z_index', 1), **geometry)
    node['style'] = _style(item)
    node['text'] = _text(item)
    if group_id is not None:
        node['_group_id'] = group_id
    return node


def _text_record(item, *, group_id=None):
    ident = _string(item.get('id'), 'Text id')
    geometry = {key: _number(item.get(key), key) for key in ('x', 'y', 'width', 'height')}
    if geometry['width'] <= 0 or geometry['height'] <= 0:
        raise ValueError('Text dimensions must be positive')
    node = dict(id=ident, type='text_shape', angle=0, z_index=item.get('z_index', 1), **geometry)
    node['text'] = _text(item)
    if group_id is not None:
        node['_group_id'] = group_id
    return node


def _connector_record(item, shapes, ports=None):
    ident = _string(item.get('id'), 'Connection id')
    start_id, end_id = _string(item.get('start_id'), 'Connection start_id'), _string(item.get('end_id'), 'Connection end_id')
    if start_id not in shapes or end_id not in shapes:
        raise ValueError('Connections must reference shapes in the same manifest')
    if start_id == end_id:
        raise ValueError('Self connectors are not supported')
    start, end = shapes[start_id], shapes[end_id]

    def endpoint(shape, key, id_key):
        value = item.get(key)
        port_id = item.get(id_key)
        if port_id:
            if not isinstance(value, dict):
                value = {}
            declared = (ports or {}).get(shape['id'], {}).get(port_id)
            if declared is None:
                raise ValueError('Connection references an unknown port: ' + port_id)
            value = dict(declared, **value)
        return value

    a, (x, y) = _anchor_value(start, endpoint(start, 'start_anchor', 'start_port'), 'right')
    b, (ex, ey) = _anchor_value(end, endpoint(end, 'end_anchor', 'end_port'), 'left')
    line_shape = item.get('shape', 'straight')
    if line_shape not in LINE_SHAPES:
        raise ValueError('Connector shape must be straight or right_angled_polyline')
    line_style = item.get('border_style', 'solid')
    if line_style not in LINE_STYLES:
        raise ValueError('Connector border_style must be solid, dash or dot')
    start_arrow, end_arrow = item.get('start_arrow', 'none'), item.get('end_arrow', 'line_arrow')
    if start_arrow not in ARROW_STYLES or end_arrow not in ARROW_STYLES:
        raise ValueError('Unsupported connector arrow style')
    line_color = color(item.get('border_color', '#000000'))
    node = dict(
        id=ident, type='connector', angle=0, z_index=item.get('z_index', 2),
        x=min(x, ex), y=min(y, ey), width=abs(ex - x), height=abs(ey - y),
        style=dict(border_color=line_color, border_color_type=1, border_opacity=100,
                   border_style=line_style, border_width='narrow'),
        connector=dict(
            shape=line_shape, specified_coordinate=True, caption_auto_direction=False,
            start_object=a, end_object=b,
            start=dict(arrow_style=start_arrow, attached_object=a),
            end=dict(arrow_style=end_arrow, attached_object=b), turning_points=[],
        ),
    )
    if 'label' in item:
        if not isinstance(item['label'], str):
            raise ValueError('label must be a string')
        label = dict(text=item['label'], font_size=18, text_color=line_color, text_color_type=1)
        if 'label_position' in item:
            label['caption_position'] = _number(item['label_position'], 'label_position')
            if not 0 <= label['caption_position'] <= 1:
                raise ValueError('label_position must be in [0, 1]')
        node['connector']['captions'] = {'data': [label]}
    return node


def normalise_manifest(spec):
    """Return a stable graph from either the legacy or the manifest input."""
    spec = _obj(spec, 'Diagram manifest')
    legacy_shapes = spec.get('shapes')
    legacy_connectors = spec.get('connectors')
    if legacy_shapes is None and legacy_connectors is None:
        # New manifest: nodes select shape/text; anchors name reusable ports.
        raw_nodes = _list(spec.get('nodes', []), 'nodes')
        anchors = spec.get('anchors', {})
        if not isinstance(anchors, dict):
            raise ValueError('anchors must be an object keyed by shape id')
        groups = _list(spec.get('groups', []), 'groups')
        group_ids = set()
        for group in groups:
            group = _obj(group, 'group')
            gid = _string(group.get('id'), 'Group id')
            if gid in group_ids:
                raise ValueError('Group IDs must be unique')
            group_ids.add(gid)
            _list(group.get('members', []), 'Group members')
        group_members = {}
        for group in groups:
            for member in group.get('members', []):
                member = _string(member, 'Group member')
                if member in group_members:
                    raise ValueError('A node can belong to only one container group')
                group_members[member] = group['id']
        node_records = []
        shapes = {}
        port_map = {}
        for item in raw_nodes:
            item = _obj(item, 'node')
            kind = item.get('type', item.get('kind', 'shape'))
            if kind not in ('shape', 'text'):
                raise ValueError('Only shape and text nodes belong in the node list')
            gid = group_members.get(item.get('id'))
            record = _shape_record(item, group_id=gid) if kind == 'shape' else _text_record(item, group_id=gid)
            if gid is not None:
                record.pop('_group_id', None)
            if kind == 'shape':
                if record['id'] in shapes:
                    raise ValueError('Shape IDs must be unique')
                shapes[record['id']] = record
            node_records.append(record)
            for port in _list(item.get('ports', []), 'ports'):
                port = _obj(port, 'port')
                side = port.get('side')
                offset = _number(port.get('offset', 0.5), 'port offset')
                if side not in ANCHOR_SIDES or not 0 <= offset <= 1:
                    raise ValueError('Invalid shape port')
                port_map.setdefault(record['id'], {})[_string(port.get('id'), 'port id')] = {'side': side, 'offset': offset}
        if any(ident not in {n['id'] for n in node_records} for ident in group_members):
            raise ValueError('Group references an unknown node')
        connectors = _list(spec.get('connections', []), 'connections')
        group_meta = [{'id': g['id'], 'label': g.get('label', ''), 'members': list(g['members'])} for g in groups]
    else:
        node_records = []
        port_map, group_meta = {}, []
        shapes = {}
        # Legacy input is intentionally normalised through the same records.
        for item in _list(legacy_shapes or [], 'shapes'):
            item = _obj(item, 'shape')
            record = _shape_record(item)
            node_records.append(record)
            shapes[record['id']] = record
        connectors = _list(legacy_connectors or [], 'connectors')
        anchors = {}

    used = {node['id'] for node in node_records}
    if len(used) != len(node_records):
        raise ValueError('Node IDs must be unique')
    connector_records = []
    for item in connectors:
        item = _obj(item, 'connection')
        record = _connector_record(item, shapes, port_map)
        if record['id'] in used:
            raise ValueError('Connection IDs must not reuse node IDs')
        used.add(record['id'])
        connector_records.append(record)
    return node_records + connector_records, port_map, group_meta


def compile_diagram(spec):
    """Compile a manifest to Feishu RAW nodes; existing shapes are not accepted."""
    spec = _obj(spec, 'Diagram manifest')
    existing = {item.get('id') for item in _list(spec.get('existing_shapes', []), 'existing_shapes')}
    if existing:
        raise ValueError('CLI append cannot reference existing shapes; append new shapes first, then use editor connect with an optional line template')
    nodes, ports, groups = normalise_manifest(spec)
    # Normalisation returns manifest metadata for callers that need it, but the
    # CLI append payload must remain exactly a native nodes object.
    return {'nodes': nodes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    source = json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
    result = compile_diagram(source)
    with Path(args.output).open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
