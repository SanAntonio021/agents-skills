#!/usr/bin/env python
"""Read-only, profile-driven checks of DOCX/DOTX formatting (not pagination).

Rules describe this document family's roles; the tool supplies no universal
Chinese font/spacing defaults. Word-native rendering remains a separate check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from lxml import etree as E

from style_guard import DocxPackage, _parse_xml

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
Q = lambda tag: '{' + W + '}' + tag
VAL = Q('val')
P_KEYS = {
    'alignment': ('jc', 'val', str),
    'first_line_chars': ('ind', 'firstLineChars', lambda v: int(v) / 100),
    'first_line_pt': ('ind', 'firstLine', lambda v: int(v) / 20),
    'left_pt': ('ind', 'left', lambda v: int(v) / 20),
    'hanging_pt': ('ind', 'hanging', lambda v: int(v) / 20),
    'line': ('spacing', 'line', int),
    'line_rule': ('spacing', 'lineRule', str),
    'before_pt': ('spacing', 'before', lambda v: int(v) / 20),
    'after_pt': ('spacing', 'after', lambda v: int(v) / 20),
    'outline_level': ('outlineLvl', 'val', int),
    'keep_next': ('keepNext', 'val', lambda v: v not in ('0', 'false', 'off')),
    'widow_control': ('widowControl', 'val', lambda v: v not in ('0', 'false', 'off')),
}
R_KEYS = {'font_ascii', 'font_east_asia', 'size_pt', 'bold', 'color'}
SELECT_KEYS = {'style', 'text', 'text_regex', 'in_table', 'auto_numbered'}


def text(node):
    return ''.join(node.xpath('.//w:t/text()', namespaces=NS))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def properties(node):
    """Flatten attributes so partial direct overrides retain inherited values."""
    result = {}
    if node is not None:
        for item in node:
            if not isinstance(item.tag, str):
                continue
            tag = E.QName(item).localname
            if item.attrib:
                for key, value in item.attrib.items():
                    result[(tag, E.QName(key).localname)] = value
            else:
                result[(tag, 'val')] = '1'
    return result


def merge_properties(target, values):
    # A more specific font choice replaces the inherited choice for that slot.
    # Explicit + theme in the same rFonts element still favours theme.
    for slot in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        if any(('rFonts', k) in values for k in (slot, slot + 'Theme')):
            target.pop(('rFonts', slot), None)
            target.pop(('rFonts', slot + 'Theme'), None)
    if any(tag == 'color' for tag, _ in values):
        for key in list(target):
            if key[0] == 'color':
                target.pop(key)
    target.update(values)


def merge_style(target, values, run=False):
    # Bold is a toggle in style definitions, absolute in direct formatting.
    values = dict(values)
    if run and ('b', 'val') in values:
        enabled = values.pop(('b', 'val')) not in ('0', 'false', 'off')
        if enabled:
            inherited = target.get(('b', 'val'), '0') not in ('0', 'false', 'off')
            target[('b', 'val')] = '0' if inherited else '1'
    merge_properties(target, values)


class Inventory:
    def __init__(self, path):
        self.package = DocxPackage.from_path(Path(path))
        self.doc = _parse_xml(self.package.entries['word/document.xml'])
        self.styles = _parse_xml(self.package.entries['word/styles.xml'])
        self.by_id = {s.get(Q('styleId')): s for s in self.styles.findall(Q('style'))}
        self.default_style = next((k for k, s in self.by_id.items()
                                   if s.get(Q('type')) == 'paragraph'
                                   and s.get(Q('default')) == '1'), None)
        self.defaults_p = properties(self.styles.find('w:docDefaults/w:pPrDefault/w:pPr', NS))
        self.defaults_r = properties(self.styles.find('w:docDefaults/w:rPrDefault/w:rPr', NS))
        raw = self.package.entries.get('word/numbering.xml')
        self.numbering = _parse_xml(raw) if raw else E.Element(Q('numbering'))
        self.paragraphs = list(self.doc.findall('.//w:p', NS))

    def chain(self, sid):
        result, seen = [], set()
        while sid:
            if sid in seen:
                raise ValueError('Cyclic style inheritance: ' + sid)
            seen.add(sid)
            if sid not in self.by_id:
                raise ValueError('Undefined style: ' + sid)
            style = self.by_id[sid]
            result.append(style)
            based = style.find(Q('basedOn'))
            sid = based.get(VAL) if based is not None else None
        return list(reversed(result))

    def style_id(self, p):
        node = p.find('w:pPr/w:pStyle', NS)
        return node.get(VAL) if node is not None else self.default_style

    def numbering_level(self, pprops):
        nid = pprops.get(('numPr', 'numId'))
        # numPr is nested, resolved separately by paragraph_properties.
        if nid is None or nid == '0':
            return None
        num = next((x for x in self.numbering.findall(Q('num')) if x.get(Q('numId')) == nid), None)
        if num is None:
            raise ValueError('Undefined numbering numId: ' + nid)
        ref = num.find(Q('abstractNumId'))
        aid = ref.get(VAL) if ref is not None else None
        abstract = next((x for x in self.numbering.findall(Q('abstractNum'))
                        if x.get(Q('abstractNumId')) == aid), None)
        if abstract is None:
            raise ValueError('Undefined abstract numbering: ' + str(aid))
        level_id = pprops.get(('numPr', 'ilvl'), '0')
        level = next((x for x in abstract.findall(Q('lvl')) if x.get(Q('ilvl')) == level_id), None)
        override = next((x for x in num.findall(Q('lvlOverride')) if x.get(Q('ilvl')) == level_id), None)
        if override is not None and override.find(Q('lvl')) is not None:
            level = override.find(Q('lvl'))
        start = level.find(Q('start')) if level is not None else None
        start_value = int(start.get(VAL)) if start is not None else 1
        if override is not None and override.find(Q('startOverride')) is not None:
            start_value = int(override.find(Q('startOverride')).get(VAL))
        return nid, level_id, level, start_value

    @staticmethod
    def num_props(node):
        result = {}
        if node is not None:
            for name in ('numId', 'ilvl'):
                val = node.find('w:numPr/w:' + name, NS)
                if val is not None:
                    result[('numPr', name)] = val.get(VAL)
        return result

    def paragraph_properties(self, p):
        style_values = {}
        for style in self.chain(self.style_id(p)):
            props = style.find(Q('pPr'))
            style_values.update(properties(props))
            style_values.update(self.num_props(props))
        direct = p.find(Q('pPr'))
        numbering_values = dict(style_values)
        numbering_values.update(self.num_props(direct))
        numbering = self.numbering_level(numbering_values)
        values = dict(self.defaults_p)
        if numbering and numbering[2] is not None:
            values.update(properties(numbering[2].find(Q('pPr'))))
        values.update(style_values)
        values.update(properties(direct))
        return values, numbering

    def run_properties(self, p, run):
        values = dict(self.defaults_r)
        for style in self.chain(self.style_id(p)):
            merge_style(values, properties(style.find(Q('rPr'))), run=True)
        if run is not None:
            rstyle = run.find('w:rPr/w:rStyle', NS)
            if rstyle is not None:
                for style in self.chain(rstyle.get(VAL)):
                    merge_style(values, properties(style.find(Q('rPr'))), run=True)
            merge_properties(values, properties(run.find(Q('rPr'))))
        return values

    def value(self, p, key, run=None):
        if key in P_KEYS:
            values, _ = self.paragraph_properties(p)
            tag, attr, convert = P_KEYS[key]
            if key == 'first_line_pt' and ('ind', 'firstLineChars') in values:
                return None  # Character units take precedence over twips.
            raw = values.get((tag, attr))
            return convert(raw) if raw is not None else None
        values = self.run_properties(p, run)
        if key in ('font_ascii', 'font_east_asia'):
            slot = 'ascii' if key == 'font_ascii' else 'eastAsia'
            theme = values.get(('rFonts', slot + 'Theme'))
            # Theme may override an explicit family. Do not invent a resolved font.
            return {'theme': theme, 'resolution': 'not_resolved'} if theme else values.get(('rFonts', slot))
        if key == 'size_pt':
            raw = values.get(('sz', 'val'))
            return float(raw) / 2 if raw else None
        if key == 'bold':
            return values.get(('b', 'val'), '0') not in ('0', 'false', 'off')
        if key == 'color':
            if values.get(('color', 'themeColor')):
                return {'theme': values[('color', 'themeColor')], 'resolution': 'not_resolved'}
            return values.get(('color', 'val'))
        raise ValueError('Unsupported property: ' + key)

    def matches(self, p, select):
        if set(select) - SELECT_KEYS:
            raise ValueError('Unknown selector: ' + str(set(select) - SELECT_KEYS))
        return (('style' not in select or self.style_id(p) == select['style'])
                and ('text' not in select or text(p) == select['text'])
                and ('text_regex' not in select or re.search(select['text_regex'], text(p)))
                and ('auto_numbered' not in select or bool(self.paragraph_properties(p)[1]) == select['auto_numbered'])
                and ('in_table' not in select or bool(p.xpath('ancestor::w:tbl', namespaces=NS)) == select['in_table']))

    def location(self, p):
        return {'part': 'word/document.xml', 'xpath': p.getroottree().getpath(p),
                'style': self.style_id(p), 'text': text(p)[:180]}


def audit(path, rules):
    before = digest(path)
    inv = Inventory(path)
    if set(rules) - {'schema', 'description', 'paragraph_rules', 'a4', 'table_grid', 'numbering_groups'}:
        raise ValueError('Unknown top-level rule key')
    if rules.get('schema') != 1:
        raise ValueError('Rules require schema=1')
    if not any(rules.get(k) for k in ('paragraph_rules', 'a4', 'table_grid', 'numbering_groups')):
        raise ValueError('No active checks declared')
    findings, checks, selected = [], [], set()
    for rule in rules.get('paragraph_rules', []):
        if set(rule) - {'name', 'select', 'expect', 'min', 'max'}:
            raise ValueError('Unknown paragraph rule key')
        expected = rule['expect']
        if not expected or set(expected) - (set(P_KEYS) | R_KEYS):
            raise ValueError('Empty or unsupported properties in ' + rule['name'])
        matched = [p for p in inv.paragraphs if inv.matches(p, rule['select'])]
        checks.append({'rule': rule['name'], 'matched': len(matched)})
        if not rule.get('min', 1) <= len(matched) <= rule.get('max', 10**9):
            findings.append({'rule': rule['name'], 'problem': 'match_count', 'actual': len(matched)})
        for p in matched:
            selected.add(p)
            for key, wanted in expected.items():
                runs = p.xpath('.//w:r[w:t]', namespaces=NS) if key in R_KEYS else [None]
                if key in R_KEYS and not runs:
                    continue
                seen = set()
                for run in runs:
                    actual = inv.value(p, key, run)
                    marker = json.dumps(actual, sort_keys=True)
                    if actual != wanted and marker not in seen:
                        findings.append({'rule': rule['name'], **inv.location(p),
                                         'property': key, 'expected': wanted, 'actual': actual})
                    seen.add(marker)
    if rules.get('a4'):
        sections = inv.doc.findall('.//w:sectPr', NS)
        if not sections:
            findings.append({'rule': 'A4', 'problem': 'missing_section_properties'})
        for i, section in enumerate(sections):
            size = section.find(Q('pgSz'))
            dims = sorted([int(size.get(Q('w'))), int(size.get(Q('h')))]) if size is not None else []
            if len(dims) != 2 or abs(dims[0]-11906) > 5 or abs(dims[1]-16838) > 5:
                findings.append({'rule': 'A4', 'section': i+1, 'dimensions_twips': dims})
        checks.append({'rule': 'A4', 'sections': len(sections)})
    if rules.get('table_grid'):
        tables = inv.doc.findall('.//w:tbl', NS)
        for ti, table in enumerate(tables):
            grid = [int(c.get(Q('w'))) for c in table.findall('w:tblGrid/w:gridCol', NS)]
            for ri, row in enumerate(table.findall(Q('tr'))):
                def rowint(name):
                    node = row.find('w:trPr/w:' + name, NS)
                    return int(node.get(VAL)) if node is not None else 0
                col = rowint('gridBefore')
                for ci, cell in enumerate(row.findall(Q('tc'))):
                    span = cell.find('w:tcPr/w:gridSpan', NS)
                    n = int(span.get(VAL)) if span is not None else 1
                    width = cell.find('w:tcPr/w:tcW', NS)
                    if width is not None and width.get(Q('type')) == 'dxa' and col+n <= len(grid):
                        if abs(int(width.get(Q('w'))) - sum(grid[col:col+n])) > 5:
                            findings.append({'rule': 'table_grid', 'table': ti+1, 'row': ri+1,
                                             'cell': ci+1, 'problem': 'cell_width_grid_mismatch'})
                    col += n
                if not grid or col + rowint('gridAfter') != len(grid):
                    findings.append({'rule': 'table_grid', 'table': ti+1, 'row': ri+1, 'problem': 'row_span_mismatch'})
        checks.append({'rule': 'table_grid', 'tables': len(tables)})
    for rule in rules.get('numbering_groups', []):
        if set(rule) - {'name', 'select', 'counts', 'start'}:
            raise ValueError('Unknown numbering rule key')
        matched = [p for p in inv.paragraphs if inv.matches(p, rule['select'])]
        groups = {}
        ordered = []
        for p in matched:
            _, num = inv.paragraph_properties(p)
            if num is None:
                findings.append({'rule': rule['name'], **inv.location(p), 'problem': 'missing_auto_numbering'})
                continue
            nid, level_id, level, start = num
            if level is None:
                findings.append({'rule': rule['name'], **inv.location(p), 'problem': 'missing_numbering_level'})
                continue
            key = (nid, level_id)
            if key not in groups:
                groups[key] = 0
                ordered.append(key)
                if start != rule.get('start', 1):
                    findings.append({'rule': rule['name'], 'num_id': nid, 'problem': 'wrong_start', 'actual': start})
            groups[key] += 1
        counts = [groups[k] for k in ordered]
        if not matched or ('counts' in rule and counts != rule['counts']):
            findings.append({'rule': rule['name'], 'problem': 'group_counts', 'actual': counts})
        checks.append({'rule': rule['name'], 'groups': counts})
    after = digest(path)
    if before != after:
        raise RuntimeError('Source changed during read-only audit')
    return {'status': 'STATIC_FAIL' if findings else 'STATIC_PASS', 'source_sha256': before,
            'source_unchanged': True, 'layout_status': 'NOT_CHECKED',
            'coverage': {'paragraphs': len(inv.paragraphs), 'paragraphs_selected': len(selected)},
            'checks': checks, 'findings': findings,
            'limitations': ['Checks only the declared properties/selectors in the main document part.',
                            'Table style conditional formatting and theme-font resolution are not evaluated.',
                            'Numbering groups check definitions and counts, not the rendered counter sequence.',
                            'Pagination, clipping, field freshness and rendered line breaks require native checks.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--rules', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.report and args.report.resolve() in (args.input.resolve(), args.rules.resolve()):
        parser.error('Report must not overwrite input or rules')
    try:
        report = audit(args.input, json.loads(args.rules.read_text(encoding='utf-8')))
        report['rules_sha256'] = digest(args.rules)
        if args.report:
            if args.report.exists():
                raise ValueError('Report already exists; select a new path')
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['status'] == 'STATIC_PASS' else 1
    except (ValueError, KeyError, OSError, E.XMLSyntaxError) as exc:
        print(json.dumps({'status': 'ERROR', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
