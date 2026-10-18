from pathlib import Path
import os
import subprocess
import sys

task = Path(__file__).resolve().parent
source = task.parents[1] / 'git-branch-consolidation'
test_root = Path(r'D:\AgentSkillTests\git-branch-consolidation-20261014\final')
test_root.mkdir(parents=True, exist_ok=True)
environment = dict(os.environ, GBC_TEST_ROOT=str(test_root))
log = task / 'final-tests.log'
with log.open('wb') as handle:
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(source / 'tests'),
                             '-p', 'test_*.py', '-v'], env=environment, stdout=handle, stderr=subprocess.STDOUT)
print(log.read_text(encoding='utf-8', errors='replace'))
sys.exit(result.returncode)
