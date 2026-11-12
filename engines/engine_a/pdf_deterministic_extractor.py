"""
pdf_deterministic_extractor.py - Pure Python Deterministic Extractor for TNREGINET EC PDFs
========================================================================================
Exhaustively extracts all structured fields from official Tamil Nadu Encumbrance Certificate PDFs:
- Zero LLM dependency: 100% deterministic, rules & pattern-based.
- Multi-Schedule support: seamlessly extracts Schedule 1, Schedule 2, Schedule 3, etc.
- Multi-page continuation stitching across page breaks (Schedule Table, Boundaries, Remarks).
- Combined column handling: splits 'Survey No-Extent' into distinct Survey and Extent values.
- Multi-party mapping: separates multiple Executants (Sellers) and Claimants (Buyers) via index reset.
- Universal deed nature detection: supports both English and Tamil natures (e.g. Partition, Receipt, MODTD).
- Bounded Schedule Parsing: Prevents boundary or remarks text from polluting schedule fields (e.g. plot_no).
- Comprehensive Flat/Apartment Table Structure: New Door No, Old Door No, Floor No, Block No, UDS, Super Built-up Area.
- Directional Boundaries: supports full Tamil words, inflections (கிழக்கில், மேற்கில், வடக்கில், தெற்கில்), and shorthands ((வ), (தெ), (கி), (மே)).
- Verbatim Tamil initials preservation (e.g. 'ரா.' or 'R.' never transliterated or distorted).
- Entity categorization (Individual vs Organization/Bank/Temple).
- Linear Plot Dimensions (East-West North/South, North-South East/West, Sq.Ft, Sq.M).
- Planning & Regularization citations (DLP, DTCP, CMDA, Panchayat order numbers and dates).
- Patta & Revenue Subdivisions (Patta No, TSLR, Parent Survey, Subdivided SFs).
"""

import os
import sys
import re
import json
import datetime
from typing import Dict, List, Any, Optional, Tuple
import pypdf
import pdfplumber

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class PDFDeterministicExtractor:
    """Deterministic extractor for official TNREGINET Certificate of Encumbrance PDFs."""

    ORGANIZATION_KEYWORDS = [
        "bank", "வங்கி", "limited", "லிமிடெட்", "லிமிெடட்", "ltd", "pvt", "பிரைவேட்", "private",
        "company", "கம்பெனி", "நிறுவனம்", "society", "சங்க", "trust", "டிரஸ்ட்",
        "temple", "கோயில்", "திருக்கோயில்", "அருள்மிகு", "செயலர்", "அலுவலர்",
        "corporation", "கார்ப்பரேஷன்", "board", "வாரியம்", "housing", "promoters", "builders"
    ]

    @staticmethod
    def normalize_tamil_unicode(text: str) -> str:
        """
        Normalizes legacy Tamil font glyph sequences:
        Swaps pre-vowel signs (\u0BC6, \u0BC7, \u0BC8) placed before consonants (\u0B95-\u0BB9)
        so that standard Unicode ordering (consonant + vowel sign) is maintained.
        e.g. 'ேமற்கு' -> 'மேற்கு', 'ெதற்கு' -> 'தெற்கு', 'ேராடு' -> 'ரோடு'.
        """
        if not text:
            return ""
        return re.sub(r'([\u0BC6\u0BC7\u0BC8])([\u0B95-\u0BB9])', r'\2\1', text)

    @classmethod
    def extract_from_pdf(cls, pdf_path: str, fallback_doc_no: str = "", fallback_year: str = "", fallback_sro: str = "") -> Dict[str, Any]:
        """
        Parses an official TNREGINET Certificate of Encumbrance PDF deterministically.
        Returns exhaustive structured data conforming to the official schema.
        """
        result = {
            "success": False,
            "pdf_source": pdf_path,
            "document_metadata": {},
            "entries": [],
            "raw_text_by_page": [],
            "error": None
        }

        if not os.path.exists(pdf_path):
            result["error"] = f"File not found: {pdf_path}"
            return result

        try:
            reader = pypdf.PdfReader(pdf_path)
            all_lines: List[str] = []

            for idx, p in enumerate(reader.pages):
                raw_page = p.extract_text() or ""
                cleaned_page = raw_page.replace('\xa0', ' ').replace('\r\n', '\n')
                lines = [l.strip() for l in cleaned_page.split('\n') if l.strip()]
                all_lines.extend(lines)
                result["raw_text_by_page"].append({
                    "page_number": idx + 1,
                    "line_count": len(lines),
                    "character_count": len(cleaned_page)
                })

            if not all_lines:
                result["error"] = "Empty PDF content"
                return result

            # Base Document Metadata
            metadata = cls._extract_metadata(all_lines, fallback_doc_no, fallback_year, fallback_sro)
            result["document_metadata"] = metadata

            # 1. Check if this PDF contains a Multi-Entry Government Survey EC (e.g. APP_8400001_... or Survey Details in header)
            is_survey_ec = any("Survey Details" in l or "சர்ேவ விவரம்" in l or "சர்வே விவரம்" in l for l in all_lines[:35])
            if is_survey_ec:
                survey_entries = cls._extract_survey_ec_entries(pdf_path, fallback_sro or metadata.get("sro_name", ""))
                if survey_entries:
                    # Also check if any standalone deed ECs were appended at the end
                    seen_docs = {e["registration_particulars"]["document_id"] for e in survey_entries if e.get("registration_particulars", {}).get("document_id")}
                    doc_splits = []
                    for p_idx, p in enumerate(reader.pages):
                        p_text = p.extract_text() or ""
                        # Only look for standalone deed header (not survey table entries)
                        if "Document No.& Year" in p_text and "Survey Details" not in p_text[:200]:
                            m = re.search(r'Document No\.\& Year[^\:]*[\:\-]\s*([0-9]+\s*\/\s*[0-9]{4})', p_text)
                            if m:
                                d_id = m.group(1).replace(' ', '')
                                if d_id not in seen_docs:
                                    doc_splits.append((p_idx, d_id))
                    
                    if doc_splits:
                        page_texts = [p.extract_text() or "" for p in reader.pages]
                        for idx, (p_idx, d_id) in enumerate(doc_splits):
                            end_p = doc_splits[idx+1][0] if idx+1 < len(doc_splits) else len(page_texts)
                            doc_lines = []
                            for p in range(p_idx, end_p):
                                cl = page_texts[p].replace('\xa0', ' ').replace('\r\n', '\n')
                                doc_lines.extend([l.strip() for l in cl.split('\n') if l.strip()])
                            parts = d_id.split('/')
                            m_meta = cls._extract_metadata(doc_lines, parts[0], parts[1], fallback_sro)
                            ent = cls._parse_entry(doc_lines, m_meta, pdf_path=pdf_path)
                            if ent:
                                ent["entry_index"] = len(survey_entries) + 1
                                survey_entries.append(ent)
                                seen_docs.add(d_id)

                    result["entries"] = survey_entries
                    result["document_metadata"]["total_entries_count"] = len(survey_entries)
                    result["success"] = True
                    return result

            # 2. Check for multiple standalone document certificates in merged EC PDF
            doc_splits = []
            for p_idx, p in enumerate(reader.pages):
                p_text = p.extract_text() or ""
                m = re.search(r'Document No\.\& Year[^\:]*[\:\-]\s*([0-9]+\s*\/\s*[0-9]{4})', p_text)
                if m:
                    doc_splits.append((p_idx, m.group(1).replace(' ', '')))

            if len(doc_splits) > 1:
                page_texts = [p.extract_text() or "" for p in reader.pages]
                multi_entries = []
                for idx, (p_idx, d_id) in enumerate(doc_splits):
                    end_p = doc_splits[idx+1][0] if idx+1 < len(doc_splits) else len(page_texts)
                    doc_lines = []
                    for p in range(p_idx, end_p):
                        cl = page_texts[p].replace('\xa0', ' ').replace('\r\n', '\n')
                        doc_lines.extend([l.strip() for l in cl.split('\n') if l.strip()])
                    parts = d_id.split('/')
                    m_meta = cls._extract_metadata(doc_lines, parts[0], parts[1], fallback_sro)
                    ent = cls._parse_entry(doc_lines, m_meta, pdf_path=pdf_path, start_page=p_idx)
                    if ent:
                        multi_entries.append(ent)
                if multi_entries:
                    result["entries"] = multi_entries
                    result["success"] = True
                    first_meta = cls._extract_metadata(all_lines, fallback_doc_no, fallback_year, fallback_sro)
                    first_meta["total_entries_count"] = len(multi_entries)
                    result["document_metadata"] = first_meta
                    return result

            # 2. Extract Entry with multi-schedule support
            entry_data = cls._parse_entry(all_lines, metadata, pdf_path=pdf_path)
            if entry_data and entry_data.get("registration_particulars", {}).get("document_number"):
                result["entries"] = [entry_data]
                result["success"] = True
            else:
                # Fallback to survey extraction if standard parser returned no valid doc
                survey_entries = cls._extract_survey_ec_entries(pdf_path, fallback_sro or metadata.get("sro_name", ""))
                if survey_entries:
                    result["entries"] = survey_entries
                    result["document_metadata"]["total_entries_count"] = len(survey_entries)
                    result["success"] = True
                else:
                    result["error"] = "No registered entry parsed from PDF"

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    @staticmethod
    def _parse_extent_dict(ext_str: str) -> Dict[str, Any]:
        if not ext_str:
            return {"raw": "", "sqft": 0.0, "sq_meters": 0.0}
        clean_ext = ext_str.strip()
        nums = re.findall(r'[0-9]+(?:\.[0-9]+)?', clean_ext)
        val = float(nums[0]) if nums else 0.0
        if any(k in clean_ext.lower() for k in ["acre", "ஏக்கர்"]):
            sqft = round(val * 43560.0, 2)
        elif any(k in clean_ext.lower() for k in ["cent", "சென்ட்"]):
            sqft = round(val * 435.6, 2)
        elif any(k in clean_ext.lower() for k in ["sq.m", "sqm", "சதுர மீட்டர்"]):
            sqft = round(val / 0.092903, 2)
        else:
            sqft = val
        return {
            "raw": clean_ext,
            "sqft": sqft,
            "sq_meters": round(sqft * 0.092903, 2)
        }

    @staticmethod
    def _parse_survey_dict(sur_str: str) -> Dict[str, str]:
        if not sur_str:
            return {"raw": "", "survey": "", "subdivision": ""}
        s_clean = sur_str.split('-')[0].strip().strip(',')
        m = re.search(r'([0-9]+)\s*[\/\-]\s*([0-9A-Za-z]+(?:\s*,\s*[0-9A-Za-z]+)?)', s_clean)
        if m:
            return {"raw": s_clean, "survey": m.group(1).strip(), "subdivision": m.group(2).strip()}
        m2 = re.search(r'([0-9]+)', s_clean)
        if m2:
            return {"raw": s_clean, "survey": m2.group(1).strip(), "subdivision": ""}
        return {"raw": s_clean, "survey": "", "subdivision": ""}

    @classmethod
    def _extract_survey_ec_entries(cls, pdf_path: str, sro_fallback: str = "") -> List[Dict[str, Any]]:
        """
        Deterministically extracts all tabular transactions from a multi-entry Survey EC PDF
        with full multi-page continuation stitching and multi-schedule extraction.
        """
        entries = []
        all_table_rows = []

        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for p_idx, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    for t_idx, t in enumerate(tables):
                        if not t:
                            continue
                        # Page 1 Table 0 is the metadata box (SRO, Date, Village, Survey Details)
                        if p_idx == 0 and t_idx == 0 and len(t) <= 3 and any("Survey Details" in str(c) for r in t for c in r if c):
                            for r in t:
                                for c in r:
                                    if c and "S.R.O" in c and not sro_fallback:
                                        m_sro = re.search(r'S\.R\.O[^\:]*[\:\-]\s*([^\n\r]+)', c)
                                        if m_sro:
                                            sro_fallback = m_sro.group(1).strip()
                            continue

                        for row in t:
                            if not row or not any(row):
                                continue
                            row_str = " ".join([str(c) for c in row if c])
                            # Filter out repeated page header banners and column titles
                            if any(h in row_str for h in ["GOVERNMENT OF TAMILNADU", "REGISTRATION DEPARTMENT", "Certificate of Encumbrance"]):
                                continue
                            if any(h in row_str for h in ["Date of Execution & Date of Presentation", "Sr. No./", "Name of Executant(s)"]):
                                continue
                            if "Zone:" in row_str and "District:" in row_str and "S.R.O:" in row_str:
                                m_sro = re.search(r'S\.R\.O[\:\-]\s*([^\n\r]+)', row_str)
                                if m_sro and not sro_fallback:
                                    sro_fallback = m_sro.group(1).strip()
                                continue
                            all_table_rows.append(row)

            current_entry = None
            current_sched = None
            entry_idx = 1

            for r in all_table_rows:
                doc_cell = None
                for c in r[:3]:
                    if c and re.search(r'^\s*(\d{1,6})\s*/\s*(\d{4})\s*$', c.strip()):
                        doc_cell = c.strip()
                        break

                if doc_cell:
                    if current_entry:
                        if current_sched:
                            if not current_sched.get("plot_no"):
                                target_text = f"{current_sched.get('schedule_remarks_full', '')} {current_sched.get('boundaries', {}).get('raw', '')}"
                                p_fallback = re.search(r'(?:(?:மனை|மைன|பிளாட்)\s*(?:எண்|நெ|நம்பர்)?|Plot\s*(?:No\.?)?)\s*([0-9]+[A-Za-z]?)', target_text, re.I)
                                if p_fallback:
                                    current_sched["plot_no"] = p_fallback.group(1).strip()
                            current_entry["schedules"].append(current_sched)
                            current_sched = None
                        entries.append(current_entry)
                        entry_idx += 1

                    m_doc = re.search(r'(\d{1,6})\s*/\s*(\d{4})', doc_cell)
                    d_no = m_doc.group(1)
                    yr = m_doc.group(2)
                    dates_raw = r[2] if len(r) > 2 and r[2] else ""
                    dates_list = re.findall(r'\d{2}-[A-Za-z]{3}-\d{4}', dates_raw)

                    exec_list = []
                    if len(r) > 4 and r[4]:
                        for raw_e in r[4].split('\n'):
                            clean_e = re.sub(r'^[0-9\.\s]+', '', raw_e).strip()
                            if clean_e:
                                exec_list.append(cls._format_party_entry(clean_e))

                    claim_list = []
                    if len(r) > 5 and r[5]:
                        for raw_c in r[5].split('\n'):
                            clean_c = re.sub(r'^[0-9\.\s]+', '', raw_c).strip()
                            if clean_c:
                                claim_list.append(cls._format_party_entry(clean_c))

                    vol_page = r[6].strip() if len(r) > 6 and r[6] and r[6] != '-' else None

                    current_entry = {
                        "entry_index": entry_idx,
                        "registration_particulars": {
                            "document_number": d_no,
                            "registration_year": yr,
                            "document_id": f"{d_no}/{yr}",
                            "nature_of_deed": r[3].replace('\n', ' ').strip() if len(r) > 3 and r[3] else "",
                            "volume_no": vol_page,
                            "page_no": None,
                            "book_no": "1",
                            "sro_name": sro_fallback,
                            "dates": {
                                "execution_date": dates_list[0] if len(dates_list) > 0 else "",
                                "presentation_date": dates_list[1] if len(dates_list) > 1 else "",
                                "registration_date": dates_list[2] if len(dates_list) > 2 else (dates_list[0] if dates_list else "")
                            }
                        },
                        "financials": {
                            "consideration_value_raw": "-",
                            "consideration_value_num": 0.0,
                            "market_value_raw": "-",
                            "market_value_num": 0.0,
                            "currency": "INR"
                        },
                        "parties": {
                            "executants": exec_list,
                            "claimants": claim_list
                        },
                        "pr_lineage": {
                            "pr_raw": "",
                            "pr_documents": []
                        },
                        "schedules": []
                    }
                    current_sched = None
                elif current_entry:
                    # Parse row cells individually rather than flattening into a single space-separated string
                    # 1. Financials & PR (check cells in row)
                    for c in r:
                        if not c: continue
                        con_m = re.search(r'(?:Consideration\s*Value|ைகமாற்றுத்\s*ெதாைக|கைமாற்றுத்\s*தொகை)[^\:]*[\:\-]\s*Rs\.?\s*([0-9\,]+|\-)', c, re.I)
                        if con_m and con_m.group(1) != '-':
                            v_num = float(con_m.group(1).replace(',', ''))
                            current_entry["financials"]["consideration_value_raw"] = f"Rs. {con_m.group(1)}/-"
                            current_entry["financials"]["consideration_value_num"] = v_num

                        mkt_m = re.search(r'(?:Market\s*Value|சந்ைத\s*மதிப்பு|சந்தை\s*மதிப்பு)[^\:]*[\:\-]\s*Rs\.?\s*([0-9\,]+|\-)', c, re.I)
                        if mkt_m and mkt_m.group(1) != '-':
                            v_num = float(mkt_m.group(1).replace(',', ''))
                            current_entry["financials"]["market_value_raw"] = f"Rs. {mkt_m.group(1)}/-"
                            current_entry["financials"]["market_value_num"] = v_num

                        pr_m = re.search(r'(?:PR\s*Number|முந்ைதய\s*ஆவண\s*எண்|முந்தைய\s*ஆவண\s*எண்)[^\:]*[\:\-]\s*([^\n\r]+)', c, re.I)
                        if pr_m:
                            pr_val = pr_m.group(1).strip()
                            # A PR cell can wrap across several physical lines when a deed cites
                            # multiple parents (e.g. "1572/ 2007, 1644/\n2007, 1904/ 2007").
                            # Stitch the continuation lines of the same cell deterministically.
                            pr_full = cls._stitch_pr_cell_continuation(c[pr_m.start(1):])
                            if pr_full:
                                pr_val = pr_full
                            current_entry["pr_lineage"]["pr_raw"] = pr_val
                            current_entry["pr_lineage"]["pr_documents"] = cls._parse_pr_string(
                                pr_val, exclude_doc_id=current_entry["registration_particulars"].get("document_id", "")
                            )

                    # 2. Schedule Marker detection
                    for c in r:
                        if not c: continue
                        sm = re.search(r'(?:Schedule\s*([0-9]+)?\s*Details(?:\s*\(([^\)]*)\))?|அட்டவணை\s*([0-9]+)?\s*விவரங்கள்(?:\s*\(([^\)]*)\))?|அட்டவைண\s*([0-9]+)?\s*விவரங்கள்(?:\s*\(([^\)]*)\))?|Schedule\s*Details(?:\s*\(([^\)]*)\))?)', c, re.I)
                        if sm:
                            if current_sched:
                                if not current_sched.get("plot_no"):
                                    target_text = f"{current_sched.get('schedule_remarks_full', '')} {current_sched.get('boundaries', {}).get('raw', '')}"
                                    p_fallback = re.search(r'(?:(?:மனை|மைன|பிளாட்)\s*(?:எண்|நெ|நம்பர்)?|Plot\s*(?:No\.?)?)\s*([0-9]+[A-Za-z]?)', target_text, re.I)
                                    if p_fallback:
                                        current_sched["plot_no"] = p_fallback.group(1).strip()
                                current_entry["schedules"].append(current_sched)
                                current_sched = None
                            if "(After Rectification)" in c:
                                s_id = "Schedule Details (After Rectification)"
                            elif "(Before Rectification)" in c:
                                s_id = "Schedule 1 Details (Before Rectification)"
                            elif sm.group(1):
                                s_id = f"Schedule {sm.group(1)}"
                            else:
                                s_id = f"Schedule {len(current_entry['schedules']) + 1}"

                            current_sched = {
                                "schedule_id": s_id,
                                "property_type": "Plot",
                                "extent": {"raw": "", "sqft": 0.0, "sq_meters": 0.0},
                                "village": "",
                                "street": "",
                                "survey_number": {"raw": "", "survey": "", "subdivision": ""},
                                "plot_no": "",
                                "door_no": "",
                                "new_door_no": "",
                                "old_door_no": "",
                                "floor_no": "",
                                "flat_no": "",
                                "block_no": "",
                                "ward_no": "",
                                "boundaries": {"raw": "", "east": "", "west": "", "north": "", "south": ""},
                                "schedule_remarks_full": ""
                            }
                            break

                    if current_sched is None:
                        row_has_field = any(any(k in str(c) for k in ["Property Type", "Property Extent", "Survey No", "Village", "விஸ்தீர்ணம்", "புல எண்", "கிராமம்"]) for c in r if c)
                        if row_has_field:
                            current_sched = {
                                "schedule_id": f"Schedule {len(current_entry['schedules']) + 1}",
                                "property_type": "Plot",
                                "extent": {"raw": "", "sqft": 0.0, "sq_meters": 0.0},
                                "village": "",
                                "street": "",
                                "survey_number": {"raw": "", "survey": "", "subdivision": ""},
                                "plot_no": "",
                                "door_no": "",
                                "new_door_no": "",
                                "old_door_no": "",
                                "floor_no": "",
                                "flat_no": "",
                                "block_no": "",
                                "ward_no": "",
                                "boundaries": {"raw": "", "east": "", "west": "", "north": "", "south": ""},
                                "schedule_remarks_full": ""
                            }

                    is_field_row = False
                    if current_sched:
                        for c in r:
                            if not c: continue

                            # 1. Clean Property Type
                            pt_m = re.search(r'(?:Property\s*Type[\s\/]*(?:ெசாத்தின்\s*வைகப்பாடு|சொத்தின்\s*வகைப்பாடு)?|ெசாத்தின்\s*வைகப்பாடு|சொத்தின்\s*வகைப்பாடு)[\s\/\:\-]+([^\n\r]+?)(?=(?:Property\s*Extent|விஸ்தீர்ணம்|Survey\s*No|புல\s*எண்|Village|கிராமம்|\n|$))', c, re.I)
                            if pt_m:
                                pt_val = pt_m.group(1).strip(' ,-')
                                pt_val = re.sub(r'^(?:ெசாத்தின்\s*வைகப்பாடு|சொத்தின்\s*வகைப்பாடு)[\s\/\:\-]*', '', pt_val).strip(' ,-')
                                if pt_val:
                                    current_sched["property_type"] = pt_val
                                    is_field_row = True

                            # 2. Clean Property Extent
                            ext_m = re.search(r'(?:Property\s*Extent[\s\/]*(?:ெசாத்தின்\s*விஸ்தீர்ணம்|சொத்தின்\s*விஸ்தீர்ணம்|விஸ்தீர்ணம்)?|ெசாத்தின்\s*விஸ்தீர்ணம்|சொத்தின்\s*விஸ்தீர்ணம்|விஸ்தீர்ணம்)[\s\/\:\-]+([^\n\r]+?)(?=(?:Survey\s*No|புல\s*எண்|Village|கிராமம்|Plot|மைன|Door|கதவு|\n|$))', c, re.I)
                            if not ext_m:
                                ext_m = re.search(r'(?:Survey\s*No\-Extent|புல\s*எண்\-விஸ்த[ீி]ர்ணம்)[\s\/\:\-][^\-]+?\-\s*([^\n\r]+)', c, re.I)
                            if ext_m:
                                ext_val = ext_m.group(1).strip(' ,-')
                                ext_val = re.sub(r'^(?:ெசாத்தின்\s*விஸ்தீர்ணம்|சொத்தின்\s*விஸ்தீர்ணம்|விஸ்தீர்ணம்)[\s\/\:\-]*', '', ext_val).strip(' ,-')
                                if ext_val:
                                    current_sched["extent"] = cls._parse_extent_dict(ext_val)
                                    is_field_row = True

                            # 3. Clean Survey Number
                            sur_m = re.search(r'(?:Survey\s*No\.?|புல\s*எண்)[\s\/\:\-]+([0-9]+[A-Za-z0-9\/\,\s\-]+?)(?=(?:New\s*Door|Old\s*Door|Door|Floor|Plot|புதிய|பழைய|கதவு|தள|மனை|மைன|\n|$))', c, re.I)
                            if not sur_m:
                                sur_m = re.search(r'(?:Survey\s*No\-Extent|புல\s*எண்\-விஸ்த[ீி]ர்ணம்)[\s\/\:\-]+([^\-\n\r]+)', c, re.I)
                            if sur_m:
                                sur_val = sur_m.group(1).strip(' ,-')
                                current_sched["survey_number"] = cls._parse_survey_dict(sur_val)
                                is_field_row = True

                            # 4. Clean Village & Street (NEVER overwritten by schedule remarks)
                            vs_m = re.search(r'(?:Village\s*&\s*Street[\s\/]*(?:கிராமம்\s*மற்றும்\s*(?:ெத|தெ)ரு)?|கிராமம்\s*மற்றும்\s*(?:ெத|தெ)ரு|Village\s*\/கிராமம்)[\s\/\:\-]+([\s\S]+?)(?=(?:Survey\s*No|புல\s*எண்|Plot\s*No|மைன\s*எண்|Door\s*No|கதவு\s*எண்|Boundary|Schedule|$))', c, re.I)
                            if vs_m:
                                raw_vs = vs_m.group(1).strip()
                                raw_vs = re.sub(r'^(?:கிராமம்\s*மற்றும்\s*(?:ெத|தெ)ரு|Village\s*\/கிராமம்)[\s\/\:\-]*', '', raw_vs).strip()
                                raw_vs = re.sub(r'\s+', ' ', raw_vs).strip()
                                if ',' in raw_vs:
                                    vp, sp = raw_vs.split(',', 1)
                                    current_sched["village"] = vp.strip().rstrip(',')
                                    current_sched["street"] = sp.strip().rstrip(',')
                                else:
                                    current_sched["village"] = raw_vs.strip().rstrip(',')
                                is_field_row = True

                            # 5. Full Plot Number Parsing
                            pl_m = re.search(r'(?:Plot\s*No\.?|மைன\s*எண்|மனை\s*எண்)[\s\/\:\-]*([A-Za-z0-9\s\/\-]+?)(?=(?:New\s*Door|Old\s*Door|Door|Boundary|Schedule|Floor|Block|\n|$))', c, re.I)
                            if pl_m:
                                pl_val = pl_m.group(1).strip(' ,-')
                                pl_val = re.sub(r'^(?:மைன\s*எண்|மனை\s*எண்)[\s\/\:\-]*', '', pl_val).strip(' ,-')
                                if pl_val:
                                    current_sched["plot_no"] = pl_val
                                    is_field_row = True

                            # 6. Door numbers, Floor, Block, Ward, Flat
                            nd_m = re.search(r'(?:New\s*Door\s*No\.?|புதிய\s*கதவு\s*எண்)[\s\/\:\-]*([^\n\r]+)', c, re.I)
                            if nd_m:
                                d_val = re.split(r'(?:Plot|Floor|Block|Old|Door|மனை|மைன|தள|பிளாக்)', nd_m.group(1))[0].strip(' ,-')
                                if d_val:
                                    current_sched["new_door_no"] = d_val
                                    current_sched["door_no"] = d_val
                                    is_field_row = True

                            od_m = re.search(r'(?:Old\s*Door\s*No\.?|பைழய\s*கதவு\s*எண்|பழைய\s*கதவு\s*எண்)[\s\/\:\-]*([^\n\r]+)', c, re.I)
                            if od_m:
                                d_val = re.split(r'(?:Plot|Floor|Block|New|Door|மனை|மைன|தள|பிளாக்)', od_m.group(1))[0].strip(' ,-')
                                if d_val:
                                    current_sched["old_door_no"] = d_val
                                    if not current_sched["door_no"]:
                                        current_sched["door_no"] = d_val
                                    is_field_row = True

                            d_m = re.search(r'(?:Door\s*No\.?|கதவு\s*எண்)[\s\/\:\-]*([^\n\r]+)', c, re.I)
                            if d_m and not any(k in c for k in ['New Door', 'Old Door', 'புதிய கதவு', 'பைழய கதவு', 'பழைய கதவு']):
                                d_val = re.split(r'(?:Plot|Floor|Block|மனை|மைன|தள|பிளாக்)', d_m.group(1))[0].strip(' ,-')
                                if d_val and not current_sched["door_no"]:
                                    current_sched["door_no"] = d_val
                                    is_field_row = True

                            fl_m = re.search(r'(?:Flat\s*No\.?|அடுக்குமாடி\s*எண்)[\s\/\:\-]*([^\n\r]+)', c, re.I)
                            if fl_m:
                                fl_val = re.split(r'(?:Plot|Door|Floor|Block|மனை|மைன)', fl_m.group(1))[0].strip(' ,-')
                                if fl_val:
                                    current_sched["flat_no"] = fl_val
                                    is_field_row = True

                            floor_m = re.search(r'(?:Floor\s*No\.?|தள\s*எண்)[\s\/\:\-]*([^\n\r]+)', c, re.I)
                            if floor_m:
                                floor_val = re.split(r'(?:Plot|Door|Flat|Block|மனை|மைன)', floor_m.group(1))[0].strip(' ,-')
                                if floor_val:
                                    current_sched["floor_no"] = floor_val
                                    is_field_row = True

                            block_m = re.search(r'(?:Block\s*No\.?|பிளாக்\s*எண்)[\s\/\:\-]*([^\n\r]+)', c, re.I)
                            if block_m:
                                b_val = re.split(r'(?:Plot|Door|Floor|Flat|மனை|மைன)', block_m.group(1))[0].strip(' ,-')
                                if b_val:
                                    current_sched["block_no"] = b_val
                                    is_field_row = True

                            ward_m = re.search(r'(?:Ward\s*No\.?|வார்டு\s*எண்)[\s\/\:\-]*([^\n\r]+)', c, re.I)
                            if ward_m:
                                w_val = re.split(r'(?:Plot|Door|Floor|Block|மனை|மைன)', ward_m.group(1))[0].strip(' ,-')
                                if w_val:
                                    current_sched["ward_no"] = w_val
                                    is_field_row = True

                            # 7. Multi-Line Boundaries
                            bnd_m = re.search(r'(?:Boundary\s*Details|எல்லை\s*விவரம்|எல்ைல\s*விபரங்கள்|எல்லை\s*விபரங்கள்)[\s\:\-]+([\s\S]+)', c, re.I)
                            if bnd_m:
                                b_raw = bnd_m.group(1).strip()
                                if "Schedule Remarks" in b_raw:
                                    b_raw = b_raw.split("Schedule Remarks")[0].strip()
                                current_sched["boundaries"] = cls._parse_boundaries(b_raw)
                                is_field_row = True

                            # 8. Multi-Line Schedule Remarks
                            rem_m = re.search(r'(?:Schedule\s*Remarks[^\:]*|ெசாத்து\s*விவரம்[^\:]*குறிப்பு(?:ைர|ரை)|சொத்து\s*விவரம்[^\:]*குறிப்பு(?:ைர|ரை)|குறிப்பு(?:ைர|ரை))[\s\/\:\-]+([\s\S]+)', c, re.I)
                            if rem_m:
                                r_val = cls.normalize_tamil_unicode(rem_m.group(1).strip())
                                r_val = re.sub(r'[ \t]+', ' ', r_val).strip()
                                if current_sched["schedule_remarks_full"]:
                                    current_sched["schedule_remarks_full"] += " " + r_val
                                else:
                                    current_sched["schedule_remarks_full"] = r_val
                                is_field_row = True

                        # 9. Continuation row check: stitch trailing lines into schedule_remarks_full
                        if not is_field_row and current_sched.get("schedule_remarks_full"):
                            cont_text = " ".join([str(c).strip() for c in r if c and str(c).strip() != '-'])
                            if cont_text and not any(h in cont_text for h in ["helpdesk@", "கட்டணமில்லா", "மின்னஞ்சல் முகவரி", "S.R.O /சா.ப.அ:"]):
                                cont_clean = cls.normalize_tamil_unicode(cont_text)
                                cont_clean = re.sub(r'\s+', ' ', cont_clean).strip()
                                current_sched["schedule_remarks_full"] = (current_sched["schedule_remarks_full"] + " " + cont_clean).strip()

            if current_entry:
                if current_sched:
                    if not current_sched.get("plot_no"):
                        target_text = f"{current_sched.get('schedule_remarks_full', '')} {current_sched.get('boundaries', {}).get('raw', '')}"
                        p_fallback = re.search(r'(?:(?:மனை|மைன|பிளாட்)\s*(?:எண்|நெ|நம்பர்)?|Plot\s*(?:No\.?)?)\s*([0-9]+[A-Za-z]?)', target_text, re.I)
                        if p_fallback:
                            current_sched["plot_no"] = p_fallback.group(1).strip()
                    current_entry["schedules"].append(current_sched)
                entries.append(current_entry)

        except Exception as e:
            pass

        return entries

    @classmethod
    def _extract_metadata(cls, all_lines: List[str], fb_doc: str, fb_yr: str, fb_sro: str = "") -> Dict[str, Any]:
        """Extracts top-level certificate metadata from document lines."""
        meta = {
            "certificate_title": "Certificate of Encumbrance on Property (சொத்து தொடர்பான வில்லங்கச் சான்று)",
            "sro_name": "",
            "certificate_date": "",
            "search_query_doc": str(fb_doc).strip(),
            "search_query_year": str(fb_yr).strip(),
            "total_entries_count": 1
        }
        full_text = " ".join(all_lines[:50])

        # SRO Name
        sro_m = re.search(r'S\.R\.O\s*\/[^\:]*[\:\-]\s*([^\n\r]+?)(?:\s+Date|\s+நாள்|\n|\r|$)', full_text)
        if sro_m:
            cand = sro_m.group(1).strip()
            if cand and not cand.startswith('Date') and not cand.startswith('நாள்'):
                meta["sro_name"] = cand
        if not meta["sro_name"]:
            meta["sro_name"] = fb_sro

        # Date
        date_m = re.search(r'(?:Date\s*\/[^\:]*|நாள்)[\:\-]\s*([0-9]{1,2}\s*[\-\/\.][A-Za-z0-9]+\s*[\-\/\.][0-9]{4})', full_text)
        if date_m:
            meta["certificate_date"] = date_m.group(1).replace(' ', '')

        # Document No & Year in header
        doc_yr_m = re.search(r'(?:Document\s*No\.?\s*&\s*Year|Searched\s*Document\s*Number|ஆவண\s*எண்\s*மற்றும்\s*ஆண்டு|ேதடப்பட்ட\s*ஆவண\s*எண்|தேடப்பட்ட\s*ஆவண\s*எண்)[\:\-]\s*([0-9]+)\s*[\/\-]\s*([0-9]{4})', full_text)
        if doc_yr_m:
            meta["search_query_doc"] = doc_yr_m.group(1).strip()
            meta["search_query_year"] = doc_yr_m.group(2).strip()

        # Total entries count from footer
        footer_text = " ".join(all_lines[-40:])
        cnt_m = re.search(r'(?:Number\s*of\s*Entries|பதிவுகளின்\s*எண்ணிக்ைக|பதிவுகளின்\s*எண்ணிக்கை)[\:\-]\s*([0-9]+)', footer_text)
        if cnt_m:
            meta["total_entries_count"] = int(cnt_m.group(1).strip())

        return meta

    @classmethod
    def _parse_entry(cls, all_lines: List[str], metadata: Dict[str, Any], pdf_path: str = "", start_page: int = 0) -> Optional[Dict[str, Any]]:
        """Parses the entry components by combining all document lines across page breaks."""
        doc_no = metadata.get("search_query_doc", "")
        year = metadata.get("search_query_year", "")

        entry = {
            "entry_index": 1,
            "registration_particulars": {
                "document_number": doc_no,
                "registration_year": year,
                "document_id": f"{doc_no}/{year}",
                "nature_of_deed": "Sale deed",
                "volume_no": None,
                "page_no": None,
                "dates": {}
            },
            "financials": {},
            "parties": {
                "executants": [],
                "claimants": []
            },
            "pr_lineage": {
                "pr_raw": "",
                "pr_documents": []
            },
            "schedules": []
        }

        # -------------------------------------------------------------
        # 1. Dates (Execution, Presentation, Registration)
        # -------------------------------------------------------------
        # Find index of Consideration Value
        idx_con = len(all_lines)
        for i, l in enumerate(all_lines):
            if any(k in l for k in ['Consideration Value', 'ைகமாற்றுத் ெதாைக', 'கைமாற்றுத் தொகை']):
                idx_con = i
                break

        # Find entry table start strictly after Certificate Header (skip certificate generation date)
        idx_entry_start = 0
        for i, l in enumerate(all_lines[:idx_con]):
            if any(k in l for k in ['Date of Execution', 'Date of Presentation', 'எழுதிக்', 'தாக்கல்', 'பதிவு நாள்', 'Sr. No.', 'வ. எண்']):
                idx_entry_start = i
            elif doc_no and year and (f"{doc_no}/{year}" in l or f"{doc_no} / {year}" in l):
                idx_entry_start = max(idx_entry_start, i)

        dates_found = []
        for l in all_lines[idx_entry_start:idx_con]:
            for dm in re.finditer(r'\b([0-9]{1,2}\s*[\-\/][A-Za-z]{3}\s*[\-\/][0-9]{4})\b', l):
                d_str = dm.group(1).replace(' ', '')
                dates_found.append(d_str)

        exec_date = dates_found[0] if len(dates_found) > 0 else ""
        pres_date = dates_found[1] if len(dates_found) > 1 else exec_date
        reg_date = dates_found[2] if len(dates_found) > 2 else pres_date
        entry["registration_particulars"]["dates"] = {
            "execution_date": exec_date,
            "presentation_date": pres_date,
            "registration_date": reg_date
        }

        # -------------------------------------------------------------
        # 2. Universal Nature & Multi-Party Extraction (Table-Cell First)
        # -------------------------------------------------------------
        exec_list = []
        claim_list = []
        nature_val = ""
        vol_page_val = None

        if pdf_path and os.path.exists(pdf_path):
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as plumb:
                    page_slice = plumb.pages[start_page:start_page + 2] if start_page < len(plumb.pages) else plumb.pages[:2]
                    for p in page_slice:
                        tables = p.extract_tables()
                        for t in tables:
                            if len(t) >= 2 and len(t[0]) >= 6:
                                header = " ".join([str(c) for c in t[0] if c])
                                if any(k in header for k in ["Executant", "எழுதிக்", "Claimant", "வாங்கியவர்"]):
                                    data_row = t[1]
                                    # Column 3: Nature
                                    if len(data_row) > 3 and data_row[3]:
                                        nature_val = str(data_row[3]).replace('\n', ' ').strip()
                                    # Column 4: Executants
                                    if len(data_row) > 4 and data_row[4]:
                                        for raw_e in str(data_row[4]).split('\n'):
                                            clean_e = re.sub(r'^[0-9\.\s]+', '', raw_e).strip()
                                            clean_e = re.sub(r'\(?PR\)?[0-9]+|\(?AG\)?[0-9]+', '', clean_e).strip().rstrip('(').strip()
                                            if clean_e:
                                                exec_list.append(cls._format_party_entry(clean_e))
                                    # Column 5: Claimants
                                    if len(data_row) > 5 and data_row[5]:
                                        for raw_c in str(data_row[5]).split('\n'):
                                            clean_c = re.sub(r'^[0-9\.\s]+', '', raw_c).strip()
                                            clean_c = re.sub(r'\(?PR\)?[0-9]+|\(?AG\)?[0-9]+', '', clean_c).strip().rstrip('(').strip()
                                            if clean_c:
                                                claim_list.append(cls._format_party_entry(clean_c))
                                    # Column 6: Volume / Page
                                    if len(data_row) > 6 and data_row[6] and str(data_row[6]).strip() != '-':
                                        vol_page_val = str(data_row[6]).strip()
                                    break
                            elif len(t) >= 1 and len(t[0]) >= 6 and exec_list:
                                # Continuation row on next page
                                cont_e = t[0][4]
                                if cont_e and re.search(r'^[0-9]+\.', str(cont_e).strip()):
                                    for raw_e in str(cont_e).split('\n'):
                                        clean_e = re.sub(r'^[0-9\.\s]+', '', raw_e).strip()
                                        clean_e = re.sub(r'\(?PR\)?[0-9]+|\(?AG\)?[0-9]+', '', clean_e).strip().rstrip('(').strip()
                                        if clean_e and not any(e.get("name") == clean_e or e.get("raw") == clean_e for e in exec_list):
                                            exec_list.append(cls._format_party_entry(clean_e))
                        if exec_list or claim_list:
                            pass
            except Exception as e_plumb:
                pass

        if exec_list or claim_list:
            if exec_list:
                entry["parties"]["executants"] = exec_list
            if claim_list:
                entry["parties"]["claimants"] = claim_list
            if nature_val:
                entry["registration_particulars"]["nature_of_deed"] = nature_val
            if vol_page_val:
                if ',' in vol_page_val or '/' in vol_page_val:
                    v_parts = re.split(r'[\,\/]', vol_page_val)
                    entry["registration_particulars"]["volume_no"] = v_parts[0].strip()
                    entry["registration_particulars"]["page_no"] = v_parts[1].strip()
                else:
                    entry["registration_particulars"]["volume_no"] = vol_page_val
        else:
            # Fallback to line-based heuristic scanning for parties
            idx_con = len(all_lines)
            for i, l in enumerate(all_lines):
                if any(k in l for k in ['Consideration Value', 'ைகமாற்றுத் ெதாைக', 'கைமாற்றுத் தொகை']):
                    idx_con = i
                    break

            idx_date = -1
            for i in range(idx_con - 1, -1, -1):
                if re.search(r'\b[0-9]{1,2}\s*[\-\/][A-Za-z]{3}\s*[\-\/][0-9]{4}\b', all_lines[i]):
                    idx_date = i
                    break

            start_party = (idx_date + 1) if idx_date != -1 else 0
            target_lines = all_lines[start_party:idx_con]
            combined = " ".join(target_lines)

            # Nature is everything strictly before the first '1.'
            m_first = re.search(r'^(.*?)(?=\b1\.\s*)', combined)
            if m_first:
                raw_nature = m_first.group(1).strip()
                party_str = combined[m_first.end():].strip()
            else:
                raw_nature = "Sale deed"
                party_str = combined

            # Clean trailing volume/page number or hyphen
            party_str = re.sub(r'[\s\-]+$', '', party_str)
            vol_page_m = re.search(r'([0-9]+\s*[\,\/]\s*[0-9]+)\s*$', party_str)
            vol_no, page_no = None, None
            if vol_page_m:
                vp_str = vol_page_m.group(1)
                party_str = party_str[:vol_page_m.start()].strip()
                parts = re.split(r'[\,\/]', vp_str)
                if len(parts) >= 2:
                    vol_no = parts[0].strip()
                    page_no = parts[1].strip()

            # Tokenize numbered party segments
            matches = list(re.finditer(r'(?:^|\s+)(\d+)\.\s*', party_str))
            party_tokens = []
            for idx, match in enumerate(matches):
                num = int(match.group(1))
                start_pos = match.end()
                end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(party_str)
                name_str = party_str[start_pos:end_pos].strip().rstrip('- ')
                name_str = re.sub(r'\s+[0-9]+$', '', name_str).strip()
                party_tokens.append((num, name_str))

            raw_executants = []
            raw_claimants = []
            seen_reset = False
            last_num = 0

            for num, name in party_tokens:
                if (num == 1 and last_num >= 1) or (num <= last_num):
                    seen_reset = True
                if not seen_reset:
                    raw_executants.append(name)
                else:
                    raw_claimants.append(name)
                last_num = num

            entry["registration_particulars"]["nature_of_deed"] = raw_nature or "Sale deed"
            entry["registration_particulars"]["volume_no"] = vol_no
            entry["registration_particulars"]["page_no"] = page_no
            entry["parties"]["executants"] = [cls._format_party_entry(name) for name in raw_executants if name]
            entry["parties"]["claimants"] = [cls._format_party_entry(name) for name in raw_claimants if name]

        # -------------------------------------------------------------
        # 3. Line-based Financials and PR Numbers
        # -------------------------------------------------------------
        con_raw, mkt_raw, pr_raw = "", "", ""
        for i, l in enumerate(all_lines[:80]):
            if any(k in l for k in ['Consideration Value', 'ைகமாற்றுத் ெதாைக', 'கைமாற்றுத் தொகை']):
                if i + 1 < len(all_lines): con_raw = all_lines[i + 1].strip()
            elif any(k in l for k in ['Market Value', 'சந்ைத மதிப்பு', 'சந்தை மதிப்பு']):
                if i + 1 < len(all_lines): mkt_raw = all_lines[i + 1].strip()
            elif any(k in l for k in ['PR Number', 'முந்ைதய ஆவண எண்', 'முந்தைய ஆவண எண்']):
                if i + 1 < len(all_lines): pr_raw = all_lines[i + 1].strip()

        # Robust PR citation harvesting (superset of the legacy next-line rule above):
        #  - scans the whole entry header (not just the first 80 lines; large layout /
        #    consolidation deeds with many parties push the PR row far down),
        #  - reads values printed on the SAME line as the label,
        #  - stitches wrapped multi-parent lists across continuation lines,
        #  - is not masked when the PR label shares a line with Consideration/Market Value.
        # Legacy citations are always retained (never silently discarded).
        self_doc_id = f"{doc_no}/{year}" if doc_no and year else ""
        legacy_pr_docs = cls._parse_pr_string(pr_raw, exclude_doc_id=self_doc_id)
        robust_pr_raw = cls._extract_pr_raw_from_lines(all_lines)
        robust_pr_docs = cls._parse_pr_string(robust_pr_raw, exclude_doc_id=self_doc_id)
        merged_pr_docs = list(robust_pr_docs)
        for p_doc in legacy_pr_docs:
            if not any(m["formatted"] == p_doc["formatted"] for m in merged_pr_docs):
                merged_pr_docs.append(p_doc)
        if robust_pr_docs and (not legacy_pr_docs or len(robust_pr_docs) >= len(legacy_pr_docs)):
            pr_raw = robust_pr_raw

        entry["financials"] = {
            "consideration_value_raw": con_raw,
            "consideration_value_num": cls._extract_numeric_value(con_raw),
            "market_value_raw": mkt_raw,
            "market_value_num": cls._extract_numeric_value(mkt_raw),
            "currency": "INR"
        }

        entry["pr_lineage"] = {
            "pr_raw": pr_raw,
            "pr_documents": merged_pr_docs
        }

        # -------------------------------------------------------------
        # 4. Multi-Schedule Slicing and Extraction
        # -------------------------------------------------------------
        sched_headers = []
        for i, l in enumerate(all_lines):
            # Must not be Remarks
            if any(k in l for k in ['Schedule Remarks', 'ெசாத்து விவரம்', 'சொத்து விவரம்']):
                continue
            sm = re.search(r'(?:Schedule\s*([0-9]+)\s*Details|அட்டவைண\s*([0-9]+)\s*விவரங்கள்|அட்டவணை\s*([0-9]+)\s*விவரங்கள்)', l, re.I)
            if sm:
                s_num = sm.group(1) or sm.group(2) or sm.group(3) or "1"
                sched_headers.append((int(s_num), i))

        # Footer index
        idx_footer = len(all_lines)
        for i, l in enumerate(all_lines):
            if any(k in l for k in ['Number of Entries', 'பதிவுகளின் எண்ணிக்ைக', 'பதிவுகளின் எண்ணிக்கை']):
                idx_footer = i
                break

        if not sched_headers:
            for i, l in enumerate(all_lines):
                if 'Schedule' in l and 'Details' in l:
                    sched_headers.append((1, i))
                    break

        if not sched_headers:
            return entry

        # Deduplicate consecutive identical schedule markers
        clean_sched_headers = []
        for s_num, idx in sched_headers:
            if clean_sched_headers and clean_sched_headers[-1][0] == s_num:
                continue
            clean_sched_headers.append((s_num, idx))

        # Process each schedule slice
        for s_idx, (s_num, start_idx) in enumerate(clean_sched_headers):
            end_sched_idx = clean_sched_headers[s_idx + 1][1] if s_idx + 1 < len(clean_sched_headers) else idx_footer
            sched_lines = all_lines[start_idx:end_sched_idx]
            sched_obj = cls._parse_single_schedule(sched_lines, s_num)
            entry["schedules"].append(sched_obj)

        return entry

    @classmethod
    def _parse_single_schedule(cls, lines: List[str], sched_num: int) -> Dict[str, Any]:
        """Parses an individual schedule section containing table cells, boundaries, and remarks."""
        idx_bnd = -1
        idx_rem = -1

        for i, l in enumerate(lines):
            if any(k in l for k in ['Schedule Remarks', 'ெசாத்து விவரம்', 'சொத்து விவரம்']):
                if idx_rem == -1: idx_rem = i
            elif any(k in l for k in ['Boundary Details', 'எல்ைல விபரங்கள்', 'எல்லை விபரங்கள்']):
                if idx_bnd == -1: idx_bnd = i

        valid_ends = [i for i in [idx_bnd, idx_rem] if i != -1]
        end_table = min(valid_ends) if valid_ends else len(lines)
        table_lines = lines[:end_table]

        sched = {
            "schedule_id": f"Schedule {sched_num}",
            "property_type": "Plot",
            "extent": {"raw": "", "sqft": 0.0, "sq_meters": 0.0},
            "village": "",
            "street": "",
            "survey_number": {"raw": "", "survey": "", "subdivision": ""},
            "plot_no": "",
            "new_door_no": "",
            "old_door_no": "",
            "door_no": "",
            "floor_no": "",
            "flat_no": "",
            "block_no": "",
            "ward_no": "",
            "raw_table_properties": {},
            "flat_details": {
                "is_flat": False,
                "new_door_no": "",
                "old_door_no": "",
                "door_no": "",
                "floor_no": "",
                "flat_no": "",
                "block_no": "",
                "ward_no": "",
                "undivided_share_land_sqft": 0.0,
                "undivided_share_ratio": "",
                "super_built_up_area_sqft": 0.0,
                "facing_or_location": ""
            },
            "boundaries": {"raw": "", "east": "", "west": "", "north": "", "south": ""},
            "linear_dimensions": {
                "east_west_north": "",
                "east_west_south": "",
                "north_south_east": "",
                "north_south_west": "",
                "calculated_sqft": 0.0,
                "calculated_sqm": 0.0
            },
            "planning_approval": {
                "regularization_order": "",
                "panchayat_approval": ""
            },
            "patta_and_parent_land": {
                "patta_no": "",
                "parent_survey": "",
                "subdivided_surveys": [],
                "total_land_extent_raw": ""
            },
            "schedule_remarks_full": ""
        }

        for idx, l in enumerate(table_lines):
            # Property Type
            if any(k in l for k in ['Property Type', 'ெசாத்தின் வைகப்பாடு', 'சொத்தின் வகைப்பாடு']):
                if ':' in l:
                    raw_type = l.split(':', 1)[1].strip()
                    raw_type = re.split(r'(?:Survey\s*No|புல\s*எண்)', raw_type)[0].strip(' ,-')
                    sched["property_type"] = raw_type

            # Combined Survey No-Extent column
            if any(k in l for k in ['Survey No-Extent', 'புல எண்-விஸ்தீர்ணம்']):
                if ':' in l:
                    content = l.split(':', 1)[1].strip()
                    if ' - ' in content:
                        sur_part, ext_part = content.split(' - ', 1)
                    else:
                        sur_part = content
                        ext_part = ''
                    if sur_part and not sched["survey_number"]["raw"]:
                        sched["survey_number"]["raw"] = sur_part.strip()
                        if '/' in sur_part:
                            s_no, sub_no = sur_part.split('/', 1)
                            sched["survey_number"]["survey"] = s_no.strip()
                            sched["survey_number"]["subdivision"] = sub_no.strip()
                        else:
                            sched["survey_number"]["survey"] = sur_part.strip()
                    if ext_part and not sched["extent"]["raw"]:
                        sched["extent"]["raw"] = ext_part.strip()
                        num_sqft = cls._extract_numeric_value(ext_part)
                        sched["extent"]["sqft"] = num_sqft
                        sched["extent"]["sq_meters"] = round(num_sqft * 0.092903, 2) if num_sqft > 0 else 0.0

            # Standalone Property Extent
            if any(k in l for k in ['Property Extent', 'ெசாத்தின் விஸ்தீர்ணம்', 'சொத்தின் விஸ்தீர்ணம்']) and not any(k in l for k in ['Survey No-Extent', 'புல எண்-விஸ்தீர்ணம்']):
                if ':' in l:
                    raw_ext = l.split(':', 1)[1].strip()
                    sched["extent"]["raw"] = raw_ext
                    num_sqft = cls._extract_numeric_value(raw_ext)
                    sched["extent"]["sqft"] = num_sqft
                    sched["extent"]["sq_meters"] = round(num_sqft * 0.092903, 2) if num_sqft > 0 else 0.0

            # Village & Street
            if any(k in l for k in ['Village & Street', 'கிராமம் மற்றும் ெதரு', 'கிராமம் மற்றும் தெரு']):
                if ':' in l:
                    raw_vs = l.split(':', 1)[1].strip()
                    raw_vs = re.split(r'(?:Survey\s*No|புல\s*எண்)', raw_vs)[0].strip()
                    if raw_vs.endswith(',') and idx + 1 < len(table_lines):
                        next_l = table_lines[idx + 1]
                        if not any(k in next_l for k in ['Survey', 'புல எண்', 'Door', 'Floor', 'Plot', 'மைன', 'கதவு', 'தள']):
                            raw_vs += " " + next_l.strip()

                    if ',' in raw_vs:
                        v, s = raw_vs.split(',', 1)
                        sched["village"] = v.strip().rstrip(',')
                        sched["street"] = s.strip().rstrip(',')
                    else:
                        sched["village"] = raw_vs.strip().rstrip(',')

            # Standalone Survey No
            if any(k in l for k in ['Survey No', 'புல எண்']) and not any(k in l for k in ['Survey No-Extent', 'புல எண்-விஸ்தீர்ணம்']):
                s_m = re.search(r'(?:Survey\s*No\.?|புல\s*எண்)[\s\/\:\-]*([0-9]+[A-Za-z0-9\/\,\s\-]+)', l)
                if s_m and not sched["survey_number"]["raw"]:
                    raw_sur = s_m.group(1).strip().rstrip(' ,-')
                    raw_sur = re.split(r'(?:New\s*Door|Old\s*Door|Door|Floor|Plot|புதிய|பழைய|கதவு|தள|மனை|மைன)', raw_sur)[0].strip(' ,-')
                    sched["survey_number"]["raw"] = raw_sur
                    if '/' in raw_sur:
                        s_no, sub_no = raw_sur.split('/', 1)
                        sched["survey_number"]["survey"] = s_no.strip()
                        sched["survey_number"]["subdivision"] = sub_no.strip()
                    else:
                        sched["survey_number"]["survey"] = raw_sur

            # Door Numbers
            if any(k in l for k in ['New Door No', 'புதிய கதவு எண்']):
                m = re.search(r'(?:New\s*Door\s*No\.?|புதிய\s*கதவு\s*எண்)[\s\/\:\-]*([^\n\r]+)', l)
                if m:
                    d_val = re.split(r'(?:Plot\s*No|Floor\s*No|Block\s*No|மனை\s*எண்|மைன\s*எண்|தள\s*எண்)', m.group(1))[0].strip(' ,-')
                    clean_d = re.sub(r'^(?:New\s*Door\s*No\.?|புதிய\s*கதவு\s*எண்)[\s\/\:\-]*', '', d_val).strip(' ,-')
                    sched["new_door_no"] = clean_d

            if any(k in l for k in ['Old Door No', 'பைழய கதவு எண்', 'பழைய கதவு எண்']):
                m = re.search(r'(?:Old\s*Door\s*No\.?|பழைய\s*கதவு\s*எண்|பைழய\s*கதவு\s*எண்)[\s\/\:\-]*([^\n\r]+)', l)
                if m:
                    d_val = re.split(r'(?:Plot\s*No|Floor\s*No|Block\s*No|மனை\s*எண்|மைன\s*எண்|தள\s*எண்)', m.group(1))[0].strip(' ,-')
                    clean_d = re.sub(r'^(?:Old\s*Door\s*No\.?|பழைய\s*கதவு\s*எண்|பைழய\s*கதவு\s*எண்)[\s\/\:\-]*', '', d_val).strip(' ,-')
                    sched["old_door_no"] = clean_d

            if any(k in l for k in ['Door No', 'கதவு எண்']) and not any(k in l for k in ['New Door', 'புதிய கதவு', 'Old Door', 'பைழய கதவு', 'பழைய கதவு']):
                m = re.search(r'(?:Door\s*No\.?|கதவு\s*எண்)[\s\/\:\-]*([^\n\r]+)', l)
                if m:
                    d_val = re.split(r'(?:Plot\s*No|Floor\s*No|Block\s*No|மனை\s*எண்|மைன\s*எண்|தள\s*எண்)', m.group(1))[0].strip(' ,-')
                    clean_d = re.sub(r'^(?:Door\s*No\.?|கதவு\s*எண்)[\s\/\:\-]*', '', d_val).strip(' ,-')
                    sched["door_no"] = clean_d

            # Floor No
            if any(k in l for k in ['Floor No', 'தள எண்']):
                m = re.search(r'(?:Floor\s*No\.?|தள\s*எண்)[\s\/\:\-]*([^\n\r]+)', l)
                if m:
                    f_val = re.split(r'(?:Plot\s*No|Door\s*No|Block\s*No|மனை\s*எண்|மைன\s*எண்)', m.group(1))[0].strip(' ,-')
                    clean_f = re.sub(r'^(?:Floor\s*No\.?|தள\s*எண்)[\s\/\:\-]*', '', f_val).strip(' ,-')
                    sched["floor_no"] = clean_f

            # Block No & Ward No
            if any(k in l for k in ['Block No', 'பிளாக் எண்']):
                m = re.search(r'(?:Block\s*No\.?|பிளாக்\s*எண்)[\s\/\:\-]*([^\n\r]+)', l)
                if m:
                    b_val = re.split(r'(?:Plot\s*No|Door\s*No|Floor\s*No|மனை\s*எண்|மைன\s*எண்)', m.group(1))[0].strip(' ,-')
                    clean_b = re.sub(r'^(?:Block\s*No\.?|பிளாக்\s*எண்)[\s\/\:\-]*', '', b_val).strip(' ,-')
                    sched["block_no"] = clean_b

            if any(k in l for k in ['Ward No', 'வார்டு எண்']):
                m = re.search(r'(?:Ward\s*No\.?|வார்டு\s*எண்)[\s\/\:\-]*([^\n\r]+)', l)
                if m:
                    sched["ward_no"] = m.group(1).strip()

            # Flat No
            if any(k in l for k in ['Flat No', 'அடுக்குமாடி எண்']):
                m = re.search(r'(?:Flat\s*No\.?|அடுக்குமாடி\s*எண்)[\s\/\:\-]*([^\n\r]+)', l, re.I)
                if m:
                    fl_val = re.split(r'(?:Plot\s*No|Door\s*No|Floor\s*No|Block\s*No|மனை\s*எண்)', m.group(1))[0].strip(' ,-')
                    clean_fl = re.sub(r'^(?:Flat\s*No\.?|அடுக்குமாடி\s*எண்)[\s\/\:\-]*', '', fl_val, flags=re.I).strip(' ,-')
                    sched["flat_no"] = clean_fl

            # Generic Key-Value Harvester for any table column variations
            if ':' in l and not any(k in l for k in ['Schedule Remarks', 'Boundary Details', 'ெசாத்து விவரம்', 'சொத்து விவரம்', 'எல்ைல', 'எல்லை']):
                parts = l.split(':', 1)
                lbl = parts[0].strip()
                val = parts[1].strip()
                if lbl and val and len(lbl) < 60:
                    sched["raw_table_properties"][lbl] = val

            # Plot No
            if any(k in l for k in ['Plot No', 'மைன எண்', 'மனை எண்']) and not any(k in l for k in ['Flat No', 'அடுக்குமாடி எண்']):
                m = re.search(r'(?:Plot\s*No\.?|மைன\s*எண்|மனை\s*எண்)[\s\/\:\-]*([^\n\r]+)', l)
                if m:
                    raw_plot = m.group(1).strip()
                    raw_plot = re.split(r'(?:New\s*Door|Old\s*Door|Floor|Block|புதிய|பழைய|தள|பிளாக்)', raw_plot)[0].strip(' ,-')
                    clean_plot = re.sub(r'^(?:Plot\s*No\.?|மைன\s*எண்|மனை\s*எண்|பிளாட்\s*நிர்\.?|பிளாட்\s*எண்)[\s\/\:\-]*', '', raw_plot).strip(' ,-')
                    sched["plot_no"] = clean_plot

        # Boundaries & Remarks
        if idx_bnd != -1 and idx_rem != -1 and idx_rem < idx_bnd:
            # Layout Case A: Remarks started first (e.g. Right Column on Page 1)
            # Boundaries started at idx_bnd (Left Column on Page 1)
            after_bnd_lines = lines[idx_bnd + 1:]
            
            # Check if boundaries completed on Page 1 before any page break
            has_south_on_page1 = False
            split_idx = len(after_bnd_lines)
            
            for j, bl in enumerate(after_bnd_lines):
                bl_clean = bl.strip()
                if any(k in bl_clean for k in ['தெற்கு', 'ெதற்கு', 'South']):
                    has_south_on_page1 = True
                if bl_clean.isdigit() and has_south_on_page1:
                    split_idx = j
                    break
            
            raw_b_lines = after_bnd_lines[:split_idx]
            rem_continuation_lines = [l for l in after_bnd_lines[split_idx:] if not l.strip().isdigit()]
            
            raw_b_clean = [l for l in raw_b_lines if not l.isdigit()]
            raw_b_text = " ".join(raw_b_clean)
            sched["boundaries"] = cls._parse_boundaries(raw_b_text)
            
            rem_lines = lines[idx_rem:idx_bnd] + rem_continuation_lines
            if rem_lines:
                rem_lines[0] = re.sub(r'^(?:Schedule Remarks\/[^\:]*|ெசாத்து விவரம்[^\:]*|சொத்து விவரம்[^\:]*)[\:\-]\s*', '', rem_lines[0])
                clean_rems = [l for l in rem_lines if not l.isdigit()]
                stitched = " ".join(clean_rems)
                stitched = re.sub(r'[\.]{4,}|[\…]{2,}', ' ', stitched)
                stitched = re.sub(r'\s+', ' ', stitched).strip()
                norm_rems = cls.normalize_tamil_unicode(stitched)
                sched["schedule_remarks_full"] = norm_rems
        else:
            # Layout Case B: Standard order (Boundaries before Remarks or only one present)
            if idx_bnd != -1:
                end_bnd = idx_rem if idx_rem != -1 and idx_rem > idx_bnd else len(lines)
                raw_b_lines = lines[idx_bnd + 1:end_bnd]
                raw_b_clean = [l for l in raw_b_lines if not l.isdigit()]
                raw_b_text = " ".join(raw_b_clean)
                extra_lines = lines[end_bnd:] if end_bnd < len(lines) else []
                sched["boundaries"] = cls._parse_boundaries(raw_b_text, extra_lines)

            if idx_rem != -1:
                end_rem = idx_bnd if idx_bnd != -1 and idx_bnd > idx_rem else len(lines)
                rem_lines = lines[idx_rem:end_rem]
                if rem_lines:
                    rem_lines[0] = re.sub(r'^(?:Schedule Remarks\/[^\:]*|ெசாத்து விவரம்[^\:]*|சொத்து விவரம்[^\:]*)[\:\-]\s*', '', rem_lines[0])
                    clean_rems = [l for l in rem_lines if not l.isdigit()]
                    stitched = " ".join(clean_rems)
                    stitched = re.sub(r'[\.]{4,}|[\…]{2,}', ' ', stitched)
                    stitched = re.sub(r'\s+', ' ', stitched).strip()
                    norm_rems = cls.normalize_tamil_unicode(stitched)
                    sched["schedule_remarks_full"] = norm_rems

                # Subfield extraction from remarks
                builtup_m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*சதுரடியில்\s*கட்டியுள்ள\s*அடுக்குமாடி', norm_rems)
                if not builtup_m:
                    builtup_m = re.search(r'அடுக்குமாடி[^\d]*([0-9]+(?:\.[0-9]+)?)\s*சதுரடி', norm_rems)
                builtup_sqft = float(builtup_m.group(1)) if builtup_m else 0.0

                uds_ratios = re.findall(r'([0-9]+\s*\/\s*[0-9]+)\s*(?:பாகம்|பங்கு|share)', norm_rems, re.I)
                uds_ratio = ", ".join(list(dict.fromkeys(uds_ratios)))

                floor_face_m = re.search(r'((?:முதல்|இரண்டாம்|மூன்றாம்|நான்காம்|தரைத்)?\s*தளத்தில்\s*[^\,\.]+?பக்கம்)', norm_rems)
                floor_facing = floor_face_m.group(1).strip() if floor_face_m else ""

                is_flat_deed = (sched["property_type"].lower() == "flats" or bool(sched["floor_no"]) or bool(builtup_sqft > 0))
                sched["flat_details"] = {
                    "is_flat": is_flat_deed,
                    "new_door_no": sched["new_door_no"],
                    "old_door_no": sched["old_door_no"],
                    "door_no": sched["door_no"],
                    "floor_no": sched["floor_no"],
                    "flat_no": sched["flat_no"],
                    "block_no": sched["block_no"],
                    "ward_no": sched["ward_no"],
                    "undivided_share_land_sqft": sched["extent"]["sqft"] if is_flat_deed else 0.0,
                    "undivided_share_ratio": uds_ratio,
                    "super_built_up_area_sqft": builtup_sqft,
                    "facing_or_location": floor_facing
                }

                p_m = re.search(r'(?:பட்டா\s*(?:நம்பர்|எண்)|Patta\s*No\.?)[\s\:\-]*([0-9]+)', norm_rems)
                if p_m: sched["patta_and_parent_land"]["patta_no"] = p_m.group(1).strip()

                parent_m = re.search(r'(?:அயன்\s*சர்வே|அயன்\s*புஞ்சை\s*சர்வே|பழைய\s*சர்வே)[\s\:\-]*எண்[\s\:\-]*([0-9]+(?:\/[0-9A-Za-z\u0B80-\u0BFF]+)?)', norm_rems)
                if parent_m: sched["patta_and_parent_land"]["parent_survey"] = parent_m.group(1).strip()

                all_subdivs = re.findall(r'(?:சர்வே|SF)[\s\:\-]*எண்[\s\:\-]*([0-9]+(?:\/[0-9A-Za-z\u0B80-\u0BFF]+))', norm_rems)
                sched["patta_and_parent_land"]["subdivided_surveys"] = sorted(list(set(all_subdivs)))

                dlp_m = re.search(r'((?:டி[\,\s\.]*எல்[\,\s\.]*பி[\,\s\.]*எ|டி[\,\s\.]*எல்[\,\s\.]*பி|DLP|DTCP|CMDA)[\s\:\-]*எண்\s*[0-9]+\/[0-9]{2,4})', norm_rems)
                if dlp_m: sched["planning_approval"]["regularization_order"] = dlp_m.group(0).strip()

                panch_m = re.search(r'((?:ந\.க\.எண்|ந\.க\.|Na\.Ka\.No\.?)[\s\:\-]*[0-9]+\/[0-9]{2,4}(?:[\s\,]*(?:நாள்|Date)[\s\:\-]*[0-9\.\/\-]+)?)', norm_rems)
                if panch_m: sched["planning_approval"]["panchayat_approval"] = panch_m.group(0).strip(' ,-')

                dim_n = re.findall(r'வடபுற[^\d]*(\d+)', norm_rems)
                dim_s = re.findall(r'தென்புற[^\d]*(\d+)', norm_rems)
                dim_e = re.findall(r'கீழ்புற[^\d]*(\d+)', norm_rems)
                dim_w = re.findall(r'மேல்புற[^\d]*(\d+)', norm_rems)

                if dim_n: sched["linear_dimensions"]["east_west_north"] = f"{dim_n[-1]} அடி"
                if dim_s: sched["linear_dimensions"]["east_west_south"] = f"{dim_s[-1]} அடி"
                if dim_e: sched["linear_dimensions"]["north_south_east"] = f"{dim_e[-1]} அடி"
                if dim_w: sched["linear_dimensions"]["north_south_west"] = f"{dim_w[-1]} அடி"

                sqft_m = re.search(r'சதுரடி\s*([0-9]+)', norm_rems)
                sqm_m = re.search(r'(?:ச\.மீ\.?|சதுர\s*மிட்டர்)\s*([0-9\.]+)', norm_rems)
                if sqft_m: sched["linear_dimensions"]["calculated_sqft"] = float(sqft_m.group(1))
                if sqm_m: sched["linear_dimensions"]["calculated_sqm"] = float(sqm_m.group(1))

        if not sched.get("plot_no"):
            target_text = f"{sched.get('schedule_remarks_full', '')} {sched.get('boundaries', {}).get('raw', '')}"
            p_fallback = re.search(r'(?:(?:மனை|மைன|பிளாட்)\s*(?:எண்|நெ|நம்பர்)?|Plot\s*(?:No\.?)?)\s*([0-9]+[A-Za-z]?)', target_text, re.I)
            if p_fallback:
                sched["plot_no"] = p_fallback.group(1).strip()

        return sched

    @classmethod
    def _parse_boundaries(cls, raw_b: str, extra_lines: List[str] = None) -> Dict[str, str]:
        """Parses directional boundaries supporting English and Tamil (words, suffixes, shorthands, continuation)."""
        norm = cls.normalize_tamil_unicode(raw_b)
        dirs = {"raw": norm, "east": "", "west": "", "north": "", "south": ""}

        # 1. Shorthand notation check: (வ), (தெ), (கி), (மே), (E), (W), (N), (S)
        shorthands = list(re.finditer(r'\(\s*(வ|வட|ெத|தெ|கி|கிழ|ேம|மே|[EWNSewns])\s*\)[\s\-ல்:]*([^,(]+)', norm))
        if shorthands:
            for m in shorthands:
                cardinal = m.group(1).strip().upper()
                val = m.group(2).strip(' ,-')
                if cardinal in ['கி', 'கிழ', 'E']: dirs['east'] = val
                elif cardinal in ['ேம', 'மே', 'W']: dirs['west'] = val
                elif cardinal in ['வ', 'வட', 'N']: dirs['north'] = val
                elif cardinal in ['ெத', 'தெ', 'S']: dirs['south'] = val
            return dirs

        # 2. Universal Bilingual Delimiter
        next_dir = r'(?=(?:[\,\;]?\s*(?:East|West|North|South|கிழக்கு|கிழக்கில்|கிழக்கே|கிழக்ேக|மேற்கு|ேமற்கு|மேற்கில்|ேமற்கில்|வடக்கு|வடக்கில்|தெற்கு|ெதற்கு|தெற்கில்|ெதற்கில்))|$)'
        
        m_e = re.search(r'(?:East|கிழக்கு|கிழக்கில்|கிழக்ேக|கிழக்கே)[\s\:\-]*([\s\S]+?)' + next_dir, norm, re.I)
        m_w = re.search(r'(?:West|ேமற்கு|ேமற்கில்|மேற்கு|மேற்கில்)[\s\:\-]*([\s\S]+?)' + next_dir, norm, re.I)
        m_n = re.search(r'(?:North|வடக்கு|வடக்கில்)[\s\:\-]*([\s\S]+?)' + next_dir, norm, re.I)
        m_s = re.search(r'(?:South|ெதற்கு|ெதற்கில்|தெற்கு|தெற்கில்)[\s\:\-]*([\s\S]+?)' + next_dir, norm, re.I)

        if m_e: dirs["east"] = re.sub(r'\s+', ' ', m_e.group(1)).strip(' ,-')
        if m_w: dirs["west"] = re.sub(r'\s+', ' ', m_w.group(1)).strip(' ,-')
        if m_n: dirs["north"] = re.sub(r'\s+', ' ', m_n.group(1)).strip(' ,-')
        if m_s: dirs["south"] = re.sub(r'\s+', ' ', m_s.group(1)).strip(' ,-')

        # 3. Page break continuation check: If directions are incomplete and extra_lines provided
        if (not dirs["north"] or not dirs["south"] or not dirs["east"] or not dirs["west"]) and extra_lines:
            next_cont_delim = r'(?=(?:[\,\;]?\s*(?:East|West|North|South|கிழக்கு|கிழக்கில்|ேமற்கு|ேமற்கில்|மேற்கு|மேற்கில்|வடக்கு|வடக்கில்|ெதற்கு|ெதற்கில்|தெற்கு|தெற்கில்|யூடிஆர்|சர்ேவ|சர்வே|கட்டுப்பட்ட|அடங்கியது|ெந\.|நெ\.))|$)'
            for el in extra_lines[:15]:
                el_norm = cls.normalize_tamil_unicode(el)
                if any(k in el_norm for k in ['வடக்கு', 'தெற்கு', 'கிழக்கு', 'மேற்கு', 'East', 'West', 'North', 'South']):
                    # Prefix before first cardinal continuation
                    m_pref = re.match(r'^(.*?)(?=(?:[\,\;]?\s*(?:East|West|North|South|வடக்கு|தெற்கு|கிழக்கு|மேற்கு)))', el_norm, re.I)
                    if m_pref:
                        pref = m_pref.group(1).strip(' ,-')
                        if pref:
                            if dirs["west"] and not dirs["north"]:
                                dirs["west"] = (dirs["west"] + " " + pref).strip()
                            elif dirs["east"] and not dirs["west"]:
                                dirs["east"] = (dirs["east"] + " " + pref).strip()

                    if not dirs["north"]:
                        mn = re.search(r'(?:North|வடக்கு|வடக்கில்)[\s\:\-]*([^\n\r]+?)' + next_cont_delim, el_norm, re.I)
                        if mn: dirs["north"] = mn.group(1).strip(' ,-')
                    if not dirs["south"]:
                        ms = re.search(r'(?:South|தெற்கு|தெற்கில்|ெதற்கு|ெதற்கில்)[\s\:\-]*([^\n\r]+?)' + next_cont_delim, el_norm, re.I)
                        if ms: dirs["south"] = ms.group(1).strip(' ,-')
                    if not dirs["west"]:
                        mw = re.search(r'(?:West|மேற்கு|மேற்கில்|ேமற்கு|ேமற்கில்)[\s\:\-]*([^\n\r]+?)' + next_cont_delim, el_norm, re.I)
                        if mw: dirs["west"] = mw.group(1).strip(' ,-')
                    if not dirs["east"]:
                        me = re.search(r'(?:East|கிழக்கு|கிழக்கில்|கிழக்கே|கிழக்ேக)[\s\:\-]*([^\n\r]+?)' + next_cont_delim, el_norm, re.I)
                        if me: dirs["east"] = me.group(1).strip(' ,-')
                    break

        return dirs

    @classmethod
    def _format_party_entry(cls, name_str: str) -> Dict[str, Any]:
        """Parses a party string into structured entity object with verbatim initials and classification."""
        clean = name_str.strip().rstrip('- ')
        no_num = re.sub(r'^[0-9]+\.\s*', '', clean).strip()

        # Detect initials (Tamil or English): e.g. "ரா." or "S." or "ஆர்." or "K.R."
        init_m = re.match(r'^([A-Za-z\u0B80-\u0BFF\.\,]{1,5}\.[\s\.]*)', no_num)
        initial_verbatim = init_m.group(1).strip() if init_m else ""
        clean_name = no_num[len(initial_verbatim):].strip() if initial_verbatim else no_num

        lower = no_num.lower()
        is_org = any(k in lower for k in cls.ORGANIZATION_KEYWORDS)
        party_type = "ORGANIZATION" if is_org else "INDIVIDUAL"

        return {
            "raw": clean,
            "name": clean_name or no_num,
            "initial_verbatim": initial_verbatim,
            "party_type": party_type
        }

    # ------------------------------------------------------------------
    # PR (prior document / முந்தைய ஆவண எண்) citation parsing
    # ------------------------------------------------------------------
    # Doc-number / year token. Lookbehinds stop date fragments such as
    # "12-05-2007" from being read as document "05/2007".
    PR_TOKEN_RE = re.compile(
        r'(?<![0-9])(?<![0-9]/)(?<![0-9]-)(?<![0-9]\.)([0-9]{1,7})\s*[\/\-]\s*([12][09][0-9]{2})(?![0-9])'
    )
    PR_LABEL_RE = re.compile(
        r'(?:(?<![A-Za-z])PR\s*Number|(?<![A-Za-z])PR\s*No\b\.?|முந்ைதய\s*ஆவண\s*எண்(?:கள்)?|முந்தைய\s*ஆவண\s*எண்(?:கள்)?)',
        re.I
    )
    # Labels of neighbouring EC cells; a PR value never continues past one of these.
    PR_STOP_LABEL_RE = re.compile(
        r'(?:Consideration\s*Value|Market\s*Value|Document\s*Remarks|Schedule\s*(?:[0-9]+\s*)?Details|Schedule\s*Remarks|'
        r'Property\s*Type|Property\s*Extent|Survey\s*No|Village|Boundary|Nature|Executant|Claimant|'
        r'Number\s*of\s*Entries|ைகமாற்றுத்|கைமாற்றுத்|சந்ைத\s*மதிப்பு|சந்தை\s*மதிப்பு|ஆவணக்?\s*குறிப்பு|'
        r'அட்டவைண|அட்டவணை|சொத்தின்|ெசாத்தின்|புல\s*எண்|கிராமம்|எல்லை|எல்ைல|பதிவுகளின்)',
        re.I
    )
    PR_PURE_TOKEN_LINE_RE = re.compile(r'^[\s0-9\/\-\,\;\.&]*(?:(?:and|மற்றும்)[\s0-9\/\-\,\;\.&]*)*$', re.I)

    @classmethod
    def _is_pr_continuation_line(cls, prev_text: str, line: str) -> bool:
        """A following physical line belongs to the PR value only if it carries doc tokens and
        either the previous text visibly continues (trailing , / - &) or the line is token-only."""
        if not line or cls.PR_STOP_LABEL_RE.search(line) or cls.PR_LABEL_RE.search(line):
            return False
        if not re.search(r'[0-9]', line):
            return False
        prev = (prev_text or "").rstrip()
        if prev.endswith((',', '/', '-', '&', ';')) or re.search(r'(?:and|மற்றும்)$', prev, re.I):
            return True
        return bool(cls.PR_PURE_TOKEN_LINE_RE.match(line.strip()))

    @classmethod
    def _stitch_pr_cell_continuation(cls, cell_tail: str) -> str:
        """Joins the PR value of a table cell that wraps across several lines."""
        if not cell_tail:
            return ""
        lines = [l.strip() for l in str(cell_tail).replace('\r', '\n').split('\n')]
        lines = [l for l in lines if l]
        if not lines:
            return ""
        acc = lines[0]
        stop = cls.PR_STOP_LABEL_RE.search(acc)
        if stop:
            acc = acc[:stop.start()].strip()
        for l in lines[1:]:
            if cls._is_pr_continuation_line(acc, l):
                acc = f"{acc} {l}".strip()
            else:
                break
        return acc.strip()

    @classmethod
    def _extract_pr_raw_from_lines(cls, all_lines: List[str]) -> str:
        """
        Deterministically harvests the PR citation value from EC text lines.
        Search window: from the top of the entry up to the first schedule header
        (PR row always precedes the schedule block). The first PR label wins.
        """
        if not all_lines:
            return ""
        end = len(all_lines)
        for i, l in enumerate(all_lines):
            if re.search(r'(?:Schedule\s*[0-9]+\s*Details|அட்டவைண\s*[0-9]+\s*விவரங்கள்|அட்டவணை\s*[0-9]+\s*விவரங்கள்)', l, re.I) \
                    and not any(k in l for k in ['Schedule Remarks', 'ெசாத்து விவரம்', 'சொத்து விவரம்']):
                end = i
                break

        for i in range(end):
            line = all_lines[i]
            labels = list(cls.PR_LABEL_RE.finditer(line))
            if not labels:
                continue
            remainder = line[labels[-1].end():]
            remainder = re.sub(r'^[^\:\-0-9]{0,40}?[\:\-]', '', remainder, count=1).strip()
            stop = cls.PR_STOP_LABEL_RE.search(remainder)
            if stop:
                remainder = remainder[:stop.start()].strip()
            acc = remainder
            j = i + 1
            # Legacy behaviour: value printed on the next line under the label.
            if not cls.PR_TOKEN_RE.search(acc) and j < len(all_lines):
                nxt = all_lines[j].strip()
                if not cls.PR_STOP_LABEL_RE.search(nxt) and not cls.PR_LABEL_RE.search(nxt):
                    acc = f"{acc} {nxt}".strip() if acc and acc not in ('-', ':') else nxt
                    j += 1
            # Wrapped continuation lines (bounded look-ahead).
            while j < len(all_lines) and j < i + 8:
                nxt = all_lines[j].strip()
                if cls._is_pr_continuation_line(acc, nxt):
                    acc = f"{acc} {nxt}".strip()
                    j += 1
                else:
                    break
            return acc.strip()
        return ""

    @classmethod
    def _parse_pr_string(cls, pr_str: str, exclude_doc_id: str = "") -> List[Dict[str, str]]:
        """
        Parses PR citations into individual {doc_no, year} objects.
        Accepts comma / semicolon / 'and' / 'மற்றும்' / whitespace separated lists and
        spaced slashes ("1572/ 2007, 1644/ 2007, 1904/ 2007"). Order preserved, duplicates
        and self-citations removed, implausible years rejected.
        """
        pr_list: List[Dict[str, str]] = []
        if not pr_str:
            return pr_list
        max_year = datetime.date.today().year + 1
        excl = re.sub(r'\s+', '', str(exclude_doc_id or ""))
        seen = set()
        for m in cls.PR_TOKEN_RE.finditer(str(pr_str)):
            d_no = m.group(1)
            yr = m.group(2)
            if not (1800 <= int(yr) <= max_year):
                continue
            formatted = f"{d_no}/{yr}"
            if formatted in seen or (excl and formatted == excl):
                continue
            seen.add(formatted)
            pr_list.append({
                "doc_no": d_no,
                "year": yr,
                "formatted": formatted
            })
        return pr_list

    @staticmethod
    def _extract_numeric_value(raw_val: str) -> float:
        """Extracts clean numeric float from currency/extent strings like 'ரூ. 1,90,000/-' or 'Rs. 64,00,000/-'."""
        m = re.search(r'([0-9]+(?:[\,][0-9]+)*(?:\.[0-9]+)?)', raw_val)
        if m:
            clean = m.group(1).replace(',', '')
            try:
                return float(clean)
            except ValueError:
                return 0.0
        return 0.0


if __name__ == '__main__':
    if len(sys.argv) > 1:
        target_pdf = sys.argv[1]
        print(f"Extracting: {target_pdf}")
        out = PDFDeterministicExtractor.extract_from_pdf(target_pdf)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("Usage: python pdf_deterministic_extractor.py <path_to_pdf>")
