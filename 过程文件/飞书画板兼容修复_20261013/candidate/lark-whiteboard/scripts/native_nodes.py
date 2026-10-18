"""Compile a small native diagram; labels belong to their shapes."""
import argparse
import json
import math
import re
from pathlib import Path


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Colors must be #RRGGBB')
    return value


def anchor(node, value, default):
    if value is None:
        value = {'side': default}
    if not isinstance(value, dict):
        raise ValueError('Anchor must be an object or null')
    side, offset = value.get('side', default), value.get('offset', 0.5)
    if side not in ('left', 'right', 'top', 'bottom') or isinstance(offset, bool) or not isinstance(offset, (int, float)) or not 0 <= offset <= 1:
        raise ValueError('Anchor needs a side and offset in [0, 1]')
    px, py = {'left': (0, offset), 'right': (1, offset), 'top': (offset, 0), 'bottom': (offset, 1)}[side]
    return dict(id=node['id'], position=dict(x=px, y=py), snap_to=side), (node['x'] + px * node['width'], node['y'] + py * node['height'])


def compile_diagram(spec):
    nodes, shapes, used = [], {}, set()
    existing = {item['id'] for item in spec.get('existing_shapes', [])}
    if existing:
        raise ValueError('CLI append cannot reference existing shapes; append new shapes first, then use editor connect with an optional line template')
    for item in spec.get('shapes', []):
        ident = item['id']
        if not isinstance(ident, str) or not ident or ident in used:
            raise ValueError('Shape IDs must be nonempty and unique')
        used.add(ident)
        shape = item.get('shape', 'rect')
        if shape not in ('rect', 'round_rect'):
            raise ValueError('Only rect and round_rect are supported')
        geometry = {k: item[k] for k in ('x', 'y', 'width', 'height')}
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in geometry.values()):
            raise ValueError('Geometry must be finite numbers')
        if geometry['width'] <= 0 or geometry['height'] <= 0:
            raise ValueError('Shape dimensions must be positive')
        size = item.get('font_size', 20)
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not math.isfinite(size) or size <= 0:
            raise ValueError('font_size must be positive and finite')
        if not isinstance(item.get('text', ''), str):
            raise ValueError('text must be a string')
        node = dict(id=ident, type='composite_shape', composite_shape={'type': shape}, angle=0, z_index=1, **geometry)
        node['style'] = dict(border_color='#2457a7', border_color_type=1, border_opacity=100, border_style='solid', border_width='narrow', fill_color='#e8f0fe', fill_color_type=1, fill_opacity=100)
        node['text'] = dict(text=item.get('text', ''), font_size=size, angle=0, font_weight='regular', horizontal_align='center', vertical_align='mid', italic=False, line_through=False, underline=False, text_color='#1f2329', text_color_type=1, text_background_color_type=0, theme_text_background_color_code=-1)
        for key in ('border_color', 'fill_color'):
            if key in item:
                node['style'][key] = color(item[key])
        if 'text_color' in item:
            node['text']['text_color'] = color(item['text_color'])
        nodes.append(node)
        shapes[ident] = node
    for item in spec.get('connectors', []):
        ident = item['id']
        if not isinstance(ident, str) or not ident or ident in used:
            raise ValueError('Connector IDs must be nonempty and unique')
        used.add(ident)
        start, end = shapes[item['start_id']], shapes[item['end_id']]
        if start['id'] == end['id']:
            raise ValueError('Self connectors are not supported')
        a, (x, y) = anchor(start, item.get('start_anchor'), 'right')
        b, (ex, ey) = anchor(end, item.get('end_anchor'), 'left')
        line_shape, line_style = item.get('shape', 'straight'), item.get('border_style', 'solid')
        if line_shape not in ('straight', 'right_angled_polyline'):
            raise ValueError('Connector shape must be straight or right_angled_polyline')
        if line_style not in ('solid', 'dash', 'dot'):
            raise ValueError('Connector border_style must be solid, dash or dot')
        node = dict(id=ident, type='connector', angle=0, z_index=2, x=min(x, ex), y=min(y, ey), width=abs(ex-x), height=abs(ey-y),
                    style=dict(border_color=color(item.get('border_color', '#000000')), border_color_type=1, border_opacity=100, border_style=line_style, border_width='narrow'),
                    connector=dict(shape=line_shape, specified_coordinate=True, caption_auto_direction=False, start_object=a, end_object=b, start=dict(arrow_style='none', attached_object=a), end=dict(arrow_style='line_arrow', attached_object=b), turning_points=[]))
        if 'label' in item:
            if not isinstance(item['label'], str):
                raise ValueError('label must be a string')
            node['connector']['captions'] = {'data': [dict(text=item['label'], font_size=18, text_color=color(item.get('border_color', '#000000')), text_color_type=1)]}
        nodes.append(node)
    return {'nodes': nodes}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    result = compile_diagram(json.loads(Path(a.input).read_text(encoding='utf-8-sig')))
    with Path(a.output).open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
