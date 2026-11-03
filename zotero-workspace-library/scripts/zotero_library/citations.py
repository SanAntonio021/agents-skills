"""BibTeX export and explicit, repeatable manuscript edits. No generated citation keys."""
import difflib
import os
import re
import uuid
from pathlib import Path

from .errors import LibraryError
from .request import KEY, require


def entries(text):
    """Read balanced BibTeX entries, retaining their original spelling and contents."""
    found = {}
    cursor = 0
    pattern = re.compile(r'(?m)^[ \t]*@([A-Za-z]+)\s*([({])')
    while match := pattern.search(text, cursor):
        opening = match[2]
        braces = 1 if opening == '{' else 0
        quoted = False
        pos = match.end()
        start = pos
        while pos < len(text):
            char = text[pos]
            if char == '\\':
                pos += 2
                continue
            if char == '"' and braces == (1 if opening == '{' else 0):
                quoted = not quoted
            if not quoted:
                if char == '{':
                    braces += 1
                elif char == '}':
                    braces -= 1
                    if opening == '{' and braces == 0:
                        break
                elif char == ')' and opening == '(' and braces == 0:
                    break
            pos += 1
        require(pos < len(text) and braces >= 0, 'invalid_bibtex')
        cursor = pos + 1
        if match[1].lower() in ('comment', 'preamble', 'string'):
            continue
        key, comma, _ = text[start:pos].partition(',')
        key = key.strip()
        require(comma and key and not re.search(r'[\s,{}()\\#%&^~;@\[\]]', key), 'invalid_citation_key')
        require(key not in found, 'duplicate_citation_key')
        found[key] = text[match.start():cursor].strip()
    return found


def exported(client, library, keys):
    require(isinstance(keys, list) and 0 < len(keys) <= 100
            and all(isinstance(key, str) and KEY.fullmatch(key) for key in keys)
            and len(set(keys)) == len(keys), 'invalid_item_keys')
    client.api.bind()
    result, mapping = {}, []
    for key in keys:
        item = client.get(library, key, children=False)
        require(item['data'].get('itemType') not in ('note', 'attachment', 'annotation')
                and not item['data'].get('deleted'), 'citation_requires_regular_item')
        text = client.api.exchange(client.prefix(library) + '/items/' + key, {'format': 'bibtex'})
        parsed = entries(text)
        require(len(parsed) == 1, 'unexpected_bibtex_export')
        citation_key, entry = next(iter(parsed.items()))
        if citation_key in result and result[citation_key] != entry:
            raise LibraryError('exported_citation_key_conflict')
        result[citation_key] = entry
        mapping.append({'item_key': key, 'citation_key': citation_key})
    return result, mapping


def target_path(value):
    require(isinstance(value, str) and Path(value).is_absolute(), 'explicit_absolute_target_required')
    path = Path(value)
    require(path.parent.is_dir() and not path.is_symlink(), 'target_unavailable')
    return path


def original(path, required=False):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        require(not required, 'target_unavailable')
        return None


def decoded(raw):
    try:
        return (raw or b'').decode('utf-8-sig')
    except UnicodeError:
        raise LibraryError('target_requires_utf8') from None


def encoded(text, raw):
    return (b'\xef\xbb\xbf' if raw and raw.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8')


def replace_checked(path, before, after):
    if before == after:
        return False
    lock = path.with_name(path.name + '.zotero-library.lock')
    temporary = path.with_name(path.name + '.' + str(uuid.uuid4()) + '.tmp')
    acquired = False
    try:
        with lock.open('x'):
            acquired = True
            try:
                require(original(path) == before, 'target_changed_during_operation')
                with temporary.open('xb') as stream:
                    stream.write(after); stream.flush(); os.fsync(stream.fileno())
                require(original(path) == before, 'target_changed_during_operation')
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    except FileExistsError:
        raise LibraryError('target_busy') from None
    finally:
        # Do not remove a lock owned by another command.
        if acquired:
            lock.unlink(missing_ok=True)
    return True


def merge_bib(raw, new):
    text = decoded(raw)
    old = entries(text)
    conflicts = []
    for key, entry in new.items():
        if key in old and old[key].replace('\r\n', '\n') != entry.replace('\r\n', '\n'):
            conflicts.append({'key': key, 'difference': '\n'.join(list(difflib.unified_diff(
                old[key].splitlines(), entry.splitlines(), fromfile='existing', tofile='exported', lineterm=''))[:80])})
    if conflicts:
        return None, conflicts
    newline = '\r\n' if '\r\n' in text else '\n'
    added = [entry.replace('\r\n', '\n').replace('\n', newline)
             for key, entry in new.items() if key not in old]
    if added:
        text += (newline if text and not text.endswith(('\r', '\n')) else '') + newline.join(added) + newline
    return encoded(text, raw), []


def export_bib(client, library, keys, output=None):
    new, mapping = exported(client, library, keys)
    result = {'state': 'exported', 'entries': mapping}
    if output is None:
        result['bibtex'] = '\n\n'.join(new.values()) + '\n'
        return result
    path = target_path(output)
    require(path.suffix.lower() == '.bib', 'bibliography_requires_bib_extension')
    raw = original(path)
    merged, conflicts = merge_bib(raw, new)
    if conflicts:
        return {'state': 'conflict', 'conflicts': conflicts}
    result.update(path=str(path), changed=replace_checked(path, raw, merged))
    return result


def cite(client, request):
    require(isinstance(request, dict) and set(request) ==
            {'schema', 'library', 'keys', 'style', 'target', 'bibliography'} and request['schema'] == 1,
            'invalid_citation_request')
    library = request['library']
    require(library == {'type': 'user'} or isinstance(library, dict) and set(library) == {'type', 'id'}
            and library['type'] == 'group' and type(library['id']) is int and library['id'] > 0,
            'invalid_library')
    require(request['style'] in ('markdown', 'latex'), 'invalid_citation_style')
    target = request['target']
    require(isinstance(target, dict) and set(target) == {'path', 'anchor', 'placement'}
            and isinstance(target['anchor'], str) and target['anchor']
            and target['placement'] in ('before', 'after'), 'explicit_insertion_position_required')
    path, bib = target_path(target['path']), target_path(request['bibliography'])
    require(path.resolve() != bib.resolve() and bib.suffix.lower() == '.bib', 'invalid_bibliography_target')
    raw, bib_raw = original(path, required=True), original(bib)
    text = decoded(raw)
    require(text.count(target['anchor']) == 1, 'citation_anchor_must_be_unique')
    position = text.index(target['anchor'])
    if target['placement'] == 'after':
        position += len(target['anchor'])
    if request['style'] == 'latex':
        line = text[text.rfind('\n', 0, position) + 1:position]
        require(not re.search(r'(?<!\\)(?:\\\\)*%', line), 'citation_position_commented')
    new, mapping = exported(client, library, request['keys'])
    merged, conflicts = merge_bib(bib_raw, new)
    if conflicts:
        return {'state': 'conflict', 'conflicts': conflicts}
    keys = list(dict.fromkeys(row['citation_key'] for row in mapping))
    citation = ('\\cite{' + ','.join(keys) + '}') if request['style'] == 'latex' else '[' + '; '.join('@' + key for key in keys) + ']'
    if target['placement'] == 'after':
        exists = text[position:].startswith(citation)
    else:
        exists = text[:position].endswith(citation)
    updated = raw if exists else encoded(text[:position] + citation + text[position:], raw)
    require(original(path, required=True) == raw, 'target_changed_during_operation')
    bib_changed = replace_checked(bib, bib_raw, merged)
    changed = replace_checked(path, raw, updated)
    return {'state': 'cited', 'citation': citation, 'entries': mapping, 'path': str(path),
            'bibliography': str(bib), 'changed': changed, 'bibliography_changed': bib_changed}
