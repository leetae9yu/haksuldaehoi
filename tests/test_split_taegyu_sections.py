from __future__ import annotations

import copy
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from tools.apply_taegyu_revisions import build_revised_hwpx
from tools.split_taegyu_sections import split_taegyu_sections

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "본논문_1차.hwpx"
TRACKED = ROOT / "revisions" / "14_citation_final_with_ids.md"


def _local_name(tag: str | bytes | etree.QName) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _paragraphs(root: etree._Element) -> list[etree._Element]:
    return [
        child for child in root if _local_name(child.tag) == "p"
    ]


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


def _footnote_texts(root: etree._Element) -> list[str]:
    return [
        "".join(
            text_node.text or ""
            for text_node in footnote.iter()
            if _local_name(text_node.tag) == "t"
        ).strip()
        for footnote in root.iter()
        if _local_name(footnote.tag) == "footNote"
    ]


def _normalized_xml(paragraph: etree._Element) -> bytes:
    normalized = copy.deepcopy(paragraph)
    normalized.set("pageBreak", "1")
    for element in normalized.iter():
        if _local_name(element.tag) == "footNote":
            element.set("number", "0")
        if (
            _local_name(element.tag) == "autoNum"
            and element.get("numType") == "FOOTNOTE"
        ):
            element.set("num", "0")
    return etree.tostring(
        normalized,
        method="c14n",
        with_comments=True,
    )


@pytest.mark.parametrize(
    ("key", "filename", "start_prefix", "end_prefix"),
    [
        ("intro", "서론.hwpx", "I. 서론", "Ⅱ. 웹 크롤링"),
        (
            "chapter_ii",
            "본론_II.hwpx",
            "Ⅱ. 웹 크롤링",
            "III. 생성형",
        ),
        (
            "conclusion",
            "결론.hwpx",
            "VI. 결론",
            "각주 및 참고문헌은",
        ),
    ],
)
def test_split_taegyu_sections_preserves_selected_xml(
    tmp_path: Path,
    key: str,
    filename: str,
    start_prefix: str,
    end_prefix: str | None,
) -> None:
    revised = tmp_path / "revised.hwpx"
    build_revised_hwpx(SOURCE, TRACKED, revised)
    outputs = split_taegyu_sections(revised, tmp_path)

    assert outputs[key] == tmp_path / filename
    with (
        zipfile.ZipFile(revised) as source_zip,
        zipfile.ZipFile(outputs[key]) as split_zip,
    ):
        assert split_zip.testzip() is None
        source_root = etree.fromstring(
            source_zip.read("Contents/section0.xml")
        )
        split_root = etree.fromstring(
            split_zip.read("Contents/section0.xml")
        )
        source_paragraphs = _paragraphs(source_root)
        split_paragraphs = _paragraphs(split_root)
        source_texts = [_direct_text(p) for p in source_paragraphs]
        start = next(
            index
            for index, text in enumerate(source_texts)
            if text.startswith(start_prefix)
        )
        end = (
            len(source_paragraphs)
            if end_prefix is None
            else next(
                index
                for index, text in enumerate(source_texts[start + 1 :], start + 1)
                if text.startswith(end_prefix)
            )
        )
        expected = source_paragraphs[start:end]

        assert _direct_text(split_paragraphs[0]) == ""
        assert [
            _direct_text(paragraph)
            for paragraph in split_paragraphs[1:]
        ] == [_direct_text(paragraph) for paragraph in expected]
        assert len(split_paragraphs) == len(expected) + 1
        assert split_paragraphs[1].get("pageBreak") == "0"
        assert all(
            _normalized_xml(actual) == _normalized_xml(original)
            for actual, original in zip(
                split_paragraphs[1:],
                expected,
                strict=True,
            )
        )
        expected_footnote_texts = [
            "".join(
                text_node.text or ""
                for text_node in footnote.iter()
                if _local_name(text_node.tag) == "t"
            ).strip()
            for paragraph in expected
            for footnote in paragraph.iter()
            if _local_name(footnote.tag) == "footNote"
        ]
        assert _footnote_texts(split_root) == expected_footnote_texts
        footnotes = [
            footnote
            for footnote in split_root.iter()
            if _local_name(footnote.tag) == "footNote"
        ]
        assert [footnote.get("number") for footnote in footnotes] == [
            str(number)
            for number in range(1, len(footnotes) + 1)
        ]

        excluded = {
            "Contents/section0.xml",
            "Preview/PrvText.txt",
        }
        for item in source_zip.infolist():
            if item.filename not in excluded:
                assert split_zip.read(item.filename) == source_zip.read(
                    item.filename
                )
        preview = split_zip.read("Preview/PrvText.txt").decode("utf-8")
        assert start_prefix in preview
        if end_prefix is not None:
            assert end_prefix not in preview
