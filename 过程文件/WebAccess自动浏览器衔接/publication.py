import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
commit = sys.argv[1]
assert len(commit) == 40 and all(c in '0123456789abcdef' for c in commit)
mode = 'verify' if '--verify' in sys.argv else 'sync'
suffix = next((x.split('=', 1)[1] for x in sys.argv if x.startswith('--attempt=')), '')
assert not suffix or suffix.isdigit()
receipt_path = root / (mode + (('-' + suffix) if suffix else '') + '.json')
assert not receipt_path.exists(), str(receipt_path)
shell = shutil.which('pwsh') or shutil.which('powershell')
args = [shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
        r'D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1',
        '-Skills', 'web-access', '-ExpectedRemoteCommit', commit, '-AllowHistoricalCommit',
        '-ExpectedRuntimeLocalFiles', 'web-access/config.env', '-UpdateTimeoutSeconds', '180']
if mode == 'verify':
    args.append('-VerifyOnly')
env = os.environ.copy()
env.update(GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='http.sslBackend',
           GIT_CONFIG_VALUE_0='openssl', GIT_CONFIG_KEY_1='http.version', GIT_CONFIG_VALUE_1='HTTP/1.1')
result = subprocess.run(args, env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
receipt_path.write_bytes(result.stdout)
receipt_path.with_suffix('.stderr.txt').write_bytes(result.stderr)
receipt = json.loads(result.stdout.decode('utf-8-sig'))
print(json.dumps({'process_exit': result.returncode, 'status': receipt.get('status'),
                  'errors': receipt.get('errors'), 'warnings': receipt.get('warnings')}, ensure_ascii=False))
raise SystemExit(result.returncode)
