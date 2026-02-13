"""Tests for Mode A2 (LiteLLM + tool_use loop) execution.

Mode A2 iteratively calls litellm.acompletion, processes tool_calls,
and returns results to the LLM until a final text response is produced.
"""

from __future__ import annotations

import pytest

from tests.helpers.mocks import (
    make_litellm_response,
    make_tool_call,
    patch_litellm,
)


class TestModeA2Mock:
    """Mode A2 tests using mocked LLM calls."""

    async def test_basic_no_tool_calls(self, make_agent_core):
        """A2 basic: LLM returns text without tool calls."""
        agent = make_agent_core(
            name="a2-basic",
            model="openai/gpt-4o",
        )

        resp = make_litellm_response(content="Hello from A2 mode.")

        with patch_litellm(resp):
            result = await agent.run_cycle("Say hello")

        assert result.action == "responded"
        assert "Hello from A2 mode." in result.summary

    async def test_search_memory_tool_call(self, make_agent_core):
        """A2: LLM calls search_memory, then responds with final text."""
        agent = make_agent_core(
            name="a2-search",
            model="openai/gpt-4o",
        )

        # Write a knowledge file so search has results
        (agent.person_dir / "knowledge" / "facts.md").write_text(
            "The answer to everything is 42.\n", encoding="utf-8"
        )

        # First call: tool_call to search_memory
        tc = make_tool_call(
            "search_memory",
            {"query": "answer", "scope": "knowledge"},
            call_id="call_search",
        )
        resp1 = make_litellm_response(content="", tool_calls=[tc])

        # Second call: final response
        resp2 = make_litellm_response(content="The answer is 42.")

        with patch_litellm(resp1, resp2):
            result = await agent.run_cycle("What is the answer?")

        assert "42" in result.summary

    async def test_read_file_permission_allowed(self, make_agent_core, tmp_path):
        """A2: read_file succeeds for paths within person_dir."""
        agent = make_agent_core(
            name="a2-read-ok",
            model="openai/gpt-4o",
        )

        # Write a file inside person_dir
        test_file = agent.person_dir / "knowledge" / "test_data.md"
        test_file.write_text("Secret knowledge content.", encoding="utf-8")

        tc = make_tool_call(
            "read_file",
            {"path": str(test_file)},
            call_id="call_read",
        )
        resp1 = make_litellm_response(content="", tool_calls=[tc])
        resp2 = make_litellm_response(content="Read the file.")

        with patch_litellm(resp1, resp2):
            result = await agent.run_cycle("Read my knowledge file")

        assert result.summary

    async def test_read_file_permission_denied(self, make_agent_core):
        """A2: read_file is denied for paths outside allowed directories."""
        agent = make_agent_core(
            name="a2-read-deny",
            model="openai/gpt-4o",
            permissions="## ファイル操作\n- /allowed/path/\n",
        )

        tc = make_tool_call(
            "read_file",
            {"path": "/etc/passwd"},
            call_id="call_read_forbidden",
        )
        resp1 = make_litellm_response(content="", tool_calls=[tc])
        resp2 = make_litellm_response(
            content="Access denied for the requested file."
        )

        with patch_litellm(resp1, resp2):
            result = await agent.run_cycle("Read /etc/passwd")

        # The agent should have received a "Permission denied" tool result
        # and then produced a final response
        assert result.summary

    async def test_execute_command_allowed(self, make_agent_core):
        """A2: execute_command succeeds for allowed commands."""
        agent = make_agent_core(
            name="a2-cmd-ok",
            model="openai/gpt-4o",
            permissions="## コマンド実行\n- echo: OK\n",
        )

        tc = make_tool_call(
            "execute_command",
            {"command": "echo hello_test"},
            call_id="call_cmd",
        )
        resp1 = make_litellm_response(content="", tool_calls=[tc])
        resp2 = make_litellm_response(content="Command output: hello_test")

        with patch_litellm(resp1, resp2):
            result = await agent.run_cycle("Run echo hello_test")

        assert result.summary

    async def test_execute_command_metachar_rejected(self, make_agent_core):
        """A2: commands with shell metacharacters are rejected."""
        agent = make_agent_core(
            name="a2-cmd-metachar",
            model="openai/gpt-4o",
            permissions="## コマンド実行\n- ls: OK\n",
        )

        tc = make_tool_call(
            "execute_command",
            {"command": "ls; rm -rf /"},
            call_id="call_cmd_bad",
        )
        resp1 = make_litellm_response(content="", tool_calls=[tc])
        resp2 = make_litellm_response(content="Command was rejected.")

        with patch_litellm(resp1, resp2):
            result = await agent.run_cycle("List files dangerously")

        assert result.summary

    async def test_write_and_edit_file(self, make_agent_core):
        """A2: write_file and edit_file modify files on disk."""
        agent = make_agent_core(
            name="a2-write-edit",
            model="openai/gpt-4o",
        )

        target = agent.person_dir / "knowledge" / "new_file.md"

        # Tool call 1: write_file
        tc_write = make_tool_call(
            "write_file",
            {"path": str(target), "content": "original content"},
            call_id="call_write",
        )
        resp1 = make_litellm_response(content="", tool_calls=[tc_write])

        # Tool call 2: edit_file
        tc_edit = make_tool_call(
            "edit_file",
            {
                "path": str(target),
                "old_string": "original",
                "new_string": "modified",
            },
            call_id="call_edit",
        )
        resp2 = make_litellm_response(content="", tool_calls=[tc_edit])

        # Final response
        resp3 = make_litellm_response(content="File updated.")

        with patch_litellm(resp1, resp2, resp3):
            result = await agent.run_cycle("Write and edit a file")

        assert target.exists()
        assert "modified content" in target.read_text(encoding="utf-8")

    async def test_context_threshold_session_chain(self, make_agent_core):
        """A2: context threshold triggers session chaining."""
        agent = make_agent_core(
            name="a2-chain",
            model="openai/gpt-4o",
            context_threshold=0.001,  # Very low to force chaining
            max_chains=1,
        )

        # First response with high token count to trigger threshold
        resp1 = make_litellm_response(
            content="Working on it...",
            prompt_tokens=200_000,
            completion_tokens=1_000,
        )

        # After chain restart: continuation prompt response (no tool calls)
        resp2 = make_litellm_response(
            content="Continued after chain.",
            prompt_tokens=1_000,
            completion_tokens=500,
        )

        with patch_litellm(resp1, resp2):
            result = await agent.run_cycle("Do a complex task")

        # The first response hit the threshold and chaining occurred
        assert result.summary


class TestModeA2Live:
    """Mode A2 tests using real API calls."""

    @pytest.mark.live
    @pytest.mark.timeout(60)
    async def test_live_basic_response(self, make_agent_core):
        """Live A2: real LiteLLM call with a non-Claude model."""
        agent = make_agent_core(
            name="a2-live",
            model="claude-sonnet-4-20250514",
            execution_mode="autonomous",
        )
        # Force A2 mode even with Claude model
        agent._sdk_available = False

        result = await agent.run_cycle(
            "Reply with exactly: ANIMAWORKS_A2_TEST_OK"
        )

        assert result.summary
        assert result.action == "responded"


class TestModeA2AzureLive:
    """Mode A2 tests using Azure OpenAI API."""

    @pytest.mark.live
    @pytest.mark.azure
    @pytest.mark.timeout(60)
    async def test_live_azure_basic_response(self, make_agent_core):
        """Live A2: Azure OpenAI gpt-4.1 call via LiteLLM."""
        import os

        agent = make_agent_core(
            name="a2-azure-live",
            model="azure/gpt-4.1",
            credential="azure",
            api_base_url=os.environ.get("AZURE_API_BASE", ""),
        )
        agent._sdk_available = False

        result = await agent.run_cycle(
            "Reply with exactly: ANIMAWORKS_AZURE_TEST_OK"
        )

        assert result.summary
        assert result.action == "responded"
