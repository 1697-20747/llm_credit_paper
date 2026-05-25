#!/usr/bin/env python3
"""
prepare_training_data.py
========================
Builds the JSONL fine-tuning dataset for the CAMELS credit analyst model.

Data sources assembled here:
  1. Synthetic CAMELS instruction pairs (generated locally)
  2. Rating agency methodology Q&A (parsed from public PDFs you supply)
  3. Bank annual report → analysis pairs (from public filings you supply)

Output: data/camels_training.jsonl  (train split)
        data/camels_eval.jsonl      (eval split, 10%)

Run:
    python prepare_training_data.py --synthetic_only
    python prepare_training_data.py --add_pdfs ./rating_agency_pdfs/
"""

import json
import random
import argparse
import hashlib
from pathlib import Path
from typing import Optional
import re

# ── optional deps (only needed for PDF ingestion of source material) ──────────
try:
    import fitz  # pymupdf
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

SYSTEM_PROMPT = (
    "You are a senior credit analyst at a major financial institution, "
    "specialising in bank credit analysis using the CAMELS framework "
    "(Capital Adequacy, Asset Quality, Management, Earnings, Liquidity, "
    "Sensitivity to Market Risk). "
    "You follow rating agency methodologies from Moody's, S&P Global Ratings, "
    "and Fitch Ratings. "
    "All numerical claims must cite a specific source (e.g. [Source: p.42, "
    "Table 3]). If data is unavailable, explicitly state 'Data not available'. "
    "Never fabricate or extrapolate figures. "
    "Structure analysis with: Assessment (Strong/Adequate/Weak/Critical), "
    "Key metrics, Peer context, Risks, and Source citations."
)

# ─────────────────────────────────────────────────────────────────────────────
# 1.  SYNTHETIC CAMELS INSTRUCTION PAIRS
#     These are carefully crafted with real-world plausible UK bank numbers.
#     Expand this list — aim for 200+ per pillar before training.
# ─────────────────────────────────────────────────────────────────────────────

CAPITAL_EXAMPLES = [
    {
        "input": (
            "Analyse Capital Adequacy for a UK systemically important bank with:\n"
            "CET1 ratio: 13.8% (regulatory minimum incl. buffers: 11.0%)\n"
            "Tier 1 ratio: 16.2%\n"
            "Total Capital ratio: 19.1%\n"
            "UK leverage ratio: 5.4% (minimum: 3.25%)\n"
            "RWA: £210.4bn\n"
            "RWA density (RWA/Total Assets): 24.1%\n"
            "CET1 capital: £29.0bn\n"
            "MREL requirement: 28.5% RWA\n"
            "Reported MREL: 34.2% RWA"
        ),
        "output": (
            "## Capital Adequacy (CAMELS — C)\n\n"
            "**Assessment: STRONG**\n\n"
            "The bank maintains a CET1 ratio of 13.8% [Source: Capital Table], "
            "representing 280bps of headroom above its regulatory minimum of 11.0% "
            "(comprising the 4.5% Pillar 1 minimum, 2.5% Capital Conservation Buffer, "
            "an assumed ~1.5% Pillar 2A requirement, and a ~2.5% G-SII/O-SII buffer). "
            "Under S&P's bank capital methodology, a CET1 ratio of 13–15% for a major "
            "systemically important UK bank would typically support a 'strong' capital "
            "assessment, all else equal.\n\n"
            "**Leverage:** The UK leverage ratio of 5.4% [Source: Capital Table] comfortably "
            "exceeds the PRA's 3.25% minimum for major UK deposit-takers, providing a "
            "non-risk-weighted capital backstop.\n\n"
            "**MREL:** Reported MREL of 34.2% RWA [Source: Resolution disclosure] exceeds "
            "the 28.5% requirement by 570bps, indicating strong resolvability positioning "
            "consistent with Fitch's view on resolution buffer adequacy.\n\n"
            "**Key risk:** RWA density of 24.1% [Source: Balance sheet / RWA table] is "
            "relatively low, suggesting the IRB modelling approach may be compressing "
            "risk weights. Investors and rating agencies increasingly scrutinise output "
            "floors under Basel IV (effective 2025) which could inflate RWAs materially. "
            "Sensitivity analysis on Basel IV impact is required to fully assess capital "
            "resilience.\n\n"
            "**Rating agency context:** Moody's 'Banks' methodology scores capital using "
            "a Tangible Common Equity / Risk-Weighted Assets metric; at ~13.8% this would "
            "likely map to a 'baa1'–'a3' capital score component, supportive of investment "
            "grade ratings."
        ),
    },
    {
        "input": (
            "Assess capital adequacy for a mid-tier UK bank:\n"
            "CET1 ratio: 10.3% (regulatory minimum: 10.1%)\n"
            "Tier 1 ratio: 12.1%\n"
            "Total Capital ratio: 15.6%\n"
            "UK leverage ratio: 4.1%\n"
            "RWA: £45.2bn\n"
            "CET1 capital: £4.65bn\n"
            "Stressed CET1 (Bank of England 2024 stress test): 7.2%\n"
            "Hurdle rate in stress: 6.8%"
        ),
        "output": (
            "## Capital Adequacy (CAMELS — C)\n\n"
            "**Assessment: ADEQUATE (WATCH)**\n\n"
            "The bank's CET1 ratio of 10.3% [Source: Capital Table] provides only 20bps "
            "of headroom above its 10.1% regulatory minimum (Pillar 1 + Pillar 2A + "
            "combined buffer requirement), which is materially thinner than most rated "
            "UK bank peers. This limited headroom constrains the bank's ability to absorb "
            "unexpected losses or RWA inflation without breaching minimum requirements.\n\n"
            "**Stress test performance:** The BoE stress test result of 7.2% CET1 at the "
            "trough [Source: Stress disclosure] provides 40bps above the 6.8% hurdle rate — "
            "a narrow margin that, under Moody's methodology, would likely be viewed as a "
            "capital constraint on ratings. Fitch typically requires stressed CET1 > hurdle "
            "by at least 100–150bps to avoid negative capital pressure on ratings.\n\n"
            "**Leverage:** The 4.1% leverage ratio [Source: Capital Table] is adequate "
            "relative to the 3.25% PRA minimum but provides limited comfort given the thin "
            "risk-based buffer.\n\n"
            "**Assessment:** Capital adequacy is marginal. Any deterioration in asset "
            "quality or macro conditions could quickly erode the buffer. This profile is "
            "consistent with a sub-investment-grade or low investment-grade rating on "
            "capital grounds alone. Active monitoring required."
        ),
    },
]

ASSET_QUALITY_EXAMPLES = [
    {
        "input": (
            "Assess asset quality for a UK retail-focused bank:\n"
            "Total gross loans: £450.2bn\n"
            "Stage 1 loans (IFRS 9): £405.1bn (90.0%)\n"
            "Stage 2 loans: £30.8bn (6.8%)\n"
            "Stage 3 loans (credit-impaired): £14.3bn (3.2%)\n"
            "ECL allowance (total): £6.8bn\n"
            "  of which Stage 3: £4.9bn\n"
            "Coverage ratio (Stage 3 ECL / Stage 3 loans): 34.3%\n"
            "Total coverage ratio (total ECL / total loans): 1.51%\n"
            "Impairment charge (income statement): £1.45bn\n"
            "Cost of risk (impairment / avg loans): 32bps\n"
            "Net write-offs: £1.1bn\n"
            "Mortgage portfolio: £310bn (69% of loans), avg LTV 42%\n"
            "Unsecured consumer credit: £20bn\n"
            "Commercial real estate: £18bn"
        ),
        "output": (
            "## Asset Quality (CAMELS — A)\n\n"
            "**Assessment: ADEQUATE**\n\n"
            "**IFRS 9 Staging:** The loan book shows 90.0% of balances in Stage 1 "
            "[Source: IFRS 9 staging table], with Stage 3 (credit-impaired) at 3.2% "
            "(£14.3bn) [Source: IFRS 9 staging table]. The Stage 2 bucket of 6.8% "
            "(£30.8bn) warrants monitoring as forward-looking migration risk — elevated "
            "Stage 2 balances can be a leading indicator of future Stage 3 formation "
            "under adverse macro scenarios.\n\n"
            "**Coverage:** Stage 3 coverage of 34.3% [Source: ECL table] is below the "
            "~40–50% typically seen at major UK banks, reflecting the predominantly "
            "secured nature of the portfolio (mortgage-heavy at 69% [Source: Loan book "
            "breakdown]). Total ECL coverage of 1.51% is broadly in line with UK retail "
            "bank peers.\n\n"
            "**Cost of risk:** At 32bps [Source: income statement / loan disclosure], "
            "impairment charges appear manageable relative to the loan book. This is "
            "within the historical normalised range for UK retail banks but above the "
            "sub-20bps levels seen during low-default-rate years (2021–2022).\n\n"
            "**Mortgage quality:** Average LTV of 42% [Source: Mortgage disclosure] on "
            "the £310bn mortgage book provides significant collateral protection. Even "
            "under a severe UK house price correction of 30%, the weighted average LTV "
            "would remain below 60% for most of the portfolio.\n\n"
            "**Key risks:** (1) Unsecured consumer credit (£20bn) carries higher loss "
            "severity and is more sensitive to unemployment. (2) CRE (£18bn) requires "
            "scrutiny given UK commercial property market volatility. (3) Stage 2 "
            "migration risk if macro conditions deteriorate."
        ),
    },
]

EARNINGS_EXAMPLES = [
    {
        "input": (
            "Assess earnings quality and sustainability for a UK bank:\n"
            "Net Interest Income (NII): £13.8bn\n"
            "Net Interest Margin (NIM): 3.02%\n"
            "Other income (fees, commissions, trading): £4.1bn\n"
            "Total income: £17.9bn\n"
            "Operating costs: £9.8bn\n"
            "Cost:income ratio: 54.7%\n"
            "Impairment charge: £1.45bn\n"
            "Pre-tax profit: £6.65bn\n"
            "Tax charge: £1.7bn (effective rate: 25.6%)\n"
            "Profit after tax: £4.95bn\n"
            "Return on tangible equity (RoTE): 16.2%\n"
            "Return on assets (RoA): 0.56%\n"
            "EPS (basic): 76.3p\n"
            "DPS: 3.17p\n"
            "Prior year NIM: 2.89%\n"
            "Prior year RoTE: 14.8%"
        ),
        "output": (
            "## Earnings (CAMELS — E)\n\n"
            "**Assessment: STRONG**\n\n"
            "**Profitability:** The bank delivered a RoTE of 16.2% [Source: KPI summary], "
            "up from 14.8% in the prior year [Source: comparative KPI table], and above "
            "the cost of equity (typically estimated at 10–12% for major UK banks). This "
            "level of RoTE is consistent with an S&P 'strong' earnings assessment and "
            "supports positive rating momentum.\n\n"
            "**NII and NIM:** Net Interest Income of £13.8bn on a NIM of 3.02% [Source: "
            "Income statement / NIM disclosure] represents expansion of 13bps year-on-year "
            "[Source: comparative disclosure], driven by the higher interest rate "
            "environment benefiting liability-sensitive retail deposit franchises. "
            "Sustainability of NIM at current levels is a key forward risk as base rates "
            "normalise and deposit competition intensifies.\n\n"
            "**Cost efficiency:** The cost:income ratio of 54.7% [Source: income statement] "
            "is improving but still above the ~50% target typical of efficiency-focused "
            "UK banks. Operating leverage (income growing faster than costs) is positive.\n\n"
            "**Diversification:** Non-interest income of £4.1bn (23% of total income) "
            "[Source: income breakdown] provides moderate diversification but the bank "
            "remains predominantly NII-dependent — a vulnerability if rates fall sharply.\n\n"
            "**RoA of 0.56%** [Source: balance sheet / income statement] is adequate for "
            "a large balance sheet bank, broadly in line with European systemically "
            "important bank peers.\n\n"
            "**Key risk:** NIM compression in a falling rate environment could materially "
            "reduce NII. Sensitivity: each 25bps rate reduction estimated to impact NII "
            "by ~£200–350m (quantification subject to interest rate sensitivity disclosure)."
        ),
    },
]

LIQUIDITY_EXAMPLES = [
    {
        "input": (
            "Assess liquidity and funding for a UK bank:\n"
            "Liquidity Coverage Ratio (LCR): 142%\n"
            "Net Stable Funding Ratio (NSFR): 131%\n"
            "High Quality Liquid Assets (HQLA): £68.4bn\n"
            "Loan:deposit ratio (LDR): 98.7%\n"
            "Retail deposits: £312bn\n"
            "Wholesale funding (total): £89bn\n"
            "  of which < 1 year maturity: £31bn\n"
            "  of which > 1 year maturity: £58bn\n"
            "TFSME borrowings (BoE): £12bn (maturing 2025–2026)\n"
            "Covered bond issuance (outstanding): £18bn\n"
            "Senior unsecured issuance (YTD): £4.5bn\n"
            "Liquidity pool: £120bn"
        ),
        "output": (
            "## Liquidity (CAMELS — L)\n\n"
            "**Assessment: STRONG**\n\n"
            "**Regulatory ratios:** The LCR of 142% [Source: Liquidity disclosure] provides "
            "a 4,200bps surplus above the 100% minimum, representing significant buffer "
            "to absorb a 30-day stress outflow. The NSFR of 131% [Source: Liquidity "
            "disclosure] confirms that stable funding more than covers required stable "
            "funding over a one-year horizon — both ratios are above UK major bank averages.\n\n"
            "**Funding structure:** The bank is predominantly retail-funded with £312bn of "
            "retail deposits [Source: Funding analysis]. The LDR of 98.7% [Source: balance "
            "sheet] is within acceptable range; above 100% would indicate net wholesale "
            "reliance. Retail deposits are generally more stable than wholesale under stress.\n\n"
            "**Wholesale funding:** Total wholesale funding of £89bn (£31bn short-dated, "
            "£58bn longer-dated) [Source: funding maturity profile] — the maturity profile "
            "is reasonably well-distributed. The £12bn TFSME drawdown [Source: BoE scheme "
            "disclosure] creates a known refinancing need in 2025–2026 which management "
            "must address through market issuance or organic deposit growth.\n\n"
            "**HQLA:** The £68.4bn HQLA pool [Source: Liquidity disclosure] consists "
            "primarily of central bank reserves and UK gilts, providing high-quality, "
            "readily monetisable assets. This represents approximately 22 days of total "
            "asset value — a strong liquidity position.\n\n"
            "**Key risk:** TFSME maturity concentration (£12bn in 2025–2026) requires "
            "proactive management. Deposit repricing risk if retail competition intensifies "
            "could also reduce the funding cost advantage of the retail deposit base."
        ),
    },
]

MANAGEMENT_EXAMPLES = [
    {
        "input": (
            "Assess management quality and governance for a UK listed bank:\n"
            "Board composition: 12 directors, 8 independent NEDs, 2 executive directors, "
            "2 shareholder-nominated NEDs\n"
            "Chair: Independent NED (former central banker)\n"
            "CEO tenure: 3 years\n"
            "CFO tenure: 2 years\n"
            "CRO: Reports to Board Risk Committee (not CEO)\n"
            "Audit Committee: 4 independent NEDs, meets 6x per year\n"
            "Risk Committee: 5 NEDs including CRO attend\n"
            "Remuneration: CEO total comp £5.2m (65% deferred/variable)\n"
            "External auditor: PwC (12-year tenure)\n"
            "PRA/FCA regulatory actions: None in past 3 years\n"
            "Major conduct fines (past 5 years): £180m (PPI — concluded)\n"
            "Strategic plan: 3-year cost-saving programme (£1.2bn target by 2026)\n"
            "ESG: Net zero 2050 commitment, TCFD-aligned reporting"
        ),
        "output": (
            "## Management (CAMELS — M)\n\n"
            "**Assessment: ADEQUATE TO STRONG**\n\n"
            "**Governance structure:** The board composition of 8 independent NEDs out of "
            "12 total directors [Source: Corporate Governance Report] meets the UK Corporate "
            "Governance Code requirement for at least half the board (excluding the Chair) "
            "to be independent. The Chair's central banking background is credit-positive "
            "for regulatory engagement.\n\n"
            "**Risk governance:** The CRO reporting line to the Board Risk Committee "
            "(rather than through the CEO) [Source: Governance disclosure] is a positive "
            "governance feature, reducing the risk of commercial pressure overriding risk "
            "limits — consistent with PRA SS3/16 expectations for risk governance in "
            "systemic banks.\n\n"
            "**Remuneration structure:** CEO total compensation of £5.2m with 65% deferred "
            "or variable [Source: Remuneration Report] aligns incentives with longer-term "
            "performance and meets the PRA's remuneration rules for material risk-takers. "
            "The high deferral ratio is viewed positively by rating agencies as reducing "
            "short-termism.\n\n"
            "**Auditor tenure:** PwC's 12-year audit tenure [Source: Audit Committee report] "
            "is approaching the FRC's mandatory rotation threshold (20 years for FTSE 350), "
            "but concentration risk exists. No audit qualifications noted.\n\n"
            "**Regulatory record:** No PRA/FCA regulatory actions in the past 3 years is "
            "a positive signal. The concluded PPI conduct fine of £180m [Source: conduct "
            "disclosure] is legacy and not indicative of current risk management quality, "
            "though total industry PPI costs underscore the importance of conduct risk frameworks.\n\n"
            "**Strategy:** The £1.2bn cost-saving programme [Source: Strategic Report] "
            "is credible if executed; delivery risk exists as with any transformation programme."
        ),
    },
]

SENSITIVITY_EXAMPLES = [
    {
        "input": (
            "Assess market risk and interest rate sensitivity for a UK bank:\n"
            "Structural interest rate sensitivity (NII impact):\n"
            "  +100bps parallel shift: +£800m NII (12 months)\n"
            "  -100bps parallel shift: -£650m NII (12 months)\n"
            "  +25bps: +£200m NII\n"
            "Trading book VaR (99%, 1-day, avg): £42m\n"
            "Stressed VaR: £185m\n"
            "FX net open position: £1.2bn\n"
            "Duration of equity: 2.8 years\n"
            "FVOCI bond portfolio: £28bn (unrealised loss: £1.8bn)\n"
            "Interest rate risk in banking book (IRRBB) capital requirement: £2.1bn\n"
            "Pension fund deficit: £0 (surplus of £420m)\n"
            "Counterparty credit risk (CVA): £320m\n"
            "Commodity exposure: Nil"
        ),
        "output": (
            "## Sensitivity to Market Risk (CAMELS — S)\n\n"
            "**Assessment: ADEQUATE**\n\n"
            "**Interest rate sensitivity:** The bank is asset-sensitive on NII — a +100bps "
            "rate increase generates approximately +£800m NII benefit over 12 months "
            "[Source: IRRBB disclosure], while a -100bps decline costs £650m [Source: "
            "IRRBB disclosure]. The asymmetry (greater upside than downside) reflects the "
            "predominance of variable-rate lending and partially hedged fixed-rate deposits. "
            "In the current rate environment (likely declining from peak), this asset "
            "sensitivity creates NII headwinds — a key near-term earnings risk.\n\n"
            "**Duration of equity (2.8 years)** [Source: IRRBB disclosure] indicates "
            "meaningful exposure to long-duration rate moves in the banking book. Under "
            "BCBS 368 (IRRBB standards), this is within normal bounds but warrants "
            "monitoring as the yield curve shifts.\n\n"
            "**FVOCI portfolio:** The £1.8bn unrealised loss on the £28bn FVOCI bond "
            "portfolio [Source: OCI/investment securities disclosure] flows through Other "
            "Comprehensive Income, not P&L, but is excluded from regulatory capital under "
            "current CRR2 provisions. If the FVOCI filter were removed (a Basel IV risk), "
            "the CET1 impact would be material (~60–80bps on the above portfolio size).\n\n"
            "**Trading risk:** Average VaR of £42m [Source: Market risk report] is modest "
            "relative to the balance sheet, reflecting a predominantly retail/commercial "
            "banking model with limited proprietary trading. Stressed VaR of £185m "
            "[Source: Market risk report] confirms limited tail risk from trading.\n\n"
            "**Pension:** A pension surplus of £420m [Source: pension disclosure] eliminates "
            "this as a capital risk — a credit-positive distinguishing feature.\n\n"
            "**Key risk:** NII sensitivity to declining rates is the primary market risk "
            "concern. The bank's NIM trajectory in a 2025–2026 rate normalisation scenario "
            "requires close monitoring."
        ),
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# 2.  RATING METHODOLOGY Q&A PAIRS
# ─────────────────────────────────────────────────────────────────────────────

RATING_METHODOLOGY_EXAMPLES = [
    {
        "question": (
            "Under Moody's bank rating methodology, what is the Baseline Credit "
            "Assessment (BCA) and how does capital factor into it?"
        ),
        "answer": (
            "Moody's Baseline Credit Assessment (BCA) represents a bank's intrinsic "
            "financial strength, independent of external support (government or parent). "
            "It is expressed on Moody's alphanumeric rating scale from aaa to ca. "
            "Capital is one of four key financial profile factors in the BCA scorecard "
            "(alongside Asset Risk, Profitability, and Funding/Liquidity). "
            "The capital sub-score uses Tangible Common Equity (TCE) as a percentage of "
            "Risk-Weighted Assets as the primary metric. A TCE/RWA ratio above ~14–15% "
            "typically maps to an 'a' range capital score; 10–14% to 'baa'; below 8% to "
            "'b' range or below. The four financial profile factors are combined with a "
            "Macro Profile assessment (reflecting country/operating environment risk) to "
            "produce the preliminary BCA, which is then adjusted for qualitative factors "
            "before arriving at the final BCA."
        ),
    },
    {
        "question": (
            "How does S&P Global Ratings assess a bank's capital and earnings under "
            "its bank rating methodology?"
        ),
        "answer": (
            "S&P uses a Risk-Adjusted Capital (RAC) ratio as the primary capital metric, "
            "which applies S&P's own risk weights (rather than regulatory Basel III "
            "weights) to provide a more conservative and internationally comparable "
            "measure. The RAC ratio is defined as Adjusted Common Equity (ACE) divided "
            "by S&P Risk-Weighted Assets. An RAC ratio above 15% is considered 'very "
            "strong'; 10–15% 'strong'; 7–10% 'adequate'; below 7% 'moderate' or weaker. "
            "For earnings, S&P looks at Core Earnings / Average RWA as the primary "
            "profitability metric. A ratio above 1.5–2.0% is typically considered "
            "adequate for investment grade. S&P also assesses earnings quality, "
            "diversification and volatility. The capital and earnings assessment feeds "
            "into the Bank Industry Country Risk Assessment (BICRA) and the bank's "
            "stand-alone credit profile (SACP)."
        ),
    },
    {
        "question": (
            "Under Fitch's bank rating criteria, what is the Viability Rating and "
            "how is asset quality scored?"
        ),
        "answer": (
            "Fitch's Viability Rating (VR) is the agency's assessment of a bank's "
            "intrinsic creditworthiness — its ability to maintain viability without "
            "external extraordinary support. It runs from 'aaa' to 'f' (failure). "
            "Asset quality is one of the five key assessment factors in Fitch's framework "
            "(alongside Earnings & Profitability, Capitalisation & Leverage, Funding & "
            "Liquidity, and Business Profile). For asset quality, Fitch focuses on: "
            "(1) Impaired loan ratio (broadly equivalent to Stage 3 / NPL ratio), where "
            "a ratio below 3% is typically considered low risk; (2) Reserve coverage "
            "ratio (loan loss reserves / impaired loans); (3) Net charge-offs / average "
            "gross loans (cost of risk); (4) Loan book concentration risks; and (5) "
            "Growth rate of the loan portfolio. Fitch also considers the operating "
            "environment's influence on expected credit losses — in a stressed macro "
            "scenario, even low current NPLs may indicate future deterioration if "
            "leading indicators (Stage 2 balances, macro overlays) signal stress."
        ),
    },
    {
        "question": (
            "What is IFRS 9 ECL staging and why does it matter for bank credit analysis?"
        ),
        "answer": (
            "IFRS 9 (effective 1 January 2018) replaced IAS 39's incurred loss model "
            "with an Expected Credit Loss (ECL) framework using three stages: "
            "Stage 1: Performing loans with no significant increase in credit risk since "
            "origination. ECL provision = 12-month ECL. "
            "Stage 2: Loans with a significant increase in credit risk (SICR) since "
            "origination but not yet credit-impaired. ECL provision = Lifetime ECL. "
            "Stage 3: Credit-impaired loans (equivalent to traditional NPLs / defaulted). "
            "ECL provision = Lifetime ECL. "
            "For credit analysts, IFRS 9 staging is significant because: "
            "(1) Stage 2 balances are a leading indicator — migration from Stage 1 to "
            "Stage 2 can precede actual defaults by 6–18 months; "
            "(2) Stage 3 / total loans is the primary NPL metric under IFRS 9; "
            "(3) Stage 3 coverage ratio (Stage 3 ECL allowance / Stage 3 gross loans) "
            "indicates provisioning adequacy — low coverage on secured portfolios "
            "(e.g. 30–40%) is normal; on unsecured portfolios 80–100%+ coverage is expected; "
            "(4) The macro overlay / forward-looking economic scenarios embedded in ECL "
            "models mean provisions are more volatile than under IAS 39, requiring "
            "analysis of the ECL model assumptions."
        ),
    },
    {
        "question": (
            "What are the Basel III / Basel IV minimum capital requirements for a "
            "UK bank and what buffers apply?"
        ),
        "answer": (
            "Under Basel III (as implemented in the UK via CRR/CRD and PRA rules), "
            "minimum capital requirements for UK banks are: "
            "Pillar 1 minimum CET1: 4.5% of RWA. "
            "Pillar 1 minimum Tier 1: 6.0% of RWA. "
            "Pillar 1 minimum Total Capital: 8.0% of RWA. "
            "On top of Pillar 1, UK banks are subject to: "
            "Capital Conservation Buffer (CCoB): +2.5% CET1 (automatic restriction on "
            "distributions if breached). "
            "Countercyclical Capital Buffer (CCyB): set by FPC, currently 2.0% for UK "
            "exposures (as of 2024). "
            "G-SII / O-SII buffer: 1.0–2.5% CET1 for systemically important banks. "
            "Pillar 2A: firm-specific add-on set by PRA (typically 1.5–3.0% for major banks). "
            "Total regulatory CET1 requirement for a major UK bank therefore typically "
            "ranges from 10.0% to 12.5%+. "
            "Basel IV (output floor, effective 2025–2030) will require that RWAs under "
            "internal models are floored at 72.5% of standardised approach RWAs by 2030, "
            "which could materially increase RWA inflation for IRB banks. "
            "The UK leverage ratio framework requires a minimum 3.25% leverage ratio "
            "(Tier 1 capital / total exposures) for major UK deposit-takers."
        ),
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# 3.  NEGATIVE / REFUSAL EXAMPLES (anti-hallucination)
# ─────────────────────────────────────────────────────────────────────────────

NEGATIVE_EXAMPLES = [
    {
        "input": (
            "Assess the liquidity position. Available data:\n"
            "Total deposits: £280bn\n"
            "Total loans: £260bn\n"
            "Note: LCR, NSFR and HQLA data not disclosed in this filing."
        ),
        "output": (
            "## Liquidity (CAMELS — L)\n\n"
            "**Assessment: INDETERMINATE — INSUFFICIENT DATA**\n\n"
            "Critical liquidity metrics including the Liquidity Coverage Ratio (LCR), "
            "Net Stable Funding Ratio (NSFR), and High Quality Liquid Asset (HQLA) pool "
            "size are not available in the provided data. Without these regulatory ratios, "
            "a complete CAMELS liquidity assessment cannot be made to rating agency standards.\n\n"
            "**Available data:** The loan:deposit ratio can be estimated at approximately "
            "92.9% (£260bn / £280bn), which suggests the bank is predominantly deposit-funded "
            "and unlikely to be in acute structural liquidity stress — but this is a crude "
            "measure and cannot substitute for LCR/NSFR analysis.\n\n"
            "**Data gaps:** LCR (mandatory Pillar 3 disclosure under CRR2), NSFR, HQLA "
            "composition and the maturity profile of wholesale funding are required for a "
            "complete assessment. These should be disclosed in the Pillar 3 report or "
            "supplementary liquidity disclosure. The analyst should obtain these before "
            "assigning a liquidity rating.\n\n"
            "**Do not estimate or extrapolate:** It would be inappropriate to assign an "
            "LCR estimate without factual disclosure. This section is marked incomplete."
        ),
    },
    {
        "input": (
            "What was the bank's NPL ratio in 2019? Only 2024 and 2023 data is provided:\n"
            "Stage 3 / gross loans 2024: 3.2%\n"
            "Stage 3 / gross loans 2023: 2.9%"
        ),
        "output": (
            "2019 NPL/Stage 3 data is not available in the provided annual report extract. "
            "Only 2024 (3.2%) and 2023 (2.9%) figures have been provided [Source: IFRS 9 "
            "staging table]. "
            "Historical data for 2019 would need to be sourced from the bank's 2019 or 2020 "
            "annual report, or from EBA transparency exercise data (eba.europa.eu) if the "
            "bank participates. It would be inappropriate to estimate or extrapolate the "
            "2019 figure from current data given the structural change from IAS 39 to "
            "IFRS 9 (effective 2018), which makes pre-2018 and post-2018 NPL comparisons "
            "difficult without restatement."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# ASSEMBLY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def build_camels_pair(pillar_data: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": pillar_data["input"]},
            {"role": "assistant", "content": pillar_data["output"]},
        ]
    }


def build_qa_pair(qa: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": qa["question"]},
            {"role": "assistant", "content": qa["answer"]},
        ]
    }


def build_negative_pair(neg: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": neg["input"]},
            {"role": "assistant", "content": neg["output"]},
        ]
    }


def deduplicate(records: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in records:
        key = hashlib.md5(json.dumps(r, sort_keys=True).encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def split_train_eval(records: list[dict], eval_frac: float = 0.10):
    random.shuffle(records)
    n_eval = max(1, int(len(records) * eval_frac))
    return records[n_eval:], records[:n_eval]


def ingest_pdf_qa_pairs(pdf_path: Path) -> list[dict]:
    """
    Extracts Q&A pairs from rating agency methodology PDFs you supply.
    This is a skeleton — real extraction requires domain-specific chunking.
    Each ~500-word chunk becomes an instruction pair.
    """
    if not HAS_FITZ:
        print(f"  [WARN] pymupdf not installed — skipping {pdf_path.name}")
        return []
    pairs = []
    doc = fitz.open(str(pdf_path))
    full_text = " ".join(page.get_text() for page in doc)
    doc.close()
    # Naive chunking by paragraph — replace with smarter semantic chunking
    paragraphs = [p.strip() for p in full_text.split("\n\n") if len(p.strip()) > 200]
    for i, para in enumerate(paragraphs):
        if any(kw in para.lower() for kw in ["capital", "asset quality", "liquidity",
                                               "earnings", "management", "sensitivity",
                                               "rating", "credit", "camels"]):
            pairs.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Explain the following credit analysis concept from a "
                            f"rating agency methodology document:\n\n{para[:800]}"
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": (
                            "[Note: This is a direct methodology extract for training. "
                            "In practice the analyst would paraphrase and apply to specific data.]\n\n"
                            + para[:1200]
                        ),
                    },
                ]
            })
    print(f"  Extracted {len(pairs)} pairs from {pdf_path.name}")
    return pairs


def main():
    parser = argparse.ArgumentParser(description="Build CAMELS training data")
    parser.add_argument("--synthetic_only", action="store_true",
                        help="Only use hand-crafted synthetic pairs")
    parser.add_argument("--add_pdfs", type=str, default=None,
                        help="Path to folder of rating agency methodology PDFs")
    parser.add_argument("--output_dir", type=str, default="data",
                        help="Output directory for JSONL files")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    records = []

    # --- Synthetic CAMELS pairs ---
    for ex in CAPITAL_EXAMPLES:
        records.append(build_camels_pair(ex))
    for ex in ASSET_QUALITY_EXAMPLES:
        records.append(build_camels_pair(ex))
    for ex in EARNINGS_EXAMPLES:
        records.append(build_camels_pair(ex))
    for ex in LIQUIDITY_EXAMPLES:
        records.append(build_camels_pair(ex))
    for ex in MANAGEMENT_EXAMPLES:
        records.append(build_camels_pair(ex))
    for ex in SENSITIVITY_EXAMPLES:
        records.append(build_camels_pair(ex))

    # --- Rating methodology Q&A ---
    for qa in RATING_METHODOLOGY_EXAMPLES:
        records.append(build_qa_pair(qa))

    # --- Negative / refusal examples ---
    for neg in NEGATIVE_EXAMPLES:
        records.append(build_negative_pair(neg))

    print(f"Synthetic pairs: {len(records)}")

    # --- Optional: ingest PDFs ---
    if args.add_pdfs and not args.synthetic_only:
        pdf_dir = Path(args.add_pdfs)
        for pdf in pdf_dir.glob("*.pdf"):
            records.extend(ingest_pdf_qa_pairs(pdf))

    records = deduplicate(records)
    train, eval_ = split_train_eval(records)

    train_path = output_dir / "camels_training.jsonl"
    eval_path = output_dir / "camels_eval.jsonl"

    with open(train_path, "w") as f:
        for r in train:
            f.write(json.dumps(r) + "\n")

    with open(eval_path, "w") as f:
        for r in eval_:
            f.write(json.dumps(r) + "\n")

    print(f"\n✅ Training data written:")
    print(f"   Train: {train_path} ({len(train)} examples)")
    print(f"   Eval:  {eval_path} ({len(eval_)} examples)")
    print(f"\n📌 IMPORTANT: This is a seed dataset (~{len(records)} examples).")
    print("   Aim to expand to 5,000–15,000 examples before training.")
    print("   See CAMELS_PROJECT_PLAN.md for data sourcing guidance.")


if __name__ == "__main__":
    main()
