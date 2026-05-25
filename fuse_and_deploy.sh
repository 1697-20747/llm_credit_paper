#!/bin/bash
# =============================================================================
# fuse_and_deploy.sh — Fuse adapter and deploy to Ollama
# Handles MLX → GGUF conversion for Ollama compatibility
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$PROJECT_ROOT/.venv"
PYTHON="$VENV/bin/python"
MODELS_DIR="$PROJECT_ROOT/models"

source "$VENV/bin/activate"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

ADAPTER_DIR="$MODELS_DIR/qwen2.5-7b-camels-adapter"
BASE_MODEL="mlx-community/Qwen2.5-7B-Instruct-4bit"
FUSED_DIR="$MODELS_DIR/qwen2.5-7b-camels-fused"
GGUF_DIR="$MODELS_DIR/qwen2.5-7b-camels-gguf"

[[ -f "$ADAPTER_DIR/adapters.safetensors" ]] || \
    error "Adapter not found: $ADAPTER_DIR"

# ── Detect fuse flag ──────────────────────────────────────────────────────────
DEQUANT_FLAG=$($PYTHON -c "
import subprocess
r = subprocess.run(['python','-m','mlx_lm','fuse','--help'],
                  capture_output=True, text=True)
h = r.stdout + r.stderr
print('--dequantize' if '--dequantize' in h else '--de-quantize')
" 2>/dev/null || echo "--dequantize")

# ── Fuse adapter ──────────────────────────────────────────────────────────────
mkdir -p "$FUSED_DIR"
info "Fusing adapter (this takes a few minutes)..."

$PYTHON -m mlx_lm fuse \
    --model "$BASE_MODEL" \
    --adapter-path "$ADAPTER_DIR" \
    --save-path "$FUSED_DIR" \
    $DEQUANT_FLAG

info "Fused: $FUSED_DIR"

# ── Export directly to GGUF (avoids U32 data type conversion error) ───────────
mkdir -p "$GGUF_DIR"
info "Exporting to GGUF for Ollama..."

# Method 1: mlx_lm convert with export-gguf flag (mlx-lm 0.19+)
GGUF_FILE="$GGUF_DIR/camels-analyst-7b-q4_k_m.gguf"

$PYTHON -c "
import subprocess, sys

# Try mlx_lm fuse with --export-gguf (some versions support this directly)
result = subprocess.run([
    sys.executable, '-m', 'mlx_lm', 'fuse',
    '--help'
], capture_output=True, text=True)

has_gguf = '--export-gguf' in (result.stdout + result.stderr)
print('has_export_gguf:', has_gguf)
" 2>/dev/null

# Try direct GGUF export via fuse --export-gguf
$PYTHON -m mlx_lm fuse \
    --model "$BASE_MODEL" \
    --adapter-path "$ADAPTER_DIR" \
    --save-path "$GGUF_DIR" \
    --export-gguf 2>/dev/null && GGUF_EXPORTED=true || GGUF_EXPORTED=false

if [[ "$GGUF_EXPORTED" == "false" ]]; then
    # Fallback: use mlx_lm.convert with gguf output
    info "Trying convert with GGUF output..."
    $PYTHON -c "
import subprocess, sys, os
result = subprocess.run([
    sys.executable, '-m', 'mlx_lm', 'convert',
    '--hf-path', '$FUSED_DIR',
    '--mlx-path', '$GGUF_DIR',
    '--gguf-path', '$GGUF_FILE',
], capture_output=True, text=True)
print(result.stdout[-500:] if result.stdout else '')
print(result.stderr[-500:] if result.stderr else '')
sys.exit(result.returncode)
" 2>/dev/null || GGUF_EXPORTED=false
fi

# ── Find the GGUF file ────────────────────────────────────────────────────────
FOUND_GGUF=$(find "$GGUF_DIR" "$MODELS_DIR" -name "*.gguf" 2>/dev/null | head -1)

if [[ -n "$FOUND_GGUF" ]]; then
    info "GGUF found: $FOUND_GGUF"
    GGUF_FILE="$FOUND_GGUF"

    # Write Modelfile pointing to GGUF
    cat > "$PROJECT_ROOT/Modelfile" << MODELEOF
FROM $GGUF_FILE

SYSTEM """You are a senior credit analyst specialising in bank credit analysis \
using the CAMELS framework (Capital Adequacy, Asset Quality, Management, \
Earnings, Liquidity, Sensitivity to Market Risk). You follow Moody's, S&P \
Global Ratings, and Fitch Ratings methodologies. Every numerical claim must \
include a source citation [Source: p.XX] or [Source: Table Y, p.XX]. \
If data is unavailable write 'Data not available' — never fabricate figures. \
Structure every response: Assessment (Strong/Adequate/Weak/Critical), \
Key Metrics, Analysis, Peer Context, Key Risks, Rating Agency Commentary."""

PARAMETER temperature 0.05
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 4096
PARAMETER num_predict 2048
MODELEOF

    info "Modelfile written pointing to GGUF."
    info "Creating Ollama model..."
    ollama create camels-analyst-7b -f "$PROJECT_ROOT/Modelfile"
    info "✅ Ollama model created: camels-analyst-7b"

else
    # ── Fallback: serve the fused MLX model directly via mlx_lm ──────────────
    warn "GGUF export not available — using MLX direct serving instead"
    warn "The model will run via mlx_lm.server instead of Ollama"

    cat > "$PROJECT_ROOT/serve_mlx.sh" << 'SERVEEOF'
#!/bin/bash
# Serve the fine-tuned model directly via mlx_lm (no Ollama needed)
# Compatible with OpenAI API format — works with main.py --llm-url
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PROJECT_ROOT/.venv/bin/activate"

MODEL_DIR="$PROJECT_ROOT/models/qwen2.5-7b-camels-fused"
PORT=8080

echo "Starting MLX model server on http://localhost:$PORT"
echo "Use: python main.py --llm-url http://localhost:$PORT --model camels"
echo ""

python -m mlx_lm.server \
    --model "$MODEL_DIR" \
    --port $PORT
SERVEEOF
    chmod +x "$PROJECT_ROOT/serve_mlx.sh"

    info "Created serve_mlx.sh as alternative to Ollama"
    info "Run: ./serve_mlx.sh"
    info "Then: python main.py --llm-url http://localhost:8080 --model camels"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo " DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════════════"
if [[ -n "$FOUND_GGUF" ]]; then
echo " Mode    : Ollama (GGUF)"
echo ""
echo " Start   : ollama serve"
echo " Test    : ollama run camels-analyst-7b \"Analyse capital adequacy: CET1 13.5%, minimum 11.0%, leverage 5.2%\""
echo " Analyse : python main.py --pdf financials/2025-lbg-annual-report.pdf --bank 'Lloyds Banking Group'"
else
echo " Mode    : MLX direct server (fallback)"
echo ""
echo " Start   : ./serve_mlx.sh"
echo " Analyse : python main.py --llm-url http://localhost:8080 --model camels --pdf financials/2025-lbg-annual-report.pdf --bank 'Lloyds Banking Group'"
fi
echo "═══════════════════════════════════════════════════════════"
