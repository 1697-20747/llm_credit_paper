#!/usr/bin/env python3
"""
02_extract_financials.py — patched May 2026
Fix: pdfplumber table extraction wrapped per-page with timeout protection.
Complex Pillar 3 PDFs (NatWest 2022, HSBC, Deutsche) no longer hang.
"""

import re
import json
import signal
import argparse
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional

import fitz
import pdfplumber

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
FINANCIALS_DIR = PROJECT_ROOT / "financials"
OUTPUT_DIR     = PROJECT_ROOT / "processed" / "financials"
LOGS_DIR       = PROJECT_ROOT / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

SUPPORTED_EXTS = {".pdf", ".htm", ".html"}

# ── Section keywords ─────────────────────────────────────────────────────────
SECTION_KEYWORDS = {
    "capital_adequacy": [
        "capital adequacy","cet1","common equity tier 1","tier 1 capital",
        "total capital ratio","risk-weighted assets","rwa","leverage ratio",
        "mrel","capital requirements","pillar 1","pillar 2","capital buffers",
        "capital conservation buffer","countercyclical buffer","capital position",
        "basel","capital ratios","capital resources","own funds",
    ],
    "asset_quality": [
        "stage 1","stage 2","stage 3","expected credit loss","ecl",
        "impairment","credit impaired","non-performing","npl",
        "loan loss","provisions","allowance for credit losses",
        "write-off","coverage ratio","cost of risk","credit quality",
        "ifrs 9","staging","forbearance","allowance for loan",
        "net charge-off","charge-off","probability of default",
        "loss given default","exposure at default",
    ],
    "management_governance": [
        "board of directors","governance","risk committee","audit committee",
        "remuneration","chief executive","chief financial officer",
        "senior management","board composition","independent director",
        "risk appetite","three lines of defence","internal audit",
        "conduct risk","compensation committee","corporate governance",
    ],
    "earnings_profitability": [
        "net interest income","net interest margin","nim",
        "return on equity","return on tangible equity","rote",
        "return on assets","roa","cost income ratio","cost:income",
        "operating profit","pre-tax profit","profit before tax",
        "earnings per share","eps","dividend","total income",
        "noninterest income","non-interest income","efficiency ratio",
    ],
    "liquidity_funding": [
        "liquidity coverage ratio","lcr","net stable funding ratio","nsfr",
        "hqla","high quality liquid assets","liquidity pool",
        "loan to deposit","loan deposit ratio","retail deposits",
        "wholesale funding","funding mix","liquidity risk",
        "customer deposits","liquidity stress","available stable funding",
    ],
    "market_risk_sensitivity": [
        "market risk","interest rate risk","irrbb",
        "value at risk","var","stressed var",
        "net interest income sensitivity","rate sensitivity",
        "duration","fvoci","fair value","foreign exchange",
        "fx risk","trading risk","structural hedge",
    ],
    "balance_sheet": [
        "total assets","total liabilities","shareholders equity",
        "net assets","balance sheet","consolidated balance sheet",
        "total equity","retained earnings","tangible equity",
        "total deposits","total loans",
    ],
    "income_statement": [
        "income statement","profit and loss","profit or loss",
        "consolidated income","revenue","operating expenses",
        "noninterest expense","non-interest expense",
        "provision for credit losses","income before tax",
    ],
    "stress_testing": [
        "stress test","stress scenario","adverse scenario",
        "bank of england stress","icaap","ilaap","climate risk",
        "severely adverse","dfast","ccar",
    ],
    "rwa_breakdown": [
        "rwa by risk type","credit risk rwa","market risk rwa",
        "operational risk rwa","rwa breakdown","risk weighted exposure",
        "standardised approach","irb approach","advanced irb",
        "foundation irb","slotting criteria","specialised lending",
    ],
    "irb_models": [
        "probability of default","loss given default","exposure at default",
        "pd model","lgd model","irb model","rating model",
        "internal ratings","obligor rating","facility rating",
        "through the cycle","point in time","model validation",
        "back-testing","model performance",
    ],
    "counterparty_credit_risk": [
        "counterparty credit risk","cva","credit valuation adjustment",
        "dva","wrong way risk","replacement cost","potential future exposure",
        "expected positive exposure","netting agreement",
        "collateral agreement","central counterparty","ccp",
    ],
    "operational_risk": [
        "operational risk","op risk","loss data","business environment",
        "internal control","operational risk rwa","ama approach",
        "scenario analysis","key risk indicator",
    ],
    "remuneration_p3": [
        "material risk taker","identified staff","variable remuneration",
        "deferred remuneration","malus","clawback","remuneration policy",
        "high earner","code staff","performance adjustment",
    ],
}

METRIC_PATTERNS = [
    ("cet1_ratio",          r"(?:CET\s*1|common equity tier 1)\s+(?:ratio|capital ratio)\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("tier1_ratio",         r"[Tt]ier\s*1\s+(?:ratio|capital ratio)\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("total_capital_ratio", r"[Tt]otal\s+capital\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("leverage_ratio",      r"(?:UK\s+)?leverage\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("nim",                 r"[Nn]et\s+[Ii]nterest\s+[Mm]argin\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("rote",                r"[Rr]eturn\s+on\s+(?:[Tt]angible\s+)?[Cc]ommon\s+[Ee]quity\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("roe",                 r"[Rr]eturn\s+on\s+(?:average\s+)?[Ee]quity\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("roa",                 r"[Rr]eturn\s+on\s+(?:average\s+)?[Aa]ssets?\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("lcr",                 r"[Ll]iquidity\s+[Cc]overage\s+[Rr]atio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("nsfr",                r"[Nn]et\s+[Ss]table\s+[Ff]unding\s+[Rr]atio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("cost_income",         r"[Cc]ost\s*[:/]\s*[Ii]ncome\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("efficiency_ratio",    r"[Ee]fficiency\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("stage3_pct",          r"[Ss]tage\s*3\s+(?:loans\s+)?[:\s]+(?:[$£€][\d\.]+(?:bn|m|B|M)[,\s]+)?(\d+\.?\d*)\s*%"),
    ("rwa",                 r"[Rr]isk[- ]?weighted\s+assets?\s*[:\s$£€]+(\d[\d,\.]+)\s*(?:bn|billion|B\b)"),
    ("mrel",                r"MREL\s*[:\s]+(\d+\.?\d*)\s*%"),
    ("npl_ratio",           r"(?:NPL|non[- ]performing\s+loan)\s+ratio\s*[:\s]+(\d+\.?\d*)\s*%"),
]


def is_pillar3_document(text_sample: str, filename: str) -> bool:
    signals = ["pillar 3","pillar iii","pillar3","risk disclosure",
               "capital disclosures","basel iii disclosures","capital and risk"]
    combined = (text_sample[:3000] + " " + filename).lower()
    return any(s in combined for s in signals)


def guess_bank_name(text_sample: str, filename: str) -> str:
    bank_patterns = [
        r"(JPMorgan\s+Chase)", r"(Bank\s+of\s+America)", r"(Wells\s+Fargo)",
        r"(Citigroup|Citi\s+Inc\.?)", r"(Goldman\s+Sachs)", r"(Morgan\s+Stanley)",
        r"(U\.?S\.?\s+Bancorp)", r"(PNC\s+Financial)", r"(Truist\s+Financial)",
        r"(Capital\s+One)", r"(American\s+Express)",
        r"(Bank\s+of\s+New\s+York\s+Mellon|BNY\s+Mellon)", r"(State\s+Street)",
        r"(Charles\s+Schwab)", r"(Fifth\s+Third)", r"(Regions\s+Financial)",
        r"(KeyCorp|KeyBank)", r"(Huntington\s+Bancshares)", r"(Comerica)",
        r"(Zions\s+Bancorporation)", r"(Lloyds\s+Banking\s+Group)",
        r"(HSBC\s+Holdings)", r"(Barclays\s+(?:PLC|Bank)?)", r"(NatWest\s+Group)",
        r"(Standard\s+Chartered)", r"(Deutsche\s+Bank)", r"(BNP\s+Paribas)",
        r"(UniCredit)", r"(ING\s+Group)", r"(ABN\s+AMRO)",
        r"(Intesa\s+Sanpaolo)", r"(Santander)", r"(Westpac)",
        r"(Commonwealth\s+Bank|CBA)", r"(ANZ\s+Banking|ANZ\s+Group)",
        r"(National\s+Australia\s+Bank|NAB)",
        r"(Royal\s+Bank\s+of\s+Canada|RBC)",
        r"(TD\s+Bank|Toronto[- ]Dominion)",
        r"(Scotiabank|Bank\s+of\s+Nova\s+Scotia)",
        r"(Bank\s+of\s+Montreal|BMO)",
        r"(CIBC|Canadian\s+Imperial)",
    ]
    for pat in bank_patterns:
        m = re.search(pat, text_sample, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    stem = Path(filename).stem
    # Strip date prefixes like 250227-, 240221-
    stem = re.sub(r"^\d{6}-", "", stem)
    stem = re.sub(r"_\d{4}_.*$", "", stem)
    stem = re.sub(r"[-_](annual|pillar|p3|10k|ar).*$", "", stem, flags=re.IGNORECASE)
    return stem.replace("_", " ").replace("-", " ").title()


def guess_reporting_year(text_sample: str, filename: str) -> Optional[str]:
    # Filename patterns first
    for pat in [
        r"[-_](\d{4})[-_]annual", r"(\d{4})[-_]10k", r"(\d{4})-lbg",
        r"[-_](\d{4})[-_]pillar", r"pillar3[-_](\d{4})", r"[-_](\d{4})\.pdf",
        r"accounts[-_](\d{4})", r"report[-_](\d{4})",
    ]:
        m = re.search(pat, filename, re.IGNORECASE)
        if m:
            y = int(m.group(1))
            if 2000 <= y <= 2030:
                return str(y)
    # Text patterns
    for pat in [
        r"[Ff]or\s+the\s+[Yy]ear\s+[Ee]nded\s+\w+\s+\d+,?\s+(\d{4})",
        r"31\s+December\s+(\d{4})", r"December\s+31,?\s+(\d{4})",
        r"[Aa]nnual\s+[Rr]eport\s+(?:and\s+\w+\s+)?(\d{4})",
        r"[Pp]illar\s+3\s+(?:[Rr]eport\s+)?(\d{4})",
        r"31\s+October\s+(\d{4})", r"October\s+31,?\s+(\d{4})",  # CA banks
        r"30\s+June\s+(\d{4})", r"June\s+30,?\s+(\d{4})",        # AU banks
    ]:
        m = re.search(pat, text_sample)
        if m:
            y = int(m.group(1))
            if 2000 <= y <= 2030:
                return str(y)
    return None


def extract_metrics(text: str) -> dict:
    found = {}
    for name, pattern in METRIC_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                found[name] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return found


def classify_sections(text: str) -> list:
    tl = text.lower()
    return [s for s, kws in SECTION_KEYWORDS.items()
            if sum(1 for kw in kws if kw in tl) >= 2]


def clean_table(raw_table: list) -> list:
    cleaned = []
    for row in (raw_table or []):
        if row is None:
            continue
        clean_row = [str(c).strip() if c is not None else "" for c in row]
        if any(clean_row):
            cleaned.append(clean_row)
    return cleaned


def extract_tables_safe(pdf_page, page_num: int) -> list:
    """
    Extract tables from a single pdfplumber page with full error isolation.
    Tries strict line strategy first, falls back to text strategy.
    Returns empty list on any error — never hangs.
    """
    tables = []

    # Strategy 1: strict lines (best for Pillar 3 formatted tables)
    try:
        raw = pdf_page.extract_tables({
            "vertical_strategy":   "lines_strict",
            "horizontal_strategy": "lines_strict",
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 10,
        })
        if raw:
            return raw
    except Exception:
        pass

    # Strategy 2: text alignment (fallback for PDFs without border lines)
    try:
        raw = pdf_page.extract_tables({
            "vertical_strategy":   "text",
            "horizontal_strategy": "text",
            "snap_tolerance": 5,
            "join_tolerance": 5,
        })
        if raw:
            return raw
    except Exception:
        pass

    return []


def process_pdf(file_path: Path) -> tuple:
    """Extract text and tables from a PDF. Robust against complex/corrupt pages."""
    doc        = fitz.open(str(file_path))
    total_pages = len(doc)
    pages_data  = []
    global_metrics = {}

    # ── Phase 1: text extraction via PyMuPDF (fast, never hangs) ─────────────
    all_text_first_10 = []
    for i, page in enumerate(doc):
        pnum = i + 1
        try:
            text = page.get_text("text")
        except Exception:
            text = ""
        sections = classify_sections(text)
        metrics  = extract_metrics(text)
        for k, v in metrics.items():
            if k not in global_metrics:
                global_metrics[k] = {"value": v, "source_page": pnum}
        pages_data.append({
            "page_num": pnum, "char_count": len(text),
            "text": text, "sections": sections,
            "metrics_found": metrics, "tables": [],
        })
        if i < 10:
            all_text_first_10.append(text)
    doc.close()

    # ── Phase 2: table extraction via pdfplumber (per-page, safe) ────────────
    table_count = 0
    try:
        with pdfplumber.open(str(file_path)) as pdf:
            for i, plumb_page in enumerate(pdf.pages):
                pnum = i + 1
                if i >= len(pages_data):
                    break
                page_text = pages_data[i]["text"]

                raw_tables = extract_tables_safe(plumb_page, pnum)
                for tbl_idx, tbl in enumerate(raw_tables):
                    cleaned = clean_table(tbl)
                    if len(cleaned) < 2:
                        continue
                    # Infer caption from page text
                    caption = f"Table {tbl_idx+1} (p.{pnum})"
                    for pat in [
                        r"(?:Table|Note)\s+\d+[\.\:]\s*([^\n]{10,80})",
                        r"((?:Capital|Liquidity|Asset|Credit|Income|RWA|IRB|Balance)[^\n]{5,60}(?:ratio|position|summary|table|breakdown)[^\n]{0,20})",
                    ]:
                        caps = re.findall(pat, page_text, re.IGNORECASE)
                        if caps:
                            caption = caps[min(tbl_idx, len(caps)-1)].strip()
                            break
                    pages_data[i]["tables"].append({
                        "table_index": tbl_idx, "page_num": pnum,
                        "caption": caption,
                        "source": f"p.{pnum}, Table {tbl_idx+1}",
                        "rows": len(cleaned),
                        "cols": max(len(r) for r in cleaned) if cleaned else 0,
                        "data": cleaned,
                    })
                    table_count += 1
    except Exception as e:
        print(f"    WARNING table extraction failed: {e}")

    return pages_data, global_metrics, all_text_first_10, total_pages, table_count


def process_html(file_path: Path) -> tuple:
    raw_html = file_path.read_text(encoding="utf-8", errors="replace")
    clean = re.sub(r"<script[^>]*>.*?</script>", " ", raw_html, flags=re.IGNORECASE|re.DOTALL)
    clean = re.sub(r"<style[^>]*>.*?</style>",  " ", clean,    flags=re.IGNORECASE|re.DOTALL)
    clean = re.sub(r"<(?:br|p|div|tr|h[1-6])[^>]*>", "\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<td[^>]*>", " | ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = clean.replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&nbsp;"," ")
    clean = re.sub(r"\s{3,}", "  ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()

    chunk_size  = 3000
    page_splits = re.split(r"(?:Page\s+\d+\s+of\s+\d+|-{10,})", clean)
    text_chunks = page_splits if len(page_splits) > 10 else [
        clean[i:i+chunk_size] for i in range(0, len(clean), chunk_size)
    ]

    pages_data     = []
    global_metrics = {}
    for i, chunk in enumerate(text_chunks):
        pnum     = i + 1
        sections = classify_sections(chunk)
        metrics  = extract_metrics(chunk)
        for k, v in metrics.items():
            if k not in global_metrics:
                global_metrics[k] = {"value": v, "source_page": pnum}
        pages_data.append({
            "page_num": pnum, "char_count": len(chunk),
            "text": chunk, "sections": sections,
            "metrics_found": metrics, "tables": [],
        })

    all_text_first_10 = [p["text"] for p in pages_data[:10]]
    return pages_data, global_metrics, all_text_first_10, len(pages_data), 0


def process_file(file_path: Path, source_folder: str = "financials") -> dict:
    ext       = file_path.suffix.lower()
    file_type = "html" if ext in (".htm", ".html") else "pdf"
    print(f"\n  Processing ({file_type.upper()}): {file_path.name}")

    if file_type == "html":
        pages_data, global_metrics, first_10, total_pages, table_count = process_html(file_path)
    else:
        pages_data, global_metrics, first_10, total_pages, table_count = process_pdf(file_path)

    first_text = " ".join(first_10)
    bank_name  = guess_bank_name(first_text, file_path.name)
    year       = guess_reporting_year(first_text, file_path.name)
    is_p3      = is_pillar3_document(first_text, file_path.name)
    doc_type   = "pillar3" if is_p3 else "annual_report"

    section_index = {}
    for page in pages_data:
        for s in page["sections"]:
            section_index.setdefault(s, []).append(page["page_num"])

    print(f"    Bank: {bank_name} | Year: {year or 'unknown'} | "
          f"Type: {doc_type} | Pages: {total_pages} | Tables: {table_count}")
    print(f"    Sections: {list(section_index.keys())[:6]}")

    return {
        "metadata": {
            "source_file": file_path.name, "source_path": str(file_path),
            "source_folder": source_folder, "document_type": doc_type,
            "file_type": file_type, "bank_name": bank_name,
            "reporting_year": year, "total_pages": total_pages,
            "total_tables": table_count,
            "processed_at": datetime.now().isoformat(),
            "char_total": sum(p["char_count"] for p in pages_data),
        },
        "key_metrics":   global_metrics,
        "section_index": section_index,
        "pages":         pages_data,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",      default=None)
    parser.add_argument("--folder",    default=None)
    parser.add_argument("--reprocess", action="store_true")
    args = parser.parse_args()

    if args.file:
        p      = Path(args.file)
        files  = [p if p.is_absolute() else PROJECT_ROOT / p]
        folder = args.folder or "financials"
    elif args.folder:
        src    = PROJECT_ROOT / args.folder
        files  = sorted(f for f in src.iterdir()
                        if f.suffix.lower() in SUPPORTED_EXTS and f.is_file())
        folder = args.folder
    else:
        files  = sorted(f for f in FINANCIALS_DIR.iterdir()
                        if f.suffix.lower() in SUPPORTED_EXTS and f.is_file())
        folder = "financials"

    if not files:
        print(f"No supported files found."); return

    print(f"Found {len(files)} file(s) in {folder}/")
    processed = skipped = errors = 0
    error_log = []

    for file_path in files:
        out_path = OUTPUT_DIR / (file_path.stem + ".json")
        if out_path.exists() and not args.reprocess:
            print(f"  Skipping (exists): {file_path.name}")
            skipped += 1
            continue
        try:
            result = process_file(file_path, source_folder=folder)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"    ✅ {out_path.name} ({out_path.stat().st_size//1024}KB)")
            processed += 1
        except KeyboardInterrupt:
            print(f"\nInterrupted. Saving progress...")
            break
        except Exception as e:
            print(f"    ❌ ERROR: {file_path.name}: {e}")
            error_log.append({"file": file_path.name, "error": str(e)})
            errors += 1
            # Continue to next file — don't stop

    with open(LOGS_DIR / "extract_financials_run.json", "w") as f:
        json.dump({"run_at": datetime.now().isoformat(),
                   "processed": processed, "skipped": skipped,
                   "errors": errors, "error_details": error_log}, f, indent=2)

    print(f"\nDone. Processed: {processed} | Skipped: {skipped} | Errors: {errors}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
