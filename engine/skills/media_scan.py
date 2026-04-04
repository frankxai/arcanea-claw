"""media-scan skill: Discover new media files and register them in asset_metadata.

Walks configured scan paths, computes MD5 hashes, extracts basic metadata
(size, dimensions, MIME type), and inserts new rows with status='new'.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger("arcanea-claw.media-scan")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md5_hash(filepath: Path, chunk_size: int = 8192) -> str:
    """Compute MD5 hex digest for a file."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _extract_metadata(filepath: Path) -> dict[str, Any]:
    """Return basic file metadata including dimensions for images."""
    stat = filepath.stat()
    mime, _ = mimetypes.guess_type(str(filepath))
    meta: dict[str, Any] = {
        "file_size": stat.st_size,
        "mime_type": mime or "application/octet-stream",
        "width": None,
        "height": None,
    }
    if mime and mime.startswith("image/"):
        try:
            with Image.open(filepath) as img:
                meta["width"], meta["height"] = img.size
        except Exception as exc:
            logger.warning("Could not read dimensions for %s: %s", filepath, exc)
    return meta


def _should_ignore(path: Path, ignore_patterns: list[str]) -> bool:
    """Return True if any path component matches an ignore pattern."""
    for part in path.parts:
        for pattern in ignore_patterns:
            if part == pattern or (pattern.startswith(".") and part.startswith(".")):
                return True
    return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Scan configured paths for new media files.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.

    Returns:
        Dict with ``new_files_count`` and ``file_hashes``.
    """
    scan_cfg = config.get("scan", {})
    scan_paths: list[str] = scan_cfg.get("paths", [])
    extensions: set[str] = {ext.lower() for ext in scan_cfg.get("extensions", [])}
    ignore_patterns: list[str] = scan_cfg.get("ignore_patterns", [])

    # Fetch existing hashes to skip known files
    existing_resp = supabase.table("asset_metadata").select("file_hash").execute()
    existing_hashes: set[str] = {
        row["file_hash"] for row in (existing_resp.data or []) if row.get("file_hash")
    }

    new_files: list[dict[str, Any]] = []
    new_hashes: list[str] = []

    for scan_root in scan_paths:
        root = Path(scan_root).resolve()
        if not root.exists():
            logger.warning("Scan path does not exist: %s", root)
            continue

        # CRIT-05: followlinks=False prevents symlink traversal attacks
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)

            # Prune ignored directories in-place
            dirnames[:] = [
                d for d in dirnames
                if not _should_ignore(current / d, ignore_patterns)
            ]

            for fname in filenames:
                filepath = current / fname
                if filepath.suffix.lower() not in extensions:
                    continue

                try:
                    file_hash = _md5_hash(filepath)
                except OSError as exc:
                    logger.warning("Cannot read %s: %s", filepath, exc)
                    continue

                if file_hash in existing_hashes:
                    continue

                meta = _extract_metadata(filepath)
                row = {
                    "file_path": str(filepath),
                    "file_name": fname,
                    "file_hash": file_hash,
                    "file_size": meta["file_size"],
                    "mime_type": meta["mime_type"],
                    "width": meta["width"],
                    "height": meta["height"],
                    "status": "new",
                    "quality_score": 0,
                    "tags": [],
                    "metadata": {},
                }
                new_files.append(row)
                new_hashes.append(file_hash)
                existing_hashes.add(file_hash)  # prevent intra-batch dupes

    # Bulk insert
    if new_files:
        try:
            supabase.table("asset_metadata").insert(new_files).execute()
            logger.info("Inserted %d new assets into asset_metadata", len(new_files))
        except Exception as exc:
            logger.error("Failed to insert assets: %s", exc)
            raise

    return {
        "new_files_count": len(new_files),
        "file_hashes": new_hashes,
    }
