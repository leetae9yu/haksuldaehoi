from __future__ import annotations

import copy
import hashlib
import zipfile
from pathlib import Path

from lxml import etree


SOURCE = Path("/tmp/ai-law-original-fresh.hwpx")
OUTPUT = Path("/home/opc/oracle-shared/생성형AI_무단크롤링_II장_append-only.hwpx")
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

ACCESS_CONTROL = (
    "이와 관련하여 robots.txt는 크롤러가 준수할 접근 경로를 제시하는 프로토콜상의 "
    "지침이지만, 접근 권한을 부여하는 인증 수단은 아니며 유효한 보안 조치를 대체하지도 "
    "않는다. 따라서 robots.txt에 표시된 접근 제한과 로그인 인증, IP 주소 "
    "차단, 요청 빈도 제한 및 CAPTCHA 등 실제 접근을 차단하거나 제한하는 기술적 조치는 "
    "구별할 필요가 있다. 전자는 자동화된 클라이언트에 대한 접근 지침을 제시하는 반면, "
    "후자는 서버 차원에서 접근 가능 여부나 요청량을 통제한다. 이러한 기술적 차이는 "
    "크롤러가 운영자의 의사표시를 따르지 않은 경우와 실제 접근통제를 우회한 경우를 "
    "구분하여 평가하기 위한 사실적 전제가 된다."
)

TRAINING_PIPELINE = (
    "이러한 과정을 구체적으로 살펴보면, 웹 크롤링을 통한 데이터 수집과 생성형 AI의 "
    "모델 학습은 하나의 행위가 아니라 서로 구별되는 기술적 단계로 이루어진다. 먼저 "
    "크롤러가 웹페이지를 수집하면 본문과 "
    "메타데이터를 추출하고 문서 형식을 정규화하며, 목적에 따라 중복 제거와 품질 "
    "필터링을 수행하여 학습용 데이터셋을 구성한다. 텍스트 데이터는 이후 모델이 처리할 "
    "수 있도록 토큰(token) 단위로 변환되고 수치화된다. 모델 학습 단계에서는 이러한 "
    "입력에 대한 예측 오차를 계산하고 그 결과에 따라 다수의 매개변수를 반복적으로 "
    "갱신한다. 따라서 크롤링, 데이터셋 구축, 토큰화 및 모델 학습은 각각 구별하여 "
    "이해하여야 하며, 구체적인 전처리 방식과 수집 자료의 실제 학습 포함 여부는 모델과 "
    "개발 주체에 따라 달라질 수 있다."
)

SEARCH_TRAINING_CAVEAT = (
    "앞서 살펴본 기술적 차이는 두 크롤링의 수집 이후 처리 목적에서도 구체화된다. 다만 "
    "학습 목적 크롤링이 원본 사이트의 방문 감소를 항상 초래한다고 단정할 수는 없으며, "
    "실제 영향은 AI 서비스의 구현 방식, 출력 형태 및 이용자 행태에 따라 달라질 수 있다. "
    "또한 목적별 크롤러가 구분되어 있더라도 개발사의 운영 방식에 "
    "따라 하나의 수집 결과가 복수의 용도로 활용될 가능성이 있으므로, 크롤러의 명칭뿐 "
    "아니라 수집 이후의 실제 이용 과정도 함께 살펴볼 필요가 있다."
)


def direct_text(paragraph: etree._Element) -> str:
    return "".join(
        paragraph.xpath(
            './*[local-name()="run"]/*[local-name()="t"]/text()'
        )
    ).strip()


def canonical_hash(element: etree._Element) -> str:
    serialized = etree.tostring(element, method="c14n", with_comments=True)
    return hashlib.sha256(serialized).hexdigest()


def note_texts(element: etree._Element) -> list[str]:
    return [
        "".join(
            footnote.xpath(
                './/*[local-name()="subList"]//*[local-name()="t"]/text()'
            )
        ).strip()
        for footnote in element.xpath('.//*[local-name()="footNote"]')
    ]


def added_paragraph(template: etree._Element, text: str) -> etree._Element:
    paragraph = copy.deepcopy(template)
    for child in list(paragraph):
        paragraph.remove(child)
    run = etree.SubElement(paragraph, f"{{{HP}}}run")
    run.set("charPrIDRef", "19")
    text_node = etree.SubElement(run, f"{{{HP}}}t")
    text_node.text = text
    return paragraph


def footnote_template(paragraph: etree._Element) -> etree._Element:
    controls = paragraph.xpath(
        './/*[local-name()="ctrl"][.//*[local-name()="footNote"]]'
    )
    if len(controls) != 1:
        raise ValueError("Expected exactly one footnote control in source paragraph")
    return controls[0]


def append_footnote(
    paragraph: etree._Element,
    template: etree._Element,
    number: int,
    note_text: str,
) -> None:
    control = copy.deepcopy(template)
    footnote = control.xpath('.//*[local-name()="footNote"]')[0]
    footnote.set("number", str(number))
    footnote.set("instId", str(1_700_000_000 + number))
    for autonumber in control.xpath('.//*[local-name()="autoNum"]'):
        autonumber.set("num", str(number))
    note_nodes = control.xpath(
        './/*[local-name()="footNote"]'
        '//*[local-name()="subList"]'
        '//*[local-name()="p"]'
        '//*[local-name()="t"]'
    )
    if not note_nodes:
        raise ValueError("Footnote template contains no note text")
    note_nodes[0].text = f" {note_text}"
    for node in note_nodes[1:]:
        node.text = ""
    for linesegarray in control.xpath('.//*[local-name()="linesegarray"]'):
        linesegarray.getparent().remove(linesegarray)
    run = etree.SubElement(paragraph, f"{{{HP}}}run")
    run.set("charPrIDRef", "19")
    run.append(control)


def main() -> None:
    with zipfile.ZipFile(SOURCE) as source_zip:
        parser = etree.XMLParser(remove_blank_text=False)
        source_root = etree.fromstring(
            source_zip.read("Contents/section0.xml"),
            parser,
        )
        all_paragraphs = list(source_root)
        start = next(
            index
            for index, paragraph in enumerate(all_paragraphs)
            if direct_text(paragraph).startswith("Ⅱ. 웹 크롤링")
        )
        end = next(
            index
            for index, paragraph in enumerate(all_paragraphs[start + 1 :], start + 1)
            if direct_text(paragraph).startswith("III. 생성형")
        )
        originals = all_paragraphs[start:end]
        original_direct_texts = [direct_text(paragraph) for paragraph in originals]
        original_note_texts = [
            note
            for paragraph in originals
            for note in note_texts(paragraph)
        ]
        body_template = originals[2]
        note_templates = {
            3: footnote_template(originals[2]),
            4: footnote_template(originals[6]),
            8: footnote_template(originals[17]),
        }
        notes = {
            9: (
                "IETF, “RFC 9309: Robots Exclusion Protocol”, "
                "https://datatracker.ietf.org/doc/html/rfc9309 "
                "(검색일: 2026. 7. 18.)."
            ),
            10: (
                "이성용·김상중, “생성형 AI 학습 데이터 무단 이용의 위법성 판단과 "
                "민법 제750조의 보충적 적용”, 『재산법연구』 제43권 제1호, "
                "한국재산법학회, 2026, 136-138면; 김성원·최상민·이수원, "
                "“텍스트·데이터 마이닝 과정의 저작물 이용 면책 규정 신설안에 대한 소고 "
                "— 적대적 생성신경망에의 적용”, 『지식재산연구』 제18권 제1호, "
                "한국지식재산연구원, 2023, 151면."
            ),
            11: (
                "OpenAI, “Overview of OpenAI Crawlers”, OpenAI Developers, "
                "https://developers.openai.com/api/docs/bots "
                "(검색일: 2026. 7. 18.)."
            ),
        }

        output_root = etree.Element(
            source_root.tag,
            nsmap=source_root.nsmap,
            attrib=source_root.attrib,
        )
        output_root.append(copy.deepcopy(all_paragraphs[0]))

        for index, paragraph in enumerate(originals):
            output_root.append(copy.deepcopy(paragraph))
            if index == 2:
                addition = added_paragraph(body_template, ACCESS_CONTROL)
                append_footnote(addition, note_templates[3], 9, notes[9])
                output_root.append(addition)
            elif index == 6:
                addition = added_paragraph(body_template, TRAINING_PIPELINE)
                append_footnote(addition, note_templates[4], 10, notes[10])
                output_root.append(addition)
            elif index == 17:
                addition = added_paragraph(body_template, SEARCH_TRAINING_CAVEAT)
                append_footnote(addition, note_templates[8], 11, notes[11])
                output_root.append(addition)

        for number, footnote in enumerate(
            output_root.xpath('//*[local-name()="footNote"]'),
            start=3,
        ):
            footnote.set("number", str(number))
            for autonumber in footnote.xpath('.//*[local-name()="autoNum"]'):
                autonumber.set("num", str(number))

        section_xml = etree.tostring(
            output_root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
        preview = "\n\n".join(
            direct_text(paragraph)
            for paragraph in output_root
            if direct_text(paragraph)
        )

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

    with zipfile.ZipFile(OUTPUT) as output_zip:
        if bad_file := output_zip.testzip():
            raise ValueError(f"Corrupt archive member: {bad_file}")
        parsed = etree.fromstring(output_zip.read("Contents/section0.xml"))
        output_paragraphs = list(parsed)[1:]
        added_texts = {ACCESS_CONTROL, TRAINING_PIPELINE, SEARCH_TRAINING_CAVEAT}
        retained = [
            paragraph
            for paragraph in output_paragraphs
            if direct_text(paragraph) not in added_texts
        ]
        additions = [
            direct_text(paragraph)
            for paragraph in output_paragraphs
            if direct_text(paragraph) in added_texts
        ]
        retained_direct_texts = [direct_text(paragraph) for paragraph in retained]
        retained_note_texts = [
            note
            for paragraph in retained
            for note in note_texts(paragraph)
        ]

        if retained_direct_texts != original_direct_texts:
            raise ValueError("At least one original Section II sentence was modified")
        if retained_note_texts != original_note_texts:
            raise ValueError("At least one original Section II footnote text was modified")
        if additions != [
            ACCESS_CONTROL,
            TRAINING_PIPELINE,
            SEARCH_TRAINING_CAVEAT,
        ]:
            raise ValueError("Unexpected append-only paragraph set or order")
        if len(parsed.xpath('//*[local-name()="footNote"]')) != 9:
            raise ValueError("Expected six original and three new footnotes")
        note_numbers = [
            int(footnote.get("number"))
            for footnote in parsed.xpath('//*[local-name()="footNote"]')
        ]
        if note_numbers != list(range(3, 12)):
            raise ValueError(f"Unexpected footnote numbering: {note_numbers}")
        if len(output_paragraphs) != len(originals) + 3:
            raise ValueError("Output contains an unexpected paragraph count")

    original_chars = sum(len(direct_text(paragraph)) for paragraph in originals)
    added_chars = sum(map(len, additions))
    print(OUTPUT)
    print(f"original_paragraphs={len(originals)} unchanged")
    print(f"added_paragraphs={len(additions)}")
    print(f"original_chars={original_chars}")
    print(f"added_chars={added_chars}")
    print(f"growth={added_chars / original_chars * 100:.1f}%")
    print("footnotes=6 original + 3 new")


if __name__ == "__main__":
    main()
