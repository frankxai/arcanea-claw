---
name: media-upload
description: Upload scored media to Vercel Blob or Supabase Storage by quality tier
trigger: pipeline
depends_on:
  - taste-score
sandbox: false
inputs:
  - name: hero_threshold
    type: int
    description: Minimum TASTE score for Vercel Blob upload
    source: config.yaml#arcanea_claw.upload.hero_threshold
  - name: gallery_threshold
    type: int
    description: Minimum TASTE score for Supabase Storage upload
    source: config.yaml#arcanea_claw.upload.gallery_threshold
outputs:
  - name: uploaded_count
    type: int
    description: Number of assets uploaded this cycle
dependencies:
  python:
    - supabase
  node:
    - "@vercel/blob"
tables:
  - asset_metadata (UPDATE storage_url, thumbnail_url, storage_tier)
---

# media-upload

Routes scored assets to the appropriate storage backend:

- **hero** (80+) — Vercel Blob via Node subprocess
- **gallery** (60-79) — Supabase Storage bucket `arcanea-gallery`
- **thumbnail** (40-59) — Supabase Storage bucket `thumbnails`

Assets below 40 (reject tier) are not uploaded.

## Pipeline Position

**Step 6 of 8** — runs after taste-score, feeds social-prep.
