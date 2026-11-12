"""
ec_portal_client.py - Live TNREGINET Encumbrance Certificate Portal Client
==========================================================================
Executes live Search Encumbrance Certificate queries against TNREGINET (STAR 2.0):
1. Initializes authenticated session on openEncumbranceCertSearch.
2. Resolves Zone, District, SRO hierarchy and dynamically fetches Village dropdown options.
3. Automatically solves SimpleCaptcha with OCR verification.
4. Executes searchDocYearWise (Survey Wise / Ward-Block Wise) for 1975-Present date ranges.
5. Handles 100/200 page overflow by integrating adaptive binary date halving.
6. Downloads official Encumbrance Certificate PDF via directPrintDwnLoad (tmpltMstID=8400004).
"""

import os
import sys
import re
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import requests
import urllib3
from bs4 import BeautifulSoup

# Disable insecure HTTPS warnings
urllib3.disable_warnings()

from engine_a_core import EngineACore
from ec_date_splitter import ECDateSplitter


class ECPortalClient:
    """Client for querying TNREGINET Encumbrance Certificate Portal & downloading full EC PDFs."""

    BASE_URL = "https://tnreginet.gov.in/portal/webHP"
    EC_SEARCH_URL = (
        "https://tnreginet.gov.in/portal/webHP?"
        "requestType=ApplicationRH&actionVal=openEncumbranceCertSearch"
        "&screenId=8400001&scenarioId=2&menuCode=8400010&auditUSFlag=true&UserLocaleID=en"
    )

    HIERARCHY_FILE = os.path.join(os.path.dirname(__file__), "sro_hierarchy.json")

    @classmethod
    def create_session(cls) -> requests.Session:
        """Creates a requests session configured with standard browser headers."""
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ta;q=0.8',
            'X-Requested-With': 'XMLHttpRequest'
        })
        return s

    @classmethod
    def init_ec_session(cls, session: requests.Session, log_callback=None, max_attempts: int = 3) -> Dict[str, Any]:
        """Initializes the EC Search page, extracts tokens, and solves the captcha with network retry."""
        def log(m):
            if log_callback: log_callback(m)
            else: print(m)

        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                log(f"[*] Initializing live TNREGINET EC Search session (attempt {attempt}/{max_attempts})...")
                resp = session.get(cls.EC_SEARCH_URL, verify=False, timeout=30)
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                auth_token_el = soup.find('input', {'name': 'authToken'}) or soup.find('input', {'id': 'authToken'})
                auth_token = auth_token_el.get('value', '') if auth_token_el else ''

                csrf_m = re.search(r"var\s+csrf\s*=\s*['\"]([a-f0-9\-]+)['\"]", resp.text)
                csrf_token = csrf_m.group(1) if csrf_m else ''

                log(f"[+] Session established (CSRF={csrf_token[:8]}..., AuthToken={auth_token[:8]}...)")

                # Harvest full base form fields from EncumbranceCertificateForm
                base_form_fields = []
                ec_form = soup.find('form', {'id': 'EncumbranceCertificateForm'})
                if ec_form:
                    for inp in ec_form.find_all(['input', 'select']):
                        name = inp.get('name')
                        if not name or name in ['btn_SearchDoc', 'btn_ResetForm', 'btn_AddSurvey', 'btn_UpdateSurvey', 'submitPersonalDetail', 'btn_selectDoc']:
                            continue
                        val = inp.get('value', '')
                        if inp.name == 'select':
                            opt = inp.find('option', selected=True)
                            val = opt.get('value', '') if opt else ''
                        base_form_fields.append((name, val))

                # Solve captcha
                captcha_code = EngineACore.solve_captcha(session, csrf_token, max_attempts=12, log_callback=log_callback)
                if not captcha_code:
                    raise RuntimeError("Failed to resolve live TNREGINET captcha after multiple attempts.")

                return {
                    "csrf_token": csrf_token,
                    "auth_token": auth_token,
                    "captcha_code": captcha_code,
                    "base_form_fields": base_form_fields
                }
            except (ConnectionResetError, requests.exceptions.RequestException, Exception) as e:
                last_err = e
                log(f"      [!] Session init error (attempt {attempt}/{max_attempts}): {e}")
                if attempt < max_attempts:
                    backoff = 2 * attempt  # 2s, 4s
                    log(f"      [⇄] Retrying session initialization in {backoff}s (network backoff)...")
                    time.sleep(backoff)
                else:
                    raise RuntimeError(f"Failed to initialize live TNREGINET EC session after {max_attempts} attempts: {last_err}")

    # SRO City Aliases and Tamil Transliteration Mapping (Tier 1)
    SRO_ALIASES = {
        'trichy': 'trichy', 'tiruchirappalli': 'trichy', 'tiruchi': 'trichy', 'திருச்சிராப்பள்ளி': 'trichy', 'திருச்சி': 'trichy',
        'madras': 'chennai', 'சென்னை': 'chennai',
        'kovai': 'coimbatore', 'கோயம்புத்தூர்': 'coimbatore', 'கோவை': 'coimbatore',
        'tanjore': 'thanjavur', 'தஞ்சாவூர்': 'thanjavur', 'தஞ்சை': 'thanjavur',
        'tuticorin': 'thoothukudi', 'தூத்துக்குடி': 'thoothukudi',
        'nellai': 'tirunelveli', 'திருநெல்வேலி': 'tirunelveli',
        'pondy': 'puducherry', 'pondicherry': 'puducherry', 'புதுச்சேரி': 'puducherry',
        'chengalpattu': 'chengleput', 'செங்கல்பட்டு': 'chengleput',
        'kancheepuram': 'kanchipuram', 'காஞ்சிபுரம்': 'kanchipuram',
        'madurai': 'madurai', 'மதுரை': 'madurai',
        'salem': 'salem', 'சேலம்': 'salem',
        'ooty': 'udhagamandalam', 'உதகமண்டலம்': 'udhagamandalam',
        'cuddalore': 'cuddalore', 'கடலூர்': 'cuddalore',
        'vellore': 'vellore', 'வேலூர்': 'vellore'
    }

    # SRO Roman & Tamil Numeral Normalization
    SRO_NUMERAL_MAP = {
        'இணை 1': 'joint 1', 'இணை 2': 'joint 2', 'இணை 3': 'joint 3', 'இணை 4': 'joint 4',
        'இணை1': 'joint 1', 'இணை2': 'joint 2', 'இணை3': 'joint 3',
        'joint i': 'joint 1', 'joint ii': 'joint 2', 'joint iii': 'joint 3', 'joint iv': 'joint 4',
        'joint-1': 'joint 1', 'joint-2': 'joint 2', 'joint-i': 'joint 1', 'joint-ii': 'joint 2',
        'joint1': 'joint 1', 'joint2': 'joint 2',
    }

    @staticmethod
    def transliterate_tamil(text: str) -> str:
        """Deterministically transliterates Tamil script to phonetic Latin characters."""
        if not text:
            return ""
        tamil_vowels = {
            'அ': 'a', 'ஆ': 'aa', 'இ': 'i', 'ஈ': 'ee', 'உ': 'u', 'ஊ': 'oo',
            'எ': 'e', 'ஏ': 'ae', 'ஐ': 'ai', 'ஒ': 'o', 'ஓ': 'oo', 'ஔ': 'au'
        }
        tamil_consonants = {
            'க': 'k', 'ங': 'ng', 'ச': 's', 'ஞ': 'ny', 'ட': 't', 'ண': 'n',
            'த': 'th', 'ந': 'n', 'ப': 'p', 'ம': 'm', 'ய': 'y', 'ர': 'r',
            'ல': 'l', 'வ': 'v', 'ழ': 'zh', 'ள': 'l', 'ற': 'r', 'ன': 'n',
            'ஜ': 'j', 'ஷ': 'sh', 'ஸ': 's', 'ஹ': 'h', 'க்ஷ': 'ksh'
        }
        tamil_signs = {
            'ா': 'aa', 'ி': 'i', 'ீ': 'ee', 'ு': 'u', 'ூ': 'oo',
            'ெ': 'e', 'ே': 'ae', 'ை': 'ai', 'ொ': 'o', 'ோ': 'oo', 'ௌ': 'au',
            '்': ''
        }
        res = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            if c in tamil_vowels:
                res.append(tamil_vowels[c])
            elif c in tamil_consonants:
                base = tamil_consonants[c]
                if i + 1 < n and text[i+1] in tamil_signs:
                    sign = tamil_signs[text[i+1]]
                    res.append(base + sign)
                    i += 1
                else:
                    res.append(base + 'a')
            else:
                res.append(c)
            i += 1
        return ''.join(res)

    @classmethod
    def normalize_phonetic_name(cls, name: str) -> str:
        """
        Tier 1 Phonetic Normalizer:
        - Transliterates Tamil script to phonetic Latin.
        - Strips administrative noise (Ward, Block, Village, Taluk, Kiramam, Gramam, etc.).
        - Normalizes Tamil-English phonetic sound pairs (b/p, g/k/c, s/sh, th/t/dh/d, zh/l, rr/r, ee/ea/i, oo/u).
        - Collapses repeated consonants and vowels to prevent transliteration spelling mismatches.
        """
        if not name:
            return ""
        s = cls.transliterate_tamil(str(name)).lower()
        s = re.sub(r'\b(ward|block|village|taluk|district|dist|tk|rev|revenue|kiramam|gramam|kiram|வட்டம்|கிராமம்)\b', ' ', s, flags=re.I)
        s = re.sub(r'[^a-z0-9]', ' ', s)
        sub_pairs = [
            (r'bh|p', 'b'),
            (r'g|c|q|ch', 'k'),
            (r'sh|z', 's'),
            (r'th|dh|d', 't'),
            (r'zh|ll', 'l'),
            (r'rr', 'r'),
            (r'ee|ea|y', 'i'),
            (r'oo|ou', 'u'),
        ]
        for pat, rep in sub_pairs:
            s = re.sub(pat, rep, s)
        s = re.sub(r'([b-df-hj-np-tv-z])\1+', r'\1', s)
        s = re.sub(r'([aeiou])\1+', r'\1', s)
        return re.sub(r'\s+', '', s)

    @classmethod
    def clean_sro_name_for_matching(cls, s: str) -> str:
        """Cleans and normalizes SRO query strings across numeral and city alias variants."""
        if not s:
            return ""
        txt = str(s).lower().strip()
        for k, v in cls.SRO_NUMERAL_MAP.items():
            txt = txt.replace(k, v)
        for k, v in cls.SRO_ALIASES.items():
            txt = re.sub(r'\b' + re.escape(k) + r'\b', v, txt)
            txt = txt.replace(k, v)
        txt = re.sub(r'[^a-z0-9]', '', txt)
        return txt

    @classmethod
    def resolve_sro_hierarchy(
        cls,
        sro_name_or_id: str,
        return_details: bool = False
    ) -> Any:
        """
        Finds zone_id, district_id, sro_id, sro_name from sro_hierarchy.json.
        Applies Tier 1 alias resolution, Arabic/Roman numeral mapping, and fuzzy scoring (threshold >= 0.80).
        Returns:
          - If return_details=False: Dict with SRO info (including 'confidence_score' and 'top_3_candidates') or None.
          - If return_details=True: Tuple (sro_info or None, confidence_score, top_3_candidates).
        """
        import difflib

        if not sro_name_or_id or not str(sro_name_or_id).strip():
            return (None, 0.0, []) if return_details else None

        if not os.path.exists(cls.HIERARCHY_FILE):
            return (None, 0.0, []) if return_details else None

        with open(cls.HIERARCHY_FILE, "r", encoding="utf-8") as f:
            hierarchy = json.load(f)

        raw_query = str(sro_name_or_id).strip()
        q_clean = cls.clean_sro_name_for_matching(raw_query)

        all_candidates = []
        for zone in hierarchy:
            z_id = str(zone.get("zone_id", ""))
            z_name = zone.get("zone_name", "")
            for dist in zone.get("districts", []):
                d_id = str(dist.get("district_id", ""))
                d_name = dist.get("district_name", "")
                for sro in dist.get("sros", []):
                    s_id = str(sro.get("sro_id", ""))
                    s_name = sro.get("sro_name", "")
                    s_clean = cls.clean_sro_name_for_matching(s_name)

                    candidate_info = {
                        "zone_id": z_id,
                        "zone_name": z_name,
                        "district_id": d_id,
                        "district_name": d_name,
                        "sro_id": s_id,
                        "sro_name": s_name
                    }

                    # Exact SRO ID match
                    if raw_query == s_id:
                        candidate_info["confidence_score"] = 1.0
                        candidate_info["top_3_candidates"] = [s_name]
                        return (candidate_info, 1.0, [s_name]) if return_details else candidate_info

                    # Exact normalized name match
                    if q_clean and q_clean == s_clean:
                        candidate_info["confidence_score"] = 1.0
                        candidate_info["top_3_candidates"] = [s_name]
                        return (candidate_info, 1.0, [s_name]) if return_details else candidate_info

                    score = difflib.SequenceMatcher(None, q_clean, s_clean).ratio()
                    all_candidates.append((score, candidate_info))

        if not all_candidates:
            return (None, 0.0, []) if return_details else None

        all_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_candidate = all_candidates[0]
        top_3 = [x[1]["sro_name"] for x in all_candidates[:3]]

        if best_score >= 0.80:
            best_candidate["confidence_score"] = best_score
            best_candidate["top_3_candidates"] = top_3
            return (best_candidate, best_score, top_3) if return_details else best_candidate

        # Failed threshold (< 0.80)
        return (None, best_score, top_3) if return_details else None

    @classmethod
    def fetch_villages_for_sro(
        cls,
        session: requests.Session,
        csrf_token: str,
        sro_id: str,
        is_revenue: bool = False,
        max_attempts: int = 3
    ) -> List[Tuple[str, str]]:
        """Dynamically loads village options for the selected SRO with network retry."""
        action = "loadRevenueVillageCombo" if is_revenue else "loadVillageCombo"
        url = f"{cls.BASE_URL}?requestType=ApplicationRH&actionVal={action}&queryType=Select&screenId=8400001&comboValue={sro_id}&_csrf={csrf_token}"
        
        for attempt in range(1, max_attempts + 1):
            try:
                r = session.post(url, verify=False, timeout=20)
                soup = BeautifulSoup(r.text, 'html.parser')
                options = []
                for opt in soup.find_all('option'):
                    val = opt.get('value', '').strip()
                    txt = opt.get_text(strip=True)
                    if val and val != "0" and val != "-1":
                        options.append((val, txt))
                if options:
                    return options
            except (ConnectionResetError, requests.exceptions.RequestException) as e:
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
            except Exception:
                pass
        return []

    @classmethod
    def match_village_id(cls, village_options: List[Tuple[str, str]], target_village: str) -> Optional[Tuple[str, str]]:
        """Matches target village name against dropdown options with priority on exact and ward matches."""
        matched = cls.expand_and_match_villages(village_options, [target_village])
        return matched[0] if matched else None

    @classmethod
    def expand_and_match_villages(
        cls,
        village_options: List[Tuple[str, str]],
        deed_villages: List[str]
    ) -> List[Tuple[str, str]]:
        """
        Enforces Ward-Aware & Direction-Aware Strict Village Matching with Tier 1 Phonetic Normalization:
        1. If a deed village specifies a specific Ward (e.g. 'Ward -AG' or 'Ward AG'):
           - Matches ONLY portal options for that exact Ward: 'Ward -AG (K.Abishekapuram)'.
           - Strictly excludes all other wards ('Ward -AA', 'Ward -AK', 'Ward -AB', etc.).
        2. If a deed village specifies a Direction (e.g. 'North', 'East', 'West', 'South'):
           - Matches ONLY portal options with that exact direction (e.g. 'Piratiyur East').
           - Strictly excludes conflicting directions.
        3. If a deed village has NO Ward and NO Direction (e.g. historical revenue village 'K-Abishekapuram' or 'Piratiyur'):
           - Matches the parent base village option without ward or direction if available.
           - Falls back to bifurcated directional options only if no base option exists.
        4. Zero Spurious Fallback:
           - Returns ONLY verified matches. Never blindly returns village_options[0] if deed villages fail to match.
        """
        import difflib

        def extract_ward(name: str) -> Optional[str]:
            tamil_ward_map = {"ஏஜி": "AG", "ஏ": "A", "பி": "B", "சி": "C", "டி": "D", "இ": "E", "எச்": "H", "கே": "K"}
            name_norm = str(name)
            for tm, en in tamil_ward_map.items():
                name_norm = name_norm.replace(tm, en)
            m = re.search(r'(?:\bward\b|வார்டு)\s*[-_]?\s*([a-zA-Z0-9]+)\b', name_norm, re.I)
            return m.group(1).upper() if m else None

        def extract_direction(name: str) -> Optional[str]:
            dir_map = {
                'north': 'NORTH', 'vadakku': 'NORTH', 'வடக்கு': 'NORTH',
                'south': 'SOUTH', 'therku': 'SOUTH', 'தெற்கு': 'SOUTH',
                'east': 'EAST', 'kizhakku': 'EAST', 'கிழக்கு': 'EAST',
                'west': 'WEST', 'merku': 'WEST', 'மேற்கு': 'WEST'
            }
            m = re.search(r'\b(north|south|east|west|vadakku|therku|kizhakku|merku|வடக்கு|தெற்கு|கிழக்கு|மேற்கு)\b', str(name), re.I)
            return dir_map.get(m.group(1).lower()) if m else None

        matched_dict = {}

        for d_name in deed_villages:
            if not d_name or not str(d_name).strip():
                continue

            d_ward = extract_ward(d_name)
            d_dir = extract_direction(d_name)
            d_phonetic = cls.normalize_phonetic_name(d_name)

            if d_ward:
                # 1. Ward-specific match: must match exact ward and base village phonetic
                for v_id, v_name in village_options:
                    v_ward = extract_ward(v_name)
                    if v_ward and v_ward == d_ward:
                        v_phonetic = cls.normalize_phonetic_name(v_name)
                        score = difflib.SequenceMatcher(None, d_phonetic, v_phonetic).ratio()
                        if score >= 0.70:
                            matched_dict[v_id] = v_name
            else:
                # 2. Non-ward match: exclude portal options that possess a ward
                non_ward_opts = [(vid, vn) for vid, vn in village_options if not extract_ward(vn)]
                if d_dir:
                    # Deed specifies direction: match only portal option with same direction
                    for v_id, v_name in non_ward_opts:
                        v_dir = extract_direction(v_name)
                        if v_dir and v_dir == d_dir:
                            v_phonetic = cls.normalize_phonetic_name(v_name)
                            score = difflib.SequenceMatcher(None, d_phonetic, v_phonetic).ratio()
                            if score >= 0.80:
                                matched_dict[v_id] = v_name
                else:
                    # Deed has NO direction: prefer portal options with NO direction
                    base_opts = [(vid, vn) for vid, vn in non_ward_opts if not extract_direction(vn)]
                    target_opts = base_opts if base_opts else non_ward_opts
                    for v_id, v_name in target_opts:
                        v_phonetic = cls.normalize_phonetic_name(v_name)
                        score = difflib.SequenceMatcher(None, d_phonetic, v_phonetic).ratio()
                        if score >= 0.80:
                            matched_dict[v_id] = v_name

        return list(matched_dict.items())

    @classmethod
    def match_villages_with_dual_registry(
        cls,
        session: requests.Session,
        csrf_token: str,
        sro_id: str,
        deed_villages: List[str],
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Tier 1 & Tier 3 Dual-Registry Resolver & Strict Audit Shield:
        1. Queries loadVillageCombo (Registration Registry).
        2. If any deed village has 0 matches, automatically queries loadRevenueVillageCombo (Revenue Registry).
        3. If any deed village remains unresolved (confidence < 0.80 across both registries):
           - DO NOT SILENTLY BYPASS.
           - Emits prominent CRITICAL AUDIT BLOCKER with top 3 candidate suggestions.
           - Flags audit blocker to halt false clean title opinions.
        """
        import difflib

        def log(msg):
            if log_callback: log_callback(msg)
            else: print(msg)

        def extract_ward(name: str) -> Optional[str]:
            tamil_ward_map = {"ஏஜி": "AG", "ஏ": "A", "பி": "B", "சி": "C", "டி": "D", "இ": "E", "எச்": "H", "கே": "K"}
            name_norm = str(name)
            for tm, en in tamil_ward_map.items():
                name_norm = name_norm.replace(tm, en)
            m = re.search(r'(?:\bward\b|வார்டு)\s*[-_]?\s*([a-zA-Z0-9]+)\b', name_norm, re.I)
            return m.group(1).upper() if m else None

        def extract_direction(name: str) -> Optional[str]:
            dir_map = {
                'north': 'NORTH', 'vadakku': 'NORTH', 'வடக்கு': 'NORTH',
                'south': 'SOUTH', 'therku': 'SOUTH', 'தெற்கு': 'SOUTH',
                'east': 'EAST', 'kizhakku': 'EAST', 'கிழக்கு': 'EAST',
                'west': 'WEST', 'merku': 'WEST', 'மேற்கு': 'WEST'
            }
            m = re.search(r'\b(north|south|east|west|vadakku|therku|kizhakku|merku|வடக்கு|தெற்கு|கிழக்கு|மேற்கு)\b', str(name), re.I)
            return dir_map.get(m.group(1).lower()) if m else None

        # 1. Query Registration Registry
        reg_options = cls.fetch_villages_for_sro(session, csrf_token, sro_id, is_revenue=False)
        matched_reg = cls.expand_and_match_villages(reg_options, deed_villages)
        
        matched_dict = {v_id: (v_name, "REGISTRATION") for v_id, v_name in matched_reg}

        # Check which deed villages were satisfied by registration options
        def is_deed_village_satisfied(dv: str, matched_list: List[Tuple[str, str]]) -> bool:
            d_ward = extract_ward(dv)
            d_dir = extract_direction(dv)
            dv_norm = cls.normalize_phonetic_name(dv)
            for _, mv_name in matched_list:
                m_ward = extract_ward(mv_name)
                m_dir = extract_direction(mv_name)
                if d_ward != m_ward:
                    continue
                if d_dir != m_dir:
                    continue
                mv_norm = cls.normalize_phonetic_name(mv_name)
                if difflib.SequenceMatcher(None, dv_norm, mv_norm).ratio() >= 0.70:
                    return True
            return False

        unmatched_deed_villages = [
            dv for dv in deed_villages 
            if dv and str(dv).strip() and not is_deed_village_satisfied(dv, matched_reg)
        ]

        rev_options = []
        if unmatched_deed_villages:
            log(f"      [⇄] Dual-Registry Fallback: Deed village(s) {unmatched_deed_villages} not in Registration dropdown. Querying Revenue registry (loadRevenueVillageCombo)...")
            rev_options = cls.fetch_villages_for_sro(session, csrf_token, sro_id, is_revenue=True)
            matched_rev = cls.expand_and_match_villages(rev_options, unmatched_deed_villages)
            for v_id, v_name in matched_rev:
                matched_dict[v_id] = (v_name, "REVENUE")

            # Re-evaluate unsatisfied after revenue lookup
            all_current_matched = [(vid, vinfo[0]) for vid, vinfo in matched_dict.items()]
            unmatched_deed_villages = [
                dv for dv in deed_villages 
                if dv and str(dv).strip() and not is_deed_village_satisfied(dv, all_current_matched)
            ]

        # TIER 3: The Strict Audit Shield (Zero Silent Bypassing)
        unresolved_details = []
        all_portal_options = reg_options + rev_options

        if unmatched_deed_villages:
            for bad_v in unmatched_deed_villages:
                bad_norm = cls.normalize_phonetic_name(bad_v)
                candidate_scores = []
                for v_id, v_name in all_portal_options:
                    v_norm = cls.normalize_phonetic_name(v_name)
                    score = difflib.SequenceMatcher(None, bad_norm, v_norm).ratio()
                    candidate_scores.append((score, v_name))
                candidate_scores.sort(key=lambda x: x[0], reverse=True)
                top_3 = candidate_scores[:3]

                log("\n" + "=" * 76)
                log("CRITICAL AUDIT BLOCKER: UNRESOLVED DEED VILLAGE")
                log("=" * 76)
                log(f"  Deed Village String: '{bad_v}'")
                log(f"  SRO ID: {sro_id}")
                log("  Dual-Registry Status: 0 matches in Registration (loadVillageCombo) & Revenue (loadRevenueVillageCombo)")
                log("  Top 3 Closest Candidate Suggestions:")
                for c_idx, (c_score, c_name) in enumerate(top_3, 1):
                    log(f"    {c_idx}. '{c_name}' (Phonetic Confidence: {c_score:.2f})")
                log("  ACTION REQUIRED: Pausing search track to prevent false clean title opinion.")
                log("=" * 76 + "\n")

                unresolved_details.append({
                    "deed_village": bad_v,
                    "sro_id": sro_id,
                    "confidence_score": top_3[0][0] if top_3 else 0.0,
                    "top_3_candidates": [c[1] for c in top_3]
                })

        return {
            "matched_villages": [(v_id, v_info[0]) for v_id, v_info in matched_dict.items()],
            "matched_details": [{"village_id": v_id, "village_name": v_info[0], "registry": v_info[1]} for v_id, v_info in matched_dict.items()],
            "unresolved_villages": unresolved_details,
            "has_blockers": len(unresolved_details) > 0,
            "total_options_available": len(all_portal_options)
        }

    # Portal "busy" pages that are delivered as a (valid-looking) PDF instead of a certificate.
    # Certificate print/download retries for transient portal errors ("Please try after sometime").
    PRINT_MAX_ATTEMPTS = 4
    TRANSIENT_BACKOFF_S = (3, 6, 12)
    EC_TRANSIENT_HTML_RE = re.compile(r'(?:Please\s*try\s*after\s*some\s*time|try\s*again\s*later)', re.I)
    EC_ERROR_PAGE_RE = re.compile(r'(?:Please\s*try\s*after\s*some\s*time|HTML_CONTENT|try\s*again\s*later)', re.I)
    EC_ERROR_COUNT_RE = re.compile(r'No\.?\s*Of\s*Records\s*:+\s*([0-9]+)', re.I)
    EC_CERT_MARKER_RE = re.compile(r'(?:Encumbrance|வில்லங்க|Number\s*of\s*Entries|Document\s*No)', re.I)

    @classmethod
    def inspect_ec_pdf(cls, content: bytes) -> Dict[str, Any]:
        """
        Deterministically classifies downloaded bytes as an authentic EC certificate or not.
        Byte-level checks alone miss error pages because PDF text streams are compressed,
        so the text layer of the first pages is inspected.
        Returns {"authentic", "reason", "pages", "error_record_count"}.
        """
        info = {"authentic": False, "reason": "", "pages": 0, "error_record_count": None}
        if not content or not content.startswith(b'%PDF'):
            info["reason"] = "NOT_A_PDF"
            return info
        if b'HTML_CONTENT' in content or b'Please try after sometime' in content:
            info["reason"] = "PORTAL_ERROR_PAGE"
            return info
        try:
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            info["pages"] = len(reader.pages)
            text = " ".join((reader.pages[i].extract_text() or "") for i in range(min(2, len(reader.pages))))
        except Exception as e:
            info["reason"] = f"UNREADABLE_PDF: {e}"
            return info
        cnt = cls.EC_ERROR_COUNT_RE.search(text)
        if cls.EC_ERROR_PAGE_RE.search(text):
            info["reason"] = "PORTAL_ERROR_PAGE"
            if cnt:
                info["error_record_count"] = int(cnt.group(1))
            return info
        if info["pages"] == 0 or not text.strip():
            info["reason"] = "EMPTY_PDF"
            return info
        if not cls.EC_CERT_MARKER_RE.search(text):
            info["reason"] = "NOT_AN_EC_CERTIFICATE"
            return info
        info["authentic"] = True
        info["reason"] = "OK"
        return info

    @classmethod
    def execute_ec_search(
        cls,
        session: requests.Session,
        auth_token: str,
        csrf_token: str,
        captcha_code: str,
        sro_info: Dict[str, str],
        village_id: str = "",
        survey_no: str = "",
        subdivision_no: str = "",
        start_date: str = "",
        end_date: str = "",
        survey_items: Optional[List[Dict[str, str]]] = None,
        is_ward_block: bool = False,
        ward_no: str = "",
        block_no: str = "",
        output_pdf_path: str = "",
        base_form_fields: Optional[List[Tuple[str, str]]] = None,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Submits searchDocYearWise to TNREGINET for the given SRO, villages, and survey numbers.
        Detects if email submission prompt appears (triggering binary date halving),
        downloads real official PDF if Acknowledgement / dwnLoadPdf link is returned,
        or extracts table rows if rendered synchronously.
        """
        def log(m):
            if log_callback: log_callback(m)
            else: print(m)

        desc = f"SF={survey_no}/{subdivision_no}" if not survey_items else f"{len(survey_items)} survey items"
        log(f"[*] Querying EC: SRO={sro_info['sro_name']}, {desc}, Period={start_date} to {end_date}...")

        def update_or_add(lst, key, val):
            for i, (k, v) in enumerate(lst):
                if k == key:
                    lst[i] = (key, val)
                    return
            lst.append((key, val))

        # Dynamically harvest base_form_fields if not supplied
        if not base_form_fields:
            try:
                r_base = session.get(cls.EC_SEARCH_URL, verify=False, timeout=25)
                soup_b = BeautifulSoup(r_base.text, 'html.parser')
                ec_form = soup_b.find('form', {'id': 'EncumbranceCertificateForm'})
                if ec_form:
                    base_form_fields = []
                    for inp in ec_form.find_all(['input', 'select']):
                        nm = inp.get('name')
                        if not nm or nm in ['btn_SearchDoc', 'btn_ResetForm', 'btn_AddSurvey', 'btn_UpdateSurvey', 'submitPersonalDetail', 'btn_selectDoc']:
                            continue
                        vl = inp.get('value', '')
                        if inp.name == 'select':
                            opt = inp.find('option', selected=True)
                            vl = opt.get('value', '') if opt else ''
                        base_form_fields.append((nm, vl))
            except Exception:
                pass

        if base_form_fields:
            payload = [item for item in base_form_fields if item[0] not in ['multi_cmb_Village', 'multi_SurveyNo', 'multi_SubDivisionNo']]
        else:
            payload = [
                ('requestType', 'ApplicationRH'),
                ('actionVal', 'searchDocYearWise'),
                ('screenId', '8400001'),
                ('menuCode', '8400010'),
                ('documentNo', ''),
                ('browserDetails', 'None'),
                ('isRevenueVillage', 'false'),
                ('formId', 'EncumbranceCertificateForm'),
                ('showBookFlag', 'false'),
                ('showDateFlag', 'true'),
                ('divId', 'searchComponentSection'),
                ('applyOnline', 'false'),
                ('loggedInGuest', 'false'),
                ('authToken', auth_token),
                ('DOC_SEARCH', '1'),
                ('VILLAGE_SELECTION', 'false'),
                ('validVillage', '2'),
                ('countNoRecords', '0'),
                ('isECValid', 'N'),
                ('tmpltMstID', ''),
                ('previewFlagFrmCnfg', 'true'),
                ('landDocIndexId', ''),
                ('jsonString', ''),
                ('docCreateAppId', '8400001'),
                ('appTransId', '0'),
                ('backUrl', ''),
                ('templateIds', ''),
                ('multiVillageLimitEC', '3'),
            ]

        update_or_add(payload, 'requestType', 'ApplicationRH')
        update_or_add(payload, 'actionVal', 'searchDocYearWise')
        update_or_add(payload, 'screenId', '8400001')
        update_or_add(payload, 'divId', 'searchComponentSection')
        update_or_add(payload, 'isPlotFlatWise', 'false')
        update_or_add(payload, 'isRevenueVillage', 'false')
        update_or_add(payload, 'sroName', sro_info['sro_name'])
        update_or_add(payload, 'cmb_Zone', sro_info['zone_id'])
        update_or_add(payload, 'cmb_District', sro_info['district_id'])
        update_or_add(payload, 'cmb_SroName', sro_info['sro_id'])
        update_or_add(payload, 'hdnZone', sro_info['zone_id'])
        update_or_add(payload, 'hdnDistrict', sro_info['district_id'])
        update_or_add(payload, 'hdnSroName', sro_info['sro_id'])
        update_or_add(payload, 'txt_PeriodStartDt', start_date)
        update_or_add(payload, 'txt_PeriodEndDt', end_date)
        update_or_add(payload, 'txt_Captcha', captcha_code)
        update_or_add(payload, 'captcha_val', captcha_code)
        update_or_add(payload, '_csrf', csrf_token)

        # Multi survey items (up to 3 unique villages allowed by portal)
        if survey_items:
            for s_item in survey_items:
                payload.append(('multi_cmb_Village', str(s_item.get('village_id', ''))))
                payload.append(('multi_SurveyNo', str(s_item.get('survey_no', ''))))
                payload.append(('multi_SubDivisionNo', str(s_item.get('subdivision_no', '') or '')))
        else:
            payload.append(('multi_cmb_Village', village_id))
            payload.append(('multi_SurveyNo', survey_no))
            payload.append(('multi_SubDivisionNo', subdivision_no or ''))

        if is_ward_block:
            update_or_add(payload, 'actionVal', 'searchWardBlockDetails')
            update_or_add(payload, 'DOC_SEARCH', '4')
            update_or_add(payload, 'isWardBlockWise', 'true')
            update_or_add(payload, 'isPlotFlatWise', 'false')
            if ward_no:
                update_or_add(payload, 'wardNo', ward_no)
                payload.append(('multi_ward', ward_no))
                payload.append(('multi_ward_id', ward_no))
            if block_no:
                update_or_add(payload, 'blockNo', block_no)
                payload.append(('multi_block', block_no))
            if village_id:
                payload.append(('multi_cmb_Town', village_id))
                payload.append(('multi_cmb_Town_Id', village_id))
            search_url = f"{cls.BASE_URL}?requestType=ApplicationRH&actionVal=searchWardBlockDetails&screenId=8400001&divId=searchComponentSection&isWardBlockWise=true&_csrf={csrf_token}"
        else:
            search_url = f"{cls.BASE_URL}?requestType=ApplicationRH&actionVal=searchDocYearWise&screenId=8400001&divId=searchComponentSection&isPlotFlatWise=false&_csrf={csrf_token}"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': cls.EC_SEARCH_URL
        }

        resp = None
        for attempt in range(1, 4):
            try:
                resp = session.post(search_url, data=payload, headers=headers, verify=False, timeout=45)
                break
            except (ConnectionResetError, requests.exceptions.RequestException, Exception) as e_post:
                log(f"      [!] searchDocYearWise network error (attempt {attempt}/3): {e_post}")
                if attempt < 3:
                    backoff = 2 * attempt
                    log(f"      [⇄] Retrying search query in {backoff}s...")
                    time.sleep(backoff)
                else:
                    raise

        if output_pdf_path:
            with open(output_pdf_path + ".search_resp.html", "w", encoding="utf-8") as f:
                f.write(resp.text)

        # 1. Parse authoritative record count from TNREGINET form field
        count_match = re.search(r'name=["\']countNoRecords["\'][^>]*value=["\'](\d+)["\']', resp.text, re.I)
        rec_count = int(count_match.group(1)) if count_match else 0
        count_field_present = bool(count_match)
        # 2. Check if table rows are actually rendered
        soup_resp = BeautifulSoup(resp.text, 'html.parser')
        doc_table = soup_resp.find('table', id='DocPropertyDesc')
        has_table_rows = bool(doc_table and len(doc_table.find_all('tr')) > 1)
        has_items_banner = "items found" in resp.text and "0 items found" not in resp.text and "No items found" not in resp.text
        has_results = has_table_rows or has_items_banner
        # 2b. Transient portal error on the search step itself (no authoritative count rendered)
        if not count_field_present and not has_results and cls.EC_TRANSIENT_HTML_RE.search(resp.text or ""):
            log(f"      [!] Portal transient error on search step ('try after sometime'); no countNoRecords rendered.")
            return {
                "success": False,
                "overflow": False,
                "split_needed": False,
                "nil": False,
                "transient": True,
                "error": "Portal transient error on search step",
                "pdf_saved": None,
                "records": [],
                "pdf_status": "PORTAL_TRANSIENT_ERROR",
                "portal_record_count": None,
                "count_field_present": False
            }
        # 3. Universal Overflow Evaluation (HTML countNoRecords / explicit overflow prompt only)
        is_overflow = False
        if rec_count >= 200:
            is_overflow = True
        elif ECDateSplitter.is_overflow_message(resp.text):
            is_overflow = True
        if is_overflow:
            log(f"      [!] Alert: Query returned {rec_count or '>200'} records, exceeding portal 200-record threshold.")
            log(f"      [⇄] Triggering Adaptive Binary Date Halving...")
            return {
                "success": False,
                "overflow": True,
                "split_needed": True,
                "error": f"Portal overflow ({rec_count} records) - date halving required",
                "pdf_status": "OVERFLOW",
                "portal_record_count": rec_count,
                "count_field_present": count_field_present
            }
        if not has_results and rec_count == 0:
            log(f"      [i] Nil encumbrance: No documents registered during search period ({start_date} to {end_date}).")
            return {
                "success": True,
                "overflow": False,
                "split_needed": False,
                "nil": True,
                "entries_found": 0,
                "pdf_saved": None,
                "records": [],
                "pdf_status": "NIL",
                "portal_record_count": rec_count,
                "count_field_present": count_field_present
            }

        # 3. Trigger official PDF generation on portal (directPrintDwnLoad screenId=700786)
        pdf_downloaded_path = None
        pdf_status = "NOT_GENERATED"
        pdf_inspection: Dict[str, Any] = {}
        for p_attempt in range(1, cls.PRINT_MAX_ATTEMPTS + 1):
            try:
                print_payload = list(payload)
                update_or_add(print_payload, 'requestType', 'ApplicationRH')
                update_or_add(print_payload, 'actionVal', 'directPrintDwnLoad')
                update_or_add(print_payload, 'screenId', '700786')
                # Primary Government portal template: 8400004 (770.91 pt width, fits cleanly in A4 Landscape)
                update_or_add(print_payload, 'tmpltMstID', '8400004')
                if is_ward_block:
                    update_or_add(print_payload, 'backUrl', 'webHP?requestType=ApplicationRH&actionVal=openEncumbranceCertSearch&screenId=8400001&scenarioId=2&ECSrcJSP=searchWardBlockWise')
                else:
                    update_or_add(print_payload, 'backUrl', 'webHP?requestType=ApplicationRH&actionVal=openEncumbranceCertSearch&screenId=8400001&scenarioId=2&ECSrcJSP=SearchDocYearWise')
                update_or_add(print_payload, '_csrf', csrf_token)

                print_url = f"{cls.BASE_URL}?requestType=ApplicationRH&actionVal=directPrintDwnLoad&screenId=700786&_csrf={csrf_token}"
                p_resp = session.post(print_url, data=print_payload, verify=False, timeout=45)

                m_pdf = re.search(r'href=[\'"]([^\'"]*actionVal=dwnLoadPdf[^\'"]*)[\'"]', p_resp.text)
                if not m_pdf:
                    # Fallback to tmpltMstID 8400003 only if 8400004 is unavailable
                    update_or_add(print_payload, 'tmpltMstID', '8400003')
                    p_resp2 = session.post(print_url, data=print_payload, verify=False, timeout=45)
                    m_pdf = re.search(r'href=[\'"]([^\'"]*actionVal=dwnLoadPdf[^\'"]*)[\'"]', p_resp2.text)
                if not m_pdf:
                    # Check original search response just in case
                    m_pdf = re.search(r'href=[\'"]([^\'"]*actionVal=dwnLoadPdf[^\'"]*)[\'"]', resp.text)

                if m_pdf:
                    pdf_rel = m_pdf.group(1).replace('&amp;', '&')
                    pdf_url = f"https://tnreginet.gov.in/portal/{pdf_rel}" if not pdf_rel.startswith('http') else pdf_rel
                    log(f"      [✓] Acknowledgement received from TNREGINET: Official Government EC PDF ready at {pdf_url}")
                    dl_resp = session.get(pdf_url, verify=False, timeout=60)
                    pdf_inspection = cls.inspect_ec_pdf(dl_resp.content)
                    if pdf_inspection.get("authentic") and output_pdf_path:
                        with open(output_pdf_path, 'wb') as pf:
                            pf.write(dl_resp.content)
                        pdf_downloaded_path = output_pdf_path
                        pdf_status = "CERTIFIED"
                        log(f"      [✓] Successfully downloaded raw government EC PDF ({len(dl_resp.content)} bytes, {pdf_inspection.get('pages')} pages) -> {output_pdf_path}")
                        break
                    err_cnt = pdf_inspection.get("error_record_count")
                    # The "Please try after sometime ... No Of Records:: N" page is a TRANSIENT certificate
                    # generator error. Its N is a stale template value (it reads 206 even for a single day),
                    # so it is never used as a window count and never triggers date halving. The search
                    # HTML countNoRecords above is the only authoritative count.
                    pdf_status = "PORTAL_TRANSIENT_ERROR" if pdf_inspection.get("reason") == "PORTAL_ERROR_PAGE" else "ERROR_PAGE"
                    log(f"      [!] Portal returned a non-certificate PDF ({pdf_inspection.get('reason')}, {len(dl_resp.content)} bytes"
                        f"{', error-page text says ' + str(err_cnt) + ' records (ignored; HTML count=' + str(rec_count) + ')' if err_cnt is not None else ''}). "
                        f"Not saved as an EC. Retrying same window (attempt {p_attempt}/{cls.PRINT_MAX_ATTEMPTS}).")
                    if p_attempt < cls.PRINT_MAX_ATTEMPTS:
                        time.sleep(cls.TRANSIENT_BACKOFF_S[min(p_attempt - 1, len(cls.TRANSIENT_BACKOFF_S) - 1)])
                        continue
                break
            except (ConnectionResetError, requests.exceptions.RequestException, Exception) as e_print:
                log(f"      [!] directPrintDwnLoad network notice (attempt {p_attempt}/{cls.PRINT_MAX_ATTEMPTS}): {e_print}")
                if p_attempt < cls.PRINT_MAX_ATTEMPTS:
                    time.sleep(2 * p_attempt)
                else:
                    log(f"      [!] directPrintDwnLoad ended: {e_print}")

        # 4. Helper to parse records from HTML soup
        def _extract_page_records(soup_obj):
            recs = []
            for t in soup_obj.find_all('table'):
                rows = t.find_all('tr')
                if not rows: continue
                hdr = [c.get_text(strip=True).lower() for c in rows[0].find_all(['th', 'td'])]
                if any('document no' in h for h in hdr):
                    for r in rows[1:]:
                        cols = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
                        if len(cols) >= 6:
                            doc_raw = cols[0]
                            nums = re.findall(r'\d+', doc_raw)
                            doc_no = nums[-2] if len(nums) >= 2 else doc_raw
                            year = nums[-1] if len(nums) >= 2 else ""
                            recs.append({
                                "doc_raw": doc_raw,
                                "doc_no": doc_no,
                                "year": year,
                                "sro_name": cols[1],
                                "district": cols[2],
                                "village": cols[3],
                                "survey_no": cols[4],
                                "property_type": cols[5]
                            })
            return recs

        all_records = []
        soup1 = BeautifulSoup(resp.text, 'html.parser')
        all_records.extend(_extract_page_records(soup1))

        # Check for pagination links
        pag_links = []
        for a in soup1.find_all('a'):
            href = a.get('href', '')
            if 'd-' in href and '-p=' in href and href not in [l[0] for l in pag_links]:
                txt = a.get_text(strip=True)
                if txt.isdigit():
                    pag_links.append((href, int(txt)))

        pag_links.sort(key=lambda x: x[1])
        if pag_links:
            log(f"      [+] Fetching {len(pag_links)} additional pagination pages from portal...")
            for href, p_num in pag_links:
                full_p_url = "https://tnreginet.gov.in" + href if href.startswith('/') else href
                try:
                    r_p = session.get(full_p_url, verify=False, timeout=20)
                    soup_p = BeautifulSoup(r_p.text, 'html.parser')
                    p_recs = _extract_page_records(soup_p)
                    all_records.extend(p_recs)
                except Exception as e_p:
                    log(f"      [!] Page {p_num} retrieval notice: {e_p}")

        log(f"      [✓] Retrieved {len(all_records)} official encumbrance records from TNREGINET for {start_date} to {end_date}!")

        # Save discovery records to JSON
        records_json_path = output_pdf_path.replace('.pdf', '_records.json') if output_pdf_path else None
        if records_json_path:
            with open(records_json_path, 'w', encoding='utf-8') as f:
                json.dump(all_records, f, indent=2, ensure_ascii=False)

        if pdf_status == "PORTAL_TRANSIENT_ERROR":
            return {
                "success": False,
                "overflow": False,
                "split_needed": False,
                "nil": False,
                "transient": True,
                "error": f"Portal transient error ('Please try after sometime') persisted after {cls.PRINT_MAX_ATTEMPTS} certificate attempts",
                "entries_found": len(all_records),
                "records": all_records,
                "records_json": records_json_path,
                "pdf_saved": None,
                "pdf_status": pdf_status,
                "pdf_inspection": pdf_inspection,
                "portal_record_count": rec_count,
                "count_field_present": count_field_present
            }
        return {
            "success": True,
            "overflow": False,
            "split_needed": False,
            "nil": False,
            "entries_found": len(all_records),
            "records": all_records,
            "records_json": records_json_path,
            "pdf_saved": pdf_downloaded_path,
            "pdf_status": pdf_status,
            "pdf_inspection": pdf_inspection,
            "portal_record_count": rec_count,
            "count_field_present": count_field_present
        }

    @classmethod
    def execute_ec_search_with_halving(
        cls,
        session: requests.Session,
        auth_token: str,
        csrf_token: str,
        captcha_code: str,
        sro_info: Dict[str, str],
        village_id: str = "",
        survey_no: str = "",
        subdivision_no: str = "",
        start_date: str = "",
        end_date: str = "",
        survey_items: Optional[List[Dict[str, str]]] = None,
        is_ward_block: bool = False,
        ward_no: str = "",
        block_no: str = "",
        output_pdf_path: str = "",
        base_form_fields: Optional[List[Tuple[str, str]]] = None,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Executes EC search with recursive adaptive binary date halving.
        If the date window exceeds the synchronous portal capacity (prompting for email submission),
        the interval is recursively split in half, each half is downloaded, and the raw PDFs
        are merged chronologically using pypdf.PdfWriter into output_pdf_path.
        """
        def log(m):
            if log_callback: log_callback(m)
            else: print(m)

        # Attempt search on current window
        res = cls.execute_ec_search(
            session=session,
            auth_token=auth_token,
            csrf_token=csrf_token,
            captcha_code=captcha_code,
            sro_info=sro_info,
            village_id=village_id,
            survey_no=survey_no,
            subdivision_no=subdivision_no,
            start_date=start_date,
            end_date=end_date,
            survey_items=survey_items,
            is_ward_block=is_ward_block,
            ward_no=ward_no,
            block_no=block_no,
            output_pdf_path=output_pdf_path,
            base_form_fields=base_form_fields,
            log_callback=log_callback
        )

        if not res.get("split_needed") and not res.get("overflow"):
            return res

        log(f"[*] Overflow / Email prompt encountered for {start_date} to {end_date}. Halving date interval...")
        (left_start, left_end), (right_start, right_end) = ECDateSplitter.split_interval(start_date, end_date)
        log(f"[*] Left half: {left_start} to {left_end}; Right half: {right_start} to {right_end}")

        import pypdf

        left_pdf = output_pdf_path.replace(".pdf", f"_{left_start}_{left_end}.pdf") if output_pdf_path else ""
        right_pdf = output_pdf_path.replace(".pdf", f"_{right_start}_{right_end}.pdf") if output_pdf_path else ""

        left_res = cls.execute_ec_search_with_halving(
            session=session,
            auth_token=auth_token,
            csrf_token=csrf_token,
            captcha_code=captcha_code,
            sro_info=sro_info,
            village_id=village_id,
            survey_no=survey_no,
            subdivision_no=subdivision_no,
            start_date=left_start,
            end_date=left_end,
            survey_items=survey_items,
            is_ward_block=is_ward_block,
            ward_no=ward_no,
            block_no=block_no,
            output_pdf_path=left_pdf,
            base_form_fields=base_form_fields,
            log_callback=log_callback
        )

        right_res = cls.execute_ec_search_with_halving(
            session=session,
            auth_token=auth_token,
            csrf_token=csrf_token,
            captcha_code=captcha_code,
            sro_info=sro_info,
            village_id=village_id,
            survey_no=survey_no,
            subdivision_no=subdivision_no,
            start_date=right_start,
            end_date=right_end,
            survey_items=survey_items,
            is_ward_block=is_ward_block,
            ward_no=ward_no,
            block_no=block_no,
            output_pdf_path=right_pdf,
            base_form_fields=base_form_fields,
            log_callback=log_callback
        )

        combined_records = (left_res.get("records") or []) + (right_res.get("records") or [])
        pdf_files_to_merge = []
        for p in [left_res.get("pdf_saved"), right_res.get("pdf_saved")]:
            if p and os.path.exists(p) and os.path.getsize(p) > 1000:
                pdf_files_to_merge.append(p)

        merged_pdf = None
        if output_pdf_path:
            if len(pdf_files_to_merge) == 1:
                import shutil
                shutil.copyfile(pdf_files_to_merge[0], output_pdf_path)
                merged_pdf = output_pdf_path
            elif len(pdf_files_to_merge) > 1:
                writer = pypdf.PdfWriter()
                for pf in pdf_files_to_merge:
                    writer.append(pf)
                with open(output_pdf_path, "wb") as f_out:
                    writer.write(f_out)
                writer.close()
                merged_pdf = output_pdf_path
                log(f"[✓] Merged {len(pdf_files_to_merge)} chunk PDFs period-wise into: {output_pdf_path}")

            # Clean up intermediate chunk files if they differ from output_pdf_path
            for pf in pdf_files_to_merge:
                if pf != output_pdf_path and os.path.exists(pf):
                    try: os.remove(pf)
                    except OSError: pass

        return {
            "success": True,
            "overflow": False,
            "split_needed": False,
            "nil": len(combined_records) == 0 and not merged_pdf,
            "entries_found": len(combined_records),
            "records": combined_records,
            "pdf_saved": merged_pdf
        }
