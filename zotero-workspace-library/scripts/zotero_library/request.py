"""Strict public request validation; business evidence is data, never executable code."""
import hashlib
import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .errors import LibraryError
from .identity import normalize_doi

VERSIONS = {'official', 'accepted_manuscript', 'preprint', 'temporary_preprint', 'unresolved'}
KEY = re.compile(r'[A-Z0-9]{8}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
FIELDS = {'title', 'DOI', 'url', 'date', 'publicationTitle', 'volume', 'issue', 'pages',
          'publisher', 'place', 'ISBN', 'ISSN', 'reportNumber', 'institution', 'abstractNote',
          'language', 'edition', 'seriesTitle', 'shortTitle'}
TYPES = {'journalArticle', 'conferencePaper', 'preprint', 'report', 'book', 'document',
         'standard', 'webpage', 'thesis'}


def require(ok, code='invalid_request'):
    if not ok:
        raise LibraryError(code)


def obj(value, allowed, required=()):
    require(isinstance(value, dict) and set(required) <= value.keys() <= set(allowed))


def string(value, maximum=4096):
    require(isinstance(value, str) and 0 < len(value) <= maximum and '\x00' not in value)


def key(value):
    require(isinstance(value, str) and KEY.fullmatch(value))


def url(value):
    string(value)
    u = urlsplit(value)
    require(u.scheme in {'https', 'http'} and u.hostname and not u.username and not u.password)
    require(not re.search(r'(token|password|secret|authorization|api.?key)=', u.query, re.I))


def evidence(value):
    require(isinstance(value, list) and 0 < len(value) <= 30)
    for entry in value:
        string(entry)
        require(not re.search(r'(bearer\s|password\s*[:=]|token\s*[:=])', entry, re.I))


def attachment(value, candidate=False):
    obj(value, {'key', 'sha256', 'version', 'evidence'} | ({'disposition'} if candidate else set()),
        {'key', 'sha256', 'version', 'evidence'})
    key(value['key'])
    require(isinstance(value['sha256'], str) and SHA.fullmatch(value['sha256']))
    require(isinstance(value['version'], str) and value['version'] in VERSIONS)
    evidence(value['evidence'])
    if candidate:
        require(value.get('disposition', 'duplicate') in ('duplicate', 'superseded'))


def validate_collection(value):
    allowed = {'schema', 'operation_id', 'library', 'key', 'expected_version',
               'expected_name', 'expected_parent', 'name', 'parentCollection'}
    required = {'schema', 'library', 'key', 'expected_version', 'expected_name', 'expected_parent'}
    obj(value, allowed, required)
    require(value['schema'] == 1)
    if 'operation_id' in value:
        try:
            require(str(uuid.UUID(value['operation_id'])) == value['operation_id'], 'invalid_operation_id')
        except (ValueError, TypeError, AttributeError):
            raise LibraryError('invalid_operation_id') from None
    lib = value['library']
    obj(lib, {'type', 'id'}, {'type'})
    require(isinstance(lib['type'], str) and lib['type'] in {'user', 'group'})
    if lib['type'] == 'group':
        require(type(lib.get('id')) is int and lib['id'] > 0)
    else:
        require('id' not in lib)
    key(value['key'])
    require(type(value['expected_version']) is int and value['expected_version'] >= 0)
    string(value['expected_name'], 255)
    for field in ('expected_parent', 'parentCollection'):
        if field not in value:
            continue
        parent = value[field]
        if parent is False:
            continue
        key(parent)
    if 'name' in value:
        string(value['name'], 255)
        require(bool(value['name'].strip()), 'invalid_collection_name')
    require('name' in value or 'parentCollection' in value, 'collection_update_has_no_changes')
    return value


def validate_membership(value):
    obj(value, {'schema', 'operation_id', 'library', 'key', 'expected_version',
                'expected_collections', 'workspace_root', 'target_collection'},
        {'schema', 'library', 'key', 'expected_version', 'expected_collections',
         'workspace_root', 'target_collection'})
    require(value['schema'] == 1)
    if 'operation_id' in value:
        try:
            require(str(uuid.UUID(value['operation_id'])) == value['operation_id'], 'invalid_operation_id')
        except (ValueError, TypeError, AttributeError):
            raise LibraryError('invalid_operation_id') from None
    lib = value['library']
    obj(lib, {'type', 'id'}, {'type'})
    require((lib['type'] == 'user' and 'id' not in lib) or
            (lib['type'] == 'group' and type(lib.get('id')) is int and lib['id'] > 0), 'invalid_library')
    for field in ('key', 'workspace_root', 'target_collection'):
        key(value[field])
    require(type(value['expected_version']) is int and value['expected_version'] >= 0)
    require(isinstance(value['expected_collections'], list) and
            all(isinstance(x, str) and KEY.fullmatch(x) for x in value['expected_collections']) and
            len(value['expected_collections']) == len(set(value['expected_collections'])),
            'invalid_expected_collections')
    return value


def validate(value, kind='archive'):
    value = json.loads(json.dumps(value, allow_nan=False))
    if kind == 'collection':
        return validate_collection(value)
    if kind == 'membership':
        return validate_membership(value)
    if kind == 'tags':
        obj(value, {'schema', 'operation_id', 'library', 'key', 'expected_version', 'tags'},
            {'schema', 'library', 'key', 'expected_version', 'tags'})
        require(value['schema'] == 1)
        if 'operation_id' in value:
            try:
                require(str(uuid.UUID(value['operation_id'])) == value['operation_id'], 'invalid_operation_id')
            except (ValueError, TypeError, AttributeError):
                raise LibraryError('invalid_operation_id') from None
        lib = value['library']
        obj(lib, {'type', 'id'}, {'type'})
        require(lib['type'] in {'user', 'group'})
        require((lib['type'] == 'user' and 'id' not in lib) or
                (lib['type'] == 'group' and type(lib.get('id')) is int and lib['id'] > 0))
        key(value['key'])
        require(type(value['expected_version']) is int and value['expected_version'] >= 0)
        require(isinstance(value['tags'], list) and 0 < len(value['tags']) <= 30)
        for tag in value['tags']:
            string(tag, 255)
            require(tag == tag.strip(), 'invalid_tag')
        require(len(set(value['tags'])) == len(value['tags']), 'duplicate_tag')
        return value
    common = {'schema', 'operation_id', 'library', 'identity', 'parent_key'}
    allowed = common | ({'metadata', 'collections', 'pdf', 'reuse_pdf', 'distinct_candidates',
                         'parent_pdf_evidence'} if kind == 'archive'
                        else {'keep', 'candidates'})
    obj(value, allowed, {'schema', 'library', 'identity'})
    require(value['schema'] == 1)
    if 'operation_id' in value:
        try:
            require(str(uuid.UUID(value['operation_id'])) == value['operation_id'])
        except (ValueError, TypeError, AttributeError):
            raise LibraryError('invalid_operation_id') from None
    lib = value['library']
    obj(lib, {'type', 'id'}, {'type'})
    require(isinstance(lib['type'], str) and lib['type'] in {'user', 'group'})
    if lib['type'] == 'group':
        require(type(lib.get('id')) is int and lib['id'] > 0)
    else:
        require('id' not in lib)
    identity = value['identity']
    obj(identity, {'title', 'doi', 'creators', 'date', 'url', 'evidence'}, {'title', 'evidence'})
    string(identity['title'])
    evidence(identity['evidence'])
    if 'doi' in identity:
        string(identity['doi'], 512)
        identity['doi'] = normalize_doi(identity['doi'])
        require(re.fullmatch(r'10\.\d{4,9}/\S+', identity['doi'], re.I))
    if 'date' in identity:
        string(identity['date'], 64)
    if 'url' in identity:
        url(identity['url'])
    if 'creators' in identity:
        require(isinstance(identity['creators'], list) and len(identity['creators']) <= 200)
        for creator in identity['creators']:
            obj(creator, {'creatorType', 'firstName', 'lastName', 'name'}, {'creatorType'})
            require(isinstance(creator['creatorType'], str) and creator['creatorType'] in {'author', 'editor', 'contributor'})
            require(bool(creator.get('name') or creator.get('lastName')))
            for text in creator.values():
                string(text, 512)
    if 'parent_key' in value:
        key(value['parent_key'])
    proof = value.get('parent_pdf_evidence')
    if proof is not None:
        require(kind == 'archive' and 'parent_key' in value, 'parent_pdf_requires_explicit_parent')
        obj(proof, {'key', 'sha256', 'evidence'}, {'key', 'sha256', 'evidence'})
        key(proof['key'])
        require(isinstance(proof['sha256'], str) and SHA.fullmatch(proof['sha256']))
        evidence(proof['evidence'])
    require(identity.get('doi') or identity.get('url') or
            (identity.get('date') and identity.get('creators')) or proof,
            'identity_evidence_insufficient')
    if kind == 'archive':
        reviewed = value.get('distinct_candidates', [])
        require(isinstance(reviewed, list) and len(reviewed) <= 30)
        require(not reviewed or 'parent_key' not in value, 'distinct_review_with_explicit_parent')
        seen = set()
        for candidate in reviewed:
            obj(candidate, {'key', 'version', 'title', 'evidence'},
                {'key', 'version', 'title', 'evidence'})
            key(candidate['key'])
            require(candidate['key'] not in seen, 'duplicate_distinct_review')
            seen.add(candidate['key'])
            require(type(candidate['version']) is int and candidate['version'] >= 0)
            string(candidate['title'])
            evidence(candidate['evidence'])
        meta = value.get('metadata', {})
        obj(meta, FIELDS | {'itemType'})
        for field, text in meta.items():
            string(text, 20000 if field == 'abstractNote' else 4096)
            if field == 'url':
                url(text)
        if 'DOI' in meta:
            meta['DOI'] = normalize_doi(meta['DOI'])
            require(re.fullmatch(r'10\.\d{4,9}/\S+', meta['DOI'], re.I))
        require(meta.get('itemType', 'document') in TYPES)
        for field, ident in (('title', 'title'), ('DOI', 'doi'), ('url', 'url'), ('date', 'date')):
            if field in meta and ident in identity:
                require(meta[field].lower() == identity[ident].lower(), 'identity_conflict')
        collections = value.setdefault('collections', [])
        require(isinstance(collections, list) and len(collections) <= 30)
        for collection in collections:
            obj(collection, {'key', 'path'})
            require(len(collection) == 1)
            if 'key' in collection:
                key(collection['key'])
            else:
                require(isinstance(collection['path'], list) and 0 < len(collection['path']) <= 10)
                for part in collection['path']:
                    string(part, 255)
        require(not ('pdf' in value and 'reuse_pdf' in value))
        if 'reuse_pdf' in value:
            attachment(value['reuse_pdf'])
        if 'pdf' in value:
            pdf = value['pdf']
            obj(pdf, {'path', 'sha256', 'version', 'evidence'}, {'path', 'version', 'evidence'})
            string(pdf['path'])
            require(Path(pdf['path']).is_absolute(), 'pdf_path_must_be_absolute')
            pdf['path'] = str(Path(pdf['path']).resolve())
            require(isinstance(pdf['version'], str) and pdf['version'] in VERSIONS)
            evidence(pdf['evidence'])
            if 'sha256' in pdf:
                require(isinstance(pdf['sha256'], str) and SHA.fullmatch(pdf['sha256']))
    else:
        require('parent_key' in value and 'keep' in value and 'candidates' in value)
        attachment(value['keep'])
        require(isinstance(value['candidates'], list) and 0 < len(value['candidates']) <= 30)
        seen = {value['keep']['key']}
        for candidate in value['candidates']:
            attachment(candidate, candidate=True)
            require(candidate['key'] not in seen)
            seen.add(candidate['key'])
            require(candidate['version'] != 'unresolved' and value['keep']['version'] != 'unresolved'
                    and (candidate['version'] == value['keep']['version'] or
                         candidate.get('disposition') == 'superseded'),
                    'prune_version_not_verified')
    return value


def read_request(path, kind='archive'):
    try:
        p = Path(path)
        require(p.stat().st_size <= 256 * 1024, 'request_too_large')
        return validate(json.loads(p.read_text('utf-8-sig')), kind)
    except (OSError, ValueError, TypeError, KeyError):
        raise LibraryError('invalid_request') from None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':')).encode()).hexdigest()
