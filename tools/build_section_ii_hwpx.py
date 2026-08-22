from __future__ import annotations

import copy
import io
import re
import urllib.request
import zipfile
from pathlib import Path

from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MARKDOWN = ROOT / "section_II_final.md"
OUTPUT = Path("/home/opc/oracle-shared/생성형AI_무단크롤링_II장_수정본.hwpx")
DOWNLOAD_URL = (
    "https://drive.usercontent.google.com/download"
    "?id=1fB_YZ4AhSdwQJtd9fJec5u3z1tvPeSZR&export=download&confirm=t"
)

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}


def qname(local_name: str) -> str:
    return f"{{{HP}}}{local_name}"


def element_text(element: etree._Element) -> str:
    return "".join(element.xpath('.//*[local-name()="t"]/text()')).strip()


def parse_markdown() -> tuple[list[tuple[str, str]], dict[int, str]]:
    text = SOURCE_MARKDOWN.read_text(encoding="utf-8")
    body, note_block = re.split(r"\n\*\*\[각주 목록\]\*\*\n", text, maxsplit=1)

    notes: dict[int, str] = {}
    for match in re.finditer(
        r"^\[각주 (\d+)\]\s*(.*?)(?=^\[각주 \d+\]|\Z)",
        note_block,
        flags=re.MULTILINE | re.DOTALL,
    ):
        notes[int(match.group(1))] = " ".join(match.group(2).split())

    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append(("body", " ".join(paragraph_lines).strip()))
            paragraph_lines.clear()

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("## "):
            flush_paragraph()
            blocks.append(("h1", line[3:].strip()))
        elif line.startswith("### "):
            flush_paragraph()
            blocks.append(("h2", line[4:].strip()))
        elif line.startswith("#### "):
            flush_paragraph()
            blocks.append(("h3", line[5:].strip()))
        elif line != "---":
            paragraph_lines.append(line)
    flush_paragraph()

    referenced = {
        int(number)
        for _, value in blocks
        for number in re.findall(r"\[각주 (\d+)\]", value)
    }
    if referenced != set(notes):
        raise ValueError(
            f"Footnote mismatch: referenced={sorted(referenced)}, notes={sorted(notes)}"
        )
    return blocks, notes


def plain_paragraph(template: etree._Element, text: str) -> etree._Element:
    paragraph = copy.deepcopy(template)
    for child in list(paragraph):
        paragraph.remove(child)
    run = etree.SubElement(paragraph, qname("run"))
    run.set("charPrIDRef", "19")
    text_element = etree.SubElement(run, qname("t"))
    text_element.text = text
    return paragraph


def footnote_control(
    template: etree._Element,
    number: int,
    note_text: str,
) -> etree._Element:
    control = copy.deepcopy(template)
    footnote = control.xpath('.//*[local-name()="footNote"]')[0]
    footnote.set("number", str(number))
    footnote.set("instId", str(1_500_000_000 + number))
    autonumbers = control.xpath('.//*[local-name()="autoNum"]')
    for autonumber in autonumbers:
        autonumber.set("num", str(number))
    note_text_nodes = control.xpath(
        './/*[local-name()="footNote"]'
        '//*[local-name()="subList"]'
        '//*[local-name()="p"]'
        '//*[local-name()="t"]'
    )
    if not note_text_nodes:
        raise ValueError("Footnote template has no text node")
    note_text_nodes[0].text = f" {note_text}"
    for node in note_text_nodes[1:]:
        node.text = ""
    for linesegarray in control.xpath('.//*[local-name()="linesegarray"]'):
        linesegarray.getparent().remove(linesegarray)
    return control


def body_paragraph(
    template: etree._Element,
    footnote_template: etree._Element,
    text: str,
    notes: dict[int, str],
) -> etree._Element:
    paragraph = copy.deepcopy(template)
    for child in list(paragraph):
        paragraph.remove(child)

    cursor = 0
    for match in re.finditer(r"\[각주 (\d+)\]", text):
        before = text[cursor : match.start()]
        if before:
            run = etree.SubElement(paragraph, qname("run"))
            run.set("charPrIDRef", "19")
            text_element = etree.SubElement(run, qname("t"))
            text_element.text = before

        number = int(match.group(1))
        run = etree.SubElement(paragraph, qname("run"))
        run.set("charPrIDRef", "19")
        run.append(footnote_control(footnote_template, number, notes[number]))
        cursor = match.end()

    remainder = text[cursor:]
    if remainder or len(paragraph) == 0:
        run = etree.SubElement(paragraph, qname("run"))
        run.set("charPrIDRef", "19")
        text_element = etree.SubElement(run, qname("t"))
        text_element.text = remainder
    return paragraph


def build_section_xml(original: bytes) -> tuple[bytes, str]:
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(original, parser)
    direct_paragraphs = list(root)

    section_settings = copy.deepcopy(direct_paragraphs[0])
    h1_template = next(
        paragraph
        for paragraph in direct_paragraphs
        if element_text(paragraph).startswith("Ⅱ. 웹 크롤링")
    )
    h2_template = next(
        paragraph
        for paragraph in direct_paragraphs
        if element_text(paragraph).startswith("1. 웹 크롤링")
    )
    h3_template = next(
        paragraph
        for paragraph in direct_paragraphs
        if element_text(paragraph).startswith("(1) 생성형")
    )
    body_template = next(
        paragraph
        for paragraph in direct_paragraphs
        if element_text(paragraph).startswith("웹 크롤링은 자동화된")
    )
    footnote_template = body_template.xpath(
        './/*[local-name()="ctrl"][.//*[local-name()="footNote"]]'
    )[0]

    blocks, notes = parse_markdown()
    for child in list(root):
        root.remove(child)
    root.append(section_settings)

    preview_parts: list[str] = []
    for kind, text in blocks:
        preview_parts.append(text)
        if kind == "body":
            paragraph = body_paragraph(body_template, footnote_template, text, notes)
        else:
            template = {"h1": h1_template, "h2": h2_template, "h3": h3_template}[kind]
            paragraph = plain_paragraph(template, text)
            if kind == "h1":
                paragraph.set("pageBreak", "0")
        root.append(paragraph)

    xml = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    return xml, "\n\n".join(preview_parts)


def download_original() -> bytes:
    request = urllib.request.Request(
        DOWNLOAD_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("Downloaded source is not a valid HWPX archive")
    return data


def main() -> None:
    original = download_original()
    source_zip = zipfile.ZipFile(io.BytesIO(original))
    section_xml, preview = build_section_xml(source_zip.read("Contents/section0.xml"))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w") as output_zip:
        mimetype = source_zip.read("mimetype")
        output_zip.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_STORED)
        for item in source_zip.infolist():
            if item.filename == "mimetype":
                continue
            if item.filename == "Contents/section0.xml":
                output_zip.writestr(item, section_xml)
            elif item.filename == "Preview/PrvText.txt":
                output_zip.writestr(item, preview.encode("utf-8"))
            else:
                output_zip.writestr(item, source_zip.read(item.filename))

    with zipfile.ZipFile(OUTPUT) as check_zip:
        bad_file = check_zip.testzip()
        if bad_file is not None:
            raise ValueError(f"Corrupt member: {bad_file}")
        parsed = etree.fromstring(check_zip.read("Contents/section0.xml"))
        visible_text = "\n".join(
            text.strip()
            for text in parsed.xpath(
                '/*[local-name()="sec"]/*[local-name()="p"]'
                '//*[local-name()="t"]/text()'
            )
            if text.strip()
        )
        footnote_count = len(parsed.xpath('//*[local-name()="footNote"]'))
        if "III." in visible_text or "Ⅰ. 서론" in visible_text:
            raise ValueError("Non-II chapter content remains in output")
        if footnote_count != 20:
            raise ValueError(f"Expected 20 footnotes, found {footnote_count}")
        if "[각주" in visible_text:
            raise ValueError("Markdown footnote markers remain in output")

    print(OUTPUT)
    print(f"bytes={OUTPUT.stat().st_size}")
    print("footnotes=20")


if __name__ == "__main__":
    main()
