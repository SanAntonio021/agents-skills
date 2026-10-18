"""Run the supported release helper while preserving unpublished source files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
HELPER = REPO.parent / 'automation/ccswitch-skill-sync/Invoke-CcSwitchSkillSync.ps1'
WORD = 'da0c2758ad7577f76974c6bce58e4aa1f77c2a52'
EXPERIMENTS = ['writing-router/evals/paragraph-quality.json',
               'writing-router/tests/test_paragraph_quality.py']
NEW = ['writing-router/references/exact-edit.md', 'writing-router/scripts/exact_edit.py',
       'writing-router/tests/test_exact_edit.py']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO).decode('utf-8').strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def inventory(skills):
    names = git('ls-files', '--cached', '--others', '--exclude-standard', '--', *skills).splitlines()
    return {name: sha(REPO / name) for name in names}


def run(mode, commit, verify_only=False):
    assert len(commit) == 40 and all(c in '0123456789abcdef' for c in commit)
    assert not git('diff', '--cached', '--name-only'), 'Preserve existing staging'
    skills = ['docx', 'writing-router'] if mode == 'word' else ['writing-router']
    if mode == 'word':
        assert commit == WORD
        assert not git('diff', commit, 'HEAD', '--', *skills), 'Historical release would replace newer work'
    folder = ROOT / ('sync-' + mode + '-' + uuid.uuid4().hex[:8])
    folder.mkdir()
    before = inventory(skills)
    write(folder / 'source-before.json', before)
    parks = EXPERIMENTS + NEW if mode == 'word' else EXPERIMENTS
    actual = git('ls-files', '--others', '--exclude-standard', '--', *skills).splitlines()
    assert set(actual) == set(parks), actual
    rows = []
    for name in parks:
        source, target = REPO / name, folder / 'parked' / name
        assert source.resolve().is_relative_to(REPO.resolve())
        assert target.resolve().is_relative_to(folder.resolve())
        assert source.is_file() and not source.is_symlink() and not source.is_junction()
        assert not target.exists()
        rows.append({'path': name, 'sha256': sha(source), 'moved': False, 'restored': False})
    journal = folder / 'preservation.json'
    write(journal, rows)
    results = []
    try:
        for row in rows:
            source, target = REPO / row['path'], folder / 'parked' / row['path']
            assert sha(source) == row['sha256']
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            row['moved'] = True
            write(journal, rows)
        changed = git('diff', 'HEAD', '--name-only', '--', *skills).splitlines()
        exceptions = []
        for name in changed:
            assert git('cat-file', '-t', commit + ':' + name) == 'blob'
            exceptions.append(name + '=' + sha(REPO / name))
        write(folder / 'exceptions.json', exceptions)
        env = os.environ.copy()
        # Invocation-only Git TLS selection; persistent Git/proxy configuration is unchanged.
        count = int(env.get('GIT_CONFIG_COUNT', '0'))
        env[f'GIT_CONFIG_KEY_{count}'] = 'http.sslBackend'
        env[f'GIT_CONFIG_VALUE_{count}'] = 'openssl'
        env['GIT_CONFIG_COUNT'] = str(count + 1)
        for verify in ((True,) if verify_only else (False, True)):
            stage = 'verify' if verify else 'sync'
            script = ("$ErrorActionPreference='Stop'; "
                      "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
                      "$OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
                      f"[string[]]$e=Get-Content -LiteralPath '{folder / 'exceptions.json'}' -Raw -Encoding UTF8 | ConvertFrom-Json; "
                      f"& '{HELPER}' -Skills '{','.join(skills)}' -ExpectedRemoteCommit '{commit}' "
                      "-ExpectedWorktreeExceptions $e "
                      + ('-AllowHistoricalCommit ' if mode == 'word' else '')
                      + ('-VerifyOnly' if verify else ''))
            proc = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                   '-Command', script], cwd=REPO, env=env, capture_output=True,
                                  text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
            (folder / (stage + '-stdout.txt')).write_text(proc.stdout, encoding='utf-8')
            (folder / (stage + '-stderr.txt')).write_text(proc.stderr, encoding='utf-8')
            result = json.loads(proc.stdout.lstrip('\ufeff'))
            write(folder / (stage + '.json'), result)
            print(json.dumps({'stage': stage, 'exit_code': proc.returncode,
                              'status': result.get('status'), 'message': result.get('message'),
                              'folder': str(folder)}, ensure_ascii=False), flush=True)
            results.append(result)
            if proc.returncode or result.get('status') != 'runtime_active' or not result.get('ok'):
                break
    finally:
        for row in rows:
            source, target = folder / 'parked' / row['path'], REPO / row['path']
            if source.exists():
                assert not target.exists(), 'Concurrent source change; do not overwrite: ' + str(target)
                assert sha(source) == row['sha256']
                source.rename(target)
            assert target.is_file() and sha(target) == row['sha256']
            row['restored'] = True
            write(journal, rows)
        after = inventory(skills)
        write(folder / 'source-after.json', after)
        assert before == after, 'Source changed during release; inspect manifests'
        write(folder / 'restored.json', {'source_identical': True, 'parked_files_restored': len(rows)})
    assert len(results) == (1 if verify_only else 2) and all(
        r.get('ok') and r.get('status') == 'runtime_active' for r in results)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['word', 'exact'])
    p.add_argument('commit')
    p.add_argument('--verify-only', action='store_true')
    a = p.parse_args()
    run(a.mode, a.commit, a.verify_only)
