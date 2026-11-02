"""Conservative identity rules shared by requests, reads and persisted readback."""
import re
import unicodedata


def normalize_doi(value):
    value = str(value or '').strip()
    value = re.sub(r'^doi:\s*', '', value, flags=re.I)
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value, flags=re.I)
    return value.strip().lower()


def normalize_text(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).split()).lower()


def year(value):
    match = re.search(r'\b[12][0-9]{3}\b', str(value or ''))
    return match.group(0) if match else normalize_text(value)


def creators(value):
    return [(x.get('creatorType', 'author'), normalize_text(x.get('name') or
        ((x.get('firstName') or '') + ' ' + (x.get('lastName') or '')))) for x in value or []]


def match_identity(data, identity):
    if data.get('itemType') in {'attachment', 'note', 'annotation'} or data.get('deleted') or data.get('parentItem'):
        return 'parent_not_regular'
    if normalize_text(data.get('title')) != normalize_text(identity['title']):
        return 'title_conflict'
    wanted, stored = normalize_doi(identity.get('doi')), normalize_doi(data.get('DOI'))
    if wanted and stored and wanted != stored:
        return 'doi_conflict'
    if identity.get('date') and year(data.get('date')) != year(identity['date']):
        return 'date_conflict' if data.get('date') else 'identity_evidence_insufficient'
    if identity.get('creators') and creators(data.get('creators')) != creators(identity['creators']):
        return 'creators_conflict' if data.get('creators') else 'identity_evidence_insufficient'
    if wanted and stored:
        return None
    same_url = bool(identity.get('url') and str(data.get('url', '')).strip() == identity['url'].strip())
    same_people_year = bool(identity.get('creators') and identity.get('date')
        and creators(data.get('creators')) == creators(identity['creators'])
        and year(data.get('date')) == year(identity['date']))
    return None if same_url or same_people_year else 'identity_evidence_insufficient'


def related(data, identity):
    return (normalize_text(data.get('title')) == normalize_text(identity['title'])
        or bool(identity.get('doi') and normalize_doi(data.get('DOI')) == normalize_doi(identity['doi']))
        or bool(identity.get('creators') and identity.get('date')
            and creators(data.get('creators')) == creators(identity['creators'])
            and year(data.get('date')) == year(identity['date'])))
