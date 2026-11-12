"""Issue 2: urban Town Survey (TSLR) schedules must be planned as WARD_BLOCK_WISE searches
(ward / block / T.S. No.), never as rural survey searches of the Town Survey number."""
import copy
import pytest

from ec_matrix_planner import ECMatrixPlanner
from tslr_urban_parser import TSLRUrbanParser as T


def _deed(doc_id, sro, schedules):
    no, yr = doc_id.split("/")
    return {"registration_particulars": {"document_number": no, "registration_year": yr, "document_id": doc_id, "sro_name": sro},
            "schedules": schedules}


def _sched(village, survey_raw, remarks="", ward_no="", block_no=""):
    return {"village": village, "survey_number": {"raw": survey_raw}, "schedule_remarks_full": remarks,
            "ward_no": ward_no, "block_no": block_no, "plot_no": "", "flat_no": "", "boundaries": {}}


def _wb_jobs(plan):
    return [j for j in plan["search_jobs"] if j.get("search_mode") == "WARD_BLOCK_WISE"]


def _rural_survey_pairs(plan):
    pairs = set()
    for j in plan["search_jobs"]:
        if j.get("search_mode") == "SURVEY_WISE":
            if j.get("surveys"):
                pairs |= {(str(a), str(b)) for a, b in j["surveys"]}
            if j.get("survey_no"):
                pairs.add((str(j["survey_no"]), str(j.get("subdivision_no") or "")))
    return pairs


# ---------------------------------------------------------------- the 8396/2022 schedule
EXAMPLE_REMARK = "புதிய வார்டு ஏஜே, புதிய பிளாக் 2, புதிய டி.எஸ்.நெ.19 ஆகும்"


@pytest.mark.parametrize("ward_no,block_no", [("", ""), ("AJ", "2"), ("ஏஜே", "2")])
def test_8396_schedule_plans_ward_block_wise_ts_19(ward_no, block_no):
    plan = ECMatrixPlanner.plan_from_deeds([_deed("8396/2022", "Trichy Joint 1",
                                                  [_sched("WARD -AJ (Piratiyur East)", "19,71/2,94/1,95/1", EXAMPLE_REMARK, ward_no, block_no)])])
    wb = _wb_jobs(plan)
    assert wb, "no WARD_BLOCK_WISE job planned"
    first = plan["search_jobs"][0]
    assert (first["search_mode"], first["ward_no"], first["block_no"], first["survey_no"], first["priority"]) == ("WARD_BLOCK_WISE", "AJ", "2", "19", 0)
    # every WARD_BLOCK job uses the Town Survey number - never a rural S.F. number (the old table-field bug used 71/2)
    assert {(j["ward_no"], j["block_no"], j["survey_no"], j["subdivision_no"]) for j in wb} == {("AJ", "2", "19", "")}
    assert ("19", "") not in _rural_survey_pairs(plan)


def test_baseline_planner_mixed_rural_survey_into_tslr_query():
    """Documents a verified defect: with table Ward/Block fields the pre-fix planner built a
    WARD_BLOCK query from the first RURAL survey pair (71/2) of the schedule."""
    from conftest import load_baseline_module
    legacy = load_baseline_module("engines/engine_b/ec_matrix_planner.py", "legacy_planner_tslr").ECMatrixPlanner
    plan = legacy.plan_from_deeds([_deed("8396/2022", "Trichy Joint 1",
                                         [_sched("WARD -AJ (Piratiyur East)", "19,71/2,94/1,95/1", EXAMPLE_REMARK, "AJ", "2")])])
    assert ("AJ", "2", "71") in {(j["ward_no"], j["block_no"], j["survey_no"]) for j in _wb_jobs(plan)}


# ---------------------------------------------------------------- keyword variants
@pytest.mark.parametrize("remark,village,expected", [
    ("Ward No. 12, Block No. 35, T.S.No. 1234/1", "Ward 12 (Thillai Nagar)", ("12", "35", "1234", "1")),
    ("New Ward AJ, New Block 2, New T.S. No 19", "", ("AJ", "2", "19", "")),
    ("TSLR No. 77, Ward C, Block 9", "", ("C", "9", "77", "")),
    ("Town Survey No. 456/2 in Ward 7 Block 3", "", ("7", "3", "456", "2")),
    ("வார்டு எண் 5, பிளாக் எண் 14, டி.எஸ்.எண் 88", "", ("5", "14", "88", "")),
    ("வார்டு ஏ.ஜி, பிளாக் 0014, டி எஸ் எல் ஆர் சர்வே எண் 13", "", ("AG", "0014", "13", "")),
    ("நகர அளவை எண் 45, வார்டு கே, பிளாக் 7", "", ("K", "7", "45", "")),
    ("டவுன் சர்வே எண் 88/2ஏ, வார்டு எம், பிளாக் 4", "", ("M", "4", "88", "2A")),
    ("புதிய வார்டு ஏஜே, புதிய பிளாக் 2, புதிய டி.எஸ்.ெந.19 ஆகும்", "", ("AJ", "2", "19", "")),  # legacy glyph order
])
def test_keyword_variants(remark, village, expected):
    plan = ECMatrixPlanner.plan_from_deeds([_deed("100/2020", "Trichy Joint 1", [_sched(village, "", remark)])])
    first = _wb_jobs(plan)[0]
    assert (first["ward_no"], first["block_no"], first["survey_no"], first["subdivision_no"]) == expected
    assert first["priority"] == 0


def test_explicit_ts_pair_is_removed_from_rural_survey_planning():
    plan = ECMatrixPlanner.plan_from_deeds([_deed("100/2020", "Trichy Joint 1",
                                                  [_sched("Ward 12 (Thillai Nagar)", "1234/1, 56/2", "Ward No. 12, Block No. 35, T.S.No. 1234/1")])])
    rural = _rural_survey_pairs(plan)
    assert ("1234", "1") not in rural and ("56", "2") in rural


def test_old_and_new_tslr_are_separated():
    remark = "பழைய வார்டு எண் 5, பிளாக் 3, டி.எஸ். எண் 10, தற்போது புதிய வார்டு ஏ.ஜே, புதிய பிளாக் எண் 2, புதிய டி.எஸ்.நெ. 19 ஆகும்"
    plan = ECMatrixPlanner.plan_from_deeds([_deed("100/2020", "Trichy Joint 1", [_sched("", "", remark)])])
    p0 = [(j["ward_no"], j["block_no"], j["survey_no"]) for j in _wb_jobs(plan) if j["priority"] == 0]
    p3 = [(j["ward_no"], j["block_no"], j["survey_no"]) for j in _wb_jobs(plan) if j["priority"] == 3]
    assert p0 == [("AJ", "2", "19")]
    assert ("5", "3", "10") in p3


def test_ambiguous_tamil_ward_letter_plans_alternate():
    plan = ECMatrixPlanner.plan_from_deeds([_deed("100/2020", "Trichy Joint 1", [_sched("", "", "வார்டு பி, பிளாக் 7, டி.எஸ்.நெ. 45")])])
    p0 = {j["ward_no"] for j in _wb_jobs(plan) if j["priority"] == 0}
    p3 = {j["ward_no"] for j in _wb_jobs(plan) if j["priority"] == 3}
    assert p0 == {"B"} and "P" in p3


def test_latin_village_label_resolves_ambiguity():
    plan = ECMatrixPlanner.plan_from_deeds([_deed("100/2020", "Trichy Joint 1", [_sched("WARD -P (Puthur)", "", "வார்டு பி, பிளாக் 7, டி.எஸ்.நெ. 45")])])
    assert {j["ward_no"] for j in _wb_jobs(plan)} == {"P"}


# ---------------------------------------------------------------- negatives / rural parity
@pytest.mark.parametrize("remark", [
    "டி.எஸ்.ராமன் அவர்களுக்கு சொந்தமான மனை",                # Tamil initials T.S. - not a Town Survey
    "T.S. Raman son of Subramanian",
    "Plot No 26 in S.F.No. 173/2H Kambarasampettai village",
    "அயன் புஞ்சை சர்வே எண் 131/1B ல் மனை எண் 5",
])
def test_rural_or_non_tslr_text_is_not_urban(remark):
    assert not T.parse_text(remark)["is_urban_tslr"]
    plan = ECMatrixPlanner.plan_from_deeds([_deed("100/2020", "Srirangam", [_sched("Kambarasampettai", "131/1B", remark)])])
    assert not _wb_jobs(plan)
    assert ("131", "1B") in _rural_survey_pairs(plan)


def _core(job):
    keys = ("priority", "track", "sro_name", "village_name", "search_mode", "ward_no", "block_no",
            "survey_no", "subdivision_no", "date_start", "date_end", "surveys")
    core = {k: (list(map(tuple, job[k])) if k == "surveys" and job.get(k) else job.get(k)) for k in keys}
    core["job_kind"] = job["job_id"].split("_", 2)[2]  # drop the JOB_NN_ sequence prefix
    return core


def _has_tamil(s):
    import re
    return bool(re.search(r"[\u0B80-\u0BFF]", s or ""))


def test_benchmark_plans_preserved_vs_baseline(benchmark_extractions):
    """1579/2021 (+2776/1983, 1583/2021, 83/2024), 208/2005, 2367/2010, 1590/2021, 235/2021:
    - every rural / master survey job of the pre-fix planner is produced identically, in order;
    - every pre-fix WARD_BLOCK job is still produced (Tamil ward codes now transliterated)."""
    from conftest import load_baseline_module
    legacy = load_baseline_module("engines/engine_b/ec_matrix_planner.py", "legacy_planner_bench").ECMatrixPlanner
    entries = []
    for ext in benchmark_extractions.values():
        for e in ext.get("entries", []):
            e = copy.deepcopy(e)
            e.setdefault("document_metadata", ext.get("document_metadata", {}))
            entries.append(e)
    groups = [entries] + [[e] for e in entries]
    groups.append([e for e in entries if e["registration_particulars"]["document_id"] in ("1579/2021", "2776/1983", "1583/2021", "83/2024")])
    for g in groups:
        ids = [e["registration_particulars"]["document_id"] for e in g]
        new_jobs = ECMatrixPlanner.plan_from_deeds(copy.deepcopy(g))["search_jobs"]
        old_jobs = legacy.plan_from_deeds(copy.deepcopy(g))["search_jobs"]
        assert [_core(j) for j in new_jobs if j["search_mode"] != "WARD_BLOCK_WISE"] == \
               [_core(j) for j in old_jobs if j["search_mode"] != "WARD_BLOCK_WISE"], ids
        new_wb = {(j["ward_no"], j["block_no"], j["survey_no"], j["subdivision_no"], j["priority"]) for j in new_jobs if j["search_mode"] == "WARD_BLOCK_WISE"}
        for j in old_jobs:
            if j["search_mode"] != "WARD_BLOCK_WISE":
                continue
            ward = j["ward_no"]
            if _has_tamil(ward):
                ward = T.normalize_ward_code(ward)[0]
            assert (ward, j["block_no"], j["survey_no"], j["subdivision_no"], j["priority"]) in new_wb, (ids, j["job_id"])
        assert not any(_has_tamil(w) for w, *_ in new_wb), ids


def test_1590_benchmark_tamil_ward_code_transliterated(benchmark_extractions):
    """Real benchmark text: 'மாநகராட்சி பதிவேட்டின் படி புதிய வார்டு ஏஎல், புதிய பிளாக் 3,
    புதிய டி.எஸ்.நெ.28/1 ஆகும். வழிகாட்டி பதிவேட்டின் படி புதிய வார்டு ஏகே'. The pre-fix
    planner sent wardNo='ஏஎல்' to TNREGINET (0 records)."""
    from conftest import load_baseline_module
    legacy = load_baseline_module("engines/engine_b/ec_matrix_planner.py", "legacy_planner_1590").ECMatrixPlanner
    ents = copy.deepcopy(benchmark_extractions["document_1590_2021.pdf"]["entries"])
    old_wb = _wb_jobs(legacy.plan_from_deeds(copy.deepcopy(ents)))
    assert any(j["ward_no"] == "ஏஎல்" for j in old_wb)
    new_wb = _wb_jobs(ECMatrixPlanner.plan_from_deeds(ents))
    got = {(j["ward_no"], j["block_no"], j["survey_no"], j["subdivision_no"], j["priority"]) for j in new_wb}
    assert {("AK", "3", "28", "1", 0), ("AL", "3", "28", "1", 0)} <= got


def test_1579_benchmark_tslr_job_present():
    import json, os
    from conftest import ROOT
    ext = json.load(open(os.path.join(ROOT, "data", "batch_audit_results.json"), encoding="utf-8"))["document_1579_2021.pdf"]
    plan = ECMatrixPlanner.plan_from_deeds(copy.deepcopy(ext["entries"]))
    first = plan["search_jobs"][0]
    assert (first["search_mode"], first["ward_no"], first["block_no"], first["survey_no"]) == ("WARD_BLOCK_WISE", "AG", "0014", "13")
