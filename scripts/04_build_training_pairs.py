#!/usr/bin/env python3
"""
04_build_training_pairs.py
==========================
Converts all source data → JSONL instruction pairs for QLoRA fine-tuning.

Pipeline A — Financial Statements:
  processed/financials/*.json → section-level CAMELS analysis prompts

Pipeline B — Rating Agency Material:
  processed/rating_agency/*.json → methodology Q&A pairs

Pipeline C — Credit Reports (GOLD):
  training_data/credit_report_pairs.jsonl → real analyst-written analyses

Pipeline D — EBA Transparency Exercise:
  training_data/eba_pairs.jsonl → 156 EU banks, capital metrics 2019–2025

Pipeline E — FDIC Call Reports:
  training_data/fdic_pairs.jsonl → top US banks, quarterly data

Run:
    python scripts/04_build_training_pairs.py

Output:
    training_data/combined_training.jsonl
    training_data/combined_eval.jsonl
    logs/build_pairs_stats.json
"""

import json
import random
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
PROCESSED_FIN = PROJECT_ROOT / "processed" / "financials"
PROCESSED_RA  = PROJECT_ROOT / "processed" / "rating_agency"
TRAINING_DIR  = PROJECT_ROOT / "training_data"
LOGS_DIR      = PROJECT_ROOT / "logs"
TRAINING_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

SYSTEM_PROMPT = (
    "You are a senior credit analyst specialising in bank credit analysis "
    "using the CAMELS framework (Capital Adequacy, Asset Quality, Management, "
    "Earnings, Liquidity, Sensitivity to Market Risk). "
    "You follow Moody's, S&P Global Ratings, and Fitch Ratings methodologies. "
    "Every numerical claim must cite a source in the format [Source: p.XX] or "
    "[Source: Table Y, p.XX]. "
    "If data is unavailable, state 'Data not available' — never fabricate figures. "
    "Structure responses with: Assessment (Strong/Adequate/Weak/Critical), "
    "key metrics, peer context, risks, and source citations."
)

SECTION_TO_PILLAR = {
    "capital_adequacy":        "Capital Adequacy (C)",
    "asset_quality":           "Asset Quality (A)",
    "management_governance":   "Management Quality (M)",
    "earnings_profitability":  "Earnings (E)",
    "liquidity_funding":       "Liquidity & Funding (L)",
    "market_risk_sensitivity": "Sensitivity to Market Risk (S)",
    "balance_sheet":           "Balance Sheet Overview",
    "income_statement":        "Income Statement Overview",
    "stress_testing":          "Stress Testing",
}

MIN_SECTION_CHARS = 400
MAX_PROMPT_CHARS  = 6000
MAX_TABLE_ROWS    = 25


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path, pipeline_tag: str, quality_tag: str) -> list:
    """Load a pre-built JSONL file and tag each pair with pipeline/quality."""
    if not path.exists():
        return []
    pairs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                pair = json.loads(line)
                if "_meta" not in pair:
                    pair["_meta"] = {}
                pair["_meta"].setdefault("pipeline", pipeline_tag)
                pair["_meta"].setdefault("quality",  quality_tag)
                pairs.append(pair)
            except json.JSONDecodeError:
                pass
    return pairs


def dedup(records: list) -> list:
    seen, out = set(), []
    for r in records:
        h = hashlib.md5(r["messages"][1]["content"][:300].encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            out.append(r)
    return out


def strip_meta(records: list) -> list:
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]


def write_jsonl(records: list, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Written: {path.name} ({len(records)} records)")


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline A — Financial statements
# ─────────────────────────────────────────────────────────────────────────────

def format_table_for_prompt(table: dict, max_rows: int = MAX_TABLE_ROWS) -> str:
    data = table.get("data", [])
    if not data:
        return ""
    lines = [f"[TABLE: {table.get('caption','Table')} | {table.get('source','')}]"]
    for row in data[:max_rows]:
        lines.append(" | ".join(str(c) for c in row))
    if len(data) > max_rows:
        lines.append(f"... ({len(data) - max_rows} more rows)")
    return "\n".join(lines)


def collect_section_pages(pages: list, section_name: str, max_pages: int = 8) -> tuple:
    matched = [p for p in pages if section_name in p.get("sections", [])][:max_pages]
    text_parts, tables = [], []
    for page in matched:
        text = page.get("text", "").strip()
        if len(text) >= MIN_SECTION_CHARS:
            text_parts.append(f"[Page {page['page_num']}]\n{text}")
        tables.extend(page.get("tables", []))
    return "\n\n".join(text_parts), tables


def build_section_prompt(bank_name, year, section_name, text, tables, key_metrics) -> str:
    pillar_label = SECTION_TO_PILLAR.get(section_name, section_name.replace("_", " ").title())
    section_metric_map = {
        "capital_adequacy":       ["cet1_ratio", "tier1_ratio", "total_capital_ratio",
                                   "leverage_ratio", "rwa", "mrel"],
        "earnings_profitability": ["nim", "rote", "cost_income"],
        "liquidity_funding":      ["lcr", "nsfr"],
        "asset_quality":          ["stage3_pct"],
    }
    parts = [
        f"Bank: {bank_name}", f"Reporting Year: {year}", "",
        f"TASK: Analyse the {pillar_label} section from the following extract. "
        f"Cite specific page numbers for every figure. "
        f"Assess as Strong / Adequate / Weak / Critical. Include: key ratios, "
        f"year-on-year changes, regulatory context, rating agency considerations, "
        f"and key risks.", "",
        "--- EXTRACTED ANNUAL REPORT CONTENT ---",
    ]
    metric_lines = [
        f"  {m.replace('_',' ').upper()}: {key_metrics[m]['value']} "
        f"[Source: p.{key_metrics[m]['source_page']}]"
        for m in section_metric_map.get(section_name, []) if m in key_metrics
    ]
    if metric_lines:
        parts += ["KEY METRICS EXTRACTED:"] + metric_lines + [""]
    if text:
        truncated = text[:MAX_PROMPT_CHARS]
        if len(text) > MAX_PROMPT_CHARS:
            truncated += "\n[... truncated ...]"
        parts += ["TEXT CONTENT:", truncated]
    if tables:
        parts += ["\nTABLES:"] + [format_table_for_prompt(t) for t in tables[:4]]
    return "\n".join(parts)


def build_template_response(bank_name, year, section_name, key_metrics, tables) -> str:
    pillar_label = SECTION_TO_PILLAR.get(section_name, section_name.replace("_", " ").title())
    cap_metrics = {
        "cet1_ratio":          ("CET1 ratio",               "%"),
        "tier1_ratio":         ("Tier 1 ratio",              "%"),
        "total_capital_ratio": ("Total capital ratio",       "%"),
        "leverage_ratio":      ("Leverage ratio",            "%"),
        "rwa":                 ("Risk-weighted assets",      "bn"),
        "mrel":                ("MREL ratio",                "%"),
        "nim":                 ("Net Interest Margin",       "%"),
        "rote":                ("Return on Tangible Equity", "%"),
        "cost_income":         ("Cost:Income ratio",         "%"),
        "lcr":                 ("LCR",                       "%"),
        "nsfr":                ("NSFR",                      "%"),
        "stage3_pct":          ("Stage 3 (NPL) ratio",      "%"),
    }
    lines = [f"## {pillar_label}", "", f"**Bank:** {bank_name} | **Year:** {year}", "", "### Key Metrics"]
    found = [
        f"- {label}: {key_metrics[k]['value']}{unit} [Source: p.{key_metrics[k]['source_page']}]"
        for k, (label, unit) in cap_metrics.items() if k in key_metrics
    ]
    lines += found if found else ["*(Metrics pending extraction)*"]
    if tables:
        lines += ["", "### Identified Financial Tables"]
        lines += [f"- {t.get('caption','Table')} ({t.get('source','')})" for t in tables[:6]]
    lines += ["", "### Analysis",
              f"[Template — requires analyst review or LLM generation]", "",
              f"Extracted content for {pillar_label} from {bank_name} {year} Annual Report."]
    return "\n".join(lines)


def process_financial_json(json_path: Path) -> list:
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    meta          = doc.get("metadata", {})
    bank_name     = meta.get("bank_name", "Unknown Bank")
    year          = meta.get("reporting_year", "Unknown Year")
    key_metrics   = doc.get("key_metrics", {})
    pages         = doc.get("pages", [])
    section_index = doc.get("section_index", {})
    pairs = []
    for section_name, page_nums in section_index.items():
        if not page_nums:
            continue
        text, tables = collect_section_pages(pages, section_name)
        if len(text) < MIN_SECTION_CHARS and not tables:
            continue
        pairs.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": build_section_prompt(
                    bank_name, year, section_name, text, tables, key_metrics)},
                {"role": "assistant", "content": build_template_response(
                    bank_name, year, section_name, key_metrics, tables)},
            ],
            "_meta": {
                "source_file": json_path.name, "bank_name": bank_name,
                "year": year, "section": section_name,
                "pipeline": "financial_template", "quality": "template",
            }
        })
    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline B — Rating agency material
# ─────────────────────────────────────────────────────────────────────────────

AGENCY_LABELS = {
    "moodys": "Moody's", "sp": "S&P Global Ratings", "fitch": "Fitch Ratings",
    "eba": "European Banking Authority (EBA)",
    "bis_basel": "Basel Committee on Banking Supervision (BCBS)",
    "boe_pra": "Bank of England / PRA", "fca": "Financial Conduct Authority",
    "fdic": "FDIC", "occ": "OCC", "fed": "Federal Reserve",
    "imf": "IMF", "dbrs": "DBRS Morningstar", "other": "Rating/Regulatory Body",
}

TOPIC_TEMPLATES = {
    "capital":            ["Explain how {agency} assesses bank capital adequacy.",
                           "What capital metrics does {agency} use?"],
    "asset_quality":      ["How does {agency} assess asset quality in bank credit analysis?"],
    "earnings":           ["How does {agency} evaluate bank profitability?"],
    "liquidity":          ["How does {agency} assess bank liquidity and funding?"],
    "management":         ["How does {agency} evaluate bank management quality?"],
    "sensitivity":        ["How does {agency} assess market risk for banks?"],
    "rating_methodology": ["Explain the overall rating methodology {agency} uses for banks.",
                           "What is the structure of {agency}'s bank rating framework?"],
    "rating_action":      ["Summarise this rating action and key credit factors from {agency}."],
    "stress_testing":     ["How does {agency} incorporate stress testing into bank credit analysis?"],
    "general":            ["Explain the following concept from {agency}'s bank credit methodology."],
}


def build_rating_agency_pair(chunk: dict, agency: str, doc_type: str) -> Optional[dict]:
    text, topics, wc = chunk.get("text",""), chunk.get("camels_topics",["general"]), chunk.get("word_count",0)
    if wc < 40:
        return None
    label    = AGENCY_LABELS.get(agency, "Rating Body")
    topic    = topics[0] if topics else "general"
    templates = TOPIC_TEMPLATES.get(topic, TOPIC_TEMPLATES["general"])
    question  = templates[chunk["chunk_id"] % len(templates)].format(agency=label)
    user      = (f"{question}\n\nDocument extract ({label}):\n\n{text[:1500]}"
                 if topic in ("general","rating_action") else
                 f"{question}\n\nFrom {label} documentation:\n\n{text[:2000]}")
    assistant = (f"Based on {label}'s "
                 f"{'rating report' if doc_type == 'rating_report' else 'methodology'}:\n\n"
                 f"{text[:2500]}\n\n"
                 f"**Topics:** {', '.join(topics)}\n**Source:** {label}")
    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "_meta": {"agency": agency, "topics": topics, "pipeline": "rating_agency",
                  "quality": "extracted"},
    }


def process_rating_agency_json(json_path: Path) -> list:
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    meta     = doc.get("metadata", {})
    agency   = meta.get("agency", "other")
    doc_type = meta.get("document_type", "general")
    return [p for c in doc.get("chunks",[]) if (p := build_rating_agency_pair(c, agency, doc_type))]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-frac", type=float, default=0.10)
    parser.add_argument("--seed",      type=int,   default=42)
    args = parser.parse_args()
    random.seed(args.seed)

    # ── A: Financial statements ───────────────────────────────────────────────
    fin_jsons = sorted(PROCESSED_FIN.glob("*.json"))
    financial_pairs = []
    print(f"\n[PIPELINE A] Financial statements: {len(fin_jsons)} files")
    for p in fin_jsons:
        pairs = process_financial_json(p)
        print(f"  {p.name}: {len(pairs)} pairs")
        financial_pairs.extend(pairs)

    # ── B: Rating agency ──────────────────────────────────────────────────────
    ra_jsons = sorted(PROCESSED_RA.glob("*.json"))
    rating_pairs = []
    print(f"\n[PIPELINE B] Rating agency docs: {len(ra_jsons)} files")
    for p in ra_jsons:
        pairs = process_rating_agency_json(p)
        print(f"  {p.name}: {len(pairs)} pairs")
        rating_pairs.extend(pairs)

    # ── C: Gold credit reports ────────────────────────────────────────────────
    credit_pairs = load_jsonl(TRAINING_DIR / "credit_report_pairs.jsonl",
                              "credit_report", "gold")
    if credit_pairs:
        print(f"\n[PIPELINE C] Credit reports (GOLD): {len(credit_pairs)} pairs ⭐")
    else:
        print(f"\n[PIPELINE C] Credit reports: none (add DOCX to credit_reports/)")

    # ── D: EBA Transparency Exercise ──────────────────────────────────────────
    eba_pairs = load_jsonl(TRAINING_DIR / "eba_pairs.jsonl",
                           "eba_transparency", "structured")
    if eba_pairs:
        print(f"\n[PIPELINE D] EBA transparency: {len(eba_pairs)} pairs")
    else:
        print(f"\n[PIPELINE D] EBA: none (run: python scripts/parse_eba_km.py)")

    # ── E: FDIC Call Reports ──────────────────────────────────────────────────
    fdic_pairs = load_jsonl(TRAINING_DIR / "fdic_pairs.jsonl",
                            "fdic_call_report", "structured")
    if fdic_pairs:
        print(f"\n[PIPELINE E] FDIC Call Reports: {len(fdic_pairs)} pairs")
    else:
        print(f"\n[PIPELINE E] FDIC: none (run: ./run.sh --download-fdic)")

    # ── Write pipeline-specific files ─────────────────────────────────────────
    if financial_pairs:
        write_jsonl(strip_meta(financial_pairs), TRAINING_DIR / "financial_pairs.jsonl")
    if rating_pairs:
        write_jsonl(strip_meta(rating_pairs), TRAINING_DIR / "rating_agency_pairs.jsonl")

    # ── Combine all sources ───────────────────────────────────────────────────
    all_pairs = financial_pairs + rating_pairs + eba_pairs + fdic_pairs + credit_pairs
    if credit_pairs:
        all_pairs += credit_pairs   # 2× weight for gold pairs
        print(f"  Gold pairs duplicated (2x weight)")

    if not all_pairs:
        print("\nNo pairs generated.")
        return

    all_pairs = dedup(all_pairs)
    random.shuffle(all_pairs)

    n_eval      = max(1, int(len(all_pairs) * args.eval_frac))
    eval_pairs  = all_pairs[:n_eval]
    train_pairs = all_pairs[n_eval:]

    write_jsonl(strip_meta(train_pairs), TRAINING_DIR / "combined_training.jsonl")
    write_jsonl(strip_meta(eval_pairs),  TRAINING_DIR / "combined_eval.jsonl")

    # ── Stats ──────────────────────────────────────────────────────────────────
    quality_counts  = {}
    pipeline_counts = {}
    for p in all_pairs:
        q    = p.get("_meta", {}).get("quality",  "unknown")
        pipe = p.get("_meta", {}).get("pipeline", "unknown")
        quality_counts[q]     = quality_counts.get(q, 0) + 1
        pipeline_counts[pipe] = pipeline_counts.get(pipe, 0) + 1

    stats = {
        "run_at":              datetime.now().isoformat(),
        "financial_pairs":     len(financial_pairs),
        "rating_agency_pairs": len(rating_pairs),
        "eba_pairs":           len(eba_pairs),
        "fdic_pairs":          len(fdic_pairs),
        "credit_report_pairs": len(credit_pairs),
        "total_after_dedup":   len(all_pairs),
        "train_count":         len(train_pairs),
        "eval_count":          len(eval_pairs),
        "by_quality":          quality_counts,
        "by_pipeline":         pipeline_counts,
    }
    with open(LOGS_DIR / "build_pairs_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n{'='*60}")
    print(f"TRAINING DATA BUILD COMPLETE")
    print(f"  Financial    : {len(financial_pairs)}")
    print(f"  Rating agency: {len(rating_pairs)}")
    print(f"  EBA          : {len(eba_pairs)}")
    print(f"  FDIC         : {len(fdic_pairs)}")
    print(f"  Gold (DOCX)  : {len(credit_pairs)}")
    print(f"  ─────────────────────────")
    print(f"  Total (dedup): {len(all_pairs)}")
    print(f"  Training     : {len(train_pairs)}")
    print(f"  Eval         : {len(eval_pairs)}")
    print(f"  By pipeline  : {pipeline_counts}")
    print(f"  By quality   : {quality_counts}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
