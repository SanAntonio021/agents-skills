"""Verified official Local API connection shared by all commands."""
import re
import urllib.request
from pathlib import Path

from . import connection
from .errors import LibraryError
from .request import KEY, digest, require
from .identity import normalize_doi, normalize_text, match_identity, related, creators, year
from .local_api import LocalAPI


class Client:
    def __init__(self, profile=None, base_url=None, timeout=3, policy=None, vault=None):
        self.status = connection.empty_status()
        try:
            profile_path, ini = connection.resolve_profile(profile)
            preferences = connection.read_preferences(profile_path)
            self.base, source = connection.select_base_url(base_url, preferences)
        except connection.CheckError as error:
            raise LibraryError(str(error)) from None
        self.profile = str(profile_path) if profile_path else None
        self.binding = {'base_url': self.base, 'profile': self.profile}
        self.timeout = timeout
        # --policy remains accepted for old callers; no plugin policy is read.
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), connection.NoRedirect())
        self.api = LocalAPI(self, vault)
        self.status.update(profile=self.profile,
            profile_error=None if profile_path else 'profile_not_found',
            prefs_file=str(profile_path / 'prefs.js') if profile_path else None,
            profiles_ini=str(ini) if ini else None, base_url=self.base, base_url_source=source,
            local_api_enabled_pref=preferences.get(connection.API_PREF))
        require(preferences.get(connection.API_PREF) is not False, 'local_api_disabled')
        self.api.bind()
        headers = self.api.last_headers
        version = next((v for k, v in headers.items() if k.lower() == 'x-zotero-version'), '')
        api_version = next((v for k, v in headers.items() if k.lower() == 'zotero-api-version'), '')
        self.status.update(api_running=True, api_status=200,
            api_version=api_version, zotero_version=version)
        require(api_version == '3' and connection.VERSION.fullmatch(version),
                'local_api_identity_unverified')
        self.status['api_verified'] = True
        schema = self.read('schema')
        self.status.update(schema_running=True, schema_status=200)
        require(isinstance(schema, dict) and isinstance(schema.get('itemTypes'), (list, dict))
                and type(schema.get('version')) is int, 'local_api_schema_unverified')
        self.status.update(api_running=True, api_status=200, api_verified=True,
            api_version=api_version, zotero_version=version, schema_running=True,
            schema_status=200, schema_version=schema['version'], schema_verified=True,
            entry_verified=True, read_only_ready=True,
            local_api_write_supported=self.api.write_supported)

    def diagnostics(self):
        result = dict(self.status)
        result['process'] = connection.process_status()
        try:
            result['local_api_authorization_present'] = self.api.authorization_present()
        except LibraryError as error:
            result['local_api_authorization_error'] = error.code
        return result

    def read(self, path, params=None):
        return self.api.json(path, params=params)

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
            reason = self.identity_reason(request, item)
            return {'state': 'review_required' if reason else 'matched', 'reason': reason,
                    'parent_key': item['key'], 'candidates': [self.identity_summary(item, reason)]}
        items = self.candidates(request['library'], identity)
        distinct = self.reviewed_distinct(request, items)
        items = [item for item in items if item['key'] not in distinct]
        audit = {'distinct_candidates': distinct} if distinct else {}
        candidates = [self.identity_summary(item, match_identity(item['data'], identity)) for item in items]
        matches = [item for item in candidates if item['reason'] is None]
        if not candidates:
            return {'state': 'not_found', 'candidates': [], **audit}
        if len(matches) == 1 and len(candidates) == 1:
            return {'state': 'matched', 'parent_key': matches[0]['key'], 'candidates': candidates, **audit}
        return {'state': 'review_required', 'reason': 'duplicate_parents_require_review' if len(matches) > 1
                else 'identity_candidates_require_review', 'candidates': candidates, **audit}

    def reviewed_distinct(self, request, items):
        """Accept documented identity distinctions, pinned to each current item version."""
        identity, distinct = request['identity'], []
        candidates = {item['key'] for item in items}
        for reviewed in request.get('distinct_candidates', []):
            item = self.get(request['library'], reviewed['key'], children=False)
            data = item['data']
            require(item['version'] == reviewed['version'] and
                    normalize_text(data.get('title')) == normalize_text(reviewed['title']),
                    'distinct_candidate_changed_requires_review')
            require(item['key'] in candidates, 'distinct_candidate_not_in_lookup')
            same_doi = bool(identity.get('doi') and
                            normalize_doi(data.get('DOI')) == identity['doi'])
            same_url = bool(identity.get('url') and
                            str(data.get('url', '')).strip() == identity['url'].strip())
            require(match_identity(data, identity) == 'title_conflict' and
                    not same_doi and not same_url, 'distinct_candidate_identity_conflict')
            distinct.append(item['key'])
        return distinct

    def identity_reason(self, request, item):
        """Verify an existing PDF when legacy parent metadata lacks identity fields."""
        fields, identity = item['data'], request['identity']
        reason = match_identity(fields, identity)
        proof = request.get('parent_pdf_evidence')
        if proof is None:
            return reason
        # Missing one field must not hide a genuine conflict in another field.
        if identity.get('creators') and fields.get('creators') and creators(identity['creators']) != creators(fields['creators']):
            return 'creators_conflict'
        if identity.get('date') and fields.get('date') and year(identity['date']) != year(fields['date']):
            return 'date_conflict'
        require(request.get('parent_key') == item['key'], 'parent_pdf_parent_mismatch')
        child = self.get(request['library'], proof['key'], children=False)
        data = child['data']
        require(data.get('itemType') == 'attachment' and
                data.get('parentItem') == item['key'] and not data.get('deleted') and
                data.get('contentType') == 'application/pdf', 'parent_pdf_parent_mismatch')
        from .files import inspect_pdf
        from .reading import file_path
        inspect_pdf(file_path(self, request['library'], child['key']), proof['sha256'])
        return None if reason == 'identity_evidence_insufficient' else reason

    @staticmethod
    def identity_summary(item, reason):
        data = item['data']
        return {'key': item['key'], 'version': item['version'], 'title': data.get('title'), 'doi': data.get('DOI'),
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

    def collection(self, library, key):
        require(isinstance(key, str) and KEY.fullmatch(key), 'invalid_collection_key')
        item = self.read(self.prefix(library) + '/collections/' + key)
        require(isinstance(item, dict) and item.get('key') == key, 'invalid_local_api_response')
        return item

    def prepare(self, request, backend='local_api'):
        self.api.bind()
        require(self.api.write_supported, 'capability_missing_local_api_writes')
        identity = request.get('identity', {})
        return {'candidateKeys': [x['key'] for x in self.candidates(request['library'], identity)]
                if identity and not request.get('parent_key') else []}

    def inspect(self, request, keys):
        from .files import file_hash
        from .reading import file_path
        out = []
        for key in keys:
            item = self.get(request['library'], key, children=False)
            require(item['data'].get('itemType') == 'attachment', 'not_attachment')
            path = file_path(self, request['library'], key)
            out.append({'key': key, 'path': str(path), 'sha256': file_hash(path),
                        'deleted': bool(item['data'].get('deleted'))})
        return out

    def binding_hash(self):
        return digest(self.binding)
