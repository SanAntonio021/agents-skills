"""Build single-turn comparison groups with unedited, explicitly named outputs."""
import argparse
import json
from pathlib import Path

from contrast import ROOT, ENTRIES, CASES, replay, material_state


def excluded_runs():
    path = ROOT / 'excluded-runs.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def collect_run(host, version, case):
    if not material_state(version)['valid']:
        return None
    exclusions = excluded_runs()
    parent = ROOT / 'runs' / host / version / case['id']
    for receipt in sorted(parent.glob('*/completion.json'), reverse=True):
        if receipt.parent.relative_to(ROOT).as_posix() in exclusions:
            continue
        report = json.loads(receipt.read_text(encoding='utf-8'))
        if report['status'] != 'completed' or len(report['turns']) != len(case['turns']):
            continue
        if report['snapshot'] != replay.hash_files(ROOT / version):
            continue
        if not report['snapshot_unchanged'] or not report['vocab_unchanged']:
            continue
        if report['vocab'] != replay.hash_files(replay.SOURCE.parent / 'vocab'):
            continue
        if any(not turn['model_valid'] for turn in report['turns']):
            continue
        finals = []
        for index, turn in enumerate(case['turns'], 1):
            folder = receipt.parent / f'turn-{index}'
            actual = (folder / 'prompt.txt').read_text(encoding='utf-8')
            if (index == 1 and not actual.endswith('\n\n' + turn['prompt'])) or (index > 1 and actual != turn['prompt']):
                break
            events = replay.events_from((folder / 'events.jsonl').read_text(encoding='utf-8'))
            result = replay.parse_result(host, events)
            if result['error'] or not result['final']:
                break
            if host == 'claude' and index == 1 and f'writing-eval:{ENTRIES[version]}' not in result['native_skills']:
                break
            finals.append(result['final'])
        if len(finals) == len(case['turns']):
            return {'source': str(receipt.parent), 'route': report['route'], 'outputs': finals}
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='review')
    parser.add_argument('--candidate', choices=['local-after', 'local-refined'], default='local-after')
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    target = (ROOT / args.output).resolve()
    if not target.is_relative_to(ROOT.resolve()):
        parser.error('Output must remain in this workspace')
    target.mkdir(exist_ok=False)
    suite = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['evals']
    cases = {case['id']: case for case in suite}
    groups, missing, selected = [], [], []
    labels = {'humanizer-original': 'Humanizer-zh_original', 'waza-original': 'Waza_original',
              'local-before': 'Local_before', 'local-after': 'Local_after', 'local-refined': 'Local_refined'}
    versions = ['humanizer-original', 'waza-original', 'local-before', args.candidate]
    for host in ['claude', 'codex']:
        for case_id in CASES:
            case = cases[case_id]
            runs = {version: collect_run(host, version, case) for version in versions}
            if not all(runs.values()):
                missing.append({'host': host, 'case': case_id,
                                'versions': [v for v, r in runs.items() if not r]})
                if not args.allow_incomplete or sum(bool(r) for r in runs.values()) < 2:
                    continue
            missing_versions = [v for v, r in runs.items() if not r]
            runs = {v: r for v, r in runs.items() if r}
            if len({json.dumps(r['route'], sort_keys=True) for r in runs.values()}) != 1:
                missing.append({'host': host, 'case': case_id, 'reason': 'routes differ'})
                continue
            selected.append({'host': host, 'case': case_id, 'runs': runs})
            for index, turn in enumerate(case['turns'], 1):
                number = len(groups) + 1
                folder = target / f'comparison-{number:02d}'
                (folder / 'outputs').mkdir(parents=True)
                history = '\n\n'.join(f'第 {n} 轮任务：{item["prompt"]}'
                                      for n, item in enumerate(case['turns'][:index], 1))
                replay.write_json(folder / 'eval_metadata.json', {
                    'eval_id': number, 'eval_name': f'{host}-{case_id}-turn-{index}',
                    'prompt': f'{host}，{case_id}，第 {index} 轮。同一轮完整输出，非盲评。缺失版本：{missing_versions or "无"}。\n\n{history}',
                })
                for version, run in runs.items():
                    (folder / 'outputs' / f'{labels[version]}.md').write_text(run['outputs'][index - 1], encoding='utf-8')
                groups.append({'group': number, 'host': host, 'case': case_id, 'turn': index})
    replay.write_json(target / 'selection.json', selected)
    replay.write_json(target / 'availability.json', {'groups': groups, 'missing': missing,
                       'excluded_runs': exclusions if (exclusions := excluded_runs()) else {},
                       'integrity_note': 'Current full snapshots/plugins match frozen manifests; historical per-case receipts protect Markdown and vocabulary, not every file type.',
                       'blind': False, 'user_choices': [], 'quality_accepted': False})
    print(json.dumps({'ready_groups': len(groups), 'missing': missing}, ensure_ascii=False))


if __name__ == '__main__':
    main()
