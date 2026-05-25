#!/usr/bin/env python3
"""
check_mlx_api.py — prints the correct mlx-lm training command for your version
Run: .venv/bin/python check_mlx_api.py
"""
import subprocess, sys

python = sys.executable

# Get mlx-lm version
result = subprocess.run(
    [python, "-c", "import mlx_lm; print(mlx_lm.__version__)"],
    capture_output=True, text=True
)
version = result.stdout.strip()
print(f"mlx-lm version: {version}")

# Get full help to see what args are available
result = subprocess.run(
    [python, "-m", "mlx_lm", "lora", "--help"],
    capture_output=True, text=True
)
help_text = result.stdout + result.stderr

# Check which args exist
has_num_layers   = "--num-layers" in help_text
has_lora_layers  = "--lora-layers" in help_text
has_train_file   = "--train-file" in help_text
has_lora_rank    = "--lora-rank" in help_text
has_grad_accum   = "--grad-accumulation" in help_text

print(f"--num-layers      : {'YES' if has_num_layers else 'NO'}")
print(f"--lora-layers     : {'YES' if has_lora_layers else 'NO'}")
print(f"--train-file      : {'YES' if has_train_file else 'NO'}")
print(f"--lora-rank       : {'YES' if has_lora_rank else 'NO'}")
print(f"--grad-accum      : {'YES' if has_grad_accum else 'NO'}")
print()

# Print the correct base command
print("Correct invocation:")
if has_num_layers:
    print("  python -m mlx_lm lora  (new style)")
    print("  Use: --num-layers  (not --lora-layers)")
else:
    print("  python -m mlx_lm.lora  (old style)")
    print("  Use: --lora-layers")

print()
print("Full help output saved to: logs/mlx_help.txt")
with open("logs/mlx_help.txt", "w") as f:
    f.write(help_text)
