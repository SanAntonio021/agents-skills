"""Prepare complete, anonymously labeled outputs for the existing skill viewer."""
import json
import argparse
from pathlib import Path
import random

from run_evaluation import CASE_FILE, ROOT, MODELS, SOURCE, events_from, hash_files, parse_result, write_json

SELECTION = ['unnecessary-defense-project', 'necessary-negation-paper']


def completed_run(host, version, case):
    parent = ROOT / 'runs' / host / version / case['id']
    if not parent.exists():
        return None
    for folder in sorted(parent.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        receipt = folder / 'completion.json'
        recovered = not receipt.exists()
        if recovered:
            receipt = folder / 'execution.json'
        if not receipt.exists():
            continue
        report = json.loads(receipt.read_text(encoding='utf-8'))
        if host == 'claude' and not (report.get('loader') == 'native_skill_plugin'
                                     and report.get('native_skill_confirmed')):
            continue
        if report.get('snapshot') != hash_files(ROOT / version):
            continue
        if report.get('vocab') != hash_files(SOURCE.parent / 'vocab'):
            continue
        if not recovered and report.get('status') != 'completed':
            continue
        if report.get('requested_model') != MODELS[host]:
            continue
        request_file = folder / 'turn-1/prompt.txt'
        if not request_file.exists() or not request_file.read_text(encoding='utf-8').endswith(case['turns'][0]['prompt']):
            continue
        outputs = []
        native_skills = set()
        for index in range(1, len(case['turns']) + 1):
            path = folder / f'turn-{index}/events.jsonl'
            if not path.exists():
                break
            events = events_from(path.read_text(encoding='utf-8'))
            result = parse_result(host, events)
            native_skills.update(result['native_skills'])
            terminal = any(e.get('type') == ('turn.completed' if host == 'codex' else 'result') for e in events)
            if not terminal or result['error'] or not result['final'] or result['final'].startswith('API Error:'):
                break
            outputs.append(result['final'])
        if host == 'claude' and f"writing-eval:{case['entry_skill']}" not in native_skills:
            continue
        if len(outputs) == len(case['turns']):
            return {'folder': str(folder), 'outputs': outputs, 'route': report.get('route'),
                    'recovered_from_terminal_events': recovered}
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='review-current')
    args = parser.parse_args()
    target = ROOT / args.output_dir
    if not target.resolve().is_relative_to(ROOT.resolve()):
        parser.error('Review directory must stay within the evaluation workspace')
    target.mkdir(exist_ok=False)
    cases = {c['id']: c for c in json.loads(CASE_FILE.read_text(encoding='utf-8'))['evals']}
    mapping = []
    missing = []
    for host in ['codex', 'claude']:
        for case_id in SELECTION:
            case = cases[case_id]
            pair = {v: completed_run(host, v, case) for v in ['baseline', 'candidate']}
            if not all(pair.values()):
                missing.append({'host': host, 'case': case_id, 'reason': 'missing complete matched outputs'})
                continue
            if pair['baseline']['route'] != pair['candidate']['route']:
                # Early Codex baselines predate the explicit existing_cli route label.
                old_route = pair['baseline']['route'] or {'route': 'existing_cli'}
                new_route = pair['candidate']['route'] or {'route': 'existing_cli'}
                if old_route != new_route:
                    missing.append({'host': host, 'case': case_id, 'reason': 'request routes differ'})
                    continue
            order = random.SystemRandom().sample(list(pair), 2)
            group = len(mapping) + 1
            folder = target / f'comparison-{group:02d}'
            (folder / 'outputs').mkdir(parents=True)
            prompt = '\n\n'.join(f'第 {i} 轮：{t["prompt"]}' for i, t in enumerate(case['turns'], 1))
            write_json(folder / 'eval_metadata.json', {'eval_id': group,
                       'prompt': f'{host}。请判断哪版更自然且必要信息完整；也可选择持平或均不满意。\n\n{prompt}'})
            entry = {'group': group, 'host': host, 'case': case_id, 'versions': {}}
            for label, version in zip(['A', 'B'], order):
                prose = '\n\n'.join(f'## 第 {i} 轮\n\n{text}' for i, text in enumerate(pair[version]['outputs'], 1))
                (folder / 'outputs' / f'{label}.md').write_text(prose + '\n', encoding='utf-8')
                entry['versions'][label] = {'version': version, 'source': pair[version]['folder']}
            mapping.append(entry)
    write_json(target / 'blind-map.json', mapping)
    write_json(target / 'review-availability.json', {'ready_groups': len(mapping), 'missing': missing,
               'user_choices': [], 'quality_accepted': False,
               'note': 'Complete outputs only; no automatic style or read-scope pass. Raw traces remain available.'})
    print(json.dumps({'ready_groups': len(mapping), 'missing': missing}, ensure_ascii=False))


if __name__ == '__main__':
    main()
