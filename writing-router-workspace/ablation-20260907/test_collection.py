import collect_ablation as collector


def test_title_allows_boundary_lines_not_rewritten_body():
    case = {'original': 'q = 0.0015。\n限制句。', 'heading': '## 标题'}
    good = '## 标题\n\nq = 0.0015。\n限制句。\n'
    assert collector.exact_assessment(case, good)['whole_response_matches']
    for bad in [good.replace('q =', 'q='), good.replace('0.0015', '0.015'),
                good.replace('q = 0.0015。\n限制句。', '限制句。\nq = 0.0015。'),
                good + '正文未改。', good.replace('限制句。', '限制句。 ')]:
        assert not collector.exact_assessment(case, bad)['whole_response_matches']


def test_append_checks_original_prefix_and_whole_output():
    case = {'original': '## 标题\n\n原文。', 'append': '新增。'}
    good = case['original'] + '\n\n新增。\n'
    assert collector.exact_assessment(case, good)['whole_response_matches']
    assert collector.exact_assessment(case, case['original'] + case['append'])['whole_response_matches']
    for bad in [good + '说明。', good.replace('原文。', '新原文。'),
                good.replace('新增。', '增加。'), good.replace('标题\n\n', '标题\n')]:
        assert not collector.exact_assessment(case, bad)['whole_response_matches']


def test_summary_is_not_a_keyword_score():
    assert collector.exact_assessment({'id': 'sensor-summary'}, '摘要')['status'] == 'semantic_review_required'
