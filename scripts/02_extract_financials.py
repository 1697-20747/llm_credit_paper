#!/usr/bin/env python3
"""
02_extract_financials.py
========================
Extracts structured text and tables from:
  - Bank annual reports (PDF, HTM) from financials/
  - Pillar 3 risk disclosure reports (PDF) from pillar3/

Pillar 3 reports contain significantly more granular risk data:
  - Detailed RWA by risk type (credit, market, operational)
  - IRB model outputs (PD, LGD, EAD by portfolio segment)
  - Detailed LCR/NSFR composition and HQLA quality
  - CVA and counterparty credit risk
  - Remuneration (material risk takers)
  - Capital instruments detail

Run:
    python scripts/02_extract_financials.py                    # financials/
    python scripts/02_extract_financials.py --folder pillar3   # pillar3/
    python scripts/02_extract_financials.py --file financials/lloyds.pdf
    python scripts/02_extract_financials.py --reprocess
"""

import re
import json
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

# ── Standard annual report sections ──────────────────────────────────────────
SECTION_KEYWORDS = {
    "capital_adequacy": [
        "capital adequacy", "cet1", "common equity tier 1", "tier 1 capital",
        "total capital ratio", "risk-weighted assets", "rwa", "leverage ratio",
        "mrel", "capital requirements", "pillar 1", "pillar 2", "capital buffers",
        "capital conservation buffer", "countercyclical buffer", "capital position",
        "basel", "capital ratios", "capital resources", "own funds",
    ],
    "asset_quality": [
        "stage 1", "stage 2", "stage 3", "expected credit loss", "ecl",
        "impairment", "credit impaired", "non-performing", "npl",
        "loan loss", "provisions", "allowance for credit losses",
        "write-off", "coverage ratio", "cost of risk", "credit quality",
        "ifrs 9", "staging", "forbearance", "allowance for loan",
        "net charge-off", "charge-off", "probability of default",
        "loss given default", "exposure at default", "pd ", "lgd ", "ead ",
    ],
    "management_governance": [
        "board of directors", "governance", "risk committee", "audit committee",
        "remuneration", "chief executive", "chief financial officer",
        "senior management", "board composition", "independent director",
        "risk appetite", "three lines of defence", "internal audit",
        "external auditor", "regulatory compliance", "conduct risk",
        "compensation committee", "corporate governance", "material risk taker",
    ],
    "earnings_profitability": [
        "net interest income", "net interest margin", "nim",
        "return on equity", "return on tangible equity", "rote",
        "return on assets", "roa", "cost income ratio", "cost:income",
        "operating profit", "pre-tax profit", "profit before tax",
        "earnings per share", "eps", "dividend", "total income",
        "noninterest income", "non-interest income", "efficiency ratio",
        "return on average", "net revenue",
    ],
    "liquidity_funding": [
        "liquidity coverage ratio", "lcr", "net stable funding ratio", "nsfr",
        "hqla", "high quality liquid assets", "liquidity pool",
        "loan to deposit", "loan deposit ratio", "retail deposits",
        "wholesale funding", "funding mix", "liquidity risk",
        "tfsme", "term funding", "covered bond", "customer deposits",
        "liquidity stress", "available stable funding", "funding plan",
    ],
    "market_risk_sensitivity": [
        "market risk", "interest rate risk", "irrbb",
        "value at risk", "var", "stressed var",
        "net interest income sensitivity", "rate sensitivity",
        "duration", "fvoci", "fair value", "foreign exchange",
        "fx risk", "pension", "trading risk", "structural hedge",
        "interest rate sensitive", "rate risk",
    ],
    "balance_sheet": [
        "total assets", "total liabilities", "shareholders equity",
        "net assets", "balance sheet", "consolidated balance sheet",
        "total equity", "retained earnings", "tangible equity",
        "total deposits", "total loans",
    ],
    "income_statement": [
        "income statement", "profit and loss", "profit or loss",
        "consolidated income", "revenue", "operating expenses",
        "noninterest expense", "non-interest expense",
        "provision for credit losses", "income before tax",
    ],
    "stress_testing": [
        "stress test", "stress scenario", "adverse scenario",
        "bank of england stress", "icaap", "ilaap", "climate risk",
        "severely adverse", "dfast", "ccar", "internal capital adequacy",
    ],
    # ── Pillar 3 specific sections ────────────────────────────────────────────
    "rwa_breakdown": [
        "rwa by risk type", "credit risk rwa", "market risk rwa",
        "operational risk rwa", "rwa breakdown", "risk weighted exposure",
        "standardised approach", "irb approach", "advanced irb",
        "foundation irb", "slotting criteria", "specialised lending",
        "equity exposures", "securitisation rwa",
    ],
    "irb_models": [
        "probability of default", "loss given default", "exposure at default",
        "pd model", "lgd model", "irb model", "rating model",
        "internal ratings", "obligor rating", "facility rating",
        "through the cycle", "point in time", "model validation",
        "back-testing", "model performance", "gini coefficient",
    ],
    "counterparty_credit_risk": [
        "counterparty credit risk", "cva", "credit valuation adjustment",
        "dva", "wrong way risk", "replacement cost", "potential future exposure",
        "expected positive exposure", "eepe", "netting agreement",
        "collateral agreement", "central counterparty", "ccp",
    ],
    "operational_risk": [
        "operational risk", "op risk", "loss data", "business environment",
        "internal control", "operational risk rwa", "ama approach",
        "standardised approach operational", "basic indicator approach",
        "scenario analysis", "key risk indicator",
    ],
    "remuneration_p3": [
        "material risk taker", "identified staff", "variable remuneration",
        "deferred remuneration", "malus", "clawback", "remuneration policy",
        "high earner", "code staff", "performance adjustment",
    ],
}

# Pillar 3 enhanced metric patterns
PILLAR3_METRIC_PATTERNS = [
    ("irb_pd_corporate",    r"[Cc]orporate\s+(?:average\s+)?PD[:\s]+(\d+\.?\d*)\s*%"),
    ("irb_lgd_mortgage",    r"[Mm]ortgage\s+(?:average\s+)?LGD[:\s]+(\d+\.?\d*)\s*%"),
    ("cva_charge",          r"CVA\s+(?:charge|RWA)[:\s£$€]+(\d[\d,\.]+)\s*(?:m|bn|M|B)?"),
    ("op_risk_rwa",         r"[Oo]perational\s+risk\s+RWA[:\s£$€]+(\d[\d,\.]+)\s*(?:bn|billion)?"),
    ("credit_risk_rwa_pct", r"[Cc]redit\s+risk\s+(?:as\s+%\s+of\s+)?RWA[:\s]+(\d+\.?\d*)\s*%"),
    ("hqla_l1_pct",         r"[Ll]evel\s+1\s+(?:assets?|HQLA)[:\s]+(\d+\.?\d*)\s*%"),
    ("nsfr_asf",            r"[Aa]vailable\s+[Ss]table\s+[Ff]unding[:\s£$€]+(\d[\d,\.]+)\s*(?:bn)?"),
    ("nsfr_rsf",            r"[Rr]equired\s+[Ss]table\s+[Ff]unding[:\s£$€]+(\d[\d,\.]+)\s*(?:bn)?"),
]

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
] + PILLAR3_METRIC_PATTERNS


def is_pillar3_document(text_sample: str, filename: str) -> bool:
    """Detect if a document is a Pillar 3 report."""
    signals = [
        "pillar 3", "pillar iii", "pillar3",
        "risk disclosure", "capital disclosures",
        "basel iii disclosures", "capital and risk",
    ]
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
        r"(Commonwealth\s+Bank)", r"(ANZ\s+Banking)", r"(Westpac)",
        r"(National\s+Australia\s+Bank|NAB)",
    ]
    for pat in bank_patterns:
        m = re.search(pat, text_sample, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    stem = Path(filename).stem
    stem = re.sub(r"_\d{4}_.*$", "", stem)
    stem = re.sub(r"[-_](annual|pillar|p3).*$", "", stem, flags=re.IGNORECASE)
    return stem.replace("_", " ").replace("-", " ").title()


def guess_reporting_year(text_sample: str, filename: str) -> Optional[str]:
    for pat in [r"(\d{4})_10k", r"(\d{4})[_-]annual",
                r"(\d{4})-lbg", r"(\d{4})[_-]pillar"]:
        m = re.search(pat, filename, re.IGNORECASE)
        if m:
            return m.group(1)
    for pat in [
        r"[Ff]or\s+the\s+[Yy]ear\s+[Ee]nded\s+\w+\s+\d+,?\s+(\d{4})",
        r"31\s+December\s+(\d{4})", r"December\s+31,?\s+(\d{4})",
        r"[Aa]nnual\s+[Rr]eport\s+(?:and\s+\w+\s+)?(\d{4})",
        r"[Pp]illar\s+3\s+(?:[Rr]eport\s+)?(\d{4})",
    ]:
        m = re.search(pat, text_sample)
        if m:
            year = int(m.group(1))
            if 2000 <= year <= 2030:
                return str(year)
    return None


def extract_metrics_from_text(text: str) -> dict:
    found = {}
    for metric_name, pattern in METRIC_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                found[metric_name] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return found


def classify_page_sections(text: str) -> list:
    text_lower = text.lower()
    return [
        section for section, keywords in SECTION_KEYWORDS.items()
        if sum(1 for kw in keywords if kw in text_lower) >= 2
    ]


def clean_table(raw_table: list) -> list:
    cleaned = []
    for row in (raw_table or []):
        if row is None:
            continue
        clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
        if any(cell for cell in clean_row):
            cleaned.append(clean_row)
    return cleaned


def infer_table_caption(page_text: str, table_index: int, page_num: int) -> str:
    patterns = [
        r"(?:Table|Note|Exhibit)\s+\d+[\.\:]\s*([^\n]{10,80})",
        r"((?:Consolidated|Group|Summary)\s+[^\n]{10,60}(?:Sheet|Statement|Income|Capital|Risk|Funding)[^\n]{0,30})",
        r"((?:Capital|Liquidity|Asset|Credit|Income|Balance|RWA|IRB)[^\n]{5,60}(?:ratios?|position|summary|table|breakdown)[^\n]{0,20})",
    ]
    for pat in patterns:
        matches = re.findall(pat, page_text, re.IGNORECASE)
        if matches:
            return matches[min(table_index, len(matches) - 1)].strip()
    return f"Table {table_index + 1} (p.{page_num})"


def process_pdf(file_path: Path) -> tuple:
    doc_fitz    = fitz.open(str(file_path))
    total_pages = len(doc_fitz)
    pages_data  = []
    global_metrics    = {}
    all_text_first_10 = []

    for page_num in range(total_pages):
        page   = doc_fitz[page_num]
        text   = page.get_text("text")
        pnum_1 = page_num + 1

        sections = classify_page_sections(text)
        metrics  = extract_metrics_from_text(text)

        for k, v in metrics.items():
            if k not in global_metrics:
                global_metrics[k] = {"value": v, "source_page": pnum_1}

        pages_data.append({
            "page_num": pnum_1, "char_count": len(text),
            "text": text, "sections": sections,
            "metrics_found": metrics, "tables": [],
        })
        if page_num < 10:
            all_text_first_10.append(text)

    doc_fitz.close()

    table_count = 0
    try:
        with pdfplumber.open(str(file_path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                pnum_1 = page_num + 1
                try:
                    tables = page.extract_tables({
                        "vertical_strategy": "lines_strict",
                        "horizontal_strategy": "lines_strict",
                        "snap_tolerance": 3, "join_tolerance": 3,
                        "edge_min_length": 10,
                    }) or page.extract_tables({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "snap_tolerance": 5, "join_tolerance": 5,
                    })
                except Exception:
                    tables = []

                page_text = pages_data[page_num]["text"] if page_num < len(pages_data) else ""
                for tbl_idx, tbl in enumerate(tables or []):
                    cleaned = clean_table(tbl)
                    if len(cleaned) < 2:
                        continue
                    pages_data[page_num]["tables"].append({
                        "table_index": tbl_idx, "page_num": pnum_1,
                        "caption": infer_table_caption(page_text, tbl_idx, pnum_1),
                        "source": f"p.{pnum_1}, Table {tbl_idx + 1}",
                        "rows": len(cleaned),
                        "cols": max(len(r) for r in cleaned) if cleaned else 0,
                        "data": cleaned,
                    })
                    table_count += 1
    except Exception as e:
        print(f"    WARNING table extraction: {e}")

    return pages_data, global_metrics, all_text_first_10, total_pages, table_count


def process_html(file_path: Path) -> tuple:
    raw_html = file_path.read_text(encoding="utf-8", errors="replace")
    clean = re.sub(r"<script[^>]*>.*?</script>", " ", raw_html, flags=re.IGNORECASE|re.DOTALL)
    clean = re.sub(r"<style[^>]*>.*?</style>", " ", clean, flags=re.IGNORECASE|re.DOTALL)
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

    html_tables   = []
    table_pattern = re.compile(r"<table[^>]*>(.*?)</table>", re.IGNORECASE|re.DOTALL)
    row_pattern   = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE|re.DOTALL)
    cell_pattern  = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE|re.DOTALL)

    for tbl_match in table_pattern.finditer(raw_html):
        rows = []
        for row_match in row_pattern.finditer(tbl_match.group(1)):
            cells = [re.sub(r"<[^>]+>", " ", c.group(1)).strip()
                     for c in cell_pattern.finditer(row_match.group(1))]
            if any(cells):
                rows.append(cells)
        if len(rows) >= 2 and len(rows[0]) >= 2:
            html_tables.append(rows)

    pages_data = []
    global_metrics = {}

    for i, chunk in enumerate(text_chunks):
        pnum_1   = i + 1
        sections = classify_page_sections(chunk)
        metrics  = extract_metrics_from_text(chunk)
        for k, v in metrics.items():
            if k not in global_metrics:
                global_metrics[k] = {"value": v, "source_page": pnum_1}
        pages_data.append({
            "page_num": pnum_1, "char_count": len(chunk),
            "text": chunk, "sections": sections,
            "metrics_found": metrics, "tables": [],
        })

    all_text_first_10 = [p["text"] for p in pages_data[:10]]
    return pages_data, global_metrics, all_text_first_10, len(pages_data), 0


def build_section_index(pages_data: list) -> dict:
    section_index = {}
    for page in pages_data:
        for section in page["sections"]:
            section_index.setdefault(section, []).append(page["page_num"])
    return section_index


def process_file(file_path: Path, source_folder: str = "financials") -> dict:
    ext       = file_path.suffix.lower()
    file_type = "html" if ext in (".htm", ".html") else "pdf"

    print(f"\n  Processing ({file_type.upper()}): {file_path.name}")

    if file_type == "html":
        pages_data, global_metrics, first_10, total_pages, table_count = process_html(file_path)
    else:
        pages_data, global_metrics, first_10, total_pages, table_count = process_pdf(file_path)

    first_pages_text = " ".join(first_10)
    bank_name        = guess_bank_name(first_pages_text, file_path.name)
    reporting_year   = guess_reporting_year(first_pages_text, file_path.name)
    section_index    = build_section_index(pages_data)
    is_p3            = is_pillar3_document(first_pages_text, file_path.name)

    doc_type = "pillar3" if is_p3 else "annual_report"
    print(f"    Bank: {bank_name} | Year: {reporting_year or 'unknown'} | "
          f"Type: {doc_type} | Pages: {total_pages} | Tables: {table_count}")
    print(f"    Sections: {list(section_index.keys())[:6]}")

    return {
        "metadata": {
            "source_file":    file_path.name,
            "source_path":    str(file_path),
            "source_folder":  source_folder,
            "document_type":  doc_type,
            "file_type":      file_type,
            "bank_name":      bank_name,
            "reporting_year": reporting_year,
            "total_pages":    total_pages,
            "total_tables":   table_count,
            "processed_at":   datetime.now().isoformat(),
            "char_total":     sum(p["char_count"] for p in pages_data),
        },
        "key_metrics":   global_metrics,
        "section_index": section_index,
        "pages":         pages_data,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",      type=str, default=None,
                        help="Process a single file")
    parser.add_argument("--folder",    type=str, default=None,
                        help="Source folder: financials (default) or pillar3")
    parser.add_argument("--reprocess", action="store_true")
    args = parser.parse_args()

    if args.file:
        p    = Path(args.file)
        files  = [p if p.is_absolute() else PROJECT_ROOT / p]
        folder = args.folder or "financials"
    elif args.folder:
        source_dir = PROJECT_ROOT / args.folder
        source_dir.mkdir(exist_ok=True)
        files  = sorted(f for f in source_dir.iterdir()
                        if f.suffix.lower() in SUPPORTED_EXTS and f.is_file())
        folder = args.folder
    else:
        files  = sorted(f for f in FINANCIALS_DIR.iterdir()
                        if f.suffix.lower() in SUPPORTED_EXTS and f.is_file())
        folder = "financials"

    if not files:
        print(f"No supported files found in {folder}/")
        return

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
            size_kb = out_path.stat().st_size // 1024
            print(f"    ✅ {out_path.name} ({size_kb}KB)")
            processed += 1
        except Exception as e:
            print(f"    ❌ ERROR: {e}")
            traceback.print_exc()
            error_log.append({"file": file_path.name, "error": str(e)})
            errors += 1

    log_path = LOGS_DIR / "extract_financials_run.json"
    with open(log_path, "w") as f:
        json.dump({"run_at": datetime.now().isoformat(), "processed": processed,
                   "skipped": skipped, "errors": errors,
                   "error_details": error_log}, f, indent=2)

    print(f"\nDone. Processed: {processed} | Skipped: {skipped} | Errors: {errors}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
