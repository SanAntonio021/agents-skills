"""Focused byte preservation, file protection, and CLI tests; no model calls."""

import codecs
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "exact_edit.py"
SPEC = importlib.util.spec_from_file_location("exact_edit", SCRIPT)
exact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exact)
TITLE = "# \u6d4b\u8bd5\u7ed3\u679c"
FIRST = "\u901f\u7387\u4e3a100 Gbps\u3002"
SECOND = "\u8ddd\u79bb\u4e3a1 km\u3002"
APPEND = "\u4ee5\u4e0a\u4e3a\u7528\u6237\u786e\u8ba4\u539f\u53e5\u3002"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ByteTests(unittest.TestCase):
    def test_shared_flow_links_narrow_exact_edit_reference(self):
        root = SCRIPT.parents[1]
        common = (root / 'references/common-quality.md').read_text(encoding='utf-8')
        reference = (root / 'references/exact-edit.md').read_text(encoding='utf-8')
        self.assertIn('(exact-edit.md)', common)
        self.assertIn('(../scripts/exact_edit.py)', reference)
        self.assertIn('edit_bytes', reference)
        self.assertIn('validate_bytes', reference)
        self.assertIn('--source-sha256', reference)

    def test_title_append_newline_bom_matrix(self):
        for nl in (b"\n", b"\r\n"):
            for bom in (b"", codecs.BOM_UTF8):
                for trailing in (b"", nl):
                    for title, append in ((TITLE, None), (None, APPEND), (TITLE, APPEND)):
                        with self.subTest(nl=nl, bom=bom, trailing=trailing, title=title, append=append):
                            body = FIRST.encode() + nl + SECOND.encode() + trailing
                            source = bom + body
                            expected = bom + (TITLE.encode() + nl if title else b"") + body
                            if append:
                                expected += (b"" if trailing else nl) + APPEND.encode()
                            actual = exact.edit_bytes(source, sha(source), title=title, append=append)
                            self.assertEqual(expected, actual)
                            self.assertIn(body, actual)
                            self.assertTrue(exact.validate_bytes(
                                source, actual, sha(source), title=title, append=append,
                            )["ok"])

    def test_single_line_defaults_to_lf_without_forced_final_newline(self):
        source = FIRST.encode()
        self.assertEqual(
            f"{TITLE}\n{FIRST}\n{APPEND}".encode(),
            exact.edit_bytes(source, sha(source), title=TITLE, append=APPEND),
        )

    def test_empty_and_bom_only_sources(self):
        for source in (b"", codecs.BOM_UTF8):
            with self.subTest(source=source):
                self.assertEqual(source + TITLE.encode() + b"\n" + APPEND.encode(),
                                 exact.edit_bytes(source, sha(source), title=TITLE, append=APPEND))
                self.assertEqual(source + APPEND.encode(),
                                 exact.edit_bytes(source, sha(source), append=APPEND))

    def test_only_missing_boundary_newlines_are_added(self):
        source = b"\r\n" + FIRST.encode() + b"\r\n\r\n"
        append = "\r\n  " + APPEND + "  \n"
        self.assertEqual(TITLE.encode() + source + append.encode(),
                         exact.edit_bytes(source, sha(source), title=TITLE, append=append))
        source = FIRST.encode()
        self.assertEqual(source + append.encode(), exact.edit_bytes(source, sha(source), append=append))

    def test_mixed_newlines_and_whitespace_remain_exact(self):
        source = ("  " + FIRST + "\r\n\t" + SECOND + "\n  ").encode()
        self.assertEqual(TITLE.encode() + b"\r\n" + source + b"\r\n" + APPEND.encode(),
                         exact.edit_bytes(source, sha(source), title=TITLE, append=APPEND))
        source = b"a\nb\r\nc"
        self.assertEqual(b"T\n" + source + b"\nS",
                         exact.edit_bytes(source, sha(source), title="T", append="S"))

    def test_rejects_moved_sentence_changed_number_and_extra_comment(self):
        source = f"{FIRST}\n{SECOND}".encode()
        correct = f"{TITLE}\n{FIRST}\n{SECOND}\n{APPEND}".encode()
        candidates = (
            f"{TITLE}\n{SECOND}\n{FIRST}\n{APPEND}".encode(),
            correct.replace(b"100", b"120"),
            correct + "\n\u4fee\u6539\u8bf4\u660e\uff1a\u5df2\u6dfb\u52a0\u6807\u9898\u3002".encode(),
            correct + b"\n",
            codecs.BOM_UTF8 + correct,
            correct.replace(b"\n", b"\r\n"),
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                result = exact.validate_bytes(source, candidate, sha(source), title=TITLE, append=APPEND)
                self.assertFalse(result["ok"])
                self.assertEqual("candidate_mismatch", result["error"])

    def test_validation_is_tied_to_the_exact_operation(self):
        source = FIRST.encode()
        candidate = exact.edit_bytes(source, sha(source), title=TITLE, append=APPEND)
        self.assertFalse(exact.validate_bytes(source, candidate, sha(source), title=TITLE)["ok"])

    def test_hash_includes_bom_and_line_endings(self):
        source = b"a\nb"
        for changed in (b"a\r\nb", codecs.BOM_UTF8 + source, source + b"\n"):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(exact.ExactEditError, "SHA256"):
                    exact.edit_bytes(changed, sha(source), title=TITLE)
                with self.assertRaises(exact.ExactEditError):
                    exact.validate_bytes(changed, changed, sha(source), title=TITLE)
        self.assertEqual(TITLE.encode() + b"\n" + source,
                         exact.edit_bytes(source, sha(source).upper(), title=TITLE))

    def test_invalid_hash_operations_and_utf8(self):
        for digest in ("", "0" * 63, "g" * 64, "0" * 64):
            with self.subTest(digest=digest), self.assertRaises(exact.ExactEditError):
                exact.edit_bytes(b"body", digest, title=TITLE)
        for operation in ({}, {"title": ""}, {"append": ""}, {"title": "a\nb"},
                          {"title": "a\rb"}, {"title": "\ufeffa"}, {"append": "\ud800"}):
            with self.subTest(operation=operation), self.assertRaises(exact.ExactEditError):
                exact.edit_bytes(b"body", sha(b"body"), **operation)
        with self.assertRaises(exact.ExactEditError):
            exact.edit_bytes(b"\xff", sha(b"\xff"), title=TITLE)
        with self.assertRaises(exact.ExactEditError):
            exact.validate_bytes(b"body", b"\xff", sha(b"body"), title=TITLE)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.txt"
        self.output = self.root / "new.txt"
        self.original = codecs.BOM_UTF8 + f"{FIRST}\r\n{SECOND}".encode()
        self.source.write_bytes(self.original)
        self.digest = sha(self.original)

    def apply(self, **kwargs):
        return exact.apply_file(self.source, self.output, self.digest, title=TITLE, append=APPEND, **kwargs)

    def cli(self, action="apply", *extra):
        args = [sys.executable, "-B", str(SCRIPT), action,
                "--source", str(self.source), "--source-sha256", self.digest,
                "--title", TITLE, "--append", APPEND,
                "--output" if action == "apply" else "--candidate", str(self.output), *extra]
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual("", proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(proc.returncode == 0, result["ok"])
        return proc.returncode, result

    def test_creates_new_file_and_preserves_source(self):
        receipt = self.apply()
        self.assertTrue(receipt["ok"])
        self.assertEqual(sha(self.output.read_bytes()), receipt["output_sha256"])
        self.assertEqual(self.original, self.source.read_bytes())
        self.assertTrue(exact.validate_file(
            self.source, self.output, self.digest, title=TITLE, append=APPEND,
        )["ok"])

    def test_existing_target_and_source_are_not_overwritten(self):
        self.output.write_bytes(b"user changes")
        with self.assertRaises(exact.ExactEditError) as caught:
            self.apply()
        self.assertEqual("target_exists", caught.exception.code)
        self.assertEqual(b"user changes", self.output.read_bytes())
        with self.assertRaises(exact.ExactEditError) as caught:
            exact.apply_file(self.source, self.source, self.digest, title=TITLE)
        self.assertEqual("source_overwrite", caught.exception.code)
        self.assertEqual(self.original, self.source.read_bytes())

    def test_hardlink_to_source_is_not_overwritten(self):
        os.link(self.source, self.output)
        with self.assertRaises(exact.ExactEditError) as caught:
            self.apply()
        self.assertEqual("source_overwrite", caught.exception.code)
        self.assertEqual(self.original, self.source.read_bytes())

    def test_changed_hash_prevents_creation(self):
        changed = self.original.replace(b"100", b"120")
        self.source.write_bytes(changed)
        code, result = self.cli()
        self.assertNotEqual(0, code)
        self.assertEqual("hash_mismatch", result["error"])
        self.assertFalse(self.output.exists())
        self.assertEqual(changed, self.source.read_bytes())

    def test_hash_change_during_preflight_prevents_creation(self):
        read = exact._read_regular
        calls = 0

        def change_before_second_read(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.source.write_bytes(b"user update")
            return read(path)

        with patch.object(exact, "_read_regular", side_effect=change_before_second_read):
            with self.assertRaises(exact.ExactEditError) as caught:
                self.apply()
        self.assertEqual("hash_mismatch", caught.exception.code)
        self.assertFalse(self.output.exists())
        self.assertEqual(b"user update", self.source.read_bytes())

    def test_exclusive_creation_handles_target_race(self):
        original_open = Path.open

        def race(path, mode="r", *args, **kwargs):
            if path == self.output and mode == "xb":
                with original_open(path, "wb") as stream:
                    stream.write(b"created by user")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", race):
            with self.assertRaises(exact.ExactEditError) as caught:
                self.apply()
        self.assertEqual("target_exists", caught.exception.code)
        self.assertEqual(b"created by user", self.output.read_bytes())
        self.assertEqual(self.original, self.source.read_bytes())

    def test_non_regular_inputs_and_missing_parent(self):
        with self.assertRaises(exact.ExactEditError):
            exact.apply_file(self.root, self.output, self.digest, title=TITLE)
        with self.assertRaises(exact.ExactEditError):
            exact.validate_file(self.source, self.root, self.digest, title=TITLE)
        with self.assertRaises(OSError):
            exact.apply_file(self.source, self.root / "missing" / "new.txt", self.digest, title=TITLE)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / "missing").exists())

    def make_link(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")

    def test_symlink_input_and_candidate_are_rejected(self):
        link = self.root / "linked.txt"
        self.make_link(link, self.source)
        with self.assertRaises(exact.ExactEditError) as caught:
            exact.apply_file(link, self.output, self.digest, title=TITLE)
        self.assertEqual("link_rejected", caught.exception.code)
        with self.assertRaises(exact.ExactEditError):
            exact.validate_file(self.source, link, self.digest, title=TITLE)
        self.assertFalse(self.output.exists())

    def test_dangling_output_symlink_is_rejected(self):
        absent = self.root / "absent.txt"
        self.make_link(self.output, absent)
        with self.assertRaises(exact.ExactEditError) as caught:
            self.apply()
        self.assertEqual("link_rejected", caught.exception.code)
        self.assertFalse(absent.exists())

    def test_parent_symlink_escape_and_dotdot_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "linked-dir"
        self.make_link(link, outside, directory=True)
        for output in (link / "escaped.txt", link / ".." / "escaped.txt"):
            with self.subTest(output=output), self.assertRaises(exact.ExactEditError) as caught:
                exact.apply_file(self.source, output, self.digest, title=TITLE)
            self.assertEqual("link_rejected", caught.exception.code)
        self.assertEqual([], list(outside.iterdir()))
        self.assertFalse((self.root / "escaped.txt").exists())
        (outside / "source.txt").write_bytes(self.original)
        with self.assertRaises(exact.ExactEditError):
            exact.apply_file(link / "source.txt", self.output, self.digest, title=TITLE)

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_windows_junction_parent_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        junction = self.root / "junction"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                              capture_output=True, timeout=15)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.addCleanup(os.rmdir, junction)
        with self.assertRaises(exact.ExactEditError) as caught:
            exact.apply_file(self.source, junction / "escaped.txt", self.digest, title=TITLE)
        self.assertEqual("link_rejected", caught.exception.code)
        self.assertEqual([], list(outside.iterdir()))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO is POSIX-only")
    def test_fifo_is_rejected_without_opening(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(exact.ExactEditError):
            exact.apply_file(fifo, self.output, self.digest, title=TITLE)

    def test_cli_apply_and_verify_structured_success(self):
        self.assertEqual(0, self.cli()[0])
        self.assertEqual(0, self.cli("verify")[0])
        self.assertEqual(self.original, self.source.read_bytes())

    def test_cli_mismatch_hash_and_existing_target_fail_without_success(self):
        self.output.write_bytes(b"candidate with extra commentary")
        for action, error in (("verify", "candidate_mismatch"), ("apply", "target_exists")):
            with self.subTest(action=action):
                code, result = self.cli(action)
                self.assertNotEqual(0, code)
                self.assertEqual(error, result["error"])
        code, result = self.cli("verify", "--source-sha256", "0" * 64)
        self.assertNotEqual(0, code)
        self.assertEqual("hash_mismatch", result["error"])
        self.assertEqual(b"candidate with extra commentary", self.output.read_bytes())

    def test_cli_bad_arguments_utf8_and_missing_input_are_structured(self):
        code, result = self.cli("apply", "--unknown")
        self.assertNotEqual(0, code)
        self.assertEqual("argument_error", result["error"])
        self.source.write_bytes(b"\xff")
        self.digest = sha(b"\xff")
        code, result = self.cli()
        self.assertNotEqual(0, code)
        self.assertEqual("invalid_utf8", result["error"])
        self.source.unlink()
        code, result = self.cli()
        self.assertNotEqual(0, code)
        self.assertEqual("io_error", result["error"])
        self.assertFalse(self.output.exists())

    def test_cli_write_failure_does_not_report_success(self):
        stdout = io.StringIO()
        with patch.object(exact.os, "fsync", side_effect=OSError("simulated disk error")):
            with redirect_stdout(stdout):
                code = exact.main([
                    "apply", "--source", str(self.source), "--output", str(self.output),
                    "--source-sha256", self.digest, "--title", TITLE,
                ])
        result = json.loads(stdout.getvalue())
        self.assertNotEqual(0, code)
        self.assertFalse(result["ok"])
        self.assertEqual("io_error", result["error"])
        self.assertEqual(self.original, self.source.read_bytes())

    def test_cli_readback_mismatch_does_not_report_success(self):
        read = exact._read_regular

        def changed_output(path):
            if Path(path) == self.output:
                self.output.write_bytes(b"external output change")
            return read(path)

        stdout = io.StringIO()
        with patch.object(exact, "_read_regular", side_effect=changed_output):
            with redirect_stdout(stdout):
                code = exact.main([
                    "apply", "--source", str(self.source), "--output", str(self.output),
                    "--source-sha256", self.digest, "--title", TITLE,
                ])
        result = json.loads(stdout.getvalue())
        self.assertNotEqual(0, code)
        self.assertFalse(result["ok"])
        self.assertEqual("write_verification_failed", result["error"])
        self.assertEqual(b"external output change", self.output.read_bytes())
        self.assertEqual(self.original, self.source.read_bytes())


if __name__ == "__main__":
    unittest.main()
