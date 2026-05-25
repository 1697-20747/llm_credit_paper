# Methodology

## CAMELS Framework

CAMELS is the primary supervisory rating framework used by US bank regulators
(Federal Reserve, OCC, FDIC) and has been adopted internationally as the
standard structure for bank credit analysis. This system implements CAMELS
as defined in:

- FDIC Risk Management Examination Manual (Section 6.1)
- OCC Comptroller's Handbook — Bank Supervision Process
- Federal Reserve SR Letter 96-38 (RFI/C(D) rating system)

### The Six Pillars

#### C — Capital Adequacy
Assesses whether a bank holds sufficient capital to absorb unexpected losses
while continuing to operate. Key metrics:

| Metric | Regulatory Minimum (UK) | Analysis Focus |
|--------|------------------------|----------------|
| CET1 ratio | ~11% (incl. buffers) | Headroom above minimum |
| Tier 1 ratio | ~12.5% | Capital quality |
| Total Capital ratio | ~15%+ | Full capital stack |
| UK Leverage ratio | 3.25% | Non-risk-weighted backstop |
| MREL | Firm-specific (~28-35%) | Resolvability |

Basel III/IV context: The system applies Basel III capital framework thresholds
and flags Basel IV output floor implications (72.5% SA floor, phasing 2025–2030).

#### A — Asset Quality
Evaluates the credit quality of the loan book and investment portfolio.
Primary framework: IFRS 9 Expected Credit Loss (ECL) staging.

| Stage | Definition | ECL Provision |
|-------|-----------|---------------|
| Stage 1 | No significant increase in credit risk | 12-month ECL |
| Stage 2 | Significant increase in credit risk (SICR) | Lifetime ECL |
| Stage 3 | Credit-impaired (default) | Lifetime ECL |

Key metrics: Stage 3 ratio, ECL coverage ratio, cost of risk (bps),
net charge-off rate, Stage 2 migration risk.

#### M — Management Quality
Qualitative assessment of governance, risk management, and strategic execution.
Covers: board independence, CRO reporting lines, remuneration structure,
regulatory track record, audit quality, risk culture.

#### E — Earnings
Profitability sustainability and quality assessment. Key metrics:
NII, NIM, RoTE vs cost of equity, cost:income ratio (or efficiency ratio
for US banks), income diversification, EPS, DPS.

#### L — Liquidity & Funding
Funding stability and liquidity adequacy. Key metrics:

| Metric | Minimum | Analysis |
|--------|---------|---------|
| LCR | 100% | 30-day stress survival |
| NSFR | 100% | 1-year structural funding |
| Loan:Deposit ratio | n/a | Structural reliance |
| HQLA pool | n/a | Liquid asset quality |

#### S — Sensitivity to Market Risk
Exposure to interest rate, foreign exchange, and other market risks.
Key metrics: NII sensitivity to rate shifts (+/- 100bps, +/- 25bps),
FVOCI unrealised gains/losses, trading VaR, IRRBB capital requirement,
duration of equity.

---

## Rating Agency Alignment

### Moody's Bank Rating Methodology
The system is trained on Moody's BCA (Baseline Credit Assessment) framework:
- **Financial Profile:** Asset Risk, Capital, Profitability, Funding/Liquidity
- **Macro Profile:** Operating environment and country risk
- **Qualitative adjustments:** Corporate behaviour, opacity, governance

Capital scoring: TCE/RWA → aaa (>20%) → aa (15-20%) → a (10-15%) →
baa (7-10%) → ba (<7%)

### S&P Global Banks Rating Criteria
S&P SACP (Stand-Alone Credit Profile) framework:
- **BICRA:** Bank Industry and Country Risk Assessment (Economic/Industry risk)
- **Anchor:** Starting point from BICRA
- **Adjustments:** Business position, capital/earnings, risk position,
  funding/liquidity, comparable ratings analysis

Capital metric: Risk-Adjusted Capital (RAC) ratio using S&P's own risk weights.
RAC > 15% = Very Strong; 10–15% = Strong; 7–10% = Adequate; < 7% = Moderate.

### Fitch Bank Rating Criteria
Fitch Viability Rating (VR) framework:
- **Operating Environment** (10–15% weight)
- **Business Profile** (5–15% weight)
- **Financial Profile:**
  - Asset Quality (12.5–17.5%)
  - Earnings & Profitability (12.5–17.5%)
  - Capitalisation & Leverage (12.5–17.5%)
  - Funding & Liquidity (12.5–17.5%)

### DBRS Morningstar
Intrinsic Assessment (IA) framework covering franchise strength,
earnings power, risk profile, funding/liquidity, capitalisation.

---

## Anti-Hallucination Design

The primary risk in LLM-generated financial analysis is fabrication of
specific financial figures. This system addresses this through:

**1. Grounded prompting architecture**
Every LLM call includes the raw extracted financial data as context.
The model is explicitly instructed to only reference figures present in
the provided data and to write "Data not available" otherwise.

**2. Citation enforcement in training**
All training pairs (both template and upgraded) include explicit source
citations in the format [Source: p.XX]. The model is trained to produce
these citations as a structural requirement, not an option.

**3. Post-generation numerical validation**
`response_validator.py` extracts all numbers from the LLM output and
cross-references them against the extracted source data. Discrepancies
are flagged with a validation warning appended to the analysis.

**4. Temperature control**
Inference uses temperature=0.05 — near-deterministic outputs for factual
sections. This minimises creative extrapolation of financial figures.

**5. Negative example training**
The training set includes explicit "refusal" examples where data is
missing — teaching the model to acknowledge gaps rather than fill them.

---

## Data Pipeline

### Financial Statement Extraction
1. **Triage** — diagnose extraction strategy (standard text, tables, OCR)
2. **Text extraction** — PyMuPDF for PDF, custom HTML parser for EDGAR filings
3. **Table extraction** — pdfplumber (two-pass: strict then loose settings)
4. **Section classification** — keyword-based CAMELS section tagging
5. **Metric extraction** — regex patterns for 14 key financial ratios

### Rating Agency Processing
1. **Scanned PDF detection** — character count sampling
2. **OCR** — pdftoppm (300 DPI) + tesseract (LSTM engine, English)
3. **Text cleaning** — OCR artefact removal, whitespace normalisation
4. **Semantic chunking** — paragraph-aware splitting at ~500 words
5. **CAMELS topic tagging** — keyword matching across 8 topic categories

### Training Pair Construction
**Pipeline A (Financial):** One pair per detected CAMELS section per filing.
User prompt = task instruction + extracted data. Assistant response = upgraded
analyst prose with citations.

**Pipeline B (Rating Agency):** One pair per ~500-word chunk. User prompt =
methodology question for the relevant CAMELS topic. Assistant response =
structured methodology content.

---

## Evaluation Approach

The model is evaluated against a held-out set of 173 pairs (10% of total)
not seen during training. Evaluation metrics:

- **Citation rate** — % of numerical claims with source citations
- **Factual accuracy** — % of cited figures matching source data
- **Structure compliance** — % of outputs following CAMELS structure
- **Assessment calibration** — distribution of Strong/Adequate/Weak/Critical

Full evaluation results: [RESULTS.md](RESULTS.md)
