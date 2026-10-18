"""Opt-in native acceptance on generated fixtures only; never takes user documents."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from docx import Document
from docx.oxml import OxmlElement

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reference_fields as refs
import style_guard as guard


def run(root):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = root / 'synthetic-source.docx'
    doc = Document()
    doc.add_paragraph('See Figure 2 and Table 1; Equation (1).')
    doc.add_paragraph('Figure 1 First result', style='Caption')
    doc.add_paragraph('Figure 2 Second result', style='Caption')
    doc.add_paragraph('Table 1 Parameters', style='Caption')
    eq = doc.add_paragraph()
    math = OxmlElement('m:oMath')
    run_ = OxmlElement('m:r')
    text = OxmlElement('m:t')
    text.text = 'x=1'
    run_.append(text)
    math.append(run_)
    eq._p.append(math)
    eq.add_run(' (1)')
    doc.sections[0].header.paragraphs[0].text = 'See Figure 2.'
    doc.sections[0].footer.paragraphs[0].text = 'See Table 1.'
    doc.add_table(rows=1, cols=1).cell(0, 0).text = 'Equation (1) applies.'
    doc.save(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    output = root / 'native-final.docx'
    result = refs.finalize(source, output, mode='full', allow_office_com=True)
    if result.get('ok'):
        package = guard.DocxPackage.from_path(output)
        inv = refs.Inventory(package)
        first = next(f for f in inv.fields if f.kind == 'SEQ' and 'Figure' in f.instruction)
        paragraph = first.start.getparent().getparent()
        following = paragraph.getnext()
        paragraph.getparent().remove(paragraph)
        following.addnext(paragraph)
        moved = root / 'moved-object.docx'
        refs.publish(inv.updated(), moved)
        refreshed = root / 'moved-refreshed.docx'
        second = refs.finalize(moved, refreshed, mode='local', allow_office_com=True)
        result['movement_test'] = second
        if second.get('ok'):
            after = refs.Inventory(guard.DocxPackage.from_path(refreshed))
            body_ref = next(f for f in after.fields if f.story == 'main' and f.kind == 'REF')
            assert body_ref.text == '1', body_ref.text
            assert any(f.story.startswith('header:') and f.kind == 'REF' and f.text == '1' for f in after.fields)
        result['ok'] = result['ok'] and second.get('ok', False)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    (root / 'native-acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get('ok') else 2)
