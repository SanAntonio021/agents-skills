"""Integration checks for the two-stage, source-preserving paragraph workflow."""
import hashlib
import json
from pathlib import Path
import sys

from docx import Document
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import edit_paragraphs
import document_versions


def test_local_finalization_retains_both_evidence_stages(tmp_path):
    source, edits, output = [tmp_path / p for p in ('source.docx', 'edits.json', 'final.docx')]
    doc = Document()
    doc.add_paragraph('Original prose')
    doc.save(source)
    before = source.read_bytes()
    edits.write_text(json.dumps([dict(op='replace', old='Original prose', text='Approved prose')]), encoding='utf-8')
    result = edit_paragraphs.finalize_edits(source, edits, output)
    assert result['ok']
    assert result['reference_refresh']['status'] == 'NOT_APPLICABLE'
    assert source.read_bytes() == before
    stage = Path(result['paragraph_stage']['output'])
    assert stage.exists() and stage != output
    assert edit_paragraphs.check_edits(source, edits, stage)['ok']
    for document, record in ((stage, Path(result['paragraph_stage']['record'])), (output, Path(str(output) + '.check.json'))):
        data = json.loads(record.read_text(encoding='utf-8'))
        assert data['document_versions']['checked_document']['sha256'] == hashlib.sha256(document.read_bytes()).hexdigest()
        assert document_versions.assess(data, document)['status'] == 'CURRENT'


def test_finalization_never_overwrites_existing_delivery(tmp_path):
    source, edits, output = [tmp_path / p for p in ('source.docx', 'edits.json', 'final.docx')]
    Document().save(source)
    edits.write_text('[]', encoding='utf-8')
    output.write_bytes(b'user-owned')
    with pytest.raises(ValueError):
        edit_paragraphs.finalize_edits(source, edits, output)
    assert output.read_bytes() == b'user-owned'
