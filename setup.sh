#!/bin/bash
# =============================================================================
# setup.sh — One-time environment setup
# =============================================================================
# Run this once before first use. Checks/installs system dependencies,
# creates the venv, and installs Python packages.
#
# Usage:
#   chmod +x setup.sh run.sh
#   ./setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements_ingestion.txt"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  LLM Credit Paper — Environment Setup"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Check macOS ───────────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
    warn "This setup script is for macOS. Continuing anyway."
fi

# ── Check Homebrew ────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    warn "Homebrew not found."
    warn "Install it from: https://brew.sh"
    warn "Then re-run this script."
    warn "Continuing without system dependency checks..."
else
    success "Homebrew found: $(brew --version | head -1)"

    # ── Install poppler (pdfinfo, pdffonts, pdftoppm) ─────────────────────────
    if command -v pdfinfo &>/dev/null; then
        success "poppler already installed: $(pdfinfo -v 2>&1 | head -1)"
    else
        info "Installing poppler..."
        brew install poppler
        success "poppler installed."
    fi

    # ── Install tesseract (OCR fallback — only needed for scanned PDFs) ───────
    if command -v tesseract &>/dev/null; then
        success "tesseract already installed: $(tesseract --version 2>&1 | head -1)"
    else
        warn "tesseract not installed (needed only for scanned/image PDFs)."
        read -r -p "  Install tesseract now? [y/N] " response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            brew install tesseract
            success "tesseract installed."
        else
            warn "Skipping tesseract. Install later with: brew install tesseract"
        fi
    fi
fi

# ── Find Python 3.10+ ─────────────────────────────────────────────────────────
find_python() {
    for cmd in python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &>/dev/null; then
            major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
            minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
            if [[ "$major" -eq 3 && "$minor" -ge 10 ]]; then
                echo "$cmd"
                return
            fi
        fi
    done
    return 1
}

if PYTHON=$(find_python); then
    success "Python found: $PYTHON ($($PYTHON --version))"
else
    warn "Python 3.10+ not found."
    if command -v brew &>/dev/null; then
        info "Installing Python 3.11 via Homebrew..."
        brew install python@3.11
        PYTHON=python3.11
        success "Python 3.11 installed."
    else
        error "Cannot install Python — Homebrew not available. Install manually from python.org"
    fi
fi

# ── Create virtual environment ────────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    info "Virtual environment already exists at .venv"
    read -r -p "  Recreate it? [y/N] " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
        info "Removed old venv."
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    success "Virtual environment created at .venv"
fi

# ── Activate and install packages ─────────────────────────────────────────────
source "$VENV_DIR/bin/activate"
success "Virtual environment activated."

info "Upgrading pip..."
pip install --quiet --upgrade pip

info "Installing Python dependencies..."
pip install -r "$REQUIREMENTS"
success "All Python packages installed."

# ── Make scripts executable ───────────────────────────────────────────────────
chmod +x "$SCRIPT_DIR/run.sh"
chmod +x "$SCRIPT_DIR/setup.sh"
success "Shell scripts marked executable."

# ── Verify imports ────────────────────────────────────────────────────────────
info "Verifying imports..."
python3 -c "
import fitz
import pdfplumber
import pypdf
import pydantic
import pandas
print('All imports OK')
" && success "All Python packages verified."

# ── Create placeholder README in PDF folders ─────────────────────────────────
for dir in financials rating_agency; do
    readme="$SCRIPT_DIR/$dir/README.txt"
    if [[ ! -f "$readme" ]]; then
        echo "Place PDFs in this folder then run: ./run.sh" > "$readme"
    fi
done

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Setup complete."
echo ""
echo "  Next steps:"
echo "  1. Copy bank annual report PDFs to:  financials/"
echo "  2. Copy rating agency PDFs to:       rating_agency/"
echo "  3. Run:  ./run.sh"
echo "═══════════════════════════════════════════════════════"
echo ""
