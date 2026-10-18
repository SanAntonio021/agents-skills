"""Three frozen writing contexts, equal vocab, fresh sessions, no installation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent
SPEC = importlib.util.spec_from_file_location('prior_ablation', ROOT.parent / 'ablation-20260907/run_ablation.py')
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
replay = base.replay
COMMIT = '7a5c4934be4106ac740ffdb95280bb81b3f4b83c'
ARMS = ['local', 'khazix', 'examples']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    replay.write_json(path, data)


def cases():
    return json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['cases']


def local_refs(case):
    refs = ['writing-router/SKILL.md', 'writing-router/references/collaborative-writing.md',
            'writing-router/references/common-quality.md', 'writing-router/references/ai-smell-catalog.md',
            'style-vocab/SKILL.md']
    if case['genre'] == 'research_report':
        refs += ['research-report/SKILL.md', 'research-report/references/modes.md',
                 'research-report/references/report-contract.md', 'research-report/references/research-ledger.md']
    elif case['genre'] == 'paper':
        refs += ['ieee-manuscript-edit/SKILL.md', 'ieee-manuscript-edit/references/chinese-paper.md',
                 'writing-router/references/exact-edit.md']
    else:
        refs += ['technical-writing/SKILL.md']
    return refs


def material_refs(arm, case):
    if arm == 'khazix':
        return ['upstream/khazix-writer/' + p for p in
                ['SKILL.md', 'references/style_examples.md', 'references/content_methodology.md']]
    refs = ['local/' + p for p in local_refs(case)]
    return refs + (['candidate/examples.md'] if arm == 'examples' else [])


def prompt(arm, case):
    parts = ['只在最终回复中交付本次任务要求的正文，不创建或修改文件。工具返回只供内部检查，不附在最终回复中。'
             '不使用其他会话、记忆、私有样稿、子智能体、网络或业务系统。'
             '以下提供本轮词表与写作规则的完整正文，只使用所提供的版本，不读取其他副本。'
             '用户的具体任务范围优先于写作规则中的通用格式。']
    for relative in case['vocab']:
        path = ROOT / 'snapshot/vocab' / relative
        parts.append(f'<vocabulary path="{path.as_posix()}">\n{path.read_text(encoding="utf-8")}\n</vocabulary>')
    for relative in material_refs(arm, case):
        path = ROOT / 'snapshot' / relative
        parts.append(f'<skill_reference path="{path.as_posix()}">\n{path.read_text(encoding="utf-8")}\n</skill_reference>')
    return '\n'.join(parts) + '\n\n' + case['prompt']


def prepare():
    target = ROOT / 'snapshot'
    target.mkdir(exist_ok=False)
    for name in base.SKILLS:
        shutil.copytree(SOURCE / name, target / 'local' / name,
                        ignore=shutil.ignore_patterns('*.baiduyun.uploading.cfg', '__pycache__', '.pytest_cache'))
    (target / 'candidate').mkdir()
    shutil.copyfile(ROOT / 'examples.md', target / 'candidate/examples.md')
    for relative in sorted({p for c in cases() for p in c['vocab']}):
        path = target / 'vocab' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE.parent / 'vocab' / relative, path)
    downloads = []
    for relative in ['LICENSE', 'khazix-writer/SKILL.md', 'khazix-writer/references/style_examples.md',
                     'khazix-writer/references/content_methodology.md']:
        path = target / 'upstream' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f'https://raw.githubusercontent.com/KKKKhazix/khazix-skills/{COMMIT}/{relative}'
        for attempt, delay in enumerate([0, 10, 30], 1):
            time.sleep(delay)
            result = subprocess.run(['curl.exe', '--silent', '--show-error', '--fail', '--location',
                                     '--max-time', '30', url], capture_output=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=40)
            downloads.append({'url': url, 'attempt': attempt, 'exit_code': result.returncode,
                              'error': result.stderr.decode('utf-8', errors='replace')})
            write_json(ROOT / 'downloads.json', downloads)
            if result.returncode == 0:
                result.stdout.decode('utf-8')
                with path.open('xb') as stream:
                    stream.write(result.stdout)
                break
        else:
            raise RuntimeError('Download failed; retained partial preparation: ' + relative)
    (target / 'upstream/LICENSE').read_text(encoding='utf-8').index('MIT License')
    for case in cases():
        for arm in ARMS:
            prompt(arm, case)
    write_json(ROOT / 'snapshot-manifest.json', base.hashes(target))
    write_json(ROOT / 'provenance.json', {
        'upstream_commit': COMMIT, 'upstream_repository': 'https://github.com/KKKKhazix/khazix-skills',
        'local_is': 'Current source worktree, not installed runtime',
        'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip(),
        'source_status': subprocess.check_output(['git', 'status', '--short'], cwd=SOURCE, text=True, encoding='utf-8'),
        'candidate_change': 'Only the synthetic before/after examples appendix; local rule bodies unchanged',
        'case_sha256': digest((ROOT / 'cases.json').read_bytes()),
        'models': replay.MODELS, 'effort': 'max', 'runtime_modified': False})
    print('Prepared frozen contexts; no installed skill changes.', flush=True)


def seal():
    if (ROOT / 'runs').exists():
        raise RuntimeError('Cannot change material after experiments start')
    shutil.copyfile(ROOT / 'snapshot-manifest.json', ROOT / 'preflight-manifest.json')
    shutil.copyfile(ROOT / 'examples.md', ROOT / 'snapshot/candidate/examples.md')
    for case in cases():
        for arm in ARMS:
            prompt(arm, case)
    write_json(ROOT / 'snapshot-manifest.json', base.hashes(ROOT / 'snapshot'))
    provenance = json.loads((ROOT / 'provenance.json').read_text(encoding='utf-8'))
    provenance['case_sha256'] = digest((ROOT / 'cases.json').read_bytes())
    provenance['preflight_changes'] = 'Clarified size requirement and negation scope; added required-limit summary control before first run'
    write_json(ROOT / 'provenance.json', provenance)
    print('Preflight audit fixes sealed before first model run.')


def run_one(host, arm, case, repeat, env, route, timeout):
    expected = json.loads((ROOT / 'snapshot-manifest.json').read_text(encoding='utf-8'))
    if base.hashes(ROOT / 'snapshot') != expected:
        raise RuntimeError('Frozen material changed')
    folder = ROOT / 'runs' / host / arm / case['id'] / f'repeat-{repeat}'
    if folder.exists():
        folder = folder / f'attempt-{uuid.uuid4()}'
    folder.mkdir(parents=True, exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix='khazix-contrast-'))
    body = prompt(arm, case)
    (folder / 'prompt.txt').write_bytes(body.encode('utf-8'))
    argv = base.command(host, scratch)
    write_json(folder / 'command.json', argv)
    receipt = {'host': host, 'arm': arm, 'case': case['id'], 'repeat': repeat,
               'requested_model': replay.MODELS[host], 'route': route, 'scratch': str(scratch),
               'prompt_sha256': digest(body.encode('utf-8')), 'status': 'running',
               'loader': 'inline_full_rules_and_vocabulary', 'references': material_refs(arm, case),
               'upstream_scope': case['upstream_scope'] if arm == 'khazix' else 'applicable',
               'quality_accepted': False, 'snapshot_manifest_sha256': digest((ROOT / 'snapshot-manifest.json').read_bytes())}
    write_json(folder / 'execution.json', receipt)
    start = time.monotonic()
    proc = subprocess.Popen(argv, cwd=scratch, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(body, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        stdout, stderr = proc.communicate(timeout=20)
    events = replay.events_from(stdout)
    parsed = replay.parse_result(host, events)
    context = base.context_evidence(host, parsed, events)
    models = context.get('models', parsed['models'])
    for name, value in [('events.jsonl', stdout), ('stderr.txt', stderr), ('final.md', parsed['final'])]:
        (folder / name).write_bytes(replay.redact(value).encode('utf-8'))
    write_json(folder / 'read-evidence.json', parsed['reads'])
    write_json(folder / 'context-evidence.json', context)
    isolated = not (context.get('user_instructions_present') or context.get('automatic_skill_catalog_present'))
    if host == 'claude':
        isolated &= bool(context['init']) and all(not x.get('skills') and not x.get('plugins') and not x.get('mcp_servers') for x in context['init'])
    material_ok = base.hashes(ROOT / 'snapshot') == expected
    ok = not timed_out and proc.returncode == 0 and not parsed['error'] and bool(parsed['final']) and models == [replay.MODELS[host]] and isolated and material_ok
    receipt.update(status='completed' if ok else 'failed', models=models, session=parsed['session'],
                   duration_seconds=round(time.monotonic() - start, 1), timed_out=timed_out,
                   exit_code=proc.returncode, material_unchanged=material_ok,
                   automatic_catalog_and_user_context_absent=isolated,
                   background_rules='Host rules may remain; inspect successful reads, not a fully blank system context',
                   read_scope='pending_review')
    write_json(folder / 'completion.json', receipt)
    print(json.dumps({k: receipt[k] for k in ['host', 'arm', 'case', 'repeat', 'status', 'duration_seconds']}, ensure_ascii=False), flush=True)
    return ok


def run(args):
    env, route = replay.selected_claude_environment() if args.host == 'claude' else (os.environ.copy(), {'route': 'existing_cli'})
    selected = [c for c in cases() if not args.case or c['id'] == args.case]
    failures = []
    for repeat in range(1, args.repeats + 1):
        for case in selected if repeat % 2 else list(reversed(selected)):
            if not run_one(args.host, args.arm, case, repeat, env, route, args.timeout):
                failures.append((case['id'], repeat))
                if repeat == 1 and case == selected[0]:
                    raise SystemExit('Initial failure; inspect before further runs')
    if failures:
        raise SystemExit('Incomplete runs: ' + str(failures))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'seal', 'run'])
    p.add_argument('--host', choices=list(replay.MODELS))
    p.add_argument('--arm', choices=ARMS)
    p.add_argument('--case')
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--timeout', type=int, default=300)
    args = p.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'seal':
        seal()
    elif args.host and args.arm:
        run(args)
    else:
        p.error('run needs host and arm')
