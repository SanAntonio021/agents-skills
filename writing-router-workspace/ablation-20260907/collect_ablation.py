"""Collect immutable outputs, loading evidence, and exact-edit checks separately."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

import run_ablation as runner

ROOT = runner.ROOT


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def normalize(text):
    return text.replace('\r\n', '\n')


def exact_assessment(case, text):
    """Allow only boundary line breaks, never normalize body whitespace."""
    if 'original' not in case:
        return {'status': 'semantic_review_required'}
    source = normalize(case['original'])
    text = normalize(text)
    if 'heading' in case:
        pattern = re.escape(case['heading']) + r'\n+' + re.escape(source) + r'\n*'
    else:
        pattern = re.escape(source) + r'\n*' + re.escape(case['append']) + r'\n*'
    ok = re.fullmatch(pattern, text) is not None
    return {'status': 'pass' if ok else 'fail', 'whole_response_matches': ok,
            'policy': 'Only connecting and terminal line breaks may differ; body whitespace is exact.'}


def returned_texts(folder, host):
    if host == 'codex':
        return [e['output'] for e in read_json(folder / 'read-evidence.json')
                if e.get('exit_code') == 0 and isinstance(e.get('output'), str)]
    texts = []
    for event in runner.replay.events_from((folder / 'events.jsonl').read_text(encoding='utf-8')):
        if event.get('type') != 'user':
            continue
        for block in event.get('message', {}).get('content', []):
            if block.get('type') == 'tool_result' and not block.get('is_error'):
                content = block.get('content', '')
                if isinstance(content, list):
                    content = '\n'.join(b.get('text', '') for b in content)
                if isinstance(content, str):
                    texts.append(re.sub(r'^\s*\d+\t', '', content, flags=re.M))
    return texts


def loading_assessment(folder, receipt, case):
    prompt = (folder / 'prompt.txt').read_text(encoding='utf-8')
    returned = [normalize(s) for s in returned_texts(folder, receipt['host'])]
    references = {}
    for relative in runner.required_refs(case):
        path = ROOT / 'snapshot' / relative
        body = path.read_text(encoding='utf-8')
        supplied = f'<skill_reference path="{path.as_posix()}">\n{body}\n</skill_reference>' in prompt
        read = any(normalize(body).strip() in s for s in returned)
        references[relative] = 'inline' if supplied else 'successful_full_return' if read else 'not_proven'
    vocabulary = {}
    for relative in case['vocab']:
        path = runner.VOCAB / relative
        body = path.read_text(encoding='utf-8')
        supplied = f'<vocabulary path="{path.as_posix()}">\n{body}\n</vocabulary>' in prompt
        read = any(normalize(body).strip() in s for s in returned)
        vocabulary[relative] = 'inline' if supplied else 'successful_full_return' if read else 'not_proven'
    calls = read_json(folder / 'read-evidence.json')
    commands = '\n'.join(e.get('command', '') for e in calls)
    return {'references': references, 'vocabulary': vocabulary,
            'all_required_rules_supplied_or_returned': all(v != 'not_proven' for v in references.values()),
            'all_vocabulary_supplied_or_returned': all(v != 'not_proven' for v in vocabulary.values()),
            'local_or_shared_rules_read': 'local.md' in commands or 'shared-rules.md' in commands,
            'successful_tool_returns': len(returned),
            'note': 'Full text in context does not prove instruction compliance; partial returns are not full reads.'}


def select_completed(root, host, arm, case, repeat):
    folder = root / host / arm / case / f'repeat-{repeat}'
    found, excluded = [], []
    for path in sorted(folder.rglob('completion.json')):
        receipt = read_json(path)
        prompt = (path.parent / 'prompt.txt').read_bytes()
        valid = (receipt.get('status') == 'completed' and receipt.get('material_unchanged')
                 and receipt.get('models') == [runner.replay.MODELS[host]]
                 and receipt.get('automatic_context_isolated')
                 and receipt.get('prompt_sha256') == hashlib.sha256(prompt).hexdigest())
        # write_text on Windows converts prompt newlines; verify the original text hash too.
        if not valid and receipt.get('status') == 'completed':
            canonical = (path.parent / 'prompt.txt').read_text(encoding='utf-8').encode('utf-8')
            valid = (receipt.get('material_unchanged') and receipt.get('models') == [runner.replay.MODELS[host]]
                     and receipt.get('automatic_context_isolated')
                     and receipt.get('prompt_sha256') == hashlib.sha256(canonical).hexdigest())
        if valid:
            found.append((path.parent, receipt))
        else:
            excluded.append({'path': str(path.relative_to(ROOT)), 'status': receipt.get('status')})
    if len(found) > 1:
        raise ValueError(f'Multiple successful attempts require explicit selection: {folder}')
    return (found[0] if found else None), excluded


def collect(phase):
    root = ROOT / ('controlled-runs' if phase == 'controlled' else 'runs')
    review = ROOT / ('review-' + phase)
    review.mkdir(exist_ok=True)
    cases = read_json(ROOT / 'cases.json')['cases']
    arms = ['without-skill', 'loaded-skill'] if phase == 'controlled' else ['without-skill', 'with-skill', 'loaded-skill']
    rows, missing, excluded = [], [], []
    for host in ['claude', 'codex']:
        for number, case in enumerate(cases, 1):
            for repeat in [1, 2]:
                group = review / f'{host}-{case["id"]}-repeat-{repeat}'
                (group / 'outputs').mkdir(parents=True, exist_ok=True)
                write_json(group / 'eval_metadata.json', {'eval_id': number, 'prompt': case['prompt']})
                for arm in arms:
                    selected, failures = select_completed(root, host, arm, case['id'], repeat)
                    excluded.extend(failures)
                    key = f'{host}/{arm}/{case["id"]}/repeat-{repeat}'
                    if selected is None:
                        missing.append(key)
                        continue
                    folder, receipt = selected
                    final = folder / 'final.md'
                    row = {'key': key, 'host': host, 'arm': arm, 'case': case['id'], 'repeat': repeat,
                           'path': str(folder.relative_to(ROOT)), 'model': receipt['models'][0],
                           'output_sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
                           'loading': loading_assessment(folder, receipt, case),
                           'exact_check': exact_assessment(case, final.read_text(encoding='utf-8')),
                           'semantic_review': 'pending', 'duration_seconds': receipt['duration_seconds']}
                    rows.append(row)
                    shutil.copyfile(final, group / 'outputs' / (arm + '.md'))
    result = {'phase': phase, 'rows': rows, 'missing': missing, 'excluded_attempts': excluded,
              'execution_complete': not missing, 'quality_accepted': False}
    write_json(ROOT / f'collection-{phase}.json', result)
    print(json.dumps({'phase': phase, 'selected': len(rows), 'missing': missing,
                      'excluded': len(excluded)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['diagnostic', 'controlled'])
    collect(parser.parse_args().phase)
