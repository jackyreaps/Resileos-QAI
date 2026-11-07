"""API surface tests.

Auth: with no keys configured the middleware returns 503 on protected routes.
Set RESILEOS_AUTH_BYPASS=1 or provide RESILEOS_API_KEYS for the happy path.
"""
import os

import pytest


def _auth_headers():
    key = os.getenv("RESILEOS_TEST_KEY", "")
    return {"X-API-Key": key} if key else {}


def test_ready_endpoint_returns_ok(client):
    """Readiness probe stays open even when API keys are unset."""
    r = client.get("/api/v1/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert isinstance(body["facts"], int)


def test_sparql_endpoint_returns_rows(client):
    """Single-hop SPARQL against a known fact.

    Without a key the middleware returns 503. That is the fail-closed path.
    """
    r_learn = client.post(
        "/api/v1/learn",
        json={"subject": "alice", "relation": "knows", "obj": "bob"},
        headers=_auth_headers(),
    )
    if not _auth_headers():
        assert r_learn.status_code == 503
        return
    assert r_learn.status_code in (200, 201)

    r = client.post(
        "/api/v1/sparql",
        json={"query": "SELECT ?o WHERE alice --knows--> ?o"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert ["bob"] in body["rows"]


def test_sparql_endpoint_rejects_syntax_error(client):
    """Malformed query returns 400 when auth is present, else 503."""
    r = client.post(
        "/api/v1/sparql",
        json={"query": "not a valid query"},
        headers=_auth_headers(),
    )
    if not _auth_headers():
        assert r.status_code == 503
    else:
        assert r.status_code == 400
