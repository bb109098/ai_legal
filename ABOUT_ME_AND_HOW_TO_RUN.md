# OverPaidEMI Tamil Nadu Digital Title Scrutiny Engine (Local Desktop Edition)

**Autonomous 50-Year Title Pedigree, Cadastral Concordance & Bank Scrutiny System**  
**Execution Environment:** Pure Local Python (Zero-LLM / Offline Deterministic)  
**Standard of Clearance:** Tier-1 Commercial Bank Legal Scrutiny & Madras High Court Conveyancing Standards  
**Jurisdiction:** State of Tamil Nadu, Registration Department (TNREGINET) & Land Administration (Tamil Nilam / TSLR)

---

## 1. Clean Directory Architecture

The project has been separated into clean, dedicated directories so that a non-technical user sees only what is needed:

```
D:\Ai_legal\
│
├── digital_scrutiny_engine\          <-- ⭐ CORE ARCHITECTURE ONLY (Self-Contained)
│   ├── core_engine\                  <-- 6 Modular Zero-LLM Scrutiny Engines
│   │   ├── __init__.py
│   │   ├── cadastral_concordance.py  <-- SRO Bifurcation & Urban TSLR/SF Concordance
│   │   ├── ledger_disambiguator.py   <-- 4-Stage Elimination & Sec 48 TPA Proof
│   │   ├── title_graph_chainer.py    <-- 50-Year DAG Pedigree & Present Owner Tracer
│   │   ├── tnreginet_crawler.py      <-- Certified Deed Schedule & EC Ledger Ingestion
│   │   ├── bank_report_generator.py  <-- 13-Column Bank Clearance HTML & CSV Dossier
│   │   └── evidence_vault.py         <-- TNREGINET Evidence Vault (Deeds + Full EC)
│   ├── app_server.py                 <-- Local Web Server (Browser Dashboard)
│   ├── run_legal_engine.py           <-- Core Scrutiny CLI Engine
│   ├── scrutiny_engine_bridge.py     <-- Master Production Bridge Orchestrator
│   ├── cadastral_geo_engine.py       <-- Cadastral GPS & ArcGIS Satellite Engine
│   ├── tngis_client.py               <-- TNGIS Cadastral & FMB Sketch Client
│   ├── sro_registry_data.py          <-- Tamil Nadu SRO Directory (Districts & SROs)
│   ├── START_APP.bat                 <-- One-Click Web Dashboard Launcher
│   ├── RUN_LEGAL_AUDIT.bat           <-- One-Click Desktop CLI Scrutiny Launcher
│   ├── output\                       <-- Isolated folders created for each run
│   └── [Master Reference PDFs/JSON]  <-- Certified Benchmark deeds & ECs
│
├── tests_and_sample_inputs\          <-- 📦 SEPARATE TEST & SCRATCH FOLDER
│   ├── [400+ experimental scripts]  <-- analyze_*, probe_*, test_*, submit_*
│   ├── [Sample deed PDFs & txt]      <-- document_*, sample_*, poolampatti_*
│   └── [Scraped HTML & captchas]     <-- Intermediate HTML dumps, PNGs, JSONs
│
├── sample_outputs\                   <-- 📁 HISTORICAL SAMPLE RUN DOSSIERS
│   └── [All historical audit runs]   <-- Past HTML reports, CSVs, and JSONs
│
├── START_APP.bat                     <-- 🚀 1-Click Launch from Root
├── RUN_LEGAL_AUDIT.bat               <-- 🚀 1-Click CLI Scrutiny from Root
└── ABOUT_ME_AND_HOW_TO_RUN.md        <-- 📖 This Documentation Guide
```

---

## 2. Quick Start Guide (For Non-Technical Users)

### Method 1: One-Click Desktop Web Dashboard (Easiest)
1. In Windows File Explorer, navigate to: `D:\Ai_legal\` (or `D:\Ai_legal\digital_scrutiny_engine\`).
2. Double-click **`START_APP.bat`**.
3. A local server will start and your web browser will automatically open:
   👉 **`http://localhost:5000`**
4. Select the **District**, choose the **SRO**, enter the **Document Number** and **Year**, and click:
   👉 **"RUN FULL 50-YEAR DIGITAL SCRUTINY AUDIT"**
5. On the results page, you can review the 13-column bank clearance pedigree, examine the Section 48 TPA non-double sale proof, and download official TNREGINET evidence files with 1-click.

---

### Method 2: Running via PowerShell / Command Prompt

Open PowerShell in `D:\Ai_legal\digital_scrutiny_engine\` (or `D:\Ai_legal\`) and run:

#### A. Start the Local Web App:
```powershell
python app_server.py
```
*Open `http://localhost:5000` in Google Chrome or Microsoft Edge.*

#### B. Run Scrutiny on Specific Documents from Command Line:
* **Doc 1590/2021 (Trichy Joint 1 - Family Settlement, Freehold Title):**
  ```powershell
  python run_legal_engine.py --doc 1590 --year 2021 --sro "Trichy Joint 1" --district "Trichy" --sroid "20445:1"
  ```
* **Doc 1579/2021 (Trichy Joint 1 - Sale Deed with Bank of Baroda MODTD & Top-Up):**
  ```powershell
  python run_legal_engine.py --doc 1579 --year 2021 --sro "Trichy Joint 1" --district "Trichy" --sroid "20445:1"
  ```
* **Doc 2367/2010 (Thamaraipatti - Madurai East Poolampatti Layout Plot 134):**
  ```powershell
  python run_legal_engine.py --doc 2367 --year 2010 --sro "Thamaraipatti" --district "Madurai" --sroid "20243:1"
  ```
* **Interactive Terminal Prompt (Enter any Doc No, Year, SRO):**
  ```powershell
  python run_legal_engine.py --interactive
  ```

---

## 3. What Each Run Folder Contains

For **every single run**, an isolated folder is created in `output\run_YYYYMMDD_HHMMSS_Doc_<DocNo>_<Year>_<SROName>\`:

| File Name | Purpose & Contents |
| :--- | :--- |
| **`report.html`** | Complete institutional bank legal opinion dossier with 13-column pedigree, Section 48 TPA proof banner, elimination ledger table, and clickable evidence download links. |
| **`01_Target_Deed_Doc_*.pdf`** | Official TNREGINET certified copy of the target deed under scrutiny. |
| **`02_Parent_Deed_Doc_*.pdf`** | Official TNREGINET certified copy of the traced parent document (e.g. Doc 2776/1983, Doc 3586/2004, Doc 27/1982). |
| **`03_Full_Raw_Encumbrance_Certificate_1975_2026.pdf`** | Complete 50-year raw EC PDF ledger for verification and lawyer cross-checking. |
| **`04_Registered_Bank_Mortgage_MODTD_*.pdf`** | Primary registered bank mortgage deed (if active encumbrance exists). |
| **`05_Registered_TopUp_Mortgage_*.pdf`** | Supplemental top-up mortgage deed (if active bank top-up exists). |
| **`audit_trail_elimination_ledger.csv`** | Excel spreadsheet detailing every raw EC entry examined with statutory rejection codes and reasons. |
| **`cadastral_snapshot.jpg`** | High-resolution satellite snapshot with plot boundary overlay and GPS coordinates. |
| **`fmb_sketch.pdf`** | Official Field Measurement Book sketch diagram. |
| **`master_dossier.json`** | Structured JSON export of all parsed parameters, lineages, and audit checks. |

---

## 4. The 6 Modular Zero-LLM Core Architecture Engines

| Core Module | File | Operational Responsibility |
| :--- | :--- | :--- |
| **1. Cadastral Concordance Engine** | `core_engine/cadastral_concordance.py` | Bridges Urban TSLR (Ward/Block/TS) with Rural Revenue SF numbers; handles SRO jurisdictional bifurcations across parent and child SROs (1975–2026). |
| **2. Ledger Disambiguator** | `core_engine/ledger_disambiguator.py` | Deterministic 4-stage sequential elimination cascade (Subdivisions, Layout Plots, Multi-unit Flats, Mortgages) and Section 48 TPA mathematical non-double sale proof. |
| **3. Title Graph Chainer** | `core_engine/title_graph_chainer.py` | Traces backward parentage (Target $\to$ Parent PR $\to$ Root 1975) and forward to 2026 for MODTD charges, declaring the present title holder with **zero dummy strings**. |
| **4. TNREGINET Crawler** | `core_engine/tnreginet_crawler.py` | 2-Stage automated retrieval for registered deed schedules and 50-year raw EC survey ledgers. |
| **5. Bank Report Generator** | `core_engine/bank_report_generator.py` | Generates institutional 13-column bank clearance HTML report, elimination CSV, and master JSON dossier. |
| **6. Evidence Vault** | `core_engine/evidence_vault.py` | Automatically packages target deeds, parent deeds, full raw ECs, and bank mortgages directly into each run's output folder. |
