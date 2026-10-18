"""Exercise exact editing on this experiment's synthetic originals only."""
import codecs
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT.parent.parent / 'writing-router/scripts/exact_edit.py'
SPEC = importlib.util.spec_from_file_location('exact_edit_proof', SCRIPT)
exact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exact)


def run():
    cases = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['cases']
    output = Path(tempfile.mkdtemp(prefix='proof-', dir=ROOT))
    results = []
    for case in cases:
        if 'original' not in case:
            continue
        for newline in ['\n', '\r\n']:
            for bom in [b'', codecs.BOM_UTF8]:
                folder = output / f'{case["id"]}-{len(results) + 1}'
                folder.mkdir()
                source = bom + case['original'].replace('\n', newline).encode('utf-8')
                digest = hashlib.sha256(source).hexdigest()
                source_path, target = folder / 'source.md', folder / 'output.md'
                source_path.write_bytes(source)
                operation = {'title': case['heading']} if 'heading' in case else {'append': case['append']}
                applied = exact.apply_file(source_path, target, digest, **operation)
                verified = exact.validate_file(source_path, target, digest, **operation)
                candidate = target.read_bytes()
                if 'heading' in case:
                    sentences = case['original'].split('。')
                    moved = '。'.join([sentences[1], sentences[0], *sentences[2:]])
                    reorder = candidate.replace(case['original'].encode(), moved.encode())
                    number = candidate.replace(b'40000', b'40001')
                else:
                    first, second = '新标签已经打印，', '核对编号后再替换旧标签。'
                    reorder = candidate.replace((first + second).encode(), (second + first).encode())
                    number = candidate.replace(b'09:30', b'09:35')
                corruptions = {'sentence_order': reorder, 'number': number,
                               'extra_explanation': candidate + '\n已保持原文。'.encode()}
                rejected = {}
                for name, bad in corruptions.items():
                    assert bad != candidate, name
                    rejected[name] = not exact.validate_bytes(source, bad, digest, **operation)['ok']
                assert source_path.read_bytes() == source
                assert applied['ok'] and verified['ok'] and all(rejected.values())
                results.append({'case': case['id'], 'newline': repr(newline), 'bom': bool(bom),
                                'output': str(target.relative_to(ROOT)), 'apply': applied,
                                'verify': verified, 'deliberate_corruptions_rejected': rejected,
                                'source_unchanged': True})
    receipt = {'model_generated': False, 'results': results,
               'passed': len(results), 'corruptions_rejected': sum(len(r['deliberate_corruptions_rejected']) for r in results)}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'receipt': str(output / 'receipt.json'), 'passed': receipt['passed'],
                      'corruptions_rejected': receipt['corruptions_rejected']}, ensure_ascii=False))


if __name__ == '__main__':
    run()
