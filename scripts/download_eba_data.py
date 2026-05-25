#!/usr/bin/env python3
"""
download_eba_data.py
====================
Downloads EBA EU-wide Transparency Exercise data in CSV format.

EBA switched from Excel to CSV format and now uses the European Data
Access Portal (EDAP). This script downloads the CSV files and converts
them to structured CAMELS training pairs.

Direct CSV download URLs use the pattern:
  https://www.eba.europa.eu/assets/TE{YEAR}/Full_database/{ID}/

Manual download option:
  https://www.eba.europa.eu/eu-wide-transparency-exercise-0
  → Full database → CSV files

Usage:
    python scripts/download_eba_data.py
    python scripts/download_eba_data.py --manual-dir raw_data/eba

Output:
    training_data/eba_pairs.jsonl
    logs/eba_download_log.json
"""

import re
import json
import time
import ssl
import os
import argparse
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from datetime import datetime

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl._create_unverified_context()

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
DATA_DIR      = PROJECT_ROOT / "raw_data" / "eba"
TRAINING_DIR  = PROJECT_ROOT / "training_data"
LOGS_DIR      = PROJECT_ROOT / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRAINING_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

GREEN = '\033[0;32m'; YELLOW = '\033[1;33m'; RED = '\033[0;31m'; NC = '\033[0m'
def info(msg):   print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg):   print(f"{YELLOW}[WARN]{NC}  {msg}")
def manual(msg): print(f"{YELLOW}[MANUAL]{NC} {msg}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}

# ─────────────────────────────────────────────────────────────────────────────
# EBA data now available as CSV via EDAP
# Direct ZIP download URLs — these contain the full CSV database
# ─────────────────────────────────────────────────────────────────────────────

EBA_CSV_URLS = {
    "2024": [
        "https://www.eba.europa.eu/assets/TE2024/Full_database/256109/TE2024_Data.zip",
        "https://www.eba.europa.eu/assets/TE2024/Full_database/256109/TE_2024_Data.zip",
    ],
    "2023": [
        "https://www.eba.europa.eu/assets/TE2023/Full_database/837203/TE2023_Data.zip",
        "https://www.eba.europa.eu/assets/TE2023/Full_database/837203/TE_2023_Data.zip",
    ],
    "2022": [
        "https://www.eba.europa.eu/assets/TE2022/Full_database/TE2022_Data.zip",
    ],
    "2021": [
        "https://www.eba.europa.eu/sites/default/files/document_library/Risk%20Analysis%20and%20Data/EU-wide%20Transparency%20Exercise/2021/1025059/TE2021_Data.zip",
    ],
    "2020": [
        "https://www.eba.europa.eu/sites/default/files/document_library/Risk%20Analysis%20and%20Data/EU-wide%20Transparency%20Exercise/2020/933179/TE2020_Data.zip",
    ],
}

# Manual download page — always works
MANUAL_URL = "https://www.eba.europa.eu/eu-wide-transparency-exercise-0"

SYSTEM_PROMPT = (
    "You are a senior credit analyst specialising in bank credit analysis "
    "using the CAMELS framework. You follow Moody's, S&P Global Ratings, "
    "and Fitch Ratings methodologies. Every numerical claim must cite a source. "
    "If data is unavailable, state 'Data not available' — never fabricate figures."
)

# EBA CSV column name fragments → CAMELS metric mapping
# EBA uses coded column names — these are common patterns across years
EBA_METRIC_MAP = {
    "CET1": ("cet1_ratio", "%", "capital"),
    "T1": ("tier1_ratio", "%", "capital"),
    "TC": ("total_capital_ratio", "%", "capital"),
    "LEV": ("leverage_ratio", "%", "capital"),
    "NPL_RAT": ("npl_ratio", "%", "asset_quality"),
    "COV_RAT": ("npl_coverage", "%", "asset_quality"),
    "ROE": ("roe", "%", "earnings"),
    "ROA": ("roa", "%", "earnings"),
    "NIM": ("nim", "%", "earnings"),
    "CI": ("cost_income", "%", "earnings"),
    "LCR": ("lcr", "%", "liquidity"),
    "NSFR": ("nsfr", "%", "liquidity"),
}


def http_get_bytes(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=120) as r:
            data = r.read()
            return data if len(data) > 5000 else None
    except Exception as e:
        warn(f"  {url[-60:]}: {e}")
        return None


def try_download_zip(year: str) -> Path | None:
    """Try to download EBA CSV zip for a given year."""
    dest = DATA_DIR / f"eba_transparency_{year}.zip"
    if dest.exists() and dest.stat().st_size > 10_000:
        info(f"  Already have: {dest.name}")
        return dest

    urls = EBA_CSV_URLS.get(year, [])
    for url in urls:
        info(f"  Trying: {url[-65:]}")
        content = http_get_bytes(url)
        if content:
            dest.write_bytes(content)
            info(f"  ✅ {dest.name} ({len(content)//1024}KB)")
            return dest
        time.sleep(0.5)
    return None


def extract_zip(zip_path: Path, year: str) -> list[Path]:
    """Extract ZIP and return list of CSV files."""
    extract_dir = DATA_DIR / f"eba_{year}"
    extract_dir.mkdir(exist_ok=True)
    try:
        with zipfile.ZipFile(str(zip_path), 'r') as zf:
            zf.extractall(str(extract_dir))
        csvs = list(extract_dir.rglob("*.csv"))
        info(f"  Extracted {len(csvs)} CSV file(s) to {extract_dir.name}/")
        return csvs
    except Exception as e:
        warn(f"  ZIP extraction failed: {e}")
        return []


def parse_eba_csv(csv_path: Path, year: str) -> list:
    """Parse EBA CSV file into bank records."""
    try:
        import pandas as pd
    except ImportError:
        warn("pandas not installed. Run: .venv/bin/pip install pandas")
        return []

    try:
        df = pd.read_csv(str(csv_path), encoding="utf-8", low_memory=False)
        info(f"  {csv_path.name}: {len(df)} rows × {len(df.columns)} cols")

        # Find bank identifier columns
        bank_col    = None
        country_col = None
        for col in df.columns:
            cl = col.lower()
            if any(k in cl for k in ["bank_name", "instname", "name", "entity"]):
                bank_col = col
            if any(k in cl for k in ["country", "cntry", "lei_cou"]):
                country_col = col

        if not bank_col:
            # Try first string column
            str_cols = [c for c in df.columns if df[c].dtype == object]
            bank_col = str_cols[0] if str_cols else None

        if not bank_col:
            warn(f"  Could not identify bank column in {csv_path.name}")
            return []

        records = []
        for _, row in df.iterrows():
            bank = str(row.get(bank_col, "")).strip()
            if not bank or bank.lower() in ("nan", ""):
                continue

            country = str(row.get(country_col, "EU")).strip() if country_col else "EU"
            metrics = {}

            for col in df.columns:
                col_upper = col.upper()
                for key, (metric_key, unit, pillar) in EBA_METRIC_MAP.items():
                    if key in col_upper:
                        val = row.get(col)
                        try:
                            fval = float(val)
                            if fval == fval and fval != 0:
                                metrics[metric_key] = {
                                    "value":  round(fval, 3),
                                    "unit":   unit,
                                    "pillar": pillar,
                                    "source": f"EBA Transparency Exercise {year}",
                                }
                        except (TypeError, ValueError):
                            pass

            if len(metrics) >= 3:
                records.append({
                    "bank_name": bank,
                    "country":   country,
                    "year":      year,
                    "metrics":   metrics,
                    "source":    f"EBA EU-wide Transparency Exercise {year}",
                })

        info(f"  → {len(records)} bank records with ≥3 metrics")
        return records

    except Exception as e:
        warn(f"  CSV parsing failed: {e}")
        return []


def load_manual_csvs(manual_dir: Path, year: str) -> list:
    """Load manually downloaded EBA CSVs from a directory."""
    csvs = list(manual_dir.glob(f"*{year}*.csv")) + \
           list(manual_dir.glob(f"eba*{year}*.csv"))
    records = []
    for csv_path in csvs:
        records.extend(parse_eba_csv(csv_path, year))
    return records


def build_training_pair(record: dict) -> dict | None:
    """Convert EBA bank record to training pair."""
    bank    = record["bank_name"]
    year    = record["year"]
    country = record["country"]
    metrics = record["metrics"]
    source  = record["source"]

    if len(metrics) < 3:
        return None

    metric_lines = []
    for key, data in sorted(metrics.items(), key=lambda x: x[1]["pillar"]):
        unit_str = "%" if data["unit"] == "%" else f" {data['unit']}"
        metric_lines.append(f"  {key.replace('_',' ').upper()}: {data['value']}{unit_str}")

    pillars   = set(d["pillar"] for d in metrics.values())
    user_content = (
        f"Bank: {bank}\nCountry: {country}\nData year: {year}\n"
        f"Source: {source}\n\n"
        f"TASK: Provide a CAMELS assessment for the following pillars: "
        f"{', '.join(sorted(pillars))}.\n"
        f"Cite the source for each metric. Assess Strong/Adequate/Weak/Critical.\n\n"
        f"--- FINANCIAL DATA ---\n" + "\n".join(metric_lines)
    )

    # Build structured response
    lines = [f"## CAMELS Analysis — {bank} ({year})",
             f"**Source:** {source} | **Country:** {country}", ""]

    for pillar in sorted(pillars):
        pil_metrics = {k: v for k, v in metrics.items() if v["pillar"] == pillar}
        if not pil_metrics:
            continue
        pillar_label = {"capital": "Capital Adequacy (C)",
                        "asset_quality": "Asset Quality (A)",
                        "earnings": "Earnings (E)",
                        "liquidity": "Liquidity (L)"}.get(pillar, pillar.title())
        # Simple threshold-based assessment
        assess = "Adequate"
        if pillar == "capital":
            cet1 = pil_metrics.get("cet1_ratio", {}).get("value", 0)
            assess = "Strong" if cet1 > 14 else "Adequate" if cet1 > 11 else "Weak"
        elif pillar == "asset_quality":
            npl = pil_metrics.get("npl_ratio", {}).get("value", 0)
            assess = "Strong" if npl < 2 else "Adequate" if npl < 5 else "Weak"
        elif pillar == "earnings":
            roe = pil_metrics.get("roe", {}).get("value", 0)
            assess = "Strong" if roe > 10 else "Adequate" if roe > 5 else "Weak"
        elif pillar == "liquidity":
            lcr = pil_metrics.get("lcr", {}).get("value", 0)
            assess = "Strong" if lcr > 140 else "Adequate" if lcr > 100 else "Weak"

        lines += [f"### {pillar_label}",
                  f"**Assessment: {assess}**", ""]
        for k, d in pil_metrics.items():
            lines.append(f"- {k.replace('_',' ').title()}: {d['value']}"
                         f"{d['unit']} [Source: {source}]")
        lines.append("")

    lines += [
        "### Peer Context",
        f"Data from {source} covers 120+ EU/EEA banks on a standardised "
        f"supervisory reporting basis — directly comparable across institutions.",
        "",
        "### Key Risks",
        "Point-in-time snapshot. Forward-looking assessment requires trend "
        "analysis and management commentary.",
    ]

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_content},
            {"role": "assistant", "content": "\n".join(lines)},
        ],
        "_meta": {
            "bank": bank, "country": country, "year": year,
            "pipeline": "eba_transparency", "quality": "structured",
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="*",
                        default=["2024", "2023", "2022", "2021", "2020"])
    parser.add_argument("--manual-dir", type=str, default=None,
                        help="Directory containing manually downloaded EBA CSVs")
    args = parser.parse_args()

    try:
        import pandas as pd
    except ImportError:
        warn("pandas not installed. Run: .venv/bin/pip install pandas openpyxl")
        return

    print(f"\nEBA Transparency Exercise Downloader (CSV format)")
    print(f"Years: {args.years}\n")

    all_pairs = []
    log = {"run_at": datetime.now().isoformat(), "years": {}}
    manual_needed = []

    for year in args.years:
        info(f"\n[{year}]")

        records = []

        # Try automatic download first
        zip_path = try_download_zip(year)
        if zip_path:
            csvs = extract_zip(zip_path, year)
            for csv_path in csvs:
                records.extend(parse_eba_csv(csv_path, year))
        elif args.manual_dir:
            records = load_manual_csvs(Path(args.manual_dir), year)

        if not records:
            warn(f"  No data for {year} — manual download needed")
            manual_needed.append(year)
            log["years"][year] = {"status": "failed"}
            continue

        pairs = [p for r in records if (p := build_training_pair(r))]
        all_pairs.extend(pairs)
        log["years"][year] = {"status": "ok", "records": len(records),
                               "pairs": len(pairs)}
        info(f"  {len(records)} banks → {len(pairs)} training pairs")

    # Write output
    if all_pairs:
        out_path = TRAINING_DIR / "eba_pairs.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for p in all_pairs:
                clean = {k: v for k, v in p.items() if not k.startswith("_")}
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")
        info(f"\n✅ Written: {out_path} ({len(all_pairs)} pairs)")
    else:
        warn("\nNo pairs generated from automatic download.")

    if manual_needed:
        print(f"\n{'='*60}")
        print(f"MANUAL DOWNLOAD NEEDED for years: {manual_needed}")
        print(f"{'='*60}")
        print(f"""
1. Go to: {MANUAL_URL}
2. Find each year → click 'Full database' → download ZIP
3. Save ZIPs to: raw_data/eba/
4. Re-run: .venv/bin/python scripts/download_eba_data.py

OR place CSV files directly in raw_data/eba/ and run:
   .venv/bin/python scripts/download_eba_data.py --manual-dir raw_data/eba
""")

    log_path = LOGS_DIR / "eba_download_log.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)
    info(f"Log: {log_path}")
    print(f"\nNext: ./run.sh --pairs-only")


if __name__ == "__main__":
    main()
