---
name: social-prep
description: Generate social media queue entries for hero-tier artwork
trigger: pipeline
depends_on:
  - media-upload
sandbox: true
inputs:
  - name: model
    type: str
    description: Gemini model for caption generation
    source: config.yaml#arcanea_claw.classify.model
outputs:
  - name: posts_queued
    type: int
    description: Number of social queue entries created
dependencies:
  python:
    - google-generativeai
    - supabase
tables:
  - social_queue (INSERT with status='draft')
  - asset_metadata (READ hero-tier assets)
---

# social-prep

For each hero-tier asset, creates draft social media entries across 4 platforms:

- **Instagram**: 1:1 variant + caption with guardian/element hashtags
- **LinkedIn**: 1.91:1 variant + professional description
- **X (Twitter)**: 16:9 variant + short caption
- **YouTube**: 16:9 variant as potential video thumbnail

Captions are generated via Gemini, balancing mystical Arcanea voice with
platform-appropriate tone and hashtags.

## Pipeline Position

**Step 7 of 8** — runs after media-upload, feeds notify.
