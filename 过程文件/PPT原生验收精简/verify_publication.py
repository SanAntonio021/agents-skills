import subprocess
import shutil
import json
from pathlib import Path

root = Path(__file__).resolve().parent
shell = shutil.which('pwsh') or shutil.which('powershell')
if not shell:
    raise RuntimeError('PowerShell unavailable')
args = [shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
        r'D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1',
        '-Skills', 'pptx', '-ExpectedRemoteCommit', '0ed35a57c9294756bdcee7b400fea97da1895481',
        '-AllowHistoricalCommit', '-UpdateTimeoutSeconds', '180', '-VerifyOnly']
result = subprocess.run(args, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
(root / 'verify.json').write_bytes(result.stdout)
(root / 'verify.stderr.txt').write_bytes(result.stderr)
receipt = json.loads(result.stdout.decode('utf-8-sig'))
print(json.dumps({'process_exit': result.returncode, 'status': receipt.get('status'),
                  'ok': receipt.get('ok'), 'exit_code': receipt.get('exit_code'),
                  'errors': receipt.get('errors'), 'warnings': receipt.get('warnings')}, ensure_ascii=False))
raise SystemExit(result.returncode)
