# Results

> **Status: Complete — Round 3 training finished 25 May 2026**

---

## Training Summary

Three rounds of QLoRA fine-tuning on Apple Silicon (M2 Pro, 16GB).
Each round built on the previous adapter checkpoint.

| Round | Platform | Base Model | Pairs | Seq Len | Iters | Val Loss Start | Val Loss End |
|-------|----------|-----------|-------|---------|-------|----------------|--------------|
| 1 | Mac 16GB MLX | Qwen2.5-7B-Instruct-4bit | 1,737 | 512 | 400 | 3.140 | 1.300 |
| 2 | Mac 16GB MLX | Qwen2.5-7B-Instruct-4bit | 3,832 | 512 | 400 | 2.530 | 1.070 |
| 3 | Mac 16GB MLX | Qwen2.5-7B-Instruct-4bit | 3,832 | 512 | 600 | — | **0.876** |

Val loss of 0.876 represents a 72% reduction from the starting point of 3.14.
Peak GPU memory: 5.721 GB throughout all runs (stable, no OOM events in round 3).
Training speed: ~0.45–0.50 it/sec. Round 3 duration: ~22 minutes.

---

## Final Training Configuration (Round 3)

| Parameter | Value |
|-----------|-------|
| Base model | `mlx-community/Qwen2.5-7B-Instruct-4bit` |
| Fine-tuning method | QLoRA (MLX 0.31.3) |
| LoRA rank | 4 |
| LoRA alpha | 8 |
| LoRA layers | 4 (top layers only) |
| Training pairs | 3,449 (train) + 383 (eval) |
| Max sequence length | 512 tokens |
| Learning rate | 2e-5 |
| Effective batch size | 16 (batch 1 × grad accum 16) |
| Gradient checkpointing | Yes |
| Iterations | 600 |
| Checkpoint frequency | Every 50 steps |
| Platform | Apple Silicon MLX |
| Peak memory | 5.721 GB |

---

## Dataset Statistics (Final)

| Source | Files / Banks | Pairs | Quality |
|--------|--------------|-------|---------|
| US bank 10-K filings (SEC EDGAR) | ~90 HTM | ~810 | Upgraded |
| UK/EU bank annual reports | ~14 PDF | ~126 | Upgraded |
| EBA Transparency Exercise | 156 EU banks | 1,463 | Structured |
| FDIC Call Report API | 100 US banks | 492 | Structured |
| Rating agency methodology | 13 PDF | ~884 | Extracted |
| FDIC/OCC/Basel regulatory docs | 6 PDF | ~318 | Extracted |
| **Total (after dedup)** | | **3,693** | |
| Training set (90%) | | 3,324 | |
| Eval set (10%) | | 369 | |

**By pipeline:**

| Pipeline | Pairs |
|----------|-------|
| EBA Transparency Exercise | 1,463 |
| Financial statements (annual reports) | 854 |
| Rating agency / regulatory docs | 884 |
| FDIC Call Reports | 492 |
| Credit reports (gold, DOCX) | 0 — add yours to `credit_reports/` |

**By quality tier:**

| Quality | Pairs | Description |
|---------|-------|-------------|
| Structured | 1,955 | EBA + FDIC — rule-based assessments with real data |
| Extracted | 884 | Rating agency methodology — direct source content |
| Upgraded | 854 | Financial statements — Claude Haiku analyst prose |

**Geographic coverage:**

| Region | Banks | Years |
|--------|-------|-------|
| USA | ~110 (EDGAR + FDIC) | 2015–2025 |
| EU/EEA | 156 (EBA) | 2019–2025 |
| UK | ~10 | 2020–2025 |
| AU | ~4 | 2020–2025 |

---

## End-to-End Test: Lloyds Banking Group 2025

Tested on: `2025-lbg-annual-report.pdf` + `2025-lbg-fy-pillar-3.pdf`
Model: `camels-base` (base Qwen2.5-7B + CAMELS system prompt via Ollama)
Generated: 25 May 2026

### Metrics Extracted (with source page citations)

| Metric | Value | Source Page |
|--------|-------|-------------|
| CET1 Ratio | 14.0% | p.53 |
| Total Capital Ratio | 18.9% | p.146 |
| Leverage Ratio | 5.4% | p.53 |
| ROTE | 22.1% | p.105 |
| LCR | 145.0% | p.183 |
| NSFR | 124.0% | p.183 |
| Structural hedge | £244bn | p.29 (Pillar 3) |
| IAS 19 surplus | £2.6bn | p.29 (Pillar 3) |

All 8 metrics correctly extracted with accurate page references.
Pillar 3 report (133 pages) correctly contributed 2 additional metrics not in the annual report.

### Assessment Outputs

| Pillar | Assessment | Notes |
|--------|-----------|-------|
| Capital Adequacy (C) | Strong | CET1 14.0%, 250bps above minimum |
| Asset Quality (A) | Adequate | Low impairment £795m, motor finance charge flagged |
| Management (M) | Adequate | Governance structure, engagement metrics |
| Earnings (E) | Strong | ROTE 22.1%, PBT £6.7bn +12% YoY |
| Liquidity (L) | Adequate | LCR 145%, NSFR 124% |
| Sensitivity (S) | Adequate | Structural hedge £244bn, pension surplus declining |

### Benchmark Context (vs Global Bank Population)

| Metric | Value | Global Decile | Global Median |
|--------|-------|---------------|---------------|
| CET1 Ratio | 14.0% | 7th | 13.8% |
| Leverage Ratio | 5.4% | 5th | 5.5% |
| LCR | 145% | 4th | 165.5% |

### Known Limitations in Current Output

| Issue | Cause | Fix |
|-------|-------|-----|
| Fabricated peer comparisons | Refusal training truncated at 512 tokens | 2,048+ token Colab Pro training |
| Invented rating agency citations | Same root cause | 2,048+ token training |
| LCR decile incorrect (1st vs 4th) | Benchmark index sample size too small | More data in benchmark index |
| Shallow Pillar 3 integration | P3 sections not yet classified in detail | P3 section keyword tuning |

---

## Base Model vs Fine-tuned Model Comparison

Qualitative comparison on Lloyds 2025 capital adequacy section:

| Criterion | Base Model Only | Fine-tuned (Round 3) |
|-----------|----------------|---------------------|
| CAMELS structure followed | Partial | Yes |
| Assessment rating included | Inconsistent | Yes — every pillar |
| Source citations present | Rare | Yes — every figure |
| Real page numbers cited | No | Yes — extracted from document |
| Regulatory thresholds correct | Often wrong | Yes — Basel III/PRA framework |
| "Data not available" refusals | Never | Partial — improves with longer training |
| Peer comparison fabrication | Always | Partial — still occurs at 512 tokens |

---

## Evaluation Notes

**What improved significantly:**
- Citation discipline — the model reliably produces `[Source: filename, p.XX]` for all extracted metrics
- Assessment ratings — Strong/Adequate/Weak/Critical appears consistently at the top of each section
- Regulatory context — Basel III minimum thresholds, PRA requirements, IFRS 9 staging referenced correctly
- Document structure — all 6 CAMELS pillars generated in correct order with correct headings

**What still needs improvement:**
- Peer fabrication — model invents HSBC/Barclays comparisons when no peer data is in the prompt. Fixed by 2,048-token training where refusal examples are not truncated
- Rating agency citations — model generates `[Source: Moody's 2025 Report, p.13]` for non-existent sources. Same fix
- Benchmark decile accuracy — LCR decile calculation incorrect due to small benchmark sample size. Fixed by adding more banks to benchmark index

**Next training round targets:**
- Colab Pro A100, 2,048–4,096 tokens, Unsloth
- Expected: peer fabrication eliminated, rating agency citations grounded in methodology only
- Expected val loss: ~0.6–0.7

---

## Roadmap

- [x] Complete round 1 training (Mac, 512 tokens, 1,737 pairs)
- [x] Expand dataset to 3,832 pairs (EBA + FDIC added)
- [x] Complete round 2 + 3 training (Mac, 512 tokens, 3,832 pairs)
- [x] End-to-end test on Lloyds 2025 annual report + Pillar 3
- [x] Publish to GitHub
- [ ] Colab Pro training at 2,048–4,096 tokens
- [ ] Add Moody's bank rating methodology
- [ ] Add HSBC, NatWest, Standard Chartered, Deutsche Bank filings
- [ ] Resolve GGUF U32 conversion error for clean Ollama deployment
- [ ] Add real analyst credit papers to `credit_reports/` (gold standard)
- [ ] Extend benchmark index — EBA historical years 2018–2019
- [ ] Asset class generalisation — project finance pipeline
