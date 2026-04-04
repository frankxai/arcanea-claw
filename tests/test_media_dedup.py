"""Tests for engine.skills.media_dedup — duplicate detection and rejection."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from engine.skills.media_dedup import run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_supabase_mock(assets: list[dict], update_tracker: list | None = None):
    """Build a mock supabase that returns ``assets`` for the select query
    and optionally tracks update calls.
    """
    mock_sb = MagicMock()

    # select chain
    select_chain = MagicMock()
    select_chain.neq.return_value = select_chain
    select_chain.order.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=assets)

    # update chain (tracks which IDs get rejected)
    update_chain = MagicMock()
    update_eq = MagicMock()
    update_eq.execute.return_value = MagicMock(data=[])
    update_chain.eq = MagicMock(return_value=update_eq)

    if update_tracker is not None:
        original_eq = update_chain.eq
        def tracking_eq(col, val):
            update_tracker.append(val)
            return update_eq
        update_chain.eq = tracking_eq

    def mock_table(name):
        t = MagicMock()
        t.select.return_value = select_chain
        t.update.return_value = update_chain
        return t

    mock_sb.table = mock_table
    return mock_sb


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMediaDedup:

    def test_no_assets_returns_zero(self):
        """Empty DB should return 0 duplicates."""
        mock_sb = _build_supabase_mock([])
        result = run({}, mock_sb)
        assert result["duplicates_found"] == 0

    def test_no_duplicates_returns_zero(self):
        """All unique hashes should produce 0 duplicates."""
        assets = [
            {"id": "a1", "file_hash": "hash_a", "quality_score": 80, "created_at": "2026-01-01", "tags": [], "status": "new"},
            {"id": "a2", "file_hash": "hash_b", "quality_score": 90, "created_at": "2026-01-02", "tags": [], "status": "new"},
        ]
        mock_sb = _build_supabase_mock(assets)
        result = run({}, mock_sb)
        assert result["duplicates_found"] == 0

    def test_keeps_highest_scored_asset(self):
        """Among duplicates, the one with the highest quality_score should be kept."""
        rejected_ids = []
        assets = [
            {"id": "a1", "file_hash": "same", "quality_score": 50, "created_at": "2026-01-01", "tags": [], "status": "new"},
            {"id": "a2", "file_hash": "same", "quality_score": 90, "created_at": "2026-01-02", "tags": [], "status": "new"},
            {"id": "a3", "file_hash": "same", "quality_score": 70, "created_at": "2026-01-03", "tags": [], "status": "new"},
        ]
        mock_sb = _build_supabase_mock(assets, update_tracker=rejected_ids)
        result = run({}, mock_sb)

        assert result["duplicates_found"] == 2
        # a2 has highest score (90), so a1 and a3 should be rejected
        assert "a2" not in rejected_ids
        assert "a1" in rejected_ids
        assert "a3" in rejected_ids

    def test_keeps_earliest_when_scores_equal(self):
        """Among duplicates with equal scores, the earliest created_at should be kept."""
        rejected_ids = []
        assets = [
            {"id": "early", "file_hash": "dup", "quality_score": 80, "created_at": "2026-01-01", "tags": [], "status": "new"},
            {"id": "late", "file_hash": "dup", "quality_score": 80, "created_at": "2026-06-01", "tags": [], "status": "new"},
        ]
        mock_sb = _build_supabase_mock(assets, update_tracker=rejected_ids)
        result = run({}, mock_sb)

        assert result["duplicates_found"] == 1
        assert "late" in rejected_ids
        assert "early" not in rejected_ids

    def test_duplicate_tag_added(self):
        """Rejected assets should get a 'duplicate' tag."""
        assets = [
            {"id": "keep", "file_hash": "x", "quality_score": 100, "created_at": "2026-01-01", "tags": ["hero"], "status": "new"},
            {"id": "dup", "file_hash": "x", "quality_score": 10, "created_at": "2026-01-02", "tags": ["art"], "status": "new"},
        ]

        update_payloads = []

        mock_sb = MagicMock()
        select_chain = MagicMock()
        select_chain.neq.return_value = select_chain
        select_chain.order.return_value = select_chain
        select_chain.execute.return_value = MagicMock(data=assets)

        update_eq = MagicMock()
        update_eq.execute.return_value = MagicMock(data=[])

        def track_update(payload):
            update_payloads.append(payload)
            chain = MagicMock()
            chain.eq.return_value = update_eq
            return chain

        def mock_table(name):
            t = MagicMock()
            t.select.return_value = select_chain
            t.update = track_update
            return t

        mock_sb.table = mock_table

        result = run({}, mock_sb)
        assert result["duplicates_found"] == 1

        # The update payload should contain "duplicate" in tags
        assert len(update_payloads) == 1
        assert "duplicate" in update_payloads[0]["tags"]
        assert update_payloads[0]["status"] == "rejected"
        assert update_payloads[0]["metadata"]["duplicate_of"] == "keep"

    def test_handles_null_file_hash(self):
        """Assets with None file_hash should be silently skipped."""
        assets = [
            {"id": "a1", "file_hash": None, "quality_score": 80, "created_at": "2026-01-01", "tags": [], "status": "new"},
            {"id": "a2", "file_hash": "unique", "quality_score": 90, "created_at": "2026-01-02", "tags": [], "status": "new"},
        ]
        mock_sb = _build_supabase_mock(assets)
        result = run({}, mock_sb)
        assert result["duplicates_found"] == 0

    def test_multiple_duplicate_groups(self):
        """Multiple groups of duplicates should all be processed."""
        rejected_ids = []
        assets = [
            # Group 1: hash_a
            {"id": "g1_keep", "file_hash": "hash_a", "quality_score": 100, "created_at": "2026-01-01", "tags": [], "status": "new"},
            {"id": "g1_dup", "file_hash": "hash_a", "quality_score": 50, "created_at": "2026-01-02", "tags": [], "status": "new"},
            # Group 2: hash_b
            {"id": "g2_keep", "file_hash": "hash_b", "quality_score": 90, "created_at": "2026-01-01", "tags": [], "status": "new"},
            {"id": "g2_dup1", "file_hash": "hash_b", "quality_score": 30, "created_at": "2026-01-02", "tags": [], "status": "new"},
            {"id": "g2_dup2", "file_hash": "hash_b", "quality_score": 20, "created_at": "2026-01-03", "tags": [], "status": "new"},
            # Unique
            {"id": "unique", "file_hash": "hash_c", "quality_score": 80, "created_at": "2026-01-01", "tags": [], "status": "new"},
        ]
        mock_sb = _build_supabase_mock(assets, update_tracker=rejected_ids)
        result = run({}, mock_sb)

        assert result["duplicates_found"] == 3
        assert "g1_dup" in rejected_ids
        assert "g2_dup1" in rejected_ids
        assert "g2_dup2" in rejected_ids
        assert "g1_keep" not in rejected_ids
        assert "g2_keep" not in rejected_ids
        assert "unique" not in rejected_ids

    def test_existing_duplicate_tag_not_doubled(self):
        """If a duplicate already has the 'duplicate' tag, it should not be added again."""
        assets = [
            {"id": "keep", "file_hash": "x", "quality_score": 100, "created_at": "2026-01-01", "tags": [], "status": "new"},
            {"id": "dup", "file_hash": "x", "quality_score": 10, "created_at": "2026-01-02", "tags": ["duplicate"], "status": "new"},
        ]

        update_payloads = []

        mock_sb = MagicMock()
        select_chain = MagicMock()
        select_chain.neq.return_value = select_chain
        select_chain.order.return_value = select_chain
        select_chain.execute.return_value = MagicMock(data=assets)

        update_eq = MagicMock()
        update_eq.execute.return_value = MagicMock(data=[])

        def track_update(payload):
            update_payloads.append(payload)
            chain = MagicMock()
            chain.eq.return_value = update_eq
            return chain

        def mock_table(name):
            t = MagicMock()
            t.select.return_value = select_chain
            t.update = track_update
            return t

        mock_sb.table = mock_table

        run({}, mock_sb)

        # Should still have exactly one "duplicate" tag, not two
        assert update_payloads[0]["tags"].count("duplicate") == 1
