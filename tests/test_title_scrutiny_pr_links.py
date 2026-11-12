"""Engine C consistency with the multi-parent PR traversal: the upstream chain must follow a
cited parent that is actually in evidence, and a discharge receipt whose PR field cites the
mortgage with spacing ('5000/ 2023') must still reconcile."""
import json
import os

import pytest

from title_scrutiny_engine import TitleScrutinyEngine


def _ent(doc_id, nature, execs, claims, pr_docs, pr_raw="", date="01-Jan-2020", plot="26"):
    no, yr = doc_id.split("/")
    return {
        "registration_particulars": {"document_number": no, "registration_year": yr, "document_id": doc_id,
                                     "nature_of_deed": nature, "dates": {"registration_date": date}},
        "parties": {"executants": [{"name": n} for n in execs], "claimants": [{"name": n} for n in claims]},
        "pr_lineage": {"pr_raw": pr_raw or ", ".join(pr_docs),
                       "pr_documents": [{"doc_no": p.split("/")[0], "year": p.split("/")[1], "formatted": p} for p in pr_docs]},
        "financials": {},
        "schedules": [{"plot_no": plot, "extent": {"raw": "1000 sqft", "sqft": 1000.0}, "survey_number": {"raw": "131/1B"},
                       "boundaries": {}, "schedule_remarks_full": ""}],
    }


def _write_run(tmp_path, deeds, ledger_tx, root_doc):
    run = tmp_path / "run"
    (run / "deeds").mkdir(parents=True)
    for i, ent in enumerate(deeds, 1):
        d = run / "deeds" / f"{i:02d}_Doc_{ent['registration_particulars']['document_id'].replace('/', '_')}"
        d.mkdir()
        (d / "02_pdf_detailed_extraction.json").write_text(json.dumps({"success": True, "entries": [ent]}), encoding="utf-8")
    root = next(e for e in deeds if e["registration_particulars"]["document_id"] == root_doc)
    (run / "02_pdf_detailed_extraction.json").write_text(json.dumps({"success": True, "entries": [root]}), encoding="utf-8")
    (run / "04_unified_master_property_ledger_1975_2026.json").write_text(json.dumps({"transactions": ledger_tx}), encoding="utf-8")
    return str(run)


def test_upstream_chain_follows_cited_parent_present_in_evidence(tmp_path):
    root = _ent("3086/2007", "Sale deed", ["Kannan"], ["Balaji Promoters"], ["1904/2007", "1572/2007"], date="05-Mar-2007")
    parent = _ent("1572/2007", "Sale deed", ["Muthu"], ["Kannan"], [], date="01-Feb-2007")
    run = _write_run(tmp_path, [root, parent], [], "3086/2007")
    rep = TitleScrutinyEngine.scrutinize_run(run, target_plot="26", log_callback=lambda m: None)
    blob = json.dumps(rep, ensure_ascii=False)
    assert "1572/2007" in blob
    steps = [s for s in json.dumps(rep).split('"predecessor": ')[1:]]
    assert any(s.startswith('"1572/2007"') for s in steps)


def test_discharge_receipt_with_spaced_pr_reconciles(tmp_path):
    root = _ent("1579/2021", "Sale deed", ["Venkatraman"], ["Balamurugan"], [], date="11-Mar-2021")
    modt = _ent("5000/2023", "Deposit of Title Deeds", ["Balamurugan"], ["Indian Bank"], ["1579/2021"], date="01-Jun-2023")
    receipt = _ent("7000/2025", "Receipt", ["Indian Bank"], ["Balamurugan"], ["5000/2023"], pr_raw="5000/ 2023", date="01-Jun-2025")
    run = _write_run(tmp_path, [root], [modt, receipt], "1579/2021")
    rep = TitleScrutinyEngine.scrutinize_run(run, target_plot="26", log_callback=lambda m: None)
    blob = json.dumps(rep, ensure_ascii=False)
    assert "5000/2023" in blob
    assert "NO_DISCHARGE_ON_RECORD" not in blob
