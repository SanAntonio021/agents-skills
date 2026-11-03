"""Bound Local API text/auth transport; never expose response bodies on errors."""
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
        self.client = client
        self.server_id = None
        self.vault = vault

    def exchange(self, path='', params=None, method='GET', body=None, timeout=None):
        query = '?' + urllib.parse.urlencode(params) if params else ''
        headers = {'Zotero-API-Version': '3'}
        if self.server_id:
            headers['Zotero-Server-ID'] = self.server_id
        if body is not None:
            body = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.client.base + '/api/' + path + query,
                                        data=body, headers=headers, method=method)
        try:
            with self.client.opener.open(request, timeout=timeout or self.client.timeout) as response:
                identity = response.headers.get('Zotero-Server-ID')
                require(identity and re.fullmatch(r'[A-Za-z0-9._:-]{1,200}', identity),
                        'capability_missing_local_api_writes')
                require(not self.server_id or identity == self.server_id, 'database_identity_changed')
                self.server_id = identity
                raw = response.read(32 * 1024 * 1024 + 1)
                require(len(raw) <= 32 * 1024 * 1024, 'local_api_response_too_large')
                return raw.decode('utf-8-sig')
        except urllib.error.HTTPError as error:
            code = error.code
            identity = error.headers.get('Zotero-Server-ID')
            error.close()
            if self.server_id and identity and identity != self.server_id:
                raise LibraryError('database_identity_changed') from None
            raise LibraryError({401: 'local_api_authorization_required',
                                403: 'local_api_authorization_denied', 404: 'local_api_not_found',
                                412: 'local_api_version_conflict', 428: 'local_api_precondition_required',
                                429: 'local_api_authorization_rate_limited'}.get(code, 'local_api_request_failed')) from None
        except (OSError, urllib.error.URLError):
            raise LibraryError('local_api_result_unknown') from None
        except UnicodeError:
            raise LibraryError('invalid_local_api_response') from None

    def bind(self, expected=None):
        self.exchange()
        require(expected is None or expected == self.server_id, 'database_identity_changed')
        return self.server_id

    def credentials(self, renew=False):
        self.bind()
        vault = self.vault or Vault(digest({'connection': self.client.binding, 'database': self.server_id}))
        if renew:
            vault.forget()
        secret = vault.get()
        if secret:
            return {'key': secret, 'remember': True}
        try:
            result = json.loads(self.exchange('local/authorize', method='POST',
                                body={'appName': 'Zotero Workspace Library'}, timeout=120))
        except ValueError:
            raise LibraryError('invalid_authorization_response') from None
        require(isinstance(result, dict) and isinstance(result.get('key'), str)
                and re.fullmatch(r'[A-Za-z0-9_-]{8,200}', result['key'])
                and isinstance(result.get('remember'), bool), 'invalid_authorization_response')
        if result['remember']:
            vault.put(result['key'])
        return {'key': result['key'], 'remember': result['remember']}

    def authorization_present(self):
        self.bind()
        vault = self.vault or Vault(digest({'connection': self.client.binding, 'database': self.server_id}))
        return bool(vault.get())
