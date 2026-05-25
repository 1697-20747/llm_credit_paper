#!/usr/bin/env python3
"""
train_unsloth.py
================
QLoRA fine-tuning for Linux + NVIDIA GPU using Unsloth.
Use this instead of train_mlx.sh on non-Mac systems.

Unsloth provides faster training with lower VRAM via custom CUDA kernels
and 4-bit quantisation. Typically 2-5x faster than standard HuggingFace
training with the same GPU.

Prerequisites:
    pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    pip install --no-deps trl peft accelerate bitsandbytes datasets

Hardware:
    Minimum : NVIDIA GPU with 16GB VRAM (RTX 3090, RTX 4080, A100 40GB)
    Recommended : 24GB+ VRAM (RTX 3090/4090, A100 80GB)

    VRAM < 20GB  → uses Qwen2.5-7B-Instruct
    VRAM >= 20GB → uses Qwen2.5-14B-Instruct

Usage:
    python train_unsloth.py
    python train_unsloth.py --model 7b     # force 7B regardless of VRAM
    python train_unsloth.py --model 14b    # force 14B
    python train_unsloth.py --dry-run      # validate setup without training

Cloud platforms (if no local GPU):
    Google Colab Pro  (~$10/month, A100 access)
    RunPod            (~$0.50/hr, H100 available)
    Lambda Labs       (~$0.60/hr)
    Modal             (pay per second)
"""

import os
import sys
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TRAINING_DIR = PROJECT_ROOT / "training_data"
MODELS_DIR   = PROJECT_ROOT / "models"
LOGS_DIR     = PROJECT_ROOT / "logs"
MODELS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

GREEN  = '\033[0;32m'; YELLOW = '\033[1;33m'; RED = '\033[0;31m'; NC = '\033[0m'
def info(msg):  print(f"{GREEN}[INFO]{NC}  {msg}", flush=True)
def warn(msg):  print(f"{YELLOW}[WARN]{NC}  {msg}", flush=True)
def error(msg): print(f"{RED}[ERROR]{NC} {msg}", flush=True); sys.exit(1)


def check_dependencies():
    """Check all required packages are installed."""
    missing = []
    for pkg in ["unsloth", "trl", "peft", "accelerate", "bitsandbytes", "datasets", "torch"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        error(
            f"Missing packages: {', '.join(missing)}\n"
            "Install with:\n"
            "  pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'\n"
            "  pip install --no-deps trl peft accelerate bitsandbytes datasets"
        )


def detect_vram() -> float:
    """Return available VRAM in GB."""
    try:
        import torch
        if not torch.cuda.is_available():
            error("No CUDA GPU detected. Use train_mlx.sh for Apple Silicon Mac.")
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        gpu_name = torch.cuda.get_device_properties(0).name
        info(f"GPU: {gpu_name} ({vram:.1f}GB VRAM)")
        return vram
    except Exception as e:
        error(f"CUDA error: {e}")


def select_model(force_model: str, vram_gb: float) -> tuple[str, dict]:
    """Select model and hyperparameters based on VRAM."""
    if force_model == "14b" or (force_model is None and vram_gb >= 20):
        model_name = "Qwen/Qwen2.5-14B-Instruct"
        hparams = {
            "max_seq_length":   3072,
            "lora_rank":        16,
            "lora_alpha":       32,
            "lora_layers":      16,
            "batch_size":       2,
            "grad_accum":       8,
            "num_epochs":       3,
            "learning_rate":    2e-5,
            "warmup_steps":     25,
        }
        info(f"Selected: Qwen2.5-14B (VRAM: {vram_gb:.1f}GB)")
    else:
        model_name = "Qwen/Qwen2.5-7B-Instruct"
        hparams = {
            "max_seq_length":   2048,
            "lora_rank":        8,
            "lora_alpha":       16,
            "lora_layers":      8,
            "batch_size":       2,
            "grad_accum":       8,
            "num_epochs":       3,
            "learning_rate":    2e-5,
            "warmup_steps":     20,
        }
        info(f"Selected: Qwen2.5-7B (VRAM: {vram_gb:.1f}GB < 20GB threshold)")

    return model_name, hparams


def get_training_data() -> tuple[Path, Path]:
    """Find training data — prefer upgraded pairs."""
    if (TRAINING_DIR / "combined_training_upgraded.jsonl").exists():
        train = TRAINING_DIR / "combined_training_upgraded.jsonl"
        eval_ = TRAINING_DIR / "combined_eval_upgraded.jsonl"
        info("Using upgraded training data (analyst-quality pairs)")
    elif (TRAINING_DIR / "combined_training.jsonl").exists():
        train = TRAINING_DIR / "combined_training.jsonl"
        eval_ = TRAINING_DIR / "combined_eval.jsonl"
        warn("Upgraded pairs not found — using template pairs")
        warn("Run scripts/05_upgrade_training_pairs.py for better results")
    else:
        error("No training data found. Run ./run.sh --reprocess first.")
    return train, eval_


def format_messages_for_training(example: dict) -> dict:
    """
    Convert messages format to text format for SFTTrainer.
    Applies Qwen2.5 chat template.
    """
    messages = example.get("messages", [])
    text = ""
    for msg in messages:
        role    = msg["role"]
        content = msg["content"]
        if role == "system":
            text += f"<|im_start|>system\n{content}<|im_end|>\n"
        elif role == "user":
            text += f"<|im_start|>user\n{content}<|im_end|>\n"
        elif role == "assistant":
            text += f"<|im_start|>assistant\n{content}<|im_end|>\n"
    return {"text": text}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",   choices=["7b", "14b"], default=None,
                        help="Force model size (default: auto-detect from VRAM)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate setup without training")
    args = parser.parse_args()

    info("=== CAMELS Credit Analyst — Unsloth QLoRA Training (Linux/CUDA) ===")

    check_dependencies()

    import torch
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import load_dataset

    vram_gb          = detect_vram()
    model_name, hp   = select_model(args.model, vram_gb)
    train_path, eval_path = get_training_data()

    train_lines = sum(1 for _ in open(train_path))
    eval_lines  = sum(1 for _ in open(eval_path))
    output_dir  = MODELS_DIR / f"camels-adapter-{model_name.split('/')[-1].lower()}"

    print(f"\n{'='*60}")
    print(f" TRAINING CONFIGURATION")
    print(f"{'='*60}")
    print(f"  Model           : {model_name}")
    print(f"  Training pairs  : {train_lines}")
    print(f"  Eval pairs      : {eval_lines}")
    print(f"  Max seq length  : {hp['max_seq_length']}")
    print(f"  LoRA rank       : {hp['lora_rank']}")
    print(f"  Batch size      : {hp['batch_size']} × {hp['grad_accum']} accum = {hp['batch_size'] * hp['grad_accum']} effective")
    print(f"  Epochs          : {hp['num_epochs']}")
    print(f"  Learning rate   : {hp['learning_rate']}")
    print(f"  Output dir      : {output_dir}")
    print(f"{'='*60}\n")

    if args.dry_run:
        info("Dry run complete — setup looks good. Run without --dry-run to train.")
        return

    confirm = input("Proceed? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # ── Load model ────────────────────────────────────────────────────────────
    info("Loading model (downloads if not cached)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=hp["max_seq_length"],
        dtype=None,
        load_in_4bit=True,
    )

    # ── Apply LoRA ────────────────────────────────────────────────────────────
    info("Applying LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=hp["lora_rank"],
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=hp["lora_alpha"],
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        max_seq_length=hp["max_seq_length"],
    )

    # ── Load and format dataset ───────────────────────────────────────────────
    info("Loading training data...")
    dataset = load_dataset(
        "json",
        data_files={
            "train": str(train_path),
            "test":  str(eval_path),
        }
    )
    dataset = dataset.map(format_messages_for_training)

    # ── Training arguments ────────────────────────────────────────────────────
    training_args = TrainingArguments(
        per_device_train_batch_size=hp["batch_size"],
        gradient_accumulation_steps=hp["grad_accum"],
        warmup_steps=hp["warmup_steps"],
        num_train_epochs=hp["num_epochs"],
        learning_rate=hp["learning_rate"],
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_steps=100,
        save_total_limit=3,
        output_dir=str(output_dir),
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="none",
        seed=42,
    )

    # ── Trainer ───────────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["test"],
        dataset_text_field="text",
        max_seq_length=hp["max_seq_length"],
        dataset_num_proc=2,
        args=training_args,
    )

    # ── Train ─────────────────────────────────────────────────────────────────
    info("Starting training...")
    trainer_stats = trainer.train()
    info(f"Training complete. Steps: {trainer_stats.global_step}")

    # ── Save ──────────────────────────────────────────────────────────────────
    lora_path = MODELS_DIR / "camels-analyst-lora"
    model.save_pretrained(str(lora_path))
    tokenizer.save_pretrained(str(lora_path))
    info(f"LoRA adapter saved: {lora_path}")

    # ── Merge and save ────────────────────────────────────────────────────────
    info("Merging adapter into base model...")
    model.save_pretrained_merged(
        str(MODELS_DIR / "camels-analyst-merged"),
        tokenizer,
        save_method="merged_16bit",
    )
    info(f"Merged model saved: {MODELS_DIR / 'camels-analyst-merged'}")

    # ── Save GGUF for Ollama ──────────────────────────────────────────────────
    info("Saving GGUF (Q4_K_M) for Ollama...")
    model.save_pretrained_gguf(
        str(MODELS_DIR / "camels-analyst-gguf"),
        tokenizer,
        quantization_method="q4_k_m",
    )

    gguf_files = list((MODELS_DIR / "camels-analyst-gguf").glob("*.gguf"))
    if gguf_files:
        gguf_path = gguf_files[0]
        info(f"GGUF saved: {gguf_path}")
        print(f"\nDeploy with Ollama:")
        print(f"  ollama create camels-analyst -f ./Modelfile")
        print(f"  ollama serve")
    else:
        warn("GGUF not found — check models/camels-analyst-gguf/")

    print(f"\n{'='*60}")
    print(f" TRAINING COMPLETE")
    print(f"{'='*60}")
    print(f"  LoRA adapter : {lora_path}")
    print(f"  Merged model : {MODELS_DIR / 'camels-analyst-merged'}")
    print(f"  GGUF (Ollama): {MODELS_DIR / 'camels-analyst-gguf'}")
    print(f"\n  Run analysis:")
    print(f"  python main.py --pdf financials/lloyds_2025.pdf \\")
    print(f"                 --bank 'Lloyds Banking Group'")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
