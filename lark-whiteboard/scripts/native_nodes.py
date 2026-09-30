"""Compile a small native diagram; labels belong to their shapes."""
import argparse
import json
import math
from pathlib import Path


def compile_diagram(spec):
    nodes, shapes, used = [], {}, set()
    existing = {item['id'] for item in spec.get('existing_shapes', [])}
    if existing:
        raise ValueError('CLI append cannot reference existing shapes; append new shapes first, then use editor connect with an existing line template')
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
        if not isinstance(size, (int, float)) or not math.isfinite(size) or size <= 0:
            raise ValueError('font_size must be positive and finite')
        if not isinstance(item.get('text', ''), str):
            raise ValueError('text must be a string')
        node = dict(id=ident, type='composite_shape', composite_shape={'type': shape}, angle=0, z_index=1, **geometry)
        node['style'] = dict(border_color='#2457a7', border_color_type=1, border_opacity=100, border_style='solid', border_width='narrow', fill_color='#e8f0fe', fill_color_type=1, fill_opacity=100)
        node['text'] = dict(text=item.get('text', ''), font_size=size, angle=0, font_weight='regular', horizontal_align='center', vertical_align='mid', italic=False, line_through=False, underline=False, text_color='#1f2329', text_color_type=1, text_background_color_type=0, theme_text_background_color_code=-1)
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
        x, y = start['x'] + start['width'], start['y'] + start['height'] / 2
        ex, ey = end['x'], end['y'] + end['height'] / 2
        if ex < x or ey < y:
            raise ValueError('Initial connectors require a target to the right and not above the source; reposition through the editor later')
        a = dict(id=start['id'], position=dict(x=1, y=0.5), snap_to='right')
        b = dict(id=end['id'], position=dict(x=0, y=0.5), snap_to='left')
        nodes.append(dict(id=ident, type='connector', angle=0, z_index=2, x=x, y=y, width=ex-x, height=ey-y,
                          style=dict(border_color='#000000', border_color_type=0, border_opacity=100, border_style='solid', border_width='narrow', theme_border_color_code=-1),
                          connector=dict(shape='straight', specified_coordinate=True, caption_auto_direction=False, start_object=a, end_object=b, start=dict(arrow_style='none', attached_object=a), end=dict(arrow_style='line_arrow', attached_object=b), turning_points=[])))
    return {'nodes': nodes}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    result = compile_diagram(json.loads(Path(a.input).read_text(encoding='utf-8-sig')))
    with Path(a.output).open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
