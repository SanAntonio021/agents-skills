"""Pinned upstream/local comparison, reusing the existing CLI replay engine."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
import uuid

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent
PREVIOUS = ROOT.parent / 'paragraph-quality-20260907'
spec = importlib.util.spec_from_file_location('contrast_replay', PREVIOUS / 'run_evaluation.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
SKILLS = ['writing-router', 'technical-writing', 'project-writing', 'research-report',
          'meeting-notes', 'ieee-manuscript-edit', 'style-vocab']
ENTRIES = {'local-before': 'writing-router', 'local-after': 'writing-router',
           'local-refined': 'writing-router',
           'humanizer-original': 'humanizer-zh', 'waza-original': 'write'}
CASES = ['empty-common-sense-report', 'necessary-negation-paper', 'natural-prose-general']
UPSTREAM = {
    'humanizer-original': ('op7418-Humanizer-zh', '91f3d394db8419c20d67ebe22a96cf8fee0a404b', ''),
    'waza-original': ('tw93-Waza', '9c97ccb6d96e776bf814e27498d0afc0ed3d1e94', 'skills/write/'),
}


def file_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()
            and not p.name.endswith('.baiduyun.uploading.cfg') and '__pycache__' not in p.parts}


def expected_files(version):
    if version in UPSTREAM:
        return json.loads((ROOT / 'upstream-manifest.json').read_text(encoding='utf-8'))[version]['files']
    return json.loads((ROOT / f'{version}-manifest.json').read_text(encoding='utf-8'))


def material_state(version):
    expected = expected_files(version)
    snapshot = file_hashes(ROOT / version)
    plugin = file_hashes(ROOT / 'plugins' / version / 'skills')
    return {'snapshot': snapshot, 'plugin': plugin,
            'valid': expected == snapshot == plugin}


def make_plugin(version):
    folder = ROOT / 'plugins' / version
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / version, folder / 'skills')
    (folder / '.claude-plugin').mkdir()
    replay.write_json(folder / '.claude-plugin/plugin.json', {'name': 'writing-eval', 'version': '0.0.0'})


def freeze_local(version):
    destination = ROOT / version
    destination.mkdir(exist_ok=False)
    for skill in SKILLS:
        shutil.copytree(SOURCE / skill, destination / skill,
                        ignore=shutil.ignore_patterns('*.baiduyun.uploading.cfg', '__pycache__', '.pytest_cache'))
    make_plugin(version)
    replay.write_json(ROOT / f'{version}-manifest.json', file_hashes(destination))


def prepare():
    source_cases = json.loads((SOURCE / 'writing-router/evals/paragraph-quality.json').read_text(encoding='utf-8'))
    selected = [copy.deepcopy(case) for case in source_cases['evals'] if case['id'] in CASES]
    report = next(case for case in selected if case['id'] == CASES[0])
    report['turns'][1]['prompt'] = '把三种型号的价格和交期改成三条列表，判断句放在列表前。展示这一部分的完整修改稿。'
    report['turns'][2]['expectations'] = [
        '只概括现有报价中的交期结论，保留5天到货要求，不扩成采购建议或综合最优。',
        '摘要不要求复述核对过程或与交期判断无直接关系的验收状态；可保留必要限制，但不得机械收尾。',
        '正文中的未验收事实不能改成已验收、计划或执行条件；若结论扩大为可采购，仍判失败。',
    ]
    report['turns'][2]['protected_facts'] = [fact for fact in report['turns'][2]['protected_facts']
                                               if fact['kind'] != 'status']
    replay.write_json(ROOT / 'cases.json', {'fixture_policy': 'synthetic-only', 'evals': selected})
    freeze_local('local-before')
    provenance = {}
    for version, (repository, commit, prefix) in UPSTREAM.items():
        mirror = SOURCE.parent / 'upstream' / repository
        archive = ROOT / f'{version}.zip'
        argv = ['git', '-C', str(mirror), 'archive', '--format=zip', '-o', str(archive), commit]
        if prefix:
            argv.append(prefix.rstrip('/'))
        subprocess.run(argv, check=True, capture_output=True)
        target = ROOT / version / ENTRIES[version]
        target.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                if info.is_dir() or (prefix and not info.filename.startswith(prefix)):
                    continue
                relative = info.filename[len(prefix):]
                path = (target / relative).resolve()
                if not path.is_relative_to(target.resolve()):
                    raise ValueError('Archive entry escapes snapshot')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bundle.read(info))
        if prefix:
            license_bytes = subprocess.run(['git', '-C', str(mirror), 'show', f'{commit}:LICENSE'],
                                           capture_output=True, check=True).stdout
            (target / 'UPSTREAM-LICENSE').write_bytes(license_bytes)
        make_plugin(version)
        provenance[version] = {'mirror': str(mirror), 'commit': commit, 'path': prefix or '.',
                               'files': file_hashes(ROOT / version)}
    replay.write_json(ROOT / 'upstream-manifest.json', provenance)


def prompt(snapshot, entry, user_prompt, native=False):
    return ('只在对话中交付，不创建或修改文件。'
            f'本次技能入口为 {(snapshot / entry / "SKILL.md").as_posix()}。'
            + (f'请通过 Skill 工具调用 writing-eval:{entry}。' if native else '')
            + f'技能及其参考文件、脚本只使用 {snapshot.as_posix()} 下的版本。'
            '可只读个人词表 D:/BaiduSyncdisk/.agents/vocab；个人样稿不可用。'
            '不读取其他版本、已安装业务技能、历史对话、记忆、评测材料或私有样稿；'
            '不调用子智能体、业务系统或网络检索。技能自带检查脚本可通过bash使用标准输入运行，结果留在对话中。'
            '\n\n' + user_prompt)


original_command = replay.command


def command(host, cwd, session, direct=False, plugin=None):
    argv = original_command(host, cwd, session, direct, plugin)
    if host == 'claude':
        for flag in ['--tools', '--allowedTools']:
            argv[argv.index(flag) + 1] = 'Read,Glob,Grep,Skill,Bash'
    return argv


def run(args):
    replay.ROOT = ROOT
    replay.initial_prompt = prompt
    replay.command = command
    os.environ['CLAUDE_CODE_GIT_BASH_PATH'] = r'C:\Program Files\Git\bin\bash.exe'
    os.environ['PATH'] = str(ROOT / 'tool-bin') + os.pathsep + r'C:\Program Files\Git\bin' + os.pathsep + os.environ['PATH']
    cases = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['evals']
    failures = []
    receipt = ROOT / 'batches' / f'{args.host}-{args.version}-{uuid.uuid4()}.json'
    receipt.parent.mkdir(exist_ok=True)
    before = material_state(args.version)
    batch = {'host': args.host, 'version': args.version, 'case': args.case,
             'before': before, 'status': 'running'}
    replay.write_json(receipt, batch)
    if not before['valid']:
        batch['status'] = 'invalid_material_before'
        replay.write_json(receipt, batch)
        raise RuntimeError('Snapshot or plugin differs from frozen manifest')
    for case in cases:
        if args.case != 'all' and case['id'] != args.case:
            continue
        case['entry_skill'] = ENTRIES[args.version]
        if not replay.run(args.host, args.version, case, args.timeout, 3,
                          direct=args.host == 'claude', native=args.host == 'claude'):
            failures.append(case['id'])
    after = material_state(args.version)
    batch.update(after=after, failures=failures,
                 status='completed' if before == after and after['valid'] and not failures else 'failed')
    replay.write_json(receipt, batch)
    if before != after or not after['valid']:
        raise RuntimeError('Snapshot changed during comparison')
    if failures:
        raise SystemExit('Incomplete cases: ' + ', '.join(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'freeze-after', 'run'])
    parser.add_argument('--host', choices=['claude', 'codex'])
    parser.add_argument('--version', choices=ENTRIES)
    parser.add_argument('--case', choices=['all', *CASES], default='all')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'freeze-after':
        freeze_local(args.version or 'local-after')
    elif not args.host or not args.version:
        parser.error('run needs --host and --version')
    else:
        run(args)
