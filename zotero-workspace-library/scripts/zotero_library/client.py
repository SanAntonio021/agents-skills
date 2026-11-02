"""One verified connection for diagnostics, Local API reads and fixed native operations."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import connection
from .errors import LibraryError, NativeRejected
from .request import KEY, digest, require
from .identity import normalize_doi, normalize_text, match_identity, related


DEFAULT_POLICY = Path(__file__).resolve().parents[2] / 'references' / 'automatic_fetch_policy.json'


class Client:
    def __init__(self, profile=None, base_url=None, timeout=3, policy=None):
        self.status = connection.status_payload(profile, base_url, timeout)
        if not self.status['read_only_ready']:
            raise LibraryError(self.status.get('error') or 'local_api_not_ready')
        self.base = self.status['base_url']
        self.profile = self.status['profile']
        self.binding = {'base_url': self.base, 'profile': self.profile}
        self.timeout = timeout
        # Reuse the version-pinned source audit by default. Explicit --policy
        # remains available for an isolated or separately reviewed install.
        self.policy = policy or (str(DEFAULT_POLICY) if DEFAULT_POLICY.is_file() else None)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), connection.NoRedirect())

    def read(self, path, params=None):
        if params:
            path += '?' + urllib.parse.urlencode(params)
        result = connection.request(self.opener, self.base, '/api/' + path, self.timeout)
        if not connection.successful(result):
            raise LibraryError('local_api_not_found' if result.get('status') == 404 else 'local_api_read_failed')
        try:
            return json.loads(result['body'])
        except (ValueError, TypeError):
            raise LibraryError('invalid_local_api_response') from None

    @staticmethod
    def prefix(library):
        return 'users/0' if library['type'] == 'user' else 'groups/' + str(library['id'])

    def list_all(self, path, params=None):
        out = []
        for offset in range(0, 100000, 100):
            page = self.read(path, {**(params or {}), 'start': offset, 'limit': 100})
            require(isinstance(page, list), 'invalid_local_api_response')
            out.extend(page)
            if len(page) < 100:
                return out
        raise LibraryError('local_api_pagination_limit')

    def find(self, library, query='', doi=None):
        # everything includes DOI; the default titleCreatorYear mode does not.
        items = self.list_all(self.prefix(library) + '/items/top',
                              {'q': normalize_doi(doi) if doi else query, 'qmode': 'everything'})
        if doi:
            doi = normalize_doi(doi)
            return [x for x in items if normalize_doi(x.get('data', {}).get('DOI', '')) == doi]
        return items

    def candidates(self, library, identity):
        found = {}
        queries = [identity['title']]
        words = re.findall(r'\w+', normalize_text(identity['title']))
        if words:
            queries.append(max(words, key=len))
        for person in identity.get('creators', [])[:1]:
            queries.append(person.get('lastName') or person.get('name'))
        if identity.get('doi'):
            for item in self.find(library, doi=identity['doi']):
                found[item['key']] = item
        for query in dict.fromkeys(queries):
            for item in self.find(library, query=query):
                if related(item.get('data', {}), identity):
                    found[item['key']] = item
        return list(found.values())

    def resolve(self, request):
        """Read-only resolution; never silently replace a supplied key."""
        identity = request['identity']
        if request.get('parent_key'):
            try:
                item = self.get(request['library'], request['parent_key'], children=False)
            except LibraryError as error:
                if error.code != 'local_api_not_found':
                    raise
                return {'state': 'review_required', 'reason': 'parent_not_found', 'candidates': []}
            reason = match_identity(item['data'], identity)
            return {'state': 'review_required' if reason else 'matched', 'reason': reason,
                    'parent_key': item['key'], 'candidates': [self.identity_summary(item, reason)]}
        items = self.candidates(request['library'], identity)
        candidates = [self.identity_summary(item, match_identity(item['data'], identity)) for item in items]
        matches = [item for item in candidates if item['reason'] is None]
        if not candidates:
            return {'state': 'not_found', 'candidates': []}
        if len(matches) == 1 and len(candidates) == 1:
            return {'state': 'matched', 'parent_key': matches[0]['key'], 'candidates': candidates}
        return {'state': 'review_required', 'reason': 'duplicate_parents_require_review' if len(matches) > 1
                else 'identity_candidates_require_review', 'candidates': candidates}

    @staticmethod
    def identity_summary(item, reason):
        data = item['data']
        return {'key': item['key'], 'title': data.get('title'), 'doi': data.get('DOI'),
                'date': data.get('date'), 'creators': data.get('creators', []), 'reason': reason}

    def get(self, library, key, children=True, trashed=False):
        require(isinstance(key, str) and KEY.fullmatch(key), 'invalid_item_key')
        item = self.read(self.prefix(library) + '/items/' + key)
        require(isinstance(item, dict) and item.get('key') == key, 'invalid_local_api_response')
        if children:
            children_data = self.list_all(self.prefix(library) + '/items/' + key + '/children',
                                          {'includeTrashed': '1'} if trashed else {})
            item['children'] = children_data
            for child in children_data:
                if child.get('data', {}).get('itemType') == 'attachment':
                    child['children'] = self.list_all(self.prefix(library) + '/items/' + child['key'] + '/children',
                                                      {'includeTrashed': '1'} if trashed else {})
        return item

    def collections(self, library):
        return self.list_all(self.prefix(library) + '/collections')

    def native(self, data):
        # No native input is accepted from a caller: this program and all actions are private.
        if not self.status['debug_bridge_available']:
            raise LibraryError(self.status.get('debug_bridge_error') or 'debug_bridge_unavailable')
        preferences = connection.read_preferences(Path(self.profile) if self.profile else None)
        token = preferences.get(connection.TOKEN_PREF)
        if not isinstance(token, str) or not token.isascii() or not token or any(ord(c) < 33 or ord(c) == 127 for c in token):
            raise LibraryError('bridge_credential_missing_or_invalid')
        program = Path(__file__).with_name('native.js').read_text('utf-8')
        program = 'try {\n' + program.replace('__ZOTERO_LIBRARY_INPUT__', json.dumps(data, ensure_ascii=True))
        program += '\n} catch(e) { return {nativeError:e.publicCode || "native_capability_unavailable"}; }'
        request = urllib.request.Request(self.base + '/debug-bridge/execute',
            data=program.encode('utf-8'), headers={'Content-Type': 'text/plain',
            'Authorization': 'Bearer ' + token})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                require(response.status == 201 and len(raw) <= 4 * 1024 * 1024, 'invalid_bridge_response')
                result = json.loads(raw)
                if isinstance(result, dict) and 'result' in result:
                    result = result['result']
                if isinstance(result, str):
                    result = json.loads(result)
                require(isinstance(result, dict), 'invalid_bridge_response')
                if 'nativeError' in result:
                    code = result['nativeError']
                    require(isinstance(code, str) and re.fullmatch('[a-z_]{1,80}', code), 'native_operation_failed')
                    raise NativeRejected(code)
                return result
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            raise LibraryError({401: 'bridge_authentication_failed', 403: 'bridge_access_denied',
                                404: 'bridge_not_available'}.get(code, 'bridge_http_error')) from None
        except (OSError, urllib.error.URLError):
            raise LibraryError('bridge_result_unknown') from None
        except (ValueError, TypeError):
            raise LibraryError('invalid_bridge_response') from None

    def prepare(self, request):
        caps = self.native({'action': 'capabilities'})
        for key in ('nativeWrite', 'preferences', 'fileHash'):
            require(caps.get(key) is True, 'capability_missing_' + key)
        if request.get('pdf'):
            require(caps.get('importFile') is True, 'capability_missing_import_from_file')
        require(not caps.get('legacyActive'), 'legacy_batch_active')
        reviewed = [{'id': 'debug-bridge@iris-advies.com', 'version': '3.0.1', 'preference_keys': []}]
        if self.policy:
            try:
                policy = json.loads(Path(self.policy).read_text('utf-8-sig'))
                require(set(policy) == {'schema', 'addons'} and policy['schema'] == 1)
                for entry in policy['addons']:
                    require(set(entry) == {'id', 'version', 'preference_keys', 'evidence'})
                    require(isinstance(entry['evidence'], str) and bool(entry['evidence']))
                    require(isinstance(entry['preference_keys'], list))
                    for key in entry['preference_keys']:
                        require(isinstance(key, str) and re.fullmatch(r'extensions\.[a-zA-Z0-9_.-]{1,180}', key)
                                and not re.search('token|secret|password|auth', key, re.I))
                reviewed.extend(policy['addons'])
            except (OSError, ValueError, TypeError, KeyError):
                raise LibraryError('invalid_automatic_fetch_policy') from None
        keys = []
        unknown = []
        for addon in caps.get('addons', []):
            entry = next((x for x in reviewed if (x['id'], x['version']) == (addon['id'], addon['version'])), None)
            if entry is None:
                unknown.append(addon['id'])
            else:
                keys.extend(entry['preference_keys'])
        require(not unknown, 'automatic_fetch_policy_unverified')
        caps['preferenceKeys'] = sorted(set(keys))
        # Include title/author candidates even when the DOI lookup is empty.
        identity = request.get('identity', {})
        caps['candidateKeys'] = [x['key'] for x in self.candidates(request['library'], identity)] \
            if identity and not request.get('parent_key') else []
        return caps

    def inspect(self, request, keys):
        return self.native({'action': 'inspect', 'request': {'library': request['library']}, 'keys': keys})['files']

    def binding_hash(self):
        return digest(self.binding)
