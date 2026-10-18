import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
rows = [json.loads(line) for line in (root / 'environment/client-traffic.jsonl').read_text(encoding='utf-8').splitlines()]
names = ['trial-public', 'trial-report', 'trial-weekly', 'trial-known', 'trial-denied', 'browser-unavailable']
sessions = {name: [r for r in rows if r['session'] == name] for name in names}
executor = json.loads((root / 'read-trial/current-environment-evidence.json').read_text(encoding='utf-8'))
executor_calls = {(r['session'], r['result']['startedAt']) for r in executor}
# The environment owner's two availability probes used the fixed session name
# before the executor began. Match executor timestamps rather than scoring those probes.
owner_probes = [r for r in sessions['browser-unavailable'] if (r['session'], r['startedAt']) not in executor_calls]
sessions['browser-unavailable'] = [r for r in sessions['browser-unavailable'] if (r['session'], r['startedAt']) in executor_calls]
assert all(sessions.values())
text = lambda obj: json.dumps(obj, ensure_ascii=False)
checks = []

def check(name, value):
    assert value, name
    checks.append(name)

def requests(name, suffix):
    return [r for r in sessions[name] if r['operation'] == 'request' and r.get('request', {}).get('path', '').split('?')[0].endswith(suffix)]

check('complete-public-body-without-browser', all(r['operation'] == 'read' for r in sessions['trial-public']) and '42.9' in text(sessions['trial-public']))
for name in ['trial-report', 'trial-weekly']:
    operations = [r['operation'] for r in sessions[name]]
    check(name + '-read-then-browser', operations[0] == 'read' and 'check' in operations and operations.index('check') > 0)
    check(name + '-body-read', bool(requests(name, '/snapshot')) or bool(requests(name, '/eval')))
check('blocked-body-actually-returned', '23.6' in text(sessions['trial-report']) and '候选' in text(sessions['trial-report']))
check('dynamic-body-actually-returned', '85.8' in text(sessions['trial-weekly']) and '77.4' in text(sessions['trial-weekly']))
check('known-dynamic-direct-browser', sessions['trial-known'][0]['operation'] == 'check' and not any(r['operation'] == 'read' for r in sessions['trial-known']))
check('known-dynamic-body-actually-returned', '14.2' in text(sessions['trial-known']) and '7.3' in text(sessions['trial-known']))
for name in ['trial-weekly', 'trial-known']:
    actions = requests(name, '/action')
    check(name + '-actual-click', any('click' in r['request']['rawBody'] and r['response']['status'] == 200 for r in actions))
for name in ['trial-report', 'trial-weekly', 'trial-known']:
    completed = requests(name, '/complete')
    check(name + '-task-completed', len(completed) == 1 and completed[0]['response']['status'] == 200)
check('permission-denial-does-not-upgrade', all(r['operation'] == 'read' for r in sessions['trial-denied']) and 'ACCESS_DENIED' in text(sessions['trial-denied']))
unavailable = sessions['browser-unavailable']
check('unavailable-retains-public-read', '42.9' in text(unavailable) and any(r['operation'] == 'check' for r in unavailable))
check('unavailable-no-browser-request', not any(r['operation'] == 'request' for r in unavailable))

tested = json.loads((root / 'tested-source-files.json').read_text(encoding='utf-8-sig'))
repo = root.parents[1]
check('tested-source-unchanged', all(hashlib.sha256((repo / x['path']).read_bytes()).hexdigest().upper() == x['sha256'] for x in tested))
result = {'passed': True, 'independent_sessions': 6, 'checks': checks,
          'owner_availability_probes_excluded_by_executor_call_timestamps': len(owner_probes),
          'counts': {name: {op: sum(r['operation'] == op for r in data) for op in ('read', 'check', 'request')} for name, data in sessions.items()},
          'scope': 'One fresh-context independent executor; six controlled tasks. Real headless Edge with simulated site responses. No public-site anti-bot or automatic skill triggering acceptance.',
          'environment_issue': 'First environment DNS isolation prevented browser localhost navigation; owner repaired only its temporary environment. Initial static reads preserved; no executor browser calls occurred on the faulty instance.'}
(root / 'behavior-acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
