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
