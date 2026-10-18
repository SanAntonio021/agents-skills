"""Collect complete outputs without equating execution, loading, and quality."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

import run_contrast as run

ROOT = run.ROOT


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def exact_check(case, text):
    if case['category'] != 'heading':
        return {'status': 'semantic_review_required'}
    text = text.replace('\r\n', '\n')
    pattern = re.escape(case['heading']) + r'\n+' + re.escape(case['original']) + r'\n*'
    ok = bool(re.fullmatch(pattern, text))
    return {'status': 'pass' if ok else 'fail', 'body_occurs_verbatim': case['original'] in text,
            'entire_response_matches': ok, 'boundary_newlines_ignored': True}


def read_commands(folder, host):
    calls = read_json(folder / 'read-evidence.json')
    if host == 'claude':
        return [c.get('input', {}).get('file_path', '') for c in calls]
    return [c.get('command', '') for c in calls]


def collect():
    rows, missing, excluded = [], [], []
    review = ROOT / 'review'
    review.mkdir(exist_ok=True)
    manifest_hash = run.digest((ROOT / 'snapshot-manifest.json').read_bytes())
    assert run.base.hashes(ROOT / 'snapshot') == read_json(ROOT / 'snapshot-manifest.json')
    for host in run.replay.MODELS:
        for number, case in enumerate(run.cases(), 1):
            for repeat in [1, 2]:
                group = review / f'{host}-{case["id"]}-repeat-{repeat}'
                (group / 'outputs').mkdir(parents=True, exist_ok=True)
                run.write_json(group / 'eval_metadata.json', {
                    'eval_id': number, 'prompt': case['prompt'] + '\n\n评阅提示：原版仅作跨文体观察，本题不在其公众号长文适用范围；不计入本地与候选的收益判断。'})
                for arm in run.ARMS:
                    key = f'{host}/{arm}/{case["id"]}/repeat-{repeat}'
                    found = []
                    for file in sorted((ROOT / 'runs' / key).rglob('completion.json')):
                        receipt = read_json(file)
                        prompt = (file.parent / 'prompt.txt').read_bytes()
                        valid = (receipt.get('status') == 'completed' and receipt.get('material_unchanged')
                                 and receipt.get('models') == [run.replay.MODELS[host]]
                                 and receipt.get('automatic_catalog_and_user_context_absent')
                                 and receipt.get('snapshot_manifest_sha256') == manifest_hash
                                 and receipt.get('prompt_sha256') == run.digest(prompt)
                                 and prompt == run.prompt(arm, case).encode('utf-8'))
                        if valid:
                            found.append((file.parent, receipt))
                        else:
                            excluded.append({'key': key, 'path': str(file.parent.relative_to(ROOT)), 'status': receipt.get('status')})
                    if len(found) > 1:
                        raise ValueError('Multiple successful attempts: ' + key)
                    if not found:
                        missing.append(key)
                        continue
                    folder, receipt = found[0]
                    final = folder / 'final.md'
                    text = final.read_text(encoding='utf-8')
                    commands = read_commands(folder, host)
                    flags = [c for c in commands if any(marker in c.replace('\\', '/') for marker in
                             ['writing-samples/', 'writing-profile/', 'cases.json', 'memories/', 'ablation-20260907'])]
                    row = {'key': key, 'host': host, 'arm': arm, 'case': case['id'], 'category': case['category'],
                           'repeat': repeat, 'path': str(folder.relative_to(ROOT)), 'model': receipt['models'][0],
                           'session': receipt['session'], 'output_sha256': run.digest(final.read_bytes()),
                           'all_requested_rules_and_vocab_in_prompt': True, 'unexpected_read_flags': flags,
                           'background_rule_reads': sum('local.md' in c or 'shared-rules.md' in c for c in commands),
                           'upstream_scope': receipt['upstream_scope'], 'eligible_for_local_candidate_comparison': arm != 'khazix',
                           'duration_seconds': receipt['duration_seconds'], 'exact_check': exact_check(case, text),
                           'semantic_review': 'pending', 'user_accepted': False}
                    rows.append(row)
                    label = {'local': 'A-current-local', 'examples': 'B-local-plus-examples',
                             'khazix': 'C-khazix-out-of-scope'}[arm]
                    shutil.copyfile(final, group / 'outputs' / (label + '.md'))
    assert len({r['session'] for r in rows}) == len(rows), 'Fresh-session requirement failed'
    result = {'planned': 72, 'completed': len(rows), 'missing': missing, 'excluded': excluded,
              'rows': rows, 'quality_accepted': False, 'runtime_modified': False}
    run.write_json(ROOT / 'collection.json', result)
    print(json.dumps({'completed': len(rows), 'missing': len(missing), 'excluded': len(excluded),
                      'unexpected_read_flags': sum(bool(r['unexpected_read_flags']) for r in rows)}))


if __name__ == '__main__':
    collect()
