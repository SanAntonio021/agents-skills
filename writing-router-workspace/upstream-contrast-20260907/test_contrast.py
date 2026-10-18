import copy
import json
from types import SimpleNamespace
from pathlib import Path

import contrast
import collect


def test_neutral_prompt_does_not_expose_test_labels_or_scoring():
    text = contrast.prompt(Path('snapshot'), 'write', 'current user request', True)
    assert '合成' not in text and 'TRACE_WRITING_CONTEXT' not in text
    assert 'expectations' not in text and 'protected_facts' not in text
    assert text.endswith('current user request')
    assert 'writing-eval:write' in text


def test_same_native_tools_for_every_arm():
    for variant in contrast.ENTRIES:
        argv = contrast.command('claude', Path('workspace'), None, True, Path(variant))
        assert argv[argv.index('--tools') + 1] == 'Read,Glob,Grep,Skill,Bash'
        assert argv[argv.index('--allowedTools') + 1] == 'Read,Glob,Grep,Skill,Bash'
        assert '--bare' not in argv and '--safe-mode' not in argv


def test_pinned_originals_and_plugins_match():
    manifest = json.loads((contrast.ROOT / 'upstream-manifest.json').read_text(encoding='utf-8'))
    for variant, (_, commit, _) in contrast.UPSTREAM.items():
        assert manifest[variant]['commit'] == commit
        assert manifest[variant]['files'] == contrast.file_hashes(contrast.ROOT / variant)
        assert contrast.file_hashes(contrast.ROOT / variant) == contrast.file_hashes(
            contrast.ROOT / 'plugins' / variant / 'skills')


def test_case_prompts_are_shared_and_status_is_not_a_summary_checklist():
    cases = json.loads((contrast.ROOT / 'cases.json').read_text(encoding='utf-8'))['evals']
    assert {case['id'] for case in cases} == set(contrast.CASES)
    report = next(case for case in cases if case['id'] == contrast.CASES[0])
    assert '验收状态放在最后' not in report['turns'][1]['prompt']
    assert all(fact['kind'] != 'status' for fact in report['turns'][2]['protected_facts'])
    assert any('样机验收尚未进行' in fact['text'] for fact in report['turns'][0]['protected_facts'])
    for case in cases:
        expected = [turn['prompt'] for turn in case['turns']]
        for variant, entry in contrast.ENTRIES.items():
            routed = copy.deepcopy(case)
            routed['entry_skill'] = entry
            assert [turn['prompt'] for turn in routed['turns']] == expected


def test_paper_still_protects_scope_and_untested_state():
    cases = json.loads((contrast.ROOT / 'cases.json').read_text(encoding='utf-8'))['evals']
    paper = next(case for case in cases if case['id'] == 'necessary-negation-paper')
    for turn in paper['turns']:
        assert any('多发送端测试尚未开展' in fact['text'] for fact in turn['protected_facts'])


def test_all_frozen_materials_still_match():
    for variant in contrast.ENTRIES:
        assert contrast.material_state(variant)['valid']


def test_collector_rejects_changed_material(monkeypatch):
    monkeypatch.setattr(collect, 'material_state', lambda _: {'valid': False})
    assert collect.collect_run('claude', 'local-after', {'id': 'unused'}) is None


def test_hash_anomaly_is_explicitly_excluded():
    exclusions = collect.excluded_runs()
    assert len(exclusions) == 7
    assert sum(path.startswith('runs/claude/humanizer-original/') for path in exclusions) == 3


def test_hashes_ignore_upload_sidecars_but_include_scripts(tmp_path):
    (tmp_path / 'script.py').write_text('print(1)', encoding='utf-8')
    before = contrast.file_hashes(tmp_path)
    (tmp_path / 'script.py.baiduyun.uploading.cfg').write_text('temporary', encoding='utf-8')
    assert contrast.file_hashes(tmp_path) == before
    (tmp_path / 'script.py').write_text('print(2)', encoding='utf-8')
    assert contrast.file_hashes(tmp_path) != before


def test_batch_creates_and_persists_integrity_receipt(tmp_path, monkeypatch):
    (tmp_path / 'cases.json').write_text('{"evals": []}', encoding='utf-8')
    monkeypatch.setattr(contrast, 'ROOT', tmp_path)
    monkeypatch.setattr(contrast, 'material_state', lambda _: {'valid': True})
    monkeypatch.setattr(contrast.replay, 'ROOT', tmp_path)
    monkeypatch.setattr(contrast.replay, 'initial_prompt', contrast.prompt)
    monkeypatch.setattr(contrast.replay, 'command', contrast.command)
    monkeypatch.setenv('PATH', '')
    monkeypatch.setenv('CLAUDE_CODE_GIT_BASH_PATH', '')
    contrast.run(SimpleNamespace(host='codex', version='local-before', case='all'))
    receipt, = (tmp_path / 'batches').glob('*.json')
    result = json.loads(receipt.read_text(encoding='utf-8'))
    assert result['before'] == result['after'] == {'valid': True}
    assert result['status'] == 'completed'
