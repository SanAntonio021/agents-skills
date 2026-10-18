"""Collect full conversations and prepare masked paired reviews."""
import json
from pathlib import Path
import random
import re

import run_style as run

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def paragraphs(text):
    return re.split(r'\n\s*\n', text.replace('\r\n', '\n').strip())


def boundary_checks(case_id, texts):
    ps = [paragraphs(text) for text in texts]
    checks = [{'text': 'Each output has two paragraphs', 'passed': all(len(p) == 2 for p in ps),
               'evidence': 'Paragraph counts: ' + str([len(p) for p in ps])}]
    if len(ps) == 3 and all(len(p) == 2 for p in ps):
        if case_id == 'integration-note':
            checks.append({'text': 'Turn 3 preserves the supply paragraph from turn 2',
                           'passed': ps[1][1] == ps[2][1], 'evidence': 'Exact paragraph comparison; only CRLF normalized.'})
        if case_id == 'test-explanation':
            checks.extend([
                {'text': 'Turn 2 preserves the results paragraph', 'passed': ps[0][1] == ps[1][1],
                 'evidence': 'Turn 1/2 second paragraph exact comparison.'},
                {'text': 'Turn 3 preserves the process paragraph', 'passed': ps[1][0] == ps[2][0],
                 'evidence': 'Turn 2/3 first paragraph exact comparison.'},
                {'text': 'Turn 3 uses the requested opening', 'passed': ps[2][1].startswith('在单传感器台架试验中'),
                 'evidence': 'Second paragraph opening.'},
                {'text': 'Turn 3 preserves text after the first results sentence',
                 'passed': ps[1][1].partition('。')[2] == ps[2][1].partition('。')[2],
                 'evidence': 'Remainder after first Chinese full stop; first sentence needs semantic review.'},
            ])
    return checks


def collect():
    manifest = run.verify(ROOT)
    cases = run.load_cases(ROOT / 'snapshot/cases.json')
    rng = random.Random(8092026)
    rows, incomplete, keys, pairs = [], [], [], []
    for host in run.MODELS:
        for case in cases:
            outputs = {}
            for arm in ['installed', 'candidate']:
                found = sorted((ROOT / 'runs' / host / arm / case['id']).glob('*/completion.json'))
                if len(found) != 1:
                    incomplete.append({'host': host, 'arm': arm, 'case': case['id'], 'reason': 'Missing or ambiguous attempt', 'count': len(found)})
                    continue
                folder = found[0].parent
                completion = read(found[0])
                if completion['status'] != 'completed':
                    incomplete.append({'host': host, 'arm': arm, 'case': case['id'], 'reason': 'Execution failed', 'path': str(folder)})
                    continue
                texts, sessions, checks = [], [], []
                for index in range(len(case['turns'])):
                    turn = folder / f'turn-{index + 1}'
                    result = read(turn / 'completion.json')
                    assert result['status'] == 'completed' and not result['quality_accepted']
                    saved = (turn / 'prompt.txt').read_text(encoding='utf-8')
                    assert saved == run.prompt(ROOT, arm, case, index)
                    assert read(turn / 'execution.json')['prompt_sha256'] == run.sha(saved.encode())
                    assert not read(turn / 'read-evidence.json')
                    texts.append((turn / 'final.md').read_text(encoding='utf-8'))
                    sessions.append(result['session'])
                assert len(set(sessions)) == 1
                checks = boundary_checks(case['id'], texts)
                row = {'host': host, 'arm': arm, 'case': case['id'], 'session': sessions[0],
                       'path': str(folder.relative_to(ROOT)), 'turns': texts,
                       'full_input_verified': True, 'mechanical_checks': checks, 'semantic_review': 'pending'}
                rows.append(row)
                outputs[arm] = row
            if len(outputs) != 2:
                continue
            number = len(pairs) + 1
            order = ['installed', 'candidate']
            rng.shuffle(order)
            group = ROOT / 'review' / f'pair-{number:02}'
            write(group / 'eval_metadata.json', {'eval_id': number, 'eval_name': case['id'],
                  'prompt': '\n\n'.join(f'第{i+1}轮：{p}' for i, p in enumerate(case['turns']))})
            pair = {'id': number, 'case': case['id'], 'prompts': case['turns'], 'outputs': {}}
            for label, arm in zip(['A', 'B'], order):
                row = outputs[arm]
                pair['outputs'][label] = row['turns']
                text = '\n\n'.join(f'## 第{i+1}轮\n\n{t}' for i, t in enumerate(row['turns']))
                out = group / 'outputs' / (label + '.md')
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text, encoding='utf-8')
                keys.append({'pair': number, 'label': label, 'host': host, 'arm': arm, 'path': row['path']})
            pairs.append(pair)
    assert len({r['session'] for r in rows}) == len(rows)
    result = {'planned_conversations': 12, 'planned_turns': 28, 'completed_conversations': len(rows),
              'completed_turns': sum(len(r['turns']) for r in rows), 'incomplete': incomplete,
              'rows': rows, 'quality_accepted': False, 'snapshot_file_count': len(manifest)}
    write(ROOT / 'collection.json', result)
    write(ROOT / 'blind-input.json', pairs)
    write(ROOT / 'blind-key.json', keys)
    print(json.dumps({k: result[k] for k in ['completed_conversations', 'completed_turns', 'incomplete']}, ensure_ascii=False))


if __name__ == '__main__':
    collect()
