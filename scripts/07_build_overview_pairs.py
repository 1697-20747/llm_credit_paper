#!/usr/bin/env python3
"""
07_build_overview_pairs.py
==========================
Pipeline F — Overview training pairs.

Generates two-paragraph overview training pairs from annual report JSON files:
  Para 1: Institutional Profile  (size, ownership, markets, ratings)
  Para 2: Annual Review Highlights (strategic themes, major events, headline performance)

These pairs teach the model to produce tight, factual, third-person overview
sections — the first section of every credit paper.

Two modes:
  --template  : build template pairs immediately (no API cost, lower quality)
  --upgrade   : call Claude Haiku API to generate real analyst-quality overviews
                (recommended, ~$3–5 for full dataset)

The --upgrade mode reads the first pages of each source PDF directly via fitz
to get richer content than what's in the processed JSON.

Run:
    # Fast, no cost — template responses for training shape
    .venv/bin/python3 scripts/07_build_overview_pairs.py --template

    # Best quality — real analyst prose via Claude API
    export ANTHROPIC_API_KEY=sk-ant-...
    .venv/bin/python3 scripts/07_build_overview_pairs.py --upgrade

    # Upgrade only the ones not yet done (resumable)
    .venv/bin/python3 scripts/07_build_overview_pairs.py --upgrade --resume

Output:
    training_data/overview_pairs.jsonl
    training_data/overview_pairs_upgraded.jsonl  (if --upgrade)
"""

import os
import re
import json
import time
import ssl
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
PROCESSED_DIR  = PROJECT_ROOT / "processed" / "financials"
FINANCIALS_DIR = PROJECT_ROOT / "financials"
PILLAR3_DIR    = PROJECT_ROOT / "pillar3"
TRAINING_DIR   = PROJECT_ROOT / "training_data"
LOGS_DIR       = PROJECT_ROOT / "logs"
TRAINING_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl._create_unverified_context()

OVERVIEW_SYSTEM = (
    "You are a senior credit analyst writing institutional overviews for credit papers. "
    "Write in the third person. Every factual claim must be cited [Source: p.XX]. "
    "Be precise and concise — no opinion, no waffle. "
    "If a fact is not clearly stated in the source, write 'not disclosed' rather than inferring."
)

PROFILE_SYSTEM = (
    "You are a senior credit analyst. Write exactly ONE paragraph (4-6 sentences) "
    "summarising the material facts about this bank. Include: type of institution, "
    "domicile and primary regulator, key business lines and geographies, approximate "
    "total assets, ownership structure (listed/mutual/state), and any credit ratings "
    "explicitly mentioned. Cite every fact [Source: p.XX]. Third person. "
    "No opinion or forward-looking statements."
)

HIGHLIGHTS_SYSTEM = (
    "You are a senior credit analyst. Write exactly ONE paragraph (4-6 sentences) "
    "summarising the key highlights from this bank's Annual Review. Focus on: "
    "the headline financial performance narrative management chose to emphasise, "
    "major strategic developments or acquisitions, significant regulatory actions "
    "or fines, CEO or senior leadership changes, and any material one-off items. "
    "Cite every fact [Source: p.XX]. Third person. Factual only."
)

MAX_INTRO_CHARS = 4000
MIN_INTRO_CHARS = 500


def get_intro_text(doc: dict, max_chars: int = MAX_INTRO_CHARS) -> str:
    """Extract intro text from processed JSON — first 15 pages."""
    pages = doc.get("pages", [])
    parts = []
    total = 0
    for page in pages[:15]:
        text = page.get("text", "").strip()
        if text:
            parts.append(f"[Page {page['page_num']}]\n{text}")
            total += len(text)
        if total >= max_chars:
            break
    combined = "\n\n".join(parts)
    return combined[:max_chars]


def get_intro_text_pdf(source_file: str, max_chars: int = MAX_INTRO_CHARS) -> str:
    """Extract intro text directly from PDF — richer than JSON for early pages."""
    if not FITZ_AVAILABLE:
        return ""
    for folder in [FINANCIALS_DIR, PILLAR3_DIR]:
        pdf_path = folder / source_file
        if pdf_path.exists():
            try:
                doc = fitz.open(str(pdf_path))
                parts = []
                for i, page in enumerate(doc):
                    if i >= 20:
                        break
                    text = page.get_text("text").strip()
                    if text:
                        parts.append(f"[Page {i+1}]\n{text}")
                doc.close()
                combined = "\n\n".join(parts)
                return combined[:max_chars]
            except Exception:
                pass
    return ""


def build_template_pair(doc: dict) -> dict | None:
    """Build a template pair (no API — placeholder response)."""
    meta      = doc.get("metadata", {})
    bank      = meta.get("bank_name", "")
    year      = meta.get("reporting_year", "")
    doc_type  = meta.get("document_type", "annual_report")
    source    = meta.get("source_file", "")

    if not bank or not year or doc_type != "annual_report":
        return None

    intro = get_intro_text(doc)
    if len(intro) < MIN_INTRO_CHARS:
        return None

    metrics = doc.get("key_metrics", {})
    metric_lines = []
    for k, v in metrics.items():
        val = v.get("value") if isinstance(v, dict) else v
        pg  = v.get("source_page", "?") if isinstance(v, dict) else "?"
        if val is not None:
            metric_lines.append(f"  {k.replace('_',' ').upper()}: {val} [p.{pg}]")

    user_profile = (
        f"Bank: {bank}\n"
        f"Year: {year}\n\n"
        f"TASK: Write the Institutional Profile paragraph (4-6 sentences, third person, "
        f"cited [Source: p.XX]).\n\n"
        f"ANNUAL REPORT EXTRACT:\n{intro[:MAX_INTRO_CHARS]}"
    )

    user_highlights = (
        f"Bank: {bank}\n"
        f"Year: {year}\n\n"
        f"TASK: Write the Annual Review Highlights paragraph (4-6 sentences, third person, "
        f"cited [Source: p.XX]).\n\n"
        + (f"KEY METRICS EXTRACTED:\n" + "\n".join(metric_lines) + "\n\n" if metric_lines else "")
        + f"ANNUAL REPORT EXTRACT:\n{intro[:MAX_INTRO_CHARS]}"
    )

    template_profile = (
        f"{bank} is a [institution type] domiciled in [domicile], regulated by "
        f"[regulator], with total assets of approximately [£/$/€Xbn] as of "
        f"31 December {year} [Source: p.X]. The Group's principal activities comprise "
        f"[business lines] with operations in [geographies] [Source: p.X]. "
        f"[Ownership structure]. [Credit ratings if disclosed]."
    )

    template_highlights = (
        f"In {year}, {bank} reported [headline metric] [Source: p.X], reflecting "
        f"[management narrative]. [Major strategic development]. "
        f"[Any significant regulatory action or material event]. "
        f"[CEO/leadership change if applicable]. "
        f"Management [characterised performance/outlook] as [quote/summary]."
    )

    # Build as a combined overview task
    user_combined = (
        f"Bank: {bank}\n"
        f"Year: {year}\n\n"
        f"TASK: Write the Overview section for the credit paper. Produce exactly two paragraphs:\n"
        f"  Para 1 — Institutional Profile (4-6 sentences): type, domicile, regulator, "
        f"business lines, total assets, ownership, credit ratings.\n"
        f"  Para 2 — {year} Annual Review Highlights (4-6 sentences): headline financial "
        f"performance, strategic developments, major events, CEO changes.\n\n"
        f"Third person. Every fact cited [Source: p.XX]. Never fabricate.\n\n"
        + (f"KEY METRICS:\n" + "\n".join(metric_lines) + "\n\n" if metric_lines else "")
        + f"ANNUAL REPORT EXTRACT:\n{intro[:MAX_INTRO_CHARS]}"
    )

    combined_response = (
        f"### Institutional Profile\n\n"
        f"{template_profile}\n\n"
        f"### {year} Annual Review — Key Highlights\n\n"
        f"{template_highlights}"
    )

    return {
        "messages": [
            {"role": "system",    "content": OVERVIEW_SYSTEM},
            {"role": "user",      "content": user_combined},
            {"role": "assistant", "content": combined_response},
        ],
        "_meta": {
            "bank": bank, "year": year,
            "source_file": source,
            "pipeline": "overview_template",
            "quality": "template",
        }
    }


def call_claude(prompt: str, system: str, api_key: str, max_tokens: int = 500) -> str | None:
    """Call Claude Haiku for a single overview paragraph."""
    payload = json.dumps({
        "model":      "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "system":     system,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=60) as r:
            data = json.loads(r.read().decode())
            return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"    API error: {e}")
        return None


def build_upgraded_pair(doc: dict, api_key: str) -> dict | None:
    """Build an overview pair with real analyst-quality prose via Claude API."""
    meta     = doc.get("metadata", {})
    bank     = meta.get("bank_name", "")
    year     = meta.get("reporting_year", "")
    doc_type = meta.get("document_type", "annual_report")
    source   = meta.get("source_file", "")

    if not bank or not year or doc_type != "annual_report":
        return None

    # Try to get richer intro text from source PDF
    intro = get_intro_text_pdf(source) or get_intro_text(doc)
    if len(intro) < MIN_INTRO_CHARS:
        return None

    metrics = doc.get("key_metrics", {})
    metric_lines = [
        f"  {k.replace('_',' ').upper()}: "
        f"{(v.get('value') if isinstance(v,dict) else v)} "
        f"[p.{(v.get('source_page','?') if isinstance(v,dict) else '?')}]"
        for k, v in metrics.items()
        if (v.get("value") if isinstance(v, dict) else v) is not None
    ]

    intro_trunc = intro[:MAX_INTRO_CHARS]
    metrics_str = ("KEY METRICS EXTRACTED:\n" + "\n".join(metric_lines) + "\n\n"
                   if metric_lines else "")

    # Para 1: institutional profile
    profile_prompt = (
        f"Bank: {bank}\nYear: {year}\n\n"
        f"TASK: Write exactly ONE paragraph (4-6 sentences) for the Institutional Profile "
        f"section of a credit paper. Include: institution type, domicile, primary regulator, "
        f"key business lines, approximate total assets, ownership/listing status, and any "
        f"credit ratings mentioned. Every fact cited [Source: p.XX].\n\n"
        f"{metrics_str}"
        f"ANNUAL REPORT EXTRACT:\n{intro_trunc}"
    )

    print(f"    Profile...", end=" ", flush=True)
    profile = call_claude(profile_prompt, PROFILE_SYSTEM, api_key, max_tokens=450)
    if not profile:
        return None
    print("✅")
    time.sleep(0.4)

    # Para 2: AR highlights
    highlights_prompt = (
        f"Bank: {bank}\nYear: {year}\n\n"
        f"TASK: Write exactly ONE paragraph (4-6 sentences) summarising the key highlights "
        f"from the {year} Annual Review. Include: headline financial performance, major "
        f"strategic developments, significant regulatory actions, CEO changes, material "
        f"one-off items. Every fact cited [Source: p.XX].\n\n"
        f"{metrics_str}"
        f"ANNUAL REPORT EXTRACT:\n{intro_trunc}"
    )

    print(f"    Highlights...", end=" ", flush=True)
    highlights = call_claude(highlights_prompt, PROFILE_SYSTEM, api_key, max_tokens=450)
    if not highlights:
        return None
    print("✅")
    time.sleep(0.4)

    combined_response = (
        f"### Institutional Profile\n\n{profile}\n\n"
        f"### {year} Annual Review — Key Highlights\n\n{highlights}"
    )

    # Combined user prompt (what the model will see at inference)
    user_combined = (
        f"Bank: {bank}\nYear: {year}\n\n"
        f"TASK: Write the Overview section for the credit paper. Two paragraphs:\n"
        f"  Para 1 — Institutional Profile (4-6 sentences)\n"
        f"  Para 2 — {year} Annual Review Highlights (4-6 sentences)\n"
        f"Third person. Every fact cited [Source: p.XX].\n\n"
        + metrics_str
        + f"ANNUAL REPORT EXTRACT:\n{intro_trunc}"
    )

    return {
        "messages": [
            {"role": "system",    "content": OVERVIEW_SYSTEM},
            {"role": "user",      "content": user_combined},
            {"role": "assistant", "content": combined_response},
        ],
        "_meta": {
            "bank": bank, "year": year,
            "source_file": source,
            "pipeline": "overview_upgraded",
            "quality": "upgraded",
        }
    }


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--template", action="store_true",
                      help="Build template pairs (no API, instant)")
    mode.add_argument("--upgrade",  action="store_true",
                      help="Build analyst-quality pairs via Claude API")
    parser.add_argument("--resume", action="store_true",
                        help="Skip banks already in output file")
    parser.add_argument("--limit",  type=int, default=None,
                        help="Process at most N files (for testing)")
    args = parser.parse_args()

    api_key = None
    if args.upgrade:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not set.")
            print("Run: export ANTHROPIC_API_KEY=sk-ant-...")
            return

    out_path = (TRAINING_DIR / "overview_pairs_upgraded.jsonl"
                if args.upgrade else TRAINING_DIR / "overview_pairs.jsonl")

    # Load existing for resume
    done = set()
    if args.resume and out_path.exists():
        with open(out_path) as f:
            for line in f:
                try:
                    p = json.loads(line)
                    meta = p.get("_meta", {})
                    done.add(f"{meta.get('bank','')}_{meta.get('year','')}")
                except Exception:
                    pass
        print(f"Resuming — {len(done)} pairs already done")

    json_files = sorted(PROCESSED_DIR.glob("*.json"))
    if args.limit:
        json_files = json_files[:args.limit]

    print(f"\nOverview Pair Builder — {'API upgrade' if args.upgrade else 'template'} mode")
    print(f"Source files : {len(json_files)}")
    print(f"Output       : {out_path}\n")

    built = skipped = errors = 0

    with open(out_path, "a" if args.resume else "w", encoding="utf-8") as out_f:
        for json_path in json_files:
            try:
                with open(json_path, encoding="utf-8") as f:
                    doc = json.load(f)

                meta  = doc.get("metadata", {})
                bank  = meta.get("bank_name", "")
                year  = meta.get("reporting_year", "")
                dkey  = f"{bank}_{year}"

                if meta.get("document_type") != "annual_report":
                    skipped += 1
                    continue
                if args.resume and dkey in done:
                    skip_msg = f"  SKIP (done): {bank} {year}"
                    print(skip_msg)
                    skipped += 1
                    continue

                print(f"  {bank} {year} ({json_path.name})")

                if args.upgrade:
                    pair = build_upgraded_pair(doc, api_key)
                else:
                    pair = build_template_pair(doc)

                if pair:
                    out_f.write(json.dumps(
                        {k: v for k, v in pair.items() if not k.startswith("_")},
                        ensure_ascii=False) + "\n")
                    out_f.flush()
                    built += 1
                else:
                    skipped += 1

            except KeyboardInterrupt:
                print(f"\nInterrupted — {built} pairs written. Resume with --resume")
                break
            except Exception as e:
                print(f"    ERROR: {e}")
                errors += 1

    print(f"\n{'='*60}")
    print(f" Overview pairs built  : {built}")
    print(f" Skipped               : {skipped}")
    print(f" Errors                : {errors}")
    print(f" Output                : {out_path}")

    if args.upgrade and built > 0:
        print(f"\n Next: add to training run:")
        print(f"   load(TRAINING_DIR / 'overview_pairs_upgraded.jsonl')")
        print(f"   in 04_build_training_pairs.py Pipeline F")
    elif args.template and built > 0:
        print(f"\n Tip: upgrade with --upgrade for analyst-quality prose (~$3)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
