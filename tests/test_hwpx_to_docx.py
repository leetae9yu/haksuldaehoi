from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from tools.hwpx_to_docx import convert_hwpx
from tools.validate_hwpx_docx import validate_documents

HEADER_XML = """\
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"
 xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"
 xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">
  <hh:fontfaces>
    <hh:fontface lang="HANGUL"><hh:font id="0" face="함초롬바탕"/></hh:fontface>
  </hh:fontfaces>
  <hh:charProperties>
    <hh:charPr id="0" height="1000" textColor="#000000">
      <hh:fontRef hangul="0" latin="0"/><hh:spacing hangul="0" latin="0"/>
    </hh:charPr>
    <hh:charPr id="1" height="1200" textColor="#123456">
      <hh:fontRef hangul="0" latin="0"/><hh:spacing hangul="0" latin="0"/>
      <hh:bold/>
    </hh:charPr>
  </hh:charProperties>
  <hh:paraProperties>
    <hh:paraPr id="0">
      <hh:align horizontal="CENTER"/>
      <hh:margin>
        <hc:left value="0"/><hc:right value="0"/>
        <hc:prev value="0"/><hc:next value="0"/>
      </hh:margin>
      <hh:lineSpacing type="PERCENT" value="160"/>
    </hh:paraPr>
  </hh:paraProperties>
</hh:head>
"""

SECTION_XML = """\
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
 xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0">
    <hp:run charPrIDRef="1"><hp:t>논문 제목</hp:t></hp:run>
    <hp:run charPrIDRef="0">
      <hp:ctrl>
        <hp:footNote number="1">
          <hp:subList>
            <hp:p paraPrIDRef="0">
              <hp:run charPrIDRef="0"><hp:t>각주 내용</hp:t></hp:run>
            </hp:p>
          </hp:subList>
        </hp:footNote>
      </hp:ctrl>
    </hp:run>
  </hp:p>
  <hp:p paraPrIDRef="0">
    <hp:run charPrIDRef="0"><hp:t>본문 문장</hp:t></hp:run>
  </hp:p>
  <hp:p paraPrIDRef="0">
    <hp:run charPrIDRef="0">
      <hp:tbl rowCnt="1" colCnt="1">
        <hp:tr><hp:tc>
          <hp:subList>
            <hp:p paraPrIDRef="0">
              <hp:run charPrIDRef="0"><hp:t>표 내용</hp:t></hp:run>
            </hp:p>
          </hp:subList>
          <hp:cellAddr colAddr="0" rowAddr="0"/>
          <hp:cellSpan colSpan="1" rowSpan="1"/>
          <hp:cellSz width="7200" height="720"/>
        </hp:tc></hp:tr>
      </hp:tbl>
    </hp:run>
  </hp:p>
  <hp:secPr>
    <hp:pagePr width="59528" height="84186">
      <hp:margin left="7937" right="7937" top="5669" bottom="4252"
       header="3118" footer="3118" gutter="0"/>
    </hp:pagePr>
  </hp:secPr>
</hs:sec>
"""


def _write_fixture(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", HEADER_XML)
        archive.writestr("Contents/section0.xml", SECTION_XML)


def test_convert_preserves_text_style_table_and_footnote(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.docx"
    _write_fixture(source)

    convert_hwpx(source, target)

    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        document = etree.fromstring(archive.read("word/document.xml"))
        footnotes = etree.fromstring(archive.read("word/footnotes.xml"))
        settings = etree.fromstring(archive.read("word/settings.xml"))
        styles = etree.fromstring(archive.read("word/styles.xml"))
        document_text = "".join(str(text) for text in document.itertext())
        footnote_text = "".join(str(text) for text in footnotes.itertext())
        document_xml = etree.tostring(document, encoding="unicode")
        footnotes_xml = etree.tostring(footnotes, encoding="unicode")
        settings_xml = etree.tostring(settings, encoding="unicode")
        styles_xml = etree.tostring(styles, encoding="unicode")

    assert "논문 제목" in document_text
    assert "본문 문장" in document_text
    assert "표 내용" in document_text
    assert "각주 내용" in footnote_text
    assert "<w:b/>" in document_xml
    assert 'w:val="123456"' in document_xml
    assert '<w:rStyle w:val="FootnoteAnchor"/>' in document_xml
    assert '<w:footnoteReference w:id="2"/>' in document_xml
    assert "<w:footnoteReference" in document_xml
    assert "<w:footnoteReference" not in document_xml.replace(
        '<w:footnoteReference w:id="2"/>', ""
    )
    assert "<w:t>)</w:t>" not in document_xml
    assert '<w:footnote w:id="0" w:type="separator">' in footnotes_xml
    assert '<w:footnote w:id="1" w:type="continuationSeparator">' in footnotes_xml
    assert '<w:footnote w:id="2">' in footnotes_xml
    assert '<w:pStyle w:val="Footnote"/>' in footnotes_xml
    assert '<w:rStyle w:val="FootnoteCharacters"/>' in footnotes_xml
    assert "<w:footnoteRef/>" in footnotes_xml
    assert "<w:t>)" not in footnotes_xml
    assert '<w:footnote w:id="0"/>' in settings_xml
    assert '<w:footnote w:id="1"/>' in settings_xml
    assert 'w:styleId="FootnoteCharacters"' in styles_xml
    assert 'w:styleId="FootnoteAnchor"' in styles_xml
    assert 'w:styleId="Footnote"' in styles_xml
    assert validate_documents(source, target)["valid"] is True
