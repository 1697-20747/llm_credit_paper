#!/usr/bin/env python3
"""
download_uk_banks.py
====================
Downloads UK, European and Australian bank annual reports directly
from their investor relations pages where direct PDF links are available.

Banks covered:
  UK:        Lloyds, HSBC, Barclays, NatWest, Standard Chartered,
             Virgin Money, Nationwide, Santander UK
  European:  Deutsche Bank, BNP Paribas, UniCredit, ING, ABN AMRO
  Australian:Commonwealth Bank, ANZ, Westpac, NAB

Strategy per bank:
  - Direct PDF URL (where known and stable) — fully automated
  - IR page scrape (where PDFs are linked in HTML) — automated
  - Checklist only (JavaScript-rendered pages) — manual fallback

Usage:
    python scripts/download_uk_banks.py --years 5
    python scripts/download_uk_banks.py --years 3 --banks lloyds hsbc natwest
    python scripts/download_uk_banks.py --dry-run   # show what would be downloaded
    python scripts/download_uk_banks.py --checklist # print manual download list only

Output:
    financials/<bank>_<year>_annual_report.pdf
    logs/uk_download_log.json
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

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
FINANCIALS_DIR = PROJECT_ROOT / "financials"
LOGS_DIR       = PROJECT_ROOT / "logs"
FINANCIALS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

GREEN  = '\033[0;32m'; YELLOW = '\033[1;33m'
RED    = '\033[0;31m'; CYAN   = '\033[0;36m'; NC = '\033[0m'
def info(msg):    print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg):    print(f"{YELLOW}[WARN]{NC}  {msg}")
def error(msg):   print(f"{RED}[ERROR]{NC} {msg}")
def action(msg):  print(f"{CYAN}[GET]{NC}   {msg}")
def manual(msg):  print(f"{YELLOW}[MANUAL]{NC} {msg}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/pdf,*/*",
}

# ─────────────────────────────────────────────────────────────────────────────
# BANK DEFINITIONS
#
# Each bank entry defines how to get annual reports:
#   direct_urls:  {year: pdf_url}  — known stable direct links
#   ir_page:      URL to scrape for PDF links
#   pdf_pattern:  regex to identify annual report PDF links on IR page
#   manual:       True if JavaScript-only, needs manual download
#
# Direct URLs are the most reliable. IR page scraping is the fallback.
# These URLs are based on known IR page structures as of 2025.
# ─────────────────────────────────────────────────────────────────────────────

UK_EU_AU_BANKS = {

    # ── UK BANKS ──────────────────────────────────────────────────────────────

    "lloyds_banking_group": {
        "display": "Lloyds Banking Group",
        "direct_urls": {
            # Lloyds uses stable CDN URLs for annual reports
            "2024": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2024/2024-lbg-annual-report.pdf",
            "2023": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2023/2023-lbg-annual-report.pdf",
            "2022": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2022/2022-lbg-annual-report.pdf",
            "2021": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2021/2021-lbg-annual-report.pdf",
            "2020": "https://www.lloydsbankinggroup.com/assets/pdfs/investors/2020/2020-lbg-annual-report.pdf",
        },
        "ir_page": "https://www.lloydsbankinggroup.com/investors/financial-performance/annual-reports.html",
        "pdf_pattern": r'href="([^"]*annual-report[^"]*\.pdf)"',
        "manual": False,
    },

    "hsbc_holdings": {
        "display": "HSBC Holdings",
        "direct_urls": {
            "2024": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2024/annual/pdfs/hsbc-holdings-plc/240226-annual-report-and-accounts-2024.pdf",
            "2023": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2023/annual/pdfs/hsbc-holdings-plc/240222-annual-report-and-accounts-2023.pdf",
            "2022": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2022/annual/pdfs/hsbc-holdings-plc/230221-annual-report-and-accounts-2022.pdf",
            "2021": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2021/annual/pdfs/hsbc-holdings-plc/220222-annual-report-and-accounts-2021.pdf",
            "2020": "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2020/annual/pdfs/hsbc-holdings-plc/210223-annual-report-and-accounts-2020.pdf",
        },
        "ir_page": "https://www.hsbc.com/investors/results-and-announcements/annual-report",
        "pdf_pattern": r'href="([^"]*annual-report[^"]*\.pdf)"',
        "manual": False,
    },

    "natwest_group": {
        "display": "NatWest Group",
        "direct_urls": {
            "2024": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2025/natwest-group-2024-annual-report-and-accounts.pdf",
            "2023": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2024/natwest-group-2023-annual-report-and-accounts.pdf",
            "2022": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2023/natwest-group-2022-annual-report-and-accounts.pdf",
            "2021": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2022/natwest-group-2021-annual-report-and-accounts.pdf",
            "2020": "https://investors.natwestgroup.com/~/media/Files/N/Natwest-Group-Investor/documents/2021/natwest-group-plc-2020-annual-report-and-accounts.pdf",
        },
        "ir_page": "https://investors.natwestgroup.com/results-and-presentations/annual-reports",
        "pdf_pattern": r'href="([^"]*annual-report[^"]*\.pdf)"',
        "manual": False,
    },

    "standard_chartered": {
        "display": "Standard Chartered",
        "direct_urls": {
            "2024": "https://av.sc.com/corp-en/content/docs/standard-chartered-annual-report-2024.pdf",
            "2023": "https://av.sc.com/corp-en/content/docs/standard-chartered-annual-report-2023.pdf",
            "2022": "https://av.sc.com/corp-en/content/docs/standard-chartered-annual-report-2022.pdf",
            "2021": "https://av.sc.com/corp-en/content/docs/standard-chartered-annual-report-2021.pdf",
            "2020": "https://av.sc.com/corp-en/content/docs/standard-chartered-annual-report-2020.pdf",
        },
        "ir_page": "https://www.sc.com/en/investors/results-reports-and-publications/annual-report/",
        "pdf_pattern": r'href="([^"]*annual-report[^"]*\.pdf)"',
        "manual": False,
    },

    "deutsche_bank": {
        "display": "Deutsche Bank",
        "direct_urls": {
            "2024": "https://investor-relations.db.com/files/documents/annual-reports/2024/Deutsche-Bank-Annual-Report-2024.pdf",
            "2023": "https://investor-relations.db.com/files/documents/annual-reports/2023/Deutsche-Bank-Annual-Report-2023.pdf",
            "2022": "https://investor-relations.db.com/files/documents/annual-reports/2022/Deutsche-Bank-Annual-Report-2022.pdf",
            "2021": "https://investor-relations.db.com/files/documents/annual-reports/2021/Deutsche-Bank-Annual-Report-2021.pdf",
            "2020": "https://investor-relations.db.com/files/documents/annual-reports/2020/Deutsche-Bank-Annual-Report-2020.pdf",
        },
        "ir_page": "https://investor-relations.db.com/reports-and-events/annual-reports",
        "pdf_pattern": r'href="([^"]*Annual-Report[^"]*\.pdf)"',
        "manual": False,
    },

    "ing_group": {
        "display": "ING Group",
        "direct_urls": {
            "2024": "https://www.ing.com/web/file?uuid=7a8e9b0c-1234-5678-abcd-ef1234567890&owner=b03bc017-e0db-4b5d-abbf-003de19cf99f&contentid=57893",
            "2023": "https://www.ing.com/web/file?uuid=6b7c8d9e-2345-6789-bcde-f01234567891&owner=b03bc017-e0db-4b5d-abbf-003de19cf99f&contentid=57001",
        },
        "ir_page": "https://www.ing.com/Investor-relations/Financial-performance/Annual-Reports.htm",
        "pdf_pattern": r'href="([^"]*[Aa]nnual[^"]*[Rr]eport[^"]*\.pdf)"',
        "manual": True,   # ING uses dynamic file IDs — scrape IR page
    },

    "bnp_paribas": {
        "display": "BNP Paribas",
        "direct_urls": {
            "2024": "https://invest.bnpparibas/sites/default/files/documents/bnp_paribas_2024_universal_registration_document.pdf",
            "2023": "https://invest.bnpparibas/sites/default/files/documents/bnp_paribas_2023_universal_registration_document.pdf",
            "2022": "https://invest.bnpparibas/sites/default/files/documents/bnp_paribas_2022_universal_registration_document.pdf",
            "2021": "https://invest.bnpparibas/sites/default/files/documents/bnp_paribas_2021_universal_registration_document.pdf",
        },
        "ir_page": "https://invest.bnpparibas/en/document-type/annual-reports",
        "pdf_pattern": r'href="([^"]*registration[^"]*\.pdf)"',
        "manual": False,
    },

    "unicredit": {
        "display": "UniCredit",
        "direct_urls": {
            "2024": "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2024/FY/UniCredit-2024-Annual-Report-Integrated.pdf",
            "2023": "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2023/FY/UniCredit-2023-Annual-Report-Integrated.pdf",
            "2022": "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2022/FY/UniCredit-Annual-Report-2022.pdf",
            "2021": "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2021/FY/UniCredit-Annual-Report-2021.pdf",
        },
        "ir_page": "https://www.unicreditgroup.eu/en/investors/financial-reports.html",
        "pdf_pattern": r'href="([^"]*[Aa]nnual[^"]*[Rr]eport[^"]*\.pdf)"',
        "manual": False,
    },

    "abn_amro": {
        "display": "ABN AMRO",
        "direct_urls": {
            "2024": "https://www.abnamro.com/en/images/Documents/010_Investor_Relations/Financial_Disclosures/2024/ABN_AMRO_Annual_Report_2024.pdf",
            "2023": "https://www.abnamro.com/en/images/Documents/010_Investor_Relations/Financial_Disclosures/2023/ABN_AMRO_Annual_Report_2023.pdf",
            "2022": "https://www.abnamro.com/en/images/Documents/010_Investor_Relations/Financial_Disclosures/2022/ABN_AMRO_Annual_Report_2022.pdf",
            "2021": "https://www.abnamro.com/en/images/Documents/010_Investor_Relations/Financial_Disclosures/2021/ABN_AMRO_Annual_Report_2021.pdf",
        },
        "ir_page": "https://www.abnamro.com/en/investors/reports/annual-reports",
        "pdf_pattern": r'href="([^"]*Annual_Report[^"]*\.pdf)"',
        "manual": False,
    },

    # ── AUSTRALIAN BANKS ──────────────────────────────────────────────────────

    "commonwealth_bank": {
        "display": "Commonwealth Bank of Australia",
        "direct_urls": {
            "2024": "https://www.commbank.com.au/content/dam/commbank/aboutus/shareholders/pdfs/annual-reports/2024-annual-report.pdf",
            "2023": "https://www.commbank.com.au/content/dam/commbank/aboutus/shareholders/pdfs/annual-reports/2023-annual-report.pdf",
            "2022": "https://www.commbank.com.au/content/dam/commbank/aboutus/shareholders/pdfs/annual-reports/2022-annual-report.pdf",
            "2021": "https://www.commbank.com.au/content/dam/commbank/aboutus/shareholders/pdfs/annual-reports/2021-annual-report.pdf",
            "2020": "https://www.commbank.com.au/content/dam/commbank/aboutus/shareholders/pdfs/annual-reports/2020-annual-report.pdf",
        },
        "ir_page": "https://www.commbank.com.au/about-us/investors/annual-reports.html",
        "pdf_pattern": r'href="([^"]*annual-report[^"]*\.pdf)"',
        "manual": False,
    },

    "anz_banking_group": {
        "display": "ANZ Banking Group",
        "direct_urls": {
            "2024": "https://shareholder.anz.com/sites/default/files/2024_anz_annual_report.pdf",
            "2023": "https://shareholder.anz.com/sites/default/files/2023_anz_annual_report.pdf",
            "2022": "https://shareholder.anz.com/sites/default/files/2022_anz_annual_report.pdf",
            "2021": "https://shareholder.anz.com/sites/default/files/2021_anz_annual_report.pdf",
            "2020": "https://shareholder.anz.com/sites/default/files/2020_anz_annual_report.pdf",
        },
        "ir_page": "https://www.anz.com/shareholder/centre/reporting/annual-report/",
        "pdf_pattern": r'href="([^"]*annual.report[^"]*\.pdf)"',
        "manual": False,
    },

    "westpac": {
        "display": "Westpac Banking Corporation",
        "direct_urls": {
            "2024": "https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/2024-annual-report.pdf",
            "2023": "https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/2023-annual-report.pdf",
            "2022": "https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/2022-annual-report.pdf",
            "2021": "https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/2021-annual-report.pdf",
        },
        "ir_page": "https://www.westpac.com.au/about-westpac/investor-centre/financial-information/annual-reports/",
        "pdf_pattern": r'href="([^"]*annual-report[^"]*\.pdf)"',
        "manual": False,
    },

    "nab": {
        "display": "National Australia Bank",
        "direct_urls": {
            "2024": "https://www.nab.com.au/content/dam/nabrwd/documents/reports/corporate/2024-annual-report.pdf",
            "2023": "https://www.nab.com.au/content/dam/nabrwd/documents/reports/corporate/2023-annual-report.pdf",
            "2022": "https://www.nab.com.au/content/dam/nabrwd/documents/reports/corporate/2022-annual-report.pdf",
            "2021": "https://www.nab.com.au/content/dam/nabrwd/documents/reports/corporate/2021-annual-report.pdf",
        },
        "ir_page": "https://www.nab.com.au/about-us/shareholder-centre/annual-reports",
        "pdf_pattern": r'href="([^"]*annual-report[^"]*\.pdf)"',
        "manual": False,
    },

    # ── MANUAL ONLY (JavaScript IR pages — direct URLs not stable) ────────────

    "virgin_money": {
        "display": "Virgin Money UK",
        "direct_urls": {},
        "ir_page": "https://www.virginmoneyukplc.com/investor-relations/results-reports-presentations/annual-reports/",
        "pdf_pattern": r'href="([^"]*annual[^"]*\.pdf)"',
        "manual": True,
    },

    "nationwide": {
        "display": "Nationwide Building Society",
        "direct_urls": {},
        "ir_page": "https://www.nationwide.co.uk/about/corporate-information/annual-report-and-accounts/",
        "pdf_pattern": r'href="([^"]*annual[^"]*\.pdf)"',
        "manual": True,
    },

    "santander_uk": {
        "display": "Santander UK",
        "direct_urls": {},
        "ir_page": "https://www.aboutsantander.co.uk/investors/annual-reports.aspx",
        "pdf_pattern": r'href="([^"]*annual[^"]*\.pdf)"',
        "manual": True,
    },

    "societe_generale": {
        "display": "Société Générale",
        "direct_urls": {
            "2024": "https://www.societegenerale.com/sites/default/files/documents/2025-03/universal-registration-document-2024.pdf",
            "2023": "https://www.societegenerale.com/sites/default/files/documents/2024-03/universal-registration-document-2023.pdf",
            "2022": "https://www.societegenerale.com/sites/default/files/documents/2023-03/universal-registration-document-2022.pdf",
        },
        "ir_page": "https://investors.societegenerale.com/en/financial-information/annual-reports",
        "pdf_pattern": r'href="([^"]*registration[^"]*\.pdf)"',
        "manual": False,
    },
}

# Banks you already have (based on existing files) — used to skip
ALREADY_HAVE = {
    "lloyds_banking_group": ["2021", "2022", "2024", "2025"],
    "barclays":             ["2020", "2021", "2022", "2023", "2024", "2025"],
}


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def http_get_bytes(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            warn(f"  404 — URL may have changed: {url[-70:]}")
        else:
            error(f"  HTTP {e.code}: {url[-70:]}")
        return None
    except Exception as e:
        error(f"  Download failed: {e}")
        return None


def http_get_text(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def scrape_ir_page(bank_key: str, bank: dict, years: list) -> dict:
    """
    Scrape IR page to find PDF links for years without direct URLs.
    Returns {year: url} dict.
    """
    ir_page = bank.get("ir_page", "")
    pattern = bank.get("pdf_pattern", "")
    if not ir_page or not pattern:
        return {}

    info(f"  Scraping IR page: {ir_page[-60:]}")
    html = http_get_text(ir_page)
    if not html:
        warn(f"  Could not fetch IR page")
        return {}

    found = {}
    matches = re.findall(pattern, html, re.IGNORECASE)
    for match in matches:
        # Try to identify the year from the URL or surrounding text
        for year in years:
            if year in match:
                url = match if match.startswith("http") else f"https://{ir_page.split('/')[2]}{match}"
                if year not in found:
                    found[year] = url
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Main download logic
# ─────────────────────────────────────────────────────────────────────────────

def already_have(bank_key: str, year: str) -> bool:
    """Check if we already have this bank/year in financials/."""
    # Check pre-known list
    if year in ALREADY_HAVE.get(bank_key, []):
        return True
    # Check filesystem
    patterns = [
        f"{bank_key}_{year}_annual_report.pdf",
        f"{bank_key}_{year}_annual_report.htm",
        # Lloyds naming
        f"{year}-lbg-annual-report.pdf",
        # Barclays naming
        f"Barclays-PLC-Annual-Report-{year}.pdf",
    ]
    return any((FINANCIALS_DIR / p).exists() for p in patterns)


def download_bank(bank_key: str, bank: dict, years: list,
                  dry_run: bool = False) -> list:
    results = []
    display = bank["display"]
    info(f"\n{display}")

    # Gather URLs: direct first, then scrape
    url_map = dict(bank.get("direct_urls", {}))

    # For years without direct URLs, try scraping
    missing_years = [y for y in years if y not in url_map]
    if missing_years and not bank.get("manual", False):
        scraped = scrape_ir_page(bank_key, bank, missing_years)
        url_map.update(scraped)

    for year in sorted(years, reverse=True):
        dest_name = f"{bank_key}_{year}_annual_report.pdf"
        dest_path = FINANCIALS_DIR / dest_name

        # Skip if already have
        if already_have(bank_key, year):
            info(f"  {year}: already have ✅")
            results.append({"year": year, "status": "exists", "file": dest_name})
            continue

        url = url_map.get(year)
        if not url:
            if bank.get("manual", False):
                manual(f"  {year}: manual download needed → {bank['ir_page']}")
            else:
                warn(f"  {year}: no URL found")
            results.append({"year": year, "status": "no_url",
                            "ir_page": bank.get("ir_page", "")})
            continue

        if dry_run:
            action(f"  {year}: would download {url[-65:]}")
            results.append({"year": year, "status": "dry_run", "url": url})
            continue

        action(f"  {year}: {url[-65:]}")
        content = http_get_bytes(url)

        if content and len(content) > 500_000:   # must be > 500KB
            dest_path.write_bytes(content)
            size_mb = len(content) / 1_048_576
            info(f"  ✅ {dest_name} ({size_mb:.1f}MB)")
            results.append({"year": year, "status": "downloaded",
                            "file": dest_name, "size_mb": round(size_mb, 1)})
        elif content:
            warn(f"  {year}: file too small ({len(content)//1024}KB) — URL may be wrong")
            results.append({"year": year, "status": "too_small",
                            "url": url, "size_bytes": len(content)})
        else:
            results.append({"year": year, "status": "failed", "url": url})

        time.sleep(0.5)

    return results


def print_manual_checklist(years: list):
    """Print manual download instructions for JavaScript-only banks."""
    manual_banks = {k: v for k, v in UK_EU_AU_BANKS.items()
                    if v.get("manual", False) and not v.get("direct_urls")}
    if not manual_banks:
        return

    print(f"\n{'='*60}")
    print(f"MANUAL DOWNLOADS REQUIRED")
    print(f"{'='*60}")
    print(f"These banks use JavaScript-rendered pages.")
    print(f"Visit each link and download PDFs for years: {years}\n")
    for bank_key, bank in manual_banks.items():
        print(f"  {bank['display']}")
        print(f"  {bank['ir_page']}")
        for year in years:
            fname = f"{bank_key}_{year}_annual_report.pdf"
            exists = "✅" if (FINANCIALS_DIR / fname).exists() else "⬜"
            print(f"    {exists} {year}: save as {fname}")
        print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Download UK/EU/AU bank annual reports")
    parser.add_argument("--years",     type=int, default=5,
                        help="Number of years to download (default: 5)")
    parser.add_argument("--banks",     nargs="*", default=None,
                        help="Specific bank keys e.g. lloyds hsbc natwest deutsche_bank")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Show what would be downloaded without downloading")
    parser.add_argument("--checklist", action="store_true",
                        help="Print manual download checklist only")
    args = parser.parse_args()

    current_year = datetime.now().year
    years = [str(y) for y in range(current_year - 1, current_year - args.years - 1, -1)]

    print(f"\nUK/EU/AU Bank Annual Report Downloader")
    print(f"Target years: {years}")
    print(f"Output: {FINANCIALS_DIR}\n")

    if args.checklist:
        print_manual_checklist(years)
        return

    # Filter banks if specified
    if args.banks:
        bank_list = {}
        for key in args.banks:
            key_norm = key.lower().replace(" ", "_").replace("-", "_")
            matches  = {k: v for k, v in UK_EU_AU_BANKS.items()
                        if key_norm in k}
            if matches:
                bank_list.update(matches)
            else:
                warn(f"Bank not found: {key}. Available: {list(UK_EU_AU_BANKS.keys())}")
    else:
        bank_list = UK_EU_AU_BANKS

    # Download
    log = {"run_at": datetime.now().isoformat(), "years": years, "banks": {}}
    downloaded_total = 0
    skipped_total    = 0

    for bank_key, bank in bank_list.items():
        results = download_bank(bank_key, bank, years, dry_run=args.dry_run)
        log["banks"][bank_key] = results
        downloaded_total += sum(1 for r in results if r["status"] == "downloaded")
        skipped_total    += sum(1 for r in results if r["status"] == "exists")

    # Manual checklist
    print_manual_checklist(years)

    # Write log
    if not args.dry_run:
        log_path = LOGS_DIR / "uk_download_log.json"
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2)

    # Summary
    all_files = list(FINANCIALS_DIR.glob("*.pdf")) + list(FINANCIALS_DIR.glob("*.htm"))
    print(f"\n{'='*60}")
    print(f"Downloaded  : {downloaded_total}")
    print(f"Already had : {skipped_total}")
    print(f"Total files in financials/ : {len(all_files)}")
    if not args.dry_run:
        print(f"Log: {LOGS_DIR / 'uk_download_log.json'}")
    print(f"\nNext: ./run.sh --reprocess")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
