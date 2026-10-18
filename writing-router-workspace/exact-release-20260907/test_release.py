import zipfile
from pathlib import Path

import native_smoke as smoke
import release_tools as release


def test_candidate_contains_only_the_five_approved_changes():
    with zipfile.ZipFile(release.ROOT / 'baseline.zip') as archive:
        baseline = {n: archive.read(n).replace(b'\r\n', b'\n') for n in archive.namelist() if not n.endswith('/')}
    current = {p.relative_to(release.ROOT / 'candidate').as_posix(): p.read_bytes().replace(b'\r\n', b'\n')
               for p in (release.ROOT / 'candidate/writing-router').rglob('*')
               if p.is_file() and '__pycache__' not in p.parts}
    changed = {name for name in set(baseline) | set(current) if baseline.get(name) != current.get(name)}
    assert changed == set(release.FILES)


def test_installed_skills_are_not_disabled_in_smoke_commands():
    for host in ['claude', 'codex']:
        command = smoke.command(host, Path.cwd())
        assert not set(command) & {'--safe-mode', '--disable-slash-commands', '--bare', '--ignore-user-config'}
        assert 'skills.include_instructions=false' not in command
        assert command[command.index('--model') + 1] == smoke.replay.MODELS[host]
        if host == 'claude':
            assert 'Skill' in command[command.index('--tools') + 1].split(',')
            assert 'user' in command[command.index('--setting-sources') + 1].split(',')
        else:
            assert command[command.index('--sandbox') + 1] == 'workspace-write'


def test_candidate_does_not_contain_experimental_display_gate():
    entry = (release.ROOT / 'candidate/writing-router/SKILL.md').read_text(encoding='utf-8')
    common = (release.ROOT / 'candidate/writing-router/references/common-quality.md').read_text(encoding='utf-8')
    assert '(references/exact-edit.md)' in entry
    assert '(exact-edit.md)' in common
    assert '中文正文展示前检查' not in common
    assert '逐批执行共同质量规则' not in entry
