"""Local synthetic replay; prompt scoping and read receipts, not a read sandbox."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sqlite3
import time
import uuid

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent
CASE_FILE = SOURCE / 'writing-router/evals/paragraph-quality.json'
MODELS = {'codex': 'gpt-5.6-sol', 'claude': 'claude-opus-5'}
NODE = r'D:\Program Files\nodejs\node.exe'
CODEX = str(Path.home() / 'AppData/Roaming/npm/node_modules/@openai/codex/bin/codex.js')
CLAUDE = str(Path.home() / 'AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe')
PRIVATE_VALUES = []


def redact(text):
    for value in PRIVATE_VALUES:
        if value:
            text = text.replace(value, '[REDACTED]')
    for key, value in os.environ.items():
        if len(value) >= 8 and re.search('KEY|TOKEN|SECRET|PASSWORD|COOKIE', key, re.I):
            text = text.replace(value, '[REDACTED]')
    return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}|Bearer\s+[^\s"\\]+', '[REDACTED]', text)


def write_json(path, value):
    path.write_text(redact(json.dumps(value, ensure_ascii=False, indent=2)) + '\n', encoding='utf-8')


def events_from(text):
    result = []
    for line in text.splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


def parse_result(host, events):
    session = None
    final = ''
    models = set()
    reads = []
    error = False
    skill_calls = {}
    successful_results = set()
    for event in events:
        session = event.get('session_id', event.get('thread_id', session))
        if host == 'claude':
            message = event.get('message', {})
            if isinstance(message, dict):
                if message.get('model'):
                    models.add(message['model'])
                for block in message.get('content', []):
                    if block.get('type') == 'tool_use':
                        reads.append({'name': block.get('name'), 'input': block.get('input')})
                        if block.get('name') == 'Skill':
                            skill_calls[block.get('id')] = block.get('input', {}).get('skill')
            if event.get('type') == 'user':
                for block in event.get('message', {}).get('content', []):
                    if block.get('type') == 'tool_result' and not block.get('is_error'):
                        successful_results.add(block.get('tool_use_id'))
            if event.get('model'):
                models.add(event['model'])
            if event.get('type') == 'result':
                final = event.get('result', '')
                error |= bool(event.get('is_error'))
                models.update(event.get('modelUsage', {}).keys())
        else:
            item = event.get('item', {})
            if event.get('type') == 'item.completed':
                if item.get('type') == 'agent_message':
                    final = item.get('text', '')
                elif item.get('type') == 'command_execution':
                    reads.append({'command': item.get('command'), 'exit_code': item.get('exit_code'),
                                  'output': item.get('aggregated_output', '')})
            if event.get('type') in {'error', 'turn.failed'}:
                error = True
    models.discard('<synthetic>')
    return {'session': session, 'final': final, 'models': sorted(models), 'reads': reads, 'error': error,
            'native_skills': [skill_calls[key] for key in successful_results if skill_calls.get(key)]}


def hash_files(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*.md')) if '.git' not in p.parts}


def initial_prompt(snapshot, entry, prompt, native=False):
    return (
        '这是独立的合成中文文稿任务，不对应真实项目。只在对话中交付，不创建或修改任何文件。'
        f'本次业务技能仅从 {snapshot.as_posix()} 读取，入口为 '
        f'{(snapshot / entry / "SKILL.md").as_posix()}。'
        + (f'请通过 Skill 工具调用 writing-eval:{entry}，使用本次临时插件中的技能。' if native else '')
        + '按入口选择本次文体并读取所需参考文件。'
        '沿相对链接仍在该技能快照内读取，不读取其他版本、源码工作树、已安装业务技能、'
        '历史对话、记忆或评测用例文件。个人样稿本次不可用，不读取writing-profile或writing-samples。'
        f'适用个人词表可只读 {str(SOURCE.parent / "vocab")}。'
        '不调用子智能体、业务系统或网络检索。读取限制由本次提示约定，不要求调整任何系统权限。'
        '\n\n' + prompt
    )


def command(host, cwd, session, direct=False, plugin=None):
    model = MODELS[host]
    if host == 'claude':
        args = [CLAUDE, '--bare' if direct else '--safe-mode', '--print', '--verbose', '--output-format', 'stream-json',
                '--model', model, '--effort', 'max', '--tools', 'Read,Glob,Grep,Skill' if plugin else 'Read,Glob,Grep',
                '--allowedTools', 'Read,Glob,Grep,Skill' if plugin else 'Read,Glob,Grep', '--permission-mode', 'dontAsk',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
        if direct:
            args += ['--setting-sources', '']
            if not plugin:
                args += ['--disable-slash-commands']
        if plugin:
            if direct:
                args.remove('--bare')
            args += ['--plugin-dir', str(plugin)]
        if session:
            args += ['--resume', session]
        return args
    args = [NODE, CODEX, 'exec']
    if session:
        args += ['resume']
    args += ['--model', model, '-c', 'model_reasoning_effort="max"',
             '-c', 'approval_policy="never"', '-c', 'sandbox_mode="read-only"',
             '--skip-git-repo-check', '--json']
    if session:
        args += [session, '-']
    else:
        args += ['--sandbox', 'read-only', '-C', str(cwd), '-']
    return args


def selected_claude_environment():
    path = Path.home() / '.cc-switch/cc-switch.db'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute(
            'select name,settings_config from providers where app_type=? and is_current=1',
            ('claude',)).fetchall()
    if len(rows) != 1:
        raise RuntimeError('Current Claude provider is not unique')
    name, raw = rows[0]
    config = json.loads(raw).get('env', {})
    endpoint = config.get('ANTHROPIC_BASE_URL', '')
    if not endpoint.startswith('https://'):
        raise RuntimeError('Selected upstream is not an HTTPS provider')
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('ANTHROPIC_'):
            del env[key]
    for key in ['ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY']:
        if config.get(key):
            env[key] = config[key]
            if key != 'ANTHROPIC_BASE_URL':
                PRIVATE_VALUES.append(config[key])
    if not (env.get('ANTHROPIC_AUTH_TOKEN') or env.get('ANTHROPIC_API_KEY')):
        raise RuntimeError('Selected upstream has no Claude credential')
    return env, {'route': 'direct_selected_provider_child_env_only', 'name': name, 'endpoint': endpoint}


def run(host, version, case, timeout, max_turns, direct=False, native=False):
    snapshot = ROOT / version
    folder = ROOT / 'runs' / host / version / case['id'] / time.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=False)
    before = hash_files(snapshot)
    plugin = ROOT / 'plugins' / version if native else None
    material = plugin / 'skills' if plugin else snapshot
    if plugin and hash_files(material) != before:
        raise RuntimeError('Temporary plugin differs from the selected snapshot')
    vocab_before = hash_files(SOURCE.parent / 'vocab')
    env, route = selected_claude_environment() if direct else (os.environ.copy(), {'route': 'existing_cli'})
    report = {'host': host, 'version': version, 'case': case['id'], 'requested_model': MODELS[host],
              'requested_effort': 'max', 'status': 'running', 'turns': [],
              'snapshot': before, 'vocab': vocab_before,
              'isolation': 'separate case sessions; prompt scoping plus post-run read inspection, not an OS read sandbox',
              'style_acceptance': 'not_reviewed', 'read_scope_acceptance': 'not_reviewed', 'route': route,
              'loader': 'native_skill_plugin' if native else 'explicit_file_reads',
              'native_skill_confirmed': False}
    write_json(folder / 'execution.json', report)
    session = None
    for index, turn in enumerate(case['turns'][:max_turns], 1):
        turn_dir = folder / f'turn-{index}'
        turn_dir.mkdir()
        prompt = initial_prompt(material, case['entry_skill'], turn['prompt'], native) if index == 1 else turn['prompt']
        (turn_dir / 'prompt.txt').write_text(prompt, encoding='utf-8')
        argv = command(host, folder, session, direct, plugin)
        write_json(turn_dir / 'command.json', argv)
        start = time.monotonic()
        process = subprocess.Popen(argv, cwd=folder, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        timed_out = False
        try:
            stdout, stderr = process.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            stdout, stderr = process.communicate(timeout=20)
        (turn_dir / 'events.jsonl').write_text(redact(stdout), encoding='utf-8')
        (turn_dir / 'stderr.txt').write_text(redact(stderr), encoding='utf-8')
        parsed = parse_result(host, events_from(stdout))
        if f"writing-eval:{case['entry_skill']}" in parsed['native_skills']:
            report['native_skill_confirmed'] = True
        session = parsed['session'] or session
        if session:
            try:
                uuid.UUID(session)
            except ValueError:
                parsed['error'] = True
                session = None
        if host == 'codex' and session:
            rollouts = list((Path.home() / '.codex/sessions').rglob(f'*{session}.jsonl'))
            for path in rollouts:
                for e in events_from(path.read_text(encoding='utf-8')):
                    if e.get('type') == 'turn_context' and e.get('payload', {}).get('model'):
                        parsed['models'].append(e['payload']['model'])
            parsed['models'] = sorted(set(parsed['models']))
        (turn_dir / 'final.md').write_text(redact(parsed['final']), encoding='utf-8')
        write_json(turn_dir / 'read-evidence.json', parsed['reads'])
        ok = not (timed_out or process.returncode or parsed['error']) and bool(parsed['final']) and bool(session)
        if native and not report['native_skill_confirmed']:
            ok = False
        model_valid = parsed['models'] == [MODELS[host]]
        status = {'turn': index, 'exit_code': process.returncode, 'timed_out': timed_out,
                  'duration_seconds': round(time.monotonic() - start, 1), 'reported_models': parsed['models'],
                  'model_valid': model_valid, 'session': session, 'command_count': len(parsed['reads']),
                  'native_skill_confirmed': report['native_skill_confirmed'],
                  'status': 'completed' if ok and model_valid else 'failed'}
        report['turns'].append(status)
        write_json(turn_dir / 'execution.json', status)
        print(json.dumps({'folder': str(folder), **status}, ensure_ascii=False), flush=True)
        if not ok or not model_valid:
            report['status'] = 'failed'
            break
    else:
        report['status'] = 'completed' if max_turns >= len(case['turns']) else 'partial_probe'
    report['snapshot_unchanged'] = before == hash_files(snapshot)
    if plugin:
        report['snapshot_unchanged'] &= before == hash_files(material)
    report['vocab_unchanged'] = vocab_before == hash_files(SOURCE.parent / 'vocab')
    if not report['snapshot_unchanged'] or not report['vocab_unchanged']:
        report['status'] = 'invalid_material_drift'
    write_json(folder / 'completion.json', report)
    print(json.dumps({'folder': str(folder), 'status': report['status']}, ensure_ascii=False), flush=True)
    return report['status'] in {'completed', 'partial_probe'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', choices=MODELS, required=True)
    parser.add_argument('--version', choices=['baseline', 'candidate', 'both'], required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--max-turns', type=int, default=100)
    parser.add_argument('--direct-current-claude', action='store_true')
    parser.add_argument('--native-skill', action='store_true')
    args = parser.parse_args()
    if args.direct_current_claude and args.host != 'claude':
        parser.error('--direct-current-claude requires --host claude')
    if args.native_skill and args.host != 'claude':
        parser.error('--native-skill requires --host claude')
    cases = json.loads(CASE_FILE.read_text(encoding='utf-8'))['evals']
    selected = cases if args.case == 'all' else [next(case for case in cases if case['id'] == args.case)]
    versions = ['baseline', 'candidate'] if args.version == 'both' else [args.version]
    for case in selected:
        for version in versions:
            if not run(args.host, version, case, args.timeout, args.max_turns, args.direct_current_claude, args.native_skill):
                raise SystemExit(1)


if __name__ == '__main__':
    main()
