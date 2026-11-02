"""Archive once through the shared layer, then durably close this browser task."""
import json
import os
import sys
import uuid
from pathlib import Path


def shared_modules():
    root = Path(__file__).resolve().parents[3] / 'zotero-workspace-library' / 'scripts'
    if not (root / 'zotero_library' / 'operations.py').is_file():
        from .cli import OperationError
        raise OperationError('dependency_missing', 'dependency_missing_zotero_library')
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from zotero_library.client import Client
    from zotero_library.operations import Executor, Store, summary
    from zotero_library.request import read_request, digest
    return Client, Executor, Store, summary, read_request, digest


def finalize(args):
    from .cli import OperationError
    try:
        return _finalize(args)
    except OperationError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise OperationError('finalize_failed', 'finalization_receipt_or_request_invalid') from None


def _finalize(args):
    from . import cli
    from .session_store import get_session_store, validate_session_id
    Client, Executor, Store, summary, read_request, digest = shared_modules()
    from zotero_library.errors import LibraryError
    from zotero_library.identity import normalize_doi
    validate_session_id(args.session)
    store = get_session_store()  # Enforce the existing test-backend boundary before any write.
    if not 0 < args.timeout <= 10:
        raise cli.OperationError('invalid_timeout', 'timeout must be greater than zero and no more than 10')
    try:
        request = read_request(args.request)
    except LibraryError as error:
        raise cli.OperationError('archive_request_invalid', error.code) from None
    if not request.get('pdf') and not request.get('reuse_pdf'):
        raise cli.OperationError('archive_request_invalid', 'finalize requires a verified PDF')
    request_hash = digest({'request': request, 'required_version': getattr(args, 'required_version', None),
                           'parent_key_source': getattr(args, 'parent_key_source', 'user')})
    root = Path(os.environ.get('PAPER_DOWNLOAD_TEST_STATE_DIR') or
                Path(os.environ['LOCALAPPDATA']) / 'PaperDownload') / 'finalizations'
    root.mkdir(parents=True, exist_ok=True)
    path = root / (args.session + '.json')
    record = json.loads(path.read_text('utf-8')) if path.is_file() else None
    if record and record['request_hash'] != request_hash:
        raise cli.OperationError('session_conflict', 'finalize request differs from the original')

    def save():
        temporary = path.with_suffix('.' + str(uuid.uuid4()) + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(record, stream, ensure_ascii=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    if record and record.get('stage') == 'completed':
        store.delete(args.session)  # Idempotent cleanup after a crash following receipt commit.
        return record
    session = cli.load_session(store, args.session)
    if request['identity'].get('doi') != normalize_doi(session['doi']):
        raise cli.OperationError('session_conflict', 'archive DOI differs from the downloaded article')
    if not record:
        validation = session.get('validation', {})
        if (session.get('stage') not in {'downloaded_identity_verified', 'downloaded_identity_requires_review'}
                or not session.get('path') or not validation.get('sha256')):
            raise cli.OperationError('download_incomplete', 'resume the original session to obtain a validated PDF before finalize')
        from zotero_library.files import inspect_pdf
        try:
            inspect_pdf(session['path'], validation['sha256'])
        except LibraryError as error:
            raise cli.OperationError('session_conflict', error.code) from None
        if request.get('pdf'):
            if Path(session['path']).resolve() != Path(request['pdf']['path']):
                raise cli.OperationError('session_conflict', 'archive PDF differs from the session output')
        from zotero_archive import prepare_handoff
        try:
            client = Client(args.profile, args.base_url, args.timeout, args.policy)
            prepared = prepare_handoff(Executor(client, Store(args.state_dir)), request,
                getattr(args, 'parent_key_source', 'user'), getattr(args, 'required_version', None))
        except LibraryError as error:
            return {'stage': 'archive_pending', 'error': error.code}
        if prepared['stage'] != 'ready':
            return prepared
        record = {'session': args.session, 'request_hash': request_hash, 'stage': 'archive_pending',
                  'archive_request': prepared['request']}
        if prepared.get('correction'):
            record['correction'] = prepared['correction']
        save()
    if record['stage'] == 'archive_pending':
        try:
            client = Client(args.profile, args.base_url, args.timeout, args.policy)
            executor = Executor(client, Store(args.state_dir))
            receipt = executor.run(record.get('archive_request', request))
        except LibraryError as error:
            return {'stage': 'archive_pending', 'error': error.code}
        record['archive'] = summary(receipt)
        if receipt['state'] != 'completed':
            save()
            return {'stage': 'archive_pending', 'archive': record['archive']}
        record['stage'] = 'archive_completed_closure_pending'
        save()  # The original complete command is retried only after this durable boundary.
    result = cli.complete(args, retain_session=True)
    record['closure'] = result
    if result['stage'] == 'completed':
        record['stage'] = 'completed'
    save()  # Keep the credential session until the final non-credential receipt is durable.
    if record['stage'] == 'completed':
        store.delete(args.session)
    return record
