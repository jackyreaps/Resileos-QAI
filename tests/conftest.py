"""Shared pytest fixtures for the API tests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient bound to the live app.

    Module-scoped so the singleton Titanos state (loaded once at import)
    is reused across the test file rather than reset per test.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from app import app
    return TestClient(app)
