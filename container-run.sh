#!/bin/bash
# ArcaneaClaw Container Runner
# Auto-detects: Podman (preferred) -> Docker -> Native Python fallback
# Usage: bash container-run.sh [start|stop|status|logs|build|shell]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="arcanea-claw"
CONTAINER_NAME="arcanea-claw"

# ---------------------------------------------------------------------------
# Detect container engine
# ---------------------------------------------------------------------------
detect_engine() {
    if command -v podman &>/dev/null; then
        ENGINE="podman"
        COMPOSE="podman-compose"
        COMPOSE_FILE="podman-compose.yml"
        echo "[claw] Engine: Podman (rootless, daemonless)"
    elif command -v docker &>/dev/null; then
        ENGINE="docker"
        COMPOSE="docker compose"
        COMPOSE_FILE="docker-compose.yml"
        echo "[claw] Engine: Docker"
    else
        ENGINE="native"
        echo "[claw] Engine: Native Python (no container runtime found)"
    fi
}

# ---------------------------------------------------------------------------
# Ensure staging/processed dirs exist on Linux FS
# ---------------------------------------------------------------------------
ensure_dirs() {
    mkdir -p /home/frankx/arcanea-claw/staging
    mkdir -p /home/frankx/arcanea-claw/processed
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_build() {
    if [ "$ENGINE" = "native" ]; then
        echo "[claw] Native mode — nothing to build. Install deps with:"
        echo "  pip install -r requirements.txt && npm install --production"
        return
    fi

    echo "[claw] Building $IMAGE_NAME with $ENGINE ..."
    if [ "$ENGINE" = "podman" ]; then
        $ENGINE build -t "$IMAGE_NAME" -f "$SCRIPT_DIR/Containerfile" "$SCRIPT_DIR"
    else
        $ENGINE build -t "$IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"
    fi
    echo "[claw] Build complete."
}

cmd_start() {
    ensure_dirs

    if [ "$ENGINE" = "native" ]; then
        echo "[claw] Starting in native Python mode ..."
        cd "$SCRIPT_DIR"
        if [ -f run.sh ]; then
            bash run.sh
        else
            ARCANEA_CLAW_CONFIG="$SCRIPT_DIR/config.yaml" python engine/daemon.py
        fi
        return
    fi

    echo "[claw] Starting $CONTAINER_NAME with $ENGINE ..."
    if [ "$ENGINE" = "podman" ]; then
        cd "$SCRIPT_DIR" && podman-compose -f "$COMPOSE_FILE" up -d
    else
        cd "$SCRIPT_DIR" && $COMPOSE -f "$COMPOSE_FILE" up -d
    fi
    echo "[claw] Container started. Check: $0 status"
}

cmd_stop() {
    if [ "$ENGINE" = "native" ]; then
        echo "[claw] Native mode — killing Python processes ..."
        pkill -f "engine/daemon.py" 2>/dev/null || echo "[claw] No daemon running."
        return
    fi

    echo "[claw] Stopping $CONTAINER_NAME ..."
    if [ "$ENGINE" = "podman" ]; then
        cd "$SCRIPT_DIR" && podman-compose -f "$COMPOSE_FILE" down
    else
        cd "$SCRIPT_DIR" && $COMPOSE -f "$COMPOSE_FILE" down
    fi
    echo "[claw] Stopped."
}

cmd_status() {
    if [ "$ENGINE" = "native" ]; then
        if pgrep -f "engine/daemon.py" >/dev/null 2>&1; then
            echo "[claw] Daemon running (native, PID $(pgrep -f 'engine/daemon.py'))"
        else
            echo "[claw] Daemon not running."
        fi
        return
    fi

    echo "[claw] Container status ($ENGINE):"
    $ENGINE ps -a --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

cmd_logs() {
    if [ "$ENGINE" = "native" ]; then
        echo "[claw] Native mode — check stdout or journalctl."
        return
    fi

    echo "[claw] Logs for $CONTAINER_NAME ($ENGINE):"
    $ENGINE logs -f "$CONTAINER_NAME"
}

cmd_shell() {
    if [ "$ENGINE" = "native" ]; then
        echo "[claw] Native mode — you are already on the host. cd $SCRIPT_DIR"
        return
    fi

    echo "[claw] Opening shell in $CONTAINER_NAME ($ENGINE) ..."
    $ENGINE exec -it "$CONTAINER_NAME" /bin/bash
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
detect_engine

case "${1:-help}" in
    build)  cmd_build  ;;
    start)  cmd_start  ;;
    stop)   cmd_stop   ;;
    status) cmd_status ;;
    logs)   cmd_logs   ;;
    shell)  cmd_shell  ;;
    *)
        echo "Usage: $0 {build|start|stop|status|logs|shell}"
        echo ""
        echo "  build   Build the container image"
        echo "  start   Start ArcaneaClaw (auto-detects engine)"
        echo "  stop    Stop ArcaneaClaw"
        echo "  status  Show container/process status"
        echo "  logs    Tail container logs"
        echo "  shell   Open a shell inside the container"
        echo ""
        echo "Engine priority: Podman > Docker > Native Python"
        ;;
esac
