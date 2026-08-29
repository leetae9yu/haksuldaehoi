from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher

from docx.text.paragraph import Paragraph
from lxml import etree

from tools.docx_hwpx_content import direct_text, local_name

ROLE_PATTERNS = (
    ("title", re.compile(r"^생성형 AI 학습을 위한 무단 데이터 크롤링")),
    ("subtitle", re.compile(r".*성과도용 일반조항.*중심으로")),
    ("chapter", re.compile(r"^[ⅠⅡⅢⅣⅤⅥVI]+\.\s")),
    ("section", re.compile(r"^\s*\d+\.\s")),
    ("subsection", re.compile(r"^\s*\(\d+\)\s")),
    ("heading", re.compile(r"^\[.+\]$")),
)


def role(text: str) -> str:
    stripped = text.strip()
    for name, pattern in ROLE_PATTERNS:
        if pattern.match(stripped):
            return name
    return "blank" if not stripped else "body"


def top_paragraphs(section: etree._Element) -> list[etree._Element]:
    return [child for child in section if local_name(child) == "p"]


def _choose_template(
    source: Paragraph,
    reference: list[Paragraph],
    templates: list[etree._Element],
    position: int,
) -> etree._Element:
    wanted = role(source.text)
    candidates = [
        index
        for index, paragraph in enumerate(reference)
        if role(paragraph.text) == wanted
        and not any(
            local_name(node) in {"tbl", "pic", "secPr"}
            for node in templates[index].iter()
        )
    ]
    index = min(candidates, key=lambda item: abs(item - position)) if candidates else 0
    return templates[index]


def aligned_paragraphs(
    source: list[Paragraph],
    reference: list[Paragraph],
    templates: list[etree._Element],
) -> list[tuple[Paragraph, etree._Element]]:
    matcher = SequenceMatcher(
        None,
        [paragraph.text for paragraph in reference],
        [paragraph.text for paragraph in source],
        autojunk=False,
    )
    result: list[tuple[Paragraph, etree._Element]] = []
    for operation, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        left_size = left_end - left_start
        right_size = right_end - right_start
        if operation in {"equal", "replace"} and left_size == right_size:
            result.extend(
                (source[right_start + offset], templates[left_start + offset])
                for offset in range(right_size)
            )
            continue
        if operation == "delete":
            continue
        for offset in range(right_size):
            source_paragraph = source[right_start + offset]
            result.append(
                (
                    source_paragraph,
                    _choose_template(
                        source_paragraph,
                        reference,
                        templates,
                        left_start + offset,
                    ),
                )
            )
    return result


def _contains_table(paragraph: etree._Element) -> bool:
    return any(local_name(node) == "tbl" for node in paragraph.iter())


def deduplicate_tables(section: etree._Element) -> None:
    seen: set[str] = set()
    tables = [
        node for node in section.iter() if local_name(node) == "tbl"
    ]
    for table in tables:
        table_id = table.get("id", "")
        if table_id not in seen:
            seen.add(table_id)
            continue
        paragraph = next(
            ancestor
            for ancestor in table.iterancestors()
            if local_name(ancestor) == "p"
            and ancestor.getparent() is section
        )
        section.remove(paragraph)


def restore_cover_layout(
    section: etree._Element,
    reference: list[etree._Element],
) -> None:
    current = top_paragraphs(section)
    reference_table = next(
        index
        for index, paragraph in enumerate(reference)
        if _contains_table(paragraph)
    )
    current_table = next(
        index
        for index, paragraph in enumerate(current)
        if _contains_table(paragraph)
    )
    current_by_role = {
        role(direct_text(paragraph)): paragraph
        for paragraph in current[:current_table]
        if role(direct_text(paragraph)) in {"title", "subtitle"}
    }
    prefix = [
        copy.deepcopy(
            current_by_role.get(role(direct_text(paragraph)), paragraph)
        )
        for paragraph in reference[:reference_table]
    ]
    rebuilt = prefix + [current[current_table]] + current[current_table + 1 :]
    for paragraph in current:
        section.remove(paragraph)
    for paragraph in rebuilt:
        section.append(paragraph)
