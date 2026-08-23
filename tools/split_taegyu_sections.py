# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "lxml>=5.3",
# ]
# ///
#
# Usage:
# uv run -m tools.split_taegyu_sections SOURCE.hwpx OUTPUT_DIRECTORY

from __future__ import annotations

import copy
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lxml import etree

from tools.hwpx_xml import direct_text as _direct_text
from tools.hwpx_xml import local_name as _local_name
from tools.hwpx_xml import renumber_footnotes as _renumber_footnotes


@dataclass(frozen=True)
class SectionSpec:
    key: str
    filename: str
    start_prefix: str
    end_prefix: str


SECTIONS: Final = (
    SectionSpec(
        key="intro",
        filename="서론.hwpx",
        start_prefix="I. 서론",
        end_prefix="Ⅱ. 웹 크롤링",
    ),
    SectionSpec(
        key="chapter_ii",
        filename="본론_II.hwpx",
        start_prefix="Ⅱ. 웹 크롤링",
        end_prefix="III. 생성형",
    ),
    SectionSpec(
        key="conclusion",
        filename="결론.hwpx",
        start_prefix="VI. 결론",
        end_prefix="각주 및 참고문헌은",
    ),
)
BOUNDARY_ALIASES: Final = {
    "I. 서론": ("I. 서론", "Ⅰ. 서론"),
    "VI. 결론": ("VI. 결론", "Ⅵ. 결론"),
}


class SectionSplitError(ValueError):
    """Raised when a standalone section cannot be selected safely."""


def _unique_index(texts: list[str], prefix: str) -> int:
    markers = BOUNDARY_ALIASES.get(prefix, (prefix,))
    matches = [
        index
        for index, text in enumerate(texts)
        if not text.startswith("▶목 차◀")
        and any(
            text.startswith(marker) or text.endswith(marker)
            for marker in markers
        )
    ]
    if len(matches) != 1:
        raise SectionSplitError(
            f"Expected one paragraph starting with {prefix!r}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _build_section_xml(
    source_root: etree._Element,
    paragraphs: list[etree._Element],
    start: int,
    end: int,
) -> tuple[bytes, str]:
    if start <= 0 or end <= start:
        raise SectionSplitError(
            f"Invalid paragraph range: start={start}, end={end}"
        )
    new_root = copy.deepcopy(source_root)
    for child in list(new_root):
        new_root.remove(child)
    new_root.append(copy.deepcopy(paragraphs[0]))
    selected = [
        copy.deepcopy(paragraph)
        for paragraph in paragraphs[start:end]
    ]
    selected[0].set("pageBreak", "0")
    for paragraph in selected:
        new_root.append(paragraph)
    _renumber_footnotes(new_root)
    preview = "\n\n".join(
        text
        for paragraph in selected
        if (text := _direct_text(paragraph))
    )
    section_xml = etree.tostring(
        new_root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    return section_xml, preview


def _write_section_archive(
    source_zip: zipfile.ZipFile,
    output_path: Path,
    section_xml: bytes,
    preview: str,
) -> None:
    with zipfile.ZipFile(output_path, "w") as output_zip:
        output_zip.writestr(
            "mimetype",
            source_zip.read("mimetype"),
            compress_type=zipfile.ZIP_STORED,
        )
        for item in source_zip.infolist():
            if item.filename == "mimetype":
                continue
            output_item = copy.copy(item)
            if item.filename == "Contents/section0.xml":
                output_zip.writestr(output_item, section_xml)
                continue
            if item.filename == "Preview/PrvText.txt":
                output_zip.writestr(
                    output_item,
                    preview.encode("utf-8"),
                )
                continue
            output_zip.writestr(
                output_item,
                source_zip.read(item.filename),
            )


def split_taegyu_sections(
    source_path: Path,
    output_directory: Path,
    *,
    filename_overrides: Mapping[str, str] | None = None,
) -> dict[str, Path]:
    """Create standalone HWPX files for Taegyu's three owned sections."""
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    parser = etree.XMLParser(remove_blank_text=False)
    with zipfile.ZipFile(source_path) as source_zip:
        source_root = etree.fromstring(
            source_zip.read("Contents/section0.xml"),
            parser,
        )
        paragraphs = [
            child
            for child in source_root
            if _local_name(child.tag) == "p"
        ]
        texts = [_direct_text(paragraph) for paragraph in paragraphs]
        for spec in SECTIONS:
            start = _unique_index(texts, spec.start_prefix)
            end = _unique_index(texts, spec.end_prefix)
            section_xml, preview = _build_section_xml(
                source_root,
                paragraphs,
                start,
                end,
            )
            filename = (
                spec.filename
                if filename_overrides is None
                else filename_overrides.get(
                    spec.key,
                    spec.filename,
                )
            )
            output_path = output_directory / filename
            _write_section_archive(
                source_zip,
                output_path,
                section_xml,
                preview,
            )
            outputs[spec.key] = output_path
    return outputs


def main() -> int:
    """Split one revised HWPX into three standalone section files."""
    if len(sys.argv) != 3:
        print(
            "Usage: python -m tools.split_taegyu_sections "
            "SOURCE.hwpx OUTPUT_DIRECTORY",
            file=sys.stderr,
        )
        return 2
    outputs = split_taegyu_sections(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
    )
    for output in outputs.values():
        print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
