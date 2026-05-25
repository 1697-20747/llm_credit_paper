#!/bin/bash
# =============================================================================
# run.sh — CAMELS Credit Paper Ingestion Pipeline
# =============================================================================
# Usage:
#   ./run.sh                          # full pipeline
#   ./run.sh --download-us            # download US banks from EDGAR
#   ./run.sh --download-uk            # download UK/EU/AU banks
#   ./run.sh --download-ra            # download rating agency / regulatory docs
#   ./run.sh --download-eba           # download EBA transparency exercise data
#   ./run.sh --download-fdic          # download FDIC Call Report data
#   ./run.sh --download-all           # download everything
#   ./run.sh --download-all --years 5 # override years (default: 10)
#   ./run.sh --skip-triage
#   ./run.sh --pairs-only
#   ./run.sh --reprocess
#
# Downloads always skip existing files — safe to re-run at any time.
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
REQUIREMENTS="$PROJECT_ROOT/requirements_ingestion.txt"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Find Python 3.10+ ─────────────────────────────────────────────────────────
find_python() {
    for cmd in python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &>/dev/null; then
            major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
            minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
            if [[ "$major" -eq 3 && "$minor" -ge 10 ]]; then
                echo "$cmd"; return
            fi
        fi
    done
    error "Python 3.10+ not found. Install with: brew install python@3.11"
}

PYTHON=$(find_python)
info "Using Python: $PYTHON ($($PYTHON --version))"

# ── Create venv if needed ─────────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
info "Virtual environment activated."

# ── Install/update dependencies ───────────────────────────────────────────────
STAMP="$VENV_DIR/.install_stamp"
REQ_HASH=$(md5 -q "$REQUIREMENTS" 2>/dev/null || md5sum "$REQUIREMENTS" | cut -d' ' -f1)
if [[ ! -f "$STAMP" || "$(cat "$STAMP" 2>/dev/null)" != "$REQ_HASH" ]]; then
    info "Installing dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -r "$REQUIREMENTS"
    echo "$REQ_HASH" > "$STAMP"
    info "Dependencies installed."
else
    info "Dependencies up to date."
fi

if ! command -v pdfinfo &>/dev/null; then
    warn "poppler not found — install with: brew install poppler"
fi

# ── Parse args ────────────────────────────────────────────────────────────────
DOWNLOAD_US=false
DOWNLOAD_UK=false
DOWNLOAD_RA=false
DOWNLOAD_EBA=false
DOWNLOAD_FDIC=false
YEARS=10
FDIC_LIMIT=100
PIPELINE_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --download-us)   DOWNLOAD_US=true;   shift ;;
        --download-uk)   DOWNLOAD_UK=true;   shift ;;
        --download-ra)   DOWNLOAD_RA=true;   shift ;;
        --download-eba)  DOWNLOAD_EBA=true;  shift ;;
        --download-fdic) DOWNLOAD_FDIC=true; shift ;;
        --download-all)
            DOWNLOAD_US=true; DOWNLOAD_UK=true; DOWNLOAD_RA=true
            DOWNLOAD_EBA=true; DOWNLOAD_FDIC=true
            shift ;;
        --years)       YEARS="$2";      shift 2 ;;
        --fdic-limit)  FDIC_LIMIT="$2"; shift 2 ;;
        *)             PIPELINE_ARGS+=("$1"); shift ;;
    esac
done

# ── Downloads ─────────────────────────────────────────────────────────────────
if [[ "$DOWNLOAD_US" == true ]]; then
    info "Downloading US bank 10-Ks from SEC EDGAR (years: $YEARS)..."
    python "$PROJECT_ROOT/scripts/download_financials.py" \
        --source edgar --years "$YEARS"
fi

if [[ "$DOWNLOAD_UK" == true ]]; then
    info "Downloading UK/EU/AU bank annual reports (years: $YEARS)..."
    python "$PROJECT_ROOT/scripts/download_uk_banks.py" \
        --years "$YEARS"
fi

if [[ "$DOWNLOAD_RA" == true ]]; then
    info "Downloading rating agency and regulatory methodology documents..."
    python "$PROJECT_ROOT/scripts/download_rating_agency.py"
fi

if [[ "$DOWNLOAD_EBA" == true ]]; then
    info "Downloading EBA EU-wide Transparency Exercise data..."
    python "$PROJECT_ROOT/scripts/download_eba_data.py"
fi

if [[ "$DOWNLOAD_FDIC" == true ]]; then
    info "Downloading FDIC Call Report data (top $FDIC_LIMIT banks, $YEARS years)..."
    python "$PROJECT_ROOT/scripts/download_fdic_data.py" \
        --limit "$FDIC_LIMIT" --years "$YEARS"
fi

# ── Run the pipeline ──────────────────────────────────────────────────────────
info "Starting ingestion pipeline..."
echo ""
python "$PROJECT_ROOT/scripts/00_run_pipeline.py" "${PIPELINE_ARGS[@]+"${PIPELINE_ARGS[@]}"}"
