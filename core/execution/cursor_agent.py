from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Mode D executor: cursor-agent CLI wrapper.

Runs cursor-agent as a subprocess with --output-format stream-json --stream-partial-output
and parses NDJSON output. Integrates with AnimaWorks MCP server for tool access.
"""

import asyncio
import json
import logging
import os
import shutil
import signal
from pathlib import Path
from typing import Any

from core.execution.base import (
    BaseExecutor,
    ExecutionResult,
    ToolCallRecord,
    _truncate_for_record,
)
from core.i18n import t
from core.memory.shortterm import ShortTermMemory
from core.prompt.context import ContextTracker
from core.schemas import ImageData, ModelConfig

logger = logging.getLogger("animaworks.execution.cursor_agent")

__all__ = [
    "CursorAgentExecutor",
    "is_cursor_agent_available",
    "_RESUMABLE_TRIGGERS",
    "_chat_id_path",
    "_clear_chat_id",
    "_load_chat_id",
    "_resolve_session_type",
    "_save_chat_id",
]

# ── Constants ───────────────────────────────────────────────────

_CURSOR_AGENT_BINARY_NAMES = ("agent", "cursor-agent", "cursor")
_DEFAULT_TIMEOUT_SECONDS = 600
_GRACEFUL_KILL_WAIT = 3.0
_RESUMABLE_TRIGGERS = frozenset({"chat"})

# ── Binary discovery ───────────────────────────────────────────


def _find_cursor_agent_binary() -> str | None:
    """Return path to cursor-agent binary, or None if not found."""
    for name in _CURSOR_AGENT_BINARY_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def is_cursor_agent_available() -> bool:
    """Return True when cursor-agent CLI is available on PATH."""
    return _find_cursor_agent_binary() is not None


# ── Session (chat ID) persistence ─────────────────────────────


def _resolve_session_type(trigger: str) -> str:
    """Map a trigger string to its session type for chatId isolation."""
    if not trigger or trigger.startswith("chat"):
        return "chat"
    return trigger.split(":")[0]


def _chat_id_path(anima_dir: Path, session_type: str, thread_id: str = "default") -> Path:
    base = anima_dir / "shortterm" / session_type
    if thread_id != "default":
        return base / thread_id / "cursor_chat_id.txt"
    return base / "cursor_chat_id.txt"


def _save_chat_id(anima_dir: Path, chat_id: str, session_type: str, thread_id: str = "default") -> None:
    p = _chat_id_path(anima_dir, session_type, thread_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(chat_id, encoding="utf-8")


def _load_chat_id(anima_dir: Path, session_type: str, thread_id: str = "default") -> str | None:
    p = _chat_id_path(anima_dir, session_type, thread_id)
    if p.is_file():
        cid = p.read_text(encoding="utf-8").strip()
        return cid or None
    return None


def _clear_chat_id(anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
    p = _chat_id_path(anima_dir, session_type, thread_id)
    p.unlink(missing_ok=True)


# ── Executor ───────────────────────────────────────────────────


class CursorAgentExecutor(BaseExecutor):
    """Execute via cursor-agent CLI (Mode D).

    Spawns cursor-agent as a subprocess with NDJSON streaming output.
    MCP integration with core/mcp/server.py provides AnimaWorks tools.
    """

    @property
    def supports_streaming(self) -> bool:  # noqa: D102
        return False

    def __init__(
        self,
        model_config: ModelConfig,
        anima_dir: Path,
        tool_registry: list[str] | None = None,
        personal_tools: dict[str, str] | None = None,
        interrupt_event: asyncio.Event | None = None,
    ) -> None:
        super().__init__(model_config, anima_dir, interrupt_event=interrupt_event)
        self._tool_registry = tool_registry or []
        self._personal_tools = personal_tools or {}
        self._workspace = anima_dir / ".cursor-workspace"

    # ── Helpers ─────────────────────────────────────────────────

    def _find_binary(self) -> str | None:
        """Return path to cursor-agent binary, or None."""
        return _find_cursor_agent_binary()

    def _ensure_workspace(self) -> None:
        """Create workspace and .cursor directories."""
        self._workspace.mkdir(parents=True, exist_ok=True)
        (self._workspace / ".cursor").mkdir(parents=True, exist_ok=True)

    def _write_mcp_config(self) -> None:
        """Write .cursor/mcp.json with AnimaWorks MCP server config."""
        import sys

        from core.paths import PROJECT_DIR

        mcp_dir = self._workspace / ".cursor"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        mcp_path = mcp_dir / "mcp.json"
        config = {
            "mcpServers": {
                "aw": {
                    "command": sys.executable,
                    "args": ["-m", "core.mcp.server"],
                    "env": {
                        "ANIMAWORKS_ANIMA_DIR": str(self._anima_dir),
                        "ANIMAWORKS_PROJECT_DIR": str(PROJECT_DIR),
                        "PYTHONPATH": str(PROJECT_DIR),
                        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    },
                }
            }
        }
        mcp_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _resolve_cursor_model(self) -> str:
        """Strip cursor/ prefix from model name."""
        model = self._model_config.model
        if model.startswith("cursor/"):
            return model[len("cursor/") :]
        return model

    def _build_command(self, prompt: str, *, resume_chat_id: str | None = None) -> list[str]:
        """Build CLI command for cursor-agent."""
        binary = self._find_binary()
        if not binary:
            return []
        cmd = [
            binary,
            "-p",
            "--force",
            "--trust",
            "--approve-mcps",
            "--workspace",
            str(self._workspace),
            "--model",
            self._resolve_cursor_model(),
            "--output-format",
            "stream-json",
            "--stream-partial-output",
        ]
        if resume_chat_id:
            cmd.extend(["--resume", resume_chat_id])
        cmd.append(prompt)
        return cmd

    def _build_env(self) -> dict[str, str]:
        """Build environment for subprocess.

        cursor-agent authenticates via ``agent login`` (stored in
        ``~/.cursor-agent/``).  We do NOT inject ``CURSOR_API_KEY`` from
        AnimaWorks credentials — only pass it through if it's already
        set in the host environment.
        """
        env = dict(os.environ)
        for key in ("PATH", "HOME", "LANG"):
            if key not in env:
                val = os.environ.get(key)
                if val:
                    env[key] = val
        return env

    def _parse_ndjson_event(self, stdout_line: str) -> dict[str, Any] | None:
        """Parse a single NDJSON line. Return dict or None on parse error."""
        line = stdout_line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse NDJSON line: %s", e)
            return None

    async def _kill_process(self, proc: asyncio.subprocess.Process, timeout: float = _GRACEFUL_KILL_WAIT) -> None:
        """Graceful kill: SIGTERM → wait → SIGKILL."""
        if proc.returncode is not None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
            await asyncio.sleep(timeout)
        except ProcessLookupError:
            return
        if proc.returncode is not None:
            return
        try:
            proc.kill()
        except ProcessLookupError:
            pass

    def _extract_tool_record(self, tc: dict[str, Any]) -> ToolCallRecord | None:
        """Parse tool_call event data into ToolCallRecord."""
        tool_name = ""
        tool_id = tc.get("id", "") or tc.get("tool_call_id", "")
        input_summary = ""
        result_summary = ""
        is_error = False

        for key in ("readToolCall", "writeToolCall", "editToolCall"):
            if key in tc:
                tool_name = key.replace("ToolCall", "").lower()
                if tool_name == "read":
                    tool_name = "Read"
                elif tool_name == "write":
                    tool_name = "Write"
                elif tool_name == "edit":
                    tool_name = "Edit"
                args = tc.get(key, {})
                if isinstance(args, dict):
                    input_summary = _truncate_for_record(str(args), 500)
                break

        if not tool_name and "function" in tc:
            fn = tc["function"]
            if isinstance(fn, dict):
                tool_name = fn.get("name", "") or "unknown"
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    input_summary = _truncate_for_record(args, 500)
                else:
                    input_summary = _truncate_for_record(str(args), 500)
            else:
                tool_name = str(fn)

        if not tool_name:
            tool_name = tc.get("name", "unknown")

        if tool_name.startswith("mcp__aw__"):
            tool_name = tool_name[len("mcp__aw__") :]

        result = tc.get("result") or tc.get("output") or tc.get("content")
        if result is not None:
            result_summary = _truncate_for_record(str(result), 500)
        if tc.get("is_error") or tc.get("error"):
            is_error = True

        return ToolCallRecord(
            tool_name=tool_name,
            tool_id=str(tool_id),
            input_summary=input_summary,
            result_summary=result_summary,
            is_error=is_error,
        )

    # ── Execution ───────────────────────────────────────────────

    async def execute(
        self,
        prompt: str,
        system_prompt: str = "",
        tracker: ContextTracker | None = None,
        shortterm: ShortTermMemory | None = None,
        trigger: str = "",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        max_turns_override: int | None = None,
        thread_id: str = "default",
    ) -> ExecutionResult:
        """Run cursor-agent subprocess and parse NDJSON output.

        For resumable triggers (currently ``chat`` only), persists the
        cursor-agent session ID to disk and passes ``--resume <chatId>``
        on subsequent calls.  If resume fails the chatId is cleared and
        a fresh session is attempted once.
        """
        if self._check_interrupted():
            return ExecutionResult(text="[Session interrupted by user]")

        binary = self._find_binary()
        if not binary:
            return ExecutionResult(text=t("cursor_agent.not_installed"))

        self._ensure_workspace()
        self._write_mcp_config()

        if system_prompt:
            combined_prompt = "<system_context>\n" + system_prompt + "\n</system_context>\n\n" + prompt
        else:
            combined_prompt = prompt

        session_type = _resolve_session_type(trigger)
        is_resumable = session_type in _RESUMABLE_TRIGGERS
        resume_chat_id = _load_chat_id(self._anima_dir, session_type, thread_id) if is_resumable else None

        if resume_chat_id:
            logger.info(
                "Resuming cursor-agent session %s (type=%s, thread=%s)",
                resume_chat_id[:12],
                session_type,
                thread_id,
            )

        result, session_id, failed = await self._run_subprocess(combined_prompt, resume_chat_id=resume_chat_id)

        if failed and resume_chat_id:
            logger.warning(
                "Session resume failed (chat_id=%s), retrying with fresh session",
                resume_chat_id[:12],
            )
            _clear_chat_id(self._anima_dir, session_type, thread_id)
            result, session_id, _failed = await self._run_subprocess(combined_prompt, resume_chat_id=None)

        if session_id and is_resumable:
            _save_chat_id(self._anima_dir, session_id, session_type, thread_id)
            logger.debug("Saved cursor-agent chat_id %s for %s/%s", session_id[:12], session_type, thread_id)

        return result

    async def _run_subprocess(
        self,
        combined_prompt: str,
        *,
        resume_chat_id: str | None = None,
    ) -> tuple[ExecutionResult, str | None, bool]:
        """Spawn cursor-agent and parse its NDJSON output.

        Returns ``(result, session_id, failed)`` where *failed* is True
        when the process exited with a non-zero code for a non-auth reason.
        """
        cmd = self._build_command(combined_prompt, resume_chat_id=resume_chat_id)
        env = self._build_env()

        accumulated_text = ""
        tool_records: list[ToolCallRecord] = []
        session_id: str | None = None
        failed = False

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                async with asyncio.timeout(_DEFAULT_TIMEOUT_SECONDS):
                    assert proc.stdout is not None
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        if self._check_interrupted():
                            await self._kill_process(proc)
                            return (
                                ExecutionResult(
                                    text=accumulated_text or "[Session interrupted by user]",
                                    tool_call_records=tool_records,
                                ),
                                session_id,
                                False,
                            )

                        event = self._parse_ndjson_event(line.decode("utf-8", errors="replace").strip())
                        if event is None:
                            continue

                        etype = event.get("type", "")

                        if etype == "system" and event.get("subtype") == "init":
                            sid = event.get("session_id")
                            if sid:
                                session_id = str(sid)

                        elif etype == "assistant":
                            content_list = event.get("message", {}).get("content", [])
                            parts: list[str] = []
                            for item in content_list:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    parts.append(item.get("text", ""))
                                elif isinstance(item, str):
                                    parts.append(item)
                            if parts:
                                accumulated_text = "".join(parts)

                        elif etype == "tool_call":
                            subtype = event.get("subtype", "")
                            tc = event.get("tool_call", {})
                            if subtype == "completed":
                                record = self._extract_tool_record(tc)
                                if record:
                                    tool_records.append(record)

                        elif etype == "result":
                            result_text = event.get("result", "")
                            if result_text and not accumulated_text:
                                accumulated_text = result_text

            except TimeoutError:
                logger.warning("Cursor agent timed out after %ds", _DEFAULT_TIMEOUT_SECONDS)
                await self._kill_process(proc)
                timeout_msg = t("cursor_agent.timeout", timeout=_DEFAULT_TIMEOUT_SECONDS)
                return (
                    ExecutionResult(
                        text=accumulated_text + f"\n\n{timeout_msg}" if accumulated_text else timeout_msg,
                        tool_call_records=tool_records,
                    ),
                    session_id,
                    True,
                )

            stderr_bytes = await proc.stderr.read() if proc.stderr else b""
            await proc.wait()

            if proc.returncode != 0:
                failed = True
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")
                logger.warning(
                    "Cursor agent exited with code %d: %s",
                    proc.returncode,
                    stderr_text[:500],
                )
                if (
                    "auth" in stderr_text.lower()
                    or "login" in stderr_text.lower()
                    or "unauthorized" in stderr_text.lower()
                ):
                    return (ExecutionResult(text=t("cursor_agent.not_authenticated")), session_id, False)
                if not accumulated_text:
                    accumulated_text = f"[Cursor Agent Error (exit {proc.returncode}): {stderr_text[:500]}]"

        except FileNotFoundError:
            return (ExecutionResult(text=t("cursor_agent.not_installed")), None, True)
        except Exception as e:
            logger.exception("Cursor agent execution error")
            return (ExecutionResult(text=f"[Cursor Agent Error: {e}]"), None, True)

        replied_to = self._read_replied_to_file()
        return (
            ExecutionResult(
                text=accumulated_text,
                replied_to_from_transcript=replied_to,
                tool_call_records=tool_records,
            ),
            session_id,
            failed,
        )
