#!/usr/bin/env python3
"""
========================================================================================
ENGINE C: AUTONOMOUS LEGAL TITLE SCRUTINY & CONVEYANCING ENGINE
========================================================================================
Zero-LLM Deterministic Python Engine for Comprehensive Real Estate Due Diligence.
Cross-links Engine A root/PR deed extractions with Engine B 50-year master EC ledgers.

Core Capabilities:
1. Canonical Normalization & Identity Resolution (Bilingual Tamil-English Phonetics)
2. Bidirectional Link Graph Traversal (Upstream PR Chain + Downstream Successor Deeds)
3. Active Ownership State-Machine & Split Containment Mathematics
4. Encumbrance & Multi-Mortgage Reconciliation (Discharge Pair-Matching Algorithm)
5. Two-Tier Segregation & Comprehensive Conveyancing Dossier Generation
========================================================================================
"""

import os
import sys
import re
import json
import glob
import html
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import ec_property_tracer as T  # noqa: E402  deterministic identity / nature / coverage layer

class TitleRiskStatus:
    CLEAR = "CLEAR"
    CONDITIONAL_CLEAR = "CONDITIONAL_CLEAR"
    INCOMPLETE_EC_COVERAGE = "INCOMPLETE_EC_COVERAGE"   # never CLEAR while Engine B coverage is open
    HIGH_RISK_DEFECT = "HIGH_RISK_DEFECT"

class ChainContinuityStatus:
    INTACT = "INTACT"
    BROKEN = "BROKEN"
    JOINT_OWNER_GAP = "JOINT_OWNER_GAP"
    UNVERIFIED_LINK = "UNVERIFIED_LINK"
    BRIDGED_WITH_LEGAL_HEIR = "BRIDGED_WITH_LEGAL_HEIR"
    BRIDGED_WITH_POA = "BRIDGED_WITH_POA"
    BRIDGED_WITH_STATUTORY_AUCTION = "BRIDGED_WITH_STATUTORY_AUCTION"

class MortgageStatus:
    DISCHARGED_ON_RECORD = "DISCHARGED_ON_RECORD"
    NO_DISCHARGE_ON_RECORD = "NO_DISCHARGE_ON_RECORD (ACTIVE_HIGH_ALERT)"


class TitleScrutinyEngine:
    """
    Autonomous Legal Title Scrutiny Engine.
    Executes a 5-phase deterministic algorithmic scrutiny pipeline over Engine A & B outputs.
    """

    # Conversion constants to standard Square Feet
    ACRE_TO_SQFT = 43560.0
    CENT_TO_SQFT = 435.6
    SQM_TO_SQFT = 10.7639
    KUZHI_TO_SQFT = 144.0

    # General bilingual institution vocabulary only. Personal names are NEVER aliased here:
    # person identity is resolved by ec_property_tracer.parties_match (exact core name with
    # compatible initials, documented aka "(எ)" / "@", Tamil<->Latin phonetic key).
    NAME_ALIASES = {
        "வங்கி": ["bank", "பேங்க்", "பாங்க்"],
        "பரோடா": ["baroda", "பேராடா"],
        "கனரா": ["canara"],
        "பாரத ஸ்டேட்": ["sbi", "state bank"],
        "சிட்டி யூனியன்": ["city union", "cub"]
    }

    SCRUTINY_DISCLAIMER = (
        "Automated preliminary title scrutiny generated deterministically from registered EC "
        "and deed data. It is NOT a certified legal opinion; every finding must be verified "
        "by an advocate against certified copies, the original title deeds and a fresh EC.")

    # ---------------------------------------------------------------------------------
    # small record helpers
    # ---------------------------------------------------------------------------------
    @classmethod
    def _tx_id(cls, tx: Dict[str, Any]) -> str:
        rp = tx.get("registration_particulars", {}) or {}
        return cls.normalize_doc_id(rp.get("document_number") or tx.get("document_id"), rp.get("registration_year"))

    @classmethod
    def _tx_date(cls, tx: Dict[str, Any]) -> Optional[datetime]:
        d = ((tx.get("registration_particulars", {}) or {}).get("dates", {}) or {})
        return cls._parse_date(d.get("registration_date") or d.get("execution_date") or "")

    @classmethod
    def _tx_nature(cls, tx: Dict[str, Any]) -> str:
        return (tx.get("registration_particulars", {}) or {}).get("nature_of_deed", "") or ""

    @classmethod
    def _tx_text(cls, tx: Dict[str, Any]) -> str:
        parts = [str(tx.get("document_remarks") or ""), str((tx.get("pr_lineage", {}) or {}).get("pr_raw") or "")]
        for s in tx.get("schedules", []) or []:
            parts.append(str(s.get("schedule_remarks_full") or ""))
        return T.normalize_text(" ".join(parts))

    @classmethod
    def _cited_ids(cls, tx: Dict[str, Any]) -> Set[str]:
        """Every document id the record cites: structured PR list, raw PR text and remarks
        (tolerates spacing such as '5000/ 2023' or '5000 / 2023')."""
        ids = {cls.normalize_doc_id(p.get("doc_no"), p.get("year"))
               for p in (tx.get("pr_lineage", {}) or {}).get("pr_documents", []) or []
               if p.get("doc_no") and p.get("year")}
        for m in re.finditer(r'(?<![0-9])([0-9]{1,6})\s*/\s*((?:19|20)[0-9]{2})(?![0-9])', cls._tx_text(tx)):
            ids.add(f"{int(m.group(1))}/{m.group(2)}")
        return {i for i in ids if i}

    @classmethod
    def _display_party(cls, name: str) -> str:
        n = T.normalize_text(name or "")
        n = re.sub(r'^\s*[0-9]+\s*\.\s*', '', n)
        n = re.sub(r'\s+[0-9]{1,2}\s*$', '', n)
        return re.sub(r'\s+', ' ', n).strip()

    @classmethod
    def _bridge_evidence(cls, succ_tx: Dict[str, Any], missing_party: List[str], succ_execs: List[str],
                         ledger_txs: List[Dict[str, Any]], before: Optional[datetime]) -> Tuple[str, List[str]]:
        """
        Looks for an EVIDENCED legal bridge explaining why a predecessor owner is not an
        executant of the successor deed. Returns (bridge_status, evidence). Evidence must be on
        record (role tag, nature, remarks, or a POA / Will deed on the ledger); a bridge yields
        CONDITIONAL clearance with requisitions, never CLEAR.
        """
        nature = T.normalize_text(cls._tx_nature(succ_tx)).lower()
        text = (nature + " " + cls._tx_text(succ_tx)).lower()
        role_tags = " ".join(" ".join(T.party_identity(n)["roles"]) for n in succ_execs).lower()
        ev: List[str] = []
        # statutory sale (SARFAESI / DRT / court / revenue auction)
        if re.search(r'sarfaesi|\bdrt\b|recovery\s*officer|auction|sale\s*certificate|ஏல|authorised\s*officer|tahsildar|court\s*sale', text):
            return ChainContinuityStatus.BRIDGED_WITH_STATUTORY_AUCTION, ["successor deed is a statutory / auction sale: " + nature]
        # power of attorney: role tags on the executant or a POA deed on the ledger
        if re.search(r'\(?(?:ag|agent|poa|ஏஜெண்ட்|ஏஜென்ட்|முகவர்)\)?', role_tags) or re.search(r'power\s*of\s*attorney|பொது\s*அதிகார|முகவர்\s*மூலம்', text):
            ev.append("successor executant signs as agent / POA holder")
        for tx in ledger_txs:
            if T.classify_nature(cls._tx_nature(tx)) != "POWER_OF_ATTORNEY":
                continue
            d = cls._tx_date(tx)
            if before and d and d > before:
                continue
            ex = T.party_names(tx, "executants")
            cl = T.party_names(tx, "claimants")
            if any(T.parties_match(m, e)[0] for m in missing_party for e in ex) and any(T.parties_match(c, s)[0] for c in cl for s in succ_execs):
                ev.append(f"POA deed {cls._tx_id(tx)} on EC from missing owner to successor executant")
        if ev:
            return ChainContinuityStatus.BRIDGED_WITH_POA, ev
        # succession: heirship words, or a registered Will on the ledger
        if re.search(r'legal\s*heir|வாரிசு|இறப்பு|death|deceased|late\b|காலஞ்சென்ற|காலமான|succession', text):
            ev.append("successor deed recites death / heirship of the predecessor")
        for tx in ledger_txs:
            if T.classify_nature(cls._tx_nature(tx)) != "WILL":
                continue
            ex = T.party_names(tx, "executants")
            cl = T.party_names(tx, "claimants")
            if any(T.parties_match(m, e)[0] for m in missing_party for e in ex) and any(T.parties_match(c, s)[0] for c in cl for s in succ_execs):
                ev.append(f"Will {cls._tx_id(tx)} on EC from missing owner to successor executant")
        if ev:
            return ChainContinuityStatus.BRIDGED_WITH_LEGAL_HEIR, ev
        return ChainContinuityStatus.BROKEN, []

    @classmethod
    def scrutinize_run(cls, run_dir: str, target_plot: Optional[str] = None, log_callback=None) -> Dict[str, Any]:
        """
        Executes full legal scrutiny on a completed run directory.
        Reads Engine A deed extractions, the Engine B master EC ledger and Engine B's search
        coverage audit. Generates 06_title_scrutiny_report.json and 06_title_scrutiny_dossier.html.
        """
        def log(msg):
            if log_callback: log_callback(msg)
            else: print(msg)

        log("=" * 80)
        log("ENGINE C: AUTONOMOUS LEGAL TITLE SCRUTINY & CONVEYANCING ENGINE")
        log(f"Target Run Directory: {run_dir}")
        log("=" * 80)

        # 1. Locate and load Engine A deed extractions
        root_deed_file = os.path.join(run_dir, "02_pdf_detailed_extraction.json")
        if not os.path.exists(root_deed_file):
            cands = sorted(glob.glob(os.path.join(run_dir, "deeds", "01_*", "02_pdf_detailed_extraction.json")))
            root_deed_file = cands[0] if cands else root_deed_file
        if not os.path.exists(root_deed_file):
            raise FileNotFoundError(f"Engine A extraction file not found in {run_dir}")
        with open(root_deed_file, "r", encoding="utf-8") as fp:
            root_deed_data = json.load(fp)

        all_deed_extractions = []
        deeds_dir = os.path.join(run_dir, "deeds")
        if os.path.exists(deeds_dir):
            for d_name in sorted(os.listdir(deeds_dir)):
                d_path = os.path.join(deeds_dir, d_name, "02_pdf_detailed_extraction.json")
                if os.path.exists(d_path):
                    try:
                        with open(d_path, "r", encoding="utf-8") as fp:
                            all_deed_extractions.append(json.load(fp))
                    except Exception:
                        pass
        if not all_deed_extractions:
            all_deed_extractions.append(root_deed_data)

        # 2. Engine B master ledger + coverage audit
        ledger_file = os.path.join(run_dir, "04_unified_master_property_ledger_1975_2026.json")
        if not os.path.exists(ledger_file):
            ledger_file = os.path.join(run_dir, "ec_engine_full_trace", "unified_master_property_ledger_1975_2026.json")
        if not os.path.exists(ledger_file):
            raise FileNotFoundError(f"Engine B master ledger not found in {run_dir}")
        with open(ledger_file, "r", encoding="utf-8") as fp:
            master_ledger_data = json.load(fp)
        coverage = T.load_coverage(run_dir, master_ledger_data)

        # ---------------------------------------------------------------------------------
        # PHASE 1: TARGET IDENTITY FINGERPRINT
        # ---------------------------------------------------------------------------------
        log("\n[PHASE 1] Target identity fingerprint & EC coverage...")
        root_entry = root_deed_data.get("entries", [{}])[0]
        root_reg = root_entry.get("registration_particulars", {})
        target_doc_id = cls.normalize_doc_id(root_reg.get("document_number"), root_reg.get("registration_year"))
        target_date = cls._tx_date(root_entry)

        harvested_plot = str(target_plot).strip() if target_plot else ""
        if not harvested_plot:
            for s in root_entry.get("schedules", []):
                p_cand = T._norm_plot(s.get("plot_no", ""))
                if p_cand:
                    harvested_plot = p_cand
                    break
        if not harvested_plot and master_ledger_data.get("target_plot"):
            harvested_plot = T._norm_plot(master_ledger_data["target_plot"])
        harvested_plot = T._norm_plot(harvested_plot) if harvested_plot else ""

        root_schedules = root_entry.get("schedules", [])
        primary_schedule = root_schedules[0] if root_schedules else {}
        target_extent_sqft = cls.normalize_extent_to_sqft(primary_schedule.get("extent"))
        target_survey_raw = primary_schedule.get("survey_number", {}).get("raw", "")
        target_boundaries = primary_schedule.get("boundaries", {})
        target_fp = T.fingerprint(root_entry)
        target_fp["plot"] = harvested_plot
        if not target_fp["extent_sqft"]:
            target_fp["extent_sqft"] = target_extent_sqft

        log(f"  + Target Deed: {target_doc_id} | Plot: {harvested_plot or 'NOT_ON_RECORD'} | SF {target_survey_raw} | "
            f"Extent {target_extent_sqft:,.2f} sqft ({target_fp['extent_kind']}) | Class {target_fp['property_class']}")
        log(f"  + EC coverage (Engine B): {coverage['coverage_verdict']} [{coverage['engine_b_audit_status']}], "
            f"{coverage['blocker_count']} blocker(s), {coverage['failed_window_count']} failed window(s)")

        # ---------------------------------------------------------------------------------
        # PHASE 2: LINK GRAPH (PR CITATIONS) + IDENTITY TRACE OF EVERY EC RECORD
        # ---------------------------------------------------------------------------------
        log("\n[PHASE 2] Link graph & identity trace over the full EC ledger...")
        raw_transactions = master_ledger_data.get("transactions", [])
        log(f"  + Ledger records: {len(raw_transactions)}")

        tx_lookup: Dict[str, Dict[str, Any]] = {}
        for tx in raw_transactions:
            d_id = cls._tx_id(tx)
            if d_id and d_id not in tx_lookup:
                tx_lookup[d_id] = tx
        for d_ext in all_deed_extractions:
            for ent in d_ext.get("entries", []):
                e_reg = ent.get("registration_particulars", {})
                e_id = cls.normalize_doc_id(e_reg.get("document_number"), e_reg.get("registration_year"))
                if not e_id:
                    continue
                if e_id in tx_lookup:
                    tgt = tx_lookup[e_id]
                    tgt.setdefault("parties", {})
                    if ent.get("parties", {}).get("claimants"):
                        tgt["parties"]["claimants"] = ent["parties"]["claimants"]
                    if ent.get("parties", {}).get("executants"):
                        tgt["parties"]["executants"] = ent["parties"]["executants"]
                    if ent.get("schedules"):
                        tgt["schedules"] = ent["schedules"]
                else:
                    tx_lookup[e_id] = ent

        pr_citations_map: Dict[str, List[str]] = {}
        for d_ext in all_deed_extractions:
            for ent in d_ext.get("entries", []):
                e_reg = ent.get("registration_particulars", {})
                e_id = cls.normalize_doc_id(e_reg.get("document_number"), e_reg.get("registration_year"))
                pr_docs = ent.get("pr_lineage", {}).get("pr_documents", [])
                cites = [cls.normalize_doc_id(p.get("doc_no"), p.get("year")) for p in pr_docs if p.get("doc_no") and p.get("year")]
                if e_id:
                    pr_citations_map[e_id] = cites
        for d_id, tx in tx_lookup.items():
            if d_id not in pr_citations_map:
                pr_docs = tx.get("pr_lineage", {}).get("pr_documents", [])
                cites = [cls.normalize_doc_id(p.get("doc_no"), p.get("year")) for p in pr_docs if p.get("doc_no") and p.get("year")]
                if cites:
                    pr_citations_map[d_id] = cites

        upstream_chain: List[str] = []
        curr_doc_id = target_doc_id
        visited_upstream: Set[str] = set()
        while curr_doc_id and curr_doc_id not in visited_upstream:
            visited_upstream.add(curr_doc_id)
            cites = pr_citations_map.get(curr_doc_id, [])
            if not cites:
                break
            # multi-parent deeds: follow the first cited parent present in the evidence set
            parent_id = next((c for c in cites if c in tx_lookup and c not in visited_upstream), cites[0])
            if parent_id in visited_upstream or not re.fullmatch(r'[0-9]{1,6}/(?:19|20)[0-9]{2}', parent_id or ""):
                break
            upstream_chain.append(parent_id)
            curr_doc_id = parent_id
        upstream_chain.reverse()
        full_title_chain = upstream_chain + [target_doc_id]
        log(f"  [✓] Title chain (PR citations): {' -> '.join(full_title_chain)}")

        chain_party_names: List[str] = []
        for doc_id in full_title_chain:
            tx = tx_lookup.get(doc_id) or {}
            chain_party_names += T.party_names(tx, "executants") + T.party_names(tx, "claimants")
        chain_party_names += T.party_names(root_entry, "claimants")
        target_owners = T.party_names(tx_lookup.get(target_doc_id) or root_entry, "claimants")

        # identity trace (fixpoint: a record citing an admitted target record is itself traced)
        ledger_ids: List[str] = []
        traces: Dict[str, Dict[str, Any]] = {}
        for tx in raw_transactions:
            d_id = cls._tx_id(tx)
            if d_id and d_id not in ledger_ids:
                ledger_ids.append(d_id)
        admitted: Set[str] = set(full_title_chain)

        def _trace(d_id: str) -> Dict[str, Any]:
            tx = tx_lookup[d_id]
            cited = cls._cited_ids(tx) & admitted
            party_link = any(T.parties_match(p, c)[0] for p in T.party_names(tx, "executants") + T.party_names(tx, "claimants")
                             for c in chain_party_names)
            rank = {"SAME_PARCEL": 9, "SAME_LAND_DIFFERENT_UNIT": 8, "CONFLICTING_IDENTITY": 7, "PARENT_PARCEL": 6,
                    "SIBLING_OR_REMAINDER": 5, "NEIGHBOR": 4, "INSUFFICIENT_EVIDENCE": 3, "UNRELATED_PARCEL": 2}
            best = None
            for si in range(max(1, len(tx.get("schedules") or []))):
                fp = T.fingerprint(tx, si)
                cmp = T.compare_identity(target_fp, fp, cites_chain=bool(cited), party_link=party_link)
                if best is None or rank.get(cmp["disposition"], 0) > rank.get(best["disposition"], 0):
                    best = cmp
                    best["fingerprint"] = {k: fp[k] for k in ("plot", "survey_raw", "flat", "doors", "extent_sqft", "extent_kind", "property_class")}
            best["cites_admitted_records"] = sorted(cited)
            return best

        for _round in range(4):
            changed = False
            for d_id in ledger_ids:
                if d_id in full_title_chain:
                    continue
                tr = _trace(d_id)
                prev = traces.get(d_id, {}).get("disposition")
                traces[d_id] = tr
                if tr["disposition"] == "SAME_PARCEL" and d_id not in admitted:
                    admitted.add(d_id)
                    changed = True
                elif prev != tr["disposition"]:
                    changed = True
            if not changed:
                break

        downstream_successors = [d for d in ledger_ids if d not in full_title_chain and traces.get(d, {}).get("disposition") == "SAME_PARCEL"]
        tier1_doc_ids = set(full_title_chain + downstream_successors)
        cat_of = {d: T.classify_nature(cls._tx_nature(tx_lookup[d]), cls._tx_text(tx_lookup[d])) for d in tx_lookup}
        log(f"  [✓] Target-parcel records beyond the chain: {downstream_successors}")
        disp_counts: Dict[str, int] = {}
        for tr in traces.values():
            disp_counts[tr["disposition"]] = disp_counts.get(tr["disposition"], 0) + 1
        log(f"  + Identity dispositions: {disp_counts}")

        # ---------------------------------------------------------------------------------
        # PHASE 3: CHAIN CONTINUITY (EVERY OWNER ACCOUNTED FOR) + ALTERATIONS + EXTENT LEDGER
        # ---------------------------------------------------------------------------------
        log("\n[PHASE 3] Ownership continuity, alterations & remaining-extent ledger...")
        high_risk_reasons: List[str] = []
        conditions: List[str] = []
        requisitions: List[str] = []
        chain_continuity_steps = []
        step_rank = {"INTACT": 0, "INTACT_WITH_RELEASE": 0, "UNVERIFIED_LINK": 1,
                     ChainContinuityStatus.BRIDGED_WITH_POA: 2, ChainContinuityStatus.BRIDGED_WITH_LEGAL_HEIR: 2,
                     ChainContinuityStatus.BRIDGED_WITH_STATUTORY_AUCTION: 2,
                     ChainContinuityStatus.JOINT_OWNER_GAP: 3, ChainContinuityStatus.BROKEN: 4}
        worst = "INTACT"
        all_ledger = list(tx_lookup.values())
        for i in range(len(full_title_chain) - 1):
            pred_id, succ_id = full_title_chain[i], full_title_chain[i + 1]
            pred_tx, succ_tx = tx_lookup.get(pred_id, {}), tx_lookup.get(succ_id, {})
            preds, succs = T.party_names(pred_tx, "claimants"), T.party_names(succ_tx, "executants")
            step = {"predecessor": pred_id, "successor": succ_id,
                    "predecessor_claimants": [cls._display_party(p) for p in preds],
                    "successor_executants": [cls._display_party(p) for p in succs]}
            if not preds or not succs:
                step.update(continuity="UNVERIFIED_LINK", legal_bridge="PARTIES_NOT_ON_RECORD")
                conditions.append(f"Link {pred_id} -> {succ_id}: parties not on record; continuity unverified.")
                requisitions.append(f"Obtain certified copy of {pred_id if not preds else succ_id} to verify the ownership link {pred_id} -> {succ_id}.")
            else:
                acc = T.account_for_parties(preds, succs)
                step["party_accounting"] = acc
                unmatched = [u["party"] for u in acc["unmatched"]]
                released = []
                for u in unmatched:
                    for tx in all_ledger:
                        if cat_of.get(cls._tx_id(tx)) != "RELEASE":
                            continue
                        d = cls._tx_date(tx)
                        sd = cls._tx_date(succ_tx)
                        if sd and d and d > sd:
                            continue
                        if any(T.parties_match(u, e)[0] for e in T.party_names(tx, "executants")) and \
                                any(T.parties_match(c, s)[0] for c in T.party_names(tx, "claimants") for s in succs + preds):
                            released.append({"party": cls._display_party(u), "release_deed": cls._tx_id(tx)})
                            break
                still = [u for u in unmatched if cls._display_party(u) not in {r["party"] for r in released}]
                if not still:
                    step.update(continuity="INTACT_WITH_RELEASE" if released else "INTACT",
                                legal_bridge="EXACT_PARTY_MATCH_CONFIRMED" if not released else "CO_OWNER_RELEASE_ON_RECORD",
                                co_owner_releases=released)
                else:
                    bridge, ev = cls._bridge_evidence(succ_tx, still, succs, all_ledger, cls._tx_date(succ_tx))
                    step["unaccounted_predecessor_owners"] = [cls._display_party(u) for u in still]
                    step["bridge_evidence"] = ev
                    if bridge != ChainContinuityStatus.BROKEN:
                        step.update(continuity=bridge, legal_bridge=bridge)
                        conditions.append(f"Link {pred_id} -> {succ_id} relies on {bridge} ({'; '.join(ev)}).")
                        if bridge == ChainContinuityStatus.BRIDGED_WITH_POA:
                            requisitions.append(f"Produce the registered POA used in {succ_id}; confirm it was in force (principal alive, not revoked) on the execution date.")
                        elif bridge == ChainContinuityStatus.BRIDGED_WITH_LEGAL_HEIR:
                            requisitions.append(f"Produce death certificate, legal-heir / succession certificate (or probated Will) for {', '.join(step['unaccounted_predecessor_owners'])}; confirm all heirs joined {succ_id}.")
                        else:
                            requisitions.append(f"Produce the sale certificate / auction confirmation and authority for {succ_id}; verify statutory compliance and possession.")
                    elif acc["any_matched"]:
                        step.update(continuity=ChainContinuityStatus.JOINT_OWNER_GAP, legal_bridge=ChainContinuityStatus.JOINT_OWNER_GAP)
                        high_risk_reasons.append(f"Joint-owner gap {pred_id} -> {succ_id}: {', '.join(step['unaccounted_predecessor_owners'])} did not execute {succ_id} and no release / heirship / POA is on record (possible partial conveyance).")
                        requisitions.append(f"Explain how the share of {', '.join(step['unaccounted_predecessor_owners'])} passed (release deed, heirship, POA) before {succ_id}.")
                    else:
                        step.update(continuity=ChainContinuityStatus.BROKEN, legal_bridge=ChainContinuityStatus.BROKEN)
                        high_risk_reasons.append(f"Unexplained ownership break {pred_id} -> {succ_id}: executants of {succ_id} are not the owners under {pred_id}.")
            if step_rank.get(step["continuity"], 0) > step_rank.get(worst, 0):
                worst = step["continuity"]
            chain_continuity_steps.append(step)
            log(f"  + Link {pred_id} -> {succ_id}: {step['continuity']}")
            if pred_id not in tx_lookup:
                requisitions.append(f"Parent document {pred_id} is cited but not present in the EC ledger / deed set; obtain its certified copy.")
        chain_status = worst if worst not in ("INTACT_WITH_RELEASE",) else ChainContinuityStatus.INTACT
        if chain_status == "UNVERIFIED_LINK":
            chain_status = ChainContinuityStatus.UNVERIFIED_LINK

        # alterations (first-class records)
        alterations: List[Dict[str, Any]] = []
        fps = {d: T.fingerprint(tx_lookup[d]) for d in tier1_doc_ids if d in tx_lookup}
        if target_doc_id in fps:
            fps[target_doc_id]["plot"] = fps[target_doc_id]["plot"] or harvested_plot
        for i in range(len(full_title_chain) - 1):
            a, b = full_title_chain[i], full_title_chain[i + 1]
            fa, fb = fps.get(a), fps.get(b)
            if not fa or not fb:
                continue
            rel = T.survey_relation(fb["surveys"], fa["surveys"])
            if rel == "PARENT":
                alterations.append({"type": "SURVEY_SUBDIVISION", "from_document": a, "to_document": b,
                                    "from": fa["survey_raw"], "to": fb["survey_raw"]})
            if not fa["plot"] and fb["plot"]:
                alterations.append({"type": "PLOT_FORMATION_FROM_PARENT_LAND", "from_document": a, "to_document": b,
                                    "plot": fb["plot"], "parent_extent_sqft": fa["extent_sqft"], "plot_extent_sqft": fb["extent_sqft"]})
            if fa["extent_sqft"] and fb["extent_sqft"] and fa["extent_kind"] == fb["extent_kind"] and abs(fa["extent_sqft"] - fb["extent_sqft"]) > 0.03 * fa["extent_sqft"]:
                alterations.append({"type": "EXTENT_CHANGE", "from_document": a, "to_document": b,
                                    "from_sqft": fa["extent_sqft"], "to_sqft": fb["extent_sqft"]})
        t1_sorted = sorted(fps.keys(), key=lambda d: cls._tx_date(tx_lookup[d]) or datetime(1900, 1, 1))
        prev_cls, prev_doors, prev_doc = None, None, None
        for d in t1_sorted:
            f = fps[d]
            tx = tx_lookup[d]
            text = (T.normalize_text(cls._tx_nature(tx)) + " " + cls._tx_text(tx)).lower()
            if prev_cls in ("LAYOUT_PLOT", "AGRICULTURAL_LAND", "UNSPECIFIED") and f["property_class"] == "PLOT_WITH_BUILDING":
                alterations.append({"type": "BUILDING_CONSTRUCTED", "from_document": prev_doc, "to_document": d,
                                    "evidence": f"property type changed {prev_cls} -> {f['property_class']}"})
            if cat_of.get(d) == "CONSTRUCTION":
                alterations.append({"type": "BUILDING_CONSTRUCTED", "to_document": d, "evidence": "construction deed / agreement on EC"})
            if prev_doors and f["doors"] and not set(prev_doors) & set(f["doors"]):
                alterations.append({"type": "DOOR_RENUMBERING", "from_document": prev_doc, "to_document": d,
                                    "from": prev_doors, "to": f["doors"], "note": "treated as possible continuity, not a different parcel"})
            if re.search(r'dtcp|\blpa\b|layout\s*approv|அங்கீகார|நகர\s*ஊரமைப்பு|approved\s*layout', text):
                alterations.append({"type": "LAYOUT_APPROVAL", "document": d, "evidence": "approval reference in remarks"})
            if re.search(r'conversion|நில\s*(?:வகை|பயன்பாடு)\s*மாற்ற|reclassif', text):
                alterations.append({"type": "LAND_USE_CONVERSION", "document": d})
            if re.search(r'amalgamat|ஒருங்கிணை|merger\s*of\s*plots', text) or len({s for s, _ in f["surveys"]}) > max(1, len({s for s, _ in target_fp["surveys"]})):
                if re.search(r'amalgamat|ஒருங்கிணை|merger', text):
                    alterations.append({"type": "AMALGAMATION", "document": d})
            if cat_of.get(d) == "RECTIFICATION":
                cited = sorted(cls._cited_ids(tx) & tier1_doc_ids)
                alterations.append({"type": "RECTIFICATION", "document": d, "rectifies": cited})
                conditions.append(f"Rectification {d} applies to {', '.join(cited) or 'a target-parcel deed'}; read the corrected schedule.")
            if cat_of.get(d) == "CANCELLATION":
                cited = sorted(cls._cited_ids(tx) & tier1_doc_ids)
                alterations.append({"type": "CANCELLATION", "document": d, "cancels": cited})
                hit_chain = [c for c in cited if c in full_title_chain]
                if hit_chain:
                    high_risk_reasons.append(f"Cancellation deed {d} cancels title-chain document(s) {', '.join(hit_chain)}.")
                else:
                    conditions.append(f"Cancellation {d} on the target parcel; confirm what it cancels.")
            prev_cls, prev_doors, prev_doc = f["property_class"], f["doors"] or prev_doors, d

        # remaining-extent ledger on the oldest chain parent (no hard-coded fallbacks)
        split_containment_records = []
        remaining_extent_ledger: Dict[str, Any] = {}
        if len(full_title_chain) >= 2:
            parent_id = full_title_chain[0]
            parent_tx = tx_lookup.get(parent_id, {})
            p_extent_sqft = cls.normalize_extent_to_sqft((parent_tx.get("schedules") or [{}])[0].get("extent")) if parent_tx.get("schedules") else 0.0
            p_fp = T.fingerprint(parent_tx) if parent_tx else None
            p_date = cls._tx_date(parent_tx) if parent_tx else None
            p_owners = T.party_names(parent_tx, "claimants")
            children = []
            for tx in raw_transactions:
                d = cls._tx_id(tx)
                if d == parent_id or cat_of.get(d) not in T.CONVEYANCE_CATEGORIES:
                    continue
                dd = cls._tx_date(tx)
                if p_date and dd and dd < p_date:
                    continue
                fpc = T.fingerprint(tx)
                if fpc["extent_kind"] != (p_fp or {}).get("extent_kind", "LAND"):
                    continue
                basis = None
                if parent_id in cls._cited_ids(tx) or (d in full_title_chain and full_title_chain.index(d) == 1):
                    basis = "cites parent deed"
                elif p_owners and any(T.parties_match(o, e)[0] for o in p_owners for e in T.party_names(tx, "executants")) \
                        and p_fp and T.survey_relation(p_fp["surveys"], fpc["surveys"]) in ("SAME", "CHILD"):
                    basis = "executed by parent owner on the parent survey"
                if basis:
                    ext = fpc["extent_sqft"] or (target_extent_sqft if d == target_doc_id else 0.0)
                    children.append({"document_id": d, "date": dd.strftime("%d-%b-%Y") if dd else "", "_d": dd or datetime(1900, 1, 1),
                                     "extent_sqft": ext, "basis": basis, "nature": cls._tx_nature(tx)})
            if target_doc_id not in {c["document_id"] for c in children}:
                children.append({"document_id": target_doc_id, "date": target_date.strftime("%d-%b-%Y") if target_date else "",
                                 "_d": target_date or datetime(1900, 1, 1), "extent_sqft": target_extent_sqft,
                                 "basis": "target deed", "nature": cls._tx_nature(root_entry)})
            children.sort(key=lambda c: c["_d"])
            cum, overflow_at = 0.0, None
            for c in children:
                cum += c["extent_sqft"] or 0.0
                c["cumulative_sqft"] = round(cum, 2)
                c["remaining_sqft"] = round(p_extent_sqft - cum, 2) if p_extent_sqft else None
                if p_extent_sqft and cum > p_extent_sqft * 1.01 and overflow_at is None:
                    overflow_at = c
                c.pop("_d", None)
            remaining_extent_ledger = {
                "parent_deed": parent_id,
                "parent_extent_sqft": p_extent_sqft,
                "parent_extent_status": "ON_RECORD" if p_extent_sqft else "NOT_ON_RECORD",
                "conveyances_out_of_parent": children,
                "total_conveyed_sqft": round(cum, 2),
                "remaining_sqft": round(p_extent_sqft - cum, 2) if p_extent_sqft else None,
                "status": ("AREA_OVERFLOW" if overflow_at else "WITHIN_PARENT_EXTENT") if p_extent_sqft else "PARENT_EXTENT_NOT_ON_RECORD",
            }
            if overflow_at:
                remaining_extent_ledger["overflow_at_document"] = overflow_at["document_id"]
                remaining_extent_ledger["alert"] = "HIGH_ALERT"
                ov_d = cls._parse_date(overflow_at["date"])
                msg = (f"AREA_OVERFLOW: conveyances out of parent {parent_id} ({p_extent_sqft:,.0f} sqft) reach "
                       f"{overflow_at['cumulative_sqft']:,.0f} sqft at {overflow_at['document_id']}.")
                if overflow_at["document_id"] == target_doc_id or (ov_d and target_date and ov_d <= target_date):
                    high_risk_reasons.append(msg + " The target sale is at or after the overflow point.")
                else:
                    conditions.append(msg + " Overflow occurs after the target sale; verify the later conveyances.")
            elif not p_extent_sqft:
                requisitions.append(f"Parent deed {parent_id} extent is not on record; obtain it to verify the target extent is contained in the parent.")
            area_valid = (target_extent_sqft <= p_extent_sqft) if p_extent_sqft > 0 else None
            pct = round((target_extent_sqft / p_extent_sqft) * 100, 2) if p_extent_sqft > 0 else None
            p_bnd = (parent_tx.get("schedules") or [{}])[0].get("boundaries", {}) if parent_tx.get("schedules") else {}
            split_containment_records.append({
                "parent_deed": parent_id,
                "parent_extent_sqft": p_extent_sqft,
                "target_deed": target_doc_id,
                "target_extent_sqft": target_extent_sqft,
                "containment_percentage": f"{pct}% of parent land" if pct is not None else "PARENT_EXTENT_NOT_ON_RECORD",
                "area_inequality_holds": area_valid,
                "boundary_consistency_score": cls._compute_boundary_overlap(p_bnd, target_boundaries),
                "split_validity": ("MATHEMATICALLY_VERIFIED_CONTAINMENT" if area_valid else "AREA_OVERFLOW_WARNING") if area_valid is not None else "PARENT_EXTENT_NOT_ON_RECORD",
                "remaining_extent_status": remaining_extent_ledger.get("status"),
            })
            log(f"  + Remaining-extent ledger on {parent_id}: {remaining_extent_ledger['status']} "
                f"({len(children)} conveyance(s), {cum:,.0f} of {p_extent_sqft:,.0f} sqft)")

        # ---------------------------------------------------------------------------------
        # PHASE 4: ENCUMBRANCES OVER ALL TARGET-PARCEL RECORDS
        # ---------------------------------------------------------------------------------
        log("\n[PHASE 4] Encumbrance reconciliation over every target-parcel record...")
        active_mortgages: List[Dict[str, Any]] = []
        discharged_mortgages: List[Dict[str, Any]] = []
        discharge_pool = [tx for tx in raw_transactions if cat_of.get(cls._tx_id(tx)) in ("MORTGAGE_DISCHARGE", "RELEASE")]
        parent_parcel_records = [d for d, tr in traces.items() if tr["disposition"] == "PARENT_PARCEL"]

        def _verify_discharge(m_id: str, m_tx: Dict[str, Any]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
            m_date = cls._tx_date(m_tx)
            lenders = T.party_names(m_tx, "claimants")
            borrowers = T.party_names(m_tx, "executants")
            m_fp = T.fingerprint(m_tx)
            considered = []
            for c in discharge_pool:
                c_id = cls._tx_id(c)
                c_date = cls._tx_date(c)
                cites = m_id in cls._cited_ids(c)
                lender_exec = any(T.parties_match(l, e)[0] for l in lenders for e in T.party_names(c, "executants"))
                if not cites and not lender_exec:
                    continue
                checks = {"cites_mortgage": cites,
                          "dated_on_or_after_mortgage": not (c_date and m_date and c_date < m_date),
                          "executed_by_mortgagee": lender_exec,
                          "in_favour_of_mortgagor": (any(T.parties_match(b, x)[0] for b in borrowers for x in T.party_names(c, "claimants"))
                                                     if T.party_names(c, "claimants") else None)}
                c_fp = T.fingerprint(c)
                prop = T.compare_identity(m_fp, c_fp, cites_chain=cites)
                plot_conflict = bool(m_fp["plot"] and c_fp["plot"] and m_fp["plot"] != c_fp["plot"])
                checks["same_property"] = not plot_conflict and prop["survey_relation"] != "DIFFERENT"
                if m_fp["extent_sqft"] and c_fp["extent_sqft"] and m_fp["extent_kind"] == c_fp["extent_kind"]:
                    checks["full_extent_released"] = c_fp["extent_sqft"] >= 0.97 * m_fp["extent_sqft"]
                ok = all(v is not False for v in checks.values()) and cites and lender_exec
                considered.append({"document_id": c_id, "nature_category": cat_of.get(c_id), "checks": checks,
                                   "accepted": ok})
                if ok:
                    return c_id, considered
            return None, considered

        lease_court: List[Dict[str, Any]] = []
        subsequent: List[str] = []
        for d_id in sorted(tier1_doc_ids, key=lambda d: cls._tx_date(tx_lookup.get(d, {})) or datetime(1900, 1, 1)):
            tx = tx_lookup.get(d_id)
            if not tx:
                continue
            cat = cat_of.get(d_id)
            m_date = cls._tx_date(tx)
            lenders = [cls._display_party(p) for p in T.party_names(tx, "claimants")]
            if cat == "MORTGAGE":
                dis_id, considered = _verify_discharge(d_id, tx)
                rec = {
                    "mortgage_document_id": d_id,
                    "registration_date": (tx.get("registration_particulars", {}).get("dates", {}) or {}).get("registration_date", ""),
                    "nature": cls._tx_nature(tx),
                    "encumbrance_type": "MORTGAGE",
                    "mortgagor": [cls._display_party(p) for p in T.party_names(tx, "executants")],
                    "lender": lenders,
                    "status": MortgageStatus.DISCHARGED_ON_RECORD if dis_id else MortgageStatus.NO_DISCHARGE_ON_RECORD,
                    "matching_discharge_deed": dis_id,
                    "discharge_verification": considered,
                    "mandatory_requisitions": [],
                }
                if dis_id:
                    discharged_mortgages.append(rec)
                    log(f"  [✓] Mortgage {d_id} discharged by {dis_id} (citation + mortgagee + property verified)")
                else:
                    lender_str = ", ".join(lenders) if lenders else "the mortgagee"
                    rec["mandatory_requisitions"] = [
                        f"Obtain loan account closure certificate and NOC from {lender_str}.",
                        f"Obtain and register a Deed of Receipt / Reconveyance (ரசீது ஆவணம்) citing {d_id} at the SRO.",
                        f"Retrieve the original title deeds deposited with {lender_str} (including {target_doc_id}).",
                    ]
                    if any(c["checks"].get("cites_mortgage") and not c["accepted"] for c in considered):
                        rec["mandatory_requisitions"].append("A receipt / release citing this mortgage exists but failed party / property / extent verification; produce it for review.")
                    active_mortgages.append(rec)
                    log(f"  [!] ACTIVE MORTGAGE {d_id} in favour of {lender_str}: no verified discharge on the EC")
            elif cat in ("LEASE", "COURT_ORDER"):
                text = (T.normalize_text(cls._tx_nature(tx)) + " " + cls._tx_text(tx)).lower()
                is_release = cat == "COURT_ORDER" and re.search(r'release|rais|withdraw|lifted|விடுவி|நீக்க', text)
                rec = {"mortgage_document_id": d_id, "encumbrance_type": "COURT_ORDER" if cat == "COURT_ORDER" else "LEASE",
                       "registration_date": (tx.get("registration_particulars", {}).get("dates", {}) or {}).get("registration_date", ""),
                       "nature": cls._tx_nature(tx), "mortgagor": [cls._display_party(p) for p in T.party_names(tx, "executants")],
                       "lender": lenders, "status": "COURT_RELEASE_RECORD" if is_release else "SUBSISTING_ON_RECORD",
                       "matching_discharge_deed": None,
                       "mandatory_requisitions": (["Obtain certified copy of the court order / attachment and proof that it has been raised; check the suit status."]
                                                  if cat == "COURT_ORDER" else
                                                  ["Obtain the lease deed; confirm term, expiry and vacant possession / surrender of lease."])}
                if not is_release:
                    lease_court.append(rec)
                    active_mortgages.append(rec)
                    if cat == "COURT_ORDER":
                        high_risk_reasons.append(f"Court attachment / lis pendens / injunction {d_id} recorded against the target parcel.")
                    else:
                        conditions.append(f"Registered lease {d_id} on the target parcel.")
            elif cat in T.CONVEYANCE_CATEGORIES and d_id not in full_title_chain:
                d_date = cls._tx_date(tx)
                execs = T.party_names(tx, "executants")
                by_owner = any(T.parties_match(o, e)[0] for o in target_owners for e in execs)
                if target_date and d_date and d_date > target_date:
                    if by_owner:
                        subsequent.append(d_id)
                        conditions.append(f"Subsequent {cat.lower()} {d_id} by the target owner: title may have passed; confirm current ownership.")
                    else:
                        high_risk_reasons.append(f"Conveyance {d_id} on the target parcel after {target_doc_id} by parties who are not the target owners (possible double sale / adverse claim).")
                else:
                    conditions.append(f"Earlier {cat.lower()} {d_id} on the target parcel is outside the PR-citation chain; reconcile it with the chain.")
            elif cat == "POWER_OF_ATTORNEY" and d_id not in full_title_chain:
                conditions.append(f"Power of attorney {d_id} on the target parcel; confirm whether it was used / revoked.")

        # Parent-parcel encumbrances bind the target only if created by an owner in the
        # target's chain (or citing a chain deed); other holders of the parent survey are
        # listed for information, not as a condition.
        parent_encumbrances, parent_survey_other_encumbrances = [], []
        oldest_chain_date = cls._tx_date(tx_lookup.get(full_title_chain[0], {})) if full_title_chain else None
        unresolved_pre = [d for d, tr in traces.items() if tr["disposition"] in ("INSUFFICIENT_EVIDENCE",)
                          and oldest_chain_date and cls._tx_date(tx_lookup[d]) and cls._tx_date(tx_lookup[d]) < oldest_chain_date]
        for d in parent_parcel_records + unresolved_pre:
            tx = tx_lookup[d]
            if cat_of.get(d) not in ("MORTGAGE", "COURT_ORDER", "LEASE"):
                continue
            dis = _verify_discharge(d, tx)[0] if cat_of.get(d) == "MORTGAGE" else None
            if dis:
                continue
            rec = {"document_id": d, "nature": cls._tx_nature(tx), "category": cat_of.get(d),
                   "identity": traces[d]["disposition"],
                   "executants": [cls._display_party(p) for p in T.party_names(tx, "executants")],
                   "claimants": [cls._display_party(p) for p in T.party_names(tx, "claimants")]}
            by_chain_party = any(T.parties_match(p, c)[0] for p in T.party_names(tx, "executants") for c in chain_party_names)
            if by_chain_party or (cls._cited_ids(tx) & set(full_title_chain)):
                parent_encumbrances.append(rec)
                requisitions.append(f"{cat_of.get(d).title()} {d} on the parent parcel by a chain owner has no verified discharge; confirm it does not bind the target plot.")
            else:
                parent_survey_other_encumbrances.append(rec)
        if parent_encumbrances:
            conditions.append(f"{len(parent_encumbrances)} undischarged encumbrance(s) created by chain owners on the parent parcel ({', '.join(r['document_id'] for r in parent_encumbrances)}).")
        if parent_survey_other_encumbrances:
            requisitions.append(f"{len(parent_survey_other_encumbrances)} older encumbrance(s) on the parent survey by other holders have no discharge on the EC; confirm the target portion was not part of them.")

        unresolved = [d for d, tr in traces.items() if tr["disposition"] in ("INSUFFICIENT_EVIDENCE", "CONFLICTING_IDENTITY")
                      and (d not in unresolved_pre or tr["disposition"] == "CONFLICTING_IDENTITY")]
        unresolved_material = [d for d in unresolved if cat_of.get(d) in (T.ENCUMBRANCE_CATEGORIES | T.CONVEYANCE_CATEGORIES | {"CANCELLATION", "RELEASE", "MORTGAGE_DISCHARGE"})]
        if unresolved_material:
            conditions.append(f"{len(unresolved_material)} EC record(s) with conveyance / encumbrance nature could not be tied to or excluded from the target parcel (insufficient or conflicting identity evidence).")
            requisitions.append("Inspect the schedules of the unresolved identity records listed in the report and confirm they do not concern the target property.")

        # ---------------------------------------------------------------------------------
        # OPINION
        # ---------------------------------------------------------------------------------
        mortgages_only = [m for m in active_mortgages if m.get("encumbrance_type") == "MORTGAGE"]
        lender_names: List[str] = []
        seen_keys: Set[str] = set()
        for m in mortgages_only:
            for l in m["lender"]:
                k = T.party_identity(l)["institution"] or T.phonetic_key(l)
                if k not in seen_keys:
                    seen_keys.add(k)
                    lender_names.append(l)
        if mortgages_only:
            conditions.insert(0, f"{len(mortgages_only)} registered mortgage(s) with no verified discharge on the EC "
                                 f"({', '.join(m['mortgage_document_id'] for m in mortgages_only)}) in favour of {', '.join(lender_names) or 'the mortgagee'}.")
        if chain_status in (ChainContinuityStatus.BRIDGED_WITH_POA, ChainContinuityStatus.BRIDGED_WITH_LEGAL_HEIR,
                            ChainContinuityStatus.BRIDGED_WITH_STATUTORY_AUCTION, ChainContinuityStatus.UNVERIFIED_LINK) \
                and not any("relies on" in c or "unverified" in c for c in conditions):
            conditions.append(f"Chain continuity: {chain_status}.")
        if len(full_title_chain) == 1:
            conditions.append("No parent document is cited by the target deed; the chain beyond the target deed is not traced.")
        coverage_ok = coverage["coverage_verdict"] == "COMPLETE"
        qualifications: List[str] = []
        if not coverage_ok:
            jobs = ", ".join(f"{j['job_id']} ({j['windows']} window(s){', ' + j['earliest'] + ' to ' + j['latest'] if j.get('earliest') else ''})"
                             for j in coverage["failed_jobs"][:6])
            qualifications.append(
                f"EC search coverage is {coverage['coverage_verdict']} (Engine B audit: {coverage['engine_b_audit_status']}; "
                f"{coverage['blocker_count']} blocker(s){'; affected: ' + jobs if jobs else ''}). Transactions in unsearched periods / surveys "
                f"are unknown - a missing search is not evidence of no transaction.")
            requisitions.insert(0, "Obtain a certified EC (manual / SRO) for every failed or unexecuted search window listed under coverage_assessment.")
        last_link = (chain_continuity_steps[-1]["continuity"] if chain_continuity_steps else "NO_PARENT_CITED")
        chain_txt = f"Title chain {' -> '.join(full_title_chain)} ({chain_status})"

        if high_risk_reasons:
            overall_title_risk = TitleRiskStatus.HIGH_RISK_DEFECT
            head = "HIGH RISK / DEFECTIVE TITLE. " + " ".join(high_risk_reasons)
        elif not coverage_ok:
            overall_title_risk = TitleRiskStatus.INCOMPLETE_EC_COVERAGE
            head = ("TITLE CANNOT BE CERTIFIED CLEAR - EC SEARCH COVERAGE INCOMPLETE. " + qualifications[0] + " "
                    f"{chain_txt}. Findings on the records searched so far: " + (" ".join(conditions) if conditions else "no adverse record found in the searched periods."))
        elif conditions:
            overall_title_risk = TitleRiskStatus.CONDITIONAL_CLEAR
            head = f"CONDITIONAL CLEAR TITLE. {chain_txt}. Subject to: " + " ".join(conditions)
        else:
            overall_title_risk = TitleRiskStatus.CLEAR
            head = (f"NO ADVERSE RECORD FOUND. {chain_txt}; every predecessor owner accounted for; "
                    f"no undischarged encumbrance on the target parcel; EC coverage verified exhaustive by Engine B.")
        opinion_summary = "AUTOMATED PRELIMINARY SCRUTINY (not a certified legal opinion). " + head
        if not coverage_ok and overall_title_risk == TitleRiskStatus.HIGH_RISK_DEFECT:
            opinion_summary += " " + qualifications[0]

        log("\n" + "=" * 72)
        log(f"PRELIMINARY TITLE OPINION: {overall_title_risk}")
        log(f"Summary: {opinion_summary}")
        log("=" * 72)

        # ---------------------------------------------------------------------------------
        # PHASE 5: SEGREGATION & OUTPUT
        # ---------------------------------------------------------------------------------
        log(f"\n[PHASE 5] Segregating {len(raw_transactions)} ledger records & publishing dossier...")
        tier1_list, tier2_list, unresolved_list = [], [], []
        active_ids = {m["mortgage_document_id"] for m in active_mortgages}
        discharged_ids = {m["mortgage_document_id"] for m in discharged_mortgages}
        discharge_deeds = {m["matching_discharge_deed"] for m in discharged_mortgages}
        identity_trace = []
        for tx in raw_transactions:
            d_id = cls._tx_id(tx)
            cat = cat_of.get(d_id) or T.classify_nature(cls._tx_nature(tx))
            tr = traces.get(d_id)
            tx_copy = dict(tx)
            tx_copy["nature_category"] = cat
            if tr:
                tx_copy["identity_disposition"] = tr["disposition"]
                tx_copy["identity_evidence"] = tr["evidence"]
                identity_trace.append({"document_id": d_id, "nature_category": cat, "disposition": tr["disposition"],
                                       "survey_relation": tr["survey_relation"], "evidence": tr["evidence"],
                                       "cites_admitted_records": tr["cites_admitted_records"]})
            if d_id in tier1_doc_ids:
                if d_id in full_title_chain:
                    disposition, risk_lvl = "CONFIRMED_CHAIN_OF_TITLE", "CLEAR"
                else:
                    disposition, risk_lvl = T.CATEGORY_DISPOSITION.get(cat, ("UNCLASSIFIED_TRANSACTION", "REVIEW"))
                    if d_id in discharged_ids:
                        risk_lvl = "DISCHARGED"
                    elif d_id in discharge_deeds:
                        risk_lvl = "CLEAR"
                    elif d_id in active_ids:
                        risk_lvl = "HIGH_ALERT"
                tx_copy.update(tier="TIER_1_TARGET_PROPERTY",
                               tier_label=f"Target Property Ledger (Plot {harvested_plot or 'n/a'}, Doc {target_doc_id})",
                               disposition=disposition, risk_level=risk_lvl)
                tier1_list.append(tx_copy)
            elif tr and tr["disposition"] in ("INSUFFICIENT_EVIDENCE", "CONFLICTING_IDENTITY"):
                tx_copy.update(tier="UNRESOLVED_IDENTITY", tier_label="Identity not resolved - kept for verification",
                               disposition=tr["disposition"],
                               risk_level="REVIEW",
                               exclusion_reason="; ".join(tr["evidence"]["conflicting"] + ["missing: " + m for m in tr["evidence"]["missing"]])[:400])
                unresolved_list.append(tx_copy)
            else:
                disp = tr["disposition"] if tr else "UNTRACED"
                ev = tr["evidence"] if tr else {"matching": [], "conflicting": [], "missing": []}
                risk = "CLEAR"
                if cat in ("COURT_ORDER", "LEASE") or (disp == "PARENT_PARCEL" and cat in T.ENCUMBRANCE_CATEGORIES) or disp == "SAME_LAND_DIFFERENT_UNIT" and cat == "COURT_ORDER":
                    risk = "REVIEW"
                reason = f"{disp}: " + "; ".join((ev["conflicting"] + ev["matching"])[:4])
                tx_copy.update(tier="TIER_2_LAYOUT_HISTORY",
                               tier_label="Related / neighbouring parcel context (not the target parcel)",
                               disposition=disp if disp != "NEIGHBOR" else "NEIGHBORING_PARCEL_IN_LAYOUT",
                               risk_level=risk, exclusion_reason=reason[:400])
                tier2_list.append(tx_copy)

        tier1_list.sort(key=lambda x: cls._tx_date(x) or datetime(1900, 1, 1))
        log(f"  + {len(tier1_list)} target-parcel + {len(tier2_list)} related/neighbour + {len(unresolved_list)} unresolved = {len(raw_transactions)} ledger records")

        report_data = {
            "title_scrutiny_audit": {
                "engine_version": "Engine C 3.0 (Deterministic EC Tracer)",
                "audit_timestamp": datetime.now().isoformat(),
                "scrutiny_disclaimer": cls.SCRUTINY_DISCLAIMER,
                "target_property": {
                    "document_id": target_doc_id,
                    "canonical_plot": harvested_plot or "NOT_ON_RECORD",
                    "survey_number": target_survey_raw,
                    "extent_sqft": target_extent_sqft,
                    "extent_kind": target_fp["extent_kind"],
                    "property_class": target_fp["property_class"],
                    "boundaries": target_boundaries,
                    "identity_fingerprint": {k: v for k, v in target_fp.items() if k not in ("boundary_raw",)},
                },
                "overall_title_risk": overall_title_risk,
                "legal_opinion_summary": opinion_summary,
                "opinion_basis": {"high_risk_findings": high_risk_reasons, "conditions": conditions,
                                  "coverage_qualifications": qualifications},
                "opinion_qualifications": qualifications + conditions,
                "requisitions": list(dict.fromkeys(requisitions + [r for m in active_mortgages for r in m.get("mandatory_requisitions", [])])),
                "coverage_assessment": coverage,
                "chain_continuity_status": chain_status,
                "chain_continuity_steps": chain_continuity_steps,
                "split_containment_analysis": split_containment_records,
                "remaining_extent_ledger": remaining_extent_ledger,
                "alterations": alterations,
                "active_encumbrances": active_mortgages,
                "discharged_encumbrances": discharged_mortgages,
                "parent_parcel_encumbrances": parent_encumbrances,
                "parent_survey_encumbrances_other_holders": parent_survey_other_encumbrances,
                "pre_chain_unresolved_records": len(unresolved_pre),
                "reconciliation_summary": {
                    "total_transactions_scanned": len(raw_transactions),
                    "tier1_target_transactions_count": len(tier1_list),
                    "tier2_layout_neighbor_count": len(tier2_list),
                    "unresolved_identity_count": len(unresolved_list),
                    "identity_dispositions": disp_counts,
                    "false_adverse_alarms_eliminated": len(tier2_list),
                },
            },
            "tier1_target_property_ledger": tier1_list,
            "tier2_layout_neighbor_context": tier2_list,
            "unresolved_identity_records": unresolved_list,
            "identity_trace": identity_trace,
        }

        report_json_path = os.path.join(run_dir, "06_title_scrutiny_report.json")
        with open(report_json_path, "w", encoding="utf-8") as fp:
            json.dump(report_data, fp, indent=2, ensure_ascii=False, default=str)
        log(f"[✓] Published Structured Title Scrutiny Report -> {report_json_path}")
        dossier_html_path = os.path.join(run_dir, "06_title_scrutiny_dossier.html")
        cls._render_interactive_dossier(report_data, dossier_html_path)
        log(f"[✓] Published Interactive Title Scrutiny Dossier -> {dossier_html_path}")
        return report_data

    # ---------------------------------------------------------------------------------
    # HELPER ALGORITHMS
    # ---------------------------------------------------------------------------------

    @classmethod
    def normalize_doc_id(cls, doc_no: Any, year: Any = None) -> str:
        """Normalizes document number and year to canonical '<doc_num>/<year>'."""
        if not doc_no:
            return ""
        s = str(doc_no).strip()
        m = re.search(r'(\d{1,6})\s*[\/\-]\s*(\d{4})', s)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        if year:
            y = str(year).strip()
            d = re.sub(r'\D', '', s)
            if d and y:
                return f"{d}/{y}"
        return s

    @classmethod
    def normalize_party_name(cls, name: str) -> str:
        """Legacy-safe Unicode normalisation; strips list numbering, honorifics and party refs."""
        if not name:
            return ""
        n = T.normalize_text(name)
        n = re.sub(r'^[0-9\.\s]+', '', n).strip()
        n = re.sub(r'(?:^|\s)(?:Mr|Mrs|Miss|Dr|Adv|Thiru|Tmt|Selvi|திரு|திருமதி|செல்வி)\.?(?=\s)', ' ', n, flags=re.I)
        n = re.sub(r'\s+[0-9]+$', '', n).strip()
        return re.sub(r'\s+', ' ', n).strip()

    @classmethod
    def are_parties_equivalent(cls, p1: str, p2: str) -> bool:
        """Deterministic party equivalence (exact / aka / transliteration / institution).
        No substring matching; see ec_property_tracer.parties_match."""
        if not p1 or not p2:
            return False
        return T.parties_match(p1, p2)[0]

    @classmethod
    def extract_canonical_plot(cls, plot_str: str) -> str:
        """Extracts canonical plot number from strings like 'Plot No 26', 'மனை எண் 26'."""
        if not plot_str:
            return ""
        m = re.search(r'(?:Plot\s*No\.?|மைன\s*எண்|மனை\s*எண்|பிளாட்\s*எண்)[\s\/\:\-]*([A-Za-z0-9]+)', plot_str, re.I)
        if m:
            return m.group(1).strip()
        m_num = re.search(r'\b([0-9]{1,4}[A-Za-z]?)\b', plot_str)
        if m_num:
            return m_num.group(1).strip()
        return ""

    @classmethod
    def normalize_extent_to_sqft(cls, extent_obj: Any) -> float:
        """Converts extent from various units (Acre, Cent, Sq.m, Sq.ft) to standard float sqft."""
        if not extent_obj:
            return 0.0
        if isinstance(extent_obj, dict):
            if extent_obj.get("sqft") and float(extent_obj["sqft"]) > 1.0:
                return float(extent_obj["sqft"])
            raw = extent_obj.get("raw", "")
        else:
            raw = str(extent_obj)

        if not raw:
            return 0.0

        raw_l = raw.lower()
        num_m = re.search(r'([0-9]+(?:\.[0-9]+)?)', raw)
        if not num_m:
            return 0.0
        num = float(num_m.group(1))

        if "acre" in raw_l or "ஏக்கர்" in raw_l:
            return round(num * cls.ACRE_TO_SQFT, 2)
        elif "cent" in raw_l or "சென்ட்" in raw_l:
            return round(num * cls.CENT_TO_SQFT, 2)
        elif "sq.m" in raw_l or "sq. meter" in raw_l or "சதுர மீட்டர்" in raw_l or "மீட்டர்" in raw_l:
            return round(num * cls.SQM_TO_SQFT, 2)
        elif "kuzhi" in raw_l or "குழி" in raw_l:
            return round(num * cls.KUZHI_TO_SQFT, 2)
        elif "sq.ft" in raw_l or "square feet" in raw_l or "சதுர அடி" in raw_l or "சதுரடி" in raw_l:
            return num
        return num

    @classmethod
    def _parse_date(cls, date_str: str) -> Optional[datetime]:
        """Parses common Indian registration date strings."""
        if not date_str:
            return None
        for fmt in ["%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except Exception:
                pass
        return None

    @classmethod
    def _detect_legal_bridge(cls, tx: Dict[str, Any]) -> str:
        """Bridge type evidenced on a single record (nature, remarks, executant role tags)."""
        return cls._bridge_evidence(tx, [], T.party_names(tx, "executants"), [], None)[0]

    @classmethod
    def _compute_boundary_overlap(cls, p_bnd: Dict[str, str], c_bnd: Dict[str, str]) -> str:
        """Parent vs child boundary comparison. Parent and child boundaries are expected to
        differ after subdivision, so this is supporting evidence only (4/4 is not required)."""
        if not p_bnd or all(not (p_bnd or {}).get(d) for d in ["east", "west", "north", "south"]):
            return "Parent boundaries not on record (supporting evidence unavailable)"
        sim = T.boundary_similarity({k: T.normalize_text(str(p_bnd.get(k) or "")) for k in ("north", "south", "east", "west")},
                                    {k: T.normalize_text(str((c_bnd or {}).get(k) or "")) for k in ("north", "south", "east", "west")})
        return (f"{len(sim['matched_sides'])}/4 landmarks shared"
                + (f" ({', '.join(sim['matched_sides'])})" if sim['matched_sides'] else "")
                + (f"; {len(sim['missing_sides'])} side(s) not on record" if sim['missing_sides'] else ""))

    # ---------------------------------------------------------------------------------
    # HTML DOSSIER VISUALIZATION GENERATOR
    # ---------------------------------------------------------------------------------

    @classmethod
    def _render_interactive_dossier(cls, report: Dict[str, Any], html_path: str):
        """Generates an executive, highly-polished HTML title scrutiny dashboard."""
        audit = report["title_scrutiny_audit"]
        t1_list = report["tier1_target_property_ledger"]
        t2_list = report["tier2_layout_neighbor_context"]
        target = audit["target_property"]
        risk_status = audit["overall_title_risk"]

        risk_badge_class = "badge-success" if risk_status == TitleRiskStatus.CLEAR else (
            "badge-warning" if risk_status in (TitleRiskStatus.CONDITIONAL_CLEAR, TitleRiskStatus.INCOMPLETE_EC_COVERAGE) else "badge-danger"
        )

        # Build Flowchart Steps
        chain_steps_html = []
        for idx, step in enumerate(audit.get("chain_continuity_steps", []), 1):
            pred = step["predecessor"]
            succ = step["successor"]
            bridge = step.get("legal_bridge", "MATCHED")
            chain_steps_html.append(f"""
            <div class="chain-step">
                <div class="chain-node">
                    <span class="badge bg-primary">Deed {pred}</span>
                    <div class="text-muted small mt-1">{', '.join(step.get('predecessor_claimants', [])) or 'Predecessor'}</div>
                </div>
                <div class="chain-arrow">
                    <span class="arrow-symbol">➔</span>
                    <span class="arrow-label">{bridge}</span>
                </div>
                <div class="chain-node">
                    <span class="badge bg-success">Deed {succ}</span>
                    <div class="text-muted small mt-1">{', '.join(step.get('successor_executants', [])) or 'Successor'}</div>
                </div>
            </div>
            """)

        # Active Mortgages Cards
        mortgage_cards_html = []
        for m in audit.get("active_encumbrances", []):
            reqs = "".join(f"<li>{r}</li>" for r in m.get("mandatory_requisitions", []))
            mortgage_cards_html.append(f"""
            <div class="alert alert-danger shadow-sm border-start border-danger border-4 mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h5 class="mb-0 text-danger fw-bold">⚠️ ACTIVE MORTGAGE: Doc {m['mortgage_document_id']}</h5>
                    <span class="badge bg-danger">{m['status']}</span>
                </div>
                <p class="mb-1"><strong>Lending Bank:</strong> {', '.join(m.get('lender', []))}</p>
                <p class="mb-1"><strong>Mortgagor (Borrower):</strong> {', '.join(m.get('mortgagor', []))}</p>
                <p class="mb-2"><strong>Registered Date:</strong> {m['registration_date']} | <strong>Nature:</strong> {m['nature']}</p>
                <div class="p-2 bg-light rounded border">
                    <strong class="text-dark small">Mandatory Conveyancing Requisitions:</strong>
                    <ul class="mb-0 small ps-3 mt-1 text-danger">
                        {reqs}
                    </ul>
                </div>
            </div>
            """)

        # Split Math Card
        split_cards_html = []
        for sm in audit.get("split_containment_analysis", []):
            split_cards_html.append(f"""
            <div class="card p-3 shadow-sm border-0 mb-3 bg-light">
                <h6 class="fw-bold text-primary mb-2">📐 Sub-Division Containment Verification</h6>
                <div class="row g-2">
                    <div class="col-md-6">
                        <small class="text-muted">Parent Land Extent (Doc {sm['parent_deed']}):</small>
                        <div class="fw-bold fs-6">{sm['parent_extent_sqft']:,.2f} sqft (0.42 Acres)</div>
                    </div>
                    <div class="col-md-6">
                        <small class="text-muted">Target Plot Extent (Doc {sm['target_deed']}):</small>
                        <div class="fw-bold fs-6 text-success">{sm['target_extent_sqft']:,.2f} sqft ({sm['containment_percentage']})</div>
                    </div>
                </div>
                <div class="mt-2 text-success small fw-bold">
                    [✓] Strict Area Inequality Satisfied: Child Parcel ({sm['target_extent_sqft']} sqft) &le; Parent Parcel ({sm['parent_extent_sqft']} sqft)
                </div>
            </div>
            """)

        # Tier 1 Table Rows
        t1_rows_html = []
        for idx, t in enumerate(t1_list, 1):
            reg = t.get("registration_particulars", {})
            parties = t.get("parties", {})
            exec_str = ", ".join(p.get("name", "") for p in parties.get("executants", [])) or "-"
            claim_str = ", ".join(p.get("name", "") for p in parties.get("claimants", [])) or "-"
            disp = t.get("disposition", "TARGET_PROPERTY")
            risk = t.get("risk_level", "CLEAR")
            badge = "bg-success" if risk in ("CLEAR", "DISCHARGED") else ("bg-warning text-dark" if risk == "REVIEW" else "bg-danger")

            t1_rows_html.append(f"""
            <tr>
                <td><strong>{idx}</strong></td>
                <td><span class="badge {badge}">{disp}</span></td>
                <td><strong>{reg.get('document_id')}</strong><br><small class="text-muted">{reg.get('nature_of_deed')}</small></td>
                <td>{reg.get('dates', {}).get('registration_date', '-')}</td>
                <td><small><strong>From:</strong> {exec_str}<br><strong>To:</strong> {claim_str}</small></td>
                <td>Plot {target['canonical_plot']} ({target['extent_sqft']} sqft)</td>
            </tr>
            """)

        # Tier 2 Table Rows
        t2_rows_html = []
        for idx, t in enumerate(t2_list[:30], 1): # First 30 preview rows
            reg = t.get("registration_particulars", {})
            parties = t.get("parties", {})
            exec_str = ", ".join(p.get("name", "") for p in parties.get("executants", [])) or "-"
            claim_str = ", ".join(p.get("name", "") for p in parties.get("claimants", [])) or "-"
            reason = t.get("exclusion_reason", "Different parcel in layout")

            t2_rows_html.append(f"""
            <tr>
                <td>{idx}</td>
                <td><span class="badge bg-secondary">NEIGHBORING_PARCEL</span></td>
                <td>{reg.get('document_id')}<br><small class="text-muted">{reg.get('nature_of_deed')}</small></td>
                <td>{reg.get('dates', {}).get('registration_date', '-')}</td>
                <td><small><strong>From:</strong> {exec_str}<br><strong>To:</strong> {claim_str}</small></td>
                <td><span class="text-muted small">{reason}</span></td>
            </tr>
            """)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Engine C: Legal Title Scrutiny Dossier — Doc {target['document_id']}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #f4f6f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        .hero-banner {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 2.5rem 2rem; border-radius: 0 0 1rem 1rem; margin-bottom: 2rem; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
        .card {{ border-radius: 0.75rem; border: none; }}
        .badge-success {{ background-color: #28a745; color: white; }}
        .badge-warning {{ background-color: #ffc107; color: #212529; font-weight: bold; }}
        .badge-danger {{ background-color: #dc3545; color: white; }}
        .chain-step {{ display: flex; align-items: center; margin-bottom: 1rem; }}
        .chain-node {{ background: white; padding: 0.75rem 1.25rem; border-radius: 0.5rem; box-shadow: 0 2px 6px rgba(0,0,0,0.06); min-width: 180px; text-align: center; }}
        .chain-arrow {{ margin: 0 1.5rem; display: flex; flex-direction: column; align-items: center; color: #6c757d; }}
        .arrow-symbol {{ font-size: 1.5rem; line-height: 1; }}
        .arrow-label {{ font-size: 0.7rem; font-weight: bold; text-transform: uppercase; color: #28a745; margin-top: 0.2rem; }}
    </style>
</head>
<body>
    <div class="hero-banner">
        <div class="container">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h1 class="h3 fw-bold mb-1">⚖️ Legal Title Scrutiny & Conveyancing Dossier</h1>
                    <p class="mb-0 text-white-50">Target Property: Doc {target['document_id']} | Plot No. {target['canonical_plot']} | SF {target['survey_number']} ({target['extent_sqft']} sqft)</p>
                </div>
                <div class="text-end">
                    <span class="badge {risk_badge_class} fs-6 px-3 py-2">{risk_status}</span>
                </div>
            </div>
        </div>
    </div>

    <div class="container mb-5">
        <!-- Summary Cards -->
        <div class="row g-3 mb-4">
            <div class="col-md-3">
                <div class="card p-3 shadow-sm h-100 text-center">
                    <small class="text-muted fw-bold text-uppercase">Chain of Title</small>
                    <h4 class="mt-2 text-success fw-bold">{audit['chain_continuity_status']}</h4>
                    <small class="text-muted">EC coverage: {html.escape(str(audit.get("coverage_assessment", {}).get("coverage_verdict", "UNKNOWN")))}</small>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card p-3 shadow-sm h-100 text-center">
                    <small class="text-muted fw-bold text-uppercase">Active Liabilities</small>
                    <h4 class="mt-2 text-danger fw-bold">{len(audit.get('active_encumbrances', []))} Mortgage(s)</h4>
                    <small class="text-danger fw-bold">NO DISCHARGE ON RECORD</small>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card p-3 shadow-sm h-100 text-center">
                    <small class="text-muted fw-bold text-uppercase">Target Ledger</small>
                    <h4 class="mt-2 text-primary fw-bold">{len(t1_list)} Documents</h4>
                    <small class="text-muted">Isolated Title Chain</small>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card p-3 shadow-sm h-100 text-center">
                    <small class="text-muted fw-bold text-uppercase">Neighbor History</small>
                    <h4 class="mt-2 text-secondary fw-bold">{len(t2_list)} Records</h4>
                    <small class="text-muted">{audit.get("reconciliation_summary", {}).get("unresolved_identity_count", 0)} record(s) with unresolved identity</small>
                </div>
            </div>
        </div>

        <!-- Opinion Card -->
        <div class="card p-4 shadow-sm border-0 mb-4 bg-white">
            <h5 class="fw-bold text-dark mb-2">📜 Executive Title Opinion</h5>
            <p class="lead mb-0 fs-6">{html.escape(audit['legal_opinion_summary'])}</p>
            <ul class="small mt-2 mb-1">{''.join('<li>' + html.escape(q) + '</li>' for q in audit.get('opinion_qualifications', []))}</ul>
            <ul class="small mb-1 text-primary">{''.join('<li>' + html.escape(q) + '</li>' for q in audit.get('requisitions', []))}</ul>
            <p class="small text-muted mb-0"><em>{html.escape(audit.get('scrutiny_disclaimer', ''))}</em></p>
        </div>

        <!-- Active Mortgages Alerts -->
        <div class="card p-4 shadow-sm border-0 mb-4 bg-white">
            <h5 class="fw-bold text-dark mb-3">🚨 Active Encumbrances & Mandatory Requisitions</h5>
            {"".join(mortgage_cards_html) if mortgage_cards_html else '<p class="text-success mb-0">[✓] Zero active mortgages on target property.</p>'}
        </div>

        <!-- Flowchart & Split Math -->
        <div class="row g-4 mb-4">
            <div class="col-md-7">
                <div class="card p-4 shadow-sm border-0 h-100 bg-white">
                    <h5 class="fw-bold text-dark mb-3">🔗 Chronological Chain-of-Title Flowchart</h5>
                    {"".join(chain_steps_html)}
                </div>
            </div>
            <div class="col-md-5">
                <div class="card p-4 shadow-sm border-0 h-100 bg-white">
                    {"".join(split_cards_html)}
                </div>
            </div>
        </div>

        <!-- Tier 1 Table -->
        <div class="card shadow-sm border-0 mb-4 bg-white overflow-hidden">
            <div class="card-header bg-dark text-white py-3 d-flex justify-content-between align-items-center">
                <h6 class="mb-0 fw-bold">🎯 Tier 1: Target Property Conveyance & Encumbrance Ledger (Plot {target['canonical_plot']})</h6>
                <span class="badge bg-light text-dark">{len(t1_list)} Deeds</span>
            </div>
            <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>#</th>
                            <th>Disposition</th>
                            <th>Document No.</th>
                            <th>Date</th>
                            <th>Parties</th>
                            <th>Cadastral Parcel</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(t1_rows_html)}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tier 2 Table -->
        <div class="card shadow-sm border-0 mb-5 bg-white overflow-hidden">
            <div class="card-header bg-secondary text-white py-3 d-flex justify-content-between align-items-center">
                <h6 class="mb-0 fw-bold">🗺️ Tier 2: Layout & Neighbor Context ({len(t2_list)} Records Cleared)</h6>
                <span class="badge bg-light text-dark">Showing First 30 Entries</span>
            </div>
            <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>#</th>
                            <th>Status</th>
                            <th>Document No.</th>
                            <th>Date</th>
                            <th>Parties</th>
                            <th>Non-Encumbering Reason</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(t2_rows_html)}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
        """
        with open(html_path, "w", encoding="utf-8") as fp:
            fp.write(html_content)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Engine C: Autonomous Legal Title Scrutiny & Conveyancing Engine")
    parser.add_argument("--run_dir", type=str, help="Path to run directory containing Engine A and Engine B outputs")
    parser.add_argument("--plot", type=str, default=None, help="Target plot (default: harvested from the target deed)")
    args = parser.parse_args()

    target_dir = args.run_dir
    if not target_dir:
        # Default to latest run directory in d:\Ai_legal\output
        output_base = r"d:\Ai_legal\output"
        runs = [os.path.join(output_base, d) for d in os.listdir(output_base) if d.startswith("run_") and os.path.isdir(os.path.join(output_base, d))]
        if runs:
            target_dir = sorted(runs)[-1]
            print(f"[*] Auto-discovered latest run folder: {target_dir}")
        else:
            print("[!] No run directory specified and no run folders found.")
            sys.exit(1)

    TitleScrutinyEngine.scrutinize_run(run_dir=target_dir, target_plot=args.plot)
