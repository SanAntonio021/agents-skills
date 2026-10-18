"""Fresh-session writing ablation; never changes installed CLI configuration."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import tomllib
import uuid

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent
spec = importlib.util.spec_from_file_location('ablation_replay', ROOT.parent / 'paragraph-quality-20260907/run_evaluation.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
SKILLS = ['writing-router', 'research-report', 'ieee-manuscript-edit',
          'technical-writing', 'project-writing', 'meeting-notes', 'style-vocab']
VOCAB = SOURCE.parent / 'vocab'
CODEX_HOME = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')


def required_refs(case):
    refs = ['writing-router/SKILL.md', 'writing-router/references/collaborative-writing.md',
            'writing-router/references/common-quality.md', 'writing-router/references/ai-smell-catalog.md',
            'style-vocab/SKILL.md']
    if case['id'] == 'sensor-summary':
        refs += ['research-report/SKILL.md', 'research-report/references/modes.md',
                 'research-report/references/report-contract.md', 'research-report/references/research-ledger.md']
    elif case['id'] == 'paper-heading-only':
        refs += ['ieee-manuscript-edit/SKILL.md', 'ieee-manuscript-edit/references/chinese-paper.md']
    return refs


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()
            and not p.name.endswith('.baiduyun.uploading.cfg')
            and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts}


def prepare():
    target = ROOT / 'snapshot'
    target.mkdir(exist_ok=False)
    for name in SKILLS:
        shutil.copytree(SOURCE / name, target / name,
                        ignore=shutil.ignore_patterns('*.baiduyun.uploading.cfg', '__pycache__', '.pytest_cache'))
    replay.write_json(ROOT / 'snapshot-manifest.json', hashes(target))


def make_prompt(arm, case, inline_vocab=False):
    common = ('只在最终回复中交付本次任务要求的正文，不创建或修改文件。'
              '工具返回只供内部检查，不附在最终回复中。'
              '不使用其他会话、记忆、私有样稿、子智能体、网络或业务系统。'
              '先只读以下适用词表，两组均使用这些词表：'
              + '、'.join((VOCAB / path).as_posix() for path in case['vocab']) + '。')
    if inline_vocab:
        common = ('只在最终回复中交付本次任务要求的正文，不创建或修改文件。'
                  '工具返回只供内部检查，不附在最终回复中。'
                  '不使用其他会话、记忆、私有样稿、子智能体、网络或业务系统。'
                  '以下已提供本轮适用词表的完整正文，两组均使用这些词表，不再读取其他词表副本。')
        for relative in case['vocab']:
            path = VOCAB / relative
            common += f'\n<vocabulary path="{path.as_posix()}">\n{path.read_text(encoding="utf-8")}\n</vocabulary>\n'
    if arm == 'loaded-skill':
        treatment = '以下已提供本轮适用技能及参考文件的完整正文，按它们处理任务；不再读取这些文件的其他副本。'
        for relative in required_refs(case):
            path = ROOT / 'snapshot' / relative
            treatment += f'\n<skill_reference path="{path.as_posix()}">\n{path.read_text(encoding="utf-8")}\n</skill_reference>\n'
    elif arm == 'with-skill':
        treatment = (f'读取 {(ROOT / "snapshot/writing-router/SKILL.md").as_posix()}，'
                     f'按该入口读取本轮所需技能及参考文件；只使用 {(ROOT / "snapshot").as_posix()} 下的版本。'
                     '不要读取已安装的技能副本、测试材料或其他版本。')
    else:
        treatment = '本次不使用写作技能；不读取任何 SKILL.md、技能参考文件、测试材料或技能脚本，只依据用户材料和上述词表处理。'
    return common + treatment + '\n\n' + case['prompt']


def command(host, cwd):
    if host == 'claude':
        return [replay.CLAUDE, '--safe-mode', '--print', '--verbose', '--output-format', 'stream-json',
                '--model', replay.MODELS[host], '--effort', 'max', '--setting-sources', '',
                '--disable-slash-commands', '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep',
                '--permission-mode', 'dontAsk', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
    args = [replay.NODE, replay.CODEX, 'exec', '--model', replay.MODELS[host],
            '--sandbox', 'read-only', '--skip-git-repo-check', '--json', '-C', str(cwd)]
    settings = ['model_reasoning_effort="max"', 'approval_policy="never"',
                'project_doc_max_bytes=0', 'developer_instructions=""',
                'skills.include_instructions=false', 'web_search="disabled"']
    settings += [f'features.{name}=false' for name in
                 ['plugins', 'memories', 'skill_search', 'hooks', 'apps', 'browser_use',
                  'browser_use_external', 'computer_use', 'multi_agent', 'remote_plugin']]
    config = CODEX_HOME / 'config.toml'
    if config.exists():
        data = tomllib.loads(config.read_text(encoding='utf-8'))
        for name in data.get('mcp_servers', {}):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                raise ValueError('MCP server name needs a separately verified CLI key encoding')
            settings.append(f'mcp_servers.{name}.enabled=false')
    for value in settings:
        args += ['-c', value]
    return args + ['-']


def context_evidence(host, parsed, events):
    if host == 'claude':
        init = [e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init']
        return {'init': [{k: e.get(k) for k in ['model', 'tools', 'skills', 'plugins', 'mcp_servers']} for e in init]}
    result = {'rollouts': [], 'models': [], 'user_instructions_present': False,
              'automatic_skill_catalog_present': False}
    if not parsed['session']:
        return result
    for path in (CODEX_HOME / 'sessions').rglob(f'*{parsed["session"]}.jsonl'):
        result['rollouts'].append(str(path))
        for event in replay.events_from(path.read_text(encoding='utf-8')):
            payload = event.get('payload', {})
            if event.get('type') == 'turn_context':
                result['models'].append(payload.get('model'))
                result['user_instructions_present'] |= bool(payload.get('user_instructions'))
            if event.get('type') == 'response_item' and payload.get('role') in ['developer', 'user']:
                result['automatic_skill_catalog_present'] |= '<skills_instructions>' in json.dumps(payload)
    result['models'] = sorted({m for m in result['models'] if m})
    return result


def run_one(host, arm, case, repeat, timeout, env, route, inline_vocab=False):
    folder = ROOT / ('controlled-runs' if inline_vocab else 'runs') / host / arm / case['id'] / f'repeat-{repeat}'
    if folder.exists():
        folder = folder / f'attempt-{uuid.uuid4()}'
    folder.mkdir(parents=True, exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix='writing-ablation-'))
    before = hashes(ROOT / 'snapshot')
    vocab_before = hashes(VOCAB)
    expected = json.loads((ROOT / 'snapshot-manifest.json').read_text(encoding='utf-8'))
    if before != expected:
        raise RuntimeError('Frozen snapshot changed')
    prompt = make_prompt(arm, case, inline_vocab)
    (folder / 'prompt.txt').write_text(prompt, encoding='utf-8')
    args = command(host, scratch)
    replay.write_json(folder / 'command.json', args)
    report = {'host': host, 'arm': arm, 'case': case['id'], 'repeat': repeat,
              'requested_model': replay.MODELS[host], 'route': route, 'scratch': str(scratch),
              'status': 'running', 'snapshot': before, 'vocab': vocab_before,
              'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
              'loader': 'inline_rules' if arm == 'loaded-skill' else 'explicit_file_reads',
              'vocab_loader': 'inline' if inline_vocab else 'requested_file_reads',
              'quality_accepted': False}
    replay.write_json(folder / 'execution.json', report)
    started = time.monotonic()
    process = subprocess.Popen(args, cwd=scratch, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace',
                               creationflags=subprocess.CREATE_NO_WINDOW)
    timed_out = False
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        stdout, stderr = process.communicate(timeout=20)
    events = replay.events_from(stdout)
    parsed = replay.parse_result(host, events)
    context = context_evidence(host, parsed, events)
    models = context.get('models', parsed['models'])
    (folder / 'events.jsonl').write_text(replay.redact(stdout), encoding='utf-8')
    (folder / 'stderr.txt').write_text(replay.redact(stderr), encoding='utf-8')
    (folder / 'final.md').write_text(replay.redact(parsed['final']), encoding='utf-8')
    replay.write_json(folder / 'read-evidence.json', parsed['reads'])
    replay.write_json(folder / 'context-evidence.json', context)
    isolated = not (context.get('user_instructions_present') or context.get('automatic_skill_catalog_present'))
    if host == 'claude':
        isolated &= bool(context['init']) and all(not e.get('skills') and not e.get('plugins')
                                                and not e.get('mcp_servers') for e in context['init'])
    material_ok = before == hashes(ROOT / 'snapshot') and vocab_before == hashes(VOCAB)
    report.update(timed_out=timed_out, exit_code=process.returncode,
                  duration_seconds=round(time.monotonic() - started, 1), session=parsed['session'],
                  models=models, automatic_context_isolated=isolated,
                  material_unchanged=material_ok, read_scope='pending_review',
                  tool_calls=len(parsed['reads']))
    ok = (not timed_out and process.returncode == 0 and not parsed['error'] and bool(parsed['final'])
          and models == [replay.MODELS[host]] and isolated and material_ok)
    report['status'] = 'completed' if ok else 'failed'
    replay.write_json(folder / 'completion.json', report)
    print(json.dumps({k: report[k] for k in ['host', 'arm', 'case', 'repeat', 'status',
                                           'duration_seconds', 'tool_calls', 'automatic_context_isolated']},
                     ensure_ascii=False), flush=True)
    return ok


def run(args):
    env, route = replay.selected_claude_environment() if args.host == 'claude' else (os.environ.copy(), {'route': 'existing_cli'})
    cases = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['cases']
    # Counterbalance case order across repeats; the arm flag changes only skill instructions.
    failed = []
    for repeat in range(1, args.repeats + 1):
        for case in cases if repeat % 2 else list(reversed(cases)):
            if not run_one(args.host, args.arm, case, repeat, args.timeout, env, route, args.inline_vocab):
                failed.append((repeat, case['id']))
                if repeat == 1 and case == cases[0]:
                    raise SystemExit('Initial run failed; inspect isolation/model/transport before continuing')
    if failed:
        raise SystemExit('Incomplete runs: ' + str(failed))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--host', choices=replay.MODELS)
    parser.add_argument('--arm', choices=['with-skill', 'without-skill', 'loaded-skill'])
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--inline-vocab', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.host and args.arm:
        run(args)
    else:
        parser.error('run requires host and arm')
