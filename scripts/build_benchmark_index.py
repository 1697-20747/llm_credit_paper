#!/usr/bin/env python3
"""
build_benchmark_index.py
========================
Builds a benchmark index from all processed financial data.

For every metric (CET1, NIM, LCR, RoTE etc.), computes:
  - Population distribution (all banks, all years)
  - Decile thresholds
  - Recent-year distribution (last 3 years — more relevant for current analysis)
  - By-region breakdowns (US, UK, EU, AU, CA)

The benchmark index is used at inference time to add decile context to
single-bank analyses:
  "CET1 ratio 12.6% — 6th decile vs global bank population (p10: 9.8%, median: 12.1%, p90: 16.4%)"

IMPORTANT — RWA Currency Note:
  RWA is reported in local currency and is NOT comparable across currency zones.
  The benchmark index provides regional RWA distributions only:
    region_UK  → GBP  (Lloyds, Barclays, HSBC, NatWest)
    region_EU  → EUR  (Deutsche, BNP, UniCredit, Santander, etc.)
    region_US  → USD  (JPMorgan, BofA, etc.)
    region_AU  → AUD  (ANZ, Westpac, CBA, NAB)
    region_CA  → CAD  (RBC, TD, Scotiabank, BMO, CIBC)
  The global 'all' and 'recent' RWA distributions are retained but should
  only be used for absolute scale context, not peer comparison.

Run:
    python scripts/build_benchmark_index.py
    python scripts/build_benchmark_index.py --include-fdic
    python scripts/build_benchmark_index.py --include-eba

Output:
    processed/benchmark_index.json
    processed/benchmark_summary.json
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
    # RWA — regional distributions only (currency not comparable globally)
    "rwa":                 ("Risk-Weighted Assets",         "bn", True,  (0.0,  5000.0)),
}

# Region patterns for bank classification
# RWA currency by region: UK=GBP, EU=EUR, US=USD, AU=AUD, CA=CAD
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
        "commonwealth bank", "cba", "anz", "westpac", "national australia",
    ],
    # Canadian banks — RWA in CAD, not comparable with GBP/EUR/USD/AUD.
    # Always use region_CA for RWA peer comparison.
    "CA": [
        "royal bank of canada", "rbc", "toronto-dominion", "td bank",
        "bank of nova scotia", "scotiabank", "bank of montreal", "bmo",
        "canadian imperial", "cibc",
    ],
}


def classify_region(bank_name: str) -> str:
    name_lower = bank_name.lower()
    for region, patterns in REGION_PATTERNS.items():
        if any(p in name_lower for p in patterns):
            return region
    return "Other"


def percentile(sorted_vals: list, p: float) -> float:
    if not sorted_vals:
        return 0.0
    n   = len(sorted_vals)
    idx = (p / 100.0) * (n - 1)
    lo  = int(idx)
    hi  = min(lo + 1, n - 1)
    return sorted_vals[lo] + (idx - lo) * (sorted_vals[hi] - sorted_vals[lo])


def compute_distribution(values: list) -> dict:
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
        "deciles": [round(percentile(vals, i * 10), 3) for i in range(1, 10)],
    }


def get_decile(value: float, distribution: dict) -> int:
    if not distribution or "deciles" not in distribution:
        return 5
    for i, threshold in enumerate(distribution["deciles"]):
        if value <= threshold:
            return i + 1
    return 10


def get_percentile_rank(value: float, distribution: dict) -> float:
    if not distribution or "count" not in distribution:
        return 50.0
    deciles = distribution.get("deciles", [])
    if not deciles:
        return 50.0
    for i, threshold in enumerate(deciles):
        if value <= threshold:
            prev = deciles[i-1] if i > 0 else distribution["min"]
            return i * 10.0 + (value - prev) / max(threshold - prev, 0.001) * 10.0
    return 99.0


def format_benchmark_context(metric_key: str, value: float,
                              index: dict, recent_only: bool = True) -> str:
    if metric_key not in index:
        return ""
    meta          = METRIC_META.get(metric_key, (metric_key, "%", True, (0, 100)))
    label, unit, higher_better, _ = meta
    dist_key      = "recent" if recent_only and "recent" in index[metric_key] else "all"
    dist          = index[metric_key].get(dist_key, {})
    if not dist:
        return ""
    decile   = get_decile(value, dist)
    count    = dist.get("count", 0)
    median   = dist.get("median", 0)
    p10      = dist.get("p10", 0)
    p90      = dist.get("p90", 0)
    if higher_better:
        strength = ("top quartile" if decile >= 8 else "above median"
                    if decile >= 6 else "below median" if decile >= 4 else "bottom quartile")
    else:
        strength = ("top quartile (low=strong)" if decile <= 3 else "above median"
                    if decile <= 5 else "below median" if decile <= 7 else "bottom quartile")
    unit_str = unit if unit == "%" else f" {unit}"
    return (f"{label} {value}{unit_str} — {decile}th decile globally "
            f"({strength}; median: {median}{unit_str}, p10: {p10}{unit_str}, "
            f"p90: {p90}{unit_str}; n={count})")


def collect_from_financials() -> list:
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
            flat = {}
            for k, v in metrics.items():
                flat[k] = v.get("value") if isinstance(v, dict) else v
            if flat:
                records.append({"bank": bank, "year": str(year),
                                 "region": classify_region(bank),
                                 "source": "annual_report", "metrics": flat})
        except Exception:
            pass
    info(f"Collected {len(records)} records from annual reports")
    return records


def collect_from_fdic() -> list:
    fdic_path = TRAINING_DIR / "fdic_pairs.jsonl"
    if not fdic_path.exists():
        return []
    import re
    records = []
    with open(fdic_path, encoding="utf-8") as f:
        for line in f:
            try:
                pair  = json.loads(line.strip())
                user  = pair.get("messages", [{}])[1].get("content", "")
                bank_m = re.search(r"Bank: (.+)", user)
                year_m = re.search(r"Period: (\d{4})", user)
                bank   = bank_m.group(1).strip() if bank_m else "Unknown"
                year   = year_m.group(1) if year_m else "unknown"
                metrics = {}
                for lt in user.split("\n"):
                    m = re.match(r"\s+([A-Z_]+):\s+([\d.]+)(%| bn| m)?", lt)
                    if m:
                        metrics[m.group(1).lower()] = float(m.group(2))
                if metrics:
                    records.append({"bank": bank, "year": year,
                                     "region": "US", "source": "fdic",
                                     "metrics": metrics})
            except Exception:
                pass
    info(f"Collected {len(records)} records from FDIC data")
    return records


def collect_from_eba() -> list:
    eba_path = TRAINING_DIR / "eba_pairs.jsonl"
    if not eba_path.exists():
        return []
    import re
    records = []
    with open(eba_path, encoding="utf-8") as f:
        for line in f:
            try:
                pair  = json.loads(line.strip())
                user  = pair.get("messages", [{}])[1].get("content", "")
                bank_m = re.search(r"Bank: (.+)", user)
                year_m = re.search(r"Data year: (\d{4})", user)
                bank   = bank_m.group(1).strip() if bank_m else "Unknown"
                year   = year_m.group(1) if year_m else "unknown"
                metrics = {}
                for lt in user.split("\n"):
                    m = re.match(r"\s+([A-Z_]+):\s+([\d.]+)(%| bn)?", lt)
                    if m:
                        metrics[m.group(1).lower()] = float(m.group(2))
                if metrics:
                    records.append({"bank": bank, "year": year,
                                     "region": "EU", "source": "eba",
                                     "metrics": metrics})
            except Exception:
                pass
    info(f"Collected {len(records)} records from EBA data")
    return records


def build_index(records: list) -> dict:
    current_year  = datetime.now().year
    recent_years  = {str(y) for y in range(current_year - 3, current_year + 1)}
    all_values    = defaultdict(list)
    recent_values = defaultdict(list)
    region_values = defaultdict(lambda: defaultdict(list))

    for rec in records:
        year   = rec.get("year", "unknown")
        region = rec.get("region", "Other")
        for mk, value in rec.get("metrics", {}).items():
            if mk not in METRIC_META:
                continue
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            lo, hi = METRIC_META[mk][3]
            if not (lo <= value <= hi):
                continue
            all_values[mk].append(value)
            if year in recent_years:
                recent_values[mk].append(value)
            region_values[region][mk].append(value)

    index = {}
    for mk in METRIC_META:
        all_dist    = compute_distribution(all_values[mk])
        recent_dist = compute_distribution(recent_values[mk])
        if not all_dist:
            continue
        index[mk] = {
            "label":         METRIC_META[mk][0],
            "unit":          METRIC_META[mk][1],
            "higher_better": METRIC_META[mk][2],
            "all":           all_dist,
            "recent":        recent_dist if recent_dist else all_dist,
        }
        for region in ["US", "UK", "EU", "AU", "CA"]:
            reg_dist = compute_distribution(region_values[region][mk])
            if reg_dist and reg_dist["count"] >= 5:
                index[mk][f"region_{region}"] = reg_dist
        info(f"  {mk:<25} all={all_dist['count']:>4} "
             f"recent={recent_dist.get('count', 0):>4}  "
             f"median={all_dist['median']:>7.2f}{METRIC_META[mk][1]}")
    return index


def build_summary(index: dict) -> dict:
    summary = {"generated_at": datetime.now().isoformat(), "metrics": {}}
    for mk, data in index.items():
        d = data.get("all", {})
        summary["metrics"][mk] = {
            "label":             data["label"],
            "sample_size":       d.get("count", 0),
            "global_median":     f"{d.get('median', 0)}{data['unit']}",
            "p10_p90":           f"{d.get('p10', 0)}–{d.get('p90', 0)}{data['unit']}",
            "decile_thresholds": data["all"].get("deciles", []),
        }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-fdic", action="store_true")
    parser.add_argument("--include-eba",  action="store_true")
    args = parser.parse_args()

    print(f"\nBuilding Benchmark Index\n{'='*50}")
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

    print("\nComputing distributions...")
    index   = build_index(all_records)
    summary = build_summary(index)

    idx_path = PROCESSED_DIR / "benchmark_index.json"
    sum_path = PROCESSED_DIR / "benchmark_summary.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    with open(sum_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    info(f"\n✅ Benchmark index: {idx_path}")
    info(f"✅ Summary:         {sum_path}")

    print(f"\n{'='*70}")
    print(f"{'Metric':<28} {'N':>5}  {'Median':>8}  {'p10–p90':<20}")
    print(f"{'─'*70}")
    for mk, data in summary["metrics"].items():
        print(f"  {data['label']:<26} {data['sample_size']:>5}  "
              f"{data['global_median']:>8}  {data['p10_p90']:<20}")
    print(f"{'='*70}")
    print("\nNote: RWA is only meaningful within same-currency region_XX distributions.")
    print("Next: ./run.sh --pairs-only")


if __name__ == "__main__":
    main()
