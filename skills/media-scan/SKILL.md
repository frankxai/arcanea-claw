---
name: media-scan
description: Scan configured paths for new/changed media files
trigger: scheduled
interval: 900
sandbox: true
inputs:
  - name: scan_paths
    type: list[str]
    description: Filesystem paths to scan for media files
    source: config.yaml#arcanea_claw.scan.paths
  - name: extensions
    type: list[str]
    description: Allowed file extensions
    source: config.yaml#arcanea_claw.scan.extensions
  - name: ignore_patterns
    type: list[str]
    description: Directory/file patterns to skip
    source: config.yaml#arcanea_claw.scan.ignore_patterns
outputs:
  - name: new_files_count
    type: int
    description: Number of newly discovered files inserted into asset_metadata
  - name: file_hashes
    type: list[str]
    description: MD5 hashes of all newly found files
dependencies:
  python:
    - Pillow
    - supabase
tables:
  - asset_metadata (INSERT WHERE NOT EXISTS by file_hash)
---

# media-scan

Walks configured scan paths on a 15-minute heartbeat, discovers new or changed
media files, computes MD5 hashes, extracts basic metadata (size, dimensions,
MIME type), and inserts new rows into `asset_metadata` with `status='new'`.

Files already tracked (by hash match) are skipped. Directories matching
`ignore_patterns` are pruned from the walk.

## Pipeline Position

**Step 1 of 8** — runs first, feeds media-classify and media-dedup.
