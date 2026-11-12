"""
ec_matrix_planner.py - Search Envelope & Multi-SRO Matrix Planner for EC Engine
===============================================================================
Interconnects the findings of Engine A (PR Lineage & Target Deeds) to construct
an exhaustive, multi-tier search matrix for the TNREGINET Encumbrance Certificate engine.

Key Responsibilities:
1. Harvests all historical SROs, village variants, primary surveys, parent surveys,
   layout survey lists, and TSLR (Ward/Block) particulars across the PR deed chain.
2. Determines the jurisdictional timeline and applies safety buffer overlaps (±1 year)
   across SRO bifurcation points.
3. Classifies search tracks:
   - Track 1: Primary Plot Survey Wise (1975 to Present).
   - Track 2: Parent Survey / Pre-Subdivision (1975 to Year of Subdivision).
   - Track 3: Urban Ward / Block / TSLR (Municipal Era to Present).
   - Track 4: Auxiliary Layout Surveys (Pre-Layout Era).
4. Emits an execution plan of discrete, prioritized SearchJob objects.
"""

import os
import sys
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

from tslr_urban_parser import TSLRUrbanParser


class SearchTrack:
    PRIMARY_SURVEY = "PRIMARY_SURVEY"
    PARENT_SURVEY = "PARENT_SURVEY"
    URBAN_TSLR = "URBAN_TSLR"
    LAYOUT_AUXILIARY = "LAYOUT_AUXILIARY"
    PLOT_SUPPLEMENTARY = "PLOT_SUPPLEMENTARY"


class ECMatrixPlanner:
    """Plans and constructs the complete EC search envelope from PR lineage data."""

    SYSTEM_START_DATE = "01-Jan-1975"

    @classmethod
    def plan_from_engine_a_run(cls, run_dir: str) -> Dict[str, Any]:
        """
        Reads an Engine A run directory (containing target deed and all PR deed folders)
        and builds the comprehensive Search Matrix.
        """
        deeds_dir = os.path.join(run_dir, "deeds")
        if not os.path.exists(deeds_dir):
            deeds_dir = run_dir  # Fallback to direct directory

        extracted_deeds = []
        for root, dirs, files in os.walk(run_dir):
            if "ec_engine_full_trace" in root:
                continue
            for f in files:
                if f == "02_pdf_detailed_extraction.json":
                    p = os.path.join(root, f)
                    try:
                        with open(p, "r", encoding="utf-8") as fp:
                            data = json.load(fp)
                            if data.get("success") and data.get("entries"):
                                doc_meta = data.get("document_metadata", {})
                                for entry in data["entries"]:
                                    if "document_metadata" not in entry:
                                        entry["document_metadata"] = doc_meta
                                    extracted_deeds.append(entry)
                    except Exception as e:
                        print(f"[!] Warning: failed reading {p}: {e}")

        # If portal summaries exist without PDF extraction, load those too
        for root, dirs, files in os.walk(run_dir):
            if "ec_engine_full_trace" in root:
                continue
            for f in files:
                if f == "01_portal_summary.json":
                    p = os.path.join(root, f)
                    try:
                        with open(p, "r", encoding="utf-8") as fp:
                            data = json.load(fp)
                            # Check if already covered
                            doc_id = data.get("document_id")
                            if doc_id and not any(d.get("registration_particulars", {}).get("document_id") == doc_id for d in extracted_deeds):
                                # Wrap into minimal entry
                                minimal_entry = {
                                    "registration_particulars": {
                                        "document_number": data.get("document_number"),
                                        "registration_year": data.get("registration_year"),
                                        "document_id": doc_id,
                                        "sro_name": data.get("sro_name"),
                                        "dates": {"registration_date": data.get("registration_date")}
                                    },
                                    "schedules": data.get("schedules", [])
                                }
                                extracted_deeds.append(minimal_entry)
                    except Exception as e:
                        print(f"[!] Warning: failed reading {p}: {e}")

        # If master_dossier.json exists in run_dir, extract comprehensive property envelope as fallback
        if not extracted_deeds:
            master_dossier_path = os.path.join(run_dir, "master_dossier.json")
            if os.path.exists(master_dossier_path):
                try:
                    with open(master_dossier_path, "r", encoding="utf-8") as fp:
                        md = json.load(fp)
                    
                    sro = md.get("metadata", {}).get("sro_name", "")
                    if not sro and md.get("sro_lineage"):
                        sro = md["sro_lineage"][0].get("sro_name", "")

                    doc_no = md.get("metadata", {}).get("doc_no", "")
                    doc_yr = md.get("metadata", {}).get("doc_year", "")

                    cf = md.get("cadastral_family", {})
                    surveys = cf.get("search_surveys", [])
                    if not surveys:
                        target_id = cf.get("target_primary_identifier", "")
                        if target_id:
                            surveys.append(target_id)
                        if cf.get("parent_sf"):
                            surveys.append(cf.get("parent_sf"))

                    villages = []
                    md_text = json.dumps(md)
                    if "Ward -AG" in md_text or "Ward AG" in md_text or "Abishekapuram" in md_text:
                        villages.append("Ward -AG (K.Abishekapuram)")
                    if "Piratiyur" in md_text:
                        villages.append("Piratiyur")

                    schedules = []
                    for s_item in surveys:
                        for s_no, sub_no in cls.parse_survey_subdivision_string(s_item):
                            if not sub_no:
                                continue
                            for v in (villages or [""]):
                                schedules.append({
                                    "village": v,
                                    "survey_number": {
                                        "raw": s_item,
                                        "survey": s_no,
                                        "subdivision": sub_no
                                    },
                                    "ward_no": cf.get("ward", ""),
                                    "block_no": cf.get("block", ""),
                                    "plot_no": md.get("primary_deed", {}).get("plot_no", "")
                                })

                    if schedules or sro:
                        extracted_deeds.append({
                            "registration_particulars": {
                                "document_number": doc_no,
                                "registration_year": doc_yr,
                                "document_id": f"{doc_no}/{doc_yr}",
                                "sro_name": sro
                            },
                            "schedules": schedules
                        })
                except Exception as e:
                    print(f"[!] Warning reading master_dossier.json: {e}")

        return cls.plan_from_deeds(extracted_deeds)

    TAMIL_SUBDIVISION_LETTER_MAP = {
        'ஹெச்': 'H', 'எச்': 'H', 'எப்': 'F', 'ஜி': 'G', 'ஜே': 'J', 'கே': 'K',
        'எல்': 'L', 'எம்': 'M', 'என்': 'N', 'க்யூ': 'Q', 'ஆர்': 'R', 'எஸ்': 'S',
        'டபிள்யூ': 'W', 'எக்ஸ்': 'X', 'இசட்': 'Z', 'இஸட்': 'Z', 'ஒய்': 'Y',
        'ஏ': 'A', 'பி': 'B', 'சி': 'C', 'டி': 'D', 'இ': 'E', 'ஐ': 'I',
        'ஓ': 'O', 'யு': 'U', 'வி': 'V',
    }

    @classmethod
    def replace_tamil_subdivision_letters(cls, text: str) -> str:
        """Translates Tamil deed subdivision characters to English (e.g. எச் -> H, ஏ -> A, பி -> B)."""
        if not text:
            return ""
        s = str(text)
        sorted_keys = sorted(cls.TAMIL_SUBDIVISION_LETTER_MAP.keys(), key=len, reverse=True)
        letter_alt = '|'.join(re.escape(k) for k in sorted_keys)
        
        # Match letters following digit, slash, hyphen, or whitespace
        pattern = rf'([0-9]+[\/\-]?[0-9]*\s*[\/\-]?\s*)({letter_alt})(?![a-zA-Z0-9\u0B80-\u0BFF])'
        s = re.sub(pattern, lambda m: m.group(1) + cls.TAMIL_SUBDIVISION_LETTER_MAP.get(m.group(2), m.group(2)), s)
        
        pattern2 = rf'([0-9])({letter_alt})(?![a-zA-Z0-9\u0B80-\u0BFF])'
        s = re.sub(pattern2, lambda m: m.group(1) + cls.TAMIL_SUBDIVISION_LETTER_MAP.get(m.group(2), m.group(2)), s)
        return s

    @classmethod
    def parse_survey_subdivision_string(cls, text: Any) -> List[Tuple[str, str]]:
        """
        Parses survey strings accurately from deed schedules and boundaries:
          173/2H -> survey_no="173", subdivision_no="2H"
          173/2எச் -> survey_no="173", subdivision_no="2H"
          173/2ஏ -> survey_no="173", subdivision_no="2A"
          173/2 -> survey_no="173", subdivision_no="2"
          173/2 part or 173/2 பகுதி -> survey_no="173", subdivision_no="2"
          173-2H or 173 - 2H -> survey_no="173", subdivision_no="2H"
          173/2-H -> survey_no="173", subdivision_no="2H"
        DO NOT extract bare numbers as surveys if they are accompanied by a subdivision.
        """
        if not text:
            return []
        s_clean = str(text).strip()
        s_clean = re.sub(r'[\(\)\[\]]', ' ', s_clean)
        s_clean = re.sub(r'\b(?:part|portion|share)\b', '', s_clean, flags=re.I)
        
        # Translate Tamil subdivision letters (Tier 2 Normalization)
        s_clean = cls.replace_tamil_subdivision_letters(s_clean)
        
        results = []
        # 1. Match explicit 'subdivision / உட்பிரிவு' patterns: e.g. 173 உட்பிரிவு 2H
        for m in re.finditer(r'\b([0-9]+)\s*(?:உட்பிரிவு|sub\s*division|sub|பிரிவு)\s*([0-9]+(?:\s*[A-Za-z0-9]+)*)\b', s_clean, re.I):
            s_no = m.group(1).strip()
            sub_raw = m.group(2).strip()
            sub_no = re.sub(r'[\s\/\-]+', '', sub_raw).upper()
            if s_no and sub_no:
                results.append((s_no, sub_no))

        # Strip noise words for standard slash/dash matching
        s_clean_std = re.sub(r'(?:பகுதி|மற்றும்|பங்கு|உட்பிரிவு|பிரிவு|புல\s*எண்|சர்வே\s*எண்)', ' ', s_clean)

        # 2. Match standard slash/dash patterns: e.g. 173/2H, 173/2 A, 173-2H
        for m in re.finditer(r'\b([0-9]+)\s*[\/\-]\s*([0-9]+(?:\s*[\/\-]?\s*[A-Za-z0-9]+)*)\b', s_clean_std):
            s_no = m.group(1).strip()
            sub_raw = m.group(2).strip()
            sub_no = re.sub(r'[\s\/\-]+', '', sub_raw).upper()
            if s_no and sub_no and (s_no, sub_no) not in results:
                results.append((s_no, sub_no))
        return results

    @classmethod
    def plan_from_deeds(cls, deeds: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Core matrix planning algorithm from a list of structured deed entries.
        """
        current_year = datetime.now().year
        current_date_str = datetime.now().strftime("%d-%b-%Y")

        # 1. Harvest & sort timeline
        timeline = []
        for d in deeds:
            reg_info = d.get("registration_particulars", {})
            yr_str = str(reg_info.get("registration_year", ""))
            try:
                yr = int(yr_str)
            except ValueError:
                yr = current_year
            sro = (
                reg_info.get("sro_name") 
                or d.get("document_metadata", {}).get("sro_name")
                or d.get("sro_name") 
                or ""
            )
            timeline.append({
                "year": yr,
                "document_id": reg_info.get("document_id", ""),
                "sro_name": sro,
                "entry": d
            })

        # If any deed in timeline is missing sro_name, inherit from closest known SRO in chain
        known_sros = [item["sro_name"] for item in timeline if item.get("sro_name")]
        fallback_sro = known_sros[-1] if known_sros else ""
        for item in timeline:
            if not item.get("sro_name"):
                item["sro_name"] = fallback_sro

        timeline.sort(key=lambda x: x["year"])

        # 2. Extract unique parameters across all deeds
        sros_by_era = []
        villages = set()
        primary_surveys = set()
        parent_surveys = set()
        layout_surveys = set()
        tslr_entries = []
        plot_numbers = set()
        flat_numbers = set()
        earliest_subdivision_year = current_year
        earliest_layout_year = current_year

        def clean_village_name(v_raw: str) -> str:
            if not v_raw:
                return ""
            v = v_raw.strip()
            v = re.sub(r'^(?:&?\s*Street\s*\/|\bVillage\s*\/|\bVillage\b|\bகிராமம்\b|\bஊர்\b)[\s\:\.\-]*', '', v, flags=re.I)
            v = re.sub(r'[\r\n\t]+', ' ', v).strip()
            m_cut = re.search(r'(.*?)(?:Survey\s*No|Door\s*No|Plot\s*No|Ward\s*No|Extent)', v, flags=re.I)
            if m_cut and m_cut.group(1).strip():
                v = m_cut.group(1).strip()
            v = v.strip(" ,.:-&")
            return v

        max_timeline_yr = max(item["year"] for item in timeline) if timeline else current_year

        for item in timeline:
            d = item["entry"]
            yr = item["year"]
            sro = item["sro_name"]
            is_root_deed = (yr == max_timeline_yr)
            
            if sro and not any(s["sro_name"] == sro for s in sros_by_era):
                sros_by_era.append({"sro_name": sro, "first_seen_year": yr, "last_seen_year": yr})
            else:
                for s in sros_by_era:
                    if s["sro_name"] == sro:
                        s["last_seen_year"] = max(s["last_seen_year"], yr)

            sched_list = d.get("schedules", [])
            for sched in sched_list:
                # 1. Harvest Village
                v_raw = sched.get("village", "").strip()
                v_clean = clean_village_name(v_raw)
                if v_clean:
                    villages.add(v_clean)

                # Check schedule remarks / boundaries for additional village references
                rem_txt = str(sched.get("schedule_remarks_full", "")) + " " + json.dumps(sched.get("boundaries", {}))
                for v_m in re.finditer(r'(?:கிராமம்|Village|வட்டம்|Taluk)[\s\:\-]+([A-Za-z0-9\-\.\s\(\)]+)', rem_txt, re.I):
                    v_found = clean_village_name(v_m.group(1).strip())
                    if len(v_found) >= 4 and not any(kw in v_found.lower() for kw in ['road', 'street', 'salai', 'lane', 'plot']):
                        villages.add(v_found)

                # 1b. Urban TSLR classification (deterministic). Done BEFORE survey harvesting so an
                # explicitly declared Town Survey number is never planned as a rural S.F. number.
                tslr_info = TSLRUrbanParser.parse_schedule(sched)
                explicit_ts_pairs = set()
                if tslr_info.get("explicit_ts_keyword"):
                    explicit_ts_pairs = {(str(a), str(b).upper()) for a, b in tslr_info.get("ts_pairs", []) if b}

                # 2. Harvest Survey & Subdivision (Strict Clean Splitting)
                deed_surveys = []
                sur_obj = sched.get("survey_number", {})
                # If sur_obj is a dict, reconstruct full raw text and parse thoroughly
                if isinstance(sur_obj, dict):
                    raw_text = sur_obj.get("raw") or f"{sur_obj.get('survey', '')}/{sur_obj.get('subdivision', '')}"
                    deed_surveys.extend(cls.parse_survey_subdivision_string(raw_text))
                elif isinstance(sur_obj, str) and sur_obj.strip():
                    deed_surveys.extend(cls.parse_survey_subdivision_string(sur_obj))
                # Also check schedule raw fields
                if sched.get("survey_subdivision_raw"):
                    deed_surveys.extend(cls.parse_survey_subdivision_string(sched["survey_subdivision_raw"]))
                # Town Survey (TSLR) pairs are municipal identifiers, not rural survey fields.
                if explicit_ts_pairs:
                    deed_surveys = [(a, b) for a, b in deed_surveys if (str(a).strip(), str(b).strip().upper()) not in explicit_ts_pairs]
                # Deduplicate clean (survey, subdivision) pairs
                for s_no, sub_no in deed_surveys:
                    s_no = str(s_no).strip()
                    sub_no = str(sub_no).strip()
                    if not s_no or not sub_no:
                        continue
                    # If subdivision still contains a comma or slash (e.g. malformed), re-split
                    if "," in sub_no or "/" in sub_no:
                        sub_pairs = cls.parse_survey_subdivision_string(f"{s_no}/{sub_no}")
                        for sp_s, sp_sub in sub_pairs:
                            if not sp_s or not sp_sub:
                                continue
                            if is_root_deed:
                                primary_surveys.add((sp_s, sp_sub))
                                earliest_subdivision_year = min(earliest_subdivision_year, yr)
                            else:
                                parent_surveys.add((sp_s, sp_sub))
                    else:
                        if is_root_deed:
                            primary_surveys.add((s_no, sub_no))
                            earliest_subdivision_year = min(earliest_subdivision_year, yr)
                        else:
                            parent_surveys.add((s_no, sub_no))

                # Plot & Flat
                p_no = sched.get("plot_no", "").strip()
                if p_no:
                    plot_numbers.add(p_no)
                fl_no = sched.get("flat_no", "").strip()
                if fl_no:
                    flat_numbers.add(fl_no)

                # TSLR (Ward / Block / Town Survey) - deterministic urban identity
                def _add_tslr(entry: Dict[str, Any]):
                    key = (entry.get("ward", ""), entry.get("block", ""), entry.get("survey_or_ts", ""), entry.get("subdiv", ""))
                    if not any((t.get("ward", ""), t.get("block", ""), t.get("survey_or_ts", ""), t.get("subdiv", "")) == key for t in tslr_entries):
                        tslr_entries.append(entry)

                if tslr_info.get("entries"):
                    for t_ent in tslr_info["entries"]:
                        t_new = dict(t_ent)
                        t_new["year"] = yr
                        t_new["document_id"] = item.get("document_id", "")
                        _add_tslr(t_new)
                else:
                    # Legacy behaviour (kept for parity) when NO Town Survey number is stated anywhere:
                    # table Ward/Block fields without a TS number fall back to the first schedule survey.
                    ward_raw = sched.get("ward_no", "").strip()
                    block_raw = sched.get("block_no", "").strip()
                    if ward_raw or block_raw:
                        w_code, _ = TSLRUrbanParser.normalize_ward_code(ward_raw)
                        b_code = TSLRUrbanParser.normalize_block_code(block_raw)
                        ward = w_code or ward_raw
                        block = b_code or block_raw
                        if not any(t["ward"] == ward and t["block"] == block for t in tslr_entries):
                            tslr_entries.append({
                                "ward": ward,
                                "block": block,
                                "survey_or_ts": deed_surveys[0][0] if deed_surveys else "",
                                "subdiv": deed_surveys[0][1] if deed_surveys else "",
                                "year": yr,
                                "era": "CURRENT",
                                "ts_source": "LEGACY_FIRST_SCHEDULE_SURVEY_UNVERIFIED",
                                "document_id": item.get("document_id", "")
                            })
                    # Ward + Block declared but no TS number: record the urban identity (no job is
                    # emitted by Track 0 without a TS number; Track 3 keeps legacy behaviour).
                    if tslr_info.get("ward_detected") and tslr_info.get("block"):
                        w_guess = TSLRUrbanParser.ward_from_village(sched.get("village", ""))
                        if not w_guess:
                            w_guess = TSLRUrbanParser.parse_text(sched.get("schedule_remarks_full", ""))["current"]["ward"]
                        if w_guess:
                            _add_tslr({
                                "ward": w_guess, "block": tslr_info["block"], "survey_or_ts": "", "subdiv": "",
                                "year": yr, "era": "CURRENT", "ts_source": "",
                                "document_id": item.get("document_id", "")
                            })

                # Schedule Remarks Deep Mining for Layout Surveys
                remarks = sched.get("schedule_remarks_full", "")
                if remarks or sched.get("village", ""):
                    # Look for Layout formation surveys (only keep if subdivision present)
                    layout_m = re.search(r'(?:மனை\s*பிரிவு|layout|நகர்)[\s\S]{0,100}?(?:புல\s*எண்கள்?|சர்வே\s*எண்கள்?|Survey\s*Nos?\.?)[\s\:\-]*([0-9\,\s\/\.\-மற்றும்and]+)', remarks, re.I)
                    if layout_m:
                        earliest_layout_year = min(earliest_layout_year, yr)
                        raw_s_list = layout_m.group(1)
                        for ls_s, ls_sub in cls.parse_survey_subdivision_string(raw_s_list):
                            layout_surveys.add((ls_s, ls_sub))

        # 3. Construct the Search Jobs
        search_jobs = []
        job_seq = 1

        # Prioritize ward-specific / urban village name if present in schedules
        ward_villages = [v for v in villages if "ward" in v.lower()]
        primary_village = ward_villages[0] if ward_villages else (sorted(list(villages))[-1] if villages else "")

        # --- TRACK 0: URBAN WARD / BLOCK / TSLR SEARCH (Priority 0) ---
        # When an urban ward and Town Survey (TS) number are detected, prioritize municipal search
        if tslr_entries:
            for t_entry in tslr_entries:
                if t_entry.get("era", "CURRENT") != "CURRENT":
                    continue  # historical (old) TS numbers and ambiguous ward readings -> Track 3
                ward = t_entry.get("ward", "").strip()
                block = t_entry.get("block", "").strip()
                ts_no = t_entry.get("survey_or_ts", "").strip()
                ts_sub = t_entry.get("subdiv", "").strip()

                if ward and ts_no:
                    current_sro = sros_by_era[-1]["sro_name"] if sros_by_era else ""
                    search_jobs.append({
                        "job_id": f"JOB_{job_seq:02d}_TSLR_W{ward}_B{block}_TS{ts_no}",
                        "priority": 0,
                        "track": SearchTrack.URBAN_TSLR,
                        "sro_name": current_sro,
                        "village_name": primary_village,
                        "village_type": "REGISTRATION",
                        "search_mode": "WARD_BLOCK_WISE",
                        "ward_no": ward,
                        "block_no": block,
                        "survey_no": ts_no,
                        "subdivision_no": ts_sub,
                        "date_start": cls.SYSTEM_START_DATE,
                        "date_end": current_date_str,
                        "ts_source": t_entry.get("ts_source", ""),
                        "ward_source": t_entry.get("ward_source", ""),
                        "rationale": f"Municipal Corporation Town Survey (TSLR) search across Ward {ward}, Block {block}, T.S. {ts_no} ({cls.SYSTEM_START_DATE} to {current_date_str})."
                    })
                    job_seq += 1

        # --- MASTER TRACK 0: COMPREHENSIVE MULTI-VILLAGE SRO BATCH ---
        # SRO-first grouping, all deed villages matched & expanded,
        # batched in groups of up to 3 villages, populated strictly with deed-reflected survey pairs.
        primary_clean_surveys = sorted([(s, sub) for s, sub in primary_surveys if sub])
        parent_clean_surveys = sorted([(s, sub) for s, sub in parent_surveys if sub and (s, sub) not in primary_surveys])

        for sro_info in (sros_by_era if sros_by_era else [{"sro_name": "", "first_seen_year": 1975, "last_seen_year": current_year}]):
            sro_name = sro_info["sro_name"]
            
            # Primary Plot Parcels (1975 to Present)
            if primary_clean_surveys:
                search_jobs.append({
                    "job_id": f"JOB_{job_seq:02d}_MASTER_SRO_PRIMARY_{sro_name.replace(' ', '_')}",
                    "priority": 0,
                    "track": "MASTER_SRO_BATCH",
                    "sro_name": sro_name,
                    "deed_villages": list(villages),
                    "surveys": primary_clean_surveys,
                    "date_start": cls.SYSTEM_START_DATE,
                    "date_end": current_date_str,
                    "search_mode": "SURVEY_WISE",
                    "rationale": f"Comprehensive multi-village primary plot survey search in {sro_name} ({cls.SYSTEM_START_DATE} to {current_date_str})."
                })
                job_seq += 1

            # Parent Lineage Parcels (1975 to Pre-subdivision cutoff date)
            if parent_clean_surveys:
                parent_years = [item["year"] for item in timeline if item["year"] < max_timeline_yr]
                parent_cutoff_year = max(parent_years) if parent_years else 1983
                parent_end_date = f"31-Dec-{parent_cutoff_year}"
                search_jobs.append({
                    "job_id": f"JOB_{job_seq:02d}_MASTER_SRO_PARENT_{sro_name.replace(' ', '_')}",
                    "priority": 0,
                    "track": "MASTER_SRO_BATCH",
                    "sro_name": sro_name,
                    "deed_villages": list(villages),
                    "surveys": parent_clean_surveys,
                    "date_start": cls.SYSTEM_START_DATE,
                    "date_end": parent_end_date,
                    "search_mode": "SURVEY_WISE",
                    "rationale": f"Comprehensive multi-village parent lineage survey search in {sro_name} before subdivision ({cls.SYSTEM_START_DATE} to {parent_end_date})."
                })
                job_seq += 1

        # --- TRACK 1: PRIMARY PLOT SURVEY (1975 to Present) ---
        for s_no, sub_no in sorted(primary_surveys):
            if not sub_no:
                continue
            # For each SRO in history
            for sro_info in (sros_by_era if sros_by_era else [{"sro_name": "", "first_seen_year": 1975, "last_seen_year": current_year}]):
                sro_name = sro_info["sro_name"]
                
                # Determine date window for this SRO with ±1 year buffer
                if len(sros_by_era) <= 1:
                    dt_start = cls.SYSTEM_START_DATE
                    dt_end = current_date_str
                else:
                    # Earlier SRO gets 1975 up to transition + 1
                    # Later SRO gets transition - 1 up to today
                    is_earliest = (sro_info["first_seen_year"] == min(s["first_seen_year"] for s in sros_by_era))
                    is_latest = (sro_info["last_seen_year"] == max(s["last_seen_year"] for s in sros_by_era))
                    
                    if is_earliest:
                        dt_start = cls.SYSTEM_START_DATE
                        dt_end = f"31-Dec-{sro_info['last_seen_year'] + 1}"
                    elif is_latest:
                        dt_start = f"01-Jan-{sro_info['first_seen_year'] - 1}"
                        dt_end = current_date_str
                    else:
                        dt_start = f"01-Jan-{sro_info['first_seen_year'] - 1}"
                        dt_end = f"31-Dec-{sro_info['last_seen_year'] + 1}"

                search_jobs.append({
                    "job_id": f"JOB_{job_seq:02d}_PRIMARY_SF_{s_no}_{sub_no}",
                    "priority": 1,
                    "track": SearchTrack.PRIMARY_SURVEY,
                    "sro_name": sro_name,
                    "village_name": primary_village,
                    "village_type": "REGISTRATION",
                    "search_mode": "SURVEY_WISE",
                    "survey_no": s_no,
                    "subdivision_no": sub_no,
                    "date_start": dt_start,
                    "date_end": dt_end,
                    "rationale": f"Primary plot parcel trace on Survey {s_no}/{sub_no} covering active jurisdiction ({dt_start} to {dt_end})."
                })
                job_seq += 1

        # --- TRACK 2: PARENT SURVEY PRE-SUBDIVISION (1975 to Earliest Subdivision Year) ---
        subdiv_cutoff_year = min(earliest_subdivision_year, current_year)
        if subdiv_cutoff_year > 1975:
            cutoff_date_str = f"31-Dec-{subdiv_cutoff_year}"
            for ps_no, psub_no in sorted(parent_surveys):
                if not psub_no:
                    continue
                # Search primarily in the Mother / Earliest SRO
                mother_sro = sros_by_era[0]["sro_name"] if sros_by_era else ""
                search_jobs.append({
                    "job_id": f"JOB_{job_seq:02d}_PARENT_SF_{ps_no}_{psub_no or 'ALL'}",
                    "priority": 2,
                    "track": SearchTrack.PARENT_SURVEY,
                    "sro_name": mother_sro,
                    "village_name": primary_village,
                    "village_type": "REGISTRATION",
                    "search_mode": "SURVEY_WISE",
                    "survey_no": ps_no,
                    "subdivision_no": psub_no,
                    "date_start": cls.SYSTEM_START_DATE,
                    "date_end": cutoff_date_str,
                    "rationale": f"Parent land verification on Survey {ps_no}/{psub_no or '*'} before subdivision ({cls.SYSTEM_START_DATE} to {cutoff_date_str})."
                })
                job_seq += 1

        # --- TRACK 3: URBAN WARD / BLOCK / TSLR (if municipal conversion detected) ---
        if tslr_entries:
            for t_entry in tslr_entries:
                ward = t_entry.get("ward", "")
                block = t_entry.get("block", "")
                ts_no = t_entry.get("survey_or_ts", "")
                ts_sub = t_entry.get("subdiv", "")
                ts_yr = t_entry.get("year", 2000)

                if any(j.get("search_mode") == "WARD_BLOCK_WISE" and j.get("ward_no") == ward and j.get("survey_no") == ts_no for j in search_jobs):
                    continue

                ts_start_date = f"01-Jan-{max(1975, ts_yr - 5)}"
                current_sro = sros_by_era[-1]["sro_name"] if sros_by_era else ""

                search_jobs.append({
                    "job_id": f"JOB_{job_seq:02d}_TSLR_W{ward}_B{block}_TS{ts_no}",
                    "priority": 3,
                    "track": SearchTrack.URBAN_TSLR,
                    "sro_name": current_sro,
                    "village_name": primary_village,
                    "village_type": "REGISTRATION",
                    "search_mode": "WARD_BLOCK_WISE",
                    "ward_no": ward,
                    "block_no": block,
                    "survey_no": ts_no,
                    "subdivision_no": ts_sub,
                    "date_start": ts_start_date,
                    "date_end": current_date_str,
                    "era": t_entry.get("era", "CURRENT"),
                    "ts_source": t_entry.get("ts_source", ""),
                    "ward_source": t_entry.get("ward_source", ""),
                    "rationale": f"Municipal Corporation Town Survey (TSLR) search across Ward {ward}, Block {block}, T.S. {ts_no}/{ts_sub} ({ts_start_date} to {current_date_str})."
                })
                job_seq += 1

        # --- TRACK 4: AUXILIARY LAYOUT SURVEYS (Pre-layout era) ---
        if layout_surveys and earliest_layout_year > 1975:
            layout_end_date = f"31-Dec-{earliest_layout_year}"
            mother_sro = sros_by_era[0]["sro_name"] if sros_by_era else ""
            for ls_no, lsub_no in sorted(layout_surveys):
                # Only search auxiliary surveys that are not already in primary
                if not any(p[0] == ls_no for p in primary_surveys):
                    search_jobs.append({
                        "job_id": f"JOB_{job_seq:02d}_LAYOUT_AUX_{ls_no}_{lsub_no or 'ALL'}",
                        "priority": 4,
                        "track": SearchTrack.LAYOUT_AUXILIARY,
                        "sro_name": mother_sro,
                        "village_name": primary_village,
                        "village_type": "REGISTRATION",
                        "search_mode": "SURVEY_WISE",
                        "survey_no": ls_no,
                        "subdivision_no": lsub_no,
                        "date_start": cls.SYSTEM_START_DATE,
                        "date_end": layout_end_date,
                        "rationale": f"Pre-layout promoter land encumbrance check on auxiliary layout survey {ls_no}/{lsub_no or '*'} ({cls.SYSTEM_START_DATE} to {layout_end_date})."
                    })
                    job_seq += 1

        plan = {
            "created_at": datetime.now().isoformat(),
            "target_deeds_analyzed": len(deeds),
            "timeline": timeline,
            "harvested_envelope": {
                "sros_by_era": sros_by_era,
                "villages": list(villages),
                "primary_surveys": [f"{s}/{sub}" if sub else s for s, sub in sorted(primary_surveys)],
                "parent_surveys": [f"{s}/{sub}" if sub else s for s, sub in sorted(parent_surveys)],
                "layout_surveys": [f"{s}/{sub}" if sub else s for s, sub in sorted(layout_surveys)],
                "plot_numbers": list(plot_numbers),
                "flat_numbers": list(flat_numbers),
                "tslr_entries": tslr_entries,
                "earliest_subdivision_year": earliest_subdivision_year,
                "earliest_layout_year": earliest_layout_year
            },
            "total_search_jobs": len(search_jobs),
            "search_jobs": search_jobs
        }

        return plan
