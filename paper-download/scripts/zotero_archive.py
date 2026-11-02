"""Download business boundary: verify the PDF and correct only assistant handoffs."""
import argparse
import copy
import json
import sys
from pathlib import Path

from institutional_access.finalize import shared_modules


def prepare_handoff(executor, request, key_source='user', required_version=None):
    shared_modules()
    from zotero_library.request import validate, require, VERSIONS
    from institutional_access.pdf_tools import validate_pdf_bytes
    request = validate(request)
    require(key_source in {'assistant', 'user'}, 'invalid_parent_key_source')
    pdf = request.get('pdf') or request.get('reuse_pdf')
    require(pdf is not None, 'download_pdf_required')
    if required_version is not None:
        require(required_version in VERSIONS, 'invalid_required_version')
        if pdf['version'] != required_version:
            return {'stage': 'identity_review_required', 'reason': 'pdf_version_mismatch'}
    # File identity belongs here; the shared executor independently verifies bytes and storage.
    if request.get('pdf'):
        try:
            validation = validate_pdf_bytes(Path(pdf['path']).read_bytes(),
                doi=request['identity'].get('doi', ''), title=request['identity']['title'],
                provider_identity_match=True)
        except (OSError, ValueError):
            return {'stage': 'identity_review_required', 'reason': 'pdf_identity_unreadable'}
        if not validation['identity_verified']:
            return {'stage': 'identity_review_required', 'reason': 'pdf_identity_requires_review'}
        require(not pdf.get('sha256') or pdf['sha256'] == validation['sha256'], 'pdf_hash_mismatch')
        # Do not enrich the input: the executor hashes the original request before
        # deriving this SHA. Changing it here would bypass an earlier operation.
    resolved = executor.client.resolve(request)
    if resolved['state'] in {'matched', 'not_found'}:
        # Keep requests without an explicit key stable across retries. Native lookup repeats the check.
        return {'stage': 'ready', 'request': request}
    if not request.get('parent_key') or key_source != 'assistant':
        return {'stage': 'identity_review_required', **resolved}
    # A submitted operation owns its original target, including when its result is unknown.
    existing = executor.existing(request)
    if existing:
        from zotero_library.operations import summary
        existing = executor.status(existing['operation_id'])
        rejected = bool(existing['attempts'] and existing['attempts'][-1].get('rejected'))
        native = existing.get('native', {})
        no_write = existing['state'] == 'failed' and (rejected or
            (native.get('status') == 'failed' and native.get('contentWritesStarted') is False))
        if not no_write:
            return {'stage': 'reconcile_original_operation', 'archive': summary(existing)}
    corrected = copy.deepcopy(request)
    original_key = corrected.pop('parent_key')
    corrected.pop('operation_id', None)  # A corrected target is a different request.
    candidate = executor.client.resolve(corrected)
    if candidate['state'] != 'matched':
        return {'stage': 'identity_review_required', 'reason': 'handoff_target_not_unique',
                'original': resolved, 'resolution': candidate}
    corrected['parent_key'] = candidate['parent_key']
    return {'stage': 'ready', 'request': corrected, 'correction': {
        'original_key': original_key, 'parent_key': candidate['parent_key'],
        'basis': candidate['candidates'],
        **({'original_operation_id': existing['operation_id']} if existing else {})}}


def archive_request(executor, request, key_source='user', required_version=None):
    prepared = prepare_handoff(executor, request, key_source, required_version)
    if prepared['stage'] != 'ready':
        return prepared
    from zotero_library.operations import summary
    receipt = executor.run(prepared['request'])
    return {'stage': 'completed' if receipt['state'] == 'completed' else 'archive_pending',
            'archive': summary(receipt), **({'correction': prepared['correction']} if prepared.get('correction') else {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    parser.add_argument('--parent-key-source', choices=('user', 'assistant'), default='user')
    parser.add_argument('--required-version', choices=('official', 'accepted_manuscript', 'preprint', 'temporary_preprint', 'unresolved'))
    for name in ('profile', 'base-url', 'policy', 'state-dir'):
        parser.add_argument('--' + name)
    parser.add_argument('--timeout', type=float, default=3)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 10:
        parser.error('timeout must be greater than zero and no more than 10')
    try:
        Client, Executor, Store, _, read_request, _ = shared_modules()
        from zotero_library.errors import LibraryError
        result = archive_request(Executor(Client(args.profile, args.base_url, args.timeout, args.policy),
            Store(args.state_dir)), read_request(args.request), args.parent_key_source, args.required_version)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result['stage'] == 'completed' else 2
    except Exception as error:
        print(json.dumps({'error': getattr(error, 'code', 'download_archive_failed')}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
