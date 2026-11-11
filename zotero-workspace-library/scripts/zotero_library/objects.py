"""Official API object operations, imported PDF uploads and conditional recycling."""
import copy
import hashlib
from pathlib import Path

from .errors import LibraryError
from .files import inspect_pdf
from .identity import match_identity
from .protection import candidate_state, confirm, snapshot
from .reading import file_path
from .request import require


def validate_collection_target(rows, key, name, parent):
    by_key = {row['key']: row for row in rows}
    require(key in by_key, 'collection_not_found')
    if parent is not False:
        require(parent in by_key, 'collection_parent_not_found')
        seen = set()
        cursor = parent
        while cursor is not False:
            require(cursor != key, 'collection_cycle')
            require(cursor not in seen, 'collection_hierarchy_invalid')
            seen.add(cursor)
            row = by_key.get(cursor)
            require(row is not None, 'collection_parent_not_found')
            cursor = row['data'].get('parentCollection') or False
    for row in rows:
        if row['key'] == key:
            continue
        if row['data'].get('name') == name and (row['data'].get('parentCollection') or False) == parent:
            raise LibraryError('collection_name_conflict')
    return by_key[key]


def inspect_collection_update(client, request):
    library = request['library']
    rows = client.collections(library)
    by_key = {row['key']: row for row in rows}
    current = by_key.get(request['key'])
    require(current is not None, 'collection_not_found')
    data = current['data']
    current_parent = data.get('parentCollection') or False
    target_name = request.get('name', data.get('name'))
    target_parent = request.get('parentCollection', current_parent)
    validate_collection_target(rows, current['key'], target_name, target_parent)
    already_current = data.get('name') == target_name and current_parent == target_parent
    if not already_current:
        require(current['version'] == request['expected_version'] and
                data.get('name') == request['expected_name'] and
                current_parent == request['expected_parent'],
                'collection_state_changed_requires_review')
    return {'current': current, 'name': target_name, 'parent': target_parent,
            'already_current': already_current}


def plan_collection_update(client, request):
    plan = inspect_collection_update(client, request)
    current = plan['current']
    return {
        'state': 'already_current' if plan['already_current'] else 'ready',
        'write_required': not plan['already_current'],
        'collection': {
            'key': current['key'],
            'before': {'version': current['version'], 'name': current['data'].get('name'),
                       'parentCollection': current['data'].get('parentCollection') or False},
            'after': {'name': plan['name'], 'parentCollection': plan['parent']},
        },
    }


class Objects:
    def __init__(self, client, receipt, save):
        self.client, self.receipt, self.save = client, receipt, save
        self.request = receipt['request']
        self.library = self.request['library']
        self.prefix = client.prefix(self.library)
        self.result = receipt.setdefault('native', {})
        self.result.update(requestHash=receipt['request_hash'], preferenceRecovery=[])
        self.result.setdefault('contentWritesStarted', False)
        self.result.setdefault('collections', [])
        self.result.setdefault('trashed', [])
        self.result.setdefault('skipped', [])

    def mutate(self, stage, path, method='POST', **kwargs):
        record = {'name': stage, 'state': 'intent'}
        self.receipt.setdefault('api_stages', []).append(record)
        self.receipt['in_flight'] = stage
        self.result['contentWritesStarted'] = True
        self.save()
        result = self.client.api.json(path, method=method, authorize=True, **kwargs)
        if isinstance(result, dict) and result.get('failed'):
            failures = list(result['failed'].values())
            code = failures[0].get('code') if failures else None
            raise LibraryError('local_api_version_conflict' if code == 412 else 'local_api_batch_rejected')
        record['state'] = 'confirmed'
        self.receipt.pop('in_flight', None)
        self.save()
        return result

    def lookup(self, key):
        try:
            return self.client.get(self.library, key, children=False)
        except LibraryError as error:
            if error.code != 'local_api_not_found':
                raise
            return None

    def parent(self):
        key = self.result.get('parentKey') or self.receipt['api_keys']['parent']
        item = self.lookup(key)
        if item:
            require(self.client.identity_reason(self.request, item) is None, 'identity_conflict')
            return item
        resolved = self.client.resolve(self.request)
        if resolved.get('distinct_candidates'):
            self.result['distinctCandidates'] = resolved['distinct_candidates']
        require(resolved['state'] != 'review_required', resolved.get('reason') or 'identity_conflict')
        return self.lookup(resolved['parent_key']) if resolved['state'] == 'matched' else None

    def collection_keys(self, create):
        targets = []
        for target in self.request.get('collections', []):
            rows = self.client.collections(self.library)
            if 'key' in target:
                require(any(x['key'] == target['key'] for x in rows), 'collection_not_found')
                targets.append(target['key'])
                continue
            parent = False
            for index, name in enumerate(target['path']):
                matches = [x for x in rows if x['data'].get('name') == name
                    and (x['data'].get('parentCollection') or False) == parent]
                require(len(matches) <= 1, 'ambiguous_collection_path')
                if not matches:
                    require(create, 'collection_readback_failed')
                    key = next(x['key'] for x in self.receipt['api_keys']['collections']
                               if x['path'] == target['path'][:index+1])
                    require(not any(x['key'] == key for x in rows), 'fixed_collection_key_conflict')
                    self.mutate('collection:' + key, self.prefix + '/collections',
                                body=[{'key': key, 'version': 0, 'name': name, 'parentCollection': parent}])
                    rows = self.client.collections(self.library)
                    matches = [x for x in rows if x['key'] == key and
                        x['data'].get('name') == name and
                        (x['data'].get('parentCollection') or False) == parent]
                    require(len(matches) == 1, 'collection_readback_failed')
                parent = matches[0]['key']
            targets.append(parent)
        return sorted(set(targets))

    def check_source(self):
        pdf = self.request['pdf']
        inspect_pdf(pdf['path'], pdf['sha256'])
        raw = Path(pdf['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == pdf['sha256'], 'pdf_hash_mismatch')
        return raw

    def upload(self, item):
        key = item['key']
        raw = self.check_source()
        endpoint = self.prefix + '/items/' + key + '/file'
        headers = {'If-None-Match': '*'}
        form = {'md5': hashlib.md5(raw).hexdigest(), 'filename': 'document.pdf',
                'filesize': len(raw), 'mtime': int(Path(self.request['pdf']['path']).stat().st_mtime*1000),
                'contentType': 'application/pdf'}
        upload = self.mutate('upload_prepare:' + key, endpoint, form=form, headers=headers)
        if not upload.get('exists'):
            require(isinstance(upload.get('uploadKey'), str), 'invalid_upload_response')
            upload_path = self.client.api.upload_path(upload.get('url', ''))
            # Ephemeral upload address and uploadKey are never persisted.
            self.receipt['in_flight'] = 'upload_bytes:' + key
            self.save()
            self.client.api.exchange(upload_path, method='POST', binary=raw)
            self.receipt.pop('in_flight', None)
            self.save()
            self.check_source()
            self.mutate('upload_register:' + key, endpoint, form={'upload': upload['uploadKey']},
                        headers=headers)
        inspect_pdf(file_path(self.client, self.library, key), self.request['pdf']['sha256'])

    def attachment(self, parent, create):
        requested = self.request.get('pdf') or self.request.get('reuse_pdf')
        if not requested:
            return None
        if 'reuse_pdf' in self.request:
            item = self.lookup(requested['key'])
            require(item and item['data'].get('parentItem') == parent['key'] and
                    not item['data'].get('deleted'), 'reuse_pdf_state_unknown')
            inspect_pdf(file_path(self.client, self.library, item['key']), requested['sha256'])
            return {'key': item['key'], 'reused': True}
        self.check_source() if create else None
        children = self.client.get(self.library, parent['key'], trashed=True)['children']
        fixed = self.receipt['api_keys']['attachment']
        placeholder = None
        for item in children:
            data = item['data']
            if data.get('deleted') or data.get('itemType') != 'attachment':
                continue
            if data.get('contentType') != 'application/pdf':
                continue
            try:
                path = file_path(self.client, self.library, item['key'])
            except LibraryError:
                if item['key'] == fixed:
                    placeholder = item
                    continue
                raise LibraryError('existing_attachment_state_unknown') from None
            # A readable different PDF is preserved; it is not inferred redundant.
            result = inspect_pdf(path)
            if result['sha256'] == requested['sha256']:
                return {'key': item['key'], 'reused': item['key'] != fixed}
            require(item['key'] != fixed, 'fixed_attachment_file_conflict')
        require(create, 'attachment_readback_failed')
        if not placeholder:
            require(self.lookup(fixed) is None, 'fixed_attachment_key_conflict')
            self.mutate('attachment:' + fixed, self.prefix + '/items', body=[{
                'key': fixed, 'version': 0, 'itemType': 'attachment', 'parentItem': parent['key'],
                'title': 'PDF', 'linkMode': 'imported_file', 'contentType': 'application/pdf',
                'filename': 'document.pdf'}])
            placeholder = self.lookup(fixed)
        require(placeholder and placeholder['data'].get('parentItem') == parent['key'],
                'attachment_parent_mismatch')
        self.upload(placeholder)
        return {'key': fixed, 'reused': False}

    def archive(self, create):
        parent = self.parent()
        if 'protection_baseline' not in self.receipt:
            require(create, 'legacy_protection_baseline_missing')
            self.receipt['protection_baseline'] = {
                'parentKey': parent['key'] if parent else None,
                'snapshot': snapshot(self.client, self.library, parent)}
            self.save()
        baseline = self.receipt['protection_baseline']
        if baseline.get('parentKey'):
            require(parent and parent['key'] == baseline['parentKey'], 'protected_parent_changed')
            confirm(self.client, self.library, parent['key'], baseline.get('snapshot'))
        if not parent:
            require(create, 'parent_readback_failed')
            data = copy.deepcopy(self.request.get('metadata', {}))
            data.setdefault('itemType', 'document')
            for field, name in [('title', 'title'), ('doi', 'DOI'), ('date', 'date'), ('url', 'url'),
                                ('creators', 'creators')]:
                if field in self.request['identity']:
                    data[name] = self.request['identity'][field]
            data.update(key=self.receipt['api_keys']['parent'], version=0)
            self.mutate('parent:' + data['key'], self.prefix + '/items', body=[data])
            parent = self.lookup(data['key'])
            require(parent is not None, 'parent_readback_failed')
        self.result['parentKey'] = parent['key']
        self.save()
        target_keys = self.collection_keys(create)
        current = self.lookup(parent['key'])
        require(self.client.identity_reason(self.request, current) is None, 'identity_conflict')
        union = sorted(set(target_keys) | set(current['data'].get('collections', [])))
        if set(union) != set(current['data'].get('collections', [])):
            require(create, 'collection_readback_failed')
            self.mutate('membership:' + parent['key'], self.prefix + '/items/' + parent['key'],
                        method='PATCH', body={'collections': union},
                        headers={'If-Unmodified-Since-Version': str(current['version'])})
        self.result['collections'] = target_keys
        self.save()
        self.result['attachment'] = self.attachment(parent, create)
        fresh = self.client.get(self.library, parent['key'], trashed=True)
        require(self.client.identity_reason(self.request, fresh) is None, 'identity_readback_failed')
        require(set(target_keys) <= set(fresh['data'].get('collections', [])), 'collection_readback_failed')
        external = confirm(self.client, self.library, parent['key'], baseline.get('snapshot'))
        if baseline.get('snapshot') is None:
            external = [child['key'] for child in fresh['children']]
        own = self.receipt['api_keys']['attachment']
        self.result['external_children_preserved'] = [x for x in external if x != own]
        self.result.update(verified=True, preserved=True, status='completed', error=None)
        return self.result

    def library_version(self):
        self.client.read(self.prefix + '/items', {'limit': 1})
        value = next((v for k, v in self.client.api.last_headers.items()
                      if k.lower() == 'last-modified-version'), None)
        require(value is not None and str(value).isdigit(), 'library_version_unavailable')
        return int(value)

    def checked_candidate(self, candidate):
        version = self.library_version()
        result = candidate_state(self.client, self.request, candidate)
        require(self.library_version() == version, 'prune_concurrent_change')
        return result, version

    def prune(self, create):
        self.result['parentKey'] = self.request['parent_key']
        self.result['collections'] = []
        parent = self.client.get(self.library, self.request['parent_key'], trashed=True)
        require(match_identity(parent['data'], self.request['identity']) is None, 'identity_conflict')
        if 'protection_baseline' not in self.receipt:
            require(create, 'legacy_protection_baseline_missing')
            self.receipt['protection_baseline'] = {'parentKey': parent['key'],
                'snapshot': snapshot(self.client, self.library, parent)}
            self.save()
        baseline = self.receipt['protection_baseline']['snapshot']
        for candidate in self.request['candidates']:
            key = candidate['key']
            action = self.receipt.setdefault('prune_actions', {}).get(key)
            item = self.lookup(key)
            if action and item and item['data'].get('deleted'):
                try:
                    require(item['version'] == action['expected_version'],
                            'trash_result_changed_requires_review')
                    self.checked_candidate(candidate)
                    confirm(self.client, self.library, parent['key'], baseline,
                            self.result['trashed'] + [key])
                except LibraryError:
                    if create and action.get('write_confirmed'):
                        self.restore(key, item)
                    raise
                if key not in self.result['trashed']:
                    self.result['trashed'].append(key)
                self.save()
                continue
            if not create:
                require(key in self.result['trashed'] or any(x.get('key') == key for x in
                        self.result['skipped']), 'prune_result_not_confirmed')
                continue
            self.result['skipped'] = [x for x in self.result['skipped'] if x.get('key') != key]
            try:
                state, version = self.checked_candidate(candidate)
                require(not state['item']['data'].get('deleted'), 'candidate_already_trashed')
                confirm(self.client, self.library, parent['key'], baseline, self.result['trashed'])
            except LibraryError as error:
                self.result['skipped'].append({'key': key, 'reason': error.code})
                continue
            before = state['item']['version']
            self.receipt['prune_actions'][key] = {'before_version': before,
                                                 'expected_version': version + 1}
            self.save()
            self.mutate('trash:' + key, self.prefix + '/items', body=[{
                'key': key, 'version': before, 'deleted': True}],
                headers={'If-Unmodified-Since-Version': str(version)})
            self.receipt['prune_actions'][key]['write_confirmed'] = True
            self.save()
            current = self.lookup(key)
            try:
                require(current and current['data'].get('deleted') and
                        current['version'] == version + 1, 'trash_readback_failed')
                self.checked_candidate(candidate)
                confirm(self.client, self.library, parent['key'], baseline,
                        self.result['trashed'] + [key])
            except LibraryError:
                if current and current['data'].get('deleted'):
                    self.restore(key, current)
                raise
            self.result['trashed'].append(key)
            self.save()
        confirm(self.client, self.library, parent['key'], baseline, self.result['trashed'])
        keep = self.lookup(self.request['keep']['key'])
        require(keep and not keep['data'].get('deleted'), 'keep_readback_failed')
        inspect_pdf(file_path(self.client, self.library, keep['key']), self.request['keep']['sha256'])
        self.result.update(verified=True, preserved=True, status='completed', error=None)
        return self.result

    def restore(self, key, item):
        # Restore only this operation's recycle flag and only the version read.
        try:
            self.mutate('restore:' + key, self.prefix + '/items/' + key, method='PATCH',
                        body={'deleted': False},
                        headers={'If-Unmodified-Since-Version': str(item['version'])})
        except LibraryError:
            raise LibraryError('trash_restore_unknown') from None
        restored = self.lookup(key)
        require(restored and not restored['data'].get('deleted'), 'trash_restore_unknown')
        self.result['trashed'] = [x for x in self.result['trashed'] if x != key]
        self.receipt['prune_actions'].pop(key, None)
        self.save()

    def update_collection(self, create):
        plan = inspect_collection_update(self.client, self.request)
        current = plan['current']
        before = {'version': current['version'], 'name': current['data'].get('name'),
                  'parentCollection': current['data'].get('parentCollection') or False}
        if not plan['already_current']:
            require(create, 'collection_update_not_confirmed')
            library_version = next((value for key, value in self.client.api.last_headers.items()
                                    if key.lower() == 'last-modified-version'), None)
            require(library_version is not None and str(library_version).isdigit(),
                    'library_version_unavailable')
            body = copy.deepcopy(current['data'])
            body.update(key=current['key'], version=current['version'], name=plan['name'],
                        parentCollection=plan['parent'])
            self.mutate('collection_update:' + current['key'], self.prefix + '/collections',
                        body=[body], headers={'If-Unmodified-Since-Version': str(library_version)})
            self.receipt['in_flight'] = 'collection_readback:' + current['key']
            self.save()
            updated = self.client.collection(self.library, current['key'])
            require(updated['data'].get('name') == plan['name'] and
                    (updated['data'].get('parentCollection') or False) == plan['parent'] and
                    updated['version'] > current['version'], 'collection_update_readback_failed')
            rows = self.client.collections(self.library)
            validate_collection_target(rows, current['key'], plan['name'], plan['parent'])
            after = {'version': updated['version'], 'name': updated['data'].get('name'),
                     'parentCollection': updated['data'].get('parentCollection') or False}
            self.receipt.pop('in_flight', None)
            self.save()
            changed = True
        else:
            after = before
            changed = False
        self.result['collectionUpdate'] = {'key': current['key'], 'before': before,
                                           'after': after, 'changed': changed}
        self.result.update(verified=True, status='completed', error=None)
        return self.result

    def execute(self, create=True):
        if self.receipt['kind'] == 'archive':
            return self.archive(create)
        if self.receipt['kind'] == 'prune':
            return self.prune(create)
        return self.update_collection(create)
