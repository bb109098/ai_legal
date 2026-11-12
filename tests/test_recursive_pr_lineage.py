"""Issue 1 (traversal side): an officially cited PR deed must be traversed - and its own PR
citations queued - even when its village / survey differ from the child deed because of an
administrative boundary shift (rural revenue village -> urban ward / TSLR, layout consolidation,
SRO bifurcation). Fixture: 8396/2022 -> 3086/2007 -> {1572/2007, 1644/2007, 1904/2007}."""
import glob
import json
import os

import pytest

import recursive_pr_engine as rpe
from recursive_pr_engine import RecursivePREngine
from pdf_deterministic_extractor import PDFDeterministicExtractor as X

TJ3 = {"sro_id": "SRO_TJ3", "sro_name": "Trichy Joint 3"}      # root SRO (created after 2007)
TJ1 = {"sro_id": "SRO_TJ1", "sro_name": "Trichy Joint 1"}      # mother SRO
MAN = {"sro_id": "SRO_MAN", "sro_name": "Manachanallur"}       # sister SRO (homonym holder)
SRG = {"sro_id": "SRO_SRG", "sro_name": "Srirangam"}           # sister SRO (true rural parent)
DISTRICT = [TJ1, TJ3, MAN, SRG]


def _extraction(doc_id, executants, claimants, pr_lines, village, survey, remarks=""):
    """Builds an extraction exactly as the extractor would, using the real PR harvesting path."""
    pr_raw = X._extract_pr_raw_from_lines(pr_lines) if pr_lines else ""
    d_no, yr = doc_id.split("/")
    return {
        "success": True,
        "document_metadata": {"search_query_doc": d_no, "search_query_year": yr},
        "entries": [{
            "registration_particulars": {"document_number": d_no, "registration_year": yr, "document_id": doc_id},
            "parties": {"executants": [X._format_party_entry(n) for n in executants],
                        "claimants": [X._format_party_entry(n) for n in claimants]},
            "pr_lineage": {"pr_raw": pr_raw, "pr_documents": X._parse_pr_string(pr_raw, exclude_doc_id=doc_id)},
            "financials": {},
            "schedules": [{"village": village, "survey_number": {"raw": survey}, "schedule_remarks_full": remarks,
                           "boundaries": {}, "flat_details": {}}],
        }],
    }


ROOT_8396 = dict(villages=["WARD -AJ (Piratiyur East)"], surveys=["19,71/2,94/1,95/1"],
                 ext=_extraction("8396/2022", ["Lakshmi Constructions"], ["Bala Murugan"],
                                 ["PR Number/முந்தைய ஆவண எண்:", "3086/2007"], "WARD -AJ (Piratiyur East)",
                                 "19,71/2,94/1,95/1", "புதிய வார்டு ஏஜே, புதிய பிளாக் 2, புதிய டி.எஸ்.நெ.19 ஆகும்"))

PR_3086_LINES = ["PR Number/முந்தைய ஆவண எண்: 1572/ 2007, 1644/", "2007, 1904/ 2007"]


def _install_fakes(monkeypatch, registry):
    """registry: {(sro_id, doc_id): {"villages":[], "surveys":[], "ext": extraction}}"""
    marker_to_ext = {}

    def fake_fetch(sro_id, sro_name, doc_no, year, book_no="1", run_folder="", log_callback=None):
        key = (sro_id, f"{doc_no}/{year}")
        rec = registry.get(key)
        base = {"success": False, "doc_no": doc_no, "year": year, "sro_id": sro_id, "sro_name": sro_name,
                "total_records_found": 0, "schedules": [], "survey_numbers": [], "villages": [], "error": "NO_RECORDS_FOUND"}
        if not rec:
            return base
        marker = f"{sro_id}|{doc_no}/{year}"
        marker_to_ext[marker] = rec["ext"]
        res = dict(base, success=True, total_records_found=1, error=None,
                   survey_numbers=rec["surveys"], villages=rec["villages"])
        if run_folder:
            os.makedirs(run_folder, exist_ok=True)
            pdf = os.path.join(run_folder, "official_encumbrance_certificate.pdf")
            with open(pdf, "wb") as fh:
                fh.write(b"%PDF-1.7\n" + marker.encode() + b"\n" + b"0" * 2048)
            res["official_pdf_saved"] = pdf
        return res

    def fake_extract(pdf_path, doc_no="", year="", sro=""):
        with open(pdf_path, "rb") as fh:
            marker = fh.read().split(b"\n")[1].decode()
        return json.loads(json.dumps(marker_to_ext[marker]))

    monkeypatch.setattr(rpe.EngineACore, "fetch_portal_document", staticmethod(fake_fetch))
    monkeypatch.setattr(rpe.PDFDeterministicExtractor, "extract_from_pdf", staticmethod(fake_extract))
    monkeypatch.setattr(rpe.time, "sleep", lambda s: None)
    monkeypatch.setattr(RecursivePREngine, "find_district_sros",
                        classmethod(lambda cls, sid, sname, did="": ("Trichy", DISTRICT, TJ1)))


def _run(tmp_path, root=TJ3, doc="8396", year="2022"):
    return RecursivePREngine.execute_lineage_discovery(doc, year, root["sro_id"], root["sro_name"],
                                                       run_folder=str(tmp_path), log_callback=None)


def _base_registry(genuine_3086_claimants):
    return {
        (TJ3["sro_id"], "8396/2022"): ROOT_8396,
        # Homonym 3086/2007 at a sister SRO earlier in the cascade (different deed entirely)
        (MAN["sro_id"], "3086/2007"): dict(villages=["Samayapuram"], surveys=["22/3"],
                                           ext=_extraction("3086/2007", ["Unrelated Seller"], ["Unrelated Buyer"],
                                                           ["PR Number/முந்தைய ஆவண எண்:", "77/1990"], "Samayapuram", "22/3")),
        # Genuine rural parent: Kambarasampettai SF 131/1B, cites three parents
        (SRG["sro_id"], "3086/2007"): dict(villages=["Kambarasampettai"], surveys=["131/1B"],
                                           ext=_extraction("3086/2007", ["Kannan", "Selvi", "Ramasamy"], genuine_3086_claimants,
                                                           PR_3086_LINES, "Kambarasampettai", "131/1B")),
        (SRG["sro_id"], "1572/2007"): dict(villages=["Kambarasampettai"], surveys=["131/1B"],
                                           ext=_extraction("1572/2007", ["Muthu"], ["Kannan"],
                                                           ["PR Number/முந்தைய ஆவண எண்:", "500/1998"], "Kambarasampettai", "131/1B")),
        (TJ1["sro_id"], "1644/2007"): dict(villages=["Kambarasampettai"], surveys=["131/1C"],
                                           ext=_extraction("1644/2007", ["Velu"], ["Selvi"], ["PR Number/முந்தைய ஆவண எண்:", "-"],
                                                           "Kambarasampettai", "131/1C")),
        # 1904/2007 is not indexed online anywhere -> offline citation edge (never silently dropped)
        (SRG["sro_id"], "500/1998"): dict(villages=["Kambarasampettai"], surveys=["131/1"],
                                          ext=_extraction("500/1998", ["Periyasamy"], ["Muthu"], ["PR Number/முந்தைய ஆவண எண்:", "-"],
                                                          "Kambarasampettai", "131/1")),
    }


def _edge(lineage, child, parent):
    return next((e for e in lineage["lineage_edges"] if e["from_child"] == child and e["to_parent"] == parent), None)


def test_8396_chain_traverses_past_depth_1_with_party_continuity(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, _base_registry(["Lakshmi Constructions"]))
    lin = _run(tmp_path)
    deeds = lin["master_deeds"]
    assert set(deeds) == {"8396/2022", "3086/2007", "1572/2007", "1644/2007", "500/1998"}
    # 3086/2007 resolved at the TRUE SRO (Srirangam), not the earlier homonym, not mis-attributed to Tier 1
    assert deeds["3086/2007"]["sro_name"] == "Srirangam"
    assert any("party continuity" in r for r in deeds["3086/2007"]["reasons"])
    assert deeds["3086/2007"]["verification_status"] == "CONCORDANCE_CONFIRMED"
    # all three cited parents were queued from the 3086/2007 PR field
    for parent in ("1572/2007", "1644/2007", "1904/2007"):
        assert _edge(lin, "3086/2007", parent), parent
    assert _edge(lin, "3086/2007", "1904/2007")["relationship"] == "OFFLINE_ARCHIVE_CITATION"
    assert deeds["1572/2007"]["sro_name"] == "Srirangam" and deeds["1644/2007"]["sro_name"] == "Trichy Joint 1"
    assert deeds["500/1998"]["depth"] == 3 and lin["lineage_depth"] == 3


def test_cited_pr_never_dropped_without_any_geographic_or_party_evidence(tmp_path, monkeypatch):
    # Genuine 3086/2007 has a different claimant name (e.g. developer later conveyed via POA):
    # no signal beyond the documentary citation itself.
    reg = _base_registry(["Sri Balaji Promoters"])
    del reg[(MAN["sro_id"], "3086/2007")]  # single discordant candidate
    _install_fakes(monkeypatch, reg)
    lin = _run(tmp_path)
    d = lin["master_deeds"]["3086/2007"]
    assert d["sro_name"] == "Srirangam"
    assert d["relationship"] == "PARENT_REFERENCE_CITED_ADMIN_SHIFT"
    assert d["verification_status"] == "CITED_PR_GEOGRAPHY_UNCONFIRMED"
    assert any("Administrative boundary shift detected" in r for r in d["reasons"])
    # ... and the PR numbers of 3086/2007 were extracted and traversed
    assert {"1572/2007", "1644/2007", "500/1998"} <= set(lin["master_deeds"])
    edge = _edge(lin, "8396/2022", "3086/2007")
    assert edge["verification_status"] == "CITED_PR_GEOGRAPHY_UNCONFIRMED"


def test_retained_candidate_pdf_and_provenance(tmp_path, monkeypatch):
    reg = _base_registry(["Sri Balaji Promoters"])   # both Tier 3 candidates discordant (tie)
    _install_fakes(monkeypatch, reg)
    lin = _run(tmp_path)
    d = lin["master_deeds"]["3086/2007"]
    # deterministic tie-break = cascade order; the choice is flagged, not hidden
    assert d["verification_status"] == "CITED_PR_GEOGRAPHY_UNCONFIRMED"
    folder = d["folder"]
    with open(os.path.join(folder, "official_encumbrance_certificate.pdf"), "rb") as fh:
        assert d["sro_id"].encode() in fh.read(200)  # canonical PDF == retained candidate's PDF
    prov = json.load(open(os.path.join(folder, "03_lineage_resolution.json"), encoding="utf-8"))
    assert {e["sro_name"] for e in prov["candidate_evaluations"]} == {"Manachanallur", "Srirangam"}
    # rejected candidate PDFs are kept out of Engine B's '*.pdf' baseline glob
    assert not glob.glob(os.path.join(folder, "_sro_candidates", "*.pdf"))
    assert glob.glob(os.path.join(folder, "_sro_candidates", "*.pdf.candidate"))
    baseline_pdfs = glob.glob(os.path.join(str(tmp_path), "deeds", "**", "*.pdf"), recursive=True)
    assert all(os.path.basename(p) == "official_encumbrance_certificate.pdf" for p in baseline_pdfs)


def test_same_sro_benchmark_behaviour_unchanged(tmp_path, monkeypatch):
    """1579/2021 -> 2776/1983 style chain at the same SRO: accepted at Tier 1 exactly as before."""
    S = TJ1
    reg = {
        (S["sro_id"], "1579/2021"): dict(villages=["Ward -AG (K.Abishekapuram)"], surveys=["173/2H"],
                                        ext=_extraction("1579/2021", ["Venkatraman"], ["Balamurugan"],
                                                        ["PR Number/முந்தைய ஆவண எண்:", "2776/1983"], "Ward -AG (K.Abishekapuram)", "173/2H")),
        (S["sro_id"], "2776/1983"): dict(villages=["K-Abishekapuram"], surveys=["173/2"],
                                        ext=_extraction("2776/1983", ["X"], ["Venkatraman"], ["PR Number/முந்தைய ஆவண எண்:", "-"],
                                                        "K-Abishekapuram", "173/2")),
    }
    _install_fakes(monkeypatch, reg)
    lin = _run(tmp_path, root=S, doc="1579", year="2021")
    d = lin["master_deeds"]["2776/1983"]
    assert d["sro_name"] == S["sro_name"]
    assert d["relationship"] == "PARENT_REFERENCE" and d["verification_status"] == "CONCORDANCE_CONFIRMED"
    assert _edge(lin, "1579/2021", "2776/1983")["relationship"] == "PARENT_REFERENCE"


# ---------------------------------------------------------------- triangulation unit tests
def _child(villages, surveys, ext=None):
    return {"doc_id": "C/2022", "sro_name": "X", "portal_data": {"villages": villages, "survey_numbers": surveys},
            "pdf_data": ext or {}}


def test_tokenised_survey_cells_and_ward_label_unwrap():
    child = _child(["WARD -AJ (Piratiyur East)"], ["19,71/2,94/1,95/1"])
    score, reasons = RecursivePREngine._triangulate_concordance(child, {"villages": ["Piratiyur"], "survey_numbers": ["94/1"]})
    assert "Survey Number Root Matches" in reasons and "Revenue Village Matches" in reasons
    assert score == 100.0


def test_tokenised_rule_never_pairs_bare_town_survey_with_rural_subdivision():
    # "5,19": comma-joined cell of bare (Town Survey) numbers. The legacy raw rule does not match
    # "19/2"; the new tokenised rule must not introduce a TS-vs-rural false match either.
    child = _child(["WARD -AJ (Piratiyur East)"], ["5,19"])
    _, reasons = RecursivePREngine._triangulate_concordance(child, {"villages": ["Kambarasampettai"], "survey_numbers": ["19/2"]})
    assert "Survey Number Root Matches" not in reasons


def test_old_survey_in_child_remarks_links_rural_parent():
    ext = _extraction("C/2022", ["A"], ["B"], [], "WARD -AJ (Piratiyur East)", "19",
                      "கம்பரசம்பேட்டை கிராமம் அயன் புஞ்சை சர்வே எண் 131/1B ல் உள்ள மனை")
    child = _child(["WARD -AJ (Piratiyur East)"], ["19"], ext)
    _, reasons = RecursivePREngine._triangulate_concordance(child, {"villages": ["Kambarasampettai"], "survey_numbers": ["131/1B"]})
    assert "Survey Number Root Matches" in reasons


def test_triangulation_never_scores_below_baseline():
    from conftest import load_baseline_module
    import sys
    legacy_mod = load_baseline_module("engines/engine_a/recursive_pr_engine.py", "legacy_rpe")
    legacy = legacy_mod.RecursivePREngine._triangulate_concordance
    villages = [[], ["Kambarasampettai"], ["WARD -AJ (Piratiyur East)"], ["Ward -AG (K.Abishekapuram)"], ["K-Abishekapuram"]]
    surveys = [[], ["131/1B"], ["19,71/2,94/1,95/1"], ["173/2H"], ["173/2"], ["13"], ["94/1"]]
    for cv in villages:
        for cs in surveys:
            for pv in villages:
                for ps in surveys:
                    for same in (False, True):
                        child = _child(cv, cs)
                        cand = {"villages": pv, "survey_numbers": ps}
                        new_score, _ = RecursivePREngine._triangulate_concordance(child, cand, is_same_sro=same)
                        old_score, _ = legacy(child, cand, is_same_sro=same)
                        assert new_score >= old_score, (cv, cs, pv, ps, same)


def _registry_homonym_last(claimants):
    """Genuine 3086/2007 earlier in the cascade (Manachanallur), homonym LAST (Srirangam)."""
    r = _base_registry(claimants)
    gen = r.pop((SRG["sro_id"], "3086/2007"))
    hom = r.pop((MAN["sro_id"], "3086/2007"))
    r[(MAN["sro_id"], "3086/2007")] = gen
    r[(SRG["sro_id"], "3086/2007")] = hom
    r[(MAN["sro_id"], "1572/2007")] = r.pop((SRG["sro_id"], "1572/2007"))
    r[(MAN["sro_id"], "500/1998")] = r.pop((SRG["sro_id"], "500/1998"))
    return r


def test_baseline_reproduces_depth_1_abort(tmp_path, monkeypatch):
    """Verified root cause of the 8396/2022 symptom: the genuine parent is rejected on geography,
    the next sister SRO's homonym overwrites the canonical PDF, the on-disk fallback then adopts
    the homonym's PDF (attributing it to the Tier 1 SRO) and queues the homonym's PRs, so
    1572/2007 / 1644/2007 / 1904/2007 are never traversed."""
    from conftest import load_baseline_module
    legacy = load_baseline_module("engines/engine_a/recursive_pr_engine.py", "legacy_rpe_repro")
    monkeypatch.setitem(_install_fakes.__globals__, "rpe", legacy)
    monkeypatch.setitem(_install_fakes.__globals__, "RecursivePREngine", legacy.RecursivePREngine)
    _install_fakes(monkeypatch, _registry_homonym_last(["Lakshmi Constructions"]))
    lin = legacy.RecursivePREngine.execute_lineage_discovery("8396", "2022", TJ3["sro_id"], TJ3["sro_name"], run_folder=str(tmp_path))
    assert "1572/2007" not in lin["master_deeds"]
    assert lin["master_deeds"]["3086/2007"]["sro_name"] == TJ3["sro_name"]  # mis-attributed


def test_fixed_engine_traverses_when_homonym_is_last_in_cascade(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, _registry_homonym_last(["Lakshmi Constructions"]))
    lin = _run(tmp_path)
    assert lin["master_deeds"]["3086/2007"]["sro_name"] == "Manachanallur"
    assert {"1572/2007", "1644/2007", "500/1998"} <= set(lin["master_deeds"])
    assert [e["to_parent"] for e in lin["lineage_edges"] if e["from_child"] == "3086/2007"] == ["1572/2007", "1644/2007", "1904/2007"]


def test_party_continuity_beats_cascade_order_among_discordant_candidates(tmp_path, monkeypatch):
    # Both candidates geographically discordant; only the genuine one (LAST in cascade) has
    # chain-of-title party continuity -> it must win over the earlier homonym.
    _install_fakes(monkeypatch, _base_registry(["Lakshmi Constructions"]))
    lin = _run(tmp_path)
    assert lin["master_deeds"]["3086/2007"]["sro_name"] == "Srirangam"
