# CAMELS Credit Analysis System
### Offline AI-Powered Bank Credit Paper Generator with Benchmark Percentiles

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Platform: macOS Apple Silicon](https://img.shields.io/badge/Platform-macOS%20Apple%20Silicon-lightgrey.svg)](https://apple.com/mac)
[![Platform: Google Colab](https://img.shields.io/badge/Platform-Google%20Colab%20A100-F9AB00.svg)](https://colab.research.google.com)
[![Base Model: Qwen2.5-7B](https://img.shields.io/badge/Base%20Model-Qwen2.5--7B-orange.svg)](https://huggingface.co/Qwen)

---

## How It Works

Feed the system a bank's annual report PDF (and optionally its Pillar 3 report).
A fine-tuned Qwen2.5-7B model — running entirely offline via Ollama on your Mac —
reads the documents, extracts key metrics, and writes a complete structured credit
paper. No cloud API. No data leaving your machine. No hallucinated numbers.

**The model does all of this locally:**
- Writes the institutional profile and Annual Review highlights
- Analyses all six CAMELS pillars with citations to source page numbers
- Positions each metric against a benchmark population of 800+ bank-years
- Flags proximity to Basel III / PRA downgrade triggers
- Generates interactive peer distribution dashboards

**Training pipeline (one-time, runs before inference):**
1. Annual reports, Pillar 3 reports, and rating agency methodology documents
   are downloaded and extracted into structured JSON
2. Claude Haiku (cheap, fast) writes analyst-quality example responses —
   this produces the training data, it never runs at inference time
3. Qwen2.5-7B is fine-tuned on those examples using QLoRA
4. The fine-tuned model is deployed locally via Ollama
5. From that point, **Qwen handles everything** — no external API calls ever

---

## Overview

A fully offline, production-grade pipeline that generates structured, auditable bank
credit analyses using the **CAMELS framework** (Capital Adequacy, Asset Quality,
Management, Earnings, Liquidity, Sensitivity to Market Risk).

Every analysis includes:
- **Benchmark percentile rankings** — each metric ranked against a global bank population
- **Peer distribution charts** — histogram showing bank position vs global and regional peers
- **Downgrade trigger analysis** — distance to each regulatory threshold with time-to-trigger projection
- **Trend analysis** — 1-year and 5-year trajectory vs the peer population
- **Overview section** — institutional profile + key highlights from the Annual Review

> *CET1 ratio 14.0% — 7th decile globally (median: 13.8%, p10: 10.5%, p90: 14.2%;
> n=847 bank-years); 5th decile vs UK peers*

---

## What It Produces

**For each bank analysis, the system generates:**

1. **Credit paper** (`output/<bank>/<year>/*.md`) — full CAMELS analysis with:
   - Overview section (institutional profile + AR highlights)
   - Benchmark table (decile vs global population)
   - Six CAMELS pillars with cited metrics, regulatory context, peer comparison
   - Source citations on every numerical claim `[Source: p.XX]`

2. **Global peer dashboard** (`output/<bank>/<year>/dashboard.html`) — interactive HTML with:
   - Overview tab: summary cards, decile badges, downgrade alert banners
   - Distribution tab: peer histogram with bank/median markers + period label + toggle
   - Trends tab: time series per metric with trigger threshold lines
   - Downgrade Triggers tab: sorted by severity, distance + projected years to trigger

3. **Regional peer dashboard** (`output/<bank>/<year>/dashboard_regional.html`) — same format,
   filtered to same-currency regional peers (UK/EU/US/AU/CA)

4. **Dark mode** (`output/<bank>/<year>/dashboard_dark.html`) — dark version of global dashboard

5. **Audit JSON** (`output/<bank>/<year>/*_audit.json`) — machine-readable metrics, source pages, sections

```bash
open output/Lloyds_Banking_Group/2025/dashboard.html
open output/Lloyds_Banking_Group/2025/dashboard_regional.html
```

---

## What Makes This Different

| Feature | This System | Typical LLM |
|---------|------------|-------------|
| Source citations | Every figure cited `[Source: p.XX]` | None |
| Benchmark context | Decile vs 800+ bank population | None |
| Downgrade triggers | Distance to Basel/PRA thresholds | None |
| Regional peers | Separate UK/EU/US/AU/CA distributions | None |
| RWA currency handling | Regional only (GBP/EUR/USD/AUD/CAD) | N/A |
| Hallucination control | Refuses to invent data | Often fabricates |
| Offline inference | Fully local, no API calls | Requires cloud |
| Domain fine-tuning | Trained on 4,000+ CAMELS pairs | Generic |
| Audit trail | JSON audit index per analysis | None |
| Pillar 3 integration | RWA, IRB models, LCR detail | None |

---

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Data pipeline | ✅ Complete | 5 sources, 4,145 pairs |
| Financial pair upgrade | ✅ Complete | Claude Haiku, ~$5, resumable |
| Rating agency pairs | ✅ Complete | 1,336 pairs incl. IMF FSAP, OCC, Fed DFAST |
| EBA transparency data | ✅ Complete | 1,463 pairs, 156 EU banks, 2019–2025 |
| FDIC Call Reports | ✅ Complete | 492 pairs, 100 US banks |
| Overview pairs (Pipeline F) | ✅ Complete | ~150 pairs, API-upgraded |
| Benchmark index | ✅ Complete | UK/EU/US/AU/CA regional + global |
| Round 3 training (Mac) | ✅ Complete | 512 tokens, val loss → 0.876 |
| Dashboards | ✅ Complete | Global + regional HTML, dark mode |
| Downgrade triggers | ✅ Complete | Basel III / PRA / ECB thresholds |
| Overview section | ✅ Complete | Institutional profile + AR highlights |
| Data expansion | 🔄 In progress | 10-year coverage, Pillar 3, Canadian banks |
| Colab Pro training | ⬜ Pending | 4,096 tokens, A100 — awaiting full dataset |

---

## A Note on Bank Data Quality and Industry Standards

> *This section documents a genuine industry problem that directly affects this project
> and any other system attempting systematic quantitative analysis of bank disclosures.*

### The Problem with Bank Reporting Data

Building this system required downloading, parsing, and extracting structured financial
data from bank annual reports and Pillar 3 disclosures. The experience reveals a
significant gap between what the regulatory framework requires banks to disclose and
the practical accessibility of that data.

**Pillar 3 reports are published in a mix of formats.** Some banks publish PDF-only.
Others publish Excel workbooks alongside or instead of PDFs — but the Excel files
vary enormously in structure, sheet naming, column layout, and unit conventions from
bank to bank and year to year within the same bank. There is no standard schema.
A CET1 ratio reported as `13.50` in one bank's workbook appears as `0.1350` in
another's and `1350` (basis points) in a third.

**Extracting data from PDFs is inherently unreliable.** PDF is a presentation format,
not a data format. Tables in PDFs are reconstructed by layout engines that make
assumptions about column boundaries, merged cells, and row associations that frequently
produce incorrect results — particularly in the dense regulatory capital tables that
Pillar 3 reports contain. A figure that reads clearly to a human eye may be extracted
as part of the wrong row, merged with an adjacent cell, or split across two entries.
Any pipeline that relies on PDF table extraction for quantitative data must be treated
as producing *approximate* outputs requiring human validation, not ground truth.
**This system is no exception.**

**File naming conventions are inconsistent and change year to year.** In building the
download pipeline for this project, every major bank required its own bespoke URL
pattern that often changed between reporting years. HSBC uses date-stamped filenames
(`250227-annual-report-and-accounts-2024.pdf`) with the date reflecting the results
announcement day rather than the reporting period. Deutsche Bank stores each year's
report in the following year's folder on their server. NatWest changes the filename
of its Pillar 3 report every year with no consistent pattern. ABN AMRO migrated its
document hosting to a third-party CDN mid-series. These are not edge cases — they
represent the norm across the industry.

**Access controls create unnecessary barriers.** Several banks block automated
downloads entirely (Standard Chartered returns HTTP 403). Several others require
JavaScript execution to render their IR pages (ING, BBVA, Société Générale), making
programmatic access impossible without a headless browser. Some major US banks embed
their Pillar 3 documents in iframe viewers that prevent direct PDF download. None of
these controls serve a legitimate purpose — all of these documents are intended for
public distribution.

### What Good Would Look Like

The regulatory framework already mandates disclosure of most of this data. The gap
is purely in the *machine-readability* of that disclosure. A modest set of industry
conventions would transform this situation:

**Standardised machine-readable format.** The EBA EU-wide Transparency Exercise
demonstrates what is possible: 156 banks, consistent schema, CSV download, annual
cadence, free access. This project uses that data as its highest-quality source.
The same approach applied to Pillar 3 at the bank level — a standardised
Apache Parquet or JSON schema for the key quantitative tables — would eliminate
the extraction problem entirely and enable a new generation of analytical tools.

**Consistent file naming.** A simple convention such as
`<LEI>_<report-type>_<YYYY-MM-DD>.pdf` would make discovery and version tracking
trivial. The Legal Entity Identifier (LEI) is already a global standard; using it
as the primary key in filenames costs nothing and enables unambiguous identification.

**Stable, predictable URLs.** Regulatory filings should live at predictable paths
and not move between years. Redirects to CDNs, date-stamped paths, and
JavaScript-gated IR pages all add friction without adding value.

**Companion data files alongside PDFs.** Where banks publish a PDF Pillar 3, they
should also publish a companion structured file — XBRL, JSON, or Parquet — containing
the same quantitative tables in machine-readable form. Several regulators (EBA, FDIC,
Federal Reserve) already require this. Extending the requirement to all G-SIBs and
D-SIBs would be straightforward.

**Open download permissions.** Public regulatory disclosures should be accessible
without authentication, without JavaScript, without iframe viewers, and without
rate limiting that prevents systematic research. These documents are already public
— the friction of obtaining them serves no one.

Until such standards exist, projects like this one must work around the problem with
bespoke scrapers, PDF heuristics, manual downloads, and validation steps — all of
which add complexity and introduce potential for error. The EBA, FDIC, and Federal
Reserve have shown the way. The industry should follow.

---

## Training Dataset

### Current (4,145 pairs)

| Source | Type | Coverage | Pairs |
|--------|------|----------|-------|
| US bank 10-K filings (SEC EDGAR) | HTM | ~90 filings, 2017–2025 | ~937 |
| UK/EU bank annual reports | PDF | Lloyds, Barclays, HSBC, NatWest, Santander, UniCredit | ~937 |
| EBA EU-wide Transparency Exercise | CSV | 156 EU/EEA banks, 2019–2025 | ~1,463 |
| FDIC Call Report API | REST | 100 US banks, annual | ~492 |
| Fitch Bank Rating Criteria | PDF | Text-based | ~58 |
| S&P Global Banks Rating Criteria | PDF | Full methodology | ~85 |
| DBRS Morningstar Methodology | PDF | Full methodology | ~25 |
| Moody's Banks Rating Criteria | PDF | Argentina supplement (framework valid) | ~60 |
| Basel Committee standards (BIS) | PDF | 9 documents | ~500 |
| OCC Comptroller's Handbook | PDF | 7 volumes | ~240 |
| Federal Reserve DFAST | PDF | 2023 + 2024 stress test results | ~90 |
| IMF FSAP Technical Notes | PDF | UK, US, Germany, France, Euro Area | ~200 |
| IMF GFSR | PDF | April/October 2022–2024 | ~120 |
| Overview pairs (Pipeline F) | API-generated | ~150 annual reports | ~150 |
| **Total** | | | **~4,300** |

### Training Pipelines

| Pipeline | Source | Quality | Purpose |
|----------|--------|---------|---------|
| A — Financial statements | Annual report JSON | Template → upgraded | CAMELS section analysis |
| B — Rating agency | Methodology PDFs | Extracted | Framework knowledge |
| C — Gold credit reports | DOCX analyst papers | Gold (2× weight) | Ground truth style |
| D — EBA transparency | CSV structured data | Structured | EU bank benchmarks |
| E — FDIC Call Reports | API structured data | Structured | US bank benchmarks |
| F — Overview pairs | Annual report intros | API-upgraded | Profile + highlights writing |

**Pipeline F explained:** Claude Haiku reads the first pages of each annual report
and writes analyst-quality institutional profile and AR highlights paragraphs. These
become training examples — Haiku is a data writer, not an inference model. After
training, Qwen writes all overview sections entirely locally with no API calls.

### Target (8,000–9,000 pairs)

- **Annual reports**: 10-year coverage (2015–2025) for all UK/EU/AU/CA banks
- **Pillar 3 reports**: All major banks 2018–2025
- **Canadian banks**: RBC, TD, Scotiabank, BMO, CIBC
- **Australian banks**: ANZ, Westpac, NAB, CBA
- **Extended US EDGAR**: JPMorgan, Goldman, Morgan Stanley, BofA, Citigroup — 10 years

See `DATA_ACQUISITION_PLAN.md` for full plan and URL patterns.

---

## RWA Currency Note

RWA is reported in local currency and is **not directly comparable** across currency
zones. The benchmark index handles this correctly:

| Region | Currency | Banks |
|--------|----------|-------|
| `region_UK` | GBP | Lloyds, Barclays, HSBC, NatWest, StanChart |
| `region_EU` | EUR | Deutsche, BNP, UniCredit, Santander, ABN, Intesa |
| `region_US` | USD | JPMorgan, BofA, Citigroup, Goldman, etc. |
| `region_AU` | AUD | ANZ, Westpac, CBA, NAB |
| `region_CA` | CAD | RBC, TD, Scotiabank, BMO, CIBC |

The regional dashboard automatically uses the correct currency-matched peer group.

---

## Hardware Support

| Platform | RAM | Model | Max Tokens | Status |
|----------|-----|-------|-----------|--------|
| macOS Apple Silicon (M1/M2 16GB) | 16GB | Qwen2.5-7B (4-bit) | 512 | ✅ Supported |
| macOS Apple Silicon (M2 Pro 32GB) | 32GB | Qwen2.5-7B | 2,048 | ✅ Recommended |
| macOS Apple Silicon (M2 Max 64GB) | 64GB | Qwen2.5-14B | 4,096 | ✅ Optimal |
| Google Colab Pro (A100 40GB) | — | Qwen2.5-7B | 4,096 | ✅ Best value ($10/mo) |
| Google Colab Pro+ (A100 80GB) | — | Qwen2.5-14B | 4,096 | ✅ Best quality |
| Linux + NVIDIA (24GB VRAM) | Any | Qwen2.5-7B | 2,048 | ✅ Supported |
| Google Colab free (T4 16GB) | — | Qwen2.5-7B | 1,024 | ✅ Budget option |

> **Recommendation:** Train on **Colab Pro ($10/month)** at 4,096 tokens.
> Sequence length matters more than model size.
> A well-trained 7B at 4,096 tokens beats a 14B at 512 tokens.

---

## Training Roadmap

| Round | Platform | Tokens | Pairs | Val Loss | Status |
|-------|----------|--------|-------|----------|--------|
| 1 | Mac 16GB (MLX) | 512 | 1,737 | 3.14 → 1.30 | ✅ Done |
| 2 | Mac 16GB (MLX) | 512 | 3,832 | 2.53 → 1.07 | ✅ Done |
| 3 | Mac 16GB (MLX) | 512 | 3,832 | — → **0.876** | ✅ Done |
| 4 | Colab Pro A100 | 4,096 | 4,300+ | ~0.5–0.6 | ⬜ Pending dataset |
| 5 | Colab Pro A100 | 4,096 | 8,000+ | ~0.4 | ⬜ After data expansion |

---

## Repository Structure

```
llm_credit_paper/
│
├── scripts/
│   ├── 00_run_pipeline.py              # Master orchestrator
│   ├── 01_triage.py                    # PDF/HTM diagnostic
│   ├── 02_extract_financials.py        # Annual report + Pillar 3 extraction
│   ├── 03_extract_rating_agency.py     # Methodology + rating reports
│   ├── 04_build_training_pairs.py      # JSONL pair builder (6 pipelines A–F)
│   ├── 05_upgrade_training_pairs.py    # Claude Haiku quality upgrade (resumable)
│   ├── 06_extract_credit_reports.py    # DOCX credit paper extraction (GOLD)
│   ├── 07_build_overview_pairs.py      # ★ Pipeline F — overview pair builder
│   ├── build_benchmark_index.py        # Percentile/decile index (UK/EU/US/AU/CA)
│   ├── parse_eba_km.py                 # EBA Historical KM CSV parser
│   ├── download_annual_reports.py      # ★ Primary AR + P3 downloader
│   ├── rename_downloaded_files.py      # Normalise date-stamped filenames
│   ├── download_financials.py          # SEC EDGAR downloader
│   ├── download_rating_agency.py       # Regulatory + IMF doc downloader
│   ├── download_eba_data.py            # EBA transparency downloader
│   └── download_fdic_data.py           # FDIC Call Report API downloader
│
├── financials/                         # Annual reports (PDF, HTM)
├── pillar3/                            # Pillar 3 disclosures (PDF and/or Excel)
├── rating_agency/                      # Methodology PDFs
├── credit_reports/                     # GOLD analyst credit papers (DOCX)
├── raw_data/eba/                       # EBA transparency CSV files
│
├── processed/
│   ├── financials/                     # Extracted JSON per filing
│   ├── rating_agency/                  # Chunked JSON per methodology doc
│   ├── benchmark_index.json            # Decile index with UK/EU/US/AU/CA regions
│   └── benchmark_summary.json
│
├── training_data/
│   ├── combined_training_upgraded.jsonl # ★ Main training set
│   ├── combined_eval_upgraded.jsonl     # ★ Eval set
│   ├── financial_pairs_upgraded.jsonl   # Analyst-quality financial pairs
│   ├── rating_agency_pairs.jsonl        # Rating agency + regulatory pairs
│   ├── eba_pairs.jsonl                  # EBA transparency pairs
│   ├── fdic_pairs.jsonl                 # FDIC Call Report pairs
│   └── overview_pairs_upgraded.jsonl   # ★ Overview pairs (Pipeline F)
│
├── models/
│   ├── qwen2.5-7b-camels-adapter/      # LoRA adapter (round 3)
│   ├── qwen2.5-7b-camels-fused/        # Fused model
│   └── qwen2.5-7b-camels-4bit/         # 4-bit quantised for Ollama
│
├── output/
│   └── <bank>/<year>/
│       ├── dashboard.html              # ★ Global peer dashboard
│       ├── dashboard_regional.html     # ★ Regional peer dashboard
│       ├── dashboard_dark.html         # Dark mode
│       └── *_audit.json               # Metrics + source pages
│
├── generate_dashboard.py              # ★ Standalone dashboard generator
├── test_analysis.py                   # ★ Standalone end-to-end analysis
├── run.sh                             # ★ Main entry point
├── train_mlx.sh                       # QLoRA training (Apple Silicon)
├── colab_training.ipynb               # Google Colab training notebook
├── DATA_ACQUISITION_PLAN.md           # ★ Full data plan + URL fixes
└── requirements_ingestion.txt         # All Python dependencies
```

---

## Quick Start

```bash
# 1. Prerequisites
brew install poppler git-lfs ollama
git clone https://github.com/1697-20747/llm_credit_paper.git
cd llm_credit_paper && chmod +x run.sh && ./setup.sh

# 2. Download data
./run.sh --download-all

# 3. Rename date-stamped manual downloads
.venv/bin/python3 scripts/rename_downloaded_files.py

# 4. Validate downloads (removes redirect pages)
.venv/bin/python3 scripts/download_annual_reports.py --validate

# 5. Extract and build training data
./run.sh --reprocess
./run.sh --pairs-only

# 6. Build overview pairs (Pipeline F) — Claude Haiku writes training examples
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python3 scripts/07_build_overview_pairs.py --upgrade

# 7. Build benchmark index
.venv/bin/python3 scripts/build_benchmark_index.py --include-fdic --include-eba

# 8. Upgrade financial pairs to analyst quality (~$5)
.venv/bin/python3 scripts/05_upgrade_training_pairs.py

# 9. Rebuild combined training file
.venv/bin/python3 -c "
import json, random
from pathlib import Path
TRAINING_DIR = Path('training_data')
random.seed(42)
def load(p): return [json.loads(l) for l in open(p) if l.strip()] if p.exists() else []
all_pairs = (load(TRAINING_DIR/'financial_pairs_upgraded.jsonl') +
             load(TRAINING_DIR/'rating_agency_pairs.jsonl') +
             load(TRAINING_DIR/'eba_pairs.jsonl') +
             load(TRAINING_DIR/'fdic_pairs.jsonl') +
             load(TRAINING_DIR/'overview_pairs_upgraded.jsonl'))
random.shuffle(all_pairs)
n = max(1, int(len(all_pairs)*0.10))
def write(r,p): open(p,'w').writelines(json.dumps(x,ensure_ascii=False)+'\n' for x in r)
write(all_pairs[n:], TRAINING_DIR/'combined_training_upgraded.jsonl')
write(all_pairs[:n], TRAINING_DIR/'combined_eval_upgraded.jsonl')
print(f'Train: {len(all_pairs)-n}  Eval: {n}  Total: {len(all_pairs)}')
"

# 10. Train on Mac (512 tokens baseline)
sudo purge && ./prepare_for_training.sh && ./train_mlx.sh

# 11. Deploy and run
./fuse_and_deploy.sh
ollama serve  # separate terminal
.venv/bin/python3 test_analysis.py \
  --pdf financials/2025-lbg-annual-report.pdf \
  --pillar3 pillar3/lloyds_banking_group_2025_pillar3.pdf \
  --bank "Lloyds Banking Group"

open output/Lloyds_Banking_Group/2025/dashboard.html
```

---

## Running an Analysis

```bash
# UK bank with Pillar 3
.venv/bin/python3 test_analysis.py \
  --pdf financials/2025-lbg-annual-report.pdf \
  --pillar3 pillar3/lloyds_banking_group_2025_pillar3.pdf \
  --bank "Lloyds Banking Group"

# US bank (SEC EDGAR HTM)
.venv/bin/python3 test_analysis.py \
  --pdf financials/jpmorgan_chase_2025_10k.htm \
  --bank "JPMorgan Chase"

# Dashboards only (from existing audit file)
.venv/bin/python3 generate_dashboard.py \
  --audit output/Lloyds_Banking_Group/2025/*_audit.json
```

---

## Google Colab Training (Recommended for Round 4+)

Upload to Colab Pro (A100, $10/month):
- `training_data/combined_training_upgraded.jsonl`
- `training_data/combined_eval_upgraded.jsonl`
- `colab_training.ipynb`

Set `MAX_SEQ = 4096` in Cell 1. Run all cells. Downloads adapter as zip.

| Runtime | Max Seq | Time | Val Loss |
|---------|---------|------|----------|
| Free T4 | 1,024 | ~60min | ~0.7 |
| Colab Pro A100 | 4,096 | ~20min | ~0.5–0.6 |

---

## Dashboard Features

Distribution charts show the full peer population as a histogram. Your bank is a
**navy diamond line** with abbreviated label (`LBG 14.0%`). Peer median is a
**grey dashed triangle line**. Rating triggers are **coloured dashed lines**
(amber/red/dark red). Period badge shows `Recent 3yr (n=9)` with a toggle to
switch to all-time. The Downgrade Triggers tab projects years-to-trigger at
current trajectory for every metric approaching a threshold.

---

## Anti-Hallucination Controls

1. Grounded prompting — LLM only sees extracted source content
2. Citation enforcement — every number requires `[Source: p.XX]`
3. Temperature 0.05 — near-deterministic outputs
4. Refusal training — "Data not available" not fabrication
5. Audit JSON — every cited figure mapped to source page
6. Benchmark grounding — percentile context from real population

---

## Known Issues and Fixes

| Issue | Fix |
|-------|-----|
| `permission denied` on scripts | `chmod +x run.sh` — auto-fixes all |
| Extractor hangs on complex Pillar 3 PDF | Fixed — per-page isolation in `02_extract_financials.py` |
| Date-stamped HSBC/Lloyds filenames | Run `rename_downloaded_files.py` after manual download |
| Redirect pages pass as valid PDFs | `--validate` flag; min 1MB AR, 500KB P3 |
| Training OOM on 16GB Mac | `sudo purge` first; or use Colab Pro |
| GGUF U32 conversion error | Use Ollama base model for inference |
| RWA cross-currency comparison | Use `dashboard_regional.html` — regional peers only |
| `fitz` module not found | Use `.venv/bin/python3` not system python |
| Fitch PDF in iframe | Cmd+P → Save as PDF |

---

## Free API Keys Required

| Service | Purpose | URL |
|---------|---------|-----|
| HuggingFace | Model download | `huggingface.co/settings/tokens` |
| FDIC BankFind | Call Report data | `api.fdic.gov/banks/docs` |
| Anthropic API | Training data generation (~$8 total) | `console.anthropic.com` |
| Fitch Ratings | Rating criteria PDF | `fitchratings.com/site/register` |
| S&P Global | Rating criteria PDF | `spglobal.com/ratings/en/research-insights/register` |

---

## Citation

```bibtex
@software{camels_credit_analysis_2025,
  author  = {Schultz, Bruce},
  title   = {CAMELS Credit Analysis System},
  year    = {2025},
  url     = {https://github.com/1697-20747/llm_credit_paper},
  license = {Apache-2.0}
}
```

---

## Disclaimer

For research and internal analytical use only. Generated analyses do not constitute
investment advice or official credit ratings. All outputs should be reviewed by a
qualified credit professional before use in any decision-making context.

---

## License

Apache 2.0 — see [LICENSE](LICENSE). Compatible with Qwen2.5 base model licence.
