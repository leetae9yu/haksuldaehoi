from __future__ import annotations

import copy
import re
import zipfile
from pathlib import Path

from docx.text.hyperlink import Hyperlink
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

from tools.docx_hwpx_styles import CharCatalog

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def direct(element: etree._Element, name: str) -> list[etree._Element]:
    return [child for child in element if local_name(child) == name]


def direct_text(paragraph: etree._Element) -> str:
    return "".join(
        child.text or ""
        for run in direct(paragraph, "run")
        for child in run
        if local_name(child) == "t"
    )


def read_footnotes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/footnotes.xml"))
    return {
        note.get(f"{{{W}}}id", ""): "".join(
            text.text or ""
            for text in note.iter()
            if local_name(text) == "t"
        )
        for note in root
        if note.get(f"{{{W}}}type") is None
    }


def _source_runs(paragraph: Paragraph) -> list[Run]:
    result: list[Run] = []
    for content in paragraph.iter_inner_content():
        if isinstance(content, Run):
            result.append(content)
        elif isinstance(content, Hyperlink):
            result.extend(content.runs)
    return result


def _append_text(parent: etree._Element, text: str) -> None:
    target = etree.SubElement(parent, f"{{{HP}}}t")
    chunks = text.replace("\r", "").split("\n")
    target.text = chunks[0]
    for chunk in chunks[1:]:
        line_break = etree.SubElement(target, f"{{{HP}}}lineBreak")
        line_break.tail = chunk


def _footnote_control(
    template: etree._Element,
    citation: str,
    number: int,
) -> etree._Element:
    footnote = copy.deepcopy(template)
    for element in footnote.iter():
        if local_name(element) == "autoNum":
            element.set("num", str(number))
    texts = [
        element
        for element in footnote.iter()
        if local_name(element) == "t"
    ]
    for index, text in enumerate(texts):
        text.text = citation if index == 0 else ""
        for child in list(text):
            text.remove(child)
    return footnote


def _source_note_ids(paragraph: Paragraph) -> list[str]:
    return [
        child.get(f"{{{W}}}id", "")
        for run in _source_runs(paragraph)
        for child in run._r
        if local_name(child) == "footnoteReference"
    ]


def _update_matching_footnotes(
    target: etree._Element,
    source: Paragraph,
    notes: dict[str, str],
    note_template: etree._Element,
    note_number: list[int],
) -> bool:
    note_ids = _source_note_ids(source)
    controls = [
        node
        for node in target.iter()
        if local_name(node) == "footNote"
    ]
    source_text = re.sub(r"\s+", "", source.text)
    target_text = re.sub(r"\s+", "", direct_text(target))
    if source_text != target_text or len(note_ids) != len(controls):
        return False
    for note_id, control in zip(note_ids, controls, strict=True):
        note_number[0] += 1
        replacement = _footnote_control(
            note_template,
            notes.get(note_id, ""),
            note_number[0],
        )
        parent = control.getparent()
        if parent is None:
            return False
        parent.replace(control, replacement)
    return True


def _strip_memo_controls(target: etree._Element) -> None:
    memo_ids = {
        node.get("id", "")
        for node in target.iter()
        if local_name(node) == "fieldBegin" and node.get("type") == "MEMO"
    }
    for parent in target.iter():
        for child in list(parent):
            if local_name(child) != "ctrl":
                continue
            fields = [
                node
                for node in child.iter()
                if local_name(node) in {"fieldBegin", "fieldEnd"}
            ]
            if any(
                node.get("type") == "MEMO"
                or node.get("id", "") in memo_ids
                for node in fields
            ):
                parent.remove(child)


def fill_paragraph(
    target: etree._Element,
    source: Paragraph,
    catalog: CharCatalog,
    notes: dict[str, str],
    note_template: etree._Element,
    note_number: list[int],
) -> None:
    _strip_memo_controls(target)
    if _update_matching_footnotes(
        target,
        source,
        notes,
        note_template,
        note_number,
    ):
        return
    structural_runs = [
        run
        for run in direct(target, "run")
        if any(
            local_name(child) in {"tbl", "pic", "secPr"}
            for child in run
        )
    ]
    footnote_styles = [
        run.get("charPrIDRef", "0")
        for run in direct(target, "run")
        if any(local_name(node) == "footNote" for node in run.iter())
    ]
    note_parent = note_template.getparent()
    note_run = note_parent.getparent() if note_parent is not None else None
    fallback_note_style = (
        note_run.get("charPrIDRef", "0") if note_run is not None else "0"
    )
    footnote_index = 0
    base_run = next(iter(direct(target, "run")), None)
    base_style = base_run.get("charPrIDRef", "0") if base_run is not None else "0"
    lines = next(iter(direct(target, "linesegarray")), None)
    for run in direct(target, "run"):
        target.remove(run)

    insertion = target.index(lines) if lines is not None else len(target)
    for source_run in _source_runs(source):
        has_footnote = any(
            local_name(child) == "footnoteReference"
            for child in source_run._r
        )
        if has_footnote:
            style_id = (
                footnote_styles[footnote_index]
                if footnote_index < len(footnote_styles)
                else fallback_note_style
            )
            footnote_index += 1
        else:
            style_id = catalog.closest(base_style, source_run)
        run = etree.Element(f"{{{HP}}}run", charPrIDRef=style_id)
        for child in source_run._r:
            kind = local_name(child)
            if kind == "t":
                _append_text(run, child.text or "")
            elif kind == "tab":
                text = etree.SubElement(run, f"{{{HP}}}t")
                etree.SubElement(text, f"{{{HP}}}tab")
            elif kind == "br":
                _append_text(run, " ")
            elif kind == "footnoteReference":
                note_id = child.get(f"{{{W}}}id", "")
                note_number[0] += 1
                control = etree.SubElement(run, f"{{{HP}}}ctrl")
                control.append(
                    _footnote_control(
                        note_template,
                        notes.get(note_id, ""),
                        note_number[0],
                    )
                )
        if len(run):
            target.insert(insertion, run)
            insertion += 1
    for run in structural_runs:
        target.insert(insertion, run)
        insertion += 1
