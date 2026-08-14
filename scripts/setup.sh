#!/usr/bin/env bash
# One-shot environment setup for nvidiabroadcast-linux.
# Creates the venv and installs GPU torch (CUDA 12.8 / sm_120 for Blackwell)
# plus the video deps. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
    echo "[setup] creating venv"
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip

echo "[setup] installing torch/torchvision (cu128)"
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

echo "[setup] installing video deps"
.venv/bin/pip install numpy opencv-python pyvirtualcam

echo "[setup] verifying GPU"
.venv/bin/python - <<'PY'
import torch
print("torch", torch.__version__, "| cuda", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
    print("capability sm_%d%d" % torch.cuda.get_device_capability(0))
PY
echo "[setup] done"
