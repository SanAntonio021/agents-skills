import json
from pathlib import Path
import run_ablation as runner


def cases():
    return json.loads((runner.ROOT / 'cases.json').read_text(encoding='utf-8'))['cases']


def test_prompts_share_business_and_tool_output_policy():
    for case in cases():
        on = runner.make_prompt('with-skill', case)
        off = runner.make_prompt('without-skill', case)
        assert on.split('\n\n', 1)[1] == off.split('\n\n', 1)[1] == case['prompt']
        for prompt in [on, off]:
            assert '工具返回只供内部检查，不附在最终回复中' in prompt
            assert '结果留在对话中' not in prompt
            assert 'review' not in prompt and 'fixture_policy' not in prompt
            assert all((runner.VOCAB / path).as_posix() in prompt for path in case['vocab'])


def test_no_resume_and_same_command_for_both_arms(tmp_path):
    for host in ['claude', 'codex']:
        command = runner.command(host, tmp_path)
        assert '--resume' not in command and 'resume' not in command
        assert '--model' in command and runner.replay.MODELS[host] in command
    claude = runner.command('claude', tmp_path)
    assert '--safe-mode' in claude and '--disable-slash-commands' in claude
    assert claude[claude.index('--tools') + 1] == 'Read,Glob,Grep'
    codex = runner.command('codex', tmp_path)
    for value in ['project_doc_max_bytes=0', 'skills.include_instructions=false',
                  'features.plugins=false', 'features.memories=false']:
        assert value in codex


def test_current_material_is_frozen():
    assert runner.hashes(runner.ROOT / 'snapshot') == json.loads(
        (runner.ROOT / 'snapshot-manifest.json').read_text(encoding='utf-8'))


def test_exact_fixtures_are_original_user_text():
    for case in cases():
        if 'original' in case:
            assert case['original'] in case['prompt']
        if 'append' in case:
            assert case['append'] in case['prompt']
        assert '口径' not in case['prompt'] and '丙型' not in case['prompt']


def test_mcp_cli_key_is_not_a_literal_quoted_table(tmp_path, monkeypatch):
    (tmp_path / 'config.toml').write_text('[mcp_servers.claude-codex-bridge]\ncommand="test"\n', encoding='utf-8')
    monkeypatch.setattr(runner, 'CODEX_HOME', tmp_path)
    args = runner.command('codex', tmp_path)
    assert 'mcp_servers.claude-codex-bridge.enabled=false' in args
    assert not any('mcp_servers."' in arg for arg in args)


def test_loaded_arm_contains_exact_required_rule_bodies():
    for case in cases():
        prompt = runner.make_prompt('loaded-skill', case)
        assert prompt.endswith('\n\n' + case['prompt'])
        for relative in runner.required_refs(case):
            path = runner.ROOT / 'snapshot' / relative
            assert f'<skill_reference path="{path.as_posix()}">\n{path.read_text(encoding="utf-8")}\n</skill_reference>' in prompt
        assert '结果留在对话中' not in prompt


def test_controlled_arms_supply_identical_vocabulary_and_business():
    for case in cases():
        prompts = [runner.make_prompt(arm, case, True)
                   for arm in ['without-skill', 'loaded-skill']]
        for prompt in prompts:
            assert prompt.endswith('\n\n' + case['prompt'])
            for relative in case['vocab']:
                path = runner.VOCAB / relative
                assert f'<vocabulary path="{path.as_posix()}">\n{path.read_text(encoding="utf-8")}\n</vocabulary>' in prompt
        assert prompts[0].split('</vocabulary>')[:-1] == prompts[1].split('</vocabulary>')[:-1]
