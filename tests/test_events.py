"""Tests for engine.events — emit, consume, complete, fail cross-claw events."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from engine.events import (
    emit_event,
    consume_events,
    complete_event,
    fail_event,
    on_hero_uploaded,
    on_nft_minted,
    on_alpha_detected,
    on_blog_ready,
    EVENT_TRIGGERS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_supabase(insert_data=None, select_data=None):
    """Create a fluent Supabase mock with configurable responses."""
    mock_sb = MagicMock()

    # Insert chain
    insert_resp = MagicMock()
    insert_resp.data = insert_data or []
    insert_chain = MagicMock()
    insert_chain.execute.return_value = insert_resp

    # Select chain
    select_resp = MagicMock()
    select_resp.data = select_data or []
    select_chain = MagicMock()
    select_chain.eq.return_value = select_chain
    select_chain.order.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = select_resp

    # Update chain
    update_chain = MagicMock()
    update_eq = MagicMock()
    update_eq.execute.return_value = MagicMock(data=[])
    update_chain.eq.return_value = update_eq

    # Use a single MagicMock for the table return value so assert_called_with works
    table_obj = MagicMock()
    table_obj.insert.return_value = insert_chain
    table_obj.select.return_value = select_chain
    table_obj.update.return_value = update_chain
    mock_sb.table.return_value = table_obj

    return mock_sb


# ---------------------------------------------------------------------------
# emit_event
# ---------------------------------------------------------------------------

class TestEmitEvent:

    def test_known_event_type_inserts_row(self):
        """Known event types should insert into claw_events and return True."""
        mock_sb = _mock_supabase()
        result = emit_event(
            mock_sb,
            event_type="media.hero_uploaded",
            source_claw="media",
            payload={"asset_id": "abc", "guardian": "Lyria"},
        )
        assert result is True
        mock_sb.table.assert_called_with("claw_events")

    def test_unknown_event_type_returns_false(self):
        """Unknown event types should return False and not insert."""
        mock_sb = _mock_supabase()
        result = emit_event(
            mock_sb,
            event_type="nonexistent.event",
            source_claw="media",
            payload={},
        )
        assert result is False

    def test_emitted_event_has_correct_target(self):
        """The inserted event should target the claw specified in EVENT_TRIGGERS."""
        inserted_events = []

        mock_sb = MagicMock()
        insert_chain = MagicMock()
        insert_chain.execute.return_value = MagicMock(data=[])

        def track_insert(event):
            inserted_events.append(event)
            return insert_chain

        mock_sb.table.return_value.insert = track_insert

        emit_event(mock_sb, "forge.nft_minted", "forge", {"nft_id": "x"})

        assert len(inserted_events) == 1
        event = inserted_events[0]
        assert event["target_claw"] == "herald"
        assert event["action"] == "announce_mint"
        assert event["source_claw"] == "forge"
        assert event["status"] == "pending"

    def test_emit_handles_supabase_error_gracefully(self):
        """If supabase insert fails, emit_event should return False, not raise."""
        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.side_effect = RuntimeError("db down")

        result = emit_event(mock_sb, "media.hero_uploaded", "media", {})
        assert result is False

    def test_all_event_triggers_have_required_fields(self):
        """Every entry in EVENT_TRIGGERS should have target_claw, action, description."""
        for event_type, trigger in EVENT_TRIGGERS.items():
            assert "target_claw" in trigger, f"{event_type} missing target_claw"
            assert "action" in trigger, f"{event_type} missing action"
            assert "description" in trigger, f"{event_type} missing description"


# ---------------------------------------------------------------------------
# consume_events
# ---------------------------------------------------------------------------

class TestConsumeEvents:

    def test_returns_pending_events(self):
        """consume_events should return events and mark them as processing."""
        events = [
            {"id": "e1", "event_type": "media.hero_uploaded", "action": "draft_announcement"},
            {"id": "e2", "event_type": "forge.nft_minted", "action": "announce_mint"},
        ]
        mock_sb = _mock_supabase(select_data=events)
        result = consume_events(mock_sb, "herald", limit=5)

        assert len(result) == 2
        assert result[0]["id"] == "e1"

    def test_returns_empty_list_on_no_events(self):
        mock_sb = _mock_supabase(select_data=[])
        result = consume_events(mock_sb, "herald")
        assert result == []

    def test_marks_events_as_processing(self):
        """Each consumed event should be updated to status=processing."""
        events = [{"id": "e1"}, {"id": "e2"}]

        update_calls = []

        mock_sb = MagicMock()

        # select chain
        select_chain = MagicMock()
        select_chain.eq.return_value = select_chain
        select_chain.order.return_value = select_chain
        select_chain.limit.return_value = select_chain
        select_chain.execute.return_value = MagicMock(data=events)

        # update chain that tracks calls
        def mock_update(payload):
            update_calls.append(payload)
            eq_chain = MagicMock()
            eq_chain.execute.return_value = MagicMock()
            return MagicMock(eq=MagicMock(return_value=eq_chain))

        def mock_table(name):
            t = MagicMock()
            t.select.return_value = select_chain
            t.update = mock_update
            return t

        mock_sb.table = mock_table

        consume_events(mock_sb, "herald", limit=5)

        assert len(update_calls) == 2
        assert all(u["status"] == "processing" for u in update_calls)

    def test_handles_supabase_error_gracefully(self):
        """If supabase fails, consume_events should return empty list."""
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.side_effect = RuntimeError("db down")

        result = consume_events(mock_sb, "herald")
        assert result == []


# ---------------------------------------------------------------------------
# complete_event / fail_event
# ---------------------------------------------------------------------------

class TestCompleteEvent:

    def test_marks_event_completed(self):
        """complete_event should update status to 'completed' with result."""
        update_payloads = []

        mock_sb = MagicMock()
        update_eq = MagicMock()
        update_eq.execute.return_value = MagicMock()

        def track_update(payload):
            update_payloads.append(payload)
            return MagicMock(eq=MagicMock(return_value=update_eq))

        mock_sb.table.return_value.update = track_update

        complete_event(mock_sb, "e1", {"drafted": True})

        assert len(update_payloads) == 1
        assert update_payloads[0]["status"] == "completed"
        assert update_payloads[0]["result"] == {"drafted": True}
        assert "completed_at" in update_payloads[0]

    def test_complete_with_none_result(self):
        """Passing None result should default to empty dict."""
        update_payloads = []

        mock_sb = MagicMock()
        update_eq = MagicMock()
        update_eq.execute.return_value = MagicMock()

        def track_update(payload):
            update_payloads.append(payload)
            return MagicMock(eq=MagicMock(return_value=update_eq))

        mock_sb.table.return_value.update = track_update

        complete_event(mock_sb, "e1", None)
        assert update_payloads[0]["result"] == {}

    def test_complete_handles_error_gracefully(self):
        """complete_event should not raise on supabase failure."""
        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError("fail")

        # Should not raise
        complete_event(mock_sb, "e1", {})


class TestFailEvent:

    def test_marks_event_failed(self):
        """fail_event should update status to 'failed' with error in result."""
        update_payloads = []

        mock_sb = MagicMock()
        update_eq = MagicMock()
        update_eq.execute.return_value = MagicMock()

        def track_update(payload):
            update_payloads.append(payload)
            return MagicMock(eq=MagicMock(return_value=update_eq))

        mock_sb.table.return_value.update = track_update

        fail_event(mock_sb, "e1", "timeout occurred")

        assert len(update_payloads) == 1
        assert update_payloads[0]["status"] == "failed"
        assert update_payloads[0]["result"]["error"] == "timeout occurred"
        assert "completed_at" in update_payloads[0]

    def test_fail_handles_error_gracefully(self):
        """fail_event should not raise on supabase failure."""
        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError("fail")

        fail_event(mock_sb, "e1", "some error")


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

class TestEventHelpers:

    def test_on_hero_uploaded(self):
        """on_hero_uploaded should emit a media.hero_uploaded event."""
        mock_sb = _mock_supabase()
        on_hero_uploaded(mock_sb, asset_id="a1", guardian="Lyria", storage_url="https://cdn/a1.webp")
        # Verify insert was called on claw_events
        mock_sb.table.assert_called_with("claw_events")

    def test_on_nft_minted(self):
        mock_sb = _mock_supabase()
        on_nft_minted(mock_sb, nft_id="n1", token_id=42, tx_hash="0xabc", chain="base")
        mock_sb.table.assert_called_with("claw_events")

    def test_on_alpha_detected(self):
        mock_sb = _mock_supabase()
        on_alpha_detected(mock_sb, signal_id="s1", priority="high", content="Big opportunity")
        mock_sb.table.assert_called_with("claw_events")

    def test_on_alpha_detected_truncates_content(self):
        """Content longer than 500 chars should be truncated in the payload."""
        inserted_events = []

        mock_sb = MagicMock()
        insert_chain = MagicMock()
        insert_chain.execute.return_value = MagicMock(data=[])

        def track_insert(event):
            inserted_events.append(event)
            return insert_chain

        mock_sb.table.return_value.insert = track_insert

        long_content = "x" * 1000
        on_alpha_detected(mock_sb, signal_id="s1", priority="low", content=long_content)

        assert len(inserted_events) == 1
        assert len(inserted_events[0]["payload"]["content"]) == 500

    def test_on_blog_ready(self):
        mock_sb = _mock_supabase()
        on_blog_ready(mock_sb, title="New Post", slug="new-post", excerpt="First paragraph")
        mock_sb.table.assert_called_with("claw_events")
