from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

from lxml import etree


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname


def _normalized(parts: list[str]) -> str:
    return re.sub(r"\s+", "", "".join(parts))


def _has_ancestor(element: etree._Element, name: str) -> bool:
    return any(_local(parent) == name for parent in element.iterancestors())


def _read_xml(archive: zipfile.ZipFile, name: str) -> etree._Element:
    return etree.fromstring(archive.read(name))


def _source_body_text(section: etree._Element) -> str:
    parts = [
        node.text or ""
        for node in section.iter()
        if _local(node) == "t" and not _has_ancestor(node, "footNote")
    ]
    return _normalized(parts)


def _target_body_text(document: etree._Element) -> str:
    parts: list[str] = []
    for node in document.iter():
        if _local(node) != "t":
            continue
        run = node.getparent()
        if run is not None and any(
            _local(child) == "footnoteReference" for child in run
        ):
            continue
        parts.append(node.text or "")
    return _normalized(parts)


def _source_footnotes(section: etree._Element) -> list[str]:
    return [
        _normalized([node.text or "" for node in note.iter() if _local(node) == "t"])
        for note in section.iter()
        if _local(note) == "footNote"
    ]


def _target_footnotes(footnotes: etree._Element) -> list[str]:
    result: list[str] = []
    for note in footnotes:
        note_id = next(
            (
                value
                for key, value in note.attrib.items()
                if etree.QName(key).localname == "id"
            ),
            "0",
        )
        if int(note_id) <= 0:
            continue
        text = _normalized(
            [node.text or "" for node in note.iter() if _local(node) == "t"]
        )
        result.append(text.removeprefix(")"))
    return result


def validate_documents(source: Path, target: Path) -> dict[str, object]:
    with zipfile.ZipFile(source) as source_archive:
        source_bad_member = source_archive.testzip()
        source_section = _read_xml(source_archive, "Contents/section0.xml")
    with zipfile.ZipFile(target) as target_archive:
        target_bad_member = target_archive.testzip()
        target_document = _read_xml(target_archive, "word/document.xml")
        target_footnotes = _read_xml(target_archive, "word/footnotes.xml")

    source_notes = _source_footnotes(source_section)
    target_notes = _target_footnotes(target_footnotes)
    source_tables = sum(_local(node) == "tbl" for node in source_section.iter())
    target_tables = sum(_local(node) == "tbl" for node in target_document.iter())
    source_images = sum(_local(node) == "pic" for node in source_section.iter())
    target_images = sum(_local(node) == "drawing" for node in target_document.iter())
    body_matches = _source_body_text(source_section) == _target_body_text(
        target_document
    )
    notes_match = source_notes == target_notes
    valid = all(
        (
            source_bad_member is None,
            target_bad_member is None,
            body_matches,
            notes_match,
            source_tables == target_tables,
            source_images == target_images,
        )
    )
    return {
        "valid": valid,
        "source_zip_valid": source_bad_member is None,
        "target_zip_valid": target_bad_member is None,
        "body_text_matches": body_matches,
        "footnote_text_matches": notes_match,
        "source_footnotes": len(source_notes),
        "target_footnotes": len(target_notes),
        "source_tables": source_tables,
        "target_tables": target_tables,
        "source_images": source_images,
        "target_images": target_images,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate HWPX-to-DOCX preservation.")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    arguments = parser.parse_args()
    report = validate_documents(arguments.source, arguments.target)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
