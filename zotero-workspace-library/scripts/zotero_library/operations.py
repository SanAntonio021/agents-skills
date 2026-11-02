"""Durable non-credential receipts with operation locking and no unknown-result replay."""
import contextlib
import copy
import json
import os
import time
import uuid
from pathlib import Path

from .errors import LibraryError, NativeRejected
from .files import inspect_pdf
from .request import digest, require, validate
from .identity import match_identity


class Store:
    def __init__(self, root=None):
        if root is None:
            root = os.environ.get('ZOTERO_LIBRARY_STATE_DIR')
        self.root = Path(root) if root else Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'ZoteroLibrary/operations'
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, operation_id):
        try:
            require(str(uuid.UUID(operation_id)) == operation_id, 'invalid_operation_id')
        except (ValueError, TypeError, AttributeError):
            raise LibraryError('invalid_operation_id') from None
        return self.root / (operation_id + '.json')

    def read(self, operation_id):
        path = self.path(operation_id)
        try:
            value = json.loads(path.read_text('utf-8'))
            require(value.get('operation_id') == operation_id, 'receipt_corrupt')
            return value
        except FileNotFoundError:
            return None
        except (ValueError, OSError):
            raise LibraryError('receipt_unreadable') from None

    def save(self, receipt):
        path = self.path(receipt['operation_id'])
        temporary = path.with_suffix('.' + str(uuid.uuid4()) + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(receipt, stream, ensure_ascii=True, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @contextlib.contextmanager
    def lock(self, operation_id):
        path = self.path(operation_id).with_suffix('.lock')
        with path.open('a+b') as stream:
            stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise LibraryError('operation_busy') from None
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)


class Executor:
    def __init__(self, client, store=None):
        self.client = client
        self.store = store or Store()

    def identify(self, request, kind='archive'):
        """Stable identity of the input, before deriving file metadata."""
        request_hash = digest({'kind': kind, 'request': validate(request, kind)})
        operation_id = request.get('operation_id') or str(uuid.uuid5(uuid.NAMESPACE_URL,
            self.client.binding_hash() + ':' + request_hash))
        return operation_id, request_hash

    def existing(self, request, kind='archive'):
        operation_id, request_hash = self.identify(request, kind)
        receipt = self.store.read(operation_id)
        if receipt:
            require(receipt['request_hash'] == request_hash and receipt['kind'] == kind,
                    'operation_request_conflict')
            require(receipt['connection'] == self.client.binding, 'operation_connection_mismatch')
        return receipt

    def _prepare_files(self, request, kind):
        files = {}
        if kind == 'archive' and 'pdf' in request:
            result = inspect_pdf(request['pdf']['path'], request['pdf'].get('sha256'))
            request['pdf']['sha256'] = result['sha256']
        if 'reuse_pdf' in request:
            expected = request['reuse_pdf']
            entries = self.client.inspect(request, [expected['key']])
            require(len(entries) == 1, 'reuse_pdf_state_unknown')
            files[expected['key']] = inspect_pdf(entries[0]['path'], expected['sha256'])
        if kind == 'prune':
            entries = self.client.inspect(request, [request['keep']['key']])
            require(len(entries) == 1, 'keep_state_unknown')
            inspect_pdf(entries[0]['path'], request['keep']['sha256'])
            # Unknown candidates are preserved by the native executor, never inferred safe.
            for candidate in request['candidates']:
                try:
                    entries = self.client.inspect(request, [candidate['key']])
                    if len(entries) == 1:
                        files[candidate['key']] = inspect_pdf(entries[0]['path'], candidate['sha256'])
                except LibraryError:
                    continue
        return files

    def _verify(self, receipt, job):
        request = receipt['request']
        receipt['readback_verified'] = False
        receipt.pop('pdf_verification', None)
        receipt.pop('error', None)
        require(job.get('requestHash') == receipt['request_hash'], 'native_receipt_conflict')
        receipt['native'] = job
        receipt['state'] = job['status'] if job['status'] != 'completed' else 'unknown'
        if job['status'] != 'completed':
            if any(p['recovery'] not in ('restored', 'not_needed') for p in job.get('preferenceRecovery', [])):
                receipt['state'] = 'recovery_required'
            self.store.save(receipt)
            return receipt
        require(job.get('verified') is True and job.get('preserved') is True, 'native_readback_incomplete')
        parent = self.client.get(request['library'], job['parentKey'], trashed=receipt['kind'] == 'prune')
        data = parent['data']
        require(match_identity(data, request['identity']) is None, 'identity_readback_failed')
        require(set(job.get('collections', [])) <= set(data.get('collections', [])), 'collection_readback_failed')
        if receipt['kind'] == 'archive' and (request.get('pdf') or request.get('reuse_pdf')):
            attachment = job.get('attachment')
            require(isinstance(attachment, dict), 'attachment_readback_failed')
            child = next((x for x in parent['children'] if x['key'] == attachment['key']), None)
            require(child and child['data'].get('parentItem') == job['parentKey']
                    and child['data'].get('contentType') == 'application/pdf'
                    and not child['data'].get('deleted'), 'attachment_readback_failed')
            expected = request.get('pdf') or request['reuse_pdf']
            fresh = self.client.inspect(request, [attachment['key']])
            require(len(fresh) == 1 and fresh[0]['sha256'] == expected['sha256'], 'attachment_hash_readback_failed')
            receipt['pdf_verification'] = inspect_pdf(fresh[0]['path'], expected['sha256'])
        if receipt['kind'] == 'prune':
            for key in job.get('trashed', []):
                item = self.client.get(request['library'], key, children=False)
                require(item['data'].get('deleted') in (1, True), 'trash_readback_failed')
            kept = self.client.inspect(request, [request['keep']['key']])
            require(len(kept) == 1 and not kept[0]['deleted'], 'keep_readback_failed')
            inspect_pdf(kept[0]['path'], request['keep']['sha256'])
        recovery = job.get('preferenceRecovery', [])
        receipt['state'] = 'completed' if all(p['recovery'] in ('restored', 'not_needed') for p in recovery) else 'recovery_required'
        receipt['readback_verified'] = True
        self.store.save(receipt)
        return receipt

    def _inspect(self, receipt):
        require(receipt['connection'] == self.client.binding, 'operation_connection_mismatch')
        if not receipt['attempts']:
            return receipt
        attempt = receipt['attempts'][-1]
        if attempt.get('rejected'):
            return receipt
        info = self.client.native({'action': 'operation', 'attemptId': attempt['id']})
        if info.get('job') is not None:
            try:
                return self._verify(receipt, info['job'])
            except LibraryError as error:
                receipt['state'] = 'unknown'
                receipt['error'] = error.code
                self.store.save(receipt)
                return receipt
        if info['processIdentity'] == attempt['processIdentity']:
            receipt['state'] = 'unknown'
            receipt['error'] = 'original_process_still_alive_operation_unknown'
        else:
            # Old process has ended. Never restore preferences from a stale snapshot.
            receipt['state'] = 'recovery_required' if attempt['preferenceKeys'] else 'interrupted'
            receipt['error'] = 'original_process_ended_reconcile_persisted_state'
            # Persisted results must be queried before any continuation.
            receipt['persisted_candidates'] = [x['key'] for x in self.client.candidates(
                receipt['request']['library'], receipt['request']['identity'])]
        self.store.save(receipt)
        return receipt

    def status(self, operation_id):
        with self.store.lock(operation_id):
            receipt = self.store.read(operation_id)
            require(receipt is not None, 'operation_not_found')
            return self._inspect(receipt)

    def run(self, request, kind='archive', resume=False, wait=10):
        request = validate(request, kind)
        # Hash the original normalized request, before deriving a source-file hash.
        operation_id, request_hash = self.identify(request, kind)
        with self.store.lock(operation_id):
            receipt = self.store.read(operation_id)
            if receipt:
                require(receipt['request_hash'] == request_hash and receipt['kind'] == kind,
                        'operation_request_conflict')
                require(receipt['connection'] == self.client.binding, 'operation_connection_mismatch')
                if receipt['state'] == 'completed':
                    # Revalidate persisted results; completed import never creates a second item.
                    try:
                        return self._verify(receipt, receipt['native'])
                    except LibraryError as error:
                        receipt['state'] = 'unknown'
                        receipt['error'] = error.code
                        self.store.save(receipt)
                        return receipt
                receipt = self._inspect(receipt)
                if receipt['state'] in {'completed', 'running', 'unknown', 'recovery_required'}:
                    return receipt
                if not resume and receipt['state'] != 'prepared':
                    return receipt
            else:
                receipt = {'schema': 1, 'operation_id': operation_id, 'request_hash': request_hash,
                    'input_request': copy.deepcopy(request), 'request': request, 'kind': kind, 'connection': self.client.binding,
                    'state': 'prepared', 'attempts': []}
                self.store.save(receipt)
            caps = self.client.prepare(request)
            if request.get('pdf') and receipt['request'].get('pdf', {}).get('sha256'):
                request['pdf']['sha256'] = receipt['request']['pdf']['sha256']
            files = self._prepare_files(request, kind)
            receipt['request'] = request
            attempt_id = str(uuid.uuid5(uuid.UUID(operation_id), str(len(receipt['attempts']))))
            attempt = {'id': attempt_id, 'processIdentity': caps['processIdentity'],
                       'preferenceKeys': caps['preferenceKeys']}
            receipt['attempts'].append(attempt)
            receipt['state'] = 'dispatched'
            receipt.pop('error', None)
            self.store.save(receipt)  # Durable BEFORE the first native write.
            try:
                job = self.client.native({'action': 'start', 'kind': kind, 'request': request,
                    'operationId': operation_id, 'attemptId': attempt_id, 'requestHash': request_hash,
                    'processIdentity': caps['processIdentity'],
                    'candidateKeys': caps['candidateKeys'],
                    'preferenceKeys': caps['preferenceKeys'], 'files': files})
                receipt = self._verify(receipt, job)
                deadline = time.monotonic() + min(wait, 30)
                while receipt['state'] == 'running' and time.monotonic() < deadline:
                    time.sleep(.1)
                    receipt = self._inspect(receipt)
            except NativeRejected as error:
                attempt['rejected'] = True
                receipt['state'] = 'failed'
                receipt['error'] = error.code
                self.store.save(receipt)
            except LibraryError as error:
                # Even authentication/error responses do not authorize a different interface replay.
                receipt['state'] = 'unknown'
                receipt['error'] = error.code
                self.store.save(receipt)
            return receipt

    def resume(self, operation_id, wait=10):
        receipt = self.store.read(operation_id)
        require(receipt is not None, 'operation_not_found')
        return self.run(receipt['input_request'], receipt['kind'], resume=True, wait=wait)


def summary(receipt):
    return {key: receipt[key] for key in ('operation_id', 'kind', 'state', 'error', 'native',
        'readback_verified', 'pdf_verification') if key in receipt}
