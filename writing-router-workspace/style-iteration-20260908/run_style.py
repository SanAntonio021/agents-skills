"""Frozen full-context comparison. prepare is offline; run invokes paid CLI models.

python -B run_style.py prepare
python -B run_style.py run --host claude --arm installed [--case ID] [--timeout 300]
Run the other host/arm combinations separately. No overwrite, retries, or quality pass.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
SKILLS = ('writing-router', 'technical-writing', 'style-vocab')
INPUT_REFS = ('writing-router/SKILL.md',
              'writing-router/references/collaborative-writing.md',
              'writing-router/references/common-quality.md',
              'writing-router/references/ai-smell-catalog.md',
              'technical-writing/SKILL.md', 'style-vocab/SKILL.md')
MODELS = {'claude': 'claude-opus-4-6', 'codex': 'gpt-5.6-sol'}
TIMEOUT = 300


def prior():
    spec = importlib.util.spec_from_file_location(
        'style_prior', ROOT.parent / 'khazix-contrast-20260907/run_contrast.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.base, module.replay


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    """Exclusive writes also protect partial and failed runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(data)


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Expected a portable relative path')
    path = Path(value)
    if path.anchor or any(p in ('..', '.', '') for p in value.split('/')):
        raise ValueError('Unsafe relative path')
    return path


def child(root, value):
    path = root / relative(value)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes material root')
    return path


def load_cases(path):
    cases = json.loads(path.read_text(encoding='utf-8-sig'))['cases']
    if not isinstance(cases, list) or not cases:
        raise ValueError('cases must be a nonempty list')
    ids = set()
    for case in cases:
        name = case.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name) or name.lower() in ids:
            raise ValueError('Case IDs must be unique safe names')
        ids.add(name.lower())
        if (not isinstance(case.get('turns'), list) or not case['turns']
                or not all(isinstance(t, str) and t.strip() for t in case['turns'])):
            raise ValueError('Each case requires nonempty string turns')
        if not isinstance(case.get('vocab'), list):
            raise ValueError('Each case requires a vocab list')
        for value in case['vocab']:
            relative(value)
    return cases


def hashes(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def prepare(root=ROOT, installed=None, vocab=None, rules=None):
    home = Path(os.environ.get('USERPROFILE') or os.environ.get('HOME') or '')
    if not home.is_absolute() or not home.is_dir():
        raise ValueError('Host home is unavailable')
    installed = installed or home / '.codex/skills'
    cases = load_cases(root / 'cases.json')
    appendix = (root / 'candidate.md').read_text(encoding='utf-8')
    if not appendix.strip():
        raise ValueError('Candidate appendix is empty')
    if rules is None:
        local = home / '.agent-rules/local.md'
        body = local.read_text(encoding='utf-8')
        match = re.search(r'共享规范文件[^`\n]*`([^`]+)`', body)
        if not match or not Path(match[1]).is_absolute():
            raise ValueError('Shared rules path is unavailable')
        rules = [local, Path(match[1])]
    materials = {}
    for name in SKILLS:
        source = installed / name
        if not (source / 'SKILL.md').is_file():
            raise ValueError('Installed skill is missing: ' + name)
        for path in sorted(source.rglob('*')):
            if path.is_file() and path.suffix.lower() == '.md':
                if not path.resolve().is_relative_to(source.resolve()):
                    raise ValueError('Skill reference escapes its root')
                materials['installed/' + name + '/' + path.relative_to(source).as_posix()] = path
    for index, path in enumerate(rules):
        materials[f'rules/{index}-{path.name}'] = path
    old_vocab = root.parent / 'khazix-contrast-20260907/snapshot/vocab'
    current_vocab = root.parents[2] / 'vocab'
    for name in sorted({p for c in cases for p in c['vocab']}):
        source = child(vocab, name) if vocab else child(old_vocab, name)
        if not source.is_file() and vocab is None:
            source = child(current_vocab, name)
        materials['vocab/' + name] = source
    # Validate everything before reserving a snapshot; no partial input silently omitted.
    contents = {name: path.read_bytes() for name, path in materials.items()}
    for data in contents.values():
        data.decode('utf-8')
    for name in INPUT_REFS:
        if 'installed/' + name not in contents:
            raise ValueError('Required input is missing: ' + name)
    target = root / 'snapshot'
    target.mkdir(exist_ok=False)
    for name, data in contents.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    save(target / 'cases.json', {'cases': cases})
    save(target / 'candidate.md', appendix)
    save(root / 'snapshot-manifest.json', hashes(target))
    save(root / 'provenance.json', {
        'installed_root': str(installed), 'sources': {k: str(v) for k, v in materials.items()},
        'models': MODELS, 'effort': 'max', 'candidate_difference': 'appendix only',
        'loader': 'inline_full_materials', 'quality_accepted': False})


def verify(root):
    expected = json.loads((root / 'snapshot-manifest.json').read_text(encoding='utf-8'))
    if hashes(root / 'snapshot') != expected:
        raise ValueError('Frozen material changed or is incomplete')
    return expected


def prompt(root, arm, case, turn):
    if turn:
        return case['turns'][turn]
    parts = ['本次为完整规则输入对照，不测试自动技能触发。只在对话中回答，不写文件。'
             '以下是全部可用规则、词表和用户材料；不调用任何工具、插件、MCP、子智能体或网络，'
             '不读取外部样稿、记忆、其他会话或其他文件。个人样稿本轮不可用。'
             '规则中的文件读取由下方完整注入替代；用户任务的具体范围优先。']
    snapshot = root / 'snapshot'
    paths = sorted((snapshot / 'rules').rglob('*.md'))
    paths += [snapshot / 'installed' / name for name in INPUT_REFS]
    paths += [child(snapshot / 'vocab', name) for name in case['vocab']]
    for path in paths:
        parts.append(f'<material path="{path.relative_to(snapshot).as_posix()}">\n'
                     + path.read_text(encoding='utf-8') + '\n</material>')
    common = '\n\n'.join(parts)
    if arm == 'candidate':
        common += '\n\n<candidate_appendix>\n' + (snapshot / 'candidate.md').read_text(encoding='utf-8') + '\n</candidate_appendix>'
    elif arm != 'installed':
        raise ValueError('Unknown arm')
    return common + '\n\n<user_task>\n' + case['turns'][0] + '\n</user_task>'


def command(host, cwd, session, base, replay):
    args = base.command(host, cwd)
    # Historical helpers retain their old defaults; this experiment owns selection.
    args[args.index('--model') + 1] = MODELS[host]
    if host == 'claude':
        args[args.index('--tools') + 1] = ''
        index = args.index('--allowedTools')
        del args[index:index + 2]
        args += ['--no-chrome']
        if session:
            args += ['--resume', session]
        return args
    args = args[:-1]
    settings = ['sandbox_mode="read-only"', 'sandbox_read_only.network_access=false']
    settings += [f'features.{name}=false' for name in (
        'shell_tool', 'unified_exec', 'code_mode', 'code_mode_host', 'in_app_browser',
        'image_generation', 'workspace_dependencies', 'goals', 'multi_agent_v2',
        'skill_mcp_dependency_install', 'enable_mcp_apps', 'standalone_web_search')]
    for value in settings:
        args += ['-c', value]
    args += ['--ignore-rules']
    if session:
        args.insert(args.index('exec') + 1, 'resume')
        for flag in ('--sandbox', '-C'):
            index = args.index(flag)
            del args[index:index + 2]
        args += [session]
    return args + ['-']


def preflight(host, base, replay):
    # Read the required network policy before any external CLI invocation.
    policy = Path.home() / '.codex/skills/web-access/SKILL.md'
    policy_hash = sha(policy.read_bytes())
    prefix = [replay.CLAUDE] if host == 'claude' else [replay.NODE, replay.CODEX, 'exec']
    receipts = []
    for suffix in ([['--help']] if host == 'claude' else [['--help'], ['resume', '--help']]):
        result = subprocess.run(prefix + suffix, capture_output=True, text=True,
                                encoding='utf-8', timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('CLI help failed')
        probe = command(host, Path.cwd(), str(uuid.uuid4()) if 'resume' in suffix else None, base, replay)
        for flag in {p for p in probe if p.startswith('--')}:
            if flag not in result.stdout:
                raise RuntimeError('CLI does not support required option: ' + flag)
        receipts.append({'command': prefix + suffix, 'help': result.stdout})
    return {'web_access_sha256': policy_hash, 'cli': receipts}


def execute(argv, cwd, env, body, timeout):
    started = time.monotonic()
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='replace', creationflags=flags)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(body, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           capture_output=True, timeout=10, creationflags=flags)
        else:
            proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            stdout, stderr = exc.output or '', exc.stderr or ''
            if isinstance(stdout, bytes):
                stdout = stdout.decode('utf-8', errors='replace')
            if isinstance(stderr, bytes):
                stderr = stderr.decode('utf-8', errors='replace')
    return stdout, stderr, proc.returncode, timed_out, round(time.monotonic() - started, 3)


def assess(host, events, parsed, context, previous, code, timed_out):
    reasons = []
    session = parsed['session']
    try:
        uuid.UUID(session or '')
    except (ValueError, TypeError, AttributeError):
        reasons.append('missing_or_invalid_session')
    sessions = {e.get('session_id') or e.get('thread_id') for e in events}
    sessions.discard(None)
    if (previous and session != previous) or sessions != {session}:
        reasons.append('session_mismatch')
    if timed_out or code != 0 or parsed['error']:
        reasons.append('execution_failed')
    if not parsed['final'].strip():
        reasons.append('empty_final')
    terminal = [e for e in events if e.get('type') == ('result' if host == 'claude' else 'turn.completed')]
    if len(terminal) != 1 or (host == 'claude' and terminal[0].get('subtype') != 'success'):
        reasons.append('missing_success_completion')
    models = context.get('models', parsed['models'])
    if models != [MODELS[host]]:
        reasons.append('model_mismatch')
    if context.get('user_instructions_present') or context.get('automatic_skill_catalog_present'):
        reasons.append('automatic_context_present')
    if host == 'claude':
        init = context.get('init', [])
        if not init or any(e.get(k) for e in init for k in ('tools', 'skills', 'plugins', 'mcp_servers')):
            reasons.append('claude_isolation_unproven')
    elif not context.get('rollouts'):
        reasons.append('missing_context_evidence')
    tool_events = [e for e in events if e.get('item', {}).get('type') in (
        'command_execution', 'mcp_tool_call', 'web_search', 'file_change', 'tool_call')]
    if parsed['reads'] or tool_events:
        reasons.append('forbidden_tool_call')
    usage = [{k: e[k] for k in ('usage', 'modelUsage', 'total_cost_usd') if k in e}
             for e in terminal]
    if not usage or not any(u.get('usage') or u.get('modelUsage') for u in usage):
        reasons.append('missing_usage')
    return {'status': 'failed' if reasons else 'completed', 'reasons': reasons,
            'session': session, 'previous_session': previous, 'usage': usage,
            'models': models, 'exit_code': code, 'timed_out': timed_out,
            'quality_accepted': False, 'style_acceptance': 'not_reviewed'}


def run_case(root, host, arm, case, env, base, replay, timeout=TIMEOUT, executor=execute):
    if not 0 < timeout <= TIMEOUT:
        raise ValueError('timeout must be in (0, 300]')
    folder = root / 'runs' / host / arm / case['id'] / str(uuid.uuid4())
    folder.mkdir(parents=True, exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix='style-iteration-'))
    session = None
    turns = []
    conversation = []
    for index in range(len(case['turns'])):
        dest = folder / f'turn-{index + 1}'
        dest.mkdir()
        body = prompt(root, arm, case, index)
        save(dest / 'prompt.txt', body)
        save(dest / 'execution.json', {'status': 'started', 'expected_session': session,
             'timeout_seconds': timeout, 'prompt_sha256': sha(body.encode('utf-8')),
             'model': MODELS[host], 'effort': 'max', 'scratch': str(scratch)})
        stdout = stderr = ''
        parsed = {'reads': [], 'final': '', 'session': None}
        context = {}
        started = time.monotonic()
        result = {'status': 'failed', 'quality_accepted': False, 'reasons': ['runner_exception'],
                  'session': None, 'previous_session': session, 'models': [],
                  'exit_code': None, 'timed_out': False, 'usage': []}
        try:
            verify(root)
            argv = command(host, scratch, session, base, replay)
            save(dest / 'command.json', argv)
            stdout, stderr, code, timed_out, duration = executor(argv, scratch, env, body, timeout)
            events = [e for e in replay.events_from(stdout) if isinstance(e, dict)]
            parsed = replay.parse_result(host, events)
            context = base.context_evidence(host, parsed, events)
            if host == 'claude':
                context['automatic_context_check'] = 'safe-mode + empty settings sources + init inventory; no raw system prompt supplied by CLI'
                context['user_instructions_present'] = any(e.get('user_instructions') for e in events if e.get('type') == 'system')
                context['automatic_skill_catalog_present'] = any('<skills_instructions>' in json.dumps(e) for e in events if e.get('type') == 'system')
            result = assess(host, events, parsed, context, session, code, timed_out)
            result['duration_seconds'] = duration
            verify(root)
        except Exception as exc:
            result.update(status='failed', exception_type=type(exc).__name__,
                          exception=replay.redact(str(exc)))
            result.setdefault('reasons', []).append('runner_or_material_failure')
        result.setdefault('duration_seconds', round(time.monotonic() - started, 3))
        for name, value in [('events.jsonl', stdout), ('stderr.txt', stderr), ('final.md', parsed['final'])]:
            save(dest / name, replay.redact(value))
        for name, value in [('read-evidence.json', parsed['reads']), ('context-evidence.json', context),
                            ('session.json', {'expected': session, 'observed': parsed['session']}),
                            ('usage.json', result.get('usage', [])), ('completion.json', result)]:
            save(dest / name, replay.redact(json.dumps(value, ensure_ascii=False, indent=2)))
        turns.append(result)
        conversation.extend([{'role': 'user', 'content': body},
                             {'role': 'assistant', 'content': parsed['final']}])
        if result['status'] != 'completed':
            break
        session = result['session']
    summary = {'case': case['id'], 'host': host, 'arm': arm, 'turns': turns,
               'status': 'completed' if len(turns) == len(case['turns']) and all(t['status'] == 'completed' for t in turns) else 'failed',
               'quality_accepted': False, 'skipped_turns': len(case['turns']) - len(turns)}
    save(folder / 'conversation.json', replay.redact(json.dumps(conversation, ensure_ascii=False, indent=2)))
    save(folder / 'completion.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--host', choices=MODELS)
    parser.add_argument('--arm', choices=['installed', 'candidate'])
    parser.add_argument('--model', help='Explicit user-requested override for the selected host only')
    parser.add_argument('--case', help='Exact case ID; omit for all cases')
    parser.add_argument('--timeout', type=int, default=TIMEOUT)
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.model:
            parser.error('--model applies to run only')
        prepare()
        return
    if not args.host or not args.arm or not 0 < args.timeout <= TIMEOUT:
        parser.error('run requires --host, --arm and timeout in 1..300')
    if args.model:
        if not args.model.strip() or args.model.startswith('-'):
            parser.error('Invalid model identifier')
        MODELS[args.host] = args.model
    verify(ROOT)
    selected = [c for c in load_cases(ROOT / 'snapshot/cases.json') if not args.case or c['id'] == args.case]
    if not selected:
        parser.error('Unknown case')
    base, replay = prior()
    evidence = preflight(args.host, base, replay)
    env, route = replay.selected_claude_environment() if args.host == 'claude' else (os.environ.copy(), {'route': 'existing_cli'})
    save(ROOT / 'runs' / ('preflight-' + str(uuid.uuid4()) + '.json'),
         {'evidence': evidence, 'route': route, 'host': args.host, 'arm': args.arm,
          'requested_model': MODELS[args.host], 'explicit_override': args.model,
          'snapshot_manifest_sha256': sha((ROOT / 'snapshot-manifest.json').read_bytes())})
    failed = False
    for case in selected:
        result = run_case(ROOT, args.host, args.arm, case, env, base, replay, args.timeout)
        print(json.dumps({k: result[k] for k in ('case', 'host', 'arm', 'status')}, ensure_ascii=False))
        failed |= result['status'] != 'completed'
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
