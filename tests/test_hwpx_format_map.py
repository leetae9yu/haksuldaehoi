from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from tools.hwpx_format_map import compare_format_maps


def _mutate_title_paragraph(source: Path, target: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}

    root = etree.fromstring(members["Contents/section0.xml"])
    title = next(
        paragraph
        for paragraph in root.iter()
        if etree.QName(paragraph).localname == "p"
        and "생성형 AI 학습을 위한 무단 데이터 크롤링"
        in "".join(str(text) for text in paragraph.itertext())
    )
    title.set("paraPrIDRef", "0")
    members["Contents/section0.xml"] = etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
    )

    with zipfile.ZipFile(target, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def test_identical_hwpx_matches_format_map() -> None:
    reference = Path("본논문_1차.hwpx")

    assert compare_format_maps(reference, reference) == []


def test_changed_title_paragraph_style_fails_format_map(tmp_path: Path) -> None:
    reference = Path("본논문_1차.hwpx")
    candidate = tmp_path / "changed-title.hwpx"
    _mutate_title_paragraph(reference, candidate)

    mismatches = compare_format_maps(reference, candidate)

    assert any(
        mismatch.startswith("paragraph-style:title:")
        for mismatch in mismatches
    )
