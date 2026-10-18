"""Compare release scope without exposing provider or credential contents."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import sys

task = Path(__file__).resolve().parent
profile = Path(os.environ['USERPROFILE'])
assert profile.is_absolute() and profile.is_dir()


def digest(content):
    return hashlib.sha256(content).hexdigest()


def tree(root):
    result = {}
    if not root.is_dir():
        return result
    for current, directories, files in os.walk(root, followlinks=False):
        current = Path(current)
        for name in list(directories):
            path = current / name
            relative = path.relative_to(root).as_posix()
            if relative == 'git-branch-consolidation' or name == '__pycache__':
                directories.remove(name)
            elif path.is_symlink() or path.is_junction():
                result[relative] = {'kind': 'link', 'target': os.readlink(path)}
                directories.remove(name)
        for name in files:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[relative] = {'kind': 'link', 'target': os.readlink(path)}
            else:
                result[relative] = {'kind': 'file', 'sha256': digest(path.read_bytes())}
    return result


snapshot = {'non_target_runtime': {}, 'configuration_files': {}, 'configuration_tables': {}}
for app in ('.cc-switch', '.codex', '.claude', '.agents'):
    snapshot['non_target_runtime'][app] = tree(profile / app / 'skills')
for name in ('.cc-switch/settings.json', '.codex/config.toml', '.codex/auth.json',
             '.claude/settings.json', '.claude/.credentials.json'):
    path = profile / name
    snapshot['configuration_files'][name] = digest(path.read_bytes()) if path.is_file() else None
database = profile / '.cc-switch/cc-switch.db'
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
    connection.execute('BEGIN')
    for table in ('providers', 'provider_endpoints', 'mcp_servers', 'prompts', 'settings',
                  'skill_repos', 'proxy_config', 'proxy_live_backup', 'proxy_failover_live_snapshots'):
        rows = connection.execute('SELECT * FROM "' + table + '"').fetchall()
        serialized = [json.dumps(row, ensure_ascii=False, separators=(',', ':'),
                                 default=lambda value: {'bytes': value.hex()}) for row in rows]
        snapshot['configuration_tables'][table] = digest('\n'.join(sorted(serialized)).encode('utf-8'))
    connection.rollback()

baseline_path = task / 'release-protection-before.json'
if len(sys.argv) > 1 and sys.argv[1] == 'before':
    assert not baseline_path.exists(), 'Do not overwrite the release protection baseline'
    baseline_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Release protection baseline saved; non-target runtime entries:',
          sum(len(value) for value in snapshot['non_target_runtime'].values()))
else:
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    changes = [category for category in snapshot if snapshot[category] != baseline[category]]
    report = {'ok': not changes, 'changed_categories': changes,
              'non_target_runtime_entries': sum(len(value) for value in snapshot['non_target_runtime'].values())}
    (task / 'release-protection-after.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    sys.exit(bool(changes))
