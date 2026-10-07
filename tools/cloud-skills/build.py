#!/usr/bin/env python3
"""Offline, pinned single-source cloud skill builder. Never authenticates or publishes."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MANIFEST = 'references/cloud-build.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def safe_path(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or str(p) != value:
        raise ValueError('unsafe relative path: ' + value)
    return value


def transform(data, replacements):
    text = data.decode('utf-8')
    for item in replacements:
        if not item['before'] or text.count(item['before']) != item.get('count', 1):
            raise ValueError('replacement anchor mismatch: ' + item['id'])
        text = text.replace(item['before'], item['after'])
    return text.encode()


def skill_name(data):
    text = data.decode('utf-8')
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise ValueError('invalid SKILL frontmatter')
    front = text[4:].split('\n---\n', 1)[0]
    names = re.findall(r"^(?:name|'name'|\"name\")\s*:\s*(.*)$", front, re.M)
    if len(names) != 1 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', names[0]):
        raise ValueError('missing, duplicate, or unsupported frontmatter name')
    return names[0]


def metadata(config):
    interface = '\n'.join('  ' + k + ': ' + json.dumps(v, ensure_ascii=False)
                          for k, v in config['interface'].items())
    implicit = str(config.get('allow_implicit_invocation', False)).lower()
    return ('interface:\n' + interface + '\npolicy:\n  allow_implicit_invocation: ' + implicit + '\n').encode()


def build(source, config, revision, adapter_bytes, source_root=None):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('source revision must be a full commit SHA')
    if sha(source) != config['expected_source_sha256']:
        raise ValueError('source hash changed: review source and update adapter pin first')
    if config['schema_version'] == 1:
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
        body = transform(body.encode(), config['replacements']).decode()
        outputs = {'SKILL.md': ('---\n' + front + '\n---\n' + body + config['append_body']).encode()}
        source_files = {config['source_path']: sha(source)}
        transforms = ['map-explicit-only-frontmatter'] + [x['id'] for x in config['replacements']]
    elif config['schema_version'] == 2:
        source_root = Path(source_root or ROOT).resolve()
        outputs, source_files, transforms = {}, {}, []
        for item in config['files']:
            src, dst = safe_path(item['source']), safe_path(item['target'])
            if dst in outputs or dst in (MANIFEST, 'agents/openai.yaml', 'references/cloud-source/SKILL.md'):
                raise ValueError('duplicate or reserved output: ' + dst)
            path = source_root / src
            if path.is_symlink() or not path.resolve().is_relative_to(source_root):
                raise ValueError('source escapes root')
            data = path.read_bytes()
            if sha(data) != item['sha256']:
                raise ValueError('source hash changed: ' + src)
            source_files[src] = sha(data)
            selected = data
            if item.get('select'):
                text = data.decode('utf-8')
                parts = []
                for section in item['select']:
                    start, end = section['start'], section['end']
                    if text.count(start) != 1 or (end and text.count(end) != 1):
                        raise ValueError('section anchor mismatch: ' + src)
                    a = text.index(start)
                    b = text.index(end, a + len(start)) if end else len(text)
                    parts.append(text[a:b])
                selected = ''.join(parts).encode()
                if sha(selected) != item['selected_sha256']:
                    raise ValueError('selected source hash changed: ' + src)
                transforms.append(dst + ':select-reviewed-source-sections')
            outputs[dst] = transform(selected, item.get('replacements', []))
            transforms += [dst + ':' + x['id'] for x in item.get('replacements', [])]
        if config['source_path'] not in source_files or 'SKILL.md' not in outputs:
            raise ValueError('source SKILL must be explicitly mapped')
        outputs['SKILL.md'] += config.get('append_body', '').encode()
        outputs['references/cloud-source/SKILL.md'] = source
    else:
        raise ValueError('unsupported config schema')
    outputs.setdefault('references/cloud-source/SKILL.md', source)
    outputs['agents/openai.yaml'] = metadata(config)
    name = skill_name(outputs['SKILL.md'])
    if name != config.get('skill', 'ask-first'):
        raise ValueError('unexpected generated skill name')
    manifest = {
        'schema_version': 2, 'skill': name,
        'source_repository': config['source_repository'],
        'source_path': config['source_path'], 'source_revision': revision,
        'source_sha256': sha(source), 'source_files_sha256': source_files,
        'adapter_version': config['adapter_version'], 'adapter_sha256': sha(adapter_bytes),
        'config_sha256': sha(json_bytes(config)),
        'transformations': transforms + ['append-cloud-boundaries'],
        'generated_sha256': {p: sha(data) for p, data in outputs.items()},
        'materialized_sha256': None,
        'materialized_note': 'Null until explicit post-host semantic verification; excludes this manifest to avoid self-hashing.',
    }
    outputs[MANIFEST] = json_bytes(manifest)
    return outputs


def files_snapshot(target, exclude_manifest=False):
    files = {}
    for path in sorted(target.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlinks are not supported in the target')
        if path.is_file():
            name = path.relative_to(target).as_posix()
            if not exclude_manifest or name != MANIFEST:
                files[name] = sha(path.read_bytes())
    return files


def snapshot(target):
    return sha(json_bytes(files_snapshot(target)))


def manifest_core(data):
    value = json.loads(data)
    value['materialized_sha256'] = None
    return value


def materialized_matches(target, outputs):
    path = target / MANIFEST
    if not path.is_file():
        return False
    actual = json.loads(path.read_bytes())
    if manifest_core(path.read_bytes()) != manifest_core(outputs[MANIFEST]):
        return False
    recorded = actual.get('materialized_sha256')
    if recorded is None:
        return False
    if recorded != files_snapshot(target, exclude_manifest=True):
        raise ValueError('materialized target drift: review every changed file')
    verify_materialized(target, outputs, snapshot(target))
    return True


def plan(target, outputs, expected):
    current = snapshot(target)
    if MANIFEST in outputs and materialized_matches(target, outputs):
        if current != expected:
            raise ValueError('target drift: materialized snapshot requires explicit review')
        return current, []
    changed = [p for p, data in outputs.items()
               if not (target / p).is_file() or (target / p).read_bytes() != data]
    if current != expected:
        raise ValueError('target drift: review current diff; refusing to overwrite')
    return current, changed


def verify_materialized(target, outputs, expected):
    """Accept only exact generated files plus a reviewed host YAML normalization."""
    if snapshot(target) != expected:
        raise ValueError('target drift before materialized verification')
    try:
        import yaml
    except ImportError as error:
        raise ValueError('PyYAML is required for explicit semantic verification') from error
    actual_files = files_snapshot(target, exclude_manifest=True)
    expected_names = set(outputs) - {MANIFEST}
    for name in expected_names - {'agents/openai.yaml'}:
        if actual_files.get(name) != sha(outputs[name]):
            raise ValueError('generated bytes differ: ' + name)
    actual_manifest = (target / MANIFEST).read_bytes()
    if manifest_core(actual_manifest) != manifest_core(outputs[MANIFEST]):
        raise ValueError('manifest provenance differs')
    class UniqueLoader(yaml.SafeLoader):
        pass

    def unique_mapping(loader, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ValueError('duplicate host YAML key: ' + str(key))
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
    original = yaml.load(outputs['agents/openai.yaml'], Loader=UniqueLoader)
    host = yaml.load((target / 'agents/openai.yaml').read_bytes(), Loader=UniqueLoader)
    if not isinstance(host, dict) or set(host) != set(original):
        raise ValueError('unexpected host YAML sections')
    icons = set()
    for section in original:
        if not isinstance(host[section], dict):
            raise ValueError('invalid host YAML section')
        for key, value in original[section].items():
            if host[section].get(key) != value or type(host[section].get(key)) != type(value):
                raise ValueError('host YAML changed managed value: ' + section + '.' + key)
        extras = set(host[section]) - set(original[section])
        allowed = {'icon_small', 'icon_large'} if section == 'interface' else {'products'}
        if not extras <= allowed:
            raise ValueError('unexpected host YAML key')
        for key in extras:
            value = host[section][key]
            if key == 'products':
                if not isinstance(value, list) or len(value) != len(set(value)) or not set(value) <= {'chatgpt', 'codex', 'api', 'atlas'}:
                    raise ValueError('unexpected host product value')
            else:
                name = safe_path(value.removeprefix('./'))
                if not name.startswith('assets/') or name not in actual_files:
                    raise ValueError('unverified host icon')
                icons.add(name)
    if set(actual_files) - expected_names - icons:
        raise ValueError('unexpected materialized files: ' + str(sorted(set(actual_files) - expected_names - icons)))
    manifest = json.loads(outputs[MANIFEST])
    manifest['materialized_sha256'] = actual_files
    return json_bytes(manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='ask-first.json')
    parser.add_argument('--source-revision')
    parser.add_argument('--skills-root', type=Path, required=True)
    parser.add_argument('--target-dir', required=True, help='existing identity or host-initialized new skill name')
    parser.add_argument('--expected-target-sha256')
    parser.add_argument('--inspect-target', action='store_true')
    parser.add_argument('--record-materialized', action='store_true')
    parser.add_argument('--apply', action='store_true', help='write locally; default is preview')
    args = parser.parse_args()
    root = args.skills_root.resolve()
    if not (root / '.git').exists():
        raise ValueError('use the supported personal-skills Git checkout')
    if not re.fullmatch(r'(?:skill-[a-zA-Z0-9]+|[a-z0-9]+(?:-[a-z0-9]+)*)', args.target_dir):
        raise ValueError('invalid target directory')
    target = root / args.target_dir
    if target.is_symlink() or not target.is_dir():
        raise ValueError('existing host-initialized target directory required')
    config_path = HERE / safe_path(args.config)
    config = json.loads(config_path.read_text())
    name = config.get('skill', 'ask-first')
    if skill_name((target / 'SKILL.md').read_bytes()) != name:
        raise ValueError('target name mismatch')
    if args.inspect_target:
        if args.apply or args.record_materialized:
            raise ValueError('inspection cannot write')
        print(snapshot(target))
        return
    if not args.source_revision or not args.expected_target_sha256:
        raise ValueError('source revision and reviewed target hash are required')
    outputs = build((ROOT / safe_path(config['source_path'])).read_bytes(), config,
                    args.source_revision, Path(__file__).read_bytes())
    before = snapshot(target)
    if args.record_materialized:
        recorded = verify_materialized(target, outputs, args.expected_target_sha256)
        outputs = {MANIFEST: recorded}
        changed = [] if (target / MANIFEST).read_bytes() == recorded else [MANIFEST]
    else:
        before, changed = plan(target, outputs, args.expected_target_sha256)
    print(json.dumps({'status': 'preview' if not args.apply else 'applied' if changed else 'unchanged',
                      'before_sha256': before, 'changed': changed}, ensure_ascii=False))
    if not args.apply:
        for name in changed:
            old = (target / name).read_text().splitlines(True) if (target / name).exists() else []
            print(''.join(difflib.unified_diff(old, outputs[name].decode().splitlines(True),
                                             fromfile=name + ' (current)', tofile=name + ' (generated)')), end='')
    if args.apply and changed:
        if snapshot(target) != before:
            raise ValueError('target changed during preview')
        originals = {p: (target / p).read_bytes() if (target / p).exists() else None for p in changed}
        try:
            for name in changed:
                path = target / safe_path(name)
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
