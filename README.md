# CAMELS Credit Analysis System
### Offline AI-Powered Bank Credit Paper Generator with Benchmark Percentiles

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Platform: macOS Apple Silicon](https://img.shields.io/badge/Platform-macOS%20Apple%20Silicon-lightgrey.svg)](https://apple.com/mac)
[![Platform: Linux CUDA](https://img.shields.io/badge/Platform-Linux%20CUDA-76b900.svg)](https://nvidia.com)
[![Base Model: Qwen2.5](https://img.shields.io/badge/Base%20Model-Qwen2.5--7B%2F14B-orange.svg)](https://huggingface.co/Qwen)

---

## Overview

A fully offline, production-grade pipeline that generates structured, auditable bank
credit analyses using the **CAMELS framework** (Capital Adequacy, Asset Quality,
Management, Earnings, Liquidity, Sensitivity to Market Risk).

Every analysis includes **benchmark percentile rankings** — each metric is compared
against the full population of banks in the training dataset and assigned a global
decile and regional peer decile:

> *CET1 ratio 12.6% — 6th decile globally (median: 12.1%, p10: 9.8%, p90: 16.4%;
> n=847 bank-years); 4th decile vs UK peers (UK median: 14.2%)*

The system fine-tunes a local Qwen2.5 model on a domain-specific dataset built from:
- **200+ bank annual reports** (SEC EDGAR 10-K filings + UK/EU PDFs, 2015–2025)
- **EBA EU-wide Transparency Exercise** (156 EU/EEA banks, 2019–2025, capital metrics)
- **FDIC Call Report API** (top 100 US banks, annual data, 5 years)
- **Rating agency methodology** (Fitch, S&P, DBRS Morningstar)
- **Regulatory guidance** (Basel III/IV, OCC Comptroller's Handbook, FDIC CAMELS
  manual, EBA SREP guidelines, PRA supervisory statements)
- **Pillar 3 risk disclosures** (where available — granular RWA, IRB model outputs)

Every output is **source-cited and auditable**. No hallucination of financial data.
**Zero external API calls at inference time.** Runs entirely on-device.

---

## What Makes This Different

| Feature | This System | Typical LLM |
|---------|------------|-------------|
| Source citations | Every figure cited `[Source: p.XX]` | None |
| Benchmark context | Decile vs 800+ bank population | None |
| Hallucination control | Refuses to invent data | Often fabricates |
| Offline inference | Fully local, no API calls | Requires cloud |
| Domain fine-tuning | Trained on 3,200+ CAMELS pairs | Generic |
| Audit trail | JSON audit index per analysis | None |

---

## Hardware Support

| Platform | RAM | Model | Training Time | Status |
|----------|-----|-------|--------------|--------|
| macOS Apple Silicon (M1/M2/M3) | 16GB | Qwen2.5-7B (4-bit) | ~15–30 min | ✅ Supported |
| macOS Apple Silicon (M2 Pro/M3 Pro) | 32GB | Qwen2.5-14B | ~8–12 hours | ✅ Recommended |
| macOS Apple Silicon (M2 Max/M3 Max) | 64GB | Qwen2.5-14B | ~5–8 hours | ✅ Optimal |
| Linux + NVIDIA GPU (16GB VRAM) | Any | Qwen2.5-7B | ~2–4 hours | ✅ Supported |
| Linux + NVIDIA GPU (24GB+ VRAM) | Any | Qwen2.5-14B | ~3–6 hours | ✅ Supported |
| Google Colab (free T4) | 15GB VRAM | Qwen2.5-7B | ~60 minutes | ✅ Supported |
| Google Colab Pro (A100) | 40GB VRAM | Qwen2.5-14B | ~15 minutes | ✅ Fastest |

> **16GB M2 Pro note:** Training completes in ~15–30 minutes using the pre-quantised
> 4-bit base model (`mlx-community/Qwen2.5-7B-Instruct-4bit`, ~4GB). Peak memory
> stable at ~5.7GB. Sequence length is reduced to 512 tokens. Re-train on Colab
> with 2,048+ tokens for production quality.

---

## Training — Sequence Length and Quality

| Tokens | RAM Required | Quality | Notes |
|--------|-------------|---------|-------|
| 512 | 16GB (4-bit) | Baseline | 16GB Mac — trains fast, shorter analyses |
| 1,024 | 24GB | Good | Captures most CAMELS sections fully |
| 2,048 | 32GB | Very good | Recommended production minimum |
| 4,096 | 64GB | Excellent | Full annual report sections retained |
| 8,192 | 80GB+ A100 | Optimal | No truncation — best possible output |

**Optimal unconstrained config (A100 80GB):**
```yaml
model:          Qwen/Qwen2.5-14B-Instruct
max_seq_length: 8192
lora_rank:      32
lora_alpha:     64
num_layers:     32
```

---

## Training Dataset

| Source | Type | Files/Banks | Pairs | Notes |
|--------|------|-------------|-------|-------|
| US bank 10-K filings (SEC EDGAR) | HTM | ~90 filings | ~810 | Automated |
| UK/EU bank annual reports | PDF | ~14 filings | ~126 | Manual IR pages |
| EBA Transparency Exercise | CSV | 156 EU banks | ~1,463 | 2019–2025, Q2+Q4 |
| FDIC Call Report API | REST API | 100 US banks | ~400 | Annual, 5 years |
| Fitch Bank Rating Criteria (OCR) | PDF | 1 | ~58 | Scanned — OCR |
| S&P Global Banks Rating Criteria | PDF | 1 | ~85 | — |
| DBRS Morningstar Methodology | PDF | 1 | ~25 | — |
| Basel Committee standards (BIS) | PDF | 7 | ~500 | All free downloads |
| OCC Comptroller's Handbook | PDF | 4 | ~215 | CAMELS pillar-by-pillar |
| FDIC CAMELS manual | PDF | 1 | ~27 | Original CAMELS definition |
| EBA SREP guidelines | PDF | 1 | ~36 | EU supervisory framework |
| PRA supervisory approach | PDF | 1 | ~23 | UK framework |
| BIS working papers | PDF | 2 | ~52 | Academic methodology |
| **Total** | | | **~3,800+** | After all sources combined |

All 854 financial statement pairs upgraded to analyst-quality prose via Claude Haiku
(one-time ~$5 API call, fully resumable). See [DATA_SOURCES.md](DATA_SOURCES.md).

---

## Repository Structure

```
llm_credit_paper/
│
├── scripts/
│   ├── 00_run_pipeline.py            # Master orchestrator
│   ├── 01_triage.py                  # PDF/HTM diagnostic
│   ├── 02_extract_financials.py      # Annual report + Pillar 3 extraction
│   ├── 03_extract_rating_agency.py   # Methodology + rating reports (OCR)
│   ├── 04_build_training_pairs.py    # JSONL pair builder (5 pipelines)
│   ├── 05_upgrade_training_pairs.py  # Claude API quality upgrade (resumable)
│   ├── 06_extract_credit_reports.py  # DOCX credit paper extraction (GOLD)
│   ├── build_benchmark_index.py      # Percentile/decile index builder
│   ├── parse_eba_km.py               # EBA Historical KM CSV parser
│   ├── download_financials.py        # SEC EDGAR downloader
│   ├── download_uk_banks.py          # UK/EU/AU bank downloader
│   ├── download_rating_agency.py     # Regulatory doc downloader
│   ├── download_pillar3.py           # Pillar 3 report downloader
│   ├── download_eba_data.py          # EBA transparency ZIP downloader
│   ├── download_fdic_data.py         # FDIC Call Report API downloader
│   └── cleanup_small_files.py        # Post-download cleanup
│
├── financials/                       # Annual reports (PDF, HTM)
├── pillar3/                          # Pillar 3 risk disclosures (PDF)
├── rating_agency/                    # Methodology PDFs
├── rating_reports/                   # Bank-specific rating reports (PDF)
├── credit_reports/                   # GOLD — analyst credit papers (DOCX)
├── raw_data/eba/                     # EBA transparency CSV files
│
├── processed/
│   ├── financials/                   # Extracted JSON per filing
│   ├── rating_agency/                # Chunked JSON per methodology doc
│   ├── credit_reports/               # Extracted JSON per credit paper
│   ├── benchmark_index.json          # Percentile/decile index (all metrics)
│   └── benchmark_summary.json        # Human-readable benchmark summary
│
├── training_data/
│   ├── combined_training.jsonl           # Main training set (all sources)
│   ├── combined_eval.jsonl               # Eval set (10%)
│   ├── combined_training_upgraded.jsonl  # Analyst-quality upgraded version
│   ├── combined_eval_upgraded.jsonl      # Upgraded eval set
│   ├── financial_pairs.jsonl             # Financial statement pairs
│   ├── rating_agency_pairs.jsonl         # Rating agency pairs
│   ├── eba_pairs.jsonl                   # EBA transparency pairs
│   └── fdic_pairs.jsonl                  # FDIC Call Report pairs
│
├── models/
│   ├── qwen2.5-7b-camels-adapter/        # LoRA adapter (safetensors)
│   ├── qwen2.5-7b-camels-fused/          # Fused model
│   └── qwen2.5-7b-camels-4bit/           # 4-bit quantised
│
├── benchmark.py                      # Benchmark utility (decile lookups)
├── main.py                           # Inference pipeline
├── run.sh                            # Main entry point
├── setup.sh                          # One-time environment setup
├── train_mlx.sh                      # QLoRA training (Apple Silicon)
├── train_unsloth.py                  # QLoRA training (Linux/CUDA)
├── fuse_and_deploy.sh                # Post-training fuse + deploy
├── serve_mlx.sh                      # MLX direct server (Ollama fallback)
├── prepare_for_training.sh           # Close apps, purge RAM, prevent sleep
├── colab_training.ipynb              # Google Colab training notebook
├── check_mlx_api.py                  # MLX version diagnostic
├── fdic_debug.py                     # FDIC API diagnostic (dev tool)
├── Modelfile                         # Ollama model definition
└── requirements_ingestion.txt        # All Python dependencies
```

---

## Architecture

```
Source Documents
────────────────────────────────────────────────────────
Annual Reports   Pillar 3   Rating Agency   Credit Papers
(PDF/HTM)        (PDF)      (PDF)           (DOCX/GOLD)
     │               │           │               │
     └───────────────┴───────────┴───────────────┘
                         │
                    [01 Triage]
                         │
          ┌──────────────┼──────────────────┐
          ▼              ▼                  ▼
  [02 Extract      [03 Extract RA    [06 Extract
   Financials]      + Reports]        Credit Papers]
          │              │                  │
          └──────────────┴──────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
    [parse_eba_km.py]    [download_fdic_data.py]
    (156 EU banks)       (100 US banks)
              │                     │
              └──────────┬──────────┘
                         ▼
            [build_benchmark_index.py]
            (decile thresholds, all metrics)
                         │
                         ▼
            [04 Build Training Pairs]
            (5 pipelines, ~3,800 pairs)
                         │
                         ▼
            [05 Upgrade Quality]
            (Claude Haiku, ~$5, resumable)
                         │
                         ▼
            [train_mlx.sh / colab_training.ipynb]
            (QLoRA, auto-detects hardware)
                         │
                         ▼
            [serve_mlx.sh / Ollama]
            (local inference, port 8080)
                         │
                         ▼
                    [main.py]
            PDF → CAMELS paper + benchmark
                  table + audit index
```

---

## Quick Start

### macOS (Apple Silicon)

```bash
# 1. Prerequisites (one-time)
brew install poppler tesseract git-lfs ollama
git clone https://github.com/bruceschultz/llm_credit_paper.git
cd llm_credit_paper
chmod +x *.sh
./setup.sh

# 2. Download data
./run.sh --download-us --years 10        # US 10-K filings (automated)
./run.sh --download-uk --years 5         # UK/EU/AU annual reports
./run.sh --download-ra                   # Regulatory methodology docs
./run.sh --download-pillar3              # Pillar 3 reports (where available)

# FDIC Call Report data (requires free API key)
# Get key: https://api.fdic.gov/banks/docs → Request API Key
export FDIC_API_KEY=your_key_here
./run.sh --download-fdic

# EBA data — manual download required (EDAP portal)
# See DATA_SOURCES.md for instructions
# Save CSV to raw_data/eba/ then:
.venv/bin/python scripts/parse_eba_km.py

# 3. Build benchmark index
.venv/bin/python scripts/build_benchmark_index.py --include-fdic --include-eba

# 4. Build training pairs
./run.sh --reprocess

# 5. Upgrade training quality (~$5 one-time)
# Get API key: console.anthropic.com (separate from Claude Pro)
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python scripts/05_upgrade_training_pairs.py

# 6. Train
sudo purge
./prepare_for_training.sh
./train_mlx.sh

# 7. Deploy
./fuse_and_deploy.sh
ollama serve              # separate terminal
# OR if GGUF conversion fails:
./serve_mlx.sh            # MLX direct server, port 8080

# 8. Run analysis
python main.py \
  --pdf financials/2025-lbg-annual-report.pdf \
  --bank "Lloyds Banking Group"
```

### Google Colab (recommended for higher quality)

```bash
# Upload these two files to Colab:
#   training_data/combined_training_upgraded.jsonl
#   training_data/combined_eval_upgraded.jsonl
#   colab_training.ipynb
#
# colab.research.google.com
# Runtime → T4 GPU (free) or A100 (Colab Pro)
# Run all cells → downloads adapter zip automatically
# Extract to models/ → ollama create camels-analyst-7b -f ./Modelfile
```

---

## Benchmark Index

The benchmark index is built from all processed financial data and provides
population-level percentile context for every metric in every analysis.

**Build:**
```bash
.venv/bin/python scripts/build_benchmark_index.py
.venv/bin/python scripts/build_benchmark_index.py --include-fdic --include-eba
```

**Test:**
```bash
.venv/bin/python benchmark.py
```

**Sample output:**
```
Lloyds CET1 12.6% (UK)
  Decile: 6/10 globally | Percentile: 54th
  6th decile globally — above median
  Global median: 12.1% | p10: 9.8% | p90: 16.4% | n=847 bank-years
  4th decile vs UK peers | UK median: 14.2% | n=52
```

**In every generated credit paper:**

| Metric | Value | Global Decile | Median | p10–p90 | Region |
|--------|-------|---------------|--------|---------|--------|
| CET1 Ratio | 12.6% [p.42] | **6th** | 12.1% | 9.8–16.4% | 4th (UK) |
| LCR | 145% [p.87] | **7th** | 138% | 105–210% | 5th (UK) |
| NIM | 2.3% [p.31] | **5th** | 2.1% | 1.2–3.8% | 6th (UK) |

---

## Training Data Quality Tiers

| Quality | Source | Weight | Count |
|---------|--------|--------|-------|
| `gold` | `credit_reports/` DOCX | 2× | 0 (add yours) |
| `structured` | EBA transparency, FDIC | 1× | ~1,863 |
| `extracted` | Rating agency PDFs | 1× | ~884 |
| `upgraded` | Financial statements (analyst prose) | 1× | ~854 |

Add real analyst credit papers to `credit_reports/` and re-run for gold-standard training.

---

## Source Folders

| Folder | Contents | How to populate |
|--------|----------|----------------|
| `financials/` | Annual reports PDF/HTM | `./run.sh --download-us --download-uk` |
| `pillar3/` | Pillar 3 risk disclosures | `./run.sh --download-pillar3` |
| `rating_agency/` | Methodology PDFs | `./run.sh --download-ra` |
| `rating_reports/` | Bank rating reports | Manual — Fitch/S&P/Moody's IR pages |
| `credit_reports/` | Your credit papers (DOCX) | Manual — your own analyst work |
| `raw_data/eba/` | EBA transparency CSV | Manual — EDAP portal |

All folders auto-created. Empty folders silently skipped.

---

## Post-Training Deployment

```bash
# Fuse + quantise + create Ollama model
./fuse_and_deploy.sh

# Start server (keep open)
ollama serve

# Test
ollama run camels-analyst-7b \
  "Analyse capital adequacy: CET1 13.5%, minimum 11.0%, leverage 5.2%"

# Full analysis
python main.py \
  --pdf financials/lloyds_2025.pdf \
  --bank "Lloyds Banking Group"
```

**If GGUF conversion fails** (U32 data type — known MLX/Ollama issue):
```bash
./serve_mlx.sh   # OpenAI-compatible API on port 8080
```

**Iterative quality improvement:**

| Round | Platform | Seq Length | Time | Quality |
|-------|----------|-----------|------|---------|
| 1 ✅ done | Mac 16GB | 512 | ~30 min | Baseline |
| 2 | Colab T4 (free) | 2,048 | ~60 min | Good |
| 3 | Colab Pro A100 | 4,096 | ~15 min | Excellent |
| 4 | + DOCX gold pairs | 4,096 | ~15 min | Best |

---

## EBA Data — Manual Download

EBA moved all data to their EDAP portal — no direct download URL available.

1. Go to `https://www.eba.europa.eu/eu-wide-transparency-exercise-0`
2. Select a year → find **"Key Metrics"** CSV download
3. Save to `raw_data/eba/` (any `.csv` filename)
4. Run: `.venv/bin/python scripts/parse_eba_km.py`

The parser auto-detects any CSV in `raw_data/eba/` and handles the EBA long-format
structure (one row per bank × metric × period).

---

## FDIC Data — API Key Required

The FDIC BankFind API now requires a free API key:

1. Go to `https://api.fdic.gov/banks/docs`
2. Click **"Request API Key"** — arrives by email instantly
3. `export FDIC_API_KEY=your_key_here`
4. `./run.sh --download-fdic`

---

## Anti-Hallucination Controls

1. **Grounded prompting** — LLM receives only data extracted from source document
2. **Citation enforcement** — every number requires `[Source: p.XX]`
3. **Post-generation validation** — output figures cross-checked against source
4. **Temperature 0.05** — near-deterministic factual outputs
5. **Refusal training** — "Data not available" not fabrication
6. **Audit index** — JSON maps every cited figure to source page
7. **Benchmark grounding** — percentile context from real population data

---

## Regulatory Framework

**Capital (Basel III/IV, PRA):** Pillar 1 (4.5% CET1), CCB (2.5%), CCyB,
G-SII/O-SII, Pillar 2A, UK leverage (3.25%), Basel IV output floor (72.5% by 2030).

**Asset Quality (IFRS 9):** Stage 1 (12m ECL), Stage 2 (Lifetime/SICR),
Stage 3 (Lifetime/impaired).

**Liquidity:** LCR ≥100%, NSFR ≥100%.

**Rating agencies:** Moody's BCA, S&P SACP/BICRA, Fitch VR/IDR, DBRS IA.

---

## Known Issues and Fixes

| Issue | Fix |
|-------|-----|
| `permission denied` on shell scripts | `chmod +x *.sh` |
| Training OOM (Metal GPU) | `sudo purge` + `./prepare_for_training.sh`; or Colab |
| mlx-lm argument errors | `python check_mlx_api.py` to diagnose |
| GGUF U32 conversion error | Use `./serve_mlx.sh` instead of Ollama |
| Zero training pairs after filter | Latest `train_mlx.sh` truncates not skips |
| HuggingFace 401 error | `.venv/bin/python -c "from huggingface_hub import login; login()"` |
| EBA download 404 | Manual download from EDAP — see above |
| FDIC API 403 error | Set `FDIC_API_KEY` — free from `api.fdic.gov/banks/docs` |
| Analyses too short | Re-train on Colab with `max_seq_length: 4096` |

---

## Dependencies

All Python dependencies install automatically via `./setup.sh`.

**System packages (one-time):**
```bash
brew install poppler tesseract ollama git-lfs
```

**Free API keys needed:**
- HuggingFace: `huggingface.co/settings/tokens` (model download)
- FDIC: `api.fdic.gov/banks/docs` (Call Report data)
- Anthropic API: `console.anthropic.com` (training pair upgrade, ~$5 one-time)

---

## Linux / CUDA Training

```bash
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install --no-deps trl peft accelerate bitsandbytes datasets
python train_unsloth.py   # auto-detects VRAM, selects 7B or 14B
```

---

## Citation

```bibtex
@software{camels_credit_analysis_2025,
  author  = {Schultz, Bruce},
  title   = {CAMELS Credit Analysis System},
  year    = {2025},
  url     = {https://github.com/bruceschultz/llm_credit_paper},
  license = {Apache-2.0}
}
```

---

## Disclaimer

For research and internal analytical use only. Generated analyses do not constitute
investment advice or official credit ratings. Review by a qualified credit
professional is required before use.

---

## License

Apache 2.0 — see [LICENSE](LICENSE). Compatible with Qwen2.5 base model licence.
