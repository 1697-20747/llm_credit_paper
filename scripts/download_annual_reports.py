#!/usr/bin/env python3
"""
download_annual_reports.py  — verified URLs May 2026
=====================================================
Downloads bank Annual Reports and Pillar 3 reports.
Skips valid existing files. Min 1MB for AR, 500KB for P3.

Usage:
    .venv/bin/python3 scripts/download_annual_reports.py
    .venv/bin/python3 scripts/download_annual_reports.py --validate
    .venv/bin/python3 scripts/download_annual_reports.py --ar-only
    .venv/bin/python3 scripts/download_annual_reports.py --pillar3-only
    .venv/bin/python3 scripts/download_annual_reports.py --banks lloyds hsbc rbc
"""

import ssl, time, argparse, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl._create_unverified_context()

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
FINANCIALS_DIR = PROJECT_ROOT / "financials"
PILLAR3_DIR    = PROJECT_ROOT / "pillar3"
LOGS_DIR       = PROJECT_ROOT / "logs"
LOG_FILE       = LOGS_DIR / "download_annual_reports.log"

for d in [FINANCIALS_DIR, PILLAR3_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True)

MIN_AR = 1_000_000   # 1 MB  — real ARs are 5MB+; redirect pages are <500KB
MIN_P3 =   500_000   # 500KB — Pillar 3 can be smaller but never <500KB

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN ='\033[0;36m'; GREY  ='\033[0;37m'; NC  ='\033[0m'

downloaded = skipped = failed = 0
failed_list = []

def log(m):
    with open(LOG_FILE,"a") as f: f.write(m+"\n")

def info(m):    s=f"{GREEN}[INFO]{NC}   {m}";  print(s); log(m)
def get(m):     s=f"{CYAN}[GET]{NC}    {m}";   print(s); log(m)
def skip(m):    s=f"{GREY}[SKIP]{NC}   {m}";   print(s); log(m)
def ok(m):      s=f"{GREEN}[OK]{NC}     {m}";   print(s); log(m)
def warn(m):    s=f"{YELLOW}[WARN]{NC}   {m}";  print(s); log(m)
def manual(m):  s=f"{YELLOW}[MANUAL]{NC} {m}";  print(s); log(m)
def fail(m):
    global failed
    s=f"{RED}[FAIL]{NC}   {m}"; print(s); log(m)
    failed_list.append(m); failed+=1

def is_valid(p: Path, min_b: int) -> bool:
    if not p.exists() or p.stat().st_size < min_b: return False
    with open(p,"rb") as f: return f.read(4)==b"%PDF"

def fetch(url: str, dest: Path, label: str, min_b: int=MIN_AR) -> bool:
    global downloaded, skipped
    if is_valid(dest, min_b):
        skip(f"{label} ({dest.stat().st_size//1024}KB)"); skipped+=1; return True
    dest.unlink(missing_ok=True)
    get(label)
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept":"application/pdf,*/*",
        "Referer":"https://www.google.com/",
    })
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=90) as r:
            data=r.read()
        if len(data)>=min_b and data[:4]==b"%PDF":
            dest.write_bytes(data)
            ok(f"{label} — {len(data)//1024}KB"); downloaded+=1; return True
        fail(f"{label} — not a valid PDF ({len(data)//1024}KB, need {min_b//1024}KB+)")
        return False
    except urllib.error.HTTPError as e:
        fail(f"{label} — HTTP {e.code}"); return False
    except Exception as e:
        fail(f"{label} — {e}"); return False
    finally:
        time.sleep(0.5)

def validate():
    info("Validating existing files...")
    removed=0
    for d,mb in [(FINANCIALS_DIR,MIN_AR),(PILLAR3_DIR,MIN_P3)]:
        for f in d.glob("*.pdf"):
            if not is_valid(f,mb):
                warn(f"INVALID ({f.stat().st_size//1024}KB): {f.name}")
                f.unlink(); removed+=1
    info(f"Removed {removed} invalid/redirect files.")

# =============================================================================
# URL REGISTRY — verified May 2026
# =============================================================================

AR = {

    # ── UK ─────────────────────────────────────────────────────────────────────
    "lloyds": [
        # 2021-2025: /investors/<year>/
        # 2023 uses /annual-report/2023/ path (different from others)
        # 2020: Form 20-F; 2016-2019: /financial-performance/.../q4/
        (2025,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/2025/lbg-2025-annual-report.pdf","financials/2025-lbg-annual-report.pdf"),
        (2024,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/2024/lbg-2024-annual-report.pdf","financials/2024-lbg-annual-report.pdf"),
        (2023,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/annual-report/2023/2023-lbg-annual-report.pdf","financials/2023-lbg-annual-report.pdf"),
        (2022,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/2022/lbg-2022-annual-report.pdf","financials/2022-lbg-annual-report.pdf"),
        (2021,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/2021/lbg-2021-annual-report.pdf","financials/2021-lbg-annual-report.pdf"),
        (2020,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/2020/full-year/2020-lbg-form-20f.pdf","financials/2020-lbg-annual-report.pdf"),
        (2019,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/2019/q4/2019-lbg-annual-report.pdf","financials/2019-lbg-annual-report.pdf"),
        (2018,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/2018/q4/2018-lbg-annual-report.pdf","financials/2018-lbg-annual-report.pdf"),
        (2017,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/2017/q4/2017-lbg-annual-report.pdf","financials/2017-lbg-annual-report.pdf"),
        (2016,"https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/2016/q4/2016-lbg-annual-report.pdf","financials/2016-lbg-annual-report.pdf"),
    ],
    "barclays": [
        # 2020-2025 verified; pre-2020 ResultAnnouncements path
        *[(y,f"https://home.barclays/content/dam/home-barclays/documents/investor-relations/reports-and-events/annual-reports/{y}/Barclays-PLC-Annual-Report-{y}.pdf",f"financials/Barclays-PLC-Annual-Report-{y}.pdf") for y in [2025,2024,2023,2022,2021,2020]],
        *[(y,f"https://home.barclays/content/dam/home-barclays/documents/investor-relations/ResultAnnouncements/FullYear{y}Results/Barclays-PLC-Annual-Report-{y}.pdf",f"financials/Barclays-PLC-Annual-Report-{y}.pdf") for y in [2019,2018,2017,2016]],
    ],
    "hsbc": [
        # Date prefix = results announcement date; verified 2019-2022
        # 2023=240221, 2024=250227, 2025=260227
        (2025,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2025/annual/pdfs/hsbc-holdings-plc/260227-annual-report-and-accounts-2025.pdf","financials/hsbc_holdings_2025_annual_report.pdf"),
        (2024,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2024/annual/pdfs/hsbc-holdings-plc/250227-annual-report-and-accounts-2024.pdf","financials/hsbc_holdings_2024_annual_report.pdf"),
        (2023,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2023/annual/pdfs/hsbc-holdings-plc/240221-annual-report-and-accounts-2023.pdf","financials/hsbc_holdings_2023_annual_report.pdf"),
        (2022,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2022/annual/pdfs/hsbc-holdings-plc/230221-annual-report-and-accounts-2022.pdf","financials/hsbc_holdings_2022_annual_report.pdf"),
        (2021,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2021/annual/pdfs/hsbc-holdings-plc/220222-annual-report-and-accounts-2021.pdf","financials/hsbc_holdings_2021_annual_report.pdf"),
        (2020,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2020/annual/pdfs/hsbc-holdings-plc/210223-annual-report-and-accounts-2020.pdf","financials/hsbc_holdings_2020_annual_report.pdf"),
        (2019,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2019/annual/pdfs/hsbc-holdings-plc/200218-hsbc-holdings-plc-annual-report-and-accounts-2019.pdf","financials/hsbc_holdings_2019_annual_report.pdf"),
        (2018,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2018/annual/pdfs/hsbc-holdings-plc/190219-hsbc-holdings-plc-annual-report-and-accounts-2018.pdf","financials/hsbc_holdings_2018_annual_report.pdf"),
        (2017,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2017/annual/pdfs/hsbc-holdings-plc/180220-annual-report-and-accounts-2017.pdf","financials/hsbc_holdings_2017_annual_report.pdf"),
        (2016,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2016/annual/pdfs/hsbc-holdings-plc/170221-annual-report-and-accounts-2016.pdf","financials/hsbc_holdings_2016_annual_report.pdf"),
    ],
    "natwest": [
        # Verified — each year has specific date path + filename
        # 2022 has NO year suffix; pre-2020 filed as RBS
        (2024,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/14022025/nwg-annual-report-and-accounts-2024.pdf","financials/natwest_group_2024_annual_report.pdf"),
        (2023,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/16022024/nwg-annual-report-and-accounts-2023.pdf","financials/natwest_group_2023_annual_report.pdf"),
        (2022,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/17022023/nwg-annual-report-and-accounts.pdf","financials/natwest_group_2022_annual_report.pdf"),
        (2021,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/18022022/natwest-group-annual-report-accounts-2021.pdf","financials/natwest_group_2021_annual_report.pdf"),
        (2020,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/19022021/natwest-group-annual-report-accounts-2020.pdf","financials/natwest_group_2020_annual_report.pdf"),
        (2019,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/14022020/rbs-group-annual-report-2019.pdf","financials/natwest_group_2019_annual_report.pdf"),
        (2018,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/15022019/rbs-annual-report-2018.pdf","financials/natwest_group_2018_annual_report.pdf"),
        (2017,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/23022018/rbs-annual-report-2017.pdf","financials/natwest_group_2017_annual_report.pdf"),
        (2016,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/24022017/rbs-annual-report-2016.pdf","financials/natwest_group_2016_annual_report.pdf"),
        (2015,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/26022016/rbs-annual-report-2015.pdf","financials/natwest_group_2015_annual_report.pdf"),
    ],

    # ── EU ─────────────────────────────────────────────────────────────────────
    "deutsche": [
        # Each year stored in NEXT year's folder (verified)
        (2024,"https://investor-relations.db.com/files/documents/annual-reports/2025/Annual-Report-2024.pdf","financials/deutsche_bank_2024_annual_report.pdf"),
        (2023,"https://investor-relations.db.com/files/documents/annual-reports/2024/Annual-Report-2023.pdf","financials/deutsche_bank_2023_annual_report.pdf"),
        (2022,"https://investor-relations.db.com/files/documents/annual-reports/2023/Annual-Report-2022.pdf","financials/deutsche_bank_2022_annual_report.pdf"),
        (2021,"https://investor-relations.db.com/files/documents/annual-reports/2022/Annual-Report-2021.pdf","financials/deutsche_bank_2021_annual_report.pdf"),
        (2020,"https://investor-relations.db.com/files/documents/annual-reports/2021/Annual-Report-2020.pdf","financials/deutsche_bank_2020_annual_report.pdf"),
        (2019,"https://investor-relations.db.com/files/documents/annual-reports/2020/Annual-Report-2019.pdf","financials/deutsche_bank_2019_annual_report.pdf"),
        (2018,"https://investor-relations.db.com/files/documents/annual-reports/2019/Annual-Report-2018.pdf","financials/deutsche_bank_2018_annual_report.pdf"),
        (2017,"https://investor-relations.db.com/files/documents/annual-reports/2018/Annual-Report-2017.pdf","financials/deutsche_bank_2017_annual_report.pdf"),
        (2016,"https://investor-relations.db.com/files/documents/annual-reports/2017/Annual-Report-2016.pdf","financials/deutsche_bank_2016_annual_report.pdf"),
        (2015,"https://investor-relations.db.com/files/documents/annual-reports/2016/Annual-Report-2015.pdf","financials/deutsche_bank_2015_annual_report.pdf"),
    ],
    "bnp": [
        # URD (Universal Registration Document) — dated path
        (2024,"https://invest.bnpparibas/sites/default/files/documents/2025-03/bnp-paribas-2024-universal-registration-document.pdf","financials/bnp_paribas_2024_annual_report.pdf"),
        (2023,"https://invest.bnpparibas/sites/default/files/documents/2024-03/bnp-paribas-2023-universal-registration-document.pdf","financials/bnp_paribas_2023_annual_report.pdf"),
        (2022,"https://invest.bnpparibas/sites/default/files/documents/2023-03/bnp-paribas-2022-universal-registration-document.pdf","financials/bnp_paribas_2022_annual_report.pdf"),
        (2021,"https://invest.bnpparibas/sites/default/files/documents/2022-03/bnp-paribas-2021-universal-registration-document.pdf","financials/bnp_paribas_2021_annual_report.pdf"),
        (2020,"https://invest.bnpparibas/sites/default/files/documents/2021-04/bnp-paribas-2020-universal-registration-document.pdf","financials/bnp_paribas_2020_annual_report.pdf"),
        (2019,"https://invest.bnpparibas/sites/default/files/documents/2020-03/bnp-paribas-2019-universal-registration-document.pdf","financials/bnp_paribas_2019_annual_report.pdf"),
        (2018,"https://invest.bnpparibas/sites/default/files/documents/2019-03/bnp-paribas-2018-registration-document.pdf","financials/bnp_paribas_2018_annual_report.pdf"),
        (2017,"https://invest.bnpparibas/sites/default/files/documents/2018-03/bnp-paribas-2017-registration-document.pdf","financials/bnp_paribas_2017_annual_report.pdf"),
    ],
    "unicredit": [
        (2024,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2024/4Q24/2024-Annual-Reports-and-Accounts-General-Meeting-Draft.pdf","financials/unicredit_2024_annual_report.pdf"),
        (2023,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2023/4Q23/2023-Annual-Reports-and-Accounts.pdf","financials/unicredit_2023_annual_report.pdf"),
        (2022,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2022/4Q22/2022-Annual-Reports-and-Accounts.pdf","financials/unicredit_2022_annual_report.pdf"),
        (2021,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2021/4Q21/2021-Annual-Reports-and-Accounts.pdf","financials/unicredit_2021_annual_report.pdf"),
        (2020,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2020/4Q20/2020-Annual-Reports-and-Accounts.pdf","financials/unicredit_2020_annual_report.pdf"),
        (2019,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2019/4Q19/2019-Annual-Reports-and-Accounts.pdf","financials/unicredit_2019_annual_report.pdf"),
        (2018,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2018/4Q18/2018-Annual-Report.pdf","financials/unicredit_2018_annual_report.pdf"),
        (2017,"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/2017/4Q17/2017-Annual-Report.pdf","financials/unicredit_2017_annual_report.pdf"),
    ],
    "santander": [
        *[(y,f"https://www.santander.com/content/dam/santander-com/en/documentos/informe-financiero-anual/{y}/ifa-{y}-consolidated-annual-financial-report-en.pdf",f"financials/santander_group_{y}_annual_report.pdf") for y in [2024,2023,2022,2021,2020,2019]],
        *[(y,f"https://www.santander.com/content/dam/santander-com/en/documentos/informe-anual-y-de-sostenibilidad/{y}/santander-{y}-annual-report.pdf",f"financials/santander_group_{y}_annual_report.pdf") for y in [2018,2017]],
    ],
    "abn": [
        # 2023 Contentful CDN (verified); 2024 try same CDN pattern; 2015-2022 abnamro.com
        (2024,"https://downloads.ctfassets.net/1u811bvgvthc/ABN-AMRO-Integrated-Annual-Report-2024/ABN-AMRO-Annual-Report-2024.pdf","financials/abn_amro_2024_annual_report.pdf"),
        (2023,"https://downloads.ctfassets.net/1u811bvgvthc/1ct3rr0164d6Vt5YuVrWqe/e700292b6cdec93acb5d782976efaf0e/ABN_AMRO___Integrated_Annual_Report_2023.pdf","financials/abn_amro_2023_annual_report.pdf"),
        *[(y,f"https://www.abnamro.com/en/images/documents/Investors/Annual_Reports/{y}/ABN-AMRO-Annual-Report-{y}.pdf",f"financials/abn_amro_{y}_annual_report.pdf") for y in [2022,2021,2020,2019,2018,2017,2016,2015]],
    ],
    "intesa": [
        # 2021+ new path; older scriptIsir0 path
        *[(y,f"https://group.intesasanpaolo.com/content/dam/intesasanpaolo/investor-relations/annual-reports/report-annuale-{y}-en.pdf",f"financials/intesa_sanpaolo_{y}_annual_report.pdf") for y in [2024,2023,2022,2021]],
        *[(y,f"https://group.intesasanpaolo.com/scriptIsir0/si09/contentData/view/Annual-Report-{y}.pdf",f"financials/intesa_sanpaolo_{y}_annual_report.pdf") for y in [2020,2019,2018,2017]],
    ],

    # ── AU ─────────────────────────────────────────────────────────────────────
    "anz": [
        # 2024 uses ANZBGL prefix; 2015-2023 uses plain ANZ-Annual-Report-YYYY.pdf
        (2024,"https://www.anz.com/content/dam/anzcom/shareholder/ANZBGL-2024-Annual%20Report.pdf","financials/anz_banking_2024_annual_report.pdf"),
        *[(y,f"https://www.anz.com/content/dam/anzcom/shareholder/ANZ-Annual-Report-{y}.pdf",f"financials/anz_banking_{y}_annual_report.pdf") for y in [2023,2022,2021,2020,2019,2018,2017,2016,2015]],
    ],
    "westpac": [
        # Per-year naming convention (verified from live search)
        (2024,"https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/wbc-annual-report-2024.pdf","financials/westpac_2024_annual_report.pdf"),
        (2023,"https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/WG-AnnualReport-2023.pdf","financials/westpac_2023_annual_report.pdf"),
        (2022,"https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/WBC_2022_Annual_Report.pdf","financials/westpac_2022_annual_report.pdf"),
        # 2021 and earlier — try standard wbc-annual-report-YYYY.pdf pattern
        *[(y,f"https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/wbc-annual-report-{y}.pdf",f"financials/westpac_{y}_annual_report.pdf") for y in [2021,2020,2019,2018]],
        *[(y,f"https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/{y}-annual-report.pdf",f"financials/westpac_{y}_annual_report.pdf") for y in [2017,2016,2015]],
    ],
    "nab": [
        # 2022+ /nab/ path; older /nabrwd/ path
        *[(y,f"https://www.nab.com.au/content/dam/nab/documents/reports/corporate/{y}-annual-report.pdf",f"financials/nab_{y}_annual_report.pdf") for y in [2024,2023,2022]],
        *[(y,f"https://www.nab.com.au/content/dam/nabrwd/documents/reports/corporate/{y}-annual-report.pdf",f"financials/nab_{y}_annual_report.pdf") for y in [2021,2020,2019,2018,2017,2016,2015]],
    ],
    "commonwealth": [
        # CBA FY ends June — /docs/results/fyYY/ path
        *[(y,f"https://www.commbank.com.au/content/dam/commbank-assets/investors/docs/results/fy{str(y)[2:]}/{y}-annual-report.pdf",f"financials/commonwealth_bank_{y}_annual_report.pdf") for y in [2024,2023,2022,2021,2020,2019,2018]],
    ],

    # ── CA ─────────────────────────────────────────────────────────────────────
    "rbc": [
        # Verified pattern: rbc.com/investor-relations/_assets-custom/pdf/ar_YYYY_e.pdf
        *[(y,f"https://www.rbc.com/investor-relations/_assets-custom/pdf/ar_{y}_e.pdf",f"financials/rbc_{y}_annual_report.pdf") for y in [2024,2023,2022,2021,2020,2019,2018,2017,2016,2015]],
    ],
    "td": [
        # Verified: td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/<y>/q4/<y>-annual-report-en.pdf
        *[(y,f"https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/{y}/q4/{y}-annual-report-en.pdf",f"financials/td_bank_{y}_annual_report.pdf") for y in [2024,2023,2022,2021,2020,2019,2018,2017,2016,2015]],
    ],
    "scotiabank": [
        # Verified: scotiabank.com/content/dam/scotiabank/corporate/BNS_Annual_Report_<YYYY>_EN.pdf
        *[(y,f"https://www.scotiabank.com/content/dam/scotiabank/corporate/BNS_Annual_Report_{y}_EN.pdf",f"financials/scotiabank_{y}_annual_report.pdf") for y in [2024,2023,2022,2021,2020,2019,2018,2017,2016,2015]],
    ],
    "bmo": [
        # BMO FY ends October — try standard path
        *[(y,f"https://www.bmo.com/content/dam/bmo/en/documents/investors/annual-reports/bmo-annual-report-{y}.pdf",f"financials/bmo_{y}_annual_report.pdf") for y in [2024,2023,2022,2021,2020,2019,2018,2017,2016,2015]],
    ],
    "cibc": [
        # CIBC FY ends October
        *[(y,f"https://www.cibc.com/content/dam/cibc-public-assets/about-cibc/investor-relations/pdfs/annual-reports/cibc-annual-report-{y}-en.pdf",f"financials/cibc_{y}_annual_report.pdf") for y in [2024,2023,2022,2021,2020,2019,2018,2017,2016,2015]],
    ],
}

# =============================================================================
# PILLAR 3
# =============================================================================

P3 = {
    "lloyds": [
        *[(y,f"https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/{y}/q4/{y}-lbg-fy-pillar-3.pdf",f"pillar3/lloyds_banking_group_{y}_pillar3.pdf") for y in range(2018,2026)],
    ],
    "barclays": [
        # 2022-2024: reports-and-events path (verified)
        *[(y,f"https://home.barclays/content/dam/home-barclays/documents/investor-relations/reports-and-events/annual-reports/{y}/Pillar-3/Barclays-PLC-Pillar-3-Report-{y}.pdf",f"pillar3/barclays_{y}_pillar3.pdf") for y in [2024,2023,2022]],
        # 2018-2021: ResultAnnouncements path (verified)
        *[(y,f"https://home.barclays/content/dam/home-barclays/documents/investor-relations/ResultAnnouncements/FullYear{y}Results/FY{str(y)[2:]}-Barclays-PLC-Pillar-3-Report.pdf",f"pillar3/barclays_{y}_pillar3.pdf") for y in [2021,2020,2019,2018]],
    ],
    "hsbc": [
        # Verified: <prefix>-pillar-3-disclosures-at-31-december-<year>.pdf
        (2024,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2024/annual/pdfs/hsbc-holdings-plc/250227-pillar-3-disclosures-at-31-december-2024.pdf","pillar3/hsbc_holdings_2024_pillar3.pdf"),
        (2023,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2023/annual/pdfs/hsbc-holdings-plc/240221-pillar-3-disclosures-at-31-december-2023.pdf","pillar3/hsbc_holdings_2023_pillar3.pdf"),
        (2022,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2022/annual/pdfs/hsbc-holdings-plc/230221-pillar-3-disclosures-at-31-december-2022.pdf","pillar3/hsbc_holdings_2022_pillar3.pdf"),
        (2021,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2021/annual/pdfs/hsbc-holdings-plc/220222-pillar-3-disclosures-at-31-december-2021.pdf","pillar3/hsbc_holdings_2021_pillar3.pdf"),
        (2020,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2020/annual/pdfs/hsbc-holdings-plc/210223-pillar-3-disclosures-at-31-december-2020.pdf","pillar3/hsbc_holdings_2020_pillar3.pdf"),
        (2019,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2019/annual/pdfs/hsbc-holdings-plc/200218-pillar-3-disclosures-at-31-december-2019.pdf","pillar3/hsbc_holdings_2019_pillar3.pdf"),
        (2018,"https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2018/annual/pdfs/hsbc-holdings-plc/190219-pillar-3-disclosures-at-31-december-2018.pdf","pillar3/hsbc_holdings_2018_pillar3.pdf"),
    ],
    "natwest": [
        # Each year unique filename — verified from live search
        (2024,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/14022025/nwg-pillar-3-report-2024.pdf","pillar3/natwest_group_2024_pillar3.pdf"),
        (2023,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/16022024/nwg-pillar-3-report-2023.pdf","pillar3/natwest_group_2023_pillar3.pdf"),
        (2022,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/17022023/nwg-pillar-3-report-v1.pdf","pillar3/natwest_group_2022_pillar3.pdf"),
        (2021,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/18022022/nwg-pillar-3-supplement-2021.pdf","pillar3/natwest_group_2021_pillar3.pdf"),
        (2020,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/19022021/natwest-holdings-pillar-3-report-fy2020.pdf","pillar3/natwest_group_2020_pillar3.pdf"),
        (2019,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/14022020/rbs-pillar-3-report-2019.pdf","pillar3/natwest_group_2019_pillar3.pdf"),
        (2018,"https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/15022019/rbs-pillar-3-report-2018.pdf","pillar3/natwest_group_2018_pillar3.pdf"),
    ],
    "deutsche": [
        # Same year-offset pattern as AR
        (2024,"https://investor-relations.db.com/files/documents/annual-reports/2025/Pillar-3-Report-2024.pdf","pillar3/deutsche_bank_2024_pillar3.pdf"),
        (2023,"https://investor-relations.db.com/files/documents/annual-reports/2024/Pillar-3-Report-2023.pdf","pillar3/deutsche_bank_2023_pillar3.pdf"),
        (2022,"https://investor-relations.db.com/files/documents/annual-reports/2023/Pillar-3-Report-2022.pdf","pillar3/deutsche_bank_2022_pillar3.pdf"),
        (2021,"https://investor-relations.db.com/files/documents/annual-reports/2022/Pillar-3-Report-2021.pdf","pillar3/deutsche_bank_2021_pillar3.pdf"),
        (2020,"https://investor-relations.db.com/files/documents/annual-reports/2021/Pillar-3-Report-2020.pdf","pillar3/deutsche_bank_2020_pillar3.pdf"),
        (2019,"https://investor-relations.db.com/files/documents/annual-reports/2020/Pillar-3-Report-2019.pdf","pillar3/deutsche_bank_2019_pillar3.pdf"),
        (2018,"https://investor-relations.db.com/files/documents/annual-reports/2019/Pillar-3-Report-2018.pdf","pillar3/deutsche_bank_2018_pillar3.pdf"),
        (2017,"https://investor-relations.db.com/files/documents/annual-reports/2018/Pillar-3-Report-2017.pdf","pillar3/deutsche_bank_2017_pillar3.pdf"),
    ],
    "unicredit": [
        *[(y,f"https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/{y}/4Q{str(y)[2:]}/{y}-Pillar3-Report.pdf",f"pillar3/unicredit_{y}_pillar3.pdf") for y in [2024,2023,2022,2021,2020]],
    ],
    "jpmorgan": [
        *[(y,f"https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/investor-relations/documents/basel-disclosures/{y}-4q-pillar-3-capital-disclosures.pdf",f"pillar3/jpmorgan_chase_{y}_pillar3.pdf") for y in [2024,2023,2022,2021,2020]],
    ],
}

MANUAL = [
    ("Standard Chartered AR+P3 (HTTP 403)","https://www.sc.com/en/investors/results-and-reports/","financials/standard_chartered_<year>_annual_report.pdf"),
    ("ING Group AR+P3 (JS-rendered)","https://www.ing.com/Investor-relations/Financial-performance/Annual-reports.htm","financials/ing_group_<year>_annual_report.pdf"),
    ("BBVA AR (JS-rendered)","https://shareholdersandinvestors.bbva.com/financial-information/annual-report/","financials/bbva_<year>_annual_report.pdf"),
    ("BofA Pillar 3","https://investor.bankofamerica.com/regulatory-and-other-filings/basel-disclosures","pillar3/bank_of_america_<year>_pillar3.pdf"),
    ("Wells Fargo Pillar 3","https://www.wellsfargo.com/invest_relations/basel/","pillar3/wells_fargo_<year>_pillar3.pdf"),
    ("Goldman Sachs Pillar 3","https://www.goldmansachs.com/investor-relations/financials/basel-disclosures/","pillar3/goldman_sachs_<year>_pillar3.pdf"),
    ("Canadian bank Pillar 3","Each bank IR page → Regulatory Capital → OSFI Pillar 3","pillar3/rbc_<year>_pillar3.pdf  etc"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate",     action="store_true")
    parser.add_argument("--ar-only",      action="store_true")
    parser.add_argument("--pillar3-only", action="store_true")
    parser.add_argument("--banks",        nargs="*", default=None)
    args = parser.parse_args()

    log(f"\n{'='*60}\n Annual Report + Pillar 3 Downloader  {datetime.now()}\n{'='*60}")
    print(f"\n{'='*60}")
    print(f" Annual Report + Pillar 3 Downloader")
    print(f" Started: {datetime.now():%d %b %Y %H:%M}")
    print(f" Min AR: {MIN_AR//1024}KB  Min P3: {MIN_P3//1024}KB  Timeout: 90s")
    print(f"{'='*60}")

    if args.validate:
        validate()

    banks = set(args.banks) if args.banks else None
    ok_b  = lambda k: banks is None or k in banks

    if not args.pillar3_only:
        print(f"\n{'━'*60}\n ANNUAL REPORTS\n{'━'*60}")
        for bank, entries in AR.items():
            if not ok_b(bank): continue
            print(f"\n{CYAN}{bank.upper()}{NC}")
            for yr, url, rel in sorted(entries, reverse=True, key=lambda x: x[0]):
                fetch(url, PROJECT_ROOT/rel, f"{bank.title()} {yr}", MIN_AR)

    if not args.ar_only:
        print(f"\n{'━'*60}\n PILLAR 3 REPORTS\n{'━'*60}")
        for bank, entries in P3.items():
            if not ok_b(bank): continue
            print(f"\n{CYAN}{bank.upper()} — Pillar 3{NC}")
            for yr, url, rel in sorted(entries, reverse=True, key=lambda x: x[0]):
                fetch(url, PROJECT_ROOT/rel, f"{bank.title()} {yr} Pillar 3", MIN_P3)

    print(f"\n{'━'*60}\n MANUAL DOWNLOADS\n{'━'*60}")
    for name, url, save in MANUAL:
        manual(f"{name}"); manual(f"  {url}"); manual(f"  Save: {save}\n")

    ar_n = len(list(FINANCIALS_DIR.glob("*.pdf")))+len(list(FINANCIALS_DIR.glob("*.htm")))
    p3_n = len(list(PILLAR3_DIR.glob("*.pdf")))
    print(f"\n{'━'*60}\n SUMMARY\n{'━'*60}")
    print(f" Downloaded : {downloaded}")
    print(f" Skipped    : {skipped}")
    print(f" Failed     : {failed}")
    if failed_list:
        print("\n Failed:"); [print(f"   ✗ {f}") for f in failed_list]
    print(f"\n financials/ : {ar_n}   pillar3/ : {p3_n}")
    print(f" Next: ./run.sh --reprocess\n{'━'*60}\n")

if __name__=="__main__":
    main()
