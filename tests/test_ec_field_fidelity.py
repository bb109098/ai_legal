"""
EC raw PDF -> JSON field fidelity (Engine B survey-EC path + shared helpers).

Fixture: tests/fixtures/ec_1579_job02_sampled_rows.json holds the pdfplumber table rows of 11
sampled entries of the 22:25 run's Job 02 EC (Trichy Joint 1, survey 173/2H, 96 pages), with the
original page splits. Strings are the certificate's own legacy-order Tamil text.
"""
import os
import sys
import json
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engines", "engine_a"))
from pdf_deterministic_extractor import PDFDeterministicExtractor as X  # noqa: E402

FIX = json.load(open(os.path.join(HERE, "fixtures", "ec_1579_job02_sampled_rows.json"), encoding="utf-8"))
SIDES = ("north", "south", "east", "west")


@pytest.fixture(scope="module")
def ledger():
    import pdfplumber

    class _Page:
        def __init__(self, rows): self.rows = rows
        def extract_tables(self): return [self.rows]

    class _Pdf:
        pages = [_Page(p) for p in FIX["pages"]]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    orig = pdfplumber.open
    pdfplumber.open = lambda p: _Pdf()
    try:
        entries = X._extract_survey_ec_entries("fake.pdf", "Trichy Joint 1")
    finally:
        pdfplumber.open = orig
    return {e["registration_particulars"]["document_id"]: e for e in entries}


def _b(e, i=0):
    return e["schedules"][i]["boundaries"]


# ------------------------------------------------------------------ boundaries: layout families
def test_all_sampled_entries_extracted(ledger):
    assert len(ledger) == 11


def test_suffix_tamil_same_landmark_all_sides_with_wrap(ledger):
    b = _b(ledger["4761/1975"])  # "30 அடி\nரோட்டுக்கு தெற்கு" wraps mid-phrase
    assert b["layout_family"] == "TAMIL_SUFFIX_RELATIVE"
    assert all(b[s] == "30 அடி ரோட்டுக்கு" for s in SIDES)


def test_suffix_tamil_landmark_goes_to_opposite_side(ledger):
    # "10அடி அகலமுள்ள பாதைக்கு வடக்கு" = property lies NORTH of the path -> path is the SOUTH side
    b = _b(ledger["358/1976"])
    assert b["south"] == "10அடி அகலமுள்ள பாதைக்கு"
    assert b["north"] == "74 வது மனைக்கு"
    assert b["east"] == "ராமானுஜம் மனைக்கு"
    assert b["west"] == "மீட்டர் பாக்டரி ரோட்டுக்கு"
    words = [a["direction_word"] for a in b["as_written"]]
    assert words == ["வடக்கு", "தெற்கு", "மேற்கு", "கிழக்கு"]


def test_suffix_landmark_without_dative_in_dative_list(ledger):
    b = _b(ledger["627/1977"])  # "... பிளாட் நீ 51 மேற்கு" (no -க்கு) inside a dative list
    assert all(b[s] for s in SIDES)
    assert b["east"] == "பிளாட் நீ 51"


def test_boundary_continued_on_next_page_is_stitched(ledger):
    b = _b(ledger["995/1983"])  # last two sides are on the next page as an unlabelled row
    assert all(b[s] for s in SIDES)
    assert b["north"] == "ரெங்கநாதன் நிலத்திற்கு"
    assert b["east"] == "சாவித்திரி நிலத்திற்கு"
    assert ledger["995/1983"]["schedules"][0]["schedule_remarks_full"] in ("", "-")


def test_tamil_conjunction_um_shares_landmark_and_matches_english_twin(ledger):
    """Plot 72 appears twice: Tamil 1405/2010 ("ரோட்டுக்கும் தெற்கும், மேற்கும்") and English
    2528/2015 ("SOUTH AND WEST OF 30 FEET WIDE ROAD"). Both must give the same four sides."""
    t, en = _b(ledger["1405/2010"]), _b(ledger["2528/2015"])
    assert t["north"].startswith("30அடி அகலமுள்ள ரோட்டு") and t["east"] == t["north"]
    assert t["south"].startswith("பிளாட் எண்.77") and t["west"].startswith("பிளாட் எண்.73")
    assert en["north"] == en["east"] == "30 FEET WIDE ROAD"
    assert en["south"] == "PLOT NO 77" and en["west"] == "PLOT NO 73"
    assert en.get("direction_convention") == "ENGLISH_OF_RELATIVE"


def test_english_by_prefix(ledger):
    b = _b(ledger["1754/2013"])
    assert b["layout_family"] == "PREFIX_LABEL"
    assert (b["east"], b["west"]) == ("PLOT NO 25", "PLOT NO 23")
    assert b["north"] and b["south"]


def test_dash_boundaries_are_not_invented(ledger):
    b = _b(ledger["4503/1980"])  # "-, -, -, -"
    assert b["layout_family"] == "EMPTY_ON_CERTIFICATE"
    assert not any(b[s] for s in SIDES)


@pytest.mark.parametrize("raw,expect", [
    ("East: பிளாட்நெ45, West: 30 அடி\nரோடு, North: X, South: -", {"east": "பிளாட்நெ45", "west": "30 அடி ரோடு", "north": "X", "south": ""}),
    ("East:, West:, North:, South:", {"east": "", "west": "", "north": "", "south": ""}),
    # 2482/2002 as printed (legacy glyph order; "வடக்கில", broken "ேமறகல்")
    ("\u0bb5\u0b9f\u0b95\u0bcd\u0b95\u0bbf\u0bb2-P.S \u0bae\u0bc1\u0ba4\u0bcd\u0ba4\u0bc1 \u0bc6\u0b9a\u0bbe\u0ba8\u0bcd\u0ba4\u0bae\u0bbe\u0ba9 \u0bae\u0bc8\u0ba9, \u0bc6\u0ba4\u0bb1\u0bcd\u0b95\u0bbf\u0bb2\u0bcd-30\u0b85\u0b9f\u0bbf\n\u0b85\u0b95\u0bb2\u0b95\u0bbf\u0bc7\u0bae \u0bc7\u0bb0\u0bbe\u0b9f\u0bc1, \u0b95\u0bbf\u0bb4\u0b95\u0bcd\u0b95\u0bbf\u0bb2\u0bcd-\u0ba8\u0bbe\u0b95\u0bae\u0bcd\u0bae\u0bbe\u0bb3\u0bcd \u0b95\u0bbe\u0bb2\u0bbf\u0bae\u0bc8\u0ba9, \u0bc7\u0bae\u0bb1\u0b95\u0bb2\u0bcd-\n\u0bc6\u0baa\u0bbe\u0ba9\u0bcd\u0ba9\u0bae\u0bcd\u0bae\u0bbe\u0bb3\u0bcd \u0bc6\u0b9a\u0bbe\u0ba8\u0bcd\u0ba4\u0bae\u0bbe\u0ba9 \u0b95\u0bbe\u0bb2\u0bbf\u0bae\u0bc8\u0ba9",
     {"north": "P.S முத்து சொந்தமான மனை", "south": "30அடி அகலகிமே ரோடு", "east": "நாகம்மாள் காலிமனை", "west": "பொன்னம்மாள் சொந்தமான காலிமனை"}),
    ("(வ) ரோடு (தெ) மனை (கி) வீடு (மே) தோட்டம்", {"north": "ரோடு", "south": "மனை", "east": "வீடு", "west": "தோட்டம்"}),
])
def test_parse_boundaries_prefix_variants(raw, expect):
    b = X._parse_boundaries(raw)
    assert {s: b[s] for s in SIDES} == expect


def test_glued_direction_word_and_aforesaid_is_not_west():
    # 2436/2004 as printed: "...நிலத்திற்குவடக்கு" glued to the dative ending
    b = X._parse_boundaries("\u0b8e.\u0bc6\u0b95\u0bbe\u0b9f\u0bc1\u0baa\u0bcd\u0baa\u0bb5\u0bb0\u0bcd \u0ba8\u0bbf\u0bb2\u0ba4\u0bcd\u0ba4\u0bbf\u0bb1\u0bcd\u0b95\u0bc1\u0bb5\u0b9f\u0b95\u0bcd\u0b95\u0bc1, \u0bae\u0bc0\u0ba9\u0bbe\u0b9f\u0bcd\u0b9a\u0bbf \u0ba8\u0bbf\u0bb2\u0ba4\u0bcd\u0ba4\u0bbf\u0bb1\u0bcd\u0b95\u0bc1 \u0bc6\u0ba4\u0bb1\u0bcd\u0b95\u0bc1,\n\u0bc6\u0baa\u0bbe\u0ba4\u0bc1\u0baa\u0bbe\u0bc8\u0ba4\u0b95\u0bcd\u0b95\u0bc1 \u0bc7\u0bae\u0bb1\u0bcd\u0b95\u0bc1, \u0b9a\u0bbf\u0ba4\u0bae\u0bcd\u0baa\u0bb0\u0bae\u0bcd \u0ba8\u0bbf\u0bb2\u0ba4\u0bcd\u0ba4\u0bbf\u0bb1\u0bcd\u0b95\u0bc1 \u0b95\u0bbf\u0bb4\u0b95\u0bcd\u0b95\u0bc1")
    assert all(b[s] for s in SIDES)
    assert b["south"] == "எ.கொடுப்பவர் நிலத்திற்கு"
    # "மேற்படி" (aforesaid) is never a direction word (legacy order as printed)
    b2 = X._parse_boundaries("\u0bc7\u0bae\u0bb1\u0bcd\u0baa\u0b9f\u0bbf \u0bae\u0bc8\u0ba9\u0b95\u0bcd\u0b95\u0bc1 \u0bb5\u0b9f\u0b95\u0bcd\u0b95\u0bc1")
    assert b2["south"] == "மேற்படி மனைக்கு" and not b2["west"]


# ------------------------------------------------------------------ page-break split main rows
def test_registration_date_on_next_page_is_not_copied_from_execution(ledger):
    d = ledger["178/1997"]["registration_particulars"]["dates"]
    assert d == {"execution_date": "22-Jan-1997", "presentation_date": "22-Jan-1997", "registration_date": "24-Jan-1997"}


def test_parties_continued_on_next_page(ledger):
    e = ledger["5201/2003"]
    assert len(e["parties"]["claimants"]) == 5
    e2 = ledger["5604/2008"]
    assert len(e2["parties"]["executants"]) == 6 and len(e2["parties"]["claimants"]) == 6


def test_wrapped_organisation_name_is_one_party(ledger):
    ex = ledger["5201/2003"]["parties"]["executants"]
    assert len(ex) == 1 and "லிமிடெட்" in ex[0]["name"] and ex[0]["party_type"] == "ORGANIZATION"


def test_party_reference_suffix_and_unicode_order(ledger):
    p = ledger["4761/1975"]["parties"]["executants"][0]
    assert not p["name"][-1].isdigit() and p.get("party_ref") == "1"
    c = ledger["358/1976"]["parties"]["claimants"][0]
    assert c["name"] == "வெங்கடாசலம்"  # legacy "ெவங்கடாசலம் 1" -> standard order, ref stripped
    assert c["raw"].endswith("1")      # raw kept verbatim


# ------------------------------------------------------------------ registration particulars
def test_volume_and_page_split(ledger):
    r = ledger["4503/1980"]["registration_particulars"]
    assert (r["volume_no"], r["page_no"], r["vol_page_raw"]) == ("2729", "141", "2729, 141")
    assert ledger["5201/2003"]["registration_particulars"]["volume_no"] is None  # '-' on certificate


def test_document_remarks_captured(ledger):
    assert ledger["4503/1980"]["document_remarks"] == "volumeno:2415 pageno:105 5076/1974"


# ------------------------------------------------------------------ schedule identity
def test_street_and_door_split_across_rows(ledger):
    s = ledger["178/1997"]["schedules"][0]
    assert s["street"] == "INDIAN BANK COLONY(INCLUDING DAVID COLONY)"
    assert s["new_door_no"] == "27" and s["door_no"] == "27"


def test_field_labels_never_leak_into_values(ledger):
    s = ledger["5201/2003"]["schedules"][0]
    assert s["flat_no"] == "0" and s["new_door_no"] == "0" and s["old_door_no"] == "0"
    assert s["plot_no"] == "64"


def test_lettered_schedule_and_no_phantom_schedule(ledger):
    sch = ledger["5604/2008"]["schedules"]
    assert [x["schedule_id"] for x in sch] == ["Schedule B"]
    # boundary text names neighbour plots 74/76: never used as this schedule's plot number
    assert sch[0]["plot_no"] == ""


def test_multi_survey_list(ledger):
    sn = ledger["4503/1980"]["schedules"][0]["survey_number"]
    assert sn["subdivision"] == "2"
    assert sn["survey_list"] == [{"survey": "173", "subdivision": "2"}, {"survey": "173", "subdivision": "2T"}]
    assert X._parse_survey_dict("173/2, 7")["subdivision"] == "2, 7"  # unchanged legacy reading


# ------------------------------------------------------------------ PR citations
@pytest.mark.parametrize("raw,own,expect", [
    ("1873/ 78", "5201/2003", ["1873/1978"]),
    ("2209/ 5, 2978/ 71, 3580/ 4", "4201/2013", ["2209/2005", "2978/1971", "3580/2004"]),
    ("1151/ 15, 1405/ 10", "2528/2015", ["1151/2015", "1405/2010"]),
    ("5593/68/", "93/2018", ["5593/1968"]),
    ("0/ 1900", "561/1997", []),
    ("0/ 0", "1723/2001", []),
    ("5351/ 1973", "5154/1988", ["5351/1973"]),
])
def test_pr_abbreviated_years_and_placeholders(raw, own, expect):
    got = X._parse_pr_string(raw, exclude_doc_id=own)
    assert [d["formatted"] for d in got] == expect


def test_pr_short_year_from_page_split_row(ledger):
    assert [d["formatted"] for d in ledger["5201/2003"]["pr_lineage"]["pr_documents"]] == ["1873/1978"]
    assert ledger["5201/2003"]["pr_lineage"]["pr_documents"][0]["year_as_printed"] == "78"


# ------------------------------------------------------------------ helpers
@pytest.mark.parametrize("cell,expect", [
    ("1. ராமன்\n2. கிருஷ்ணன்", ["ராமன்", "கிருஷ்ணன்"]),
    ("1. ... கூட்டுறவு சங்கம்\nலிமிெடட்", ["... கூட்டுறவு சங்கம் லிமிெடட்"]),
    ("Kamalam", ["Kamalam"]),
    ("-", []),
])
def test_split_party_cell(cell, expect):
    assert X._split_party_cell(cell) == expect


def test_continuation_row_detection():
    assert X._is_continuation_row(["", "", "24-Jan-1997", "", "", "", ""])
    assert not X._is_continuation_row(["", "New Door No./புதிய கதவு எண்: 27", "", "", "", "", ""])
    assert not X._is_continuation_row(["கட்டணமில்லா ெதாைலேபசி எண்", "1800 102 5174"])
