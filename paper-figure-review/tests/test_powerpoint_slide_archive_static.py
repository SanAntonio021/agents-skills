from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from xml.etree import ElementTree


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = SKILL_ROOT / "assets" / "powerpoint-slide-archive"


def require(text: str, fragment: str, location: Path) -> None:
    if fragment not in text:
        raise AssertionError(f"{location} missing required fragment: {fragment}")


def validate_sources() -> None:
    ignore_path = ASSET_ROOT / ".gitignore"
    require(ignore_path.read_text(encoding="utf-8"), "PaperFigureSlideArchive.ppam", ignore_path)

    vba_path = ASSET_ROOT / "SlideArchive.bas"
    vba_text = vba_path.read_text(encoding="utf-8-sig")
    for fragment in [
        "Public Sub ArchiveCurrentSlide",
        "sourceSlide.Duplicate",
        "archivedSlide.MoveTo activeDeck.Slides.Count",
        "SlideShowTransition.Hidden = msoTrue",
        "PFR_ARCHIVE_SOURCE_SLIDE_ID",
        "PFR_ARCHIVE_VERSION",
        "PFR_ARCHIVE_TIMESTAMP",
        "activeDeck.Save",
        "RestoreSourceSelection",
        "Len(activeDeck.Path) = 0",
        "activeDeck.ReadOnly = msoTrue",
    ]:
        require(vba_text, fragment, vba_path)

    ribbon_path = ASSET_ROOT / "customUI14.xml"
    ribbon_root = ElementTree.parse(ribbon_path).getroot()
    namespace = {"ui": "http://schemas.microsoft.com/office/2009/07/customui"}
    home_tab = ribbon_root.find(".//ui:tab[@idMso='TabHome']", namespace)
    if home_tab is None:
        raise AssertionError("RibbonX does not target the Home tab")
    button = home_tab.find(".//ui:button[@id='PFRArchiveCurrentSlide']", namespace)
    if button is None:
        raise AssertionError("RibbonX archive button missing")
    if button.attrib.get("label") != "留档当前页":
        raise AssertionError("RibbonX button label mismatch")
    if button.attrib.get("onAction") != "ArchiveCurrentSlide":
        raise AssertionError("RibbonX callback mismatch")

    reference_path = SKILL_ROOT / "references" / "powerpoint-slide-archive.md"
    reference_text = reference_path.read_text(encoding="utf-8")
    for fragment in [
        "`Ctrl+S` 保持 PowerPoint 原生保存行为",
        "副本移到末尾并设为隐藏",
        "不会新增受信任位置，也不会修改宏安全策略",
        "-VbaTemplatePath",
        "export_powerpoint_slide_archive_vba_for_vbe.ps1",
        "test_powerpoint_slide_archive_lifecycle.ps1",
        "事务备份",
    ]:
        require(reference_text, fragment, reference_path)

    install_path = SKILL_ROOT / "scripts" / "install_powerpoint_slide_archive.ps1"
    install_text = install_path.read_text(encoding="utf-8-sig")
    for fragment in [
        ".staged.ppam",
        ".backup.ppam",
        "[IO.File]::Move($backupPath, $targetPath)",
        "replaced_existing",
    ]:
        require(install_text, fragment, install_path)

    integration_path = SKILL_ROOT / "tests" / "test_powerpoint_slide_archive.ps1"
    integration_text = integration_path.read_text(encoding="utf-8-sig")
    for fragment in [
        "$slides.Count -eq 4",
        "PFR_ARCHIVE_VERSION') -eq '1'",
        "PFR_ARCHIVE_VERSION') -eq '2'",
        "$archiveSlide1.Export",
        "$archiveSlide2.Export",
    ]:
        require(integration_text, fragment, integration_path)

    lifecycle_path = SKILL_ROOT / "tests" / "test_powerpoint_slide_archive_lifecycle.ps1"
    lifecycle_text = lifecycle_path.read_text(encoding="utf-8-sig")
    for fragment in [
        "首次安装",
        "同路径重装",
        "卸载",
        "最终重装",
    ]:
        require(lifecycle_text, fragment, lifecycle_path)


def validate_package(package_path: Path) -> None:
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        required = {
            "ppt/vbaProject.bin",
            "customUI/customUI14.xml",
            "_rels/.rels",
            "[Content_Types].xml",
        }
        missing = required - names
        if missing:
            raise AssertionError(f"PPAM missing entries: {sorted(missing)}")

        ribbon = ElementTree.fromstring(archive.read("customUI/customUI14.xml"))
        if not ribbon.tag.endswith("customUI"):
            raise AssertionError("packaged RibbonX root is invalid")

        relationships = ElementTree.fromstring(archive.read("_rels/.rels"))
        ribbon_relationship_type = (
            "http://schemas.microsoft.com/office/2007/relationships/ui/extensibility"
        )
        ribbon_relationships = [
            node
            for node in relationships
            if node.attrib.get("Target") == "customUI/customUI14.xml"
        ]
        if len(ribbon_relationships) != 1:
            raise AssertionError("PPAM must contain exactly one RibbonX root relationship")
        if ribbon_relationships[0].attrib.get("Type") != ribbon_relationship_type:
            raise AssertionError("PPAM RibbonX root relationship type is invalid")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppam", type=Path)
    args = parser.parse_args()

    validate_sources()
    if args.ppam is not None:
        validate_package(args.ppam.resolve())
    print("PowerPoint slide archive static tests passed")


if __name__ == "__main__":
    main()
