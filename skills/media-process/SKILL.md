---
name: media-process
description: Convert classified media to WebP and generate size variants
trigger: pipeline
depends_on:
  - media-classify
sandbox: true
inputs:
  - name: webp_quality
    type: int
    description: WebP compression quality (0-100)
    source: config.yaml#arcanea_claw.process.webp_quality
  - name: max_dimension
    type: int
    description: Maximum pixel dimension on longest side
    source: config.yaml#arcanea_claw.process.max_dimension
  - name: size_variants
    type: dict
    description: Named variant sizes (width, height)
    source: config.yaml#arcanea_claw.process.size_variants
  - name: staging_dir
    type: str
    description: Root directory for processed output
    source: config.yaml#arcanea_claw.process.staging_dir
outputs:
  - name: processed_count
    type: int
    description: Number of assets processed this cycle
dependencies:
  python:
    - Pillow
    - supabase
tables:
  - asset_metadata (UPDATE metadata JSONB with variant paths, status='processed')
---

# media-process

Takes classified assets and produces production-ready WebP files:

- Base conversion: WebP quality 85, max 2400px longest side
- Thumbnail: 320x320 center crop
- Variants: hero (1920x1080), gallery (1200x800), social square (1080x1080),
  social story (1080x1920), social wide (1200x628)

Output is organized by guardian: `/data/staging/{guardian}/{variant}/{filename}.webp`

## Pipeline Position

**Step 4 of 8** — runs after media-dedup, feeds taste-score.
