#!/usr/bin/env python3
"""
ENGINE C - EC PROPERTY TRACER (deterministic, zero-LLM)
========================================================================================
Evidence layer used by title_scrutiny_engine.py. Every rule here is deterministic and
explainable; nothing is merged or rejected on similarity alone.

1. Deed nature taxonomy      classify_nature(): sale, gift, settlement, partition, exchange,
                             mortgage (incl. MODT / deposit of title deeds), mortgage discharge
                             (receipt / reconveyance), release of rights (NOT a discharge by
                             itself), rectification, cancellation, POA, lease, court
                             (attachment / lis pendens / injunction / decree), will, agreement,
                             construction.
2. Party identity            party_identity() / parties_match(): exact match after Unicode +
                             honorific + initial normalisation, documented aka "(எ)" / "@",
                             Tamil<->Latin phonetic key for cross-script names, institution
                             keys for banks. No substring matching; conflicting initials never
                             match.
3. Parcel fingerprint        fingerprint(): plot, survey list (+ parent/child subdivision
                             relation), door (old/new), flat, floor, block, ward, town survey,
                             land vs UDS vs built-up extent, property class, village, four
                             boundaries (as extracted, incl. layout_family / as_written).
4. Identity comparison       compare_identity(): evidence vector {matching, conflicting,
                             missing} and a disposition: SAME_PARCEL, PARENT_PARCEL,
                             SIBLING_OR_REMAINDER, NEIGHBOR, SAME_LAND_DIFFERENT_UNIT,
                             INSUFFICIENT_EVIDENCE, CONFLICTING_IDENTITY.
                             Missing data is INSUFFICIENT_EVIDENCE, never a negative match.
5. EC coverage               load_coverage(): Engine B audit status, blockers and window
                             outcomes. A search that did not run is never proof of no record.
"""

import os
import re
import json
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# ----------------------------------------------------------------------------------------
# 1. Deed nature taxonomy
# ----------------------------------------------------------------------------------------
# Order matters: the first matching rule wins ("Reconveyance of mortgaged property" is a
# discharge, not a mortgage; "Cancellation of sale" is a cancellation, not a sale).
NATURE_RULES: List[Tuple[str, str]] = [
    ("COURT_ORDER", r'attach|lis\s*pendens|injunction|decree|court|jappthi|ஜப்தி|நீதிமன்ற|தடை\s*உத்தரவு|சொத்து\s*முடக்க|prohibitory'),
    ("CANCELLATION", r'cancel|ரத்து'),
    ("RECTIFICATION", r'rectif|பிழைத்திருத்த|பிைழத்திருத்த'),
    ("MORTGAGE_DISCHARGE", r'reconvey|discharge|receipt|ரசீது|மீட்பு|redemption'),
    ("RELEASE", r'release|விடுதலை'),
    ("MORTGAGE", r'mortgage|deposit\s*of\s*title|\bmodt\b|hypothec|அடமான|அடைமான|ஈடு|ஒத்தி'),
    ("POWER_OF_ATTORNEY", r'power\s*of\s*attorney|\bpoa\b|அதிகார\s*(?:ஆவணம்|பத்திரம்)|பவர்'),
    ("LEASE", r'\blease|குத்தகை|வாடகை'),
    ("WILL", r'\bwill\b|உயில்|testament'),
    ("PARTITION", r'partition|பாகப்பிரிவினை|பாகப்பிரிவிைன'),
    ("SETTLEMENT", r'settlement|தான\s*செட்டில்|செட்டில்மெண்ட்|செட்டில்'),
    ("GIFT", r'\bgift|தானம்|தான\s*பத்திர'),
    ("EXCHANGE", r'exchange|பரிவர்த்தனை'),
    ("CONSTRUCTION", r'construction|கட்டுமான'),
    ("AGREEMENT", r'agreement|ஒப்பந்த'),
    ("SALE", r'sale|conveyance|கிரய|விற்பனை|sale\s*deed'),
]
CONVEYANCE_CATEGORIES = {"SALE", "GIFT", "SETTLEMENT", "PARTITION", "EXCHANGE", "WILL"}
ENCUMBRANCE_CATEGORIES = {"MORTGAGE", "LEASE", "COURT_ORDER"}

CATEGORY_DISPOSITION = {
    "SALE": ("SUBSEQUENT_CONVEYANCE_SALE", "HIGH_ALERT"),
    "GIFT": ("SUBSEQUENT_CONVEYANCE_GIFT", "HIGH_ALERT"),
    "SETTLEMENT": ("SUBSEQUENT_CONVEYANCE_SETTLEMENT", "HIGH_ALERT"),
    "PARTITION": ("PARTITION", "HIGH_ALERT"),
    "EXCHANGE": ("SUBSEQUENT_CONVEYANCE_EXCHANGE", "HIGH_ALERT"),
    "WILL": ("TESTAMENTARY_DISPOSITION", "HIGH_ALERT"),
    "MORTGAGE": ("ENCUMBRANCE_MORTGAGE", "HIGH_ALERT"),
    "MORTGAGE_DISCHARGE": ("MORTGAGE_DISCHARGE_RECEIPT", "INFO"),
    "RELEASE": ("RELEASE_OF_RIGHTS", "REVIEW"),
    "RECTIFICATION": ("RECTIFICATION", "REVIEW"),
    "CANCELLATION": ("CANCELLATION", "HIGH_ALERT"),
    "POWER_OF_ATTORNEY": ("POWER_OF_ATTORNEY", "REVIEW"),
    "LEASE": ("ENCUMBRANCE_LEASE", "HIGH_ALERT"),
    "COURT_ORDER": ("COURT_ATTACHMENT_LIS_PENDENS", "HIGH_ALERT"),
    "CONSTRUCTION": ("CONSTRUCTION_RECORD", "REVIEW"),
    "AGREEMENT": ("AGREEMENT", "REVIEW"),
    "OTHER": ("UNCLASSIFIED_TRANSACTION", "REVIEW"),
}


def classify_nature(nature: str, remarks: str = "") -> str:
    """Deed category from the nature column; remarks are used only when the nature is blank."""
    n = normalize_text(nature or "").lower()
    for cat, rx in NATURE_RULES:
        if re.search(rx, n, re.I):
            return cat
    if not n.strip() and remarks:
        r = normalize_text(remarks).lower()
        for cat, rx in NATURE_RULES:
            if re.search(rx, r, re.I):
                return cat
    return "OTHER"


# ----------------------------------------------------------------------------------------
# Text helpers
# ----------------------------------------------------------------------------------------
_PRE_VOWEL = "\u0BC6\u0BC7\u0BC8"


def normalize_text(text: str) -> str:
    """
    Unicode-normalises Tamil without corrupting text that is already in standard order:
    a word is treated as legacy glyph order only when a pre-vowel sign (ெ ே ை) appears where
    standard Unicode never puts one (word start, after a pulli or after another vowel sign).
    """
    if not text:
        return ""
    out = []
    for word in re.split(r'(\s+)', str(text)):
        if re.search(r'(?:^|[^\u0B95-\u0BB9])[' + _PRE_VOWEL + r'][\u0B95-\u0BB9]', word):
            word = re.sub(r'([' + _PRE_VOWEL + r'])([\u0B95-\u0BB9])', r'\2\1', word)
        out.append(word)
    return unicodedata.normalize("NFC", "".join(out))


_TA_VOWELS = {'அ': 'a', 'ஆ': 'a', 'இ': 'i', 'ஈ': 'i', 'உ': 'u', 'ஊ': 'u', 'எ': 'e', 'ஏ': 'e',
              'ஐ': 'ai', 'ஒ': 'o', 'ஓ': 'o', 'ஔ': 'au'}
_TA_CONS = {'க': 'k', 'ங': 'n', 'ச': 's', 'ஞ': 'n', 'ட': 't', 'ண': 'n', 'த': 't', 'ந': 'n',
            'ப': 'p', 'ம': 'm', 'ய': 'y', 'ர': 'r', 'ல': 'l', 'வ': 'v', 'ழ': 'l', 'ள': 'l',
            'ற': 'r', 'ன': 'n', 'ஜ': 's', 'ஷ': 's', 'ஸ': 's', 'ஹ': 'h'}
_TA_SIGNS = {'ா': 'a', 'ி': 'i', 'ீ': 'i', 'ு': 'u', 'ூ': 'u', 'ெ': 'e', 'ே': 'e', 'ை': 'ai',
             'ொ': 'o', 'ோ': 'o', 'ௌ': 'au', '்': ''}


def phonetic_key(text: str) -> str:
    """
    Script-independent phonetic skeleton: Tamil is transliterated, then voiced/unvoiced and
    long/short distinctions that Tamil script does not make are collapsed
    ("பாலமுருகன்" == "Balamurugan" == "palamurukan").
    """
    t = normalize_text(text)
    res = []
    i = 0
    while i < len(t):
        c = t[i]
        if c in _TA_VOWELS:
            res.append(_TA_VOWELS[c])
        elif c in _TA_CONS:
            nxt = t[i + 1] if i + 1 < len(t) else ""
            if nxt in _TA_SIGNS:
                res.append(_TA_CONS[c] + _TA_SIGNS[nxt])
                i += 1
            else:
                res.append(_TA_CONS[c] + 'a')
        elif c.isascii() and c.isalpha():
            res.append(c.lower())
        i += 1
    s = "".join(res)
    for a, b in (("th", "t"), ("dh", "t"), ("sh", "s"), ("ch", "s"), ("zh", "l"), ("ph", "p"),
                 ("ee", "i"), ("oo", "u"), ("aa", "a"), ("w", "v"), ("b", "p"), ("g", "k"),
                 ("d", "t"), ("j", "s"), ("z", "s"), ("c", "k"), ("q", "k"), ("x", "ks"), ("f", "p")):
        s = s.replace(a, b)
    s = re.sub(r'(.)\1+', r'\1', s)
    return s


# ----------------------------------------------------------------------------------------
# 2. Party identity
# ----------------------------------------------------------------------------------------
HONORIFICS = r'(?:Mr|Mrs|Ms|Miss|Dr|Adv|Thiru|Tmt|Selvi|Late|Sri|Shri|Smt|திரு|திருமதி|செல்வி|காலஞ்சென்ற|லேட்|ஸ்ரீ)'
ROLE_TAGS = r'\((?:PR|AG|POA|Agent|Principal|பிரின்ஸ்பால்|ஏஜெண்ட்|ஏஜென்ட்|முகவர்|கார்டியன்|guardian|minor|மைனர்)\)'
BANK_TOKENS = r'bank|வங்கி|பேங்க்|பாங்க்|co-?op|கூட்டுறவு|finance|பைனான்ஸ்|housing|limited|லிமிடெட்|ltd'
# General institution vocabulary only - never personal names.
INSTITUTION_KEYS = [
    ("BANK_OF_BARODA", r'baroda|பரோடா|பேராடா|பேரோடா'),
    ("STATE_BANK_OF_INDIA", r'state\s*bank|\bsbi\b|ஸ்டேட்\s*பேங்க்|பாரத\s*ஸ்டேட்'),
    ("INDIAN_OVERSEAS_BANK", r'indian\s*overseas|\biob\b|இந்தியன்\s*ஓவர்சீஸ்'),
    ("INDIAN_BANK", r'indian\s*bank|இந்தியன்\s*(?:வங்கி|பேங்க்)'),
    ("CANARA_BANK", r'canara|கனரா'),
    ("CITY_UNION_BANK", r'city\s*union|\bcub\b|சிட்டி\s*யூனியன்'),
    ("KARUR_VYSYA_BANK", r'karur\s*vysya|\bkvb\b|கரூர்\s*வைசியா|கரூர்\s*வைஸ்யா'),
    ("ORIENTAL_BANK", r'oriental|ஓரியண்டல்'),
    ("LIC_HOUSING", r'lic\s*housing|எல்ஐசி'),
    ("HDFC", r'\bhdfc\b|எச்டிஎப்சி'),
    ("ICICI", r'\bicici\b|ஐசிஐசிஐ'),
    ("AXIS", r'\baxis\b|ஆக்சிஸ்'),
    ("TMB", r'tamilnad\s*mercantile|\btmb\b|தமிழ்நாடு\s*மெர்க்கன்டைல்'),
    ("IDBI", r'\bidbi\b'),
    ("UNION_BANK", r'union\s*bank|யூனியன்\s*பேங்க்'),
    ("PUNJAB_NATIONAL", r'punjab\s*national|\bpnb\b'),
]


def party_identity(name: str) -> Dict[str, Any]:
    """Normalised identity of one party string (raw kept by the caller)."""
    raw = normalize_text(name or "")
    s = re.sub(r'^\s*[0-9]+\s*\.\s*', '', raw)
    roles = re.findall(ROLE_TAGS, s, re.I)
    s = re.sub(ROLE_TAGS, ' ', s, flags=re.I)
    s = re.sub(r'(?<=\S)\s*[0-9]{1,2}\s*$', '', s)                       # party reference "1"
    s = re.sub(r'(?:^|\s)' + HONORIFICS + r'\.?(?=\s|$)', ' ', s, flags=re.I)
    s = re.sub(r'^' + HONORIFICS + r'\.\s*', '', s.strip(), flags=re.I)
    # documented aka: "புஸ்பா(எ) புஸ்கலா", "X @ Y", "X alias Y"
    alts = [a for a in re.split(r'\(\s*(?:எ|என்கிற|alias|aka)\s*\)|\s@\s|\balias\b|\baka\b|என்கிற', s, flags=re.I) if a.strip()]
    low = s.lower()
    inst = None
    if re.search(BANK_TOKENS, low, re.I):
        for key, rx in INSTITUTION_KEYS:
            if re.search(rx, low, re.I):
                inst = key
                break
        if not inst:
            core_inst = re.sub(BANK_TOKENS + r'|branch|கிளை|க்காக|தற்போதைய|அலுவலர்|மேலாளர்|manager|of|the|ஆப்', ' ', low, flags=re.I)
            inst = "INST:" + phonetic_key(core_inst)[:24]
    names = []
    for a in (alts or [s]):
        a = a.strip(' ,.-')
        initials = []
        # leading / trailing initials: "K.R. Ramu", "Ramu K.", "ஆர்.எம். சரஸ்வதி", "சாரதாஆச்சி.M"
        while True:
            m = re.match(r'^([A-Za-z]{1,2}|[\u0B80-\u0BFF]{1,4})\s*\.\s*', a)
            if not m or len(a) <= m.end():
                break
            initials.append(phonetic_key(m.group(1))[:1])
            a = a[m.end():]
        m2 = re.search(r'[\s\.]([A-Za-z])\.?$', a)
        if m2 and len(a) > 3:
            initials.append(m2.group(1).lower())
            a = a[:m2.start()]
        core = re.sub(r'[\s\.\-,]+', '', a).lower()
        if core:
            names.append({"core": core, "key": phonetic_key(a), "initials": sorted(set(i for i in initials if i))})
    return {"display": re.sub(r'\s+', ' ', raw).strip(), "names": names, "institution": inst, "roles": roles}


def parties_match(a: str, b: str) -> Tuple[bool, str]:
    """
    Deterministic equivalence of two party strings. Returns (match, basis).
    Bases: EXACT, AKA, TRANSLITERATION, INSTITUTION. Never substring; conflicting initials
    never match; a phonetic match needs at least 5 skeleton characters.
    """
    ia, ib = party_identity(a), party_identity(b)
    if ia["institution"] or ib["institution"]:
        if ia["institution"] and ia["institution"] == ib["institution"]:
            return True, "INSTITUTION"
        return False, "INSTITUTION_DIFFERS" if (ia["institution"] and ib["institution"]) else "PERSON_VS_INSTITUTION"
    for na in ia["names"]:
        for nb in ib["names"]:
            if na["initials"] and nb["initials"] and not set(na["initials"]) & set(nb["initials"]):
                continue
            basis = "AKA" if (len(ia["names"]) > 1 or len(ib["names"]) > 1) else None
            if na["core"] == nb["core"]:
                return True, basis or "EXACT"
            if len(na["key"]) >= 5 and na["key"] == nb["key"]:
                return True, basis or "TRANSLITERATION"
    return False, "NO_MATCH"


def party_names(tx: Dict[str, Any], role: str) -> List[str]:
    return [p.get("raw") or p.get("name") or "" for p in (tx.get("parties", {}) or {}).get(role, []) or [] if (p.get("raw") or p.get("name"))]


def account_for_parties(predecessors: List[str], successors: List[str]) -> Dict[str, Any]:
    """Every predecessor claimant must appear among the successor executants."""
    matched, unmatched = [], []
    for p in predecessors:
        hit = next(((s, basis) for s in successors for ok, basis in [parties_match(p, s)] if ok), None)
        (matched if hit else unmatched).append({"party": p, "matched_with": hit[0] if hit else None, "basis": hit[1] if hit else None})
    return {"matched": matched, "unmatched": unmatched,
            "all_accounted": bool(predecessors) and not unmatched,
            "any_matched": bool(matched)}


# ----------------------------------------------------------------------------------------
# 3. Parcel fingerprint
# ----------------------------------------------------------------------------------------
def _norm_plot(v: Any) -> str:
    s = normalize_text(str(v or "")).strip()
    if not s or s in ("-", "0"):
        return ""
    m = re.search(r'(?:Plot\s*No\.?|மனை\s*எண்|பிளாட்\s*(?:எண்|நெ)?)[\s\.\:/\-]*([0-9]+[A-Za-z\u0B80-\u0BFF]?)', s, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r'\b([0-9]{1,4})\s*([A-Za-z]|[\u0B80-\u0BFF]{1,2})?\b', s)
    if m:
        return (m.group(1) + (m.group(2) or "")).upper()
    return ""


def parse_surveys(survey_obj: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if not survey_obj:
        return out
    for item in survey_obj.get("survey_list") or []:
        if item.get("survey"):
            out.append((str(item["survey"]), str(item.get("subdivision") or "").upper()))
    if not out:
        raw = str(survey_obj.get("raw") or "")
        for tok in re.split(r'\s*[,;&]\s*|\s+and\s+', raw):
            m = re.fullmatch(r'\s*([0-9]+)\s*(?:/\s*([0-9A-Za-z]+(?:/[0-9A-Za-z]+)*))?\s*', tok)
            if m:
                out.append((m.group(1), (m.group(2) or "").upper()))
        if not out and survey_obj.get("survey"):
            out.append((str(survey_obj["survey"]), str(survey_obj.get("subdivision") or "").split(",")[0].strip().upper()))
    return list(dict.fromkeys(out))


def survey_relation(a: List[Tuple[str, str]], b: List[Tuple[str, str]]) -> str:
    """
    Relation of survey set b relative to a: SAME, PARENT (b is a less-subdivided form of a,
    e.g. 173/2 vs 173/2H), CHILD, SIBLING (same parent, different child), RELATED_BASE (same
    base survey only), DIFFERENT, UNKNOWN (one side missing).
    """
    if not a or not b:
        return "UNKNOWN"
    best = "DIFFERENT"
    rank = {"SAME": 6, "PARENT": 5, "CHILD": 5, "SIBLING": 3, "RELATED_BASE": 2, "DIFFERENT": 0}
    for sa, da in a:
        for sb, db in b:
            if sa != sb:
                continue
            if da == db:
                rel = "SAME"
            elif not db or (da.startswith(db) and len(db) < len(da)):
                rel = "PARENT"
            elif not da or (db.startswith(da) and len(da) < len(db)):
                rel = "CHILD"
            elif da and db and re.match(r'[0-9]+', da) and re.match(r'[0-9]+', db) and \
                    re.match(r'[0-9]+', da).group(0) == re.match(r'[0-9]+', db).group(0):
                rel = "SIBLING"
            else:
                rel = "RELATED_BASE"
            if rank[rel] > rank[best]:
                best = rel
    return best


def _remarks_fields(text: str) -> Dict[str, str]:
    t = normalize_text(text or "")
    out = {}
    m = re.search(r'(?:டி\s*\.?\s*எஸ்|T\.?\s*S\.?|town\s*survey|நகர\s*அளவை)[^0-9]{0,25}?([0-9]+(?:/[0-9A-Za-z]+)?)', t, re.I)
    if m:
        out["town_survey"] = m.group(1)
    m = re.search(r'(?:வார்டு|ward)\s*(?:எண்|no\.?)?[\s\.:\-]*([A-Za-z\u0B80-\u0BFF]{1,4}|[0-9]{1,3})\b', t, re.I)
    if m:
        out["ward"] = phonetic_key(m.group(1)) or m.group(1)
    m = re.search(r'(?:பிளாக்|block)\s*(?:எண்|no\.?)?[\s\.:\-]*([0-9]{1,5})', t, re.I)
    if m:
        out["block"] = m.group(1).lstrip("0") or "0"
    return out


def property_class(sched: Dict[str, Any]) -> str:
    pt = normalize_text(str(sched.get("property_type") or "")).lower()
    if sched.get("flat_no") not in (None, "", "-", "0") or re.search(r'flat|apartment|அடுக்கு', pt):
        return "FLAT_APARTMENT"
    if re.search(r'agri|விவசாய|நஞ்சை|புஞ்சை', pt):
        return "AGRICULTURAL_LAND"
    if re.search(r'with\s*building|building|கட்டிட', pt) or (re.search(r'\bhouse\b|வீடு', pt) and not re.search(r'site|மனை', pt)):
        return "PLOT_WITH_BUILDING"
    if re.search(r'undivided|uds|பிரிபடாத', pt):
        return "UNDIVIDED_SHARE"
    if re.search(r'site|plot|மனை', pt):
        return "LAYOUT_PLOT"
    return "UNSPECIFIED"


_UNIT_SQFT = [(r'hectare|ஹெக்டேர்', 107639.0), (r'acre|ஏக்கர்|ஏக்', 43560.0), (r'cent|சென்ட்|செண்ட்', 435.6),
              (r'kuzhi|குழி', 144.0), (r'ground|கிரவுண்ட்', 2400.0), (r'sq\.?\s*m|square\s*met|சதுர\s*மீ|மீட்டர்', 10.7639),
              (r'sq\.?\s*f|square\s*f|சதுர\s*அடி|சதுரடி|sft', 1.0)]


def extent_sqft(ext: Any) -> float:
    """Extent in sqft (structured value first, else the raw text with its unit). Values
    below 50 sqft are implausible for a parcel (unit lost in extraction) -> treated as missing."""
    v = 0.0
    raw = ""
    if isinstance(ext, dict):
        try:
            v = float(ext.get("sqft") or 0)
        except (TypeError, ValueError):
            v = 0.0
        raw = str(ext.get("raw") or "")
    elif ext:
        raw = str(ext)
    if v <= 1.0 and raw:
        m = re.search(r'([0-9]+(?:\.[0-9]+)?)', raw)
        if m:
            for rx, f in _UNIT_SQFT:
                if re.search(rx, raw, re.I):
                    v = float(m.group(1)) * f
                    break
    return round(v, 2) if v >= 50.0 else 0.0


def fingerprint(tx: Dict[str, Any], sched_idx: int = 0) -> Dict[str, Any]:
    scheds = tx.get("schedules") or []
    s = scheds[sched_idx] if len(scheds) > sched_idx else {}
    remarks = " ".join([str(s.get("schedule_remarks_full") or ""), str(tx.get("document_remarks") or "")])
    rf = _remarks_fields(remarks)
    pclass = property_class(s)
    ext = extent_sqft(s.get("extent"))
    uds_text = re.search(r'undivided|\buds\b|பிரிபடாத|பிரிக்கப்படாத', normalize_text(remarks + " " + str(s.get("property_type") or "")).lower())
    ext_kind = "UDS" if (pclass in ("FLAT_APARTMENT", "UNDIVIDED_SHARE") or uds_text) else "LAND"
    plot = _norm_plot(s.get("plot_no")) or (_norm_plot(tx.get("entry_plot")) if tx.get("entry_plot") not in (None, "-") else "")
    doors = {d for d in [str(s.get(k) or "").strip() for k in ("door_no", "new_door_no", "old_door_no")] if d and d not in ("-", "0")}
    b = s.get("boundaries") or {}
    return {
        "plot": plot,
        "surveys": parse_surveys(s.get("survey_number") or {}),
        "survey_raw": (s.get("survey_number") or {}).get("raw", ""),
        "doors": sorted(doors),
        "flat": str(s.get("flat_no") or "").strip() if str(s.get("flat_no") or "").strip() not in ("-", "0") else "",
        "floor": str(s.get("floor_no") or "").strip(),
        "block": str(s.get("block_no") or "").strip() or rf.get("block", ""),
        "ward": str(s.get("ward_no") or "").strip() or rf.get("ward", ""),
        "town_survey": rf.get("town_survey", ""),
        "property_class": pclass,
        "extent_sqft": ext,
        "extent_kind": ext_kind,
        "village": normalize_text(str(s.get("village") or "")),
        "boundaries": {k: normalize_text(str(b.get(k) or "")) for k in ("north", "south", "east", "west")},
        "boundary_family": b.get("layout_family", ""),
        "boundary_raw": normalize_text(str(b.get("raw") or "")),
    }


_DATIVE = r'(?:க்கும்|க்கு|ற்கும்|ற்கு|ுக்கும்|ுக்கு|க்குச்|கும்|கு)$'


def _landmark_key(v: str) -> str:
    v = normalize_text(v or "").lower()
    v = re.sub(r'(?:அவர்களின்|அவர்களுக்கு|சொந்தமான|உள்ள|belonging\s*to|property\s*of|of|by|the|திரு\.?|திருமதி)', ' ', v)
    v = re.sub(_DATIVE, '', v.strip())
    v = re.sub(r'[\s\.\,\-\(\)\'"]+', '', v)
    v = v.replace("ft", "அடி").replace("feet", "அடி").replace("road", "ரோடு").replace("ரோட்டு", "ரோடு").replace("ரோட்", "ரோடு")
    return v


def boundary_similarity(a: Dict[str, str], b: Dict[str, str]) -> Dict[str, Any]:
    """Side-by-side comparison; a side missing on either deed is 'missing', never a mismatch."""
    res = {"matched_sides": [], "differing_sides": [], "missing_sides": []}
    for side in ("north", "south", "east", "west"):
        va, vb = a.get(side, ""), b.get(side, "")
        if not va or not vb:
            res["missing_sides"].append(side)
            continue
        ka, kb = _landmark_key(va), _landmark_key(vb)
        na, nb = set(re.findall(r'[0-9]+', ka)), set(re.findall(r'[0-9]+', kb))
        if ka == kb or (len(ka) >= 4 and (ka in kb or kb in ka) and (na == nb)):
            res["matched_sides"].append(side)
        else:
            res["differing_sides"].append(side)
    return res


# ----------------------------------------------------------------------------------------
# 4. Identity comparison
# ----------------------------------------------------------------------------------------
def compare_identity(target: Dict[str, Any], cand: Dict[str, Any], cites_chain: bool = False,
                     target_plot_override: str = "", party_link: bool = False) -> Dict[str, Any]:
    """Evidence vector and disposition of one EC record against the target parcel."""
    match, conflict, missing = [], [], []
    t_plot = target_plot_override or target["plot"]
    s_rel = survey_relation(target["surveys"], cand["surveys"])

    if cites_chain:
        match.append("PR / remarks cite a deed in the target's title chain")
    if party_link:
        match.append("a party is an owner / party in the target's title chain")

    # plot
    plot_eq = plot_diff = False
    if t_plot and cand["plot"]:
        if t_plot == cand["plot"]:
            plot_eq = True
            match.append(f"plot {cand['plot']} equal")
        else:
            plot_diff = True
            conflict.append(f"plot {cand['plot']} differs from target plot {t_plot}")
    else:
        missing.append("plot")

    # survey
    if s_rel == "UNKNOWN":
        missing.append("survey")
    elif s_rel == "SAME":
        match.append(f"survey {cand['survey_raw']} same")
    elif s_rel in ("PARENT", "CHILD", "SIBLING", "RELATED_BASE"):
        match.append(f"survey {cand['survey_raw']} related to target ({s_rel})")
    else:
        conflict.append(f"survey {cand['survey_raw']} unrelated to target survey")

    # flat / unit
    flat_diff = False
    if target["flat"] and cand["flat"]:
        if target["flat"].upper() == cand["flat"].upper():
            match.append(f"flat {cand['flat']} equal")
        else:
            flat_diff = True
            conflict.append(f"flat {cand['flat']} differs from target flat {target['flat']}")
    elif target["flat"] or cand["flat"] or "FLAT_APARTMENT" in (target["property_class"], cand["property_class"]):
        missing.append("flat number")

    # urban identifiers (support only; renumbering is common)
    for k, label in (("town_survey", "town survey"), ("ward", "ward"), ("block", "block")):
        if target[k] and cand[k]:
            (match if target[k] == cand[k] else conflict).append(
                f"{label} {cand[k]} {'equal' if target[k] == cand[k] else 'differs'}")
    door_eq = bool(set(target["doors"]) & set(cand["doors"]))
    if target["doors"] and cand["doors"]:
        if door_eq:
            match.append("door number equal")
        else:
            missing.append("door number differs (possible municipal renumbering - not a mismatch)")

    # extent (UDS never compared with land extent)
    ext_ratio = None
    if target["extent_sqft"] and cand["extent_sqft"]:
        if target["extent_kind"] != cand["extent_kind"]:
            missing.append(f"extent not comparable ({cand['extent_kind']} vs {target['extent_kind']})")
        else:
            ext_ratio = cand["extent_sqft"] / target["extent_sqft"]
            if 0.97 <= ext_ratio <= 1.03:
                match.append("extent equal")
            elif ext_ratio > 1.03:
                missing.append(f"extent larger than target ({cand['extent_sqft']:.0f} sqft) - parent / larger parcel possible")
            else:
                conflict.append(f"extent smaller than target ({cand['extent_sqft']:.0f} sqft)")
    else:
        missing.append("extent")

    # boundaries
    bsim = boundary_similarity(target["boundaries"], cand["boundaries"])
    if len(bsim["matched_sides"]) >= 1:
        match.append(f"boundaries agree on {len(bsim['matched_sides'])}/4 sides ({', '.join(bsim['matched_sides'])})")
    if len(bsim["missing_sides"]) == 4:
        missing.append("boundaries")
    adjacent = bool(t_plot) and bool(re.search(r'(?:பிளாட்|மனை|plot)\s*(?:எண்|நெ|no\.?)?[\s\.:]*' + re.escape(t_plot) + r'(?![0-9])', cand["boundary_raw"], re.I))
    if adjacent:
        match.append(f"boundary text names target plot {t_plot} as an adjoining property (neighbour evidence)")

    # disposition
    strong_boundary = len(bsim["matched_sides"]) >= 3
    survey_ok = s_rel in ("SAME", "PARENT", "CHILD", "UNKNOWN")
    if flat_diff and (plot_eq or s_rel in ("SAME", "CHILD", "PARENT")):
        disp = "SAME_LAND_DIFFERENT_UNIT"
    elif cites_chain and not plot_diff and not flat_diff:
        disp = "SAME_PARCEL"
    elif cites_chain and plot_diff:
        disp = "CONFLICTING_IDENTITY"
    elif plot_eq and survey_ok and not (ext_ratio is not None and ext_ratio < 0.97):
        corroborated = s_rel != "UNKNOWN" or party_link or door_eq or bool(bsim["matched_sides"]) or \
            (ext_ratio is not None and 0.97 <= ext_ratio <= 1.03)
        disp = "SAME_PARCEL" if corroborated else "INSUFFICIENT_EVIDENCE"
    elif plot_eq:
        disp = "CONFLICTING_IDENTITY"
    elif not t_plot or not cand["plot"]:
        if strong_boundary and survey_ok and (ext_ratio is None or 0.97 <= ext_ratio <= 1.03):
            disp = "SAME_PARCEL"
        elif s_rel == "PARENT" or (s_rel == "SAME" and ext_ratio is not None and ext_ratio > 1.5):
            disp = "PARENT_PARCEL" if (ext_ratio is None or ext_ratio > 1.03) else "INSUFFICIENT_EVIDENCE"
        elif s_rel == "SIBLING":
            disp = "SIBLING_OR_REMAINDER"
        elif adjacent:
            disp = "NEIGHBOR"
        elif s_rel == "DIFFERENT":
            disp = "UNRELATED_PARCEL"
        else:
            disp = "INSUFFICIENT_EVIDENCE"
    else:  # both plots present and different
        if s_rel in ("SAME", "PARENT", "CHILD", "SIBLING", "RELATED_BASE", "UNKNOWN") or adjacent:
            disp = "NEIGHBOR"
        else:
            disp = "UNRELATED_PARCEL"
    if disp == "SIBLING_OR_REMAINDER" and plot_diff:
        disp = "NEIGHBOR"
    return {"disposition": disp, "survey_relation": s_rel,
            "evidence": {"matching": match, "conflicting": conflict, "missing": missing},
            "boundary_comparison": bsim}


# ----------------------------------------------------------------------------------------
# 5. Engine B coverage
# ----------------------------------------------------------------------------------------
def load_coverage(run_dir: str, ledger: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reads Engine B's audit verdict from the ledger and from
    ec_engine_full_trace/01_ec_search_matrix_plan.json (window outcomes). Coverage is
    COMPLETE only when Engine B says VERIFIED_EXHAUSTIVE, no blocker is open and no search
    window failed. Missing audit data is UNKNOWN, never complete.
    """
    sources = []
    status = ledger.get("audit_status")
    blockers = list(ledger.get("audit_blockers") or [])
    if status:
        sources.append("master_ledger.audit_status")
    windows: List[Dict[str, Any]] = []
    plan_path = None
    for cand in (os.path.join(run_dir, "ec_engine_full_trace", "01_ec_search_matrix_plan.json"),
                 os.path.join(run_dir, "01_ec_search_matrix_plan.json")):
        if os.path.exists(cand):
            plan_path = cand
            break
    if plan_path:
        try:
            with open(plan_path, "r", encoding="utf-8") as fp:
                plan = json.load(fp)
            sources.append(os.path.relpath(plan_path, run_dir))
            windows = plan.get("window_outcomes") or []
            if plan.get("audit_status") and (not status or plan["audit_status"] != "VERIFIED_EXHAUSTIVE"):
                status = plan["audit_status"] if status in (None, "", "VERIFIED_EXHAUSTIVE") else status
            seen = {json.dumps(b, sort_keys=True, ensure_ascii=False) for b in blockers}
            for b in plan.get("audit_blockers") or []:
                k = json.dumps(b, sort_keys=True, ensure_ascii=False)
                if k not in seen:
                    blockers.append(b)
                    seen.add(k)
        except Exception as e:  # unreadable audit file is itself a coverage gap
            blockers.append({"type": "COVERAGE_AUDIT_UNREADABLE", "reason": str(e)})
    failed = [w for w in windows if w.get("outcome") == "FAILED"]
    by_type: Dict[str, int] = {}
    for b in blockers:
        t = b.get("type") if isinstance(b, dict) else "UNSPECIFIED"
        by_type[t or "UNSPECIFIED"] = by_type.get(t or "UNSPECIFIED", 0) + 1
    by_reason: Dict[str, int] = {}
    failed_jobs: Dict[str, Dict[str, Any]] = {}
    seen_win: Set[Tuple[Any, Any, Any]] = set()

    def _d(v: str):
        for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(v, fmt)
            except (TypeError, ValueError):
                pass
        return None

    for b in blockers + failed:
        if not isinstance(b, dict):
            continue
        key = (b.get("job_id"), b.get("date_start"), b.get("date_end"))
        if b.get("job_id") and key in seen_win:
            continue
        seen_win.add(key)
        r_key = str(b.get("reason") or b.get("type") or "").split(":")[0]
        by_reason[r_key] = by_reason.get(r_key, 0) + 1
        jid = b.get("job_id")
        if jid and (b.get("type") in (None, "EC_WINDOW_NOT_CERTIFIED", "EC_JOB_NOT_EXECUTED") or b.get("outcome") == "FAILED"):
            j = failed_jobs.setdefault(jid, {"job_id": jid, "windows": 0, "earliest": None, "latest": None, "reasons": set()})
            j["windows"] += 1
            j["reasons"].add(r_key)
            for k in ("date_start", "date_end"):
                dv = _d(b.get(k) or "")
                if dv:
                    if j["earliest"] is None or dv < _d(j["earliest"]):
                        j["earliest"] = b[k]
                    if j["latest"] is None or dv > _d(j["latest"]):
                        j["latest"] = b[k]
    if not status and not windows:
        verdict = "UNKNOWN"
    elif status == "VERIFIED_EXHAUSTIVE" and not blockers and not failed:
        verdict = "COMPLETE"
    else:
        verdict = "INCOMPLETE"
    return {
        "coverage_verdict": verdict,
        "engine_b_audit_status": status or "NOT_REPORTED",
        "audit_sources": sources,
        "blocker_count": len(blockers),
        "blockers_by_type": by_type,
        "failure_reasons": by_reason,
        "failed_window_count": len(failed),
        "window_count": len(windows),
        "failed_jobs": [dict(v, reasons=sorted(v["reasons"])) for v in failed_jobs.values()],
        "note": ("A portal search that failed or was not executed is NOT evidence that no "
                 "transaction exists for that period / survey.") if verdict != "COMPLETE" else "",
    }
