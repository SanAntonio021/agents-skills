import json
import re

import run_contrast as run
from collect import exact_check


def test_all_cases_have_two_per_category_and_explicit_upstream_scope():
    cases = run.cases()
    assert len(cases) == 6 and len({c['id'] for c in cases}) == 6
    for category in ['summary', 'technical', 'heading']:
        assert sum(c['category'] == category for c in cases) == 2
    assert all(c['upstream_scope'] != 'applicable' for c in cases)


def test_candidate_changes_only_examples_context():
    for case in run.cases():
        assert run.material_refs('examples', case) == run.material_refs('local', case) + ['candidate/examples.md']
        assert not any(p.startswith('local/') for p in run.material_refs('khazix', case))


def test_prompts_share_business_vocabulary_and_wrapper():
    for case in run.cases():
        prompts = [run.prompt(arm, case) for arm in run.ARMS]
        for prompt in prompts:
            assert prompt.endswith('\n\n' + case['prompt'])
            assert 'review' not in prompt.split('<skill_reference', 1)[0]
            assert case['upstream_scope'] not in prompt
            assert all(judgment not in prompt for judgment in case['review'])
        assert len({p.split('<skill_reference', 1)[0] for p in prompts}) == 1


def test_complete_expected_rules_are_supplied():
    for case in run.cases():
        for arm in run.ARMS:
            prompt = run.prompt(arm, case)
            for relative in run.material_refs(arm, case):
                path = run.ROOT / 'snapshot' / relative
                assert f'<skill_reference path="{path.as_posix()}">\n{path.read_text(encoding="utf-8")}\n</skill_reference>' in prompt


def test_heading_source_is_verbatim_in_business_prompt():
    for case in run.cases():
        if case['category'] == 'heading':
            assert case['original'] in case['prompt']
            assert case['heading'].startswith('## ')


def test_frozen_snapshot_matches_manifest():
    assert run.base.hashes(run.ROOT / 'snapshot') == json.loads(
        (run.ROOT / 'snapshot-manifest.json').read_text(encoding='utf-8'))


def test_synthetic_examples_are_not_test_answer_strings():
    examples = (run.ROOT / 'examples.md').read_text(encoding='utf-8')
    for case in run.cases():
        assert case['prompt'] not in examples
        if 'original' in case:
            assert case['original'] not in examples
        assert not re.search(r'[A-Z]:[\\/]|https?://', case['prompt'])


def test_commands_use_fresh_sessions_and_same_fixed_models(tmp_path):
    for host in run.replay.MODELS:
        argv = run.base.command(host, tmp_path)
        assert 'resume' not in argv and '--resume' not in argv
        assert argv[argv.index('--model') + 1] == run.replay.MODELS[host]


def test_exact_check_is_not_contains_only():
    case = next(c for c in run.cases() if c['category'] == 'heading')
    good = case['heading'] + '\n\n' + case['original']
    assert exact_check(case, good)['status'] == 'pass'
    for bad in [good + '\n原文未改。', good.replace('，', ','), good.replace(' = ', '='), good.replace('0.18', '0.19')]:
        assert exact_check(case, bad)['status'] == 'fail'
