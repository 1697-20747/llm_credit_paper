#!/usr/bin/env python3
"""
05_upgrade_training_pairs.py
============================
Upgrades 'template' quality financial statement training pairs to
analyst-quality responses using the Claude API (one-time online step).

FULLY RESUMABLE — safe to interrupt with Ctrl+C at any time.
Progress is saved after every single pair. Output JSONL is written
incrementally so partial results are always available.

Re-run the same command to continue from where it stopped.

Usage:
    .venv/bin/python scripts/05_upgrade_training_pairs.py --dry-run
    .venv/bin/python scripts/05_upgrade_training_pairs.py --limit 10
    .venv/bin/python scripts/05_upgrade_training_pairs.py
    .venv/bin/python scripts/05_upgrade_training_pairs.py --reset

Requirements:
    export ANTHROPIC_API_KEY=sk-ant-...
"""

import os
import json
import time
import signal
import argparse
import hashlib
from pathlib import Path
from datetime import datetime

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
TRAINING_DIR  = PROJECT_ROOT / "training_data"
LOGS_DIR      = PROJECT_ROOT / "logs"
PROGRESS_FILE = LOGS_DIR / "upgrade_progress.json"
STATS_FILE    = LOGS_DIR / "upgrade_stats.json"

# Incremental output — written pair by pair, always current
UPGRADED_JSONL    = TRAINING_DIR / "financial_pairs_upgraded.jsonl"
COMBINED_TRAIN    = TRAINING_DIR / "combined_training_upgraded.jsonl"
COMBINED_EVAL     = TRAINING_DIR / "combined_eval_upgraded.jsonl"

GREEN  = '\033[0;32m'; YELLOW = '\033[1;33m'
RED    = '\033[0;31m'; CYAN   = '\033[0;36m'; NC = '\033[0m'
def info(msg):   print(f"{GREEN}[INFO]{NC}  {msg}", flush=True)
def warn(msg):   print(f"{YELLOW}[WARN]{NC}  {msg}", flush=True)
def error(msg):  print(f"{RED}[ERROR]{NC} {msg}", flush=True)
def action(msg): print(f"{CYAN}[API]{NC}   {msg}", flush=True)

MODEL               = "claude-haiku-4-5-20251001"
MAX_TOKENS          = 1500
TEMPERATURE         = 0.3
RETRY_ATTEMPTS      = 5
RETRY_BASE_DELAY    = 10
BATCH_PAUSE         = 1.5

# Global flag for clean interrupt handling
_interrupted = False

def handle_interrupt(sig, frame):
    global _interrupted
    _interrupted = True
    print(f"\n{YELLOW}[INTERRUPT]{NC} Ctrl+C caught — finishing current pair then saving...")

signal.signal(signal.SIGINT, handle_interrupt)

SYSTEM_PROMPT = (
    "You are a senior credit analyst at a major financial institution with 20 years "
    "of experience in bank credit analysis. You specialise in the CAMELS framework "
    "(Capital Adequacy, Asset Quality, Management, Earnings, Liquidity, Sensitivity "
    "to Market Risk) and follow Moody's, S&P Global Ratings, and Fitch Ratings "
    "methodologies.\n\n"
    "Write a high-quality, factual CAMELS analysis section based on the extracted "
    "annual report data provided. Rules:\n"
    "1. Every numerical claim MUST cite source: [Source: p.XX] or [Source: Table Y, p.XX]. "
    "Only cite page numbers explicitly in the input.\n"
    "2. If a metric is absent, write 'Data not available' — never fabricate figures.\n"
    "3. Use exact numbers from input — do not round or adjust.\n"
    "4. Begin with: **Assessment: [Strong / Adequate / Weak / Critical]**\n"
    "5. Structure: Assessment → Key Metrics → Analysis → Peer Context → Key Risks\n"
    "6. End with a brief Moody's / S&P / Fitch rating agency commentary.\n"
    "7. Professional analyst prose — not bullet points.\n"
    "8. Be specific and factual. Length: 300–500 words."
)


# ─────────────────────────────────────────────────────────────────────────────
# Progress — atomic save using temp file + rename
# ─────────────────────────────────────────────────────────────────────────────

def pair_id(pair: dict) -> str:
    return hashlib.md5(pair["messages"][1]["content"][:500].encode()).hexdigest()


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            warn("Progress file corrupted — loading backup")
            backup = PROGRESS_FILE.with_suffix(".json.bak")
            if backup.exists():
                with open(backup) as f:
                    return json.load(f)
    return {"completed": {}, "failed": {}, "started_at": datetime.now().isoformat()}


def save_progress(progress: dict):
    """
    Atomic save — write to temp file first, then rename.
    Prevents corruption if interrupted mid-write.
    """
    progress["last_updated"] = datetime.now().isoformat()
    tmp = PROGRESS_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(progress, f, indent=2)
    # Backup previous version
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.replace(PROGRESS_FILE.with_suffix(".json.bak"))
    tmp.replace(PROGRESS_FILE)


# ─────────────────────────────────────────────────────────────────────────────
# Incremental JSONL writer
# ─────────────────────────────────────────────────────────────────────────────

class IncrementalWriter:
    """
    Appends pairs to a JSONL file as they complete.
    On resume, rebuilds from progress checkpoint rather than re-appending.
    """
    def __init__(self, path: Path):
        self.path = path

    def write_all(self, pairs: list):
        """Write complete list — used for rebuild at start of run."""
        tmp = self.path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def append(self, pair: dict):
        """Append a single pair — safe incremental write."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


# ─────────────────────────────────────────────────────────────────────────────
# API client
# ─────────────────────────────────────────────────────────────────────────────

def call_claude(client, user_content: str) -> str | None:
    for attempt in range(RETRY_ATTEMPTS):
        if _interrupted:
            return None
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            return response.content[0].text

        except Exception as e:
            err_str = str(e).lower()

            if "rate_limit" in err_str or "429" in err_str or "overloaded" in err_str:
                wait = RETRY_BASE_DELAY * (2 ** attempt)
                warn(f"  Rate limit — waiting {wait}s (attempt {attempt+1}/{RETRY_ATTEMPTS})")
                # Sleep in small increments so Ctrl+C is responsive
                for _ in range(int(wait)):
                    if _interrupted:
                        return None
                    time.sleep(1)
                continue

            if "authentication" in err_str or "401" in err_str or "api_key" in err_str:
                error("Authentication failed — check ANTHROPIC_API_KEY")
                return None

            if "context" in err_str or "too long" in err_str or "413" in err_str:
                warn("Input too long — skipping pair")
                return None

            wait = RETRY_BASE_DELAY * (2 ** attempt)
            warn(f"  API error: {str(e)[:80]} — waiting {wait}s")
            for _ in range(int(wait)):
                if _interrupted:
                    return None
                time.sleep(1)

    error(f"Failed after {RETRY_ATTEMPTS} attempts")
    return None


def truncate_prompt(content: str, max_chars: int = 8000) -> str:
    if len(content) <= max_chars:
        return content
    return content[:1000] + content[1000:max_chars] + "\n\n[... truncated ...]"


# ─────────────────────────────────────────────────────────────────────────────
# Rebuild combined files from current state
# ─────────────────────────────────────────────────────────────────────────────

def rebuild_combined(upgraded_financial: list):
    import random
    ra_pairs  = load_jsonl(TRAINING_DIR / "rating_agency_pairs.jsonl")
    all_pairs = upgraded_financial + ra_pairs
    random.seed(42)
    random.shuffle(all_pairs)
    n_eval    = max(1, int(len(all_pairs) * 0.10))
    return all_pairs[n_eval:], all_pairs[:n_eval]


def write_combined(upgraded_financial: list):
    """Rebuild and write combined training files."""
    train, eval_ = rebuild_combined(upgraded_financial)
    IncrementalWriter(COMBINED_TRAIN).write_all(train)
    IncrementalWriter(COMBINED_EVAL).write_all(eval_)
    return len(train), len(eval_)


# ─────────────────────────────────────────────────────────────────────────────
# Main upgrade loop
# ─────────────────────────────────────────────────────────────────────────────

def run_upgrade(pairs: list, client, progress: dict,
                limit: int = None, dry_run: bool = False):

    global _interrupted

    to_upgrade = pairs[:limit] if limit else pairs
    total      = len(to_upgrade)
    writer     = IncrementalWriter(UPGRADED_JSONL)

    info(f"Pairs to upgrade: {total}")
    info(f"Already completed: {len(progress['completed'])}")

    if dry_run:
        info("DRY RUN — showing first 3 prompts\n")

    # ── Rebuild current state from progress before starting ───────────────────
    # This ensures the output file is consistent with checkpoint on resume
    current_pairs = []
    for pair in to_upgrade:
        pid = pair_id(pair)
        if pid in progress["completed"]:
            current_pairs.append({
                "messages": [
                    pair["messages"][0],
                    pair["messages"][1],
                    {"role": "assistant", "content": progress["completed"][pid]},
                ]
            })
        else:
            current_pairs.append(pair)

    # Write current state to output file (reflects all previously completed work)
    if not dry_run:
        writer.write_all(current_pairs)
        info(f"Output file initialised with {len(current_pairs)} pairs")

    api_calls = 0
    skipped   = 0
    failed    = 0

    for i, pair in enumerate(to_upgrade, 1):
        if _interrupted:
            info("Interrupted — saving current state...")
            break

        pid = pair_id(pair)

        # Already completed
        if pid in progress["completed"]:
            skipped += 1
            if dry_run and i <= 3:
                print(f"\n{'─'*50}\nPair {i}: [cached]\n")
            continue

        # Previously permanently failed
        if pid in progress.get("failed", {}):
            failed += 1
            continue

        user_content = truncate_prompt(pair["messages"][1]["content"])

        if dry_run:
            if i <= 3:
                print(f"\n{'─'*50}")
                print(f"Pair {i}/{total} — {pair['messages'][1]['content'][:100]}")
                print(f"Prompt preview:\n{user_content[:400]}\n...")
            elif i == 4:
                print(f"\n[...{total - 3} more pairs]")
            continue

        action(f"[{i}/{total}] {pair['messages'][1]['content'][:60].strip()}...")

        response = call_claude(client, user_content)

        if _interrupted and not response:
            info("Interrupted cleanly after finishing previous pair.")
            break

        if response:
            # 1. Save to progress checkpoint (atomic)
            progress["completed"][pid] = response
            save_progress(progress)

            # 2. Build upgraded pair
            upgraded_pair = {
                "messages": [
                    pair["messages"][0],
                    pair["messages"][1],
                    {"role": "assistant", "content": response},
                ]
            }

            # 3. Update in-memory list and rewrite output file
            #    (find and replace in current_pairs)
            for j, cp in enumerate(current_pairs):
                if pair_id(cp) == pid:
                    current_pairs[j] = upgraded_pair
                    break

            # 4. Rewrite output JSONL with updated pair
            writer.write_all(current_pairs)

            api_calls += 1
            preview = response[:100].replace("\n", " ")
            info(f"  ✅ {preview}...")

        else:
            if not _interrupted:
                progress["failed"][pid] = datetime.now().isoformat()
                save_progress(progress)
                failed += 1
                warn("  Keeping template for this pair")

        # Interruptible pause
        for _ in range(int(BATCH_PAUSE)):
            if _interrupted:
                break
            time.sleep(1)

        if i % 50 == 0:
            pct = round(100 * (skipped + api_calls) / total)
            info(f"  Progress: {i}/{total} ({pct}%) | "
                 f"Done: {api_calls} | Cached: {skipped} | Failed: {failed}")

    # ── Final combined file rebuild ───────────────────────────────────────────
    if not dry_run:
        info("Rebuilding combined training files...")
        n_train, n_eval = write_combined(current_pairs)
        info(f"Combined training: {n_train} pairs")
        info(f"Combined eval:     {n_eval} pairs")

    return api_calls, skipped, failed, current_pairs


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit",   type=int, default=None)
    parser.add_argument("--reset",   action="store_true")
    parser.add_argument("--model",   type=str, default=MODEL)
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        error("ANTHROPIC_API_KEY not set.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return

    try:
        import anthropic
    except ImportError:
        error("anthropic not installed. Run: .venv/bin/pip install anthropic")
        return

    financial_path = TRAINING_DIR / "financial_pairs.jsonl"
    if not financial_path.exists():
        error(f"Not found: {financial_path}. Run ./run.sh --reprocess first.")
        return

    pairs = load_jsonl(financial_path)
    info(f"Loaded {len(pairs)} financial pairs")

    if args.reset:
        PROGRESS_FILE.unlink(missing_ok=True)
        info("Progress reset.")

    progress     = load_progress()
    already_done = len(progress["completed"])
    if already_done > 0:
        info(f"Resuming — {already_done} pairs already in checkpoint")

    if args.dry_run:
        run_upgrade(pairs, None, progress, limit=args.limit, dry_run=True)
        print("\nDry run complete.")
        return

    remaining  = len(pairs) - already_done
    to_process = min(remaining, args.limit) if args.limit else remaining

    print(f"\n{'='*60}")
    print(f"UPGRADE PLAN")
    print(f"{'='*60}")
    print(f"  Financial pairs total  : {len(pairs)}")
    print(f"  Already in checkpoint  : {already_done}")
    print(f"  To process this run    : {to_process}")
    print(f"  Model                  : {args.model}")
    print(f"  Est. cost (Haiku)      : ~${to_process * 0.002:.2f}")
    print(f"  Est. time              : ~{max(1, to_process * 2 // 60)} min")
    print(f"  Safe to interrupt      : YES — Ctrl+C saves immediately")
    print(f"  Resume command         : (same command again)")
    print(f"  Progress file          : {PROGRESS_FILE}")
    print(f"  Output file            : {UPGRADED_JSONL}")
    print(f"{'='*60}")

    if to_process == 0:
        info("All pairs already in checkpoint.")
        info("Run with --reset to start over, or check output files.")
        return

    confirm = input("\nProceed? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    client     = anthropic.Anthropic(api_key=api_key)
    start_time = time.time()

    api_calls, skipped, failed, final_pairs = run_upgrade(
        pairs, client, progress, limit=args.limit
    )

    elapsed = (time.time() - start_time) / 60

    stats = {
        "run_at":          datetime.now().isoformat(),
        "model":           args.model,
        "api_calls":       api_calls,
        "from_cache":      skipped,
        "failed":          failed,
        "interrupted":     _interrupted,
        "elapsed_minutes": round(elapsed, 1),
        "output_upgraded": str(UPGRADED_JSONL),
        "output_train":    str(COMBINED_TRAIN),
        "output_eval":     str(COMBINED_EVAL),
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n{'='*60}")
    if _interrupted:
        print(f"INTERRUPTED — progress saved")
    else:
        print(f"UPGRADE COMPLETE")
    print(f"{'='*60}")
    print(f"  API calls    : {api_calls}")
    print(f"  From cache   : {skipped}")
    print(f"  Failed       : {failed}")
    print(f"  Elapsed      : {elapsed:.1f} min")
    if _interrupted:
        print(f"\n  Resume with: .venv/bin/python scripts/05_upgrade_training_pairs.py")
    else:
        print(f"\n  Training file: {COMBINED_TRAIN.name}")
        print(f"  Eval file    : {COMBINED_EVAL.name}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
