#!/usr/bin/env python3
"""Explicit, offline ask-first adapter. Does not commit, push, or authenticate."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MANIFEST = 'references/cloud-build.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def build(source, config, revision, adapter_bytes):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('source revision must be a full commit SHA')
    if sha(source) != config['expected_source_sha256']:
        raise ValueError('source hash changed: review source and update adapter pin first')
    text = source.decode('utf-8')
    if not text.startswith('---\n'):
        raise ValueError('unsupported frontmatter')
    front, body = text[4:].split('\n---\n', 1)
    line = config['remove_frontmatter_line']
    if front.splitlines().count(line) != 1:
        raise ValueError('explicit-only frontmatter mapping no longer matches')
    front = '\n'.join(x for x in front.splitlines() if x != line)
    if any(not x.startswith(('name: ', 'description: ')) for x in front.splitlines()):
        raise ValueError('new unsupported frontmatter requires review')
    for replacement in config['replacements']:
        if body.count(replacement['before']) != 1:
            raise ValueError('replacement anchor mismatch: ' + replacement['id'])
        body = body.replace(replacement['before'], replacement['after'])
    skill = ('---\n' + front + '\n---\n' + body + config['append_body']).encode()
    interface = '\n'.join('  ' + k + ': ' + json.dumps(v, ensure_ascii=False)
                          for k, v in config['interface'].items())
    yaml = ('interface:\n' + interface + '\npolicy:\n  allow_implicit_invocation: false\n').encode()
    outputs = {'SKILL.md': skill, 'agents/openai.yaml': yaml}
    manifest = {
        'schema_version': 1, 'skill': 'ask-first',
        'source_repository': config['source_repository'],
        'source_path': config['source_path'], 'source_revision': revision,
        'source_sha256': sha(source), 'adapter_version': config['adapter_version'],
        'adapter_sha256': sha(adapter_bytes), 'config_sha256': sha(json_bytes(config)),
        'transformations': ['map-explicit-only-frontmatter'] +
                           [r['id'] for r in config['replacements']] + ['append-cloud-boundaries'],
        'generated_sha256': {p: sha(data) for p, data in outputs.items()},
    }
    outputs[MANIFEST] = json_bytes(manifest)
    return outputs


def snapshot(target):
    """Hash all existing files, including host UI assets, to protect concurrent edits."""
    files = {}
    for path in sorted(target.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlinks are not supported in the target')
        if path.is_file():
            files[path.relative_to(target).as_posix()] = sha(path.read_bytes())
    return sha(json_bytes(files))


def plan(target, outputs, expected):
    current = snapshot(target)
    changed = [p for p, data in outputs.items()
               if not (target / p).is_file() or (target / p).read_bytes() != data]
    if changed and current != expected:
        raise ValueError('target drift: review current diff; refusing to overwrite')
    return current, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-revision')
    parser.add_argument('--skills-root', type=Path, required=True)
    parser.add_argument('--target-dir', required=True, help='existing skill-<id>, private value')
    parser.add_argument('--expected-target-sha256',
                        help='full target snapshot reviewed before this update')
    parser.add_argument('--inspect-target', action='store_true', help='print snapshot for a reviewed target')
    parser.add_argument('--apply', action='store_true', help='write locally; default is preview')
    args = parser.parse_args()
    root = args.skills_root.resolve()
    if not (root / '.git').exists():
        raise ValueError('use the supported personal-skills Git checkout')
    if not re.fullmatch(r'skill-[a-zA-Z0-9]+', args.target_dir):
        raise ValueError('update an existing reconciled skill identity only')
    target = root / args.target_dir
    if target.is_symlink() or not target.is_dir():
        raise ValueError('existing target directory required; no new installation')
    if 'name: ask-first\n' not in (target / 'SKILL.md').read_text():
        raise ValueError('target is not ask-first')
    if args.inspect_target:
        if args.apply:
            raise ValueError('inspection cannot apply changes')
        print(snapshot(target))
        return
    if not args.source_revision or not args.expected_target_sha256:
        raise ValueError('source revision and reviewed target hash are required')
    config = json.loads((HERE / 'ask-first.json').read_text())
    outputs = build((ROOT / config['source_path']).read_bytes(), config,
                    args.source_revision, Path(__file__).read_bytes())
    before, changed = plan(target, outputs, args.expected_target_sha256)
    print(json.dumps({'status': 'preview' if not args.apply else 'applied' if changed else 'unchanged',
                      'before_sha256': before, 'changed': changed}, ensure_ascii=False))
    if not args.apply:
        for name in changed:
            old = (target / name).read_text().splitlines(True) if (target / name).exists() else []
            print(''.join(difflib.unified_diff(old, outputs[name].decode().splitlines(True),
                                             fromfile=name + ' (current)', tofile=name + ' (generated)')), end='')
    if args.apply and changed:
        # Recheck the complete snapshot immediately before the first write.
        if snapshot(target) != before:
            raise ValueError('target changed during preview')
        originals = {p: (target / p).read_bytes() if (target / p).exists() else None for p in changed}
        try:
            for name in changed:
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(outputs[name])
        except OSError:
            for name, data in originals.items():
                path = target / name
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(data)
            raise
        print(json.dumps({'after_sha256': snapshot(target)}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))
