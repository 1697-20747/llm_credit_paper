# CAMELS Credit Analysis System — Full Project Architecture

## Executive Summary

A fully offline, Mac-native pipeline that:
1. Ingests a bank's annual report PDF
2. Extracts structured text, tables and financial data
3. Runs a locally post-trained Qwen2.5-14B model (fine-tuned on credit/CAMELS domain data)
4. Produces a structured, auditable credit paper with source citations

---

## System Architecture Overview

```
[Annual Report PDF]
        │
        ▼
[Stage 1: PDF Ingestion & Extraction]
  - pdfplumber / pymupdf (tables)
  - pdfminer.six (text flow)
  - camelot-py (complex tables)
  - Outputs: structured JSON + markdown
        │
        ▼
[Stage 2: Financial Data Parser]
  - Regex + heuristic column mapper
  - Maps to CAMELS taxonomy
  - Outputs: camels_data.json (auditable, line-referenced)
        │
        ▼
[Stage 3: Local LLM Inference]
  - Qwen2.5-14B-Instruct (post-trained)
  - Served via Ollama or llama.cpp HTTP server
  - Structured prompt → structured JSON credit paper
        │
        ▼
[Stage 4: Report Assembly]
  - Jinja2 templates → Markdown → DOCX/PDF
  - Every claim tagged with source page/table
  - Auditable citation index appended
```

---

## Stage Breakdown

### Stage 1 — PDF Ingestion

**Tools:**
- `pymupdf` (fitz): fastest, best for text blocks and page geometry
- `pdfplumber`: best for table detection with bounding boxes
- `camelot-py`: fallback for lattice/stream tables in financials
- `pytesseract` + `pdf2image`: OCR fallback for scanned pages

**Output per document:**
```json
{
  "pages": [
    {
      "page_num": 12,
      "text": "...",
      "tables": [
        {
          "caption": "Consolidated Balance Sheet",
          "data": [["Item","2024","2023"], ["Total Assets","876,402","875,123"]],
          "bbox": [72, 120, 540, 480]
        }
      ]
    }
  ]
}
```

---

### Stage 2 — CAMELS Data Extraction

Maps raw extracted data to the six CAMELS pillars:

| Pillar | Key Metrics Extracted |
|--------|----------------------|
| **C** Capital Adequacy | CET1 ratio, Tier 1 ratio, Total Capital ratio, RWA, leverage ratio, MREL |
| **A** Asset Quality | NPL ratio, Stage 1/2/3 loans (IFRS 9), coverage ratio, impairment charges, write-offs |
| **M** Management | Exec remuneration, governance disclosures, board composition, risk committee, audit findings |
| **E** Earnings | NII, NIM, ROE, ROA, cost:income ratio, pre-tax profit, EPS, DPS |
| **L** Liquidity | LCR, NSFR, LDR, liquidity pool, HQLA, funding mix, wholesale vs retail |
| **S** Sensitivity | Duration gap, market risk VaR, interest rate sensitivity, FX exposure, stress test results |

---

### Stage 3 — Model Selection & Post-Training

#### Base Model: Qwen2.5-14B-Instruct

**Why Qwen2.5-14B:**
- 14B params — fits in 16GB unified memory (M2/M3 Mac) with 4-bit quantisation
- Strong instruction following
- Apache 2.0 licence (commercial-safe)
- Outperforms LLaMA-3-8B on structured reasoning benchmarks
- Quantised GGUF available for llama.cpp / Ollama

**Quantisation target:** Q4_K_M (best quality/size tradeoff, ~8GB VRAM)

#### Post-Training Method: QLoRA (Quantised LoRA)

- Fine-tune only adapter weights (~1-3% of parameters)
- 4-bit base model + 16-bit LoRA adapters
- Runs on a Mac M2/M3 with 32GB unified memory using `mlx-lm` (Apple's MLX framework — native Metal acceleration)
- No GPU required; MLX is purpose-built for Apple Silicon

**Preferred training stack (Mac-native):**
```
apple/ml-foundation → mlx-lm (QLoRA on Apple Silicon)
OR
unsloth (if running on a separate Linux/CUDA box)
```

---

### Training Data Requirements

#### Minimum viable: ~500–2,000 high-quality instruction pairs
#### Recommended: 5,000–15,000 pairs for robust domain shift

#### Data Categories Needed

**1. CAMELS Framework Instruction Pairs (500–1,000 examples)**
- Format: `{instruction, input (financial data), output (analysis paragraph)}`
- Source: Write synthetic examples from public bank annual reports + CAMELS templates

**2. Rating Agency Methodology Text (1,000–3,000 examples)**
- Moody's, S&P, Fitch bank rating methodologies (publicly available PDFs)
- Convert to Q&A format: "Given CET1 of 13.5% and NPL of 2.1%, what does Moody's methodology suggest?"
- Sources:
  - Moody's "Banks" methodology (free PDF on moodys.com)
  - S&P "Banks: Rating Methodology" (available on spglobal.com)
  - Fitch "Bank Rating Criteria" (fitchratings.com — free registration)
  - Basel Committee papers (bis.org — fully public)
  - ECB supervisory guidance (bankingsupervision.europa.eu)
  - PRA/FCA supervisory statements (bankofengland.co.uk)

**3. Financial Statement Analysis Examples (2,000–5,000 examples)**
- Real bank annual reports (public companies) → analyst-style commentary
- Sources:
  - SEC EDGAR (US banks — 10-K filings, fully public): `efts.sec.gov/LATEST/search-index`
  - Bank of England statistical releases (public)
  - EBA transparency exercises (eba.europa.eu — Excel data packs, free)
  - Annual reports: HSBC, Barclays, NatWest, Standard Chartered, Lloyds (all public PDFs)

**4. Credit Research Reports (1,000–3,000 examples)**
- Sell-side credit research is gated, but:
  - University library access (Bloomberg Terminal academic, Refinitiv Eikon academic)
  - Open-access credit research: BIS working papers, IMF working papers, World Bank
  - Synthetic generation: take real financials + write structured analysis manually for 200–500 examples, then use GPT-4 (online, one-time) to generate the rest as synthetic training data

**5. Negative Examples / Refusal Training (200–500 examples)**
- Cases where data is missing → model should say "insufficient data" not hallucinate
- Contradictory data → model flags inconsistency

---

### Data Format (JSONL — standard fine-tuning format)

```jsonl
{"messages": [
  {"role": "system", "content": "You are a senior credit analyst specialising in bank credit analysis using the CAMELS framework. All statements must be supported by specific financial data. If data is unavailable, state this explicitly. Never fabricate numbers."},
  {"role": "user", "content": "Analyse the Capital Adequacy of a bank with the following data:\nCET1 ratio: 13.8%\nTier 1 ratio: 16.2%\nTotal Capital ratio: 19.1%\nRWA: £210.4bn\nLeverage ratio: 5.4%\nRegulatory minimum CET1: 11.0% (including buffers)"},
  {"role": "assistant", "content": "## Capital Adequacy (CAMELS — C)\n\n**Assessment: STRONG**\n\nThe bank maintains a CET1 ratio of 13.8%, representing a 280bps headroom above its regulatory minimum of 11.0% (inclusive of capital conservation buffer, countercyclical buffer, and systemic risk buffer). This positions the bank comfortably within what S&P would classify as 'adequate' to 'strong' capitalisation for a systemically important institution.\n\nThe leverage ratio of 5.4% exceeds the PRA's minimum requirement of 3.25% for major UK banks, providing an additional non-risk-weighted capital buffer. Total Risk-Weighted Assets of £210.4bn underpin the Tier 1 ratio of 16.2%.\n\n**Key risks:** RWA density and model risk in internal ratings-based (IRB) approach not assessable without further disclosure.\n\n**Sources:** [CET1 ratio: p.XX], [RWA: p.XX], [Leverage ratio: p.XX]"}
]}
```

---

### Stage 4 — Local Serving

**Option A (Recommended): Ollama**
```bash
ollama create camels-analyst -f Modelfile
ollama run camels-analyst
# Exposes: http://localhost:11434/api/generate
```

**Option B: llama.cpp server**
```bash
./server -m qwen2.5-14b-camels.Q4_K_M.gguf --port 8080 -c 8192
# Exposes: http://localhost:8080/completion
```

The main Python script calls these local endpoints — zero external API calls.

---

## File Structure

```
camels_project/
├── requirements.txt
├── README.md
│
├── 01_ingest/
│   ├── pdf_extractor.py        # PDF → structured JSON
│   ├── table_parser.py         # Table detection & normalisation
│   └── ocr_fallback.py         # Tesseract for scanned pages
│
├── 02_camels_mapper/
│   ├── financial_parser.py     # Maps numbers to CAMELS taxonomy
│   ├── camels_schema.py        # Pydantic models for each pillar
│   └── ratio_calculator.py     # Derive ratios if not explicit
│
├── 03_model/
│   ├── training/
│   │   ├── prepare_data.py     # Build JSONL training set
│   │   ├── train_mlx.sh        # MLX QLoRA training script (Mac)
│   │   ├── train_unsloth.sh    # Unsloth alternative (Linux/CUDA)
│   │   └── data/
│   │       ├── camels_pairs.jsonl
│   │       ├── rating_agency_qa.jsonl
│   │       └── synthetic_reports.jsonl
│   └── Modelfile               # Ollama model definition
│
├── 04_inference/
│   ├── llm_client.py           # HTTP client for local LLM
│   ├── prompt_builder.py       # CAMELS prompt templates
│   └── response_validator.py   # Hallucination checks
│
├── 05_report/
│   ├── report_assembler.py     # Combines pillar analyses
│   ├── citation_index.py       # Builds source reference table
│   ├── templates/
│   │   └── credit_paper.md.j2  # Jinja2 template
│   └── export.py               # → DOCX / PDF output
│
└── main.py                     # Orchestrator — runs full pipeline
```

---

## Anti-Hallucination Strategy

1. **Grounded prompting**: Every LLM call includes raw extracted data; model is instructed to only use provided data
2. **Citation enforcement**: System prompt requires `[Source: p.XX, Table Y]` tags on every numeric claim
3. **Post-generation validation**: `response_validator.py` checks all numbers in output exist in `camels_data.json`
4. **Confidence scoring**: Model asked to flag `LOW_CONFIDENCE` where data is ambiguous or missing
5. **Structured output**: JSON-mode responses prevent free-form hallucination
6. **Temperature = 0**: Deterministic outputs for factual sections

---

## Hardware Requirements (Mac)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 16GB unified | 32GB unified |
| Mac | M1 Pro | M2 Max / M3 Pro |
| Storage | 20GB free | 50GB free |
| Python | 3.10+ | 3.11 |

Training time estimate (MLX, M2 Max, 5k examples): ~4–8 hours

---

## Regulatory/Rating Framework References Embedded

The model is fine-tuned to reference:
- **Basel III / IV** capital adequacy thresholds
- **IFRS 9** staging definitions (ECL)
- **PRA SS** supervisory statements (UK)
- **Moody's Bank Rating Methodology**
- **S&P Global Ratings — Banks**
- **Fitch Bank Rating Criteria**
- **EBA Guidelines** on SREP
