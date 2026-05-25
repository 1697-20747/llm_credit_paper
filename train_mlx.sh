#!/bin/bash
# =============================================================================
# train_mlx.sh — CAMELS Credit Analyst QLoRA Training
# 16GB optimised — pre-quantised 4-bit base model + content truncation
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$PROJECT_ROOT/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"
LOGS_DIR="$PROJECT_ROOT/logs"
MODELS_DIR="$PROJECT_ROOT/models"
MLX_DATA_DIR="$PROJECT_ROOT/training_data/mlx"
mkdir -p "$LOGS_DIR" "$MODELS_DIR" "$MLX_DATA_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ "$(uname)" == "Darwin" ]] || error "Requires macOS Apple Silicon."
[[ -f "$PYTHON" ]]           || error "Project venv not found. Run ./setup.sh first."

source "$VENV/bin/activate"

MEMORY_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "unknown")

info "=== CAMELS Credit Analyst — MLX QLoRA Training ==="
info "Chip   : $CHIP"
info "Memory : ${MEMORY_GB}GB unified"

# ── Install dependencies ──────────────────────────────────────────────────────
$PYTHON -c "import mlx_lm" 2>/dev/null || { info "Installing mlx-lm..."; $PIP install --quiet mlx-lm; }
$PYTHON -c "import huggingface_hub" 2>/dev/null || { $PIP install --quiet huggingface_hub; }
MLX_VERSION=$($PYTHON -c "import mlx_lm; print(mlx_lm.__version__)" 2>/dev/null || echo "unknown")
info "mlx-lm : $MLX_VERSION"

# ── HuggingFace login ─────────────────────────────────────────────────────────
HF_USER=$($PYTHON -c "
from huggingface_hub import HfApi
try:    print(HfApi().whoami().get('name',''))
except: print('')
" 2>/dev/null)
if [[ -z "$HF_USER" ]]; then
    $PYTHON -c "from huggingface_hub import login; login()"
else
    info "HuggingFace : $HF_USER"
fi

# ── Select config ─────────────────────────────────────────────────────────────
if (( MEMORY_GB <= 16 )); then
    info "16GB RAM → pre-quantised 4-bit Qwen2.5-7B"
    BASE_MODEL="mlx-community/Qwen2.5-7B-Instruct-4bit"
    OUTPUT_DIR="$MODELS_DIR/qwen2.5-7b-camels-adapter"
    LORA_RANK=4
    LORA_ALPHA=8
    NUM_LAYERS=4
    BATCH_SIZE=1
    GRAD_ACCUM=16
    MAX_SEQ_LEN=512
    NUM_ITERS=400
    LR=2e-5
    SAVE_EVERY=50
    EVAL_STEPS=25
    GRAD_CHECKPOINT=true
    CACHE_THRESHOLD=2
    DISK_NEEDED=6

elif (( MEMORY_GB <= 32 )); then
    info "32GB RAM → Qwen2.5-14B"
    BASE_MODEL="Qwen/Qwen2.5-14B-Instruct"
    OUTPUT_DIR="$MODELS_DIR/qwen2.5-14b-camels-adapter"
    LORA_RANK=16
    LORA_ALPHA=32
    NUM_LAYERS=16
    BATCH_SIZE=1
    GRAD_ACCUM=16
    MAX_SEQ_LEN=3072
    NUM_ITERS=500
    LR=2e-5
    SAVE_EVERY=100
    EVAL_STEPS=50
    GRAD_CHECKPOINT=true
    CACHE_THRESHOLD=8
    DISK_NEEDED=30

else
    info "64GB+ RAM → Qwen2.5-14B full"
    BASE_MODEL="Qwen/Qwen2.5-14B-Instruct"
    OUTPUT_DIR="$MODELS_DIR/qwen2.5-14b-camels-adapter"
    LORA_RANK=16
    LORA_ALPHA=32
    NUM_LAYERS=16
    BATCH_SIZE=2
    GRAD_ACCUM=8
    MAX_SEQ_LEN=4096
    NUM_ITERS=600
    LR=2e-5
    SAVE_EVERY=100
    EVAL_STEPS=50
    GRAD_CHECKPOINT=false
    CACHE_THRESHOLD=16
    DISK_NEEDED=30
fi

# ── Find training data ────────────────────────────────────────────────────────
if [[ -f "$PROJECT_ROOT/training_data/combined_training_upgraded.jsonl" ]]; then
    SRC_TRAIN="$PROJECT_ROOT/training_data/combined_training_upgraded.jsonl"
    SRC_EVAL="$PROJECT_ROOT/training_data/combined_eval_upgraded.jsonl"
    info "Training data : upgraded (analyst-quality)"
elif [[ -f "$PROJECT_ROOT/training_data/combined_training.jsonl" ]]; then
    SRC_TRAIN="$PROJECT_ROOT/training_data/combined_training.jsonl"
    SRC_EVAL="$PROJECT_ROOT/training_data/combined_eval.jsonl"
    warn "Using template-quality pairs"
else
    error "No training data. Run: ./run.sh --reprocess"
fi
[[ -f "$SRC_EVAL" ]] || error "Eval data not found: $SRC_EVAL"

# ── Prepare MLX data — TRUNCATE content to fit MAX_SEQ_LEN ───────────────────
# Do NOT skip pairs — truncate the user/assistant content to fit.
# The model learns from truncated examples; this is standard practice.
info "Preparing MLX data (truncating to ${MAX_SEQ_LEN} tokens)..."

$PYTHON << PYEOF
import json
from pathlib import Path

MAX_SEQ_LEN  = $MAX_SEQ_LEN
# chars per token varies — use 3 as conservative estimate for mixed content
# Reserve 20% headroom for tokeniser overhead
MAX_CHARS = int(MAX_SEQ_LEN * 3 * 0.8)

# Per-role char budgets
SYSTEM_MAX    = 800           # keep system prompt intact
USER_MAX      = MAX_CHARS // 2
ASSISTANT_MAX = MAX_CHARS // 2

def truncate_msg(content, max_chars):
    if len(content) <= max_chars:
        return content
    # Truncate from the middle of user content (keep task + end)
    # Truncate from the end of assistant content (keep assessment + start)
    return content[:max_chars]

pairs_files = [
    ('$SRC_TRAIN', '$MLX_DATA_DIR/train.jsonl'),
    ('$SRC_EVAL',  '$MLX_DATA_DIR/valid.jsonl'),
]

for src, dst in pairs_files:
    written = 0
    with open(dst, 'w') as out:
        for line in open(src):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                messages = record.get('messages', [])
                truncated = []
                for msg in messages:
                    role    = msg.get('role', '')
                    content = msg.get('content', '')
                    if role == 'system':
                        content = truncate_msg(content, SYSTEM_MAX)
                    elif role == 'user':
                        content = truncate_msg(content, USER_MAX)
                    elif role == 'assistant':
                        content = truncate_msg(content, ASSISTANT_MAX)
                    truncated.append({'role': role, 'content': content})
                record['messages'] = truncated
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
                written += 1
            except Exception as e:
                pass
    print(f'  {Path(dst).name}: {written} pairs written (truncated to fit {MAX_SEQ_LEN} tokens)')
PYEOF

TRAIN_LINES=$(wc -l < "$MLX_DATA_DIR/train.jsonl")
EVAL_LINES=$(wc -l  < "$MLX_DATA_DIR/valid.jsonl")
info "Train: $TRAIN_LINES  |  Eval: $EVAL_LINES"
(( TRAIN_LINES > 0 )) || error "No training pairs. Check source data."

# ── Disk check ────────────────────────────────────────────────────────────────
AVAILABLE_GB=$(df -g "$PROJECT_ROOT" | awk 'NR==2{print $4}')
(( AVAILABLE_GB >= DISK_NEEDED )) || error "Need ~${DISK_NEEDED}GB free, only ${AVAILABLE_GB}GB."

AVAIL_MEM=$($PYTHON -c "
import subprocess
r = subprocess.run(['vm_stat'], capture_output=True, text=True)
f=i=0
for line in r.stdout.split('\n'):
    if 'Pages free'     in line:
        try: f=int(line.split(':')[1].strip().rstrip('.'))
        except: pass
    if 'Pages inactive' in line:
        try: i=int(line.split(':')[1].strip().rstrip('.'))
        except: pass
print(f'{(f+i)*16384/1073741824:.1f}')
" 2>/dev/null || echo "?")

# ── Write config YAML ─────────────────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
CONFIG_FILE="$OUTPUT_DIR/lora_config.yaml"
cat > "$CONFIG_FILE" << YAML
model: "$BASE_MODEL"
train: true
data: "$MLX_DATA_DIR"
fine_tune_type: lora
num_layers: $NUM_LAYERS
batch_size: $BATCH_SIZE
iters: $NUM_ITERS
val_batches: 5
learning_rate: $LR
steps_per_report: 10
steps_per_eval: $EVAL_STEPS
grad_accumulation_steps: $GRAD_ACCUM
adapter_path: "$OUTPUT_DIR"
save_every: $SAVE_EVERY
max_seq_length: $MAX_SEQ_LEN
seed: 42
grad_checkpoint: $GRAD_CHECKPOINT
clear_cache_threshold: $CACHE_THRESHOLD
lora_parameters:
  rank: $LORA_RANK
  alpha: $LORA_ALPHA
  dropout: 0.05
  scale: 10.0
YAML

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo " TRAINING CONFIGURATION"
echo "═══════════════════════════════════════════════════════════"
echo " Model           : $BASE_MODEL"
echo " Training pairs  : $TRAIN_LINES (truncated to $MAX_SEQ_LEN tokens)"
echo " Eval pairs      : $EVAL_LINES"
echo " LoRA rank       : $LORA_RANK  |  layers: $NUM_LAYERS"
echo " Batch           : $BATCH_SIZE × $GRAD_ACCUM = $(( BATCH_SIZE * GRAD_ACCUM )) effective"
echo " Max seq length  : $MAX_SEQ_LEN tokens"
echo " Grad checkpoint : $GRAD_CHECKPOINT"
echo " Disk free       : ${AVAILABLE_GB}GB"
echo " Mem available   : ~${AVAIL_MEM}GB"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo " ✅ Safe to interrupt — re-run resumes from last checkpoint."
echo ""

read -r -p "Proceed? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── Download model ────────────────────────────────────────────────────────────
info "Downloading model (~${DISK_NEEDED}GB if not cached)..."
$PYTHON -c "
from huggingface_hub import snapshot_download
path = snapshot_download('$BASE_MODEL', ignore_patterns=['*.bin','*.pt'])
print(f'Model ready: {path}')
" || error "Model download failed."

# ── Train ─────────────────────────────────────────────────────────────────────
LOG_FILE="$LOGS_DIR/training_$(date +%Y%m%d_%H%M%S).log"
info "Training started — log: $LOG_FILE"
echo ""

$PYTHON -m mlx_lm lora --config "$CONFIG_FILE" 2>&1 | tee "$LOG_FILE"
TRAIN_STATUS=${PIPESTATUS[0]}

if [[ $TRAIN_STATUS -ne 0 ]]; then
    if grep -q "OutOfMemory\|Insufficient Memory\|kIOGPU" "$LOG_FILE" 2>/dev/null; then
        echo ""
        echo "═══════════════════════════════════════════════════════════"
        echo " STILL OUT OF MEMORY — Last resort options:"
        echo "  1. Restart Mac completely, close everything, run immediately"
        echo "  2. sudo purge && ./train_mlx.sh"
        echo "  3. Edit train_mlx.sh: change NUM_LAYERS=2 and LORA_RANK=2"
        echo "═══════════════════════════════════════════════════════════"
    fi
    error "Training failed — check $LOG_FILE"
fi

info "Training complete ✅"

# ── Fuse ──────────────────────────────────────────────────────────────────────
MODEL_SLUG=$(echo "$BASE_MODEL" | sed 's|.*/||' | tr '[:upper:]' '[:lower:]')
FUSED_DIR="$MODELS_DIR/${MODEL_SLUG}-camels-fused"
mkdir -p "$FUSED_DIR"
info "Fusing adapter..."

$PYTHON -m mlx_lm fuse \
    --model "$BASE_MODEL" \
    --adapter-path "$OUTPUT_DIR" \
    --save-path "$FUSED_DIR" \
    --de-quantize

info "Fused: $FUSED_DIR"

# ── 4-bit quantise ────────────────────────────────────────────────────────────
QUANT_DIR="$MODELS_DIR/${MODEL_SLUG}-camels-4bit"
info "Quantising to 4-bit..."

$PYTHON -m mlx_lm convert \
    --hf-path "$FUSED_DIR" \
    --mlx-path "$QUANT_DIR" \
    -q --q-bits 4

info "4-bit: $QUANT_DIR"

# ── Modelfile ─────────────────────────────────────────────────────────────────
PARAM_SIZE=$(echo "$BASE_MODEL" | grep -oE '[0-9]+B' | head -1 | tr '[:upper:]' '[:lower:]')
OLLAMA_NAME="camels-analyst-${PARAM_SIZE:-7b}"

cat > "$PROJECT_ROOT/Modelfile" << MODELEOF
FROM $QUANT_DIR

SYSTEM """You are a senior credit analyst specialising in bank credit analysis \
using the CAMELS framework. You follow Moody's, S&P Global Ratings, and Fitch \
Ratings methodologies. Every numerical claim must include a source citation \
[Source: p.XX]. If data is unavailable write 'Data not available' — never \
fabricate figures. Structure every response: Assessment (Strong/Adequate/Weak/\
Critical), Key Metrics, Analysis, Peer Context, Key Risks, Rating Agency Commentary."""

PARAMETER temperature 0.05
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 4096
PARAMETER num_predict 2048
MODELEOF

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " ALL DONE"
echo "═══════════════════════════════════════════════════════════"
echo " Adapter  : $OUTPUT_DIR"
echo " Fused    : $FUSED_DIR"
echo " 4-bit    : $QUANT_DIR"
echo " Log      : $LOG_FILE"
echo ""
echo " Deploy:"
echo "   ollama create $OLLAMA_NAME -f ./Modelfile"
echo "   ollama serve"
echo "   python main.py --pdf financials/lloyds_2025.pdf --bank 'Lloyds Banking Group'"
echo "═══════════════════════════════════════════════════════════"
