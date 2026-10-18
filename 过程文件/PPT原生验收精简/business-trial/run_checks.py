import hashlib, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = Path(r'D:\BaiduSyncdisk\.agents\skills\pptx')
SOURCE = ROOT.parent / 'sample.pptx'
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', TEMP=str(ROOT/'temp'), TMP=str(ROOT/'temp'))

def run(label, args):
    start = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    p = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (ROOT / (label + '.stdout.txt')).write_text(p.stdout, encoding='utf-8')
    (ROOT / (label + '.stderr.txt')).write_text(p.stderr, encoding='utf-8')
    record = dict(label=label, start=start, executable=args[0], argv=args[1:], cwd=str(ROOT), input=str(SOURCE), returncode=p.returncode, stdout=str(ROOT/(label+'.stdout.txt')), stderr=str(ROOT/(label+'.stderr.txt')))
    with (ROOT/'tool-records.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False)+'\n')
    print(label, p.returncode)
    print(p.stdout)
    print(p.stderr)
    return p

if __name__ == '__main__':
    mode=sys.argv[1]
    if mode == 'static':
        initial = dict(source=str(SOURCE), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), skill=str(SKILL/'SKILL.md'), skill_sha256=hashlib.sha256((SKILL/'SKILL.md').read_bytes()).hexdigest())
        (ROOT/'input-hashes.json').write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding='utf-8')
        run('officecli-text', [sys.executable, '-B', str(SKILL/'scripts/officecli_bridge.py'), 'view', str(SOURCE), 'text'])
        run('officecli-validate', [sys.executable, '-B', str(SKILL/'scripts/officecli_bridge.py'), 'validate', str(SOURCE)])
        preflight = run('python-preflight', [sys.executable, '-B', str(SKILL/'scripts/python_runtime_preflight.py'), '--json-out', str(ROOT/'python-runtime-preflight.json')])
        if preflight.returncode == 0:
            python=json.loads((ROOT/'python-runtime-preflight.json').read_text(encoding='utf-8'))['selected_executable']
            run('package-validation', [python, '-B', str(SKILL/'scripts/office/validate.py'), str(SOURCE)])
            run('typography', [python, '-B', str(SKILL/'scripts/typography_audit.py'), str(SOURCE), '--json'])
            run('slide-size', [python, '-B', str(SKILL/'scripts/slide_size_audit.py'), str(SOURCE), '--json'])
    elif mode == 'native':
        args=[sys.executable, '-B', str(SKILL/'scripts/office_native_gate.py'), 'check', str(SOURCE), '--format', 'pptx', '--json', '--allow-office-com', '--require-render', '--render-output-dir', str(ROOT/'native-png')]
        if len(sys.argv)>2:
            args += ['--powerpoint-exe', sys.argv[2]]
        run('native-gate', args)
    elif mode == 'content':
        run('content-extraction', [sys.executable, '-B', str(ROOT/'inspect_content.py')])
