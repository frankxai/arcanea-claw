"""Shared fixtures for ArcaneaClaw tests."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest


class _SupabaseChain:
    """Fluent mock that supports .table().select().eq().execute() chains."""

    def __init__(self, data=None):
        self._data = data if data is not None else []

    def table(self, name: str):
        return self

    def select(self, *args, **kwargs):
        return self

    def insert(self, rows):
        return self

    def update(self, payload):
        return self

    def upsert(self, payload, **kwargs):
        return self

    def eq(self, col, val):
        return self

    def neq(self, col, val):
        return self

    def gte(self, col, val):
        return self

    def order(self, col, **kwargs):
        return self

    def limit(self, n):
        return self

    def is_(self, col, val):
        return self

    def execute(self):
        resp = MagicMock()
        resp.data = self._data
        return resp


@pytest.fixture
def mock_supabase():
    """Return a fluent-chain mock Supabase client with empty data by default."""
    return _SupabaseChain()


def make_supabase(data):
    """Create a fluent-chain Supabase mock that returns ``data`` on every execute()."""
    return _SupabaseChain(data)
