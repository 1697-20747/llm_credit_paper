#!/usr/bin/env python3
"""
download_financials.py
======================
Downloads bank annual reports from SEC EDGAR (US banks, fully automated)
and generates a checklist for UK/EU banks (manual download).

Uses the EDGAR filing viewer API which returns a proper typed document list,
avoiding the need to parse index HTML or guess from filenames.

Usage:
    python scripts/download_financials.py --source edgar --years 5
    python scripts/download_financials.py --source uk --years 5
    python scripts/download_financials.py --source all --years 5
    python scripts/download_financials.py --source edgar --banks "JPMorgan Chase"
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

# ── SSL fix for macOS Python 3.11 ─────────────────────────────────────────────
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

GREEN = '\033[0;32m'; YELLOW = '\033[1;33m'
RED   = '\033[0;31m'; CYAN   = '\033[0;36m'; NC = '\033[0m'
def info(msg):   print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg):   print(f"{YELLOW}[WARN]{NC}  {msg}")
def error(msg):  print(f"{RED}[ERROR]{NC} {msg}")
def action(msg): print(f"{CYAN}[GET]{NC}   {msg}")

US_BANKS = {
    "JPMorgan Chase":          "0000019617",
    "Bank of America":         "0000070858",
    "Wells Fargo":             "0000072971",
    "Citigroup":               "0000831001",
    "Goldman Sachs":           "0000886982",
    "Morgan Stanley":          "0000895421",
    "US Bancorp":              "0000036104",
    "PNC Financial":           "0000713676",
    "Truist Financial":        "0000092122",
    "Capital One":             "0000927628",
    "American Express":        "0000004962",
    "Bank of New York Mellon": "0001390777",
    "State Street":            "0000093751",
    "Charles Schwab":          "0000316709",
    "Fifth Third Bancorp":     "0000035527",
    "Regions Financial":       "0001281761",
    "KeyCorp":                 "0000091576",
    "Huntington Bancshares":   "0000049196",
    "Comerica":                "0000028412",
    "Zions Bancorporation":    "0000109380",
}

HEADERS = {"User-Agent": "LLM-Credit-Paper-Research contact@example.com"}


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def http_get_json(url: str) -> dict:
    time.sleep(0.15)
    req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code != 404:
            error(f"HTTP {e.code}: {url}")
        return {}
    except Exception as e:
        error(f"GET failed: {e}")
        return {}


def http_get_bytes(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={**HEADERS, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=120) as r:
            return r.read()
    except Exception as e:
        error(f"Download failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# EDGAR API
# ─────────────────────────────────────────────────────────────────────────────

def get_10k_filings(cik: str, years: int) -> list:
    """Fetch 10-K filing list via EDGAR submissions API."""
    cik_padded = cik.lstrip("0").zfill(10)
    data       = http_get_json(f"https://data.sec.gov/submissions/CIK{cik_padded}.json")
    if not data:
        return []

    recent       = data.get("filings", {}).get("recent", {})
    forms        = recent.get("form", [])
    accessions   = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    cutoff       = datetime.now().year - years

    results = []
    for i, form in enumerate(forms):
        if form not in ("10-K", "10-K/A"):
            continue
        try:
            if int(filing_dates[i][:4]) < cutoff:
                continue
        except (ValueError, IndexError):
            continue
        results.append({
            "accession_number": accessions[i],
            "filing_date":      filing_dates[i],
            "report_date":      report_dates[i] if i < len(report_dates) else "",
            "cik":              cik_padded,
        })
    return results


def get_primary_document_url(cik_padded: str, accession_number: str) -> str | None:
    """
    Use the EDGAR filing viewer API to get the typed document list.
    This API explicitly marks document type (10-K, EX-*, etc.) so we
    can reliably identify the primary filing document.

    API: https://efts.sec.gov/LATEST/search-index?q="ACCESSION"&forms=10-K
    Better: https://data.sec.gov/submissions/ already has primary document info.

    Most reliable: the EDGAR filing viewer JSON endpoint.
    """
    acc_nodash = accession_number.replace("-", "")
    cik_int    = str(int(cik_padded))

    # ── Method 1: EDGAR filing viewer API ────────────────────────────────────
    # This returns a full document list with explicit sequence numbers and types
    viewer_url = (
        f"https://www.sec.gov/cgi-bin/viewer?action=view"
        f"&cik={cik_int}&type=10-K&dateb=&owner=include&count=10"
    )

    # ── Method 2: EDGAR filing index via data.sec.gov (most reliable) ────────
    # The submissions API actually includes primary document filename directly
    # in the filings data — we just need to look it up properly
    submissions = http_get_json(
        f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    )
    if submissions:
        recent      = submissions.get("filings", {}).get("recent", {})
        accessions  = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        forms        = recent.get("form", [])

        for i, acc in enumerate(accessions):
            if acc == accession_number and i < len(primary_docs):
                primary_doc = primary_docs[i]
                if primary_doc:
                    base = (f"https://www.sec.gov/Archives/edgar/data/"
                            f"{cik_int}/{acc_nodash}/")
                    url  = base + primary_doc
                    info(f"  Primary doc from submissions API: {primary_doc}")
                    return url

    # ── Method 3: Filing index JSON with primaryDocument field ───────────────
    base_url  = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/"
    index_data = http_get_json(f"{base_url}{accession_number}-index.json")
    if index_data:
        # The index JSON has a primaryDocument field
        primary = index_data.get("primaryDocument", "")
        if primary:
            return base_url + primary

        # Fall back to finding type=10-K in the document list
        for item in index_data.get("directory", {}).get("item", []):
            if item.get("type") in ("10-K", "10-K/A"):
                return base_url + item["name"]

    # ── Method 4: EDGAR full-text search API ─────────────────────────────────
    search_url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?q=%22{accession_number}%22&forms=10-K"
    )
    search_data = http_get_json(search_url)
    if search_data:
        hits = search_data.get("hits", {}).get("hits", [])
        for hit in hits:
            src = hit.get("_source", {})
            if src.get("file_type") == "10-K":
                file_url = src.get("file_url", "")
                if file_url:
                    return file_url

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Download orchestration
# ─────────────────────────────────────────────────────────────────────────────

def download_edgar_banks(bank_list: dict, years: int) -> list:
    log   = []
    total = len(bank_list)

    for idx, (bank_name, cik) in enumerate(bank_list.items(), 1):
        info(f"[{idx}/{total}] {bank_name}")

        filings = get_10k_filings(cik, years)
        if not filings:
            warn(f"  No 10-K filings found")
            log.append({"bank": bank_name, "status": "no_filings", "files": []})
            continue

        info(f"  Found {len(filings)} 10-K filing(s)")
        bank_files = []

        for filing in filings:
            year      = (filing["report_date"] or filing["filing_date"])[:4]
            safe_name = re.sub(r"[^a-z0-9]+", "_", bank_name.lower()).strip("_")
            filename  = f"{safe_name}_{year}_10k"

            # Skip if already downloaded
            existing = list(FINANCIALS_DIR.glob(f"{filename}.*"))
            if existing:
                info(f"  Already have: {existing[0].name}")
                bank_files.append({"year": year, "status": "exists",
                                   "file": existing[0].name})
                continue

            url = get_primary_document_url(filing["cik"], filing["accession_number"])
            if not url:
                warn(f"  Could not find primary document for {year}")
                bank_files.append({"year": year, "status": "no_primary",
                                   "accession": filing["accession_number"]})
                continue

            ext  = ".pdf" if url.lower().endswith(".pdf") else ".htm"
            dest = FINANCIALS_DIR / f"{filename}{ext}"

            action(f"  {year}: ...{url[-65:]}")
            content = http_get_bytes(url)

            if content and len(content) > 50_000:
                dest.write_bytes(content)
                size_mb = len(content) / 1_048_576
                info(f"  ✅ {dest.name} ({size_mb:.1f}MB)")
                bank_files.append({"year": year, "status": "downloaded",
                                   "file": dest.name, "size_mb": round(size_mb, 1)})
            else:
                sz = len(content) if content else 0
                warn(f"  File too small ({sz} bytes) — likely wrong document")
                bank_files.append({"year": year, "status": "failed",
                                   "url": url, "size_bytes": sz})

            time.sleep(0.5)

        log.append({"bank": bank_name, "cik": cik, "files": bank_files})

    return log


# ─────────────────────────────────────────────────────────────────────────────
# UK / EU / AU checklist
# ─────────────────────────────────────────────────────────────────────────────

UK_EU_BANKS = {
    "Lloyds Banking Group": "https://www.lloydsbankinggroup.com/investors/financial-performance/annual-reports.html",
    "HSBC Holdings":        "https://www.hsbc.com/investors/results-and-announcements/annual-report",
    "Barclays":             "https://home.barclays/investor-relations/reports-and-events/annual-reports/",
    "NatWest Group":        "https://investors.natwestgroup.com/results-and-presentations/annual-reports",
    "Standard Chartered":   "https://www.sc.com/en/investors/results-reports-and-publications/annual-report/",
    "Virgin Money":         "https://www.virginmoneyukplc.com/investor-relations/results-reports-presentations/annual-reports/",
    "Nationwide":           "https://www.nationwide.co.uk/about/corporate-information/annual-report-and-accounts/",
    "Santander UK":         "https://www.aboutsantander.co.uk/investors/annual-reports.aspx",
    "Deutsche Bank":        "https://investor-relations.db.com/reports-and-events/annual-reports",
    "BNP Paribas":          "https://invest.bnpparibas/en/document-type/annual-reports",
    "UniCredit":            "https://www.unicreditgroup.eu/en/investors/financial-reports.html",
    "ING Group":            "https://www.ing.com/Investor-relations/Financial-performance/Annual-Reports.htm",
    "Societe Generale":     "https://investors.societegenerale.com/en/financial-information/annual-reports",
    "ABN AMRO":             "https://www.abnamro.com/en/investors/reports/annual-reports",
    "Commonwealth Bank":    "https://www.commbank.com.au/about-us/investors/annual-reports.html",
    "ANZ Banking Group":    "https://www.anz.com/shareholder/centre/reporting/annual-report/",
}


def generate_uk_checklist(years: int) -> str:
    current_year = datetime.now().year
    year_range   = list(range(current_year - 1, current_year - years - 1, -1))
    lines = [
        "# UK/EU/AU Bank Annual Reports — Download Checklist",
        f"Generated: {datetime.now().strftime('%Y-%m-%d')}",
        f"Target years: {year_range}", "",
        "## Instructions",
        "1. Click the IR page link for each bank",
        "2. Download Annual Report PDF for each year",
        f"3. Save to: {FINANCIALS_DIR}/",
        "4. Use the exact filename shown", "", "---", "",
    ]
    for bank_name, ir_page in UK_EU_BANKS.items():
        safe = re.sub(r"[^a-z0-9]+", "_", bank_name.lower()).strip("_")
        lines += [f"### {bank_name}", f"IR Page: {ir_page}", "", "Years:"]
        for year in year_range:
            fname  = f"{safe}_{year}_annual_report.pdf"
            status = "✅" if (FINANCIALS_DIR / fname).exists() else "⬜"
            lines.append(f"  {status} {year}: `{fname}`")
        lines += ["", "---", ""]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["edgar", "uk", "all"], default="all")
    parser.add_argument("--years",  type=int, default=5)
    parser.add_argument("--banks",  nargs="*", default=None)
    args = parser.parse_args()

    print(f"\nBank Annual Report Downloader")
    print(f"Target: last {args.years} years | Output: {FINANCIALS_DIR}\n")

    log = {"run_at": datetime.now().isoformat(), "edgar": [], "uk_checklist": None}

    if args.source in ("edgar", "all"):
        bank_list = US_BANKS
        if args.banks:
            bank_list = {k: v for k, v in US_BANKS.items()
                         if any(b.lower() in k.lower() for b in args.banks)}
            if not bank_list:
                warn(f"No banks matched. Available: {list(US_BANKS.keys())}")

        if bank_list:
            # Delete any previously downloaded exhibits (small .htm files < 2MB)
            cleaned = 0
            for f in FINANCIALS_DIR.glob("*_10k.htm"):
                if f.stat().st_size < 2_000_000:
                    f.unlink()
                    cleaned += 1
            if cleaned:
                info(f"Removed {cleaned} small exhibit files from previous run")

            info(f"Downloading {len(bank_list)} US bank(s) from SEC EDGAR...")
            edgar_log    = download_edgar_banks(bank_list, args.years)
            log["edgar"] = edgar_log
            downloaded   = sum(1 for b in edgar_log
                               for f in b.get("files", []) if f.get("status") == "downloaded")
            skipped      = sum(1 for b in edgar_log
                               for f in b.get("files", []) if f.get("status") == "exists")
            info(f"\nEDGAR: {downloaded} downloaded, {skipped} already existed")

    if args.source in ("uk", "all"):
        info(f"\nGenerating UK/EU/AU checklist...")
        checklist_path = LOGS_DIR / "uk_eu_download_checklist.md"
        checklist_path.write_text(generate_uk_checklist(args.years))
        log["uk_checklist"] = str(checklist_path)
        info(f"Checklist: {checklist_path}")

    log_path = LOGS_DIR / "download_log.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    all_files = list(FINANCIALS_DIR.glob("*.pdf")) + list(FINANCIALS_DIR.glob("*.htm"))
    print(f"\n{'='*60}")
    print(f"Files in financials/ : {len(all_files)}")
    print(f"Log                  : {log_path}")
    if log.get("uk_checklist"):
        print(f"UK/EU checklist      : {log['uk_checklist']}")
    print(f"\nNext: ./run.sh --reprocess\n")


if __name__ == "__main__":
    main()
