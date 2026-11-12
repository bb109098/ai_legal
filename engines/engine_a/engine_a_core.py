"""
engine_a_core.py - Core Engine A: Target Document Particulars Ingestion
========================================================================
Standalone, robust extraction engine for TNREGINET Target Documents.
- Live TNREGINET searchDocPropertyDtls query with automated captcha solving.
- Exhaustive parsing of government portal response (all schedules, villages, survey numbers, property types).
- Bilingual Tamil/English deed PDF parsing (parties, boundaries, extents, PR references).
- Ground truth verification & audit logging without hallucinated placeholders.
"""

import os
import sys
import re
import json
import time
import datetime
import warnings
from typing import Dict, List, Any, Optional, Tuple
import requests
import urllib3
from bs4 import BeautifulSoup
import pypdf

warnings.filterwarnings('ignore')
urllib3.disable_warnings()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


class EngineACore:
    """Standalone Target Document Extractor for Engine A."""

    BASE_URL = "https://tnreginet.gov.in/portal/webHP"
    DOC_SEARCH_URL = (
        "https://tnreginet.gov.in/portal/webHP?"
        "requestType=ApplicationRH&actionVal=openDocumentSearch"
        "&screenId=8400001&scenarioId=1&menuCode=8400008&auditUSFlag=true&UserLocaleID=en"
    )
    CAPTCHA_URL = "https://tnreginet.gov.in/portal/SimpleCaptcha"

    @classmethod
    def create_session(cls) -> Tuple[requests.Session, str]:
        """Initializes a new session and extracts the CSRF token from the document search page."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ta;q=0.8',
            'X-Requested-With': 'XMLHttpRequest'
        })
        resp = session.get(cls.DOC_SEARCH_URL, verify=False, timeout=20)
        csrf_m = re.search(r"var\s+csrf\s*=\s*['\"]([a-f0-9\-]+)['\"]", resp.text)
        csrf = csrf_m.group(1) if csrf_m else ""
        return session, csrf

    @classmethod
    def solve_captcha(cls, session: requests.Session, csrf: str, max_attempts: int = 10, log_callback=None) -> Optional[str]:
        """Solves SimpleCaptcha using local RapidOCR and verifies with actionVal=checkCaptcha."""
        try:
            from rapidocr_onnxruntime import RapidOCR
            import cv2
            import numpy as np
        except ImportError as e:
            if log_callback: log_callback(f"[!] OCR dependency missing: {e}")
            return None

        ocr = RapidOCR()
        for attempt in range(1, max_attempts + 1):
            try:
                if log_callback: log_callback(f"[*] Captcha attempt {attempt}/{max_attempts}...")
                cap_resp = session.get(cls.CAPTCHA_URL, verify=False, timeout=10)
                if cap_resp.status_code != 200:
                    continue
                
                nparr = np.frombuffer(cap_resp.content, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    continue

                scaled = cv2.resize(img, (img.shape[1] * 3, img.shape[0] * 3), interpolation=cv2.INTER_CUBIC)
                gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
                _, bin_inv = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)

                for prep in [scaled, gray, bin_inv]:
                    res, _ = ocr(prep, use_det=False)
                    if res and res[0]:
                        raw_cand = res[0][0]
                        clean_cand = re.sub(r'[^a-zA-Z0-9]', '', raw_cand)
                        for c in [clean_cand, clean_cand.upper(), clean_cand.lower()]:
                            if len(c) < 4:
                                continue
                            check_url = (
                                f"{cls.BASE_URL}?requestType=ApplicationRH&actionVal=checkCaptcha"
                                f"&queryType=Select&screenId=114&captcha_val={c}"
                            )
                            c_res = session.post(check_url, data={'_csrf': csrf}, verify=False, timeout=8)
                            if '#true' in c_res.text:
                                if log_callback: log_callback(f"[+] Captcha verified successfully: '{c}' (Attempt {attempt})")
                                return c
            except Exception as e:
                if log_callback: log_callback(f"[-] Captcha error: {e}")
                pass
        return None

    @classmethod
    def fetch_portal_document(
        cls,
        sro_id: str,
        sro_name: str,
        doc_no: str,
        year: str,
        book_no: str = "1",
        run_folder: str = "",
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Executes live query against TNREGINET searchDocPropertyDtls.
        Returns parsed results and saves raw government HTML.
        """
        result = {
            "success": False,
            "source": "TNREGINET_LIVE_PORTAL",
            "doc_no": str(doc_no).strip(),
            "year": str(year).strip(),
            "sro_id": str(sro_id).strip(),
            "sro_name": str(sro_name).strip(),
            "book_no": str(book_no).strip(),
            "timestamp": datetime.datetime.now().isoformat(),
            "total_records_found": 0,
            "schedules": [],
            "survey_numbers": [],
            "villages": [],
            "raw_html_saved": "",
            "logs": [],
            "error": None
        }

        def _log(msg: str):
            result["logs"].append(msg)
            if log_callback: log_callback(msg)
            print(msg)

        _log(f"[*] Initializing TNREGINET session for Doc {doc_no}/{year} at SRO '{sro_name}' ({sro_id})...")

        try:
            session, csrf = cls.create_session()
            if not csrf:
                _log("[-] Failed to obtain CSRF token from portal.")
                result["error"] = "CSRF_TOKEN_MISSING"
                return result

            captcha_code = cls.solve_captcha(session, csrf, log_callback=_log)
            if not captcha_code:
                _log("[-] Captcha solving failed after maximum attempts.")
                result["error"] = "CAPTCHA_SOLVE_FAILED"
                return result

            payload = {
                'requestType': 'ApplicationRH',
                'actionVal': 'searchDocPropertyDtls',
                'screenId': '8400001',
                'browserDetails': 'None',
                'documentNo': str(doc_no),
                'menuCode': '',
                'captcha_val': captcha_code,
                'txt_Captcha': captcha_code,
                'propertyNos': '',
                'surveyNos': '',
                'surveyNosList': '',
                'landPropertyDtsListData': '',
                'isECValid': 'N',
                'tmpltMstID': '84',
                'previewFlagFrmCnfg': 'true',
                'landDocIndexId': '',
                'docCreateAppId': '8400001',
                'appTransId': '0',
                'backUrl': '',
                'templateIds': '',
                'sroId': str(sro_id),
                'strSroName': str(sro_name),
                'year': str(year),
                'docNo': str(doc_no),
                'loggedInGuest': 'false',
                'jsonString': '',
                'viewECDocWise': 'true',
                'viewPrECDocWise': 'false',
                'authToken': '',
                'SROName': '',
                'cmb_SroName': str(sro_id),
                'txt_DocumentNo': str(doc_no),
                'cmb_Year': str(year),
                'sub_book_no': str(book_no),
                'cmb_doc_type': str(book_no),
                'countNoRecords': '0',
                'isPlotFlatWise': 'false',
                '_csrf': csrf
            }

            _log(f"[*] Submitting searchDocPropertyDtls (Book {book_no})...")
            post_resp = session.post(cls.BASE_URL, data=payload, verify=False, timeout=30)
            raw_html = post_resp.text

            # Check if records were found
            soup = BeautifulSoup(raw_html, 'html.parser')
            tables = soup.find_all('table')

            # If Book 1 had 0 records and book_no was 1, attempt Book 4 fallback
            is_empty = not tables or len(tables[0].find_all('tr')) <= 1
            if is_empty and book_no == "1":
                _log("[*] No records found in Book 1 (Regular Deeds). Checking Book 4 (POA / Will / Trust deeds)...")
                payload['sub_book_no'] = '4'
                payload['cmb_doc_type'] = '4'
                post_resp_b4 = session.post(cls.BASE_URL, data=payload, verify=False, timeout=25)
                soup_b4 = BeautifulSoup(post_resp_b4.text, 'html.parser')
                tables_b4 = soup_b4.find_all('table')
                if tables_b4 and len(tables_b4[0].find_all('tr')) > 1:
                    _log("[+] Found document records in Book 4!")
                    raw_html = post_resp_b4.text
                    soup = soup_b4
                    tables = tables_b4
                    result["book_no"] = "4"
                    is_empty = False

            # Save raw HTML response
            if run_folder:
                os.makedirs(run_folder, exist_ok=True)
                raw_path = os.path.join(run_folder, "00_TNREGINET_Direct_Doc_Search_Result.html")
                with open(raw_path, "w", encoding="utf-8") as f:
                    f.write(raw_html)
                result["raw_html_saved"] = raw_path
                _log(f"[+] Raw server HTML response saved to: {raw_path}")

            if is_empty:
                _log(f"[-] TNREGINET reported 0 property records for Doc {doc_no}/{year} at SRO {sro_name}.")
                result["total_records_found"] = 0
                result["error"] = "NO_RECORDS_FOUND"
                return result

            # Parse Table Rows
            rows = tables[0].find_all('tr')
            _log(f"[+] Found {len(rows) - 1} table row(s) in portal response.")
            
            schedules = []
            survey_set = set()
            village_set = set()

            for r_idx, row in enumerate(rows[1:], start=1):
                cols = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                if len(cols) >= 6:
                    sr_no = cols[0]
                    sro_val = cols[1]
                    dist_val = cols[2]
                    vil_val = cols[3]
                    sur_val = cols[4]
                    prop_type = cols[5]

                    if vil_val:
                        village_set.add(vil_val)
                    if sur_val:
                        survey_set.add(sur_val)

                    sched_entry = {
                        "schedule_index": r_idx,
                        "sr_no": sr_no,
                        "sro_office": sro_val,
                        "district": dist_val,
                        "village": vil_val,
                        "survey_subdivision_raw": sur_val,
                        "survey_numbers_parsed": cls._parse_survey_string(sur_val),
                        "property_type_raw": prop_type,
                        "plot_no": cls._extract_plot_number(prop_type)
                    }
                    schedules.append(sched_entry)

            result["success"] = True
            result["total_records_found"] = len(schedules)
            result["schedules"] = schedules
            result["survey_numbers"] = sorted(list(survey_set))
            result["villages"] = sorted(list(village_set))
            _log(f"[+] Successfully extracted {len(schedules)} schedule(s), {len(survey_set)} survey number(s), {len(village_set)} village(s).")

            # Attempt automated official Government EC PDF download
            if run_folder:
                downloaded_pdf = cls.download_official_ec_pdf(
                    session=session,
                    search_html=raw_html,
                    csrf=csrf,
                    run_folder=run_folder,
                    log_callback=_log
                )
                if downloaded_pdf:
                    result["official_pdf_saved"] = downloaded_pdf

            return result

        except Exception as e:
            _log(f"[!] Extraction exception: {e}")
            result["error"] = str(e)
            return result

    @classmethod
    def download_official_ec_pdf(
        cls,
        session: requests.Session,
        search_html: str,
        csrf: str,
        run_folder: str,
        log_callback=None
    ) -> Optional[str]:
        """
        Automatically triggers directPrintDwnLoad and downloads the official government EC PDF.
        Requires zero manual human upload.
        """
        def _log(msg):
            if log_callback: log_callback(msg)
            print(msg)

        try:
            soup = BeautifulSoup(search_html, 'html.parser')
            f_inputs = {i.get('name'): i.get('value', '') for i in soup.find_all('input') if i.get('name')}
            f_inputs.update({
                'requestType': 'ApplicationRH',
                'actionVal': 'directPrintDwnLoad',
                'screenId': '700786',
                'tmpltMstID': '8400004',
                '_csrf': csrf
            })

            _log("[*] Triggering directPrintDwnLoad to generate official Government EC PDF...")
            dl_resp = session.post(
                f"{cls.BASE_URL}?requestType=ApplicationRH&actionVal=directPrintDwnLoad&screenId=700786",
                data=f_inputs,
                verify=False,
                timeout=30
            )

            pdf_bytes = None
            if dl_resp.content.startswith(b'%PDF'):
                pdf_bytes = dl_resp.content
            else:
                m = re.search(r'href=[\'"]([^\'"]*actionVal=dwnLoadPdf[^\'"]*)[\'"]', dl_resp.text)
                if m:
                    pdf_rel = m.group(1).replace('&amp;', '&')
                    pdf_full_url = f"https://tnreginet.gov.in/portal/{pdf_rel}"
                    _log(f"[*] Downloading official government EC PDF binary from portal...")
                    pdf_resp = session.get(pdf_full_url, verify=False, timeout=30)
                    if pdf_resp.content.startswith(b'%PDF'):
                        pdf_bytes = pdf_resp.content

            if pdf_bytes:
                os.makedirs(run_folder, exist_ok=True)
                pdf_save_path = os.path.join(run_folder, "official_encumbrance_certificate.pdf")
                with open(pdf_save_path, "wb") as f:
                    f.write(pdf_bytes)
                _log(f"[+] Official Government EC PDF downloaded successfully: {pdf_save_path} ({len(pdf_bytes)} bytes)")
                return pdf_save_path
            else:
                _log("[-] Government portal did not return a valid PDF binary.")
                return None
        except Exception as e:
            _log(f"[!] Error downloading official PDF: {e}")
            return None

    @classmethod
    def extract_from_pdf(cls, pdf_path: str, doc_no: str, year: str, sro_name: str) -> Dict[str, Any]:
        """Deep bilingual Tamil/English extraction from physical/scanned deed PDF."""
        res = {
            "pdf_path": pdf_path,
            "parsed": False,
            "executants": [],
            "claimants": [],
            "dates": {},
            "nature": "",
            "consideration_value": None,
            "market_value": None,
            "pr_references": [],
            "boundaries": {},
            "extent": {},
            "raw_text_length": 0
        }

        if not os.path.exists(pdf_path):
            return res

        try:
            reader = pypdf.PdfReader(pdf_path)
            full_text = ""
            for idx, p in enumerate(reader.pages):
                txt = p.extract_text() or ""
                full_text += f"\n--- Page {idx+1} ---\n" + txt

            res["raw_text_length"] = len(full_text)
            res["parsed"] = True

            # 1. Dates
            dates_m = re.findall(r'([0-9]{1,2}\s*[\-\/\.]\s*[A-Za-z0-9]+\s*[\-\/\.]\s*[0-9]{4})', full_text)
            if dates_m:
                res["dates"]["execution"] = dates_m[0].replace(' ', '')
                if len(dates_m) > 1:
                    res["dates"]["registration"] = dates_m[1].replace(' ', '')

            # 2. Nature
            nat_m = re.search(r'(?:Nature|ஆவணத்தின்\s*தன்மை)[^\n\r]*[\:\-]?\s*([A-Za-z\u0B80-\u0BFF\s\/]+)', full_text)
            if nat_m:
                res["nature"] = nat_m.group(1).split('\n')[0].strip()

            # 3. Parties
            # Executants
            for m in re.finditer(r'(?:Executant|எழுதிக்\s*கொடுத்தவர்)[^\n\r]*[\:\-]?\s*([^\n\r]+)', full_text):
                val = m.group(1).strip()
                if len(val) > 2 and val not in res["executants"]:
                    res["executants"].append(val)
            # Claimants
            for m in re.finditer(r'(?:Claimant|எழுதி\s*வாங்கியவர்)[^\n\r]*[\:\-]?\s*([^\n\r]+)', full_text):
                val = m.group(1).strip()
                if len(val) > 2 and val not in res["claimants"]:
                    res["claimants"].append(val)

            # 4. Values
            con_m = re.search(r'(?:Consideration|கைமாற்றுத்\s*தொகை|கிரயத்\s*தொகை)[^\d]*([0-9\,\.]+)', full_text)
            if con_m:
                res["consideration_value"] = con_m.group(1).replace(',', '')

            mkt_m = re.search(r'(?:Market\s*Value|சந்தை\s*மதிப்பு)[^\d]*([0-9\,\.]+)', full_text)
            if mkt_m:
                res["market_value"] = mkt_m.group(1).replace(',', '')

            # 5. PR References
            pr_set = set()
            for m in re.finditer(r'(?:PR\s*No\.?|முந்தைய\s*ஆவண\s*எண்)[\s\/\:\-]*([0-9]+\s*[\/\-]\s*[12][09][0-9]{2})', full_text, re.I):
                cand = m.group(1).replace(' ', '')
                if cand != f"{doc_no}/{year}":
                    pr_set.add(cand)
            res["pr_references"] = sorted(list(pr_set))

            # 6. Directional Boundaries
            b_block_m = re.search(r'(?:எல்லை\s*விவரங்கள்|Boundary\s*Details)[\s\/\:\-]*([^\n\r]+(?:\n[^\n\r]+){1,4})', full_text)
            if b_block_m:
                b_text = b_block_m.group(1)
                res["boundaries"]["raw"] = re.sub(r'\s+', ' ', b_text).strip()
                s_m = re.search(r'தெற்கில்\s*([^,\,]+)', b_text)
                e_m = re.search(r'கிழக்கில்\s*([^,\,]+)', b_text)
                w_m = re.search(r'மேற்கில்\s*([^,\,]+)', b_text)
                n_m = re.search(r'வடக்கில்\s*([^,\,]+)', b_text)
                if s_m: res["boundaries"]["south"] = s_m.group(1).strip()
                if e_m: res["boundaries"]["east"] = e_m.group(1).strip()
                if w_m: res["boundaries"]["west"] = w_m.group(1).strip()
                if n_m: res["boundaries"]["north"] = n_m.group(1).strip()

            # 7. Extent
            ext_m = re.search(r'(?:Extent|விஸ்தீர்ணம்)[\s\/\:\-]*([0-9\.\,]+\s*[A-Za-z\u0B80-\u0BFF\s]+)', full_text)
            if ext_m:
                res["extent"]["raw"] = ext_m.group(1).split('\n')[0].strip()

            return res
        except Exception as e:
            res["error"] = str(e)
            return res

    @staticmethod
    def _parse_survey_string(sur_str: str) -> List[Dict[str, str]]:
        """Parses survey string e.g. '173/2H, 173/2J' into structured objects."""
        surveys = []
        clean = sur_str.replace(';', ',').replace(' ', '')
        for part in clean.split(','):
            part = part.strip()
            if not part:
                continue
            if '/' in part:
                s, sub = part.split('/', 1)
                surveys.append({"raw": part, "survey": s, "subdiv": sub})
            else:
                surveys.append({"raw": part, "survey": part, "subdiv": ""})
        return surveys

    @staticmethod
    def _extract_plot_number(prop_str: str) -> str:
        """Extracts plot number from property string."""
        m = re.search(r'Plot\s*(?:No\.?)?\s*([0-9]+[A-Za-z]?)', prop_str, re.I)
        if m:
            return m.group(1)
        m_tamil = re.search(r'மனை\s*எண்\s*([0-9]+[A-Za-z]?)', prop_str)
        if m_tamil:
            return m_tamil.group(1)
        return ""

    @classmethod
    def generate_html_report(cls, combined_data: Dict[str, Any], output_path: str):
        """Generates an executive, highly readable inspection HTML report for Engine A."""
        portal_data = combined_data.get("portal_data", {})
        pdf_data = combined_data.get("pdf_data", {})
        schedules = portal_data.get("schedules", [])

        sched_rows_html = ""
        for s in schedules:
            sched_rows_html += f"""
            <tr>
                <td style="padding:10px; border:1px solid #e2e8f0; text-align:center;">{s.get('schedule_index')}</td>
                <td style="padding:10px; border:1px solid #e2e8f0; font-weight:bold; color:#1e293b;">{s.get('village')}</td>
                <td style="padding:10px; border:1px solid #e2e8f0; font-family:monospace; font-size:1.1em; color:#0284c7;">{s.get('survey_subdivision_raw')}</td>
                <td style="padding:10px; border:1px solid #e2e8f0;">{s.get('property_type_raw')}</td>
                <td style="padding:10px; border:1px solid #e2e8f0;">{s.get('plot_no') or '—'}</td>
                <td style="padding:10px; border:1px solid #e2e8f0;">{s.get('sro_office')}</td>
            </tr>
            """

        if not sched_rows_html:
            sched_rows_html = "<tr><td colspan='6' style='padding:16px; text-align:center; color:#dc2626;'>No schedule entries found on government portal.</td></tr>"

        pdf_html_section = ""
        if pdf_data.get('success') and pdf_data.get('entries'):
            ent = pdf_data['entries'][0]
            exec_str = ", ".join([f"{p['name']} ({p.get('initial_verbatim','')})" if p.get('initial_verbatim') else p['name'] for p in ent['parties']['executants']]) or '—'
            claim_str = ", ".join([f"{p['name']} ({p.get('initial_verbatim','')})" if p.get('initial_verbatim') else p['name'] for p in ent['parties']['claimants']]) or '—'
            pr_str = ent['pr_lineage']['pr_raw'] or 'None explicitly cited'
            val_str = ent['financials']['consideration_value_raw'] or '—'
            mkt_str = ent['financials']['market_value_raw'] or '—'
            sched = ent['schedules'][0] if ent.get('schedules') else {}
            bnd = sched.get('boundaries', {})
            dims = sched.get('linear_dimensions', {})
            approvals = sched.get('planning_approval', {})
            patta = sched.get('patta_and_parent_land', {})

            pdf_html_section = f"""
            <div class="section">
                <div class="section-title">📄 Official Government EC PDF Deep Extraction (Pure Deterministic)</div>
                <div class="grid">
                    <div class="card">
                        <div class="card-label">Executant(s) (விற்பனையாளர்)</div>
                        <div class="card-value" style="color:#0369a1;">{exec_str}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Claimant(s) (வாங்குபவர்)</div>
                        <div class="card-value" style="color:#0f766e;">{claim_str}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Prior Title Deed (PR) Citation</div>
                        <div class="card-value" style="color:#d97706; font-family:monospace;">{pr_str}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Consideration & Market Value</div>
                        <div class="card-value">{val_str} / {mkt_str}</div>
                    </div>
                </div>

                <div class="grid" style="margin-top:16px;">
                    <div class="card">
                        <div class="card-label">Regularization / Planning Approval</div>
                        <div class="card-value">{approvals.get('regularization_order') or '—'}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Panchayat / Local Body Order</div>
                        <div class="card-value">{approvals.get('panchayat_approval') or '—'}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Patta & Parent Survey</div>
                        <div class="card-value">{'Patta No. ' + patta.get('patta_no') if patta.get('patta_no') else '—'} {' | Parent: ' + patta.get('parent_survey') if patta.get('parent_survey') else ''}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Plot Linear Dimensions</div>
                        <div class="card-value" style="font-size:13px;">EW North: {dims.get('east_west_north','—')} | EW South: {dims.get('east_west_south','—')} | NS East: {dims.get('north_south_east','—')} | NS West: {dims.get('north_south_west','—')}</div>
                    </div>
                </div>

                <div class="card" style="margin-top:16px;">
                    <div class="card-label">Four Directional Boundaries (நான்குமால் எல்லைகள்)</div>
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-top:8px;">
                        <div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:6px; padding:10px;">
                            <div style="font-size:11px; font-weight:700; color:#0284c7;">EAST (கிழக்கு)</div>
                            <div style="font-size:13px; margin-top:4px;">{bnd.get('east') or '—'}</div>
                        </div>
                        <div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:6px; padding:10px;">
                            <div style="font-size:11px; font-weight:700; color:#0284c7;">WEST (மேற்கு)</div>
                            <div style="font-size:13px; margin-top:4px;">{bnd.get('west') or '—'}</div>
                        </div>
                        <div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:6px; padding:10px;">
                            <div style="font-size:11px; font-weight:700; color:#0284c7;">NORTH (வடக்கு)</div>
                            <div style="font-size:13px; margin-top:4px;">{bnd.get('north') or '—'}</div>
                        </div>
                        <div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:6px; padding:10px;">
                            <div style="font-size:11px; font-weight:700; color:#0284c7;">SOUTH (தெற்கு)</div>
                            <div style="font-size:13px; margin-top:4px;">{bnd.get('south') or '—'}</div>
                        </div>
                    </div>
                </div>

                <div class="card" style="margin-top:16px;">
                    <div class="card-label">Full Stitched Schedule Remarks (குறிப்புரை)</div>
                    <div style="font-size:13px; line-height:1.6; color:#334155; margin-top:6px; word-break:break-word;">
                        {sched.get('schedule_remarks_full') or '—'}
                    </div>
                </div>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Engine A Target Deed Inspection | Doc {portal_data.get('doc_no')}/{portal_data.get('year')}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background:#f8fafc; color:#1e293b; margin:0; padding:24px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background:#ffffff; border-radius:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.1); border:1px solid #e2e8f0; overflow:hidden; }}
        .header {{ background:#0f172a; color:#ffffff; padding:24px 32px; display:flex; justify-content:space-between; align-items:center; }}
        .badge {{ background:#0284c7; color:#ffffff; padding:4px 12px; border-radius:16px; font-size:12px; font-weight:bold; text-transform:uppercase; }}
        .badge.success {{ background:#16a34a; }}
        .badge.warn {{ background:#eab308; color:#000; }}
        .badge.fail {{ background:#dc2626; }}
        .section {{ padding:24px 32px; border-bottom:1px solid #f1f5f9; }}
        .section-title {{ font-size:16px; font-weight:bold; color:#334155; margin-bottom:16px; text-transform:uppercase; letter-spacing:0.5px; display:flex; align-items:center; gap:8px; }}
        .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:16px; }}
        .card {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:14px; }}
        .card-label {{ font-size:12px; color:#64748b; text-transform:uppercase; margin-bottom:4px; }}
        .card-value {{ font-size:15px; font-weight:600; color:#0f172a; word-break:break-word; }}
        table {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:14px; }}
        th {{ background:#f1f5f9; color:#475569; font-weight:600; text-align:left; padding:10px; border:1px solid #e2e8f0; }}
        .source-tag {{ font-size:11px; padding:2px 8px; border-radius:4px; font-weight:600; display:inline-block; }}
        .source-portal {{ background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; }}
        .source-pdf {{ background:#fef3c7; color:#92400e; border:1px solid #fde68a; }}
        .footer {{ background:#f8fafc; padding:16px 32px; font-size:12px; color:#94a3b8; text-align:right; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1 style="margin:0; font-size:22px;">Engine A: Target Document Particulars Ingestion</h1>
                <div style="font-size:14px; color:#94a3b8; margin-top:4px;">Official Tamil Nadu Registration Department Audit Verification</div>
            </div>
            <div>
                <span class="badge {'success' if portal_data.get('success') else 'fail'}">
                    {'VERIFIED RECORD' if portal_data.get('success') else 'NO RECORD FOUND'}
                </span>
            </div>
        </div>

        <div class="section">
            <div class="section-title">📌 Registered Particulars</div>
            <div class="grid">
                <div class="card">
                    <div class="card-label">Document Number & Year</div>
                    <div class="card-value">{portal_data.get('doc_no')} / {portal_data.get('year')}</div>
                </div>
                <div class="card">
                    <div class="card-label">Sub-Registrar Office</div>
                    <div class="card-value">{portal_data.get('sro_name')} ({portal_data.get('sro_id')})</div>
                </div>
                <div class="card">
                    <div class="card-label">Book Type</div>
                    <div class="card-value">Book {portal_data.get('book_no')} ({'Regular Conveyance' if portal_data.get('book_no')=='1' else 'POA / Miscellaneous'})</div>
                </div>
                <div class="card">
                    <div class="card-label">Total Schedules Discovered</div>
                    <div class="card-value" style="color:#0284c7;">{portal_data.get('total_records_found')} Property Entries</div>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">🏛️ Government Portal Extracted Schedules (Raw Ground Truth)</div>
            <table>
                <thead>
                    <tr>
                        <th style="text-align:center;">#</th>
                        <th>Village (கிராமம்)</th>
                        <th>Survey / Sub-Div (புல எண்)</th>
                        <th>Property Classification</th>
                        <th>Plot / Flat No</th>
                        <th>Registered SRO</th>
                    </tr>
                </thead>
                <tbody>
                    {sched_rows_html}
                </tbody>
            </table>
        </div>

        {pdf_html_section}

        <div class="section">
            <div class="section-title">🔍 Verification Provenance & Audit Artifacts</div>
            <div class="card">
                <div class="card-label">Raw Portal Response File</div>
                <div class="card-value" style="font-family:monospace; font-size:12px;">{portal_data.get('raw_html_saved') or 'Not Generated'}</div>
            </div>
        </div>

        <div class="footer">
            Generated deterministically by Engine A Standalone Lab | Execution: {portal_data.get('timestamp')}
        </div>
    </div>
</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
