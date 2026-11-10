"""Durable API stages, fixed create keys and one local lock per database."""
import contextlib
import copy
import json
import os
import subprocess
import uuid
from pathlib import Path

from .errors import LibraryError
from .files import inspect_pdf
from .request import digest, require, validate
from .identity import match_identity
from .objects import Objects
from .reading import file_path


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
        try:
            value = json.loads(self.path(operation_id).read_text('utf-8'))
            require(value.get('operation_id') == operation_id, 'receipt_corrupt')
            return value
        except FileNotFoundError:
            return None
        except (ValueError, OSError):
            raise LibraryError('receipt_unreadable') from None

    def save(self, receipt):
        atomic_json(self.path(receipt['operation_id']), receipt)

    def lock(self, operation_id):
        return file_lock(self.path(operation_id).with_suffix('.lock'), 'operation_busy')


def atomic_json(path, value):
    temporary = path.with_suffix('.' + str(uuid.uuid4()) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def file_lock(path, code):
    with path.open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise LibraryError(code) from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class Coordination:
    def __init__(self, database_id):
        # Receipt location, installation path and CLI flags cannot change this lock.
        self.root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'ZoteroLibrary/databases'
        self.root.mkdir(parents=True, exist_ok=True)
        stem = digest({'database': database_id})
        self.lock_path = self.root / (stem + '.lock')
        self.pending_path = self.root / (stem + '.json')

    def lock(self):
        return file_lock(self.lock_path, 'database_operation_busy')

    def reserve(self, receipt, store):
        if self.pending_path.exists():
            try:
                pending = json.loads(self.pending_path.read_text('utf-8'))
                previous = Store(Path(pending['receipt']).parent).read(pending['operation_id'])
            except (OSError, ValueError, KeyError, LibraryError):
                raise LibraryError('database_pending_receipt_unreadable') from None
            if previous and previous.get('state') == 'completed' and previous.get('readback_verified'):
                self.pending_path.unlink()
            else:
                require(pending['operation_id'] == receipt['operation_id'] and
                        pending['request_hash'] == receipt['request_hash'], 'database_operation_pending')
                require(Path(pending['receipt']).resolve() == store.path(receipt['operation_id']).resolve(),
                        'operation_pending_in_other_state_directory')
        atomic_json(self.pending_path, {
            'operation_id': receipt['operation_id'], 'request_hash': receipt['request_hash'],
            'receipt': str(store.path(receipt['operation_id']).resolve()),
            'database_id': receipt['database_id'], 'api_keys': receipt.get('api_keys')})

    def finish(self, receipt, store):
        if not self.pending_path.exists():
            return
        pending = json.loads(self.pending_path.read_text('utf-8'))
        if (pending.get('operation_id') == receipt['operation_id'] and
                pending.get('request_hash') == receipt['request_hash'] and
                pending.get('receipt') == str(store.path(receipt['operation_id']).resolve())):
            self.pending_path.unlink()


def legacy_process_ended(attempts):
    identity = next((x.get('processIdentity') for x in reversed(attempts) if x.get('processIdentity')), None)
    if not identity:
        return False
    try:
        pid, created = identity.split(':')
        require(pid.isdigit() and created.isdigit(), 'legacy_process_identity_unknown')
        if os.name != 'nt':
            os.kill(int(pid), 0)
            return False
        command = ("$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" + pid +
                   "' -ErrorAction Stop; if($p){[DateTimeOffset]$p.CreationDate | "
                   "ForEach-Object {$_.ToUnixTimeMilliseconds()}}")
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
            capture_output=True, text=True, timeout=5, check=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return not result.stdout.strip() or result.stdout.strip() != created
    except ProcessLookupError:
        return True
    except (OSError, ValueError, subprocess.SubprocessError, LibraryError):
        return False


class Executor:
    def __init__(self, client, store=None):
        self.client = client
        self.store = store or Store()

    def identify(self, request, kind='archive'):
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

    def verify_legacy(self, receipt):
        job = receipt.get('native', {})
        require(job.get('verified') and job.get('preserved'), 'legacy_result_unverified')
        require(job.get('requestHash') == receipt['request_hash'], 'legacy_receipt_conflict')
        request = receipt['request']
        parent = self.client.get(request['library'], job['parentKey'], trashed=True)
        require(match_identity(parent['data'], request['identity']) is None, 'identity_readback_failed')
        require(set(job.get('collections', [])) <= set(parent['data'].get('collections', [])),
                'collection_readback_failed')
        pdf = request.get('pdf') or request.get('reuse_pdf')
        if receipt['kind'] == 'archive' and pdf:
            key = job.get('attachment', {}).get('key')
            child = self.client.get(request['library'], key, children=False)
            require(child['data'].get('parentItem') == parent['key'] and not child['data'].get('deleted'),
                    'attachment_readback_failed')
            receipt['pdf_verification'] = inspect_pdf(file_path(self.client, request['library'], key), pdf['sha256'])
        if receipt['kind'] == 'prune':
            for key in job.get('trashed', []):
                require(self.client.get(request['library'], key, children=False)['data'].get('deleted'),
                        'trash_readback_failed')
            keep = self.client.get(request['library'], request['keep']['key'], children=False)
            require(not keep['data'].get('deleted'), 'keep_readback_failed')
            inspect_pdf(file_path(self.client, request['library'], keep['key']), request['keep']['sha256'])
        receipt.update(state='completed', readback_verified=True)
        receipt.pop('error', None)
        receipt['legacy_preferences_not_modified'] = True
        return receipt

    def reconcile(self, receipt):
        require(receipt['connection'] == self.client.binding, 'operation_connection_mismatch')
        self.client.api.bind(receipt.get('database_id'))
        try:
            if receipt.get('executor_version') != 2:
                self.verify_legacy(receipt)
            else:
                Objects(self.client, receipt, lambda: self.store.save(receipt)).execute(create=False)
            receipt.update(state='completed', readback_verified=True)
            receipt.pop('in_flight', None)
            receipt.pop('error', None)
            self.verify_pdf(receipt)
        except LibraryError as error:
            no_writes = (receipt.get('executor_version') == 2 and
                         receipt.get('native', {}).get('contentWritesStarted') is False and
                         not receipt.get('api_stages') and not receipt.get('in_flight'))
            if no_writes:
                receipt['state'] = 'failed'
            elif receipt.get('state') != 'prepared':
                receipt['state'] = 'unknown'
            receipt['readback_verified'] = False
            receipt['error'] = error.code
        self.store.save(receipt)
        return receipt

    def verify_pdf(self, receipt):
        if receipt['kind'] == 'archive' and (receipt['request'].get('pdf') or receipt['request'].get('reuse_pdf')):
            expected = receipt['request'].get('pdf') or receipt['request']['reuse_pdf']
            key = receipt['native']['attachment']['key']
            receipt['pdf_verification'] = inspect_pdf(
                file_path(self.client, receipt['request']['library'], key), expected['sha256'])

    def status(self, operation_id):
        with self.store.lock(operation_id):
            receipt = self.store.read(operation_id)
            require(receipt is not None, 'operation_not_found')
            with Coordination(self.client.api.server_id).lock():
                return self.reconcile(receipt)

    def run(self, request, kind='archive', resume=False, wait=10):
        request = validate(request, kind)
        operation_id, request_hash = self.identify(request, kind)
        with self.store.lock(operation_id), Coordination(self.client.api.server_id).lock():
            receipt = self.store.read(operation_id)
            if receipt:
                require(receipt['request_hash'] == request_hash and receipt['kind'] == kind,
                        'operation_request_conflict')
                require(receipt['connection'] == self.client.binding, 'operation_connection_mismatch')
                self.client.api.bind(receipt.get('database_id'))
                if receipt['state'] == 'completed' or receipt.get('in_flight'):
                    receipt = self.reconcile(receipt)
                    if receipt['state'] == 'completed':
                        Coordination(self.client.api.server_id).finish(receipt, self.store)
                        return receipt
                if receipt.get('executor_version') != 2:
                    attempts = receipt.get('attempts', [])
                    if attempts and not all(x.get('rejected') for x in attempts):
                        receipt = self.reconcile(receipt)
                        if receipt['state'] == 'completed':
                            return receipt
                        if not legacy_process_ended(attempts):
                            receipt.update(state='unknown', error='legacy_original_process_unresolved')
                            self.store.save(receipt)
                            return receipt
                        # Persisted fixed keys are required to resume an old dispatched import.
                        if not receipt.get('api_keys') or not receipt.get('database_id'):
                            receipt.update(state='unknown', error='legacy_fixed_keys_unavailable')
                            self.store.save(receipt)
                            return receipt
                    # Old numeric collection IDs cannot verify preservation over this API.
                    baseline = receipt.get('protection_baseline', {}).get('snapshot')
                    if baseline and any(not isinstance(x, str) for x in baseline.get('collections', [])):
                        receipt.update(state='unknown', error='legacy_collection_baseline_unverifiable')
                        self.store.save(receipt)
                        return receipt
                    receipt['legacy_migrated'] = True
                    receipt['executor_version'] = 2
                    receipt.setdefault('api_keys', api_keys(operation_id, receipt['request']))
                    receipt.setdefault('database_id', self.client.api.server_id)
                if receipt['state'] != 'prepared' and not resume:
                    return receipt
            else:
                receipt = {'schema': 1, 'executor_version': 2, 'operation_id': operation_id,
                    'request_hash': request_hash, 'input_request': copy.deepcopy(request),
                    'request': request, 'kind': kind, 'connection': self.client.binding,
                    'database_id': self.client.api.server_id, 'backend': 'local_api',
                    'api_keys': api_keys(operation_id, request), 'state': 'prepared', 'attempts': []}
                self.store.save(receipt)
            coordinate = Coordination(receipt['database_id'])
            try:
                self.client.prepare(receipt['request'])
                pdf = receipt['request'].get('pdf')
                if pdf:
                    pdf['sha256'] = inspect_pdf(pdf['path'], pdf.get('sha256'))['sha256']
                self.store.save(receipt)
                coordinate.reserve(receipt, self.store)
                receipt['state'] = 'dispatched'
                receipt['attempts'].append({'id': str(uuid.uuid5(uuid.UUID(operation_id),
                                           str(len(receipt['attempts'])))), 'executor_version': 2})
                receipt.pop('error', None)
                self.store.save(receipt)
                Objects(self.client, receipt, lambda: self.store.save(receipt)).execute()
                self.verify_pdf(receipt)
                receipt.update(state='completed', readback_verified=True)
                receipt.pop('in_flight', None)
                self.store.save(receipt)
                coordinate.finish(receipt, self.store)
            except LibraryError as error:
                unknown = error.code in {'local_api_result_unknown', 'invalid_local_api_response',
                    'database_identity_changed', 'trash_restore_unknown', 'prune_concurrent_change'} or bool(receipt.get('in_flight'))
                # A definite rejection has no in-flight server write to reconcile.
                if error.code in {'local_api_authorization_required', 'local_api_authorization_denied',
                    'local_api_version_conflict', 'local_api_conflict', 'local_api_request_rejected',
                    'local_api_batch_rejected', 'local_api_authorization_rate_limited'}:
                    receipt.pop('in_flight', None)
                    unknown = False
                receipt.update(state='unknown' if unknown else 'failed', error=error.code, readback_verified=False)
                receipt.setdefault('native', {}).update(status=receipt['state'], error=error.code)
                self.store.save(receipt)
                if not unknown:
                    coordinate.finish(receipt, self.store)
            return receipt

    def resume(self, operation_id, wait=10):
        receipt = self.store.read(operation_id)
        require(receipt is not None, 'operation_not_found')
        return self.run(receipt['input_request'], receipt['kind'], resume=True, wait=wait)


def summary(receipt):
    return {key: receipt[key] for key in ('operation_id', 'kind', 'state', 'error', 'native',
        'backend', 'executor_version', 'api_stages', 'readback_verified', 'pdf_verification') if key in receipt}


def api_keys(operation_id, request):
    """Durable create keys. Installation paths never enter operation identity."""
    alphabet = '23456789ABCDEFGHIJKLMNPQRSTUVWXYZ'
    def make(role):
        value = digest({'operation': operation_id, 'role': role})
        return ''.join(alphabet[int(value[i:i+2], 16) % len(alphabet)] for i in range(0, 16, 2))
    paths = []
    for target in request.get('collections', []):
        for length in range(1, len(target.get('path', [])) + 1):
            path = target['path'][:length]
            if not any(row['path'] == path for row in paths):
                paths.append({'path': path, 'key': make(['collection', path])})
    return {'parent': make('parent'), 'attachment': make('attachment'), 'collections': paths}
