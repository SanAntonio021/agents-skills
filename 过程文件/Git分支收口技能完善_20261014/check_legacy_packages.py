from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(r'D:\AgentSkillTests\git-branch-consolidation-20261014\legacy-compatibility')
SOURCE = Path(__file__).resolve().parent / 'source-before/scripts'
NEW = Path(__file__).resolve().parents[2] / 'git-branch-consolidation/scripts'
ROOT.mkdir(parents=True, exist_ok=False)

def run(*args):
    result = subprocess.run([str(arg) for arg in args], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout.decode('utf-8', 'replace') + result.stderr.decode('utf-8', 'replace'))
    return result.stdout

remote, repo = ROOT / 'remote.git', ROOT / 'repo'
run('git', 'init', '--bare', '--initial-branch=main', remote)
run('git', 'init', '--initial-branch=main', repo)
run('git', '-C', repo, 'config', 'user.name', 'Legacy Test')
run('git', '-C', repo, 'config', 'user.email', 'legacy@example.invalid')
(repo / 'source.txt').write_text('base\n', encoding='utf-8')
(repo / '.gitignore').write_text('cache/\nresults/\n', encoding='utf-8')
run('git', '-C', repo, 'add', 'source.txt', '.gitignore')
run('git', '-C', repo, 'commit', '-m', 'initial')
run('git', '-C', repo, 'remote', 'add', 'origin', remote)
run('git', '-C', repo, 'push', '-u', 'origin', 'main')
(repo / 'source.txt').write_text('staged\n', encoding='utf-8')
run('git', '-C', repo, 'add', 'source.txt')
(repo / 'source.txt').write_text('current\n', encoding='utf-8')
(repo / 'untracked.txt').write_text('kept\n', encoding='utf-8')
(repo / 'results').mkdir()
(repo / 'results/measurement.csv').write_text('1,3.141592653589793\n', encoding='utf-8')
(repo / 'cache').mkdir()
(repo / 'cache/generated').write_text('rebuildable\n', encoding='utf-8')
packages = []
for disposition_version in (1, 2):
    version_root = ROOT / f'v{disposition_version}'
    version_root.mkdir()
    entry = dict(preserve=['results'], reproducible=['cache'])
    if disposition_version == 2:
        entry['rebuild'] = {'cache': 'Regenerate from the frozen source fixture'}
    disposition = dict(schemaVersion=disposition_version, worktrees={str(repo): entry})
    path = version_root / 'ignored.json'
    path.write_text(json.dumps(disposition), encoding='utf-8')
    primary, mirror = version_root / 'primary', version_root / 'mirror'
    output = run(sys.executable, SOURCE / 'capture_recovery.py', '--repo', repo, '--remote', 'origin',
                 '--primary', primary, '--mirror', mirror, '--stamp', f'legacy-{disposition_version}',
                 '--ignored-disposition', path)
    (version_root / 'capture.log').write_bytes(output)
    # v1 disposition is compatible with schema 2's original protection semantics.
    if disposition_version == 1:
        sys.path.insert(0, str(SOURCE))
        from capture_recovery import package_manifest
        for package in (primary, mirror):
            summary_path = package / 'snapshot-summary.json'
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            summary['schemaVersion'] = 2
            summary_path.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
            package_manifest(package)
    packages.append((version_root, primary, mirror))
repo.rename(ROOT / 'retired-original')
results = []
for version_root, primary, mirror in packages:
    restore = version_root / 'restore'
    output = run(sys.executable, NEW / 'verify_recovery.py', '--source', primary, '--mirror', mirror, '--restore', restore)
    (version_root / 'verify.log').write_bytes(output)
    receipt = json.loads((restore / 'restore-verification.json').read_text(encoding='utf-8'))
    assert (restore / 'states/000/source.txt').read_text() == 'current\n'
    assert (restore / 'states/000/results/measurement.csv').is_file()
    assert not (restore / 'states/000/cache').exists()
    results.append(dict(snapshot=receipt['snapshotSchemaVersion'], status=True))
print(json.dumps(results))
