#!/usr/bin/env python3
"""
test_analysis.py
================
Standalone CAMELS analysis — works with both Ollama and MLX server.

Usage:
    # With Ollama (recommended for 16GB Mac):
    ollama serve   # in separate terminal
    python test_analysis.py \
        --pdf financials/2025-lbg-annual-report.pdf \
        --pillar3 pillar3/2025-lbg-fy-pillar-3.pdf \
        --bank "Lloyds Banking Group"

    # With MLX server (32GB+ only):
    ./serve_mlx.sh   # in separate terminal
    python test_analysis.py \
        --pdf financials/2025-lbg-annual-report.pdf \
        --bank "Lloyds Banking Group" \
        --llm-url http://localhost:8080
"""

import re
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

import fitz

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR   = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Section keywords
# ─────────────────────────────────────────────────────────────────────────────

CAMELS_SECTIONS = {
    "capital_adequacy": [
        "cet1", "common equity tier 1", "tier 1 capital", "total capital ratio",
        "risk-weighted assets", "rwa", "leverage ratio", "mrel", "capital buffer",
        "pillar 1", "pillar 2", "capital ratio", "capital position", "own funds",
    ],
    "asset_quality": [
        "stage 1", "stage 2", "stage 3", "expected credit loss", "ecl",
        "impairment", "non-performing", "npl", "loan loss", "provisions",
        "coverage ratio", "cost of risk", "ifrs 9", "forbearance",
    ],
    "management": [
        "board of directors", "governance", "risk committee", "audit committee",
        "remuneration", "risk appetite", "internal audit", "risk culture",
        "three lines", "conduct risk",
    ],
    "earnings": [
        "net interest income", "net interest margin", "nim", "return on equity",
        "return on tangible equity", "rote", "return on assets", "cost income",
        "operating profit", "pre-tax profit", "efficiency ratio",
    ],
    "liquidity": [
        "liquidity coverage ratio", "lcr", "net stable funding ratio", "nsfr",
        "hqla", "high quality liquid assets", "loan to deposit",
        "wholesale funding", "customer deposits", "liquidity pool",
    ],
    "sensitivity": [
        "market risk", "interest rate risk", "irrbb", "value at risk", "var",
        "structural hedge", "fvoci", "foreign exchange", "fx risk", "duration",
    ],
}

KEY_METRIC_PATTERNS = [
    ("cet1_ratio",          r"CET\s*1\s+(?:ratio|capital ratio)\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("tier1_ratio",         r"[Tt]ier\s*1\s+(?:ratio|capital ratio)\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("total_capital_ratio", r"[Tt]otal\s+capital\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("leverage_ratio",      r"[Ll]everage\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("mrel",                r"MREL\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("nim",                 r"[Nn]et\s+[Ii]nterest\s+[Mm]argin\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("rote",                r"[Rr]eturn\s+on\s+[Tt]angible\s+[Ee]quity\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("roe",                 r"[Rr]eturn\s+on\s+[Ee]quity\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("roa",                 r"[Rr]eturn\s+on\s+[Aa]ssets\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("lcr",                 r"[Ll]iquidity\s+[Cc]overage\s+[Rr]atio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("nsfr",                r"[Nn]et\s+[Ss]table\s+[Ff]unding\s+[Rr]atio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("cost_income",         r"[Cc]ost\s*[:/]\s*[Ii]ncome\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("stage3_pct",          r"[Ss]tage\s*3\s+[:\s]+(?:[\d\.]+(?:bn|m)[,\s]+)?(\d+\.?\d*)\s*%"),
    ("rwa_bn",              r"[Rr]isk[- ]?weighted\s+assets\s*[:\s£$€]+(\d[\d,\.]+)\s*(?:bn|billion)"),
]

SYSTEM_PROMPT = (
    "You are a senior credit analyst specialising in bank credit analysis "
    "using the CAMELS framework. You follow Moody's, S&P Global Ratings, "
    "and Fitch Ratings methodologies. Every numerical claim must cite "
    "[Source: p.XX]. If data is unavailable write 'Data not available' — "
    "never fabricate. Structure: Assessment (Strong/Adequate/Weak/Critical), "
    "Key Metrics, Analysis, Peer Context, Key Risks, Rating Agency Commentary."
)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_pdf(path: Path) -> tuple[dict, dict]:
    doc, pages, metrics = fitz.open(str(path)), {}, {}
    for i, page in enumerate(doc):
        text = page.get_text("text")
        pnum = i + 1
        pages[pnum] = text
        for name, pattern in KEY_METRIC_PATTERNS:
            if name not in metrics:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    try:
                        metrics[name] = {
                            "value":       float(m.group(1).replace(",", "")),
                            "source_page": pnum,
                            "source_file": path.name,
                        }
                    except ValueError:
                        pass
    doc.close()
    return pages, metrics


def extract_htm(path: Path) -> tuple[dict, dict]:
    raw   = path.read_text(encoding="utf-8", errors="replace")
    clean = re.sub(r"<[^>]+>", " ", raw)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&")
    clean = re.sub(r"\s{3,}", "  ", clean)
    chunks = [clean[i:i+3000] for i in range(0, len(clean), 3000)]
    pages  = {i+1: c for i, c in enumerate(chunks)}
    metrics = {}
    for name, pattern in KEY_METRIC_PATTERNS:
        for pnum, text in pages.items():
            if name not in metrics:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    try:
                        metrics[name] = {
                            "value":       float(m.group(1).replace(",", "")),
                            "source_page": pnum,
                            "source_file": path.name,
                        }
                    except ValueError:
                        pass
    return pages, metrics


def classify_sections(pages: dict) -> dict:
    index = {s: [] for s in CAMELS_SECTIONS}
    for pnum, text in pages.items():
        tl = text.lower()
        for section, keywords in CAMELS_SECTIONS.items():
            if sum(1 for kw in keywords if kw in tl) >= 2:
                index[section].append(pnum)
    return {k: v for k, v in index.items() if v}


def get_text(pages: dict, page_nums: list, max_chars: int = 3500) -> str:
    parts, total = [], 0
    for pnum in page_nums[:6]:
        text = pages.get(pnum, "").strip()
        if text:
            parts.append(f"[Page {pnum}]\n{text}")
            total += len(text)
        if total > max_chars:
            break
    combined = "\n\n".join(parts)
    return combined[:max_chars] + "\n[... truncated ...]" \
           if len(combined) > max_chars else combined


def load_benchmark() -> dict:
    path = PROJECT_ROOT / "processed" / "benchmark_index.json"
    return json.loads(path.read_text()) if path.exists() else {}


def get_decile_str(mk: str, value: float, index: dict) -> str:
    if mk not in index:
        return ""
    dist    = index[mk].get("recent") or index[mk].get("all", {})
    deciles = dist.get("deciles", [])
    if not deciles:
        return ""
    for i, t in enumerate(deciles):
        if value <= t:
            d  = i + 1
            med = dist.get("median", 0)
            p10 = dist.get("p10", 0)
            p90 = dist.get("p90", 0)
            n   = dist.get("count", 0)
            u   = index[mk].get("unit", "%")
            return (f"{d}th decile globally "
                    f"(median: {med}{u}, p10: {p10}{u}, p90: {p90}{u}; n={n})")
    return "10th decile"


# ─────────────────────────────────────────────────────────────────────────────
# LLM — supports both Ollama and MLX server
# ─────────────────────────────────────────────────────────────────────────────

def call_ollama(prompt: str, base_url: str, model: str,
                max_tokens: int = 1200) -> str:
    """Call via Ollama API format."""
    payload = json.dumps({
        "model":    model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "stream":  False,
        "options": {"temperature": 0.05, "num_predict": max_tokens},
    }).encode()

    url = f"{base_url.rstrip('/')}/api/chat"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode())
            return data.get("message", {}).get("content", "[No response]")
    except Exception as e:
        return f"[ERROR calling Ollama: {e}]"


def call_openai_compat(prompt: str, base_url: str, model: str,
                       max_tokens: int = 1200) -> str:
    """Call via OpenAI-compatible API (MLX server)."""
    payload = json.dumps({
        "model":       model,
        "messages":    [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": 0.05,
    }).encode()

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[ERROR calling MLX server: {e}]"


def call_llm(prompt: str, base_url: str, model: str) -> str:
    """Auto-detect API type and call appropriately."""
    if "11434" in base_url or "ollama" in base_url.lower():
        return call_ollama(prompt, base_url, model)
    else:
        return call_openai_compat(prompt, base_url, model)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────────────────────

PILLAR_METRICS = {
    "capital_adequacy": ["cet1_ratio","tier1_ratio","total_capital_ratio",
                         "leverage_ratio","rwa_bn","mrel"],
    "asset_quality":    ["stage3_pct","npl_ratio"],
    "earnings":         ["nim","rote","roe","roa","cost_income"],
    "liquidity":        ["lcr","nsfr"],
    "sensitivity":      [],
    "management":       [],
}

PILLAR_LABELS = {
    "capital_adequacy": "Capital Adequacy (C)",
    "asset_quality":    "Asset Quality (A)",
    "management":       "Management Quality (M)",
    "earnings":         "Earnings (E)",
    "liquidity":        "Liquidity & Funding (L)",
    "sensitivity":      "Sensitivity to Market Risk (S)",
}


def build_prompt(pillar: str, bank: str, year: str, ar_text: str,
                 metrics: dict, benchmark: dict, p3_text: str = "") -> str:
    label = PILLAR_LABELS.get(pillar, pillar.replace("_", " ").title())

    metric_lines = []
    for mk in PILLAR_METRICS.get(pillar, []):
        if mk in metrics:
            v    = metrics[mk]
            bc   = get_decile_str(mk, v["value"], benchmark)
            line = (f"  {mk.replace('_',' ').upper()}: {v['value']} "
                    f"[Source: {v['source_file']}, p.{v['source_page']}]")
            if bc:
                line += f"  ← {bc}"
            metric_lines.append(line)

    parts = [
        f"Bank: {bank}", f"Reporting Year: {year}", "",
        f"TASK: Analyse {label}. Cite every figure with [Source: p.XX].",
        f"Assess: Strong / Adequate / Weak / Critical.",
        f"Include regulatory context, peer benchmarking, rating agency view.",
        "",
    ]
    if metric_lines:
        parts += ["EXTRACTED METRICS (with global decile context):"]
        parts += metric_lines
        parts += [""]
    if ar_text:
        parts += ["ANNUAL REPORT CONTENT:", ar_text, ""]
    if p3_text:
        parts += ["PILLAR 3 CONTENT:", p3_text, ""]

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Report assembly
# ─────────────────────────────────────────────────────────────────────────────

def assemble(bank: str, year: str, analyses: dict,
             metrics: dict, benchmark: dict) -> str:
    lines = [
        f"# CAMELS Credit Analysis — {bank} ({year})",
        f"",
        f"*Generated: {datetime.now().strftime('%d %B %Y %H:%M')}*  ",
        f"*All figures cited to source document*",
        f"",
        "---",
        "",
    ]

    # Benchmark table
    if benchmark and metrics:
        bm_rows = []
        for mk, (label, unit) in [
            ("cet1_ratio",    ("CET1 Ratio",         "%")),
            ("leverage_ratio",("Leverage Ratio",      "%")),
            ("nim",           ("Net Interest Margin", "%")),
            ("rote",          ("RoTE",                "%")),
            ("lcr",           ("LCR",                 "%")),
            ("cost_income",   ("Cost:Income",         "%")),
            ("stage3_pct",    ("Stage 3 Ratio",       "%")),
        ]:
            if mk not in metrics or mk not in benchmark:
                continue
            v    = metrics[mk]
            dist = benchmark[mk].get("recent") or benchmark[mk].get("all", {})
            if not dist or not dist.get("deciles"):
                continue
            decile = next((i+1 for i,t in enumerate(dist["deciles"])
                           if v["value"] <= t), 10)
            bm_rows.append(
                f"| {label} | {v['value']}{unit} [p.{v['source_page']}] | "
                f"**{decile}th** | {dist.get('median',0)}{unit} | "
                f"{dist.get('p10',0)}–{dist.get('p90',0)}{unit} |"
            )
        if bm_rows:
            lines += [
                "## Benchmark Context (vs Global Bank Population)",
                "",
                "| Metric | Value | Global Decile | Median | p10–p90 |",
                "|--------|-------|---------------|--------|---------|",
            ] + bm_rows + ["", "---", ""]

    # CAMELS sections
    for pillar, label in PILLAR_LABELS.items():
        analysis = analyses.get(pillar, "Analysis not available.")
        lines += [f"## {label}", "", analysis, "", "---", ""]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",      required=True)
    parser.add_argument("--pillar3",  default=None)
    parser.add_argument("--bank",     required=True)
    parser.add_argument("--year",     default=None)
    parser.add_argument("--llm-url",  default="http://localhost:11434")
    parser.add_argument("--model",    default="camels-base")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    print(f"\n{'='*60}")
    print(f" CAMELS Analysis — {args.bank}")
    print(f" File   : {pdf_path.name}")
    print(f" Server : {args.llm_url}  model: {args.model}")
    print(f"{'='*60}\n")

    # Extract
    print("Extracting annual report...", end=" ", flush=True)
    if pdf_path.suffix.lower() in (".htm", ".html"):
        pages, metrics = extract_htm(pdf_path)
    else:
        pages, metrics = extract_pdf(pdf_path)
    year = args.year or re.search(r"(20\d{2})", pdf_path.name)
    year = year.group(1) if hasattr(year, "group") else (year or "2025")
    print(f"✅ {len(pages)} pages, {len(metrics)} metrics")
    for k, v in metrics.items():
        print(f"   {k}: {v['value']} [p.{v['source_page']}]")

    # Pillar 3
    p3_pages, p3_metrics = {}, {}
    if args.pillar3:
        p3_path = Path(args.pillar3)
        print(f"Extracting Pillar 3: {p3_path.name}...", end=" ", flush=True)
        p3_pages, p3_metrics = extract_pdf(p3_path)
        metrics.update(p3_metrics)
        print(f"✅ {len(p3_pages)} pages, {len(p3_metrics)} additional metrics")

    section_index    = classify_sections(pages)
    p3_section_index = classify_sections(p3_pages) if p3_pages else {}
    benchmark        = load_benchmark()
    print(f"Sections: {list(section_index.keys())}")
    print(f"Benchmark: {'loaded' if benchmark else 'not found'}\n")

    # Analyse each pillar
    analyses = {}
    for pillar in PILLAR_LABELS:
        print(f"Analysing {PILLAR_LABELS[pillar]}...", end=" ", flush=True)
        ar_text = get_text(pages, section_index.get(pillar, []))
        p3_text = get_text(p3_pages, p3_section_index.get(pillar, []),
                           max_chars=1500) if p3_pages else ""
        prompt  = build_prompt(pillar, args.bank, year, ar_text,
                               metrics, benchmark, p3_text)
        resp    = call_llm(prompt, args.llm_url, args.model)
        analyses[pillar] = resp
        preview = resp.replace("\n", " ")[:80]
        print(f"✅ {preview}")

    # Assemble
    print("\nAssembling report...", end=" ", flush=True)
    report  = assemble(args.bank, year, analyses, metrics, benchmark)
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe    = args.bank.replace(" ", "_")
    md_path = OUTPUT_DIR / f"{safe}_{year}_{ts}.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"✅")

    # Audit JSON
    audit_path = OUTPUT_DIR / f"{safe}_{year}_{ts}_audit.json"
    with open(audit_path, "w") as f:
        json.dump({
            "bank": args.bank, "year": year,
            "generated": datetime.now().isoformat(),
            "sources": {
                "annual_report": str(pdf_path),
                "pillar3": str(args.pillar3) if args.pillar3 else None,
            },
            "metrics": metrics,
            "sections": list(section_index.keys()),
        }, f, indent=2)

    print(f"\n{'='*60}")
    print(f" Report : {md_path}")
    print(f" Audit  : {audit_path}")
    print(f"\n View: cat '{md_path}'")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
