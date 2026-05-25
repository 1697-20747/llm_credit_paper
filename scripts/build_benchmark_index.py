#!/usr/bin/env python3
"""
build_benchmark_index.py
========================
Builds a benchmark index from all processed financial data.

For every metric (CET1, NIM, LCR, RoTE etc.), computes:
  - Population distribution (all banks, all years)
  - Decile thresholds
  - Recent-year distribution (last 3 years — more relevant for current analysis)
  - By-region breakdowns (US, UK, EU)

The benchmark index is used at inference time to add decile context to
single-bank analyses:
  "CET1 ratio 12.6% — 6th decile vs global bank population (p10: 9.8%, median: 12.1%, p90: 16.4%)"

Run:
    python scripts/build_benchmark_index.py
    python scripts/build_benchmark_index.py --include-fdic  # include FDIC data
    python scripts/build_benchmark_index.py --include-eba   # include EBA data

Output:
    processed/benchmark_index.json     ← full index with distributions
    processed/benchmark_summary.json   ← human-readable summary
    logs/benchmark_build_log.json
"""

import json
import math
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
PROCESSED_FIN  = PROJECT_ROOT / "processed" / "financials"
PROCESSED_DIR  = PROJECT_ROOT / "processed"
TRAINING_DIR   = PROJECT_ROOT / "training_data"
LOGS_DIR       = PROJECT_ROOT / "logs"
PROCESSED_DIR.mkdir(exist_ok=True)

GREEN = '\033[0;32m'; YELLOW = '\033[1;33m'; NC = '\033[0m'
def info(msg): print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg): print(f"{YELLOW}[WARN]{NC}  {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# Metric definitions — label, unit, higher_is_better, typical_range
# ─────────────────────────────────────────────────────────────────────────────
METRIC_META = {
    "cet1_ratio":          ("CET1 Ratio",                   "%",  True,  (8.0,  20.0)),
    "tier1_ratio":         ("Tier 1 Capital Ratio",         "%",  True,  (9.0,  22.0)),
    "total_capital_ratio": ("Total Capital Ratio",          "%",  True,  (11.0, 25.0)),
    "leverage_ratio":      ("Leverage Ratio",               "%",  True,  (3.0,  10.0)),
    "mrel":                ("MREL Ratio",                   "%",  True,  (20.0, 40.0)),
    "nim":                 ("Net Interest Margin",          "%",  True,  (0.5,  4.5)),
    "rote":                ("Return on Tangible Equity",    "%",  True,  (-5.0, 25.0)),
    "roe":                 ("Return on Equity",             "%",  True,  (-5.0, 20.0)),
    "roa":                 ("Return on Assets",             "%",  True,  (-0.5, 2.5)),
    "cost_income":         ("Cost:Income Ratio",            "%",  False, (30.0, 90.0)),
    "efficiency_ratio":    ("Efficiency Ratio",             "%",  False, (30.0, 90.0)),
    "lcr":                 ("Liquidity Coverage Ratio",     "%",  True,  (80.0, 300.0)),
    "nsfr":                ("Net Stable Funding Ratio",     "%",  True,  (80.0, 160.0)),
    "stage3_pct":          ("Stage 3 / NPL Ratio",         "%",  False, (0.0,  15.0)),
    "npl_ratio":           ("NPL Ratio",                   "%",  False, (0.0,  15.0)),
    "rwa":                 ("Risk-Weighted Assets",         "bn", True,  (0.0,  5000.0)),
}

# Region classification based on bank name patterns
REGION_PATTERNS = {
    "UK": [
        "lloyds", "barclays", "natwest", "hsbc", "standard chartered",
        "nationwide", "santander uk", "metro bank", "virgin money",
    ],
    "EU": [
        "deutsche bank", "bnp paribas", "unicredit", "ing ", "abn amro",
        "société générale", "credit agricole", "intesa", "bbva", "santander",
        "commerzbank", "rabobank", "nordea", "dnb", "svenska",
    ],
    "US": [
        "jpmorgan", "bank of america", "wells fargo", "citigroup", "goldman sachs",
        "morgan stanley", "us bancorp", "pnc", "truist", "capital one",
        "american express", "bny mellon", "state street", "charles schwab",
        "fifth third", "regions", "keycorp", "huntington", "comerica", "zions",
    ],
    "AU": [
        "commonwealth bank", "anz", "westpac", "national australia",
    ],
}


def classify_region(bank_name: str) -> str:
    name_lower = bank_name.lower()
    for region, patterns in REGION_PATTERNS.items():
        if any(p in name_lower for p in patterns):
            return region
    return "Other"


def percentile(sorted_vals: list, p: float) -> float:
    """Compute the p-th percentile of a sorted list."""
    if not sorted_vals:
        return 0.0
    n   = len(sorted_vals)
    idx = (p / 100.0) * (n - 1)
    lo  = int(idx)
    hi  = min(lo + 1, n - 1)
    return sorted_vals[lo] + (idx - lo) * (sorted_vals[hi] - sorted_vals[lo])


def compute_distribution(values: list) -> dict:
    """Compute full distribution statistics for a list of values."""
    if not values:
        return {}
    vals = sorted(v for v in values if v is not None and not math.isnan(v))
    if not vals:
        return {}
    n = len(vals)
    mean = sum(vals) / n
    variance = sum((v - mean) ** 2 for v in vals) / n
    return {
        "count":  n,
        "mean":   round(mean, 3),
        "median": round(percentile(vals, 50), 3),
        "std":    round(math.sqrt(variance), 3),
        "min":    round(vals[0], 3),
        "max":    round(vals[-1], 3),
        "p10":    round(percentile(vals, 10), 3),
        "p25":    round(percentile(vals, 25), 3),
        "p50":    round(percentile(vals, 50), 3),
        "p75":    round(percentile(vals, 75), 3),
        "p90":    round(percentile(vals, 90), 3),
        # Decile thresholds — d[i] is the threshold between decile i and i+1
        "deciles": [round(percentile(vals, i * 10), 3) for i in range(1, 10)],
    }


def get_decile(value: float, distribution: dict) -> int:
    """Return which decile (1-10) a value falls in."""
    if not distribution or "deciles" not in distribution:
        return 5  # unknown — return middle
    deciles = distribution["deciles"]
    for i, threshold in enumerate(deciles):
        if value <= threshold:
            return i + 1
    return 10


def get_percentile_rank(value: float, distribution: dict) -> float:
    """Return the percentile rank (0-100) of a value."""
    if not distribution or "count" not in distribution:
        return 50.0
    # Approximate using the decile thresholds
    deciles = distribution.get("deciles", [])
    if not deciles:
        return 50.0
    for i, threshold in enumerate(deciles):
        if value <= threshold:
            return i * 10.0 + (value - (deciles[i-1] if i > 0 else distribution["min"])) / \
                   max(threshold - (deciles[i-1] if i > 0 else distribution["min"]), 0.001) * 10.0
    return 99.0


def format_benchmark_context(metric_key: str, value: float,
                              index: dict, recent_only: bool = True) -> str:
    """
    Format a benchmark context string for a single metric value.

    Example output:
    "CET1 ratio 12.6% — 6th decile globally (p10: 9.8%, median: 12.1%, p90: 16.4%;
    n=847 banks). UK peer median: 14.2% (3rd decile vs UK banks)."
    """
    if metric_key not in index:
        return ""

    meta       = METRIC_META.get(metric_key, (metric_key, "%", True, (0, 100)))
    label      = meta[0]
    unit       = meta[1]
    higher_better = meta[2]

    dist_key   = "recent" if recent_only and "recent" in index[metric_key] else "all"
    dist       = index[metric_key].get(dist_key, {})
    if not dist:
        return ""

    decile     = get_decile(value, dist)
    pct_rank   = round(get_percentile_rank(value, dist), 1)
    count      = dist.get("count", 0)
    median     = dist.get("median", 0)
    p10        = dist.get("p10", 0)
    p90        = dist.get("p90", 0)

    # Qualitative description
    if higher_better:
        if decile >= 8:
            strength = "top quartile"
        elif decile >= 6:
            strength = "above median"
        elif decile >= 4:
            strength = "below median"
        else:
            strength = "bottom quartile"
    else:
        # Lower is better (cost:income, NPL ratio)
        if decile <= 3:
            strength = "top quartile (low = strong)"
        elif decile <= 5:
            strength = "above median (lower = better)"
        elif decile <= 7:
            strength = "below median (lower = better)"
        else:
            strength = "bottom quartile (lower = better)"

    unit_str = unit if unit == "%" else f" {unit}"
    context  = (
        f"{label} {value}{unit_str} — {decile}th decile globally "
        f"({strength}; global median: {median}{unit_str}, "
        f"p10: {p10}{unit_str}, p90: {p90}{unit_str}; "
        f"n={count} bank-years)"
    )

    return context


# ─────────────────────────────────────────────────────────────────────────────
# Data collection from processed files
# ─────────────────────────────────────────────────────────────────────────────

def collect_from_financials() -> list:
    """Collect metrics from processed annual report JSON files."""
    records = []
    json_files = list(PROCESSED_FIN.glob("*.json"))
    info(f"Scanning {len(json_files)} processed financial files...")

    for json_path in json_files:
        try:
            with open(json_path, encoding="utf-8") as f:
                doc = json.load(f)
            meta    = doc.get("metadata", {})
            bank    = meta.get("bank_name", "Unknown")
            year    = meta.get("reporting_year") or "unknown"
            metrics = doc.get("key_metrics", {})

            if not metrics:
                continue

            flat_metrics = {}
            for k, v in metrics.items():
                if isinstance(v, dict):
                    flat_metrics[k] = v.get("value")
                elif isinstance(v, (int, float)):
                    flat_metrics[k] = v

            if flat_metrics:
                records.append({
                    "bank":    bank,
                    "year":    str(year),
                    "region":  classify_region(bank),
                    "source":  "annual_report",
                    "metrics": flat_metrics,
                })
        except Exception:
            pass

    info(f"Collected {len(records)} records from annual reports")
    return records


def collect_from_fdic() -> list:
    """Collect metrics from FDIC JSONL training pairs."""
    fdic_path = TRAINING_DIR / "fdic_pairs.jsonl"
    if not fdic_path.exists():
        return []

    records = []
    with open(fdic_path, encoding="utf-8") as f:
        for line in f:
            try:
                pair  = json.loads(line.strip())
                # Extract from user message
                user  = pair.get("messages", [{}])[1].get("content", "")
                # Parse bank/year/metrics from user content
                bank_m  = __import__("re").search(r"Bank: (.+)", user)
                year_m  = __import__("re").search(r"Period: (\d{4})", user)
                bank    = bank_m.group(1).strip() if bank_m else "Unknown"
                year    = year_m.group(1) if year_m else "unknown"

                # Extract metric values from user content lines
                import re
                metrics = {}
                for line_text in user.split("\n"):
                    # Pattern: "  METRIC_NAME: 12.3%"
                    m = re.match(r"\s+([A-Z_]+):\s+([\d.]+)(%| bn| m)?", line_text)
                    if m:
                        key = m.group(1).lower()
                        val = float(m.group(2))
                        metrics[key] = val

                if metrics:
                    records.append({
                        "bank":    bank,
                        "year":    year,
                        "region":  "US",
                        "source":  "fdic",
                        "metrics": metrics,
                    })
            except Exception:
                pass

    info(f"Collected {len(records)} records from FDIC data")
    return records


def collect_from_eba() -> list:
    """Collect metrics from EBA JSONL training pairs."""
    eba_path = TRAINING_DIR / "eba_pairs.jsonl"
    if not eba_path.exists():
        return []

    records = []
    with open(eba_path, encoding="utf-8") as f:
        for line in f:
            try:
                pair  = json.loads(line.strip())
                user  = pair.get("messages", [{}])[1].get("content", "")
                import re
                bank_m   = re.search(r"Bank: (.+)", user)
                year_m   = re.search(r"Data year: (\d{4})", user)
                country_m = re.search(r"Country: (.+)", user)
                bank    = bank_m.group(1).strip() if bank_m else "Unknown"
                year    = year_m.group(1) if year_m else "unknown"
                country = country_m.group(1).strip() if country_m else "EU"

                metrics = {}
                for line_text in user.split("\n"):
                    m = re.match(r"\s+([A-Z_]+):\s+([\d.]+)(%| bn)?", line_text)
                    if m:
                        key = m.group(1).lower()
                        val = float(m.group(2))
                        metrics[key] = val

                if metrics:
                    records.append({
                        "bank":    bank,
                        "year":    year,
                        "region":  "EU",
                        "source":  "eba",
                        "metrics": metrics,
                    })
            except Exception:
                pass

    info(f"Collected {len(records)} records from EBA data")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Build index
# ─────────────────────────────────────────────────────────────────────────────

def build_index(records: list) -> dict:
    """Build the full benchmark index from collected records."""
    current_year = datetime.now().year
    recent_years = {str(y) for y in range(current_year - 3, current_year + 1)}

    # Collect all values per metric
    all_values    = defaultdict(list)
    recent_values = defaultdict(list)
    region_values = defaultdict(lambda: defaultdict(list))

    for rec in records:
        year    = rec.get("year", "unknown")
        region  = rec.get("region", "Other")
        metrics = rec.get("metrics", {})

        for metric_key, value in metrics.items():
            if metric_key not in METRIC_META:
                continue
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue

            lo, hi = METRIC_META[metric_key][3]
            if not (lo <= value <= hi):
                continue  # filter outliers / bad data

            all_values[metric_key].append(value)
            if year in recent_years:
                recent_values[metric_key].append(value)
            region_values[region][metric_key].append(value)

    # Build index
    index = {}
    for metric_key in METRIC_META:
        all_dist    = compute_distribution(all_values[metric_key])
        recent_dist = compute_distribution(recent_values[metric_key])

        if not all_dist:
            continue

        index[metric_key] = {
            "label":         METRIC_META[metric_key][0],
            "unit":          METRIC_META[metric_key][1],
            "higher_better": METRIC_META[metric_key][2],
            "all":           all_dist,
            "recent":        recent_dist if recent_dist else all_dist,
        }

        # Add regional distributions
        for region in ["US", "UK", "EU", "AU"]:
            reg_dist = compute_distribution(region_values[region][metric_key])
            if reg_dist and reg_dist["count"] >= 5:
                index[metric_key][f"region_{region}"] = reg_dist

        info(f"  {metric_key:<25} all={all_dist['count']:>4} "
             f"recent={recent_dist.get('count', 0):>4}  "
             f"median={all_dist['median']:>7.2f}{METRIC_META[metric_key][1]}")

    return index


def build_summary(index: dict) -> dict:
    """Build human-readable summary of benchmark index."""
    summary = {
        "generated_at": datetime.now().isoformat(),
        "metrics":      {},
    }
    for metric_key, data in index.items():
        all_dist = data.get("all", {})
        summary["metrics"][metric_key] = {
            "label":         data["label"],
            "sample_size":   all_dist.get("count", 0),
            "global_median": f"{all_dist.get('median', 0)}{data['unit']}",
            "p10_p90":       f"{all_dist.get('p10', 0)}–{all_dist.get('p90', 0)}{data['unit']}",
            "decile_thresholds": data["all"].get("deciles", []),
        }
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-fdic", action="store_true")
    parser.add_argument("--include-eba",  action="store_true")
    args = parser.parse_args()

    print(f"\nBuilding Benchmark Index")
    print(f"{'='*50}")

    all_records = collect_from_financials()

    if args.include_fdic:
        all_records += collect_from_fdic()

    if args.include_eba:
        all_records += collect_from_eba()

    if not all_records:
        warn("No records found. Run ./run.sh --reprocess first.")
        return

    info(f"\nTotal records: {len(all_records)}")
    by_region = defaultdict(int)
    for r in all_records:
        by_region[r["region"]] += 1
    for region, count in sorted(by_region.items()):
        info(f"  {region}: {count}")

    print(f"\nComputing distributions...")
    index   = build_index(all_records)
    summary = build_summary(index)

    # Save
    index_path   = PROCESSED_DIR / "benchmark_index.json"
    summary_path = PROCESSED_DIR / "benchmark_summary.json"

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    info(f"\n✅ Benchmark index: {index_path}")
    info(f"✅ Summary:         {summary_path}")

    # Print summary table
    print(f"\n{'='*70}")
    print(f"{'Metric':<28} {'N':>5}  {'Median':>8}  {'p10–p90':<20}")
    print(f"{'─'*70}")
    for metric_key, data in summary["metrics"].items():
        print(f"  {data['label']:<26} {data['sample_size']:>5}  "
              f"{data['global_median']:>8}  {data['p10_p90']:<20}")
    print(f"{'='*70}")
    print(f"\nNext: ./run.sh --pairs-only  (pairs will include benchmark context)")


if __name__ == "__main__":
    main()
