from __future__ import annotations

import copy
import hashlib
import re
import zipfile
from pathlib import Path

from lxml import etree

from tools.apply_taegyu_revisions import build_revised_hwpx

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "본논문_1차.hwpx"
TRACKED = ROOT / "revisions" / "14_citation_final_with_ids.md"


def _local_name(tag: str | bytes | etree.QName) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _top_level_paragraphs(xml: bytes) -> list[etree._Element]:
    root = etree.fromstring(xml)
    return [child for child in root if _local_name(child.tag) == "p"]


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


def _tracked_blocks() -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for line in TRACKED.read_text(encoding="utf-8").splitlines()
        if (match := re.match(r"^\[([^\]]+)\]\s+(.*)$", line)) is not None
    }


def _footnote_texts(paragraph: etree._Element) -> tuple[str, ...]:
    return tuple(
        "".join(
            text_node.text or ""
            for text_node in footnote.iter()
            if _local_name(text_node.tag) == "t"
        ).strip()
        for footnote in paragraph.iter()
        if _local_name(footnote.tag) == "footNote"
    )


def _canonical_hash(element: etree._Element) -> str:
    normalized = copy.deepcopy(element)
    for node in normalized.iter():
        if _local_name(node.tag) == "footNote":
            node.set("number", "0")
        if (
            _local_name(node.tag) == "autoNum"
            and node.get("numType") == "FOOTNOTE"
        ):
            node.set("num", "0")
    serialized = etree.tostring(
        normalized,
        method="c14n",
        with_comments=True,
    )
    return hashlib.sha256(serialized).hexdigest()


def _main_text_run_style(paragraph: etree._Element) -> str:
    return next(
        child.get("charPrIDRef", "")
        for child in paragraph
        if _local_name(child.tag) == "run"
        and any(
            _local_name(text_node.tag) == "t" and bool(text_node.text)
            for text_node in child.iter()
        )
    )


def test_build_revised_hwpx_preserves_unrelated_content(tmp_path: Path) -> None:
    output = tmp_path / "revised.hwpx"

    build_revised_hwpx(SOURCE, TRACKED, output)

    with (
        zipfile.ZipFile(SOURCE) as source_zip,
        zipfile.ZipFile(output) as output_zip,
    ):
        assert output_zip.testzip() is None
        ignored_members = {"Contents/section0.xml", "Preview/PrvText.txt"}
        for member in source_zip.namelist():
            if member not in ignored_members:
                assert output_zip.read(member) == source_zip.read(member)

        source_paragraphs = _top_level_paragraphs(
            source_zip.read("Contents/section0.xml")
        )
        output_paragraphs = _top_level_paragraphs(
            output_zip.read("Contents/section0.xml")
        )

    touched_source_indices = {
        12,
        13,
        14,
        15,
        16,
        21,
        22,
        23,
        26,
        27,
        28,
        30,
        48,
        121,
        122,
        123,
    }
    untouched_hashes = [
        _canonical_hash(paragraph)
        for index, paragraph in enumerate(source_paragraphs)
        if index not in touched_source_indices
    ]
    output_hashes = [_canonical_hash(paragraph) for paragraph in output_paragraphs]
    cursor = 0
    for expected_hash in untouched_hashes:
        cursor = output_hashes.index(expected_hash, cursor) + 1

    visible_text = "\n".join(map(_direct_text, output_paragraphs))
    assert "본론 수정이 마무리 된 이후에 변경된 내용에 맞추어 수정할 예정" not in visible_text
    assert "I. 서론" in visible_text
    assert "VI. 결론" in visible_text
    assert "본고의 핵심 연구 질문은" in visible_text
    assert "대규모 크롤링에서 설정되는 동시 요청 수" in visible_text
    assert "이러한 행위 중심적 판단구조는 사법 실무에서" in visible_text
    assert "III. 생성형 인공지능 학습 데이터에 대한" in visible_text


def test_build_revised_hwpx_applies_tracked_technical_paragraphs(
    tmp_path: Path,
) -> None:
    output = tmp_path / "revised.hwpx"
    tracked_blocks = _tracked_blocks()

    build_revised_hwpx(SOURCE, TRACKED, output)

    with zipfile.ZipFile(output) as output_zip:
        output_paragraphs = _top_level_paragraphs(
            output_zip.read("Contents/section0.xml")
        )

    for block_id in ("32", "38"):
        tracked_text = tracked_blocks[block_id]
        paragraph = next(
            candidate
            for candidate in output_paragraphs
            if _direct_text(candidate).startswith(tracked_text[:30])
        )
        expected = tracked_text
        for footnote_text in sorted(
            _footnote_texts(paragraph),
            key=len,
            reverse=True,
        ):
            if expected.endswith(footnote_text):
                expected = expected[: -len(footnote_text)].rstrip()
                break
        assert _direct_text(paragraph) == expected


def test_added_citation_suffixes_become_numbered_footnotes(
    tmp_path: Path,
) -> None:
    output = tmp_path / "revised.hwpx"
    tracked_blocks = _tracked_blocks()

    build_revised_hwpx(SOURCE, TRACKED, output)

    with zipfile.ZipFile(output) as output_zip:
        root = etree.fromstring(output_zip.read("Contents/section0.xml"))
    output_paragraphs = _top_level_paragraphs(
        etree.tostring(root),
    )

    citation_ranges = {
        "ADD-I-2": ("류시원,", None),
        "ADD-VI-3": ("국가법령정보센터 판례 검색 결과", "둘째,"),
    }
    for block_id, (citation_start, citation_end) in citation_ranges.items():
        tracked_text = tracked_blocks[block_id]
        start = tracked_text.index(citation_start)
        end = (
            len(tracked_text)
            if citation_end is None
            else tracked_text.index(citation_end)
        )
        expected_direct_text = (
            tracked_text[:start] + tracked_text[end:]
        ).strip()
        expected_footnote = tracked_text[start:end].strip()
        paragraph = next(
            candidate
            for candidate in output_paragraphs
            if _direct_text(candidate).startswith(
                expected_direct_text[:30],
            )
        )

        assert _direct_text(paragraph) == expected_direct_text
        assert _footnote_texts(paragraph) == (expected_footnote,)

    footnotes = [
        footnote
        for footnote in root.iter()
        if _local_name(footnote.tag) == "footNote"
    ]
    assert len(footnotes) == 36
    assert [footnote.get("number") for footnote in footnotes] == [
        str(number) for number in range(1, 37)
    ]


def test_build_revised_hwpx_keeps_footnotes_as_footnotes(tmp_path: Path) -> None:
    output = tmp_path / "revised.hwpx"

    build_revised_hwpx(SOURCE, TRACKED, output)

    with (
        zipfile.ZipFile(SOURCE) as source_zip,
        zipfile.ZipFile(output) as output_zip,
    ):
        source_root = etree.fromstring(source_zip.read("Contents/section0.xml"))
        output_root = etree.fromstring(output_zip.read("Contents/section0.xml"))

    source_footnotes = sum(
        1
        for element in source_root.iter()
        if _local_name(element.tag) == "footNote"
    )
    output_footnotes = sum(
        1
        for element in output_root.iter()
        if _local_name(element.tag) == "footNote"
    )
    assert output_footnotes == source_footnotes + 1

    output_paragraphs = [
        child for child in output_root if _local_name(child.tag) == "p"
    ]
    paragraph_49 = next(
        paragraph
        for paragraph in output_paragraphs
        if _direct_text(paragraph).startswith("기존 검색엔진 크롤링은")
    )
    assert (
        sum(
            1
            for element in paragraph_49.iter()
            if _local_name(element.tag) == "footNote"
        )
        == 1
    )
    assert "OpenAI, “Overview of OpenAI Crawlers”" not in _direct_text(paragraph_49)


def test_added_paragraphs_use_their_section_body_styles(
    tmp_path: Path,
) -> None:
    output = tmp_path / "revised.hwpx"

    build_revised_hwpx(SOURCE, TRACKED, output)

    with zipfile.ZipFile(output) as output_zip:
        output_paragraphs = _top_level_paragraphs(
            output_zip.read("Contents/section0.xml")
        )

    chapter_two_body = next(
        paragraph
        for paragraph in output_paragraphs
        if _direct_text(paragraph).startswith("기존 검색엔진 크롤링은")
    )
    added_chapter_two_body = next(
        paragraph
        for paragraph in output_paragraphs
        if _direct_text(paragraph).startswith("결국 검색 목적과 생성형 인공지능")
    )
    assert _main_text_run_style(added_chapter_two_body) == _main_text_run_style(
        chapter_two_body
    )
    assert added_chapter_two_body.attrib == chapter_two_body.attrib

    introduction_body = next(
        paragraph
        for paragraph in output_paragraphs
        if _direct_text(paragraph).startswith("생성형 인공지능 학습용 웹 크롤링은")
    )
    added_introduction_body = next(
        paragraph
        for paragraph in output_paragraphs
        if _direct_text(paragraph).startswith("본고의 핵심적인 기여는")
    )
    assert _main_text_run_style(
        added_introduction_body
    ) == _main_text_run_style(introduction_body)
    assert added_introduction_body.attrib == introduction_body.attrib
