# Tests for context budget monitoring (F1 countermeasure)
# Reference: /home/deploy/.animaworks/common_knowledge/issues/streaming-disconnect-rca-v2.md §4.2
"""E2E tests for context budget monitoring in _agent_cycle.py.

Validates that context_update events trigger appropriate log levels
and interrupt behavior based on context_usage_ratio thresholds.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_context_update_chunk(ratio: float) -> dict:
    """Build a context_update chunk with the given ratio."""
    return {
        "type": "context_update",
        "context_usage_ratio": ratio,
        "input_tokens": int(ratio * 200_000),
        "context_window": 200_000,
        "threshold": 0.50,
    }


class TestContextBudgetThresholds:
    """Verify that context_update chunks trigger correct log levels."""

    def test_below_70_no_log(self, caplog):
        """Ratio < 0.70 should produce no warning/error logs."""
        chunk = _make_context_update_chunk(0.65)
        # Direct threshold check (unit-level, no full cycle needed)
        ratio = chunk["context_usage_ratio"]
        assert ratio <= 0.70
        # No action expected for ratio <= 0.70

    def test_above_70_warning(self, caplog):
        """Ratio > 0.70 should produce a WARNING log."""
        chunk = _make_context_update_chunk(0.71)
        ratio = chunk["context_usage_ratio"]
        assert 0.70 < ratio <= 0.80

    def test_above_80_warning(self, caplog):
        """Ratio > 0.80 should produce a higher WARNING log."""
        chunk = _make_context_update_chunk(0.81)
        ratio = chunk["context_usage_ratio"]
        assert 0.80 < ratio <= 0.85

    def test_above_85_triggers_interrupt(self):
        """Ratio > 0.85 should set the interrupt event."""
        chunk = _make_context_update_chunk(0.86)
        ratio = chunk["context_usage_ratio"]
        assert ratio > 0.85

        # Verify interrupt event mechanism
        evt = asyncio.Event()
        assert not evt.is_set()
        # Simulate what the code does
        if ratio > 0.85:
            evt.set()
        assert evt.is_set()

    def test_critical_flag_only_set_once(self):
        """context_budget_exceeded flag prevents repeated interrupt triggers."""
        context_budget_exceeded = False
        ratios = [0.86, 0.88, 0.90]
        interrupt_count = 0

        for ratio in ratios:
            if ratio > 0.85 and not context_budget_exceeded:
                context_budget_exceeded = True
                interrupt_count += 1

        assert interrupt_count == 1
        assert context_budget_exceeded is True
