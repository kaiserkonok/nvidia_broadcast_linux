#!/usr/bin/env bash
# NVBroadcast for Linux — one-command installer.
#
#   curl -fsSL https://raw.githubusercontent.com/kaiserkonok/nvidia_broadcast_linux/master/install.sh | bash
#
# Installs system deps, clones the app, builds the Python env, downloads the
# model, configures the virtual camera, and adds "NVBroadcast" to your app menu.
set -euo pipefail

REPO_URL="${NVB_REPO:-https://github.com/kaiserkonok/nvidia_broadcast_linux.git}"
BRANCH="${NVB_BRANCH:-master}"
INSTALL_DIR="${NVB_HOME:-$HOME/.local/share/nvbroadcast}"
BIN_DIR="$HOME/.local/bin"
RAW_INSTALL="https://raw.githubusercontent.com/kaiserkonok/nvidia_broadcast_linux/${BRANCH}/install.sh"
WEIGHTS_URL="https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3.pth"

# ---- pretty output ----------------------------------------------------------
if [[ -t 1 ]]; then
  B=$'\e[1m'; DIM=$'\e[2m'; G=$'\e[32m'; C=$'\e[36m'; Y=$'\e[33m'; R=$'\e[31m'; X=$'\e[0m'
else B=""; DIM=""; G=""; C=""; Y=""; R=""; X=""; fi
say()  { printf "%s\n" "$*"; }
step() { printf "${C}${B}▸${X} %s\n" "$*"; }
ok()   { printf "  ${G}✓${X} %s\n" "$*"; }
warn() { printf "  ${Y}!${X} %s\n" "$*"; }
die()  { printf "\n${R}${B}✗ %s${X}\n" "$*" >&2; exit 1; }

banner() {
  printf "\n${C}${B}"
  cat <<'ART'
   ┳┓┓ ┏┳┓  ┓                    ┓
   ┃┃┃┃┃┣┫┏┓┏┓┏┓╋┏┓┏┓┏╋  ┏┓┏┓  ┃ ┓┏┓┓┏┓
   ┛┗┗┛┗┻┗┛┛┗┗┗┻┗┗┗┻┛┗ ┛ ┗┛┛   ┗┛┗┛┗┗┻┛┗
ART
  printf "${X}${DIM}   real-time, real-looking virtual camera for Linux${X}\n\n"
}

# ---- checks -----------------------------------------------------------------
banner
[[ "$(uname -s)" == "Linux" ]] || die "NVBroadcast is Linux-only."
command -v apt-get >/dev/null 2>&1 || die "This installer supports Debian/Ubuntu (apt). For other distros, see the README."

step "Checking your system"
if command -v nvidia-smi >/dev/null 2>&1; then
  ok "NVIDIA GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
else
  warn "No NVIDIA GPU detected — NVBroadcast is built for RTX cards; it may be slow without one."
fi

# ---- admin access (ask once, up front) --------------------------------------
step "Administrator access"
say "  ${DIM}NVBroadcast needs your password to install system packages and set up the camera.${X}"
sudo -v || die "sudo is required to install NVBroadcast."
# keep the sudo timestamp fresh through the long downloads (so it won't re-ask)
( while kill -0 "$$" 2>/dev/null; do sudo -n true 2>/dev/null; sleep 50; done ) &
SUDO_KEEPALIVE=$!
trap 'kill "$SUDO_KEEPALIVE" 2>/dev/null || true' EXIT
ok "Authorized"

# ---- system dependencies ----------------------------------------------------
step "Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y \
  git python3 python3-venv python3-pip \
  v4l2loopback-dkms v4l-utils \
  libxcb-cursor0 libxkbcommon0 \
  || die "Package installation failed."
ok "System packages ready"

# ---- fetch the app ----------------------------------------------------------
step "Fetching NVBroadcast"
mkdir -p "$INSTALL_DIR" "$BIN_DIR"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" fetch -q origin "$BRANCH"
  git -C "$INSTALL_DIR" reset -q --hard "origin/$BRANCH"
  ok "Updated $INSTALL_DIR"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  ok "Cloned to $INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# ---- python environment -----------------------------------------------------
step "Building the Python environment"
say "  ${DIM}This downloads PyTorch + CUDA (~3 GB). The progress bars below are live —${X}"
say "  ${DIM}it's working even when a download sits at one line for a while.${X}"
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade -q pip
./.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
./.venv/bin/pip install numpy opencv-python pyvirtualcam PySide6 flask
ok "Python environment ready"

# ---- model ------------------------------------------------------------------
step "Downloading the matting model (15 MB)"
mkdir -p models/weights
if [[ ! -s models/weights/rvm_mobilenetv3.pth ]]; then
  curl -fL --progress-bar -o models/weights/rvm_mobilenetv3.pth "$WEIGHTS_URL" || die "Model download failed."
fi
ok "Model ready"

# ---- virtual camera ---------------------------------------------------------
step "Configuring the virtual camera (needs sudo)"
sudo bash scripts/camera_reload.sh 10 "Broadcast Virtual Camera" || warn "Camera config will be retried on first launch."
ok "Virtual camera configured"

# ---- launcher + menu entry --------------------------------------------------
step "Installing launcher and menu entry"
cat > "$BIN_DIR/nvbroadcast" <<EOF
#!/usr/bin/env bash
DIR="$INSTALL_DIR"
case "\${1:-}" in
  uninstall) exec "\$DIR/scripts/uninstall.sh" "\${@:2}" ;;
  update)    curl -fsSL "$RAW_INSTALL" | bash ;;
  *)         exec "\$DIR/scripts/run_app.sh" "\$@" ;;
esac
EOF
chmod +x "$BIN_DIR/nvbroadcast"
./scripts/install_desktop.sh >/dev/null
ok "Installed 'nvbroadcast' command and menu entry"

# ---- done -------------------------------------------------------------------
printf "\n${G}${B}✓ NVBroadcast is installed.${X}\n\n"
say "  ${B}Launch it:${X}   open ${C}NVBroadcast${X} from your apps  ${DIM}(or run ${C}nvbroadcast${X}${DIM})${X}"
say "  ${B}In apps:${X}     pick ${C}“Broadcast Virtual Camera”${X} in OBS / Zoom / Meet / Discord"
say "  ${B}Uninstall:${X}   ${C}nvbroadcast uninstall${X}"
if ! printf '%s' ":$PATH:" | grep -q ":$BIN_DIR:"; then
  printf "\n  ${Y}Note:${X} add ${C}%s${X} to your PATH to use the ${C}nvbroadcast${X} command.\n" "$BIN_DIR"
fi
printf "\n"
