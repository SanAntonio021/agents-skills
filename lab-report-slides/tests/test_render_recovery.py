"""Fault injection verifies retained editable output and conservative recovery."""
import contextlib
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_deck as render


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.deck = self.root / 'deck.json'
        self.deck.write_text(json.dumps({'allow_text_only': True,
            'slides': [{'title': '合成安装测试', 'body': '非科研结果'}]}), encoding='utf-8')
        self.config = {'path': None, 'values': {}, 'sources': {}, 'persistence': {}}
        self.config_patch = patch.object(render, 'load_config', return_value=self.config)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def fail(self, stage='libreoffice', *, html_preview=False):
        def export(pptx, pdf, pages, *, stage_callback, **kwargs):
            if stage == 'png':
                pdf.write_bytes(b'PDF fixture')
                stage_callback('libreoffice', 'passed', {'runner': {'ok': True}})
            raise render.ExportFailure('注入故障 😀', stage,
                                       {'runner': {'ok': False, 'error': 'injected'}, 'stderr': '完整错误'})
        with patch.object(render, 'export_pptx', side_effect=export):
            with self.assertRaises(render.RenderFailure) as error:
                render.render(self.deck, self.root, 'report', pdf_render=True, html_preview=html_preview)
        return error.exception.manifest

    @staticmethod
    def export_ok(pptx, pdf, pages, *, stage_callback, **kwargs):
        pdf.write_bytes(b'PDF fixture')
        stage_callback('libreoffice', 'passed', {'runner': {'ok': True}})
        for page in pages:
            Image.new('RGB', (1600, 900), 'white').save(page)
        stage_callback('png', 'passed', {})

    def test_failure_retains_pptx_and_complete_diagnostics(self):
        manifest = self.fail()
        saved = json.loads(Path(manifest['files']['manifest']).read_text(encoding='utf-8'))
        self.assertFalse(saved['ok'])
        self.assertEqual(saved['stages']['pptx'], 'passed')
        self.assertEqual(saved['stages']['structure'], 'passed')
        self.assertEqual(saved['stages']['libreoffice'], 'failed')
        self.assertEqual(saved['stages']['visual'], 'not_run')
        self.assertTrue(Path(saved['files']['pptx']).is_file())
        report = json.loads(Path(saved['diagnostics']['libreoffice']).read_text(encoding='utf-8'))
        self.assertEqual(report['stderr'], '完整错误')

    def test_resume_reuses_exact_pptx_and_preserves_old_manifest(self):
        for stage in ('libreoffice', 'png'):
            with self.subTest(stage=stage):
                failed = self.fail(stage)
                path = Path(failed['files']['manifest'])
                old = path.read_bytes()
                with patch.object(render, 'export_pptx', side_effect=self.export_ok), patch.object(render, 'make_pptx') as make:
                    result = render.resume_render(path)
                    make.assert_not_called()
                self.assertEqual(path.read_bytes(), old)
                self.assertEqual(result['files']['pptx'], failed['files']['pptx'])
                self.assertNotEqual(Path(result['files']['pdf']).parent, path.parent)
                self.assertEqual(result['pptx_sha256'], failed['pptx_sha256'])
                self.assertEqual(result['status'], 'rendered_visual_pending')
                self.assertEqual(result['stages']['visual'], 'not_run')

    def test_resume_rejects_changed_pptx_and_manual_failure(self):
        failed = self.fail()
        path = Path(failed['files']['manifest'])
        Path(failed['files']['pptx']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash/state'):
            render.resume_render(path)
        failed['failed_stage'] = 'visual'
        path.write_text(json.dumps(failed), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'manual check'):
            render.resume_render(path)

    def test_html_preview_is_opt_in_and_embeds_the_rendered_pages(self):
        for enabled in (False, True):
            with self.subTest(html_preview=enabled), patch.object(render, 'export_pptx', side_effect=self.export_ok):
                result = render.render(self.deck, self.root, 'preview', daily_report=not enabled,
                                       html_preview=enabled)
            self.assertEqual(result['html_preview'], enabled)
            self.assertEqual('html' in result['files'], enabled)
            self.assertEqual('html' in result['stages'], enabled)
            if enabled:
                path = Path(result['files']['html'])
                encoded_page = base64.b64encode(Path(result['files']['png'][0]).read_bytes()).decode()
                self.assertIn('data:image/png;base64,' + encoded_page, path.read_text(encoding='utf-8'))
                self.assertEqual(result['file_hashes'][str(path)], render.file_hash(path))
                self.assertEqual(result['stages']['html'], 'passed')
            else:
                self.assertFalse((self.root / f"{result['stem']}.html").exists())
                self.assertFalse(any(path.endswith('.html') for path in result['file_hashes']))

    def test_resume_preserves_html_intent_or_accepts_an_explicit_override(self):
        for original, override, expected in [(False, None, False), (True, None, True),
                                              (False, True, True), (True, False, False)]:
            with self.subTest(original=original, override=override):
                failed = self.fail(html_preview=original)
                self.assertNotIn('html', failed['files'])
                saved = Path(failed['files']['manifest'])
                original_manifest = saved.read_bytes()
                original_pptx = Path(failed['files']['pptx']).read_bytes()
                with patch.object(render, 'export_pptx', side_effect=self.export_ok):
                    result = render.resume_render(saved, html_preview=override)
                self.assertEqual(result['html_preview'], expected)
                self.assertEqual('html' in result['files'], expected)
                self.assertEqual(saved.read_bytes(), original_manifest)
                self.assertEqual(Path(failed['files']['pptx']).read_bytes(), original_pptx)

    def test_resume_legacy_v3_infers_html_from_files(self):
        failed = self.fail()
        del failed['html_preview']
        failed['files']['html'] = str(self.root / 'legacy.html')
        saved = Path(failed['files']['manifest'])
        saved.write_text(json.dumps(failed), encoding='utf-8')
        with patch.object(render, 'export_pptx', side_effect=self.export_ok):
            result = render.resume_render(saved)
        self.assertTrue(result['html_preview'])
        self.assertTrue(Path(result['files']['html']).is_file())
        self.assertFalse((self.root / 'legacy.html').exists())

    def test_html_failure_retains_intent_without_claiming_a_generated_file(self):
        def occupy_html(pptx, pdf, pages, **kwargs):
            self.export_ok(pptx, pdf, pages, **kwargs)
            (Path(pptx).parent / (Path(pptx).stem + '.html')).write_text('User content', encoding='utf-8')
        with patch.object(render, 'export_pptx', side_effect=occupy_html):
            with self.assertRaises(render.RenderFailure) as error:
                render.render(self.deck, self.root, 'occupied', html_preview=True)
        failed = error.exception.manifest
        self.assertEqual(failed['failed_stage'], 'html')
        self.assertEqual(failed['stages']['html'], 'failed')
        self.assertTrue(failed['html_preview'])
        self.assertNotIn('html', failed['files'])
        self.assertEqual((self.root / 'occupied.html').read_text(encoding='utf-8'), 'User content')
        with patch.object(render, 'export_pptx', side_effect=self.export_ok):
            result = render.resume_render(failed['files']['manifest'])
        self.assertTrue(Path(result['files']['html']).is_file())
        self.assertNotEqual(Path(result['files']['html']).parent, self.root)

    def test_cli_preview_defaults_and_overrides(self):
        for mode in ('deck', 'resume-manifest'):
            for flags, expected in [([], None),
                                    (['--html-preview'], True), (['--no-html-preview'], False)]:
                with self.subTest(mode=mode, flags=flags):
                    args = ['--' + mode, 'input.json', '--output-dir', str(self.root), '--base-name', 'cli', *flags]
                    target = 'render' if mode == 'deck' else 'resume_render'
                    with patch.object(render, target, return_value={'ok': True}) as call, contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(render.main(args), 0)
                    self.assertEqual(call.call_args.kwargs['html_preview'],
                                     (False if mode == 'deck' else None) if expected is None else expected)
                    self.assertEqual(call.call_args.kwargs['pdf_render'], None)
                    if mode == 'deck':
                        self.assertFalse(call.call_args.kwargs['daily_report'])
        with patch.object(render, 'render', return_value={'ok': True}) as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(render.main(['--deck', 'input.json', '--output-dir', str(self.root), '--base-name', 'daily', '--daily-report']), 0)
        self.assertTrue(call.call_args.kwargs['daily_report'])
        self.assertIsNone(call.call_args.kwargs['pdf_render'])
        with patch.object(render, 'render', return_value={'ok': True}) as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(render.main(['--deck', 'input.json', '--output-dir', str(self.root), '--base-name', 'daily', '--daily-report', '--pdf-render']), 0)
        self.assertTrue(call.call_args.kwargs['daily_report'])
        self.assertTrue(call.call_args.kwargs['pdf_render'])
        for flag, expected in [('--pdf-render', True), ('--no-pdf-render', False)]:
            with patch.object(render, 'resume_render', return_value={'ok': True}) as call, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(render.main(['--resume-manifest', 'input.json', '--output-dir', str(self.root), '--base-name', 'cli', flag]), 0)
            self.assertEqual(call.call_args.kwargs['pdf_render'], expected)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            render.main(['--resume-manifest', 'failed.json', '--html-preview', '--no-html-preview'])
        self.assertEqual(error.exception.code, 2)

    def test_generation_failure_is_reported_and_not_resumable(self):
        with patch.object(render, 'make_pptx', side_effect=ValueError('generation failed')):
            with self.assertRaises(render.RenderFailure) as error:
                render.render(self.deck, self.root, 'generation', daily_report=True)
        result = error.exception.manifest
        self.assertEqual(result['failed_stage'], 'pptx')
        self.assertFalse(Path(result['files']['pptx']).exists())
        with self.assertRaises(ValueError):
            render.resume_render(result['files']['manifest'])

    def test_resume_does_not_adopt_change_after_initial_validation(self):
        failed = self.fail()
        original = render.inspect_pptx
        def inspect_and_change(path, expected):
            count = original(path, expected)
            Path(path).write_bytes(Path(path).read_bytes() + b'concurrent edit')
            return count
        with patch.object(render, 'inspect_pptx', side_effect=inspect_and_change), patch.object(render, 'export_pptx') as export:
            with self.assertRaisesRegex(render.RenderFailure, 'changed after resume validation'):
                render.resume_render(failed['files']['manifest'])
            export.assert_not_called()

    def test_diagnostics_failure_preserves_original_error(self):
        actual = render.atomic_write_json
        def write(path, payload):
            if not str(path).endswith('.manifest.json'):
                raise PermissionError('diagnostics refused')
            return actual(path, payload)
        with patch.object(render, 'atomic_write_json', side_effect=write):
            manifest = self.fail()
        self.assertEqual(manifest['error'], '注入故障 😀')
        self.assertIn('diagnostics refused', manifest['diagnostic_write_errors'])
        self.assertEqual(manifest['diagnostic_details']['libreoffice']['stderr'], '完整错误')
        self.assertEqual(manifest['diagnostic_details']['libreoffice']['runner']['error'], 'injected')

    def test_first_manifest_write_failure_is_explicit(self):
        stderr = io.StringIO()
        with patch.object(render, 'atomic_write_json', side_effect=PermissionError('disk denied')), contextlib.redirect_stderr(stderr):
            with self.assertRaises(render.RenderFailure) as error:
                render.render(self.deck, self.root, 'no-manifest', daily_report=True)
        self.assertIn('recovery is not confirmed', str(error.exception))
        self.assertEqual(error.exception.manifest['failed_stage'], 'manifest')
        self.assertFalse((self.root / 'no-manifest.manifest.json').exists())
        self.assertIn('manifest_write_error', stderr.getvalue())

    def test_later_manifest_failure_keeps_last_valid_state(self):
        actual = render.atomic_write_json
        count = 0
        def write(path, payload):
            nonlocal count
            if str(path).endswith('.manifest.json'):
                count += 1
                if count > 2:
                    raise PermissionError('replace denied')
            return actual(path, payload)
        with patch.object(render, 'atomic_write_json', side_effect=write), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(render.RenderFailure) as error:
                render.render(self.deck, self.root, 'partial', daily_report=True)
        self.assertEqual(error.exception.manifest['failed_stage'], 'manifest')
        saved = json.loads((self.root / 'partial.manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['stages']['pptx'], 'passed')
        self.assertEqual(saved['stages']['structure'], 'not_run')
        self.assertTrue(Path(saved['files']['pptx']).exists())

    def test_cli_emits_utf8_json_under_gbk_for_input_errors(self):
        env = dict(os.environ, PYTHONIOENCODING='gbk')
        missing = self.root / '不存在😀.json'
        script = Path(render.__file__)
        result = subprocess.run([sys.executable, str(script), '--deck', str(missing),
            '--output-dir', str(self.root), '--base-name', '中文'], capture_output=True, env=env)
        payload = json.loads(result.stdout.decode('utf-8'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('不存在😀', payload['error'])


if __name__ == '__main__':
    unittest.main()
