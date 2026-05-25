# Results

> **Status: In Progress**
> This document will be updated with evaluation results after training completes.

---

## Training Configuration

| Parameter | Value |
|-----------|-------|
| Base model | Qwen2.5-14B-Instruct |
| Fine-tuning method | QLoRA (MLX) |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| Training pairs | 1,564 (train) + 173 (eval) |
| Training pairs (upgraded) | 854 analyst-quality + 883 extracted |
| Max sequence length | 4,096 tokens |
| Learning rate | 2e-5 |
| Effective batch size | 16 |
| Gradient checkpointing | Yes |
| Platform | Apple Silicon (MLX) |

---

## Dataset Statistics

| Metric | Value |
|--------|-------|
| Total documents processed | 123 |
| Financial statement filings | 104 |
| Rating agency / regulatory docs | 19 |
| Total training pairs | 1,737 |
| Training set | 1,564 (90%) |
| Eval set | 173 (10%) |
| Template quality pairs | 854 → upgraded via Claude Haiku |
| Extracted quality pairs | 883 |
| Banks covered | 34 |
| Countries covered | US, UK, EU, Australia |
| Years covered | 2015–2025 |

---

## Evaluation Results

*To be completed after training.*

### Citation Compliance
- % of numerical claims with `[Source: p.XX]` citations: TBD
- % of cited figures matching source data: TBD

### Structure Compliance
- % of outputs with correct CAMELS structure: TBD
- % of outputs beginning with Assessment rating: TBD

### Assessment Distribution
| Rating | % of outputs |
|--------|-------------|
| Strong | TBD |
| Adequate | TBD |
| Weak | TBD |
| Critical | TBD |

### Hallucination Rate
- % of outputs with unverified figures: TBD
- % of outputs with fabricated page citations: TBD

---

## Sample Outputs

*To be added after training and evaluation.*

### Capital Adequacy — Lloyds Banking Group 2024

*Sample output to be inserted here.*

### Asset Quality — JPMorgan Chase 2024

*Sample output to be inserted here.*

### Overall CAMELS Assessment — Barclays 2023

*Sample output to be inserted here.*

---

## Comparison: Base Model vs Fine-tuned Model

*Side-by-side comparison to be added after training.*

| Criterion | Base Qwen2.5-14B | Fine-tuned |
|-----------|-----------------|------------|
| Citation rate | TBD | TBD |
| CAMELS structure compliance | TBD | TBD |
| Regulatory threshold accuracy | TBD | TBD |
| Hallucination rate | TBD | TBD |
| Refusal on missing data | TBD | TBD |

---

## Limitations

- Training data is predominantly US and UK banks — model may perform
  less accurately on continental European and emerging market banks
- Financial data extracted via regex patterns — complex table layouts
  may result in missed metrics requiring manual review
- OCR quality varies for scanned PDFs — Fitch methodology document
  contains some character-level noise from OCR processing
- Template-to-analyst quality upgrade uses Claude Haiku for cost
  efficiency — higher quality possible with Sonnet-class models
- Model knowledge cutoff: training data through 2025 annual reports

---

## Roadmap

- [ ] Complete training run (Q2 2025)
- [ ] Publish evaluation results
- [ ] Add HSBC, NatWest, Standard Chartered filings
- [ ] Add Moody's methodology once access obtained
- [ ] Build Parquet metrics index for public release
- [ ] Add support for interim/half-year reports
- [ ] Extend to insurance company analysis (CAMELS equivalent)
- [ ] Web interface for non-technical users
