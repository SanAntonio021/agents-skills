import collect_style as collect


def test_paragraph_check_does_not_score_length_or_punctuation():
    text = '甲；乙。\r\n\r\n丙。'
    assert collect.boundary_checks('terms-control', [text])[0]['passed']


def test_integrated_note_retains_untargeted_paragraph():
    texts = ['A。\n\n供电。', 'A。\n\n供电比较。', 'B先。\n\n供电比较。']
    assert all(c['passed'] for c in collect.boundary_checks('integration-note', texts))
    texts[2] += '多余说明。'
    assert not collect.boundary_checks('integration-note', texts)[1]['passed']


def test_first_sentence_edit_does_not_permit_other_sentence_changes():
    texts = ['过程。\n\n测了六小时。其他条件未测。',
             '新过程。\n\n测了六小时。其他条件未测。',
             '新过程。\n\n在单传感器台架试验中，测了六小时。其他条件未测。']
    assert all(c['passed'] for c in collect.boundary_checks('test-explanation', texts))
    texts[2] = texts[2].replace('其他条件未测。', '测试已完成。')
    assert not collect.boundary_checks('test-explanation', texts)[-1]['passed']
