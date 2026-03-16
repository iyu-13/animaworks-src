# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Tests for current_state.md bloat prevention.

Issue: 20260312_current-task-md-bloat-prevention
Issue #114: Working memory separated from task registry; _prune_auto_detected_resolved removed.

Covers:
- HB prompt cleanup instruction injection
- _update_state_from_summary() routes to task_queue.jsonl
- _enforce_state_size_limit() hard-trim
"""

from unittest.mock import MagicMock, patch

import pytest

from core.memory.conversation import (
    ConversationMemory,
    ParsedSessionSummary,
)
from core.schemas import ModelConfig
from tests.helpers.filesystem import create_anima_dir, create_test_data_dir

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from core.config import invalidate_cache
    from core.paths import _prompt_cache

    d = create_test_data_dir(tmp_path)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(d))
    invalidate_cache()
    _prompt_cache.clear()
    yield d
    invalidate_cache()
    _prompt_cache.clear()


@pytest.fixture
def anima_dir(data_dir):
    return create_anima_dir(data_dir, "test-bloat")


@pytest.fixture
def model_config():
    return ModelConfig(
        model="claude-sonnet-4-6",
        fallback_model="claude-sonnet-4-6",
        max_turns=5,
    )


@pytest.fixture
def conv_memory(anima_dir, model_config):
    return ConversationMemory(anima_dir, model_config)


# ── _update_state_from_summary (Issue #114: task_queue routing) ────


class TestUpdateStateFromSummary:
    """Tests that _update_state_from_summary() routes to task_queue.jsonl."""

    def test_resolved_items_mark_task_done(self, conv_memory, anima_dir):
        """Resolved items update matching task_queue entries to done."""
        from core.memory.manager import MemoryManager
        from core.memory.task_queue import TaskQueueManager

        memory_mgr = MemoryManager(anima_dir)
        tqm = TaskQueueManager(anima_dir)
        tqm.add_task(
            source="anima",
            original_instruction="Fix login bug",
            assignee=anima_dir.name,
            summary="Fix login bug",
        )
        task_id = list(tqm._load_all().keys())[0]

        parsed = ParsedSessionSummary(
            title="test",
            episode_body="test body",
            resolved_items=["Fix login bug"],
            new_tasks=[],
            current_status="",
            has_state_changes=True,
        )

        conv_memory._update_state_from_summary(memory_mgr, parsed)

        task = tqm.get_task_by_id(task_id)
        assert task is not None
        assert task.status == "done"

    def test_new_tasks_added_to_queue(self, conv_memory, anima_dir):
        """New tasks are registered in task_queue.jsonl."""
        from core.memory.manager import MemoryManager
        from core.memory.task_queue import TaskQueueManager

        memory_mgr = MemoryManager(anima_dir)
        tqm = TaskQueueManager(anima_dir)

        parsed = ParsedSessionSummary(
            title="test",
            episode_body="test body",
            resolved_items=[],
            new_tasks=["Implement feature X", "Review PR #42"],
            current_status="",
            has_state_changes=True,
        )

        conv_memory._update_state_from_summary(memory_mgr, parsed)

        pending = tqm.get_pending()
        summaries = [t.summary for t in pending]
        assert "Implement feature X" in summaries
        assert "Review PR #42" in summaries

    def test_current_state_unchanged(self, conv_memory, anima_dir):
        """current_state.md is NOT modified by _update_state_from_summary."""
        from core.memory.manager import MemoryManager

        memory_mgr = MemoryManager(anima_dir)
        original_state = "## 現在の状態\nWorking on something."
        (anima_dir / "state" / "current_state.md").write_text(original_state, encoding="utf-8")

        parsed = ParsedSessionSummary(
            title="test",
            episode_body="test body",
            resolved_items=["item"],
            new_tasks=["new task"],
            current_status="",
            has_state_changes=True,
        )

        conv_memory._update_state_from_summary(memory_mgr, parsed)

        assert (anima_dir / "state" / "current_state.md").read_text(encoding="utf-8") == original_state


# ── HB cleanup instruction injection ─────────────────────────


class TestHeartbeatCleanupInstruction:
    """Tests for _build_heartbeat_prompt() cleanup instruction injection."""

    @pytest.fixture
    def mock_heartbeat_mixin(self, anima_dir):
        """Create a minimal HeartbeatMixin-like object for testing."""
        from core._anima_heartbeat import HeartbeatMixin

        mixin = MagicMock(spec=HeartbeatMixin)
        mixin._CURRENT_STATE_CLEANUP_THRESHOLD = HeartbeatMixin._CURRENT_STATE_CLEANUP_THRESHOLD
        mixin.name = "test-bloat"
        mixin.anima_dir = anima_dir

        memory_mock = MagicMock()
        mixin.memory = memory_mock

        return mixin

    @pytest.mark.asyncio
    async def test_cleanup_injected_when_over_threshold(self, mock_heartbeat_mixin, anima_dir):
        """Cleanup instruction is injected when current_state.md exceeds threshold."""
        from core._anima_heartbeat import HeartbeatMixin

        big_state = "x" * 4000
        mock_heartbeat_mixin.memory.read_current_state.return_value = big_state
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=[])

        with patch("core._anima_heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        cleanup_parts = [p for p in parts if "current_state.md" in p and ("圧縮" in p or "cleanup" in p)]
        assert len(cleanup_parts) == 1
        assert "4000" in cleanup_parts[0]

    @pytest.mark.asyncio
    async def test_no_cleanup_when_under_threshold(self, mock_heartbeat_mixin):
        """No cleanup instruction when current_state.md is under threshold."""
        from core._anima_heartbeat import HeartbeatMixin

        small_state = "x" * 500
        mock_heartbeat_mixin.memory.read_current_state.return_value = small_state
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=[])

        with patch("core._anima_heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        cleanup_parts = [p for p in parts if "圧縮" in p or "cleanup" in p]
        assert len(cleanup_parts) == 0

    @pytest.mark.asyncio
    async def test_no_cleanup_at_exact_threshold(self, mock_heartbeat_mixin):
        """No cleanup instruction when current_state.md is exactly at threshold."""
        from core._anima_heartbeat import HeartbeatMixin

        exact_state = "x" * 3000
        mock_heartbeat_mixin.memory.read_current_state.return_value = exact_state
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=[])

        with patch("core._anima_heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        cleanup_parts = [p for p in parts if "圧縮" in p or "cleanup" in p]
        assert len(cleanup_parts) == 0


# ── Builder truncation (existing defense) ─────────────────────


class TestBuilderTruncation:
    """Verify builder.py's existing _CURRENT_STATE_MAX_CHARS defense."""

    def test_constant_exists(self):
        """_CURRENT_STATE_MAX_CHARS is defined and equals 3000."""
        from core.prompt.builder import _CURRENT_STATE_MAX_CHARS

        assert _CURRENT_STATE_MAX_CHARS == 3000
