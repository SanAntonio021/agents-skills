"""Review saved native test evidence without changing outputs or permissions."""
import codecs
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = codecs.BOM_UTF8 + ('本次记录共24000帧，其中错误帧为12帧。\r\n'
                          '帧差错率为q = 12 / 24000 = 0.0005，双通道测试尚未开展。').encode()
EXPECTED = {
    'title': codecs.BOM_UTF8 + '## 单通道测试记录\r\n'.encode() + SOURCE[3:],
    'append': SOURCE + '\r\n周五09:40送到的测试件先放西侧库房，下周一再清点。'.encode(),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def objects(text):
    for line in text.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                yield value
        except (ValueError, TypeError):
            pass


def review(folder):
    host, case = folder.parent.name, folder.name
    events = list(objects((folder / 'events.jsonl').read_text(encoding='utf-8')))
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
    args = json.loads((folder / 'command.json').read_text(encoding='utf-8'))
    scratch = (Path(receipt['scratch']) if receipt.get('scratch') else Path(args[args.index('-C') + 1]))
    output = scratch / 'result.md'
    error, exact, markers = None, None, None
    try:
        data = output.read_bytes()
        exact = data == EXPECTED[case]
        markers = {'bom_preserved': data.startswith(codecs.BOM_UTF8),
                   'original_byte_sequence_present': SOURCE[3:] in data,
                   'actual_sha256': digest(data)}
    except OSError as exc:
        error = str(exc)
    init = next((e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init'), {})
    commands, returned = [], []
    calls = {}
    for event in events:
        if host == 'codex' and event.get('type') == 'item.completed':
            item = event.get('item', {})
            if item.get('type') == 'command_execution' and item.get('exit_code') == 0:
                if 'exact_edit.py' in item.get('command', '') and any(
                    action in item['command'] for action in ('apply', 'verify')):
                    commands.append(item['command'])
                    returned.extend(objects(item.get('aggregated_output', '')))
        elif host == 'claude':
            for block in event.get('message', {}).get('content', []):
                if block.get('type') == 'tool_use':
                    cmd = block.get('input', {}).get('command', '')
                    if 'exact_edit.py' in cmd and any(action in cmd for action in ('apply', 'verify')):
                        calls[block['id']] = cmd
                elif (block.get('type') == 'tool_result' and block.get('tool_use_id') in calls
                      and not block.get('is_error')):
                    commands.append(calls[block['tool_use_id']])
                    content = block.get('content', '')
                    if isinstance(content, list):
                        content = '\n'.join(b.get('text', '') for b in content if isinstance(b, dict))
                    returned.extend(objects(content))
    applied = any(r.get('ok') is True and r.get('action') == 'apply'
                  and r.get('source_sha256') == digest(SOURCE)
                  and r.get('output_sha256') == digest(EXPECTED[case]) for r in returned)
    verified = any(r.get('ok') is True and r.get('action') == 'verify'
                   and r.get('expected_sha256') == digest(EXPECTED[case])
                   and r.get('candidate_sha256') == digest(EXPECTED[case]) for r in returned)
    result = {'batch': folder.parent.parent.name, 'host': host, 'case': case,
              'receipt_present': bool(receipt), 'session': receipt.get('session') or next(
                  (e.get('thread_id') for e in events if e.get('thread_id')), None),
              'startup_writing_router_available': 'writing-router' in init.get('skills', []) if host == 'claude' else None,
              'source_unchanged': (scratch / 'original.md').read_bytes() == SOURCE,
              'parent_byte_check': exact, 'parent_read_error': error, 'byte_details': markers,
              'successful_helper_command': bool(commands), 'apply_hash_matches_expected': applied,
              'verify_hash_matches_expected': verified, 'expected_sha256': digest(EXPECTED[case]),
              'helper_command_evidence': commands,
              'final': (folder / 'final.md').read_text(encoding='utf-8')}
    (folder / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {k: v for k, v in result.items() if k not in ('helper_command_evidence', 'final')}


if __name__ == '__main__':
    results = [review(p.parent) for batch in ['native-runs', 'native-user-source', 'native-slash-control']
               for p in sorted((ROOT / batch).glob('*/*/events.jsonl'))]
    (ROOT / 'native-review.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
