import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('builder', Path(__file__).with_name('build_review.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def setup_run(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'SOURCE', tmp_path / 'source')
    snapshot = tmp_path / 'candidate'
    snapshot.mkdir()
    (snapshot / 'rules.md').write_text('first', encoding='utf-8')
    (tmp_path / 'vocab').mkdir()
    folder = tmp_path / 'runs/codex/candidate/case/001'
    (folder / 'turn-1').mkdir(parents=True)
    (folder / 'turn-1/prompt.txt').write_text('wrapper prompt', encoding='utf-8')
    events = [
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'result'}},
        {'type': 'turn.completed'},
    ]
    (folder / 'turn-1/events.jsonl').write_text('\n'.join(map(json.dumps, events)), encoding='utf-8')
    report = {'status': 'completed', 'requested_model': 'gpt-5.6-sol',
              'snapshot': builder.hash_files(snapshot), 'vocab': {}}
    (folder / 'completion.json').write_text(json.dumps(report), encoding='utf-8')
    return folder, snapshot, {'id': 'case', 'turns': [{'prompt': 'prompt'}]}, report


def test_current_complete_output_is_selected(tmp_path, monkeypatch):
    folder, snapshot, case, report = setup_run(tmp_path, monkeypatch)
    assert builder.completed_run('codex', 'candidate', case)['outputs'] == ['result']


def test_old_snapshot_is_not_used_as_current(tmp_path, monkeypatch):
    folder, snapshot, case, report = setup_run(tmp_path, monkeypatch)
    (snapshot / 'rules.md').write_text('second', encoding='utf-8')
    assert builder.completed_run('codex', 'candidate', case) is None


def test_failed_controller_run_is_not_accepted(tmp_path, monkeypatch):
    folder, snapshot, case, report = setup_run(tmp_path, monkeypatch)
    report['status'] = 'failed'
    (folder / 'completion.json').write_text(json.dumps(report), encoding='utf-8')
    assert builder.completed_run('codex', 'candidate', case) is None


def test_different_input_is_not_paired(tmp_path, monkeypatch):
    folder, snapshot, case, report = setup_run(tmp_path, monkeypatch)
    case['turns'][0]['prompt'] = 'new prompt'
    assert builder.completed_run('codex', 'candidate', case) is None
