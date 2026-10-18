"""Offline unit tests only: python -B -m unittest discover -s <this directory>."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import run_style as runner


class RunnerTests(unittest.TestCase):
    def test_style_model_applies_to_command_and_resume(self):
        base, replay = runner.prior()
        self.assertEqual(runner.MODELS['claude'], 'claude-opus-4-6')
        for host in runner.MODELS:
            for session in (None, str(uuid.uuid4())):
                with self.subTest(host=host, session=session):
                    argv = runner.command(host, Path.cwd(), session, base, replay)
                    self.assertEqual(argv[argv.index('--model') + 1], runner.MODELS[host])

    def test_explicit_model_override_and_mismatch(self):
        base, replay = runner.prior()
        with patch.dict(runner.MODELS, {'claude': 'user-selected-model'}):
            for session in (None, str(uuid.uuid4())):
                argv = runner.command('claude', Path.cwd(), session, base, replay)
                self.assertEqual(argv[argv.index('--model') + 1], 'user-selected-model')
            self.assertEqual(runner.MODELS['codex'], 'gpt-5.6-sol')
            session = str(uuid.uuid4())
            events = replay.events_from(self.stream(session))
            parsed = replay.parse_result('claude', events)
            context = base.context_evidence('claude', parsed, events)
            self.assertEqual(runner.assess('claude', events, parsed, context, None, 0, False)['status'], 'completed')
            context['models'] = ['claude-opus-4-6']
            self.assertIn('model_mismatch', runner.assess('claude', events, parsed, context, None, 0, False)['reasons'])

    def test_cli_override_is_recorded(self):
        argv = ['run_style.py', 'run', '--host', 'claude', '--arm', 'installed',
                '--model', 'explicit-user-model']
        with patch.object(runner.sys, 'argv', argv), patch.object(runner, 'ROOT', self.root), \
                patch.dict(runner.MODELS), patch.object(runner, 'preflight', return_value={}), \
                patch.object(self.replay, 'selected_claude_environment', return_value=({}, {})), \
                patch.object(runner, 'prior', return_value=(self.base, self.replay)), \
                patch.object(runner, 'run_case', return_value={
                    'case': 'technical', 'host': 'claude', 'arm': 'installed', 'status': 'completed'}):
            with self.assertRaises(SystemExit) as result:
                runner.main()
            self.assertEqual(result.exception.code, 0)
            receipt = next((self.root / 'runs').glob('preflight-*.json'))
            record = json.loads(receipt.read_text(encoding='utf-8'))
            self.assertEqual(record['requested_model'], 'explicit-user-model')
            self.assertEqual(record['explicit_override'], 'explicit-user-model')
            self.assertEqual(runner.MODELS['codex'], 'gpt-5.6-sol')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'experiment'
        self.root.mkdir()
        self.installed = Path(self.tmp.name) / 'installed'
        self.vocab = Path(self.tmp.name) / 'vocab'
        self.case = {'id': 'technical', 'turns': ['first', 'second', 'third'], 'vocab': ['common.md']}
        runner.save(self.root / 'cases.json', {'cases': [self.case]})
        runner.save(self.root / 'candidate.md', 'APPENDIX')
        for name in runner.INPUT_REFS:
            runner.save(self.installed / name, 'FULL RULE ' + name)
        runner.save(self.installed / 'writing-router/references/unrelated.md', 'DO NOT INJECT')
        runner.save(self.vocab / 'common.md', 'WHOLE VOCAB')
        self.rules = Path(self.tmp.name) / 'shared.md'
        runner.save(self.rules, 'SHARED RULE')
        runner.prepare(self.root, self.installed, self.vocab, [self.rules])
        self.base, self.replay = runner.prior()

    def stream(self, session, error=False):
        return '\n'.join(json.dumps(e) for e in [
            {'type': 'system', 'subtype': 'init', 'session_id': session,
             'model': runner.MODELS['claude'], 'tools': [], 'skills': [], 'plugins': [], 'mcp_servers': []},
            {'type': 'result', 'subtype': 'error' if error else 'success', 'session_id': session,
             'is_error': error, 'result': 'OUTPUT', 'usage': {'input_tokens': 10, 'output_tokens': 2}}])

    def test_appendix_only_and_complete_first_material(self):
        before = runner.hashes(self.root / 'snapshot')
        installed = runner.prompt(self.root, 'installed', self.case, 0)
        candidate = runner.prompt(self.root, 'candidate', self.case, 0)
        self.assertEqual(candidate.replace('\n\n<candidate_appendix>\nAPPENDIX\n</candidate_appendix>', ''), installed)
        for ref in runner.INPUT_REFS:
            self.assertIn('FULL RULE ' + ref, installed)
        self.assertIn('WHOLE VOCAB', installed)
        self.assertNotIn('DO NOT INJECT', installed)
        self.assertIn('SHARED RULE', installed)
        self.assertEqual(runner.prompt(self.root, 'candidate', self.case, 1), 'second')
        self.assertEqual(before, runner.hashes(self.root / 'snapshot'))
        self.assertIn('installed/writing-router/references/unrelated.md', before)

    def test_resume_same_session_no_replayed_history(self):
        calls = []
        session = str(uuid.uuid4())

        def fake(argv, cwd, env, body, timeout):
            calls.append((argv, cwd, body, timeout))
            return self.stream(session), '', 0, False, 1.25

        with patch.object(runner.tempfile, 'mkdtemp', return_value=str(self.root / 'scratch')):
            result = runner.run_case(self.root, 'claude', 'installed', self.case, {}, self.base, self.replay, executor=fake)
        self.assertEqual(result['status'], 'completed')
        self.assertNotIn('--resume', calls[0][0])
        for call in calls[1:]:
            self.assertEqual(call[0][call[0].index('--resume') + 1], session)
            self.assertEqual(call[1], calls[0][1])
            self.assertEqual(call[3], 300)
        self.assertEqual([x[2] for x in calls[1:]], ['second', 'third'])
        folder = next((self.root / 'runs/claude/installed/technical').iterdir())
        self.assertEqual(len(json.loads((folder / 'conversation.json').read_text(encoding='utf-8'))), 6)
        for index in range(1, 4):
            dest = folder / f'turn-{index}'
            for name in ('prompt.txt', 'events.jsonl', 'final.md', 'read-evidence.json',
                         'context-evidence.json', 'session.json', 'execution.json', 'completion.json', 'usage.json'):
                self.assertTrue((dest / name).is_file(), name)
            self.assertFalse(result['turns'][index - 1]['quality_accepted'])
            self.assertEqual(result['turns'][index - 1]['duration_seconds'], 1.25)

    def test_failed_case_stops_and_preserves_results(self):
        count = 0

        def fake(*args):
            nonlocal count
            count += 1
            return self.stream(str(uuid.uuid4()), error=True), '', 0, False, 0.5

        with patch.object(runner.tempfile, 'mkdtemp', return_value=str(self.root / 'scratch')):
            for _ in range(2):
                result = runner.run_case(self.root, 'claude', 'installed', self.case, {}, self.base, self.replay, executor=fake)
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['skipped_turns'], 2)
        self.assertEqual(count, 2)
        self.assertEqual(len(list((self.root / 'runs/claude/installed/technical').iterdir())), 2)

    def test_exit_zero_not_success(self):
        session = str(uuid.uuid4())
        events = self.replay.events_from(self.stream(session))
        parsed = self.replay.parse_result('claude', events)
        context = self.base.context_evidence('claude', parsed, events)
        self.assertEqual(runner.assess('claude', events, parsed, context, None, 0, False)['status'], 'completed')
        scenarios = [({'error': True}, {}, None, 0, False),
                     ({'final': ''}, {}, None, 0, False),
                     ({}, {}, str(uuid.uuid4()), 0, False),
                     ({}, {'user_instructions_present': True}, None, 0, False),
                     ({}, {'automatic_skill_catalog_present': True}, None, 0, False),
                     ({'models': ['wrong']}, {}, None, 0, False),
                     ({'reads': [{'name': 'Read'}]}, {}, None, 0, False),
                     ({}, {}, None, 0, True), ({}, {}, None, 1, False)]
        for p, c, previous, code, timeout in scenarios:
            with self.subTest(p=p, c=c, previous=previous):
                result = runner.assess('claude', events, dict(parsed, **p), dict(context, **c), previous, code, timeout)
                self.assertEqual(result['status'], 'failed')
        for changed in [events[:-1], [events[0], dict(events[1], usage={})]]:
            self.assertEqual(runner.assess('claude', changed, parsed, context, None, 0, False)['status'], 'failed')

    def test_codex_resume_contract_and_evidence(self):
        session = str(uuid.uuid4())
        argv = runner.command('codex', self.root, session, self.base, self.replay)
        self.assertEqual(argv[argv.index('exec') + 1], 'resume')
        self.assertEqual(argv[-2:], [session, '-'])
        self.assertNotIn('--sandbox', argv)
        self.assertNotIn('-C', argv)
        self.assertIn('sandbox_mode="read-only"', argv)
        self.assertIn('features.shell_tool=false', argv)
        events = [{'type': 'thread.started', 'thread_id': session},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'BODY'}},
                  {'type': 'turn.completed', 'usage': {'input_tokens': 5, 'output_tokens': 1}}]
        parsed = self.replay.parse_result('codex', events)
        context = {'rollouts': ['session.jsonl'], 'models': [runner.MODELS['codex']]}
        self.assertEqual(runner.assess('codex', events, parsed, context, session, 0, False)['status'], 'completed')
        context['rollouts'] = []
        self.assertEqual(runner.assess('codex', events, parsed, context, session, 0, False)['status'], 'failed')

    def test_variable_turns_validation_and_snapshot_drift(self):
        case = copy.deepcopy(self.case)
        case['turns'] = ['one']
        path = self.root / 'one.json'
        runner.save(path, {'cases': [case]})
        self.assertEqual(len(runner.load_cases(path)[0]['turns']), 1)
        for value in ('../secret', 'C:/secret', '/secret', 'a\\secret'):
            with self.assertRaises(ValueError):
                runner.relative(value)
        runner.save(self.root / 'snapshot/extra.md', 'drift')
        with self.assertRaises(ValueError):
            runner.verify(self.root)
        with self.assertRaises(FileExistsError):
            runner.save(self.root / 'candidate.md', 'overwrite')

    def test_single_turn_and_exception_receipt(self):
        case = dict(self.case, turns=['single'])
        def success(*args):
            return self.stream(str(uuid.uuid4())), '', 0, False, 0.25
        def failure(*args):
            raise RuntimeError('Transport failed: sk-abcdefghijklmnop')
        with patch.object(runner.tempfile, 'mkdtemp', return_value=str(self.root / 'scratch')):
            good = runner.run_case(self.root, 'claude', 'installed', case, {}, self.base, self.replay, executor=success)
            bad = runner.run_case(self.root, 'claude', 'installed', case, {}, self.base, self.replay, executor=failure)
        self.assertEqual(good['status'], 'completed')
        self.assertEqual(len(good['turns']), 1)
        self.assertEqual(bad['status'], 'failed')
        self.assertIn('[REDACTED]', bad['turns'][0]['exception'])
        self.assertNotIn('sk-abcdefghijklmnop', bad['turns'][0]['exception'])
        self.assertIn('duration_seconds', bad['turns'][0])
        self.assertIn('usage', bad['turns'][0])


if __name__ == '__main__':
    unittest.main()
