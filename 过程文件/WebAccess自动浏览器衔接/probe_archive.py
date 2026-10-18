import hashlib
import json
import subprocess
import urllib.request
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
repo = root.parents[1]
url = 'https://github.com/SanAntonio021/agents-skills/archive/refs/heads/main.zip'
request = urllib.request.Request(url, headers={'User-Agent': 'cc-switch'})
output = root / 'archive-main-probe.zip'
assert not output.exists()
with urllib.request.urlopen(request, timeout=45) as response:
    info = {'url': url, 'final_url': response.url, 'http_status': response.status,
            'headers': {k: v for k, v in response.headers.items() if k.lower() in
                        {'etag', 'cache-control', 'age', 'date', 'x-cache', 'last-modified', 'x-github-request-id'}}}
    payload = response.read(64 * 1024 * 1024 + 1)
    assert len(payload) <= 64 * 1024 * 1024
output.write_bytes(payload)
info['bytes'] = len(payload)
info['sha256'] = hashlib.sha256(payload).hexdigest()
with zipfile.ZipFile(output) as z:
    info['zip_comment'] = z.comment.decode('utf-8', errors='replace')
    name = next(n for n in z.namelist() if n.endswith('/web-access/SKILL.md') and n.count('/') == 2)
    data = z.read(name)
    expected = subprocess.check_output(['git', '-C', str(repo), 'show',
                                       '9bab170c5792418feb52dda799dbd5a8ac3629ae:web-access/SKILL.md'])
    info['entry'] = name
    info['entry_matches_release'] = data == expected
    info['entry_sha256'] = hashlib.sha256(data).hexdigest()
    info['release_entry_sha256'] = hashlib.sha256(expected).hexdigest()
(root / 'archive-probe.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(info, ensure_ascii=False))
