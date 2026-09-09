from extract_paper_images import figure_filename


def test_fig_1():
    assert figure_filename("Fig. 1", 1) == "fig_1.png"


def test_fig_2a():
    assert figure_filename("Fig. 2a", 2) == "fig_2a.png"


def test_fig_10():
    assert figure_filename("Fig. 10", 10) == "fig_10.png"


def test_table_roman_I():
    assert figure_filename("Table I", 1) == "table_1.png"


def test_table_roman_III():
    assert figure_filename("Table III", 3) == "table_3.png"


def test_supplementary_fig_s2():
    assert figure_filename("Supplementary Fig. S2", 2) == "supp_fig_s2.png"


def test_fallback_index():
    assert figure_filename("Fig. ???", 5) == "fig_5.png"
