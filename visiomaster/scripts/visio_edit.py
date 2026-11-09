"""Inspect and edit existing VSDX objects without rebuilding the document."""
from __future__ import annotations

import argparse
import contextlib
import gc
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor' / 'vsdx'))
from vsdx import VisioFile, namespace as NS


@contextlib.contextmanager
def safe_package(path):
    # Upstream close_vsdx removes the path without its extension. Always isolate
    # even read-only package access so a user's same-name folder is untouched.
    with tempfile.TemporaryDirectory(prefix='visiomaster-package-') as folder:
        copy = Path(folder) / 'input.vsdx'
        copy.write_bytes(Path(path).read_bytes())
        with VisioFile(str(copy)) as package:
            yield package

CORE = ('PinX', 'PinY', 'Width', 'Height', 'LocPinX', 'LocPinY', 'Angle',
        'BeginX', 'BeginY', 'EndX', 'EndY', 'FlipX', 'FlipY',
        'TxtPinX', 'TxtPinY', 'TxtWidth', 'TxtHeight', 'TxtAngle',
        'LineColor', 'LineWeight', 'LinePattern', 'BeginArrow', 'EndArrow',
        'FillForegnd', 'FillBkgnd', 'FillPattern', 'HideText')
POSITION = {'PinX', 'PinY', 'BeginX', 'BeginY', 'EndX', 'EndY', 'Angle'}
GEOMETRY = POSITION | {'Width', 'Height', 'LocPinX', 'LocPinY',
                       'TxtPinX', 'TxtPinY', 'TxtWidth', 'TxtHeight'}
LINE_STYLE = {'LinePattern', 'BeginArrow', 'EndArrow'}
OPEN_HIDDEN = 64 + 128 + 256  # hidden, macros disabled, no workspace


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def key(page_id, shape_id):
    return f'{int(page_id)}:{int(shape_id)}'


def package_snapshot(path):
    """Read upstream shape identities, hierarchy and local XML cells, without mutation."""
    result = {'sha256': digest(path), 'pages': [], 'shapes': {}}
    with safe_package(path) as source:
        for page in source.pages:
            pid = int(page.page_id)
            result['pages'].append({'id': pid, 'name': page.name})
            def visit(shape, parent=None):
                ident = key(pid, shape.ID)
                element = shape.xml
                text = element.find(NS + 'Text')
                result['shapes'][ident] = {
                    'page_id': pid, 'id': int(shape.ID), 'parent': parent,
                    'name': element.get('NameU', ''), 'type': element.get('Type', ''),
                    'text': shape.text,
                    'simple_text': text is not None and all(
                        child.tag == NS + 'cp' and child.get('IX', '0') == '0'
                        for child in text),
                    'local_cells': {c.get('N'): c.get('F', c.get('V'))
                                    for c in element.findall(NS + 'Cell')},
                }
                for child in shape.child_shapes:
                    visit(child, ident)
            for shape in page.child_shapes:
                visit(shape)
    return result


@contextlib.contextmanager
def visio():
    import pythoncom
    import win32com.client
    # pywin32 initializes the main Python thread. Do not uninitialize COM while
    # caller-owned shape proxies are still alive (notably across test contexts).
    app = session = None
    try:
        app = win32com.client.DispatchEx('Visio.Application')
        app.Visible = False
        app.AlertResponse = 7
        class Session:
            def __getattr__(self, name):
                return getattr(self.application, name)
        session = Session()
        session.application = app
        yield session
    except BaseException as exc:
        # Failed operations retain shape proxies through their traceback frames.
        # Release unwound frames before shutting down their COM server.
        import traceback
        traceback.clear_frames(exc.__traceback__)
        raise
    finally:
        if app is not None:
            for index in range(app.Documents.Count, 0, -1):
                document = app.Documents.Item(index)
                document.Saved = True
                document.Close()
                document = None
            gc.collect()
            app.Quit()
            if session is not None:
                session.application = None
        app = None
        gc.collect()


def all_shapes(page):
    def descend(shape, parent):
        yield shape, parent
        for i in range(1, shape.Shapes.Count + 1):
            yield from descend(shape.Shapes.Item(i), shape.ID)
    for i in range(1, page.Shapes.Count + 1):
        yield from descend(page.Shapes.Item(i), None)


def pages(document):
    return [document.Pages.Item(i) for i in range(1, document.Pages.Count + 1)]


def number(value):
    return round(float(value), 7)


def geometry(shape):
    result = []
    for section in range(10, 10 + shape.GeometryCount):
        rows = []
        for row in range(shape.RowCount(section)):
            cells = []
            # X/Y/A/B/C/D/E; row type distinguishes arcs, splines and line segments.
            for column in range(7):
                try:
                    cell = shape.CellsSRC(section, row, column)
                    cells.append({'formula': str(cell.FormulaU), 'value': number(cell.ResultIU)})
                except Exception:
                    cells.append(None)
            rows.append({'type': int(shape.RowType(section, row)), 'cells': cells})
        result.append(rows)
    return result


def text_formats(shape):
    """Effective per-character properties, preserving runs outside an edit range."""
    chars = shape.Characters
    result = []
    for position in range(chars.CharCount):
        chars.Begin, chars.End = position, position + 1
        row = chars.CharPropsRow(0)
        result.append({str(col): number(shape.CellsSRC(3, row, col).ResultIU)
                       for col in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 51)})
    return result


def custom_sections(shape):
    result = {}
    for section in (6, 7, 8, 9, 240, 241, 242, 243, 244):
        if not shape.SectionExists(section, 0):
            continue
        rows = []
        for row in range(shape.RowCount(section)):
            cells = {}
            for column in range(24):
                if shape.CellsSRCExists(section, row, column, 0):
                    cell = shape.CellsSRC(section, row, column)
                    cells[cell.Name] = str(cell.FormulaU)
            rows.append(cells)
        result[str(section)] = rows
    return result


def snapshot(document):
    result = {'pages': [], 'shapes': {}, 'connections': []}
    for page in pages(document):
        result['pages'].append({'id': page.ID, 'name': page.NameU,
                                'width': number(page.PageSheet.CellsU('PageWidth').ResultIU),
                                'height': number(page.PageSheet.CellsU('PageHeight').ResultIU)})
        for shape, parent in all_shapes(page):
            cells = {}
            for name in CORE:
                if shape.CellExistsU(name, 0):
                    cells[name] = number(shape.CellsU(name).ResultIU)
            chars = []
            for row in range(shape.RowCount(3)):
                chars.append({str(col): number(shape.CellsSRC(3, row, col).ResultIU)
                              for col in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 51)})
            paras = []
            for row in range(shape.RowCount(4)):
                paras.append([number(shape.CellsSRC(4, row, col).ResultIU) for col in range(8)])
            result['shapes'][key(page.ID, shape.ID)] = {
                'page_id': page.ID, 'id': shape.ID, 'parent': parent, 'name': shape.NameU,
                'type': int(shape.Type), 'one_d': bool(shape.OneD), 'text': str(shape.Text),
                'cells': cells, 'characters': chars, 'paragraphs': paras,
                'text_formats': text_formats(shape), 'custom': custom_sections(shape),
                'geometry': geometry(shape),
                'data': [str(shape.Data1), str(shape.Data2), str(shape.Data3)],
            }
        for index in range(1, page.Connects.Count + 1):
            connection = page.Connects.Item(index)
            result['connections'].append({'page_id': page.ID,
                'from_id': connection.FromSheet.ID, 'from_cell': connection.FromCell.Name,
                'to_id': connection.ToSheet.ID, 'to_cell': connection.ToCell.Name})
    result['connections'].sort(key=lambda item: json.dumps(item, sort_keys=True))
    return result


def resolve(document, operation, aliases):
    page = next((p for p in pages(document) if p.ID == int(operation['page_id'])), None)
    if page is None:
        raise ValueError(f"Page ID not found: {operation['page_id']}")
    sid = operation.get('shape_id')
    if isinstance(sid, str) and sid.startswith('$'):
        alias_page, sid = aliases[sid[1:]]
        if alias_page != page.ID:
            raise ValueError('Alias belongs to another page')
    shape = next((s for s, _ in all_shapes(page) if s.ID == int(sid)), None) if sid is not None else None
    if 'search_text' in operation:
        matches = [s for s, _ in all_shapes(page) if str(s.Text) == operation['search_text']]
        if len(matches) != 1 or shape is None or matches[0].ID != shape.ID:
            raise ValueError('Text search is ambiguous or disagrees with the explicit Shape ID')
    if operation['op'] != 'add' and shape is None:
        raise ValueError(f'Shape ID not found: {sid}')
    if shape is not None and 'expect_text' in operation and str(shape.Text) != operation['expect_text']:
        raise ValueError(f'Unexpected text on {page.ID}:{shape.ID}')
    return page, shape


def validate_plan(plan, source):
    if plan.get('version') != 1 or plan.get('input_sha256') != digest(source):
        raise ValueError('Plan version or input SHA-256 mismatch; inspect the actual input again')
    if not isinstance(plan.get('operations'), list) or not plan['operations']:
        raise ValueError('An ordered, nonempty operations list is required')
    allowed = {'text', 'font', 'move', 'resize', 'copy', 'add', 'delete', 'line'}
    common = {'op', 'page_id', 'shape_id', 'search_text', 'expect_text'}
    fields = {
        'text': {'text', 'start', 'end'}, 'font': {'font', 'size_pt', 'start', 'end'},
        'move': {'x', 'y', 'dx', 'dy', 'ordinary_links'},
        'resize': {'width', 'height', 'ordinary_links'},
        'copy': {'as', 'dx', 'dy', 'text'},
        'add': {'as', 'kind', 'box', 'points', 'text'},
        'delete': {'ordinary_links'},
        'line': {'points', 'begin', 'end', 'begin_glue', 'end_glue', 'start_arrow', 'end_arrow', 'line_pattern'},
    }
    if set(plan) - {'version', 'input_sha256', 'operations', 'backend', 'scene_sha256'}:
        raise ValueError('Unknown plan field')
    if plan.get('backend', 'com') not in ('com', 'vsdx'):
        raise ValueError('Unknown backend')
    def finite(value):
        if isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('All numbers must be finite')
    finite(plan)
    for operation in plan['operations']:
        if operation.get('op') not in allowed or 'page_id' not in operation:
            raise ValueError('Unknown operation or missing page_id')
        if operation['op'] != 'add' and 'shape_id' not in operation:
            raise ValueError('Every existing object requires an explicit Shape ID')
        if operation['op'] in ('move', 'resize', 'delete') and 'ordinary_links' not in operation:
            raise ValueError('Declare ordinary_links explicitly, including an empty list when none exist')
        kind = operation['op']
        if set(operation) - common - fields[kind]:
            raise ValueError('Unknown operation field')
        if type(operation['page_id']) is not int or operation['page_id'] < 0:
            raise ValueError('page_id must be a nonnegative integer')
        if 'shape_id' in operation and not (type(operation['shape_id']) is int and operation['shape_id'] > 0
                or isinstance(operation['shape_id'], str) and operation['shape_id'].startswith('$')):
            raise ValueError('shape_id must be a positive integer or an alias')
        if kind == 'text' and not isinstance(operation.get('text'), str):
            raise ValueError('text is required')
        if kind == 'font' and not ({'font', 'size_pt'} & operation.keys()):
            raise ValueError('Specify font or size_pt')
        if kind == 'move' and (not ({'x', 'y', 'dx', 'dy'} & operation.keys())
                or 'x' in operation and 'dx' in operation or 'y' in operation and 'dy' in operation):
            raise ValueError('Specify either absolute or relative coordinates per axis')
        if kind == 'resize' and not ({'width', 'height'} & operation.keys()):
            raise ValueError('Specify width or height')
        if kind in ('text', 'font') and (('start' in operation) != ('end' in operation)):
            raise ValueError('Both start and end are required for a text range')
        if 'ordinary_links' in operation and not isinstance(operation['ordinary_links'], list):
            raise ValueError('ordinary_links must be a list')
        for field in ('x', 'y', 'dx', 'dy', 'width', 'height', 'size_pt'):
            if field in operation and type(operation[field]) not in (int, float):
                raise ValueError(f'{field} must be numeric')
        for field in ('start', 'end') if kind in ('text', 'font') else ():
            if field in operation and (type(operation[field]) is not int or operation[field] < 0):
                raise ValueError('Text ranges require nonnegative integer offsets')
        def point(value):
            return isinstance(value, list) and len(value) == 2 and all(type(n) in (int, float) for n in value)
        if 'points' in operation and (not isinstance(operation['points'], list) or len(operation['points']) < 2 or not all(point(p) for p in operation['points'])):
            raise ValueError('points must contain at least two numeric coordinate pairs')
        if kind == 'line':
            if not (fields[kind] & operation.keys()):
                raise ValueError('Specify a line edit')
            if 'points' in operation and any(k in operation for k in ('begin', 'end', 'begin_glue', 'end_glue')):
                raise ValueError('Use points or endpoint edits in one operation, not both')
            for endpoint in ('begin', 'end'):
                if endpoint in operation and endpoint + '_glue' in operation:
                    raise ValueError('Use coordinates or glue for an endpoint, not both')
                if endpoint in operation and not point(operation[endpoint]):
                    raise ValueError('Line endpoints require a numeric coordinate pair')
                if endpoint + '_glue' in operation:
                    glue = operation[endpoint + '_glue']
                    if not isinstance(glue, dict) or set(glue) - {'shape_id', 'cell', 'position'} or 'shape_id' not in glue or ('cell' in glue and 'position' in glue):
                        raise ValueError('Invalid glue specification')
                    if 'position' in glue and (not point(glue['position']) or any(n < 0 or n > 1 for n in glue['position'])):
                        raise ValueError('Glue position must be a pair within [0, 1]')
            for field in ('start_arrow', 'end_arrow', 'line_pattern'):
                if field in operation and (type(operation[field]) is not int or operation[field] < 0):
                    raise ValueError('Arrow and line pattern codes must be nonnegative integers')
        for relation in operation.get('ordinary_links', []):
            if not isinstance(relation, dict) or set(relation) - {'shape_id', 'endpoints', 'label_ids'} or type(relation.get('shape_id')) is not int:
                raise ValueError('Invalid ordinary line relation')
            if not isinstance(relation.get('endpoints'), list) or not relation['endpoints'] or any(e not in ('begin', 'end') for e in relation['endpoints']):
                raise ValueError('Ordinary links require explicit begin/end endpoints')
            if not isinstance(relation.get('label_ids', []), list) or any(type(i) is not int for i in relation.get('label_ids', [])):
                raise ValueError('label_ids must be an integer list')
        if kind == 'add':
            if operation.get('kind') not in ('rectangle', 'ellipse', 'line', 'polyline'):
                raise ValueError('Unsupported basic shape kind')
            if operation['kind'] in ('rectangle', 'ellipse'):
                box = operation.get('box')
                if not isinstance(box, list) or len(box) != 4 or not all(type(n) in (int, float) for n in box) or box[0] >= box[2] or box[1] >= box[3]:
                    raise ValueError('box requires ordered left,bottom,right,top coordinates')
            elif 'points' not in operation:
                raise ValueError('Line creation requires points')


def set_cell(shape, name, value, unit=''):
    shape.CellsU(name).FormulaU = f'{float(value):.12g}{unit}'
    if abs(float(shape.CellsU(name).ResultIU) - float(value)) > 1e-6:
        raise ValueError(f'Visio did not accept {shape.ID}.{name}={value}')


def path_points(shape, points):
    if not shape.OneD or len(points) < 2:
        raise ValueError('Path editing requires a native 1D line and at least two points')
    if points[0] == points[-1]:
        raise ValueError('Coincident path endpoints are not supported')
    for name, value in zip(('BeginX', 'BeginY', 'EndX', 'EndY'), points[0] + points[-1]):
        set_cell(shape, name, value, ' in')
    # Row zero is the Geometry component (137), not a path segment.
    old_geometry = geometry(shape)
    if shape.GeometryCount > 1 or any(row['type'] not in (138, 139) for section in old_geometry for row in section[1:]):
        raise ValueError(f'Complex path on Shape {shape.ID}; cannot safely replace its geometry')
    if shape.GeometryCount:
        shape.DeleteSection(10)
    shape.AddSection(10)
    shape.AddRow(10, -2, 137)
    if old_geometry:
        for column, cell in enumerate(old_geometry[0][0]['cells']):
            if cell and cell['formula']:
                shape.CellsSRC(10, 0, column).FormulaU = cell['formula']
    px, py, lx, ly, angle = [shape.CellsU(n).ResultIU for n in ('PinX', 'PinY', 'LocPinX', 'LocPinY', 'Angle')]
    for i, (x, y) in enumerate(points):
        row = shape.AddRow(10, -2, 138 if i == 0 else 139)
        local_x = (x - px) * math.cos(angle) + (y - py) * math.sin(angle) + lx
        local_y = -(x - px) * math.sin(angle) + (y - py) * math.cos(angle) + ly
        shape.CellsSRC(10, row, 0).FormulaU = f'{local_x:.12g} in'
        shape.CellsSRC(10, row, 1).FormulaU = f'{local_y:.12g} in'
    actual = []
    for row in range(1, shape.RowCount(10)):
        x = shape.CellsSRC(10, row, 0).ResultIU - lx
        y = shape.CellsSRC(10, row, 1).ResultIU - ly
        actual.append((px + x * math.cos(angle) - y * math.sin(angle),
                       py + x * math.sin(angle) + y * math.cos(angle)))
    if len(actual) != len(points) or any(abs(a - b) > 1e-6 for left, right in zip(actual, points) for a, b in zip(left, right)):
        raise ValueError('Requested polyline path was not accepted')


def changed_fields(before, after):
    result = {}
    for ident in before.keys() | after.keys():
        left, right = before.get(ident), after.get(ident)
        if left is None or right is None:
            result[ident] = {'existence'}
            continue
        fields = {name for name in left.keys() | right.keys()
                  if name not in ('cells', 'custom') and left.get(name) != right.get(name)}
        fields |= {'cells.' + name for name in left['cells'].keys() | right['cells'].keys()
                   if left['cells'].get(name) != right['cells'].get(name)}
        flat = lambda s: {f'{section}.{row}.{cell}': value for section, rows in s.get('custom', {}).items() for row, cells in enumerate(rows) for cell, value in cells.items()}
        lc, rc = flat(left), flat(right)
        fields |= {'custom.' + name for name in lc.keys() | rc.keys() if lc.get(name) != rc.get(name)}
        if fields:
            result[ident] = fields
    return result


def check_preserved(before, after, allowed, additions, deletions, connection_ids):
    if before['pages'] != after['pages']:
        raise ValueError('Unexpected page changes')
    changes = changed_fields(before['shapes'], after['shapes'])
    for ident, fields in changes.items():
        if ident in additions or ident in deletions:
            continue
        unexpected = fields - allowed.get(ident, set())
        if unexpected:
            raise ValueError(f'Unrequested properties changed on {ident}: {sorted(unexpected)}')
    if set(after['shapes']) - set(before['shapes']) != additions:
        raise ValueError('Added Shape IDs differ from the operations list')
    if set(before['shapes']) - set(after['shapes']) != deletions:
        raise ValueError('Deleted Shape IDs differ from the operations list')
    unchanged = lambda s: [c for c in s['connections'] if key(c['page_id'], c['from_id']) not in connection_ids]
    if unchanged(before) != unchanged(after):
        raise ValueError('Unrequested connection relationship changed')
    return {ident: sorted(fields) for ident, fields in changes.items()}


def perform(document, plan):
    before = snapshot(document)
    allowed, additions, deletions, aliases, connection_ids, log = {}, set(), set(), {}, set(), []
    def permit(ident, fields):
        allowed.setdefault(ident, set()).update(fields)
    for index, operation in enumerate(plan['operations']):
        page, shape = resolve(document, operation, aliases)
        kind = operation['op']
        ident = key(page.ID, shape.ID) if shape is not None else None
        prior_ids = {key(page.ID, s.ID) for s, _ in all_shapes(page)}
        if shape is not None and shape.Type == 4:
            raise ValueError(f'{ident} is an embedded image; its internal content requires reconstruction')
        # Ordinary lines have no reliable ownership metadata. Require explicit endpoint/label edits.
        for relation in operation.get('ordinary_links', []):
            if not relation.get('endpoints') or any(e not in ('begin', 'end') for e in relation['endpoints']):
                raise ValueError('Ordinary links must explicitly name begin/end endpoints')
            related = [o for o in plan['operations'] if o['page_id'] == page.ID and o.get('shape_id') == relation['shape_id']]
            if not related or not any(o['op'] in ('line', 'delete') for o in related):
                raise ValueError('An ordinary linked line needs an explicit line/delete operation')
            for endpoint in relation.get('endpoints', []):
                if not any(o['op'] == 'delete' or 'points' in o or endpoint in o or endpoint + '_glue' in o for o in related):
                    raise ValueError(f'Ordinary line endpoint {endpoint} has no explicit edit')
            for label in relation.get('label_ids', []):
                if not any(o['page_id'] == page.ID and o.get('shape_id') == label and o['op'] in ('move', 'text', 'delete') for o in plan['operations']):
                    raise ValueError(f'Associated label {label} needs an explicit edit')
        if kind in ('move', 'resize', 'delete'):
            affected = {shape.ID}
            # Group descendants retain local coordinates; native connections may be on a child.
            def children(s):
                for child_index in range(1, s.Shapes.Count + 1):
                    child = s.Shapes.Item(child_index)
                    affected.add(child.ID)
                    children(child)
            children(shape)
            connections = [c for c in snapshot(document)['connections'] if c['page_id'] == page.ID and c['to_id'] in affected]
            for connection in connections:
                connector = key(page.ID, connection['from_id'])
                if kind == 'delete':
                    remaining = plan['operations'][index + 1:]
                    endpoint = 'begin' if connection['from_cell'] == 'BeginX' else 'end'
                    handled = any(o['page_id'] == page.ID and o.get('shape_id') == connection['from_id']
                                  and (o['op'] == 'delete' or o['op'] == 'line' and (endpoint in o or endpoint + '_glue' in o or 'points' in o)) for o in remaining)
                    if not handled:
                        raise ValueError('Delete requires a subsequent delete/reconnect of each native connector')
                permit(connector, {'geometry'} | {'cells.' + n for n in GEOMETRY})
                permit(connector, {'custom.9.0.Controls.TextPosition', 'custom.9.0.Controls.TextPosition.Y'})
        if kind == 'text':
            if shape.SectionExists(8, 0) and shape.RowCount(8):
                raise ValueError(f'Text fields on {ident} require manual review; not replacing them')
            formats_before = text_formats(shape)
            if 'start' in operation or 'end' in operation:
                original_text = str(shape.Text)
                if any(ord(c) > 0xffff for c in original_text + operation['text']):
                    raise ValueError('Partial edits of non-BMP text require manual review of Visio character offsets')
                chars = shape.Characters
                chars.Begin = int(operation['start'])
                chars.End = int(operation['end'])
                if not 0 <= chars.Begin <= chars.End <= len(formats_before):
                    raise ValueError('Text range out of bounds')
                chars.Text = operation['text']
                if str(shape.Text) != original_text[:operation['start']] + operation['text'] + original_text[operation['end']:] :
                    raise ValueError('Partial text replacement was not accepted')
                formats_after = text_formats(shape)
                suffix = len(formats_before) - operation['end']
                if formats_before[:operation['start']] != formats_after[:operation['start']] or (suffix and formats_before[-suffix:] != formats_after[-suffix:]):
                    raise ValueError('Rich text formatting outside the replacement changed')
            else:
                if len({json.dumps(f, sort_keys=True) for f in formats_before}) > 1:
                    raise ValueError('Rich text requires an explicit start/end replacement range')
                shape.Text = operation['text']
                if str(shape.Text) != operation['text']:
                    raise ValueError('Text replacement was not accepted')
                if formats_before and any(f != formats_before[0] for f in text_formats(shape)):
                    raise ValueError('Whole-text replacement changed character formatting')
            permit(ident, {'text', 'characters', 'text_formats'})
        elif kind == 'font':
            if 'start' in operation and any(ord(c) > 0xffff for c in str(shape.Text)):
                raise ValueError('Partial formatting of non-BMP text requires manual review of Visio character offsets')
            formats_before = text_formats(shape)
            chars = shape.Characters
            chars.Begin = int(operation.get('start', 0))
            chars.End = int(operation.get('end', chars.CharCount))
            if not 0 <= chars.Begin < chars.End <= len(formats_before):
                raise ValueError('Font range out of bounds')
            if 'font' in operation:
                font = operation['font']
                sys.path.insert(0, str(ROOT / 'vendor' / 'upstream' / 'scripts'))
                from font_utils import installed_font_match
                if not installed_font_match(font):
                    raise ValueError('Requested font is not installed')
                if any(c in font for c in '"\r\n'):
                    raise ValueError('Invalid font name')
                # Use both font slots; AsianFont is 51, not the underline column.
                if 'start' not in operation and 'end' not in operation:
                    for row in range(shape.RowCount(3)):
                        shape.CellsSRC(3, row, 0).FormulaU = f'FONT("{font}")'
                        shape.CellsSRC(3, row, 51).FormulaU = f'FONT("{font}")'
                    font_id = int(shape.CellsSRC(3, 0, 0).ResultIU)
                else:
                    # FONT() registers a font even when it was not used by this file.
                    old = shape.CellsU('Char.Font').FormulaU
                    shape.CellsU('Char.Font').FormulaU = f'FONT("{font}")'
                    font_id = int(shape.CellsU('Char.Font').ResultIU)
                    shape.CellsU('Char.Font').FormulaU = old
                    chars.CharProps(0, font_id)
                    chars.CharProps(51, font_id)
            if 'size_pt' in operation:
                size = float(operation['size_pt'])
                if size <= 0:
                    raise ValueError('Font size must be positive')
                if 'start' in operation or 'end' in operation:
                    if size != int(size):
                        raise ValueError('Partial-run font size requires integer points')
                    chars.CharProps(7, int(size))
                else:
                    for row in range(shape.RowCount(3)):
                        shape.CellsSRC(3, row, 7).FormulaU = f'{size} pt'
            formats_after = text_formats(shape)
            start, end = operation.get('start', 0), operation.get('end', len(formats_before))
            permitted = ({'0', '51'} if 'font' in operation else set()) | ({'7'} if 'size_pt' in operation else set())
            for i, (left, right) in enumerate(zip(formats_before, formats_after)):
                changed = {c for c in left if left[c] != right[c]}
                if changed - (permitted if start <= i < end else set()):
                    raise ValueError('Font edit changed unrequested character properties')
                if start <= i < end and 'size_pt' in operation and abs(right['7'] * 72 - operation['size_pt']) > 1e-5:
                    raise ValueError('Requested font size was not accepted')
            if 'font' in operation:
                for col in ('0', '51'):
                    for f in formats_after[start:end]:
                        if int(f[col]) != font_id:
                            raise ValueError('Requested font was substituted')
            permit(ident, {'characters', 'text_formats'})
        elif kind == 'move':
            for axis in ('x', 'y'):
                name = 'Pin' + axis.upper()
                if axis in operation or 'd' + axis in operation:
                    value = operation.get(axis, shape.CellsU(name).ResultIU + operation.get('d' + axis, 0))
                    set_cell(shape, name, value, ' in')
            permit(ident, {'cells.' + n for n in POSITION})
        elif kind == 'resize':
            descendant_before = {key(page.ID, s.ID): snapshot(document)['shapes'][key(page.ID, s.ID)]
                                 for s, _ in all_shapes(page) if s.ID in affected and s.ID != shape.ID}
            old_width, old_height = shape.CellsU('Width').ResultIU, shape.CellsU('Height').ResultIU
            for field, name in (('width', 'Width'), ('height', 'Height')):
                if field in operation:
                    if float(operation[field]) <= 0:
                        raise ValueError('Dimensions must be positive')
                    set_cell(shape, name, operation[field], ' in')
            if descendant_before:
                sx, sy = shape.CellsU('Width').ResultIU / old_width, shape.CellsU('Height').ResultIU / old_height
                descendant_after = snapshot(document)['shapes']
                for child_id, left in descendant_before.items():
                    right = descendant_after[child_id]
                    for names, scale in ((('PinX', 'Width', 'LocPinX', 'TxtPinX', 'TxtWidth'), sx),
                                         (('PinY', 'Height', 'LocPinY', 'TxtPinY', 'TxtHeight'), sy)):
                        for name in names:
                            if name in left['cells'] and abs(right['cells'][name] - left['cells'][name] * scale) > 1e-5:
                                raise ValueError(f'Group child {child_id} did not resize proportionally: {name}')
                    if len(left['geometry']) != len(right['geometry']):
                        raise ValueError(f'Group child {child_id} changed geometry structure')
                    for old_section, new_section in zip(left['geometry'], right['geometry']):
                        if len(old_section) != len(new_section):
                            raise ValueError(f'Group child {child_id} changed path structure')
                        for old_row, new_row in zip(old_section[1:], new_section[1:]):
                            if old_row['type'] not in (138, 139) or old_row['type'] != new_row['type']:
                                raise ValueError(f'Group child {child_id} has unsupported resize geometry')
                            for col, scale in ((0, sx), (1, sy)):
                                if abs(new_row['cells'][col]['value'] - old_row['cells'][col]['value'] * scale) > 1e-5:
                                    raise ValueError(f'Group child {child_id} changed path unexpectedly')
                    permit(child_id, {'geometry'} | {'cells.' + n for n in GEOMETRY})
            permit(ident, {'geometry'} | {'cells.' + n for n in GEOMETRY})
        elif kind in ('copy', 'add'):
            if not operation.get('as') or operation['as'] in aliases:
                raise ValueError('New objects require a unique as alias')
            if kind == 'copy':
                shape = shape.Duplicate()
                set_cell(shape, 'PinX', shape.CellsU('PinX').ResultIU + operation.get('dx', 0), ' in')
                set_cell(shape, 'PinY', shape.CellsU('PinY').ResultIU + operation.get('dy', 0), ' in')
            else:
                style = operation['kind']
                if style in ('rectangle', 'ellipse'):
                    shape = getattr(page, 'DrawRectangle' if style == 'rectangle' else 'DrawOval')(*operation['box'])
                elif style in ('line', 'polyline'):
                    points = operation['points']
                    shape = page.DrawLine(*points[0], *points[-1])
                    path_points(shape, points)
                else:
                    raise ValueError('Supported basic shapes: rectangle, ellipse, line, polyline')
            if 'text' in operation:
                shape.Text = operation['text']
            aliases[operation['as']] = (page.ID, shape.ID)
            additions.update({key(page.ID, s.ID) for s, _ in all_shapes(page)} - prior_ids)
        elif kind == 'delete':
            descendants = set()
            def collect(s):
                descendants.add(key(page.ID, s.ID))
                for i in range(1, s.Shapes.Count + 1):
                    collect(s.Shapes.Item(i))
            collect(shape)
            deletions.update(descendants - additions)
            additions.difference_update(descendants)
            connection_ids.update(descendants)
            shape.Delete()
        elif kind == 'line':
            if not shape.OneD:
                raise ValueError('Line operations require a 1D shape')
            if 'points' in operation:
                path_points(shape, operation['points'])
            for endpoint, prefix in (('begin', 'Begin'), ('end', 'End')):
                if endpoint in operation:
                    for axis, value in zip(('X', 'Y'), operation[endpoint]):
                        set_cell(shape, prefix + axis, value, ' in')
                if endpoint + '_glue' in operation:
                    glue = operation[endpoint + '_glue']
                    _, target = resolve(document, {'op': 'line', 'page_id': page.ID, 'shape_id': glue['shape_id']}, aliases)
                    target_key = key(page.ID, target.ID)
                    target_before = snapshot(document)['shapes'][target_key]
                    if 'position' in glue:
                        shape.CellsU(prefix + 'X').GlueToPos(target, *glue['position'])
                    else:
                        shape.CellsU(prefix + 'X').GlueTo(target.CellsU(glue.get('cell', 'PinX')))
                    linked = [c for c in snapshot(document)['connections'] if c['page_id'] == page.ID and c['from_id'] == shape.ID and c['from_cell'] == prefix + 'X']
                    if len(linked) != 1 or linked[0]['to_id'] != target.ID:
                        raise ValueError('Requested connector attachment was not accepted')
                    target_after = snapshot(document)['shapes'][target_key]
                    target_changes = changed_fields({target_key: target_before}, {target_key: target_after}).get(target_key, set())
                    if any(not field.startswith('custom.7.') for field in target_changes):
                        raise ValueError('Glue changed target properties beyond connection points')
                    permit(target_key, target_changes)
            for field, name in (('start_arrow', 'BeginArrow'), ('end_arrow', 'EndArrow'), ('line_pattern', 'LinePattern')):
                if field in operation:
                    set_cell(shape, name, operation[field])
            permit(ident, {'geometry'} | {'cells.' + n for n in GEOMETRY | LINE_STYLE})
            connection_ids.add(ident)
        log.append({'index': index, 'op': kind, 'target': ident, 'aliases': dict(aliases)})
    after = snapshot(document)
    if any(key(c['page_id'], c['to_id']) not in after['shapes'] or key(c['page_id'], c['from_id']) not in after['shapes'] for c in after['connections']):
        raise ValueError('A connector points at a deleted object')
    changes = check_preserved(before, after, allowed, additions, deletions, connection_ids)
    if not changes:
        raise ValueError('No effective object change')
    return before, after, changes, log


def export(document, basename):
    from PIL import Image
    outputs = []
    for page in pages(document):
        path = Path(str(basename) + f'.page-{page.ID}.png')
        if path.exists():
            raise FileExistsError(path)
        page.Export(str(path))
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError(f'Missing or empty PNG export: {path}')
        with Image.open(path) as image:
            image.verify()
        outputs.append(path)
    return outputs


def pixel_changes(before, after):
    from PIL import Image, ImageChops
    result = []
    for left, right in zip(before, after):
        with Image.open(left) as a, Image.open(right) as b:
            a, b = a.convert('RGB'), b.convert('RGB')
            bbox = None if a.size != b.size else ImageChops.difference(a, b).getbbox()
            result.append({'before_size': a.size, 'after_size': b.size,
                           'changed': a.size != b.size or bbox is not None, 'bbox': bbox})
    if not any(item['changed'] for item in result):
        raise ValueError('No visible pixel change; do not claim a successful revision')
    return result


def scene_guard_path(scene):
    return Path(str(scene) + '.visio-edits.json')


def check_scene_guard(scene):
    if read(scene).get('metadata', {}).get('native_edit_state', {}).get('superseded'):
        raise ValueError('This scene is superseded by native Visio edits; use the recorded VSDX or reconcile it explicitly')
    guard = scene_guard_path(scene)
    if guard.exists():
        records = read(guard)
        if any(record['scene_sha256'] == digest(scene) for record in records):
            raise ValueError('This scene is superseded by native Visio edits. Continue from the recorded VSDX or reconcile the scene first.')


def reconcile_scene(scene_path, source, output, before, after, plan):
    """Only sync a complete, unambiguous, edge-free node mapping; otherwise lock old scene."""
    scene_path = Path(scene_path).resolve()
    scene = read(scene_path)
    expected = plan.get('scene_sha256')
    if expected != digest(scene_path):
        raise ValueError('A supplied scene requires a matching scene_sha256 in the plan')
    nodes = {n['id']: n for n in scene.get('nodes', [])}
    mapping = {}
    for ident, shape in before['shapes'].items():
        parts = shape['name'].split('__')
        if len(parts) == 3 and parts[0] == 'node' and parts[1] in nodes and parts[1] not in mapping:
            mapping[parts[1]] = ident
    simple = (not scene.get('edges') and not scene.get('assets') and len(before['pages']) == 1
              and len(mapping) == len(nodes) == len(before['shapes'])
              and before['shapes'].keys() == after['shapes'].keys()
              and all(o['op'] in ('text', 'font', 'move', 'resize') for o in plan['operations'])
              and all(n.get('type') in ('process_box', 'text_block') for n in nodes.values()))
    if simple:
        height = after['pages'][0]['height']
        for node_id, ident in mapping.items():
            node, shape = nodes[node_id], after['shapes'][ident]
            previous = before['shapes'][ident]
            pc = previous['cells']
            expected_box = [pc['PinX'] - pc['Width'] / 2, height - pc['PinY'] - pc['Height'] / 2, pc['Width'], pc['Height']]
            if previous['text'] != node.get('text', '') or any(abs(float(node.get(k, -999)) - v) > 1e-5 for k, v in zip(('x', 'y', 'w', 'h'), expected_box)):
                simple = False
                break
            cells = shape['cells']
            if cells['Angle'] or cells['FlipX'] or cells['FlipY'] or len(shape['characters']) != 1:
                simple = False
                break
            node.update(x=number(cells['PinX'] - cells['Width'] / 2),
                        y=number(height - cells['PinY'] - cells['Height'] / 2),
                        w=cells['Width'], h=cells['Height'], text=shape['text'])
            for operation in plan['operations']:
                if key(operation['page_id'], operation['shape_id']) == ident and operation['op'] == 'font':
                    if 'start' in operation or 'end' in operation:
                        simple = False
                        break
                    style = node.setdefault('style', {})
                    if 'font' in operation:
                        style['font_family'] = operation['font']
                    if 'size_pt' in operation:
                        style['font_size_pt'] = operation['size_pt']
        if simple:
            destination = output.with_suffix('.scene.json')
            write(destination, scene)
            return {'mode': 'scene_synced', 'scene': str(destination), 'sha256': digest(destination)}
    return {'mode': 'vsdx_authoritative', 'reason': 'Scene mapping cannot fully preserve this native edit',
            'superseded_scene': str(scene_path), 'scene_sha256': expected}


def apply(source, plan_path, output, scene=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    plan = read(plan_path)
    validate_plan(plan, source)
    if output.suffix.lower() != '.vsdx' or source == output:
        raise ValueError('Choose a new .vsdx output; overwriting the input is prohibited')
    # A discovered matching sidecar is never silently ignored.
    if scene and not Path(scene).is_file():
        raise FileNotFoundError(scene)
    scene = Path(scene).resolve() if scene else source.with_suffix('.scene.json')
    if not scene.exists():
        scene = None
    if scene and plan.get('scene_sha256') != digest(scene):
        raise ValueError('Inspect and bind the matching scene_sha256, or reconcile the scene before editing')
    report_path = output.with_suffix('.edit.json')
    collisions = [p for p in (output, report_path, output.with_suffix('.scene.json')) if p.exists()]
    collisions += list(output.parent.glob(output.stem + '.page-*.png'))
    if collisions:
        raise FileExistsError('Choose a new version; existing output family: ' + ', '.join(map(str, collisions)))
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'failed', 'source': str(source), 'input_sha256': digest(source),
              'output': str(output), 'plan': plan, 'visual_review': 'required'}
    try:
        report['package_before'] = package_snapshot(source)
        with tempfile.TemporaryDirectory(prefix='visiomaster-edit-') as temporary, visio() as app:
            try:
                doc = app.Documents.OpenEx(str(source), OPEN_HIDDEN + 2)
                baseline = snapshot(doc)
                before_pngs = export(doc, Path(temporary) / 'before')
                doc.Saved = True
                doc.Close()
                # Edit a private copy, never the original file, even if an operation fails.
                working = Path(temporary) / 'working.vsdx'
                working.write_bytes(source.read_bytes())
                if plan.get('backend', 'com') == 'vsdx':
                    current_text = {ident: s['text'] for ident, s in baseline['shapes'].items()}
                    final_text = {}
                    with safe_package(working) as package:
                        for operation in plan['operations']:
                            ident = key(operation['page_id'], operation['shape_id'])
                            record = report['package_before']['shapes'].get(ident)
                            if operation['op'] != 'text' or 'start' in operation or 'end' in operation or not record or not record['simple_text']:
                                raise ValueError('vsdx backend accepts only existing single-format whole-text replacements')
                            page = next(p for p in package.pages if int(p.page_id) == operation['page_id'])
                            matches = [k for k, text in current_text.items() if k.startswith(str(operation['page_id']) + ':') and text == operation.get('search_text')]
                            if 'search_text' in operation and matches != [ident]:
                                raise ValueError('Ambiguous text search')
                            shape = page.find_shape_by_id(str(operation['shape_id']))
                            if 'expect_text' in operation and current_text[ident] != operation['expect_text']:
                                raise ValueError('Unexpected text')
                            shape.text = operation['text']
                            current_text[ident] = final_text[ident] = operation['text']
                        library_output = Path(temporary) / 'library.vsdx'
                        package.save_vsdx(str(library_output))
                    doc = app.Documents.OpenEx(str(library_output), OPEN_HIDDEN)
                    expected = snapshot(doc)
                    allowed = {key(o['page_id'], o['shape_id']): {'text', 'characters', 'text_formats'} for o in plan['operations']}
                    changes = check_preserved(baseline, expected, allowed, set(), set(), set())
                    for ident, requested in final_text.items():
                        if expected['shapes'][ident]['text'] != requested:
                            raise ValueError('Library text replacement did not match the requested text')
                        old_formats = baseline['shapes'][ident]['text_formats']
                        if old_formats and any(f != old_formats[0] for f in expected['shapes'][ident]['text_formats']):
                            raise ValueError('Library text replacement changed formatting')
                    if not changes:
                        raise ValueError('No effective object change')
                    log = [{'op': o['op'], 'target': key(o['page_id'], o['shape_id'])} for o in plan['operations']]
                else:
                    if plan.get('backend', 'com') != 'com':
                        raise ValueError('Unknown backend')
                    doc = app.Documents.OpenEx(str(working), OPEN_HIDDEN)
                    before, expected, changes, log = perform(doc, plan)
                    if baseline != before:
                        raise ValueError('Input differs between read-only and edit open')
                doc.SaveAs(str(output))
                doc.Saved = True
                doc.Close()
                doc = app.Documents.OpenEx(str(output), OPEN_HIDDEN + 2)
                actual = snapshot(doc)
                if actual != expected:
                    raise ValueError('Saved document differs from the verified in-memory result')
                after_pngs = export(doc, output.with_suffix(''))
                report['pixels'] = pixel_changes(before_pngs, after_pngs)
                report.update(before=baseline, after=actual, changes=changes, operations=log,
                              package_after=package_snapshot(output))
                report['source_state'] = reconcile_scene(scene, source, output, baseline, actual, plan) if scene else {'mode': 'vsdx_authoritative', 'reason': 'No scene supplied or discovered'}
                if digest(source) != report['input_sha256']:
                    raise ValueError('Input file changed during editing; result must be reviewed again')
                if scene:
                    guard = scene_guard_path(scene)
                    records = read(guard) if guard.exists() else []
                    records.append({'scene_sha256': digest(scene), 'continue_from': str(output), 'output_sha256': digest(output)})
                    write(guard, records)
                    superseded = read(scene)
                    superseded.setdefault('metadata', {})['native_edit_state'] = {
                        'superseded': True, 'continue_from': str(output), 'sha256': digest(output),
                        'original_scene_sha256': plan['scene_sha256']}
                    write(scene, superseded)
                report['outputs'] = {str(p): digest(p) for p in [output, *after_pngs]}
                if digest(source) != report['input_sha256']:
                    raise ValueError('Input file changed during editing; result must be reviewed again')
                report['status'] = 'edited_pending_visual_review'
                doc = None
            finally:
                doc = None
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        raise
    finally:
        write(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('input')
    inspect.add_argument('--output', required=True)
    inspect.add_argument('--offline', action='store_true')
    inspect.add_argument('--search-text')
    edit = commands.add_parser('apply')
    edit.add_argument('input')
    edit.add_argument('--plan', required=True)
    edit.add_argument('--output', required=True)
    edit.add_argument('--scene')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            if Path(args.output).exists():
                raise FileExistsError(args.output)
            result = package_snapshot(args.input)
            if not args.offline:
                with visio() as app:
                    document = app.Documents.OpenEx(str(Path(args.input).resolve()), OPEN_HIDDEN + 2)
                    result['effective'] = snapshot(document)
                    document = None
            if args.search_text is not None:
                shapes = result.get('effective', result)['shapes']
                matches = [ident for ident, item in shapes.items() if item['text'].rstrip('\r\n') == args.search_text.rstrip('\r\n')]
                if len(matches) != 1:
                    raise ValueError(f'Expected one text match, found {len(matches)}')
                result['search_match'] = matches[0]
            write(args.output, result)
        else:
            result = apply(args.input, args.plan, args.output, args.scene)
            print(result['status'])
        return 0
    except Exception as exc:
        print(f'FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
