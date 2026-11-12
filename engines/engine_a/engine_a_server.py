"""
engine_a_server.py - Standalone Web Server for Engine A Testing Lab
===================================================================
Runs on port 5050 to provide complete isolation from the production engine.
Handles live TNREGINET queries, PDF deed uploads, report generation, and direct folder inspection.
"""

import os
import sys
import json
import time
import datetime
import cgi
import subprocess
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "engine_a_output")
HIERARCHY_FILE = os.path.join(BASE_DIR, "sro_hierarchy.json")
UI_FILE = os.path.join(BASE_DIR, "engine_a_ui.html")

os.makedirs(OUTPUT_DIR, exist_ok=True)

from engine_a_core import EngineACore
from pdf_deterministic_extractor import PDFDeterministicExtractor
from recursive_pr_engine import RecursivePREngine
from ec_engine_orchestrator import ECEngineOrchestrator


class EngineALabHandler(SimpleHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html"]:
            with open(UI_FILE, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path == "/api/hierarchy":
            content = b"[]"
            if os.path.exists(HIERARCHY_FILE):
                with open(HIERARCHY_FILE, "rb") as f:
                    content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path.startswith("/runs/"):
            # Serve files from output/engine_a_output
            rel_path = path[len("/runs/"):].strip("/")
            file_path = os.path.abspath(os.path.join(OUTPUT_DIR, rel_path))
            # Security check
            if not file_path.startswith(os.path.abspath(OUTPUT_DIR)):
                self.send_error(403, "Forbidden")
                return
            if not os.path.exists(file_path):
                self.send_error(404, "File Not Found")
                return

            self.send_response(200)
            if file_path.endswith(".html"):
                self.send_header("Content-Type", "text/html; charset=utf-8")
            elif file_path.endswith(".json"):
                self.send_header("Content-Type", "application/json; charset=utf-8")
            elif file_path.endswith(".pdf"):
                self.send_header("Content-Type", "application/pdf")
            else:
                self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
            return

        elif path == "/api/run_ec_engine":
            qs = urllib.parse.parse_qs(parsed.query)
            folder_name = qs.get("folder", [""])[0]
            target_dir = os.path.join(OUTPUT_DIR, folder_name) if folder_name else ""
            if not target_dir or not os.path.exists(target_dir):
                resp = json.dumps({"success": False, "error": f"Folder not found: {folder_name}"}).encode('utf-8')
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                return

            try:
                res = ECEngineOrchestrator.run_for_engine_a_output(target_dir)
                dossier_rel = f"/runs/{folder_name}/ec_engine_full_trace/unified_title_dossier.html"
                ledger_rel = f"/runs/{folder_name}/ec_engine_full_trace/unified_master_property_ledger_1975_2026.json"
                resp_data = {
                    "success": True,
                    "folder": folder_name,
                    "total_unique_transactions": res["master_ledger"]["total_unique_transactions"],
                    "lineage_deeds_confirmed": res["master_ledger"]["lineage_deeds_confirmed"],
                    "adverse_transactions": res["master_ledger"]["adverse_transactions_count"],
                    "high_risk_alerts": res["master_ledger"]["high_risk_alerts_count"],
                    "unsatisfied_mortgages": res["master_ledger"]["unsatisfied_mortgages_count"],
                    "dossier_url": dossier_rel,
                    "ledger_url": ledger_rel,
                    "master_ec_pdf_url": f"/runs/{folder_name}/ec_engine_full_trace/downloaded_ec_pdfs/Master_Property_EC_1975_2026.pdf",
                    "master_ec_json_url": f"/runs/{folder_name}/ec_engine_full_trace/downloaded_ec_pdfs/Master_Property_EC_1975_2026_detailed_extraction.json"
                }
                resp_bytes = json.dumps(resp_data).encode('utf-8')
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_bytes)))
                self.end_headers()
                self.wfile.write(resp_bytes)
            except Exception as e:
                resp = json.dumps({"success": False, "error": str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        elif path == "/api/open_folder":
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("path", [""])[0]
            if target and os.path.exists(target):
                try:
                    os.startfile(target)
                except Exception as e:
                    print(f"Error opening folder: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return

        elif path == "/api/open_output_root":
            try:
                os.startfile(OUTPUT_DIR)
            except Exception:
                pass
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/extract":
            self.handle_extract()
            return
        self.send_error(404, "Not Found")

    def handle_extract(self):
        try:
            # Parse multipart form data
            ctype, pdict = cgi.parse_header(self.headers.get('content-type'))
            if ctype != 'multipart/form-data':
                self.send_error(400, "Expected multipart/form-data")
                return

            pdict['boundary'] = bytes(pdict['boundary'], "utf-8")
            pdict['CONTENT-LENGTH'] = int(self.headers.get('content-length', 0))

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers['content-type'],
                }
            )

            sro_id = form.getvalue('sro_id', '').strip()
            sro_name = form.getvalue('sro_name', '').strip()
            doc_no = form.getvalue('doc_no', '').strip()
            year = form.getvalue('year', '').strip()
            book_no = form.getvalue('book_no', '1').strip()

            logs = []
            def _log(msg):
                logs.append(msg)
                print(msg)

            # Create specific run directory
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            sro_clean = "".join(c for c in sro_name if c.isalnum() or c in (' ', '_')).replace(' ', '_')
            run_folder_name = f"run_{ts}_Doc_{doc_no}_{year}_{sro_clean}"
            run_folder = os.path.join(OUTPUT_DIR, run_folder_name)
            os.makedirs(run_folder, exist_ok=True)

            _log(f"\n=======================================================")
            _log(f"ENGINE A TESTING RUN: Doc {doc_no}/{year} at SRO {sro_name}")
            _log(f"Run output directory: {run_folder}")
            _log(f"=======================================================")

            # Check for PDF deed upload
            pdf_path = ""
            if 'pdf_file' in form:
                file_item = form['pdf_file']
                if file_item.filename:
                    saved_pdf = os.path.join(run_folder, f"uploaded_deed_{file_item.filename}")
                    with open(saved_pdf, 'wb') as f:
                        f.write(file_item.file.read())
                    pdf_path = saved_pdf
                    _log(f"[+] Saved uploaded deed PDF: {saved_pdf}")

            # 1. Execute live TNREGINET query & automatic official PDF download
            portal_result = EngineACore.fetch_portal_document(
                sro_id=sro_id,
                sro_name=sro_name,
                doc_no=doc_no,
                year=year,
                book_no=book_no,
                run_folder=run_folder,
                log_callback=_log
            )

            # 2. Determine effective PDF to parse (Downloaded Official Government EC PDF takes precedence)
            effective_pdf = portal_result.get("official_pdf_saved") or pdf_path
            pdf_result = {}
            if effective_pdf and os.path.exists(effective_pdf):
                _log(f"[*] Executing deep deterministic extraction on: {os.path.basename(effective_pdf)}...")
                pdf_result = PDFDeterministicExtractor.extract_from_pdf(effective_pdf, doc_no, year, sro_name)
                if pdf_result.get("success"):
                    ent = pdf_result["entries"][0]
                    _log(f"[+] Deep extraction succeeded! Discovered {len(ent['parties']['executants'])} Executant(s), {len(ent['parties']['claimants'])} Claimant(s), PRs: {ent['pr_lineage']['pr_raw'] or 'None'}")
                    if ent.get("schedules"):
                        s = ent["schedules"][0]
                        _log(f"[+] Boundaries parsed: East='{s['boundaries']['east'][:30]}...', North='{s['boundaries']['north'][:30]}...'")
                        if s["planning_approval"]["regularization_order"]:
                            _log(f"[+] Planning Approval identified: {s['planning_approval']['regularization_order']}")
                        if s["planning_approval"]["panchayat_approval"]:
                            _log(f"[+] Panchayat Approval identified: {s['planning_approval']['panchayat_approval']}")
                else:
                    _log(f"[-] PDF parsing notice: {pdf_result.get('error')}")

            # 3. If recursive PR discovery requested, execute full BFS chain
            run_recursive = form.getvalue('run_recursive', 'true').lower() == 'true'
            lineage_result = {}
            if run_recursive and portal_result.get("success"):
                _log("\n[*] Triggering 50-Year Recursive PR Lineage Traversal...")
                lineage_result = RecursivePREngine.execute_lineage_discovery(
                    root_doc_no=doc_no,
                    root_year=year,
                    root_sro_id=sro_id,
                    root_sro_name=sro_name,
                    district_id=form.getvalue('district_id', ''),
                    run_folder=run_folder,
                    log_callback=_log
                )
                _log(f"[+] Lineage traversal finished: {lineage_result.get('total_deeds_discovered', 1)} total deeds resolved across {lineage_result.get('lineage_depth', 0)} generations.")

            # 4. Trigger 1975–Present Comprehensive Property EC Engine
            ec_result = {}
            run_full_ec = form.getvalue('run_full_ec', 'true').lower() == 'true'
            if run_full_ec and (os.path.exists(os.path.join(run_folder, "deeds")) or os.path.exists(run_folder)):
                _log("\n[*] Triggering 1975–Present Comprehensive Property EC Engine...")
                try:
                    ec_res_data = ECEngineOrchestrator.run_for_engine_a_output(
                        engine_a_run_dir=run_folder,
                        log_callback=_log
                    )
                    ec_result = {
                        "success": True,
                        "total_unique_transactions": ec_res_data["master_ledger"]["total_unique_transactions"],
                        "lineage_deeds_confirmed": ec_res_data["master_ledger"]["lineage_deeds_confirmed"],
                        "adverse_transactions": ec_res_data["master_ledger"]["adverse_transactions_count"],
                        "high_risk_alerts": ec_res_data["master_ledger"]["high_risk_alerts_count"],
                        "unsatisfied_mortgages": ec_res_data["master_ledger"]["unsatisfied_mortgages_count"],
                        "dossier_relative_url": f"/runs/{run_folder_name}/ec_engine_full_trace/unified_title_dossier.html",
                        "ledger_relative_url": f"/runs/{run_folder_name}/ec_engine_full_trace/unified_master_property_ledger_1975_2026.json",
                        "master_ec_pdf_url": f"/runs/{run_folder_name}/ec_engine_full_trace/downloaded_ec_pdfs/Master_Property_EC_1975_2026.pdf",
                        "master_ec_json_url": f"/runs/{run_folder_name}/ec_engine_full_trace/downloaded_ec_pdfs/Master_Property_EC_1975_2026_detailed_extraction.json"
                    }
                    _log(f"[+] 1975-2026 Master Property Ledger compiled successfully!")
                except Exception as e_ec:
                    _log(f"[!] EC Engine notice: {e_ec}")

            # 5. Assemble and write the Dual JSON files
            # JSON 1: 01_portal_summary.json
            json1_file = os.path.join(run_folder, "01_portal_summary.json")
            with open(json1_file, "w", encoding="utf-8") as f:
                json.dump(portal_result, f, indent=2, ensure_ascii=False)
            _log(f"[+] 01_portal_summary.json saved: {json1_file}")

            # JSON 2: 02_pdf_detailed_extraction.json
            json2_file = os.path.join(run_folder, "02_pdf_detailed_extraction.json")
            with open(json2_file, "w", encoding="utf-8") as f:
                json.dump(pdf_result, f, indent=2, ensure_ascii=False)
            _log(f"[+] 02_pdf_detailed_extraction.json saved: {json2_file}")

            # Combined Master
            combined_data = {
                "success": portal_result.get("success", False),
                "timestamp": ts,
                "doc_identity": f"{doc_no}/{year}@{sro_name}",
                "output_folder": run_folder,
                "portal_data": portal_result,
                "pdf_data": pdf_result,
                "lineage_data": lineage_result,
                "ec_data": ec_result,
                "logs": logs,
                "json1_relative_url": f"/runs/{run_folder_name}/01_portal_summary.json",
                "json2_relative_url": f"/runs/{run_folder_name}/02_pdf_detailed_extraction.json",
                "lineage_graph_url": f"/runs/{run_folder_name}/master_lineage_graph.json" if lineage_result else "",
                "lineage_report_url": f"/runs/{run_folder_name}/lineage_tree_report.html" if lineage_result else "",
                "ec_dossier_url": ec_result.get("dossier_relative_url", ""),
                "ec_ledger_url": ec_result.get("ledger_relative_url", ""),
                "report_relative_url": f"/runs/{run_folder_name}/engine_a_inspection_report.html",
                "raw_html_relative_url": f"/runs/{run_folder_name}/00_TNREGINET_Direct_Doc_Search_Result.html" if portal_result.get("raw_html_saved") else "",
                "pdf_relative_url": f"/runs/{run_folder_name}/{os.path.basename(effective_pdf)}" if effective_pdf else ""
            }

            # Master JSON
            json_file = os.path.join(run_folder, "extracted_data.json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(combined_data, f, indent=2, ensure_ascii=False)
            _log(f"[+] Complete extraction JSON saved: {json_file}")

            # 5. Generate Inspection HTML report
            report_file = os.path.join(run_folder, "engine_a_inspection_report.html")
            EngineACore.generate_html_report(combined_data, report_file)
            _log(f"[+] Inspection HTML report generated: {report_file}")

            # Send JSON response
            resp_bytes = json.dumps(combined_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)

        except Exception as e:
            err_msg = f"Error in handle_extract: {e}"
            print(err_msg)
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))


def run_server(port=5050):
    server_address = ('127.0.0.1', port)
    httpd = ThreadingHTTPServer(server_address, EngineALabHandler)
    print(f"\n=======================================================")
    print(f"🚀 Engine A Standalone Testing Lab Running!")
    print(f"👉 Local URL: http://localhost:{port}")
    print(f"📁 Output Dir: {OUTPUT_DIR}")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == '__main__':
    run_server(5050)
