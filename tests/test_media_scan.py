"""Tests for engine.skills.media_scan — hash, metadata, ignore, and run()."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from engine.skills.media_scan import _md5_hash, _extract_metadata, _should_ignore, run


# ---------------------------------------------------------------------------
# _md5_hash
# ---------------------------------------------------------------------------

class TestMd5Hash:

    def test_hash_matches_known_value(self, tmp_path):
        """Hash of known content should match hashlib.md5 directly."""
        content = b"hello arcanea claw"
        f = tmp_path / "test.bin"
        f.write_bytes(content)

        expected = hashlib.md5(content).hexdigest()
        assert _md5_hash(f) == expected

    def test_hash_empty_file(self, tmp_path):
        """Empty file should produce md5 of empty bytes."""
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")

        expected = hashlib.md5(b"").hexdigest()
        assert _md5_hash(f) == expected

    def test_hash_large_file(self, tmp_path):
        """File larger than chunk_size should still hash correctly."""
        content = os.urandom(32768)  # 32KB > default 8192 chunk
        f = tmp_path / "big.bin"
        f.write_bytes(content)

        expected = hashlib.md5(content).hexdigest()
        assert _md5_hash(f) == expected

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")

        assert _md5_hash(f1) != _md5_hash(f2)


# ---------------------------------------------------------------------------
# _extract_metadata
# ---------------------------------------------------------------------------

class TestExtractMetadata:

    def test_plain_file_metadata(self, tmp_path):
        """Non-image file should have size, mime, and None dimensions."""
        f = tmp_path / "data.txt"
        f.write_text("some content")

        meta = _extract_metadata(f)
        assert meta["file_size"] == f.stat().st_size
        assert meta["mime_type"] == "text/plain"
        assert meta["width"] is None
        assert meta["height"] is None

    def test_image_metadata(self, tmp_path):
        """PNG image should return width and height."""
        from PIL import Image

        img = Image.new("RGB", (640, 480), color="red")
        f = tmp_path / "test.png"
        img.save(str(f))

        meta = _extract_metadata(f)
        assert meta["width"] == 640
        assert meta["height"] == 480
        assert "image" in meta["mime_type"]

    def test_unknown_extension_gets_octet_stream(self, tmp_path):
        """Unrecognizable extension should default to application/octet-stream."""
        f = tmp_path / "weird.xyzqwerty"
        f.write_bytes(b"\x00\x01\x02")

        meta = _extract_metadata(f)
        assert meta["mime_type"] == "application/octet-stream"

    def test_corrupt_image_has_none_dimensions(self, tmp_path):
        """File with image extension but non-image content should have None dims."""
        f = tmp_path / "fake.png"
        f.write_bytes(b"this is not a png")

        meta = _extract_metadata(f)
        assert meta["width"] is None
        assert meta["height"] is None


# ---------------------------------------------------------------------------
# _should_ignore
# ---------------------------------------------------------------------------

class TestShouldIgnore:

    def test_matches_exact_pattern(self):
        assert _should_ignore(Path("project/.git/config"), [".git"]) is True

    def test_matches_dot_prefix_pattern(self):
        """Pattern starting with '.' matches any part starting with '.'."""
        assert _should_ignore(Path("dir/.hidden/file"), ["."]) is True

    def test_no_match_returns_false(self):
        assert _should_ignore(Path("project/src/main.py"), ["node_modules", ".git"]) is False

    def test_nested_ignore(self):
        assert _should_ignore(Path("a/b/node_modules/c"), ["node_modules"]) is True

    def test_empty_patterns_never_ignores(self):
        assert _should_ignore(Path("anything/at/all"), []) is False

    def test_root_component_matches(self):
        assert _should_ignore(Path("__pycache__/something"), ["__pycache__"]) is True


# ---------------------------------------------------------------------------
# run() integration with mock supabase
# ---------------------------------------------------------------------------

class TestRunScan:

    def test_scan_discovers_new_files(self, tmp_path):
        """run() should find new image files and insert them via supabase."""
        # Create test images
        from PIL import Image
        img = Image.new("RGB", (100, 100), "blue")
        img_path = tmp_path / "photos" / "test.png"
        img_path.parent.mkdir()
        img.save(str(img_path))

        config = {
            "scan": {
                "paths": [str(tmp_path / "photos")],
                "extensions": [".png", ".jpg"],
                "ignore_patterns": [],
            }
        }

        # Mock supabase: no existing hashes, track inserts
        inserted = []
        mock_sb = MagicMock()

        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[])

        insert_chain = MagicMock()
        insert_chain.execute.return_value = MagicMock(data=[])

        def mock_table(name):
            t = MagicMock()
            t.select.return_value = select_chain
            def mock_insert(rows):
                inserted.extend(rows)
                return insert_chain
            t.insert = mock_insert
            return t

        mock_sb.table = mock_table

        result = run(config, mock_sb)

        assert result["new_files_count"] == 1
        assert len(result["file_hashes"]) == 1
        assert len(inserted) == 1
        assert inserted[0]["file_name"] == "test.png"
        assert inserted[0]["status"] == "new"

    def test_scan_skips_known_hashes(self, tmp_path):
        """Files whose hash already exists in DB should be skipped."""
        from PIL import Image
        img = Image.new("RGB", (50, 50), "green")
        img_path = tmp_path / "art" / "known.png"
        img_path.parent.mkdir()
        img.save(str(img_path))

        known_hash = _md5_hash(img_path)

        config = {
            "scan": {
                "paths": [str(tmp_path / "art")],
                "extensions": [".png"],
                "ignore_patterns": [],
            }
        }

        mock_sb = MagicMock()
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[{"file_hash": known_hash}])

        def mock_table(name):
            t = MagicMock()
            t.select.return_value = select_chain
            return t

        mock_sb.table = mock_table

        result = run(config, mock_sb)
        assert result["new_files_count"] == 0

    def test_scan_ignores_wrong_extensions(self, tmp_path):
        """Files with non-matching extensions should be skipped."""
        (tmp_path / "doc.txt").write_text("hello")

        config = {
            "scan": {
                "paths": [str(tmp_path)],
                "extensions": [".png", ".jpg"],
                "ignore_patterns": [],
            }
        }

        mock_sb = MagicMock()
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value = select_chain

        result = run(config, mock_sb)
        assert result["new_files_count"] == 0

    def test_scan_nonexistent_path(self, tmp_path):
        """Non-existent scan path should be skipped gracefully."""
        config = {
            "scan": {
                "paths": [str(tmp_path / "does_not_exist")],
                "extensions": [".png"],
                "ignore_patterns": [],
            }
        }

        mock_sb = MagicMock()
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value = select_chain

        result = run(config, mock_sb)
        assert result["new_files_count"] == 0
