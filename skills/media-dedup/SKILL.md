---
name: media-dedup
description: Detect and reject duplicate media files by content hash
trigger: pipeline
depends_on:
  - media-classify
sandbox: true
inputs: []
outputs:
  - name: duplicates_found
    type: int
    description: Number of duplicate assets marked as rejected
dependencies:
  python:
    - supabase
tables:
  - asset_metadata (UPDATE status='rejected', add 'duplicate' tag)
---

# media-dedup

Groups all assets by `file_hash`. When duplicates exist, keeps the one with
the highest `quality_score` (or earliest `created_at` as tiebreaker) and marks
the rest with `status='rejected'` and tag `'duplicate'`.

Runs early in the pipeline to prevent wasted processing on duplicate files.

## Pipeline Position

**Step 3 of 8** — runs after media-classify, before media-process.
