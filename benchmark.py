#!/usr/bin/env python3
"""
benchmark.py
============
Benchmark context utility — used by both training pair builder and main.py.

Loads the benchmark index and provides:
  - get_decile(metric, value) → 1-10
  - get_percentile_rank(metric, value) → 0-100
  - format_context(metric, value, bank_region) → human-readable benchmark string
  - format_full_context(metrics_dict, bank_region) → full benchmark block

Used in training pairs to teach the model what decile context looks like,
and used at inference time to inject live benchmark data into prompts.
"""

import json
import math
from pathlib import Path
from functools import lru_cache

PROJECT_ROOT = Path(__file__).resolve().parent

BENCHMARK_PATH = PROJECT_ROOT / "processed" / "benchmark_index.json"

# Ordinal suffixes
def ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"


@lru_cache(maxsize=1)
def load_index() -> dict:
    """Load benchmark index — cached after first load."""
    if not BENCHMARK_PATH.exists():
        return {}
    with open(BENCHMARK_PATH, encoding="utf-8") as f:
        return json.load(f)


def _percentile_from_dist(value: float, dist: dict) -> float:
    """Compute approximate percentile rank from distribution."""
    deciles = dist.get("deciles", [])
    mn      = dist.get("min", 0)
    if not deciles:
        return 50.0
    for i, threshold in enumerate(deciles):
        if value <= threshold:
            prev = deciles[i-1] if i > 0 else mn
            span = max(threshold - prev, 1e-9)
            return i * 10.0 + ((value - prev) / span) * 10.0
    return 99.0


def _get_dist(metric_key: str, region: str = None,
              recent: bool = True) -> dict:
    """Get distribution dict for a metric, optionally filtered by region."""
    index = load_index()
    if metric_key not in index:
        return {}
    entry    = index[metric_key]
    reg_key  = f"region_{region}" if region else None

    if reg_key and reg_key in entry:
        return entry[reg_key]
    if recent and "recent" in entry:
        return entry["recent"]
    return entry.get("all", {})


def get_decile(metric_key: str, value: float, region: str = None) -> int:
    """Return which decile (1-10) a value falls in."""
    dist    = _get_dist(metric_key, region)
    deciles = dist.get("deciles", [])
    if not deciles:
        return 5
    for i, threshold in enumerate(deciles):
        if value <= threshold:
            return i + 1
    return 10


def get_percentile_rank(metric_key: str, value: float,
                        region: str = None) -> float:
    """Return the percentile rank (0-100) of a value."""
    dist = _get_dist(metric_key, region)
    if not dist:
        return 50.0
    return round(_percentile_from_dist(value, dist), 1)


def format_metric_context(metric_key: str, value: float,
                           region: str = None) -> str:
    """
    Format a one-line benchmark context for a single metric.

    Example:
      "6th decile globally (median: 12.1%, p10: 9.8%, p90: 16.4%; n=847)"
    """
    index = load_index()
    if metric_key not in index:
        return ""

    entry    = index[metric_key]
    unit     = entry.get("unit", "%")
    unit_str = unit if unit == "%" else f" {unit}"
    higher_better = entry.get("higher_better", True)

    # Global distribution
    global_dist = entry.get("recent") or entry.get("all", {})
    if not global_dist:
        return ""

    global_decile = get_decile(metric_key, value)
    global_pct    = get_percentile_rank(metric_key, value)
    global_median = global_dist.get("median", 0)
    global_p10    = global_dist.get("p10", 0)
    global_p90    = global_dist.get("p90", 0)
    global_n      = global_dist.get("count", 0)

    # Qualitative descriptor
    if higher_better:
        qual = ("top decile" if global_decile == 10 else
                "top quartile" if global_decile >= 8 else
                "above median" if global_decile >= 6 else
                "below median" if global_decile >= 4 else
                "bottom quartile")
    else:
        qual = ("strongest decile (lowest)" if global_decile == 1 else
                "strong (low is good)" if global_decile <= 3 else
                "above median (lower = better)" if global_decile <= 5 else
                "below median (lower = better)" if global_decile <= 7 else
                "weakest (high is poor)")

    context = (f"{ordinal(global_decile)} decile globally — {qual} "
               f"(global median: {global_median}{unit_str}, "
               f"p10: {global_p10}{unit_str}, p90: {global_p90}{unit_str}; "
               f"n={global_n} bank-years)")

    # Add regional context if available
    if region:
        reg_dist = entry.get(f"region_{region}", {})
        if reg_dist and reg_dist.get("count", 0) >= 5:
            reg_decile = get_decile(metric_key, value, region)
            reg_median = reg_dist.get("median", 0)
            reg_n      = reg_dist.get("count", 0)
            context += (f"; {ordinal(reg_decile)} decile vs {region} peers "
                        f"({region} median: {reg_median}{unit_str}, n={reg_n})")

    return context


def format_benchmark_block(metrics: dict, region: str = None,
                            source_pages: dict = None) -> str:
    """
    Format a full benchmark context block for multiple metrics.

    Args:
        metrics: dict of {metric_key: value} or {metric_key: {"value": v, "source_page": p}}
        region:  bank's region (US, UK, EU, AU)
        source_pages: optional dict of {metric_key: page_number}

    Returns:
        Multi-line string ready for inclusion in a CAMELS analysis.

    Example output:
        ### Benchmark Context (vs Global Bank Population)

        | Metric | Value | Global Decile | Global Median | p10–p90 |
        |--------|-------|---------------|---------------|---------|
        | CET1 Ratio | 12.6% | 6th decile | 12.1% | 9.8–16.4% |
        ...
    """
    index = load_index()
    if not index:
        return ""

    lines = [
        "### Benchmark Context (vs Global Bank Population)",
        "",
        "| Metric | Value | Global Decile | Global Median | p10–p90 | Region Decile |",
        "|--------|-------|---------------|---------------|---------|---------------|",
    ]

    for metric_key, val in metrics.items():
        # Handle both flat values and dicts
        if isinstance(val, dict):
            value = val.get("value")
        else:
            value = val

        if value is None or metric_key not in index:
            continue

        entry    = index[metric_key]
        label    = entry.get("label", metric_key)
        unit     = entry.get("unit", "%")
        unit_str = unit if unit == "%" else f" {unit}"

        global_dist   = entry.get("recent") or entry.get("all", {})
        if not global_dist:
            continue

        global_decile = get_decile(metric_key, value)
        global_median = global_dist.get("median", 0)
        global_p10    = global_dist.get("p10", 0)
        global_p90    = global_dist.get("p90", 0)

        # Source citation
        page = (source_pages or {}).get(metric_key, "")
        value_str = f"{value}{unit_str}"
        if page:
            value_str += f" [p.{page}]"

        # Regional decile
        reg_cell = "—"
        if region:
            reg_dist = entry.get(f"region_{region}", {})
            if reg_dist and reg_dist.get("count", 0) >= 5:
                reg_decile = get_decile(metric_key, value, region)
                reg_cell   = f"{ordinal(reg_decile)} ({region})"

        lines.append(
            f"| {label} | {value_str} | "
            f"**{ordinal(global_decile)}** | "
            f"{global_median}{unit_str} | "
            f"{global_p10}–{global_p90}{unit_str} | "
            f"{reg_cell} |"
        )

    lines += [
        "",
        f"*n = {index.get('cet1_ratio', {}).get('all', {}).get('count', '?')} bank-years "
        f"(annual reports 2015–2025). "
        f"{'Recent 3-year distribution used where available. ' if True else ''}"
        f"Decile 1 = weakest, Decile 10 = strongest "
        f"(except cost:income and NPL ratio where lower = stronger).*",
    ]

    return "\n".join(lines)


def is_available() -> bool:
    """Check if benchmark index exists and is usable."""
    return BENCHMARK_PATH.exists() and load_index() != {}


if __name__ == "__main__":
    # Quick test
    import sys

    if not is_available():
        print("Benchmark index not found.")
        print("Run: python scripts/build_benchmark_index.py")
        sys.exit(1)

    print("Benchmark index loaded. Sample lookups:\n")

    test_cases = [
        ("cet1_ratio",    12.6, "UK", "Lloyds CET1 12.6%"),
        ("cet1_ratio",    15.2, "US", "JPMorgan CET1 15.2%"),
        ("nim",            2.1, "UK", "UK bank NIM 2.1%"),
        ("lcr",          145.0, "EU", "EU bank LCR 145%"),
        ("cost_income",   52.0, "UK", "UK bank C:I 52%"),
        ("stage3_pct",     2.3, "EU", "EU bank Stage3 2.3%"),
    ]

    for metric, value, region, description in test_cases:
        decile  = get_decile(metric, value, region)
        pct     = get_percentile_rank(metric, value, region)
        context = format_metric_context(metric, value, region)
        print(f"{description}")
        print(f"  Decile: {decile}/10 | Percentile: {pct:.0f}th")
        print(f"  {context}")
        print()
