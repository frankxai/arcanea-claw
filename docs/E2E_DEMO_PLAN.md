# ArcaneaClaw E2E Demo Plan

> Complete walkthrough for demonstrating ArcaneaClaw working end-to-end.

---

## Pre-Demo Setup (Do Before Friend Arrives)

### 1. Environment Variables

Create `.env` in `arcanea-claw/`:

```bash
# Required
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_KEY=eyJ...  # service_role key from Supabase Settings > API

# Required for AI classification + scoring
GEMINI_API_KEY=AIza...  # from https://aistudio.google.com/apikey

# Optional
NOTIFY_WEBHOOK_URL=https://discord.com/api/webhooks/...
PIPELINE_INTERVAL=60  # 1 min for demo (default 900 = 15 min)
HEARTBEAT_INTERVAL=30
```

### 2. Database Tables (DONE)

Tables already applied to Supabase:
- `asset_metadata` — media tracking
- `agent_registry` — agent heartbeat
- `social_queue` — social post drafts
- `publish_pipeline` — deployment tracking

### 3. Supabase Storage Buckets

Create these buckets in Supabase Dashboard > Storage:
- `arcanea-gallery` (public)
- `thumbnails` (public)

### 4. Sample Media

Place 5-10 high-quality Arcanea images in a source folder:
```bash
mkdir -p /c/Users/frank/Arcanea/arcanea-claw/demo-media
# Copy guardian images, NFT art, etc. here
```

---

## Option A: Local Python Demo (Fastest, ~5 min setup)

### Setup

```bash
cd /c/Users/frank/Arcanea/arcanea-claw

# Create venv
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash

# Install deps
pip install -r requirements.txt

# Set config to use local paths
export ARCANEA_CLAW_CONFIG="$(pwd)/config.yaml"
```

Update `config.yaml` scan paths to point to demo media:
```yaml
scan:
  paths:
    - /c/Users/frank/Arcanea/arcanea-claw/demo-media
```

### Run

```bash
# Start the daemon
python engine/daemon.py
```

### What to Show

1. **Health endpoint**: Open `http://localhost:8080/health` — shows daemon state JSON
2. **Pipeline runs**: Watch terminal logs as scan → classify → score → upload executes
3. **Supabase Dashboard**: Show rows appearing in `asset_metadata` table
4. **Agent Registry**: Show the agent heartbeat updating in real-time
5. **Social Queue**: Show draft posts generated for hero-tier images

---

## Option B: Docker Demo (Production-like, ~10 min setup)

### Build & Run

```bash
cd /c/Users/frank/Arcanea/arcanea-claw

# Build
docker build -t arcanea-claw:latest .

# Run with env vars and mount demo media
docker run -d \
  --name arcanea-claw \
  -p 8080:8080 \
  -v "$(pwd)/demo-media:/data/source" \
  --env-file .env \
  -e ARCANEA_CLAW_CONFIG=/app/config.yaml \
  -e PIPELINE_INTERVAL=60 \
  arcanea-claw:latest
```

### Monitor

```bash
# Health check
curl http://localhost:8080/health | python -m json.tool

# Logs
docker logs -f arcanea-claw
```

---

## Option C: Railway Deploy (Cloud, ~15 min setup)

### Deploy

1. Go to https://railway.app/new
2. Deploy from GitHub repo: `frankxai/arcanea-claw`
3. Add environment variables:
   - `SUPABASE_URL` 
   - `SUPABASE_SERVICE_KEY`
   - `GEMINI_API_KEY`
   - `PIPELINE_INTERVAL=60` (fast for demo)
4. Add a persistent volume mounted at `/data`
5. Railway builds Dockerfile automatically

### Upload Demo Media

Since Railway doesn't have local files, use the MCP server or upload directly:
```bash
# From Claude Code with MCP connected
claw_scan  # triggers scan of /data/source
```

Or SSH into Railway and copy files to `/data/source/`.

---

## Demo Script (The Show)

### Act 1: "The Engine Starts" (2 min)

```
"ArcaneaClaw is a 24/7 AI media processing daemon. It watches directories for 
new art, classifies it against the Arcanea universe, scores quality, and 
distributes to the right channels."
```

1. Show the health endpoint returning JSON
2. Show agent_registry in Supabase — "It's alive and reporting heartbeats"

### Act 2: "Feed It Art" (3 min)

1. Drop 5 images into the source directory
2. Watch the terminal: `"Skill media_scan completed"` → shows new files found
3. Open Supabase: 5 new rows in `asset_metadata` with status `new`

### Act 3: "AI Classification" (3 min)

1. Pipeline continues: Gemini classifies each image
2. Supabase shows: Guardian assigned (Draconia, Leyla...), Element tagged, status → `classified`
3. Explain: "Every image gets mapped to our 10-Guardian mythology automatically"

### Act 4: "Quality Scoring" (3 min)

1. After processing to WebP variants, TASTE scorer runs
2. Show the 5-dimension scores in asset metadata JSONB
3. Hero tier (80+) → Vercel Blob, Gallery (60-79) → Supabase Storage
4. "AI curates our gallery automatically — only the best make it to the homepage"

### Act 5: "Social Queue" (2 min)

1. Show social_queue table: draft posts auto-generated for Instagram, LinkedIn, X, YouTube
2. Each has platform-specific captions and hashtags
3. "One image → 4 platforms → zero manual work"

### Act 6: "The MCP Bridge" (2 min)

1. Show Claude Code with claw MCP tools
2. `claw_status` → engine health
3. `claw_heroes` → hero-tier assets
4. `claw_stats` → full dashboard
5. "Any AI agent in the ecosystem can control the media engine"

---

## Architecture Diagram (Draw on Whiteboard)

```
  ┌─────────────┐     ┌──────────────┐     ┌───────────────┐
  │  Source Dir  │────▸│  ArcaneaClaw │────▸│   Supabase    │
  │  (images)   │     │   Daemon     │     │  PostgreSQL   │
  └─────────────┘     │              │     │  + Storage    │
                      │  8 Skills:   │     └───────┬───────┘
                      │  scan        │             │
                      │  classify    │◂──── Gemini Vision
                      │  dedup       │
                      │  process     │     ┌───────────────┐
                      │  score       │────▸│  Vercel Blob  │
                      │  upload      │     │  (hero-tier)  │
                      │  social_prep │     └───────────────┘
                      │  notify      │
                      └──────┬───────┘     ┌───────────────┐
                             │            ▸│  Discord/Slack│
                             └────────────▸│  Webhooks     │
                                           └───────────────┘
  ┌─────────────┐
  │ Claude Code │◂───── MCP Server (11 tools)
  │ / OpenClaw  │
  └─────────────┘
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Daemon won't start | Check `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `.env` |
| Classification fails | Check `GEMINI_API_KEY` is valid. Daemon continues without AI if missing |
| No files found | Check scan paths in `config.yaml` match actual image location |
| Upload fails | Create `arcanea-gallery` and `thumbnails` buckets in Supabase Storage |
| Docker build fails | Ensure Docker Desktop is running, ~200MB image |
| Health returns error | Check port 8080 is not in use: `netstat -an | grep 8080` |

---

## After Demo: Next Steps

1. **Railway permanent deploy** — always-on cloud daemon
2. **Connect MCP to OpenClaw** — submit skill to ClawHub (347K+ users)
3. **Connect to arcanea.ai** — auto-populate /gallery and /guardians pages
4. **Mobile capture** — photo → daemon → classified → published in minutes
5. **Discord bot** — real-time notifications with image previews
