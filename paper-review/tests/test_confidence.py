from extract_paper_images import confidence_label


def test_high_boundary():
    assert confidence_label(0.75) == "high"


def test_high_above():
    assert confidence_label(0.86) == "high"


def test_medium_boundary():
    assert confidence_label(0.50) == "medium"


def test_medium_mid():
    assert confidence_label(0.60) == "medium"


def test_low_boundary():
    assert confidence_label(0.49) == "low"


def test_low_zero():
    assert confidence_label(0.0) == "low"


def test_high_max():
    assert confidence_label(0.95) == "high"
