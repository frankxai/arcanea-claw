"""Tests for engine.daemon — run_skill, run_pipeline, kwarg injection."""

from __future__ import annotations

import asyncio
import importlib
import types
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# We need to patch heavy imports before importing daemon
import sys

_real_import = importlib.import_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_daemon_metrics():
    """Reset daemon metrics between tests."""
    from engine import daemon
    daemon._metrics["skill_runs"].clear()
    daemon._metrics["skill_errors"].clear()
    daemon._metrics["skill_timing"].clear()
    daemon._metrics["pipeline_timing"].clear()
    yield


@pytest.fixture
def mock_config():
    return {
        "agent_id": "test-agent",
        "agent_name": "Test Agent",
        "skill_chain": ["alpha", "beta"],
        "scan": {},
    }


# ---------------------------------------------------------------------------
# run_skill
# ---------------------------------------------------------------------------

class TestRunSkill:
    """Test skill loading and execution via run_skill."""

    @pytest.mark.asyncio
    async def test_run_skill_success(self, mock_config):
        """A skill with a run(config) function should execute and return ok."""
        fake_mod = types.ModuleType("engine.skills.alpha")
        fake_mod.run = lambda config: {"items": 5}

        with patch("importlib.import_module", return_value=fake_mod):
            result = await _run_skill_helper("alpha", mock_config)

        assert result["skill"] == "alpha"
        assert result["status"] == "ok"
        assert result["result"] == {"items": 5}
        assert "elapsed_ms" in result

    @pytest.mark.asyncio
    async def test_run_skill_not_found(self, mock_config):
        """Missing module should return status=skipped."""
        with patch("importlib.import_module", side_effect=ModuleNotFoundError("nope")):
            result = await _run_skill_helper("missing_skill", mock_config)

        assert result["status"] == "skipped"
        assert result["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_run_skill_no_run_function(self, mock_config):
        """Module without run() should return skipped."""
        fake_mod = types.ModuleType("engine.skills.broken")
        # no run attribute

        with patch("importlib.import_module", return_value=fake_mod):
            result = await _run_skill_helper("broken", mock_config)

        assert result["status"] == "skipped"
        assert result["reason"] == "no_run_function"

    @pytest.mark.asyncio
    async def test_run_skill_exception(self, mock_config):
        """Skill that raises should return status=error."""
        fake_mod = types.ModuleType("engine.skills.bad")
        fake_mod.run = lambda config: (_ for _ in ()).throw(RuntimeError("kaboom"))

        # Need a real callable that raises
        def boom(config):
            raise RuntimeError("kaboom")

        fake_mod.run = boom

        with patch("importlib.import_module", return_value=fake_mod):
            result = await _run_skill_helper("bad", mock_config)

        assert result["status"] == "error"
        assert "kaboom" in result["error"]

    @pytest.mark.asyncio
    async def test_kwarg_injection_supabase(self, mock_config):
        """run_skill should inject supabase kwarg when the skill's run() accepts it."""
        received = {}

        def skill_run(config, supabase):
            received["config"] = config
            received["supabase"] = supabase
            return {"ok": True}

        fake_mod = types.ModuleType("engine.skills.db_skill")
        fake_mod.run = skill_run

        mock_sb = MagicMock(name="supabase")

        with patch("importlib.import_module", return_value=fake_mod):
            from engine.daemon import run_skill
            result = await run_skill("db_skill", mock_config, supabase=mock_sb)

        assert result["status"] == "ok"
        assert received["supabase"] is mock_sb

    @pytest.mark.asyncio
    async def test_kwarg_injection_gemini_model(self, mock_config):
        """run_skill should inject gemini_model when the skill accepts it."""
        received = {}

        def skill_run(config, gemini_model):
            received["gemini_model"] = gemini_model
            return {}

        fake_mod = types.ModuleType("engine.skills.ai_skill")
        fake_mod.run = skill_run

        mock_gemini = MagicMock(name="gemini")

        with patch("importlib.import_module", return_value=fake_mod):
            from engine.daemon import run_skill
            result = await run_skill("ai_skill", mock_config, supabase=None, gemini_model=mock_gemini)

        assert result["status"] == "ok"
        assert received["gemini_model"] is mock_gemini

    @pytest.mark.asyncio
    async def test_kwarg_injection_pipeline_stats(self, mock_config):
        """run_skill should inject pipeline_stats when the skill accepts it."""
        received = {}

        def skill_run(config, pipeline_stats):
            received["pipeline_stats"] = pipeline_stats
            return {}

        fake_mod = types.ModuleType("engine.skills.stat_skill")
        fake_mod.run = skill_run

        stats = {"scanned": 10}

        with patch("importlib.import_module", return_value=fake_mod):
            from engine.daemon import run_skill
            result = await run_skill("stat_skill", mock_config, supabase=None, pipeline_stats=stats)

        assert result["status"] == "ok"
        assert received["pipeline_stats"] is stats

    @pytest.mark.asyncio
    async def test_kwarg_injection_ignores_unknown_params(self, mock_config):
        """run_skill should NOT inject params the skill doesn't declare."""
        received_keys = []

        def skill_run(config):
            received_keys.extend(["config"])
            return {}

        fake_mod = types.ModuleType("engine.skills.simple")
        fake_mod.run = skill_run

        with patch("importlib.import_module", return_value=fake_mod):
            from engine.daemon import run_skill
            result = await run_skill(
                "simple", mock_config, supabase=MagicMock(), gemini_model=MagicMock(),
            )

        assert result["status"] == "ok"
        # skill only received config — no crash from extra kwargs
        assert received_keys == ["config"]


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Test pipeline execution and stat aggregation."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_all_skills(self, mock_config):
        """Pipeline should run each skill in the chain and return results."""
        call_order = []

        def make_mod(name):
            mod = types.ModuleType(f"engine.skills.{name}")
            def run(config):
                call_order.append(name)
                return {f"{name}_done": True}
            mod.run = run
            return mod

        modules = {"alpha": make_mod("alpha"), "beta": make_mod("beta")}

        def fake_import(path):
            if path.startswith("engine.skills."):
                name = path.split(".")[-1]
                if name in modules:
                    return modules[name]
                raise ModuleNotFoundError(path)
            return _real_import(path)

        with patch("importlib.import_module", side_effect=fake_import), \
             patch("engine.daemon._emit_pipeline_events"):
            from engine.daemon import run_pipeline
            results = await run_pipeline(mock_config, supabase=None)

        assert call_order == ["alpha", "beta"]
        assert len(results) == 2
        assert all(r["status"] == "ok" for r in results)

    @pytest.mark.asyncio
    async def test_pipeline_aggregates_stats(self, mock_config):
        """Stats from each skill's result should merge into aggregated_stats."""
        aggregated_snapshots = []

        def make_mod(name, result_dict):
            mod = types.ModuleType(f"engine.skills.{name}")
            def run(config, pipeline_stats=None):
                if pipeline_stats is not None:
                    aggregated_snapshots.append(dict(pipeline_stats))
                return result_dict
            mod.run = run
            return mod

        modules = {
            "alpha": make_mod("alpha", {"count": 10}),
            "beta": make_mod("beta", {"processed": 5}),
        }

        def fake_import(path):
            if path.startswith("engine.skills."):
                name = path.split(".")[-1]
                if name in modules:
                    return modules[name]
                raise ModuleNotFoundError(path)
            return _real_import(path)

        with patch("importlib.import_module", side_effect=fake_import), \
             patch("engine.daemon._emit_pipeline_events"):
            from engine.daemon import run_pipeline
            results = await run_pipeline(mock_config, supabase=None)

        # After alpha runs, beta should see alpha's results in pipeline_stats
        assert len(aggregated_snapshots) == 2
        # First skill sees empty stats
        assert aggregated_snapshots[0] == {}
        # Second skill sees alpha's results
        assert aggregated_snapshots[1] == {"count": 10}

    @pytest.mark.asyncio
    async def test_pipeline_handles_mixed_results(self):
        """Pipeline should continue even if one skill fails or is skipped."""
        config = {
            "agent_id": "test",
            "skill_chain": ["good", "missing", "bad"],
        }

        good_mod = types.ModuleType("engine.skills.good")
        good_mod.run = lambda config: {"ok": True}

        bad_mod = types.ModuleType("engine.skills.bad")
        def bad_run(config):
            raise RuntimeError("oops")
        bad_mod.run = bad_run

        def fake_import(path):
            if path.startswith("engine.skills."):
                name = path.split(".")[-1]
                if name == "good":
                    return good_mod
                if name == "bad":
                    return bad_mod
                raise ModuleNotFoundError(path)
            return _real_import(path)

        with patch("importlib.import_module", side_effect=fake_import), \
             patch("engine.daemon._emit_pipeline_events"):
            from engine.daemon import run_pipeline
            results = await run_pipeline(config, supabase=None)

        statuses = [r["status"] for r in results]
        assert statuses == ["ok", "skipped", "error"]

    @pytest.mark.asyncio
    async def test_pipeline_tracks_timing(self, mock_config):
        """Pipeline should record timing in _metrics['pipeline_timing']."""
        mod = types.ModuleType("engine.skills.alpha")
        mod.run = lambda config: {}

        mod2 = types.ModuleType("engine.skills.beta")
        mod2.run = lambda config: {}

        modules = {"alpha": mod, "beta": mod2}

        def fake_import(path):
            if path.startswith("engine.skills."):
                name = path.split(".")[-1]
                if name in modules:
                    return modules[name]
                raise ModuleNotFoundError(path)
            return _real_import(path)

        with patch("importlib.import_module", side_effect=fake_import), \
             patch("engine.daemon._emit_pipeline_events"):
            from engine.daemon import run_pipeline, _metrics
            await run_pipeline(mock_config, supabase=None)

        assert len(_metrics["pipeline_timing"]) >= 1
        assert _metrics["pipeline_timing"][-1] >= 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_skill_helper(skill_name: str, config: dict, **kwargs):
    """Convenience wrapper around run_skill with defaults."""
    from engine.daemon import run_skill
    return await run_skill(
        skill_name,
        config,
        supabase=kwargs.get("supabase"),
        gemini_model=kwargs.get("gemini_model"),
        pipeline_stats=kwargs.get("pipeline_stats"),
    )
