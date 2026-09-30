"""Guarded CLI readback and background editor runner (Python standard library)."""
import argparse
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


def projection(raw):
    nodes = raw['nodes']
    parents = {child: n['id'] for n in nodes for child in n.get('children', [])}
    result = []
    for n in nodes:
        kind = {'composite_shape': 'shape', 'connector': 'connector', 'group': 'group'}.get(n.get('type'), 'other')
        v = dict(id=n['id'], kind=kind, **{k: n.get(k, 0) for k in ('x', 'y', 'width', 'height')})
        if 'text' in n:
            v.update(text=n['text'].get('text', ''), font_size=n['text'].get('font_size', 0))
        if kind == 'shape':
            v['shape'] = n.get('composite_shape', {}).get('type', '')
        if kind == 'connector':
            c = n['connector']
            for side in ('start', 'end'):
                endpoint = c.get(side + '_object') or c.get(side, {}).get('attached_object', {})
                v[side + '_id'] = endpoint.get('id', '')
                v[side + '_arrow'] = c.get(side, {}).get('arrow_style', 'none')
            v.update(shape=c.get('shape', ''), caption='\n'.join(t.get('text', '') for t in c.get('captions', {}).get('data', [])))
        if kind == 'group':
            v['children'] = sorted(n.get('children', []))
        if n['id'] in parents:
            v['parent_id'] = parents[n['id']]
        result.append(v)
    return sorted(result, key=lambda n: n['id'])


def equivalent(a, b):
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return math.isfinite(a) and math.isfinite(b) and abs(a-b) < 0.02
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    return a == b


def differences(before, after):
    a, b = ({n['id']: n for n in nodes} for nodes in (before, after))
    return dict(added=sorted(b.keys()-a.keys()), removed=sorted(a.keys()-b.keys()), changed=sorted(k for k in a.keys() & b.keys() if not equivalent(a[k], b[k])))


def check_scope(before, after, op):
    delta = differences(before, after)
    ids = set(op.get('ids', [])) | ({op['id']} if 'id' in op else set())
    lookup = {n['id']: n for n in before}
    for ident in list(ids):
        ids.update(lookup.get(ident, {}).get('children', []))
    allowed = ids | {n['id'] for n in before if n.get('start_id') in ids or n.get('end_id') in ids}
    if op['kind'] == 'reconnect':
        allowed.add(op['end_id'])
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
    check_intent(before, after, op, delta)
    return delta


def check_intent(before, after, op, delta=None):
    """Verify requested outcomes, rather than treating absence of damage as success."""
    a, b = ({n['id']: n for n in nodes} for nodes in (before, after))
    kind = op['kind']
    ident = op.get('id')
    def require(condition):
        if not condition:
            raise VerificationError('Requested operation postcondition failed: ' + kind)
    for field, operation, parameter in [('text','text','text'), ('font_size','font','font_size'), ('caption','caption','text'), ('shape','line_type','shape'), ('end_id','reconnect','end_id')]:
        if kind == operation:
            require(ident in b and equivalent(b[ident].get(field), op[parameter]))
    if kind == 'resize':
        require(all(equivalent(b[ident][k], op[k]) for k in ('width', 'height')))
    if kind == 'move':
        for node_id in op['ids']:
            require(equivalent(b[node_id]['x'], a[node_id]['x'] + op['dx']) and equivalent(b[node_id]['y'], a[node_id]['y'] + op['dy']))
    if kind == 'arrow':
        require(b[ident]['start_arrow'] == op['start'] and b[ident]['end_arrow'] == op['end'])
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
            paths += {'text':[('text','text')], 'font':[('text','font_size')],
                      'arrow':[('connector','start','arrow_style'),('connector','end','arrow_style')],
                      'caption':[('connector','captions'),('connector','caption_position'),('connector','caption_position_type')],
                      'line_type':[('connector','shape'),('connector','turning_points')],
                      'reconnect':[('connector','end_object'),('connector','end','attached_object'),('connector','turning_points')],
                      'group':[('parent_id',)], 'ungroup':[('parent_id',)]}.get(kind, [])
            if kind in ('line_type','reconnect'):
                paths += [(k,) for k in ('x','y','width','height')]
        # The editor canonicalizes a legacy one-pixel straight horizontal line.
        if c.get('shape') == 'straight' and left.get('height') == 1 and right.get('height') == 0 and left.get('x') == right.get('x') and left.get('y') == right.get('y') and left.get('width') == right.get('width'):
            paths.append(('height',))
            exceptions.append({'id':ident, 'normalization':'horizontal_straight_height_1_to_0'})
        for path in paths:
            strip(left, path)
            strip(right, path)
        if not equivalent(left, right):
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
    for kind in ('shape', 'connector'):
        for node in [n for n in intended if n['kind'] == kind]:
            wanted = {k: v for k, v in node.items() if k != 'id'}
            if kind == 'connector':
                wanted['start_id'] = mapping[wanted['start_id']]
                wanted['end_id'] = mapping[wanted['end_id']]
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

    def settle(self, expected):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            current = self.editor({'kind': 'inspect'})
            if not equivalent(current['nodes'], expected):
                raise VerificationError('Page changed during save verification')
            if current.get('seq') == current.get('savedSeq') and current.get('seq') is not None:
                try:
                    raw, name = self.export()
                    if equivalent(projection(raw), expected):
                        return raw, name
                except NotReady:
                    pass
            time.sleep(1)
        raise VerificationError('Save/readback did not converge; write was not retried')

    def open_page(self):
        session = self.call('/v2/tasks', {}, auth=False)
        self.token, self.task = session['taskToken'], session['taskId']
        target = self.call('/v2/tabs', {'url': self.request['document_url'], 'background': True})
        self.tab = target['targetId']
        self.call('/v2/tabs/' + self.tab + '/wait', {'selector': '.whiteboard-canvas-container', 'timeoutMs': 15000})

    def hydrate(self, raw):
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
            if equivalent(state['nodes'], projection(latest)) and state.get('seq') == state.get('savedSeq'):
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
            raw, name = self.settle(state['nodes'])
            if op is None:
                self.report['initial_nodes'] = state['nodes']
                continue
            actual = dict(op)
            reject_nested_groups(state['nodes'], op)
            if op['kind'] == 'undo':
                if previous_delete is None:
                    raise VerificationError('Undo is only allowed immediately after this session\'s delete')
                actual['undo_count'] = previous_delete['transaction_count']
                actual['undo_receipt'] = previous_delete['undo_receipt']
            self.uncertain = True
            result = self.editor(actual, state['nodes'])
            self.write(f'editor-{len(self.report["steps"])+1:03d}.json', result)
            if op['kind'] == 'undo':
                if not equivalent(result['nodes'], previous_delete['before']):
                    raise VerificationError('Undo did not restore the pre-delete projection')
                delta = differences(state['nodes'], result['nodes'])
            else:
                delta = check_scope(state['nodes'], result['nodes'], op)
            saved_raw, saved = self.settle(result['nodes'])
            raw_exceptions = check_raw_preservation(previous_delete['raw'] if op['kind'] == 'undo' else raw, saved_raw, {'kind':'undo'} if op['kind'] == 'undo' else op)
            self.uncertain = False
            self.report['steps'].append({'operation': op, 'before_raw': name, 'after_raw': saved, 'diff': delta, 'raw_exceptions':raw_exceptions})
            previous_delete = {'before': state['nodes'], 'raw':raw, 'transaction_count': result['transaction_count'], 'undo_receipt':result['undo_receipt']} if op['kind'] == 'delete' else None
        self.report['status'] = 'verified'

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
            if n.get('type') not in ('composite_shape', 'connector'):
                raise ValueError('Append only supports native shapes and bound connectors')
            if n['type'] == 'composite_shape' and not isinstance(n.get('text', {}).get('text'), str):
                raise ValueError('Native shapes must own their text')
            if n['type'] == 'connector':
                c = n['connector']
                for side in ('start','end'):
                    endpoint = c.get(side + '_object', {})
                    if endpoint.get('id') not in ids:
                        raise ValueError('CLI append cannot reference existing shapes; append new shapes first, then use editor connect with an existing line template')
                    if endpoint.get('id') not in shape_lookup or endpoint != c.get(side, {}).get('attached_object'):
                        raise ValueError('Append connector has missing or conflicting native shape endpoint')
                start,end = (shape_lookup[c[side + '_object']['id']] for side in ('start','end'))
                sx,sy = start['x']+start['width'], start['y']+start['height']/2
                ex,ey = end['x'],end['y']+end['height']/2
                if not equivalent([n['x'],n['y'],n['width'],n['height']], [sx,sy,ex-sx,ey-sy]):
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
