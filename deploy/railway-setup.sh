#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# ArcaneaClaw — Railway Post-Deploy Setup
#
# Runs after the container starts on Railway. Creates persistent volume
# directories, initializes manifest state, and registers the agent in
# Supabase so the Command Center knows this engine is alive.
# ----------------------------------------------------------------------------

set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
MANIFEST_FILE="${DATA_DIR}/manifest.json"
AGENT_ID="${AGENT_ID:-arcanea-claw-railway}"
AGENT_NAME="${AGENT_NAME:-ArcaneaClaw Railway Engine}"
VERSION="0.1.0"

# ── 1. Create persistent volume directories ──────────────────────────────────

echo "[setup] Ensuring data directories exist..."

for dir in source staging processed logs; do
  mkdir -p "${DATA_DIR}/${dir}"
  echo "[setup]   ${DATA_DIR}/${dir} — ok"
done

# ── 2. Initialize manifest if missing ────────────────────────────────────────

if [ ! -f "${MANIFEST_FILE}" ]; then
  echo "[setup] Creating initial manifest at ${MANIFEST_FILE}"
  cat > "${MANIFEST_FILE}" <<MANIFEST
{
  "agent_id": "${AGENT_ID}",
  "agent_name": "${AGENT_NAME}",
  "version": "${VERSION}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "platform": "railway",
  "pipeline_runs": 0,
  "total_assets_processed": 0,
  "skills": [
    "media_scan",
    "media_classify",
    "media_dedup",
    "media_process",
    "taste_score",
    "media_upload",
    "social_prep",
    "notify"
  ]
}
MANIFEST
else
  echo "[setup] Manifest already exists at ${MANIFEST_FILE} — skipping init"
fi

# ── 3. Register agent in Supabase ────────────────────────────────────────────

if [ -n "${SUPABASE_URL:-}" ] && [ -n "${SUPABASE_SERVICE_KEY:-}" ]; then
  echo "[setup] Registering agent in Supabase..."

  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${SUPABASE_URL}/rest/v1/agent_registry" \
    -H "apikey: ${SUPABASE_SERVICE_KEY}" \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_KEY}" \
    -H "Content-Type: application/json" \
    -H "Prefer: resolution=merge-duplicates" \
    -d "{
      \"agent_id\": \"${AGENT_ID}\",
      \"agent_name\": \"${AGENT_NAME}\",
      \"status\": \"starting\",
      \"platform\": \"railway\",
      \"version\": \"${VERSION}\",
      \"last_heartbeat\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }")

  if [ "${HTTP_STATUS}" -ge 200 ] && [ "${HTTP_STATUS}" -lt 300 ]; then
    echo "[setup] Agent registered successfully (HTTP ${HTTP_STATUS})"
  else
    echo "[setup] WARNING: Agent registration returned HTTP ${HTTP_STATUS}"
    echo "[setup]   This is non-fatal — the daemon will retry on startup"
  fi
else
  echo "[setup] SUPABASE_URL or SUPABASE_SERVICE_KEY not set — skipping registration"
  echo "[setup]   Set these in Railway variables for full functionality"
fi

# ── 4. Print connection info ─────────────────────────────────────────────────

echo ""
echo "============================================================"
echo "  ArcaneaClaw v${VERSION} — Railway Setup Complete"
echo "============================================================"
echo ""
echo "  Agent ID:     ${AGENT_ID}"
echo "  Data Volume:  ${DATA_DIR}"
echo "  Health Check: http://localhost:8080/health"
echo ""
echo "  Directories:"
echo "    Source:     ${DATA_DIR}/source"
echo "    Staging:    ${DATA_DIR}/staging"
echo "    Processed:  ${DATA_DIR}/processed"
echo "    Logs:       ${DATA_DIR}/logs"
echo ""

if [ -n "${SUPABASE_URL:-}" ]; then
  echo "  Supabase:     ${SUPABASE_URL}"
fi

if [ -n "${NOTIFY_WEBHOOK_URL:-}" ]; then
  echo "  Webhook:      (configured)"
fi

echo ""
echo "  The daemon will start automatically after this script."
echo "============================================================"
