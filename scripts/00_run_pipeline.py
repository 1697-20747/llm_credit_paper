#!/usr/bin/env python3
"""
00_run_pipeline.py — Master orchestration script.
Runs all ingestion and processing stages in order.
"""

import argparse
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
LOGS_DIR     = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

SOURCE_FOLDERS = {
    "financials":     "Bank annual reports (PDF, HTM)",
    "pillar3":        "Pillar 3 risk disclosure reports (PDF)",
    "rating_agency":  "Rating agency methodology documents (PDF)",
    "rating_reports": "Rating agency reports on specific banks (PDF)",
    "credit_reports": "Existing credit papers in Word format (DOCX)",
}


def ensure_folders():
    for folder, description in SOURCE_FOLDERS.items():
        path = PROJECT_ROOT / folder
        path.mkdir(exist_ok=True)
        readme = path / "README.txt"
        if not readme.exists():
            readme.write_text(
                f"{description}\nPlace files here then run: ./run.sh\n"
            )


def scan_sources() -> dict:
    counts = {}
    for folder in SOURCE_FOLDERS:
        path = PROJECT_ROOT / folder
        if not path.exists():
            counts[folder] = {"pdf": 0, "htm": 0, "docx": 0, "total": 0}
            continue
        pdf  = len(list(path.glob("*.pdf")))
        htm  = len(list(path.glob("*.htm"))) + len(list(path.glob("*.html")))
        docx = len(list(path.glob("*.docx"))) + len(list(path.glob("*.doc")))
        counts[folder] = {"pdf": pdf, "htm": htm, "docx": docx,
                          "total": pdf + htm + docx}
    return counts


def run_script(script_name: str, extra_args: list = None) -> bool:
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path)] + (extra_args or [])
    print(f"\n{'─'*60}\n▶  {script_name}\n{'─'*60}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"\n❌ {script_name} failed (exit code {result.returncode})")
        return False
    return True


def print_final_summary():
    training_dir = PROJECT_ROOT / "training_data"
    stats_path   = LOGS_DIR / "build_pairs_stats.json"
    print(f"\n{'='*60}\nPIPELINE COMPLETE — SUMMARY\n{'='*60}")
    if stats_path.exists():
        with open(stats_path) as f:
            stats = json.load(f)
        print(f"  Training pairs : {stats.get('train_count', '?')}")
        print(f"  Eval pairs     : {stats.get('eval_count', '?')}")
        print(f"  By pipeline    : {stats.get('by_pipeline', {})}")
        print(f"  By quality     : {stats.get('by_quality', {})}")
    if training_dir.exists():
        print(f"\nOutput files:")
        for f in sorted(training_dir.glob("*.jsonl")):
            size_kb = f.stat().st_size // 1024
            lines   = sum(1 for _ in open(f))
            print(f"  {f.name:<45} {lines} pairs  ({size_kb}KB)")
    print(f"\n{'─'*60}")
    print(f"Next step: review training_data/combined_training.jsonl")
    print(f"Then run:  ./train_mlx.sh\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-triage",      action="store_true")
    parser.add_argument("--pairs-only",       action="store_true")
    parser.add_argument("--reprocess",        action="store_true")
    parser.add_argument("--skip-benchmark",   action="store_true",
                        help="Skip rebuilding benchmark index")
    parser.add_argument("--include-fdic",     action="store_true")
    parser.add_argument("--include-eba",      action="store_true")
    args = parser.parse_args()

    ensure_folders()

    print(f"LLM Credit Paper — Ingestion Pipeline")
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Started      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    counts = scan_sources()
    print(f"\nSource material found:")
    any_files = False
    for folder, description in SOURCE_FOLDERS.items():
        c = counts[folder]
        if c["total"] == 0:
            status = "0 files — empty"
        else:
            details = []
            if c["pdf"]:  details.append(f"{c['pdf']} PDF")
            if c["htm"]:  details.append(f"{c['htm']} HTM")
            if c["docx"]: details.append(f"{c['docx']} DOCX")
            status = f"{c['total']} file(s) ({', '.join(details)})"
            any_files = True
        print(f"  {folder:<20} {status}")

    if not any_files:
        print(f"\n⚠️  No source files found.")
        return

    reprocess_flag = ["--reprocess"] if args.reprocess else []

    if not args.pairs_only:
        if not args.skip_triage:
            run_script("01_triage.py")
        if counts["financials"]["total"] > 0:
            run_script("02_extract_financials.py", reprocess_flag)
        if counts["pillar3"]["pdf"] > 0:
            print(f"\n[FOUND] {counts['pillar3']['pdf']} Pillar 3 report(s)")
            run_script("02_extract_financials.py",
                       reprocess_flag + ["--folder", "pillar3"])
        if counts["rating_agency"]["total"] > 0:
            run_script("03_extract_rating_agency.py", reprocess_flag)
        if counts["rating_reports"]["pdf"] > 0:
            run_script("03_extract_rating_agency.py",
                       reprocess_flag + ["--folder", "rating_reports"])
        if counts["credit_reports"]["docx"] > 0:
            run_script("06_extract_credit_reports.py", reprocess_flag)

    # Build benchmark index BEFORE building pairs
    # (so pairs can include benchmark context)
    if not args.skip_benchmark:
        bench_args = []
        if args.include_fdic: bench_args.append("--include-fdic")
        if args.include_eba:  bench_args.append("--include-eba")
        print(f"\n{'─'*60}\n▶  Building benchmark index\n{'─'*60}")
        run_script("build_benchmark_index.py", bench_args)

    # Build training pairs
    if not run_script("04_build_training_pairs.py"):
        print("Training pair build failed")
        return

    print_final_summary()


if __name__ == "__main__":
    main()
