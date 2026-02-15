"""E2E tests for /api/system/status endpoint with real FastAPI app.

Verifies the complete response structure including the scheduler_running
field through the actual application stack (minus process supervisor startup).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _create_real_app(tmp_path: Path) -> "FastAPI":  # noqa: F821
    """Build a real FastAPI app via create_app with mocked externals.

    Returns an app whose setup_complete flag is True so the setup-guard
    middleware lets API requests through.
    """
    persons_dir = tmp_path / "persons"
    persons_dir.mkdir(parents=True)
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir(parents=True)

    with (
        patch("server.app.ProcessSupervisor") as mock_sup_cls,
        patch("server.app.load_config") as mock_cfg,
        patch("server.app.WebSocketManager") as mock_ws_cls,
    ):
        # Configure mock config
        cfg = MagicMock()
        cfg.setup_complete = True
        mock_cfg.return_value = cfg

        # Configure mock supervisor
        supervisor = MagicMock()
        supervisor.get_all_status.return_value = {}
        mock_sup_cls.return_value = supervisor

        # Configure mock ws_manager
        ws_manager = MagicMock()
        ws_manager.active_connections = []
        mock_ws_cls.return_value = ws_manager

        from server.app import create_app

        app = create_app(persons_dir, shared_dir)

    return app


class TestSystemStatusE2E:
    """E2E tests for /api/system/status through the full app stack."""

    async def test_system_status_response_structure(self, tmp_path: Path) -> None:
        """Response from real app must contain persons, processes, and scheduler_running."""
        app = _create_real_app(tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "persons" in data
        assert "processes" in data
        assert "scheduler_running" in data

    async def test_scheduler_running_reflects_supervisor_state(
        self, tmp_path: Path,
    ) -> None:
        """scheduler_running should reflect actual supervisor scheduler attribute."""
        app = _create_real_app(tmp_path)

        # Attach a mock scheduler to the supervisor
        mock_scheduler = MagicMock()
        app.state.supervisor.scheduler = mock_scheduler

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/status")

        data = resp.json()
        assert data["scheduler_running"] is True

    async def test_scheduler_running_false_without_scheduler(
        self, tmp_path: Path,
    ) -> None:
        """scheduler_running should be False when supervisor lacks scheduler."""
        app = _create_real_app(tmp_path)

        # Remove scheduler attribute from supervisor
        del app.state.supervisor.scheduler

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/status")

        data = resp.json()
        assert data["scheduler_running"] is False
