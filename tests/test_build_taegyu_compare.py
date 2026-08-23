from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from tools.apply_taegyu_revisions import build_revised_hwpx
from tools.build_taegyu_compare import (
    COMPARISON_FILENAMES,
    build_taegyu_compare,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "본논문_1차.hwpx"
TRACKED = ROOT / "revisions" / "14_citation_final_with_ids.md"
SECTION_BOUNDARIES = {
    "intro": ("I. 서론", "Ⅱ. 웹 크롤링"),
    "chapter_ii": ("Ⅱ. 웹 크롤링", "III. 생성형"),
    "conclusion": ("VI. 결론", "각주 및 참고문헌은"),
}
BOUNDARY_ALIASES = {
    "I. 서론": ("I. 서론", "Ⅰ. 서론"),
    "VI. 결론": ("VI. 결론", "Ⅵ. 결론"),
}


def _local_name(tag: str | bytes | etree.QName) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _direct_text(paragraph: etree._Element) -> str:
    return "".join(
        text_node.text or ""
        for child in paragraph
        if _local_name(child.tag) == "run"
        for text_node in child.iter()
        if _local_name(text_node.tag) == "t"
        and not any(
            _local_name(ancestor.tag) == "footNote"
            for ancestor in text_node.iterancestors()
        )
    ).strip()


def _selected_preview(
    source_path: Path,
    start_prefix: str,
    end_prefix: str,
) -> str:
    with zipfile.ZipFile(source_path) as source_zip:
        root = etree.fromstring(
            source_zip.read("Contents/section0.xml")
        )
    paragraphs = [
        child for child in root if _local_name(child.tag) == "p"
    ]
    texts = [_direct_text(paragraph) for paragraph in paragraphs]
    start_markers = BOUNDARY_ALIASES.get(
        start_prefix,
        (start_prefix,),
    )
    start = next(
        index
        for index, text in enumerate(texts)
        if not text.startswith("▶목 차◀")
        and any(
            text.startswith(marker) or text.endswith(marker)
            for marker in start_markers
        )
    )
    end = next(
        index
        for index, text in enumerate(texts[start + 1 :], start + 1)
        if text.startswith(end_prefix)
    )
    return "\n\n".join(text for text in texts[start:end] if text)


@pytest.mark.parametrize(
    ("version", "source_key"),
    [
        ("original", "original"),
        ("edit", "edited"),
    ],
)
def test_build_taegyu_compare_creates_exact_named_section_pairs(
    tmp_path: Path,
    version: str,
    source_key: str,
) -> None:
    edited = tmp_path / "edited.hwpx"
    compare = tmp_path / "compare"
    build_revised_hwpx(SOURCE, TRACKED, edited)

    outputs = build_taegyu_compare(SOURCE, edited, compare)

    source_path = SOURCE if source_key == "original" else edited
    for section_key, (start_prefix, end_prefix) in SECTION_BOUNDARIES.items():
        output_key = f"{section_key}_{version}"
        output_path = outputs[output_key]
        assert output_path.name == COMPARISON_FILENAMES[output_key]
        assert output_path.parent == compare
        with zipfile.ZipFile(output_path) as output_zip:
            assert output_zip.testzip() is None
            preview = output_zip.read("Preview/PrvText.txt").decode("utf-8")
            root = etree.fromstring(
                output_zip.read("Contents/section0.xml")
            )
        assert preview == _selected_preview(
            source_path,
            start_prefix,
            end_prefix,
        )
        headings = [
            _direct_text(paragraph)
            for paragraph in root
            if _local_name(paragraph.tag) == "p"
            and any(
                marker in _direct_text(paragraph)
                for marker in (
                    "I. 서론",
                    "Ⅰ. 서론",
                    "Ⅱ. 웹 크롤링",
                    "III.",
                    "VI. 결론",
                    "Ⅵ. 결론",
                )
            )
        ]
        assert len(headings) == 1
        assert any(
            marker in headings[0]
            for marker in BOUNDARY_ALIASES.get(
                start_prefix,
                (start_prefix,),
            )
        )
        footnotes = [
            footnote
            for footnote in root.iter()
            if _local_name(footnote.tag) == "footNote"
        ]
        assert [footnote.get("number") for footnote in footnotes] == [
            str(number)
            for number in range(1, len(footnotes) + 1)
        ]
