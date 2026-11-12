"""
ec_engine_orchestrator.py - Master Controller for End-to-End Property EC Engine
==============================================================================
Orchestrates the entire Encumbrance Certificate discovery workflow from 1975 to Present:

Workflow:
1. Intake: Consumes the PR lineage deeds output by Engine A (or triggers Engine A).
2. Matrix Planning (ec_matrix_planner): Builds the multi-tier search jobs across
   SROs, villages, primary surveys, parent surveys, and urban TSLR.
3. Adaptive Date Halving (ec_date_splitter): Bypasses 200-page overflows seamlessly.
4. Deduplication & Reconciliation (ec_master_merger): Compiles all downloaded EC PDFs
   into the unified 1975-2026 Master Property Ledger and visual HTML dossier.
"""

import os
import sys
import re
import time
import json
import glob
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional

from ec_matrix_planner import ECMatrixPlanner, SearchTrack
from ec_date_splitter import ECDateSplitter
from ec_master_merger import ECMasterMerger
from ec_portal_client import ECPortalClient
from engine_a_core import EngineACore
from pdf_deterministic_extractor import PDFDeterministicExtractor


class ECEngineOrchestrator:
    """Master controller orchestrating complete 1975-Present property EC discovery."""

    WINDOW_TRANSIENT_RETRIES = 2
    WINDOW_TRANSIENT_BACKOFF_S = 20

    @staticmethod
    def classify_window_result(res: Optional[Dict[str, Any]], reason: str = "") -> Dict[str, Any]:
        """
        Deterministic verdict for one portal search window.
        ok=True only for an authentic downloaded certificate or a verified zero-record response
        (countNoRecords explicitly 0 in the portal form and no PDF expected).
        """
        if reason:
            return {"ok": False, "outcome": "FAILED", "reason": reason}
        if not res:
            return {"ok": False, "outcome": "FAILED", "reason": "NO_RESPONSE"}
        if res.get("split_needed") or res.get("overflow"):
            return {"ok": False, "outcome": "FAILED", "reason": "OVERFLOW_NOT_SPLIT"}
        if not res.get("success"):
            return {"ok": False, "outcome": "FAILED", "reason": res.get("pdf_status") or res.get("error") or "SEARCH_FAILED"}
        if res.get("nil"):
            if res.get("count_field_present") and int(res.get("portal_record_count") or 0) == 0:
                return {"ok": True, "outcome": "NIL_VERIFIED", "reason": "countNoRecords=0"}
            return {"ok": False, "outcome": "FAILED", "reason": "NIL_UNVERIFIED"}
        if res.get("pdf_saved") and os.path.exists(res["pdf_saved"]):
            return {"ok": True, "outcome": "CERTIFIED", "reason": "OK"}
        return {"ok": False, "outcome": "FAILED", "reason": f"EC_PDF_{res.get('pdf_status') or 'NOT_OBTAINED'}"}

    @classmethod
    def run_for_engine_a_output(
        cls,
        engine_a_run_dir: str,
        output_base_dir: Optional[str] = None,
        simulate_live_portal: bool = False,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Runs the full EC Engine workflow using an Engine A PR lineage directory as input.
        """
        def log(msg: str):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        log("========================================================================")
        log("TNREGINET 1975–2026 COMPREHENSIVE PROPERTY EC ENGINE")
        log("========================================================================")
        log(f"[*] Analyzing Engine A PR lineage run: {engine_a_run_dir}")

        if not os.path.exists(engine_a_run_dir):
            raise FileNotFoundError(f"Run directory not found: {engine_a_run_dir}")

        # Set up output directory
        if not output_base_dir:
            output_base_dir = os.path.join(engine_a_run_dir, "ec_engine_full_trace")
        os.makedirs(output_base_dir, exist_ok=True)
        ec_downloads_dir = os.path.join(output_base_dir, "downloaded_ec_pdfs")
        os.makedirs(ec_downloads_dir, exist_ok=True)

        # STAGE 1: PLAN SEARCH MATRIX
        log("\n[STAGE 1] Building Search Envelope & Multi-SRO Matrix...")
        plan = ECMatrixPlanner.plan_from_engine_a_run(engine_a_run_dir)
        env = plan["harvested_envelope"]
        
        log(f"  + Historical SROs detected: {[s['sro_name'] for s in env.get('sros_by_era', [])]}")
        log(f"  + Villages: {env.get('villages')}")
        log(f"  + Primary Plot Surveys: {env.get('primary_surveys')}")
        log(f"  + Parent Surveys (Pre-subdivision): {env.get('parent_surveys')}")
        log(f"  + Layout Auxiliary Surveys: {env.get('layout_surveys')}")
        log(f"  + Urban TSLR (Ward/Block): {len(env.get('tslr_entries', []))} references")
        log(f"  + Earliest Subdivision Year: {env.get('earliest_subdivision_year')}")
        log(f"  ==> Generated {plan['total_search_jobs']} Exhaustive Search Jobs.")

        plan_file = os.path.join(output_base_dir, "01_ec_search_matrix_plan.json")
        with open(plan_file, "w", encoding="utf-8") as fp:
            json.dump(plan, fp, indent=2, ensure_ascii=False)
        log(f"  + Saved search plan to {plan_file}")

        # STAGE 2: EXECUTION OF SEARCH JOBS
        log("\n[STAGE 2] Executing Live Search Matrix & Adaptive Date Windows on TNREGINET...")
        collected_pdf_paths = []
        collected_survey_records = []
        audit_blockers = []

        # Collect existing official PDFs from Engine A as baseline
        existing_pdfs = glob.glob(os.path.join(engine_a_run_dir, "deeds", "**", "*.pdf"), recursive=True)
        for ep in existing_pdfs:
            collected_pdf_paths.append(ep)

        # Initialize live HTTP session for portal searches
        session = ECPortalClient.create_session()

        # Per-window outcome ledger: a run is exhaustive only if EVERY planned window ended
        # with an authentic certificate (CERTIFIED) or a verified zero-record response (NIL_VERIFIED).
        window_outcomes: List[Dict[str, Any]] = []

        def _record_window(job_id: str, w_start: str, w_end: str, res: Optional[Dict[str, Any]], reason: str = "") -> Dict[str, Any]:
            outcome = ECEngineOrchestrator.classify_window_result(res, reason)
            row = {
                "job_id": job_id,
                "date_start": w_start,
                "date_end": w_end,
                "outcome": outcome["outcome"],
                "reason": outcome["reason"],
                "portal_record_count": (res or {}).get("portal_record_count"),
                "html_records": len((res or {}).get("records") or []),
                "pdf_saved": (res or {}).get("pdf_saved"),
                "error": (res or {}).get("error"),
            }
            window_outcomes.append(row)
            if not outcome["ok"]:
                audit_blockers.append({
                    "type": "EC_WINDOW_NOT_CERTIFIED",
                    "job_id": job_id,
                    "date_start": w_start,
                    "date_end": w_end,
                    "reason": outcome["reason"],
                    "portal_record_count": row["portal_record_count"],
                })
                log(f"      [!] AUDIT BLOCKER: {job_id} {w_start}..{w_end} not certified ({outcome['reason']}).")
            return row

        def run_search_with_halving(
            cur_start: str,
            cur_end: str,
            sro_info: Dict[str, str],
            survey_items: List[Dict[str, str]],
            base_job_id: str,
            depth: int = 0,
            is_ward_block: bool = False,
            ward_no: str = "",
            block_no: str = ""
        ) -> List[Dict[str, Any]]:
            """Recursively queries TNREGINET, splitting the date interval when email prompt is triggered."""
            nonlocal session
            log(f"      [Step] Querying interval {cur_start} to {cur_end} (depth={depth})...")
            
            clean_sro = sro_info['sro_name'].replace(' ', '_')
            out_pdf_name = f"EC_{base_job_id}_{clean_sro}_{cur_start}_to_{cur_end}.pdf"
            out_pdf_path = os.path.join(ec_downloads_dir, out_pdf_name)
            
            # Ensure fresh, clean HTTP session per search window to avoid server-side report buffer contamination
            session = ECPortalClient.create_session()
            session_state = None
            for s_att in range(1, 4):
                try:
                    session_state = ECPortalClient.init_ec_session(session, log_callback=log)
                    break
                except Exception as e_init:
                    log(f"      [!] Session init attempt {s_att}/3 notice: {e_init}")
                    if s_att < 3:
                        time.sleep(2 * s_att)
                        session = ECPortalClient.create_session()
                    else:
                        fail = {"success": False, "pdf_status": "SESSION_INIT_FAILED", "error": str(e_init)}
                        _record_window(base_job_id, cur_start, cur_end, fail)
                        return [fail]

            res = None
            for s_att in range(1, 4):
                try:
                    res = ECPortalClient.execute_ec_search(
                        session=session,
                        auth_token=session_state["auth_token"],
                        csrf_token=session_state["csrf_token"],
                        captcha_code=session_state["captcha_code"],
                        sro_info=sro_info,
                        survey_items=survey_items,
                        start_date=cur_start,
                        end_date=cur_end,
                        output_pdf_path=out_pdf_path,
                        base_form_fields=session_state.get("base_form_fields"),
                        is_ward_block=is_ward_block,
                        ward_no=ward_no,
                        block_no=block_no,
                        log_callback=log
                    )
                    break
                except (ConnectionResetError, requests.exceptions.RequestException, Exception) as e_exec:
                    log(f"      [!] Search execution network error (attempt {s_att}/3): {e_exec}")
                    if s_att < 3:
                        time.sleep(2 * s_att)
                        try:
                            session = ECPortalClient.create_session()
                            session_state = ECPortalClient.init_ec_session(session, log_callback=log)
                        except Exception as e_reinit:
                            log(f"      [!] Session re-init notice: {e_reinit}")
                    else:
                        res = {"success": False, "pdf_status": "SEARCH_FAILED", "error": str(e_exec)}
            
            # Transient portal error ("Please try after sometime"): retry the SAME window with a fresh
            # session and longer backoff. Never date-split on it; the error page's record count is stale.
            t_att = 0
            while res and res.get("transient") and t_att < cls.WINDOW_TRANSIENT_RETRIES:
                t_att += 1
                wait_s = cls.WINDOW_TRANSIENT_BACKOFF_S * t_att
                log(f"      [↻] Transient portal error for {cur_start} to {cur_end}; window retry {t_att}/{cls.WINDOW_TRANSIENT_RETRIES} after {wait_s}s (no date split).")
                time.sleep(wait_s)
                try:
                    session = ECPortalClient.create_session()
                    session_state = ECPortalClient.init_ec_session(session, log_callback=log)
                    res = ECPortalClient.execute_ec_search(
                        session=session,
                        auth_token=session_state["auth_token"],
                        csrf_token=session_state["csrf_token"],
                        captcha_code=session_state["captcha_code"],
                        sro_info=sro_info,
                        survey_items=survey_items,
                        start_date=cur_start,
                        end_date=cur_end,
                        output_pdf_path=out_pdf_path,
                        base_form_fields=session_state.get("base_form_fields"),
                        is_ward_block=is_ward_block,
                        ward_no=ward_no,
                        block_no=block_no,
                        log_callback=log
                    )
                except Exception as e_tr:
                    log(f"      [!] Transient-retry notice: {e_tr}")
                    res = {"success": False, "transient": True, "pdf_status": "PORTAL_TRANSIENT_ERROR", "error": str(e_tr)}

            results = []
            if res.get("split_needed") or res.get("overflow"):
                log(f"      [!] Portal email submission prompt active: records exceed synchronous threshold.")
                log(f"      [⇄] Applying Adaptive Binary Halving on {cur_start} to {cur_end}...")
                
                try:
                    left_half, right_half = ECDateSplitter.split_interval(cur_start, cur_end)
                    # Recurse left
                    res_left = run_search_with_halving(left_half[0], left_half[1], sro_info, survey_items, base_job_id, depth + 1, is_ward_block, ward_no, block_no)
                    results.extend(res_left)
                    # Recurse right
                    res_right = run_search_with_halving(right_half[0], right_half[1], sro_info, survey_items, base_job_id, depth + 1, is_ward_block, ward_no, block_no)
                    results.extend(res_right)
                except Exception as e_split:
                    log(f"      [!] Cannot split further ({cur_start} to {cur_end}): {e_split}")
                    _record_window(base_job_id, cur_start, cur_end, res, reason=f"OVERFLOW_UNSPLITTABLE: {e_split}")
                    results.append(res)
            else:
                if res.get("pdf_saved"):
                    collected_pdf_paths.append(res["pdf_saved"])
                if res.get("records"):
                    collected_survey_records.extend(res["records"])
                res["_window_outcome"] = _record_window(base_job_id, cur_start, cur_end, res)
                results.append(res)
                
            return results

        executed_master_sros = set()
        # sro -> list of {"surveys": set((s, sub)), "start", "end", "ok"} for MASTER_SRO_BATCH runs
        master_coverage: Dict[str, List[Dict[str, Any]]] = {}

        def _master_covers(job: Dict[str, Any]) -> bool:
            key = (str(job.get("survey_no", "")), str(job.get("subdivision_no", "") or ""))
            try:
                j_start = ECDateSplitter.parse_date(job["date_start"])
                j_end = ECDateSplitter.parse_date(job["date_end"])
            except Exception:
                return False
            for cov in master_coverage.get(job["sro_name"], []):
                if not cov["ok"] or key not in cov["surveys"]:
                    continue
                try:
                    if ECDateSplitter.parse_date(cov["start"]) <= j_start and ECDateSplitter.parse_date(cov["end"]) >= j_end:
                        return True
                except Exception:
                    continue
            return False

        def _job_skipped(job: Dict[str, Any], reason: str):
            audit_blockers.append({"type": "EC_JOB_NOT_EXECUTED", "job_id": job.get("job_id"), "reason": reason})
            window_outcomes.append({"job_id": job.get("job_id"), "date_start": job.get("date_start"),
                                    "date_end": job.get("date_end"), "outcome": "NOT_EXECUTED", "reason": reason})

        for job in plan["search_jobs"]:
            track = job.get("track", "")
            sro_info, sro_score, sro_top_3 = ECPortalClient.resolve_sro_hierarchy(job["sro_name"], return_details=True)
            if not sro_info:
                log("\n" + "=" * 76)
                log("CRITICAL AUDIT BLOCKER: UNRESOLVED SRO")
                log("=" * 76)
                log(f"  Deed SRO Query: '{job['sro_name']}'")
                log(f"  Confidence Score: {sro_score:.2f} (< 0.80)")
                log("  Top 3 Closest Candidate Suggestions in 575+ SRO Hierarchy:")
                for c_idx, c_name in enumerate(sro_top_3, 1):
                    log(f"    {c_idx}. '{c_name}'")
                log("  ACTION REQUIRED: Pausing search track to prevent false clean title opinion.")
                log("=" * 76 + "\n")
                audit_blockers.append({
                    "type": "UNRESOLVED_SRO",
                    "deed_sro": job["sro_name"],
                    "confidence_score": sro_score,
                    "top_3_candidates": sro_top_3
                })
                continue

            if track == "MASTER_SRO_BATCH":
                if not job.get("surveys"):
                    log(f"      [!] No deed-reflected surveys identified for MASTER_SRO_BATCH. Skipping.")
                    _job_skipped(job, "NO_SURVEYS_FOR_MASTER_BATCH")
                    continue
                executed_master_sros.add(job["sro_name"])
                log(f"\n  --> Executing {job['job_id']}: MASTER SRO BATCH | SRO: {job['sro_name']} | Dates: {job['date_start']} to {job['date_end']}")
                
                # Harvested villages across all lineage deeds
                harvested_villages = job.get("deed_villages", [])
                log(f"      [+] All villages harvested from both the main deed AND the parent PR deed(s): {harvested_villages}")

                # Match deed villages using Tier 1 & Tier 3 Dual-Registry Resolver
                try:
                    session_state = ECPortalClient.init_ec_session(session, log_callback=log)
                    village_resolution = ECPortalClient.match_villages_with_dual_registry(
                        session=session,
                        csrf_token=session_state["csrf_token"],
                        sro_id=sro_info["sro_id"],
                        deed_villages=harvested_villages,
                        log_callback=log
                    )
                except Exception as e_v:
                    log(f"      [!] Village dual-registry resolution notice: {e_v}")
                    village_resolution = {"matched_villages": [], "unresolved_villages": []}

                if village_resolution.get("unresolved_villages"):
                    audit_blockers.extend(village_resolution["unresolved_villages"])

                matched_villages = village_resolution.get("matched_villages", [])
                matched_names = [v[1] for v in matched_villages]
                job["matched_portal_villages"] = matched_names
                log(f"      [+] All matching portal village variants ({len(matched_villages)} variants): {matched_names}")

                # Save updated plan reflecting matched portal villages
                try:
                    with open(plan_file, "w", encoding="utf-8") as fp:
                        json.dump(plan, fp, indent=2, ensure_ascii=False)
                except Exception:
                    pass

                if not matched_villages:
                    log(f"      [!] Zero valid portal villages matched for SRO '{sro_info['sro_name']}'. Track paused by Audit Shield.")
                    _job_skipped(job, "NO_PORTAL_VILLAGE_MATCHED")
                    continue

                # Batch into groups of up to 3 villages (strict portal constraint)
                v_batches = [matched_villages[i:i+3] for i in range(0, len(matched_villages), 3)]
                log(f"      [+] Grouped into {len(v_batches)} execution search batch(es) (maximum 3 villages per portal query constraint):")

                survey_tuples = job.get("surveys", [])
                batch_ok = True
                survey_display = [f"{s}/{sub}" if sub else str(s) for s, sub in survey_tuples]

                for b_idx, batch in enumerate(v_batches, start=1):
                    batch_names = [v[1] for v in batch]
                    log(f"\n    [Executing Batch {b_idx}/{len(v_batches)}] Villages: {batch_names} | Surveys: {survey_display}")
                    survey_items = []
                    for v_id, v_name in batch:
                        for s_no, sub_no in survey_tuples:
                            survey_items.append({
                                "village_id": v_id,
                                "survey_no": str(s_no),
                                "subdivision_no": str(sub_no or "")
                            })
                    
                    is_wb = (job.get("search_mode") == "WARD_BLOCK_WISE")
                    w_no = str(job.get("ward_no", "") or "")
                    b_no = str(job.get("block_no", "") or "")
                    n_before = len(window_outcomes)
                    run_search_with_halving(
                        cur_start=job["date_start"],
                        cur_end=job["date_end"],
                        sro_info=sro_info,
                        survey_items=survey_items,
                        base_job_id=f"{job['job_id']}_B{b_idx:02d}",
                        is_ward_block=is_wb,
                        ward_no=w_no,
                        block_no=b_no
                    )
                    new_rows = window_outcomes[n_before:]
                    if not new_rows or any(r.get("outcome") not in ("CERTIFIED", "NIL_VERIFIED") for r in new_rows):
                        batch_ok = False
                master_coverage.setdefault(job["sro_name"], []).append({
                    "surveys": {(str(s), str(sub or "")) for s, sub in survey_tuples},
                    "start": job["date_start"],
                    "end": job["date_end"],
                    "ok": batch_ok,
                })
            elif job["sro_name"] in executed_master_sros and track in [SearchTrack.PRIMARY_SURVEY, SearchTrack.PARENT_SURVEY, SearchTrack.LAYOUT_AUXILIARY, "PRIMARY_SURVEY", "PARENT_SURVEY", "LAYOUT_AUXILIARY"] and _master_covers(job):
                log(f"      [i] SRO '{job['sro_name']}' survey {job.get('survey_no')}/{job.get('subdivision_no')} {job['date_start']}..{job['date_end']} already certified by MASTER_SRO_BATCH. Skipping redundant job {job['job_id']}.")
                window_outcomes.append({"job_id": job["job_id"], "date_start": job["date_start"], "date_end": job["date_end"],
                                        "outcome": "COVERED_BY_MASTER_BATCH", "reason": "same SRO, survey and date range certified"})
                continue
            else:
                log(f"\n  --> Executing {job['job_id']}: {job['search_mode']} | SRO: {job['sro_name']} | Dates: {job['date_start']} to {job['date_end']} | Survey: {job.get('survey_no')}/{job.get('subdivision_no')}")
                # Target output PDF path
                clean_sro = sro_info['sro_name'].replace(' ', '_')
                out_pdf_name = f"EC_{job['job_id']}_{clean_sro}_{job['date_start']}_to_{job['date_end']}.pdf"
                out_pdf_path = os.path.join(ec_downloads_dir, out_pdf_name)

                # Match village using dual-registry resolver
                v_cand = [job["village_name"]] if job.get("village_name") else []
                v_id, v_name = "", ""
                if v_cand:
                    try:
                        session_state = ECPortalClient.init_ec_session(session, log_callback=log)
                        v_res = ECPortalClient.match_villages_with_dual_registry(
                            session=session,
                            csrf_token=session_state["csrf_token"],
                            sro_id=sro_info["sro_id"],
                            deed_villages=v_cand,
                            log_callback=log
                        )
                        if v_res.get("unresolved_villages"):
                            audit_blockers.extend(v_res["unresolved_villages"])
                        if v_res.get("matched_villages"):
                            v_id, v_name = v_res["matched_villages"][0]
                    except Exception as e_v:
                        log(f"      [!] Village dual-registry match notice: {e_v}")

                if not v_id:
                    log(f"      [!] Unresolved village for job {job['job_id']}. Skipping to avoid false clean title.")
                    _job_skipped(job, "UNRESOLVED_VILLAGE")
                    continue

                s_item = [{
                    "village_id": v_id,
                    "survey_no": str(job.get("survey_no", "")),
                    "subdivision_no": str(job.get("subdivision_no", "") or "")
                }]
                is_wb = (job.get("search_mode") == "WARD_BLOCK_WISE" or track == "URBAN_TSLR")
                w_no = str(job.get("ward_no", "") or "")
                b_no = str(job.get("block_no", "") or "")
                run_search_with_halving(
                    cur_start=job["date_start"],
                    cur_end=job["date_end"],
                    sro_info=sro_info,
                    survey_items=s_item,
                    base_job_id=job["job_id"],
                    is_ward_block=is_wb,
                    ward_no=w_no,
                    block_no=b_no
                )

        # STAGE 2.5: PROPERTY-SPECIFIC SUBSEQUENT DEED RESOLUTION & MASTER EC PDF COMPILATION
        log("\n[STAGE 2.5] Compiling Official Government Survey EC PDFs & Deed Registrations...")
        
        # Determine candidate deeds from survey search that match primary subdivision or root deed year/after
        prim_survs = env.get("primary_surveys", [])
        deeds_dir = os.path.join(engine_a_run_dir, "deeds")
        
        # Existing deeds
        existing_doc_ids = set()
        for root, dirs, files in os.walk(deeds_dir):
            for f in files:
                if f == "02_pdf_detailed_extraction.json":
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8") as fp:
                            d = json.load(fp)
                            if d.get("entries"):
                                reg = d["entries"][0].get("registration_particulars", {})
                                d_id = f"{reg.get('document_number')}/{reg.get('registration_year')}"
                                existing_doc_ids.add(d_id)
                    except:
                        pass

        # Identify subsequent encumbrance deeds (e.g. 1583/2021, 83/2024 on plot subdivision)
        plot_surveys = [s for s in prim_survs if any(c.isalpha() for c in s)]
        if not plot_surveys:
            plot_surveys = prim_survs

        candidate_deeds_to_fetch = []
        for s_rec in collected_survey_records:
            d_no = str(s_rec.get("doc_no", "")).strip()
            yr = str(s_rec.get("year", "")).strip()
            d_id = f"{d_no}/{yr}"
            s_no = str(s_rec.get("survey_no", "")).strip()
            
            # Match if on specific plot survey (e.g. 173/2H)
            is_plot_match = any(ps in s_no for ps in plot_surveys)
            if is_plot_match and d_id not in existing_doc_ids and d_id not in [c[0] for c in candidate_deeds_to_fetch]:
                candidate_deeds_to_fetch.append((d_id, d_no, yr, s_rec.get("sro_name")))

        # Fetch official PDF for property encumbrance deeds
        fetched_official_pdfs = []
        for idx, (d_id, d_no, yr, s_name) in enumerate(candidate_deeds_to_fetch, start=len(existing_doc_ids)+1):
            sro_info = ECPortalClient.resolve_sro_hierarchy(s_name)
            sro_id = sro_info["sro_id"] if sro_info else "20445:1"
            sro_name = sro_info["sro_name"] if sro_info else s_name
            
            sub_folder_name = f"{idx:02d}_Subsequent_Doc_{d_no}_{yr}"
            sub_folder = os.path.join(deeds_dir, sub_folder_name)
            
            log(f"  + Fetching official government EC PDF for {d_id} at SRO '{sro_name}'...")
            fetch_res = EngineACore.fetch_portal_document(
                sro_id=sro_id,
                sro_name=sro_name,
                doc_no=d_no,
                year=yr,
                run_folder=sub_folder,
                log_callback=log
            )
            
            if fetch_res.get("success"):
                pdf_path = os.path.join(sub_folder, "official_encumbrance_certificate.pdf")
                if os.path.exists(pdf_path):
                    # Run deterministic extraction
                    ext_res = PDFDeterministicExtractor.extract_from_pdf(
                        pdf_path=pdf_path,
                        fallback_doc_no=d_no,
                        fallback_year=yr,
                        fallback_sro=sro_name
                    )
                    ext_json_path = os.path.join(sub_folder, "02_pdf_detailed_extraction.json")
                    with open(ext_json_path, "w", encoding="utf-8") as fp:
                        json.dump(ext_res, fp, indent=2, ensure_ascii=False)
                    log(f"    [✓] Extracted full JSON conversion: {ext_json_path}")
                    fetched_official_pdfs.append(pdf_path)
                    collected_pdf_paths.append(pdf_path)
                    existing_doc_ids.add(d_id)

        # Build Master Property EC PDF by concatenating all official Government EC PDFs in chronological order
        all_official_ec_pdfs = []

        # 1. Freshly downloaded survey EC PDFs from the CURRENT run
        survey_pdfs_in_downloads = [
            os.path.join(ec_downloads_dir, f) 
            for f in os.listdir(ec_downloads_dir) 
            if f.endswith(".pdf") and not f.startswith("Master_") and os.path.getsize(os.path.join(ec_downloads_dir, f)) > 1000
        ]
        # Never splice a portal error/retry page into the master certificate.
        _authentic = []
        for _p in survey_pdfs_in_downloads:
            try:
                with open(_p, "rb") as _fp:
                    _insp = ECPortalClient.inspect_ec_pdf(_fp.read())
            except Exception as _e:
                _insp = {"authentic": False, "reason": f"UNREADABLE: {_e}"}
            if _insp.get("authentic"):
                _authentic.append(_p)
            else:
                log(f"      [!] Excluding non-certificate PDF from master: {os.path.basename(_p)} ({_insp.get('reason')})")
        survey_pdfs_in_downloads = _authentic

        if not survey_pdfs_in_downloads:
            log("      [i] No multi-page survey EC PDFs downloaded during current live run.")

        for p in survey_pdfs_in_downloads:
            if p not in all_official_ec_pdfs:
                all_official_ec_pdfs.append(p)

        # 2. Add any official deed EC PDFs from deeds directory
        for root, dirs, files in os.walk(deeds_dir):
            for f in files:
                if f == "official_encumbrance_certificate.pdf":
                    p = os.path.join(root, f)
                    if p not in all_official_ec_pdfs:
                        all_official_ec_pdfs.append(p)

        def _get_pdf_sort_key(p):
            fname = os.path.basename(p)
            m = re.search(r'(\d{4})', fname)
            yr = int(m.group(1)) if m else 2026
            return (0 if "EC_JOB" in fname else 1, yr)

        all_official_ec_pdfs.sort(key=_get_pdf_sort_key)
        log(f"  + Merging {len(all_official_ec_pdfs)} freshly downloaded official EC PDF streams: {[os.path.basename(p) for p in all_official_ec_pdfs]}")

        canonical_master_path = os.path.join(ec_downloads_dir, "Master_Property_EC_1975_2026.pdf")

        if all_official_ec_pdfs:
            from pypdf import PdfWriter, PdfReader
            import pdfplumber
            writer = PdfWriter()
            for pdf_p in all_official_ec_pdfs:
                try:
                    # Mediabox Safety Net: Inspect table width across pages to prevent right-side clipping
                    table_width = 0
                    try:
                        with pdfplumber.open(pdf_p) as plumb:
                            for plumb_page in plumb.pages[:10]:
                                tables = plumb_page.find_tables()
                                for t in tables:
                                    if t.bbox[2] > table_width:
                                        table_width = t.bbox[2]
                    except Exception:
                        pass

                    r = PdfReader(pdf_p)
                    for page in r.pages:
                        cur_w = float(page.mediabox.width)
                        cur_h = float(page.mediabox.height) or 595.0
                        if table_width > cur_w:
                            new_w = max(842.0, table_width + 20.0)
                            page.mediabox.left = 0
                            page.mediabox.bottom = 0
                            page.mediabox.right = new_w
                            page.mediabox.top = cur_h
                            if hasattr(page, 'cropbox') and page.cropbox:
                                page.cropbox.right = new_w
                        writer.add_page(page)
                except Exception as e_pdf:
                    log(f"    [!] Error reading {pdf_p}: {e_pdf}")

            with open(canonical_master_path, "wb") as fp:
                writer.write(fp)
            log(f"\n[✓] Compiled Master Consolidated Property EC PDF ({len(writer.pages)} pages) -> {canonical_master_path}")

            # Also publish directly in the root run directory
            import shutil
            root_master_pdf = os.path.join(engine_a_run_dir, "03_Full_Raw_Encumbrance_Certificate_1975_2026.pdf")
            try:
                shutil.copy2(canonical_master_path, root_master_pdf)
                log(f"[✓] Published Full Raw EC PDF directly to run directory: {root_master_pdf}")
            except Exception as e_cp:
                log(f"    [!] Notice copying to root run dir: {e_cp}")

            # Also publish root-level deed PDFs for immediate local visibility
            try:
                for sub_d in sorted(os.listdir(deeds_dir)):
                    sub_p = os.path.join(deeds_dir, sub_d)
                    if os.path.isdir(sub_p):
                        d_pdf = os.path.join(sub_p, "official_encumbrance_certificate.pdf")
                        if os.path.exists(d_pdf):
                            dest_pdf = os.path.join(engine_a_run_dir, f"{sub_d}.pdf")
                            if not os.path.exists(dest_pdf):
                                shutil.copy2(d_pdf, dest_pdf)
            except Exception as e_pub:
                log(f"    [!] Notice publishing deed PDFs to root: {e_pub}")

            if canonical_master_path not in collected_pdf_paths:
                collected_pdf_paths.append(canonical_master_path)

        # STAGE 3: DETERMINISTIC RECONCILIATION & MASTER LEDGER
        log("\n[STAGE 3] Reconciling All EC PDFs into Master Property Ledger (1975-2026)...")
        
        # Save final audit status in plan
        audit_status = "INCOMPLETE_UNRESOLVED_PARCEL" if audit_blockers else "VERIFIED_EXHAUSTIVE"
        plan["audit_status"] = audit_status
        plan["audit_blockers"] = audit_blockers
        plan["window_outcomes"] = window_outcomes
        try:
            with open(plan_file, "w", encoding="utf-8") as fp:
                json.dump(plan, fp, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Compile individual EC PDFs, deduplicate, and assemble unified master property ledger
        master_ledger = ECMasterMerger.compile_from_run_directory(
            run_dir=engine_a_run_dir,
            audit_status=audit_status,
            audit_blockers=audit_blockers,
            log_callback=log
        )

        # Publish copy to root run folder for immediate visibility
        try:
            root_ledger_copy = os.path.join(engine_a_run_dir, "04_unified_master_property_ledger_1975_2026.json")
            if master_ledger.get("_saved_json") and os.path.exists(master_ledger["_saved_json"]):
                shutil.copy2(master_ledger["_saved_json"], root_ledger_copy)
                log(f"[✓] Published Unified Master Property Ledger to run root: {root_ledger_copy}")
            
            root_html_copy = os.path.join(engine_a_run_dir, "05_unified_title_dossier.html")
            if master_ledger.get("_saved_html") and os.path.exists(master_ledger["_saved_html"]):
                shutil.copy2(master_ledger["_saved_html"], root_html_copy)
                log(f"[✓] Published Interactive HTML Dossier to run root: {root_html_copy}")
        except Exception:
            pass

        log("\n========================================================================")
        log("SCRUTINY RESULTS & FINAL 1975-2026 PROPERTY LEDGER")
        log("========================================================================")
        log(f"  + Audit Status: {master_ledger.get('audit_status', 'UNKNOWN')}")
        if master_ledger.get('audit_blockers'):
            log(f"  + [!] CRITICAL AUDIT BLOCKERS ({len(master_ledger['audit_blockers'])} unresolved parcel(s)):")
            for b_idx, b_item in enumerate(master_ledger['audit_blockers'], 1):
                log(f"      {b_idx}. {b_item}")
        else:
            log("  + [✓] Audit Shield: Zero Unresolved Parcels. 100% Jurisdictional Coverage Confirmed.")
        log(f"  + Total Unique Transactions: {master_ledger.get('total_unique_transactions', 0)}")
        log(f"  + Confirmed Chain-of-Title Deeds: {master_ledger.get('lineage_deeds_confirmed', 0)}")
        log(f"  + Adverse / Other Transactions: {master_ledger.get('adverse_transactions_count', 0)}")
        log(f"  + High Risk Alerts: {master_ledger.get('high_risk_alerts_count', 0)}")
        log(f"  + Unsatisfied Mortgages: {master_ledger.get('unsatisfied_mortgages_count', 0)}")
        log(f"  + Master JSON Ledger: {master_ledger.get('_saved_json')}")
        log(f"  + Interactive HTML Dossier: {master_ledger.get('_saved_html')}")
        log("========================================================================")

        return {
            "success": True,
            "audit_status": master_ledger.get("audit_status", "UNKNOWN"),
            "audit_blockers": master_ledger.get("audit_blockers", []),
            "plan": plan,
            "master_ledger": master_ledger,
            "total_unique_transactions": master_ledger.get("total_unique_transactions", 0),
            "lineage_deeds_confirmed": master_ledger.get("lineage_deeds_confirmed", 0),
            "adverse_transactions_count": master_ledger.get("adverse_transactions_count", 0),
            "high_risk_alerts_count": master_ledger.get("high_risk_alerts_count", 0),
            "unsatisfied_mortgages_count": master_ledger.get("unsatisfied_mortgages_count", 0),
            "dossier_html": master_ledger.get("_saved_html"),
            "ledger_json": master_ledger.get("_saved_json"),
            "output_dir": output_base_dir
        }


if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else r"d:\Ai_legal\output\run_20261106_123245_Doc_1579_2021_Trichy_Joint_1"
    ECEngineOrchestrator.run_for_engine_a_output(target_dir, log_callback=print)
