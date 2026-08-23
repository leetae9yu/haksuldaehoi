from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Final

from lxml import etree

HP: Final = "http://www.hancom.co.kr/hwpml/2011/paragraph"
ADDED_FOOTNOTE_RANGES: Final = {
    "ADD-I-2": ("류시원,", None),
    "ADD-VI-3": ("국가법령정보센터 판례 검색 결과", "둘째,"),
}


def local_name(tag: str | bytes | etree.QName) -> str:
    return str(tag).rsplit("}", 1)[-1]


def direct_text(paragraph: etree._Element) -> str:
    return "".join(
        text_node.text or ""
        for child in paragraph
        if local_name(child.tag) == "run"
        for text_node in child.iter()
        if local_name(text_node.tag) == "t"
        and not any(
            local_name(ancestor.tag) == "footNote"
            for ancestor in text_node.iterancestors()
        )
    ).strip()


def footnote_texts(paragraph: etree._Element) -> tuple[str, ...]:
    return tuple(
        "".join(
            text_node.text or ""
            for text_node in footnote.iter()
            if local_name(text_node.tag) == "t"
        ).strip()
        for footnote in paragraph.iter()
        if local_name(footnote.tag) == "footNote"
    )


def footnote_controls(
    paragraph: etree._Element,
) -> tuple[etree._Element, ...]:
    return tuple(
        element
        for element in paragraph.iter()
        if local_name(element.tag) == "ctrl"
        and any(
            local_name(descendant.tag) == "footNote"
            for descendant in element.iter()
        )
    )


def rewrite_paragraph(
    paragraph: etree._Element,
    text: str,
    *,
    controls: tuple[etree._Element, ...] | None = None,
) -> None:
    first_run = next(
        child for child in paragraph if local_name(child.tag) == "run"
    )
    char_reference = first_run.get("charPrIDRef", "19")
    retained_controls = (
        tuple(
            copy.deepcopy(control)
            for control in footnote_controls(paragraph)
        )
        if controls is None
        else controls
    )
    for child in list(paragraph):
        paragraph.remove(child)
    run = etree.SubElement(paragraph, f"{{{HP}}}run")
    run.set("charPrIDRef", char_reference)
    text_node = etree.SubElement(run, f"{{{HP}}}t")
    text_node.text = text
    for control in retained_controls:
        footnote_run = etree.SubElement(
            paragraph,
            f"{{{HP}}}run",
        )
        footnote_run.set("charPrIDRef", char_reference)
        footnote_run.append(copy.deepcopy(control))


def new_body_paragraph(
    template: etree._Element,
    text: str,
) -> etree._Element:
    paragraph = copy.deepcopy(template)
    rewrite_paragraph(paragraph, text, controls=())
    return paragraph


def _split_added_footnote(
    block_id: str,
    text: str,
) -> tuple[str, str, str]:
    citation_start, citation_end = ADDED_FOOTNOTE_RANGES[block_id]
    start = text.index(citation_start)
    end = len(text) if citation_end is None else text.index(citation_end)
    return text[:start], text[start:end].strip(), text[end:]


def _new_footnote_control(
    template: etree._Element,
    citation: str,
    inst_id: int,
) -> etree._Element:
    control = copy.deepcopy(template)
    footnote = next(
        element
        for element in control.iter()
        if local_name(element.tag) == "footNote"
    )
    footnote.set("instId", str(inst_id))
    text_nodes = [
        element
        for element in footnote.iter()
        if local_name(element.tag) == "t"
    ]
    text_nodes[0].text = f" {citation}"
    for text_node in text_nodes[1:]:
        text_node.text = ""
    for linesegarray in [
        element
        for element in footnote.iter()
        if local_name(element.tag) == "linesegarray"
    ]:
        parent = linesegarray.getparent()
        if parent is not None:
            parent.remove(linesegarray)
    return control


def _append_text_run(
    paragraph: etree._Element,
    char_reference: str,
    text: str,
) -> None:
    run = etree.SubElement(paragraph, f"{{{HP}}}run")
    run.set("charPrIDRef", char_reference)
    text_node = etree.SubElement(run, f"{{{HP}}}t")
    text_node.text = text


def new_body_paragraph_with_footnote(
    template: etree._Element,
    block_id: str,
    text: str,
    footnote_template: etree._Element,
    inst_id: int,
) -> etree._Element:
    paragraph = copy.deepcopy(template)
    first_run = next(
        child for child in paragraph if local_name(child.tag) == "run"
    )
    char_reference = first_run.get("charPrIDRef", "19")
    before, citation, after = _split_added_footnote(block_id, text)
    for child in list(paragraph):
        paragraph.remove(child)
    _append_text_run(paragraph, char_reference, before)
    footnote_run = etree.SubElement(
        paragraph,
        f"{{{HP}}}run",
    )
    footnote_run.set("charPrIDRef", char_reference)
    footnote_run.append(
        _new_footnote_control(
            footnote_template,
            citation,
            inst_id,
        )
    )
    if after:
        _append_text_run(paragraph, char_reference, after)
    return paragraph


def iter_footnotes(root: etree._Element) -> Iterator[etree._Element]:
    return (
        element
        for element in root.iter()
        if local_name(element.tag) == "footNote"
    )


def renumber_footnotes(root: etree._Element) -> None:
    for number, footnote in enumerate(iter_footnotes(root), start=1):
        footnote.set("number", str(number))
        for auto_number in footnote.iter():
            if (
                local_name(auto_number.tag) == "autoNum"
                and auto_number.get("numType") == "FOOTNOTE"
            ):
                auto_number.set("num", str(number))


def insert_after(
    root: etree._Element,
    anchor: etree._Element,
    paragraph: etree._Element,
) -> None:
    root.insert(root.index(anchor) + 1, paragraph)
