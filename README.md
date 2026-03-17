# ArcaneaClaw

24/7 AI-powered media processing engine for creative world-builders. Scan, classify, deduplicate, transform, score, and deploy creative assets — fully automated.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/arcanea-claw?referralCode=arcanea)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Ffrankxai%2Farcanea-claw&env=SUPABASE_URL,SUPABASE_SERVICE_KEY,GEMINI_API_KEY&project-name=arcanea-claw&repository-name=arcanea-claw)

---

## What is ArcaneaClaw?

ArcaneaClaw is a containerized daemon that watches source directories for new media files and runs them through an 8-skill processing pipeline: scan, AI classify (Gemini), deduplicate (perceptual hashing), process (resize/convert to WebP), aesthetic score (TASTE), upload (Supabase Storage + Vercel Blob), generate social variants, and notify (Discord/Slack webhooks). It runs on 2GB RAM, reports health via HTTP, and registers itself in Supabase so the Command Center dashboard can monitor it remotely.

## Architecture

```
                        ArcaneaClaw Engine
                        ==================

  Source Files          8-Skill Pipeline            Destinations
  ============         ==================          ==============

  Google Drive    +--> scan --------+
  Local Folder   -+   classify      |  Gemini AI     Supabase Storage
  S3 / Volume         dedup         |  (vision)      Vercel Blob
                      process       |  WebP/resize   Social Platforms
                      score         |  TASTE 0-100   Webhook Notify
                      upload        |
                      social_prep   |
                      notify -------+

  Health: GET /health (port 8080)
  Heartbeat: Supabase agent_registry every 5 min
  Pipeline: Full chain every 15 min (configurable)

  ┌──────────────────────────────────────────────┐
  │  Command Center (Vercel)                     │
  │  Web UI for monitoring, config, asset browse │
  └──────────────────────────────────────────────┘
           |
           | reads from
           v
  ┌──────────────────────────────────────────────┐
  │  Supabase                                    │
  │  agent_registry, asset_queue, media_assets   │
  └──────────────────────────────────────────────┘
           ^
           | writes to
           |
  ┌──────────────────────────────────────────────┐
  │  ArcaneaClaw Engine (Railway / Docker)       │
  │  Python 3.11 + Node 20 + FFmpeg              │
  │  Non-root "claw" user, /data persistent vol  │
  └──────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Railway One-Click (Recommended)

Click the button above. Railway will prompt you for three required variables:

| Variable | Where to find it |
|----------|-----------------|
| `SUPABASE_URL` | Supabase Dashboard > Settings > API |
| `SUPABASE_SERVICE_KEY` | Supabase Dashboard > Settings > API > service_role |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |

Add a persistent volume mounted at `/data` in Railway settings. The engine starts automatically.

### Option 2: Docker Compose

```bash
git clone https://github.com/frankxai/arcanea-claw.git
cd arcanea-claw
cp .env.example .env
# Edit .env with your keys

docker compose up -d
```

Verify it's running:

```bash
curl http://localhost:8080/health
```

### Option 3: Native Python

```bash
git clone https://github.com/frankxai/arcanea-claw.git
cd arcanea-claw

pip install -r requirements.txt
npm install --production

# Create data directories
mkdir -p /data/{source,staging,processed,logs}

# Set environment variables (or use .env file)
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key"
export GEMINI_API_KEY="your-gemini-key"

python engine/daemon.py
```

## Skills Reference

The pipeline runs these skills sequentially every 15 minutes (configurable via `PIPELINE_INTERVAL`):

| # | Skill | Module | Description |
|---|-------|--------|-------------|
| 1 | **Scan** | `media_scan` | Walk source directories, discover new files by extension |
| 2 | **Classify** | `media_classify` | Gemini Vision AI identifies guardian, element, and tags |
| 3 | **Dedup** | `media_dedup` | Perceptual hash comparison prevents duplicate processing |
| 4 | **Process** | `media_process` | Resize to 6 variants, convert to WebP at 85% quality |
| 5 | **Score** | `taste_score` | TASTE aesthetic scoring (0-100) for quality gating |
| 6 | **Upload** | `media_upload` | Hero (score 80+) to Vercel Blob, gallery (60+) to Supabase |
| 7 | **Social Prep** | `social_prep` | Generate platform-specific sizes (story, square, wide) |
| 8 | **Notify** | `notify` | Send pipeline results to Discord/Slack webhooks |

### Adding a Custom Skill

Create `engine/skills/<name>.py` with an async `run(config)` function, then add the module name to the `SKILL_CHAIN` list in `engine/daemon.py`.

```python
async def run(config: dict) -> dict:
    """Your custom skill logic."""
    # Access config values
    output_dir = config.get("process", {}).get("output_dir", "/data/processed")

    # Do work...
    return {"processed": 42, "status": "complete"}
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_URL` | Yes | - | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | - | Supabase service role key |
| `GEMINI_API_KEY` | Yes | - | Google Gemini API key |
| `VERCEL_TOKEN` | No | - | Vercel API token for Blob uploads |
| `BLOB_READ_WRITE_TOKEN` | No | - | Vercel Blob read/write token |
| `NOTIFY_WEBHOOK_URL` | No | - | Discord or Slack webhook URL |
| `PIPELINE_INTERVAL` | No | `900` | Seconds between pipeline runs |
| `HEARTBEAT_INTERVAL` | No | `300` | Seconds between heartbeat pings |
| `ARCANEA_CLAW_CONFIG` | No | `/app/config.yaml` | Path to config file |

### config.yaml

The config file controls scan paths, processing parameters, upload thresholds, and classification settings. See `config.yaml` for the full reference with comments.

Key sections:

- **scan.paths** — directories to watch for new media
- **scan.extensions** — file types to process (.jpg, .png, .webp, .mp4, etc.)
- **process.size_variants** — output dimensions (hero, gallery, social_square, etc.)
- **upload.hero_threshold** — minimum TASTE score for Vercel Blob (default: 80)
- **upload.gallery_threshold** — minimum TASTE score for Supabase Storage (default: 60)
- **classify.model** — Gemini model for vision classification (default: gemini-2.0-flash)

## API Reference

### Health Endpoint

```
GET /health
```

Returns daemon state as JSON:

```json
{
  "status": "online",
  "started_at": 1710648000.0,
  "last_pipeline_at": 1710648900.0,
  "last_heartbeat_at": 1710648600.0,
  "pipeline_runs": 12,
  "errors": 0
}
```

### MCP Tools

ArcaneaClaw includes an MCP server (`mcp-server/`) that gives Claude Code native tool access to the pipeline. Install it with:

```bash
claude mcp add arcanea-claw -- node mcp-server/dist/index.js
```

Available tools:

| Tool | Description |
|------|-------------|
| `claw_status` | Get engine health and pipeline statistics |
| `claw_scan` | Trigger a scan of source directories |
| `claw_classify` | Classify an asset with Gemini Vision |
| `claw_score` | Get TASTE aesthetic score for an image |
| `claw_process` | Process a single asset through the pipeline |
| `claw_upload` | Upload a processed asset to storage |
| `claw_queue` | View the asset processing queue |
| `claw_config` | Read or update runtime configuration |

## Skillpacks

Pre-built skill bundles for common workflows:

| Skillpack | Description |
|-----------|-------------|
| `arcanea-media-pipeline` | Core 8-skill pipeline for media processing |
| `arcanea-taste-scorer` | Standalone TASTE aesthetic scoring |
| `arcanea-social-prep` | Social media variant generation |
| `arcanea-command-center` | Web dashboard for monitoring and control |

See `skillpacks/README.md` for installation and configuration details.

## Deployment

### Railway

The `railway.json` template configures everything automatically: Dockerfile build, health checks, restart policy, and environment variable prompts. Add a persistent volume at `/data` after deploy.

### Docker / Podman

Both `Dockerfile` (Docker) and `Containerfile` (Podman) are provided. The `docker-compose.yml` includes volume mounts for Google Drive integration and resource limits (2 CPU, 2GB RAM).

For Podman rootless:

```bash
podman-compose -f podman-compose.yml up -d
```

### Resource Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 core | 2 cores |
| RAM | 1 GB | 2 GB |
| Disk | 1 GB | 10 GB (for /data volume) |
| Network | Outbound HTTPS | Outbound HTTPS |

## Project Structure

```
arcanea-claw/
  engine/
    daemon.py              Main event loop (heartbeat + pipeline + health)
    supabase_client.py     Supabase DB operations (agent registry, assets)
    skills/                Skill modules (media_scan, media_classify, etc.)
  skills/                  Skill packages (scan, classify, dedup, process...)
  skillpacks/              Pre-built skill bundles
  mcp-server/              MCP server for Claude Code integration
  deploy/
    railway-setup.sh       Post-deploy initialization script
    vercel.json            Vercel config for Command Center UI
  config.yaml              Pipeline configuration
  Dockerfile               Multi-stage production build
  Containerfile            Podman-compatible build
  docker-compose.yml       Docker local deployment
  podman-compose.yml       Podman rootless deployment
  railway.json             Railway template configuration
  .env.example             Environment variable template
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-skill`)
3. Add your skill to `engine/skills/` with an async `run(config)` function
4. Add it to the `SKILL_CHAIN` in `engine/daemon.py`
5. Test locally with `docker compose up`
6. Open a pull request

## License

See [LICENSE](../LICENSE) in the root Arcanea repository.

---

Built by [FrankX](https://arcanea.ai) as part of the [Arcanea](https://arcanea.ai) creative multiverse.
