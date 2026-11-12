"""Regressions found on the live 1579/2021 Trichy Joint 1 run (run_20261112_214255).

Fixtures are short snippets copied from that run's sampled pages, plus the 1-page portal
error PDF that had been accepted as an EC ("Please try after sometime EC No Of Records:: 206").
"""
import os
import json
import pytest

from pdf_deterministic_extractor import PDFDeterministicExtractor as X
from ec_portal_client import ECPortalClient
import ec_engine_orchestrator as orch_mod
from ec_engine_orchestrator import ECEngineOrchestrator

HERE = os.path.dirname(__file__)
ERROR_PDF = os.path.join(HERE, "fixtures", "run1579_job03_error_page_206.pdf")


def _cert_pdf(path, lines):
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for l in lines:
        c.drawString(40, y, l)
        y -= 16
    c.save()
    return str(path)


# ---------------------------------------------------------------- 1. error page / split
def test_saved_error_page_is_not_an_authentic_ec():
    with open(ERROR_PDF, "rb") as f:
        info = ECPortalClient.inspect_ec_pdf(f.read())
    assert info["authentic"] is False
    assert info["reason"] == "PORTAL_ERROR_PAGE"
    assert info["error_record_count"] == 206


def test_real_certificate_text_is_authentic(tmp_path):
    p = _cert_pdf(tmp_path / "ok.pdf", ["Certificate of Encumbrance on Property",
                                        "Number of Entries: 1", "1579/2021 Sale deed"])
    with open(p, "rb") as f:
        assert ECPortalClient.inspect_ec_pdf(f.read())["authentic"] is True
    assert ECPortalClient.inspect_ec_pdf(b"<html>busy</html>")["reason"] == "NOT_A_PDF"


class _Resp:
    def __init__(self, text="", content=b""):
        self.text = text
        self.content = content or text.encode()
        self.status_code = 200


class _FakeSession:
    """Search HTML says 26 records (as on the run), but the certificate generator returns the
    'No Of Records:: 206' error page."""
    def __init__(self, pdf_bytes):
        self.pdf_bytes = pdf_bytes
        self.gets = 0

    def post(self, url, data=None, **kw):
        if "directPrintDwnLoad" in url:
            return _Resp('<a href="webHP?requestType=ApplicationRH&actionVal=dwnLoadPdf&id=1">pdf</a>')
        return _Resp('<input type="hidden" name="countNoRecords" id="countNoRecords" value="26"/>'
                     '<table id="DocPropertyDesc"><tr><th>Document No</th></tr><tr><td>4761/1975</td></tr></table>'
                     ' 26 items found')

    def get(self, url, **kw):
        self.gets += 1
        return _Resp(content=self.pdf_bytes)


def test_error_page_with_206_records_triggers_split_and_is_not_saved(tmp_path):
    with open(ERROR_PDF, "rb") as f:
        sess = _FakeSession(f.read())
    out = tmp_path / "EC_JOB_03.pdf"
    res = ECPortalClient.execute_ec_search(
        session=sess, auth_token="t", csrf_token="c", captcha_code="x",
        sro_info={"sro_id": "20445:1", "sro_name": "Trichy Joint 1", "district_id": "20034", "zone_id": "6"},
        survey_items=[{"village_id": "1", "survey_no": "173", "subdivision_no": "2"}],
        start_date="01-Jan-1975", end_date="31-Dec-1983", output_pdf_path=str(out),
        log_callback=lambda m: None,
    )
    assert res["split_needed"] is True and res["overflow"] is True
    assert res["portal_record_count"] == 206
    assert not out.exists()


# ---------------------------------------------------------------- 2. exhaustiveness verdicts
@pytest.mark.parametrize("res,ok,outcome", [
    ({"success": True, "nil": True, "count_field_present": True, "portal_record_count": 0}, True, "NIL_VERIFIED"),
    ({"success": True, "nil": True, "count_field_present": False}, False, "FAILED"),
    ({"success": True, "nil": False, "pdf_saved": None, "pdf_status": "ERROR_PAGE", "records": [{}] * 10}, False, "FAILED"),
    ({"success": False, "split_needed": True, "overflow": True}, False, "FAILED"),
    (None, False, "FAILED"),
])
def test_classify_window_result(res, ok, outcome):
    v = ECEngineOrchestrator.classify_window_result(res)
    assert v["ok"] is ok and v["outcome"] == outcome


def test_run_with_failed_parent_window_is_not_exhaustive(tmp_path, monkeypatch):
    """Replays the 1579 plan offline: TSLR nil, primary certified, parent window gets the
    206-record error page that cannot be split further. JOB_05 (173/2 to 2021) must be executed,
    not skipped as 'covered', and the run must not be VERIFIED_EXHAUSTIVE."""
    run = tmp_path / "run"
    (run / "deeds" / "01_Root_Doc_1579_2021").mkdir(parents=True)
    (run / "deeds" / "01_Root_Doc_1579_2021" / "02_pdf_detailed_extraction.json").write_text(json.dumps({"entries": []}))
    plan = {"harvested_envelope": {}, "total_search_jobs": 5, "search_jobs": [
        {"job_id": "JOB_01_TSLR", "track": "URBAN_TSLR", "sro_name": "Trichy Joint 1", "village_name": "Ward -AG (K.Abishekapuram)",
         "search_mode": "WARD_BLOCK_WISE", "ward_no": "AG", "block_no": "0014", "survey_no": "13", "subdivision_no": "",
         "date_start": "01-Jan-1975", "date_end": "12-Nov-2026"},
        {"job_id": "JOB_02_MASTER_PRIMARY", "track": "MASTER_SRO_BATCH", "sro_name": "Trichy Joint 1",
         "deed_villages": ["K-Abishekapuram"], "surveys": [["173", "2H"]], "search_mode": "SURVEY_WISE",
         "date_start": "01-Jan-1975", "date_end": "12-Nov-2026"},
        {"job_id": "JOB_03_MASTER_PARENT", "track": "MASTER_SRO_BATCH", "sro_name": "Trichy Joint 1",
         "deed_villages": ["K-Abishekapuram"], "surveys": [["173", "2"]], "search_mode": "SURVEY_WISE",
         "date_start": "01-Jan-1975", "date_end": "31-Dec-1983"},
        {"job_id": "JOB_04_PRIMARY_SF_173_2H", "track": "PRIMARY_SURVEY", "sro_name": "Trichy Joint 1",
         "village_name": "Ward -AG (K.Abishekapuram)", "search_mode": "SURVEY_WISE", "survey_no": "173",
         "subdivision_no": "2H", "date_start": "01-Jan-1975", "date_end": "12-Nov-2026"},
        {"job_id": "JOB_05_PARENT_SF_173_2", "track": "PARENT_SURVEY", "sro_name": "Trichy Joint 1",
         "village_name": "Ward -AG (K.Abishekapuram)", "search_mode": "SURVEY_WISE", "survey_no": "173",
         "subdivision_no": "2", "date_start": "01-Jan-1975", "date_end": "31-Dec-2021"},
    ]}
    good_pdf = _cert_pdf(tmp_path / "good.pdf", ["Certificate of Encumbrance on Property", "Number of Entries: 0"])
    calls = []

    def fake_search(**kw):
        calls.append(((kw.get("survey_items") or [{}])[0].get("subdivision_no"), kw["start_date"], kw["end_date"], kw.get("is_ward_block")))
        if kw.get("is_ward_block"):
            return {"success": True, "nil": True, "records": [], "pdf_saved": None, "count_field_present": True, "portal_record_count": 0}
        sub = (kw.get("survey_items") or [{}])[0].get("subdivision_no")
        if sub == "2" and kw["end_date"] == "31-Dec-1983" and kw["start_date"] == "01-Jan-1975":
            return {"success": False, "overflow": True, "split_needed": True, "pdf_status": "OVERFLOW", "portal_record_count": 206}
        if sub == "2" and kw["end_date"] != "31-Dec-2021":
            return {"success": True, "nil": False, "records": [{}], "pdf_saved": None, "pdf_status": "ERROR_PAGE",
                    "portal_record_count": 103, "count_field_present": True}
        import shutil
        dst = kw["output_pdf_path"]
        shutil.copy(good_pdf, dst)
        return {"success": True, "nil": False, "records": [], "pdf_saved": dst, "pdf_status": "CERTIFIED",
                "portal_record_count": 1, "count_field_present": True}

    monkeypatch.setattr(orch_mod.ECMatrixPlanner, "plan_from_engine_a_run", classmethod(lambda cls, d: json.loads(json.dumps(plan))))
    monkeypatch.setattr(orch_mod.ECPortalClient, "create_session", classmethod(lambda cls: object()))
    monkeypatch.setattr(orch_mod.ECPortalClient, "init_ec_session", classmethod(lambda cls, s, log_callback=None: {"auth_token": "a", "csrf_token": "c", "captcha_code": "x"}))
    monkeypatch.setattr(orch_mod.ECPortalClient, "resolve_sro_hierarchy", classmethod(lambda cls, n, return_details=False: ({"sro_id": "20445:1", "sro_name": "Trichy Joint 1"}, 1.0, []) if return_details else {"sro_id": "20445:1", "sro_name": "Trichy Joint 1"}))
    monkeypatch.setattr(orch_mod.ECPortalClient, "match_villages_with_dual_registry", classmethod(lambda cls, **kw: {"matched_villages": [("1", kw["deed_villages"][0])], "unresolved_villages": []}))
    monkeypatch.setattr(orch_mod.ECPortalClient, "execute_ec_search", classmethod(lambda cls, **kw: fake_search(**kw)))
    monkeypatch.setattr(orch_mod.time, "sleep", lambda s: None)

    ECEngineOrchestrator.run_for_engine_a_output(str(run), log_callback=lambda m: None)
    plan_out = json.load(open(run / "ec_engine_full_trace" / "01_ec_search_matrix_plan.json", encoding="utf-8"))
    assert plan_out["audit_status"] == "INCOMPLETE_UNRESOLVED_PARCEL"
    outcomes = {(o["job_id"], o["outcome"]) for o in plan_out["window_outcomes"]}
    assert ("JOB_01_TSLR", "NIL_VERIFIED") in outcomes
    assert ("JOB_04_PRIMARY_SF_173_2H", "COVERED_BY_MASTER_BATCH") in outcomes
    # JOB_05 really executed (date range beyond the failed parent batch)
    assert any(c[0] == "2" and c[2] == "31-Dec-2021" for c in calls)
    # the 206-record parent window was split into halves before failing
    assert sum(1 for c in calls if c[0] == "2" and c[2] != "31-Dec-2021") >= 3
    assert any(b["type"] == "EC_WINDOW_NOT_CERTIFIED" for b in plan_out["audit_blockers"])


# ---------------------------------------------------------------- 3-6. extraction fields
@pytest.mark.parametrize("raw,sqft", [
    ("விஸ்தர்ீ ணம்: 173/2 - 2520.0 SQUARE FEET", 2520.0),
    ("விஸ்தர்ீ ணம்: 13, 173/2H - 2340.0 SQUARE FEET", 2340.0),
    ("விஸ்தர்ீ ணம்: 173/2, 7 - 315.0 SQUARE FEET", 315.0),
    ("4.77 ஏக்கர்)", 207781.2),
    ("0.42 acre", 18295.2),
    ("2520சதுரடி", 2520.0),
    ("2520 SQFT", 2520.0),
])
def test_extent_uses_number_next_to_unit(raw, sqft):
    e = X._parse_extent_dict(raw)
    assert e["sqft"] == pytest.approx(sqft)
    assert "ணம்:" not in e["raw"] and not e["raw"].endswith(")")


def test_combined_survey_extent_cell_splits_label_from_value():
    cell = "Survey No-Extent/புல எண்-விஸ்தர்ீ ணம்: 13, 173/2H - 2340.0 SQUARE FEET"
    assert X._split_survey_extent_cell(cell) == ("13, 173/2H", "2340.0 SQUARE FEET")
    assert X._split_survey_extent_cell("Survey No./புல எண் : 173/2") is None


@pytest.mark.parametrize("v,exp", [("/", ""), (" - ", ""), ("1579/2021", "1579/2021"), ("5351/ 1973", "5351/ 1973")])
def test_empty_pr_placeholder(v, exp):
    assert X._clean_empty_pr(v) == exp


def test_survey_ec_rows_offline(tmp_path, monkeypatch):
    """Survey-EC table rows (as sampled from pages 16-17 and 84 of the run's 96-page EC):
    combined Survey No-Extent cell, ரூ. amounts, '/' PR, and label-only financial row whose
    values continue on the next page."""
    rows_p1 = [
        ["1", "15491/2021", "01-Dec-2021\n01-Dec-2021\n01-Dec-2021", "Sale deed", "1. ராமன்", "1. கிருஷ்ணன்", "-"],
        ["", "Consideration Value/ைகமாற்றுத் ெதாைக:\nரூ. 55,00,000/-", "", "Market Value/சந்ைத மதிப்பு:\nரூ. 55,00,000/-", "", "PR Number/முந்ைதய ஆவண எண்:\n/", ""],
        ["", "Schedule 1 Details:\nProperty Type/ெசாத்தின் வைகப்பாடு: Plot", "", "", "Survey No-Extent/புல எண்-விஸ்தர்ீ ணம்: 173/2 - 2520.0 SQUARE FEET", "", ""],
        ["2", "5154/1988", "14-Sep-1988\n19-Sep-1988\n19-Sep-1988", "Sale deed", "1. கோவிந்தம்", "1. ஜமீன்பானு", "-"],
        ["", "Consideration Value/ைகமாற்றுத் ெதாைக:", "", "Market Value/சந்ைத மதிப்பு:", "", "PR Number/முந்ைதய ஆவண எண்:", ""],
    ]
    rows_p2 = [
        ["", "ரூ. 40,320/-", "", "ரூ. 50,400/-", "", "5351/ 1973", ""],
        ["", "Schedule 1 Details:\nProperty Type/ெசாத்தின் வைகப்பாடு: House Site", "", "", "Property Extent/ெசாத்தின் விஸ்தீர்ணம்: 2520சதுரடி", "", ""],
    ]

    class _Page:
        def __init__(self, rows): self.rows = rows
        def extract_tables(self): return [self.rows]

    class _Pdf:
        pages = [_Page(rows_p1), _Page(rows_p2)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    import pdfplumber
    monkeypatch.setattr(pdfplumber, "open", lambda p: _Pdf())
    entries = X._extract_survey_ec_entries("fake.pdf", "Trichy Joint 1")
    by_id = {e["registration_particulars"]["document_id"]: e for e in entries}
    a = by_id["15491/2021"]
    assert a["schedules"][0]["survey_number"]["raw"] == "173/2"
    assert a["schedules"][0]["extent"]["sqft"] == 2520.0
    assert a["financials"]["market_value_num"] == 5500000.0
    assert a["pr_lineage"]["pr_raw"] == "" and a["pr_lineage"]["pr_documents"] == []
    b = by_id["5154/1988"]
    assert b["financials"]["consideration_value_num"] == 40320.0
    assert b["financials"]["market_value_num"] == 50400.0
    assert [d["formatted"] for d in b["pr_lineage"]["pr_documents"]] == ["5351/1973"]
