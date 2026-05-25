# Data Sources

## Overview

All data sources used in this project are publicly available.
No proprietary or licensed data is included in this repository.
Raw PDF files are not redistributed — only the processing scripts
and derived training pairs.

---

## Financial Statements

### US Banks — SEC EDGAR (Automated Download)

Source: U.S. Securities and Exchange Commission EDGAR database
URL: https://data.sec.gov/submissions/
Format: HTML (10-K annual filings)
Years: 2015–2025 (where available)
Licence: Public domain (regulatory filings)

| Bank | CIK | Years |
|------|-----|-------|
| JPMorgan Chase | 0000019617 | 2016–2025 |
| Bank of America | 0000070858 | 2016–2025 |
| Wells Fargo | 0000072971 | 2016–2025 |
| Citigroup | 0000831001 | 2016–2025 |
| Goldman Sachs | 0000886982 | 2016–2025 |
| Morgan Stanley | 0000895421 | 2016–2025 |
| US Bancorp | 0000036104 | 2016–2025 |
| PNC Financial | 0000713676 | 2016–2025 |
| Truist Financial | 0000092122 | 2016–2025 |
| Capital One | 0000927628 | 2016–2025 |
| American Express | 0000004962 | 2016–2025 |
| Bank of New York Mellon | 0001390777 | 2016–2025 |
| State Street | 0000093751 | 2016–2025 |
| Charles Schwab | 0000316709 | 2016–2025 |
| Fifth Third Bancorp | 0000035527 | 2016–2025 |
| Regions Financial | 0001281761 | 2016–2025 |
| KeyCorp | 0000091576 | 2016–2025 |
| Huntington Bancshares | 0000049196 | 2016–2025 |
| Comerica | 0000028412 | 2016–2025 |
| Zions Bancorporation | 0000109380 | 2016–2025 |

### UK Banks — Investor Relations Pages (Manual Download)

Source: Individual bank investor relations pages
Format: PDF
Years: 2020–2025
Licence: Publicly available (investor disclosure)

| Bank | IR Page |
|------|---------|
| Lloyds Banking Group | lloydsbankinggroup.com/investors |
| Barclays | home.barclays/investor-relations |
| HSBC Holdings | hsbc.com/investors |
| NatWest Group | investors.natwestgroup.com |
| Standard Chartered | sc.com/en/investors |
| Deutsche Bank | investor-relations.db.com |
| BNP Paribas | invest.bnpparibas |
| UniCredit | unicreditgroup.eu/en/investors |
| ING Group | ing.com/Investor-relations |
| ABN AMRO | abnamro.com/en/investors |

### Australian Banks — Investor Relations Pages (Manual Download)

| Bank | IR Page |
|------|---------|
| Commonwealth Bank | commbank.com.au/about-us/investors |
| ANZ Banking Group | anz.com/shareholder/centre |
| Westpac | westpac.com.au/about-westpac/investor-centre |
| NAB | nab.com.au/about-us/shareholder-centre |

---

## Rating Agency Methodology Documents

### Fitch Ratings
Document: Fitch Bank Rating Criteria
Source: fitchratings.com (free registration)
Format: PDF (scanned — OCR processed)
Note: Full 65-page methodology document

### S&P Global Ratings
Document: S&P Global Banks Rating Criteria
Source: spglobal.com/ratings (free registration)
Format: PDF
Note: Core bank rating methodology

### DBRS Morningstar
Document: Global Methodology for Rating Banks and Banking Organisations
Source: dbrs.morningstar.com (free, no registration)
Format: PDF

---

## Regulatory and Supervisory Documents

All documents below are fully public — no registration required.

### Basel Committee on Banking Supervision (BIS)

| Document | URL | CAMELS Relevance |
|----------|-----|-----------------|
| Core Principles for Effective Banking Supervision | bis.org/publ/bcbs230.pdf | All pillars |
| Basel III Capital Framework | bis.org/publ/bcbs189.pdf | Capital (C) |
| Basel IV / Output Floor | bis.org/bcbs/publ/d424.pdf | Capital (C) |
| Liquidity Coverage Ratio | bis.org/publ/bcbs238.pdf | Liquidity (L) |
| Net Stable Funding Ratio | bis.org/bcbs/publ/d295.pdf | Liquidity (L) |
| IRRBB Standard | bis.org/bcbs/publ/d368.pdf | Sensitivity (S) |
| Leverage Ratio Framework | bis.org/bcbs/publ/d365.pdf | Capital (C) |
| BIS WP 595 — Bank Ratings | bis.org/publ/work595.pdf | Methodology |
| BIS WP 822 — CAMELS Ratings | bis.org/publ/work822.pdf | Methodology |

### OCC Comptroller's Handbook

| Document | URL | CAMELS Pillar |
|----------|-----|---------------|
| Bank Supervision Process | occ.treas.gov (CAMELS section) | All |
| Capital Adequacy | occ.treas.gov | Capital (C) |
| Loan Portfolio Management | occ.treas.gov | Asset Quality (A) |
| Earnings | occ.treas.gov | Earnings (E) |
| Liquidity | occ.treas.gov | Liquidity (L) |
| Sensitivity to Market Risk | occ.treas.gov | Sensitivity (S) |

### FDIC

| Document | URL | CAMELS Pillar |
|----------|-----|---------------|
| Risk Management Examination Manual — Overview | fdic.gov/regulations/safety/manual | All |
| CAMELS Rating System (Section 6.1) | fdic.gov/regulations/safety/manual | All |

### Bank of England / PRA

| Document | Relevance |
|----------|-----------|
| PRA Approach to Banking Supervision | All pillars |
| PRA SS3/15 — ICAAP | Capital (C) |

### European Banking Authority

| Document | Relevance |
|----------|-----------|
| EBA SREP Guidelines | All pillars |
| EBA NPL Guidelines | Asset Quality (A) |
| EBA 2023 Stress Test Methodology | All pillars |

### IMF

| Document | Relevance |
|----------|-----------|
| Financial Soundness Indicators Guide 2019 | All pillars |

---

## Reproducibility

To reproduce the full dataset from scratch:

```bash
# 1. Download financial statements
./run.sh --download-all --years 10

# 2. Download regulatory documents
./run.sh --download-ra

# 3. Place Fitch, S&P rating methodology PDFs in rating_agency/
#    (manual download — free registration required)

# 4. Run full pipeline
./run.sh --reprocess

# 5. Upgrade training pair quality
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python scripts/05_upgrade_training_pairs.py
```

Total estimated download size: ~15GB (financial statements)
Total estimated processing time: ~2–4 hours (extraction + pair building)
Total estimated upgrade cost: ~$5 (Claude Haiku API)

---

## Data Licence and Usage

**Financial statements:** Public company disclosures. Publicly available
under applicable securities law. Not redistributed in raw form.
Training pairs derived from these documents are transformative works.

**Basel/BIS documents:** © Bank for International Settlements.
"Publications are available to the public and may be reproduced for
educational and non-commercial use." (bis.org terms)

**OCC/FDIC documents:** US government works, public domain.

**EBA documents:** © European Banking Authority. Available under
EBA's open data policy for non-commercial use.

**PRA/BoE documents:** © Bank of England. Available under Open
Government Licence v3.0.

**Rating agency documents (Fitch, S&P, DBRS):** © respective agencies.
Not redistributed. Users must obtain directly from source.
