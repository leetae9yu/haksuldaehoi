from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

from lxml import etree

from tools.hwpx_format_map import compare_format_maps

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname


def _normalized(parts: list[str]) -> str:
    return re.sub(r"\s+", "", "".join(parts))


def _word_spaced(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _has_ancestor(element: etree._Element, name: str) -> bool:
    return any(_local(parent) == name for parent in element.iterancestors())


def _word_spaced_xml(
    root: etree._Element,
    break_names: set[str],
    excluded_ancestors: set[str],
) -> str:
    parts: list[str] = []
    for event, node in etree.iterwalk(root, events=("start", "end")):
        if any(_has_ancestor(node, name) for name in excluded_ancestors):
            continue
        name = _local(node)
        if event == "start" and name == "t":
            parts.append(node.text or "")
        elif event == "start" and name in break_names:
            parts.append(" ")
        elif event == "end" and name == "p":
            parts.append("\n")
    return _word_spaced(parts)


def _docx_notes(
    document: etree._Element,
    footnotes: etree._Element,
) -> list[str]:
    notes = {
        note.get(f"{{{W}}}id", ""): _normalized(
            [
                node.text or ""
                for node in note.iter()
                if _local(node) == "t"
            ]
        )
        for note in footnotes
        if note.get(f"{{{W}}}type") is None
    }
    return [
        notes[node.get(f"{{{W}}}id", "")]
        for node in document.iter()
        if _local(node) == "footnoteReference"
    ]


def _hwpx_notes(section: etree._Element) -> list[str]:
    return [
        _normalized(
            [node.text or "" for node in note.iter() if _local(node) == "t"]
        )
        for note in section.iter()
        if _local(note) == "footNote"
    ]


def _docx_formatted_text(
    document: etree._Element,
    property_name: str,
) -> list[str]:
    parts: list[str] = []
    for run in document.iter():
        if _local(run) != "r":
            continue
        properties = next(
            (child for child in run if _local(child) == "rPr"),
            None,
        )
        property_children = [] if properties is None else list(properties)
        matching = [
            child
            for child in property_children
            if _local(child) == property_name
        ]
        if not matching or matching[0].get(
            f"{{{W}}}val",
            "single",
        ).lower() in {"0", "false", "off", "none"}:
            continue
        text = _normalized(
            [node.text or "" for node in run.iter() if _local(node) == "t"]
        )
        if text:
            parts.append(text)
    return parts


def _hwpx_formatted_text(
    section: etree._Element,
    header: etree._Element,
    property_name: str,
) -> str:
    style_ids = {
        node.get("id", "")
        for node in header.iter()
        if _local(node) == "charPr"
        and any(
            _local(child) == property_name
            and child.get("type", "SOLID") != "NONE"
            for child in node
        )
    }
    return _normalized(
        [
            child.text or ""
            for run in section.iter()
            if _local(run) == "run"
            and run.get("charPrIDRef", "") in style_ids
            and not _has_ancestor(run, "footNote")
            for child in run
            if _local(child) == "t"
        ]
    )


def _style_references_valid(
    section: etree._Element,
    header: etree._Element,
) -> bool:
    paragraph_ids = {
        node.get("id", "")
        for node in header.iter()
        if _local(node) == "paraPr"
    }
    character_ids = {
        node.get("id", "")
        for node in header.iter()
        if _local(node) == "charPr"
    }
    return all(
        node.get("paraPrIDRef", "") in paragraph_ids
        for node in section.iter()
        if _local(node) == "p"
    ) and all(
        node.get("charPrIDRef", "") in character_ids
        for node in section.iter()
        if _local(node) == "run"
    )


def validate_documents(
    source: Path,
    reference: Path,
    candidate: Path,
) -> dict[str, object]:
    with zipfile.ZipFile(source) as docx:
        source_bad_member = docx.testzip()
        document = etree.fromstring(docx.read("word/document.xml"))
        footnotes = etree.fromstring(docx.read("word/footnotes.xml"))
    with zipfile.ZipFile(candidate) as hwpx:
        candidate_bad_member = hwpx.testzip()
        section = etree.fromstring(hwpx.read("Contents/section0.xml"))
        header = etree.fromstring(hwpx.read("Contents/header.xml"))
        mimetype_stored = (
            hwpx.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        )

    source_body = _normalized(
        [node.text or "" for node in document.iter() if _local(node) == "t"]
    )
    source_body_spaced = _word_spaced_xml(
        document,
        {"br", "tab"},
        set(),
    )
    candidate_body = _normalized(
        [
            node.text or ""
            for node in section.iter()
            if _local(node) == "t"
            and not _has_ancestor(node, "footNote")
            and not _has_ancestor(node, "fieldBegin")
        ]
    )
    candidate_body_spaced = _word_spaced_xml(
        section,
        {"lineBreak", "tab"},
        {"footNote", "fieldBegin"},
    )
    source_bold = _docx_formatted_text(document, "b")
    source_underline = _docx_formatted_text(document, "u")
    candidate_bold = _hwpx_formatted_text(section, header, "bold")
    candidate_underline = _hwpx_formatted_text(section, header, "underline")
    format_mismatches = compare_format_maps(reference, candidate)
    report: dict[str, object] = {
        "source_zip_valid": source_bad_member is None,
        "candidate_zip_valid": candidate_bad_member is None,
        "mimetype_stored": mimetype_stored,
        "body_text_matches": source_body == candidate_body,
        "word_spacing_matches": source_body_spaced == candidate_body_spaced,
        "footnote_text_matches": _docx_notes(document, footnotes)
        == _hwpx_notes(section),
        "source_footnotes": len(_docx_notes(document, footnotes)),
        "candidate_footnotes": len(_hwpx_notes(section)),
        "source_tables": sum(_local(node) == "tbl" for node in document.iter()),
        "candidate_tables": sum(_local(node) == "tbl" for node in section.iter()),
        "source_images": sum(
            _local(node) == "drawing" for node in document.iter()
        ),
        "candidate_images": sum(
            _local(node) == "pic" for node in section.iter()
        ),
        "bold_text_preserved": all(
            text in candidate_bold for text in source_bold
        ),
        "underline_text_preserved": all(
            text in candidate_underline for text in source_underline
        ),
        "style_references_valid": _style_references_valid(section, header),
        "memo_controls": sum(
            _local(node) == "fieldBegin" and node.get("type") == "MEMO"
            for node in section.iter()
        ),
        "format_mismatches": format_mismatches,
    }
    report["valid"] = all(
        (
            report["source_zip_valid"],
            report["candidate_zip_valid"],
            report["mimetype_stored"],
            report["body_text_matches"],
            report["word_spacing_matches"],
            report["footnote_text_matches"],
            report["source_tables"] == report["candidate_tables"],
            report["source_images"] == report["candidate_images"],
            report["bold_text_preserved"],
            report["underline_text_preserved"],
            report["style_references_valid"],
            report["memo_controls"] == 0,
            not format_mismatches,
        )
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate DOCX-to-HWPX conversion.")
    parser.add_argument("source", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    arguments = parser.parse_args()
    report = validate_documents(
        arguments.source,
        arguments.reference,
        arguments.candidate,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
