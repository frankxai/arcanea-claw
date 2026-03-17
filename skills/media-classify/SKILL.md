---
name: media-classify
description: Classify untagged media against Arcanea canon using Gemini Vision
trigger: pipeline
depends_on:
  - media-scan
sandbox: true
inputs:
  - name: batch_size
    type: int
    description: Max images to classify per cycle
    default: 20
  - name: model
    type: str
    description: Gemini model for vision classification
    source: config.yaml#arcanea_claw.classify.model
outputs:
  - name: classified_count
    type: int
    description: Number of assets classified this cycle
dependencies:
  python:
    - google-generativeai
    - supabase
    - Pillow
tables:
  - asset_metadata (UPDATE guardian, element, gate, tags, content_type, status)
---

# media-classify

Queries `asset_metadata` for rows with `status='new'` or `guardian IS NULL`,
sends each image to Gemini Vision with a canon-aware prompt, and updates the
row with the identified Guardian, Element, Gate, tags, and content type.

Processes at most 20 images per cycle to stay within API rate limits.

## Pipeline Position

**Step 2 of 8** — runs after media-scan, feeds media-process and taste-score.
