"""Fresh installed-skill invocations on synthetic files; never changes runtime config."""
import argparse
import codecs
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('replay', ROOT.parent / 'paragraph-quality-20260907/run_evaluation.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(host, scratch):
    if host == 'claude':
        return [replay.CLAUDE, '--print', '--verbose', '--output-format', 'stream-json',
                '--model', replay.MODELS[host], '--effort', 'max', '--setting-sources', 'user',
                '--settings', '{"disableAllHooks":true,"autoMemoryEnabled":false}',
                '--tools', 'Read,Glob,Grep,Bash,Skill', '--allowedTools', 'Read,Glob,Grep,Bash,Skill',
                '--permission-mode', 'dontAsk', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
    args = [replay.NODE, replay.CODEX, 'exec', '--model', replay.MODELS[host],
            '--sandbox', 'workspace-write', '--skip-git-repo-check', '--json', '-C', str(scratch),
            '-c', 'approval_policy="never"', '-c', 'model_reasoning_effort="max"',
            '-c', 'web_search="disabled"']
    for feature in ['plugins', 'memories', 'hooks', 'apps', 'browser_use', 'browser_use_external',
                    'computer_use', 'multi_agent', 'remote_plugin']:
        args += ['-c', f'features.{feature}=false']
    config = tomllib.loads((Path.home() / '.codex/config.toml').read_text(encoding='utf-8'))
    for name in config.get('mcp_servers', {}):
        assert all(c.isalnum() or c in '_-' for c in name)
        args += ['-c', f'mcp_servers.{name}.enabled=false']
    return args


def run(host, case, batch, direct_skill=False):
    folder = ROOT / batch / host / case
    folder.mkdir(parents=True, exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix='exact-edit-live-'))
    original = ('本次记录共24000帧，其中错误帧为12帧。\r\n'
                '帧差错率为q = 12 / 24000 = 0.0005，双通道测试尚未开展。')
    source = codecs.BOM_UTF8 + original.encode('utf-8')
    title = '## 单通道测试记录'
    suffix = '周五09:40送到的测试件先放西侧库房，下周一再清点。'
    src, output = scratch / 'original.md', scratch / 'result.md'
    src.write_bytes(source)
    request = (f'只在原文开头加标题“{title}”' if case == 'title' else f'只在原文末尾追加这句原话：“{suffix}”')
    prompt = (f'请使用本机已安装的 writing-router 技能完成这个合成文稿任务。原文文件为 {src.as_posix()}，'
              f'{request}。原有正文逐字不动，包括标点、数字、公式、空格和行序。'
              f'已授权直接生成新文件 {output.as_posix()}，不要覆盖原文，不要额外解释或润色。'
              '写入范围仅限这两个文件所在的测试目录。不要读取历史会话、记忆、私人样稿、源码或其他测试目录，'
              '不要使用网络、业务系统或子智能体，不要改变配置；可读取本机规则和实际安装技能所需的参考文件。'
              '最终只给新文件路径。')
    if direct_skill:
        assert host == 'claude'
        prompt = '/writing-router ' + prompt
    expected = (codecs.BOM_UTF8 + title.encode() + b'\r\n' + source[len(codecs.BOM_UTF8):]
                if case == 'title' else source + b'\r\n' + suffix.encode())
    args = command(host, scratch)
    env, route = replay.selected_claude_environment() if host == 'claude' else (os.environ.copy(), {'route': 'existing_cli'})
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    (folder / 'prompt.txt').write_text(prompt, encoding='utf-8')
    replay.write_json(folder / 'command.json', args)
    before = {name: sha((Path.home() / f'.{host}' / 'skills/writing-router' / name).read_bytes())
              for name in ['SKILL.md', 'references/exact-edit.md', 'scripts/exact_edit.py']}
    started = time.monotonic()
    proc = subprocess.Popen(args, cwd=scratch, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(prompt, timeout=300)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        stdout, stderr = proc.communicate(timeout=20)
    parsed = replay.parse_result(host, replay.events_from(stdout))
    init_skills = [name for event in replay.events_from(stdout)
                   if event.get('type') == 'system' and event.get('subtype') == 'init'
                   for name in event.get('skills', [])]
    (folder / 'events.jsonl').write_text(replay.redact(stdout), encoding='utf-8')
    (folder / 'stderr.txt').write_text(replay.redact(stderr), encoding='utf-8')
    (folder / 'final.md').write_text(replay.redact(parsed['final']), encoding='utf-8')
    replay.write_json(folder / 'read-evidence.json', parsed['reads'])
    output_read_error = None
    try:
        body_ok = output.is_file() and output.read_bytes() == expected
    except OSError as exc:
        body_ok = None
        output_read_error = str(exc)
    unchanged = src.read_bytes() == source
    helper_seen = any('exact_edit.py' in json.dumps(r) and 'apply' in json.dumps(r) for r in parsed['reads'])
    after = {name: sha((Path.home() / f'.{host}' / 'skills/writing-router' / name).read_bytes()) for name in before}
    receipt = {'host': host, 'case': case, 'requested_model': replay.MODELS[host],
               'reported_models': parsed['models'], 'session': parsed['session'], 'route': route,
               'exit_code': proc.returncode, 'timed_out': timed_out, 'duration_seconds': round(time.monotonic()-started, 1),
               'source_unchanged': unchanged, 'output_byte_exact': body_ok, 'helper_command_observed': helper_seen,
               'parent_output_read_error': output_read_error,
               'native_skills': parsed['native_skills'], 'runtime_files_unchanged': before == after,
               'startup_skills': init_skills,
               'startup_writing_router_available': 'writing-router' in init_skills if host == 'claude' else None,
               'runtime_hashes': before, 'scratch': str(scratch), 'source_sha256': sha(source),
               'expected_sha256': sha(expected), 'review_status': 'pending_tool_result_inspection',
               'scope': 'Explicitly requested installed skill; not spontaneous-trigger reliability or style acceptance'}
    receipt['direct_slash_invocation'] = direct_skill
    replay.write_json(folder / 'receipt.json', receipt)
    print(json.dumps({k: receipt[k] for k in ['host','case','exit_code','timed_out','output_byte_exact',
                                             'source_unchanged','helper_command_observed','native_skills']}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--host', choices=['codex', 'claude'], required=True)
    p.add_argument('--batch', default='native-runs')
    p.add_argument('--case', choices=['title', 'append'])
    p.add_argument('--direct-skill', action='store_true')
    args = p.parse_args()
    assert args.batch and all(c.isalnum() or c in '-_' for c in args.batch)
    for case in ([args.case] if args.case else ['title', 'append']):
        run(args.host, case, args.batch, args.direct_skill)
