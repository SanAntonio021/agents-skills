"""Fake-only tests: no test dispatches or attaches to real Word."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reference_word as word_eval


class Collection:
    def __init__(self, items=()):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        if isinstance(index, str):
            return next(item for item in self.items if item.Name == index)
        return self.items[index - 1]

    def Update(self):
        raise AssertionError("blanket Fields.Update is forbidden")


class FakeField:
    def __init__(self, instruction, start, *, result="old", locked=False,
                 target="1", changing=False, nested=False, update_ok=True):
        self.Code = SimpleNamespace(Text=instruction, Start=start, Fields=Collection([object()] if nested else []))
        self.Result = SimpleNamespace(Text=result, Fields=Collection())
        self.Locked = locked
        self.target = target
        self.changing = changing
        self.update_ok = update_ok
        self.events = []
        self.updates = 0

    def Update(self):
        self.events.append(self.Code.Text.split()[0].upper())
        self.updates += 1
        self.Result.Text = str(self.updates) if self.changing else self.target
        return self.update_ok


class FakeRange:
    def __init__(self, fields=(), shapes=()):
        self.Fields = Collection(fields)
        self.ShapeRange = Collection(shapes)


def shape(name, fields=(), *, children=()):
    return SimpleNamespace(
        Name=name, Type=6 if children else 17, GroupItems=Collection(children),
        TextFrame=SimpleNamespace(TextRange=FakeRange(fields), Next=None, Previous=None),
    )


class FakeOptions:
    def __init__(self, app):
        object.__setattr__(self, "app", app)
        object.__setattr__(self, "values", {name: True for name in word_eval.WORD_OPTIONS})

    def __getattr__(self, name):
        if self.app.option_read_failure == name:
            raise RuntimeError("option read refused")
        return self.values[name]

    def __setattr__(self, name, value):
        self.app.events.append((name, value))
        if self.app.option_set_failure == name and value is False:
            raise RuntimeError("option set refused")
        if self.app.option_restore_failure == name and value is True:
            raise RuntimeError("option restore refused")
        self.values[name] = value


class FakeDocument:
    def __init__(self, app, path, read_only, ranges):
        self.app, self.path, self.ReadOnly = app, path, read_only
        self.ranges = ranges
        self.Content = ranges["main"]
        self.StoryRanges = SimpleNamespace(Item=lambda kind: ranges[{2: "footnotes", 3: "endnotes"}[kind]])
        self.Sections = Collection(app.sections(ranges))
        self.Saved = False
        self.closed = False
        for item in all_fields(ranges):
            item.events = app.events

    def Repaginate(self):
        self.app.events.append("repaginate")
        if self.app.repagination_mutation:
            self.app.repagination_mutation(self.ranges)

    def Save(self):
        self.app.events.append("save")
        if self.app.save_failure:
            raise RuntimeError("save failed")
        state = {key: [field.Result.Text for field in rng.Fields.items] for key, rng in self.ranges.items()}
        with ZipFile(self.path, "a") as package:
            package.writestr("test-results.json", json.dumps(state))
        self.Saved = True
        if self.app.save_mutation:
            self.app.save_mutation(self.ranges)

    def Close(self, save_changes):
        assert save_changes is False
        self.app.events.append("close")
        if self.app.close_failure:
            raise RuntimeError("close failed")
        if not self.closed:
            self.app.Documents.items.remove(self)
            self.closed = True


def all_fields(ranges):
    for rng in ranges.values():
        yield from rng.Fields.items


class FakeDocuments(Collection):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.open_calls = []

    def Open(self, **kwargs):
        self.open_calls.append(kwargs)
        self.app.events.append("reopen" if kwargs["ReadOnly"] else "open")
        assert self.app.AutomationSecurity == 3
        assert not any(self.app.Options.values.values())
        if self.app.open_failure or (kwargs["ReadOnly"] and self.app.reopen_failure):
            raise RuntimeError("open failed")
        path = Path(kwargs["FileName"])
        assert path != self.app.source
        with ZipFile(path) as package:
            settings = word_eval.ET.fromstring(package.read("word/settings.xml"))
            assert settings.find(word_eval.W + "updateFields").get(word_eval.W + "val") == "false"
            state = json.loads(package.read("test-results.json")) if kwargs["ReadOnly"] else None
        ranges = copy.deepcopy(self.app.ranges)
        if state is not None:
            for key, values in state.items():
                for field, value in zip(ranges[key].Fields.items, values):
                    field.Result.Text = value
            if self.app.reopen_mutation:
                self.app.reopen_mutation(ranges)
        document = FakeDocument(self.app, path, kwargs["ReadOnly"], ranges)
        self.items.append(document)
        return document


class FakeWordApplication:
    def __init__(self, source, ranges):
        self.source = source
        self.ranges = ranges
        self.events = []
        self.Documents = FakeDocuments(self)
        self.Options = FakeOptions(self)
        self.option_read_failure = self.option_set_failure = self.option_restore_failure = None
        self.save_failure = self.open_failure = self.reopen_failure = self.close_failure = False
        self.reopen_mutation = None
        self.save_mutation = self.repagination_mutation = None
        self.macro_failure = False
        self.sections = lambda ranges: []
        self.quit_calls = 0

    def __setattr__(self, name, value):
        if name == "AutomationSecurity" and self.macro_failure:
            raise RuntimeError("macro security unavailable")
        object.__setattr__(self, name, value)

    def Quit(self):
        assert self.Documents.Count == 0
        self.events.append("quit")
        self.quit_calls += 1


class FakeComRuntime:
    def __init__(self):
        self.initialize_calls = self.uninitialize_calls = 0

    def CoInitialize(self):
        self.initialize_calls += 1

    def CoUninitialize(self):
        self.uninitialize_calls += 1


class ProcessTimeline:
    def __init__(self, responses):
        self.responses = list(responses)

    def __call__(self, image):
        assert image == "WINWORD.EXE"
        assert self.responses, "unexpected PID probe"
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.docx"
    with ZipFile(path, "w") as package:
        package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
        package.writestr("word/settings.xml", '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:updateFields w:val="true"/></w:settings>')
    return path


def descriptors(ranges):
    return [
        {"story": story, "ordinal": ordinal, "instruction": word_eval._normalize(field.Code.Text),
         "kind": field.Code.Text.split()[0].upper(), "locked": bool(field.Locked)}
        for story, rng in ranges.items()
        for ordinal, field in enumerate(sorted(rng.Fields.items, key=lambda item: item.Code.Start))
    ]


def run(source, *, ranges=None, expected=None, stories=None, application=None,
        pids=None, allow=True, output=None, runtime=None):
    ranges = ranges or {"main": FakeRange([FakeField("SEQ Figure", 1)])}
    app = application or FakeWordApplication(source, ranges)
    runtime = runtime or FakeComRuntime()
    original = source.read_bytes()
    result = word_eval.evaluate_copy(
        source, output or source.with_name("evaluated.docx"),
        descriptors(app.ranges) if expected is None else expected,
        stories or [{"id": "main", "kind": "main"}], allow_office_com=allow,
        dispatch_ex=lambda progid: app, com_runtime=runtime,
        process_ids=ProcessTimeline([[], [4242], []] if pids is None else pids),
        pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0,
    )
    assert source.read_bytes() == original
    if result.get("retained_workspace"):
        # Test-owned fake COM cannot hold real handles or processes.
        shutil.rmtree(result["retained_workspace"])
    return result, app, runtime


def test_dependency_order_save_reopen_options_and_owned_cleanup(source):
    fields = [FakeField(" REF target ", 10), FakeField("PAGEREF target", 20),
              FakeField("SEQ Figure", 30), FakeField("STYLEREF 1", 40),
              FakeField("DATE", 50, result="fixed")]
    result, app, runtime = run(source, ranges={"main": FakeRange(fields)})
    assert result["ok"] and result["status"] == "PASS"
    updates = [value for value in app.events if isinstance(value, str) and value in (*word_eval.KINDS, "repaginate")]
    assert updates == ["STYLEREF", "SEQ", "REF", "repaginate", "PAGEREF"] * 2
    assert result["passes"] == 2
    assert app.events.index("save") < app.events.index("close") < app.events.index("reopen") < app.events.index("quit")
    assert app.quit_calls == runtime.initialize_calls == runtime.uninitialize_calls == 1
    assert all(app.Options.values.values()) and result["options_restored"]
    assert result["ownership"]["owned_pids"] == [4242]
    assert result["ownership"]["cleanup"]["status"] == "CLEAN"
    assert result["persisted"]["save_reopen_verified"]
    assert result["persisted"]["field_count"] == 5
    assert all("result_sha256" in value and "result" not in value for value in result["persisted"]["fields"])
    output = Path(result["evaluation_output"])
    assert output.is_file() and word_eval.gate.sha256(output) == result["persisted"]["evaluation_sha256"]
    opened, reopened = app.Documents.open_calls
    assert opened["ReadOnly"] is False and reopened["ReadOnly"] is True
    assert opened["FileName"] == reopened["FileName"]
    assert Path(opened["FileName"]).parent != source.parent
    assert not Path(opened["FileName"]).exists()
    assert {key: value for key, value in opened.items() if key not in {"ReadOnly", "FileName"}} == {
        "ConfirmConversions": False, "AddToRecentFiles": False, "PasswordDocument": "",
        "PasswordTemplate": "", "Revert": False, "WritePasswordDocument": "",
        "WritePasswordTemplate": "", "Visible": False, "OpenAndRepair": False, "NoEncodingDialog": True,
    }


def test_nonconvergence_stops_at_five_without_save(source):
    result, app, _ = run(source, ranges={"main": FakeRange([FakeField("SEQ Figure", 1, changing=True)])})
    assert not result["ok"] and result["status"] == "NON_CONVERGENT"
    assert result["passes"] == 5 and app.events.count("SEQ") == 5
    assert "save" not in app.events and app.quit_calls == 1
    assert result["evaluation_output"] is None


def test_already_stable_uses_one_pass_without_repagination(source):
    result, app, _ = run(source, ranges={"main": FakeRange([FakeField("SEQ Figure", 1, result="1")])})
    assert result["ok"] and result["passes"] == 1
    assert "repaginate" not in app.events


@pytest.mark.parametrize("failure", ["consent", "source", "existing", "locked", "irrelevant"])
def test_refusals_never_launch_word(source, failure):
    output = source if failure == "source" else source.with_name("evaluated.docx")
    if failure == "existing":
        output.write_bytes(b"preserve existing output")
    ranges = {"main": FakeRange([FakeField("DATE" if failure == "irrelevant" else "SEQ Figure", 1, locked=failure == "locked")])}
    result, app, runtime = run(source, ranges=ranges, allow=failure != "consent", output=output)
    assert not result["ok"] and not app.Documents.open_calls
    assert runtime.initialize_calls == 0 and app.quit_calls == 0
    if failure == "existing":
        assert output.read_bytes() == b"preserve existing output"


@pytest.mark.parametrize("mismatch", ["missing", "extra", "instruction", "ordinal", "kind", "duplicate"])
def test_total_bijection_includes_unrelated_fields(source, mismatch):
    ranges = {"main": FakeRange([FakeField("DATE", 1), FakeField("SEQ Figure", 20)])}
    expected = descriptors(ranges)
    if mismatch == "missing":
        expected.pop(0)
        expected[0]["ordinal"] = 0
    elif mismatch == "extra":
        expected.append(dict(expected[-1], ordinal=2))
    elif mismatch == "instruction":
        expected[-1]["instruction"] = "SEQ Table"
    elif mismatch == "ordinal":
        expected[-1]["ordinal"] = 9
    elif mismatch == "kind":
        expected[-1]["kind"] = "REF"
    else:
        expected.append(dict(expected[-1]))
    result, app, _ = run(source, ranges=ranges, expected=expected)
    assert result["status"] == "FIELD_MAP_MISMATCH" and not result["ok"]
    assert not any(value in app.events for value in word_eval.KINDS)
    assert app.quit_calls == 1


def test_com_order_is_independent_and_whitespace_normalized(source):
    fields = [FakeField("SEQ Figure", 30), FakeField("DATE", 1), FakeField("REF\t target\n", 20)]
    result, _, _ = run(source, ranges={"main": FakeRange(fields)})
    assert result["ok"]
    assert [item["instruction"] for item in result["persisted"]["fields"]] == ["DATE", "REF target", "SEQ Figure"]


@pytest.mark.parametrize("nested", ["code", "result", "marker"])
def test_nested_fields_fail_explicitly(source, nested):
    field = FakeField("SEQ Figure", 1, nested=nested == "code")
    if nested == "result":
        field.Result.Fields = Collection([object()])
    elif nested == "marker":
        field.Code.Text += " \x13REF target\x15"
    result, app, _ = run(source, ranges={"main": FakeRange([field])})
    assert result["status"] == "UNSUPPORTED_NESTED_FIELD" and app.quit_calls == 1


def test_com_lock_not_reported_in_expected_still_refused(source):
    ranges = {"main": FakeRange([FakeField("SEQ Figure", 1, locked=True)])}
    expected = descriptors(ranges)
    expected[0]["locked"] = False
    result, app, _ = run(source, ranges=ranges, expected=expected)
    assert result["status"] == "LOCKED_FIELD" and "SEQ" not in app.events


@pytest.mark.parametrize("instruction", ["DATE", 'INCLUDETEXT "external.docx"'])
@pytest.mark.parametrize("expected_locked", [True, False])
def test_unrelated_locked_fields_remain_untouched_without_blocking_refresh(source, instruction, expected_locked):
    ranges = {"main": FakeRange([
        FakeField(instruction, 1, result="cached unrelated value", locked=True),
        FakeField("SEQ Figure", 20),
    ])}
    expected = descriptors(ranges)
    expected[0]["locked"] = expected_locked
    app = FakeWordApplication(source, ranges)
    observed = []
    def capture(rs):
        field = rs["main"].Fields.Item(1)
        observed.append((field.Code.Text, field.Result.Text, field.Locked, field.updates))
    app.save_mutation = app.reopen_mutation = capture
    result, app, _ = run(source, application=app, expected=expected)
    assert result["ok"] and result["status"] == "PASS"
    assert result["persisted"]["field_count"] == 2
    assert observed == [(instruction, "cached unrelated value", True, 0)] * 2
    assert instruction.split()[0] not in app.events
    assert app.events.count("SEQ") == 2
    with ZipFile(result["evaluation_output"]) as package:
        assert json.loads(package.read("test-results.json"))["main"] == ["cached unrelated value", "1"]


@pytest.mark.parametrize("property_name", word_eval.WORD_OPTIONS)
@pytest.mark.parametrize("failure", ["read", "set", "restore"])
def test_options_fail_closed_and_identify_failed_property(source, property_name, failure):
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)])})
    setattr(app, f"option_{failure}_failure", property_name)
    result, app, _ = run(source, application=app)
    assert not result["ok"] and property_name in result["error"]
    assert result["evaluation_output"] is None and app.quit_calls == 1
    assert all(value for key, value in app.Options.values.items() if key != property_name)
    if failure != "restore":
        assert not app.Documents.open_calls


def test_macro_security_is_required_not_best_effort(source):
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)])})
    app.macro_failure = True
    result, app, _ = run(source, application=app)
    assert result["status"] == "SECURITY_OPTIONS_FAILED"
    assert "AutomationSecurity" in result["error"] and not app.Documents.open_calls


@pytest.mark.parametrize("failure", ["open", "save", "reopen", "close"])
def test_com_operation_failure_restores_options_and_never_passes(source, failure):
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)])})
    setattr(app, failure + "_failure", True)
    result, app, runtime = run(source, application=app)
    assert not result["ok"] and all(app.Options.values.values())
    assert runtime.uninitialize_calls == 1
    assert app.quit_calls == (0 if failure == "close" else 1)
    assert result["evaluation_output"] is None


@pytest.mark.parametrize("mutation", ["value", "instruction", "count"])
def test_saved_read_only_reopen_must_match_keys_and_values(source, mutation):
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)])})
    def change(ranges):
        fields = ranges["main"].Fields.items
        if mutation == "value":
            fields[0].Result.Text = "not persisted"
        elif mutation == "instruction":
            fields[0].Code.Text = "SEQ Table"
        else:
            fields.append(FakeField("DATE", 20))
    app.reopen_mutation = change
    result, app, _ = run(source, application=app)
    assert not result["ok"] and "reopen" in app.events and app.quit_calls == 1
    assert result["evaluation_output"] is None


@pytest.mark.parametrize("pids,quit_calls", [([[99]], 0), ([[], []], 0), ([[], [42], [42]], 1), ([[], [42, 43]], 0)])
def test_exact_pid_ownership_and_cleanup_fail_closed(source, pids, quit_calls):
    result, app, _ = run(source, pids=pids)
    assert not result["ok"] and result["evaluation_output"] is None
    assert app.quit_calls == quit_calls
    if pids == [[99]]:
        assert not app.Documents.open_calls and result["status"] == "UNSAFE_PROCESS"


def test_no_positional_fallback_for_ambiguous_com_locations(source):
    result, _, _ = run(source, ranges={"main": FakeRange([FakeField("SEQ Figure", 1), FakeField("REF target", 1)])})
    assert result["status"] == "FIELD_MAP_MISMATCH"


def test_header_footer_notes_and_named_grouped_textbox_locators(source):
    ranges = {
        "main": FakeRange([FakeField("SEQ Figure", 1)]),
        "footnotes": FakeRange([FakeField("REF target", 1)]),
        "endnotes": FakeRange([FakeField("REF target", 1)]),
        "header:1:1": FakeRange([FakeField("REF target", 1)]),
        "footer:1:2": FakeRange([FakeField("PAGEREF target", 1)]),
        "textbox:header:1:1:Box": FakeRange([FakeField("REF target", 1)]),
    }
    box = shape("Box")
    box.TextFrame.TextRange = ranges["textbox:header:1:1:Box"]
    ranges["header:1:1"].ShapeRange = Collection([shape("Group", children=[box])])
    app = FakeWordApplication(source, ranges)
    app.sections = lambda rs: [SimpleNamespace(
        Headers=Collection([SimpleNamespace(Range=rs["header:1:1"], LinkToPrevious=False)]),
        Footers=Collection([None, SimpleNamespace(Range=rs["footer:1:2"], LinkToPrevious=False)]),
    )]
    stories = [{"id": key, "kind": key} for key in ("main", "footnotes", "endnotes")]
    stories += [
        {"id": "header:1:1", "kind": "header", "section": 1, "type": 1},
        {"id": "footer:1:2", "kind": "footer", "section": 1, "type": 2},
        {"id": "textbox:header:1:1:Box", "kind": "textbox", "parent": "header:1:1", "name": "Box"},
    ]
    result, _, _ = run(source, application=app, stories=stories)
    assert result["ok"] and result["persisted"]["field_count"] == 6


def test_alias_stories_are_deduplicated(source):
    rng = FakeRange([FakeField("SEQ Figure", 1)])
    ranges = {"main": FakeRange(), "header:1:1": rng, "header:2:1": rng}
    app = FakeWordApplication(source, ranges)
    app.sections = lambda rs: [
        SimpleNamespace(Headers=Collection([SimpleNamespace(Range=rs["header:1:1"], LinkToPrevious=False)])),
        SimpleNamespace(Headers=Collection([SimpleNamespace(Range=rs["header:2:1"], LinkToPrevious=True)])),
    ]
    stories = [{"id": "main", "kind": "main"}] + [
        {"id": f"header:{index}:1", "kind": "header", "section": index, "type": 1} for index in (1, 2)
    ]
    result, app, _ = run(source, application=app, stories=stories)
    assert result["ok"] and result["persisted"]["field_count"] == 1
    assert app.events.count("SEQ") == 2


def test_ambiguous_or_missing_textbox_fails_without_updates(source):
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)], [shape("Box"), shape("Box")])})
    stories = [{"id": "main", "kind": "main"}, {"id": "textbox:main:Box", "kind": "textbox", "parent": "main", "name": "Box"}]
    result, app, _ = run(source, application=app, stories=stories)
    assert not result["ok"] and result["status"] == "UNSUPPORTED_STORY"
    assert "SEQ" not in app.events


def test_field_update_false_is_failure(source):
    result, app, _ = run(source, ranges={"main": FakeRange([FakeField("SEQ Figure", 1, update_ok=False)])})
    assert result["status"] == "FIELD_UPDATE_FAILED" and "save" not in app.events


@pytest.mark.parametrize("code,normalized", [
    (' STYLEREF  "Heading  1"  \\n ', 'STYLEREF "Heading  1" \\n'),
    ('STYLEREF\t"Heading\t1" \n', 'STYLEREF "Heading\t1"'),
    (' REF\t target \n \\h', 'REF target \\h'),
])
def test_normalization_preserves_quoted_whitespace(code, normalized):
    assert word_eval._normalize(code) == normalized


def test_quoted_instruction_mismatch_does_not_use_positional_fallback(source):
    ranges = {"main": FakeRange([FakeField('STYLEREF "Heading  1"', 1)])}
    expected = descriptors(ranges)
    expected[0]["instruction"] = 'STYLEREF "Heading 1"'
    result, app, _ = run(source, ranges=ranges, expected=expected)
    assert result["status"] == "FIELD_MAP_MISMATCH" and "STYLEREF" not in app.events


def test_quoted_instruction_round_trip_preserves_key(source):
    result, _, _ = run(source, ranges={"main": FakeRange([FakeField(' STYLEREF  "Heading  1" ', 1)])})
    assert result["ok"]
    assert result["persisted"]["fields"][0]["instruction"] == 'STYLEREF "Heading  1"'


def test_fixed_point_can_arrive_on_fifth_pass(source, monkeypatch):
    update = FakeField.Update
    def saturating(field):
        ok = update(field)
        field.Result.Text = str(min(field.updates, 4))
        return ok
    monkeypatch.setattr(FakeField, "Update", saturating)
    result, app, _ = run(source)
    assert result["ok"] and result["passes"] == 5
    assert app.events.count("SEQ") == 5


def test_repagination_cannot_change_unrelated_fields(source):
    ranges = {"main": FakeRange([FakeField("PAGEREF target", 1), FakeField("DATE", 20)])}
    app = FakeWordApplication(source, ranges)
    app.repagination_mutation = lambda rs: setattr(rs["main"].Fields.Item(2).Result, "Text", "unexpected")
    result, app, _ = run(source, application=app)
    assert result["status"] == "UNRELATED_FIELD_CHANGED" and "save" not in app.events


def test_save_cannot_change_results_after_convergence(source):
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)])})
    app.save_mutation = lambda rs: setattr(rs["main"].Fields.Item(1).Result, "Text", "changed on save")
    result, app, _ = run(source, application=app)
    assert result["status"] == "PERSISTENCE_FAILED" and "reopen" not in app.events


def test_com_uninitialization_failure_cannot_publish(source):
    class BadRuntime(FakeComRuntime):
        def CoUninitialize(self):
            super().CoUninitialize()
            raise RuntimeError("uninitialize failed")
    result, app, _ = run(source, runtime=BadRuntime())
    assert not result["ok"] and result["status"] == "CLEANUP_FAILED"
    assert app.quit_calls == 1 and result["evaluation_output"] is None


def test_source_integrity_failure_cannot_publish(source, monkeypatch):
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)])})
    original_hash = word_eval.gate.sha256
    def changing_hash(path):
        if Path(path) == source and app.quit_calls:
            return "changed-source-hash"
        return original_hash(path)
    monkeypatch.setattr(word_eval.gate, "sha256", changing_hash)
    result, _, _ = run(source, application=app)
    assert result["status"] == "SOURCE_CHANGED" and result["evaluation_output"] is None


def test_output_race_does_not_overwrite_existing_file(source, monkeypatch):
    original_link = word_eval.os.link
    def collision(staging, output):
        Path(output).write_bytes(b"other writer")
        return original_link(staging, output)
    monkeypatch.setattr(word_eval.os, "link", collision)
    result, _, _ = run(source)
    assert not result["ok"]
    assert source.with_name("evaluated.docx").read_bytes() == b"other writer"
    assert not list(source.parent.glob(".reference-word-*"))


def test_unknown_process_state_never_dispatches(source):
    result, app, runtime = run(source, pids=[RuntimeError("PID probe failed")])
    assert not result["ok"] and not app.Documents.open_calls and app.quit_calls == 0
    assert runtime.initialize_calls == runtime.uninitialize_calls == 1


def test_security_readback_is_required(source, monkeypatch):
    original_set = FakeWordApplication.__setattr__
    def ignore_security(app, name, value):
        return original_set(app, name, 1 if name == "AutomationSecurity" else value)
    monkeypatch.setattr(FakeWordApplication, "__setattr__", ignore_security)
    result, app, _ = run(source)
    assert result["status"] == "SECURITY_OPTIONS_FAILED" and not app.Documents.open_calls


def test_linked_textbox_is_explicitly_unsupported(source):
    box = shape("Box")
    box.TextFrame.Next = object()
    app = FakeWordApplication(source, {"main": FakeRange([FakeField("SEQ Figure", 1)], [box])})
    stories = [{"id": "main", "kind": "main"}, {"id": "textbox:main:Box", "kind": "textbox", "parent": "main", "name": "Box"}]
    result, app, _ = run(source, application=app, stories=stories)
    assert result["status"] == "UNSUPPORTED_STORY" and "SEQ" not in app.events


def test_settings_rewrite_preserves_markup_compatibility_prefixes(source, tmp_path):
    settings = (
        '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14">'
        '<w:updateFields w:val="true"/></w:settings>'
    )
    separate = tmp_path / "compatibility.docx"
    with ZipFile(separate, "w") as package:
        package.writestr("word/settings.xml", settings)
    output = tmp_path / "temp-copy.docx"
    word_eval._prepare_copy(separate, output)
    with ZipFile(output) as package:
        root = word_eval.ET.fromstring(package.read("word/settings.xml"))
    assert "w14" in root.nsmap
    assert root.find(word_eval.W + "updateFields").get(word_eval.W + "val") == "false"


def test_native_dispatch_creates_new_late_bound_instance_without_cache_access(monkeypatch):
    registry_check = Mock(return_value=Path("C:/Microsoft Office/WINWORD.EXE"))
    monkeypatch.setattr(word_eval, "_registered_word_server", registry_check)
    interface, ole_object, dynamic_wrapper = object(), object(), object()
    dispatch_ex = Mock(return_value=SimpleNamespace(_oleobj_=ole_object))
    dynamic_dispatch = Mock(return_value=dynamic_wrapper)
    client = SimpleNamespace(DispatchEx=dispatch_ex, dynamic=SimpleNamespace(Dispatch=dynamic_dispatch))
    monkeypatch.setitem(sys.modules, "win32com", SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    monkeypatch.setitem(sys.modules, "pythoncom", SimpleNamespace(IID_IDispatch=interface))
    assert word_eval.native_dispatch("Word.Application") is dynamic_wrapper
    registry_check.assert_called_once_with("Word.Application")
    dispatch_ex.assert_called_once_with("Word.Application", resultCLSID=interface)
    dynamic_dispatch.assert_called_once_with(ole_object)


@pytest.mark.parametrize("injected", [False, True])
def test_evaluation_uses_native_dispatch_only_when_no_factory_is_injected(source, monkeypatch, injected):
    ranges = {"main": FakeRange([FakeField("SEQ Figure", 1)])}
    app = FakeWordApplication(source, ranges)
    default_factory, injected_factory = Mock(return_value=app), Mock(return_value=app)
    monkeypatch.setattr(word_eval, "native_dispatch", default_factory)
    result = word_eval.evaluate_copy(
        source, source.with_name("evaluated.docx"), descriptors(ranges), [{"id": "main", "kind": "main"}],
        allow_office_com=True, dispatch_ex=injected_factory if injected else None,
        com_runtime=FakeComRuntime(), process_ids=ProcessTimeline([[], [4242], []]),
        pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0,
    )
    assert result["ok"]
    (injected_factory if injected else default_factory).assert_called_once_with("Word.Application")
    (default_factory if injected else injected_factory).assert_not_called()


@pytest.mark.parametrize("consent", [False, True])
@pytest.mark.parametrize("passed", [False, True])
def test_check_cli_routes_read_only_gate_and_emits_exact_json(source, monkeypatch, capsys, consent, passed):
    payload = {"ok": passed, "status": "PASS" if passed else "UNVERIFIED", "source": str(source)}
    checker = Mock(return_value=payload)
    monkeypatch.setattr(word_eval.gate, "check_file", checker)
    original = source.read_bytes()
    argv = ["check", str(source)] + (["--allow-office-com", "--json"] if consent else [])
    assert word_eval.main(argv) == (0 if passed else 2)
    dispatcher = checker.call_args.kwargs["dispatch_ex"]
    checker.assert_called_once_with(
        source, "docx", allow_office_com=consent,
        dispatch_ex=dispatcher, require_render=False,
    )
    factory = Mock(return_value=object())
    monkeypatch.setattr(word_eval, "native_dispatch", factory)
    assert dispatcher("Word.Application") is factory.return_value
    factory.assert_called_once_with("Word.Application")
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out == json.dumps(payload, ensure_ascii=False) + "\n"
    assert source.read_bytes() == original


def test_check_cli_without_consent_never_dispatches(source, monkeypatch, capsys):
    factory = Mock(side_effect=AssertionError("native COM is forbidden in this test"))
    monkeypatch.setattr(word_eval, "native_dispatch", factory)
    original = source.read_bytes()
    assert word_eval.main(["check", str(source)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"] and result["status"] == "UNVERIFIED"
    factory.assert_not_called()
    assert source.read_bytes() == original


WORD_CLSID = "{000209FF-0000-0000-C000-000000000046}"
WORD_CLSID_KEY = r"Word.Application\CLSID"
WORD_SERVER_KEY = rf"CLSID\{WORD_CLSID}\LocalServer32"


class FakeRegistry:
    HKEY_CLASSES_ROOT, KEY_READ, REG_SZ, REG_EXPAND_SZ = object(), 0x20019, 1, 2

    def __init__(self, values):
        self.values = values
        self.opens = []
        self.queries = []

    def OpenKey(self, root, key, reserved, access):
        assert root is self.HKEY_CLASSES_ROOT and reserved == 0 and access == self.KEY_READ
        self.opens.append(key)
        if key not in self.values:
            raise FileNotFoundError("key absent")
        class Handle:
            def __enter__(self):
                return key

            def __exit__(self, *_args):
                return False
        return Handle()

    def QueryValueEx(self, key, name):
        self.queries.append((key, name))
        if name not in self.values[key]:
            raise FileNotFoundError("value absent")
        return self.values[key][name], self.REG_SZ


def install_registry(monkeypatch, server=None, *, missing=None):
    values = {WORD_CLSID_KEY: {"": WORD_CLSID}, WORD_SERVER_KEY: server or {}}
    if missing:
        del values[missing]
    registry = FakeRegistry(values)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    return registry


@pytest.mark.parametrize("server", [
    {"": '"C:/Program Files/Microsoft Office/WINWORD.EXE" /Automation'},
    {"": "C:/Program Files/Microsoft Office/WINWORD.EXE /Automation"},
    {"ServerExecutable": "C:/Program Files/Microsoft Office/WINWORD.EXE", "": "D:/Kingsoft/wps.exe /Automation"},
    {"ServerExecutable": '"C:/Program Files/Microsoft Office/WINWORD.EXE"'},
])
def test_registered_server_accepts_existing_absolute_word_paths(monkeypatch, server):
    registry = install_registry(monkeypatch, server)
    checked = []
    def exists(path):
        checked.append(str(path))
        return True
    monkeypatch.setattr(word_eval.Path, "is_file", exists)
    path = word_eval._registered_word_server("Word.Application")
    assert path == Path("C:/Program Files/Microsoft Office/WINWORD.EXE")
    assert checked == [str(path)]
    assert registry.opens == [WORD_CLSID_KEY, WORD_SERVER_KEY]
    if "ServerExecutable" in server:
        assert (WORD_SERVER_KEY, "") not in registry.queries


@pytest.mark.parametrize("server,missing,reason", [
    ({"": '"D:/Kingsoft/wps.exe" /Automation /private-token'}, None, "wps.exe"),
    ({"ServerExecutable": "D:/Kingsoft/wps.exe", "": '"C:/Office/WINWORD.EXE"'}, None, "wps.exe"),
    ({}, WORD_CLSID_KEY, "Word.Application\\CLSID"),
    ({}, WORD_SERVER_KEY, "LocalServer32"),
    ({}, None, "LocalServer32"),
    ({"": "WINWORD.EXE /Automation"}, None, "absolute Windows path"),
    ({"": "C:WINWORD.EXE /Automation"}, None, "absolute Windows path"),
    ({"": '"C:/Office/WINWORD.EXE"junk'}, None, "unambiguous executable"),
    ({"ServerExecutable": ""}, None, "nonempty registry string"),
    ({"ServerExecutable": "D:/Kingsoft/wps.exe /private-token"}, None, "malformed"),
])
def test_invalid_registration_refuses_before_dispatch_without_exposing_arguments(monkeypatch, server, missing, reason):
    install_registry(monkeypatch, server, missing=missing)
    dispatch = Mock(side_effect=AssertionError("COM activation forbidden"))
    monkeypatch.setitem(sys.modules, "win32com.client", SimpleNamespace(DispatchEx=dispatch, dynamic=SimpleNamespace(Dispatch=dispatch)))
    with pytest.raises(word_eval.EvaluationFailure) as failure:
        word_eval.native_dispatch("Word.Application")
    assert failure.value.status == "APP_UNAVAILABLE"
    assert reason in str(failure.value)
    assert "private-token" not in str(failure.value)
    dispatch.assert_not_called()


def test_registered_word_executable_must_exist(monkeypatch):
    install_registry(monkeypatch, {"ServerExecutable": "C:/Absent/WINWORD.EXE"})
    monkeypatch.setattr(word_eval.Path, "is_file", lambda path: False)
    with pytest.raises(word_eval.EvaluationFailure, match="does not exist") as failure:
        word_eval._registered_word_server("Word.Application")
    assert failure.value.status == "APP_UNAVAILABLE"


def test_check_cli_preserves_registration_refusal_from_unchanged_gate(source, monkeypatch, capsys):
    install_registry(monkeypatch, {"": "D:/Kingsoft/wps.exe /Automation"})
    check = word_eval.gate.check_file
    runtime = FakeComRuntime()
    def fake_runtime_check(*args, **kwargs):
        return check(*args, **kwargs, com_runtime=runtime,
                     process_ids=ProcessTimeline([[], []]),
                     pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0)
    monkeypatch.setattr(word_eval.gate, "check_file", fake_runtime_check)
    assert word_eval.main(["check", str(source), "--allow-office-com"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"] and result["status"] == "APP_UNAVAILABLE"
    assert "wps.exe" in result["error"]
    assert not result["ownership"]["activation_succeeded"]
    assert runtime.initialize_calls == runtime.uninitialize_calls == 1


@pytest.mark.parametrize("missing", [False, True])
def test_evaluator_registration_refusal_is_unavailable_without_activation(source, monkeypatch, missing):
    install_registry(monkeypatch, {"": "D:/Kingsoft/wps.exe /Automation"},
                     missing=WORD_CLSID_KEY if missing else None)
    ranges = {"main": FakeRange([FakeField("SEQ Figure", 1)])}
    output = source.with_name("evaluated.docx")
    original = source.read_bytes()
    runtime = FakeComRuntime()
    result = word_eval.evaluate_copy(
        source, output, descriptors(ranges), [{"id": "main", "kind": "main"}],
        allow_office_com=True, com_runtime=runtime, process_ids=ProcessTimeline([[]]),
        pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0,
    )
    assert not result["ok"] and result["status"] == "APP_UNAVAILABLE"
    assert not result["ownership"]["activation_succeeded"]
    assert result["passes"] == 0 and result["evaluation_output"] is None
    assert source.read_bytes() == original and not output.exists()
    assert runtime.initialize_calls == runtime.uninitialize_calls == 1
