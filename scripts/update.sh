#!/usr/bin/env bash
# Fast in-place update: pull the latest code and make sure the model + plugin
# are present. No sudo, no re-download of PyTorch — just the new bits.
set -euo pipefail
cd "$(dirname "$0")/.."

WEIGHTS_URL="https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3.pth"
WEIGHTS_URL_BEST="https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50.pth"
DFPLUGIN_URL="https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/libdeep_filter_ladspa-0.5.6-x86_64-unknown-linux-gnu.so"

echo "Updating NVBroadcast…"
git fetch -q origin master
git reset -q --hard origin/master
mkdir -p models/weights audio/lib

[[ -s models/weights/rvm_mobilenetv3.pth ]] || \
  curl -fL --progress-bar -o models/weights/rvm_mobilenetv3.pth "$WEIGHTS_URL" || true
[[ -s models/weights/rvm_resnet50.pth ]] || \
  curl -fL --progress-bar -o models/weights/rvm_resnet50.pth "$WEIGHTS_URL_BEST" || true
[[ -s audio/lib/libdeep_filter_ladspa.so ]] || \
  curl -fL --progress-bar -o audio/lib/libdeep_filter_ladspa.so "$DFPLUGIN_URL" || true

echo "✓ Updated to $(git rev-parse --short HEAD). Relaunch NVBroadcast."
