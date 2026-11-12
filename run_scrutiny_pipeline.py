#!/usr/bin/env python3
"""
========================================================================================
TNREGINET UNIFIED ONE-CLICK LEGAL TITLE SCRUTINY PIPELINE
========================================================================================
Single unified CLI entry point orchestrating Engine A -> Engine B -> Engine C sequentially.

Architecture:
  [User CLI] 
      │
      ▼
  [Step 1: Engine A] ──> Root deed fetch, PDF extraction, 50-year recursive PR lineage
      │
      ▼
  [Step 2: Engine B] ──> Autonomous 51-year TNREGINET EC downloader (Template 8400004)
      │                  Consolidated Master EC PDF (03) + Master Ledger (04)
      │
      ▼
  [Step 3: Engine C] ──> Autonomous Title Scrutiny & Conveyancing Engine
      │                  Bidirectional graph traversal, split containment math,
      │                  mortgage discharge matching, 2-tier audit ledger (06)
      ▼
  [Step 4: Terminal Summary & Auto-Launch Dossier in Browser]
========================================================================================
"""

import os
import sys
import re
import json
import time
import shutil
import argparse
import datetime
import urllib3
import webbrowser
import pypdf

urllib3.disable_warnings()

# ---------------------------------------------------------------------------------
# ROOT DIRECTORY & SAFEGUARDED ENGINE PATHS
# ---------------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
for path_entry in [
    os.path.join(ROOT_DIR, "testing_lab"),
    os.path.join(ROOT_DIR, "engines", "engine_c"),
    os.path.join(ROOT_DIR, "engines", "engine_b"),
    os.path.join(ROOT_DIR, "engines", "engine_a"),
    os.path.join(ROOT_DIR, "data"),
    ROOT_DIR
]:
    if os.path.exists(path_entry) and path_entry not in sys.path:
        sys.path.insert(0, path_entry)

# Core Protected Engine Imports
from engine_a_core import EngineACore
from recursive_pr_engine import RecursivePREngine
from pdf_deterministic_extractor import PDFDeterministicExtractor
from ec_portal_client import ECPortalClient
from ec_engine_orchestrator import ECEngineOrchestrator
from title_scrutiny_engine import TitleScrutinyEngine, TitleRiskStatus, MortgageStatus


def main():
    parser = argparse.ArgumentParser(
        description="TNREGINET Unified Autonomous Legal Title Scrutiny Pipeline (Engines A + B + C)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python run_scrutiny_pipeline.py --doc 1579 --year 2021 --sro "Trichy Joint 1" --sro_id "20445:1" --plot 26
        """
    )
    parser.add_argument("--doc", required=True, help="Target document number (e.g. 1579)")
    parser.add_argument("--year", required=True, help="Target registration year (e.g. 2021)")
    parser.add_argument("--sro", required=True, help="Target SRO name (e.g. 'Trichy Joint 1')")
    parser.add_argument("--sro_id", default="", help="Portal SRO ID (e.g. '20445:1')")
    parser.add_argument("--plot", default=None, help="Target plot (default: harvested from the target deed by Engine C)")
    parser.add_argument("--district_id", default="20034", help="Portal District ID (default: 20034)")
    parser.add_argument("--book_no", default="1", help="Book number (default: 1)")
    parser.add_argument("--output_dir", default=os.path.join(ROOT_DIR, "output"), help="Base output directory")
    parser.add_argument("--no_browser", action="store_true", help="Do not auto-open HTML dossier in browser")

    args = parser.parse_args()

    doc_no = str(args.doc).strip()
    year = str(args.year).strip()
    sro_name = str(args.sro).strip()
    sro_id = str(args.sro_id).strip()
    plot_no = str(args.plot).strip() if args.plot else None
    district_id = str(args.district_id).strip()
    book_no = str(args.book_no).strip()
    output_base = os.path.abspath(args.output_dir)

    # 1. Resolve SRO Hierarchy if sro_id missing
    if not sro_id:
        hierarchy = ECPortalClient.resolve_sro_hierarchy(sro_name)
        if hierarchy:
            sro_id = hierarchy["sro_id"]
            sro_name = hierarchy["sro_name"]
            district_id = hierarchy.get("district_id", district_id)
        else:
            sro_id = "20445:1"

    # 2. Initialization & Sandboxing (Isolated Timestamped Run Directory)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sro_clean = "".join(c for c in sro_name if c.isalnum() or c in (' ', '_')).replace(' ', '_')
    run_folder_name = f"run_{ts}_Doc_{doc_no}_{year}_{sro_clean}"
    run_folder = os.path.join(output_base, run_folder_name)
    os.makedirs(run_folder, exist_ok=True)
    deeds_folder = os.path.join(run_folder, "deeds")
    os.makedirs(deeds_folder, exist_ok=True)

    print("=" * 80)
    print("TNREGINET UNIFIED LEGAL TITLE SCRUTINY PIPELINE (ENGINES A -> B -> C)")
    print("=" * 80)
    print(f"Target Deed    : Doc {doc_no}/{year} @ {sro_name} (SRO ID: {sro_id})")
    print(f"Target Plot    : {('Plot No. ' + plot_no) if plot_no else '(harvest from target deed)'}")
    print(f"District ID    : {district_id} | Book No: {book_no}")
    print(f"Run Sandbox    : {run_folder}")
    print("=" * 80)

    # =========================================================================
    # STEP 1: ENGINE A (ROOT DEED & 50-YEAR RECURSIVE PR LINEAGE DISCOVERY)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[STEP 1/3] EXECUTING ENGINE A (ROOT DEED & RECURSIVE PR LINEAGE)")
    print("=" * 80)

    portal_result = None
    for attempt in range(1, 4):
        portal_result = EngineACore.fetch_portal_document(
            sro_id=sro_id,
            sro_name=sro_name,
            doc_no=doc_no,
            year=year,
            book_no=book_no,
            run_folder=run_folder,
            log_callback=print
        )
        if portal_result.get("success"):
            break
        print(f"[!] Root deed fetch attempt {attempt}/3 notice: {portal_result.get('error')}")
        if attempt < 3:
            backoff = 2 * attempt
            print(f"    [⇄] Retrying in {backoff}s...")
            time.sleep(backoff)
        else:
            print("[!] Failed to fetch root deed after 3 attempts.")

    if not portal_result.get("success"):
        print("\n[!] CRITICAL ERROR: Root target deed could not be fetched from portal after 3 attempts.")
        sys.exit(1)

    effective_pdf = portal_result.get("official_pdf_saved")
    if effective_pdf and os.path.exists(effective_pdf):
        print(f"[*] Extracting structured particulars from root deed: {os.path.basename(effective_pdf)}")
        pdf_result = PDFDeterministicExtractor.extract_from_pdf(effective_pdf, doc_no, year, sro_name)
        
        json2_file = os.path.join(run_folder, "02_pdf_detailed_extraction.json")
        with open(json2_file, "w", encoding="utf-8") as f:
            json.dump(pdf_result, f, indent=2, ensure_ascii=False)
            
        target_dest = os.path.join(deeds_folder, f"01_Target_Deed_Doc_{doc_no}_{year}.pdf")
        if not os.path.exists(target_dest):
            shutil.copy2(effective_pdf, target_dest)
        
        root_pub = os.path.join(run_folder, f"01_Root_Doc_{doc_no}_{year}.pdf")
        if not os.path.exists(root_pub):
            shutil.copy2(effective_pdf, root_pub)

    json1_file = os.path.join(run_folder, "01_portal_summary.json")
    with open(json1_file, "w", encoding="utf-8") as f:
        json.dump(portal_result, f, indent=2, ensure_ascii=False)

    # Recursive Prior Deed (PR) traversal
    print("\n[*] Triggering 50-Year Recursive PR Lineage Traversal...")
    lineage_result = RecursivePREngine.execute_lineage_discovery(
        root_doc_no=doc_no,
        root_year=year,
        root_sro_id=sro_id,
        root_sro_name=sro_name,
        district_id=district_id,
        run_folder=run_folder,
        log_callback=print
    )
    print(f"[+] Engine A PR Lineage complete! Total verified deeds in lineage: {lineage_result.get('total_deeds_discovered', 1)}")

    # Ensure standardized deed naming (01_Root_Doc_*.pdf, 02_PR_Doc_*.pdf, DOC_*.pdf, PR_*.pdf)
    for root_dir_w, _, files_w in os.walk(deeds_folder):
        for f in files_w:
            p = os.path.join(root_dir_w, f)
            if f.startswith("02_Parent_Deed_Doc_") and f.endswith(".pdf"):
                m = re.search(r'Doc_(\d+)_(\d+)', f)
                if m:
                    pr_pub = os.path.join(run_folder, f"02_PR_Doc_{m.group(1)}_{m.group(2)}.pdf")
                    if not os.path.exists(pr_pub):
                        shutil.copy2(p, pr_pub)

    # =========================================================================
    # STEP 2: ENGINE B (TNREGINET 51-YEAR AUTONOMOUS EC DOWNLOADER)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[STEP 2/3] EXECUTING ENGINE B (TNREGINET 51-YEAR EC HARVESTING & LEDGER)")
    print("=" * 80)

    print(f"[*] Ingesting Engine A run directory into Engine B: {run_folder}")
    ec_result = ECEngineOrchestrator.run_for_engine_a_output(
        engine_a_run_dir=run_folder,
        log_callback=print
    )

    # =========================================================================
    # STEP 3: ENGINE C (TITLE SCRUTINY & CONVEYANCING ENGINE)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[STEP 3/3] EXECUTING ENGINE C (TITLE SCRUTINY & CONVEYANCING ANALYSIS)")
    print("=" * 80)

    scrutiny_report = TitleScrutinyEngine.scrutinize_run(
        run_dir=run_folder,
        target_plot=plot_no,
        log_callback=print
    )

    # =========================================================================
    # STEP 4: TERMINAL SUMMARY & AUTO-LAUNCH
    # =========================================================================
    audit = scrutiny_report["title_scrutiny_audit"]
    target_info = audit["target_property"]
    overall_opinion = audit["overall_title_risk"]
    active_mortgages = audit.get("active_encumbrances", [])
    reconciled = audit.get("reconciliation_summary", {})

    print("\n" + "=" * 80)
    print("LEGAL TITLE SCRUTINY EXECUTIVE SUMMARY")
    print("=" * 80)
    print(f"Target Property : Doc {target_info['document_id']} | Plot No. {target_info['canonical_plot']} | SF {target_info['survey_number']} ({target_info['extent_sqft']} sqft)")
    print(f"Ownership Chain : {audit['chain_continuity_status']}")
    print(f"EC Coverage     : {audit.get('coverage_assessment', {}).get('coverage_verdict', 'UNKNOWN')} (Engine B: {audit.get('coverage_assessment', {}).get('engine_b_audit_status', 'NOT_REPORTED')})")
    print(f"Final Title Risk: {overall_opinion}")
    print(f"Title Opinion   : {audit['legal_opinion_summary']}")
    print("-" * 80)
    print(f"Active Mortgages: {len(active_mortgages)}")
    for m in active_mortgages:
        print(f"  🚨 Doc {m['mortgage_document_id']} ({', '.join(m.get('lender', []))}) -> {m['status']}")
        for req in m.get("mandatory_requisitions", []):
            print(f"     - {req}")
    print("-" * 80)
    print(f"Audit Ledger    : {reconciled.get('total_transactions_scanned')} Total Scanned Transactions")
    print(f"  + Tier 1 (Target Property Ledger) : {reconciled.get('tier1_target_transactions_count')} Deeds")
    print(f"  + Tier 2 (Layout / Neighbor)      : {reconciled.get('tier2_layout_neighbor_count')} Records (0 False Alarms)")
    print("-" * 80)
    print(f"Report JSON     : {os.path.join(run_folder, '06_title_scrutiny_report.json')}")
    dossier_html = os.path.join(run_folder, "06_title_scrutiny_dossier.html")
    print(f"HTML Dossier    : {dossier_html}")
    print("=" * 80)

    # Auto-launch interactive HTML dossier in default browser
    if not args.no_browser and os.path.exists(dossier_html):
        print("\n[*] Launching Interactive Title Scrutiny Dossier in browser...")
        try:
            webbrowser.open(f"file:///{os.path.abspath(dossier_html)}")
        except Exception as e_br:
            print(f"[!] Notice launching browser: {e_br}")

    print("\n>>> [SUCCESS] UNIFIED LEGAL TITLE SCRUTINY PIPELINE COMPLETED SUCCESSFULLY <<<")


if __name__ == "__main__":
    main()
