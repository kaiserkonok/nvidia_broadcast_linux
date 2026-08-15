#!/usr/bin/env bash
# Fast in-place update: pull latest code, then make sure models, the mic plugin,
# and Python deps are present. No sudo, no PyTorch re-download.
set -euo pipefail
cd "$(dirname "$0")/.."

WEIGHTS_URL="https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3.pth"
WEIGHTS_URL_BEST="https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50.pth"
DFPLUGIN_URL="https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/libdeep_filter_ladspa-0.5.6-x86_64-unknown-linux-gnu.so"
FACEMESH_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

echo "Updating NVBroadcast…"
git fetch -q origin master
OLD=$(git rev-parse HEAD 2>/dev/null || echo none)
git reset -q --hard origin/master
NEW=$(git rev-parse HEAD)

# If this script itself changed, re-run the freshly-pulled version once so the
# newest asset/dep logic applies (self-update). Guard against an infinite loop.
if [[ "$OLD" != "$NEW" && "${NVB_REEXEC:-0}" != "1" ]]; then
    exec env NVB_REEXEC=1 bash scripts/update.sh
fi

mkdir -p models/weights audio/lib
[[ -s models/weights/rvm_mobilenetv3.pth ]] || \
  curl -fL --progress-bar -o models/weights/rvm_mobilenetv3.pth "$WEIGHTS_URL" || true
[[ -s models/weights/rvm_resnet50.pth ]] || \
  curl -fL --progress-bar -o models/weights/rvm_resnet50.pth "$WEIGHTS_URL_BEST" || true
[[ -s audio/lib/libdeep_filter_ladspa.so ]] || \
  curl -fL --progress-bar -o audio/lib/libdeep_filter_ladspa.so "$DFPLUGIN_URL" || true
[[ -s models/weights/face_landmarker.task ]] || \
  curl -fL --progress-bar -o models/weights/face_landmarker.task "$FACEMESH_URL" || true

# Sync Python deps (cached -> fast; picks up anything new like Ultra / Eye Contact).
if [[ -x .venv/bin/pip ]]; then
    echo "Checking Python deps…"
    ./.venv/bin/pip install -q numpy opencv-python pyvirtualcam PySide6 flask \
        transformers timm einops kornia mediapipe 2>/dev/null || true
fi

echo "✓ Updated to $(git rev-parse --short HEAD). Relaunch NVBroadcast."
