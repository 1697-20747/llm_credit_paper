#!/usr/bin/env python3
"""
01_triage.py
============
Scans all PDFs and HTM files in financials/, pillar3/, and rating_agency/.
Produces a triage report with extraction strategy per file.
Handles corrupt/invalid PDFs gracefully — logs errors and continues.

Output:
    logs/triage_report.json
    logs/triage_summary.txt
"""

import json
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime

import fitz
import pdfplumber

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
FINANCIALS_DIR = PROJECT_ROOT / "financials"
PILLAR3_DIR    = PROJECT_ROOT / "pillar3"
RATING_DIR     = PROJECT_ROOT / "rating_agency"
LOGS_DIR       = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

FINANCIAL_EXTS = {".pdf", ".htm", ".html"}
PDF_EXTS       = {".pdf"}

MIN_PDF_BYTES  = 200_000   # files smaller than this are redirect pages


@dataclass
class PDFProfile:
    path: str
    category: str
    filename: str
    file_type: str
    size_mb: float
    page_count: int
    text_extractable: bool
    avg_chars_per_page: float
    scanned_page_count: int
    table_page_count: int
    font_issues: bool
    strategy: str
    notes: list = field(default_factory=list)


def is_valid_pdf(path: Path) -> bool:
    """Check that a PDF file is real — not a redirect/error HTML page."""
    if path.stat().st_size < MIN_PDF_BYTES:
        return False
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        return magic == b"%PDF"
    except Exception:
        return False


def get_page_count(path: Path, file_type: str) -> int:
    if file_type == "html":
        return 1
    try:
        doc = fitz.open(str(path))
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return 0


def assess_text_quality(path: Path, file_type: str,
                        sample_pages: int = 5) -> tuple:
    if file_type == "html":
        try:
            text  = path.read_text(encoding="utf-8", errors="replace")
            clean = re.sub(r"<[^>]+>", " ", text)
            clean = re.sub(r"\s+", " ", clean).strip()
            avg   = len(clean) / 10
            return len(clean) > 1000, round(avg, 1), 0
        except Exception:
            return False, 0.0, 0

    try:
        doc     = fitz.open(str(path))
        total   = len(doc)
        indices = list({0, total // 2, total - 1,
                        min(3, total - 1), min(9, total - 1)})
        indices = [i for i in indices if 0 <= i < total][:sample_pages]
        char_counts, scanned = [], 0
        for i in indices:
            try:
                text = doc[i].get_text("text").strip()
                char_counts.append(len(text))
                if len(text) < 50:
                    scanned += 1
            except Exception:
                char_counts.append(0)
                scanned += 1
        doc.close()
        avg = sum(char_counts) / len(char_counts) if char_counts else 0
        return avg > 100, round(avg, 1), scanned
    except Exception:
        return False, 0.0, 0


def count_table_pages(path: Path, file_type: str,
                      max_pages: int = 30) -> int:
    """Count pages containing tables. Handles corrupt pages gracefully."""
    if file_type == "html":
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return min(len(re.findall(r"<table", text, re.IGNORECASE)), 99)
        except Exception:
            return 0

    count = 0
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages[:max_pages]:
                try:
                    if page.find_tables():
                        count += 1
                except Exception:
                    # Skip corrupt/problematic pages — don't crash
                    pass
    except Exception:
        pass
    return count


def check_font_issues(path: Path, file_type: str) -> bool:
    if file_type == "html":
        return False
    try:
        result = subprocess.run(
            ["pdffonts", str(path)],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.strip().split("\n")[2:]:
            parts = line.split()
            if len(parts) >= 5 and parts[-3] == "no":
                return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def recommend_strategy(profile: PDFProfile) -> str:
    if profile.file_type == "html":
        return "HTML_EXTRACT"
    if not profile.text_extractable:
        if profile.scanned_page_count > 2:
            return "OCR_REQUIRED"
        return "VISUAL_INSPECT"
    if profile.table_page_count > 5:
        return "FULL_WITH_TABLES"
    if profile.font_issues:
        return "FALLBACK_LAYOUT"
    return "STANDARD_TEXT"


def triage_file(file_path: Path, category: str) -> PDFProfile:
    ext       = file_path.suffix.lower()
    file_type = "html" if ext in (".htm", ".html") else "pdf"
    size_mb   = round(file_path.stat().st_size / 1_048_576, 2)

    print(f"  {file_path.name[:58]:<58}", end=" ", flush=True)

    # Fast validity check for PDFs
    if file_type == "pdf" and not is_valid_pdf(file_path):
        print(f"{size_mb:.1f}MB | INVALID_PDF (redirect/error page — delete and re-download)")
        return PDFProfile(
            path=str(file_path), category=category,
            filename=file_path.name, file_type=file_type,
            size_mb=size_mb, page_count=0,
            text_extractable=False, avg_chars_per_page=0,
            scanned_page_count=0, table_page_count=0,
            font_issues=False, strategy="INVALID_PDF",
            notes=["File is not a valid PDF — likely a redirect or error page",
                   "Delete and re-download: ./scripts/download_annual_reports.sh --validate"],
        )

    pages                    = get_page_count(file_path, file_type)
    extractable, avg_chars, scanned = assess_text_quality(file_path, file_type)
    table_pages              = count_table_pages(file_path, file_type)
    font_issues              = check_font_issues(file_path, file_type)

    profile = PDFProfile(
        path=str(file_path), category=category,
        filename=file_path.name, file_type=file_type,
        size_mb=size_mb, page_count=pages,
        text_extractable=extractable, avg_chars_per_page=avg_chars,
        scanned_page_count=scanned, table_page_count=table_pages,
        font_issues=font_issues, strategy="",
        notes=[],
    )
    profile.strategy = recommend_strategy(profile)

    if not extractable:
        profile.notes.append("WARNING: Low text yield — may need OCR")
    if pages > 400:
        profile.notes.append(f"LARGE FILE: {pages} pages")
    if size_mb > 50:
        profile.notes.append(f"LARGE SIZE: {size_mb}MB")

    print(f"{size_mb:.1f}MB | {pages}pp | {profile.strategy}")
    return profile


def main():
    all_profiles = []
    invalid_files = []

    scan_targets = [
        ("financial",     FINANCIALS_DIR, FINANCIAL_EXTS),
        ("pillar3",       PILLAR3_DIR,    PDF_EXTS),
        ("rating_agency", RATING_DIR,     PDF_EXTS),
    ]

    for category, directory, extensions in scan_targets:
        if not directory.exists():
            continue
        files = sorted(
            f for f in directory.iterdir()
            if f.suffix.lower() in extensions and f.is_file()
               and not f.name.startswith(".")
        )
        if not files:
            continue

        print(f"\n[{category.upper()}] {len(files)} file(s) in {directory.name}/")

        for file_path in files:
            try:
                profile = triage_file(file_path, category)
                all_profiles.append(asdict(profile))
                if profile.strategy == "INVALID_PDF":
                    invalid_files.append(file_path.name)
            except KeyboardInterrupt:
                print(f"\n\nInterrupted — saving partial report...")
                break
            except Exception as e:
                print(f"  ERROR processing {file_path.name}: {e}")
                all_profiles.append({
                    "path": str(file_path), "category": category,
                    "filename": file_path.name, "strategy": "ERROR",
                    "notes": [str(e)],
                })

    report = {
        "generated_at": datetime.now().isoformat(),
        "total_files":  len(all_profiles),
        "profiles":     all_profiles,
        "summary": {
            "financial_count":     sum(1 for p in all_profiles if p.get("category") == "financial"),
            "pillar3_count":       sum(1 for p in all_profiles if p.get("category") == "pillar3"),
            "rating_agency_count": sum(1 for p in all_profiles if p.get("category") == "rating_agency"),
            "needs_ocr":    [p["filename"] for p in all_profiles if p.get("strategy") == "OCR_REQUIRED"],
            "html_files":   [p["filename"] for p in all_profiles if p.get("file_type") == "html"],
            "invalid_pdfs": invalid_files,
        }
    }

    json_path = LOGS_DIR / "triage_report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    strategy_counts = {}
    for p in all_profiles:
        s = p.get("strategy", "UNKNOWN")
        strategy_counts[s] = strategy_counts.get(s, 0) + 1

    summary_lines = [
        "TRIAGE SUMMARY", "=" * 70,
        f"Generated: {report['generated_at']}",
        f"Total files: {report['total_files']}",
        "",
        f"Financial statements : {report['summary']['financial_count']}",
        f"  of which HTML/HTM  : {len(report['summary']['html_files'])}",
        f"Pillar 3 reports     : {report['summary']['pillar3_count']}",
        f"Rating agency docs   : {report['summary']['rating_agency_count']}",
        "",
        "EXTRACTION STRATEGIES:",
    ]
    for strat, count in sorted(strategy_counts.items()):
        summary_lines.append(f"  {strat:<25} {count} file(s)")

    if invalid_files:
        summary_lines += ["", "⚠️  INVALID PDFs (redirect pages — re-download):"]
        for f in invalid_files:
            summary_lines.append(f"    - {f}")
        summary_lines += [
            "",
            "Fix: ./scripts/download_annual_reports.sh --validate",
        ]

    if report["summary"]["needs_ocr"]:
        summary_lines += ["", "⚠️  FILES REQUIRING OCR:"]
        for f in report["summary"]["needs_ocr"]:
            summary_lines.append(f"    - {f}")

    summary_lines += ["", f"Full report: {json_path}"]
    summary_text = "\n".join(summary_lines)
    (LOGS_DIR / "triage_summary.txt").write_text(summary_text)
    print("\n" + summary_text)


if __name__ == "__main__":
    main()
