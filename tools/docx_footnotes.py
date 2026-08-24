from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
FOOTNOTE_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
)
FOOTNOTE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
)


def _w(name: str) -> str:
    return f"{{{W}}}{name}"


def _special_footnote(parent: etree._Element, note_id: int, kind: str) -> None:
    note = etree.SubElement(
        parent,
        _w("footnote"),
        {_w("id"): str(note_id), _w("type"): kind},
    )
    paragraph = etree.SubElement(note, _w("p"))
    run = etree.SubElement(paragraph, _w("r"))
    etree.SubElement(run, _w(kind))


def _text_paragraph(parent: etree._Element, text: str) -> None:
    paragraph = etree.SubElement(parent, _w("p"))
    paragraph_properties = etree.SubElement(paragraph, _w("pPr"))
    etree.SubElement(paragraph_properties, _w("pStyle"), {_w("val"): "FootnoteText"})
    run = etree.SubElement(paragraph, _w("r"))
    run_properties = etree.SubElement(run, _w("rPr"))
    etree.SubElement(run_properties, _w("rStyle"), {_w("val"): "FootnoteReference"})
    etree.SubElement(run, _w("footnoteRef"))
    text_node = etree.SubElement(run, _w("t"), {_w("space"): "preserve"})
    text_node.text = f") {text}"


def _footnotes_xml(notes: list[list[str]]) -> bytes:
    root = etree.Element(_w("footnotes"), nsmap={"w": W})
    _special_footnote(root, -1, "separator")
    _special_footnote(root, 0, "continuationSeparator")
    for note_id, paragraphs in enumerate(notes, start=1):
        note = etree.SubElement(root, _w("footnote"), {_w("id"): str(note_id)})
        for text in paragraphs or [""]:
            _text_paragraph(note, text)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def add_footnotes(docx_path: Path, notes: list[list[str]]) -> None:
    if not notes:
        return
    with zipfile.ZipFile(docx_path) as source:
        members = {name: source.read(name) for name in source.namelist()}

    relationships = etree.fromstring(members["word/_rels/document.xml.rels"])
    relationship_ids = [
        int(value[3:])
        for element in relationships
        if (value := element.get("Id", "")).startswith("rId") and value[3:].isdigit()
    ]
    etree.SubElement(
        relationships,
        etree.QName(REL, "Relationship"),
        {
            "Id": f"rId{max(relationship_ids, default=0) + 1}",
            "Type": FOOTNOTE_REL,
            "Target": "footnotes.xml",
        },
    )
    members["word/_rels/document.xml.rels"] = etree.tostring(
        relationships, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    content_types = etree.fromstring(members["[Content_Types].xml"])
    etree.SubElement(
        content_types,
        etree.QName(CONTENT_TYPES, "Override"),
        {"PartName": "/word/footnotes.xml", "ContentType": FOOTNOTE_CONTENT_TYPE},
    )
    members["[Content_Types].xml"] = etree.tostring(
        content_types, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    members["word/footnotes.xml"] = _footnotes_xml(notes)

    temporary = docx_path.with_suffix(".footnotes.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in members.items():
            target.writestr(name, payload)
    temporary.replace(docx_path)
