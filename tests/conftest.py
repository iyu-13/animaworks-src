"""Global test fixtures for AnimaWorks E2E tests.

Provides filesystem isolation, config cache management, and
mock/live switching for all test modules.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

from tests.helpers.filesystem import (
    create_person_dir,
    create_test_data_dir,
)

# Load .env at module level so API keys are available before fixtures run.
# main.py calls load_dotenv() for CLI usage; tests need it here.
load_dotenv()


# ── CLI options ───────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--mock",
        action="store_true",
        default=False,
        help="Force mock mode for all API calls",
    )


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def use_mock(request: pytest.FixtureRequest) -> bool:
    """Determine whether to use mocks or real API calls.

    Returns True when:
      - ``--mock`` flag is passed, OR
      - ``ANTHROPIC_API_KEY`` is not set in the environment
    """
    if request.config.getoption("--mock"):
        return True
    return not os.environ.get("ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def _skip_live_without_key(request: pytest.FixtureRequest, use_mock: bool) -> None:
    """Auto-skip ``@pytest.mark.live`` tests when in mock mode.

    Additional skip rules:
      - ``@pytest.mark.azure`` requires ``AZURE_API_KEY`` in environment
      - ``@pytest.mark.ollama`` requires ``OLLAMA_API_BASE`` in environment
    """
    if request.node.get_closest_marker("live") and use_mock:
        pytest.skip("Skipping live test: no API key or --mock flag set")
    if request.node.get_closest_marker("azure"):
        if not os.environ.get("AZURE_API_KEY"):
            pytest.skip("Skipping Azure test: AZURE_API_KEY not set")
    if request.node.get_closest_marker("ollama"):
        if not os.environ.get("OLLAMA_API_BASE"):
            pytest.skip("Skipping Ollama test: OLLAMA_API_BASE not set")


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated AnimaWorks runtime data directory.

    - Redirects ``ANIMAWORKS_DATA_DIR`` to a temp directory
    - Invalidates config and prompt caches before and after the test
    """
    from core.config import invalidate_cache
    from core.paths import _prompt_cache

    # Create the data directory structure
    d = create_test_data_dir(tmp_path)

    # Redirect all path resolution to the temp directory
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(d))

    # Invalidate caches to pick up the new data dir
    invalidate_cache()
    _prompt_cache.clear()

    yield d

    # Cleanup: invalidate caches again to avoid leaking between tests
    invalidate_cache()
    _prompt_cache.clear()


@pytest.fixture
def make_person(data_dir: Path):
    """Factory fixture to create person directories within the test data_dir.

    Returns a callable that creates a person directory and updates config.json.
    """
    from core.config import invalidate_cache

    def _make(
        name: str = "test-person",
        **kwargs: Any,
    ) -> Path:
        person_dir = create_person_dir(data_dir, name, **kwargs)
        # Invalidate config cache after changing config.json
        invalidate_cache()
        return person_dir

    return _make
