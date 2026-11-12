"""Issue 1 (extraction side): PR / முந்தைய ஆவண எண் citations must be harvested completely."""
import os
import pytest

from pdf_deterministic_extractor import PDFDeterministicExtractor as X


def _fmt(docs):
    return [d["formatted"] for d in docs]


# ---------------------------------------------------------------- _parse_pr_string
def test_parse_spaced_multi_parent_list_from_3086_2007():
    assert _fmt(X._parse_pr_string("1572/ 2007, 1644/ 2007, 1904/ 2007")) == ["1572/2007", "1644/2007", "1904/2007"]


@pytest.mark.parametrize("raw,expected", [
    ("2776/1983", ["2776/1983"]),
    ("27/ 1982", ["27/1982"]),
    ("3292/ 1991", ["3292/1991"]),
    ("1579/2021, 2776/1983", ["1579/2021", "2776/1983"]),
    ("3775/2011, 461/2020", ["3775/2011", "461/2020"]),
    ("1572/2007 மற்றும் 1644/2007", ["1572/2007", "1644/2007"]),
    ("1572-2007; 1644/2007 and 1904/2007", ["1572/2007", "1644/2007", "1904/2007"]),
    ("1572/2007 1644/2007", ["1572/2007", "1644/2007"]),          # whitespace-only separator
    ("1572/2007, 1572/ 2007", ["1572/2007"]),                       # de-duplicated
    ("-", []),
    ("", []),
])
def test_parse_pr_variants(raw, expected):
    assert _fmt(X._parse_pr_string(raw)) == expected


def test_parse_pr_rejects_dates_and_self_citation():
    assert _fmt(X._parse_pr_string("12-05-2007")) == []
    assert _fmt(X._parse_pr_string("3086/2007, 1572/2007", exclude_doc_id="3086/2007")) == ["1572/2007"]


def test_parse_pr_matches_baseline_on_benchmark_pr_fields(benchmark_extractions):
    """Every benchmark PR field parses to exactly what the pre-fix parser produced."""
    for name, ext in benchmark_extractions.items():
        for ent in ext.get("entries", []):
            raw = ent["pr_lineage"]["pr_raw"]
            assert _fmt(X._parse_pr_string(raw)) == _fmt(ent["pr_lineage"]["pr_documents"]), name


# ---------------------------------------------------------------- line harvesting
def test_value_on_same_line_as_label():
    lines = ["PR Number/முந்தைய ஆவண எண்: 1572/ 2007, 1644/ 2007, 1904/ 2007", "Schedule 1 Details:"]
    assert _fmt(X._parse_pr_string(X._extract_pr_raw_from_lines(lines))) == ["1572/2007", "1644/2007", "1904/2007"]


def test_value_on_next_line_legacy_layout():
    lines = ["PR Number/முந்தைய ஆவண எண்:", "2776/1983", "Schedule 1 Details:"]
    assert X._extract_pr_raw_from_lines(lines) == "2776/1983"


def test_wrapped_multi_parent_value():
    lines = ["PR Number/முந்தைய ஆவண எண்: 1572/ 2007, 1644/", "2007, 1904/ 2007", "Schedule 1 Details:"]
    assert _fmt(X._parse_pr_string(X._extract_pr_raw_from_lines(lines))) == ["1572/2007", "1644/2007", "1904/2007"]


def test_label_sharing_line_with_market_value():
    lines = ["Market Value/சந்தை மதிப்பு: Rs. 5,00,000/- PR Number/முந்தைய ஆவண எண்: 3086/2007", "Document Remarks: -"]
    assert X._extract_pr_raw_from_lines(lines) == "3086/2007"


def test_legacy_glyph_label():
    lines = ["முந்ைதய ஆவண எண்:", "1572/ 2007, 1644/ 2007", "Schedule 1 Details:"]
    assert _fmt(X._parse_pr_string(X._extract_pr_raw_from_lines(lines))) == ["1572/2007", "1644/2007"]


def _layout_deed_lines(n_parties=90):
    lines = [
        "Certificate of Encumbrance on Property",
        "S.R.O / : Srirangam Date / : 01-Jan-2026",
        "Document No.& Year/: 3086/2007",
        "Sr. No./ Date of Execution & Date of Presentation & Date of Registration",
        "1 05-Mar-2007 05-Mar-2007 05-Mar-2007",
        "Sale deed",
    ]
    lines += [f"{i}. Vendor Name {i}" for i in range(1, n_parties + 1)]
    lines += ["1. Sri Balaji Promoters", "-",
              "Consideration Value/கைமாற்றுத் தொகை: Rs. 1,00,000/-",
              "Market Value/சந்தை மதிப்பு: Rs. 1,00,000/-",
              "PR Number/முந்தைய ஆவண எண்: 1572/ 2007, 1644/",
              "2007, 1904/ 2007",
              "Schedule 1 Details:",
              "Property Type: Agricultural Land",
              "Village & Street: Kambarasampettai, -",
              "Survey No: 131/1B",
              "Number of Entries/பதிவுகளின் எண்ணிக்கை: 1"]
    return lines


def test_parse_entry_beyond_line_80_large_layout_deed():
    lines = _layout_deed_lines(90)
    meta = X._extract_metadata(lines, "3086", "2007", "Srirangam")
    ent = X._parse_entry(lines, meta)
    assert _fmt(ent["pr_lineage"]["pr_documents"]) == ["1572/2007", "1644/2007", "1904/2007"]


def test_baseline_parser_missed_these_citations():
    """Documents the verified root cause: the pre-fix parser looked only at the first 80 lines
    and only at the line after the label."""
    from conftest import load_baseline_module
    legacy = load_baseline_module("engines/engine_a/pdf_deterministic_extractor.py", "legacy_extractor_pr").PDFDeterministicExtractor
    lines = _layout_deed_lines(90)
    meta = legacy._extract_metadata(lines, "3086", "2007", "Srirangam")
    assert legacy._parse_entry(lines, meta)["pr_lineage"]["pr_documents"] == []
    same_line = ["Sale deed", "PR Number/முந்தைய ஆவண எண்: 1572/ 2007, 1644/ 2007, 1904/ 2007", "Schedule 1 Details:"]
    meta2 = legacy._extract_metadata(same_line, "3086", "2007", "")
    assert legacy._parse_entry(same_line, meta2)["pr_lineage"]["pr_documents"] == []


def test_survey_ec_cell_continuation():
    cell = "PR Number/முந்தைய ஆவண எண்: 1572/ 2007, 1644/\n2007, 1904/ 2007\nDocument Remarks: -"
    import re
    m = re.search(r'(?:PR\s*Number|முந்தைய\s*ஆவண\s*எண்)[^\:]*[\:\-]\s*([^\n\r]+)', cell)
    stitched = X._stitch_pr_cell_continuation(cell[m.start(1):])
    assert _fmt(X._parse_pr_string(stitched)) == ["1572/2007", "1644/2007", "1904/2007"]


# ---------------------------------------------------------------- real PDF round-trip
def test_real_pdf_round_trip(tmp_path):
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    # ASCII-only rendering (no Tamil font needed); 90 parties force a multi-page PDF and push
    # the PR row far beyond line 80.
    lines = [l for l in _layout_deed_lines(90) if all(ord(ch) < 128 for ch in l) and "1904" not in l]
    lines.insert(lines.index("Schedule 1 Details:"), "PR Number: 1572/ 2007, 1644/")
    lines.insert(lines.index("Schedule 1 Details:"), "2007, 1904/ 2007")
    pdf = tmp_path / "official_encumbrance_certificate.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    y = 820
    for l in lines:
        if y < 40:
            c.showPage(); y = 820
        c.drawString(30, y, l); y -= 14
    c.save()
    res = X.extract_from_pdf(str(pdf), "3086", "2007", "Srirangam")
    assert res["success"], res.get("error")
    assert _fmt(res["entries"][0]["pr_lineage"]["pr_documents"]) == ["1572/2007", "1644/2007", "1904/2007"]


def test_extractor_copies_are_identical():
    import hashlib
    from conftest import ROOT
    digests = {hashlib.md5(open(os.path.join(ROOT, "engines", e, "pdf_deterministic_extractor.py"), "rb").read()).hexdigest()
               for e in ("engine_a", "engine_b", "engine_c")}
    assert len(digests) == 1
