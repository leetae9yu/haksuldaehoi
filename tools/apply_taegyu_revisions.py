# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "lxml>=5.3",
# ]
# ///
#
# ─── How to run ───
# uv run -m tools.apply_taegyu_revisions SOURCE.hwpx TRACKED.md OUTPUT.hwpx

from __future__ import annotations

import copy
import re
import sys
import zipfile
from pathlib import Path
from typing import Final

from lxml import etree

from tools.hwpx_xml import ADDED_FOOTNOTE_RANGES, HP
from tools.hwpx_xml import direct_text as _direct_text
from tools.hwpx_xml import footnote_texts as _footnote_texts
from tools.hwpx_xml import local_name as _local_name

BLOCK_PATTERN: Final = re.compile(r"^\[([^\]]+)\]\s+(.*)$")
REPLACEMENT_STARTS: Final = {
    "23": "생성형 인공지능 학습용 웹 크롤링은",
    "25": "부정경쟁방지법 제2조 제1호 (카)목은",
    "30": "웹 크롤링은 자동화된 프로그램이",
    "32": "이와 관련하여 robots.txt는",
    "36": "생성형 인공지능(이하 ‘AI’) 모델은",
    "38": "이러한 과정을 구체적으로 살펴보면",
    "40": "생성형 AI 학습에 이용되는 데이터의 범위는",
    "42": "(2) 생성형 AI 학습용 웹 크롤링의 증가와 국내외 입법동향",
    "49": "기존 검색엔진 크롤링은",
    "178": "생성형 AI 학습을 위한 웹 크롤링은",
}


class RevisionFormatError(RuntimeError):
    """Raised when a tracked revision cannot be mapped safely."""


def _parse_blocks(path: Path) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = BLOCK_PATTERN.match(line)
        if match is not None:
            blocks[match.group(1)] = match.group(2)
    required = {"H-I", "23", "ADD-I-1", "25", "ADD-I-2", "ADD-I-3", "ADD-I-4", "ADD-II-1", "ADD-II-2", "H-VI", "178", "ADD-VI-1", "ADD-VI-2", "ADD-VI-3"}
    missing = required - blocks.keys()
    if missing:
        raise RevisionFormatError(f"Missing tracked blocks: {sorted(missing)}")
    return blocks


def _find_unique(
    paragraphs: list[etree._Element],
    prefix: str,
) -> etree._Element:
    matches = [
        paragraph
        for paragraph in paragraphs
        if _direct_text(paragraph).startswith(prefix)
    ]
    if len(matches) != 1:
        raise RevisionFormatError(
            f"Expected one paragraph beginning {prefix!r}; found {len(matches)}"
        )
    return matches[0]


def _revised_direct_text(
    tracked_text: str,
    paragraph: etree._Element,
) -> str:
    candidates = sorted(set(_footnote_texts(paragraph)), key=len, reverse=True)
    for footnote_text in candidates:
        if tracked_text.endswith(footnote_text):
            return tracked_text[: -len(footnote_text)].rstrip()
    if candidates:
        message = f"Tracked paragraph no longer ends with its original footnote: {_direct_text(paragraph)[:40]!r}"
        raise RevisionFormatError(message)
    return tracked_text


def _footnote_controls(
    paragraph: etree._Element,
) -> tuple[etree._Element, ...]:
    return tuple(
        element
        for element in paragraph.iter()
        if _local_name(element.tag) == "ctrl"
        and any(
            _local_name(descendant.tag) == "footNote"
            for descendant in element.iter()
        )
    )


def _rewrite_paragraph(
    paragraph: etree._Element,
    text: str,
    *,
    footnote_controls: tuple[etree._Element, ...] | None = None,
) -> None:
    first_run = next(
        child for child in paragraph if _local_name(child.tag) == "run"
    )
    char_reference = first_run.get("charPrIDRef", "19")
    controls = (
        tuple(
            copy.deepcopy(control)
            for control in _footnote_controls(paragraph)
        )
        if footnote_controls is None
        else footnote_controls
    )
    for child in list(paragraph):
        paragraph.remove(child)
    run = etree.SubElement(paragraph, f"{{{HP}}}run")
    run.set("charPrIDRef", char_reference)
    text_node = etree.SubElement(run, f"{{{HP}}}t")
    text_node.text = text
    for control in controls:
        footnote_run = etree.SubElement(paragraph, f"{{{HP}}}run")
        footnote_run.set("charPrIDRef", char_reference)
        footnote_run.append(copy.deepcopy(control))


def _new_body_paragraph(
    template: etree._Element,
    text: str,
) -> etree._Element:
    paragraph = copy.deepcopy(template)
    _rewrite_paragraph(paragraph, text, footnote_controls=())
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
        if _local_name(element.tag) == "footNote"
    )
    footnote.set("instId", str(inst_id))
    text_nodes = [
        element
        for element in footnote.iter()
        if _local_name(element.tag) == "t"
    ]
    text_nodes[0].text = f" {citation}"
    for text_node in text_nodes[1:]:
        text_node.text = ""
    for linesegarray in [
        element
        for element in footnote.iter()
        if _local_name(element.tag) == "linesegarray"
    ]:
        parent = linesegarray.getparent()
        if parent is not None:
            parent.remove(linesegarray)
    return control


def _new_body_paragraph_with_footnote(
    template: etree._Element,
    block_id: str,
    text: str,
    footnote_template: etree._Element,
    inst_id: int,
) -> etree._Element:
    paragraph = copy.deepcopy(template)
    first_run = next(
        child for child in paragraph if _local_name(child.tag) == "run"
    )
    char_reference = first_run.get("charPrIDRef", "19")
    before, citation, after = _split_added_footnote(block_id, text)
    for child in list(paragraph):
        paragraph.remove(child)

    for part in (before,):
        run = etree.SubElement(paragraph, f"{{{HP}}}run")
        run.set("charPrIDRef", char_reference)
        text_node = etree.SubElement(run, f"{{{HP}}}t")
        text_node.text = part

    footnote_run = etree.SubElement(paragraph, f"{{{HP}}}run")
    footnote_run.set("charPrIDRef", char_reference)
    footnote_run.append(
        _new_footnote_control(
            footnote_template,
            citation,
            inst_id,
        )
    )

    if after:
        run = etree.SubElement(paragraph, f"{{{HP}}}run")
        run.set("charPrIDRef", char_reference)
        text_node = etree.SubElement(run, f"{{{HP}}}t")
        text_node.text = after
    return paragraph


def _renumber_footnotes(root: etree._Element) -> None:
    footnotes = [
        element
        for element in root.iter()
        if _local_name(element.tag) == "footNote"
    ]
    for number, footnote in enumerate(footnotes, start=1):
        footnote.set("number", str(number))
        for auto_number in footnote.iter():
            if (
                _local_name(auto_number.tag) == "autoNum"
                and auto_number.get("numType") == "FOOTNOTE"
            ):
                auto_number.set("num", str(number))


def _insert_after(
    root: etree._Element,
    anchor: etree._Element,
    paragraph: etree._Element,
) -> None:
    root.insert(root.index(anchor) + 1, paragraph)


def build_revised_hwpx(
    source_path: Path,
    tracked_revision_path: Path,
    output_path: Path,
) -> None:
    """Apply Taegyu's tracked revisions while preserving unrelated HWPX content."""
    blocks = _parse_blocks(tracked_revision_path)
    with zipfile.ZipFile(source_path) as source_zip:
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(
            source_zip.read("Contents/section0.xml"),
            parser,
        )
        paragraphs = [
            child for child in root if _local_name(child.tag) == "p"
        ]

        heading_i = _find_unique(paragraphs, "본론 수정이 마무리 된 이후에 변경된 내용에 맞추어 수정할 예정.Ⅰ. 서론")
        heading_vi = _find_unique(paragraphs, "본론 수정이 마무리 된 이후에 변경된 내용에 맞추어 수정할 예정.VI. 결론")
        roadmap = _find_unique(paragraphs, "이에 본고는 우선 웹 크롤링의 기술적 구조")
        blank_after_roadmap = paragraphs[paragraphs.index(roadmap) + 1]
        blank_after_access_control = paragraphs[
            paragraphs.index(_find_unique(paragraphs, "이와 관련하여 robots.txt는")) + 1
        ]
        conclusion = _find_unique(paragraphs, REPLACEMENT_STARTS["178"])
        blank_after_conclusion = paragraphs[paragraphs.index(conclusion) + 1]

        _rewrite_paragraph(heading_i, blocks["H-I"])
        _rewrite_paragraph(heading_vi, blocks["H-VI"])

        target_paragraphs: dict[str, etree._Element] = {}
        for block_id, prefix in REPLACEMENT_STARTS.items():
            paragraph = _find_unique(paragraphs, prefix)
            target_paragraphs[block_id] = paragraph
            revised_text = _revised_direct_text(blocks[block_id], paragraph)
            if block_id == "49":
                controls = _footnote_controls(paragraph)
                _rewrite_paragraph(
                    paragraph,
                    revised_text,
                    footnote_controls=(copy.deepcopy(controls[-1]),),
                )
            else:
                _rewrite_paragraph(paragraph, revised_text)

        body_template = target_paragraphs["23"]
        add_i_1 = _new_body_paragraph(body_template, blocks["ADD-I-1"])
        _insert_after(root, target_paragraphs["23"], add_i_1)
        footnote_template = _footnote_controls(target_paragraphs["23"])[0]
        existing_inst_ids = [
            int(footnote.get("instId", "0"))
            for footnote in root.iter()
            if _local_name(footnote.tag) == "footNote"
        ]
        next_inst_id = max(existing_inst_ids, default=0) + 1
        add_i_2 = _new_body_paragraph_with_footnote(
            body_template,
            "ADD-I-2",
            blocks["ADD-I-2"],
            footnote_template,
            next_inst_id,
        )
        _insert_after(root, target_paragraphs["25"], add_i_2)
        _rewrite_paragraph(roadmap, blocks["ADD-I-3"])
        add_i_4 = _new_body_paragraph(body_template, blocks["ADD-I-4"])
        root.replace(blank_after_roadmap, add_i_4)
        _rewrite_paragraph(
            blank_after_access_control,
            blocks["ADD-II-1"],
        )
        add_ii_2 = _new_body_paragraph(
            target_paragraphs["49"],
            blocks["ADD-II-2"],
        )
        _insert_after(root, target_paragraphs["49"], add_ii_2)
        _rewrite_paragraph(
            blank_after_conclusion,
            blocks["ADD-VI-1"],
        )
        add_vi_2 = _new_body_paragraph(body_template, blocks["ADD-VI-2"])
        _insert_after(root, blank_after_conclusion, add_vi_2)
        add_vi_3 = _new_body_paragraph_with_footnote(
            body_template,
            "ADD-VI-3",
            blocks["ADD-VI-3"],
            footnote_template,
            next_inst_id + 1,
        )
        _insert_after(root, add_vi_2, add_vi_3)
        _renumber_footnotes(root)

        section_xml = etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
        preview = "\n\n".join(
            _direct_text(paragraph)
            for paragraph in root
            if _local_name(paragraph.tag) == "p" and _direct_text(paragraph)
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w") as output_zip:
            output_zip.writestr(
                "mimetype",
                source_zip.read("mimetype"),
                compress_type=zipfile.ZIP_STORED,
            )
            for item in source_zip.infolist():
                if item.filename == "mimetype":
                    continue
                if item.filename == "Contents/section0.xml":
                    output_zip.writestr(item, section_xml)
                    continue
                if item.filename == "Preview/PrvText.txt":
                    output_zip.writestr(item, preview.encode("utf-8"))
                    continue
                output_zip.writestr(item, source_zip.read(item.filename))


def main() -> int:
    """Build one revised HWPX from command-line paths."""
    if len(sys.argv) != 4:
        print(
            "Usage: python -m tools.apply_taegyu_revisions "
            "SOURCE.hwpx TRACKED.md OUTPUT.hwpx",
            file=sys.stderr,
        )
        return 2
    build_revised_hwpx(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]),
    )
    print(Path(sys.argv[3]).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
