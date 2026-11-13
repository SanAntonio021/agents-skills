"""Read-only file and reading-content checks; never changes plugin preferences."""
import json

from .errors import LibraryError
from .files import file_hash, inspect_pdf
from .identity import match_identity
from .reading import file_path, plain
from .request import require


def stable(data, parent=False, trashed=False):
    ignored = {'version', 'dateModified'}
    if parent:
        ignored.add('collections')
    if trashed:
        ignored.add('deleted')
    if not data.get('deleted'):
        ignored.add('deleted')
    return {k: v for k, v in data.items() if k not in ignored}


def snapshot(client, library, parent, placeholder=None):
    if parent is None:
        return None
    parent = client.get(library, parent['key'], trashed=True)
    rows = []
    for child in parent['children']:
        data = child['data']
        row = {'key': child['key'], 'data': data}
        if data.get('itemType') == 'attachment':
            row['annotations'] = [x['data'] for x in child.get('children', [])]
            if data.get('linkMode') != 'linked_url':
                try:
                    row['hash'] = file_hash(file_path(client, library, child['key']))
                except LibraryError:
                    if child['key'] == placeholder:
                        continue
                    raise LibraryError('existing_attachment_state_unknown') from None
        rows.append(row)
    return {'parent': parent['data'], 'collections': parent['data'].get('collections', []),
            'children': rows}


def confirm(client, library, parent_key, baseline, trashed=(), expected_tags=None):
    if not baseline:
        return []
    current = client.get(library, parent_key, trashed=True)
    old_parent = baseline['parent']
    if isinstance(old_parent, str):
        old_parent = json.loads(old_parent)
    if expected_tags is not None:
        old_parent = dict(old_parent, tags=expected_tags)
    require(stable(current['data'], parent=True) == stable(old_parent, parent=True),
            'protected_parent_changed')
    # Old native snapshots used collection IDs. The old parent JSON, when
    # available, is authoritative for keys; numeric IDs cannot be guessed.
    old_collections = baseline.get('collections', [])
    if any(not isinstance(x, str) for x in old_collections):
        require('collections' in old_parent, 'legacy_collection_baseline_unverifiable')
        old_collections = old_parent['collections']
    require(set(old_collections) <= set(current['data'].get('collections', [])),
            'original_collection_lost')
    children = {x['key']: x for x in current['children']}
    for row in baseline.get('children', []):
        child = children.get(row['key'])
        require(child is not None, 'protected_reading_content_missing')
        old = json.loads(row['data']) if isinstance(row['data'], str) else row['data']
        require(stable(child['data'], trashed=row['key'] in trashed) ==
                stable(old, trashed=row['key'] in trashed), 'protected_reading_content_changed')
        if row.get('hash'):
            require(file_hash(file_path(client, library, row['key'])) == row['hash'],
                    'protected_file_changed')
        if 'annotations' in row:
            annotations = row['annotations']
            if isinstance(annotations, str):
                annotations = json.loads(annotations)
            require([stable(x['data']) for x in child.get('children', [])] ==
                    [stable(x) for x in annotations], 'protected_annotations_changed')
    return [key for key in children if key not in {x['key'] for x in baseline.get('children', [])}]


def candidate_state(client, request, candidate):
    """Unknown checks raise; the caller preserves that candidate."""
    library = request['library']
    parent = client.get(library, request['parent_key'], trashed=True)
    require(match_identity(parent['data'], request['identity']) is None, 'identity_conflict')
    item = client.get(library, candidate['key'], trashed=True)
    keep = client.get(library, request['keep']['key'], trashed=True)
    for value in (item, keep):
        data = value['data']
        require(data.get('itemType') == 'attachment' and data.get('parentItem') == parent['key']
                and data.get('contentType') == 'application/pdf', 'attachment_parent_mismatch')
    require(not keep['data'].get('deleted'), 'keep_trashed')
    inspect_pdf(file_path(client, library, keep['key']), request['keep']['sha256'])
    pdf = inspect_pdf(file_path(client, library, item['key']), candidate['sha256'])
    require(not pdf['embedded_annotations'], 'candidate_has_embedded_annotations')
    require(not item.get('children'), 'candidate_has_annotations_or_notes')
    require(not plain(item['data'].get('note', '')).strip(), 'candidate_has_attachment_note')
    require(not any(x['data'].get('itemType') == 'note' and
                    not x['data'].get('deleted') for x in parent['children']), 'parent_has_notes')
    notes = client.list_all(client.prefix(library) + '/items', {'itemType': 'note'})
    require(not any(candidate['key'].lower() in json.dumps(x['data']).lower()
                    for x in notes), 'candidate_has_linked_notes')
    return {'item': item, 'parent': parent, 'keep': keep, 'notes': notes}
