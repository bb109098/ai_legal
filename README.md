# AI Legal — Autonomous Legal Title Scrutiny & Conveyancing Pipeline (TNREGINET)

An end-to-end deterministic system designed for property legal scrutiny across Tamil Nadu registration jurisdictions (TNREGINET).

## Core Architecture
- **Engine A (`engines/engine_a/`):** Root Deed & Recursive PR Lineage Engine. Traverses prior registered documents backward chronologically.
- **Engine B (`engines/engine_b/`):** 51-Year Encumbrance Certificate Downloader. Features adaptive binary date-halving for >200 record queries and table-unclipped PDF rendering.
- **Engine C (`engines/engine_c/`):** Autonomous Conveyancing & Title Scrutiny Engine. Executes split containment mathematics, mortgage reconciliation, and two-tier ledger segregation.

## Quick Start
```powershell
# Run Scrutiny on a Document
python run_scrutiny_pipeline.py --doc 1579 --year 2021 --sro "Trichy Joint 1" --sro_id "20445:1" --plot 26
```
Or double-click `RUN_LEGAL_SCRUTINY.bat`.

## Tests
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
```
Deterministic offline tests (no portal access) cover PR-citation harvesting, recursive PR lineage
traversal across administrative boundary shifts (8396/2022 -> 3086/2007 -> 1572/1644/1904 of 2007),
urban TSLR (Ward / Block / T.S. No.) planning, and parity with the pre-fix planner on the benchmark
extractions in `data/batch_audit_results.json`.
