"""Record the parent's full-output review; retain separate quality dimensions."""
from collections import Counter
import json
from pathlib import Path

import run_contrast as run

ROOT = Path(__file__).resolve().parent
SCOPE_DRIFT = {
    'claude/local/technical-retry/repeat-2',
    'claude/khazix/technical-retry/repeat-1',
    'claude/khazix/technical-retry/repeat-2',
    'codex/khazix/technical-retry/repeat-2',
}


def finalize():
    data = json.loads((ROOT / 'collection.json').read_text(encoding='utf-8'))
    assert data['completed'] == data['planned'] == 72 and not data['missing'] and not data['excluded']
    blind_key = json.loads((ROOT / 'technical-blind-key.json').read_text(encoding='utf-8'))
    blind_rows = json.loads((ROOT / 'technical-blind-review.json').read_text(encoding='utf-8'))['rows']
    assert len(blind_rows) == len(blind_key) == 24
    assert {r['id'] for r in blind_rows} == set(blind_key)
    blind = {blind_key[r['id']]['key']: r for r in blind_rows}
    assert set(blind) == {r['key'] for r in data['rows'] if r['category'] == 'technical'}
    assert {key for key, r in blind.items() if r['facts'] == 'fail'} == SCOPE_DRIFT
    aggregate = {}
    read_calls = 0
    for row in data['rows']:
        folder = ROOT / row['path']
        raw = (folder / 'final.md').read_bytes()
        assert run.digest(raw) == row['output_sha256']
        text = raw.decode('utf-8')
        read_calls += len(json.loads((folder / 'read-evidence.json').read_text(encoding='utf-8')))
        verdict = {'reviewer': 'parent_assistant', 'facts': 'pass', 'concision': 'pass',
                   'extra_content': False, 'notes': [], 'user_accepted': False}
        if row['category'] == 'heading':
            verdict['literal_preservation'] = row['exact_check']['status']
            verdict['notes'].append('标题、数字、公式和原有结论均已核对。')
            if row['exact_check']['status'] == 'fail':
                verdict['notes'].append('原文中文逗号变成英文逗号；数据未变，但不符合逐字保留要求。')
            else:
                verdict['notes'].append('除新增标题及连接换行外，整份正文逐字相同。')
        elif row['category'] == 'technical':
            independent = blind[row['key']]
            assert blind_key[independent['id']]['output_sha256'] == row['output_sha256']
            row['independent_blind_review'] = independent
            verdict['notes'].append('数字与主要动作已核对，无额外改写说明；逐项复核如下。')
            if row['key'] in SCOPE_DRIFT:
                verdict['facts'] = 'fail'
                verdict['notes'].append('删去了“据此”，把不能根据这64条记录识别，扩大成重启后不能识别此前报文，未保护原文否定范围。')
            else:
                verdict['notes'].append('动作次序和否定范围保持；普通顺序短语不按并行执行误判。')
            if independent['facts'] == 'review_required':
                verdict['facts'] = 'review_required'
                verdict['notes'].append('采纳匿名复审疑点：“尚未测试”改成“尚未验证”，未明确保留测试未开展这一状态。不判为已证实事实错误，也不计入通过。')
            if independent['concision'] == 'fail':
                verdict['concision'] = 'fail'
                verdict['notes'].append('采纳匿名复审意见：仍有“接收链路增益调整流程如下”的写作预告，属于轻微精简遗漏。')
            else:
                verdict['notes'].append('写作预告和重复总结已删除。')
            verdict['blind_review_resolution'] = 'accepted_after_parent_check'
        elif row['case'] == 'summary-power':
            verdict['notes'].append('保留标称功耗范围、仅R符合与不超过12 W的要求；没有新增采购或整体可用结论。')
            if row['host'] == 'codex' and row['arm'] == 'khazix':
                verdict['concision'] = 'fail'
                verdict['notes'].append('结尾又附温升测试未进行，该状态不改变本句标称功耗比较；这是简洁问题，不是事实错误。')
            else:
                verdict['notes'].append('没有附上温升测试状态。保留其余两款的功耗数值也不直接判差。')
        else:
            verdict['coverage'] = 'full' if row['host'] == 'codex' else 'partial'
            verdict['coverage_comparison_eligible'] = False
            verdict['notes'].append('没有将两个测试温度点扩大成全温区验证；准确摘要不因省略未测事项直接判事实错。')
            verdict['notes'].append('题目“得到验证的温度条件”存在只问成功测试点的合理理解，完整覆盖差异仅记录，不用于判断候选是否更善于保留必要限制。')
        verdict['format_note'] = ('部分中文句子使用英文逗号或括号；除逐字保留题外另记排版瑕疵，不等同于事实漂移。'
                                  if ',' in text else '')
        row['semantic_review'] = verdict
        group = aggregate.setdefault(row['host'] + '/' + row['arm'], Counter())
        group['outputs'] += 1
        group['fact_or_condition_failures'] += verdict['facts'] == 'fail'
        group['fact_or_condition_review_required'] += verdict['facts'] == 'review_required'
        group['concision_failures'] += verdict['concision'] == 'fail'
        if row['category'] == 'heading':
            group['heading_total'] += 1
            group['heading_exact_pass'] += row['exact_check']['status'] == 'pass'
        if row['case'] == 'summary-power':
            group['power_summary_total'] += 1
            group['power_summary_no_redundant_status'] += verdict['concision'] == 'pass'
        if row['category'] == 'technical':
            group['technical_total'] += 1
            group['technical_facts_and_scope_pass'] += verdict['facts'] == 'pass'
    data['review_policy'] = 'REVIEW-POLICY.md'
    data['independent_review'] = {'file': 'technical-blind-review.json', 'outputs': len(blind),
                                'parent_reconciled': True, 'changes_from_initial_parent_review': 3}
    data['aggregate'] = {k: dict(v) for k, v in aggregate.items()}
    data['tool_calls_total'] = read_calls
    data['decision'] = 'Retain isolated examples candidate; no stable superiority claim, source merge, or runtime publication'
    run.write_json(ROOT / 'reviewed-results.json', data)
    run.write_json(ROOT / 'review-summary.json', {'outputs_reviewed': 72, 'aggregate': data['aggregate'],
                                                'tool_calls_total': read_calls, 'decision': data['decision']})
    print(json.dumps({'outputs_reviewed': 72, 'tool_calls_total': read_calls, 'aggregate': data['aggregate']}, ensure_ascii=False))


if __name__ == '__main__':
    finalize()
