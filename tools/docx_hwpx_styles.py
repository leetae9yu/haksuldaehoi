from __future__ import annotations

from dataclasses import dataclass

from docx.text.run import Run
from lxml import etree


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


@dataclass(frozen=True)
class CharStyle:
    style_id: str
    height: int
    bold: bool
    italic: bool
    underline: bool


class CharCatalog:
    def __init__(self, header: etree._Element) -> None:
        self.styles = tuple(
            CharStyle(
                style_id=node.get("id", ""),
                height=int(node.get("height", "1000")),
                bold=any(_local_name(child) == "bold" for child in node),
                italic=any(_local_name(child) == "italic" for child in node),
                underline=any(
                    _local_name(child) == "underline"
                    and child.get("type", "NONE") != "NONE"
                    for child in node
                ),
            )
            for node in header.iter()
            if _local_name(node) == "charPr"
        )

    def closest(self, base_id: str, run: Run) -> str:
        base = next(
            (style for style in self.styles if style.style_id == base_id),
            self.styles[0],
        )
        wanted = (
            base.bold if run.bold is None else run.bold,
            base.italic if run.italic is None else run.italic,
            base.underline if run.underline is None else bool(run.underline),
        )
        return min(
            self.styles,
            key=lambda style: (
                sum(
                    left != right
                    for left, right in zip(
                        (style.bold, style.italic, style.underline),
                        wanted,
                        strict=True,
                    )
                ),
                abs(style.height - base.height),
                style.style_id != base.style_id,
            ),
        ).style_id
