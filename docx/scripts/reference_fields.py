#!/usr/bin/env python3
"""Build native references and narrowly persist Word-evaluated field results."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile

from lxml import etree

import document_versions as versions
import style_guard as guard

W, M = guard.W, guard.M
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
V = '{urn:schemas-microsoft-com:vml}'
INTERNAL = {'SEQ', 'STYLEREF', 'REF', 'PAGEREF'}
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
NUMBER = r'(?:[A-Za-z]\.)?\d+(?:[.\-]\d+)*[A-Za-z]?'
LABEL = r'(?:Figure|Fig\.|Table|Equation|Eq\.|图|表|公式|式)'
REFERENCE = re.compile(rf'(?P<label>{LABEL})\s*[（(]?(?P<number>{NUMBER})[）)]?', re.I)
CAPTION = re.compile(rf'^(?P<label>Figure|Fig\.|Table|图|表)\s*(?P<number>{NUMBER})(?=\s|[：:])', re.I)
EQUATION = re.compile(rf'[（(](?P<number>{NUMBER})[）)]\s*$')


def xml(payload):
    root = etree.fromstring(payload, etree.XMLParser(resolve_entities=False, no_network=True))
    if root.getroottree().docinfo.doctype:
        raise ValueError('DTD declarations are not supported')
    return root


def normal(code):
    return ' '.join(re.findall(r'"[^"\r\n]*"|[^\s]+', code))


def category(label):
    label = label.lower()
    if label in {'图', 'figure', 'fig.'}:
        return 'figure'
    if label in {'表', 'table'}:
        return 'table'
    return 'equation'


def canonical(node):
    return etree.tostring(node, method='c14n', with_comments=True)


def fallback(node):
    return any(p.tag == MC + 'Fallback' for p in node.iterancestors())


def write_package(package, path):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.comment = package.comment
        for info in package.infos:
            archive.writestr(info, package.entries[info.filename])


def publish(package, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f'Output exists; preserve it: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.reference-', suffix='.docx', dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        write_package(package, temporary)
        guard.DocxPackage.from_path(temporary)
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class Story:
    id: str
    part: str
    node: object
    locator: dict
    twins: list = field(default_factory=list)


@dataclass
class Field:
    story: str
    ordinal: int
    start: object
    instruction_parts: list = field(default_factory=list)
    separator: object = None
    end: object = None
    results: list = field(default_factory=list)
    simple: bool = False
    phase: str = 'code'
    nested: bool = False
    parent: object = None
    unsafe_result: bool = False

    @property
    def instruction(self):
        return normal(''.join(self.instruction_parts))

    @property
    def kind(self):
        return self.instruction.split(' ', 1)[0].upper() if self.instruction else ''

    @property
    def key(self):
        return (self.story, self.ordinal, self.instruction)

    @property
    def text(self):
        return ''.join(t.text or '' for t in self.results)

    @property
    def locked(self):
        return self.start.get(W + 'fldLock', 'false') not in {'0', 'false', 'off'}

    def descriptor(self):
        return dict(story=self.story, ordinal=self.ordinal, instruction=self.instruction,
                    kind=self.kind, locked=self.locked)


def parse_fields(story):
    fields, stack = [], []

    def visit(node):
        if node is not story.node and (node.tag == W + 'txbxContent' or node.tag == MC + 'Fallback'):
            return
        if node.tag in {W + 'footnote', W + 'endnote'} and int(node.get(W + 'id', '1')) <= 0:
            return
        if node.tag == W + 'rPr':
            return
        if node.tag == W + 'fldSimple':
            item = Field(story.id, len(fields), node, [node.get(W + 'instr', '')],
                         simple=True, phase='result', parent=stack[-1] if stack else None)
            if stack:
                stack[-1].nested = True
            fields.append(item)
            stack.append(item)
            for child in node:
                visit(child)
            stack.pop()
            item.end = node
            return
        if node.tag == W + 'fldChar':
            kind = node.get(W + 'fldCharType')
            if kind == 'begin':
                item = Field(story.id, len(fields), node, parent=stack[-1] if stack else None)
                if stack:
                    stack[-1].nested = True
                fields.append(item)
                stack.append(item)
            elif kind == 'separate':
                if not stack or stack[-1].phase != 'code':
                    raise ValueError(f'Malformed field separator in {story.id}')
                stack[-1].separator, stack[-1].phase = node, 'result'
            elif kind == 'end':
                if not stack:
                    raise ValueError(f'Unmatched field end in {story.id}')
                stack.pop().end = node
            return
        if stack:
            item = stack[-1]
            if node.tag == W + 'instrText' and item.phase == 'code':
                item.instruction_parts.append(node.text or '')
            elif item.phase == 'result':
                if node.tag == W + 't':
                    item.results.append(node)
                elif node.tag not in {W + 'r', W + 'bookmarkStart', W + 'bookmarkEnd'}:
                    item.unsafe_result = True
        for child in node:
            visit(child)

    visit(story.node)
    if stack:
        raise ValueError(f'Unclosed field in {story.id}')
    return fields


class Inventory:
    def __init__(self, package):
        if any(p.startswith('_xmlsignatures/') for p in package.entries):
            raise ValueError('Signed documents require a specialized workflow')
        self.package = package
        self.roots = {p: xml(data) for p, data in package.entries.items()
                      if p.startswith('word/') and p.endswith('.xml') and
                      (p == 'word/document.xml' or re.match(r'word/(?:header|footer|footnotes|endnotes)', p))}
        self.stories = []
        self.fields = []
        self.twins = {}
        self.issues = []
        self._stories()
        for story in self.stories:
            fs = parse_fields(story)
            self.fields.extend(fs)
            for twin in story.twins:
                other = parse_fields(Story(story.id, story.part, twin, story.locator))
                if [f.key for f in fs] != [f.key for f in other]:
                    self.issues.append(f'AlternateContent field mismatch in {story.id}')
                else:
                    for a, b in zip(fs, other):
                        self.twins.setdefault(a.key, []).append(b)
                        if b.kind in INTERNAL and (b.locked or b.nested or b.parent is not None or b.unsafe_result):
                            self.issues.append(f'Unsafe AlternateContent fallback field: {b.key}')
        self.bookmarks = {}
        for story in self.stories:
            for node in story.node.iter(W + 'bookmarkStart'):
                if fallback(node) or self._inside_other_box(node, story.node):
                    continue
                name = node.get(W + 'name')
                if name in self.bookmarks:
                    self.issues.append(f'Duplicate bookmark: {name}')
                self.bookmarks[name] = node
                ends = [e for e in story.node.iter(W + 'bookmarkEnd')
                        if not fallback(e) and e.get(W + 'id') == node.get(W + 'id')]
                if len(ends) != 1:
                    self.issues.append(f'Missing/duplicate bookmark end: {name}')
        for f in self.fields:
            if f.kind in INTERNAL:
                if f.locked:
                    self.issues.append(f'Locked field: {f.key}')
                if f.nested or f.parent is not None or f.unsafe_result:
                    self.issues.append(f'Unsupported structured/nested field: {f.key}')
                if not f.simple and f.separator is None:
                    self.issues.append(f'Field has no cached-result separator: {f.key}')
                if f.kind in {'REF', 'PAGEREF'}:
                    tokens = re.findall(r'"[^"]*"|\S+', f.instruction)
                    target = tokens[1].strip('"') if len(tokens) > 1 else ''
                    if target not in self.bookmarks:
                        self.issues.append(f'Missing reference target {target!r}: {f.key}')

    @staticmethod
    def _inside_other_box(node, root):
        for ancestor in node.iterancestors():
            if ancestor is root:
                return False
            if ancestor.tag == W + 'txbxContent':
                return True
        return False

    def _stories(self):
        doc = self.roots['word/document.xml']
        body = doc.find(W + 'body')
        self.stories.append(Story('main', 'word/document.xml', body, {'id': 'main', 'kind': 'main'}))
        rels = {}
        if 'word/_rels/document.xml.rels' in self.package.entries:
            for rel in xml(self.package.entries['word/_rels/document.xml.rels']):
                if rel.get('TargetMode') != 'External':
                    target = rel.get('Target', '')
                    rels[rel.get('Id')] = str(PurePosixPath('word') / target) if not target.startswith('/') else target.lstrip('/')
        seen = set()
        for section, properties in enumerate(doc.iter(W + 'sectPr'), 1):
            for tag in ('header', 'footer'):
                for ref in properties.findall(W + tag + 'Reference'):
                    part = rels.get(ref.get(R + 'id'))
                    if part in seen:
                        continue
                    if part not in self.roots:
                        raise ValueError(f'Missing {tag} part: {part}')
                    seen.add(part)
                    type_ = {'default': 1, 'first': 2, 'even': 3}[ref.get(W + 'type', 'default')]
                    id_ = f'{tag}:{section}:{type_}'
                    self.stories.append(Story(id_, part, self.roots[part],
                                             dict(id=id_, kind=tag, section=section, type=type_)))
        for kind in ('footnotes', 'endnotes'):
            part = f'word/{kind}.xml'
            if part in self.roots:
                self.stories.append(Story(kind, part, self.roots[part], dict(id=kind, kind=kind)))
        for story in list(self.stories):
            for box in story.node.iter(W + 'txbxContent'):
                if fallback(box):
                    continue
                name, alternate = None, None
                for ancestor in box.iterancestors():
                    if ancestor.tag == W + 'drawing':
                        prop = next(ancestor.iter(WP + 'docPr'), None)
                        if prop is not None:
                            name = prop.get('name')
                    if ancestor.tag == V + 'shape' and name is None:
                        name = ancestor.get('id')
                    if ancestor.tag == MC + 'AlternateContent':
                        alternate = ancestor
                        break
                if not name:
                    self.issues.append(f'Text box has no stable shape name in {story.id}')
                    continue
                twins = []
                if alternate is not None:
                    fb = alternate.find(MC + 'Fallback')
                    twins = list(fb.iter(W + 'txbxContent')) if fb is not None else []
                    if len(twins) > 1:
                        self.issues.append(f'Ambiguous fallback text box in {story.id}')
                id_ = f'textbox:{story.id}:{name}'
                self.stories.append(Story(id_, story.part, box, dict(id=id_, kind='textbox', parent=story.id, name=name), twins))

    def updated(self):
        entries = dict(self.package.entries)
        for part, root in self.roots.items():
            if canonical(root) != canonical(xml(self.package.entries[part])):
                entries[part] = guard._serialize_xml(root, self.package.entries[part])
        return guard.DocxPackage(self.package.infos, entries, self.package.comment)

    def require_safe(self):
        if self.issues:
            raise ValueError('; '.join(self.issues))


def set_result(f, text):
    if any(ord(c) < 32 and c not in '\t\n\r' for c in text):
        raise ValueError('Field result contains unsupported control characters')
    if '\n' in text or '\r' in text or '\t' in text:
        raise ValueError('Only single-line textual reference results can be transplanted')
    if f.text == text and f.results:
        pass
    elif f.results:
        f.results[0].text = text
        f.results[0].set(XML_SPACE, 'preserve')
        for node in f.results[1:]:
            node.text = ''
    else:
        run = etree.Element(W + 'r')
        node = etree.SubElement(run, W + 't')
        node.set(XML_SPACE, 'preserve')
        node.text = text
        if f.simple:
            f.start.append(run)
        else:
            end_run = f.end.getparent()
            if end_run.tag != W + 'r':
                raise ValueError('Unsupported empty result container')
            end_run.addprevious(run)
        f.results.append(node)
    f.start.set(W + 'dirty', 'false')


def transplant(baseline, evaluated):
    before, after = Inventory(baseline), Inventory(evaluated)
    before.require_safe()
    after.require_safe()
    if [f.key for f in before.fields] != [f.key for f in after.fields]:
        raise ValueError('Field identity bijection failed after Word save')
    results = []
    for a, b in zip(before.fields, after.fields):
        if a.kind not in INTERNAL:
            if a.text != b.text:
                raise ValueError(f'Unrelated field changed during evaluation: {a.key}')
            continue
        if re.search(r'Error!|错误[!！]|未定义书签|未找到引用源', b.text, re.I):
            raise ValueError(f'Word reported invalid reference: {a.key}: {b.text}')
        set_result(a, b.text)
        for twin in before.twins.get(a.key, []):
            set_result(twin, b.text)
        results.append(dict(a.descriptor(), result=b.text))
    return before.updated(), results


def check_delta(baseline, candidate):
    before, after = Inventory(baseline), Inventory(candidate)
    before.require_safe()
    after.require_safe()
    if [f.key for f in before.fields] != [f.key for f in after.fields]:
        raise ValueError('Field instructions, count or identity changed')
    # Recreate the sole allowed change from the original; compare every package part.
    for a, b in zip(before.fields, after.fields):
        if a.kind in INTERNAL:
            set_result(a, b.text)
            if W + 'dirty' in b.start.attrib:
                a.start.set(W + 'dirty', b.start.get(W + 'dirty'))
            else:
                a.start.attrib.pop(W + 'dirty', None)
            for twin in before.twins.get(a.key, []):
                set_result(twin, b.text)
    expected = before.updated()
    if set(expected.entries) != set(candidate.entries) or expected.comment != candidate.comment:
        raise ValueError('Package members/comment changed')
    for part, value in expected.entries.items():
        actual = candidate.entries[part]
        if part in before.roots:
            if canonical(xml(value)) != canonical(xml(actual)):
                raise ValueError(f'Non-result content changed: {part}')
        elif value != actual:
            raise ValueError(f'Unrelated package part changed: {part}')
    return {'field_result_delta': 'checked', 'unmodified_parts': 'unchanged'}


def visible_spans(paragraph):
    nodes, offset = [], 0
    for node in paragraph.iter(W + 't'):
        inner = []
        for ancestor in node.iterancestors():
            if ancestor is paragraph:
                break
            inner.append(ancestor)
        if any(a.tag in {W + 'txbxContent', W + 'del'} for a in inner):
            continue
        text = node.text or ''
        nodes.append((offset, offset + len(text), node))
        offset += len(text)
    return ''.join(n.text or '' for _, _, n in nodes), nodes


def field_nodes(code, cache, props=None):
    result = []
    for tag, value in [('fldChar', 'begin'), ('instrText', code), ('fldChar', 'separate'), ('t', cache), ('fldChar', 'end')]:
        run = etree.Element(W + 'r')
        if props is not None:
            run.append(copy.deepcopy(props))
        node = etree.SubElement(run, W + tag)
        if tag == 'fldChar':
            node.set(W + 'fldCharType', value)
            if value == 'begin':
                node.set(W + 'dirty', 'true')
        else:
            node.text = value
            node.set(XML_SPACE, 'preserve')
        result.append(run)
    return result


def replace_span(paragraph, start, end, code, cache, bookmark=None, bookmark_id=None):
    _, spans = visible_spans(paragraph)
    involved = [(a, b, n) for a, b, n in spans if a < end and b > start]
    if not involved:
        raise ValueError('Reference span no longer exists')
    first = involved[0][2]
    run = first.getparent()
    if run.tag != W + 'r' or run.getparent() is not paragraph:
        raise ValueError('Reference inside hyperlink/revision needs an explicit specialized edit')
    for _, _, node in involved:
        r = node.getparent()
        if r.getparent() is not paragraph or any(c.tag not in {W + 'rPr', W + 't'} for c in r):
            raise ValueError('Reference overlaps structured run content')
    props = run.find(W + 'rPr')
    prefix = (first.text or '')[:start - involved[0][0]]
    suffix = (involved[-1][2].text or '')[end - involved[-1][0]:]
    first.text = prefix
    for _, _, node in involved[1:]:
        node.text = ''
    nodes = field_nodes(code, cache, props)
    if bookmark:
        begin = etree.Element(W + 'bookmarkStart', {W + 'id': str(bookmark_id), W + 'name': bookmark})
        finish = etree.Element(W + 'bookmarkEnd', {W + 'id': str(bookmark_id)})
        nodes = [begin, *nodes, finish]
    trailing = etree.Element(W + 'r')
    if props is not None:
        trailing.append(copy.deepcopy(props))
    t = etree.SubElement(trailing, W + 't')
    t.text, t.attrib[XML_SPACE] = suffix, 'preserve'
    # Prefix and suffix retain their original run formatting, including split spans.
    last_run = involved[-1][2].getparent()
    if last_run is not run:
        last_props = last_run.find(W + 'rPr')
        old_props = trailing.find(W + 'rPr')
        if old_props is not None:
            trailing.remove(old_props)
        if last_props is not None:
            trailing.insert(0, copy.deepcopy(last_props))
    insert_at = paragraph.index(last_run) + 1
    for node in [*nodes, trailing]:
        paragraph.insert(insert_at, node)
        insert_at += 1


def candidates(inv):
    result = []
    field_text_nodes = {n for f in inv.fields for n in f.results}
    for story in inv.stories:
        for index, p in enumerate(story.node.iter(W + 'p')):
            if inv._inside_other_box(p, story.node) or fallback(p):
                continue
            text, spans = visible_spans(p)
            style = p.find(W + 'pPr/' + W + 'pStyle')
            if style is not None and re.search('code|verbatim|source', style.get(W + 'val', ''), re.I):
                continue
            match = CAPTION.match(text)
            kind = category(match['label']) if match else None
            if not match and any(True for _ in p.iter(M + 'oMath')):
                match, kind = EQUATION.search(text), 'equation'
            if match:
                if re.match(r'\s*(?:shows?\b|gives?\b|illustrates?\b|presents?\b|depicts?\b|给出|所示|表示|展示)', text[match.end():], re.I):
                    continue
                start, end = match.span('number')
                nodes = [n for a, b, n in spans if a < end and b > start]
                existing = next((f for f in inv.fields if any(n in f.results for n in nodes) and f.kind == 'SEQ'), None)
                result.append(dict(story=story, paragraph=p, index=index, kind=kind, number=match['number'],
                                   start=start, end=end, existing=existing,
                                   key=f'{story.id}:p{index}', label=match.groupdict().get('label') or 'Equation'))
    return result, field_text_nodes


def prepare_package(package, *, mode='full', mapping=None):
    inv = Inventory(package)
    inv.require_safe()
    if mode == 'local':
        return package, {'converted_targets': 0, 'converted_references': 0}
    if mode != 'full':
        raise ValueError('mode must be full or local')
    objects, protected = candidates(inv)
    targets, ids, all_refs = {}, [], []
    for root in inv.roots.values():
        ids.extend(int(n.get(W + 'id')) for n in root.iter(W + 'bookmarkStart') if (n.get(W + 'id') or '').isdigit())
    next_id = max(ids, default=0) + 1
    mapping = mapping or {}
    explicit = mapping.get('references', {})
    ignored = set(mapping.get('ignore', []))
    used_explicit, used_ignored = set(), set()
    if set(mapping) - {'references', 'ignore'}:
        raise ValueError('Mapping accepts references and ignore only')
    for obj in objects:
        targets.setdefault((obj['kind'], obj['number']), []).append(obj)
    object_by_key = {o['key']: o for o in objects}
    sequences = {}
    for obj in objects:
        if obj['existing'] is not None:
            tokens = re.findall(r'"[^"]*"|\S+', obj['existing'].instruction)
            if len(tokens) < 2:
                raise ValueError('SEQ field has no sequence identifier')
            sequences.setdefault(obj['kind'], set()).add(tokens[1])
    for story in inv.stories:
        for pi, p in enumerate(story.node.iter(W + 'p')):
            if inv._inside_other_box(p, story.node) or fallback(p):
                continue
            if any(o['paragraph'] is p for o in objects):
                continue
            text, spans = visible_spans(p)
            style = p.find(W + 'pPr/' + W + 'pStyle')
            if style is not None and re.search('code|verbatim|source', style.get(W + 'val', ''), re.I):
                continue
            for match in REFERENCE.finditer(text):
                start, end = match.span('number')
                if any(n in protected for a, b, n in spans if a < end and b > start):
                    continue
                key = f'{story.id}:p{pi}:c{start}'
                if key in ignored:
                    used_ignored.add(key)
                    continue
                choices = targets.get((category(match['label']), match['number']), [])
                chosen = object_by_key.get(explicit[key]) if key in explicit else choices[0] if len(choices) == 1 else None
                if chosen is None:
                    raise ValueError(f'Ambiguous/missing target for {match[0]!r} at {key}; supply explicit mapping or ignore')
                if chosen['kind'] != category(match['label']):
                    raise ValueError(f'Explicit mapping changes the object category at {key}')
                if key in explicit:
                    used_explicit.add(key)
                all_refs.append(dict(paragraph=p, start=start, end=end, target=chosen, cache=match['number']))
                tail = text[match.end():]
                if re.match(r'\s*(?:[-~至到–—～,，、]|及|和|and\b)\s*[（(]?\d', tail):
                    raise ValueError(f'Abbreviated reference range at {key}; expand both endpoint labels before export')
    if set(explicit) != used_explicit or ignored != used_ignored:
        raise ValueError('Mapping contains unused/stale reference locations')
    for obj in objects:
        existing = obj['existing']
        if existing is not None:
            # Use an existing bookmark only if its range exactly contains this number field.
            p = obj['paragraph']
            children = list(p)
            start_run = existing.start if existing.simple else existing.start.getparent()
            end_run = existing.end if existing.simple else existing.end.getparent()
            if start_run.getparent() is not p or end_run.getparent() is not p:
                raise ValueError(f'Unsupported existing caption structure: {obj["key"]}')
            bi, ei = children.index(start_run), children.index(end_run)
            found = None
            for b in children[:bi]:
                if b.tag == W + 'bookmarkStart':
                    for e in children[ei + 1:]:
                        if e.tag == W + 'bookmarkEnd' and e.get(W + 'id') == b.get(W + 'id'):
                            between = children[children.index(b)+1:children.index(e)]
                            text = ''.join(t.text or '' for c in between for t in c.iter(W + 't'))
                            if text == existing.text:
                                found = b.get(W + 'name')
            if found:
                obj['bookmark'] = found
                continue
            name = 'CodexRef_' + uuid.uuid4().hex[:20]
            start_run.addprevious(etree.Element(W + 'bookmarkStart', {W + 'id': str(next_id), W + 'name': name}))
            end_run.addnext(etree.Element(W + 'bookmarkEnd', {W + 'id': str(next_id)}))
        else:
            if not obj['number'].isdigit():
                raise ValueError(f'Plain chapter/appendix numbering needs an explicit native numbering design: {obj["key"]}')
            name = 'CodexRef_' + uuid.uuid4().hex[:20]
            known = sequences.get(obj['kind'], set())
            if len(known) > 1:
                raise ValueError(f'Multiple existing sequence schemes for {obj["kind"]}; resolve numbering explicitly')
            seq = next(iter(known)) if known else {'figure': 'Figure', 'table': 'Table', 'equation': 'Equation'}[obj['kind']]
            replace_span(obj['paragraph'], obj['start'], obj['end'], f' SEQ {seq} \\* ARABIC ', obj['number'], name, next_id)
        obj['bookmark'] = name
        next_id += 1
    for ref in sorted(all_refs, key=lambda r: r['start'], reverse=True):
        replace_span(ref['paragraph'], ref['start'], ref['end'], f' REF {ref["target"]["bookmark"]} \\h ', ref['cache'])
    result = inv.updated()
    Inventory(result).require_safe()
    return result, dict(converted_targets=sum(o['existing'] is None for o in objects), converted_references=len(all_refs))


def inspect_document(source):
    inv = Inventory(guard.DocxPackage.from_path(Path(source)))
    objects, _ = candidates(inv)
    return dict(ok=not inv.issues, status='PASS' if not inv.issues else 'UNVERIFIED',
                source=str(Path(source).resolve()), issues=inv.issues,
                fields=[dict(f.descriptor(), result=f.text) for f in inv.fields],
                literal_references=literal_references(inv),
                targets=[{k: o[k] for k in ('key', 'kind', 'number', 'label')} for o in objects])


def literal_references(inv):
    objects, protected = candidates(inv)
    locations = []
    for story in inv.stories:
        for pi, p in enumerate(story.node.iter(W + 'p')):
            if inv._inside_other_box(p, story.node) or fallback(p) or any(o['paragraph'] is p for o in objects):
                continue
            text, spans = visible_spans(p)
            for match in REFERENCE.finditer(text):
                start, end = match.span('number')
                if not any(n in protected for a, b, n in spans if a < end and b > start):
                    locations.append(dict(location=f'{story.id}:p{pi}:c{start}', text=match[0]))
    return locations


def markdown_inventory(source, pandoc='pandoc'):
    """Read the same Markdown syntax tree as the exporter, without rewriting prose."""
    source = Path(source).resolve()
    run = subprocess.run([str(pandoc), str(source), '--from=markdown', '--to=json'],
                         cwd=source.parent, capture_output=True, text=True, encoding='utf-8', timeout=60)
    if run.returncode:
        raise ValueError(f'Cannot inspect Markdown syntax tree: {run.stderr}')
    ast = json.loads(run.stdout)
    if not isinstance(ast, dict) or 'blocks' not in ast:
        raise ValueError('Pandoc returned no document syntax tree')
    counts = {'images': 0, 'display_equations': 0, 'tables': 0}

    def walk(item):
        if isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, dict):
            kind = item.get('t')
            if kind in {'Code', 'CodeBlock'}:
                return
            if kind == 'Image':
                counts['images'] += 1
            if kind == 'Table':
                counts['tables'] += 1
            if kind == 'Math' and item.get('c', [{}])[0].get('t') == 'DisplayMath':
                counts['display_equations'] += 1
            if kind == 'Cite':
                for cite in item['c'][0]:
                    if re.match(r'(?:fig|tbl|eq)[:_-]', cite.get('citationId', ''), re.I):
                        raise ValueError('Unresolved Markdown object citation; supply the explicit rendered target mapping')
            if 'c' in item:
                walk(item['c'])
    walk(ast['blocks'])
    return dict(source=str(source), parser='pandoc-json', **counts)


def check_files(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    captured = versions.capture_inputs([source, output])
    checks = check_delta(guard.DocxPackage.from_path(source), guard.DocxPackage.from_path(output))
    if versions.changed_files(captured['files']):
        raise ValueError('Files changed during checking')
    return dict(ok=True, status='PASS', source=str(output), source_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                layout='not_checked', **checks)


def finalize(source, output, *, mode='local', allow_office_com=False, mapping=None, record=None, evaluator=None,
             markdown_source=None, pandoc='pandoc', native_checker=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    record = Path(record).resolve() if record else Path(str(output) + '.check.json')
    inputs = versions.capture_inputs([source] + ([Path(markdown_source)] if markdown_source else []))
    versions.protect_output_path(output, inputs)
    versions.protect_record_path(record, output, inputs)
    if output.exists() or record.exists():
        raise ValueError('Output/check record already exists')
    baseline = guard.DocxPackage.from_path(source)
    markdown = markdown_inventory(markdown_source, pandoc) if markdown_source else None
    prepared, construction = prepare_package(baseline, mode=mode, mapping=mapping)
    inv = Inventory(prepared)
    inv.require_safe()
    needed = any(f.kind in INTERNAL for f in inv.fields)
    evidence = {'ok': True, 'status': 'NOT_APPLICABLE', 'engine': None}
    result_package, results = prepared, []
    intermediate = None
    if mode == 'full':
        intermediate = output.with_name(output.stem + '.references-prepared.docx')
        if intermediate == source or intermediate.exists():
            raise ValueError(f'Prepared output exists or is source: {intermediate}')
        publish(prepared, intermediate)
    eval_source = intermediate or source
    if needed:
        if evaluator is None:
            from reference_word import evaluate_copy
            evaluator = evaluate_copy
        with tempfile.TemporaryDirectory(prefix='codex-reference-') as directory:
            evaluated = Path(directory) / 'evaluated.docx'
            try:
                evidence = evaluator(eval_source, evaluated, [f.descriptor() for f in inv.fields],
                                     [s.locator for s in inv.stories], allow_office_com=allow_office_com)
            except Exception as exc:
                evidence = dict(ok=False, status='UNVERIFIED', engine='word', message=str(exc))
            if evidence.get('ok'):
                result_package, results = transplant(prepared, guard.DocxPackage.from_path(evaluated))
                check_delta(prepared, result_package)
    if versions.changed_files(inputs['files']):
        raise ValueError('Source changed during finalization')
    publish(result_package, output)
    published_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    versions.record_generation(output, record, inputs)
    check_baseline = intermediate or source
    checked = versions.run_check(output, record, [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
                                                  'check', str(check_baseline), str(output)], kind='reference-structure', inputs=inputs)
    if not checked.get('ok'):
        return checked
    status = 'PASS' if evidence.get('ok') else 'UNVERIFIED'
    acceptance = {'ok': not needed, 'status': 'NOT_RUN' if needed else 'NOT_APPLICABLE'}
    if needed and evidence.get('ok'):
        if native_checker is None:
            acceptance = versions.run_check(output, record, [sys.executable, '-X', 'utf8',
                str(Path(__file__).with_name('reference_word.py')), 'check', str(output),
                '--allow-office-com'], kind='word-native', inputs=inputs)
        else:
            acceptance = native_checker(output, 'docx', allow_office_com=allow_office_com, require_render=False)
        if not acceptance.get('ok'):
            status = 'UNVERIFIED'
        if 'document_versions' in acceptance:
            checked['document_versions'] = acceptance['document_versions']
    checked.update(ok=bool(evidence.get('ok')) and bool(acceptance.get('ok')), status=status, construction=construction,
                   reference_refresh=evidence, evaluated_results=results,
                   reference_baseline=str(check_baseline), prepared_output=str(intermediate) if intermediate else None,
                   output=str(output), native_acceptance=acceptance, markdown_inventory=markdown,
                   unrelated_literal_references=literal_references(inv) if mode == 'local' else [])
    if not checked['ok']:
        checked['version_check'] = dict(reusable=False, status='REFERENCE_FINALIZATION_INCOMPLETE', changed=[])
    if hashlib.sha256(output.read_bytes()).hexdigest() != published_hash or versions.changed_files(inputs['files']):
        checked.update(ok=False, status='FILES_CHANGED_DURING_FINALIZATION')
        checked['version_check'] = dict(reusable=False, status='FILES_CHANGED_DURING_FINALIZATION', changed=[])
    versions.save_record(record, checked)
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    sub = commands.add_parser('inspect')
    sub.add_argument('source', type=Path)
    for operation in ('prepare', 'refresh', 'finalize', 'check'):
        sub = commands.add_parser(operation)
        sub.add_argument('source', type=Path)
        sub.add_argument('output', type=Path)
        if operation in {'prepare', 'finalize'}:
            sub.add_argument('--mode', choices=['full', 'local'], default='full')
            sub.add_argument('--mapping', type=Path)
        if operation == 'finalize':
            sub.add_argument('--markdown-source', type=Path)
            sub.add_argument('--pandoc', default='pandoc')
        if operation in {'refresh', 'finalize'}:
            sub.add_argument('--allow-office-com', action='store_true')
            sub.add_argument('--record', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'inspect':
            result = inspect_document(args.source)
        elif args.operation == 'check':
            result = check_files(args.source, args.output)
        else:
            mapping = json.loads(args.mapping.read_text(encoding='utf-8-sig')) if getattr(args, 'mapping', None) else None
            if args.operation == 'prepare':
                if args.source.resolve() == args.output.resolve():
                    raise ValueError('Never overwrite the source')
                package, info = prepare_package(guard.DocxPackage.from_path(args.source), mode=args.mode, mapping=mapping)
                publish(package, args.output)
                result = dict(ok=True, status='PREPARED', source=str(args.source.resolve()), output=str(args.output.resolve()),
                              native_refresh='not_run', **info)
            else:
                result = finalize(args.source, args.output, mode=getattr(args, 'mode', 'local'),
                                  allow_office_com=args.allow_office_com, mapping=mapping, record=args.record,
                                  markdown_source=getattr(args, 'markdown_source', None), pandoc=getattr(args, 'pandoc', 'pandoc'))
    except Exception as exc:
        result = dict(ok=False, status='UNVERIFIED', message=str(exc), layout='not_checked')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
