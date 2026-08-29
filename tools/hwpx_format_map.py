from __future__ import annotations

import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

TITLE_PREFIX = "생성형 AI 학습을 위한 무단 데이터 크롤링"
SUBTITLE_TOKEN = "성과도용 일반조항 (파)목을 중심으로"
CHAPTER_PATTERN = re.compile(r"^[ⅠⅡⅢⅣⅤⅥVI]+\.\s")
SECTION_PATTERN = re.compile(r"^\d+\.\s")
SUBSECTION_PATTERN = re.compile(r"^\(\d+\)\s")


@dataclass(frozen=True)
class ParagraphStyle:
    para_style: str
    run_styles: tuple[str, ...]


@dataclass(frozen=True)
class FormatMap:
    role_styles: dict[str, frozenset[ParagraphStyle]]
    table_styles: dict[str, ParagraphStyle]
    cover_signature: tuple[bytes, ...]
    page_signature: bytes
    style_ids: frozenset[str]


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _direct_children(
    element: etree._Element,
    name: str,
) -> list[etree._Element]:
    return [child for child in element if _local_name(child) == name]


def _direct_text(paragraph: etree._Element) -> str:
    return "".join(
        child.text or ""
        for run in _direct_children(paragraph, "run")
        for child in run
        if _local_name(child) == "t"
    ).strip()


def _has_ancestor(element: etree._Element, name: str) -> bool:
    return any(_local_name(parent) == name for parent in element.iterancestors())


def _role(paragraph: etree._Element, text: str) -> str:
    if _has_ancestor(paragraph, "footNote"):
        return "footnote"
    if _has_ancestor(paragraph, "tc"):
        return "table-cell"
    if text.startswith(TITLE_PREFIX):
        return "title"
    if SUBTITLE_TOKEN in text:
        return "subtitle"
    if CHAPTER_PATTERN.match(text):
        return "chapter"
    if SECTION_PATTERN.match(text):
        return "section"
    if SUBSECTION_PATTERN.match(text):
        return "subsection"
    if text.startswith("[") and text.endswith("]"):
        return "bibliography-heading"
    return "body"


def _paragraph_style(paragraph: etree._Element) -> ParagraphStyle:
    run_styles: list[str] = []
    for run in _direct_children(paragraph, "run"):
        if not any(_local_name(child) == "t" for child in run):
            continue
        style_id = run.get("charPrIDRef", "")
        run_styles.append(style_id)
        break
    return ParagraphStyle(
        para_style=paragraph.get("paraPrIDRef", ""),
        run_styles=tuple(run_styles),
    )


def _canonical_element(element: etree._Element | None) -> bytes:
    if element is None:
        return b""
    attributes = tuple(
        sorted(
            (etree.QName(key).localname, value)
            for key, value in element.attrib.items()
        )
    )
    children = tuple(
        _canonical_element(child)
        for child in element
    )
    return repr((_local_name(element), attributes, children)).encode()


def extract_format_map(path: Path) -> FormatMap:
    with zipfile.ZipFile(path) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
        section = etree.fromstring(archive.read("Contents/section0.xml"))

    style_ids = frozenset(
        element.get("id", "")
        for element in header.iter()
        if _local_name(element) in {"paraPr", "charPr"}
    )
    styles: defaultdict[str, set[ParagraphStyle]] = defaultdict(set)
    for paragraph in section.iter():
        if _local_name(paragraph) != "p":
            continue
        text = _direct_text(paragraph)
        if text:
            styles[_role(paragraph, text)].add(_paragraph_style(paragraph))
    table_styles: dict[str, ParagraphStyle] = {}
    tables = [
        element for element in section.iter() if _local_name(element) == "tbl"
    ]
    for table_index, table in enumerate(tables):
        for cell in (
            element for element in table.iter() if _local_name(element) == "tc"
        ):
            address = next(
                child for child in cell if _local_name(child) == "cellAddr"
            )
            paragraphs = [
                element
                for element in cell.iter()
                if _local_name(element) == "p"
            ]
            for paragraph_index, paragraph in enumerate(paragraphs):
                key = (
                    f"t{table_index}:r{address.get('rowAddr', '0')}:"
                    f"c{address.get('colAddr', '0')}:p{paragraph_index}"
                )
                table_styles[key] = _paragraph_style(paragraph)

    section_properties = next(
        (
            element
            for element in section.iter()
            if _local_name(element) == "secPr"
        ),
        None,
    )
    cover_signature: list[bytes] = []
    for paragraph in _direct_children(section, "p"):
        lines = next(
            (
                element
                for element in paragraph.iter()
                if _local_name(element) == "linesegarray"
            ),
            None,
        )
        cover_signature.append(
            repr(
                (
                    paragraph.get("paraPrIDRef", ""),
                    paragraph.get("pageBreak", ""),
                    _role(paragraph, _direct_text(paragraph)),
                    _canonical_element(lines),
                    any(
                        _local_name(element) == "tbl"
                        for element in paragraph.iter()
                    ),
                )
            ).encode()
        )
        if any(
            _local_name(element) == "tbl"
            for element in paragraph.iter()
        ):
            break
    return FormatMap(
        role_styles={
            role: frozenset(role_style)
            for role, role_style in styles.items()
        },
        table_styles=table_styles,
        cover_signature=tuple(cover_signature),
        page_signature=_canonical_element(section_properties),
        style_ids=style_ids,
    )


def compare_format_maps(reference: Path, candidate: Path) -> list[str]:
    expected = extract_format_map(reference)
    actual = extract_format_map(candidate)
    mismatches: list[str] = []

    if expected.page_signature != actual.page_signature:
        mismatches.append("page-settings")
    if expected.cover_signature != actual.cover_signature:
        mismatches.append("cover-layout")
    if expected.style_ids != actual.style_ids:
        mismatches.append("style-definitions")
    for key, expected_style in expected.table_styles.items():
        actual_style = actual.table_styles.get(key)
        if actual_style != expected_style:
            mismatches.append(
                f"table-style:{key}:{expected_style}:{actual_style}"
            )

    for role, actual_styles in actual.role_styles.items():
        if role == "table-cell":
            continue
        expected_styles = expected.role_styles.get(role, frozenset())
        for style in sorted(
            actual_styles - expected_styles,
            key=lambda item: (item.para_style, item.run_styles),
        ):
            mismatches.append(
                "paragraph-style:"
                f"{role}:{style.para_style}:{','.join(style.run_styles)}"
            )
    return mismatches
