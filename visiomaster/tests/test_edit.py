"""Semantic checks plus real Visio integration tests (Windows only)."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import visio_edit as edit


def test_hash_binding(tmp_path):
    source = tmp_path / 'source.vsdx'
    source.write_bytes(b'original')
    plan = {'version': 1, 'input_sha256': edit.digest(source),
            'operations': [{'op': 'text', 'page_id': 0, 'shape_id': 1, 'text': 'new'}]}
    edit.validate_plan(plan, source)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='SHA-256'):
        edit.validate_plan(plan, source)


def test_scope_checks():
    shape = {'text': 'old', 'cells': {'PinX': 1}, 'characters': [], 'id': 1}
    before = {'pages': [], 'connections': [], 'shapes': {'0:1': shape}}
    after = copy.deepcopy(before)
    after['shapes']['0:1']['cells']['PinX'] = 2
    with pytest.raises(ValueError, match='Unrequested'):
        edit.check_preserved(before, after, {'0:1': {'text'}}, set(), set(), set())


def test_scene_lock(tmp_path):
    scene = tmp_path / 'figure.scene.json'
    scene.write_text('{}', encoding='utf-8')
    edit.write(edit.scene_guard_path(scene), [{'scene_sha256': edit.digest(scene)}])
    with pytest.raises(ValueError, match='superseded'):
        edit.check_scene_guard(scene)


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    if sys.platform != 'win32':
        pytest.skip('Microsoft Visio is required')
    folder = tmp_path_factory.mktemp('native-visio')
    source = folder / 'synthetic.vsdx'
    with edit.visio() as app:
        document = app.Documents.Add('')
        page = document.Pages.Item(1)
        page.PageSheet.CellsU('PageWidth').FormulaU = '10 in'
        page.PageSheet.CellsU('PageHeight').FormulaU = '7 in'
        a = page.DrawRectangle(1, 4, 3, 5)
        a.Text = '处理模块'
        b = page.DrawRectangle(6, 4, 8, 5)
        b.Text = '输出模块'
        connector = page.Drop(app.ConnectorToolDataObject, 4, 4.5)
        connector.CellsU('BeginX').GlueToPos(a, 1, .5)
        connector.CellsU('EndX').GlueToPos(b, 0, .5)
        ordinary = page.DrawLine(1, 2, 3, 2)
        label = page.DrawRectangle(1.5, 2.1, 2.5, 2.6)
        label.Text = '普通线段'
        duplicate = page.DrawRectangle(6, 1, 8, 1.5)
        duplicate.Text = '输出模块'
        rich = page.DrawRectangle(1, 5.7, 4, 6.5)
        rich.Text = '中文AB尾部'
        chars = rich.Characters
        chars.Begin, chars.End = 2, 4
        chars.CharProps(7, 20)
        inner_a = page.DrawRectangle(5, 2, 6, 3)
        inner_a.Text = '组内甲'
        inner_b = page.DrawRectangle(6, 2, 7, 3)
        inner_b.Text = '组内乙'
        selection = page.CreateSelection(0)
        selection.Select(inner_a, 2)
        selection.Select(inner_b, 2)
        group = selection.Group()
        second = document.Pages.Add()
        s = second.DrawOval(1, 1, 3, 2)
        s.Text = '第二页'
        document.SaveAs(str(source))
        ids = {'page': page.ID, 'a': a.ID, 'b': b.ID, 'connector': connector.ID,
               'ordinary': ordinary.ID, 'label': label.ID, 'duplicate': duplicate.ID,
               'group': group.ID, 'inner': inner_a.ID, 'second_page': second.ID, 'second': s.ID, 'rich': rich.ID}
        a = b = connector = ordinary = label = duplicate = inner_a = inner_b = selection = group = second = s = page = document = rich = chars = None
    return folder, source, ids


def run(native, name, operations, backend='com', source=None, extra=None):
    folder, original, ids = native
    source = source or original
    plan = {'version': 1, 'input_sha256': edit.digest(source), 'backend': backend, 'operations': operations}
    plan.update(extra or {})
    plan_path, output = folder / (name + '.plan.json'), folder / (name + '.vsdx')
    edit.write(plan_path, plan)
    original_hash = edit.digest(original)
    result = edit.apply(source, plan_path, output)
    assert edit.digest(original) == original_hash
    assert result['status'] == 'edited_pending_visual_review'
    assert result['outputs']
    return output, result


def test_native_inspection(native):
    _, source, ids = native
    raw = edit.package_snapshot(source)
    assert len(raw['pages']) == 2
    assert raw['shapes'][edit.key(ids['page'], ids['inner'])]['parent'] == edit.key(ids['page'], ids['group'])
    with edit.visio() as app:
        doc = app.Documents.OpenEx(str(source), edit.OPEN_HIDDEN + 2)
        state = edit.snapshot(doc)
        assert len(state['connections']) == 2
        doc = None


def test_native_two_rounds(native):
    _, _, ids = native
    p, a = ids['page'], ids['a']
    first, report = run(native, 'round1', [
        {'op': 'text', 'page_id': p, 'shape_id': a, 'text': '处理单元'},
        {'op': 'font', 'page_id': p, 'shape_id': a, 'font': 'SimSun', 'size_pt': 18},
        {'op': 'move', 'page_id': p, 'shape_id': a, 'dx': .3, 'ordinary_links': []},
        {'op': 'resize', 'page_id': p, 'shape_id': a, 'width': 2.3, 'height': 1.2, 'ordinary_links': []},
    ])
    assert report['after']['shapes'][edit.key(p, a)]['characters'][0]['7'] == .25
    second, report2 = run(native, 'round2', [
        {'op': 'text', 'page_id': p, 'shape_id': a, 'text': '确认单元'},
        {'op': 'move', 'page_id': p, 'shape_id': a, 'dx': -.1, 'ordinary_links': []},
    ], source=first)
    assert report2['before'] == report['after']
    assert set(report2['before']['shapes']) == set(report2['after']['shapes'])


def test_library_text(native):
    _, _, ids = native
    run(native, 'library-text', [{'op': 'text', 'page_id': ids['page'], 'shape_id': ids['a'],
                                'expect_text': '处理模块', 'text': '库写回'}], backend='vsdx')


def test_library_sequential_text(native):
    _, _, ids = native
    run(native, 'library-sequential', [
        {'op': 'text', 'page_id': ids['page'], 'shape_id': ids['a'], 'expect_text': '处理模块', 'text': '中间文字'},
        {'op': 'text', 'page_id': ids['page'], 'shape_id': ids['a'], 'search_text': '中间文字', 'expect_text': '中间文字', 'text': '最终文字'},
    ], backend='vsdx')


def test_ordinary_path_and_label(native):
    _, _, ids = native
    p, line, label = ids['page'], ids['ordinary'], ids['label']
    run(native, 'ordinary', [
        {'op': 'line', 'page_id': p, 'shape_id': line, 'points': [[1, 2], [2, 2], [2, 1], [4, 1]],
         'end_arrow': 4, 'line_pattern': 2},
        {'op': 'move', 'page_id': p, 'shape_id': label, 'dx': 1, 'dy': -1, 'ordinary_links': []},
    ])


def test_add_copy_delete_group_and_multi_page(native):
    _, _, ids = native
    p = ids['page']
    run(native, 'objects', [
        {'op': 'copy', 'page_id': p, 'shape_id': ids['group'], 'as': 'group_copy', 'dy': -1},
        {'op': 'text', 'page_id': p, 'shape_id': ids['inner'], 'text': '组内修改'},
        {'op': 'add', 'page_id': p, 'kind': 'rectangle', 'box': [1, .5, 3, 1], 'text': '新增', 'as': 'added'},
        {'op': 'font', 'page_id': p, 'shape_id': '$added', 'font': 'SimSun', 'size_pt': 14},
        {'op': 'delete', 'page_id': p, 'shape_id': ids['duplicate'], 'ordinary_links': []},
        {'op': 'text', 'page_id': ids['second_page'], 'shape_id': ids['second'], 'text': '第二页修改'},
    ])


@pytest.mark.parametrize('case', ['bad_id', 'duplicate', 'noop', 'delete_connected', 'missing_ordinary'])
def test_rejections(native, case):
    folder, source, ids = native
    p = ids['page']
    operations = {
        'bad_id': [{'op': 'text', 'page_id': p, 'shape_id': 99999, 'text': 'bad'}],
        'duplicate': [{'op': 'text', 'page_id': p, 'shape_id': ids['b'], 'search_text': '输出模块', 'text': 'bad'}],
        'noop': [{'op': 'text', 'page_id': p, 'shape_id': ids['a'], 'text': '处理模块'}],
        'delete_connected': [{'op': 'delete', 'page_id': p, 'shape_id': ids['a'], 'ordinary_links': []}],
        'missing_ordinary': [{'op': 'move', 'page_id': p, 'shape_id': ids['a'], 'dx': 1}],
    }[case]
    plan_path = folder / (case + '.plan.json')
    edit.write(plan_path, {'version': 1, 'input_sha256': edit.digest(source), 'operations': operations})
    before = edit.digest(source)
    with pytest.raises((ValueError, KeyError)):
        edit.apply(source, plan_path, folder / (case + '.vsdx'))
    assert edit.digest(source) == before


def test_export_failure(native, monkeypatch):
    folder, source, ids = native
    real_export = edit.export
    calls = []
    def fail_second(document, basename):
        calls.append(basename)
        if len(calls) == 2:
            raise RuntimeError('simulated export failure')
        return real_export(document, basename)
    monkeypatch.setattr(edit, 'export', fail_second)
    plan = folder / 'export-failure.plan.json'
    edit.write(plan, {'version': 1, 'input_sha256': edit.digest(source),
                     'operations': [{'op': 'text', 'page_id': ids['page'], 'shape_id': ids['a'], 'text': '修改'}]})
    with pytest.raises(RuntimeError, match='export failure'):
        edit.apply(source, plan, folder / 'export-failure.vsdx')
    assert edit.read(folder / 'export-failure.edit.json')['status'] == 'failed'


def test_shutdown_failure_is_not_reported_as_success(native, monkeypatch):
    import contextlib
    folder, source, ids = native
    real_visio = edit.visio

    @contextlib.contextmanager
    def fail_shutdown():
        with real_visio() as app:
            yield app
        raise RuntimeError('simulated shutdown failure')

    monkeypatch.setattr(edit, 'visio', fail_shutdown)
    plan = folder / 'shutdown-failure.plan.json'
    edit.write(plan, {'version': 1, 'input_sha256': edit.digest(source),
                     'operations': [{'op': 'text', 'page_id': ids['page'], 'shape_id': ids['a'], 'text': '修改'}]})
    with pytest.raises(RuntimeError, match='shutdown failure'):
        edit.apply(source, plan, folder / 'shutdown-failure.vsdx')
    report = edit.read(folder / 'shutdown-failure.edit.json')
    assert report['status'] == 'failed'
    assert 'shutdown failure' in report['error']


def test_rich_text_and_group_movement(native):
    _, _, ids = native
    p = ids['page']
    _, report = run(native, 'rich-group', [
        {'op': 'text', 'page_id': p, 'shape_id': ids['rich'], 'start': 2, 'end': 4, 'text': 'CD'},
        {'op': 'font', 'page_id': p, 'shape_id': ids['rich'], 'start': 2, 'end': 4, 'size_pt': 22},
        {'op': 'move', 'page_id': p, 'shape_id': ids['group'], 'dx': .2, 'ordinary_links': []},
        {'op': 'resize', 'page_id': p, 'shape_id': ids['group'], 'width': 2.4, 'ordinary_links': []},
    ])
    assert report['after']['shapes'][edit.key(p, ids['rich'])]['text'] == '中文CD尾部'


def test_reconnect_and_delete(native):
    _, _, ids = native
    p = ids['page']
    _, report = run(native, 'reconnect-delete', [
        {'op': 'delete', 'page_id': p, 'shape_id': ids['a'], 'ordinary_links': []},
        {'op': 'line', 'page_id': p, 'shape_id': ids['connector'], 'begin_glue': {'shape_id': ids['duplicate'], 'position': [1, .5]}, 'end_arrow': 4},
    ])
    assert any(c['to_id'] == ids['duplicate'] for c in report['after']['connections'])


def test_no_visible_pixel_change(tmp_path):
    from PIL import Image
    p = tmp_path / 'same.png'
    Image.new('RGB', (10, 10), 'white').save(p)
    with pytest.raises(ValueError, match='visible pixel'):
        edit.pixel_changes([p], [p])


def test_scene_reconciliation_and_portable_guard(tmp_path):
    source = tmp_path / 'old.scene.json'
    scene = {'nodes': [{'id': 'box', 'type': 'process_box', 'text': 'old', 'x': 1, 'y': 1, 'w': 2, 'h': 1}], 'edges': [], 'assets': []}
    edit.write(source, scene)
    shape = {'name': 'node__box__01', 'text': 'old', 'cells': {'PinX': 2, 'PinY': 3.5, 'Width': 2, 'Height': 1, 'Angle': 0, 'FlipX': 0, 'FlipY': 0}, 'characters': [{}]}
    before = {'pages': [{'height': 5}], 'shapes': {'0:1': shape}}
    after = copy.deepcopy(before)
    after['shapes']['0:1']['text'] = 'new'
    plan = {'scene_sha256': edit.digest(source), 'operations': [{'op': 'text', 'page_id': 0, 'shape_id': 1, 'text': 'new'}]}
    result = edit.reconcile_scene(source, None, tmp_path / 'new.vsdx', before, after, plan)
    assert result['mode'] == 'scene_synced'
    assert edit.read(result['scene'])['nodes'][0]['text'] == 'new'
    scene['metadata'] = {'native_edit_state': {'superseded': True}}
    edit.write(tmp_path / 'copied.scene.json', scene)
    with pytest.raises(ValueError, match='superseded'):
        edit.check_scene_guard(tmp_path / 'copied.scene.json')


def test_invalid_plan_fields(tmp_path):
    p = tmp_path / 'input.vsdx'
    p.write_bytes(b'input')
    base = {'version': 1, 'input_sha256': edit.digest(p), 'operations': []}
    for op in ({'op': 'move', 'page_id': 0, 'shape_id': 1, 'dx': '1', 'ordinary_links': []},
               {'op': 'line', 'page_id': 0, 'shape_id': 1, 'points': [[1, 2], [3]]},
               {'op': 'font', 'page_id': 0, 'shape_id': 1, 'size_pt': float('nan')}):
        with pytest.raises(ValueError):
            edit.validate_plan(dict(base, operations=[op]), p)
