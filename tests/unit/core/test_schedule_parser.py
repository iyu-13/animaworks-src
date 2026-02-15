"""Unit tests for HTML comment exclusion in core.schedule_parser."""
from __future__ import annotations

import pytest

from core.schedule_parser import (
    parse_cron_md,
    parse_single_cron_task,
    parse_schedule,
    parse_heartbeat_config,
)
from core.schemas import CronTask


class TestHtmlCommentExclusion:
    """Tests for HTML comment stripping before cron.md parsing."""

    def test_html_comment_single_line_excluded(self):
        """A task fully wrapped in a single HTML comment block is excluded."""
        content = """\
<!-- ## Disabled Task (毎日 9:00 JST)
type: llm
Do something disabled -->
"""
        tasks = parse_cron_md(content)
        assert tasks == []

    def test_html_comment_multiline_excluded(self):
        """Multiple tasks inside one HTML comment block are all excluded."""
        content = """\
<!--
## Task A (毎日 8:00)
type: llm
Description A

## Task B (毎週金曜 17:00)
type: llm
Description B
-->
"""
        tasks = parse_cron_md(content)
        assert tasks == []

    def test_html_comment_partial_exclusion(self):
        """Only commented-out tasks are excluded; tasks outside remain."""
        content = """\
## Active Task (毎日 9:00 JST)
type: llm
I should be parsed.

<!-- ## Disabled Task (毎日 10:00 JST)
type: llm
I should NOT be parsed. -->

## Another Active (平日 8:00)
type: llm
I should also be parsed.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 2
        assert tasks[0].name == "Active Task"
        assert tasks[1].name == "Another Active"

    def test_no_comments_unchanged(self):
        """Content without HTML comments parses normally (regression)."""
        content = """\
## Daily Report (毎日 18:00 JST)
type: llm
Summarize the day.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].name == "Daily Report"
        assert tasks[0].schedule == "毎日 18:00 JST"
        assert tasks[0].type == "llm"
        assert "Summarize" in tasks[0].description

    def test_nested_comment_markers(self):
        """Greedy-minimal match: <!-- ... <!-- ... --> stops at first -->."""
        content = """\
<!-- outer <!-- inner --> still visible
## Visible Task (毎日 7:00)
type: llm
Should be parsed.
"""
        # The regex removes "<!-- outer <!-- inner -->" leaving
        # " still visible\n## Visible Task ..." which IS parsed.
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].name == "Visible Task"

    def test_command_type_with_args(self):
        """Command-type task with tool and args parses correctly."""
        content = """\
## Deploy (平日 2:00)
type: command
tool: run_deploy
args:
  env: staging
  dry_run: true
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.name == "Deploy"
        assert task.type == "command"
        assert task.tool == "run_deploy"
        assert task.args == {"env": "staging", "dry_run": True}

    def test_llm_type_basic(self):
        """Basic LLM-type task parsing works end-to-end."""
        content = """\
## Morning Standup（毎日 9:00 JST）
type: llm
Check yesterday's progress and plan today.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.name == "Morning Standup"
        assert task.schedule == "毎日 9:00 JST"
        assert task.type == "llm"
        assert "progress" in task.description
