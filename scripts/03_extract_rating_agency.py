#!/usr/bin/env python3
"""
03_extract_rating_agency.py
===========================
Extracts and chunks rating agency PDFs into structured JSON.
Handles both methodology documents and specific bank rating reports.

Folders processed:
  rating_agency/   — methodology PDFs (Fitch, S&P, Moody's, Basel, OCC etc.)
  rating_reports/  — rating agency reports on specific banks (when --folder used)

For rating_reports/, attempts to extract:
  - Bank name being rated
  - Rating assigned and outlook
  - Rating rationale text
  - Key credit factors cited

Run:
    python scripts/03_extract_rating_agency.py
    python scripts/03_extract_rating_agency.py --folder rating_reports
    python scripts/03_extract_rating_agency.py --reprocess
    python scripts/03_extract_rating_agency.py --file rating_agency/fitch_rating.pdf
"""

import re
import json
import argparse
import traceback
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR     = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

AGENCY_PATTERNS = {
    "moodys":    [r"moody", r"moody's", r"moodys"],
    "sp":        [r"s&p\s+global", r"standard\s*&\s*poor", r"s&p\s+ratings"],
    "fitch":     [r"fitch\s+ratings?", r"fitch\s+group", r"\bfitch\b"],
    "eba":       [r"european\s+banking\s+authority", r"\beba\b"],
    "bis_basel": [r"bank\s+for\s+international\s+settlements", r"basel\s+committee", r"\bbcbs\b"],
    "boe_pra":   [r"bank\s+of\s+england", r"prudential\s+regulation", r"\bpra\b"],
    "fca":       [r"financial\s+conduct\s+authority", r"\bfca\b"],
    "fdic":      [r"federal\s+deposit\s+insurance", r"\bfdic\b"],
    "occ":       [r"comptroller\s+of\s+the\s+currency", r"\bocc\b", r"comptroller"],
    "fed":       [r"federal\s+reserve"],
    "imf":       [r"international\s+monetary\s+fund", r"\bimf\b"],
    "dbrs":      [r"dbrs\s+morningstar", r"\bdbrs\b", r"morningstar\s+credit"],
}

CAMELS_TOPIC_KEYWORDS = {
    "capital": [
        "capital adequacy", "cet1", "tier 1", "total capital", "leverage ratio",
        "risk-weighted", "rwa", "mrel", "capital buffer", "capital requirement",
        "pillar 1", "pillar 2", "output floor", "basel iv", "basel iii",
        "capital score", "capitalisation", "capital ratio",
    ],
    "asset_quality": [
        "asset quality", "credit quality", "non-performing", "npl", "impaired",
        "stage 1", "stage 2", "stage 3", "ecl", "expected credit loss",
        "loan loss", "provision", "coverage ratio", "charge-off", "ifrs 9",
        "asset risk", "allowance", "net charge", "forbearance",
    ],
    "management": [
        "management quality", "governance", "risk management", "board",
        "strategy", "management score", "internal controls", "risk culture",
        "management strength", "corporate governance",
    ],
    "earnings": [
        "earnings", "profitability", "return on equity", "return on assets",
        "net interest margin", "cost income", "pre-provision", "revenue",
        "income diversification", "earnings score", "rote", "roe", "nim",
        "efficiency ratio", "noninterest income",
    ],
    "liquidity": [
        "liquidity", "funding", "lcr", "nsfr", "hqla", "liquid assets",
        "funding stability", "deposit base", "wholesale funding",
        "maturity profile", "liquidity score", "loan to deposit",
    ],
    "sensitivity": [
        "market risk", "interest rate risk", "irrbb", "value at risk", "var",
        "sensitivity", "trading risk", "fair value", "fvoci",
        "fx risk", "duration", "pension risk", "rate sensitivity",
    ],
    "rating_methodology": [
        "rating methodology", "rating criteria", "rating approach",
        "baseline credit assessment", "bca", "viability rating", "vr",
        "issuer default rating", "idr", "stand-alone credit profile", "sacp",
        "rating scale", "scorecard", "anchor", "bicra", "camels",
        "uniform financial institutions rating",
    ],
    "rating_action": [
        "rating action", "rating affirmed", "rating upgraded", "rating downgraded",
        "outlook stable", "outlook negative", "outlook positive",
        "credit watch", "on watch", "rating rationale", "key rating drivers",
        "rating constraints", "rating sensitivities",
    ],
    "stress_testing": [
        "stress test", "stress scenario", "adverse scenario",
        "hurdle rate", "icaap", "ilaap", "severely adverse", "dfast",
    ],
}

# Patterns to extract rating-specific metadata from bank rating reports
RATING_EXTRACTION_PATTERNS = {
    "rated_bank": [
        r"([\w\s]+(?:Bank|Bancorp|Financial|Group|Holdings|Trust|Capital)[\w\s]*)"
        r"\s*(?:Rating|IDR|BCA|VR|Issuer)",
        r"Rating\s+(?:Action|Affirmation)\s+(?:on|for)\s+([\w\s]+(?:Bank|Group))",
    ],
    "rating_assigned": [
        r"(?:IDR|Long-Term IDR|Issuer Default Rating)[:\s]+([A-Da-d][+-]?)",
        r"(?:BCA|Baseline Credit Assessment)[:\s]+([a-d][a-z0-9+-]+)",
        r"(?:Viability Rating|VR)[:\s]+([a-z]{2,4}[+-]?)",
        r"(?:Long-Term Rating|LT Rating|Rating)[:\s]+([A-D][a-zA-Z0-9+-]+)",
    ],
    "outlook": [
        r"[Oo]utlook[:\s]+(Stable|Positive|Negative|Evolving|Watch\s+\w+)",
        r"[Rr]ating\s+[Ww]atch\s+(Positive|Negative|Evolving)",
    ],
}

HEADING_PATTERNS = [
    re.compile(r"^[A-Z][A-Z\s\-]{4,50}$"),
    re.compile(r"^\d+\.?\s+[A-Z][a-zA-Z\s]{4,60}$"),
    re.compile(r"^[IVX]+\.\s+[A-Z][a-zA-Z\s]{4,60}$"),
    re.compile(r"^(?:Section|Chapter|Part)\s+\d+"),
]


def is_scanned_pdf(pdf_path: Path, sample_pages: int = 5) -> bool:
    try:
        doc = fitz.open(str(pdf_path))
        total = len(doc)
        indices = list({0, total // 4, total // 2, total - 1})
        indices = [i for i in indices if 0 <= i < total][:sample_pages]
        char_counts = [len(doc[i].get_text("text").strip()) for i in indices]
        doc.close()
        avg = sum(char_counts) / len(char_counts) if char_counts else 0
        return avg < 100
    except Exception:
        return False


def check_tesseract() -> bool:
    try:
        result = subprocess.run(["tesseract", "--version"],
                                capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_pdftoppm() -> bool:
    try:
        result = subprocess.run(["pdftoppm", "-v"],
                                capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ocr_pdf(pdf_path: Path) -> str:
    if not check_tesseract():
        raise RuntimeError("tesseract not installed. Run: brew install tesseract")
    if not check_pdftoppm():
        raise RuntimeError("pdftoppm not installed. Run: brew install poppler")

    print(f"    Running OCR (this may take a few minutes)...")
    doc   = fitz.open(str(pdf_path))
    total = len(doc)
    doc.close()
    all_text = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        batch_size = 10
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            print(f"    OCR pages {batch_start+1}–{batch_end} of {total}...",
                  end=" ", flush=True)
            img_prefix = str(tmp_path / "page")
            subprocess.run([
                "pdftoppm", "-jpeg", "-r", "300",
                "-f", str(batch_start + 1), "-l", str(batch_end),
                str(pdf_path), img_prefix,
            ], capture_output=True, check=True)

            images = sorted(tmp_path.glob("page-*.jpg")) + \
                     sorted(tmp_path.glob("page-*.jpeg"))
            batch_text = []
            for img_path in images:
                result = subprocess.run([
                    "tesseract", str(img_path), "stdout",
                    "--oem", "3", "--psm", "6", "-l", "eng",
                ], capture_output=True, text=True, timeout=60)
                if result.returncode == 0 and result.stdout.strip():
                    batch_text.append(result.stdout.strip())
                img_path.unlink(missing_ok=True)
            all_text.extend(batch_text)
            print(f"{len(batch_text)} pages")

    full_text = "\n\n".join(all_text)
    print(f"    OCR complete: {len(full_text):,} characters")
    return full_text


def extract_text_standard(pdf_path: Path) -> str:
    doc  = fitz.open(str(pdf_path))
    text = "\n\n".join(
        f"[PAGE {i+1}]\n{doc[i].get_text('text')}"
        for i in range(len(doc))
    )
    doc.close()
    return text


def detect_agency(text_sample: str, filename: str) -> str:
    combined = (text_sample[:2000] + " " + filename).lower()
    for agency, patterns in AGENCY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, combined):
                return agency
    return "other"


def detect_document_type(text_sample: str, folder_hint: str = "") -> str:
    text_lower = text_sample.lower()
    # Rating reports have action language
    if folder_hint == "rating_reports" or any(kw in text_lower for kw in [
        "rating action", "rating affirmed", "rating downgraded", "rating upgraded",
        "key rating drivers", "rating sensitivities", "rating constraints",
        "outlook stable", "outlook negative",
    ]):
        return "rating_report"
    if any(kw in text_lower for kw in ["rating methodology", "rating criteria"]):
        return "rating_methodology"
    if any(kw in text_lower for kw in ["supervisory statement", "examination manual"]):
        return "regulatory_guidance"
    if any(kw in text_lower for kw in ["guidelines", "regulatory technical"]):
        return "regulatory_standard"
    if any(kw in text_lower for kw in ["working paper", "research paper"]):
        return "research_paper"
    if any(kw in text_lower for kw in ["camels", "uniform financial institutions rating"]):
        return "camels_methodology"
    return "general"


def extract_rating_metadata(text: str) -> dict:
    """Extract structured metadata from a bank rating report."""
    metadata = {"rated_bank": None, "rating": None, "outlook": None}
    for field, patterns in RATING_EXTRACTION_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, text[:3000], re.IGNORECASE)
            if m:
                metadata[field if field != "rating_assigned" else "rating"] = m.group(1).strip()
                break
    return metadata


def tag_camels_topics(text: str) -> list:
    text_lower = text.lower()
    topics = [
        topic for topic, keywords in CAMELS_TOPIC_KEYWORDS.items()
        if sum(1 for kw in keywords if kw in text_lower) >= 2
    ]
    return topics if topics else ["general"]


def is_heading_line(line: str) -> bool:
    line = line.strip()
    if len(line) < 5 or len(line) > 100:
        return False
    return any(pat.match(line) for pat in HEADING_PATTERNS)


def chunk_text(text: str, target_words: int = 500, max_words: int = 800) -> list:
    paragraphs  = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks      = []
    current     = []
    current_wds = 0

    for para in paragraphs:
        para_wds = len(para.split())
        if is_heading_line(para) and current_wds >= target_words // 2:
            if current:
                chunks.append("\n\n".join(current))
            current, current_wds = [para], para_wds
            continue
        if current_wds + para_wds > max_words and current:
            chunks.append("\n\n".join(current))
            current, current_wds = [para], para_wds
        else:
            current.append(para)
            current_wds += para_wds

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if len(c.split()) >= 40]


def clean_text(text: str) -> str:
    text = re.sub(r"\[PAGE \d+\]", "", text)
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {3,}", "  ", text)
    text = re.sub(r"(?<!\w)([^a-zA-Z0-9\s]{3,})(?!\w)", " ", text)
    return text.strip()


def process_pdf(pdf_path: Path, folder_hint: str = "") -> Optional[dict]:
    print(f"\n  Processing: {pdf_path.name}")

    doc        = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()
    print(f"    Pages: {total_pages}")

    scanned = is_scanned_pdf(pdf_path)
    if scanned:
        print(f"    Detected: SCANNED PDF — using OCR")
        try:
            raw_text = ocr_pdf(pdf_path)
        except RuntimeError as e:
            print(f"    ❌ OCR failed: {e}")
            return None
    else:
        print(f"    Detected: text-based PDF")
        raw_text = extract_text_standard(pdf_path)

    clean  = clean_text(raw_text)
    sample = clean[:3000]

    agency   = detect_agency(sample, pdf_path.name)
    doc_type = detect_document_type(sample, folder_hint)
    print(f"    Agency: {agency} | Type: {doc_type}")

    # Extract rating metadata for rating reports
    rating_meta = {}
    if doc_type == "rating_report":
        rating_meta = extract_rating_metadata(clean)
        if rating_meta.get("rated_bank"):
            print(f"    Rated bank : {rating_meta.get('rated_bank', 'unknown')}")
        if rating_meta.get("rating"):
            print(f"    Rating     : {rating_meta.get('rating', 'unknown')}")
        if rating_meta.get("outlook"):
            print(f"    Outlook    : {rating_meta.get('outlook', 'unknown')}")

    raw_chunks = chunk_text(clean, target_words=450, max_words=750)
    print(f"    Chunks: {len(raw_chunks)}")

    tagged_chunks = []
    for i, chunk in enumerate(raw_chunks):
        topics = tag_camels_topics(chunk)
        tagged_chunks.append({
            "chunk_id":      i,
            "word_count":    len(chunk.split()),
            "camels_topics": topics,
            "text":          chunk,
        })

    topic_counts = {}
    for chunk in tagged_chunks:
        for topic in chunk["camels_topics"]:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

    print(f"    Topics: {topic_counts}")

    return {
        "metadata": {
            "source_file":    pdf_path.name,
            "source_path":    str(pdf_path),
            "source_folder":  folder_hint or "rating_agency",
            "agency":         agency,
            "document_type":  doc_type,
            "total_pages":    total_pages,
            "total_chunks":   len(tagged_chunks),
            "ocr_used":       scanned,
            "processed_at":   datetime.now().isoformat(),
            **({k: v for k, v in rating_meta.items() if v} if rating_meta else {}),
        },
        "topic_distribution": topic_counts,
        "chunks":             tagged_chunks,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",      type=str, default=None,
                        help="Process a single PDF file")
    parser.add_argument("--folder",    type=str, default=None,
                        help="Source folder to process (rating_agency or rating_reports)")
    parser.add_argument("--reprocess", action="store_true",
                        help="Reprocess files that already have output JSON")
    args = parser.parse_args()

    # Determine which folders to process
    if args.file:
        p    = Path(args.file)
        pdfs = [p if p.is_absolute() else PROJECT_ROOT / p]
        folders_to_process = [("custom", pdfs)]
    elif args.folder:
        source_dir = PROJECT_ROOT / args.folder
        if not source_dir.exists():
            print(f"Folder not found: {source_dir}")
            print(f"It will be created automatically. Add PDFs and re-run.")
            source_dir.mkdir(exist_ok=True)
            return
        pdfs = sorted(source_dir.glob("*.pdf"))
        if not pdfs:
            print(f"No PDFs in {source_dir} — skipping.")
            return
        folders_to_process = [(args.folder, pdfs)]
    else:
        # Default: process rating_agency/ folder
        folders_to_process = [("rating_agency", sorted((PROJECT_ROOT / "rating_agency").glob("*.pdf")))]

    if not check_tesseract():
        print(f"\n⚠️  tesseract not installed — scanned PDFs will fail.")
        print(f"   Install: brew install tesseract\n")

    total_processed = total_skipped = total_errors = 0

    for folder_name, pdfs in folders_to_process:
        if not pdfs:
            print(f"\n[{folder_name.upper()}] No PDFs found — skipping.")
            continue

        # Output goes to processed/rating_agency/ regardless of source folder
        # so the pair builder finds everything in one place
        output_dir = PROJECT_ROOT / "processed" / "rating_agency"
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[{folder_name.upper()}] Found {len(pdfs)} PDF(s)")
        processed = skipped = errors = 0

        for pdf_path in pdfs:
            out_path = output_dir / (pdf_path.stem + ".json")
            if out_path.exists() and not args.reprocess:
                print(f"  Skipping (exists): {pdf_path.name}")
                skipped += 1
                continue
            try:
                result = process_pdf(pdf_path, folder_hint=folder_name)
                if result is None:
                    errors += 1
                    continue
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                chunks = result["metadata"]["total_chunks"]
                ocr    = " (OCR)" if result["metadata"]["ocr_used"] else ""
                dtype  = result["metadata"]["document_type"]
                print(f"    ✅ {out_path.name} — {chunks} chunks  [{dtype}]{ocr}")
                processed += 1
            except Exception as e:
                print(f"    ❌ ERROR: {e}")
                traceback.print_exc()
                errors += 1

        total_processed += processed
        total_skipped   += skipped
        total_errors    += errors
        print(f"  [{folder_name}] Processed: {processed} | Skipped: {skipped} | Errors: {errors}")

    print(f"\nTotal — Processed: {total_processed} | Skipped: {total_skipped} | Errors: {total_errors}")
    print(f"Output: {PROJECT_ROOT / 'processed' / 'rating_agency'}")


if __name__ == "__main__":
    main()
