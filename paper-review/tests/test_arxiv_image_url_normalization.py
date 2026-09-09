from extract_paper_images import source_to_download_url


def test_arxiv_relative_source_does_not_duplicate_paper_id():
    assert source_to_download_url(
        "2607.04988v1/x1.png",
        "https://arxiv.org/html/2607.04988v1/",
    ) == "https://arxiv.org/html/2607.04988v1/x1.png"


def test_arxiv_absolute_url_with_duplicate_paper_id_is_normalized():
    assert source_to_download_url(
        "https://arxiv.org/html/2607.04988v1/2607.04988v1/figures/fig1.png",
        None,
    ) == "https://arxiv.org/html/2607.04988v1/figures/fig1.png"


def test_arxiv_relative_figure_path_keeps_base_paper_id():
    assert source_to_download_url(
        "figures/fig1.png",
        "https://arxiv.org/html/2607.04988v1/",
    ) == "https://arxiv.org/html/2607.04988v1/figures/fig1.png"
