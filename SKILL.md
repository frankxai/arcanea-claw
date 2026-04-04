---
name: arcanea-claw
version: "0.3.0"
description: "The Claw Fleet — 5 AI engines (Media, Forge, Herald, Scout, Scribe) with 33 skills, cross-claw events, and fleet orchestration for creative operations."
author: "frankxai"
homepage: "https://arcanea.ai/claw"
repository: "https://github.com/frankxai/arcanea-claw"
license: "MIT"
tags: [media, image-processing, ai-classification, nft, social-media, creative, world-building, publishing, mcp, fleet]
platforms: [openclaw, nanoclaw, claude-code, standalone]
install:
  - "pip install -r requirements.txt"
  - "cd mcp-server && npm install && npm run build"
mcpServer:
  command: "node"
  args: ["mcp-server/dist/index.js"]
  env:
    CLAW_DIR: "${CLAW_DIR:-./}"
    MANIFEST_PATH: "${MANIFEST_PATH:-./manifest.json}"
metadata:
  openclaw:
    requires:
      env:
        - SUPABASE_URL
        - SUPABASE_SERVICE_KEY
        - GEMINI_API_KEY
      bins: [python3, ffmpeg]
      anyBins: [docker, podman]
    primaryEnv: SUPABASE_URL
    emoji: "lobster"
    homepage: "https://arcanea.ai/claw"
    security:
      sandboxed: true
      containerOnly: true
      permissions:
        - network:outbound
        - storage:supabase
        - storage:vercel-blob
      noPermissions:
        - shell:execute
        - filesystem:write-outside-data
    verified: true
    publisher: "@arcanea"
---

# ArcaneaClaw -- Creator Media Engine

A complete AI-powered pipeline for scanning, classifying, scoring, processing, and
publishing creative media. Built for world-builders, game designers, artists, and
anyone managing large collections of visual content.

## What It Does

```
Source Files  -->  Scan  -->  Classify  -->  Score  -->  Process  -->  Upload
   (any dir)     (discover)  (tag/label)   (TASTE)    (resize/opt)  (cloud)
```

**8 skills** working as a pipeline:

| Skill | What it does |
|-------|-------------|
| `media-scan` | Discovers new images, video, and audio in configured directories |
| `media-classify` | Tags assets by character, element, content type using heuristics + AI |
| `taste-score` | Scores aesthetic quality 0-100 across 5 dimensions using Gemini Vision |
| `media-dedup` | Finds and marks duplicate assets by perceptual hash |
| `media-process` | Resizes to 6 variants (hero, gallery, social square/story/wide, thumbnail) |
| `media-upload` | Deploys hero-tier to Vercel Blob, gallery-tier to Supabase Storage |
| `social-prep` | Generates platform-optimized variants with AI captions and hashtags |
| `notify` | Sends pipeline status updates via webhook |

## Installation

### OpenClaw (recommended)

```bash
openclaw install @arcanea/claw
```

This registers the MCP server and all 8 skills automatically via `openclaw.json`.

### NanoClaw

```bash
nanoclaw add arcanea-claw
```

### Claude Code

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "arcanea-claw": {
      "command": "node",
      "args": ["/path/to/arcanea-claw/mcp-server/dist/index.js"],
      "env": {
        "CLAW_DIR": "/path/to/media",
        "MANIFEST_PATH": "/path/to/manifest.json"
      }
    }
  }
}
```

### Standalone

```bash
git clone https://github.com/frankxai/arcanea-claw.git
cd arcanea-claw
./install.sh
```

## MCP Tools

Once installed, these tools are available to any MCP-compatible agent:

| Tool | Description |
|------|-------------|
| `claw_status` | Engine status: daemon, manifest, config |
| `claw_scan` | Scan directories for new media files |
| `claw_inbox` | List assets filtered by status/guardian with counts |
| `claw_approve` | Approve assets by ID |
| `claw_reject` | Reject assets by ID with optional reason |
| `claw_stats` | Full dashboard: guardians, elements, tiers, scores |
| `claw_process` | Process approved assets (resize, convert) |
| `claw_heroes` | List hero-tier assets (score 80+) |
| `claw_classify` | Classify untagged assets by filename heuristics |
| `claw_pipeline` | Run full pipeline: scan -> classify -> dedup -> process |

## Configuration

Edit `config.yaml` to customize:

```yaml
arcanea_claw:
  scan:
    paths:
      - /your/media/directory
    extensions: [.jpg, .jpeg, .png, .webp, .gif, .mp4]

  process:
    webp_quality: 85
    max_dimension: 2400
    size_variants:
      hero: [1920, 1080]
      gallery: [1200, 800]
      social_square: [1080, 1080]
      social_story: [1080, 1920]
      social_wide: [1200, 628]
      thumbnail: [320, 320]

  upload:
    hero_threshold: 80      # TASTE score for Vercel Blob
    gallery_threshold: 60   # TASTE score for Supabase Storage

  classify:
    model: "gemini-2.0-flash"
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CLAW_DIR` | No | Root directory for media operations (default: cwd) |
| `MANIFEST_PATH` | No | Path to manifest.json (default: `$CLAW_DIR/manifest.json`) |
| `GEMINI_API_KEY` | For scoring | Google Gemini API key for TASTE scoring and classification |
| `SUPABASE_URL` | For upload | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | For upload | Supabase service role key |
| `BLOB_READ_WRITE_TOKEN` | For upload | Vercel Blob read/write token |
| `NOTIFY_WEBHOOK_URL` | For notify | Webhook URL for pipeline notifications |

## Architecture

```
arcanea-claw/
  mcp-server/          # MCP tools (Node.js, TypeScript)
    index.ts           # 11 tools, stdio transport
    dist/              # Compiled output
  engine/              # Python pipeline engine
    daemon.py          # Background pipeline runner
    skills/            # Python skill implementations
  skills/              # Skill definitions (8 skills)
  skillpacks/          # Bundled skill collections
  config.yaml          # Pipeline configuration
  openclaw.json        # OpenClaw integration config
  clawhub.json         # ClawHub marketplace listing
  install.sh           # Universal installer
```

## Requirements

- **Node.js** >= 18 (for MCP server)
- **Python** >= 3.11 (for pipeline engine)
- **Optional**: Gemini API key (scoring), Supabase (storage), Vercel Blob (CDN)

## License

MIT
