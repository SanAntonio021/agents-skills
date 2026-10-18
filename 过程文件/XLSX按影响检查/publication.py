import subprocess
import shutil
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
verify = '--verify' in sys.argv
shell = shutil.which('pwsh') or shutil.which('powershell')
if not shell:
    raise RuntimeError('PowerShell unavailable')
args = [shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
        r'D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1',
        '-Skills', 'xlsx', '-ExpectedRemoteCommit', '532c2bd8321b5db692ab3612b83188b5145306a1',
        '-AllowHistoricalCommit', '-UpdateTimeoutSeconds', '180']
if verify:
    args.append('-VerifyOnly')
mode = 'verify' if verify else 'sync'
result = subprocess.run(args, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
(root / f'{mode}.json').write_bytes(result.stdout)
(root / f'{mode}.stderr.txt').write_bytes(result.stderr)
receipt = json.loads(result.stdout.decode('utf-8-sig'))
print(json.dumps({'process_exit': result.returncode, 'status': receipt.get('status'),
    'exit_code': receipt.get('exit_code'), 'errors': receipt.get('errors'),
    'warnings': receipt.get('warnings')}, ensure_ascii=False))
raise SystemExit(result.returncode)
