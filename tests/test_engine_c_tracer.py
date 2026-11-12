"""Engine C deterministic EC tracer: coverage-aware opinion, nature taxonomy, party accounting,
legal bridges, parcel identity dispositions, alterations and the remaining-extent ledger."""
import json

import pytest

from title_scrutiny_engine import TitleScrutinyEngine, TitleRiskStatus, ChainContinuityStatus
import ec_property_tracer as T

BOUNDS_26 = {"north": "பிளாட் எண் 20", "south": "30 அடி ரோடு", "east": "பிளாட் எண் 25", "west": "பிளாட் எண் 27"}


def ent(doc_id, nature, execs, claims, pr=(), date="01-Jan-2020", plot="26", survey="173/2H", sqft=2340.0,
        ptype="House Site", bounds=None, remarks="", flat="", pr_raw=None, village="Kattur"):
    no, yr = doc_id.split("/")
    return {
        "registration_particulars": {"document_number": no, "registration_year": yr, "document_id": doc_id,
                                     "nature_of_deed": nature, "dates": {"registration_date": date}},
        "parties": {"executants": [{"name": n} for n in execs], "claimants": [{"name": n} for n in claims]},
        "pr_lineage": {"pr_raw": pr_raw if pr_raw is not None else ", ".join(pr),
                       "pr_documents": [{"doc_no": p.split("/")[0], "year": p.split("/")[1]} for p in pr]},
        "document_remarks": remarks,
        "schedules": [{"plot_no": plot, "flat_no": flat, "property_type": ptype, "village": village,
                       "extent": {"raw": f"{sqft} Sq.ft", "sqft": sqft} if sqft else {},
                       "survey_number": {"raw": survey} if survey else {},
                       "boundaries": dict(bounds or {}), "schedule_remarks_full": remarks}],
    }


def write_run(tmp_path, deeds, ledger, root_doc, audit_status="VERIFIED_EXHAUSTIVE", blockers=None, windows=None):
    run = tmp_path / "run"
    (run / "deeds").mkdir(parents=True)
    for i, e in enumerate(deeds, 1):
        d = run / "deeds" / f"{i:02d}_Doc_{e['registration_particulars']['document_id'].replace('/', '_')}"
        d.mkdir()
        (d / "02_pdf_detailed_extraction.json").write_text(json.dumps({"entries": [e]}, ensure_ascii=False), encoding="utf-8")
    root = next(e for e in deeds if e["registration_particulars"]["document_id"] == root_doc)
    (run / "02_pdf_detailed_extraction.json").write_text(json.dumps({"entries": [root]}, ensure_ascii=False), encoding="utf-8")
    led = {"transactions": ledger}
    if audit_status:
        led["audit_status"] = audit_status
        led["audit_blockers"] = blockers or []
    (run / "04_unified_master_property_ledger_1975_2026.json").write_text(json.dumps(led, ensure_ascii=False), encoding="utf-8")
    if windows is not None:
        (run / "ec_engine_full_trace").mkdir()
        (run / "ec_engine_full_trace" / "01_ec_search_matrix_plan.json").write_text(
            json.dumps({"audit_status": audit_status, "audit_blockers": blockers or [], "window_outcomes": windows}), encoding="utf-8")
    return str(run)


def scrut(run, plot=None):
    return TitleScrutinyEngine.scrutinize_run(run, target_plot=plot, log_callback=lambda m: None)


def chain_1579(lender="பேங்க் ஆப் பரோடா"):
    parent = ent("2776/1983", "Sale", ["Raman"], ["வெங்கட்ராமன்"], date="10-Mar-1983", plot="", survey="173/2",
                 sqft=18295.2, ptype="Agricultural Land")
    root = ent("1579/2021", "Conveyance Metro/UA", ["Venkatraman"], ["பாலமுருகன்"], pr=["2776/1983"], date="05-Apr-2021",
               bounds=BOUNDS_26, ptype="Plot With Building")
    m1 = ent("1583/2021", "Deposit of Title Deeds", ["Balamurugan"], [lender], date="06-Apr-2021", bounds=BOUNDS_26)
    m2 = ent("83/2024", "Mortgage deed", ["பாலமுருகன்"], [lender], date="10-Jan-2024", bounds=BOUNDS_26)
    return parent, root, m1, m2


def blob(rep):
    return json.dumps(rep, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------
def test_1579_like_two_mortgages_incomplete_coverage_is_not_clear(tmp_path):
    parent, root, m1, m2 = chain_1579()
    blockers = [{"type": "EC_WINDOW_NOT_CERTIFIED", "job_id": "JOB_03", "date_start": "01-Jan-1975",
                 "date_end": "31-Dec-1976", "reason": "PORTAL_ERROR"}]
    run = write_run(tmp_path, [root, parent], [parent, root, m1, m2], "1579/2021",
                    audit_status="INCOMPLETE_UNRESOLVED_PARCEL", blockers=blockers,
                    windows=[{"job_id": "JOB_03", "date_start": "01-Jan-1975", "date_end": "31-Dec-1976", "outcome": "FAILED"}])
    a = scrut(run)["title_scrutiny_audit"]
    assert a["overall_title_risk"] == TitleRiskStatus.INCOMPLETE_EC_COVERAGE
    assert a["coverage_assessment"]["coverage_verdict"] == "INCOMPLETE"
    assert a["coverage_assessment"]["failed_jobs"][0]["job_id"] == "JOB_03"
    assert {m["mortgage_document_id"] for m in a["active_encumbrances"]} == {"1583/2021", "83/2024"}
    assert "பேங்க் ஆப் பரோடா" in a["legal_opinion_summary"]
    assert "JOB_03" in a["legal_opinion_summary"] and "not a certified legal opinion" in a["legal_opinion_summary"]
    assert a["chain_continuity_status"] == ChainContinuityStatus.INTACT
    assert a["target_property"]["canonical_plot"] == "26"


def test_actual_lender_named_and_complete_coverage_conditional(tmp_path):
    parent, root, m1, m2 = chain_1579(lender="Canara Bank, Thillai Nagar")
    run = write_run(tmp_path, [root, parent], [parent, root, m1, m2], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["overall_title_risk"] == TitleRiskStatus.CONDITIONAL_CLEAR
    assert "Canara Bank" in a["legal_opinion_summary"]
    assert "Baroda" not in a["legal_opinion_summary"]


def test_missing_audit_information_is_never_clear(tmp_path):
    parent, root, _, _ = chain_1579()
    run = write_run(tmp_path, [root, parent], [parent, root], "1579/2021", audit_status=None)
    a = scrut(run)["title_scrutiny_audit"]
    assert a["coverage_assessment"]["coverage_verdict"] == "UNKNOWN"
    assert a["overall_title_risk"] != TitleRiskStatus.CLEAR


def test_clean_chain_with_verified_coverage_is_clear(tmp_path):
    parent, root, _, _ = chain_1579()
    run = write_run(tmp_path, [root, parent], [parent, root], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["overall_title_risk"] == TitleRiskStatus.CLEAR
    assert "scrutiny_disclaimer" in a and "NOT a certified legal opinion" in a["scrutiny_disclaimer"]


def test_no_default_plot_26(tmp_path):
    parent, root, _, _ = chain_1579()
    for s in root["schedules"]:
        s["plot_no"] = ""
    stranger = ent("900/2022", "Sale", ["Kumar"], ["Mani"], date="01-Feb-2022", plot="26", survey="88/1")
    run = write_run(tmp_path, [root, parent], [parent, root, stranger], "1579/2021")
    rep = scrut(run)
    assert rep["title_scrutiny_audit"]["target_property"]["canonical_plot"] == "NOT_ON_RECORD"
    t1 = {t["registration_particulars"]["document_id"] for t in rep["tier1_target_property_ledger"]}
    assert "900/2022" not in t1


def test_later_sale_classified_as_sale(tmp_path):
    parent, root, _, _ = chain_1579()
    sale = ent("4000/2025", "Sale deed", ["Balamurugan"], ["Senthil"], pr=["1579/2021"], date="01-Mar-2025", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, root, sale], "1579/2021")
    rep = scrut(run)
    row = next(t for t in rep["tier1_target_property_ledger"] if t["registration_particulars"]["document_id"] == "4000/2025")
    assert row["nature_category"] == "SALE"
    assert row["disposition"] == "SUBSEQUENT_CONVEYANCE_SALE"
    assert rep["title_scrutiny_audit"]["overall_title_risk"] == TitleRiskStatus.CONDITIONAL_CLEAR


def test_court_attachment_and_lease_stay_on_target_ledger(tmp_path):
    parent, root, _, _ = chain_1579()
    court = ent("5100/2023", "Attachment before judgement - Court order", ["Sub Court Trichy"], ["Ravi"],
                date="01-Jun-2023", bounds=BOUNDS_26)
    lease = ent("5200/2023", "Lease upto 5 years", ["Balamurugan"], ["Tenant Co"], date="01-Jul-2023", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, root, court, lease], "1579/2021")
    rep = scrut(run)
    t1 = {t["registration_particulars"]["document_id"]: t for t in rep["tier1_target_property_ledger"]}
    assert t1["5100/2023"]["disposition"] == "COURT_ATTACHMENT_LIS_PENDENS"
    assert t1["5200/2023"]["disposition"] == "ENCUMBRANCE_LEASE"
    assert not any(t["registration_particulars"]["document_id"] in ("5100/2023", "5200/2023")
                   for t in rep["tier2_layout_neighbor_context"])
    assert rep["title_scrutiny_audit"]["overall_title_risk"] == TitleRiskStatus.HIGH_RISK_DEFECT


def test_joint_owner_who_did_not_sign_is_flagged(tmp_path):
    parent = ent("2776/1983", "Sale", ["Raman"], ["Venkatraman", "Lakshmi"], date="10-Mar-1983", plot="", survey="173/2", sqft=18295.2)
    root = ent("1579/2021", "Sale", ["Venkatraman"], ["Balamurugan"], pr=["2776/1983"], date="05-Apr-2021", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, root], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["chain_continuity_status"] == ChainContinuityStatus.JOINT_OWNER_GAP
    assert a["overall_title_risk"] == TitleRiskStatus.HIGH_RISK_DEFECT
    assert a["chain_continuity_steps"][0]["unaccounted_predecessor_owners"] == ["Lakshmi"]


def test_co_owner_release_accounts_for_joint_owner_and_is_not_a_discharge(tmp_path):
    parent = ent("2776/1983", "Sale", ["Raman"], ["Venkatraman", "Lakshmi"], date="10-Mar-1983", plot="", survey="173/2", sqft=18295.2)
    rel = ent("300/2010", "Release", ["Lakshmi"], ["Venkatraman"], pr=["2776/1983"], date="01-Jan-2010", plot="", survey="173/2", sqft=18295.2)
    root = ent("1579/2021", "Sale", ["Venkatraman"], ["Balamurugan"], pr=["2776/1983"], date="05-Apr-2021", bounds=BOUNDS_26)
    mort = ent("1583/2021", "Deposit of Title Deeds", ["Balamurugan"], ["Indian Bank"], date="06-Apr-2021", bounds=BOUNDS_26)
    # a co-owner style release citing the mortgage but executed by a person, not the bank
    fake = ent("1700/2022", "Release", ["Kamala"], ["Balamurugan"], pr=["1583/2021"], date="01-Jan-2022", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, rel, root, mort, fake], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["chain_continuity_steps"][0]["continuity"] == "INTACT_WITH_RELEASE"
    assert a["chain_continuity_status"] == ChainContinuityStatus.INTACT
    m = next(x for x in a["active_encumbrances"] if x["mortgage_document_id"] == "1583/2021")
    assert m["matching_discharge_deed"] is None
    assert any(v["document_id"] == "1700/2022" and not v["accepted"] for v in m["discharge_verification"])


def test_legal_heir_bridge_is_conditional_with_requisitions(tmp_path):
    parent = ent("2776/1983", "Sale", ["Raman"], ["Venkatraman"], date="10-Mar-1983", plot="", survey="173/2", sqft=18295.2)
    root = ent("1579/2021", "Sale", ["Senthil"], ["Balamurugan"], pr=["2776/1983"], date="05-Apr-2021", bounds=BOUNDS_26,
               remarks="executant is the legal heir of late Venkatraman")
    run = write_run(tmp_path, [root, parent], [parent, root], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["chain_continuity_status"] == ChainContinuityStatus.BRIDGED_WITH_LEGAL_HEIR
    assert a["overall_title_risk"] == TitleRiskStatus.CONDITIONAL_CLEAR
    assert any("legal-heir" in r for r in a["requisitions"])


def test_poa_bridge_from_ledger_deed_is_conditional(tmp_path):
    parent = ent("2776/1983", "Sale", ["Raman"], ["Venkatraman"], date="10-Mar-1983", plot="", survey="173/2", sqft=18295.2)
    poa = ent("50/2020", "General Power of Attorney", ["Venkatraman"], ["Senthil"], date="01-Jan-2020", plot="", survey="173/2", sqft=0)
    root = ent("1579/2021", "Sale", ["Senthil (AG)"], ["Balamurugan"], pr=["2776/1983"], date="05-Apr-2021", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, poa, root], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["chain_continuity_status"] == ChainContinuityStatus.BRIDGED_WITH_POA
    assert a["overall_title_risk"] == TitleRiskStatus.CONDITIONAL_CLEAR
    assert any("POA" in r for r in a["requisitions"])


def test_unexplained_break_is_high_risk(tmp_path):
    parent = ent("2776/1983", "Sale", ["Raman"], ["Venkatraman"], date="10-Mar-1983", plot="", survey="173/2", sqft=18295.2)
    root = ent("1579/2021", "Sale", ["Senthil"], ["Balamurugan"], pr=["2776/1983"], date="05-Apr-2021", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, root], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["chain_continuity_status"] == ChainContinuityStatus.BROKEN
    assert a["overall_title_risk"] == TitleRiskStatus.HIGH_RISK_DEFECT


def test_agricultural_identity_by_survey_and_boundaries(tmp_path):
    agri_b = {"north": "Muthu land", "south": "வாய்க்கால்", "east": "Govt road", "west": "Kannan land"}
    parent = ent("100/1990", "Sale", ["Raman"], ["Venkatraman"], date="01-Jan-1990", plot="", survey="45/3", sqft=43560.0,
                 ptype="Agricultural Land", bounds=agri_b)
    root = ent("200/2015", "Sale", ["Venkatraman"], ["Balamurugan"], pr=["100/1990"], date="01-Jan-2015", plot="", survey="45/3",
               sqft=43560.0, ptype="Agricultural Land", bounds=agri_b)
    crop = ent("300/2018", "Mortgage of crop", ["Balamurugan"], ["Primary Agricultural Co-op Bank"], date="01-Jan-2018", plot="",
               survey="45/3", sqft=43560.0, ptype="Agricultural Land", bounds=agri_b)
    other = ent("400/2018", "Sale", ["Kumar"], ["Mani"], date="01-Jan-2018", plot="", survey="45/3", sqft=10000.0,
                ptype="Agricultural Land", bounds={"north": "x", "south": "y", "east": "z", "west": "w"})
    run = write_run(tmp_path, [root, parent], [parent, root, crop, other], "200/2015")
    rep = scrut(run)
    t1 = {t["registration_particulars"]["document_id"] for t in rep["tier1_target_property_ledger"]}
    assert "300/2018" in t1 and "400/2018" not in t1
    assert rep["title_scrutiny_audit"]["target_property"]["property_class"] == "AGRICULTURAL_LAND"


def test_two_flats_on_same_plot_are_not_same_parcel():
    base = ent("1/2020", "Sale", ["A"], ["B"], plot="26", survey="173/2H", sqft=450.0, ptype="Flat - Undivided share", flat="A1")
    other = ent("2/2021", "Sale", ["C"], ["D"], plot="26", survey="173/2H", sqft=450.0, ptype="Flat - Undivided share", flat="B2")
    res = T.compare_identity(T.fingerprint(base), T.fingerprint(other))
    assert res["disposition"] == "SAME_LAND_DIFFERENT_UNIT"
    assert T.fingerprint(base)["extent_kind"] == "UDS"


def test_remaining_extent_overflow_is_flagged(tmp_path):
    parent = ent("2776/1983", "Sale", ["Raman"], ["Venkatraman"], date="10-Mar-1983", plot="", survey="173/2", sqft=3000.0)
    earlier = ent("900/2019", "Sale", ["Venkatraman"], ["Kumar"], pr=["2776/1983"], date="01-Jan-2019", plot="25", sqft=2000.0)
    root = ent("1579/2021", "Sale", ["Venkatraman"], ["Balamurugan"], pr=["2776/1983"], date="05-Apr-2021", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, earlier, root], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert a["remaining_extent_ledger"]["status"] == "AREA_OVERFLOW"
    assert a["remaining_extent_ledger"]["overflow_at_document"] == "1579/2021"
    assert a["overall_title_risk"] == TitleRiskStatus.HIGH_RISK_DEFECT


def test_subdivision_parent_child_and_neighbor_excluded(tmp_path):
    parent, root, _, _ = chain_1579()
    neighbour = ent("700/2022", "Sale", ["Kumar"], ["Mani"], date="01-Jan-2022", plot="27", survey="173/2H",
                    bounds={"north": "பிளாட் எண் 21", "east": "பிளாட் எண் 26"})
    run = write_run(tmp_path, [root, parent], [parent, root, neighbour], "1579/2021")
    rep = scrut(run)
    alts = {a["type"] for a in rep["title_scrutiny_audit"]["alterations"]}
    assert "SURVEY_SUBDIVISION" in alts and "PLOT_FORMATION_FROM_PARENT_LAND" in alts
    t2 = {t["registration_particulars"]["document_id"]: t for t in rep["tier2_layout_neighbor_context"]}
    assert t2["700/2022"]["disposition"] == "NEIGHBORING_PARCEL_IN_LAYOUT"
    assert T.survey_relation([("173", "2H")], [("173", "2")]) == "PARENT"
    assert T.survey_relation([("173", "2H")], [("173", "2G")]) == "SIBLING"


def test_missing_boundary_or_survey_is_insufficient_not_mismatch():
    tgt = T.fingerprint(ent("1/2020", "Sale", ["A"], ["B"], bounds=BOUNDS_26))
    cand = T.fingerprint(ent("2/2021", "Sale", ["C"], ["D"], plot="", survey="", sqft=0, bounds={}))
    res = T.compare_identity(tgt, cand)
    assert res["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert res["evidence"]["conflicting"] == []
    assert {"plot", "survey", "extent", "boundaries"} <= set(res["evidence"]["missing"])


def test_construction_recorded_as_alteration(tmp_path):
    parent, root, _, _ = chain_1579()
    cons = ent("800/2022", "Construction agreement", ["Balamurugan"], ["XYZ Builders"], date="01-Jan-2022", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, root, cons], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    assert any(x["type"] == "BUILDING_CONSTRUCTED" and x.get("to_document") == "800/2022" for x in a["alterations"])


def test_spaced_pr_discharge_reconciles_with_verification(tmp_path):
    parent, root, m1, _ = chain_1579(lender="Indian Bank")
    rec = ent("2000/2023", "Deed of Receipt", ["Indian Bank"], ["Balamurugan"], pr=[], pr_raw="1583/ 2021",
              date="01-Feb-2023", bounds=BOUNDS_26)
    run = write_run(tmp_path, [root, parent], [parent, root, m1, rec], "1579/2021")
    rep = scrut(run)
    a = rep["title_scrutiny_audit"]
    assert [m["matching_discharge_deed"] for m in a["discharged_encumbrances"]] == ["2000/2023"]
    assert a["overall_title_risk"] == TitleRiskStatus.CLEAR
    assert "NO_DISCHARGE_ON_RECORD" not in blob(rep)


def test_discharge_for_different_plot_is_rejected(tmp_path):
    parent, root, m1, _ = chain_1579(lender="Indian Bank")
    rec = ent("2000/2023", "Deed of Receipt", ["Indian Bank"], ["Balamurugan"], pr=["1583/2021"], date="01-Feb-2023", plot="31")
    run = write_run(tmp_path, [root, parent], [parent, root, m1, rec], "1579/2021")
    a = scrut(run)["title_scrutiny_audit"]
    m = next(x for x in a["active_encumbrances"] if x["mortgage_document_id"] == "1583/2021")
    v = next(x for x in m["discharge_verification"] if x["document_id"] == "2000/2023")
    assert v["checks"]["same_property"] is False and not v["accepted"]
    assert "Indian Bank" in a["legal_opinion_summary"]


def test_party_matching_rules():
    assert T.parties_match("பாலமுருகன்", "BALAMURUGAN")[0]
    assert not T.parties_match("ராமு", "ராமுசாமி")[0]                       # no substring
    assert not T.parties_match("M. Saraswathi", "K. Saraswathi")[0]         # conflicting initials
    assert T.parties_match("புஸ்பா(எ) புஸ்கலா", "புஸ்கலா")[0]                 # documented aka
    assert T.parties_match("ேபங்க் ஆப் பேராடா", "Bank of Baroda, Trichy")[0]  # institution (legacy glyph order)
    assert not T.parties_match("Bank of Baroda", "Canara Bank")[0]
    assert not TitleScrutinyEngine.are_parties_equivalent("Kumar", "Kumaravel")
    personal = {k for k in TitleScrutinyEngine.NAME_ALIASES if k in ("பாலமுருகன்", "வெங்கட்ராமன்", "சுப்ரமணியன்")}
    assert not personal


@pytest.mark.parametrize("nature,cat", [
    ("Conveyance Metro/UA", "SALE"), ("Gift deed", "GIFT"), ("Settlement-family members", "SETTLEMENT"),
    ("Partition-between family", "PARTITION"), ("Deposit of Title Deeds", "MORTGAGE"),
    ("Reconveyance of mortgaged property", "MORTGAGE_DISCHARGE"), ("Deed of Receipt", "MORTGAGE_DISCHARGE"),
    ("Release", "RELEASE"), ("Rectification Deed", "RECTIFICATION"), ("Cancellation of sale deed", "CANCELLATION"),
    ("General Power of Attorney", "POWER_OF_ATTORNEY"), ("Lease upto 5 years", "LEASE"),
    ("Attachment of property", "COURT_ORDER"), ("Lis pendens", "COURT_ORDER"), ("Will", "WILL"),
    ("கிரயம்", "SALE"), ("அடமானம்", "MORTGAGE"),
])
def test_nature_taxonomy(nature, cat):
    assert T.classify_nature(nature) == cat


def test_normalize_text_is_idempotent_on_standard_tamil():
    std = "வெங்கட்ராமன் பேங்க்"
    assert T.normalize_text(std) == std
    assert T.normalize_text(T.normalize_text("ெவங்கட்ராமன்")) == "வெங்கட்ராமன்"
