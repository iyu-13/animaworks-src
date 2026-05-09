# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for F5: auto-restart mechanism on streaming errors in PendingTaskExecutor."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.supervisor.pending_executor import (
    PendingTaskExecutor,
    TaskExecError,
    _MAX_AUTO_RESTARTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_anima_dir(tmp_path: Path) -> Path:
    """Create a minimal anima directory structure."""
    anima_dir = tmp_path / "animas" / "test_anima"
    (anima_dir / "state" / "pending").mkdir(parents=True)
    (anima_dir / "state" / "task_results").mkdir(parents=True)
    return anima_dir


@pytest.fixture
def mock_anima(tmp_anima_dir: Path) -> MagicMock:
    """Create a mock Anima object."""
    anima = MagicMock()
    anima.name = "test_anima"
    anima._anima_dir = tmp_anima_dir
    anima._status_slots = {"background": "idle"}
    anima._task_slots = {"background": ""}
    anima._mark_busy_start = MagicMock()
    anima.messenger = MagicMock()
    anima.messenger.send = MagicMock()
    return anima


@pytest.fixture
def executor(mock_anima: MagicMock, tmp_anima_dir: Path) -> PendingTaskExecutor:
    """Create a PendingTaskExecutor with mocked internals."""
    with patch(
        "core.supervisor.pending_executor.PendingTaskExecutor.__init__",
        return_value=None,
    ):
        exec_ = PendingTaskExecutor.__new__(PendingTaskExecutor)

    exec_._anima = mock_anima
    exec_._anima_name = "test_anima"
    exec_._anima_dir = tmp_anima_dir
    exec_._sync_task_queue = MagicMock()
    exec_._write_failed_result = MagicMock()
    exec_.wake = MagicMock()
    return exec_


def _make_task_desc(
    task_id: str = "task_abc123",
    reply_to: str | None = None,
    auto_restart_count: int = 0,
    original_task_id: str | None = None,
) -> dict:
    desc: dict = {
        "task_id": task_id,
        "title": "Test task",
        "description": "Test description",
        "_auto_restart_count": auto_restart_count,
    }
    if reply_to:
        desc["reply_to"] = reply_to
    if original_task_id:
        desc["_original_task_id"] = original_task_id
    return desc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_error_triggers_auto_restart(
    executor: PendingTaskExecutor,
    tmp_anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TaskExecError('streaming error') should write a restart JSON to pending/."""
    monkeypatch.setattr(
        "core.supervisor.pending_executor._AUTO_RESTART_BASE_DELAY_S", 0.1
    )

    task_id = "task_stream_err_001"
    task_desc = _make_task_desc(task_id=task_id, auto_restart_count=0)

    streaming_exc = TaskExecError("streaming error occurred")

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock, side_effect=streaming_exc):
        await executor._execute_llm_task(task_desc)

    # Wait for the delayed restart coroutine to write the file
    await asyncio.sleep(0.3)

    pending_dir = tmp_anima_dir / "state" / "pending"
    restart_files = list(pending_dir.glob(f"restart_{task_id}_*.json"))
    assert len(restart_files) == 1, f"Expected 1 restart file, got {restart_files}"

    data = json.loads(restart_files[0].read_text(encoding="utf-8"))
    assert data["task_id"] == task_id
    assert data["_auto_restart_count"] == 1


@pytest.mark.asyncio
async def test_non_streaming_error_no_restart(
    executor: PendingTaskExecutor,
    tmp_anima_dir: Path,
) -> None:
    """A plain Exception (not a streaming error) must NOT trigger auto-restart."""
    task_id = "task_plain_err_001"
    task_desc = _make_task_desc(task_id=task_id, auto_restart_count=0)

    plain_exc = RuntimeError("some other error")

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock, side_effect=plain_exc):
        await executor._execute_llm_task(task_desc)

    # No restart file should be created
    pending_dir = tmp_anima_dir / "state" / "pending"
    restart_files = list(pending_dir.glob(f"restart_{task_id}_*.json"))
    assert len(restart_files) == 0, "Expected no restart file for non-streaming error"

    # Normal failure handling should have run
    executor._write_failed_result.assert_called_once()
    args = executor._sync_task_queue.call_args_list
    statuses = [call.args[1] for call in args]
    assert "failed" in statuses


@pytest.mark.asyncio
async def test_max_restart_exceeded_uses_normal_failure(
    executor: PendingTaskExecutor,
    tmp_anima_dir: Path,
) -> None:
    """When _auto_restart_count >= _MAX_AUTO_RESTARTS, normal failure runs instead."""
    task_id = "task_max_restart_001"
    task_desc = _make_task_desc(task_id=task_id, auto_restart_count=_MAX_AUTO_RESTARTS)

    streaming_exc = TaskExecError("streaming error again")

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock, side_effect=streaming_exc):
        await executor._execute_llm_task(task_desc)

    # No restart file should be created (max exceeded)
    pending_dir = tmp_anima_dir / "state" / "pending"
    restart_files = list(pending_dir.glob(f"restart_{task_id}_*.json"))
    assert len(restart_files) == 0, "Expected no restart file when max retries exceeded"

    # Normal failure handling should have run
    executor._write_failed_result.assert_called_once()
    args = executor._sync_task_queue.call_args_list
    statuses = [call.args[1] for call in args]
    assert "failed" in statuses


@pytest.mark.asyncio
async def test_restart_increments_count(
    executor: PendingTaskExecutor,
    tmp_anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """restart JSON must have _auto_restart_count incremented by 1."""
    monkeypatch.setattr(
        "core.supervisor.pending_executor._AUTO_RESTART_BASE_DELAY_S", 0.1
    )

    task_id = "task_incr_001"
    task_desc = _make_task_desc(task_id=task_id, auto_restart_count=0)

    streaming_exc = TaskExecError("streaming error")

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock, side_effect=streaming_exc):
        await executor._execute_llm_task(task_desc)

    await asyncio.sleep(0.3)

    pending_dir = tmp_anima_dir / "state" / "pending"
    restart_files = list(pending_dir.glob(f"restart_{task_id}_*.json"))
    assert len(restart_files) == 1

    data = json.loads(restart_files[0].read_text(encoding="utf-8"))
    assert data["_auto_restart_count"] == 1  # 0 + 1


@pytest.mark.asyncio
async def test_restart_preserves_original_task_id(
    executor: PendingTaskExecutor,
    tmp_anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_original_task_id must be the first task's ID, not changed on re-runs."""
    monkeypatch.setattr(
        "core.supervisor.pending_executor._AUTO_RESTART_BASE_DELAY_S", 0.1
    )

    task_id = "task_orig_001"
    task_desc = _make_task_desc(task_id=task_id, auto_restart_count=0)
    # No _original_task_id on first run — should be set to task_id itself

    streaming_exc = TaskExecError("streaming error")

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock, side_effect=streaming_exc):
        await executor._execute_llm_task(task_desc)

    await asyncio.sleep(0.3)

    pending_dir = tmp_anima_dir / "state" / "pending"
    restart_files = list(pending_dir.glob(f"restart_{task_id}_*.json"))
    assert len(restart_files) == 1

    data = json.loads(restart_files[0].read_text(encoding="utf-8"))
    assert data["_original_task_id"] == task_id
