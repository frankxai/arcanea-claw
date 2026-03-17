---
name: taste-score
description: Score processed media on 5 aesthetic dimensions using Gemini Vision
trigger: pipeline
depends_on:
  - media-process
sandbox: true
inputs:
  - name: batch_size
    type: int
    description: Max images to score per cycle
    default: 15
  - name: model
    type: str
    description: Gemini model for scoring
    source: config.yaml#arcanea_claw.classify.model
outputs:
  - name: scored_count
    type: int
    description: Number of assets scored this cycle
  - name: hero_count
    type: int
    description: Number of assets that achieved hero tier (80+)
dependencies:
  python:
    - google-generativeai
    - supabase
    - Pillow
tables:
  - asset_metadata (UPDATE quality_score, quality_tier, status='scored')
---

# taste-score

Sends processed images to Gemini Vision for a 5-dimension quality assessment:

1. **Canon Alignment** (0-20) — matches Arcanea fantasy aesthetic
2. **Design Compliance** (0-20) — composition, palette, professionalism
3. **Emotional Impact** (0-20) — evokes wonder, power, mystery
4. **Technical Fit** (0-20) — resolution, clarity, web-ready
5. **Uniqueness** (0-20) — distinct from generic AI art

Total score (0-100) maps to quality tiers:
- **hero**: 80+ (uploaded to Vercel Blob)
- **gallery**: 60-79 (uploaded to Supabase Storage)
- **thumbnail**: 40-59 (thumbnails only)
- **reject**: <40 (not published)

Processes at most 15 images per cycle.

## Pipeline Position

**Step 5 of 8** — runs after media-process, feeds media-upload and social-prep.
