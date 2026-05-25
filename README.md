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

> *CET1 ratio 14.0% — 7th decile globally (median: 13.8%, p10: 10.5%, p90: 14.2%;
> n=847 bank-years); 5th decile vs UK peers*

The system fine-tunes a local Qwen2.5 model on a domain-specific dataset built from:
- **200+ bank annual reports** (SEC EDGAR 10-K filings + UK/EU PDFs, 2015–2025)
- **EBA EU-wide Transparency Exercise** (156 EU/EEA banks, 2019–2025)
- **FDIC Call Report API** (top 100 US banks, annual data, 5 years)
- **Rating agency methodology** (Fitch, S&P, DBRS Morningstar)
- **Regulatory guidance** (Basel III/IV, OCC, FDIC, EBA SREP, PRA)
- **Pillar 3 risk disclosures** (granular RWA, IRB model outputs, LCR composition)

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
| Domain fine-tuning | Trained on 3,800+ CAMELS pairs | Generic |
| Audit trail | JSON audit index per analysis | None |
| Pillar 3 integration | RWA, IRB models, LCR detail | None |

---

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Data pipeline | ✅ Complete | 5 sources, 3,832 pairs |
| Training pair upgrade | ✅ Complete | Claude Haiku, ~$5, resumable |
| Round 1 training (Mac) | ✅ Complete | 512 tokens, val loss 3.14→1.07 |
| Round 2 training (Colab) | 🔄 In progress | 1,024 tokens, T4 GPU |
| Benchmark index | ✅ Complete | Decile rankings for all metrics |
| End-to-end analysis | ✅ Tested | Lloyds 2025 + Pillar 3 |
| GitHub | ✅ Published | github.com/1697-20747/llm_credit_paper |

---

## Hardware Support

| Platform | RAM | Model | Training Time | Status |
|----------|-----|-------|--------------|--------|
| macOS Apple Silicon (M1/M2/M3) | 16GB | Qwen2.5-7B (4-bit) | ~15–30 min | ✅ Supported |
| macOS Apple Silicon (M2 Pro/M3 Pro) | 32GB | Qwen2.5-14B | ~8–12 hours | ✅ Recommended |
| macOS Apple Silicon (M2 Max/M3 Max) | 64GB | Qwen2.5-14B | ~5–8 hours | ✅ Optimal |
| Linux + NVIDIA GPU (16GB VRAM) | Any | Qwen2.5-7B | ~2–4 hours | ✅ Supported |
| Linux + NVIDIA GPU (24GB+ VRAM) | Any | Qwen2.5-14B | ~3–6 hours | ✅ Supported |
| Google Colab (free T4, 15.6GB VRAM) | Any | Qwen2.5-7B | ~60 minutes | ✅ Supported |
| Google Colab Pro (A100, 40GB VRAM) | Any | Qwen2.5-14B | ~15 minutes | ✅ Fastest |

> **16GB Mac note:** Training completes in ~15–30 minutes using the pre-quantised
> 4-bit base model (`mlx-community/Qwen2.5-7B-Instruct-4bit`, ~4GB). Peak memory
> stable at ~5.7GB. Sequence length limited to 512 tokens on 16GB.
> Use Colab for 1,024+ token training.

> **Colab T4 note:** 15.6GB VRAM supports 1,024 token sequence length with
> Qwen2.5-7B using Unsloth 4-bit quantisation. Use 2,048 tokens on Colab Pro A100.

---

## Training — Sequence Length and Quality

| Tokens | Platform | Quality | Notes |
|--------|----------|---------|-------|
| 512 | Mac 16GB | Baseline | Round 1 — fast, shorter analyses |
| 1,024 | Colab T4 (free) | Good | Round 2 — full sections, ~60 min |
| 2,048 | Colab Pro A100 | Very good | Recommended production minimum |
| 4,096 | 64GB Mac / A100 | Excellent | Full annual report sections |
| 8,192 | H100 80GB | Optimal | No truncation at all |

**Optimal unconstrained config (A100/H100):**
```yaml
model:          Qwen/Qwen2.5-14B-Instruct
max_seq_length: 8192
lora_rank:      32
lora_alpha:     64
num_layers:     32
```

---

## Training Dataset

| Source | Type | Coverage | Pairs |
|--------|------|----------|-------|
| US bank 10-K filings (SEC EDGAR) | HTM | ~90 filings, 2015–2025 | ~810 |
| UK/EU bank annual reports | PDF | ~14 filings, 2020–2025 | ~126 |
| EBA Transparency Exercise | CSV | 156 EU banks, 2019–2025 | ~1,463 |
| FDIC Call Report API | REST | 100 US banks, 5 years | ~492 |
| Fitch Bank Rating Criteria (OCR) | PDF | Scanned, 65 pages | ~58 |
| S&P Global Banks Rating Criteria | PDF | Full methodology | ~85 |
| DBRS Morningstar Methodology | PDF | Full methodology | ~25 |
| Basel Committee standards (BIS) | PDF | 7 documents | ~500 |
| OCC Comptroller's Handbook | PDF | 4 volumes | ~215 |
| FDIC CAMELS manual | PDF | Original definition | ~27 |
| EBA SREP guidelines | PDF | EU framework | ~36 |
| PRA supervisory approach | PDF | UK framework | ~23 |
| BIS working papers | PDF | 2 papers | ~52 |
| **Total** | | | **~3,832** |

All 854 financial statement pairs upgraded to analyst-quality prose via Claude Haiku (~$5).

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
│   ├── download_financials.py        # SEC EDGAR automated downloader
│   ├── download_uk_banks.py          # UK/EU/AU bank downloader
│   ├── download_rating_agency.py     # Regulatory doc downloader
│   ├── download_pillar3.py           # Pillar 3 report downloader
│   ├── download_eba_data.py          # EBA transparency downloader
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
│   ├── benchmark_index.json          # Percentile/decile index
│   └── benchmark_summary.json        # Human-readable benchmark summary
│
├── training_data/
│   ├── combined_training_upgraded.jsonl  # Main training set (3,449 pairs)
│   ├── combined_eval_upgraded.jsonl      # Eval set (383 pairs)
│   ├── financial_pairs_upgraded.jsonl    # Analyst-quality financial pairs
│   ├── rating_agency_pairs.jsonl         # Rating agency pairs
│   ├── eba_pairs.jsonl                   # EBA transparency pairs
│   └── fdic_pairs.jsonl                  # FDIC Call Report pairs
│
├── models/
│   ├── qwen2.5-7b-camels-adapter/        # LoRA adapter (round 1+2)
│   ├── qwen2.5-7b-camels-fused/          # Fused model
│   └── qwen2.5-7b-camels-4bit/           # 4-bit quantised
│
├── output/                           # Generated credit papers
├── benchmark.py                      # Benchmark utility (decile lookups)
├── test_analysis.py                  # Standalone analysis script
├── main.py                           # Full inference pipeline
├── run.sh                            # Main entry point
├── setup.sh                          # One-time environment setup
├── train_mlx.sh                      # QLoRA training (Apple Silicon)
├── train_unsloth.py                  # QLoRA training (Linux/CUDA)
├── fuse_and_deploy.sh                # Post-training fuse + deploy
├── serve_mlx.sh                      # MLX direct server (Ollama fallback)
├── prepare_for_training.sh           # Close apps, purge RAM, prevent sleep
├── colab_training.ipynb              # Google Colab training notebook
├── check_mlx_api.py                  # MLX version diagnostic
├── fdic_debug.py                     # FDIC API diagnostic
├── Modelfile                         # Ollama model definition
└── requirements_ingestion.txt        # All Python dependencies
```

---

## Quick Start

### macOS (Apple Silicon)

```bash
# 1. Prerequisites
brew install poppler tesseract git-lfs ollama
git clone https://github.com/1697-20747/llm_credit_paper.git
cd llm_credit_paper
chmod +x *.sh
./setup.sh

# 2. Download data
./run.sh --download-us --years 10
./run.sh --download-uk --years 5
./run.sh --download-ra
./run.sh --download-pillar3

# FDIC (free API key required)
# Get key: https://api.fdic.gov/banks/docs
export FDIC_API_KEY=your_key_here
./run.sh --download-fdic

# EBA (manual download — EDAP portal)
# Save CSV to raw_data/eba/ then:
.venv/bin/python scripts/parse_eba_km.py

# 3. Build benchmark + training pairs
.venv/bin/python scripts/build_benchmark_index.py --include-fdic --include-eba
./run.sh --reprocess

# 4. Upgrade quality (~$5 one-time)
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python scripts/05_upgrade_training_pairs.py

# 5. Train on Mac (16GB — baseline quality)
sudo purge
./prepare_for_training.sh
./train_mlx.sh

# OR train on Colab (recommended — better quality)
# Upload training_data/combined_training_upgraded.jsonl to colab_training.ipynb

# 6. Deploy
./fuse_and_deploy.sh
ollama serve   # separate terminal

# 7. Run analysis
.venv/bin/python3 test_analysis.py \
  --pdf financials/2025-lbg-annual-report.pdf \
  --pillar3 pillar3/2025-lbg-fy-pillar-3.pdf \
  --bank "Lloyds Banking Group" \
  --model camels-base
```

---

## Running an Analysis

The `test_analysis.py` script handles the full pipeline — extraction, benchmarking,
LLM analysis, and report assembly:

```bash
# Start Ollama (if not already running)
ollama serve &

# Lloyds with Pillar 3
.venv/bin/python3 test_analysis.py \
  --pdf financials/2025-lbg-annual-report.pdf \
  --pillar3 pillar3/2025-lbg-fy-pillar-3.pdf \
  --bank "Lloyds Banking Group" \
  --model camels-base

# US bank (HTM filing)
.venv/bin/python3 test_analysis.py \
  --pdf financials/jpmorgan_chase_2025_10k.htm \
  --bank "JPMorgan Chase" \
  --model camels-base
```

**Output files (in `output/`):**
- `*_credit_paper.md` — full CAMELS credit paper with benchmark table
- `*_audit.json` — extracted metrics, source pages, sections found

---

## Benchmark Index

Built from all processed financial data — provides population-level percentile
context for every metric in every analysis.

```bash
# Build
.venv/bin/python scripts/build_benchmark_index.py --include-fdic --include-eba

# Test
.venv/bin/python benchmark.py
```

**Sample analysis output:**

| Metric | Value | Global Decile | Median | p10–p90 |
|--------|-------|---------------|--------|---------|
| CET1 Ratio | 14.0% [p.53] | **7th** | 13.8% | 10.5–14.2% |
| Leverage Ratio | 5.4% [p.53] | **5th** | 5.5% | 5.1–9.3% |
| LCR | 145% [p.183] | **4th** | 165% | 150–171% |

---

## Google Colab Training

Recommended for higher quality training than 16GB Mac allows.

**Files to upload from your Mac:**
```
training_data/combined_training_upgraded.jsonl  (20MB)
training_data/combined_eval_upgraded.jsonl      (2.3MB)
colab_training.ipynb
```

**Steps:**
1. `colab.research.google.com` → Upload `colab_training.ipynb`
2. Runtime → Change runtime type → **T4 GPU** (free)
3. Run all cells — Cell 3 prompts for JSONL file upload
4. Cell 7 downloads trained adapter zip automatically
5. Extract zip to `models/` on your Mac

**Sequence length by runtime:**

| Runtime | Max Seq Length | Training Time | Quality |
|---------|---------------|--------------|---------|
| Free T4 (15.6GB) | 1,024 | ~60 min | Good |
| Colab Pro A100 (40GB) | 2,048–4,096 | ~15 min | Excellent |

> **Note:** T4 OOMs at 2,048 tokens with this dataset size. Use 1,024 tokens
> on free T4. Upgrade to Colab Pro A100 for 2,048+ tokens.

---

## Training Quality Roadmap

| Round | Platform | Tokens | Pairs | Val Loss | Status |
|-------|----------|--------|-------|----------|--------|
| 1 | Mac 16GB (MLX) | 512 | 1,737 | 3.14 → 1.30 | ✅ Done |
| 1b | Mac 16GB (MLX) | 512 | 3,832 | 2.53 → 1.07 | ✅ Done |
| 2 | Colab T4 | 1,024 | 3,832 | TBD | 🔄 Running |
| 3 | Colab Pro A100 | 4,096 | 3,832+ | TBD | Planned |
| 4 | Any | 4,096 | +DOCX gold | TBD | Planned |

Adding real analyst credit papers (DOCX) to `credit_reports/` and re-running
`./run.sh --reprocess` will add gold-standard pairs for the highest quality round.

---

## Source Folders

| Folder | Contents | How to populate |
|--------|----------|----------------|
| `financials/` | Annual reports PDF/HTM | `./run.sh --download-us --download-uk` |
| `pillar3/` | Pillar 3 risk disclosures | `./run.sh --download-pillar3` or manual |
| `rating_agency/` | Methodology PDFs | `./run.sh --download-ra` |
| `rating_reports/` | Bank rating reports | Manual — Fitch/S&P/Moody's IR pages |
| `credit_reports/` | Your credit papers (DOCX) | Manual — highest quality training data |
| `raw_data/eba/` | EBA transparency CSV | Manual — EDAP portal |

---

## Anti-Hallucination Controls

1. **Grounded prompting** — LLM only sees data extracted from source document
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
| Training OOM on 16GB Mac | `sudo purge` + `./prepare_for_training.sh`; or use Colab |
| Colab T4 OOM at 2,048 tokens | Reduce to 1,024 tokens in Cell 1 |
| mlx-lm argument errors | `python check_mlx_api.py` to diagnose |
| GGUF U32 conversion error | Use `./serve_mlx.sh` instead of Ollama |
| MLX server crashes 16GB Mac | Use Ollama (`ollama serve`) for inference instead |
| HuggingFace 401 | `.venv/bin/python -c "from huggingface_hub import login; login()"` |
| EBA download 404 | Manual download from EDAP portal |
| FDIC API 403 | Set `FDIC_API_KEY` — free from `api.fdic.gov/banks/docs` |
| `python` not found on Mac | Use `.venv/bin/python3` instead |
| `fitz` module not found | Use `.venv/bin/python3` (not system python3) |

---

## Free API Keys Required

| Service | Purpose | URL |
|---------|---------|-----|
| HuggingFace | Model download | `huggingface.co/settings/tokens` |
| FDIC BankFind | Call Report data | `api.fdic.gov/banks/docs` |
| Anthropic API | Training pair upgrade (~$5 one-time) | `console.anthropic.com` |

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
  url     = {https://github.com/1697-20747/llm_credit_paper},
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
