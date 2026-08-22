from __future__ import annotations

import copy
import io
import urllib.request
import zipfile
from pathlib import Path

from lxml import etree


OUTPUT = Path("/home/opc/oracle-shared/생성형AI_무단크롤링_II장_최소수정본.hwpx")
DOWNLOAD_URL = (
    "https://drive.usercontent.google.com/download"
    "?id=1fB_YZ4AhSdwQJtd9fJec5u3z1tvPeSZR&export=download&confirm=t"
)


def direct_text(paragraph: etree._Element) -> str:
    return "".join(
        paragraph.xpath(
            './*[local-name()="run"]/*[local-name()="t"]/text()'
        )
    ).strip()


def first_direct_text_node(paragraph: etree._Element) -> etree._Element:
    nodes = paragraph.xpath(
        './*[local-name()="run"]/*[local-name()="t"]'
    )
    if not nodes:
        raise ValueError("Paragraph has no direct text node")
    return nodes[0]


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Expected one occurrence of {old!r}, found {text.count(old)}")
    return text.replace(old, new, 1)


def replace_suffix(text: str, marker: str, replacement: str) -> str:
    if text.count(marker) != 1:
        raise ValueError(
            f"Expected one suffix marker {marker!r}, found {text.count(marker)}"
        )
    return text[: text.index(marker)] + replacement


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


def build_section(original: bytes) -> tuple[bytes, str, int, int]:
    source_zip = zipfile.ZipFile(io.BytesIO(original))
    parser = etree.XMLParser(remove_blank_text=False)
    original_root = etree.fromstring(
        source_zip.read("Contents/section0.xml"),
        parser,
    )
    direct_paragraphs = list(original_root)

    start = next(
        index
        for index, paragraph in enumerate(direct_paragraphs)
        if direct_text(paragraph).startswith("Ⅱ. 웹 크롤링")
    )
    end = next(
        index
        for index, paragraph in enumerate(direct_paragraphs[start + 1 :], start + 1)
        if direct_text(paragraph).startswith("III. 생성형")
    )

    section_paragraphs = [
        copy.deepcopy(paragraph)
        for paragraph in direct_paragraphs[start:end]
    ]
    original_body = "\n".join(
        direct_text(paragraph)
        for paragraph in section_paragraphs
        if direct_text(paragraph)
    )

    mechanism = next(
        paragraph
        for paragraph in section_paragraphs
        if direct_text(paragraph).startswith("웹 크롤링은 자동화된")
    )
    mechanism_node = first_direct_text_node(mechanism)
    mechanism_text = mechanism_node.text or ""
    mechanism_text = replace_once(
        mechanism_text,
        "최근에는 단순한 텍스트 수집을 넘어, 스크립트 실행 결과를 렌더링하여 "
        "화면에 최종적으로 표시되는 내용까지 수집 범위에 포함하는 경향을 보인다.",
        "최근에는 일부 크롤러가 스크립트를 실행하여 동적으로 생성된 내용까지 "
        "수집 범위에 포함하기도 한다.",
    )
    mechanism_text = replace_suffix(
        mechanism_text,
        "후속 방문 대기열 추가 과정에서는",
        "후속 방문 대기열 추가 과정에서는 해당 사이트의 중요도, 서버 부하, "
        "robots.txt 규칙 등을 고려할 수 있다. 다만 robots.txt는 크롤러의 접근 "
        "범위에 관한 프로토콜상 지침으로서 접근 권한을 부여하거나 보안 조치를 "
        "대체하지 않는다. 따라서 인증, IP 차단, 요청 빈도 제한 및 CAPTCHA와 "
        "같은 실제 접근통제 수단과 구별할 필요가 있다.",
    )
    mechanism_node.text = mechanism_text

    training = next(
        paragraph
        for paragraph in section_paragraphs
        if direct_text(paragraph).startswith("생성형 인공지능(이하 ‘AI’) 모델은")
    )
    training_node = first_direct_text_node(training)
    training_text = training_node.text or ""
    training_text = replace_once(
        training_text,
        "생성형 인공지능(이하 ‘AI’) 모델은 웹 크롤링으로 수집한 웹페이지를 "
        "원형 그대로 학습에 이용하지 않으며, 정제, 중복 제거, 저품질 콘텐츠 "
        "필터링 등의 전처리 과정을 거쳐 학습용 데이터셋으로 구축한다.",
        "생성형 인공지능(이하 ‘AI’) 모델의 개발 과정에서는 웹 크롤링으로 "
        "수집한 자료를 정제, 중복 제거, 저품질 콘텐츠 필터링 등의 전처리 "
        "과정을 거쳐 학습용 데이터셋으로 구축할 수 있다.",
    )
    training_text = replace_once(
        training_text,
        "텍스트 모델은 문장을 분할하여 언어의 통계적 규칙성을 학습하고,",
        "텍스트 모델은 텍스트를 토큰 단위로 변환하여 언어의 통계적 규칙성을 "
        "학습하고,",
    )
    training_text = replace_suffix(
        training_text,
        "원문 데이터가 최종적으로",
        "원문 데이터는 수치화된 입력으로 변환되어 모델의 매개변수 갱신에 "
        "활용된다. 다만 크롤링, 데이터셋 구축, 토큰화 및 모델 학습은 서로 "
        "구별되는 단계이고, 구체적인 전처리 방식과 실제 학습 포함 여부는 "
        "개발 주체와 모델에 따라 달라질 수 있다.",
    )
    training_node.text = training_text

    comparison = next(
        paragraph
        for paragraph in section_paragraphs
        if direct_text(paragraph).startswith("기존 검색엔진 크롤링은")
    )
    comparison_node = first_direct_text_node(comparison)
    comparison_text = comparison_node.text or ""
    comparison_text = replace_once(
        comparison_text,
        "반면 생성형 AI 학습용 크롤링은 자체적인 결과물 생성을 위해 원본을 "
        "학습 데이터로 소비하여 직접 방문을 감소시킨다.",
        "반면 생성형 AI 학습용 크롤링은 자체적인 결과물 생성을 위한 학습 "
        "데이터의 확보를 목적으로 하므로 원본 사이트 방문과 직접 연결되지 "
        "않을 수 있다.",
    )
    comparison_text = replace_suffix(
        comparison_text,
        "OpenAI 등 업계에서는",
        "다만 이러한 차이가 실제 트래픽 감소로 이어지는지는 서비스 구현과 "
        "이용자 행태에 따라 달라질 수 있다. OpenAI 등 업계에서는 검색용 "
        "크롤러와 학습용 크롤러를 구분하고 있으며, 웹사이트 운영자는 "
        "robots.txt를 통하여 목적별 크롤러의 접근 허용 여부를 달리 지정할 "
        "수 있다.",
    )
    comparison_node.text = comparison_text

    new_root = etree.Element(
        original_root.tag,
        nsmap=original_root.nsmap,
        attrib=original_root.attrib,
    )
    new_root.append(copy.deepcopy(direct_paragraphs[0]))
    for paragraph in section_paragraphs:
        if direct_text(paragraph).startswith("Ⅱ. 웹 크롤링"):
            paragraph.set("pageBreak", "0")
        new_root.append(paragraph)

    revised_body = "\n".join(
        direct_text(paragraph)
        for paragraph in section_paragraphs
        if direct_text(paragraph)
    )
    xml = etree.tostring(
        new_root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    return xml, revised_body, len(original_body), len(revised_body)


def main() -> None:
    original = download_original()
    source_zip = zipfile.ZipFile(io.BytesIO(original))
    section_xml, preview, old_length, new_length = build_section(original)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w") as output_zip:
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
            elif item.filename == "Preview/PrvText.txt":
                output_zip.writestr(item, preview.encode("utf-8"))
            else:
                output_zip.writestr(item, source_zip.read(item.filename))

    with zipfile.ZipFile(OUTPUT) as check_zip:
        if bad_file := check_zip.testzip():
            raise ValueError(f"Corrupt member: {bad_file}")
        parsed = etree.fromstring(check_zip.read("Contents/section0.xml"))
        direct_paragraphs = parsed.xpath(
            '/*[local-name()="sec"]/*[local-name()="p"]'
        )
        visible_text = "\n".join(
            direct_text(paragraph)
            for paragraph in direct_paragraphs
            if direct_text(paragraph)
        )
        if "Ⅰ. 서론" in visible_text or "III. 생성형" in visible_text:
            raise ValueError("Non-II chapter content remains")
        if len(parsed.xpath('//*[local-name()="footNote"]')) != 6:
            raise ValueError("Original six II-chapter footnotes were not preserved")
        required = (
            "실제 접근통제 수단과 구별할 필요가 있다.",
            "크롤링, 데이터셋 구축, 토큰화 및 모델 학습은 서로 구별되는 단계",
            "실제 트래픽 감소로 이어지는지는",
        )
        if not all(text in visible_text for text in required):
            raise ValueError("A required minimal clarification is missing")

    growth = (new_length / old_length - 1) * 100
    print(OUTPUT)
    print(f"old_chars={old_length}")
    print(f"new_chars={new_length}")
    print(f"growth={growth:.1f}%")
    print("footnotes=6")


if __name__ == "__main__":
    main()
