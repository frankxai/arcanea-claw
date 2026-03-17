---
name: arcanea-media-pipeline
version: "1.0.0"
description: "Complete AI-powered media processing pipeline for creative world-building. Scans, classifies, processes, scores, and uploads media with fantasy/mythology-aware tagging."
author: "frankxai"
homepage: "https://arcanea.ai"
repository: "https://github.com/frankxai/arcanea-claw"
license: "MIT"
tags: [media, image-processing, ai-classification, creative, world-building, fantasy, pipeline, automation]
skills:
  - media-scan
  - media-classify
  - media-process
  - media-dedup
  - taste-score
  - media-upload
  - social-prep
  - notify
dependencies:
  python: ">=3.11"
  packages: [Pillow, google-generativeai, supabase, watchdog, aiohttp, pyyaml, python-dotenv, requests]
env:
  required:
    - GEMINI_API_KEY
    - SUPABASE_URL
    - SUPABASE_SERVICE_KEY
  optional:
    - VERCEL_BLOB_TOKEN
    - NOTIFY_WEBHOOK_URL
---

# Arcanea Media Pipeline

A complete AI-powered media processing pipeline that turns creative chaos into organized, scored, and published content. Built for world-builders, game studios, creative teams, and solo artists who generate more images than they can manage.

## What It Does

Drop images anywhere. ArcaneaClaw automatically:

1. **Scans** configured directories for new media files (images, video, audio)
2. **Classifies** using Gemini Vision AI -- assigns categories, tags, content type, and mythology-aware metadata
3. **Deduplicates** via MD5 hashing to prevent redundant processing
4. **Processes** into WebP format with 6 size variants (hero, gallery, social square, social story, social wide, thumbnail)
5. **Scores** quality on 5 dimensions using the TASTE system (0-100 composite score)
6. **Uploads** to tiered storage -- CDN for hero-tier, standard storage for gallery-tier
7. **Preps social** posts with AI-generated platform-specific captions
8. **Notifies** you via webhook when the pipeline completes

## The Pipeline

```
Source Files
    |
    v
[1. media-scan] -----> Discover new files, compute hashes, extract basic metadata
    |
    v
[2. media-classify] -> Gemini Vision: assign guardian, element, tags, content type
    |
    v
[3. media-dedup] ----> Perceptual hash deduplication, merge duplicate metadata
    |
    v
[4. media-process] --> Convert to WebP, generate 6 size variants per image
    |
    v
[5. taste-score] ----> 5-dimension aesthetic scoring (0-100), tier assignment
    |
    v
[6. media-upload] ---> Hero (80+) to CDN, Gallery (60-79) to storage, rest archived
    |
    v
[7. social-prep] ----> Platform-optimized variants + AI-generated captions
    |
    v
[8. notify] ---------> Webhook with pipeline summary and hero highlights
```

## Installation

### Via ClawHub (recommended)

```bash
claw install arcanea-media-pipeline
```

### Via OpenClaw CLI

```bash
openclaw skill add arcanea-media-pipeline
```

### Standalone

```bash
git clone https://github.com/frankxai/arcanea-claw.git
cd arcanea-claw
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys
python -m engine.daemon
```

### Docker

```bash
docker compose up -d
curl http://localhost:8080/health
```

## Configuration

The pipeline is configured via `config.yaml`. Key sections:

```yaml
arcanea_claw:
  # Where to look for media
  scan:
    paths:
      - /path/to/your/media
      - /another/source/directory
    extensions: [.jpg, .jpeg, .png, .webp, .gif, .mp4, .mov]
    ignore_patterns: [".*", "__pycache__", "node_modules"]

  # Image processing settings
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

  # Quality thresholds for upload tiers
  upload:
    hero_threshold: 80
    gallery_threshold: 60

  # AI classification model
  classify:
    model: "gemini-2.0-flash"

  # Webhook notifications
  notify:
    enabled: true
    channels:
      - type: webhook
        url: "${NOTIFY_WEBHOOK_URL}"
```

## For World-Builders

Out of the box, the classification skill understands fantasy and mythology taxonomies. It ships with Arcanea's own canon (Ten Guardians, Five Elements, Ten Gates), but you can replace this with your own world's entities:

```yaml
classify:
  model: "gemini-2.0-flash"
  # Replace with your world's characters
  guardians:
    - Aragorn
    - Gandalf
    - Frodo
  # Replace with your world's systems
  elements:
    - Light
    - Shadow
    - Nature
  # Add your own content categories
  categories:
    - Character Portrait
    - Landscape
    - Battle Scene
    - Item/Artifact
    - Map
```

The classifier prompt adapts to whatever entities and categories you provide. No code changes needed.

## Scheduling

The pipeline runs on two heartbeats:

- **Status heartbeat**: Every 5 minutes -- reports agent health to the database
- **Pipeline heartbeat**: Every 15 minutes -- runs the full 8-skill chain

Both intervals are configurable:

```yaml
heartbeat:
  interval_seconds: 300
  pipeline_interval_seconds: 900
```

## Database Schema

The pipeline uses two primary tables in Supabase:

**asset_metadata** -- One row per media file:
- `file_hash` (MD5, unique)
- `file_path`, `file_size`, `dimensions`, `mime_type`
- `guardian`, `element`, `gate`, `tags`, `content_type`
- `quality_score` (0-100), `quality_tier` (hero/gallery/thumbnail/reject)
- `status` (new/classified/processed/scored/uploaded/published)
- `cdn_url`, `storage_url`

**social_queue** -- One row per platform per hero asset:
- `asset_id`, `platform`, `caption`, `hashtags`, `variant_url`
- `status` (draft/scheduled/published)
- `scheduled_at`, `published_at`

## Resource Requirements

Designed for lightweight deployment:

- **CPU**: 2 cores minimum
- **RAM**: 2 GB minimum (image processing is batched)
- **Disk**: Depends on media volume; processed variants are ~60% smaller than originals
- **API**: Gemini Flash is free-tier compatible for moderate volumes (~100 images/day)

## Individual Skills

Each skill in this pack can also be installed standalone:

| Skill | ClawHub Package | Description |
|-------|-----------------|-------------|
| media-scan | (bundled) | Directory watcher and file discovery |
| media-classify | (bundled) | Gemini Vision classification |
| media-dedup | (bundled) | Perceptual hash deduplication |
| media-process | (bundled) | WebP conversion and size variants |
| taste-score | `arcanea-taste-scorer` | 5-dimension aesthetic scoring |
| media-upload | (bundled) | Tiered storage upload |
| social-prep | `arcanea-social-prep` | Platform-optimized social variants |
| notify | (bundled) | Webhook notifications |

## Standalone or Agent

Works as:
- **OpenClaw / NanoClaw skill** -- scheduled via heartbeat, managed by the claw daemon
- **Standalone Python pipeline** -- `python -m engine.daemon`
- **Docker container** -- `docker compose up -d`
- **Claude Code skill** -- invoke individual steps from an AI coding agent
- **CI/CD step** -- run the pipeline as a post-build hook for asset-heavy projects

## License

MIT -- use it, fork it, build on it.
