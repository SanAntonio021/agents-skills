"""Read local PDF pages and search reading content without a separate index service."""
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from .errors import LibraryError
from .request import KEY, require


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []

    def handle_data(self, value):
        self.parts.append(value)


def plain(value):
    parser = Text(); parser.feed(value or '')
    return html.unescape(' '.join(parser.parts))


def file_path(client, library, key):
    require(isinstance(key, str) and KEY.fullmatch(key), 'invalid_item_key')
    raw = client.api.exchange(client.prefix(library) + '/items/' + key + '/file/view/url').strip()
    url = urllib.parse.urlsplit(raw)
    require(url.scheme == 'file' and url.netloc in ('', 'localhost') and not url.query and not url.fragment,
            'attachment_file_not_local')
    path = Path(urllib.request.url2pathname(url.path))
    require(path.is_absolute() and path.is_file(), 'attachment_file_unavailable')
    return path


def page_numbers(spec, count):
    if spec is None:
        return list(range(1, min(count, 10) + 1))
    require(isinstance(spec, str) and re.fullmatch(r'\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*', spec),
            'invalid_page_range')
    out = set()
    for part in spec.split(','):
        start, _, end = part.partition('-')
        first, last = int(start), int(end or start)
        require(1 <= first <= last <= count and last-first < 100, 'invalid_page_range')
        out.update(range(first, last+1))
    require(len(out) <= 100, 'page_range_too_large')
    return sorted(out)


def read_pdf(client, library, key, pages=None, attachment=None, max_chars=30000):
    require(1 <= max_chars <= 1000000, 'invalid_character_limit')
    try:
        from pypdf import PdfReader
    except ImportError:
        raise LibraryError('pdf_dependency_missing') from None
    client.api.bind()
    item = client.get(library, key)
    if item['data']['itemType'] == 'attachment':
        require(not attachment or attachment == key, 'attachment_parent_mismatch')
        chosen = item
    else:
        candidates = [x for x in item.get('children', []) if
                      x['data'].get('contentType') == 'application/pdf' and not x['data'].get('deleted')]
        if attachment:
            candidates = [x for x in candidates if x['key'] == attachment]
        require(len(candidates) == 1, 'pdf_attachment_selection_required')
        chosen = candidates[0]
    require(chosen['data'].get('contentType') == 'application/pdf', 'not_pdf_attachment')
    path = file_path(client, library, chosen['key'])
    require(path.stat().st_size <= 209715200, 'pdf_too_large')
    try:
        reader = PdfReader(path, strict=False)
        require(not reader.is_encrypted, 'pdf_encrypted')
        count = len(reader.pages)
        selected = page_numbers(pages, count)
        labels = reader.page_labels
        rows, remaining = [], max_chars
        for number in selected:
            text = reader.pages[number-1].extract_text() or ''
            rows.append({'page': number, 'page_label': labels[number-1],
                         'text': text[:remaining], 'truncated': len(text) > remaining,
                         'needs_ocr': not text.strip()})
            remaining = max(0, remaining-len(text))
    except LibraryError:
        raise
    except Exception:
        raise LibraryError('pdf_read_failed') from None
    parent_key = chosen['data'].get('parentItem')
    parent = client.get(library, parent_key, children=False) if parent_key else chosen
    return {'parent': {'key': parent['key'], 'title': parent['data'].get('title')},
            'attachment': {'key': chosen['key'], 'title': chosen['data'].get('title')},
            'total_pages': count, 'pages': rows, 'remaining_pages': count-len(rows),
            'state': 'ocr_required' if rows and all(x['needs_ocr'] for x in rows) else 'read',
            'complete_document': len(rows) == count and not any(x['truncated'] or x['needs_ocr'] for x in rows)}


def search(client, library, query, scope='all', limit=100):
    require(isinstance(query, str) and query.strip(), 'empty_search_query')
    require(1 <= limit <= 1000, 'invalid_search_limit')
    client.api.bind()
    if scope == 'fulltext':
        rows = client.find(library, query=query)
        return {'scope': scope, 'results': rows[:limit], 'truncated': len(rows) > limit,
                'coverage': 'Zotero indexed content; unindexed pages are not searched'}
    require(scope in ('all', 'notes', 'annotations'), 'invalid_search_scope')
    cache = {}
    def get(key):
        if key not in cache:
            cache[key] = client.get(library, key, children=False)
        return cache[key]
    out = []
    for kind in ('note', 'annotation'):
        if (scope == 'notes' and kind != 'note') or (scope == 'annotations' and kind != 'annotation'):
            continue
        for item in client.list_all(client.prefix(library) + '/items', {'itemType': kind}):
            data = item['data']
            if data.get('deleted') or data.get('itemType') != kind:
                continue
            text = plain(data.get('note')) if kind == 'note' else '\n'.join(
                str(data.get(k) or '') for k in ('annotationText', 'annotationComment'))
            haystack = text + ' ' + ' '.join(t.get('tag', '') for t in data.get('tags', []))
            if query.casefold() not in haystack.casefold():
                continue
            owner_key = data.get('parentItem')
            owner = get(owner_key) if owner_key else item
            attachment = owner if owner['data'].get('itemType') == 'attachment' else None
            parent = get(owner['data']['parentItem']) if attachment and owner['data'].get('parentItem') else owner
            position = data.get('annotationPosition') or '{}'
            try:
                position = json.loads(position) if isinstance(position, str) else position
            except ValueError:
                position = {}
            page_index = position.get('pageIndex') if isinstance(position, dict) else None
            out.append({'key': item['key'], 'type': kind, 'text': text,
                'parent': {'key': parent['key'], 'title': parent['data'].get('title')},
                'attachment': {'key': attachment['key'], 'title': attachment['data'].get('title')} if attachment else None,
                'page': page_index+1 if isinstance(page_index, int) and page_index >= 0 else None,
                'page_label': data.get('annotationPageLabel') or None})
    return {'scope': scope, 'results': out[:limit], 'truncated': len(out) > limit}
