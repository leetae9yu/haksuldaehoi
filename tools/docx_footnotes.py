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


def _text_paragraph(
    parent: etree._Element, text: str, *, include_reference: bool
) -> None:
    paragraph = etree.SubElement(parent, _w("p"))
    paragraph_properties = etree.SubElement(paragraph, _w("pPr"))
    etree.SubElement(paragraph_properties, _w("pStyle"), {_w("val"): "Footnote"})
    etree.SubElement(paragraph_properties, _w("suppressLineNumbers"))
    etree.SubElement(paragraph_properties, _w("bidi"), {_w("val"): "0"})
    etree.SubElement(
        paragraph_properties, _w("ind"), {_w("start"): "339", _w("hanging"): "339"}
    )
    etree.SubElement(paragraph_properties, _w("jc"), {_w("val"): "start"})
    if include_reference:
        reference_run = etree.SubElement(paragraph, _w("r"))
        reference_properties = etree.SubElement(reference_run, _w("rPr"))
        etree.SubElement(
            reference_properties,
            _w("rStyle"),
            {_w("val"): "FootnoteCharacters"},
        )
        etree.SubElement(reference_run, _w("footnoteRef"))
    text_run = etree.SubElement(paragraph, _w("r"))
    if include_reference:
        etree.SubElement(text_run, _w("tab"))
    text_node = etree.SubElement(text_run, _w("t"))
    text_node.text = text


def _footnotes_xml(notes: list[list[str]]) -> bytes:
    root = etree.Element(_w("footnotes"), nsmap={"w": W})
    _special_footnote(root, 0, "separator")
    _special_footnote(root, 1, "continuationSeparator")
    for note_id, paragraphs in enumerate(notes, start=2):
        note = etree.SubElement(root, _w("footnote"), {_w("id"): str(note_id)})
        for index, text in enumerate(paragraphs or [""]):
            _text_paragraph(note, text, include_reference=index == 0)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _append_footnote_styles(styles: etree._Element) -> None:
    characters = etree.SubElement(
        styles,
        _w("style"),
        {_w("type"): "character", _w("styleId"): "FootnoteCharacters"},
    )
    etree.SubElement(characters, _w("name"), {_w("val"): "Footnote Characters"})
    etree.SubElement(characters, _w("qFormat"))
    etree.SubElement(characters, _w("rPr"))

    anchor = etree.SubElement(
        styles,
        _w("style"),
        {_w("type"): "character", _w("styleId"): "FootnoteAnchor"},
    )
    etree.SubElement(anchor, _w("name"), {_w("val"): "Footnote Anchor"})
    anchor_properties = etree.SubElement(anchor, _w("rPr"))
    etree.SubElement(anchor_properties, _w("vertAlign"), {_w("val"): "superscript"})

    footnote = etree.SubElement(
        styles,
        _w("style"),
        {_w("type"): "paragraph", _w("styleId"): "Footnote"},
    )
    etree.SubElement(footnote, _w("name"), {_w("val"): "Footnote Text"})
    etree.SubElement(footnote, _w("basedOn"), {_w("val"): "Normal"})
    paragraph_properties = etree.SubElement(footnote, _w("pPr"))
    etree.SubElement(paragraph_properties, _w("suppressLineNumbers"))
    etree.SubElement(
        paragraph_properties, _w("ind"), {_w("start"): "339", _w("hanging"): "339"}
    )
    run_properties = etree.SubElement(footnote, _w("rPr"))
    etree.SubElement(run_properties, _w("sz"), {_w("val"): "20"})
    etree.SubElement(run_properties, _w("szCs"), {_w("val"): "20"})


def _append_footnote_settings(settings: etree._Element) -> None:
    properties = etree.Element(_w("footnotePr"))
    etree.SubElement(properties, _w("numFmt"), {_w("val"): "decimal"})
    etree.SubElement(properties, _w("footnote"), {_w("id"): "0"})
    etree.SubElement(properties, _w("footnote"), {_w("id"): "1"})
    settings.insert(0, properties)


def _append_section_settings(document: etree._Element) -> None:
    section = next(
        (node for node in document.iter() if etree.QName(node).localname == "sectPr"),
        None,
    )
    if section is None:
        return
    properties = etree.Element(_w("footnotePr"))
    etree.SubElement(properties, _w("numFmt"), {_w("val"): "decimal"})
    section.insert(0, properties)


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
    styles = etree.fromstring(members["word/styles.xml"])
    _append_footnote_styles(styles)
    members["word/styles.xml"] = etree.tostring(
        styles, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    settings = etree.fromstring(members["word/settings.xml"])
    _append_footnote_settings(settings)
    members["word/settings.xml"] = etree.tostring(
        settings, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    document = etree.fromstring(members["word/document.xml"])
    _append_section_settings(document)
    members["word/document.xml"] = etree.tostring(
        document, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    members["word/footnotes.xml"] = _footnotes_xml(notes)

    temporary = docx_path.with_suffix(".footnotes.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in members.items():
            target.writestr(name, payload)
    temporary.replace(docx_path)
