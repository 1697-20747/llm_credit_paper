#!/usr/bin/env python3
"""
download_pillar3.py
===================
Downloads Pillar 3 (risk disclosure) reports for major banks.

Pillar 3 reports are published alongside annual reports and contain
far more granular risk data than the annual report alone:
  - Detailed RWA breakdown by risk type and business line
  - Credit risk IRB model outputs (PD, LGD, EAD by portfolio)
  - Market risk VaR and stressed VaR detail
  - Liquidity risk (LCR, NSFR, HQLA composition)
  - Counterparty credit risk (CVA)
  - Leverage ratio detail
  - Capital instruments and TLAC/MREL
  - Remuneration disclosures

Under CRR2/CRD5 (EU) and PRA rules (UK), systemically important banks
must publish Pillar 3 reports — all are freely available on bank IR pages.

For US banks, similar disclosures appear in:
  - FR Y-9C filings (BHC data)
  - DFAST stress test results (Federal Reserve)
  - Resolution plan summaries (living wills)

Usage:
    python scripts/download_pillar3.py
    python scripts/download_pillar3.py --years 3
    python scripts/download_pillar3.py --dry-run

Output:
    pillar3/<bank>_<year>_pillar3.pdf
    logs/pillar3_download_log.json
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

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
PILLAR3_DIR   = PROJECT_ROOT / "pillar3"
LOGS_DIR      = PROJECT_ROOT / "logs"
PILLAR3_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Create README
readme = PILLAR3_DIR / "README.txt"
if not readme.exists():
    readme.write_text(
        "Pillar 3 Risk Disclosure Reports\n"
        "=================================\n"
        "Place bank Pillar 3 PDFs here OR run:\n"
        "  python scripts/download_pillar3.py\n\n"
        "Files are processed by 02_extract_financials.py with\n"
        "enhanced Pillar 3 section detection.\n\n"
        "Naming convention:\n"
        "  <bank>_<year>_pillar3.pdf\n"
        "  e.g. lloyds_banking_group_2024_pillar3.pdf\n"
    )

GREEN = '\033[0;32m'; YELLOW = '\033[1;33m'
RED   = '\033[0;31m'; CYAN   = '\033[0;36m'; NC = '\033[0m'
def info(msg):   print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg):   print(f"{YELLOW}[WARN]{NC}  {msg}")
def action(msg): print(f"{CYAN}[GET]{NC}   {msg}")
def manual(msg): print(f"{YELLOW}[MANUAL]{NC} {msg}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
}

# ─────────────────────────────────────────────────────────────────────────────
# PILLAR 3 REPORT URLS
# All are direct PDF links from bank IR pages — fully public
# ─────────────────────────────────────────────────────────────────────────────

PILLAR3_BANKS = {

    # ── UK BANKS ──────────────────────────────────────────────────────────────
    "lloyds_banking_group": {
        "display": "Lloyds Banking Group",
        "reports": {
            "2024": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2024/2024-lbg-pillar-3-report.pdf",
            "2023": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2023/2023-lbg-pillar-3-report.pdf",
            "2022": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2022/2022-lbg-pillar-3-report.pdf",
            "2021": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2021/2021-lbg-pillar-3-report.pdf",
        },
        "ir_page": "https://www.lloydsbankinggroup.com/investors/financial-performance/pillar-3-disclosures.html",
    },
    "hsbc_holdings": {
        "display": "HSBC Holdings",
        "reports": {
            "2024": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2024/annual/pdfs/hsbc-holdings-plc/240226-pillar3-2024.pdf",
            "2023": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2023/annual/pdfs/hsbc-holdings-plc/230221-pillar3-2023.pdf",
            "2022": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2022/annual/pdfs/hsbc-holdings-plc/220222-pillar3-2022.pdf",
        },
        "ir_page": "https://www.hsbc.com/investors/results-and-announcements/annual-report",
    },
    "barclays": {
        "display": "Barclays PLC",
        "reports": {
            "2024": "https://home.barclays/content/dam/home-barclays/documents/investor-relations/reports-and-events/annual-reports/2024/2024-barclays-plc-pillar-3-report.pdf",
            "2023": "https://home.barclays/content/dam/home-barclays/documents/investor-relations/reports-and-events/annual-reports/2023/2023-barclays-plc-pillar-3-report.pdf",
            "2022": "https://home.barclays/content/dam/home-barclays/documents/investor-relations/reports-and-events/annual-reports/2022/2022-barclays-plc-pillar-3-report.pdf",
        },
        "ir_page": "https://home.barclays/investor-relations/reports-and-events/annual-reports/",
    },
    "natwest_group": {
        "display": "NatWest Group",
        "reports": {
            "2024": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2025/natwest-group-2024-pillar-3-report.pdf",
            "2023": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2024/natwest-group-2023-pillar-3-report.pdf",
            "2022": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2023/natwest-group-2022-pillar-3-report.pdf",
        },
        "ir_page": "https://investors.natwestgroup.com/results-and-presentations/annual-reports",
    },
    "standard_chartered": {
        "display": "Standard Chartered",
        "reports": {
            "2024": "https://av.sc.com/corp-en/content/docs/standard-chartered-pillar3-2024.pdf",
            "2023": "https://av.sc.com/corp-en/content/docs/standard-chartered-pillar3-2023.pdf",
            "2022": "https://av.sc.com/corp-en/content/docs/standard-chartered-pillar3-2022.pdf",
        },
        "ir_page": "https://www.sc.com/en/investors/",
    },

    # ── EUROPEAN BANKS ────────────────────────────────────────────────────────
    "deutsche_bank": {
        "display": "Deutsche Bank",
        "reports": {
            "2024": "https://investor-relations.db.com/files/documents/annual-reports/2024/Deutsche-Bank-Pillar-3-Report-2024.pdf",
            "2023": "https://investor-relations.db.com/files/documents/annual-reports/2023/Deutsche-Bank-Pillar-3-Report-2023.pdf",
            "2022": "https://investor-relations.db.com/files/documents/annual-reports/2022/Deutsche-Bank-Pillar-3-Report-2022.pdf",
        },
        "ir_page": "https://investor-relations.db.com/reports-and-events/annual-reports",
    },
    "bnp_paribas": {
        "display": "BNP Paribas",
        "reports": {
            "2024": "https://invest.bnpparibas/sites/default/files/documents/bnp_paribas_pillar3_2024.pdf",
            "2023": "https://invest.bnpparibas/sites/default/files/documents/bnp_paribas_pillar3_2023.pdf",
        },
        "ir_page": "https://invest.bnpparibas/en/document-type/pillar-3",
    },
    "unicredit": {
        "display": "UniCredit",
        "reports": {
            "2024": "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2024/FY/UniCredit-Pillar3-2024.pdf",
            "2023": "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2023/FY/UniCredit-Pillar3-2023.pdf",
        },
        "ir_page": "https://www.unicreditgroup.eu/en/investors/financial-reports.html",
    },

    # ── US BANKS (Pillar 3 / Basel disclosures) ───────────────────────────────
    # US banks publish equivalent disclosures but not always called "Pillar 3"
    # Fed DFAST results are the closest equivalent for capital stress testing
    "jpmorgan_chase": {
        "display": "JPMorgan Chase",
        "reports": {
            "2024": "https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/investor-relations/documents/basel-disclosures/basel-3-pillar-3-capital-disclosures-4q2024.pdf",
            "2023": "https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/investor-relations/documents/basel-disclosures/basel-3-pillar-3-capital-disclosures-4q2023.pdf",
        },
        "ir_page": "https://www.jpmorganchase.com/ir/basel-disclosures",
    },
    "bank_of_america": {
        "display": "Bank of America",
        "reports": {
            "2024": "https://investor.bankofamerica.com/regulatory-and-other-filings/basel-disclosures/default.aspx",
        },
        "ir_page": "https://investor.bankofamerica.com/regulatory-and-other-filings/basel-disclosures",
        "manual": True,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Download helpers
# ─────────────────────────────────────────────────────────────────────────────

def http_get_bytes(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=120) as r:
            data = r.read()
            # Verify it's actually a PDF
            if data[:4] == b'%PDF' or len(data) > 100_000:
                return data
            return None
    except urllib.error.HTTPError as e:
        if e.code != 404:
            warn(f"  HTTP {e.code}: {url[-60:]}")
        return None
    except Exception as e:
        warn(f"  Failed: {e}")
        return None


def already_have(bank_key: str, year: str) -> bool:
    patterns = [
        f"{bank_key}_{year}_pillar3.pdf",
        f"{bank_key}_{year}_pillar_3.pdf",
        f"{bank_key}_{year}_p3.pdf",
    ]
    return any((PILLAR3_DIR / p).exists() for p in patterns)


def download_bank_pillar3(bank_key: str, bank: dict,
                           years: list, dry_run: bool) -> dict:
    display  = bank["display"]
    reports  = bank.get("reports", {})
    is_manual = bank.get("manual", False)
    results  = {}

    info(f"\n{display}")

    for year in years:
        if already_have(bank_key, year):
            info(f"  {year}: already have ✅")
            results[year] = "exists"
            continue

        url = reports.get(year)
        if not url:
            if is_manual:
                manual(f"  {year}: manual download → {bank.get('ir_page','')}")
            else:
                warn(f"  {year}: no URL configured")
            results[year] = "no_url"
            continue

        if dry_run:
            action(f"  {year}: would download {url[-60:]}")
            results[year] = "dry_run"
            continue

        action(f"  {year}: {url[-65:]}")
        content = http_get_bytes(url)

        if content and len(content) > 100_000:
            dest = PILLAR3_DIR / f"{bank_key}_{year}_pillar3.pdf"
            dest.write_bytes(content)
            size_mb = len(content) / 1_048_576
            info(f"  ✅ {dest.name} ({size_mb:.1f}MB)")
            results[year] = "downloaded"
        else:
            warn(f"  {year}: download failed or too small")
            results[year] = "failed"

        time.sleep(0.5)

    return results


def print_manual_checklist(years: list):
    """Print manual download list for banks that can't be automated."""
    manual_banks = {k: v for k, v in PILLAR3_BANKS.items()
                    if v.get("manual", False)}
    if not manual_banks:
        return

    print(f"\n{'='*60}")
    print(f"MANUAL PILLAR 3 DOWNLOADS")
    print(f"{'='*60}")
    for bank_key, bank in manual_banks.items():
        print(f"\n  {bank['display']}")
        print(f"  IR Page: {bank.get('ir_page','')}")
        for year in years:
            fname  = f"{bank_key}_{year}_pillar3.pdf"
            status = "✅" if (PILLAR3_DIR / fname).exists() else "⬜"
            print(f"    {status} {year}: save as pillar3/{fname}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years",   type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--banks",   nargs="*", default=None)
    args = parser.parse_args()

    current_year = datetime.now().year
    years = [str(y) for y in range(current_year - 1,
                                   current_year - args.years - 1, -1)]

    print(f"\nPillar 3 Report Downloader")
    print(f"Years: {years} | Output: {PILLAR3_DIR}\n")

    if args.banks:
        bank_list = {k: v for k, v in PILLAR3_BANKS.items()
                     if any(b.lower() in k for b in args.banks)}
    else:
        bank_list = PILLAR3_BANKS

    log = {"run_at": datetime.now().isoformat(), "banks": {}}
    downloaded = skipped = 0

    for bank_key, bank in bank_list.items():
        results = download_bank_pillar3(
            bank_key, bank, years, dry_run=args.dry_run
        )
        log["banks"][bank_key] = results
        downloaded += sum(1 for v in results.values() if v == "downloaded")
        skipped    += sum(1 for v in results.values() if v == "exists")

    print_manual_checklist(years)

    if not args.dry_run:
        log_path = LOGS_DIR / "pillar3_download_log.json"
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2)

    all_files = list(PILLAR3_DIR.glob("*.pdf"))
    print(f"\n{'='*60}")
    print(f"Downloaded  : {downloaded}")
    print(f"Already had : {skipped}")
    print(f"Total in pillar3/ : {len(all_files)}")
    print(f"\nNext: ./run.sh --reprocess")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
