"""Stage only the approved candidate and preserve experimental files by hash."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
BASE = 'e13eb80bc7fd2e48ad1558b12f9b5f165c224eb1'
FILES = ['writing-router/SKILL.md', 'writing-router/references/common-quality.md',
         'writing-router/references/exact-edit.md', 'writing-router/scripts/exact_edit.py',
         'writing-router/tests/test_exact_edit.py']
PARK = ['writing-router/evals/paragraph-quality.json',
        'writing-router/tests/test_paragraph_quality.py']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO).decode('utf-8').strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def stage():
    assert git('rev-parse', 'HEAD') == BASE, 'Base changed; recheck before staging'
    assert not git('diff', '--cached', '--name-only'), 'Existing staging must be preserved'
    for relative in FILES:
        path = ROOT / 'candidate' / relative
        assert path.is_file()
        oid = git('hash-object', '-w', '--path=' + relative, str(path))
        git('update-index', '--add', '--cacheinfo', '100644', oid, relative)
    assert set(git('diff', '--cached', '--name-only').splitlines()) == set(FILES)
    write('staged-manifest.json', {name: digest(ROOT / 'candidate' / name) for name in FILES})
    print(git('diff', '--cached', '--stat'))


def park():
    journal = ROOT / 'parked.json'
    assert not journal.exists(), 'Existing preservation journal requires inspection'
    rows = []
    for relative in PARK:
        source, target = REPO / relative, ROOT / 'parked' / relative
        assert source.resolve().is_relative_to(REPO.resolve())
        assert target.resolve().is_relative_to(ROOT.resolve())
        assert source.is_file() and not source.is_symlink() and not target.exists()
        assert not git('ls-files', '--', relative), 'Only known untracked experimental files may be parked'
        rows.append({'relative': relative, 'sha256': digest(source), 'moved': False})
    write('parked.json', rows)
    for row in rows:
        source, target = REPO / row['relative'], ROOT / 'parked' / row['relative']
        assert digest(source) == row['sha256']
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        assert digest(target) == row['sha256']
        row['moved'] = True
        write('parked.json', rows)
    print('Two experimental files preserved outside the release skill.')


def restore():
    rows = json.loads((ROOT / 'parked.json').read_text(encoding='utf-8'))
    for row in rows:
        source, target = ROOT / 'parked' / row['relative'], REPO / row['relative']
        assert source.resolve().is_relative_to(ROOT.resolve())
        assert target.resolve().is_relative_to(REPO.resolve())
        assert source.is_file() and digest(source) == row['sha256'] and not target.exists()
        source.rename(target)
        assert digest(target) == row['sha256']
        row['restored'] = True
        write('parked.json', rows)
    print('Both experimental files restored, hashes unchanged.')


def exceptions():
    changed = git('diff', 'HEAD', '--name-only', '--', 'writing-router').splitlines()
    untracked = git('ls-files', '--others', '--exclude-standard', '--', 'writing-router').splitlines()
    assert not untracked, 'Untracked target content requires preservation: ' + str(untracked)
    values = []
    for name in changed:
        assert git('cat-file', '-t', 'HEAD:' + name) == 'blob'
        values.append(name + '=' + digest(REPO / name))
    write('worktree-exceptions.json', values)
    print(json.dumps(values))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stage', 'park', 'restore', 'exceptions'])
    globals()[parser.parse_args().action]()
