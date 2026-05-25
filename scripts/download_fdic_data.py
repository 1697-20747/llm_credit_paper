#!/usr/bin/env python3
"""
download_fdic_data.py
=====================
Downloads FDIC Call Report data via the FDIC BankFind API.

Requires free API key:
  1. https://api.fdic.gov/banks/docs → Request API Key
  2. export FDIC_API_KEY=your_key_here

Usage:
    export FDIC_API_KEY=your_key_here
    python scripts/download_fdic_data.py
    python scripts/download_fdic_data.py --limit 50 --years 3

Output:
    training_data/fdic_pairs.jsonl
    logs/fdic_download_log.json
"""

import json
import time
import ssl
import os
import argparse
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl._create_unverified_context()

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
TRAINING_DIR  = PROJECT_ROOT / "training_data"
LOGS_DIR      = PROJECT_ROOT / "logs"
TRAINING_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

GREEN = '\033[0;32m'; YELLOW = '\033[1;33m'; RED = '\033[0;31m'; NC = '\033[0m'
def info(msg):  print(f"{GREEN}[INFO]{NC}  {msg}", flush=True)
def warn(msg):  print(f"{YELLOW}[WARN]{NC}  {msg}", flush=True)
def error(msg): print(f"{RED}[ERROR]{NC} {msg}", flush=True)

FDIC_API = "https://banks.data.fdic.gov/api"

SYSTEM_PROMPT = (
    "You are a senior credit analyst specialising in bank credit analysis "
    "using the CAMELS framework. You follow Moody's, S&P Global Ratings, "
    "and Fitch Ratings methodologies. Every numerical claim must cite a source. "
    "If data is unavailable, state 'Data not available' — never fabricate figures."
)

# Confirmed working field names from FDIC API (verified against live data)
FDIC_FIELDS = {
    # Capital
    "IDT1RWAJR": ("tier1_ratio",        "%",  "capital",      "Tier 1 Capital Ratio"),
    "RBCRWAJ":   ("total_capital_ratio", "%",  "capital",      "Total Risk-Based Capital Ratio"),
    "RBC1AAJ":   ("leverage_ratio",      "%",  "capital",      "Leverage Ratio"),
    # Asset quality
    "NCLNLSR":   ("net_chargeoff_rate",  "%",  "asset_quality","Net Charge-Off Rate"),
    "LNLSNTV":   ("npl_ratio",           "%",  "asset_quality","Non-Current Loan Rate"),
    # Earnings
    "ROE":       ("roe",                 "%",  "earnings",     "Return on Equity"),
    "ROA":       ("roa",                 "%",  "earnings",     "Return on Assets"),
    "NIMY":      ("nim",                 "%",  "earnings",     "Net Interest Margin"),
    "EEFFR":     ("efficiency_ratio",    "%",  "earnings",     "Efficiency Ratio"),
    # Liquidity
    "LNLSDEPR":  ("loan_deposit_ratio",  "%",  "liquidity",    "Loan-to-Deposit Ratio"),
    # Size context
    "ASSET":     ("total_assets_m",      "m",  "size",         "Total Assets ($000s)"),
}

INSTITUTION_FIELDS = "CERT,NAME,STALP,ASSET,CITY"
FINANCIAL_FIELDS   = ",".join(list(FDIC_FIELDS.keys()) + ["REPDTE", "CERT", "NAME", "STALP"])


def get_headers(api_key: str) -> dict:
    h = {"User-Agent": "CAMELS-Research-Tool/1.0"}
    if api_key:
        h["X-API-Key"] = api_key
    return h


def fdic_get(endpoint: str, params: dict, api_key: str) -> dict:
    time.sleep(0.3)
    url = f"{FDIC_API}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=get_headers(api_key))
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            error("HTTP 403 — check FDIC_API_KEY is set correctly")
        else:
            warn(f"HTTP {e.code}: {endpoint}")
        return {}
    except Exception as e:
        warn(f"API error: {e}")
        return {}


def get_large_banks(limit: int, api_key: str) -> list:
    info(f"Fetching top {limit} US banks by assets...")
    data = fdic_get("institutions", {
        "filters":    "ACTIVE:1",
        "fields":     INSTITUTION_FIELDS,
        "sort_by":    "ASSET",
        "sort_order": "DESC",
        "limit":      limit,
        "offset":     0,
        "output":     "json",
    }, api_key)
    banks = [rec.get("data", rec) for rec in data.get("data", [])]
    info(f"Found {len(banks)} banks")
    return banks


def get_bank_financials(cert: str, start_year: int,
                        end_year: int, api_key: str) -> list:
    data = fdic_get("financials", {
        "filters":    f"CERT:{cert} AND REPDTE:[{start_year}0101 TO {end_year}1231]",
        "fields":     FINANCIAL_FIELDS,
        "sort_by":    "REPDTE",
        "sort_order": "DESC",
        "limit":      20,
        "offset":     0,
        "output":     "json",
    }, api_key)
    return [rec.get("data", rec) for rec in data.get("data", [])]


def build_pair(bank_name: str, state: str, year: str,
               metrics: dict) -> dict | None:
    analysis_metrics = {k: v for k, v in metrics.items()
                        if v["pillar"] != "size"}
    if len(analysis_metrics) < 3:
        return None

    source  = f"FDIC Call Report — {bank_name} {year} Q4"
    assets  = metrics.get("total_assets_m", {}).get("value", 0)
    asset_s = (f"${assets/1_000_000:.1f}bn" if assets > 1_000_000
               else f"${assets/1_000:.1f}bn"  if assets > 1_000
               else f"${assets:.0f}m"          if assets else "unknown")

    lines = []
    for key, data in sorted(analysis_metrics.items(),
                            key=lambda x: x[1]["pillar"]):
        lines.append(f"  {data['label']}: {data['value']:.2f}%")

    user_content = (
        f"Bank: {bank_name} ({state}, USA)\n"
        f"Period: {year} Q4\nTotal Assets: {asset_s}\nSource: {source}\n\n"
        f"TASK: Provide a CAMELS assessment for the available pillars.\n"
        f"Cite '{source}' as source. Assess Strong/Adequate/Weak/Critical.\n\n"
        f"--- FDIC CALL REPORT DATA ---\n" + "\n".join(lines)
    )

    resp = [f"## CAMELS Analysis — {bank_name} ({year} Q4)",
            f"**Source:** {source} | **State:** {state} | **Assets:** {asset_s}", ""]

    pillar_labels = {
        "capital":      "Capital Adequacy (C)",
        "asset_quality":"Asset Quality (A)",
        "earnings":     "Earnings (E)",
        "liquidity":    "Liquidity (L)",
    }

    for pillar, plabel in pillar_labels.items():
        pm = {k: v for k, v in analysis_metrics.items()
              if v["pillar"] == pillar}
        if not pm:
            continue

        assess = "Adequate"
        if pillar == "capital":
            t1 = pm.get("tier1_ratio", {}).get("value", 0)
            assess = "Strong" if t1 > 12 else "Adequate" if t1 > 8 else "Weak"
        elif pillar == "asset_quality":
            nco = pm.get("net_chargeoff_rate", {}).get("value", 0)
            assess = "Strong" if nco < 0.3 else "Adequate" if nco < 1.0 else "Weak"
        elif pillar == "earnings":
            roa = pm.get("roa", {}).get("value", 0)
            assess = "Strong" if roa > 1.2 else "Adequate" if roa > 0.7 else "Weak"
        elif pillar == "liquidity":
            ldr = pm.get("loan_deposit_ratio", {}).get("value", 0)
            assess = "Strong" if ldr < 80 else "Adequate" if ldr < 100 else "Weak"

        resp += [f"### {plabel}", f"**Assessment: {assess}**", ""]
        for k, d in pm.items():
            resp.append(f"- {d['label']}: {d['value']:.2f}% [Source: {source}]")
        resp.append("")

    resp += [
        "### Peer Context",
        "US bank medians (2023): Tier 1 ~13%, Net charge-off rate ~0.5%, "
        "ROA ~1.1%, NIM ~3.2%, Efficiency ratio ~60%, Loan:deposit ~70%.",
        "",
        "### Key Risks",
        "Point-in-time FDIC Call Report data. Forward-looking assessment "
        "requires management commentary and loan book concentration analysis.",
    ]

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_content},
            {"role": "assistant", "content": "\n".join(resp)},
        ],
        "_meta": {
            "bank": bank_name, "state": state, "year": year,
            "pipeline": "fdic_call_report", "quality": "structured",
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()

    api_key = os.environ.get("FDIC_API_KEY", "")
    if not api_key:
        warn("FDIC_API_KEY not set — will likely get 403.")
        warn("Get free key: https://api.fdic.gov/banks/docs")
        warn("Then: export FDIC_API_KEY=your_key")

    current_year = datetime.now().year
    start_year   = current_year - args.years
    end_year     = current_year

    print(f"\nFDIC Call Report Downloader")
    print(f"Top {args.limit} banks | {start_year}–{end_year}\n")

    banks = get_large_banks(args.limit, api_key)
    if not banks:
        error("Could not fetch bank list.")
        return

    all_pairs = []
    log       = {"run_at": datetime.now().isoformat(), "banks": {}}

    for i, bank in enumerate(banks, 1):
        cert  = str(bank.get("CERT") or bank.get("cert", ""))
        name  = str(bank.get("NAME") or bank.get("name", "Unknown"))
        state = str(bank.get("STALP") or bank.get("stalp", "US"))

        if not cert:
            continue

        print(f"  [{i}/{len(banks)}] {name} ({state})", end=" ", flush=True)

        financials = get_bank_financials(cert, start_year, end_year, api_key)
        if not financials:
            print("— no data")
            log["banks"][name] = {"status": "no_data"}
            continue

        # Use December (Q4) periods only for annual consistency
        annual = [r for r in financials
                  if str(r.get("REPDTE", ""))[4:6] == "12"]

        pairs_for_bank = []
        for rec in annual:
            date = str(rec.get("REPDTE", ""))
            year = date[:4] if date else "unknown"

            metrics = {}
            for field, (mk, unit, pillar, label) in FDIC_FIELDS.items():
                val = rec.get(field)
                if val is not None:
                    try:
                        fval = float(val)
                        if fval == fval and fval != 0:
                            metrics[mk] = {
                                "value":  round(fval, 3),
                                "unit":   unit,
                                "pillar": pillar,
                                "label":  label,
                            }
                    except (TypeError, ValueError):
                        pass

            pair = build_pair(name, state, year, metrics)
            if pair:
                pairs_for_bank.append(pair)

        all_pairs.extend(pairs_for_bank)
        print(f"— {len(annual)} years → {len(pairs_for_bank)} pairs")
        log["banks"][name] = {"status": "ok", "pairs": len(pairs_for_bank)}

    if all_pairs:
        out = TRAINING_DIR / "fdic_pairs.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for p in all_pairs:
                clean = {k: v for k, v in p.items() if not k.startswith("_")}
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")
        info(f"\n✅ Written: {out} ({len(all_pairs)} pairs)")
        print(f"\nNext: ./run.sh --pairs-only")
    else:
        warn("No pairs generated.")

    with open(LOGS_DIR / "fdic_download_log.json", "w") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    main()
