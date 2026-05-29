#!/usr/bin/env python3
"""
download_rating_agency.py
=========================
Downloads rating agency methodology and regulatory documents.
All BIS, OCC, FDIC, PRA, EBA, Fed and IMF documents are fully automated.
Fitch, S&P and Moody's require free account registration.

Usage:
    python scripts/download_rating_agency.py
    python scripts/download_rating_agency.py --skip-manual
    python scripts/download_rating_agency.py --reprocess

Output:
    rating_agency/*.pdf
    logs/rating_agency_download_log.json
"""

import json
import ssl
import time
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl._create_unverified_context()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RATING_DIR   = PROJECT_ROOT / "rating_agency"
LOGS_DIR     = PROJECT_ROOT / "logs"
RATING_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

GREEN  = '\033[0;32m'; YELLOW = '\033[1;33m'
CYAN   = '\033[0;36m'; RED    = '\033[0;31m'; NC = '\033[0m'
def info(msg):   print(f"{GREEN}[INFO]{NC}   {msg}")
def get(msg):    print(f"{CYAN}[GET]{NC}    {msg}")
def ok(msg):     print(f"{GREEN}[OK]{NC}     {msg}")
def fail(msg):   print(f"{RED}[FAIL]{NC}   {msg}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
    "Referer": "https://www.google.com/",
}

MIN_PDF_BYTES = 100_000


def is_valid_pdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < MIN_PDF_BYTES:
        return False
    with open(path, "rb") as f:
        return f.read(4) == b"%PDF"


def download(url: str, dest: Path, description: str) -> bool:
    if is_valid_pdf(dest):
        size_mb = dest.stat().st_size / 1_048_576
        info(f"{description} — already have ({size_mb:.1f}MB)")
        return True

    get(f"{description}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=120) as r:
            data = r.read()
        if len(data) > MIN_PDF_BYTES and data[:4] == b"%PDF":
            dest.write_bytes(data)
            ok(f"{description} — {len(data)//1024}KB")
            return True
        else:
            fail(f"{description} — not a valid PDF ({len(data)} bytes)")
            return False
    except Exception as e:
        fail(f"{description} — {e}")
        return False


AUTOMATED_DOCS = {

    # ── BIS / Basel Committee ─────────────────────────────────────────────────
    "basel_iii_capital_framework.pdf": {
        "url": "https://www.bis.org/publ/bcbs189.pdf",
        "description": "Basel III Capital Framework (BCBS189)",
    },
    "basel_lcr_standard.pdf": {
        "url": "https://www.bis.org/publ/bcbs238.pdf",
        "description": "Basel III LCR Standard (BCBS238)",
    },
    "basel_nsfr_standard.pdf": {
        "url": "https://www.bis.org/publ/bcbs295.pdf",
        "description": "Basel III NSFR Standard (BCBS295)",
    },
    "basel_leverage_ratio.pdf": {
        "url": "https://www.bis.org/bcbs/publ/d424.pdf",
        "description": "Basel III Leverage Ratio (BCBS d424)",
    },
    "basel_credit_risk_irb.pdf": {
        "url": "https://www.bis.org/publ/bcbs128.pdf",
        "description": "Basel II IRB Credit Risk (BCBS128)",
    },
    "basel_irrbb_standard.pdf": {
        "url": "https://www.bis.org/bcbs/publ/d368.pdf",
        "description": "IRRBB Standard (BCBS d368)",
    },
    "basel_committee_core_principles.pdf": {
        "url": "https://www.bis.org/publ/bcbs230.pdf",
        "description": "Basel Core Principles for Effective Banking Supervision",
    },
    "bis_working_paper_bank_ratings.pdf": {
        "url": "https://www.bis.org/publ/work656.pdf",
        "description": "BIS Working Paper: Bank Ratings — What Determines their Quality",
    },
    "bis_working_paper_camels_ratings.pdf": {
        "url": "https://www.bis.org/publ/work936.pdf",
        "description": "BIS Working Paper: CAMELS Ratings and Bank Fragility",
    },
    "bis_wp_bank_capital_quality.pdf": {
        "url": "https://www.bis.org/publ/work671.pdf",
        "description": "BIS Working Paper: Bank Capital and Risk-Taking",
    },
    "bis_wp_npl_resolution.pdf": {
        "url": "https://www.bis.org/publ/work834.pdf",
        "description": "BIS Working Paper: NPL Resolution — Lessons from Europe",
    },

    # ── OCC Comptroller's Handbook ────────────────────────────────────────────
    # URLs verified May 2026 — OCC restructured some paths
    "occ_bank_supervision_process.pdf": {
        "url": "https://www.occ.gov/publications-and-resources/publications/comptrollers-handbook/files/bank-supervision-process/pub-ch-bank-supervision-process.pdf",
        "description": "OCC Handbook: Bank Supervision Process (CAMELS)",
    },
    "occ_earnings_handbook.pdf": {
        "url": "https://www.occ.gov/publications-and-resources/publications/comptrollers-handbook/files/earnings/pub-ch-earnings.pdf",
        "description": "OCC Handbook: Earnings",
    },
    "occ_liquidity_handbook.pdf": {
        "url": "https://www.occ.gov/publications-and-resources/publications/comptrollers-handbook/files/liquidity/pub-ch-liquidity.pdf",
        "description": "OCC Handbook: Liquidity",
    },
    "occ_capital_handbook.pdf": {
        "url": "https://www.occ.gov/publications-and-resources/publications/comptrollers-handbook/files/capital-dividends/pub-ch-capital-and-dividends.pdf",
        "description": "OCC Handbook: Capital and Dividends",
    },
    "occ_credit_risk_handbook.pdf": {
        "url": "https://www.occ.gov/publications-and-resources/publications/comptrollers-handbook/files/credit-risk-review/pub-ch-credit-risk-review.pdf",
        "description": "OCC Handbook: Credit Risk Review",
    },
    "occ_asset_quality_handbook.pdf": {
        "url": "https://www.occ.gov/publications-and-resources/publications/comptrollers-handbook/files/loans/pub-ch-loan-portfolio-management.pdf",
        "description": "OCC Handbook: Loan Portfolio Management (Asset Quality)",
    },
    "occ_sensitivity_handbook.pdf": {
        "url": "https://www.occ.gov/publications-and-resources/publications/comptrollers-handbook/files/interest-rate-risk/pub-ch-interest-rate-risk.pdf",
        "description": "OCC Handbook: Interest Rate Risk (Sensitivity)",
    },

    # ── FDIC ─────────────────────────────────────────────────────────────────
    "fdic_bank_examination_overview.pdf": {
        "url": "https://www.fdic.gov/regulations/examinations/supervisory/insights/siwin04/siwin04.pdf",
        "description": "FDIC: Bank Examination Overview",
    },
    "fdic_risk_management_manual.pdf": {
        "url": "https://www.fdic.gov/bank/historical/managing/managingthecrisis-complete.pdf",
        "description": "FDIC: Managing the Crisis — Bank Examination Manual",
    },

    # ── PRA / Bank of England ─────────────────────────────────────────────────
    "pra_approach_banking_supervision.pdf": {
        "url": "https://www.bankofengland.co.uk/-/media/boe/files/prudential-regulation/publication/2016/the-pras-approach-to-banking-supervision.pdf",
        "description": "PRA: Approach to Banking Supervision",
    },

    # ── EBA ───────────────────────────────────────────────────────────────────
    # EBA restructured their document URLs — using direct asset paths
    "eba_srep_guidelines.pdf": {
        "url": "https://www.eba.europa.eu/sites/default/files/document_library/Publications/Guidelines/2014/EBA-GL-2014-13/1026151/EBA-GL-2014-13-Guidelines-on-SREP.pdf",
        "description": "EBA: SREP Guidelines",
    },
    "eba_pillar3_guidelines.pdf": {
        "url": "https://www.eba.europa.eu/sites/default/files/document_library/Publications/Guidelines/2022/EBA-GL-2022-01/1049838/EBA-GL-2022-01%20Guidelines%20on%20Pillar%203%20disclosures.pdf",
        "description": "EBA: Pillar 3 Disclosure Guidelines",
    },

    # ── Federal Reserve ───────────────────────────────────────────────────────
    "fed_camels_guidance.pdf": {
        "url": "https://www.federalreserve.gov/publications/files/bhcsupervision0212.pdf",
        "description": "Fed: BHC Supervision Manual (CAMELS framework)",
    },
    "fed_dfast_2024.pdf": {
        "url": "https://www.federalreserve.gov/publications/files/2024-dfast-results-20240626.pdf",
        "description": "Fed: DFAST 2024 Stress Test Results",
    },
    "fed_dfast_2023.pdf": {
        "url": "https://www.federalreserve.gov/publications/files/2023-dfast-results-20230628.pdf",
        "description": "Fed: DFAST 2023 Stress Test Results",
    },

    # ── IMF GFSR — correct URLs use lowercase 'files' not 'Files', no .ashx ──
    "imf_gfsr_2024_april.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/gfsr/2024/april/english/text.pdf",
        "description": "IMF GFSR April 2024 — Bank Credit Risk Analysis",
    },
    "imf_gfsr_2023_october.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/gfsr/2023/october/english/text.pdf",
        "description": "IMF GFSR October 2023 — Financial Stability Analysis",
    },
    "imf_gfsr_2023_april.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/gfsr/2023/april/english/text.pdf",
        "description": "IMF GFSR April 2023 — Banking Stress and Resilience",
    },
    "imf_gfsr_2022_october.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/gfsr/2022/october/english/text.pdf",
        "description": "IMF GFSR October 2022 — Global Financial Stability",
    },

    # ── IMF FSAP — use elibrary PDF downloads ─────────────────────────────────
    # IMF FSAP pages redirect to HTML — use direct elibrary PDF links
    "imf_fsap_uk_2021.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/cr/2021/english/1creng2021516.ashx",
        "description": "IMF FSAP: UK Bank Solvency Stress Testing 2021",
    },
    "imf_fsap_us_2020.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/cr/2020/english/1creng202049.ashx",
        "description": "IMF FSAP: US Bank Stress Testing 2020",
    },
    "imf_fsap_germany_2024.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/cr/2024/english/1creng2024129.ashx",
        "description": "IMF FSAP: Germany Banking Supervision 2024",
    },
    "imf_fsap_eu_banking_2018.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/cr/2018/english/1creng201842.ashx",
        "description": "IMF FSAP: Euro Area Financial System Stability Assessment 2018",
    },

    # ── IMF Working Papers — use direct PDF pattern ───────────────────────────
    "imf_wp_bank_ratings_methodology.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/wp/2016/1wp16189.ashx",
        "description": "IMF WP: What Do Bank Ratings Tell Us About Capital Adequacy",
    },
    "imf_wp_npl_determinants.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/wp/2015/1wp15161.ashx",
        "description": "IMF WP: Non-Performing Loans — Determinants and Impact",
    },
    "imf_wp_bank_capital_procyclicality.pdf": {
        "url": "https://www.imf.org/-/media/files/publications/wp/2016/1wp16169.ashx",
        "description": "IMF WP: Bank Capital Buffers — Dynamic Model",
    },
}

MANUAL_DOCS = {
    "fitch_rating.pdf": {
        "description": "Fitch Banks Rating Criteria",
        "check_scanned": True,
        "steps": [
            "1. Register free: https://www.fitchratings.com/site/register",
            "2. Go to: https://www.fitchratings.com/research/banks/global-banks-rating-criteria",
            "3. If embedded in iframe: Cmd+P → Save as PDF",
            "4. Save to: rating_agency/fitch_rating.pdf",
        ],
    },
    "moodys_rating.pdf": {
        "description": "Moody's Banks Rating Methodology",
        "check_scanned": False,
        "steps": [
            "1. Register free: https://www.moodys.com/researchandratings",
            "2. Search: 'Banks' under Methodologies",
            "3. If embedded in iframe: Cmd+P → Save as PDF",
            "4. Save to: rating_agency/moodys_rating.pdf",
            "",
            "NOTE: Argentina methodology already in rating_agency/ covers the",
            "analytical framework — only country risk tables differ.",
        ],
    },
    "standard_poors_rating.pdf": {
        "description": "S&P Global Banks Rating Criteria",
        "check_scanned": False,
        "steps": [
            "1. Register free: https://www.spglobal.com/ratings/en/research-insights/register",
            "2. Search: 'Financial Institutions Rating Criteria'",
            "3. If embedded in iframe: Cmd+P → Save as PDF",
            "4. Save to: rating_agency/standard_poors_rating.pdf",
        ],
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-manual", action="store_true")
    parser.add_argument("--reprocess",   action="store_true")
    args = parser.parse_args()

    log = {"run_at": datetime.now().isoformat(), "docs": {}}

    print(f"\nRating Agency + Regulatory Document Downloader")
    print(f"Output: {RATING_DIR}\n")

    groups = {
        "BIS / Basel Committee":      [k for k in AUTOMATED_DOCS if k.startswith("bas") or k.startswith("bis")],
        "OCC Comptroller's Handbook": [k for k in AUTOMATED_DOCS if k.startswith("occ")],
        "FDIC":                       [k for k in AUTOMATED_DOCS if k.startswith("fdic")],
        "PRA / Bank of England":      [k for k in AUTOMATED_DOCS if k.startswith("pra")],
        "EBA":                        [k for k in AUTOMATED_DOCS if k.startswith("eba")],
        "Federal Reserve":            [k for k in AUTOMATED_DOCS if k.startswith("fed")],
        "IMF GFSR Reports":           [k for k in AUTOMATED_DOCS if k.startswith("imf_gfsr")],
        "IMF FSAP Reports":           [k for k in AUTOMATED_DOCS if k.startswith("imf_fsap")],
        "IMF Working Papers":         [k for k in AUTOMATED_DOCS if k.startswith("imf_wp")],
    }

    downloaded = failed = 0

    for group_name, filenames in groups.items():
        if not filenames:
            continue
        print(f"\n{'─'*60}")
        print(f" {group_name}")
        print(f"{'─'*60}")
        for filename in filenames:
            meta = AUTOMATED_DOCS[filename]
            dest = RATING_DIR / filename
            if args.reprocess and dest.exists():
                dest.unlink()
            result = download(meta["url"], dest, meta["description"])
            log["docs"][filename] = {"status": "ok" if result else "failed"}
            if result:
                downloaded += 1
            else:
                failed += 1
            time.sleep(0.3)

    if not args.skip_manual:
        print(f"\n{'='*60}")
        print(" MANUAL DOWNLOADS (free registration required)")
        print(f"{'='*60}")
        for filename, meta in MANUAL_DOCS.items():
            dest = RATING_DIR / filename
            if is_valid_pdf(dest):
                size_mb = dest.stat().st_size / 1_048_576
                if meta.get("check_scanned") and size_mb < 5:
                    print(f"\n⚠️  {meta['description']} — SCANNED ({size_mb:.1f}MB) — replace:")
                    for step in meta["steps"]:
                        print(f"   {step}")
                else:
                    info(f"{filename} — valid PDF ({size_mb:.1f}MB) ✅")
            else:
                print(f"\n⬜ {meta['description']}")
                for step in meta["steps"]:
                    print(f"   {step}")

    all_files = list(RATING_DIR.glob("*.pdf"))
    valid = sum(1 for f in all_files if is_valid_pdf(f))
    print(f"\n{'='*60}")
    print(f" SUMMARY")
    print(f"{'='*60}")
    print(f" Files in rating_agency/ : {len(all_files)}")
    print(f" Valid PDFs              : {valid}")
    print(f" Downloaded this run     : {downloaded}")
    print(f" Failed                  : {failed}")
    print(f"\n Next: ./run.sh --reprocess")

    with open(LOGS_DIR / "rating_agency_download_log.json", "w") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    main()
