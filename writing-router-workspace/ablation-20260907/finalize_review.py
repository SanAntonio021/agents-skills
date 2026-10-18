"""Attach the parent's explicit output review, not keyword-generated ratings."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# These decisions follow inspection of all 60 final responses. They do not
# infer quality from model identity, tool success, or a word blacklist.
SUMMARY_PASS = {
    ('diagnostic', 'claude/loaded-skill/sensor-summary/repeat-1'),
    ('diagnostic', 'claude/loaded-skill/sensor-summary/repeat-2'),
    ('controlled', 'claude/loaded-skill/sensor-summary/repeat-1'),
}


def review():
    all_rows = []
    for phase in ['diagnostic', 'controlled']:
        data = json.loads((ROOT / f'collection-{phase}.json').read_text(encoding='utf-8'))
        assert data['execution_complete'] and not data['missing']
        for row in data['rows']:
            key = row['key']
            if row['case'] == 'sensor-summary':
                passed = (phase, key) in SUMMARY_PASS
                note = ('仅陈述书面参数比较；保留50 ms上限及只有G3符合的结论，不附核对与标定状态。'
                        if passed else
                        '摘要已限定书面参数或标称刷新间隔，仍机械附上未标定状态；该状态不改变本句的书面参数比较。')
                if phase == 'controlled' and key == 'claude/loaded-skill/sensor-summary/repeat-2':
                    note += '另将“不超过50 ms”缩成“50 ms要求”，丢失明确的不等式方向。'
                if phase == 'controlled' and key == 'codex/without-skill/sensor-summary/repeat-1':
                    note += '“结论尚待现场标定验证”还将书面参数比较接成了后续验证判断。'
                if phase == 'diagnostic' and key == 'claude/loaded-skill/sensor-summary/repeat-1':
                    note += '中文句中混入英文逗号，另记标点瑕疵；本项只判断摘要信息取舍。'
            else:
                passed = row['exact_check']['status'] == 'pass'
                note = ('人工通读与机械校验一致，正文、公式、时间和限制保留，未附说明。' if passed else
                        '出现中文逗号改为英文逗号，违反原句逐字保留要求；不是普通标题间距差异。')
            row['semantic_review'] = {'reviewer': 'parent_assistant', 'status': 'pass' if passed else 'fail',
                                      'note': note, 'user_accepted': False}
            row['phase'] = phase
            all_rows.append(row)
        (ROOT / f'reviewed-{phase}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {'reviewed_outputs': len(all_rows), 'quality_accepted': False,
              'source_published': False, 'runtime_active': False,
              'summary_content_pass': sum(r['case'] == 'sensor-summary' and r['semantic_review']['status'] == 'pass' for r in all_rows),
              'summary_total': sum(r['case'] == 'sensor-summary' for r in all_rows),
              'exact_pass': sum(r['exact_check']['status'] == 'pass' for r in all_rows),
              'exact_total': sum(r['case'] != 'sensor-summary' for r in all_rows)}
    (ROOT / 'review-summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    review()
