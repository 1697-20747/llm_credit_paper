# Data Acquisition Plan — Annual Reports & Pillar 3
## CAMELS Credit Analysis System

> **Objective:** Maximise the volume and quality of annual report and Pillar 3
> training data before the Colab Pro training run at 4,096 tokens.
>
> **Focus:** Annual reports and Pillar 3 only. Rating agency, EBA, and FDIC
> pipelines covered separately.
>
> **Last updated:** 28 May 2026

---

## Current State

### What Actually Landed (valid PDFs, post-validation)

**Annual Reports — confirmed valid:**

| Bank | Years Available | Format | Source |
|------|----------------|--------|--------|
| Lloyds Banking Group | 2021, 2022, 2024, 2025 | PDF | lloydsbankinggroup.com |
| Barclays | 2020, 2021, 2022, 2023, 2024, 2025 | PDF | home.barclays |
| HSBC Holdings | 2020, 2021, 2022 | PDF | hsbc.com |
| NatWest Group | 2023, 2024 | PDF | investors.natwestgroup.com |
| JPMorgan Chase | 2025 only | HTM | SEC EDGAR |
| Goldman Sachs | 2025 only | HTM | SEC EDGAR |
| Morgan Stanley | 2025 only | HTM | SEC EDGAR |
| Citigroup | 2025 only | HTM | SEC EDGAR |
| Bank of America | 2025 only | HTM | SEC EDGAR |
| Wells Fargo | 2024, 2025 | HTM | SEC EDGAR |
| US Bancorp | 2020–2025 | HTM | SEC EDGAR |
| PNC Financial | 2021–2025 | HTM | SEC EDGAR |
| Truist Financial | 2020–2025 | HTM | SEC EDGAR |
| Regions Financial | 2018–2025 | HTM | SEC EDGAR |
| KeyCorp | 2017–2025 | HTM | SEC EDGAR |
| Comerica | 2018–2024 | HTM | SEC EDGAR |
| Fifth Third Bancorp | 2019–2025 | HTM | SEC EDGAR |
| Huntington Bancshares | 2022–2025 | HTM | SEC EDGAR |
| Capital One | 2020–2025 | HTM | SEC EDGAR |
| American Express | 2019–2025 | HTM | SEC EDGAR |
| Charles Schwab | 2021–2025 | HTM | SEC EDGAR |
| Bank of New York Mellon | 2021–2025 | HTM | SEC EDGAR |
| State Street | 2024–2025 | HTM | SEC EDGAR |
| Zions Bancorporation | 2020–2025 | HTM | SEC EDGAR |

**Pillar 3 — confirmed valid:**

| Bank | Years Available |
|------|----------------|
| Lloyds Banking Group | 2025 only (fy-pillar-3) |

### What Failed (67 files removed as redirect pages)

**Annual Reports — all redirect/error pages, need real URLs:**
- Deutsche Bank 2020–2024 (5 files)
- Santander Group 2020–2024 (5 files)
- UniCredit 2020–2024 (5 files)
- ING Group 2020–2024 (5 files)
- ABN AMRO 2020–2024 (5 files)
- Intesa Sanpaolo 2021–2024 (4 files)
- ANZ 2020–2024 (5 files)
- Westpac 2020–2024 (5 files)
- NAB 2020–2024 (5 files)
- HSBC 2023, 2024 (2 files — correct URL format needed)
- Lloyds 2020, 2023 (2 files — path format changed)

**Pillar 3 — all redirect/error pages:**
- Lloyds 2021, 2022, 2023, 2024 (4 files)
- Barclays 2020, 2021, 2022, 2023, 2024 (5 files)
- HSBC 2022, 2023, 2024 (3 files)
- Deutsche Bank 2021, 2022, 2023, 2024 (4 files)
- UniCredit 2022, 2023, 2024 (3 files)

---

## Target State

### Annual Reports — Full Target Coverage

**UK Banks:**

| Bank | Target Years | Approach | IR Page |
|------|-------------|----------|---------|
| Lloyds Banking Group | 2015–2025 | Automated — fix URL patterns | lloydsbankinggroup.com/investors |
| Barclays | 2015–2025 | Automated — already working | home.barclays/investor-relations |
| HSBC Holdings | 2015–2025 | Automated — fix date-stamp pattern | hsbc.com/investors |
| NatWest Group (RBS pre-2020) | 2015–2025 | Automated — fix results-center paths | investors.natwestgroup.com |
| Standard Chartered | 2015–2025 | **Manual** — HTTP 403 blocks automation | sc.com/en/investors |

**European Banks:**

| Bank | Target Years | Approach | IR Page / Notes |
|------|-------------|----------|-----------------|
| Deutsche Bank | 2015–2025 | Fix URL — investor-relations.db.com path changed | investor-relations.db.com |
| BNP Paribas | 2015–2025 | Fix URL — uses universal-registration-document naming | invest.bnpparibas |
| UniCredit | 2015–2025 | Fix URL — path structure changed | unicreditgroup.eu |
| Santander Group | 2015–2025 | Fix URL — santander.com annual-report path | santander.com/investors |
| ING Group | 2015–2025 | **Manual** — JavaScript-rendered IR page | ing.com/investor-relations |
| ABN AMRO | 2015–2025 | Fix URL — abnamro.com Annual_Reports path | abnamro.com/investors |
| Intesa Sanpaolo | 2015–2025 | Fix URL — group.intesasanpaolo.com path | group.intesasanpaolo.com |
| Société Générale | 2015–2025 | **Manual** — JavaScript-rendered | societegenerale.com |
| BBVA | 2015–2025 | **Manual** — JavaScript-rendered | shareholdersandinvestors.bbva.com |
| Credit Agricole | 2015–2025 | **Manual** — JavaScript-rendered | credit-agricole.com |
| Commerzbank | 2015–2025 | Automated — annualreport.commerzbank.com | annualreport.commerzbank.com |
| Rabobank | 2015–2025 | Automated — rabobank.com/en/investors | rabobank.com |

**Australian Banks:**

| Bank | Target Years | Approach | Notes |
|------|-------------|----------|-------|
| Commonwealth Bank (CBA) | 2015–2025 | Fix URL — FY year ending June | commbank.com.au/investors |
| ANZ | 2015–2025 | Fix URL — anz.com.au path changed | anz.com.au/shareholders |
| Westpac | 2015–2025 | Fix URL — westpac.com.au path | westpac.com.au/investor-centre |
| NAB | 2015–2025 | Fix URL — nab.com.au reports path | nab.com.au/investors |

**Canadian Banks (not yet in dataset — priority addition):**

| Bank | Target Years | Approach | IR Page |
|------|-------------|----------|---------|
| Royal Bank of Canada (RBC) | 2015–2025 | Automated | rbc.com/investor-relations |
| Toronto-Dominion Bank (TD) | 2015–2025 | Automated | td.com/ca/en/investor-relations |
| Scotiabank | 2015–2025 | Automated | scotiabank.com/investors |
| Bank of Montreal (BMO) | 2015–2025 | Automated | bmo.com/investor-relations |
| CIBC | 2015–2025 | Automated | cibc.com/investor-relations |

**US Banks — extend to 10-year history (currently 1–7 years):**

| Bank | Current | Target | Gap |
|------|---------|--------|-----|
| JPMorgan Chase | 2025 only | 2015–2025 | 10 years via EDGAR |
| Goldman Sachs | 2025 only | 2015–2025 | 10 years via EDGAR |
| Morgan Stanley | 2025 only | 2015–2025 | 10 years via EDGAR |
| Citigroup | 2025 only | 2015–2025 | 10 years via EDGAR |
| Bank of America | 2025 only | 2015–2025 | 10 years via EDGAR |
| Wells Fargo | 2024–2025 | 2015–2025 | 9 years via EDGAR |
| State Street | 2024–2025 | 2015–2025 | 9 years via EDGAR |

---

### Pillar 3 — Full Target Coverage

Pillar 3 reports contain the richest capital, RWA, and credit quality data of any
public document. Each one is 100–300 pages of granular regulatory disclosure.
Priority: UK banks first (best extraction quality), then EU, then US.

**UK Banks — highest priority:**

| Bank | Target Years | Where to Find | Notes |
|------|-------------|--------------|-------|
| Lloyds Banking Group | 2018–2025 | lloydsbankinggroup.com/investors/results-reporting/pillar-3 | 2025 already valid |
| Barclays | 2018–2025 | home.barclays/investor-relations/results-and-reports/pillar-3 | All 2020–2024 are redirect pages |
| HSBC Holdings | 2018–2025 | hsbc.com/investors → Basel III Pillar 3 | 2022–2024 are redirect pages |
| NatWest Group | 2018–2025 | investors.natwestgroup.com → Risk & Capital | Need correct filenames |
| Standard Chartered | 2018–2025 | sc.com/en/investors → Results & Reporting | HTTP 403 — manual download |

**European Banks:**

| Bank | Target Years | Notes |
|------|-------------|-------|
| Deutsche Bank | 2018–2025 | All are redirect pages — fix URL |
| BNP Paribas | 2018–2025 | invest.bnpparibas → Pillar 3 section |
| UniCredit | 2018–2025 | All are redirect pages — fix URL |
| Santander Group | 2018–2025 | santander.com/investors → Basel III |
| ING Group | 2018–2025 | ing.com → Risk & Capital reports |
| ABN AMRO | 2018–2025 | abnamro.com/investors → Capital & Risk |
| Société Générale | 2018–2025 | societegenerale.com → Pillar 3 |

**US Banks (Basel III Disclosures):**

| Bank | Target Years | Notes |
|------|-------------|-------|
| JPMorgan Chase | 2018–2025 | jpmorganchase.com → investor-relations → basel-disclosures |
| Bank of America | 2018–2025 | investor.bankofamerica.com → regulatory-and-other-filings/basel-disclosures |
| Citigroup | 2018–2025 | citigroup.com/citi/investor → Basel III |
| Wells Fargo | 2018–2025 | wellsfargo.com/invest_relations/basel |
| Goldman Sachs | 2018–2025 | goldmansachs.com/investor-relations → Basel III |
| Morgan Stanley | 2018–2025 | morganstanley.com/about-us-ir/shareholder/pillar3 |

**Australian Banks (APS330 Capital Adequacy Reports):**

| Bank | Target Years | Notes |
|------|-------------|-------|
| Commonwealth Bank | 2018–2025 | commbank.com.au → investors → APS330 |
| ANZ | 2018–2025 | anz.com → shareholders → Basel III |
| Westpac | 2018–2025 | westpac.com.au → investor-centre → Capital |
| NAB | 2018–2025 | nab.com.au → investors → Basel III |

---

## Failure Analysis & URL Fixes Required

### Pattern 1 — Deutsche Bank (all redirect, 105KB)
Current URL: `investor-relations.db.com/files/documents/annual-reports/{year}/Deutsche-Bank-Annual-Report-{year}.pdf`
Issue: DB moved to versioned paths
Fix needed: Check current URL on db.com — try: `annual-report-{year}.pdf` → look for redirect target

### Pattern 2 — UniCredit (all redirect, 153KB)
Current URL: `unicreditgroup.eu/.../UniCredit-Consolidated-Reports-and-Accounts-{year}.pdf`
Issue: Path structure changed after 2020
Fix needed: Check unicreditgroup.eu → Investors → Annual Reports for current PDF links

### Pattern 3 — Santander (all redirect, 91KB)
Current URL: `santander.com/content/dam/.../santander-{year}-annual-report.pdf`
Issue: Santander uses date-stamped versioned filenames (like HSBC)
Fix needed: Browse santander.com/investors → find actual PDF URLs per year

### Pattern 4 — ING, ABN AMRO, Intesa, ANZ, Westpac, NAB (various sizes)
Issue: URLs partially correct but path components changed
Fix needed: Visit each IR page directly to find current PDF direct links

### Pattern 5 — HSBC 2023/2024 (125KB redirect)
Current URL uses `250227-annual-report-and-accounts-2024.pdf`
Issue: Date prefix (250227 = 27 Feb 2025) is correct for 2024 report but 2023 prefix (240221) may differ
Fix needed: Verify exact date prefix for 2023 report on hsbc.com

### Pattern 6 — Barclays Pillar 3 (all redirect, 169KB)
Current URL: `home.barclays/content/dam/.../barclays-plc-pillar-3-report.pdf`
Issue: Barclays likely uses year-specific subdirectory structure
Fix needed: Check home.barclays/investor-relations for Pillar 3 download links

### Pattern 7 — Lloyds Pillar 3 2021–2024 (all redirect, 283KB)
Current URL: `lloydsbankinggroup.com/assets/pdfs/investors/{year}/{year}-lbg-pillar-3-report.pdf`
Issue: Lloyds changed naming convention — 2025 uses `2025-lbg-fy-pillar-3.pdf` (fy prefix)
Fix needed: Use `{year}-lbg-fy-pillar-3.pdf` pattern consistently

---

## Manual Downloads Required

These banks block automated downloading. Download manually from their IR pages
and save to `financials/` and `pillar3/` using the naming convention below.

**Naming convention:**
```
financials/<bank_name>_<year>_annual_report.pdf
pillar3/<bank_name>_<year>_pillar3.pdf
```

| Bank | Type | IR Page | Priority |
|------|------|---------|----------|
| Standard Chartered | AR + P3 | sc.com/en/investors/results-and-reports | High |
| ING Group | AR + P3 | ing.com/Investor-relations | High |
| BBVA | AR + P3 | shareholdersandinvestors.bbva.com | Medium |
| Société Générale | AR | societegenerale.com/en/measuring-our-performance | Medium |
| Credit Agricole | AR | credit-agricole.com/en/finance/financial-publications | Medium |
| BNP Paribas | AR | invest.bnpparibas (URD format, date-stamped filenames) | Medium |

---

## Expected Training Data Volume (Post-Completion)

| Source | Current Pairs | Target Pairs | Gap |
|--------|--------------|-------------|-----|
| Annual reports (UK PDFs) | ~180 | ~600 | +420 (fix URLs + extend years) |
| Annual reports (US EDGAR HTM) | ~757 | ~1,500 | +743 (extend to 10yr) |
| Annual reports (EU PDFs) | ~0 | ~800 | +800 (fix URLs + new banks) |
| Annual reports (AU PDFs) | ~0 | ~400 | +400 (fix URLs) |
| Annual reports (Canada — new) | ~0 | ~450 | +450 (new source) |
| Pillar 3 reports | ~14 | ~600 | +586 (critical gap) |
| **Total financial pairs** | **~951** | **~4,350** | **+3,400** |

Combined with EBA (1,463), FDIC (492+), and rating agency (1,336):
- **Current total: ~4,145 pairs**
- **Target total: ~8,000–9,000 pairs** (before quality upgrade pass)
- **After upgrade: ~8,000–9,000 analyst-quality pairs**

---

## Execution Steps

### Step 1 — Fix automated URL failures (script update)

Fix the following in `scripts/download_annual_reports.sh`:

1. Lloyds Pillar 3 → use `{year}-lbg-fy-pillar-3.pdf` pattern
2. Barclays Pillar 3 → find correct subdirectory structure
3. HSBC 2023/2024 AR → verify date prefix
4. Deutsche Bank AR + P3 → find new URL structure
5. UniCredit AR + P3 → find post-2020 URL structure
6. Santander AR → find date-stamped filename pattern
7. ANZ, Westpac, NAB → correct path components
8. ABN AMRO, Intesa → correct path components

Then run:
```bash
chmod +x *.sh scripts/*.sh
./run.sh --download-banks
```

### Step 2 — Add Canadian banks to download script

Add to `scripts/download_annual_reports.sh`:
```
RBC:      rbc.com/investor-relations/annual-reports.html
TD:       td.com/ca/en/investor-relations
Scotiabank: scotiabank.com/investors
BMO:      bmo.com/investor-relations
CIBC:     cibc.com/investor-relations
```

### Step 3 — Extend US EDGAR coverage to 10 years

```bash
./run.sh --download-us --years 10
```

This extends JPMorgan, Goldman, Morgan Stanley, Citigroup, BofA from
single-year to 10-year coverage — adds ~900 training pairs.

### Step 4 — Manual downloads

Priority order:
1. Standard Chartered AR 2015–2025 + P3 2018–2025
2. ING Group AR 2015–2025 + P3 2018–2025
3. BNP Paribas AR (URD format — date-stamped, check each year)
4. BBVA AR 2015–2025
5. Société Générale AR 2015–2025
6. Barclays Pillar 3 2018–2025 (correct URL needed)

### Step 5 — Reprocess and rebuild pairs

```bash
./run.sh --reprocess
./run.sh --pairs-only
.venv/bin/python scripts/build_benchmark_index.py --include-fdic --include-eba
```

### Step 6 — Quality upgrade on new pairs

```bash
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python scripts/05_upgrade_training_pairs.py
```

Estimated cost: ~$15–20 for the full expanded dataset.

### Step 7 — Rebuild upgraded combined file

```bash
.venv/bin/python3 -c "
import json, random
from pathlib import Path
TRAINING_DIR = Path('training_data')
random.seed(42)
def load(p): return [json.loads(l) for l in open(p) if l.strip()] if p.exists() else []
all_pairs = (load(TRAINING_DIR/'financial_pairs_upgraded.jsonl') +
             load(TRAINING_DIR/'rating_agency_pairs.jsonl') +
             load(TRAINING_DIR/'eba_pairs.jsonl') +
             load(TRAINING_DIR/'fdic_pairs.jsonl'))
random.shuffle(all_pairs)
n = max(1, int(len(all_pairs)*0.10))
def write(r,p): open(p,'w').writelines(json.dumps(x,ensure_ascii=False)+'\n' for x in r); print(f'{p.name}: {len(r)}')
write(all_pairs[n:], TRAINING_DIR/'combined_training_upgraded.jsonl')
write(all_pairs[:n], TRAINING_DIR/'combined_eval_upgraded.jsonl')
print(f'Total: {len(all_pairs)}')
"
```

### Step 8 — Colab Pro training

Upload to Colab Pro (A100 40GB):
- `training_data/combined_training_upgraded.jsonl`
- `training_data/combined_eval_upgraded.jsonl`
- `colab_training.ipynb`

Set `MAX_SEQ = 4096` in Cell 1.
Expected: val loss ~0.5–0.6, ~20 minutes on A100.

---

## Progress Tracker

| Task | Status | Notes |
|------|--------|-------|
| Validate existing files | ✅ Done | 67 invalid files removed |
| Fix Lloyds P3 URL pattern | ⬜ Todo | Use fy- prefix |
| Fix HSBC 2023/2024 URLs | ⬜ Todo | Verify date prefix |
| Fix Deutsche Bank URLs | ⬜ Todo | New path structure |
| Fix UniCredit URLs | ⬜ Todo | Post-2020 structure |
| Fix Santander URLs | ⬜ Todo | Date-stamped names |
| Fix ANZ / Westpac / NAB | ⬜ Todo | Path corrections |
| Fix Barclays P3 URLs | ⬜ Todo | Subdirectory structure |
| Add Canadian banks | ⬜ Todo | New source |
| Extend US EDGAR to 10yr | ⬜ Todo | Run --years 10 |
| Manual: Standard Chartered | ⬜ Todo | HTTP 403 |
| Manual: ING | ⬜ Todo | JS-rendered |
| Manual: BNP Paribas | ⬜ Todo | Date-stamped URD |
| Manual: BBVA | ⬜ Todo | JS-rendered |
| Manual: Barclays P3 | ⬜ Todo | Find correct URLs |
| Reprocess all | ⬜ Todo | After downloads complete |
| Quality upgrade new pairs | ⬜ Todo | ~$15–20 API cost |
| Rebuild combined files | ⬜ Todo | |
| Colab Pro training run | ⬜ Todo | 4,096 tokens, A100 |

---

## File Naming Reference

All files must be saved with consistent naming for the extractor to work:

```
# Annual Reports
financials/<bank_slug>_<year>_annual_report.pdf
financials/<bank_slug>_<year>_10k.htm          (US EDGAR)

# Pillar 3
pillar3/<bank_slug>_<year>_pillar3.pdf

# Examples
financials/deutsche_bank_2024_annual_report.pdf
financials/rbc_2024_annual_report.pdf
pillar3/barclays_2024_pillar3.pdf
pillar3/jpmorgan_chase_2024_pillar3.pdf
```

---

*This document lives at:*
`/Users/bruceschultz/Documents/projects/llm_credit_paper/DATA_ACQUISITION_PLAN.md`

*Update the Progress Tracker as tasks complete.*
