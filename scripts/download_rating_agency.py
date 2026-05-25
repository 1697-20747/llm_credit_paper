#!/usr/bin/env python3
"""
download_rating_agency.py
=========================
Downloads freely available rating agency methodology and regulatory
documents. All sources are fully public — no registration required.

Usage:
    python scripts/download_rating_agency.py
    python scripts/download_rating_agency.py --dry-run
    python scripts/download_rating_agency.py --priority 1  # highest priority only
"""

import re
import json
import time
import ssl
import argparse
import urllib.request
import urllib.error
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
RED    = '\033[0;31m'; CYAN   = '\033[0;36m'; NC = '\033[0m'
def info(msg):   print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg):   print(f"{YELLOW}[WARN]{NC}  {msg}")
def error(msg):  print(f"{RED}[ERROR]{NC} {msg}")
def action(msg): print(f"{CYAN}[GET]{NC}   {msg}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
}

DOCUMENTS = [

    # ── FDIC ──────────────────────────────────────────────────────────────────
    {
        "filename":    "fdic_camels_rating_system.pdf",
        "url":         "https://www.fdic.gov/regulations/safety/manual/section6-1.pdf",
        "url_alt":     "https://www.fdic.gov/bank/individual/financial/index.html",
        "description": "FDIC — CAMELS Rating System (Section 6.1)",
        "category":    "camels_methodology",
        "priority":    1,
        "manual_url":  "https://www.fdic.gov/regulations/safety/manual/",
        "manual_note": "Navigate to Section 6.1 — CAMELS Rating System",
    },
    {
        "filename":    "fdic_bank_examination_overview.pdf",
        "url":         "https://www.fdic.gov/regulations/safety/manual/section1-1.pdf",
        "description": "FDIC — Risk Management Examination Manual Overview",
        "category":    "camels_methodology",
        "priority":    1,
    },

    # ── Federal Reserve ───────────────────────────────────────────────────────
    {
        "filename":    "fed_sr9638_rfi_rating_system.pdf",
        "url":         "https://www.federalreserve.gov/boarddocs/srletters/1996/sr9638.pdf",
        "description": "Federal Reserve SR 96-38 — RFI/C(D) Rating System for BHCs",
        "category":    "camels_methodology",
        "priority":    1,
        "manual_url":  "https://www.federalreserve.gov/apps/srletters/srletters.aspx",
        "manual_note": "Search SR 96-38",
    },
    {
        "filename":    "fed_commercial_bank_exam_manual.pdf",
        "url":         "https://www.federalreserve.gov/publications/files/commercial_bank_examination_manual.pdf",
        "description": "Federal Reserve — Commercial Bank Examination Manual",
        "category":    "camels_methodology",
        "priority":    1,
    },

    # ── Basel Committee (BIS) — all reliably downloadable ─────────────────────
    {
        "filename":    "basel_committee_core_principles.pdf",
        "url":         "https://www.bis.org/publ/bcbs230.pdf",
        "description": "Basel Committee — Core Principles for Effective Banking Supervision",
        "category":    "regulatory_standard",
        "priority":    1,
    },
    {
        "filename":    "basel_iii_capital_framework.pdf",
        "url":         "https://www.bis.org/publ/bcbs189.pdf",
        "description": "Basel III — Global regulatory framework for resilient banks",
        "category":    "capital_methodology",
        "priority":    1,
    },
    {
        "filename":    "basel_iv_output_floor.pdf",
        "url":         "https://www.bis.org/bcbs/publ/d424.pdf",
        "description": "Basel III Finalising post-crisis reforms (Basel IV)",
        "category":    "capital_methodology",
        "priority":    1,
    },
    {
        "filename":    "basel_lcr_standard.pdf",
        "url":         "https://www.bis.org/publ/bcbs238.pdf",
        "description": "Basel III — Liquidity Coverage Ratio",
        "category":    "liquidity_methodology",
        "priority":    1,
    },
    {
        "filename":    "basel_nsfr_standard.pdf",
        "url":         "https://www.bis.org/bcbs/publ/d295.pdf",
        "description": "Basel III — Net Stable Funding Ratio",
        "category":    "liquidity_methodology",
        "priority":    1,
    },
    {
        "filename":    "basel_irrbb_standard.pdf",
        "url":         "https://www.bis.org/bcbs/publ/d368.pdf",
        "description": "Basel Committee — Interest Rate Risk in the Banking Book (IRRBB)",
        "category":    "market_risk",
        "priority":    1,
    },
    {
        "filename":    "basel_leverage_ratio.pdf",
        "url":         "https://www.bis.org/bcbs/publ/d365.pdf",
        "description": "Basel III — Leverage ratio framework",
        "category":    "capital_methodology",
        "priority":    1,
    },
    {
        "filename":    "bis_working_paper_bank_ratings.pdf",
        "url":         "https://www.bis.org/publ/work595.pdf",
        "description": "BIS Working Paper 595 — Bank ratings and supervisors",
        "category":    "rating_methodology",
        "priority":    2,
    },
    {
        "filename":    "bis_working_paper_camels_ratings.pdf",
        "url":         "https://www.bis.org/publ/work822.pdf",
        "description": "BIS Working Paper 822 — CAMELS ratings and bank fragility",
        "category":    "camels_methodology",
        "priority":    1,
    },

    # ── OCC Comptroller's Handbook — all reliably downloadable ────────────────
    {
        "filename":    "occ_bank_supervision_process.pdf",
        "url":         "https://www.occ.treas.gov/publications-and-resources/publications/comptrollers-handbook/files/bank-supervision-process/pub-ch-bank-supervision-process.pdf",
        "description": "OCC Comptroller's Handbook — Bank Supervision Process (CAMELS)",
        "category":    "camels_methodology",
        "priority":    1,
    },
    {
        "filename":    "occ_liquidity_handbook.pdf",
        "url":         "https://www.occ.treas.gov/publications-and-resources/publications/comptrollers-handbook/files/liquidity/pub-ch-liquidity.pdf",
        "description": "OCC Comptroller's Handbook — Liquidity",
        "category":    "liquidity_methodology",
        "priority":    1,
    },
    {
        "filename":    "occ_loan_portfolio_management.pdf",
        "url":         "https://www.occ.treas.gov/publications-and-resources/publications/comptrollers-handbook/files/loan-portfolio-management/pub-ch-loan-portfolio-management.pdf",
        "description": "OCC Comptroller's Handbook — Loan Portfolio Management",
        "category":    "asset_quality",
        "priority":    1,
    },
    {
        "filename":    "occ_capital_adequacy.pdf",
        "url":         "https://www.occ.treas.gov/publications-and-resources/publications/comptrollers-handbook/files/capital-adequacy/pub-ch-capital-adequacy.pdf",
        "description": "OCC Comptroller's Handbook — Capital Adequacy",
        "category":    "capital_methodology",
        "priority":    1,
    },
    {
        "filename":    "occ_earnings_handbook.pdf",
        "url":         "https://www.occ.treas.gov/publications-and-resources/publications/comptrollers-handbook/files/earnings/pub-ch-earnings.pdf",
        "description": "OCC Comptroller's Handbook — Earnings",
        "category":    "earnings_methodology",
        "priority":    1,
    },
    {
        "filename":    "occ_sensitivity_market_risk.pdf",
        "url":         "https://www.occ.treas.gov/publications-and-resources/publications/comptrollers-handbook/files/sensitivity-to-market-risk/pub-ch-sensitivity-to-market-risk.pdf",
        "description": "OCC Comptroller's Handbook — Sensitivity to Market Risk",
        "category":    "market_risk",
        "priority":    1,
    },

    # ── EBA ───────────────────────────────────────────────────────────────────
    {
        "filename":    "eba_srep_guidelines_2018.pdf",
        "url":         "https://www.eba.europa.eu/sites/default/files/documents/10180/2002660/f5648ae8-a32e-4e8a-82d7-ba6ce0778b18/Final%20Guidelines%20on%20SREP%20and%20Pillar%202.pdf",
        "description": "EBA Guidelines on SREP and Pillar 2 (2018)",
        "category":    "regulatory_guidance",
        "priority":    1,
    },
    {
        "filename":    "eba_npl_guidelines.pdf",
        "url":         "https://www.eba.europa.eu/sites/default/files/documents/10180/2425773/b4614e97-fcd6-4bd9-8c89-80f9b98eb5d4/EBA%20GL%202018%2006%20Guidelines%20on%20management%20of%20non-performing%20exposures.pdf",
        "description": "EBA Guidelines on management of non-performing exposures",
        "category":    "asset_quality",
        "priority":    1,
    },
    {
        "filename":    "eba_stress_test_methodology_2023.pdf",
        "url":         "https://www.eba.europa.eu/sites/default/files/document_library/Risk%20Analysis%20and%20Data/EU-wide%20Stress%20Testing/2023/2551228/2023%20EU-wide%20stress%20test%20-%20Methodological%20Note.pdf",
        "description": "EBA 2023 EU-wide Stress Test Methodological Note",
        "category":    "stress_testing",
        "priority":    2,
    },

    # ── Bank of England / PRA — direct PDF links ──────────────────────────────
    {
        "filename":    "pra_approach_banking_supervision.pdf",
        "url":         "https://www.bankofengland.co.uk/-/media/boe/files/prudential-regulation/approach/banking-approach-2018.pdf",
        "description": "PRA — The Prudential Regulation Authority's approach to banking supervision",
        "category":    "regulatory_guidance",
        "priority":    1,
    },
    {
        "filename":    "pra_icaap_ilaap_supervisory_expectations.pdf",
        "url":         "https://www.bankofengland.co.uk/-/media/boe/files/prudential-regulation/supervisory-statement/2023/ss315-update-sept-2023.pdf",
        "description": "PRA SS3/15 — The Internal Capital Adequacy Assessment Process (ICAAP)",
        "category":    "capital_methodology",
        "priority":    1,
    },

    # ── IMF ───────────────────────────────────────────────────────────────────
    {
        "filename":    "imf_financial_soundness_indicators.pdf",
        "url":         "https://www.imf.org/en/Publications/Manuals-Guides/Issues/2019/05/21/Financial-Soundness-Indicators-Compilation-Guide-46113",
        "description": "IMF Financial Soundness Indicators Compilation Guide 2019",
        "category":    "camels_methodology",
        "priority":    1,
        "manual_url":  "https://www.imf.org/en/Publications/Manuals-Guides/Issues/2019/05/21/Financial-Soundness-Indicators-Compilation-Guide-46113",
        "manual_note": "Click Download PDF",
    },
    {
        "filename":    "imf_fsi_guide_2019.pdf",
        "url":         "https://www.imf.org/-/media/Files/Publications/manuals-guides/2019/fsi-compilation-guide.ashx",
        "description": "IMF Financial Soundness Indicators Guide 2019 (direct PDF)",
        "category":    "camels_methodology",
        "priority":    1,
    },
]

# ── Manual download list — good sources that need browser/registration ────────
MANUAL_DOWNLOADS = [
    {
        "filename":    "moodys_banks_rating_methodology.pdf",
        "url":         "https://www.moodys.com/researchandratings/research-type/ratings-methodologies",
        "description": "Moody's Banks Rating Methodology",
        "note":        "Free registration required. Search 'Banks' methodology.",
    },
    {
        "filename":    "sp_banks_rating_methodology.pdf",
        "url":         "https://www.spglobal.com/ratings/en/research-insights/criteria",
        "description": "S&P Global — Banks Rating Methodology (you may already have this)",
        "note":        "Free registration. Search 'Banks' criteria.",
    },
    {
        "filename":    "dbrs_global_banks_methodology.pdf",
        "url":         "https://dbrs.morningstar.com/research/398692",
        "description": "DBRS Morningstar — Global Methodology for Rating Banks (free, no login)",
        "note":        "No registration needed. Direct download.",
    },
    {
        "filename":    "fdic_camels_rating_system.pdf",
        "url":         "https://www.fdic.gov/regulations/safety/manual/",
        "description": "FDIC Risk Management Manual Section 6.1 — CAMELS",
        "note":        "Navigate to Section 6 → 6.1 Uniform Financial Institutions Rating System",
    },
]


def http_get_bytes(url: str, timeout: int = 60) -> bytes | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=timeout) as r:
            data = r.read()
            # Reject HTML pages returned instead of PDFs
            if data[:5] in (b"%PDF-", b"%PDF "):
                return data   # genuine PDF
            if b"<!DOCTYPE" in data[:200] or b"<html" in data[:200].lower():
                return None   # HTML error page
            if len(data) > 50_000:
                return data   # large enough — probably fine
            return None
    except urllib.error.HTTPError as e:
        if e.code not in (404, 403):
            error(f"  HTTP {e.code}: {url[-70:]}")
        return None
    except Exception as e:
        error(f"  Failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--priority", type=int, default=2,
                        help="Max priority level to download (1=critical only, 2=all)")
    args = parser.parse_args()

    docs = [d for d in DOCUMENTS if d.get("priority", 2) <= args.priority]
    docs.sort(key=lambda d: d.get("priority", 2))

    print(f"\nRating Agency & Regulatory Document Downloader")
    print(f"Documents to attempt: {len(docs)}")
    print(f"Output: {RATING_DIR}\n")

    log = {"run_at": datetime.now().isoformat(), "results": []}
    downloaded, skipped, failed = 0, 0, 0
    failed_list = []

    for doc in docs:
        dest_path = RATING_DIR / doc["filename"]

        print(f"[P{doc.get('priority',2)}] {doc['description'][:65]}")

        if dest_path.exists() and dest_path.stat().st_size > 10_000:
            size_kb = dest_path.stat().st_size // 1024
            info(f"  Already have: {doc['filename']} ({size_kb}KB)")
            log["results"].append({"file": doc["filename"], "status": "exists"})
            skipped += 1
            continue

        if args.dry_run:
            action(f"  Would download: {doc['url'][-65:]}")
            continue

        action(f"  {doc['url'][-65:]}")
        content = http_get_bytes(doc["url"])

        if content and len(content) > 10_000:
            dest_path.write_bytes(content)
            size_kb = len(content) // 1024
            info(f"  ✅ {doc['filename']} ({size_kb}KB)")
            log["results"].append({"file": doc["filename"], "status": "downloaded",
                                   "size_kb": size_kb})
            downloaded += 1
        else:
            warn(f"  ⚠️  Failed")
            log["results"].append({"file": doc["filename"], "status": "failed",
                                   "url": doc["url"]})
            failed += 1
            failed_list.append(doc)

        time.sleep(0.3)

    # ── Write log ─────────────────────────────────────────────────────────────
    log_path = LOGS_DIR / "rating_agency_download_log.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Downloaded  : {downloaded}")
    print(f"Already had : {skipped}")
    print(f"Failed      : {failed}")

    if failed_list:
        print(f"\nFailed downloads — try these manually:")
        for doc in failed_list:
            manual_url  = doc.get("manual_url", doc["url"])
            manual_note = doc.get("manual_note", "")
            print(f"  • {doc['description']}")
            print(f"    Save as: rating_agency/{doc['filename']}")
            print(f"    URL: {manual_url}")
            if manual_note:
                print(f"    Note: {manual_note}")
            print()

    print(f"\nMANUAL DOWNLOADS (registration/browser required):")
    for doc in MANUAL_DOWNLOADS:
        exists = (RATING_DIR / doc["filename"]).exists()
        status = "✅ already have" if exists else "⬜ needed"
        print(f"  {status} {doc['description']}")
        if not exists:
            print(f"    URL:  {doc['url']}")
            print(f"    Save: rating_agency/{doc['filename']}")
            print(f"    Note: {doc['note']}")
        print()

    all_files = list(RATING_DIR.glob("*.pdf"))
    print(f"Total files in rating_agency/: {len(all_files)}")
    print(f"\nNext: ./run.sh --reprocess\n")


if __name__ == "__main__":
    main()
