from pathlib import Path
from subprocess import run
from xml.etree import ElementTree
from zipfile import ZipFile, is_zipfile


SKILL_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = SKILL_ROOT.parent
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "ieee-official-templates"

REQUIRED_FILES = (
    "transactions-journals-letters/word-extracted/ieee-transactions-template.docx",
    "transactions-journals-letters/latex-extracted/bare_jrnl_new_sample4.tex",
    "transactions-journals-letters/latex-extracted/IEEEtran.cls",
    "ieee-access/Access_Word_Template.docx",
    "ieee-access/latex-extracted/ACCESS_latex_template_20240429/access.tex",
    "ieee-access/latex-extracted/ACCESS_latex_template_20240429/ieeeaccess.cls",
    "ieee-journal-of-microwaves/JMW_Word_Template.docx",
    "ieee-journal-of-microwaves/latex-extracted/IEEE_JMW_LaTex_Template_Oct18_2021/JMW_template.tex",
    "ieee-journal-of-microwaves/latex-extracted/IEEE_JMW_LaTex_Template_Oct18_2021/IEEEjmw.cls",
)


def test_required_runtime_templates_exist() -> None:
    missing = [path for path in REQUIRED_FILES if not (TEMPLATE_ROOT / path).is_file()]
    assert not missing, f"missing runtime template files: {missing}"


def test_distribution_excludes_source_packages_and_generated_outputs() -> None:
    forbidden = []
    try:
        tracked = run(
            [
                "git",
                "-C",
                str(REPOSITORY_ROOT),
                "ls-files",
                "--",
                TEMPLATE_ROOT.relative_to(REPOSITORY_ROOT).as_posix(),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        tracked = None

    if tracked is not None and tracked.returncode == 0:
        paths = [REPOSITORY_ROOT / line for line in tracked.stdout.splitlines() if line]
    else:
        paths = [path for path in TEMPLATE_ROOT.rglob("*") if path.is_file()]

    for path in paths:
        if (
            path.suffix.lower() in {".zip", ".pdf"}
            or path.name == ".DS_Store"
            or path.name.startswith("._")
            or "__MACOSX" in path.parts
        ):
            forbidden.append(path.relative_to(TEMPLATE_ROOT).as_posix())
    assert not forbidden, f"non-runtime template artifacts are tracked: {forbidden}"


def test_word_templates_are_valid_open_xml_packages() -> None:
    word_templates = [TEMPLATE_ROOT / path for path in REQUIRED_FILES if path.endswith(".docx")]
    for path in word_templates:
        assert is_zipfile(path), f"not a valid DOCX package: {path}"
        with ZipFile(path) as package:
            names = set(package.namelist())
            assert "[Content_Types].xml" in names
            assert "word/document.xml" in names
            ElementTree.fromstring(package.read("[Content_Types].xml"))
            ElementTree.fromstring(package.read("word/document.xml"))
