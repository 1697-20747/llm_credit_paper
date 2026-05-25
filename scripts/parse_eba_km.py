#!/usr/bin/env python3
"""
parse_eba_km.py
===============
Parses the EBA Historical Key Metrics CSV file (long format) into
structured training pairs for the CAMELS benchmark index.

The EBA KM file has one row per bank × metric × period.
This script pivots it to one row per bank × period, then builds pairs.

Usage:
    python scripts/parse_eba_km.py
    python scripts/parse_eba_km.py --file raw_data/eba/Historical\ KM.csv

Output:
    training_data/eba_pairs.jsonl
    logs/eba_parse_log.json
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "raw_data" / "eba"
TRAINING_DIR = PROJECT_ROOT / "training_data"
LOGS_DIR     = PROJECT_ROOT / "logs"
TRAINING_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

GREEN = '\033[0;32m'; YELLOW = '\033[1;33m'; RED = '\033[0;31m'; NC = '\033[0m'
def info(msg): print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg): print(f"{YELLOW}[WARN]{NC}  {msg}")

SYSTEM_PROMPT = (
    "You are a senior credit analyst specialising in bank credit analysis "
    "using the CAMELS framework. You follow Moody's, S&P Global Ratings, "
    "and Fitch Ratings methodologies. Every numerical claim must cite a source. "
    "If data is unavailable, state 'Data not available' — never fabricate figures."
)

# Map EBA Label strings → CAMELS metric keys
# Using substring matching — EBA labels are verbose
EBA_LABEL_MAP = {
    "COMMON EQUITY TIER 1 CAPITAL RATIO":      ("cet1_ratio",          "ratio", "capital"),
    "COMMON EQUITY TIER 1 CAPITAL (net":        ("cet1_capital_m",      "m",     "capital"),
    "TOTAL RISK EXPOSURE AMOUNT":               ("rwa_m",               "m",     "capital"),
    "Leverage ratio - using a transitional":    ("leverage_ratio",      "ratio", "capital"),
    "Tier 1 capital - transitional":            ("tier1_capital_m",     "m",     "capital"),
    "Total Assets":                             ("total_assets_m",      "m",     "size"),
    "TOTAL EQUITY":                             ("total_equity_m",      "m",     "capital"),
    "Financial assets at amortised cost":       ("loans_amortised_m",   "m",     "asset_quality"),
    "Gross carrying amount on Loans":           ("gross_loans_m",       "m",     "asset_quality"),
    "Credit risk (excluding CCR":               ("credit_risk_rwa_m",   "m",     "capital"),
    "Operational risk":                         ("op_risk_rwa_m",       "m",     "capital"),
    "Position, foreign exchange":               ("market_risk_rwa_m",   "m",     "sensitivity"),
    "Counterparty credit risk":                 ("ccr_rwa_m",           "m",     "capital"),
}

# Amounts in EBA file are in millions EUR
# Ratios are expressed as decimals (e.g. 0.1565 = 15.65%)


def detect_unit(label: str, amount: float) -> tuple:
    """Detect if a value is a ratio (0-1 range) or absolute (millions)."""
    if "RATIO" in label.upper() or "ratio" in label.lower():
        # Convert decimal ratio to percentage
        if abs(amount) <= 1.5:   # e.g. 0.1565 → 15.65%
            return amount * 100, "%"
        return amount, "%"       # already in percent form
    return amount, "m"           # millions EUR


def parse_period(period_str: str, exercise: str) -> tuple:
    """Parse period string like '202403' → (year, quarter)."""
    period_str = str(period_str).strip()
    if len(period_str) == 6:
        year    = period_str[:4]
        month   = int(period_str[4:6])
        quarter = f"Q{(month - 1) // 3 + 1}"
        return year, quarter
    # Fall back to exercise year
    year = str(exercise).split("_")[0]
    return year, "Q4"


def build_training_pair(bank_name: str, country: str, year: str,
                         quarter: str, metrics: dict) -> dict | None:
    if len(metrics) < 3:
        return None

    source    = f"EBA EU-wide Transparency Exercise {year}"
    period    = f"{year} {quarter}"

    # Build metrics display
    metric_lines = []
    for key, data in sorted(metrics.items(), key=lambda x: x[1]["pillar"]):
        val    = data["value"]
        unit   = data["unit"]
        unit_s = "%" if unit == "%" else f"m EUR" if unit == "m" else unit
        metric_lines.append(f"  {data['label']}: {val:.2f} {unit_s}")

    pillars = sorted(set(d["pillar"] for d in metrics.values()
                         if d["pillar"] != "size"))

    user_content = (
        f"Bank: {bank_name}\n"
        f"Country: {country}\n"
        f"Period: {period}\n"
        f"Source: {source}\n\n"
        f"TASK: Provide a CAMELS assessment covering: {', '.join(pillars)}.\n"
        f"Cite '{source}' as source for each metric.\n\n"
        f"--- EBA TRANSPARENCY DATA ---\n" + "\n".join(metric_lines)
    )

    # Build structured response
    lines = [
        f"## CAMELS Analysis — {bank_name} ({period})",
        f"**Source:** {source} | **Country:** {country}",
        "",
    ]

    # Capital section
    cap = {k: v for k, v in metrics.items() if v["pillar"] == "capital"}
    if cap:
        cet1_r = metrics.get("cet1_ratio", {}).get("value", 0)
        lev    = metrics.get("leverage_ratio", {}).get("value", 0)
        assess = ("Strong"   if cet1_r > 14 else
                  "Adequate" if cet1_r > 11 else
                  "Weak"     if cet1_r > 0  else "Indeterminate")
        lines += [f"### Capital Adequacy (C)", f"**Assessment: {assess}**", ""]
        for k, d in cap.items():
            unit_s = "%" if d["unit"] == "%" else "m EUR"
            lines.append(f"- {d['label']}: {d['value']:.2f}{unit_s} [Source: {source}]")
        if cet1_r > 0:
            lines.append(f"- CET1 headroom above 8% Pillar 1 minimum: "
                         f"{cet1_r - 8:.1f}pp [Source: {source}]")
        lines.append("")

    # Asset quality proxy (loan volumes — limited in this file)
    aq = {k: v for k, v in metrics.items() if v["pillar"] == "asset_quality"}
    if aq:
        lines += [f"### Asset Quality (A)", f"**Assessment: Data limited in KM file**", ""]
        for k, d in aq.items():
            lines.append(f"- {d['label']}: {d['value']:.0f}m EUR [Source: {source}]")
        lines.append("")

    # Size context
    size = metrics.get("total_assets_m", {})
    if size:
        assets = size["value"]
        size_cat = ("G-SIB / Major" if assets > 500_000 else
                    "Large"         if assets > 100_000 else
                    "Mid-size"      if assets > 20_000  else "Smaller")
        lines += [
            "### Peer Context",
            f"Total assets: {assets:.0f}m EUR ({size_cat} EU bank). "
            f"Data from {source} covers 120+ EU/EEA banks on a standardised "
            f"supervisory reporting basis.",
            "",
        ]

    lines += [
        "### Key Risks",
        "EBA KM file provides capital and balance sheet snapshot only. "
        "Full CAMELS assessment requires profitability, liquidity, and "
        "asset quality data from the bank's annual report.",
    ]

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_content},
            {"role": "assistant", "content": "\n".join(lines)},
        ],
        "_meta": {
            "bank":     bank_name,
            "country":  country,
            "year":     year,
            "quarter":  quarter,
            "pipeline": "eba_transparency",
            "quality":  "structured",
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default=None)
    parser.add_argument("--year-filter", nargs="*", default=None,
                        help="Only process specific years e.g. 2023 2024")
    args = parser.parse_args()

    try:
        import pandas as pd
    except ImportError:
        print("pandas not installed. Run: .venv/bin/pip install pandas")
        return

    # Find the CSV file
    if args.file:
        csv_path = Path(args.file)
    else:
        # Auto-detect any CSV in raw_data/eba/
        csvs = list(DATA_DIR.glob("*.csv")) + list(DATA_DIR.glob("*.CSV"))
        if not csvs:
            print(f"No CSV files found in {DATA_DIR}")
            print(f"Save EBA Historical KM.csv to {DATA_DIR} and re-run.")
            return
        csv_path = csvs[0]
        if len(csvs) > 1:
            info(f"Multiple CSVs found — using: {csv_path.name}")

    info(f"Loading: {csv_path.name}")
    df = pd.read_csv(str(csv_path), low_memory=False)
    info(f"Loaded: {len(df):,} rows, {df['Name'].nunique()} banks")

    if args.year_filter:
        df = df[df["exercise"].astype(str).str[:4].isin(args.year_filter)]
        info(f"After year filter: {len(df):,} rows")

    # Process each bank × period combination
    all_pairs = []
    skipped   = 0
    processed = 0

    # Group by bank + period
    group_cols = ["Name", "Country", "exercise", "Period"]
    for (bank_name, country, exercise, period_str), group in df.groupby(group_cols):

        year, quarter = parse_period(period_str, exercise)

        # Only use December (Q4) or June (H1) periods for annual/semi-annual
        if str(period_str)[4:6] not in ("12", "06"):
            skipped += 1
            continue

        metrics = {}
        for _, row in group.iterrows():
            label  = str(row.get("Label", "")).strip()
            amount = row.get("Amount")

            try:
                amount = float(amount)
            except (TypeError, ValueError):
                continue

            if amount != amount:  # NaN check
                continue

            # Match to CAMELS metric
            for prefix, (metric_key, unit_type, pillar) in EBA_LABEL_MAP.items():
                if label.startswith(prefix):
                    value, unit = detect_unit(label, amount)
                    # Use most recent value if duplicate
                    if metric_key not in metrics:
                        metrics[metric_key] = {
                            "value":  round(value, 4),
                            "unit":   unit,
                            "pillar": pillar,
                            "label":  label[:60],
                        }
                    break

        pair = build_training_pair(bank_name, country, year, quarter, metrics)
        if pair:
            all_pairs.append(pair)
            processed += 1
        else:
            skipped += 1

    info(f"Generated: {processed} pairs | Skipped: {skipped}")

    if not all_pairs:
        warn("No pairs generated. Check CSV format.")
        return

    # Write output
    out_path = TRAINING_DIR / "eba_pairs.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for p in all_pairs:
            clean = {k: v for k, v in p.items() if not k.startswith("_")}
            f.write(json.dumps(clean, ensure_ascii=False) + "\n")

    info(f"✅ Written: {out_path} ({len(all_pairs)} pairs)")

    # Stats
    years    = sorted(set(p["_meta"]["year"] for p in all_pairs))
    banks    = len(set(p["_meta"]["bank"] for p in all_pairs))
    quarters = sorted(set(p["_meta"]["quarter"] for p in all_pairs))

    print(f"\n{'='*50}")
    print(f"  Banks    : {banks}")
    print(f"  Years    : {years}")
    print(f"  Quarters : {quarters}")
    print(f"  Pairs    : {len(all_pairs)}")
    print(f"{'='*50}")
    print(f"\nNext: ./run.sh --pairs-only")

    log = {
        "run_at": datetime.now().isoformat(),
        "source": str(csv_path),
        "pairs":  len(all_pairs),
        "banks":  banks,
        "years":  years,
    }
    with open(LOGS_DIR / "eba_parse_log.json", "w") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    main()
