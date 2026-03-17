#!/bin/bash
set -euo pipefail

# ArcaneaClaw Universal Installer
# Detects: OpenClaw, NanoClaw, Claude Code, or standalone
# Usage: curl -fsSL https://arcanea.ai/claw/install | bash
#    or: ./install.sh

CLAW_VERSION="0.1.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors (if terminal supports them)
if [ -t 1 ]; then
  BOLD="\033[1m"
  DIM="\033[2m"
  CYAN="\033[36m"
  GREEN="\033[32m"
  YELLOW="\033[33m"
  RED="\033[31m"
  RESET="\033[0m"
else
  BOLD="" DIM="" CYAN="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()  { echo -e "${CYAN}[claw]${RESET} $*"; }
ok()    { echo -e "${GREEN}[  ok]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[warn]${RESET} $*"; }
fail()  { echo -e "${RED}[fail]${RESET} $*"; exit 1; }

echo ""
echo -e "${BOLD}ArcaneaClaw Installer v${CLAW_VERSION}${RESET}"
echo -e "${DIM}AI-powered media processing pipeline${RESET}"
echo "============================================"
echo ""

# -----------------------------------------------------------------------
# Prerequisite checks
# -----------------------------------------------------------------------

check_command() {
  if command -v "$1" &>/dev/null; then
    ok "$1 found: $(command -v "$1")"
    return 0
  else
    warn "$1 not found"
    return 1
  fi
}

info "Checking prerequisites..."

NODE_OK=false
PYTHON_OK=false

if check_command node; then
  NODE_VERSION=$(node -v 2>/dev/null | sed 's/v//')
  NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
  if [ "$NODE_MAJOR" -ge 18 ]; then
    ok "Node.js $NODE_VERSION (>= 18 required)"
    NODE_OK=true
  else
    warn "Node.js $NODE_VERSION is too old (>= 18 required)"
  fi
fi

if check_command python3; then
  PY_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}')
  PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
    ok "Python $PY_VERSION (>= 3.11 required)"
    PYTHON_OK=true
  else
    warn "Python $PY_VERSION found (>= 3.11 recommended for full pipeline)"
  fi
fi

if [ "$NODE_OK" = false ]; then
  fail "Node.js >= 18 is required. Install from https://nodejs.org"
fi

echo ""

# -----------------------------------------------------------------------
# Detect environment
# -----------------------------------------------------------------------

INSTALL_MODE="standalone"

# Check for OpenClaw
if [ -d "$HOME/.openclaw" ] || command -v openclaw &>/dev/null; then
  INSTALL_MODE="openclaw"
# Check for NanoClaw
elif [ -d "$HOME/.nanoclaw" ] || command -v nanoclaw &>/dev/null; then
  INSTALL_MODE="nanoclaw"
# Check for Claude Code
elif [ -f "$HOME/.claude.json" ] || [ -f ".mcp.json" ]; then
  INSTALL_MODE="claude-code"
fi

info "Detected environment: ${BOLD}${INSTALL_MODE}${RESET}"
echo ""

# -----------------------------------------------------------------------
# Install dependencies
# -----------------------------------------------------------------------

info "Installing Node.js dependencies..."
cd "$SCRIPT_DIR"
npm install --silent 2>/dev/null && ok "Root dependencies installed" || warn "Root npm install had warnings"

info "Building MCP server..."
cd "$SCRIPT_DIR/mcp-server"
npm install --silent 2>/dev/null && ok "MCP server dependencies installed" || warn "MCP npm install had warnings"
npm run build 2>/dev/null && ok "MCP server compiled" || fail "MCP server build failed"
cd "$SCRIPT_DIR"

if [ "$PYTHON_OK" = true ] && [ -f "requirements.txt" ]; then
  info "Installing Python dependencies..."
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv 2>/dev/null && ok "Virtual environment created" || warn "Could not create venv"
  fi
  if [ -d ".venv" ]; then
    .venv/bin/pip install -q -r requirements.txt 2>/dev/null && ok "Python dependencies installed" || warn "Some Python deps failed"
  fi
else
  warn "Skipping Python dependencies (Python 3.11+ not available)"
  info "  MCP tools will work. Python pipeline skills (taste-score, social-prep) require Python."
fi

echo ""

# -----------------------------------------------------------------------
# Platform-specific setup
# -----------------------------------------------------------------------

MCP_SERVER_PATH="$SCRIPT_DIR/mcp-server/dist/index.js"

case "$INSTALL_MODE" in
  openclaw)
    info "Configuring for OpenClaw..."

    OPENCLAW_SKILLS_DIR="$HOME/.openclaw/skills/arcanea-claw"
    mkdir -p "$OPENCLAW_SKILLS_DIR"

    cp "$SCRIPT_DIR/openclaw.json" "$OPENCLAW_SKILLS_DIR/openclaw.json"
    cp "$SCRIPT_DIR/SKILL.md" "$OPENCLAW_SKILLS_DIR/SKILL.md"

    # Update MCP server path in the copied config
    ESCAPED_PATH=$(echo "$MCP_SERVER_PATH" | sed 's/[&/\]/\\&/g')
    sed -i "s|mcp-server/dist/index.js|$ESCAPED_PATH|g" "$OPENCLAW_SKILLS_DIR/openclaw.json" 2>/dev/null || true

    ok "Registered with OpenClaw at $OPENCLAW_SKILLS_DIR"
    info "  Run: openclaw skills list"
    info "  Use: openclaw run arcanea-claw:media-pipeline"
    ;;

  nanoclaw)
    info "Configuring for NanoClaw..."

    NANOCLAW_DIR="$HOME/.nanoclaw/skills/arcanea-claw"
    mkdir -p "$NANOCLAW_DIR"

    cp "$SCRIPT_DIR/openclaw.json" "$NANOCLAW_DIR/openclaw.json"
    cp "$SCRIPT_DIR/SKILL.md" "$NANOCLAW_DIR/SKILL.md"

    ESCAPED_PATH=$(echo "$MCP_SERVER_PATH" | sed 's/[&/\]/\\&/g')
    sed -i "s|mcp-server/dist/index.js|$ESCAPED_PATH|g" "$NANOCLAW_DIR/openclaw.json" 2>/dev/null || true

    ok "Registered with NanoClaw at $NANOCLAW_DIR"
    info "  Run: nanoclaw skills list"
    ;;

  claude-code)
    info "Configuring for Claude Code..."

    # Find or create .mcp.json
    MCP_JSON=""
    if [ -f "$SCRIPT_DIR/.mcp.json" ]; then
      MCP_JSON="$SCRIPT_DIR/.mcp.json"
    elif [ -f "$HOME/.mcp.json" ]; then
      MCP_JSON="$HOME/.mcp.json"
    elif [ -f ".mcp.json" ]; then
      MCP_JSON="$(pwd)/.mcp.json"
    fi

    if [ -n "$MCP_JSON" ]; then
      info "Found existing .mcp.json at $MCP_JSON"
      info "Add this entry to your mcpServers if not already present:"
    else
      info "No .mcp.json found. Create one with this content:"
    fi

    echo ""
    echo -e "${DIM}  {${RESET}"
    echo -e "${DIM}    \"mcpServers\": {${RESET}"
    echo -e "${DIM}      \"arcanea-claw\": {${RESET}"
    echo -e "${DIM}        \"command\": \"node\",${RESET}"
    echo -e "${DIM}        \"args\": [\"$MCP_SERVER_PATH\"],${RESET}"
    echo -e "${DIM}        \"env\": {${RESET}"
    echo -e "${DIM}          \"CLAW_DIR\": \"$SCRIPT_DIR\"${RESET}"
    echo -e "${DIM}        }${RESET}"
    echo -e "${DIM}      }${RESET}"
    echo -e "${DIM}    }${RESET}"
    echo -e "${DIM}  }${RESET}"
    echo ""

    ok "MCP server ready at $MCP_SERVER_PATH"
    ;;

  standalone)
    info "Setting up standalone mode..."

    # Create a convenience run script
    cat > "$SCRIPT_DIR/run.sh" <<RUNEOF
#!/bin/bash
# ArcaneaClaw standalone runner
# Starts the MCP server on stdio (pipe to any MCP client)
# Or use with: npx @anthropic-ai/mcp-inspector

SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
export CLAW_DIR="\${CLAW_DIR:-\$SCRIPT_DIR}"
export MANIFEST_PATH="\${MANIFEST_PATH:-\$SCRIPT_DIR/manifest.json}"

exec node "\$SCRIPT_DIR/mcp-server/dist/index.js"
RUNEOF
    chmod +x "$SCRIPT_DIR/run.sh"

    ok "Created run.sh for standalone execution"
    info "  Start MCP server: ./run.sh"
    info "  Test with inspector: npx @anthropic-ai/mcp-inspector ./run.sh"
    ;;
esac

echo ""

# -----------------------------------------------------------------------
# Verify installation
# -----------------------------------------------------------------------

info "Verifying installation..."

if [ -f "$MCP_SERVER_PATH" ]; then
  ok "MCP server binary exists"
else
  fail "MCP server binary not found at $MCP_SERVER_PATH"
fi

if [ -f "$SCRIPT_DIR/openclaw.json" ]; then
  ok "openclaw.json present"
fi

if [ -f "$SCRIPT_DIR/clawhub.json" ]; then
  ok "clawhub.json present"
fi

if [ -f "$SCRIPT_DIR/SKILL.md" ]; then
  ok "SKILL.md present"
fi

echo ""
echo "============================================"
echo -e "${GREEN}${BOLD}ArcaneaClaw v${CLAW_VERSION} installed successfully${RESET}"
echo ""
echo "  Mode:       $INSTALL_MODE"
echo "  MCP Server: $MCP_SERVER_PATH"
echo "  Config:     $SCRIPT_DIR/config.yaml"
echo ""
echo -e "  ${DIM}11 MCP tools | 8 pipeline skills | 4 platforms${RESET}"
echo "============================================"
echo ""
