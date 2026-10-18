import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('runner', Path(__file__).with_name('run_evaluation.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_codex_final_and_read_receipt():
    result = runner.parse_result('codex', [
        {'type': 'thread.started', 'thread_id': 'fixture-id'},
        {'type': 'item.completed', 'item': {'type': 'command_execution',
          'command': 'read fixture', 'exit_code': 0, 'aggregated_output': 'rules'}},
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'prose'}},
    ])
    assert result['session'] == 'fixture-id'
    assert result['final'] == 'prose'
    assert result['reads'][0]['exit_code'] == 0
    assert result['models'] == []


def test_claude_model_failure_is_not_success():
    result = runner.parse_result('claude', [
        {'type': 'assistant', 'message': {'model': 'claude-opus-5', 'content': [
            {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'fixture.md'}}]}},
        {'type': 'result', 'session_id': 'fixture-id', 'is_error': True, 'result': 'error'},
    ])
    assert result['models'] == ['claude-opus-5']
    assert result['error']
    assert result['reads'][0]['input']['file_path'] == 'fixture.md'


def test_only_exact_codex_session_is_resumed():
    args = runner.command('codex', Path('.'), 'known-session')
    assert 'resume' in args and 'known-session' in args
    assert '--last' not in args and '--ephemeral' not in args
    assert 'sandbox_mode="read-only"' in args


def test_control_prompt_does_not_reveal_scoring_or_future_turns():
    prompt = runner.initial_prompt(Path('snapshot'), 'writing-router', 'visible current turn')
    assert 'visible current turn' in prompt
    assert 'expectations' not in prompt and 'protected_facts' not in prompt
    assert 'TRACE_WRITING_CONTEXT' not in prompt


def test_redaction_and_partial_events():
    assert 'sk-' not in runner.redact('sk-12345678901234567890')
    assert runner.events_from('not json\n{"type":"result"}\n{broken') == [{'type': 'result'}]


def test_direct_claude_does_not_put_credentials_in_command():
    args = runner.command('claude', Path('.'), None, direct=True)
    assert '--bare' in args and '--setting-sources' in args
    assert '--settings' not in args
    assert not any('AUTH_TOKEN' in arg or 'API_KEY' in arg for arg in args)


def test_child_only_credential_is_redacted(monkeypatch):
    monkeypatch.setattr(runner, 'PRIVATE_VALUES', ['dummy-child-credential'])
    assert runner.redact('value=dummy-child-credential') == 'value=[REDACTED]'


def test_native_mode_keeps_skill_tool_available():
    args = runner.command('claude', Path('.'), None, direct=True, plugin=Path('plugin'))
    assert '--bare' not in args and '--safe-mode' not in args
    assert 'Read,Glob,Grep,Skill' in args
    assert '--setting-sources' in args


def test_native_skill_requires_successful_tool_receipt():
    calls = [{'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'id': 's1', 'name': 'Skill',
         'input': {'skill': 'writing-eval:writing-router'}}]}}]
    assert not runner.parse_result('claude', calls)['native_skills']
    failed = {'type': 'user', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': 's1', 'is_error': True}]}}
    assert not runner.parse_result('claude', calls + [failed])['native_skills']
    failed['message']['content'][0]['is_error'] = False
    assert runner.parse_result('claude', calls + [failed])['native_skills'] == ['writing-eval:writing-router']
