# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "lxml>=5.3",
# ]
# ///
#
# Usage:
# uv run -m tools.build_taegyu_compare ORIGINAL.hwpx EDITED.hwpx compare

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

from tools.split_taegyu_sections import split_taegyu_sections

COMPARISON_FILENAMES: Final = {
    "intro_original": "I. 서론_원본.hwpx",
    "intro_edit": "I. 서론_edit.hwpx",
    "chapter_ii_original": "II. 본론_원본.hwpx",
    "chapter_ii_edit": "II. 본론_edit.hwpx",
    "conclusion_original": "VI. 결론_원본.hwpx",
    "conclusion_edit": "VI. 결론_edit.hwpx",
}


def _version_filenames(version: str) -> dict[str, str]:
    return {
        section: COMPARISON_FILENAMES[f"{section}_{version}"]
        for section in ("intro", "chapter_ii", "conclusion")
    }


def build_taegyu_compare(
    original_path: Path,
    edited_path: Path,
    output_directory: Path,
) -> dict[str, Path]:
    """Create named original/edit HWPX pairs for Taegyu's sections."""
    original_outputs = split_taegyu_sections(
        original_path,
        output_directory,
        filename_overrides=_version_filenames("original"),
    )
    edited_outputs = split_taegyu_sections(
        edited_path,
        output_directory,
        filename_overrides=_version_filenames("edit"),
    )
    return {
        **{
            f"{key}_original": path
            for key, path in original_outputs.items()
        },
        **{
            f"{key}_edit": path
            for key, path in edited_outputs.items()
        },
    }


def main() -> int:
    """Build six paired comparison HWPX files."""
    if len(sys.argv) != 4:
        print(
            "Usage: python -m tools.build_taegyu_compare "
            "ORIGINAL.hwpx EDITED.hwpx OUTPUT_DIRECTORY",
            file=sys.stderr,
        )
        return 2
    outputs = build_taegyu_compare(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]),
    )
    for output in outputs.values():
        print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
