#!/usr/bin/env python3
"""
cleanup_small_files.py
======================
1. Unzips any .zip files in financials/ and extracts PDFs from them
2. Removes downloaded files under a size threshold (likely exhibits/cover pages)

Usage:
    python scripts/cleanup_small_files.py           # unzip + remove files < 1MB
    python scripts/cleanup_small_files.py --mb 2    # remove files < 2MB
    python scripts/cleanup_small_files.py --dry-run # show what would happen
    python scripts/cleanup_small_files.py --unzip-only  # only unzip, no deletion
"""

import argparse
import zipfile
import shutil
from pathlib import Path

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
FINANCIALS_DIR = PROJECT_ROOT / "financials"

GREEN  = '\033[0;32m'; YELLOW = '\033[1;33m'; RED = '\033[0;31m'; NC = '\033[0m'
def info(msg):    print(f"{GREEN}[INFO]{NC}  {msg}")
def warn(msg):    print(f"{YELLOW}[WARN]{NC}  {msg}")
def deleted(msg): print(f"{RED}[DEL]{NC}   {msg}")
def extracted(msg): print(f"{GREEN}[ZIP]{NC}   {msg}")


def unzip_financials(dry_run: bool = False):
    """Extract PDFs from any .zip files in financials/."""
    zips = list(FINANCIALS_DIR.glob("*.zip"))
    if not zips:
        info("No .zip files found.")
        return

    info(f"Found {len(zips)} zip file(s) to process:")
    for zip_path in zips:
        print(f"  📦 {zip_path.name}")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                members = zf.namelist()
                pdfs = [m for m in members if m.lower().endswith('.pdf')
                        and not m.startswith('__MACOSX')]
                htms = [m for m in members if m.lower().endswith(('.htm', '.html'))
                        and not m.startswith('__MACOSX')]

                targets = pdfs if pdfs else htms
                if not targets:
                    warn(f"  No PDF or HTM files found in {zip_path.name}")
                    warn(f"  Contents: {members[:5]}")
                    continue

                for member in targets:
                    # Flatten path — extract just the filename
                    dest_name = Path(member).name
                    dest_path = FINANCIALS_DIR / dest_name

                    if dest_path.exists():
                        info(f"  Already exists: {dest_name} — skipping")
                        continue

                    if dry_run:
                        extracted(f"  Would extract: {dest_name}")
                    else:
                        # Extract to a temp location then move (avoids path issues)
                        zf.extract(member, FINANCIALS_DIR / "_tmp_zip")
                        src = FINANCIALS_DIR / "_tmp_zip" / member
                        shutil.move(str(src), str(dest_path))
                        size_mb = dest_path.stat().st_size / 1_048_576
                        extracted(f"  Extracted: {dest_name} ({size_mb:.1f}MB)")

        except zipfile.BadZipFile:
            warn(f"  Bad zip file: {zip_path.name}")
        except Exception as e:
            warn(f"  Error processing {zip_path.name}: {e}")

    # Clean up temp dir
    tmp_dir = FINANCIALS_DIR / "_tmp_zip"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)


def remove_small_files(threshold_mb: float, dry_run: bool = False):
    """Remove files under the size threshold."""
    threshold_bytes = int(threshold_mb * 1_048_576)
    mode = "DRY RUN — " if dry_run else ""

    print(f"\n{mode}Scanning for files under {threshold_mb}MB...\n")

    all_files = (list(FINANCIALS_DIR.glob("*.pdf")) +
                 list(FINANCIALS_DIR.glob("*.htm")) +
                 list(FINANCIALS_DIR.glob("*.html")))

    to_remove = []
    to_keep   = []

    for f in sorted(all_files):
        size_bytes = f.stat().st_size
        size_mb    = size_bytes / 1_048_576
        if size_bytes < threshold_bytes:
            to_remove.append((f, size_mb))
        else:
            to_keep.append((f, size_mb))

    if not to_remove:
        info(f"No files under {threshold_mb}MB. All {len(to_keep)} files look good.")
        return

    print(f"To {'remove' if not dry_run else 'remove (dry run)'}:")
    for f, size_mb in to_remove:
        print(f"  {RED}✗{NC} {f.name:<60} {size_mb:.2f}MB")

    print(f"\nTo keep:")
    for f, size_mb in to_keep:
        print(f"  {GREEN}✓{NC} {f.name:<60} {size_mb:.1f}MB")

    print(f"\nSummary: {len(to_remove)} to remove, {len(to_keep)} to keep")

    if dry_run:
        print(f"\nDry run — nothing deleted. Run without --dry-run to delete.")
        return

    confirm = input(f"\nDelete {len(to_remove)} file(s)? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    for f, size_mb in to_remove:
        f.unlink()
        deleted(f"{f.name} ({size_mb:.2f}MB)")

    info(f"\nDone. Removed {len(to_remove)} file(s).")
    info(f"Run ./run.sh --reprocess to reprocess remaining files.")


def print_summary():
    """Print a summary of what's in financials/."""
    all_files = (list(FINANCIALS_DIR.glob("*.pdf")) +
                 list(FINANCIALS_DIR.glob("*.htm")) +
                 list(FINANCIALS_DIR.glob("*.html")))
    zips      = list(FINANCIALS_DIR.glob("*.zip"))

    total_mb  = sum(f.stat().st_size for f in all_files) / 1_048_576

    print(f"\n{'='*60}")
    print(f"financials/ summary")
    print(f"{'='*60}")
    print(f"  Documents (PDF/HTM) : {len(all_files)}")
    print(f"  Zip files remaining : {len(zips)}")
    print(f"  Total size          : {total_mb:.0f}MB")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mb",         type=float, default=1.0,
                        help="Remove files smaller than this many MB (default: 1.0)")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Show what would happen without doing it")
    parser.add_argument("--unzip-only", action="store_true",
                        help="Only unzip files, skip size-based removal")
    args = parser.parse_args()

    print(f"\nCleanup: {FINANCIALS_DIR}\n")

    # Always unzip first
    unzip_financials(dry_run=args.dry_run)

    # Then remove small files (unless --unzip-only)
    if not args.unzip_only:
        remove_small_files(args.mb, dry_run=args.dry_run)

    print_summary()


if __name__ == "__main__":
    main()
