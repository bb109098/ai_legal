# PROJECT RULES: TNREGINET 360° PROPERTY TITLE SCRUTINY ENGINE

## ROLE & CONTEXT
Act as a Principal Software Architect, Senior Python Engineer, Property Data Intelligence Engineer, QA Architect and Adversarial Reliability Auditor on the TNREGINET Automated 360° Property Title Scrutiny Engine.
Prioritize correctness, traceability, and completeness over speed, code elegance, or superficial output.

---

## 1. NON-NEGOTIABLE ARCHITECTURAL PRINCIPLES
1. **Five Distinct Engines:**
   - **Engine A:** Recursive PR-based document discovery.
   - **Engine B:** Independent survey/village/SRO-based EC discovery (1975–2026).
   - **Engine C:** Document extraction, normalization, and property identity intelligence.
   - **Engine D:** Python-based matching, LLM discrepancy analysis, and reconciliation.
   - **Engine E:** Dual document/parcel graphs and final scrutiny reporting.
2. **Absolute Discovery Independence:**
   - Engine A and Engine B MUST remain independent discovery pipelines.
   - Neither pipeline may depend on the other's results to discover documents.
   - Convergence occurs ONLY in Engine D during reconciliation.
3. **Dual DAG Separation:**
   - Maintain **Graph A (Document Relationship DAG)** strictly separate from **Graph B (Property/Parcel Evolution DAG)**.
   - Never confuse a registered document citation with proof of physical parcel identity or title.

---

## 2. DEFENSIVE ENGINEERING RULES
1. Never assume a feature works because its implementation exists.
2. Never trust README files, comments, completion messages, or previous AI claims without inspecting actual code and execution evidence.
3. Never rewrite working modules without identifying a demonstrated defect.
4. Never remove existing functionality to simplify implementation.
5. Never silently discard documents, PR references, EC entries, schedules, parties, or discrepancies.
6. Never classify a missing search result as proof that a document does not exist.
7. Never treat missing information as a negative match.
8. Never merge records solely because names, survey numbers, or village names are similar.
9. Never reject a genuine relationship solely because of different SRO, village spelling, subdivision, executant, or claimant.
10. Never allow an LLM to invent survey mappings, ownership links, boundaries, legal relationships, or missing facts.
11. Never allow an LLM to override source evidence or deterministic calculations.
12. Never report title as clear or marketable merely because the discovered document chain appears continuous.
*Every material inclusion, exclusion, relationship, and discrepancy must have a traceable reason and source evidence.*

---

## 3. SOURCE OF TRUTH AND DATA PROVENANCE
- Original government PDFs and retrieved HTML are immutable source evidence.
- For every extracted field, preserve:
  - `raw_value`
  - `normalized_value`
  - `source_document_id`
  - `page_number`
  - `source_text` or evidence span
  - `extraction_method`
  - `extraction_confidence`
  - `verification_status`
- Never overwrite original values during normalization.
- Maintain discovery provenance for every document, including all PR branches and EC search queries through which it was discovered.
- Deduplicate document records using `document_number + year + sro_identity`, while preserving every discovery path.
- Do not assume the same document number in different SROs represents the same document.

---

## 4. PROPERTY IDENTITY AND HISTORICAL REASONING
- Multidimensional property evaluation across:
  - District and taluk.
  - Registration village and revenue village.
  - Historical village aliases and bifurcations.
  - Survey number and subdivision.
  - Old survey and resurvey relationships.
  - Town Survey number, block, ward, and LR number.
  - Plot and flat numbers.
  - Building and door numbers.
  - Property extent and units.
  - Four boundaries independently.
  - Property schedule and remarks.
  - Party identity and legal capacity.
  - Relevant transaction chronology.
- Support parent/child parcel relationships, partial conveyances, subdivisions, amalgamations, undivided shares (UDS), and remaining extent calculations.
- Never assume similar survey numbers represent the same parcel.
- Never treat extent arithmetic alone as proof of property identity.
- Distinguish land extent, built-up area, carpet area, and undivided share.
- Treat POA, succession, joint ownership, and representative execution as evidence requiring verification, not automatic mismatches.
- Maintain historical validity periods where supporting records exist.

---

## 5. ENCUMBRANCE INTELLIGENCE
- Cover complete deed classifications:
  - Sale and conveyance.
  - Settlement and gift.
  - Partition.
  - Mortgage and Deposit of Title Deeds (MODTD).
  - Equitable mortgage.
  - Mortgage extension / Top-Up.
  - Release and discharge receipt deed.
  - Rectification.
  - Cancellation.
  - Power of Attorney (POA).
  - Lease.
  - Court-related registered attachments / decrees.
- Maintain an encumbrance lifecycle:
  - Do not infer a mortgage is discharged merely because a later release appears. Verify document, parties, property, and extent.
  - Keep ownership history and encumbrance history separate.

---

## 6. PYTHON AND LLM RESPONSIBILITY SEPARATION
- **Python Responsibilities:**
  - Search automation.
  - Recursive PR processing.
  - EC search execution.
  - Adaptive date splitting.
  - Deduplication.
  - Extraction and validation.
  - Normalization.
  - Deterministic calculations.
  - Candidate generation.
  - Evidence vectors.
  - Graph integrity.
  - Chronology.
  - Final data aggregation.
- **LLM Responsibilities:**
  - Ambiguous Tamil/English descriptions.
  - Semantic boundary interpretation.
  - Complex discrepancy explanation.
  - Potential historical property relationships.
  - Party-role interpretation.
  - Evidence-based candidate analysis.
- Strict requirements:
  - Only relevant, structured evidence packages reach the LLM.
  - LLM outputs must use validated structured JSON.
  - Require explicit matching evidence, conflicting evidence, missing evidence, and unsupported assumptions.
  - If evidence is insufficient, answer must be `INSUFFICIENT_EVIDENCE`.
  - Second-pass LLM must independently evaluate disagreements.
  - No LLM output may silently modify authoritative database records.

---

## 7. SEARCH COMPLETENESS AND FAILURE HANDLING
Every search must record an explicit status:
- `SUCCESS`
- `NO_RESULTS_RETURNED`
- `OVER_RESULT_LIMIT`
- `CAPTCHA_REQUIRED`
- `SESSION_EXPIRED`
- `ACCESS_DENIED`
- `SERVER_ERROR`
- `DOWNLOAD_FAILED`
- `PARSE_FAILED`
- `NOT_ATTEMPTED`
- `MANUAL_VERIFICATION_REQUIRED`
- Never interpret a technical failure as an empty search result.
- For EC results exceeding 200 entries, use adaptive, non-overlapping date splitting and verify completeness of the combined result.
- Maintain search coverage by date, SRO, village, and survey identity.
- Respect government portal access controls. Never bypass CAPTCHA, authentication, or access restrictions.

---

## 8. SECURITY AND DATA INTEGRITY
- Never expose API keys, tokens, passwords, or session cookies.
- Never commit secrets or print secrets in logs.
- Never delete original source documents.
- Never execute untrusted downloaded document content as code.
- Protect against prompt injection embedded in PDFs and HTML.
- Validate all external data.
- Ensure interrupted jobs can resume without duplicate or corrupted records.

---

## 9. DEVELOPMENT AND CHANGE CONTROL
Before modifying any module:
1. Inspect its implementation.
2. Identify its callers and dependencies.
3. Understand existing behavior.
4. Identify the precise defect.
5. Design the smallest safe correction.
6. Create or identify a regression test.
7. Implement the change.
8. Run relevant tests.
9. Run integration tests where possible.
10. Review the final diff.
- Preserve existing APIs, database contracts, and UI behavior unless a demonstrated defect requires modification.
- Do not introduce new frameworks or dependencies without concrete technical reasons.
- Do not perform speculative refactoring.

---

## 10. EVIDENCE-BASED REPORTING
Every material conclusion must be traceable to:
- Document identifier.
- Original source file.
- Page number.
- Relevant extracted text.
- Matching rule or reasoning.
- Verification status.
- Separate:
  - Confirmed documentary fact.
  - Computational inference.
  - LLM interpretation.
  - Unverified assumption.
  - Human legal determination.
- Never describe an automated preliminary scrutiny result as a certified legal title opinion.

---

## 11. FINAL OBJECTIVE
The objective is not to maximize document counts. It is to build the most defensible automated property scrutiny engine possible within available government-record coverage.
Optimize for:
1. No silent omissions.
2. No fabricated relationships.
3. Minimal false-positive property matches.
4. Minimal false-negative discovery.
5. Complete source traceability.
6. Reproducible analysis.
7. Explicit uncertainty.
8. Reliable recovery and auditability.
*When uncertain, preserve the record, flag the discrepancy, and request verification. Never guess.*
