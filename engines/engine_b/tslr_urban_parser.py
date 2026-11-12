"""
tslr_urban_parser.py - Deterministic Urban Town Survey Land Record (TSLR) identity parser
=====================================================================================
Pure-Python, rule-based (zero LLM) detection of urban municipal survey coordinates in
Tamil Nadu deed schedules, so Engine B can plan a WARD_BLOCK_WISE encumbrance search instead
of a rural SURVEY_WISE search that returns "0 records" after TSLR conversion.

Recognised forms (Tamil + English, legacy-glyph normalised, any spacing / punctuation):
  Ward   : வார்டு, வார்ட், Ward, Ward No., வார்டு எண் / நம்பர் / நெ.
  Block  : பிளாக், ப்ளாக், பிளாக்கு, Block, Block No., பிளாக் எண் / நம்பர் / நெ.
  T.S.No : டி.எஸ்.நெ., டி.எஸ்.எண், டி.எஸ். நம்பர், டி.எஸ்.எல்.ஆர், T.S.No., TS No, T.S.,
           TSLR No, Town Survey No., டவுன் சர்வே எண், நகர அளவை எண், நகர நில அளவை எண்,
           நகரளவை எண், நகர சர்வே எண்
  Qualifiers: புதிய / New / தற்போதைய / Present  (current)  vs
              பழைய / Old / முந்தைய / Former / Previous / முன்னாள் (historical)

Ward codes written as Tamil letter names ("ஏஜே", "ஏ.ஜே", "ஏ-ஜே") are transliterated to the
portal's Latin code ("AJ"). Letters that are genuinely ambiguous in Tamil script (பி = B/P,
டி = D/T) default to the conventional reading and the alternates are reported so the planner
can query each deterministic variant.
"""

import re
import itertools
from typing import Any, Dict, List, Optional, Tuple


def _normalize_tamil(text: str) -> str:
    """Swap legacy pre-vowel glyph order (e.g. 'ெந' -> 'நெ') - mirrors PDFDeterministicExtractor."""
    if not text:
        return ""
    return re.sub(r'([\u0BC6\u0BC7\u0BC8])([\u0B95-\u0BB9])', r'\2\1', str(text))


class TSLRUrbanParser:
    """Deterministic urban TSLR (Ward / Block / Town Survey) extractor."""

    # Tamil letter names -> Latin letter. Longest names are matched first.
    TAMIL_LETTER_NAMES: Dict[str, str] = {
        'டபிள்யூ': 'W', 'டபுள்யூ': 'W', 'டபிள்யு': 'W',
        'எக்ஸ்': 'X', 'க்யூ': 'Q', 'கியூ': 'Q', 'இசட்': 'Z', 'இஸட்': 'Z',
        'ஹெச்': 'H', 'எச்': 'H', 'எஃப்': 'F', 'எப்': 'F',
        'எல்': 'L', 'எம்': 'M', 'என்': 'N', 'ஆர்': 'R', 'எஸ்': 'S', 'ஒய்': 'Y',
        'ஏ': 'A', 'பீ': 'B', 'பி': 'B', 'சீ': 'C', 'சி': 'C', 'டீ': 'D', 'டி': 'D',
        'ஈ': 'E', 'இ': 'E', 'ஜீ': 'G', 'ஜி': 'G', 'ஐ': 'I', 'ஜே': 'J', 'கே': 'K',
        'ஓ': 'O', 'யூ': 'U', 'யு': 'U', 'வீ': 'V', 'வி': 'V',
    }
    # Tamil-script letter names that denote two Latin letters.
    AMBIGUOUS_LETTERS: Dict[str, List[str]] = {'பி': ['B', 'P'], 'பீ': ['B', 'P'], 'டி': ['D', 'T'], 'டீ': ['D', 'T']}

    # Qualifiers are matched in every glyph order the extractor can emit: correct Unicode,
    # legacy pre-vowel order, and the order produced when legacy normalisation is applied to
    # already-correct text (e.g. 'பழைய' -> 'பழயை').
    NEW_QUAL = r'(?:புதிய|New|தற்(?:போ|போ)த(?:ைய|யை)|Present|Current)'
    OLD_QUAL = r'(?:ப(?:ழைய|ழயை|ைழய)|Old|முந்(?:தைய|தயை|ைதய)|முன்னாள்|Former|Previous|Earlier|பூர்வ)'
    NUM_KW = r'(?:எண்கள்|எண்|நம்பர்|நெ|Nos|No|Number)'

    WARD_KW = r'(?:வார்டு|வார்ட்|(?<![A-Za-z])Ward(?![A-Za-z]))'
    BLOCK_KW = r'(?:ப்ளாக்|பிளாக்கு|பிளாக்|(?<![A-Za-z])Block(?![A-Za-z]))'
    TS_KW = (
        r'(?:'
        r'(?<![\u0B80-\u0BFF])டி\s*\.?\s*எஸ்\s*\.?\s*(?:எல்\s*\.?\s*ஆர்\s*\.?)?'
        r'|(?<![A-Za-z])T\s*\.?\s*S(?:\s*\.?\s*L\s*\.?\s*R)?(?![A-Za-z])\s*\.?'
        r'|(?<![A-Za-z])Town\s*Survey'
        r'|டவுன்\s*சர்வே'
        r'|நகர\s*(?:நில\s*)?அளவை'
        r'|நகரளவை'
        r'|நகர\s*சர்வே'
        r')'
    )
    # After the TS keyword: optional "survey" word + mandatory number keyword OR a digit straight away.
    TS_RE = re.compile(
        TS_KW + r'\s*(?:சர்வே|Survey)?\s*(?:' + NUM_KW + r'(?![A-Za-z\u0B80-\u0BFF]))?\s*[\.\:\-]*\s*'
        r'(?P<val>[0-9]{1,5}(?:\s*/\s*[0-9A-Za-z\u0B80-\u0BFF]{1,6})?'
        r'(?:\s*(?:,|மற்றும்|and|&)\s*[0-9]{1,5}(?:\s*/\s*[0-9A-Za-z\u0B80-\u0BFF]{1,6})?)*)',
        re.I
    )
    WARD_RE = re.compile(
        WARD_KW + r'\s*(?:' + NUM_KW + r'(?![A-Za-z\u0B80-\u0BFF]))?\s*[\.\:\-]*\s*'
        r'(?P<val>[0-9]{1,3}[A-Za-z]?(?![0-9])|[A-Za-z]{1,3}(?![A-Za-z])|[\u0B80-\u0BFF](?:[\u0B80-\u0BFF\.\-]|\s(?=[\u0B80-\u0BFF]{1,3}\b)){0,14})',
        re.I
    )
    BLOCK_RE = re.compile(
        BLOCK_KW + r'\s*(?:' + NUM_KW + r'(?![A-Za-z\u0B80-\u0BFF]))?\s*[\.\:\-]*\s*'
        r'(?P<val>[0-9]{1,4}[A-Za-z]?(?![0-9])|[A-Za-z]{1,2}(?![A-Za-z])|[\u0B80-\u0BFF][\u0B80-\u0BFF\.\-]{0,8})',
        re.I
    )
    QUAL_BEFORE_RE = re.compile(r'(?P<q>' + NEW_QUAL + r'|' + OLD_QUAL + r')\s*$', re.I)
    STOP_WORDS = {'எண்', 'நம்பர்', 'நெ', 'மற்றும்', 'ஆகும்', 'உள்ள', 'கொண்ட', 'பகுதி', 'நகர'}

    # ------------------------------------------------------------------
    @classmethod
    def transliterate_tamil_code(cls, raw: str) -> Tuple[str, List[str]]:
        """
        'ஏஜே' / 'ஏ.ஜே' / 'ஏ-ஜே' -> ('AJ', ['AJ']); 'பிடி' -> ('BD', ['BD','BT','PD','PT']).
        Returns ('', []) if the text is not purely a sequence of Tamil letter names.
        """
        s = re.sub(r'[\s\.\-_]+', '', _normalize_tamil(raw or ""))
        if not s:
            return "", []
        names = sorted(cls.TAMIL_LETTER_NAMES.keys(), key=len, reverse=True)
        pos, letters = 0, []
        while pos < len(s):
            for nm in names:
                if s.startswith(nm, pos):
                    letters.append(nm)
                    pos += len(nm)
                    break
            else:
                return "", []
        if not letters or len(letters) > 4:
            return "", []
        primary = "".join(cls.TAMIL_LETTER_NAMES[l] for l in letters)
        options = [cls.AMBIGUOUS_LETTERS.get(l, [cls.TAMIL_LETTER_NAMES[l]]) for l in letters]
        variants = ["".join(p) for p in itertools.product(*options)]
        variants.sort(key=lambda v: (v != primary, v))
        return primary, variants[:4]

    @classmethod
    def normalize_ward_code(cls, raw: str) -> Tuple[str, List[str]]:
        """Normalises a ward value to the portal's code. Returns (code, alternates)."""
        v = _normalize_tamil((raw or "").strip()).strip(" .,-:;()")
        if not v:
            return "", []
        if re.fullmatch(r'[0-9]{1,3}[A-Za-z]?', v):
            return v.upper(), [v.upper()]
        if re.fullmatch(r'[A-Za-z]{1,3}', v):
            return v.upper(), [v.upper()]
        if re.fullmatch(r'[A-Za-z][\.\-\s]?[A-Za-z]([\.\-\s]?[A-Za-z])?', v):
            c = re.sub(r'[^A-Za-z]', '', v).upper()
            return c, [c]
        first = re.split(r'[\s,]+', v)[0]
        if first in cls.STOP_WORDS:
            return "", []
        code, alts = cls.transliterate_tamil_code(v)
        if not code:
            code, alts = cls.transliterate_tamil_code(first)
        return code, alts

    @classmethod
    def normalize_block_code(cls, raw: str) -> str:
        v = _normalize_tamil((raw or "").strip()).strip(" .,-:;()")
        if not v or v in cls.STOP_WORDS:
            return ""
        if re.fullmatch(r'[0-9]{1,4}[A-Za-z]?', v) or re.fullmatch(r'[A-Za-z]{1,2}', v):
            return v.upper()
        code, _ = cls.transliterate_tamil_code(v)
        return code

    @classmethod
    def _tamil_subdivision_to_latin(cls, sub: str) -> str:
        """'2ஏ' -> '2A', 'பி' -> 'B' (TS subdivisions follow the same letter conventions)."""
        sub = _normalize_tamil(sub or "").strip()
        m = re.match(r'^([0-9]*)(.*)$', sub)
        digits, rest = m.group(1), m.group(2).strip()
        if rest and re.search(r'[\u0B80-\u0BFF]', rest):
            code, _ = cls.transliterate_tamil_code(rest)
            if code:
                rest = code
        return (digits + rest).upper()

    @classmethod
    def _qualifier(cls, text: str, start: int) -> str:
        """'NEW' / 'OLD' / '' for the qualifier immediately preceding a keyword (<= 14 chars)."""
        window = text[max(0, start - 14):start]
        m = cls.QUAL_BEFORE_RE.search(window)
        if not m:
            return ""
        return "OLD" if re.fullmatch(cls.OLD_QUAL, m.group('q'), re.I) else "NEW"

    @classmethod
    def _mentions(cls, text: str) -> List[Dict[str, Any]]:
        out = []
        for kind, rx in (("WARD", cls.WARD_RE), ("BLOCK", cls.BLOCK_RE), ("TS", cls.TS_RE)):
            for m in rx.finditer(text):
                out.append({"kind": kind, "start": m.start(), "end": m.end(), "raw": m.group('val').strip(),
                            "evidence": text[m.start():m.end()].strip(), "qual": cls._qualifier(text, m.start())})
        out.sort(key=lambda d: d["start"])
        # Unqualified mentions inherit the qualifier of the immediately preceding mention
        # within the same clause (<= 40 chars apart, no sentence break).
        prev = None
        for d in out:
            if not d["qual"] and prev is not None and prev["qual"]:
                gap_text = text[prev["end"]:d["start"]]
                same_clause = (d["start"] - prev["end"] <= 40) and not re.search(r'[\.;!?]\s', gap_text + " ")
                if same_clause:
                    d["qual"] = prev["qual"]
                    d["qual_inherited"] = True
            prev = d
        return out

    @classmethod
    def _parse_ts_values(cls, raw: str) -> List[Tuple[str, str]]:
        vals = []
        for part in re.split(r',|மற்றும்|\band\b|&', raw or "", flags=re.I):
            m = re.search(r'([0-9]{1,5})(?:\s*/\s*([0-9A-Za-z\u0B80-\u0BFF]{1,6}))?', part)
            if m:
                pair = (m.group(1), cls._tamil_subdivision_to_latin(m.group(2) or ""))
                if pair not in vals:
                    vals.append(pair)
        return vals

    # ------------------------------------------------------------------
    @classmethod
    def parse_text(cls, text: str) -> Dict[str, Any]:
        """Parses free text (schedule remarks) into current / historical TSLR coordinates."""
        norm = re.sub(r'\s+', ' ', _normalize_tamil(text or "")).strip()
        res = {"is_urban_tslr": False, "current": {"ward": "", "ward_alternates": [], "block": "", "ts_numbers": []},
               "historical": [], "evidence": []}
        if not norm:
            return res
        ments = cls._mentions(norm)
        groups: Dict[str, Dict[str, Any]] = {}
        for d in ments:
            g = groups.setdefault(d["qual"] or "", {"ward": "", "ward_alternates": [], "block": "", "ts_numbers": []})
            if d["kind"] == "WARD" and not g["ward"]:
                code, alts = cls.normalize_ward_code(d["raw"])
                if code:
                    g["ward"], g["ward_alternates"] = code, alts
                    res["evidence"].append(d["evidence"])
            elif d["kind"] == "BLOCK" and not g["block"]:
                b = cls.normalize_block_code(d["raw"])
                if b:
                    g["block"] = b
                    res["evidence"].append(d["evidence"])
            elif d["kind"] == "TS":
                for pair in cls._parse_ts_values(d["raw"]):
                    if pair not in g["ts_numbers"]:
                        g["ts_numbers"].append(pair)
                res["evidence"].append(d["evidence"])
        cur = {"ward": "", "ward_alternates": [], "block": "", "ts_numbers": []}
        for q in ("NEW", ""):  # current = explicit "new" first, then unqualified
            g = groups.get(q)
            if not g:
                continue
            if not cur["ward"] and g["ward"]:
                cur["ward"], cur["ward_alternates"] = g["ward"], g["ward_alternates"]
            if not cur["block"] and g["block"]:
                cur["block"] = g["block"]
            if not cur["ts_numbers"] and g["ts_numbers"]:
                cur["ts_numbers"] = list(g["ts_numbers"])
        res["current"] = cur
        if "OLD" in groups:
            res["historical"].append(groups["OLD"])
        any_ts = bool(cur["ts_numbers"]) or any(h["ts_numbers"] for h in res["historical"])
        any_wb = bool(cur["ward"] and cur["block"]) or any(h["ward"] and h["block"] for h in res["historical"])
        res["is_urban_tslr"] = any_ts or any_wb
        return res

    @classmethod
    def ward_from_village(cls, village: str) -> str:
        """'WARD -AJ (Piratiyur East)' -> 'AJ'; 'Ward 12' -> '12'."""
        m = re.search(r'(?:\bward\b|வார்டு)\s*(?:no\.?|எண்)?\s*[-_:]?\s*([A-Za-z0-9]{1,4})\b', village or "", re.I)
        return m.group(1).upper() if m else ""

    @classmethod
    def parse_schedule(cls, sched: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classifies one deed schedule (Engine A PDF schedule or portal schedule row) and returns:
          {is_urban_tslr, entries:[{ward, ward_alternates, block, survey_or_ts, subdiv, source,
           era, evidence}], ts_pairs:[(ts, sub)], ward_source}
        Precedence for ward: registration village label (portal's own Latin code) > schedule
        table Ward No. > remarks (new/unqualified). Remarks may add further variants.
        """
        sched = sched or {}
        remarks = str(sched.get("schedule_remarks_full", "") or "")
        village = str(sched.get("village", "") or "")
        parsed = cls.parse_text(remarks)
        cur = parsed["current"]

        table_ward_code, table_ward_alts = cls.normalize_ward_code(str(sched.get("ward_no", "") or ""))
        table_block = cls.normalize_block_code(str(sched.get("block_no", "") or ""))
        village_ward = cls.ward_from_village(village)

        wards: List[Tuple[str, List[str], str]] = []
        if village_ward:
            wards.append((village_ward, [village_ward], "REGISTRATION_VILLAGE_LABEL"))
        if table_ward_code:
            wards.append((table_ward_code, table_ward_alts, "SCHEDULE_TABLE_WARD_NO"))
        if cur["ward"]:
            wards.append((cur["ward"], cur["ward_alternates"], "SCHEDULE_REMARKS"))
        block = cur["block"] or table_block

        ts_pairs = list(cur["ts_numbers"])
        ts_source = "SCHEDULE_REMARKS_TS_KEYWORD" if ts_pairs else ""
        if not ts_pairs and wards:
            # Portal survey cell of an urban (ward) schedule led by a bare number, e.g. "19,71/2,94/1"
            sn = sched.get("survey_number", {})
            raw_cells = [sn.get("raw", "") if isinstance(sn, dict) else str(sn or ""),
                         str(sched.get("survey_subdivision_raw", "") or "")]
            for rc in raw_cells:
                m_lead = re.match(r'^\s*([0-9]{1,5})\s*,', rc or "")
                if m_lead:
                    ts_pairs = [(m_lead.group(1), "")]
                    ts_source = "URBAN_SURVEY_CELL_LEADING_BARE_NUMBER"
                    break

        entries: List[Dict[str, Any]] = []
        if wards and ts_pairs:
            seen = set()
            primary_ward = wards[0]
            ward_variants: List[Tuple[str, str]] = [(primary_ward[0], primary_ward[2])]
            for code, alts, src in wards[1:]:
                if code not in [w for w, _ in ward_variants]:
                    # Ambiguous Tamil readings are subsumed when an authoritative Latin label agrees.
                    if not any(w in alts for w, _ in ward_variants):
                        ward_variants.append((code, src))
            # Unconfirmed Tamil-only ward: also plan its ambiguous alternates.
            if primary_ward[2] == "SCHEDULE_REMARKS" or (primary_ward[2] == "SCHEDULE_TABLE_WARD_NO" and len(wards) == 1):
                for alt in primary_ward[1][1:]:
                    ward_variants.append((alt, primary_ward[2] + "_AMBIGUOUS_ALTERNATE"))
            for w_code, w_src in ward_variants:
                for ts_no, ts_sub in ts_pairs:
                    key = (w_code, block, ts_no, ts_sub)
                    if key in seen:
                        continue
                    seen.add(key)
                    entries.append({
                        "ward": w_code, "ward_alternates": primary_ward[1], "block": block,
                        "survey_or_ts": ts_no, "subdiv": ts_sub,
                        "era": "CURRENT_ALTERNATE" if w_src.endswith("_AMBIGUOUS_ALTERNATE") else "CURRENT",
                        "ward_source": w_src, "ts_source": ts_source,
                        "evidence": parsed["evidence"],
                    })
        for hist in parsed["historical"]:
            h_ward = hist["ward"] or (wards[0][0] if wards else "")
            for ts_no, ts_sub in hist["ts_numbers"]:
                entries.append({
                    "ward": h_ward, "ward_alternates": hist["ward_alternates"] or ([h_ward] if h_ward else []),
                    "block": hist["block"] or block, "survey_or_ts": ts_no, "subdiv": ts_sub,
                    "era": "HISTORICAL", "ward_source": "SCHEDULE_REMARKS_OLD" if hist["ward"] else (wards[0][2] if wards else ""),
                    "ts_source": "SCHEDULE_REMARKS_TS_KEYWORD_OLD", "evidence": parsed["evidence"],
                })
        hist_pairs = [p for h in parsed["historical"] for p in h["ts_numbers"]]
        return {
            "is_urban_tslr": bool(entries) or parsed["is_urban_tslr"],
            "entries": [e for e in entries if e["ward"] and e["survey_or_ts"]],
            "ts_pairs": ts_pairs + [p for p in hist_pairs if p not in ts_pairs],
            "explicit_ts_keyword": bool(cur["ts_numbers"]) or bool(hist_pairs),
            "ward_detected": bool(wards),
            "block": block,
        }
