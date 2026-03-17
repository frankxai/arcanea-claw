#!/bin/bash
# Install Podman on WSL2 Ubuntu — rootless containers, no daemon
# This script needs sudo for installation, but after that podman runs rootless.
# Usage: bash install-podman.sh
set -euo pipefail

echo "==========================================="
echo " ArcaneaClaw — Podman Installer for WSL2"
echo "==========================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Check OS
# ---------------------------------------------------------------------------
if ! grep -qi 'ubuntu\|debian' /etc/os-release 2>/dev/null; then
    echo "[error] This script targets Ubuntu/Debian on WSL2."
    echo "        For other distros, see: https://podman.io/docs/installation"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Install Podman + podman-compose
# ---------------------------------------------------------------------------
echo "[1/5] Installing Podman and podman-compose ..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    podman \
    slirp4netns \
    uidmap \
    fuse-overlayfs

# podman-compose (pip-based, the maintained version)
if ! command -v podman-compose &>/dev/null; then
    echo "[1/5] Installing podman-compose via pip ..."
    pip install --user podman-compose 2>/dev/null \
        || pip3 install --user podman-compose 2>/dev/null \
        || sudo pip3 install podman-compose
fi

# ---------------------------------------------------------------------------
# 3. Configure rootless runtime
# ---------------------------------------------------------------------------
echo "[2/5] Configuring rootless container runtime ..."

# Ensure subuid/subgid ranges exist for current user
if ! grep -q "^$(whoami):" /etc/subuid 2>/dev/null; then
    echo "[2/5] Adding subuid/subgid ranges for $(whoami) ..."
    sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$(whoami)"
fi

# Create storage config for rootless
mkdir -p "$HOME/.config/containers"
if [ ! -f "$HOME/.config/containers/storage.conf" ]; then
    cat > "$HOME/.config/containers/storage.conf" << 'STORAGEEOF'
[storage]
driver = "overlay"

[storage.options.overlay]
mount_program = "/usr/bin/fuse-overlayfs"
STORAGEEOF
    echo "[2/5] Created ~/.config/containers/storage.conf"
fi

# Create registries config (pull from Docker Hub by default)
if [ ! -f "$HOME/.config/containers/registries.conf" ]; then
    cat > "$HOME/.config/containers/registries.conf" << 'REGEOF'
[registries.search]
registries = ['docker.io', 'quay.io', 'ghcr.io']

[registries.insecure]
registries = []
REGEOF
    echo "[2/5] Created ~/.config/containers/registries.conf"
fi

# ---------------------------------------------------------------------------
# 4. Verify installation
# ---------------------------------------------------------------------------
echo "[3/5] Verifying Podman installation ..."
echo ""
podman --version
echo ""

echo "[4/5] Running hello-world test (rootless, no sudo) ..."
if podman run --rm docker.io/library/hello-world 2>/dev/null; then
    echo ""
    echo "[4/5] Podman rootless test PASSED."
else
    echo ""
    echo "[4/5] hello-world failed — this may be a network issue."
    echo "       Podman itself is installed. Try: podman info"
fi

# ---------------------------------------------------------------------------
# 5. Create staging dirs for ArcaneaClaw
# ---------------------------------------------------------------------------
echo "[5/5] Creating ArcaneaClaw data directories ..."
mkdir -p /home/frankx/arcanea-claw/staging
mkdir -p /home/frankx/arcanea-claw/processed

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "==========================================="
echo " Podman installed. No daemon needed."
echo "==========================================="
echo ""
echo "Next steps:"
echo "  cd /mnt/c/Users/frank/Arcanea/arcanea-claw"
echo "  bash container-run.sh build"
echo "  bash container-run.sh start"
echo ""
echo "Useful commands:"
echo "  podman ps                    # list running containers"
echo "  podman images                # list images"
echo "  podman system prune -a       # reclaim disk space"
echo "  podman-compose --help        # compose commands"
