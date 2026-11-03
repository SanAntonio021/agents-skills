"""One loopback-only transport for reads, authorized writes and file bytes."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .authorization import Vault
from .errors import LibraryError
from .request import digest, require


class LocalAPI:
    def __init__(self, client, vault=None):
        self.client, self.vault = client, vault
        self.server_id = None
        self.last_headers = {}
        self.write_supported = False

    def exchange(self, path='', params=None, method='GET', body=None, timeout=None,
                 headers=None, form=None, binary=None, authorize=False):
        require(isinstance(path, str) and not path.startswith('/') and
                not any(x in path for x in ('..', '?', '#', '\\')), 'invalid_api_path')
        require(method in ('GET', 'POST', 'PATCH', 'PUT'), 'unsupported_api_method')
        require(sum(v is not None for v in (body, form, binary)) <= 1, 'invalid_api_body')
        query = '?' + urllib.parse.urlencode(params) if params else ''
        head = {'Zotero-API-Version': '3'}
        if self.server_id:
            head['Zotero-Server-ID'] = self.server_id
        data = None
        if body is not None:
            data = json.dumps(body, allow_nan=False).encode('utf-8')
            head['Content-Type'] = 'application/json'
        elif form is not None:
            data = urllib.parse.urlencode(form).encode('utf-8')
            head['Content-Type'] = 'application/x-www-form-urlencoded'
        elif binary is not None:
            data = binary
            head['Content-Type'] = 'application/octet-stream'
        head.update(headers or {})
        if authorize:
            require(self.write_supported and self.server_id, 'capability_missing_local_api_writes')
            head['Zotero-API-Key'] = self.credentials()['key']
        request = urllib.request.Request(self.client.base + '/api/' + path + query,
                                        data=data, headers=head, method=method)
        try:
            with self.client.opener.open(request, timeout=timeout or self.client.timeout) as response:
                self.last_headers = dict(response.headers)
                identity = response.headers.get('Zotero-Server-ID')
                require(not self.server_id or identity == self.server_id, 'database_identity_changed')
                if identity:
                    require(re.fullmatch(r'[A-Za-z0-9._:-]{1,200}', identity), 'invalid_database_identity')
                    self.server_id = identity
                if path == '':
                    ver = response.headers.get('X-Zotero-Version', '')
                    self.write_supported = bool(identity and re.match(r'(?:[1-9]\d+)\.', ver)
                                                and int(ver.split('.')[0]) >= 10)
                raw = response.read(32 * 1024 * 1024 + 1)
                require(len(raw) <= 32 * 1024 * 1024, 'local_api_response_too_large')
                return raw.decode('utf-8-sig')
        except urllib.error.HTTPError as error:
            code, identity = error.code, error.headers.get('Zotero-Server-ID')
            error.close()
            if self.server_id and identity != self.server_id:
                raise LibraryError('database_identity_changed') from None
            if code == 401 and authorize:
                self._vault().forget()
            raise LibraryError({401: 'local_api_authorization_required',
                301: 'redirect_blocked', 302: 'redirect_blocked', 307: 'redirect_blocked', 308: 'redirect_blocked',
                403: 'local_api_authorization_denied', 404: 'local_api_not_found',
                409: 'local_api_conflict', 412: 'local_api_version_conflict',
                428: 'local_api_precondition_required', 429: 'local_api_authorization_rate_limited'
                }.get(code, 'local_api_result_unknown' if code >= 500 else 'local_api_request_rejected')) from None
        except (OSError, urllib.error.URLError):
            raise LibraryError('local_api_result_unknown') from None
        except UnicodeError:
            raise LibraryError('invalid_local_api_response') from None

    def json(self, path='', **kwargs):
        raw = self.exchange(path, **kwargs)
        try:
            return json.loads(raw) if raw.strip() else None
        except ValueError:
            raise LibraryError('invalid_local_api_response') from None

    def bind(self, expected=None):
        self.exchange()
        require(expected is None or expected == self.server_id, 'database_identity_changed')
        return self.server_id

    def _vault(self):
        return self.vault or Vault(digest({'connection': self.client.binding, 'database': self.server_id}))

    def credentials(self, renew=False):
        self.bind()
        require(self.write_supported, 'capability_missing_local_api_writes')
        vault = self._vault()
        if renew:
            vault.forget()
        secret = vault.get()
        if secret:
            return {'key': secret, 'remember': True}
        result = self.json('local/authorize', method='POST',
                           body={'appName': 'Zotero Workspace Library'}, timeout=120)
        require(isinstance(result, dict) and isinstance(result.get('key'), str)
                and re.fullmatch(r'[A-Za-z0-9_-]{8,200}', result['key'])
                and isinstance(result.get('remember'), bool), 'invalid_authorization_response')
        if result['remember']:
            vault.put(result['key'])
        return result

    def authorization_present(self):
        return bool(self.server_id and self._vault().get())

    def upload_path(self, url):
        # Upload addresses and keys stay in memory, never in receipts.
        parsed = urllib.parse.urlsplit(url)
        base = urllib.parse.urlsplit(self.client.base)
        require(parsed.scheme == base.scheme and parsed.netloc == base.netloc and
                not parsed.query and not parsed.fragment and
                re.fullmatch(r'/api/local/uploads/[A-Za-z0-9]+', parsed.path), 'unsafe_upload_url')
        return parsed.path[len('/api/'):]
