import io
import re

import numpy as np
import pytest

import lineova as lv


def test_fonts_are_embedded_by_default():
    pdf = lv.bar({"a": 1, "b": 2}, title="Title").to_pdf()
    txt = pdf.decode("latin-1")
    assert "/FontFile2" in txt and "/Subtype /CIDFontType2" in txt and "/Encoding /Identity-H" in txt and "/ToUnicode" in txt
    assert "/BaseFont /Helvetica" not in txt
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")


def test_standard_fonts_option_keeps_old_behaviour():
    pdf = lv.bar({"a": 1}, title="Title").to_pdf(embed_fonts=False)
    txt = pdf.decode("latin-1")
    assert "/BaseFont /Helvetica" in txt and "/FontFile2" not in txt
    assert len(pdf) < len(lv.bar({"a": 1}, title="Title").to_pdf())


def test_only_used_styles_are_embedded():
    plain = lv.line([1, 2, 3], theme="ledger").to_pdf().decode("latin-1")
    assert plain.count("/FontFile2") <= 2             # regular (and bold for the end label)
    serif = lv.bar({"a": 1}, theme="folio", title="t").to_pdf().decode("latin-1")
    assert "LineovaSerif" in serif and "LineovaSans" not in serif


def test_xref_offsets_are_correct():
    pdf = lv.line([1, 2, 3], title="Hi").to_pdf()
    start = int(re.search(rb"startxref\s+(\d+)", pdf).group(1))
    assert pdf[start:start + 4] == b"xref"
    n = int(re.search(rb"xref\s+0 (\d+)", pdf[start:]).group(1))
    entries = re.findall(rb"(\d{10}) 00000 n ", pdf[start:])
    assert len(entries) == n - 1
    for i, off in enumerate(entries, start=1):
        assert pdf[int(off):int(off) + len(f"{i} 0 obj")] == f"{i} 0 obj".encode()


def test_unicode_survives_text_extraction():
    pypdf = pytest.importorskip("pypdf")
    c = lv.line(x=np.arange(10.0), y=np.arange(10.0) - 5, title="A → B ± 5 ≤ 10 é", subtitle="−3 °C")
    text = pypdf.PdfReader(io.BytesIO(c.to_pdf())).pages[0].extract_text()
    for piece in ("A → B ± 5 ≤ 10 é", "−3 °C", "−4"):
        assert piece in text
    flat = pypdf.PdfReader(io.BytesIO(c.to_pdf(embed_fonts=False))).pages[0].extract_text()
    assert "A -> B" in flat and "<= 10" in flat       # the standard fonts have no arrow: ASCII stand-ins


def test_unknown_characters_fall_back_to_question_mark():
    pypdf = pytest.importorskip("pypdf")
    c = lv.bar({"日本": 3, "b": 2})
    assert "?" in pypdf.PdfReader(io.BytesIO(c.to_pdf())).pages[0].extract_text()


def test_widths_agree_with_layout():
    """Embedded Liberation Sans has Helvetica's widths, so anchors computed from the real font match the layout."""
    from lineova import _text
    from lineova.backends import _ttf
    f = _ttf.load("sans", False, False)
    s = "Revenue by region 2025"
    em = sum(f.advance(f.glyph_index(ch)) for ch in s)
    assert em * 10 == pytest.approx(_text.text_width(s, 10, "sans") / _text.KIND_FACTOR["sans"], rel=0.005)


def test_rotated_halo_rich_text_and_every_chart_type():
    pytest.importorskip("pandas")
    rng = np.random.default_rng(0)
    charts = [lv.radar({"s": {"p": 1, "q": 2, "r": 3}}), lv.sankey([("a", "b", 3), ("a", "c", 1)]),
              lv.treemap({"x": {"a": 3, "b": 1}, "y": {"c": 2}}), lv.stat(42, label="x", previous=40),
              lv.bar({"alpha": 3, "beta": 5, "gamma": 4}, theme="folio"), lv.chord([[0, 2], [1, 0]], names=["a", "b"]),
              lv.scatter(x=rng.normal(size=100), y=rng.normal(size=100), theme="instrument"),
              lv.line([1, 2, 3], theme="ledger-dark"), lv.bullet({"a": (3, 4, [2, 4, 6])})]
    for c in charts:
        pdf = c.to_pdf()
        assert pdf.startswith(b"%PDF") and b"/FontFile2" in pdf


def test_pymupdf_opens_the_file():
    fitz = pytest.importorskip("pymupdf")
    c = lv.line(x=np.arange(20.0), y=np.arange(20.0) ** 0.5, title="Title −1", theme="folio")
    doc = fitz.open(stream=c.to_pdf(), filetype="pdf")
    assert doc.page_count == 1 and "Title" in doc[0].get_text() and "−1" in doc[0].get_text()
    names = {f[3] for f in doc[0].get_fonts()}
    assert any(n.startswith("LineovaSerif") for n in names)
