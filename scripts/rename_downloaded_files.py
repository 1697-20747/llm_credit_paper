#!/usr/bin/env python3
"""
rename_downloaded_files.py
==========================
Renames date-stamped HSBC files and other oddly named files to
the standard naming convention used by the extractor.

Run once after manual downloads:
    .venv/bin/python3 scripts/rename_downloaded_files.py
"""

from pathlib import Path

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
FINANCIALS_DIR = PROJECT_ROOT / "financials"
PILLAR3_DIR    = PROJECT_ROOT / "pillar3"

# (current_name_pattern, new_name)
# Uses exact filename or prefix match
AR_RENAMES = {
    # HSBC date-stamped ARs
    "260225-annual-report-and-accounts-2025.pdf": "hsbc_holdings_2025_annual_report.pdf",
    "250219-annual-report-and-accounts-2024.pdf": "hsbc_holdings_2024_annual_report.pdf",
    "240226-annual-report-and-accounts-2023.pdf": "hsbc_holdings_2023_annual_report.pdf",
    "230221-annual-report-and-accounts-2022.pdf": "hsbc_holdings_2022_annual_report.pdf",
    "220222-annual-report-and-accounts-2021.pdf": "hsbc_holdings_2021_annual_report.pdf",
    "210223-annual-report-and-accounts-2020.pdf": "hsbc_holdings_2020_annual_report.pdf",
    # These may already exist from previous runs — skip if dest exists
    "200218-hsbc-holdings-plc-annual-report-and-accounts-2019.pdf": "hsbc_holdings_2019_annual_report.pdf",
    "190219-hsbc-holdings-plc-annual-report-and-accounts-2018.pdf": "hsbc_holdings_2018_annual_report.pdf",
    "180220-annual-report-and-accounts-2017.pdf": "hsbc_holdings_2017_annual_report.pdf",
    "170221-annual-report-and-accounts-2016.pdf": "hsbc_holdings_2016_annual_report.pdf",
    "160222-annual-report-and-accounts-2015.pdf": "hsbc_holdings_2015_annual_report.pdf",
    "hsbc-holdings-plc-annual-report-and-accounts-2015.pdf": "hsbc_holdings_2015_annual_report.pdf",
    # Lloyds version-suffixed files
    "2016_lbg_annual_report_v2.pdf": "2016-lbg-annual-report.pdf",
    "2017-lbg-annual-report-v3.pdf": "2017-lbg-annual-report.pdf",
    "2018-lbg-annual-report-v2.pdf": "2018-lbg-annual-report.pdf",
}

P3_RENAMES = {
    # HSBC date-stamped Pillar 3
    "250227-pillar-3-disclosures-at-31-december-2024.pdf": "hsbc_holdings_2024_pillar3.pdf",
    "240221-pillar-3-disclosures-at-31-december-2023.pdf": "hsbc_holdings_2023_pillar3.pdf",
    "230221-pillar-3-disclosures-at-31-december-2022.pdf": "hsbc_holdings_2022_pillar3.pdf",
    "220222-pillar-3-disclosures-at-31-december-2021.pdf": "hsbc_holdings_2021_pillar3.pdf",
    "210223-pillar-3-disclosures-at-31-december-2020.pdf": "hsbc_holdings_2020_pillar3.pdf",
    "200218-pillar-3-disclosures-at-31-december-2019.pdf": "hsbc_holdings_2019_pillar3.pdf",
    "190219-pillar-3-disclosures-at-31-december-2018.pdf": "hsbc_holdings_2018_pillar3.pdf",
    # Lloyds Pillar 3 (sometimes saved with date prefix)
    "2025-lbg-fy-pillar-3.pdf": "lloyds_banking_group_2025_pillar3.pdf",
}


def rename_in(directory: Path, renames: dict):
    for old_name, new_name in renames.items():
        old_path = directory / old_name
        new_path = directory / new_name
        if not old_path.exists():
            continue
        if new_path.exists():
            print(f"  SKIP (dest exists): {old_name} → {new_name}")
            continue
        old_path.rename(new_path)
        print(f"  RENAMED: {old_name}")
        print(f"       → : {new_name}")


print(f"\nRenaming files in financials/")
rename_in(FINANCIALS_DIR, AR_RENAMES)

print(f"\nRenaming files in pillar3/")
rename_in(PILLAR3_DIR, P3_RENAMES)

print(f"\nDone.")
print(f"Next: ./run.sh --reprocess")
